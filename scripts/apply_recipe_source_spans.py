#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_recipe_source_spans.py —— 为 Env Recipe 生成字段级血缘 source_spans（P0-5）

依据：项目全面提升报告_2026-10-26 §四 P0-5：
  "建立字段级 source_spans：哪个来源支持哪个字段、转换和推论是什么。"

诚实边界（不编造）：
  - 只为**已可确证来源的高危派生字段**建立字段级血缘：
      · sowing_depth_cm  （P0-3，method=growth_days_over_200，crop_adapt_db）
      · environment.shortwave_photon_equivalent（P0-4，derived_from_zone，NASA POWER）
      · environment.dli_umol_m2_day（P0-4，deprecated）
  - environment.temperature / humidity / water_nutrient / airflow 当前**无字段级
    来源声明**（配方级 sources 只标注分区气候来源，未逐字段映射），诚实标
    field_level_provenance="not_established"，不猜测来源索引。
  - 字段级血缘是**声明**，不改变字段值本身；幂等：已存在则跳过。

用法：
    python scripts/apply_recipe_source_spans.py               # 干跑
    python scripts/apply_recipe_source_spans.py --apply       # 写盘
    python scripts/apply_recipe_source_spans.py --check       # 校验（exit 0=全通过）
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")

# 配方 sources[] 里提供农艺参数（crop_adapt_db）的来源 title 前缀 → 索引引用说明
_AGRONOMIC_SOURCE_PREFIXES = ("FAO GAEZ", "中国作物栽培数据库", "USDA", "IPNI")


def _recipe_source_indices(sources: list) -> list[int]:
    """返回提供农艺参数（crop_adapt_db 综合来源）的 sources[] 索引。"""
    idx = []
    for i, s in enumerate(sources or []):
        t = (s.get("title") or "")
        if any(p in t for p in _AGRONOMIC_SOURCE_PREFIXES):
            idx.append(i)
    return idx


def _build_source_spans(recipe: dict) -> dict:
    """为一份配方构建字段级血缘 source_spans（只含可确证字段）。"""
    spans: dict = {}
    sources = recipe.get("sources") or []
    env = recipe.get("environment") or {}

    # ---- sowing_depth_cm（P0-3 高危派生）----
    sd = recipe.get("sowing_depth_cm")
    if isinstance(sd, dict):
        method = sd.get("method")
        spans["sowing_depth_cm"] = {
            "derivation": method or "unknown",
            "source": sd.get("source") or "crop_adapt_db",
            "inference": sd.get("note") or (
                "生长周期派生播种深度，启发式近似，非作物/品种级权威农艺依据"),
            "evidence_grade": "E0",
            "unsafe_for_execution": bool(sd.get("estimated_unsafe_for_execution", False)),
            "recipe_source_indices": _recipe_source_indices(sources),
        }

    # ---- environment.shortwave_photon_equivalent（P0-4 全谱短波当量）----
    sw = env.get("shortwave_photon_equivalent")
    if isinstance(sw, dict):
        sf = sw.get("source_file") or {}
        spans["environment.shortwave_photon_equivalent"] = {
            "derivation": sw.get("method") or "climate_baseline_annual_mean",
            "source": sf.get("provider") or sw.get("source") or "unknown",
            "inference": sw.get("note") or "全谱短波辐射光子当量，非标准 PAR DLI",
            "evidence_grade": "E0",
            "external_source": bool(sf.get("provider")),  # NASA POWER 不在配方 sources[] 内
            "license": sf.get("license"),
        }

    # ---- environment.dli_umol_m2_day（P0-4 deprecated 旧字段）----
    dli = env.get("dli_umol_m2_day")
    if isinstance(dli, dict):
        spans["environment.dli_umol_m2_day"] = {
            "derivation": dli.get("method") or "climate_baseline_annual_mean",
            "source": (dli.get("source_file") or {}).get("provider")
                      or dli.get("source") or "unknown",
            "inference": dli.get("deprecated_reason")
                         or "字段名易被误读为标准 PAR DLI，已拆分",
            "evidence_grade": "E0",
            "deprecated": bool(dli.get("deprecated", False)),
            "replaced_by": dli.get("replaced_by", []),
        }

    # ---- 无字段级来源的 climate 字段：诚实声明 not_established ----
    no_span_fields = []
    for k in ("temperature", "humidity", "water_nutrient", "airflow"):
        if isinstance(env.get(k), dict):
            no_span_fields.append("environment." + k)
    if no_span_fields:
        spans["_field_level_not_established"] = {
            "fields": no_span_fields,
            "field_level_provenance": "not_established",
            "note": "这些字段当前仅有配方级 sources 分区气候来源，未逐字段映射"
                    "到具体来源条目；不猜测 source_indices。",
        }

    return spans


def _load_recipes() -> list[tuple[str, dict]]:
    out = []
    for p in sorted(glob.glob(os.path.join(RECIPES_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append((p, json.load(f)))
    return out


def scan(dry_run: bool = True) -> tuple[int, int]:
    recipes = _load_recipes()
    missing = 0
    for path, r in recipes:
        if "source_spans" not in r:
            missing += 1
            if dry_run:
                print(f"  [待建] {os.path.basename(path)}")
    print(f"共 {len(recipes)} 份配方，缺 source_spans {missing}")
    return missing, len(recipes)


def apply() -> int:
    recipes = _load_recipes()
    built = 0
    for path, r in recipes:
        if "source_spans" in r:
            continue  # 幂等：已有则跳过
        r["source_spans"] = _build_source_spans(r)
        built += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"[OK] 已为 {built} 份配方构建 source_spans")
    return 0


def check() -> int:
    recipes = _load_recipes()
    bad = 0
    for path, r in recipes:
        spans = r.get("source_spans")
        if not isinstance(spans, dict):
            bad += 1
            print(f"  [FAIL] {os.path.basename(path)}：缺 source_spans")
            continue
        # 高危派生字段必须有血缘声明
        sd = r.get("sowing_depth_cm")
        if isinstance(sd, dict) and "sowing_depth_cm" not in spans:
            bad += 1
            print(f"  [FAIL] {os.path.basename(path)}：sowing_depth_cm 无血缘")
    if bad == 0:
        print(f"[OK] 全部 {len(recipes)} 份配方 source_spans 字段级血缘已建")
        return 0
    print(f"[FAIL] {bad}/{len(recipes)} 份配方 source_spans 不完整")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.apply:
        return apply()
    return scan(dry_run=True)


if __name__ == "__main__":
    sys.exit(main())
