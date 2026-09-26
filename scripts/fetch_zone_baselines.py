#!/usr/bin/env python3
"""
P1 · 6 分区气候基线离线固化（零依赖）

用 P0 的 fetch_monthly_climate 抓取每个农业分区的**代表点**真实月度气候，
写回 data/zone_meta/global_zones.json 的 climate_baseline 字段（含 provenance）。
此后引擎读取分区气候基线无需联网，仅作兜底/校准源。

代表点选取（geo 常识，非精确栅格）：
  tropical_rainforest    (0.0, 100.0)   苏门答腊
  mediterranean         (38.0, 23.7)   雅典海岸（地中海气候典型）
  arid                  (45.0, 75.0)   中亚内陆干旱
  temperate_continental (39.9, 116.4)  北京
  subtropical_wet       (30.27, 120.16) 杭州
  subarctic             (62.0, 25.0)   芬兰

运行：
  python scripts/fetch_zone_baselines.py
（强制联网刷新；结果写入 json，二次读取走 get_zone_climate_baseline 离线）
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.climate_data import fetch_monthly_climate  # noqa: E402

ZONE_META_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")

ZONE_CENTROIDS = {
    "tropical_rainforest": (0.0, 100.0),
    "mediterranean": (38.0, 23.7),
    "arid": (45.0, 75.0),
    "temperate_continental": (39.9, 116.4),
    "subtropical_wet": (30.27, 120.16),
    "subarctic": (62.0, 25.0),
}


def main() -> None:
    with open(ZONE_META_PATH, encoding="utf-8") as f:
        data = json.load(f)
    zones = data.get("zones", [])
    by_id = {z["zone_id"]: z for z in zones}

    missing = [zid for zid in ZONE_CENTROIDS if zid not in by_id]
    if missing:
        print("警告：以下分区不在 global_zones.json，跳过：", missing)

    for zid, (lat, lon) in ZONE_CENTROIDS.items():
        if zid not in by_id:
            continue
        print(f"抓取 {zid} ({lat}, {lon}) ...", end=" ", flush=True)
        cl = fetch_monthly_climate(lat, lon, years=10, force_refresh=True)
        if cl.get("error"):
            print("失败：", cl["error"])
            continue
        by_id[zid]["climate_baseline"] = {
            "centroid_lat": lat,
            "centroid_lon": lon,
            "source": cl["source"],
            "license": cl["license"],
            "url": cl.get("url"),
            "accessed_at": cl["accessed_at"],
            "years_used": cl["years_used"],
            "monthly_mean_c": cl["monthly_mean_c"],
            "monthly_precip_mm": cl.get("monthly_precip_mm"),
            "monthly_rh_pct": cl.get("monthly_rh_pct"),
        }
        print(f"OK 源={cl['source']} 年均温≈{sum(cl['monthly_mean_c'])/12:.1f}℃")

    with open(ZONE_META_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("已写回", ZONE_META_PATH)


if __name__ == "__main__":
    main()
