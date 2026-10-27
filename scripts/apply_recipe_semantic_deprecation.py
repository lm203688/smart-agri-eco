#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
152 份 Env Recipe 播种深度语义降级标记（P0-3 整改）

背景（docs/REPORT_IMPLEMENTATION_2026-10-27.md）：
    所有 152 份配方的 sowing_depth_cm 均使用 `method = growth_days_over_200`
    派生——`growth_days/200` 是启发式近似，不是作物/品种级权威农艺参数
    （真实依据应为种子大小、覆土要求、基质和湿度条件）。因此该字段
    **不可**作为可执行参数直接进入设备动作。

整改动作（最小侵入）：
    1. 保留原字段（value/unit/source/method/growth_days/note 不动）
    2. 追加 `estimated_unsafe_for_execution: true`
    3. 追加 `safety_note`（人类可读说明）
    4. 追加 `deprecation_marker_version` / `deprecation_marker_at`（幂等审计）

不删字段、不改 schema 必填、不改 value——保证向后兼容，下游消费者可继续读
旧字段，但读 `estimated_unsafe_for_execution=true` 时应阻断进入控制层。

用法：
    python scripts/apply_recipe_semantic_deprecation.py --dry-run
    python scripts/apply_recipe_semantic_deprecation.py --apply
    python scripts/apply_recipe_semantic_deprecation.py --apply --recipe-id <id>  # 单份

幂等：脚本检测 `deprecation_marker_version` 已存在即跳过；重复执行不重复写入。

审计：写入 `data/env_recipes/.semantic_deprecation_audit.json`，记录每次执行
    的配方数、时间戳、marker_version。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")
# 审计文件放 data/ 根，不放 env_recipes/——避免被 validate_env_recipe.py
# 当配方扫入导致校验失败（audit 是 list 不是 object）。
AUDIT_PATH = os.path.join(ROOT, "data", ".semantic_deprecation_audit.json")
MARKER_VERSION = "1.0"

SAFETY_NOTE = (
    "sowing_depth_cm.value 由 `growth_days/200` 派生，是启发式近似，"
    "不是作物/品种级权威农艺依据。真实依据应为种子大小、覆土要求、"
    "基质类型和湿度条件。该字段进入设备执行层前必须经 E1 农艺专家"
    "审核；未通过审核时只允许在建议层展示（标注『待确认』），"
    "不得作为自动化控制参数。"
)


def atomic_write_json(path: str, obj: Any) -> None:
    """原子写 JSON（同 core/atomic_io.py 策略）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def list_recipe_files(only_id: str | None = None) -> list[str]:
    files = sorted(
        os.path.join(RECIPES_DIR, f)
        for f in os.listdir(RECIPES_DIR)
        if f.endswith(".json") and not f.startswith(".")
    )
    if only_id:
        target = os.path.join(RECIPES_DIR, f"{only_id}.json")
        if target not in files:
            return []
        return [target]
    return files


def process_recipe(fp: str, apply: bool) -> tuple[str, str]:
    """返回 (file, status)。status ∈ {skipped, marked, error}. """
    try:
        with open(fp, "r", encoding="utf-8") as f:
            recipe = json.load(f)
    except Exception as e:
        return os.path.basename(fp), f"error: 读取失败 {e}"

    sd = recipe.get("sowing_depth_cm")
    if not isinstance(sd, dict):
        return os.path.basename(fp), "skipped: 无 sowing_depth_cm"

    # 幂等：已标记过则跳过
    if sd.get("deprecation_marker_version") == MARKER_VERSION:
        return os.path.basename(fp), "skipped: 已标记"

    if apply:
        sd["estimated_unsafe_for_execution"] = True
        sd["safety_note"] = SAFETY_NOTE
        sd["deprecation_marker_version"] = MARKER_VERSION
        sd["deprecation_marker_at"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        recipe["sowing_depth_cm"] = sd
        atomic_write_json(fp, recipe)
        return os.path.basename(fp), "marked"

    return os.path.basename(fp), "dry-run: 待标记"


def append_audit(applied: int, skipped: int, errored: int, dry_run: bool) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    record = {
        "ts": ts,
        "marker_version": MARKER_VERSION,
        "mode": "dry-run" if dry_run else "apply",
        "applied": applied,
        "skipped": skipped,
        "errored": errored,
    }
    audit = []
    if os.path.exists(AUDIT_PATH):
        try:
            with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                audit = json.load(f)
        except Exception:
            audit = []
    if not isinstance(audit, list):
        audit = []
    audit.append(record)
    os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
    atomic_write_json(AUDIT_PATH, audit)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写入（默认）")
    ap.add_argument("--recipe-id", help="只处理指定 recipe_id（默认全库）")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        args.dry_run = True  # 默认 dry-run

    files = list_recipe_files(args.recipe_id)
    if not files:
        print(f"错误：未在 {RECIPES_DIR} 找到匹配的配方")
        return 1

    applied = 0
    skipped = 0
    pending = 0  # dry-run 模式下会写入但未执行的数量
    errored = 0
    for fp in files:
        fname, status = process_recipe(fp, args.apply)
        if status.startswith("marked"):
            applied += 1
        elif status.startswith("skipped"):
            skipped += 1
        elif status.startswith("dry-run"):
            pending += 1
        else:
            errored += 1
        if args.dry_run:
            print(f"  [{status}] {fname}")

    print("=" * 60)
    print(f"配方总数：{len(files)}")
    print(f"  marked：{applied}")
    print(f"  skipped：{skipped}")
    if args.dry_run:
        print(f"  pending：{pending}（dry-run 未实际写入）")
    print(f"  errored：{errored}")
    if args.dry_run:
        print("（dry-run 模式：未写入任何文件）")
        print("  若要应用，加 --apply 参数")

    append_audit(applied, skipped, errored, args.dry_run)
    print(f"审计记录已追加至 {AUDIT_PATH}")
    return 0 if errored == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
