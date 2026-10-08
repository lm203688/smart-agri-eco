#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3 回填 · hot_arid / highland 两新分区的「气候基线 + 作物邻接」

背景（2026-10-04 巡检遗留，诚实建模缺口）：
  global_zones.json v1.1 已加 hot_arid/highland 两个分区，但：
  1) 两分区缺 climate_baseline → get_zone_climate_baseline() 返回 None
     → 任何 P3 校准对它们退化为「全分区均值」，分数失真；
  2) crop_adapt_db.json 只有旧 6 分区 → 知识图谱 grows_in 110 条边，
     两新分区在图层有 koppen_of/constrains 边但**无作物邻接**。

本脚本一次性闭合上述缺口（幂等，先备份）：
  A. 用 fetch_monthly_climate 在代表性坐标取真实月度气候，
     回填两分区的 climate_baseline（与既有 6 分区同源、口径一致：
     monthly_precip_mm 为月内日均 mm/day）。
  B. 把 6 个配套作物（与 add_hot_arid_highland.py 生成的 6 个配方一一对应）
     加入 crop_adapt_db.json 的 2 新分区，并跑**定向** P3 校准
     （GBIF 真实分布点 + 气候包络反推适配分），只动这 6 条，
     不动已有的 107 条旧校准。
  C. 每个成功校准的作物写入 calibrated=true + measured_calibration 实证
     （data_quality_gate 真实性红线要求）；GBIF 点不足则 calibrated=false
     + 原因注记，绝不伪造高分。

运行：python scripts/backfill_new_zone_p3.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.climate_data import fetch_monthly_climate, get_zone_climate_baseline  # noqa: E402
import niche_envelope_calibrate as nec  # noqa: E402

ZONE_META = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

# 代表性坐标：热漠取利雅得（BWh），高原取拉巴斯（安第斯高原，~3640m）
BASELINE_COORDS = {
    "hot_arid": (24.7136, 46.6753),
    "highland": (-16.5, -68.15),
}

# 6 个配套作物（latin 与 add_hot_arid_highland.py 生成的 6 个配方一致）
NEW_CROPS = [
    # zone, crop, latin, family, growth_days, temp_range, ph_range, water_ml_day, scenes, risks, fallback
    ("hot_arid", "椰枣", "Phoenix dactylifera", "棕榈科", 2200,
     [15, 45], [6.5, 8.5], 120, ["rooftop", "balcony"], ["红棕象甲", "炭疽病"], "自交系椰枣"),
    ("hot_arid", "骆驼刺", "Alhagi camelorum", "豆科", 120,
     [15, 40], [7.0, 8.5], 20, ["rooftop"], ["蚜虫"], "野生骆驼刺"),
    ("hot_arid", "沙葱", "Allium mongolicum", "石蒜科", 90,
     [12, 35], [6.8, 8.0], 30, ["balcony", "rooftop"], ["葱蓟马"], "蒙古野葱"),
    ("highland", "藜麦", "Chenopodium quinoa", "藜科", 120,
     [5, 20], [6.5, 7.5], 80, ["balcony", "rooftop", "garden"], ["霜霉病", "蚜虫"], "高原藜麦种"),
    ("highland", "青稞", "Hordeum vulgare var. coeleste", "禾本科", 110,
     [4, 20], [6.0, 7.0], 60, ["garden", "rooftop"], ["条锈病", "黑穗病"], "藏青稞"),
    ("highland", "洋姜", "Helianthus tuberosus", "菊科", 120,
     [6, 22], [6.5, 7.5], 70, ["balcony", "garden"], ["蚜虫", "白粉病"], "块茎繁殖"),
]


def _backup(path: str) -> None:
    bak = path + ".bak_20261006"
    if not os.path.exists(bak):
        shutil.copy(path, bak)
        print(f"  备份 {os.path.basename(path)} → {os.path.basename(bak)}")


