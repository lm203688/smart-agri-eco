#!/usr/bin/env python3
"""
scripts/backfill_zone_dli.py —— 给 global_zones.json 补分区级 DLI（NASA POWER）

背景（P1-1）：
    116 份 Env Recipe 覆盖 8 个气候分区。DLI 是光照决策核心参数，
    但此前 0/116 份有 DLI 数据（full_liftup_assessment §1.4 曾用子串匹配把
    "handling" 误判为 dli 字段命中，实际 0）。

设计原则（对齐项目铁律「派生量不落盘」）：
    - DLI 是**分区级输入数据**，补进 global_zones.json 的 climate_baseline
      （与 monthly_mean_c / monthly_precip_mm / monthly_rh_pct 同源同坐标），
      由 engine/derived.py 在运行时从分区派生到配方，**不写回 116 份 recipe**。
    - 与既有 8 分区坐标一致：前 6 个 zone 用 centroid_lat/centroid_lon，
      hot_arid/highland 用 climate_baseline.coord（2026-10-06 已回填利雅得/拉巴斯）。
    - NASA POWER ALLSKY_SFC_SW_DWN 单位 kWh/m²/day，换算为**全谱短波辐射的
      光子当量**（kWh * 16.45 mol/m²/day），并在字段里显式标注「非标准 PAR DLI，
      PAR 约占全谱 45%-50%，项目内无实测」——绝不冒充专业 PAR DLI。

数据来源：NASA POWER 月度 point 接口（public domain），与 climate_data.py 同源。
缓存：data/shared_cache/ 目录（坐标 -> 12 月均值 kWh）。

用法：
    python scripts/backfill_zone_dli.py --dry-run   # 只报告（默认）
    python scripts/backfill_zone_dli.py --apply     # 落盘 global_zones.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZONE_META_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
CACHE_DIR = os.path.join(ROOT, "data", "shared_cache")

# 全谱短波辐射 -> 光子当量（mol/m²/day per kWh/m²/day）
# 1 kWh = 3.6e6 J；PAR 波段中心 550nm 处 1 J ≈ 4.57 μmol 光子。
# ⚠️ 这是「全谱短波辐射的光子当量」，不等于 PAR DLI。
# PAR 占全谱约 45%-50%（纬度/云量/季节依赖，项目内无实测数据），不臆造系数。
KWH_TO_PHOTON_MOL = round(3.6e6 * 4.57 / 1e6, 2)  # ≈ 16.45

_HTTP_TIMEOUT = 25
_UA = "agri-eco-mcp/1.2 (zone dli backfill)"


def _http_get_json(url: str, timeout: int = _HTTP_TIMEOUT) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _cache_path(lat: float, lon: float) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, "dli_%.2f_%.2f.json" % (lat, lon))


def _fetch_monthly_kwh(lat: float, lon: float) -> Optional[List[Optional[float]]]:
    """NASA POWER ALLSKY_SFC_SW_DWN 12 月均值（kWh/m²/day）。"""
    cp = _cache_path(lat, lon)
    if os.path.exists(cp):
        try:
            cached = json.load(open(cp, encoding="utf-8"))
            if isinstance(cached, list) and len(cached) == 12:
                return cached
        except Exception:
            pass
    url = (
        "https://power.larc.nasa.gov/api/temporal/monthly/point"
        "?parameters=ALLSKY_SFC_SW_DWN&community=RE"
        "&longitude=%.6f&latitude=%.6f&start=2015&end=2024&format=JSON" % (lon, lat)
    )
    data = _http_get_json(url)
    if not data:
        return None
    series = data.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN")
    if not isinstance(series, dict) or not series:
        return None
    months: List[List[float]] = [[] for _ in range(12)]
    for k, v in series.items():
        if len(k) != 6:
            continue
        mm = int(k[4:6]) - 1
        if 0 <= mm < 12 and isinstance(v, (int, float)):
            months[mm].append(float(v))
    out: List[Optional[float]] = [
        round(sum(m) / len(m), 3) if m else None for m in months
    ]
    try:
        json.dump(out, open(cp, "w", encoding="utf-8"))
    except Exception:
        pass
    return out


def _annual_dli(monthly_kwh: List[Optional[float]]) -> Optional[float]:
    """年均 DLI（mol/m²/day）。需 ≥9 个月有数据，避免偏态。"""
    vals = [v for v in monthly_kwh if v is not None]
    if len(vals) < 9:
        return None
    return round(sum(vals) / len(vals) * KWH_TO_PHOTON_MOL, 2)


def _zone_coord(zd: Dict[str, Any]) -> Optional[List[float]]:
    """统一取分区坐标：优先 climate_baseline.coord，其次 centroid_lat/centroid_lon。"""
    cb = zd.get("climate_baseline", {}) or {}
    coord = cb.get("coord")
    if isinstance(coord, list) and len(coord) == 2:
        return [float(coord[0]), float(coord[1])]
    lat = cb.get("centroid_lat")
    lon = cb.get("centroid_lon")
    if lat is not None and lon is not None:
        return [float(lat), float(lon)]
    return None


def _build_dli_entries() -> Dict[str, Dict[str, Any]]:
    """为 8 个 zone 生成 DLI 输入块。返回 zone_id -> {dli_annual, dli_source}。"""
    meta = json.load(open(ZONE_META_PATH, encoding="utf-8"))
    entries: Dict[str, Dict[str, Any]] = {}
    for zd in meta.get("zones", []):
        zid = zd.get("zone_id")
        coord = _zone_coord(zd)
        if not coord:
            entries[zid] = {
                "dli_annual_mol_m2_day": None,
                "dli_source": {
                    "provider": "unavailable",
                    "zone": zid,
                    "reason": "global_zones.json 无有效坐标，不编造",
                },
            }
            continue
        monthly = _fetch_monthly_kwh(coord[0], coord[1])
        dli = _annual_dli(monthly) if monthly else None
        entries[zid] = {
            "dli_annual_mol_m2_day": dli,
            "dli_source": {
                "provider": "NASA POWER ALLSKY_SFC_SW_DWN",
                "zone": zid,
                "coord": coord,
                "conversion": "kWh/m2/day * %.2f (全谱短波辐射光子当量，非标准 PAR DLI)"
                              % KWH_TO_PHOTON_MOL,
                "note": (
                    "全谱短波辐射的光子当量，非标准 PAR DLI；PAR 占全谱约 45%-50%"
                    "（纬度/云量/季节依赖，项目内无实测数据），专业应用请自行乘 PAR 比例"
                    "或改用专用辐照度传感器。"
                ),
                "license": "NASA POWER public domain",
                "years_used": [2015, 2024],
            },
        }
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(description="global_zones.json 补分区级 DLI")
    ap.add_argument("--apply", action="store_true", help="落盘（默认 dry-run 仅报告）")
    args = ap.parse_args()

    entries = _build_dli_entries()
    print("分区 DLI（全谱短波辐射光子当量，非 PAR）:")
    for zid, e in entries.items():
        v = e["dli_annual_mol_m2_day"]
        print(f"  {zid:22s} {'— 无坐标，不编造' if v is None else str(v) + ' mol/m²/day'}")

    if args.apply:
        meta = json.load(open(ZONE_META_PATH, encoding="utf-8"))
        for zd in meta["zones"]:
            zid = zd["zone_id"]
            if zid in entries:
                cb = zd.setdefault("climate_baseline", {})
                cb["dli_annual_mol_m2_day"] = entries[zid]["dli_annual_mol_m2_day"]
                cb["dli_source"] = entries[zid]["dli_source"]
        meta["meta"]["version"] = "1.2"
        meta["meta"]["last_updated"] = "2026-10-08"
        meta["meta"]["note"] = (
            "v1.2 (2026-10-08)：climate_baseline 补 DLI（NASA POWER 全谱短波辐射"
            "光子当量，非 PAR）；派生层不写回 116 份 recipe"
        )
        json.dump(meta, open(ZONE_META_PATH, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("\n已写入 global_zones.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())