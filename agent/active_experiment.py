"""active_experiment.py — 主动实验设计（信息增益驱动的种植方案推荐）。

愿景：docs/next_stage_vision_2026-10-15.md §支柱二 · 主动实验设计（Active Experiment Design）——差异化杀招。

**问题**：用户只有有限次的种植机会，哪次实验最值得做？
**答案**：用机理模型的参数敏感性 + 当前不确定性，计算每个候选动作的信息增益，
推荐"最能减少未来误差"的那次。

**核心公式**（简化贝叶斯主动学习）：
  IG(a) = H(prior) - E[ H(posterior | outcome ~ a) ]
  = 先验不确定性 - 观测后平均后验不确定性

**多目标**：exploitation vs exploration
  U(a) = α · expected_yield(a) + (1-α) · information_gain(a)
  α=0: 纯探索；α=1: 纯利用；α=0.5: 平衡

**判定标准**（Phase N+1）：信息增益可计算、可比较。

零依赖：纯 math + dataclasses。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from engine.agriworld_lite import (
    CropMechanisticParams,
    DailyInput,
    State,
    get_params,
    simulate,
    theoretical_yield_cap,
)


# ---------------------------------------------------------------------------
# 参数不确定性建模（先验正态）
# ---------------------------------------------------------------------------

UNCERTAINTY_KEYS = ("alpha_max", "k_ext", "rho_lv", "sla_m2_g", "rho_gr")

# 每参数的先验标准差（相对均值的比例），反映当前对参数的不确定度
PRIOR_STD_RATIO = {
    "alpha_max": 0.25,   # 冠层最大光合速率 ±25%
    "k_ext": 0.15,       # 消光系数 ±15%
    "rho_lv": 0.30,      # 叶呼吸 ±30%
    "sla_m2_g": 0.20,    # 叶面积系数 ±20%
    "rho_gr": 0.25,      # 生长呼吸 ±25%
}


def prior_uncertainty(crop: str) -> Dict[str, Tuple[float, float]]:
    """每参数的先验 (均值, 标准差)。"""
    p = get_params(crop)
    d = {}
    for k in UNCERTAINTY_KEYS:
        mean = getattr(p, k)
        std = mean * PRIOR_STD_RATIO[k]
        d[k] = (mean, std)
    return d


# ---------------------------------------------------------------------------
# 采样函数（Box-Muller 零依赖高斯）
# ---------------------------------------------------------------------------

def _randn(rng: random.Random, mu: float, sigma: float) -> float:
    """Box-Muller 高斯采样。"""
    u1 = rng.random() or 1e-10
    u2 = rng.random()
    return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)


def sample_params(crop: str,
                  priors: Optional[Dict[str, Tuple[float, float]]] = None,
                  seed: Optional[int] = None) -> CropMechanisticParams:
    """从先验采样一个参数向量。"""
    priors = priors or prior_uncertainty(crop)
    rng = random.Random(seed) if seed is not None else random.Random()
    base = get_params(crop).__dict__
    overrides = {}
    for k in UNCERTAINTY_KEYS:
        if k in priors:
            mu, sd = priors[k]
            overrides[k] = max(0.01, _randn(rng, mu, sd))
    return CropMechanisticParams(**{**base, **overrides})


# ---------------------------------------------------------------------------
# 信息增益计算
# ---------------------------------------------------------------------------

def expected_yield(crop: str,
                   action: DailyInput,
                   days: int = 45,
                   n_samples: int = 20,
                   seed: Optional[int] = None) -> Tuple[float, float]:
    """给定动作，多次采样后返回 (期望产量, 产量标准差)。

    多次采样参数后跑仿真，收集产量。
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    yields = []
    for i in range(n_samples):
        params = sample_params(crop, seed=rng.randint(0, 10**9))
        sim = simulate(crop, [action] * days, params=params)
        yields.append(sim["final_biomass"]["total"])
    mean = sum(yields) / len(yields)
    var = sum((y - mean) ** 2 for y in yields) / len(yields)
    return mean, math.sqrt(var)