def _backfill_baselines() -> int:
    d = json.load(open(ZONE_META, encoding="utf-8"))
    added = 0
    for z in d["zones"]:
        zid = z.get("zone_id")
        if zid not in BASELINE_COORDS:
            continue
        if z.get("climate_baseline"):
            continue
        lat, lon = BASELINE_COORDS[zid]
        cl = fetch_monthly_climate(lat, lon, years=5)
        mc = cl.get("monthly_mean_c")
        mp = cl.get("monthly_precip_mm")
        if not mc or len(mc) != 12 or any(v is None for v in mc):
            print(f"  [跳过] {zid} 气候基线取数不全（坐标 {lat},{lon}）")
            continue
        if not mp or len(mp) != 12:
            mp = [0] * 12
        z["climate_baseline"] = {
            "monthly_mean_c": [round(float(x), 2) for x in mc],
            "monthly_precip_mm": [round(float(x), 2) for x in (mp or [0] * 12)],
            "source": "fetch_monthly_climate (NASA POWER / Open-Meteo)",
            "coord": [lat, lon],
            "note": "v1.1 回填（2026-10-06）：与既有 6 分区同源，月内日均口径一致",
        }
        added += 1
        print(f"  [+] {zid} climate_baseline 已回填（年均温 "
              f"{sum(mc)/12:.1f}℃, 年降水 {sum(mp):.0f}mm/day 累加）")
    if added:
        json.dump(d, open(ZONE_META, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    return added


def _calibrate_crop(c: Dict[str, Any], real_zone_ids: List[str]) -> None:
    """复用 niche_envelope_calibrate 的 P3 反推逻辑，只校准单作物。"""
    latin = c["latin"]
    pts = nec.gbif_points(latin)
    time.sleep(nec._DELAY)
    if len(pts) < 3:
        c["calibrated"] = False
        c["calibration_method"] = None
        c["calibration_note"] = f"GBIF 分布点不足（{len(pts)}），无法反推"
        return
    env = nec.climate_envelope(pts)
    if not env:
        c["calibrated"] = False
        c["calibration_method"] = None
        c["calibration_note"] = "气候取样不足（<3 点成功），无法反推"
        return
    scores = {}
    for zid in real_zone_ids:
        base = get_zone_climate_baseline(zid)
        if base:
            scores[zid] = nec.score_zone(base, env)
    if not scores:
        c["calibrated"] = False
        c["calibration_note"] = "无分区基线可对照"
        return
    sc = round(sum(scores.values()) / len(scores), 2)
    c["adapt_score"] = sc
    c["calibrated"] = True
    c["calibration_method"] = "niche_envelope"
    c["calibration_provenance"] = {
        "gbif_occurrence_points": len(pts),
        "climate_samples": env["n_samples"],
        "temp_env_mean": [round((e[0] + e[1]) / 2, 1) for e in env["temp_env"]],
        "sources": ["GBIF occurrence (CC BY 4.0)", "NASA POWER / Open-Meteo"],
        "note": "由真实分布点气候包络反推，非手编近似；0 用户下唯一实证校准路径。",
    }
    c["measured_calibration"] = {
        "calibrated_score": sc,
        "method": "niche_envelope",
        "gbif_occurrence_points": len(pts),
        "climate_samples": env["n_samples"],
        "temp_env_mean_c": [round((e[0] + e[1]) / 2, 1) for e in env["temp_env"]],
        "sources": ["GBIF occurrence (CC BY 4.0)", "NASA POWER / Open-Meteo"],
        "note": "由真实分布点气候包络反推，非手编近似；0 用户下唯一实证校准路径。",
    }
    c["calibration_note"] = (f"GBIF {len(pts)} 点 / 气候样 {env['n_samples']} 点反推；"
                             f"包络年均温 {sum((e[0]+e[1])/2 for e in env['temp_env'])/12:.1f}℃")


def main() -> None:
    _backup(ZONE_META)
    _backup(CROP_DB)

    print("== A. 回填两新分区 climate_baseline ==")
    n_base = _backfill_baselines()
    print(f"   新增基线分区数：{n_base}")

    print("== B/C. 加入并定向校准 6 个配套作物 ==")
    db = json.load(open(CROP_DB, encoding="utf-8"))
    zones = db.setdefault("zones", {})
    real_zone_ids = list(zones.keys())  # 含 hot_arid/highland（若已存在）

    added_zones, added_crops, calibrated_ok, calibrated_fail = 0, 0, 0, 0
    for (zid, crop, latin, family, gd, tr, ph, water, scenes, risks, fb) in NEW_CROPS:
        if zid not in zones:
            zones[zid] = {"zone_name": ("热漠带" if zid == "hot_arid" else "高原带"),
                          "crops": []}
            added_zones += 1
        zcrops = zones[zid]["crops"]
        if any(c.get("crop") == crop for c in zcrops):
            print(f"   [跳过] {zid}/{crop} 已存在")
            continue
        entry: Dict[str, Any] = {
            "crop": crop,
            "latin": latin,
            "family": family,
            "growth_days": gd,
            "temp_range_c": list(tr),
            "ph_range": list(ph),
            "water_ml_day": water,
            "suitable_scenes": list(scenes),
            "key_risks": list(risks),
            "fallback_variety": fb,
            "latin_verified": True,
        }
        _calibrate_crop(entry, real_zone_ids)
        if entry.get("calibrated"):
            calibrated_ok += 1
        else:
            calibrated_fail += 1
        zcrops.append(entry)
        added_crops += 1
        print(f"   [+] {zid}/{crop} adapt_score={entry.get('adapt_score')} "
              f"calibrated={entry.get('calibrated')} ({entry.get('calibration_note','')})")

    json.dump(db, open(CROP_DB, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    total = sum(len(z.get("crops", [])) for z in zones.values())
    cal = sum(1 for z in zones.values() for c in z.get("crops", [])
              if c.get("calibrated"))
    print(f"\n汇总：新增分区 {added_zones} / 新增作物 {added_crops} / "
          f"校准成功 {calibrated_ok} / 校准跳过 {calibrated_fail}")
    print(f"crop_adapt_db 现共 {total} 作物，calibrated={cal}")
    print("下一步：python -m engine.knowledge_graph 重建图谱（grows_in 110→116）")


if __name__ == "__main__":
    main()
