#!/usr/bin/env python3
"""
scripts/generate_env_recipes.py —— 从 crop_adapt_db 生成全量 Env Recipe v1 配方

把 data/crop_adapt_db.json 中每个作物的环境参数（temp_range_c / ph_range / water_ml_day /
key_risks）包装成一份 schema 合规的 Env Recipe，写入 data/env_recipes/<zone>__<crop>.json。

设计原则（诚实优先）：
  - 只映射数据库里真实存在的参数；数据库没有的（光谱/CO2/EC）留空，不编造
  - exception_handling 由 key_risks 生成，动作统一指向 agri_diagnose_pest 诊断，不虚构农艺处方
  - execution_log / outcome / image_consent 按 day-1 协议留位（空结构）

用法：
    python scripts/generate_env_recipes.py            # 生成（覆盖 data/env_recipes/）
    python scripts/generate_env_recipes.py --dry-run  # 只统计，不写盘
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "crop_adapt_db.json")
OUT_DIR = os.path.join(ROOT, "data", "env_recipes")


def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")


def build_recipe(zone_id: str, entry: dict, db_meta: dict) -> dict:
    temp = entry.get("temp_range_c", [20, 28])
    lo, hi = (temp + [temp[-1]])[:2] if len(temp) >= 1 else [20, 28]
    ph = entry.get("ph_range", [6.0, 7.0])
    ph_mid = round((ph[0] + ph[1]) / 2, 2) if len(ph) > 1 else ph[0]
    sources = [{"title": s, "url": "", "accessed_at": db_meta.get("last_updated", "")}
               for s in db_meta.get("data_sources", [])]
    return {
        "protocol": "env-recipe",
        "recipe_version": "1.0.0",
        "crop": {
            "species": entry.get("crop", ""),
            "latin": entry.get("latin", ""),
            "family": entry.get("family", ""),
        },
        "stage": "full_cycle",
        "device_profile": {
            "device_class": "other",
            "sensor_capability": ["temp", "humidity"],
        },
        "environment": {
            "temperature": {"day_c": hi, "night_c": lo},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {
                "ph": ph_mid,
                "water_ml_day": entry.get("water_ml_day", 300),
            },
            "airflow": {"level": "medium"},
        },
        "exception_handling": [
            {"condition": f"出现「{risk}」相关症状",
             "action": "经 agri_diagnose_pest 工具诊断后按建议处理",
             "severity": "warn"}
            for risk in entry.get("key_risks", [])[:3]
        ],
        "execution_log": [],
        "outcome": {},
        "image_consent": {"captured": False, "license": "", "attribution": ""},
        "sources": sources,
        "license": "CC-BY-4.0",
    }


def main() -> int:
    dry = "--dry-run" in sys.argv
    with open(DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)
    meta = db.get("meta", {})

    os.makedirs(OUT_DIR, exist_ok=True)
    written, skipped = 0, 0
    for zone_id, zdata in db.get("zones", {}).items():
        for entry in zdata.get("crops", []):
            crop = entry.get("crop", "")
            if not crop:
                skipped += 1
                continue
            recipe = build_recipe(zone_id, entry, meta)
            path = os.path.join(OUT_DIR, f"{_sanitize(zone_id)}__{_sanitize(crop)}.json")
            if not dry:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(recipe, f, ensure_ascii=False, indent=2)
            written += 1

    print(f"{'[dry-run] ' if dry else ''}生成 {written} 份 Env Recipe → {os.path.relpath(OUT_DIR, ROOT)}"
          + (f"，跳过 {skipped}" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
