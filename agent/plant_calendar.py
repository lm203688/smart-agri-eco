"""plant_calendar.py — 霜冻锚定种植窗口（零依赖，stdlib-only）。

用途（B2，见 docs/opensource_scan_complementary.md）：给 growth_agent 补『何时种』的季节窗口层
（当前 growth_plan 只有计划、无季节窗）。

两条数据通路：
  1) 【外部日历】drop 合规的 data/plant_calendar.json 后，用 what_to_plant() 直接查表。
     —— 但 @pondlog crop-calendar 实测不可达（npm 发布包仅含 package.json；GitHub 仓库树无
        crop-calendar.json），故此通路待数据到位后才生效，本模块不编造任何日历数据。
  2) 【本地推导，默认可用】frost_anchored_windows()：调用方提供 12 个月均温，本模块
     用已移植的 WOFOST 积温参数（agent/phenology.py）反推无霜期与最晚安全播种日。
     —— 这是真正能立刻工作的通路，无需任何第三方日历数据。

月份按每月 30 天简化（年 360 天），物候推演误差远大于此简化误差，故可接受。
南半球（无霜期跨年环绕）已处理：在环形日序列上找最长无霜连续段。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAL_PATH = os.path.join(ROOT, "data", "plant_calendar.json")

DAYS_PER_MONTH = 30
YEAR_DAYS = DAYS_PER_MONTH * 12  # 360

try:
    from .phenology import estimate_stage_days, covered_crops  # type: ignore
except Exception:  # 直接以脚本方式运行时
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phenology import estimate_stage_days, covered_crops  # type: ignore


# ---------------------------------------------------------------------------
# 通路 1：外部日历查表
# ---------------------------------------------------------------------------
def load_calendar(path: str = _CAL_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"crops": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _doy_of(date_iso: str) -> Optional[int]:
    """ISO 日期 → 年内 day-of-year（1-365/366）。"""
    try:
        from datetime import date
        y, m, d = (int(x) for x in date_iso.split("-"))
        return date(y, m, d).timetuple().tm_yday
    except Exception:
        return None


def _doy_to_date(doy360: int) -> str:
    """360 天制 day-of-year → 'MM-DD' 近似（每月 30 天）。"""
    doy360 = int(doy360) % YEAR_DAYS
    m = doy360 // DAYS_PER_MONTH + 1
    d = doy360 % DAYS_PER_MONTH + 1
    return "%02d-%02d" % (m, d)


def what_to_plant(zone: int, date_iso: str, category: str = "",
                  path: str = _CAL_PATH) -> Dict[str, Any]:
    """查询某 USDA 耐寒区、某日期适合种植的作物与动作。

    返回 {available, zone, date, in_window: [ {common_name, action, window} ]}。
    数据为空或缺失时 available=False（绝不编造）。
    """
    cal = load_calendar(path)
    crops = cal.get("crops", [])
    doy = _doy_of(date_iso)
    if not crops or doy is None:
        return {"available": False, "zone": zone, "date": date_iso,
                "reason": "日历数据为空或日期无法解析；drop 合规的 data/plant_calendar.json 后生效。",
                "in_window": []}
    out: List[Dict[str, Any]] = []
    for c in crops:
        z = c.get("zones") or {}
        zmin, zmax = z.get("min", 0), z.get("max", 99)
        if not (zmin <= zone <= zmax):
            continue
        if category and c.get("category") != category:
            continue
        for w in c.get("windows", []):
            s, e = w.get("start_doy"), w.get("end_doy")
            if s is not None and e is not None and s <= doy <= e:
                out.append({"common_name": c.get("common_name", c.get("slug", "")),
                            "action": w.get("action"), "window": [s, e]})
    return {"available": True, "zone": zone, "date": date_iso,
            "in_window": out, "total_crops_loaded": len(crops)}


# ---------------------------------------------------------------------------
# 通路 2：本地推导（无霜期 + 积温 → 播期窗口）
# ---------------------------------------------------------------------------
def _daily_series(monthly_mean_c: List[float]) -> List[float]:
    """12 个月均温 → 360 天逐日序列（月内线性插值到相邻月中点）。"""
    if len(monthly_mean_c) != 12:
        raise ValueError("monthly_mean_c 必须是 12 个月均温（1 月起）。")
    # 月中点对应的日序（第 i 月月中 = i*30 + 15）
    centers = [i * DAYS_PER_MONTH + DAYS_PER_MONTH / 2.0 for i in range(12)]
    series: List[float] = []
    for m in range(12):
        c0 = centers[m]
        c1 = centers[(m + 1) % 12]
        if m == 11:
            c1 = centers[0] + YEAR_DAYS  # 跨年环绕
        t0 = monthly_mean_c[m]
        t1 = monthly_mean_c[(m + 1) % 12]
        span = c1 - c0
        for k in range(DAYS_PER_MONTH):
            day = m * DAYS_PER_MONTH + k + 0.5
            frac = (day - c0) / span if span else 0.0
            series.append(t0 + (t1 - t0) * frac)
    return series


def _longest_frost_free_run(series: List[float], frost_threshold_c: float = 0.0
                             ) -> Dict[str, Any]:
    """在环形日序列上找最长连续无霜段。返回 {start_doy, end_doy, length_days, mean_temp_c}。

    start_doy/end_doy 为 0-based 日序（0..359），end 为闭区间。
    """
    n = len(series)
    warm = [t > frost_threshold_c for t in series]
    if all(warm):
        return {"start_doy": 0, "end_doy": n - 1, "length_days": n,
                "mean_temp_c": sum(series) / n, "year_round": True}
    if not any(warm):
        return {"start_doy": None, "end_doy": None, "length_days": 0,
                "mean_temp_c": sum(series) / n, "year_round": False}

    # 找跨环起点：一个 warm 段，其前一日为 cold
    seg_start = next(i for i in range(n) if warm[i] and not warm[i - 1])
    best = {"length": -1, "start": None}
    i = seg_start
    counted = 0
    while counted < n:
        cur = i % n
        if warm[cur]:
            length = 0
            while warm[(cur + length) % n] and length < n:
                length += 1
            if length > best["length"]:
                best = {"length": length, "start": cur}
            i += length
            counted += length
        else:
            i += 1
            counted += 1
    s = best["start"]
    ln = best["length"]
    temps = [series[(s + k) % n] for k in range(ln)]
    return {"start_doy": s, "end_doy": (s + ln - 1) % n, "length_days": ln,
            "mean_temp_c": sum(temps) / ln, "year_round": False}


def frost_anchored_windows(monthly_mean_c: List[float], crops: Optional[List[str]] = None,
                           frost_threshold_c: float = 0.0,
                           safety_margin_days: int = 7) -> Dict[str, Any]:
    """按逐月均温推导无霜期，并为每种已移植作物给出播种窗口。

    参数：
        monthly_mean_c: 12 个月均温（℃），1 月起。来源可为 WorldClim/Open-Meteo/本地气象站。
        crops: 限定作物（中文名或英文 key）；None = 全部已移植作物。
        frost_threshold_c: 霜冻阈值，默认 0℃。
        safety_margin_days: 成熟预留安全边际（天），默认 7。

    返回：
        {available, frost_free: {start, end, length_days, mean_temp_c},
         windows: [ {crop, maturity_days, feasible, earliest_sow, latest_sow,
                     sow_window_days, note} ]}
        earliest_sow/latest_sow 为 'MM-DD'（360 天制近似）。
    """
    series = _daily_series(monthly_mean_c)
    ff = _longest_frost_free_run(series, frost_threshold_c)
    out: Dict[str, Any] = {
        "available": True,
        "frost_free": {
            "start": _doy_to_date(ff["start_doy"]) if ff["start_doy"] is not None else None,
            "end": _doy_to_date(ff["end_doy"]) if ff["end_doy"] is not None else None,
            "length_days": ff["length_days"],
            "mean_temp_c": round(ff["mean_temp_c"], 2),
            "year_round": ff.get("year_round", False),
        },
        "windows": [],
        "note": "月份按每月 30 天简化；物候推演基于 WOFOST 积温参数（EUPL 1.2，需署名）。",
    }
    if not ff["length_days"]:
        out["available"] = False
        out["note"] = "全年均温均低于霜冻阈值 %.1f℃，无可用无霜期。" % frost_threshold_c
        return out

    targets = crops if crops else covered_crops()
    season_t = ff["mean_temp_c"]
    for c in targets:
        est = estimate_stage_days(c, season_t)
        if not est.get("available"):
            out["windows"].append({"crop": c, "feasible": False,
                                   "note": "该作物尚未移植 WOFOST 物候参数，无法按积温推演。"})
            continue
        mat = est.get("maturity_days_from_sow")
        if mat is None:
            out["windows"].append({"crop": est.get("crop", c), "feasible": False,
                                   "note": est.get("note", "发育停滞。"),
                                   "season_mean_temp_c": round(season_t, 2)})
            continue
        mat_i = int(round(mat))
        s = ff["start_doy"]
        e = ff["end_doy"]
        if ff.get("year_round"):
            out["windows"].append({
                "crop": est.get("crop", c), "feasible": True,
                "maturity_days": mat_i, "earliest_sow": "全年可播", "latest_sow": "全年可播",
                "sow_window_days": 360, "season_mean_temp_c": round(season_t, 2),
                "note": "全年无霜，任意期播种均可成熟。",
            })
            continue
        latest = (e - mat_i - safety_margin_days) % YEAR_DAYS
        window_len = (latest - s) % YEAR_DAYS
        feasible = window_len > 0 and mat_i + safety_margin_days <= ff["length_days"]
        if not feasible:
            note = ("无霜期 %d 天不足以完成 %d 天生育期（含 %d 天安全边际），"
                    "需选早熟品种或保护地栽培。" % (ff["length_days"], mat_i, safety_margin_days))
        else:
            note = ""
        if est.get("requires_vernalization"):
            note = (note + " 【限制】该品种需春化（越冬低温）才能抽穗，本积温模型不含春化机制，"
                           "窗口仅对『春播型/春性品种』成立；冬播越冬型不可用此窗口。").strip()
        out["windows"].append({
            "crop": est.get("crop", c),
            "feasible": bool(feasible),
            "maturity_days": mat_i,
            "earliest_sow": _doy_to_date(s),
            "latest_sow": _doy_to_date(latest) if feasible else None,
            "sow_window_days": int(window_len) if feasible else 0,
            "season_mean_temp_c": round(season_t, 2),
            "requires_vernalization": est.get("requires_vernalization", False),
            "note": note,
        })
    return out


# ---------------------------------------------------------------------------
# 自测（零依赖；python agent/plant_calendar.py）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 1) 空日历：优雅返回 available=False，不编造
    r0 = what_to_plant(7, "2026-04-15")
    assert not r0["available"]

    # 2) 温带大陆性气候（北京型：1 月 -4℃，7 月 26℃）
    bj = [-4.0, -1.0, 5.0, 14.0, 20.0, 25.0, 27.0, 26.0, 21.0, 14.0, 5.0, -2.0]
    rb = frost_anchored_windows(bj, crops=["马铃薯", "小麦", "大豆"])
    assert rb["available"]
    assert rb["frost_free"]["length_days"] > 200, rb["frost_free"]

    # 3) 全年严寒（无无霜期）
    cold = [-20.0] * 12
    rc = frost_anchored_windows(cold, crops=["马铃薯"])
    assert not rc["available"]

    # 4) 热带（全年无霜）
    trop = [26.0] * 12
    rt = frost_anchored_windows(trop, crops=["马铃薯"])
    assert rt["frost_free"]["year_round"]

    print(json.dumps({
        "empty_calendar_query": r0,
        "beijing_like": rb,
        "all_year_frozen": rc,
        "tropical_year_round": rt["frost_free"],
    }, ensure_ascii=False, indent=2))
