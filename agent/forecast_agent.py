"""
ForecastAgent - L2 模型 AI 层（预测系统：采收期 / 产量 / 风险）

职责：
  1. 采收期预测：start_date + 各阶段时长 + 分区气候（GDD-lite 修正）。
  2. 产量预测：基于 Env Recipe 环境完备度 + 分区气候适宜度 + 公开农艺基准的启发式估计。
  3. 风险预测：分区气候极端（霜冻/高温）+ 种植计划风险告警。

对标战略指引 L2：预测系统（产量/采收时间/风险）是决策引擎之上的关键能力。
也呼应 KrishiDisha（WOFOST+AquaCrop+DSSAT 集成）与 CropProphEU（产量/市场/风险 MCP）的思路——
但本项目零依赖，这里用**启发式**而非 mechanistic 模型，并显式标注 model=heuristic。

诚实边界（真实性红线）：
  - 产量为启发式估计（公开农艺基准 × 气候适宜度 × 环境完备度），非 WOFOST 机制模型结果。
  - 没有给出实测校准数据时，置信度压低，并标注「需 execution_log/outcome 回流校准」。
  - 不联网、不造数据。
"""

from __future__ import annotations

import json
import os
import datetime
from typing import Dict, Any, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ZONES = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")

# 常见阳台/家用作物单箱启发式基准产量（克/箱），来自公开农艺经验区间的中值。
# 明确为 heuristic，仅作量级估计，非品种级精确值。
_BASE_YIELD_G = {
    "番茄": 1500, "生菜": 300, "辣椒": 800, "黄瓜": 2000, "草莓": 400,
    "罗勒": 150, "薄荷": 120, "香菜": 100, "小白菜": 350, "菠菜": 300,
    "茄子": 1200, "番茄（樱桃）": 1000, "葱": 200, "蒜": 150, "空心菜": 400,
    "油麦菜": 350, "甜椒": 800, "圣女果": 1000, "番茄（大果）": 1500,
}

# 单株产量的启发式变异系数（P10/P90 相对 P50 的偏离比例）。
# 依据：品种间差异（大根 vs 小根胡萝卜约 2-3×）+ 环境波动（补光/通风差异）。
# 数值来自公开农艺经验区间（如胡萝卜 150-500g，樱桃番茄 500-1200g），
# 反映「单株产量」而非「单箱产量」的合理散布范围。
# 无匹配项时走 fallback（±40%）表示"没数据的作物更不确定"。
_BASE_YIELD_SPREAD_FRAC = {
    # 果菜类：品种间差异大，方差 ±35-45%
    "番茄": 0.4, "番茄（樱桃）": 0.45, "番茄（大果）": 0.4, "圣女果": 0.45,
    "辣椒": 0.4, "甜椒": 0.4, "茄子": 0.4, "黄瓜": 0.4,
    # 叶菜类：品种间差异小，方差 ±20-30%
    "生菜": 0.3, "小白菜": 0.25, "菠菜": 0.3, "空心菜": 0.35, "油麦菜": 0.3,
    "罗勒": 0.3, "薄荷": 0.3, "香菜": 0.35,
    # 果用类：单株产量受季节影响明显，方差 ±40%
    "草莓": 0.4,
    # 根茎类（fallback 已含胡萝卜）
    "葱": 0.3, "蒜": 0.3,
}
_DEFAULT_YIELD_SPREAD_FRAC = 0.4

# 生长周期变异系数：不同分区光照/昼夜温差会导致 ±10-15% 的周期波动。
# 依据：地中海番茄 120 天 → 冷凉区可能 140 天（+17%），亚热带可能 100 天（-17%）；
# 保守取 ±12%（比产量方差小，因为生长阶段边界相对稳健）。
_DURATION_SPREAD_FRAC = 0.12


