"""SeasonAgent — 季节/物候层按需技能（零依赖，stdlib-only）。

承接 docs/opensource_scan_complementary.md 的 B1（WOFOST 积温物候）+ B2（霜冻锚定播期窗口），
给 growth_agent 补『何时种 / 长多快』这两块此前完全缺失的微观推演能力。

三种模式（payload.mode）：
  1) "planting_window"：给 12 个月均温 → 无霜期 + 各作物播种窗口（默认模式）
  2) "stage_days"：给作物 + 日均温 → 出苗/开花/成熟天数
  3) "calendar"：给 USDA 区 + 日期 → 查外部日历（需 data/plant_calendar.json，当前无数据）

数据溯源：
  - 物候参数：ajwdewit/WOFOST_crop_parameters（wofost81 分支，EUPL 1.2，需署名），
    移植于 data/wofost_phenology_reference.json，仅 7 种作物。
  - 气候输入：由调用方提供（WorldClim / Open-Meteo / 本地气象站），本 Agent 不内置气候数据。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

try:
    from .phenology import estimate_stage_days, covered_crops
    from .plant_calendar import frost_anchored_windows, what_to_plant
except Exception:  # 直接以脚本方式运行时
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phenology import estimate_stage_days, covered_crops
    from plant_calendar import frost_anchored_windows, what_to_plant


MODES = ("planting_window", "stage_days", "calendar")


class SeasonAgent:
    """季节/物候层按需技能 Agent。"""

    name = "SeasonAgent"

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = payload or {}
        mode = payload.get("mode", "planting_window")
        if mode not in MODES:
            return {
                "available": False,
                "error": "未知 mode「%s」；支持：%s" % (mode, " / ".join(MODES)),
                "covered_crops": covered_crops(),
            }

        if mode == "stage_days":
            return self._stage_days(payload)
        if mode == "calendar":
            return self._calendar(payload)
        return self._planting_window(payload)

    # ---------- mode: stage_days ----------
    def _stage_days(self, p: Dict[str, Any]) -> Dict[str, Any]:
        crop = p.get("crop", "")
        temp = p.get("mean_temp_c")
        if not crop or temp is None:
            return {"available": False, "mode": "stage_days",
                    "error": "需提供 crop 与 mean_temp_c。",
                    "covered_crops": covered_crops()}
        try:
            temp_f = float(temp)
        except (TypeError, ValueError):
            return {"available": False, "mode": "stage_days",
                    "error": "mean_temp_c 必须是数字。"}
        r = estimate_stage_days(crop, temp_f)
        r["mode"] = "stage_days"
        r["confidence"] = self._confidence(r.get("available", False), crop)
        return r

    # ---------- mode: planting_window ----------
    def _planting_window(self, p: Dict[str, Any]) -> Dict[str, Any]:
        monthly = p.get("monthly_mean_c") or []
        climate_provenance = None
        climate_input = "caller_supplied"
        if len(monthly) != 12:
            # P0：给出经纬度则自动从 NASA POWER / Open-Meteo 拉真实气候，干掉手填 12 月均温
            lat = p.get("lat")
            lon = p.get("lon")
            if lat is not None and lon is not None:
                try:
                    from .climate_data import fetch_monthly_climate
                    cl = fetch_monthly_climate(float(lat), float(lon))
                    if cl.get("monthly_mean_c") and len(cl["monthly_mean_c"]) == 12 \
                            and all(m is not None for m in cl["monthly_mean_c"]):
                        monthly = cl["monthly_mean_c"]
                        climate_provenance = cl.get("provenance")
                        climate_input = "auto_fetched_from_latlon"
                    else:
                        return {"available": False, "mode": "planting_window",
                                "error": "未提供 monthly_mean_c，且按经纬度自动获取气候失败："
                                         + (cl.get("error") or "返回无效序列") + "。",
                                "covered_crops": covered_crops()}
                except Exception as e:
                    return {"available": False, "mode": "planting_window",
                            "error": "未提供 monthly_mean_c，且按经纬度自动获取气候异常：%s" % e,
                            "covered_crops": covered_crops()}
            if len(monthly) != 12:
                return {"available": False, "mode": "planting_window",
                        "error": "需提供 monthly_mean_c（12 个月均温，1 月起），或提供 lat/lon 由系统自动获取。",
                        "covered_crops": covered_crops()}
        try:
            monthly = [float(x) for x in monthly]
        except (TypeError, ValueError):
            return {"available": False, "mode": "planting_window",
                    "error": "monthly_mean_c 必须全为数字。"}
        r = frost_anchored_windows(
            monthly,
            crops=p.get("crops"),
            frost_threshold_c=float(p.get("frost_threshold_c", 0.0)),
            safety_margin_days=int(p.get("safety_margin_days", 7)),
        )
        r["mode"] = "planting_window"
        r["available_crops"] = covered_crops()
        r["confidence"] = self._confidence(r.get("available", False), None)
        # 透明化气候输入来源：自动抓取 ≠ 手编近似
        r["climate_input"] = climate_input
        if climate_provenance:
            r["climate_provenance"] = climate_provenance
        return r

    # ---------- mode: calendar ----------
    def _calendar(self, p: Dict[str, Any]) -> Dict[str, Any]:
        zone = p.get("zone")
        date_iso = p.get("date", "")
        if zone is None or not date_iso:
            return {"available": False, "mode": "calendar",
                    "error": "需提供 zone（USDA 耐寒区）与 date（YYYY-MM-DD）。"}
        r = what_to_plant(int(zone), date_iso, category=p.get("category", ""))
        r["mode"] = "calendar"
        return r

    # ---------- 置信度 ----------
    @staticmethod
    def _confidence(available: bool, crop: str) -> Dict[str, Any]:
        """与其余 Agent 一致的 confidence 结构（rubric_score 0-1）。

        仅在『模型可用且作物被 WOFOST 覆盖』时给较高分；未覆盖/不可用则低分，
        避免把推演结果伪装成实测结论。
        """
        if not available:
            return {"rubric_score": 0.0, "level": "unavailable",
                    "reason": "气候输入不足或全年无无霜期，未产生推演。"}
        return {"rubric_score": 0.6, "level": "medium",
                "reason": "基于 WOFOST 积温参数的理论推演，未经本地实测校准；"
                          "仅覆盖 7 种已移植作物，且不含春化/光周期机制。"}


# ---------------------------------------------------------------------------
# 自测（零依赖；python agent/season_agent.py）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    a = SeasonAgent()

    r1 = a.run({"mode": "planting_window",
                "monthly_mean_c": [-4, -1, 5, 14, 20, 25, 27, 26, 21, 14, 5, -2],
                "crops": ["马铃薯", "大豆"]})
    assert r1["available"] and r1["windows"][0]["feasible"], r1

    r2 = a.run({"mode": "stage_days", "crop": "马铃薯", "mean_temp_c": 18})
    assert r2["available"] and r2["maturity_days_from_sow"] > 0

    r3 = a.run({"mode": "stage_days", "crop": "番茄", "mean_temp_c": 20})
    assert not r3["available"]

    r4 = a.run({"mode": "calendar", "zone": 7, "date": "2026-04-15"})
    assert not r4["available"]  # 外部日历数据尚未到位

    r5 = a.run({"mode": "bogus"})
    assert not r5["available"]

    print(json.dumps({
        "planting_window": r1,
        "stage_days_potato": r2,
        "stage_days_uncovered": {"available": r3["available"], "covered": r3.get("covered_crops")},
        "calendar_no_data": r4,
        "bad_mode": {"available": r5["available"], "error": r5["error"]},
    }, ensure_ascii=False, indent=2))
