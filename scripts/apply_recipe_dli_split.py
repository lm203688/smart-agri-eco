#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
152 份 Env Recipe DLI 字段语义拆分（P0-4 整改）

背景（项目全面提升报告_2026-10-26.md §四 P0-4）：
    样本字段叫 `dli_umol_m2_day`，注释却说明它是全年气候基线、全谱短波辐射
    光子当量，并非标准 PAR DLI。这种诚实注释仍无法消除字段名对自动消费者的
    误导——自动消费者会误以为 `dli_umol_m2_day` 就是可执行的标准 PAR DLI。

整改动作（最小侵入，向后兼容）：
    1. 保留旧字段 `dli_umol_m2_day`（只读兼容），追加：
       - `deprecated: true`
       - `deprecated_reason`（人类可读说明）
       - `replaced_by: ["shortwave_photon_equivalent", "par_dli"]`
    2. 新增 `environment.shortwave_photon_equivalent`：承载当前全谱短波辐射
       光子当量值（value/unit/zone_id/source/source_file/method/derived_at/note
       原样保留），并追加：
       - `latitude_deg`（从 source_file.coord[0] 提取，无则 null）
       - `spectral_definition: "full_spectrum_shortwave"`（全谱短波，非 PAR）
       - `temporal_resolution: "annual_mean"`（气候基线年均值，无季节/光周期分解）
       - `uncertainty`（无实测，诚实标注，不编造数值）
    3. 新增 `environment.par_dli`：标准 PAR DLI 专用字段。项目内无 PAR 实测或
       可信转换（PAR 占全谱约 45%-50%，随纬度/云量/季节变化），因此：
       - `value: null`
       - `status: "unavailable_pending_measurement"`
       - `reason`（人类可读说明：禁止用于精准补光控制）

不删字段、不改 value、不改必填——保证向后兼容。下游消费者读
`par_dli.value == null` 时应判定「无可靠 PAR 依据，禁止用于精准补光控制」；
`shortwave_photon_equivalent.value` 仅作全谱短波光子当量参考。

用法：
    python scripts/apply_recipe_dli_split.py --dry-run
    python scripts/apply_recipe_dli_split.py --apply
    python scripts/apply_recipe_dli_split.py --apply --recipe-id <id>  # 单份

幂等：检测 `par_dli` 与 `shortwave_photon_equivalent` 均已存在即跳过。

审计：写入 `data/.dli_split_audit.json`，记录每次执行的配方数、时间戳、版本。
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
AUDIT_PATH = os.path.join(ROOT, "data", ".dli_split_audit.json")
MARKER_VERSION = "1.0"

DEPRECATED_REASON = (
    "字段名 `dli_umol_m2_day` 易被自动消费者误读为标准 PAR DLI，"
    "实际是全年气候基线的全谱短波辐射光子当量（非标准 PAR）。"
    "已拆分为 `shortwave_photon_equivalent`（全谱短波当量）与 "
    "`par_dli`（标准 PAR DLI，项目内无实测时为 null）。"
)

PAR_DLI_REASON = (
    "项目内无 PAR 实测或可信转换：PAR 占全谱约 45%-50%，且随纬度/云量/"
    "季节变化。禁止用于精准补光控制；待接入 PAR 专用辐照度传感器或"
    "经 E1 农艺专家审核的可信转换后再回填。"
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


def _extract_latitude(source_file: Any) -> float | None:
    """从 source_file.coord[0] 提取纬度；无则 None（不编造）。"""
    if isinstance(source_file, dict):
        coord = source_file.get("coord")
        if isinstance(coord, list) and len(coord) >= 1:
            try:
                return float(coord[0])
            except (TypeError, ValueError):
                return None
    return None


def build_split(dli_old: dict) -> tuple[dict, dict, dict]:
    """从旧 dli_umol_m2_day 构造 (新 shortwave, 新 par_dli, 旧字段补标记)。

    旧字段原样保留，只追加 deprecated 三件套；新字段只新增，不修改旧值。
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )

    # --- 1. shortwave_photon_equivalent：继承旧值 + 追加语义字段 ---
    shortwave = dict(dli_old)
    shortwave["spectral_definition"] = "full_spectrum_shortwave"
    shortwave["temporal_resolution"] = "annual_mean"
    shortwave["latitude_deg"] = _extract_latitude(dli_old.get("source_file"))
    shortwave["uncertainty"] = {
        "has_estimate": False,
        "note": (
            "NASA POWER 全谱短波辐射无逐像素不确定度；PAR 占全谱比例随"
            "纬度/云量/季节变化，项目内无实测，无法量化。"
        ),
    }
    # 移除旧字段可能残留的 deprecated 标记（避免嵌套污染）
    for k in ("deprecated", "deprecated_reason", "replaced_by"):
        shortwave.pop(k, None)

    # --- 2. par_dli：无实测 → 诚实 null ---
    par_dli = {
        "value": None,
        "unit": dli_old.get("unit", "umol_m2_day"),
        "status": "unavailable_pending_measurement",
        "reason": PAR_DLI_REASON,
        "derived_at": now,
    }

    # --- 3. 旧字段补 deprecated 标记（只读兼容） ---
    old_marked = dict(dli_old)
    old_marked["deprecated"] = True
    old_marked["deprecated_reason"] = DEPRECATED_REASON
    old_marked["replaced_by"] = ["shortwave_photon_equivalent", "par_dli"]

    return shortwave, par_dli, old_marked


def process_recipe(fp: str, apply: bool) -> tuple[str, str]:
    """返回 (file, status)。status ∈ {skipped, marked, error}."""
    try:
        with open(fp, "r", encoding="utf-8") as f:
            recipe = json.load(f)
    except Exception as e:
        return os.path.basename(fp), f"error: 读取失败 {e}"

    env = recipe.get("environment")
    if not isinstance(env, dict):
        return os.path.basename(fp), "skipped: 无 environment"
    dli_old = env.get("dli_umol_m2_day")
    if not isinstance(dli_old, dict):
        return os.path.basename(fp), "skipped: 无 dli_umol_m2_day"

    # 幂等：两新字段均已存在即跳过
    if (
        "shortwave_photon_equivalent" in env
        and "par_dli" in env
        and env.get("dli_umol_m2_day", {}).get("deprecated") is True
    ):
        return os.path.basename(fp), "skipped: 已拆分"

    if apply:
        shortwave, par_dli, old_marked = build_split(dli_old)
        env["shortwave_photon_equivalent"] = shortwave
        env["par_dli"] = par_dli
        env["dli_umol_m2_day"] = old_marked
        atomic_write_json(fp, recipe)
        return os.path.basename(fp), "marked"

    return os.path.basename(fp), "dry-run: 待拆分"


def append_audit(applied: int, skipped: int, errored: int, dry_run: bool) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
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
    pending = 0
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
