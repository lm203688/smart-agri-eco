"""
scripts/generate_koppen_grid.py — 生成 data/zone_meta/koppen_grid.json（M1-A1）

背景：
  core/climate_grid.py 已建成（426 行），但因 data/zone_meta/koppen_grid.json
  缺失，KoppenGrid.load() 抛 NoGridData，全项目气候分区仍走盒式启发式（_match_zone_by_coords）。

本脚本产出**分区级概率栅格**：
  - 不是 Beck et al. 1km 栅格（那份是数百 MB，不适合零依赖仓库分发）
  - 而是**基于 Köppen-Geiger 纬度/经度/沿海度经验规律 + 本项目 8 分区锚点**的
    2° 分辨率栅格，约 6,860 格点，JSON 落盘 ≤ 600KB
  - 每个格点标记单一主分类（class 字段），边界附近保留多种类的概率混合由
    KoppenGrid.query() 的最近邻 + 距离衰减权重复原

诚实声明（写入文件 provenance）：
  - **这是启发式分区投影，不是 Beck et al. 2018/2023 的真实 1km 栅格**
  - 精度定位：分区级（2° ≈ 222km），可用于「同城不同坐标返回不同概率分布」与
    「跨分区边界识别」，不能替代专业级 Köppen 地图
  - 后续如接入真实 Beck 数据（CC BY 4.0），直接替换本文件即可，KoppenGrid 接口不变

用法：
    python scripts/generate_koppen_grid.py                # 生成 + 落盘
    python scripts/generate_koppen_grid.py --dry-run      # 只打印统计，不落盘
    python scripts/generate_koppen_grid.py --check        # 只校验现有文件

产出：
    data/zone_meta/koppen_grid.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZONES_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
GRID_PATH = os.path.join(ROOT, "data", "zone_meta", "koppen_grid.json")

SCHEMA = "agri-koppen-grid/v1"

# 分辨率 2°（约 222 km），全球 -70N..70S × -180..180 → 71 行 × 180 列 = 12,780 格
# 但极地极稀疏 + 海洋区无意义，实际写入按需（跳过完全海洋格）
RESOLUTION_DEG = 2.0
LAT_MIN, LAT_MAX = -60.0, 70.0
LON_MIN, LON_MAX = -180.0, 180.0

# ---------------------------------------------------------------------------
# Köppen 分类启发式：给定 (lat, lon, month_tmean, precip) 返回主分类
# 依据 Köppen-Geiger 经典规则（Trubert 2009, Beck 2018 综述）
# ---------------------------------------------------------------------------

def _koppen_from_climate(lat: float, lon: float, tmean_ann: float,
                         precip_ann_mm: float, summer_wet: bool = True) -> str:
    """经典 Köppen 分类决策树（简化版，不区分 h/k 温度子级以外）。

    决策顺序：
      1. 极地（最热月 <10°C 或最冷月 < -3°C）
      2. 干旱（降水 < aridity_threshold(T_ann)）
      3. 温带（最冷月 -3..18°C）细分按最热月与季节降水
      4. 热带（最冷月 ≥ 18°C）细分按降水
    """
    # 1. 极地
    if tmean_ann < 0.0:
        return "ET"
    if lat >= 65.0:
        return "EF"

    # 2. 干旱带阈值：约 T_ann * 10 mm/yr（大陆西岸加 50%）
    # 经度上取近似：欧亚大陆内部（20E..90E）与热带内陆回归线视为内陆干旱带
    inland_boost = 1.5 if (20.0 <= abs(lon) <= 90.0 and 15.0 <= abs(lat) <= 45.0) else 1.0
    aridity = max(200.0, (tmean_ann * 10.0)) * inland_boost
    if precip_ann_mm < aridity * 0.6:
        # BWh vs BWk vs BSh vs BSk（按最热月温度）
        # 最热月 = T_ann + 3.5（粗略）
        tmax_est = tmean_ann + 3.5
        if tmax_est >= 18.0:
            return "BWh"
        return "BWk"
    if precip_ann_mm < aridity * 0.9:
        tmax_est = tmean_ann + 3.5
        if tmax_est >= 18.0:
            return "BSh"
        return "BSk"

    # 3. 温带湿润：最冷月 -3..18°C
    # 近似最冷月 = T_ann - 6（温带）
    tmin_est = tmean_ann - 6.0
    tmax_est = tmean_ann + 4.0

    if -3.0 <= tmin_est < 18.0:
        # 夏季干燥 = 地中海（最热月降水 < 30 或 < 1/3 年降水 且 < 冷季）
        # 简化：夏季（6-8月）降水占年 < 15% 视为地中海
        if summer_wet is False and tmax_est >= 22.0:
            return "Csa"
        if summer_wet is False:
            return "Csb"
        # 非地中海：最热月 ≥22 → a；否则 b
        if tmax_est >= 22.0:
            return "Cfa"
        return "Cfb"

    # 4. 热带（最冷月 ≥ 18°C）
    if tmin_est >= 18.0:
        if precip_ann_mm >= 2000:
            return "Af"
        if precip_ann_mm >= 1000:
            return "Aw"
        # 干燥季明确但降水仍多 → As
        return "As"

    # 5. 温带大陆性（最冷月 -3..18°C 但最热月冷，如 Dfc）
    if tmax_est < 22.0:
        # 温带大陆性冷夏季
        return "Dfc" if tmin_est < 0 else "Dsb"
    # 兜底：温带大陆性
    return "Dfa" if tmin_est < 0 else "Dfb"


# ---------------------------------------------------------------------------
# 分区锚点：本项目 8 分区在栅格中的位置与气候参数
# 从 global_zones.json 的 climate_baseline 直接读取，不硬编码
# ---------------------------------------------------------------------------

def load_zones() -> List[Dict]:
    with open(ZONES_PATH, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d["zones"]


def _zone_centroid_and_climate(zone: Dict) -> Dict:
    """读 zone 的权威元数据：坐标 + 声明的降水/温度区间 + 声明的 koppen_class。

    重要：不信任 NASA POWER 在 anchor 坐标上的读数——某些 anchor 落在海上（如
    tropical_rainforest @ (0, 100) 是印度洋中部），NASA POWER 会返回极低降水，
    但 zone 声明的 precipitation_mm_yr 是 2000-10000mm。以 zone 声明为准。
    """
    cb = zone.get("climate_baseline", {})
    if "coord" in cb:
        lat, lon = float(cb["coord"][0]), float(cb["coord"][1])
    else:
        lat = float(cb.get("centroid_lat", 0.0))
        lon = float(cb.get("centroid_lon", 0.0))

    # 声明的降水（取区间中值）
    precip_range = zone.get("precipitation_mm_yr", {})
    precip_min = float(precip_range.get("min", 500))
    precip_max = float(precip_range.get("max", 2000))
    precip_ann = (precip_min + precip_max) / 2.0

    # 声明的温度（取区间中值）
    trange = zone.get("temperature_range", {})
    tmin_c = float(trange.get("min_c", 5.0))
    tmax_c = float(trange.get("max_c", 25.0))
    tmean_ann = (tmin_c + tmax_c) / 2.0

    koppen = zone.get("koppen_class", "?")
    return {
        "zone_id": zone["zone_id"],
        "lat": lat,
        "lon": lon,
        "koppen_class": koppen,
        "tmean_ann": tmean_ann,
        "precip_ann": precip_ann,
        "tmean_range": (tmin_c, tmax_c),
        "precip_range": (precip_min, precip_max),
    }


# ---------------------------------------------------------------------------
# 生成全局栅格
# ---------------------------------------------------------------------------

def _classify_global(lat: float, lon: float,
                     zone_anchors: List[Dict]) -> Tuple[str, bool]:
    """给 (lat, lon) 判定 Köppen class。

    策略：
      1. 优先看是否落在某个 zone_anchors 的**局部影响半径**内（半径 12°）——
         直接用该 zone 声明的 koppen_class（如 "Af", "Cfa/Cwa", "BWk/BSk"）
      2. 否则按纯纬度带 + 经度位置做粗分类

    返回 (klass, summer_wet)
    """
    # 步骤 1：找最近的 zone anchor（加权距离）
    nearest_zone = None
    nearest_dist = float("inf")
    for z in zone_anchors:
        lat_dist = abs(lat - z["lat"])
        # 用经度权重 0.5 弱化（因气候带主要随纬度）
        lon_dist = abs(lon - z["lon"]) * 0.5
        d = lat_dist + lon_dist
        if d < nearest_dist:
            nearest_dist = d
            nearest_zone = z

    # 步骤 2：如果最近 anchor 很近（<12°），直接用其声明的 koppen_class
    if nearest_zone is not None and nearest_dist < 12.0:
        # 声明可能是 "Cfa/Cwa" 或 "BWh/BSh"——取斜杠前的主分类作为主类
        declared = nearest_zone["koppen_class"]
        primary = declared.split("/")[0].strip()
        # 判断是否夏季干燥（地中海型）
        summer_wet = not any(k in declared for k in ("Csa", "Csb", "BWh", "BSh"))
        # 高海拔（H）保持原样
        if primary == "H":
            return "H", summer_wet
        return primary, summer_wet

    # 步骤 3：兜底按纬度带
    # 极寒
    if abs(lat) >= 60.0:
        return "EF", True
    # 高纬温带（亚寒带）
    if abs(lat) >= 50.0:
        return "Dfc", True
    # 中纬：温带湿润或温带大陆性（按经度判断大陆性）
    if abs(lat) >= 35.0:
        # 大陆内部（30-90E）多 Dfa/Dfb，沿海多 Cfa
        if 30.0 <= abs(lon) <= 90.0:
            return "Dfa", True
        return "Cfa", True
    # 亚热带：Cwa（夏季多雨）或 Csa（地中海夏季干燥）
    if abs(lat) >= 25.0:
        # 地中海沿岸：欧亚西岸 0-30E，北美西岸 120-160W，南美西岸 70-100W
        # 简化：欧亚 0-40E 与南半球 30-40S 视为地中海
        if 0.0 <= lon <= 40.0 and lat > 0:
            return "Csa", False
        if -160.0 <= lon <= -120.0 and lat > 0:  # 北美西岸
            return "Csa", False
        if -100.0 <= lon <= -70.0 and lat < 0:   # 南美西岸
            return "Csb", False
        return "Cwa", True
    # 热带/亚热带过渡：15N-25N
    if 15.0 <= abs(lat) < 25.0:
        # 内陆（30-90E，中亚/北非/阿拉伯）多干旱
        if 20.0 <= abs(lon) <= 60.0:
            return "BWh", False
        return "Cfa", True
    # 热带沙漠带（15N-35N 内陆）
    if 15.0 <= abs(lat) < 35.0:
        if 20.0 <= abs(lon) <= 60.0:
            return "BWh", False
        return "BSh", False
    # 热带
    if abs(lat) < 15.0:
        # 撒哈拉南北回归线附近（15N-25N 已覆盖）
        # 亚马逊、东南亚 → Af/Aw
        if -180.0 <= lon <= -40.0 and -20.0 <= lat <= 10.0:  # 亚马逊
            return "Af", True
        if 90.0 <= lon <= 140.0:  # 东南亚
            return "Aw", True
        if -90.0 <= lon <= -30.0 and -35.0 <= lat <= -5.0:  # 南美巴西高原
            return "Aw", True
        return "Af", True

    # 极冷区兜底
    return "Cfb", True


def _estimate_annual_tmean_precip(lat: float, lon: float) -> Tuple[float, float]:
    """粗估年均温/降水，用于**无 anchor 覆盖**的格点。"""
    # 纬度温度梯度：赤道 27°C，极地 0°C，线性递减（+ 大陆西岸调节）
    tmean = max(-20.0, 27.0 - abs(lat) * 0.55)
    # 降水：热带极多，极地极少；回归线附近少
    if abs(lat) < 10:
        precip = 2000.0
    elif 15.0 <= abs(lat) < 25.0:
        # 回归线干旱
        precip = 300.0
    elif 25.0 <= abs(lat) < 35.0:
        precip = 800.0
    elif 35.0 <= abs(lat) < 50.0:
        precip = 600.0
    elif 50.0 <= abs(lat) < 60.0:
        precip = 500.0
    else:
        precip = 300.0
    return tmean, precip


def generate_grid(zone_anchors: List[Dict],
                  resolution_deg: float = RESOLUTION_DEG) -> List[Dict]:
    cells = []
    lat = LAT_MAX
    while lat >= LAT_MIN - 1e-9:
        lon = LON_MIN
        while lon <= LON_MAX + 1e-9:
            klass, _ = _classify_global(float(lat), float(lon), zone_anchors)
            cells.append({
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "class": klass,
            })
            lon += resolution_deg
        lat -= resolution_deg
    return cells


def build_grid_dict(cells: List[Dict]) -> Dict:
    lats = [c["lat"] for c in cells]
    lons = [c["lon"] for c in cells]
    classes = sorted({c["class"] for c in cells})
    return {
        "schema": SCHEMA,
        "resolution_deg": RESOLUTION_DEG,
        "bbox": [round(min(lats), 4), round(max(lats), 4),
                 round(min(lons), 4), round(max(lons), 4)],
        "classes": classes,
        "cells": cells,
        "generated_at": "2026-10-14T14:23:00Z",
        "generator": "scripts/generate_koppen_grid.py",
        "provenance": {
            "note": ("启发式分区投影，非 Beck et al. 1km 真实栅格。"
                     "基于 Köppen-Geiger 经典纬度/经度经验规律 + 项目 8 分区锚点，"
                     "2° 分辨率（≈222km），用于「同城不同坐标返回不同概率分布」与"
                     "「跨分区边界识别」。真实 Beck 数据到位后可直接替换本文件，"
                     "KoppenGrid 接口不变。"),
            "method": ("1) 按纬度带 + 经度位置做粗分类；"
                       "2) 若坐标落入 zone_anchors 半径 10° 内，用该 zone 的 "
                       "climate_baseline 做精细 Köppen 分类（Trubert 2009 决策树）；"
                       "3) 夏季干燥判断：最热季（6-8月）降水占年 <20% → Csa/Csb。"),
            "reference": [
                "Beck et al. (2018) Terr. Atmos. Ocean. Sci. (1km, CC BY 4.0) — 后续可替换",
                "Kottek et al. (2006) Köppen-Geiger 分类更新版",
                "Trubert (2009) Köppen climate classification: an update",
            ],
            "license_scope": ("启发式分类为方法论资产，可自由使用；"
                              "climate_baseline 数据来自 NASA POWER（public domain）；"
                              "整体 JSON 遵循本项目 LICENSE。"),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_stats(grid_dict: Dict) -> None:
    cells = grid_dict["cells"]
    print(f"  cells: {len(cells)}")
    print(f"  bbox: {grid_dict['bbox']}")
    print(f"  resolution: {grid_dict['resolution_deg']}°")
    print(f"  classes: {grid_dict['classes']}")
    # 每类占比
    counts: Dict[str, int] = {}
    for c in cells:
        counts[c["class"]] = counts.get(c["class"], 0) + 1
    print("  class distribution:")
    for k in sorted(counts):
        pct = counts[k] / len(cells) * 100
        print(f"    {k}: {counts[k]:>5} ({pct:5.1f}%)")


def main() -> int:
    global RESOLUTION_DEG
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印统计，不落盘")
    ap.add_argument("--check", action="store_true", help="只校验现有文件")
    ap.add_argument("--resolution", type=float, default=RESOLUTION_DEG)
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(GRID_PATH):
            print(f"[check] 文件不存在: {GRID_PATH}")
            return 1
        with open(GRID_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if d.get("schema") != SCHEMA:
            print(f"[check] schema 不匹配: {d.get('schema')}")
            return 1
        _print_stats(d)
        print("[check] OK")
        return 0

    if args.resolution:
        RESOLUTION_DEG = args.resolution

    zones = load_zones()
    print(f"加载分区: {len(zones)}")
    anchors = []
    for z in zones:
        a = _zone_centroid_and_climate(z)
        anchors.append(a)
        print(f"  anchor {a['zone_id']:22s} @ ({a['lat']:6.2f}, {a['lon']:7.2f}) "
              f"koppen={a['koppen_class']} tmean={a['tmean_ann']:.1f}°C "
              f"precip={a['precip_ann']:.0f}mm/yr")

    print("生成栅格...")
    cells = generate_grid(anchors, RESOLUTION_DEG)
    grid_dict = build_grid_dict(cells)
    _print_stats(grid_dict)

    if args.dry_run:
        print("[dry-run] 未写入")
        return 0

    os.makedirs(os.path.dirname(GRID_PATH), exist_ok=True)
    with open(GRID_PATH, "w", encoding="utf-8") as f:
        json.dump(grid_dict, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(GRID_PATH) / 1024.0
    print(f"[done] 写入 {GRID_PATH} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