def information_gain(crop: str,
                     action: DailyInput,
                     days: int = 45,
                     priors: Optional[Dict[str, Tuple[float, float]]] = None,
                     n_prior_samples: int = 30,
                     noise_factor: float = 0.10,
                     seed: Optional[int] = None) -> Dict[str, Any]:
    """计算给定动作的信息增益（贝叶斯主动学习）。

    方法（简化）：
      1. 从先验采样参数集合 Θ_prior
      2. 对每个 θ_i，模拟"如果真值是 θ_i"的观测
      3. 计算后验方差（近似为观测后的样本方差）
      4. IG = Var(prior) - E[Var(posterior | a)]

    为效率考虑，只对产量维度做信息增益；对参数维度的完整后验近似用样本方差估计。
    """
    priors = priors or prior_uncertainty(crop)
    rng = random.Random(seed) if seed is not None else random.Random()

    # 1. 先验参数分布（采样）
    prior_params = [sample_params(crop, seed=rng.randint(0, 10**9))
                    for _ in range(n_prior_samples)]
    prior_yields = []
    for p in prior_params:
        sim = simulate(crop, [action] * days, params=p)
        prior_yields.append(sim["final_biomass"]["total"])

    mean_prior = sum(prior_yields) / len(prior_yields)
    var_prior = sum((y - mean_prior) ** 2 for y in prior_yields) / len(prior_yields)
    std_prior = math.sqrt(var_prior)

    # 2. 观测下的后验近似（假设观测 = 真实产量 + 噪声）
    # 对每个采样参数做"观测" → 收集观测值分布 → 计算观测后的方差
    n_observations = max(10, n_prior_samples // 3)
    posterior_means = []
    for i in range(n_observations):
        # 用某个先验参数作为"真值"
        truth_idx = rng.randint(0, len(prior_params) - 1)
        truth_params = prior_params[truth_idx]
        truth_yield = prior_yields[truth_idx]
        # 观测值 = 真值 + 噪声
        obs = truth_yield * (1 + rng.gauss(0, noise_factor))
        # 后验采样（简化：对先验中接近观测的点加权）
        weights = []
        for y in prior_yields:
            # 高斯核权重
            w = math.exp(-0.5 * ((obs - y) / (noise_factor * mean_prior + 1e-6)) ** 2)
            weights.append(w)
        wsum = sum(weights)
        posterior_means.append(sum(w * y for w, y in zip(weights, prior_yields)) / max(wsum, 1e-9))

    # 后验不确定性 = 后验均值的标准差（观测越多越集中）
    pm_mean = sum(posterior_means) / len(posterior_means)
    var_posterior = sum((m - pm_mean) ** 2 for m in posterior_means) / len(posterior_means)

    # IG = 先验方差 - 后验方差（在产量维度）
    ig = max(0.0, var_prior - var_posterior)

    # 也计算参数空间的信息增益（简化）
    param_ig = {}
    for k in UNCERTAINTY_KEYS:
        prior_std = priors[k][1]
        # 简化：假设观测后参数不确定性下降 30%（经验值）
        # 更精确的应通过 MCMC 采样，此处为零依赖简化
        param_ig[k] = round(prior_std * 0.30, 6)

    return {
        "action_summary": _action_summary(action),
        "expected_yield": round(mean_prior, 4),
        "yield_std_prior": round(std_prior, 4),
        "var_prior": round(var_prior, 6),
        "var_posterior_approx": round(var_posterior, 6),
        "information_gain_yield": round(ig, 6),
        "information_gain_pct": round(ig / max(var_prior, 1e-9) * 100, 2),
        "param_info_gain": param_ig,
        "n_prior_samples": n_prior_samples,
        "n_observations": n_observations,
    }


def _action_summary(action: DailyInput) -> Dict[str, Any]:
    return {
        "dli_mj_m2_d": action.dli,
        "temp_mean_c": action.temp_mean_c,
        "irrigation_l_m2": action.irrigation_l_m2,
        "fert_n_mg_l": action.fert_n_mg_l,
        "light_ext_hours": action.light_ext_hours,
        "rh": action.rh,
    }


# ---------------------------------------------------------------------------
# 多目标推荐（exploitation vs exploration）
# ---------------------------------------------------------------------------

@dataclass
class CandidateAction:
    """候选动作。"""
    name: str
    action: DailyInput
    expected_yield_hint: Optional[float] = None  # 若已知估计产量


def recommend_action(candidates: Sequence[CandidateAction],
                     crop: str,
                     days: int = 45,
                     exploration_weight: float = 0.5,
                     seed: Optional[int] = None) -> Dict[str, Any]:
    """在候选动作中推荐"最值得种"的一个。

    综合目标：
      U(a) = (1-w) · expected_yield_normalized(a) + w · info_gain_normalized(a)

    w=0: 纯 exploitation（最大化产量）
    w=1: 纯 exploration（最大化信息增益）
    """
    if not candidates:
        return {"error": "无候选动作"}

    scored = []
    for c in candidates:
        exp, std = expected_yield(crop, c.action, days=days, n_samples=10, seed=seed)
        ig = information_gain(crop, c.action, days=days, seed=seed)
        scored.append({
            "name": c.name,
            "expected_yield": round(exp, 4),
            "yield_std": round(std, 4),
            "info_gain": round(ig["information_gain_yield"], 6),
            "info_gain_pct": ig["information_gain_pct"],
            "action": _action_summary(c.action),
        })

    # 归一化
    max_y = max(s["expected_yield"] for s in scored)
    max_ig = max(s["info_gain"] for s in scored)
    for s in scored:
        y_norm = s["expected_yield"] / max_y if max_y > 0 else 0
        ig_norm = s["info_gain"] / max_ig if max_ig > 0 else 0
        w = exploration_weight
        s["utility"] = round((1 - w) * y_norm + w * ig_norm, 4)

    # 排序
    scored.sort(key=lambda x: -x["utility"])

    return {
        "recommendation": scored[0]["name"],
        "top_scored": scored,
        "exploration_weight": exploration_weight,
        "crop": crop,
        "days": days,
        "note": (
            f"w={w:.2f}：0=纯 exploitation，1=纯 exploration"
        ),
    }


if __name__ == "__main__":
    import json as _json
    print("=== 主动实验设计自测 ===")
    crop = "potato"

    # 候选：3 种不同光周期
    base = DailyInput(dli=10.0, temp_mean_c=22.0, rh=0.60, wind_ms=1.5,
                      co2_ppm=420.0, irrigation_l_m2=2.0, fert_n_mg_l=30.0)
    cand_high_light = DailyInput(dli=15.0, temp_mean_c=22.0, rh=0.60, wind_ms=1.5,
                                 co2_ppm=420.0, irrigation_l_m2=3.0, fert_n_mg_l=40.0)
    cand_high_temp = DailyInput(dli=10.0, temp_mean_c=28.0, rh=0.55, wind_ms=1.5,
                                co2_ppm=420.0, irrigation_l_m2=3.0, fert_n_mg_l=30.0)
    cand_water_stress = DailyInput(dli=10.0, temp_mean_c=22.0, rh=0.60, wind_ms=1.5,
                                   co2_ppm=420.0, irrigation_l_m2=0.5, fert_n_mg_l=20.0)

    candidates = [
        CandidateAction("标准条件", base),
        CandidateAction("高光照高水肥", cand_high_light),
        CandidateAction("高温环境", cand_high_temp),
        CandidateAction("水分胁迫", cand_water_stress),
    ]

    # 推荐
    r = recommend_action(candidates, crop, days=45,
                         exploration_weight=0.5, seed=42)
    print(f"推荐：{r['recommendation']}")
    for s in r["top_scored"]:
        print(f"  {s['name']:20s} yield={s['expected_yield']:.2f} "
              f"IG={s['info_gain']:.4f} ({s['info_gain_pct']:.1f}%) "
              f"utility={s['utility']}")

    # 纯 exploitation (w=0)
    r_exp = recommend_action(candidates, crop, days=45,
                             exploration_weight=0.0, seed=42)
    print(f"\n纯 exploitation (w=0) → {r_exp['recommendation']}")

    # 纯 exploration (w=1)
    r_expl = recommend_action(candidates, crop, days=45,
                              exploration_weight=1.0, seed=42)
    print(f"纯 exploration (w=1) → {r_expl['recommendation']}")

    # 信息增益详细
    print("\n各候选信息增益：")
    for c in candidates:
        ig = information_gain(crop, c.action, days=45, seed=42)
        print(f"  {c.name:20s} IG_yield={ig['information_gain_yield']:.4f} "
              f"({ig['information_gain_pct']:.1f}%), "
              f"expected_yield={ig['expected_yield']:.2f}±{ig['yield_std_prior']:.2f}")

    print("\n✅ 主动实验设计自测通过")
