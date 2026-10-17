"""agriworld_gradients.py — AgriWorld-Lite 解析梯度引擎 + 有限差分 golden 测试。

愿景：docs/next_stage_vision_2026-10-15.md §支柱一 · 关键设计：可解析梯度。

三重收益：
  1. 参数校准（贝叶斯 MAP 用解析梯度做坐标下降）
  2. 最优控制（MPC：模型预测控制给出最优动作）
  3. 敏感性分析（哪个参数最值得标定 → 主动实验设计）

设计要点：
  - 零依赖：纯 math，禁止 autograd/PyTorch/JAX
  - 数值稳定：解析梯度对零/负输入做防护
  - Golden 测试：解析梯度 vs 有限差分相对误差 < 1e-4（含数值稳定余量）

接口：
  gradient_a_wrt_k_ext(...)         : ∂A/∂k_ext
  gradient_a_wrt_alpha_max(...)     : ∂A/∂α_max（固定 k_i 系数形式）
  gradient_respiration_wrt_*        : 呼吸的三种敏感度
  gradient_et_wrt_*                 : 蒸腾的 LAI/T/VPD 敏感度
"""
from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from engine.agriworld_lite import (
    CropMechanisticParams,
    DailyInput,
    State,
    light_half_saturation,
    get_params,
    light_interception,
    photosynthesis_canopy,
    photosynthesis_gradient_lai,
    respiration,
    transpiration_pmp,
    water_stress_factor,
    temp_factor,
    vp_from_rh,
)


# ---------------------------------------------------------------------------
# 解析梯度（∂A/∂k_ext, ∂A/∂α_max）
# ---------------------------------------------------------------------------

def gradient_a_wrt_k_ext(i0_par_kj: float, lai: float, co2_ppm: float,
                         t_c: float, theta: float,
                         p: CropMechanisticParams) -> float:
    """∂A/∂k_ext = ∂A/∂I_abs · ∂I_abs/∂k_ext"""
    if i0_par_kj <= 0 or lai <= 0:
        return 0.0
    i_abs = light_interception(i0_par_kj, lai, p.k_ext)
    # dI_abs/dk = I_0 · LAI · exp(−k·LAI)
    d_iabs_d_k = i0_par_kj * lai * math.exp(-p.k_ext * lai)
    k_i = light_half_saturation(p.alpha_max)
    f_light_grad = k_i / (i_abs + k_i) ** 2
    f_temp = temp_factor(t_c, p.t_opt_c, p.t_max_c)
    f_water = water_stress_factor(theta, 0.30)
    ci = co2_ppm
    c_factor = max(0.0, (ci - p.c_star) / (ci + p.k_m)) if ci > p.c_star else 0.0
    return p.alpha_max * f_light_grad * f_temp * f_water * c_factor * d_iabs_d_k


def gradient_a_wrt_alpha_max(i0_par_kj: float, lai: float, co2_ppm: float,
                             t_c: float, theta: float,
                             p: CropMechanisticParams) -> float:
    """∂A/∂α_max 的"系数敏感度"（固定 k_i 时的形式）。

    用途：MAP 参数反演时，α_max 对 A 的主效应。
    注：k_i = α_max · 30 与 α_max 强耦合，严格全链式会让本梯度包含 k_i 的隐式影响；
    此处给的是"若 α_max 只作为线性系数"下的解析形式，与贝叶斯校准的用途匹配。
    """
    if i0_par_kj <= 0 or lai <= 0:
        return 0.0
    i_abs = light_interception(i0_par_kj, lai, p.k_ext)
    k_i = light_half_saturation(p.alpha_max)
    f_light = i_abs / (i_abs + k_i)
    f_temp = temp_factor(t_c, p.t_opt_c, p.t_max_c)
    f_water = water_stress_factor(theta, 0.30)
    ci = co2_ppm
    c_factor = max(0.0, (ci - p.c_star) / (ci + p.k_m)) if ci > p.c_star else 0.0
    return f_light * f_temp * f_water * c_factor


# ---------------------------------------------------------------------------
# 呼吸梯度
# ---------------------------------------------------------------------------

def gradient_respiration_wrt_biomass(maintenance_base: float, t_c: float,
                                     organ_biomass: float,
                                     t_ref: float = 20.0,
                                     q10: float = 2.0) -> float:
    """∂R/∂W = ρ · q10^((T−T_ref)/10)"""
    if organ_biomass <= 0:
        return 0.0
    return maintenance_base * (q10 ** ((t_c - t_ref) / 10.0))


def gradient_respiration_wrt_rho(organ_biomass: float, t_c: float,
                                 t_ref: float = 20.0,
                                 q10: float = 2.0) -> float:
    """∂R/∂ρ = W · q10^((T−T_ref)/10)"""
    if organ_biomass <= 0:
        return 0.0
    return organ_biomass * (q10 ** ((t_c - t_ref) / 10.0))


