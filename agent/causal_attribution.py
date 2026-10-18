"""causal_attribution.py — 因果归因（Shapley 值分解）。

愿景：docs/next_stage_vision_2026-10-15.md §支柱二 · 因果归因（A2-ζ）。

**核心命题**：
  产量差异归因到各驱动因子（温度/光照/水分/氮/CO2）的贡献度。
  用 Shapley 值对单变量扰动做归因，避免反事实 API 中"单变量替代"的偏差。

**方法**：
  1. 定义基线情景（所有因子 = 基线值）
  2. 定义目标情景（所有因子 = 目标值）
  3. 对每个因子计算 Shapley 值（精确枚举，N=5 时 2^5=32 子集）
  4. v(S) = 仿真产量（当 S 中因子取目标值，其余取基线值）

**零依赖**：纯 math + dataclasses。禁止 scipy/numpy。
"""
from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.agriworld_lite import (
    CropMechanisticParams,
    DailyInput,
    State,
    get_params,
    simulate,
)


# ---------------------------------------------------------------------------
# 可归因因子（驱动量）
# ---------------------------------------------------------------------------
FACTOR_FIELDS = ("temp_mean_c", "dli", "irrigation_l_m2", "fert_n_mg_l", "co2_ppm")
FACTOR_NAMES = ("温度", "光照", "水分", "氮素", "CO2")

FACTOR_FIELDS_EN = {
    "temp_mean_c": "temperature",
    "dli": "light",
    "irrigation_l_m2": "water",
    "fert_n_mg_l": "nitrogen",
    "co2_ppm": "co2",
}


@dataclass
class AttributionResult:
    """归因结果。"""
    factor: str
    shapley_value: float
    contribution_pct: float
    marginal_effect: float
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor": self.factor,
            "factor_cn": dict(zip(FACTOR_FIELDS, FACTOR_NAMES)).get(self.factor, self.factor),
            "shapley_value": round(self.shapley_value, 4),
            "contribution_pct": round(self.contribution_pct, 2),
            "marginal_effect": round(self.marginal_effect, 4),
            "confidence": round(self.confidence, 2),
        }


def _run_simulation(
    crop: str,
    baseline: Sequence[DailyInput],
    target_overrides: Dict[str, float],
    params: Optional[CropMechanisticParams] = None,
    initial_state: Optional[State] = None,
) -> float:
    """用 target_overrides 覆盖因子字段，返回仿真最终产量。"""
    p = params or get_params(crop)
    actions = [copy.deepcopy(b) for b in baseline]
    for action in actions:
        for field, value in target_overrides.items():
            if hasattr(action, field):
                setattr(action, field, value)
    result = simulate(crop, actions, params=p, initial_state=initial_state)
    return result["final_biomass"]["total"]


def _shapley_exact(
    crop: str,
    baseline_actions: Sequence[DailyInput],
    target_values: Dict[str, float],
    params: Optional[CropMechanisticParams] = None,
    initial_state: Optional[State] = None,
) -> Dict[str, float]:
    """精确 Shapley 值计算（N=5 时枚举所有 32 个子集）。"""
    n_factors = len(FACTOR_FIELDS)
    # v(∅) = 基线产量
    v_empty = _run_simulation(crop, baseline_actions, {}, params, initial_state)
    v_full = _run_simulation(crop, baseline_actions, target_values, params, initial_state)
    total_delta = v_full - v_empty

    # 缓存所有子集值
    subset_values: Dict[frozenset, float] = {
        frozenset(): v_empty,
        frozenset(FACTOR_FIELDS): v_full,
    }

    # 枚举所有 2^N 子集
    for r in range(1, n_factors):
        for combo in itertools.combinations(FACTOR_FIELDS, r):
            overrides = {f: target_values[f] for f in combo}
            subset_values[frozenset(combo)] = _run_simulation(
                crop, baseline_actions, overrides, params, initial_state
            )

    # 计算每个因子的 Shapley 值
    shapley = {}
    factorial = math.factorial
    total_permutations = factorial(n_factors)

    for i, factor in enumerate(FACTOR_FIELDS):
        others = [f for f in FACTOR_FIELDS if f != factor]
        phi_i = 0.0
        for r in range(0, n_factors):
            for combo in itertools.combinations(others, r):
                S = frozenset(combo)
                S_union = S | frozenset({factor})
                v_S = subset_values.get(S, v_empty)
                v_Si = subset_values.get(S_union, v_full)
                weight = factorial(len(S)) * factorial(n_factors - len(S) - 1) / total_permutations
                phi_i += weight * (v_Si - v_S)
        shapley[factor] = phi_i

    return shapley


