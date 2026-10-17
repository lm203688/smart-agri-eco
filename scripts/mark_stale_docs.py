#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mark_stale_docs.py —— 给 >30 天未更新的 docs/*.md 加过期头部标记

GAP_AUDIT §D4：29 篇文档 >20 天未更新，但"问题不是旧，是旧的文档还在被当权威引用"。
本脚本给这些文档顶部加一行醒目警告：

    > ⚠️ **本文档最后更新于 YYYY-MM-DD（距今 N 天），可能已过期。权威口径见 `docs/CORE_OBJECTIVE.md`。**

幂等：重复运行不会叠加警告行。

用法：
    python scripts/mark_stale_docs.py                # 加标记
    python scripts/mark_stale_docs.py --check        # 校验是否有过期文档未标记（CI 用）
    python scripts/mark_stale_docs.py --days 30      # 阈值天数（默认 30）
    python scripts/mark_stale_docs.py --dry-run      # 打印将处理的文档
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

STALE_MARKER = "本文档最后更新于 {date}（距今 {days} 天）"
SKIP_PREFIXES = ("GAP_AUDIT", "FOUNDATION_AUDIT", "next_stage_vision")  # 报告类不标


def _mtime_days(path: Path) -> int:
    return int((time.time() - path.stat().st_mtime) // 86400)


def _build_warning(path: Path, days: int) -> str:
    mtime = path.stat().st_mtime
    date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    return (
        f"> ⚠️ **{STALE_MARKER.format(date=date, days=days)}，可能已过期。"
        f"权威口径见 `docs/CORE_OBJECTIVE.md`。**\n"
    )


def _has_marker(text: str) -> bool:
    return "⚠️" in text[:400] and "可能已过期" in text[:400]


def process(days_threshold: int = 30, check: bool = False, dry_run: bool = False) -> int:
    errs = 0
    updated = 0
    skipped = 0

    # 递归遍历 docs/ 及子目录（如 planning/）下的所有 md
    for p in sorted(DOCS.rglob("*.md")):
        if any(p.name.startswith(pre) for pre in SKIP_PREFIXES):
            skipped += 1
            continue
        if p.name == "CORE_OBJECTIVE.md":  # 权威源不标
            skipped += 1
            continue

        days = _mtime_days(p)
        if days < days_threshold:
            continue

        text = p.read_text(encoding="utf-8", errors="ignore")
        if _has_marker(text):
            continue

        warning = _build_warning(p, days)
        new_text = warning + text

        if check:
            errs += 1
            print(f"  MISS  {p.name}（{days} 天未更新，未标记）")
            continue
        if dry_run:
            print(f"  WOULD  {p.name}（{days} 天）")
            continue

        p.write_text(new_text, encoding="utf-8")
        updated += 1
        print(f"  OK    {p.name}（{days} 天）")

    if check:
        if errs:
            print(f"\n❌ {errs} 篇过期文档未标记")
            return 1
        print("✅ 所有过期文档均已标记")
        return 0

    print(f"\n更新 {updated} 篇，跳过 {skipped} 篇（不含 {days_threshold} 天阈值内的文档）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return process(args.days, args.check, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
