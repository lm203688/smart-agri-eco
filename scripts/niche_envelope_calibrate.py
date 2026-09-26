#!/usr/bin/env python3
"""
P3 · 生态位包络反推校准适配分（零依赖，P0 模块复用）

0 用户下唯一能实证校准 adapt_score 的路径（docs/data_acquisition_decision.md）：
  用 GBIF 真实分布点 + P0 实时气候，反推每个作物的气候适宜包络，
  再拿 P1 已固化的 6 分区基线对照，给出每作物×每分区的适配分。

流程（按唯一 latin 去重，结果应用到所有同名条目）：
  1) GBIF occurrence/search 取真实分布点（hasCoordinate）
  2) 取最多 8 个分布点，调 fetch_monthly_climate 取其真实气候（带缓存）
  3) 聚合出 12 月气温/降水包络 [min,max]
  4) 对 6 分区：分区基线落在包络内的月份比例 → 适配分（气温 0.6 + 降水 0.4）
  5) 写回 adapt_score + calibrated=true + calibration_method/calibration_provenance

健壮性：分布点 < 3 或气候全部失败 → calibrated=false，标注原因，不伪造高分。
运行：
  python scripts/niche_envelope_calibrate.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.climate_data import fetch_monthly_climate, get_zone_climate_baseline  # noqa: E402

CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
GBIF_OCC = "https://api.gbif.org/v1/occurrence/search"
_UA = {"User-Agent": "agri-eco-demo/1.0 (demo)"}
_DELAY = 0.25
MAX_POINTS = 6
# GBIF 分布点磁盘缓存：让重跑完全离线、可复现（与气候缓存解耦）
GBIF_CACHE_DIR = os.path.join(ROOT, "data", "_demo_runtime", "gbif_occ_cache")


def gbif_points(latin: str, limit: int = 30) -> List[Dict[str, float]]:
    # 离线缓存优先（重跑不再打 GBIF，且复用已抓取气候的点）
    os.makedirs(GBIF_CACHE_DIR, exist_ok=True)
    cp = os.path.join(GBIF_CACHE_DIR, latin.replace(" ", "_") + ".json")
    if os.path.exists(cp):
        try:
            return json.load(open(cp, encoding="utf-8"))
        except Exception:
            pass
    url = (GBIF_OCC + "?scientificName=" + urllib.parse.quote(latin) +
           "&hasCoordinate=true&limit=" + str(limit))
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        pts = []
        for o in d.get("results", []):
            lat = o.get("decimalLatitude")
            lon = o.get("decimalLongitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) \
                    and -90 <= lat <= 90 and -180 <= lon <= 180:
                pts.append({"lat": lat, "lon": lon})
        try:
            json.dump(pts, open(cp, "w", encoding="utf-8"))
        except Exception:
            pass
        return pts
    except Exception:
        return []


def climate_envelope(pts: List[Dict[str, float]]) -> Optional[Dict[str, Any]]:
    temps, precs = [], []
    n_ok = 0
    for p in pts[:MAX_POINTS]:
        cl = fetch_monthly_climate(p["lat"], p["lon"], years=5)
        time.sleep(0.3)  # 礼貌限速，避免 NASA POWER / Open-Meteo 触发限流
        mc = cl.get("monthly_mean_c")
        if not mc or len(mc) != 12 or any(m is None for m in mc):
            continue
        temps.append(mc)
        pc = cl.get("monthly_precip_mm") or [None] * 12
        precs.append([(x if x is not None else 0) for x in pc])
        n_ok += 1
    if len(temps) < 3:
        return None
    
    # 修复：改用中位数聚合，避免GBIF坐标噪声拖偏均值
    # 例如香茅30点中有3个异常低温点(13.7°C)，用中位数可避免被噪声拖偏
    import statistics
    temp_env = [[statistics.median(t[m] for t in temps), max(t[m] for t in temps)] for m in range(12)]
    precip_env = [[statistics.median(p[m] for p in precs), max(p[m] for p in precs)] for m in range(12)]
    return {"temp_env": temp_env, "precip_env": precip_env, "n_samples": n_ok}


def score_zone(baseline: Dict[str, Any], env: Dict[str, Any]) -> float:
    btemp = baseline.get("monthly_mean_c") or []
    bprec = baseline.get("monthly_precip_mm") or [None] * 12
    if len(btemp) != 12:
        return 0.0
    temp_hit = sum(1 for m in range(12)
                   if env["temp_env"][m][0] <= btemp[m] <= env["temp_env"][m][1]) / 12
    prec_hit = 0
    pcount = 0
    for m in range(12):
        if bprec[m] is not None:
            pcount += 1
            if env["precip_env"][m][0] <= bprec[m] <= env["precip_env"][m][1]:
                prec_hit += 1
    prec_score = (prec_hit / pcount) if pcount else 0.5
    return round(temp_hit * 0.6 + prec_score * 0.4, 2)


def main() -> None:
    with open(CROP_DB, encoding="utf-8") as f:
        cdb = json.load(f)
    zones = cdb.get("zones", {})
    crops = [c for z in zones.values() for c in z.get("crops", [])]

    # 关键修复：crop_adapt_db.json 的分区以 zone_id 作为字典键，
    # 作物对象本身不含 zone_id 字段，必须从字典键取所属分区。
    by_latin: Dict[str, List[dict]] = {}
    crop_zone: Dict[int, str] = {}  # id(crop) -> 所属 zone_id
    for zid, z in zones.items():
        for c in z.get("crops", []):
            lat = (c.get("latin") or "").strip()
            if not lat:
                c["calibrated"] = False
                c["calibration_method"] = None
                c["calibration_note"] = "无 latin，跳过生态位反推"
                continue
            by_latin.setdefault(lat, []).append(c)
            crop_zone[id(c)] = zid

    # 分区 id 列表 = crop_adapt_db.json 的字典键（即 zone_id，与 global_zones.json 对齐）
    real_zone_ids = list(zones.keys())

    done = 0
    skipped = 0
    for latin in sorted(by_latin):
        pts = gbif_points(latin)
        time.sleep(_DELAY)
        if len(pts) < 3:
            for c in by_latin[latin]:
                c["calibrated"] = False
                c["calibration_method"] = None
                c["calibration_note"] = f"GBIF 分布点不足（{len(pts)}），无法反推"
            skipped += 1
            continue
        env = climate_envelope(pts)
        if not env:
            for c in by_latin[latin]:
                c["calibrated"] = False
                c["calibration_method"] = None
                c["calibration_note"] = "气候取样不足（<3 点成功），无法反推"
            skipped += 1
            continue
        # 逐分区打分
        scores = {}
        for zid in real_zone_ids:
            base = get_zone_climate_baseline(zid)
            if base:
                scores[zid] = score_zone(base, env)
        if not scores:
            for c in by_latin[latin]:
                c["calibrated"] = False
                c["calibration_note"] = "无分区基线可对照"
            skipped += 1
            continue
        # 取该作物所在分区的适配分（若无匹配则用全分区均值）
        for c in by_latin[latin]:
            zid = crop_zone.get(id(c))
            sc = scores.get(zid)
            if sc is None:
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
            # 契约字段：calibrated 标记必须有 measured_calibration 证据
            # （test_agents.TestCropDataIntegrity 守卫，历史上曾出现 34 个作物只有标记无证据）
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
            done += 1

    with open(CROP_DB, "w", encoding="utf-8") as f:
        json.dump(cdb, f, ensure_ascii=False, indent=2)

    calibrated = sum(1 for c in crops if c.get("calibrated"))
    print(f"唯一拉丁名 {len(by_latin)} | 反推成功 {done} 条目 | 跳过 {skipped} 种 | "
          f"110 中 calibrated=True {calibrated}")
    print("已写回", CROP_DB)


if __name__ == "__main__":
    main()