def gradient_respiration_wrt_temp(maintenance_base: float, organ_biomass: float,
                                  t_c: float, t_ref: float = 20.0,
                                  q10: float = 2.0) -> float:
    """∂R/∂T = ρ · W · q10^((T−T_ref)/10) · ln(q10) / 10"""
    if organ_biomass <= 0:
        return 0.0
    return (maintenance_base * organ_biomass * (q10 ** ((t_c - t_ref) / 10.0))
            * math.log(q10) / 10.0)


# ---------------------------------------------------------------------------
# 蒸腾梯度
# ---------------------------------------------------------------------------

def gradient_et_wrt_lai(inp: DailyInput, state: State, p: CropMechanisticParams) -> float:
    """∂ET/∂LAI = 3.5·dli·vp·temp·g_c · (1/4) · 1_{LAI<4}"""
    if state.lai <= 0.01 or state.lai >= 4.0:
        return 0.0
    vp = vp_from_rh(inp.temp_mean_c, inp.rh)
    dli_factor = min(inp.dli, 20.0) / 10.0
    vp_factor = min(vp / 1000.0, 1.5)
    temp_factor_val = max(0.0, min(1.0 + 0.03 * (inp.temp_mean_c - 20.0), 1.5))
    water_factor = min(state.theta / 0.15, 1.0)
    g_canopy_factor = p.g_canopy / 15.0
    return (3.5 * dli_factor * vp_factor * temp_factor_val * (1.0 / 4.0)
            * water_factor * g_canopy_factor)


def gradient_et_wrt_g_canopy(inp: DailyInput, state: State, p: CropMechanisticParams) -> float:
    """∂ET/∂g_canopy = ET / g_canopy（线性关系）"""
    et = transpiration_pmp(inp, state, p)
    return et / p.g_canopy if p.g_canopy > 0 else 0.0


def gradient_et_wrt_temp(inp: DailyInput, state: State, p: CropMechanisticParams) -> float:
    """∂ET/∂T：温度同时影响 temp_factor 和 vp_factor（通过水汽压）。

    ET = 3.5·dli·vp·temp·lai·wf·gf
      temp = 1 + 0.03·(T-20)
      vp = min(es(T)·(1-RH)/1000, 1.5)

    dET/dT = ET·0.03/temp + 3.5·dli·temp·wf·gf·dVP_factor/dT
    """
    t = inp.temp_mean_c
    temp_factor_val = 1.0 + 0.03 * (t - 20.0)
    if temp_factor_val <= 0:
        return 0.0
    et = transpiration_pmp(inp, state, p)
    # 第一项：temp_factor 的显式温度导数
    term1 = et * 0.03 / temp_factor_val
    # 第二项：VP 因子通过水汽压的隐式温度导数
    es_pa = 0.6108 * math.exp(17.27 * t / (t + 237.3)) * 1000.0
    d_es_d_t = (es_pa * 17.27 * 237.3 / (t + 237.3) ** 2)
    d_vp_d_t = (1 - inp.rh) * d_es_d_t
    vp_kpa = es_pa * (1 - inp.rh) / 1000.0
    d_vp_factor_d_t = d_vp_d_t / 1000.0 if vp_kpa < 1.5 else 0.0
    dli_factor = min(inp.dli, 20.0) / 10.0
    lai_factor = max(0.1, min(state.lai / 4.0, 1.0))
    water_factor = min(state.theta / 0.15, 1.0)
    g_canopy_factor = p.g_canopy / 15.0
    term2 = (3.5 * dli_factor * temp_factor_val * lai_factor
             * water_factor * g_canopy_factor * d_vp_factor_d_t)
    return term1 + term2


def gradient_et_wrt_vp(inp: DailyInput, state: State, p: CropMechanisticParams) -> float:
    """∂ET/∂VPD = ET · (1/VPD) 当 VPD < 1500 Pa（线性区）"""
    et = transpiration_pmp(inp, state, p)
    vp = vp_from_rh(inp.temp_mean_c, inp.rh)
    if vp <= 0 or vp >= 1500:
        return 0.0
    return et / vp


# ---------------------------------------------------------------------------
# 一维有限差分（黄金基准）
# ---------------------------------------------------------------------------

def finite_diff(f, x: float, eps: float = 1e-5) -> float:
    """中心差分：(f(x+ε) − f(x−ε)) / (2ε)。"""
    return (f(x + eps) - f(x - eps)) / (2 * eps)


def relative_error(analytic: float, fd: float, tol: float = 1e-9) -> float:
    """相对误差 |a−f| / max(|a|,|f|,tol)。"""
    denom = max(abs(analytic), abs(fd), tol)
    return abs(analytic - fd) / denom


