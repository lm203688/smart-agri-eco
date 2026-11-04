#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/bind_geo_zone.py —— Env Recipe v1.3 地域绑定脚本（零依赖）。

把 152 份 Env Recipe 的 geo_binding 字段从文件名约定 <zone>__<crop>.json 解析并落位，
与 crop_adapt_db.json 的 8 气候区 / global_zones.json 权威元数据对齐。
不做数据层新建：绑定是「文件名的可查询冗余」，消费方（control_agent._load_recipe /
geo_recipe._lookup_recipes）仍靠文件名解析，行为不变。

执行：
    python scripts/bind_geo_zone.py            # dry-run
    python scripts/bind_geo_zone.py --write    # 写盘

幂等：已含 geo_binding 且 zone_id 匹配的文件不重复写（不覆盖已有正确绑定）。

零依赖（stdlib only），完全离线。与 fill_source_urls.py / validate_env_recipe.py 同风格。
"""
from __future__ import annotations

import glob
import json
import os
import sys
import argparse
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_DIR = os.path.join(ROOT, "data", "env_recipes")
ADAPT_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
GLOBAL_ZONES = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")

BOUND_AT = "2026-11-04"
BINDING_METHOD = "filename_convention"
SOURCE = "global_zones.json (zone_name/koppen_class) + crop_adapt_db.json (zone作物集合)"


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[失败] 读取 {path}: {e}")
        return None


def _zone_meta() -> Dict[str, Dict[str, str]]:
    """global_zones.json → {zone_id: {zone_name, koppen_class}}。"""
    gz = _load_json(GLOBAL_ZONES)
    if not gz or "zones" not in gz:
        return {}
    out = {}
    for z in gz.get("zones", []):
        if isinstance(z, dict) and z.get("zone_id"):
            out[z["zone_id"]] = {
                "zone_name": z.get("zone_name", ""),
                "koppen_class": z.get("koppen_class", ""),
            }
    return out


def _adapt_zones() -> Dict[str, List[str]]:
    """crop_adapt_db.json → {zone_id: [crops...]}，用于校验作物归属。"""
    ad = _load_json(ADAPT_DB)
    if not ad or "zones" not in ad:
        return {}
    out = {}
    for zid, zinfo in ad.get("zones", {}).items():
        if isinstance(zinfo, dict):
            out[zid] = [c.get("crop", "") for c in zinfo.get("crops", [])]
    return out


def bind_recipes(write: bool) -> Dict[str, int]:
    stats = {"recipes": 0, "bound": 0, "already_bound": 0, "zone_missing": 0,
             "crop_not_in_zone": 0, "skipped_write": 0, "errors": 0}
    zmeta = _zone_meta()
    adapt = _adapt_zones()
    if not zmeta:
        print("[失败] global_zones.json 无 zone 元数据，中止")
        stats["errors"] += 1
        return stats

    for fp in sorted(glob.glob(os.path.join(RECIPE_DIR, "*.json"))):
        stats["recipes"] += 1
        base = os.path.splitext(os.path.basename(fp))[0]
        if "__" not in base:
            print(f"[跳过] 文件名无 <zone>__<crop> 约定: {base}")
            stats["errors"] += 1
            continue
        zone_id, crop = base.split("__", 1)
        d = _load_json(fp)
        if not d:
            stats["errors"] += 1
            continue

        # 幂等：已有正确绑定不重写
        existing = d.get("geo_binding")
        if isinstance(existing, dict) and existing.get("zone_id") == zone_id:
            stats["already_bound"] += 1
            continue

        zm = zmeta.get(zone_id)
        if not zm:
            print(f"[失败] zone_id 不在 global_zones.json: {zone_id} ({base})")
            stats["zone_missing"] += 1
            stats["errors"] += 1
            continue

        adapt_crops = adapt.get(zone_id, [])
        if adapt_crops and crop not in adapt_crops:
            print(f"[提示] 作物 {crop} 不在 {zone_id} 的 crop_adapt_db 作物集合（可能为扩展配方）")

        binding = {
            "zone_id": zone_id,
            "zone_name": zm["zone_name"],
            "koppen_class": zm["koppen_class"],
            "binding_method": BINDING_METHOD,
            "source": SOURCE,
            "bound_at": BOUND_AT,
        }
        d["geo_binding"] = binding
        if write:
            try:
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                stats["bound"] += 1
            except Exception as e:
                print(f"[失败] 写 {fp}: {e}")
                stats["errors"] += 1
        else:
            stats["bound"] += 1
            stats["skipped_write"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="实际写盘")
    args = ap.parse_args()

    stats = bind_recipes(args.write)
    print(f"=== 地域绑定统计（write={'on' if args.write else 'dry-run'}）===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not args.write:
        print("\n（dry-run；加 --write 才写盘）")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
