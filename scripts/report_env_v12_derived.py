#!/usr/bin/env python3
"""
scripts/report_env_v12_derived.py —— Env Recipe v1.2 派生量覆盖率报告（只读）

用途：验证 P1-1 判定标准「116 配方新字段覆盖 >90%」，但**不修改任何配方文件**。
DLI / 播种深度 / VPD / 露点按项目铁律是派生量，运行时从分区级输入数据推导，
不写回配方 JSON（否则会形成两份可漂移的数据源，见 engine/derived.py 头部说明）。

判定口径（对齐 full_liftup_assessment §4 表）：
    - dli           : 由配方文件名提取 zone_id → engine.derived.derive_dli()
    - sowing_depth  : 由 crop_adapt_db 查 growth_days → engine.derived.sowing_depth_cm()
    - vpd_kpa       : engine.derived.derive_from_recipe() 的 vkd.nominal_kpa
    - dew_point_c   : engine.derived.derive_from_recipe() 的 dew_point.day_max_c
    - companion_plants : 项目内无伴生/间作数据源，一律报告为「数据源缺失」（不编造）

用法：
    python scripts/report_env_v12_derived.py
    python scripts/report_env_v12_derived.py --json   # 输出 JSON 便于 CI 断言
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import derived as dv  # noqa: E402

RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")
CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")


def _zone_from_filename(fn: str) -> Optional[str]:
    return fn.split("__", 1)[0] if "__" in fn else None


def _load_growth_days() -> Dict[str, Optional[int]]:
    """crop_adapt_db 按物种（中文名）建 growth_days 索引，同名取中位数。"""
    try:
        with open(CROP_DB, encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return {}
    acc: Dict[str, List[int]] = {}
    for zd in (db.get("zones") or {}).values():
        for c in zd.get("crops", []):
            sp = c.get("crop")
            gd = c.get("growth_days")
            if sp and isinstance(gd, (int, float)):
                acc.setdefault(sp, []).append(int(gd))
    out: Dict[str, Optional[int]] = {}
    for sp, vals in acc.items():
        vals.sort()
        mid = len(vals) // 2
        out[sp] = vals[mid] if len(vals) % 2 else round((vals[mid - 1] + vals[mid]) / 2)
    return out


def _analyze() -> Dict[str, Any]:
    growth = _load_growth_days()
    recs = sorted(f for f in os.listdir(RECIPES_DIR) if f.endswith(".json"))
    total = len(recs)

    stat = {"dli": 0, "sowing_depth_cm": 0, "vpd_kpa": 0, "dew_point_c": 0,
            "companion_plants": 0}
    dli_available = 0
    rows: List[Dict[str, Any]] = []

    for fn in recs:
        path = os.path.join(RECIPES_DIR, fn)
        try:
            with open(path, encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception:
            continue
        zone = _zone_from_filename(fn)
        sp = (recipe.get("crop") or {}).get("species", "")
        d = dv.derive_from_recipe(recipe)
        dd = dv.derive_dli(zone) if zone else {"available": False}
        sd = dv.sowing_depth_cm(growth.get(sp))

        has_dli = dd.get("available") and dd.get("mol_m2_day") is not None
        has_sd = sd is not None
        has_vpd = d.get("vkd", {}).get("nominal_kpa") is not None
        has_dp = d.get("dew_point", {}).get("day_max_c") is not None

        if has_dli: stat["dli"] += 1
        if has_dli: dli_available += 1
        if has_sd: stat["sowing_depth_cm"] += 1
        if has_vpd: stat["vpd_kpa"] += 1
        if has_dp: stat["dew_point_c"] += 1

        rows.append({
            "file": fn,
            "zone": zone,
            "crop": sp,
            "dli_mol_m2_day": dd.get("mol_m2_day") if has_dli else None,
            "sowing_depth_cm": sd if has_sd else None,
            "vpd_kpa": d.get("vkd", {}).get("nominal_kpa") if has_vpd else None,
            "dew_point_c": d.get("dew_point", {}).get("day_max_c") if has_dp else None,
            "dli_source_provider": (dd.get("source") or {}).get("provider") if has_dli else None,
        })

    # 伴生植物：项目内无数据源，全部 null（不编造）
    stat["companion_plants"] = 0  # 0/116，明确记录

    return {
        "total": total,
        "stat": stat,
        "coverage_pct": {k: round(100.0 * v / total, 1) for k, v in stat.items()},
        "dli_source": "NASA POWER ALLSKY_SFC_SW_DWN（全谱短波辐射光子当量，非 PAR）",
        "companion_plants_status": "项目内无伴生/间作数据源（crop_adapt_db / knowledge_graph / global_zones 均无），一律 null 不编造",
        "rows": rows,
    }


def _print_report(r: Dict[str, Any]) -> None:
    print("Env Recipe v1.2 派生量覆盖率报告（运行时推导，不落盘）")
    print("=" * 60)
    print(f"配方总数: {r['total']}")
    print(f"DLI 来源: {r['dli_source']}")
    print()
    for k, v in r["stat"].items():
        cov = r["coverage_pct"][k]
        mark = "✅" if cov >= 90 else ("⚠️" if cov > 0 else "❌")
        print(f"  {k:22s} {mark} {v:>4d}/{r['total']}  {cov:>5.1f}%")
    print()
    print("伴生植物:", r["companion_plants_status"])
    print()
    # 展示 DLI 极值，便于人工抽查
    vals = [(row["file"], row["dli_mol_m2_day"]) for row in r["rows"]
            if row["dli_mol_m2_day"] is not None]
    if vals:
        lo = min(vals, key=lambda x: x[1])
        hi = max(vals, key=lambda x: x[1])
        print(f"DLI 最低: {lo[0]} = {lo[1]} mol/m²/day")
        print(f"DLI 最高: {hi[0]} = {hi[1]} mol/m²/day")
    print()
    # 汇总判定
    p1_1_fields = ("dli", "sowing_depth_cm", "vpd_kpa", "dew_point_c")
    ok = all(r["coverage_pct"][k] >= 90 for k in p1_1_fields)
    print("P1-1 判定（VPD/露点/DLI/播种深度 ≥90%）：",
          "✅ 达标" if ok else "❌ 未达标")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    rep = _analyze()
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        _print_report(rep)
    p1_1 = ("dli", "sowing_depth_cm", "vpd_kpa", "dew_point_c")
    return 0 if all(rep["coverage_pct"][k] >= 90 for k in p1_1) else 1


if __name__ == "__main__":
    sys.exit(main())