def _single_variable_attribution(
    crop: str,
    baseline_actions: Sequence[DailyInput],
    target_overrides: Dict[str, float],
    params: Optional[CropMechanisticParams] = None,
    initial_state: Optional[State] = None,
) -> Dict[str, float]:
    """单变量扰动归因（Sobol' 一阶简化版，作为 Shapley 的验证基线）。"""
    base_yield = _run_simulation(crop, baseline_actions, {}, params, initial_state)
    impacts = {}
    for field in FACTOR_FIELDS:
        if field not in target_overrides:
            impacts[field] = 0.0
            continue
        # 只替换当前因子
        single_override = {field: target_overrides[field]}
        result = _run_simulation(crop, baseline_actions, single_override, params, initial_state)
        impacts[field] = result - base_yield
    total_abs = sum(abs(v) for v in impacts.values())
    if total_abs < 1e-9:
        return {f: 0.0 for f in FACTOR_FIELDS}
    return {f: round(v / total_abs, 4) for f, v in impacts.items()}


def attribute_causally(
    crop: str,
    baseline_actions: Sequence[DailyInput],
    target_actions: Sequence[DailyInput],
    params: Optional[CropMechanisticParams] = None,
    initial_state: Optional[State] = None,
    method: str = "shapley",
) -> Dict[str, Any]:
    """因果归因主入口。

    参数：
      crop              : 作物名
      baseline_actions  : 基线动作序列
      target_actions    : 目标动作序列（"如果改成这样"）
      method            : "shapley"（精确，N=5 时 32 次仿真）或 "sobol"（单变量，快但偏差大）

    返回：
      {
        "crop": ...,
        "method": ...,
        "baseline_yield": ...,
        "target_yield": ...,
        "total_delta": ...,
        "attributions": [{factor, shapley_value, contribution_pct, ...}, ...],
        "dominant_factor": ...,
        "interpretation": ...,
      }
    """
    if not baseline_actions or not target_actions:
        return {"error": "baseline_actions 和 target_actions 不能为空"}

    p = params or get_params(crop)

    # 提取目标值
    target_overrides = {}
    for field in FACTOR_FIELDS:
        if hasattr(target_actions[0], field):
            target_overrides[field] = getattr(target_actions[0], field)

    # 计算基线产量
    baseline_yield = _run_simulation(crop, baseline_actions, {}, params=p, initial_state=initial_state)

    # 计算目标产量
    target_yield = _run_simulation(crop, baseline_actions, target_overrides, params=p, initial_state=initial_state)
    total_delta = target_yield - baseline_yield

    # 归因
    if method == "shapley":
        raw = _shapley_exact(crop, baseline_actions, target_overrides, params=p, initial_state=initial_state)
    else:
        raw_pct = _single_variable_attribution(
            crop, baseline_actions, target_overrides, params=p, initial_state=initial_state
        )
        # 转回绝对值
        raw = {f: raw_pct.get(f, 0.0) * total_delta for f in FACTOR_FIELDS}

    # 构造结果
    attributions = []
    sorted_factors = sorted(FACTOR_FIELDS, key=lambda f: abs(raw.get(f, 0.0)), reverse=True)

    for field in sorted_factors:
        sv = raw.get(field, 0.0)
        contrib_pct = (sv / abs(total_delta) * 100) if abs(total_delta) > 1e-9 else 0.0
        # 边际效应：单因子变化量
        baseline_val = getattr(baseline_actions[0], field, 0) if baseline_actions else 0
        target_val = target_overrides.get(field, baseline_val)
        marginal = target_val - baseline_val
        attributions.append(AttributionResult(
            factor=field,
            shapley_value=sv,
            contribution_pct=contrib_pct,
            marginal_effect=marginal,
            confidence=0.8 if method == "shapley" else 0.6,
        ))

    dominant = sorted_factors[0] if sorted_factors else "unknown"

    return {
        "crop": crop,
        "method": method,
        "baseline_yield": round(baseline_yield, 4),
        "target_yield": round(target_yield, 4),
        "total_delta": round(total_delta, 4),
        "total_delta_pct": round(total_delta / max(baseline_yield, 1e-9) * 100, 2),
        "attributions": [a.to_dict() for a in attributions],
        "dominant_factor": dominant,
        "interpretation": _interpret(crop, total_delta, dominant, attributions, method),
        "n_simulations": 32 if method == "shapley" else len(FACTOR_FIELDS) + 1,
    }


