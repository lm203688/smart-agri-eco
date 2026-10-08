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
