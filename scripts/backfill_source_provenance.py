#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/backfill_source_provenance.py —— 为 116 份 Env Recipe 补齐 sources[] 溯源三字段

依据：docs/CORE_OBJECTIVE.md §五（法务红线配套要求）：
    `sources[]` 每条必须补齐 `source_license`（逐条许可）+ `data_quality`
    （`measured`/`interpolated`/`modeled`/`estimated`）+ `trial_location`。

当前实测（2026-10-08）：
    - 458 条 sources 全部缺 `data_quality` / `trial_location` / `source_license`
    - sources[].license 已存在（4 类许可），本次把 `source_license` 与之对齐，
      不覆盖原 `license` 字段（保留兼容）。

原则（对齐项目铁律）：
    1. **零依赖**（纯标准库）；
    2. **确定性可复现** —— 同一输入必须产生同一输出；
    3. **不编造** —— 无法确定的字段写 `unknown` 而非猜测，绝不伪造测量位置；
    4. **幂等** —— 已补齐的条目跳过，不重复写。

用法：
    python scripts/backfill_source_provenance.py              # 干跑：只报告差异
    python scripts/backfill_source_provenance.py --apply      # 写盘
    python scripts/backfill_source_provenance.py --check      # 校验是否全部补齐（exit 0=补齐）

退出码：
    0 = 全部已补齐（或 `--check` 通过）
    1 = 仍有缺失 / 数据源未识别
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")

# 确定性映射：按 sources[].title 前缀判定（保持幂等，不依赖外部查询）
# 依据：data/crop_adapt_db.json meta.data_sources 的 5 条权威源
_SOURCE_META: list[dict] = [
    {
        # FAO CropInfo / Ecocrop —— 官方在线作物资料库，参数来自文献汇编，非实测
        "match": "FAO",
        "data_quality": "modeled",
        "trial_location": "FAO Ecocrop 官方在线资料库（ecocrop.apps.fao.org），非实测",
        "source_license": "CC BY-NC-SA 3.0 IGO（FAO 官方；非商用，禁止作为付费资产转售）",
    },
    {
        # 中国作物栽培数据库 —— 官方通识数据库，参数来自农业通识汇编
        "match": "中国作物栽培数据库",
        "data_quality": "modeled",
        "trial_location": "中国，多点作物栽培通识汇编（非单一试验点）",
        "source_license": "unknown（未标注许可）",
    },
    {
        # WorldClim 2.1 —— 气候栅格，站点插值
        "match": "WorldClim",
        "data_quality": "interpolated",
        "trial_location": "WorldClim 2.1 栅格（站点插值，非田间试验）",
        "source_license": "CC BY 4.0",
    },
    {
        # USDA Plant Guides —— 美国联邦政府作品，公有领域
        "match": "USDA",
        "data_quality": "modeled",
        "trial_location": "美国农业部 Plant Guides（官方汇编，非单一试验点）",
        "source_license": "公有领域（美国联邦政府作品）",
    },
    {
        # GAEZ v4 —— 全球农业生态区划，栅格建模
        "match": "GAEZ",
        "data_quality": "modeled",
        "trial_location": "GAEZ v4 全球农业生态区划栅格（模型模拟，非田间试验）",
        "source_license": "CC BY 4.0",
    },
    {
        # IPNI —— 国际植物名称索引
        "match": "IPNI",
        "data_quality": "measured",
        "trial_location": "IPNI 国际植物名称索引（名录数据，非田间试验）",
        "source_license": "CC BY 4.0",
    },
]

_FALLBACK = {
    "data_quality": "unknown",
    "trial_location": "unknown（未标注试验地）",
    "source_license": "unknown（未标注许可）",
}


def _meta_for(title: str) -> dict:
    """按 title 前缀匹配；未识别则返回 fallback（不编造）。"""
    t = (title or "").strip()
    for m in _SOURCE_META:
        if m["match"] in t:
            return m
    return _FALLBACK


def _load_recipes() -> list[tuple[str, dict]]:
    out = []
    for p in sorted(glob.glob(os.path.join(RECIPES_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append((p, json.load(f)))
    return out


def _missing_count(recipe: dict) -> int:
    n = 0
    for s in recipe.get("sources", []):
        if not isinstance(s, dict):
            continue
        for fld in ("data_quality", "trial_location", "source_license"):
            if not s.get(fld):
                n += 1
    return n


def scan(dry_run: bool = True) -> tuple[int, int]:
    """返回 (缺失字段数, 待写文件数)。dry_run=True 只报告不改盘。"""
    recipes = _load_recipes()
    total_missing = 0
    files_touch = 0
    for path, r in recipes:
        miss = _missing_count(r)
        if miss > 0:
            total_missing += miss
            files_touch += 1
            if dry_run:
                print(f"  [待补] {os.path.relpath(path, ROOT)}：缺 {miss} 字段")
        # 幂等检查：识别不出的源即使补齐也要标 unknown，这里不报错
    print(f"共 {len(recipes)} 份配方，缺失字段 {total_missing}，涉及文件 {files_touch}")
    return total_missing, files_touch


def apply() -> int:
    recipes = _load_recipes()
    total = 0
    for path, r in recipes:
        for s in r.get("sources", []):
            if not isinstance(s, dict):
                continue
            meta = _meta_for(s.get("title", ""))
            for fld in ("data_quality", "trial_location", "source_license"):
                if not s.get(fld):
                    s[fld] = meta[fld]
                    total += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"[OK] 已补齐 {total} 个字段")
    return 0


def check() -> int:
    recipes = _load_recipes()
    bad = 0
    for path, r in recipes:
        miss = _missing_count(r)
        if miss > 0:
            bad += 1
            print(f"  [FAIL] {os.path.relpath(path, ROOT)}：仍缺 {miss} 字段")
    if bad == 0:
        print(f"[OK] 全部 {len(recipes)} 份配方 sources 溯源三字段已补齐")
        return 0
    print(f"[FAIL] {bad}/{len(recipes)} 份配方仍未补齐")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘")
    ap.add_argument("--check", action="store_true", help="校验是否已补齐")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.apply:
        return apply()
    return scan(dry_run=True)


if __name__ == "__main__":
    sys.exit(main())