def _load_zone_climate(zone_id: str) -> Optional[List[float]]:
    try:
        if os.path.exists(DEFAULT_ZONES):
            d = json.load(open(DEFAULT_ZONES, "r", encoding="utf-8"))
            zones = d.get("zones", {})
            z = zones.get(zone_id) or (zones[0] if isinstance(zones, list) else None)
            if isinstance(z, dict):
                cb = z.get("climate_baseline") or {}
                mm = cb.get("monthly_mean_c")
                if isinstance(mm, list) and mm:
                    return [float(x) for x in mm]
    except Exception:
        pass
    return None


def _add_days(start_date: str, days: int) -> Optional[str]:
    if not start_date:
        return None
    try:
        d = datetime.date.fromisoformat(start_date[:10])
        return (d + datetime.timedelta(days=days)).isoformat()
    except Exception:
        return None


def _conformal_interval_of(point_est_yield: float,
                           point_est_days: int,
                           alpha: float = 0.10) -> Dict[str, Any]:
    """M5-F1：为点估计生成 split conformal 严格覆盖率区间。

    校准集：AgriRecipeBench target_prediction 3 用例（引擎点估计 vs 期望值）。
    方法：split conformal（无分布假设，有限样本 1-α 覆盖率下界）。
    G2 阶段接入真实 execution_log/outcome 后校准集可增到数十上百条，
    q 值会更紧。

    诚实标注：
      - interval_method=split_conformal（区别于启发式散布区间）
      - coverage_guarantee=1-alpha（90% 覆盖率下界）
      - calibration_n=3（当前样本量；样本少时区间偏宽）
      - 若校准集为空，退化为点估计三度重复
    """
    try:
        from agent.conformal import get_default_calibrator, split_conformal_interval
        calib = get_default_calibrator(alpha=alpha)
        out: Dict[str, Any] = {
            "yield_estimate_g": split_conformal_interval(calib, point_est_yield),
            "adjusted_duration_days": split_conformal_interval(calib, float(point_est_days)),
            "calibration_source": "benchmarks/agri_recipe_bench/cases/case_{fanqie,luobo,shengcai}_*.json",
            "reference": "docs/per_module_deep_assessment_2026-10-13.md §M5-F1",
        }
        return out
    except Exception as e:  # noqa: BLE001
        # 保形预测失败不应阻塞主预测流程；返回降级标注
        return {
            "yield_estimate_g": {
                "p50": point_est_yield, "p10": point_est_yield, "p90": point_est_yield,
                "point": point_est_yield,
                "coverage_lower": point_est_yield, "coverage_upper": point_est_yield,
                "target_coverage": 0.0,
                "calibration_n": 0,
                "calibration_set_id": "unknown",
                "interval_semantics": "central_coverage_interval",
                "interval_method": "split_conformal_unavailable",
                "coverage_guarantee": 0.0,
                "error": f"conformal 降级: {e}",
            },
            "adjusted_duration_days": {
                "p50": point_est_days, "p10": point_est_days, "p90": point_est_days,
                "point": point_est_days,
                "coverage_lower": point_est_days, "coverage_upper": point_est_days,
                "target_coverage": 0.0,
                "calibration_n": 0,
                "calibration_set_id": "unknown",
                "interval_semantics": "central_coverage_interval",
                "interval_method": "split_conformal_unavailable",
                "coverage_guarantee": 0.0,
            },
        }