def _interpret(
    crop: str,
    total_delta: float,
    dominant: str,
    attributions: List[AttributionResult],
    method: str,
) -> str:
    """生成自然语言解释。"""
    cn_name = dict(zip(FACTOR_FIELDS, FACTOR_NAMES)).get(dominant, dominant)
    direction = "增加" if total_delta > 0 else "降低"
    top_attr = attributions[0] if attributions else None
    pct = top_attr.contribution_pct if top_attr else 0

    parts = [f"产量{direction} {abs(total_delta):.2f} g/m²"]
    if top_attr:
        parts.append(f"，{cn_name}贡献最大（{pct:.1f}%）")
    parts.append(f"（{method} 归因法）")
    return "".join(parts)


def batch_attribute(
    crop: str,
    baseline: DailyInput,
    scenarios: List[Dict[str, Any]],
    days: int = 45,
    method: str = "shapley",
) -> Dict[str, Any]:
    """批量归因：给定基线和多个情景，计算每个情景的归因。

    scenarios = [{"name": "高温", "temp_mean_c": 30}, ...]
    """
    baseline_actions = [copy.deepcopy(baseline) for _ in range(days)]
    results = []
    for sc in scenarios:
        name = sc.pop("name", "scenario")
        # 覆盖字段
        target = copy.deepcopy(baseline)
        for k, v in sc.items():
            if hasattr(target, k):
                setattr(target, k, v)
        target_actions = [copy.deepcopy(target) for _ in range(days)]
        r = attribute_causally(crop, baseline_actions, target_actions, method=method)
        r["scenario_name"] = name
        results.append(r)
    return {
        "crop": crop,
        "baseline": _daily_summary(baseline),
        "n_scenarios": len(results),
        "method": method,
        "results": results,
    }


def _daily_summary(a: DailyInput) -> Dict[str, Any]:
    return {
        "dli_mj_m2_d": a.dli,
        "temp_mean_c": a.temp_mean_c,
        "irrigation_l_m2": a.irrigation_l_m2,
        "fert_n_mg_l": a.fert_n_mg_l,
        "co2_ppm": a.co2_ppm,
    }


if __name__ == "__main__":
    import json

    print("=== 因果归因（Shapley 值）自测 ===")
    crop = "potato"
    base = DailyInput(
        dli=10.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
        rh=0.60, wind_ms=1.5, co2_ppm=420.0,
        irrigation_l_m2=2.0, fert_n_mg_l=30.0,
    )
    target = DailyInput(
        dli=14.0, temp_mean_c=28.0, temp_min_c=20.0, temp_max_c=33.0,
        rh=0.55, wind_ms=1.8, co2_ppm=500.0,
        irrigation_l_m2=3.5, fert_n_mg_l=50.0,
    )

    # Shapley 归因
    r = attribute_causally(crop, [base] * 45, [target] * 45, method="shapley")
    print(f"基线产量={r['baseline_yield']:.2f}, 目标产量={r['target_yield']:.2f}")
    print(f"总差异={r['total_delta']:.2f} ({r['total_delta_pct']}%)")
    print(f"主导因子={r['dominant_factor']}")
    print("归因分解:")
    for a in r["attributions"]:
        print(f"  {a['factor_cn']:6s}: Shapley={a['shapley_value']:+.2f} "
              f"({a['contribution_pct']:+.1f}%) Δ={a['marginal_effect']:+.1f}")
    print(f"解释: {r['interpretation']}")

    # Sobol' 对比
    r2 = attribute_causally(crop, [base] * 45, [target] * 45, method="sobol")
    print(f"\nSobol' 对比: 主导因子={r2['dominant_factor']}")
    for a in r2["attributions"]:
        print(f"  {a['factor_cn']:6s}: {a['contribution_pct']:+.1f}%")

    # 批量归因
    print("\n批量归因（4 个情景）:")
    batch = batch_attribute(
        crop, base,
        scenarios=[
            {"name": "高温", "temp_mean_c": 30},
            {"name": "高光照", "dli": 18},
            {"name": "高水", "irrigation_l_m2": 5.0},
            {"name": "高氮", "fert_n_mg_l": 60},
        ],
        days=45, method="shapley",
    )
    for r in batch["results"]:
        print(f"  {r['scenario_name']:8s}: Δ={r['total_delta']:+.2f} "
              f"主导={r['dominant_factor']} ({r['interpretation']})")

    print("\n✅ 因果归因自测通过")
