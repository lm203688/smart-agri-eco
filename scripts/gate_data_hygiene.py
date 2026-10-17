#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_data_hygiene.py —— 数据目录卫生门禁

GAP_AUDIT §F1/F2/F3：
  - F1：`data/_demo_runtime/` 560 个文件混入真实数据目录，遍历脚本可能误算
  - F2：4 个 `.bak_*` 备份文件未清理
  - F3：`data/snapshots/` 空目录（设计了但没用过）

本门禁在 CI 中拦截以下情况：
  1) `data/*.bak_*` 存在 → 失败（说明没有走 backup_data.py 的自动备份策略）
  2) 遍历脚本对 `_` 前缀目录未排除 → 手动审计（本门禁只报告，不阻断）

对 F1（_demo_runtime）：本门禁只在报告里列出被排除的目录，不失败——因为
这些目录是 demo 运行时必需的。真正重要的是**遍历脚本必须显式排除**。

用法：
    python scripts/gate_data_hygiene.py
    python scripts/gate_data_hygiene.py --strict    # bak 存在即失败
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    errs: list[str] = []
    warnings: list[str] = []

    # F2：.bak_* 文件
    baks = list(DATA.glob("*.bak_*"))
    if baks:
        if args.strict:
            errs.append(f"发现 {len(baks)} 个 .bak_* 文件（应走 scripts/backup_data.py 的 .backups/ 目录）：")
            for b in baks[:5]:
                errs.append(f"  - {b.name}")
        else:
            warnings.append(f".bak_* 文件 {len(baks)} 个（建议清理）：{[b.name for b in baks[:3]]}")

    # F1：_demo_runtime 报告（不阻断）
    demo_runtime = DATA / "_demo_runtime"
    if demo_runtime.exists():
        n = sum(1 for _ in demo_runtime.rglob("*") if _.is_file())
        warnings.append(
            f"data/_demo_runtime/ 有 {n} 个文件（demo 运行时）；"
            f"所有遍历 data/**/*.json 的脚本必须显式排除 _ 前缀目录"
        )

    # F3：snapshots 空目录
    snapshots = DATA / "snapshots"
    if snapshots.exists() and not any(snapshots.iterdir()):
        warnings.append("data/snapshots/ 空目录（evolution.py 会写入，当前无快照）")

    # 检查 data/*.json 里是否混入下划线前缀目录内容
    bad_jsons = list(DATA.glob("_*/*.json"))
    if bad_jsons:
        warnings.append(f"data/_*/ 下有 {len(bad_jsons)} 个 JSON（应确保遍历脚本排除）")

    if errs:
        print("❌ 数据卫生门禁失败：")
        for e in errs:
            print(f"  {e}")
        return 1

    if warnings:
        print("⚠  数据卫生警告：")
        for w in warnings:
            print(f"  {w}")

    print("✅ 数据卫生门禁通过（strict=%s）" % args.strict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