class ForecastAgent:
    """L2 预测 Agent —— 采收期 / 产量 / 风险"""

    NAME = "ForecastAgent"
    VERSION = "1.0"

    def estimate(
        self,
        crop: str = "",
        zone_id: str = "",
        start_date: str = "",
        growth_plan: Optional[Dict[str, Any]] = None,
        zone_climate: Optional[List[float]] = None,
        env_recipe: Optional[Dict[str, Any]] = None,
        adapt_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        growth_plan = growth_plan or {}
        phases = growth_plan.get("recommendation", {}).get("phases", [])

        # ---- 1. 采收期 ----
        total_days = 0
        for ph in phases:
            dr = ph.get("day_range", [0, 0])
            if isinstance(dr, (list, tuple)) and len(dr) == 2:
                total_days += max(0, int(dr[1]) - int(dr[0]) + 1)
        if total_days == 0:
            total_days = 90  # 默认一季约 90 天

        zone_mean = None
        if zone_climate:
            zone_mean = sum(zone_climate) / len(zone_climate)
        else:
            zone_mean = _load_zone_climate(zone_id)
            if zone_mean:
                zone_mean = sum(zone_mean) / len(zone_mean)

        crop_opt = 20.0
        if env_recipe:
            t = (env_recipe.get("environment", {}).get("temperature", {}) or {}).get("day_c")
            if t is not None:
                crop_opt = float(t)

        # GDD-lite：分区年均温低于作物适温 → GDD 累积慢 → 季节拉长（乘 >1 因子）；
        # 高于适温 → 累积快 → 季节压缩（乘 <1 因子）。
        climate_factor = 1.0
        if zone_mean is not None:
            climate_factor = max(0.7, min(1.3, 1.0 + (crop_opt - zone_mean) * 0.01))
        adjusted_days = max(1, round(total_days * climate_factor))
        harvest_date = _add_days(start_date, adjusted_days)

        # ---- 2. 产量 ----
        base = _BASE_YIELD_G.get(crop) or _BASE_YIELD_G.get(crop.replace("（", "").split("（")[0]) or 500
        suit = adapt_score if isinstance(adapt_score, (int, float)) else 0.7
        light_factor = 1.0
        env_present = bool(env_recipe)
        if env_recipe:
            ppfd = (env_recipe.get("environment", {}).get("light", {}) or {}).get("ppfd_umol")
            if ppfd:
                # 200-400 umol 为家用补光合理区；低于 150 压低，高于 600 不额外加成
                light_factor = max(0.6, min(1.1, ppfd / 300.0))
        yield_g = round(base * climate_factor * (0.55 + 0.45 * float(suit)) * light_factor)

        conf = 0.55
        if env_present:
            conf += 0.1
        if isinstance(adapt_score, (int, float)):
            conf += 0.05
        if zone_mean is not None:
            conf += 0.05
        conf = round(min(0.8, conf), 2)

        # ---- 2b. 置信区间（P10 / P50 / P90）----
        # 设计原则（诚实边界）：
        #   - 单点估计（yield_g / adjusted_days）保留为 P50，向后兼容
        #   - 区间来自启发式散布系数（_BASE_YIELD_SPREAD_FRAC / _DURATION_SPREAD_FRAC）
        #   - 输入越少（无 env_recipe / 无 adapt_score）→ 区间越宽
        #   - 区间宽度**不是概率意义上的 80% CI**（无真实分布），而是「引擎启发式不确定性」的量化
        #     ——这与 model=heuristic 的诚实标注一致
        spread = _BASE_YIELD_SPREAD_FRAC.get(crop) or _BASE_YIELD_SPREAD_FRAC.get(
            crop.replace("（", "").split("（")[0]
        ) or _DEFAULT_YIELD_SPREAD_FRAC
        # 数据越缺 → 越不确定：无 env_recipe 或无 adapt_score 时各放宽 25%
        uncertainty_uplift = 0.0
        if not env_present:
            uncertainty_uplift += 0.25
        if not isinstance(adapt_score, (int, float)):
            uncertainty_uplift += 0.15
        spread_eff = spread * (1.0 + uncertainty_uplift)
        yield_p10 = max(1, round(yield_g * (1.0 - spread_eff)))
        yield_p90 = round(yield_g * (1.0 + spread_eff))

        dur_p10 = max(1, round(adjusted_days * (1.0 - _DURATION_SPREAD_FRAC)))
        dur_p90 = round(adjusted_days * (1.0 + _DURATION_SPREAD_FRAC))

        harvest_p10 = _add_days(start_date, dur_p10) if start_date else None
        harvest_p90 = _add_days(start_date, dur_p90) if start_date else None

        # ---- 3. 风险 ----
        risks: List[Dict[str, Any]] = []
        if zone_mean is not None and zone_climate:
            if min(zone_climate) < 5:
                risks.append({"type": "frost", "severity": "warn",
                               "detail": "分区最冷月均温 %.1f℃ < 5℃，露地/阳台有霜冻风险，需入室或保温" % min(zone_climate)})
            if max(zone_climate) > 35:
                risks.append({"type": "heat", "severity": "warn",
                               "detail": "分区最热月均温 %.1f℃ > 35℃，高温抑制坐果，需遮阴通风" % max(zone_climate)})
        for alert in growth_plan.get("recommendation", {}).get("risk_alerts", []) or []:
            risks.append({"type": "plan_alert", "severity": "info", "detail": str(alert)})

        return {
            "evidence": {
                "crop": crop,
                "zone_id": zone_id,
                "phases": len(phases),
                "base_duration_days": total_days,
                "zone_mean_temp_c": round(zone_mean, 1) if zone_mean is not None else None,
                "crop_opt_temp_c": crop_opt,
                "env_recipe_present": env_present,
            },
            "confidence": {
                "match_quality": conf,
                "model": "heuristic",
                "note": "产量为公开农艺基准 × 气候适宜度 × 环境完备度的启发式估计，非 WOFOST 机制模型；需 execution_log/outcome 回流校准",
                "uncertainty": {
                    "method": "heuristic_spread_based",
                    "yield_spread_fraction": round(spread_eff, 3),
                    "duration_spread_fraction": _DURATION_SPREAD_FRAC,
                    "uncertainty_uplift": round(uncertainty_uplift, 3),
                    "note": "区间宽度=启发式散布系数 × 输入完备度惩罚；非概率 CI（无真实分布假设）",
                },
            },
            "constraints": {
                "needs_calibration": not (isinstance(adapt_score, (int, float)) and env_present),
            },
            "recommendation": {
                "harvest_date": harvest_date,
                "adjusted_duration_days": adjusted_days,
                "climate_factor": round(climate_factor, 3),
                "yield_estimate_g": yield_g,
                "risk_forecast": risks,
                # ---- 置信区间（P50 与上述单点估计一致，向后兼容）----
                "prediction_interval": {
                    "yield_estimate_g": {
                        "p50": yield_g,
                        "p10": yield_p10,
                        "p90": yield_p90,
                    },
                    "adjusted_duration_days": {
                        "p50": adjusted_days,
                        "p10": dur_p10,
                        "p90": dur_p90,
                    },
                    "harvest_date": {
                        "p50": harvest_date,
                        "p10": harvest_p10,
                        "p90": harvest_p90,
                    },
                    "interval_method": "heuristic_spread_based",
                    "note": "默认启发式散布区间；split_conformal 见 recommendation.conformal_interval（M5-F1）",
                },
                # ---- M5-F1：Split Conformal 严格覆盖率区间（无分布假设，1-α 保证）----
                # 与上面启发式区间并存；不替换以避免破坏既有客户端与 golden vectors。
                # 校准集来源：AgriRecipeBench target_prediction 3 用例（benchmarks/agri_recipe_bench/cases/）。
                # 引擎改动后需重新校准；见 scripts/data/golden_vectors/forecast_conformal.json。
                "conformal_interval": _conformal_interval_of(
                    point_est_yield=yield_g,
                    point_est_days=adjusted_days,
                ),
            },
        }

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """call_skill('harvest_forecast') 入口。"""
        return self.estimate(
            crop=payload.get("crop", ""),
            zone_id=payload.get("zone_id", ""),
            start_date=payload.get("start_date", ""),
            growth_plan=payload.get("growth_plan"),
            zone_climate=payload.get("zone_climate"),
            env_recipe=payload.get("env_recipe"),
            adapt_score=payload.get("adapt_score"),
        )
