#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bench_evidence_layer.py —— 给 bench 用例补 P0-1 证据层级字段

依据：项目全面提升报告_2026-10-26 §四 P0-1：
  benchmark 用例需标证据层级（L0 工程回归 / L1 农艺参考 / L2 田留出），
  当前全部用例为自生成真值（engine ±30%）→ 均属 L0 工程回归，
  不得声称"产量准确率"。

幂等：已带 evidence_layer 的用例跳过，不覆盖。

用法：
    python scripts/apply_bench_evidence_layer.py            # 干跑
    python scripts/apply_bench_evidence_layer.py --apply    # 写盘
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = ROOT / "benchmarks" / "agri_recipe_bench" / "cases"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(CASES_DIR.rglob("*.json"))
    touched = 0
    skipped = 0
    for f in files:
        try:
            case = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"❌ {f.name}: JSON 解析失败 {e}")
            return 1
        if "evidence_layer" in case:
            skipped += 1
            continue
        # 当前全部用例为自生成真值 → L0 工程回归（诚实，非农艺准确率）
        case["evidence_layer"] = "L0_engineering_regression"
        touched += 1
        if args.apply:
            f.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"{'[OK] 已补 ' if args.apply else '[dry] 待补 '}"
          f"{touched} 个用例（跳过已有 {skipped}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
