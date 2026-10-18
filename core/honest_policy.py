"""core/honest_policy.py —— 诚实降级 / 拒识（abstention）策略层

S1.2 负例 B 类（诚实降级与拒识）的**真实校验器**。被
benchmarks/agri_recipe_bench/negative_runner.py 调用。

设计原则（诚实 AI 的"少做少说"纪律）：
  - 输入越贫乏 → 置信度越低、模型标注越偏向 rule_based（绝不伪装高置信）；
  - 观测漂移超阈 / 多源互斥 / 超出校准域 → 明确 abstain / flag，而不是硬猜；
  - 所有判据都是**确定性、可复算、可单测**的；不含任何"看起来聪明"的启发式。

每个函数返回结构化 verdict（bool 标记 + 触发理由 + 触发阈值），便于论文 Table
直接引用"系统在此条件下拒绝/降级的行为是确定性的"。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# B1  输入完备度 → 诚实置信度分级
# ---------------------------------------------------------------------------
def assess_input_completeness(
    observations: Optional[Dict[str, Any]] = None,
    env_recipe: Optional[Dict[str, Any]] = None,
    adapt_score: Optional[float] = None,
) -> Dict[str, Any]:
    """输入越贫乏 → 置信度越低、模型越偏向规则基线。

    判据（确定性、可复算）：
      - 3 信号齐备（obs + env + score）→ high / heuristic
      - 缺 1 个                       → medium / heuristic
      - 缺 2 个                       → low / rule_based
      - 全无（完全无观测输入）         → low / rule_based  ← B1 触发条件

    返回 verdict：confidence ∈ {high, medium, low}；model ∈ {heuristic, rule_based}。
    """
    has_obs = observations is not None
    has_env = bool(env_recipe)
    has_score = isinstance(adapt_score, (int, float))
    completeness = int(has_obs) + int(has_env) + int(has_score)

    if completeness >= 3:
        level, model = "high", "heuristic"
    elif completeness == 2:
        level, model = "medium", "heuristic"
    else:  # 0 或 1 信号：规则基线，不得给高置信推荐
        level, model = "low", "rule_based"

    return {
        "confidence": level,
        "model": model,
        "completeness": completeness,
        "signals": {"observations": has_obs, "env_recipe": has_env, "adapt_score": has_score},
    }


# ---------------------------------------------------------------------------
# B2  气候漂移 → 超校准域拒识（out-of-domain abstention）
# ---------------------------------------------------------------------------
def assess_climate_shift(
    shift_sd: Optional[float],
    threshold_sd: float = 3.0,
) -> Dict[str, Any]:
    """目标气候偏离历史校准域超过 threshold_sd（默认 3σ）→ 拒识。

    B2 触发条件：shift_sd=3.5 > 3.0 → out_of_domain=True。
    判据保守：3σ 是统计学公认的"超出常规模型支撑"阈值。
    """
    if shift_sd is None:
        return {"out_of_domain": False, "shift_sd": None, "threshold_sd": threshold_sd}
    try:
        s = float(shift_sd)
    except (TypeError, ValueError):
        return {"out_of_domain": False, "shift_sd": None, "threshold_sd": threshold_sd}
    return {"out_of_domain": s > threshold_sd, "shift_sd": s, "threshold_sd": threshold_sd}


# ---------------------------------------------------------------------------
# B3  数据源新鲜度 → stale 标记
# ---------------------------------------------------------------------------
def assess_source_freshness(
    max_age_years: Optional[float],
    limit_years: float = 3.0,
) -> Dict[str, Any]:
    """sources 中最新样本的年龄超过 limit_years（默认 3 年）→ stale。

    B3 触发条件：source_max_age_years=4 > 3 → stale=True。
    农业数据（土壤/气候/物候）3 年为公认的新鲜度上限。
    """
    if max_age_years is None:
        return {"stale": False, "reason": "no-sources"}
    try:
        age = float(max_age_years)
    except (TypeError, ValueError):
        return {"stale": False, "reason": "non-numeric-age"}
    return {
        "stale": age > limit_years,
        "max_age_years": age,
        "limit_years": limit_years,
    }


# ---------------------------------------------------------------------------
# B4  多源冲突 → 拒识（source_conflict）
# ---------------------------------------------------------------------------
def assess_source_conflict(
    sources: Optional[List[Dict[str, Any]]],
    conflict_delta: float = 10.0,
) -> Dict[str, Any]:
    """两源给出互斥的 Topt（差值 > conflict_delta）→ 拒识，不合并。

    B4 触发条件：sources=[{Topt:25},{Topt:40}]，差 15 > 10 → conflict=True。
    判据：Topt 相差 10℃ 已足以判定两源不可信（作物最适温度不可能差 10℃）。
    """
    if not sources or len(sources) < 2:
        return {"conflict": False, "reason": "fewer-than-2"}
    topts = [
        float(s["Topt"])
        for s in sources
        if isinstance(s, dict) and s.get("Topt") is not None
    ]
    if len(topts) < 2:
        return {"conflict": False, "reason": "no-Topt-pair"}
    spread = max(topts) - min(topts)
    return {
        "conflict": spread > conflict_delta,
        "min": min(topts),
        "max": max(topts),
        "spread": spread,
        "conflict_delta": conflict_delta,
    }


# ---------------------------------------------------------------------------
# B5  传感器自相矛盾 → flag（day_temp < night_temp）
# ---------------------------------------------------------------------------
def assess_sensor_consistency(
    day_temp_c: Optional[float],
    night_temp_c: Optional[float],
) -> Dict[str, Any]:
    """日温 < 夜温 → 传感器自相矛盾，标记数据异常。

    B5 触发条件：day_temp_c=15 < night_temp_c=22 → inconsistent=True。
    物理判据：日平均温不可能低于夜平均温（白昼升温、夜冷）。
    """
    if day_temp_c is None or night_temp_c is None:
        return {"inconsistent": False, "reason": "missing-reading"}
    try:
        d, n = float(day_temp_c), float(night_temp_c)
    except (TypeError, ValueError):
        return {"inconsistent": False, "reason": "non-numeric-reading"}
    return {
        "inconsistent": d < n,
        "day": d,
        "night": n,
        "delta": d - n,
    }


# ---------------------------------------------------------------------------
# B6  超出保形校准域 → uncalibrated 标记
# ---------------------------------------------------------------------------
def assess_calibration_support(
    distance_to_calib_set: Optional[str],
) -> Dict[str, Any]:
    """新样本偏离校准集支持区（>p99）→ 区间不得声称 90% 覆盖。

    B6 触发条件：distance_to_calib_set=">p99" → uncalibrated=True。
    判据：保形预测的覆盖率保证仅在**校准域内**成立；p99 外视为超出支撑。
    支持 ">p99"/"p99" 字符串或数值阈值（>99 视为超域）。
    """
    if distance_to_calib_set is None:
        return {"uncalibrated": False, "reason": "no-distance"}
    s = str(distance_to_calib_set).strip().lower()
    if "p99" in s:
        return {"uncalibrated": True, "distance": s}
    try:
        v = float(s)
        return {"uncalibrated": v > 99.0, "distance": v}
    except (TypeError, ValueError):
        return {"uncalibrated": False, "distance": s}