# ---------------------------------------------------------------------------
# Golden 测试：解析梯度 vs 有限差分
# ---------------------------------------------------------------------------

def run_gradient_golden_tests() -> Dict[str, Any]:
    """对每个解析梯度做 FD 对照，返回结构化结果。"""
    p = get_params("potato")
    i0 = 4500.0      # kJ·m⁻²·d⁻¹ PAR
    lai = 1.5
    co2 = 420.0
    t_c = 22.0
    theta = 0.30
    results: Dict[str, Any] = {"tests": [], "passed": 0, "failed": 0}

    # --- 测试 1：∂A/∂LAI ---
    def a_at_l(l):
        return photosynthesis_canopy(
            light_interception(i0, l, p.k_ext), co2, t_c, theta, p)
    analytic = photosynthesis_gradient_lai(i0, lai, co2, t_c, theta, p)
    fd = finite_diff(a_at_l, lai, eps=1e-4)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dA/dLAI", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 2：∂A/∂k_ext ---
    def a_at_k(k):
        return photosynthesis_canopy(
            light_interception(i0, lai, k), co2, t_c, theta, p)
    analytic = gradient_a_wrt_k_ext(i0, lai, co2, t_c, theta, p)
    fd = finite_diff(a_at_k, p.k_ext, eps=1e-6)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dA/dk_ext", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 3：∂R/∂W ---
    rho_lv = p.rho_lv
    def r_at_w(w):
        return respiration(rho_lv, t_c, 20.0, 2.0, w)
    analytic = gradient_respiration_wrt_biomass(rho_lv, t_c, 3.0)
    fd = finite_diff(r_at_w, 3.0, eps=1e-6)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dR/dW", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 4：∂R/∂T ---
    def r_at_t(t):
        return respiration(rho_lv, t, 20.0, 2.0, 3.0)
    analytic = gradient_respiration_wrt_temp(rho_lv, 3.0, t_c)
    fd = finite_diff(r_at_t, t_c, eps=1e-4)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dR/dT", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 5：∂R/∂ρ ---
    def r_at_rho(rho):
        return respiration(rho, t_c, 20.0, 2.0, 3.0)
    analytic = gradient_respiration_wrt_rho(3.0, t_c)
    fd = finite_diff(r_at_rho, rho_lv, eps=1e-6)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dR/drho", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 6：∂ET/∂LAI ---
    inp = DailyInput(dli=10.0, temp_mean_c=22.0, rh=0.60, wind_ms=1.5)
    def et_at_lai(l):
        s = State(lai=l)
        return transpiration_pmp(inp, s, p)
    analytic = gradient_et_wrt_lai(inp, State(lai=lai), p)
    fd = finite_diff(et_at_lai, lai, eps=1e-4)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dET/dLAI", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-4,
    })

    # --- 测试 7：∂ET/∂T ---
    def et_at_t(t):
        inp2 = DailyInput(dli=10.0, temp_mean_c=t, rh=0.60, wind_ms=1.5)
        return transpiration_pmp(inp2, State(lai=lai), p)
    analytic = gradient_et_wrt_temp(inp, State(lai=lai), p)
    fd = finite_diff(et_at_t, t_c, eps=1e-3)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dET/dT", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-3,
    })

    # --- 测试 8：∂ET/∂VPD (通过 RH 扰动) ---
    # VPD = es·(1-RH)，∂VPD/∂RH = -es；所以 ∂ET/∂VPD = -∂ET/∂RH / es
    def et_at_rh(rh):
        inp2 = DailyInput(dli=10.0, temp_mean_c=t_c, rh=rh, wind_ms=1.5)
        return transpiration_pmp(inp2, State(lai=lai), p)
    d_et_d_rh = finite_diff(et_at_rh, 0.60, eps=1e-4)
    es = 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3)) * 1000.0
    analytic = gradient_et_wrt_vp(inp, State(lai=lai), p)
    fd = -d_et_d_rh / es  # 链式：∂ET/∂VPD = ∂ET/∂RH / (∂VPD/∂RH)
    err = relative_error(analytic, fd)
    results["tests"].append({
        "name": "dET/dVPD", "analytic": round(analytic, 8), "fd": round(fd, 8),
        "rel_err": err, "passed": err < 1e-3,
    })

    for t in results["tests"]:
        if t["passed"]:
            results["passed"] += 1
        else:
            results["failed"] += 1
    results["total"] = len(results["tests"])
    results["all_pass"] = results["failed"] == 0
    return results


if __name__ == "__main__":
    import json
    r = run_gradient_golden_tests()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    assert r["all_pass"], "梯度 golden 测试未通过"
    print(f"\n✅ 全部 {r['passed']}/{r['total']} 梯度 golden 测试通过")
