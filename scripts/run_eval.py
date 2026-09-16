#!/usr/bin/env python3
"""
scripts/run_eval.py —— 运行 AI 评测基线（评审 P0-H）

调用 engine/eval.run_all()，打印报告。已实现指标（分区一致率）给出真实数字；
脚手架项标注 NOT_IMPLEMENTED，绝不谎报。

用法：
    python scripts/run_eval.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.eval import run_all  # noqa: E402


def _fmt(v: float) -> str:
    return f"{v * 100:.1f}%"


def main() -> int:
    report = run_all()

    zc = report["zone_consistency"]
    print("=" * 56)
    print("智慧农业生态 · AI 评测基线报告")
    print("=" * 56)

    print(f"\n[1] 分区分类一致率（GAEZ/Köppen 代理）: {_fmt(zc['rate'])}  "
          f"({zc['correct']}/{zc['total']})")
    if zc["mismatches"]:
        print("    暴露的局限：")
        for m in zc["mismatches"]:
            print(f"      - ({m['lat']},{m['lon']}) 期望 {m['expected']} / 实际 {m['got']} ｜ {m['note']}")

    cov = report["crop_db_coverage"]
    print(f"\n[2] 作物库分区覆盖: {_fmt(cov['coverage'])}  ({cov['covered']}/{cov['total']})")
    if cov["gaps"]:
        print("    覆盖缺口（信息性，不等价于适宜性错误）：")
        for g in cov["gaps"]:
            print(f"      - 作物「{g['crop']}」不在分区 {g['zone']} 清单（待补库）")

    print("\n[3] 待就绪评测（脚手架，NOT_IMPLEMENTED）：")
    for k, v in report["pending"].items():
        print(f"      - {k}: {v['status']} ｜ {v['reason']}")

    print("\n" + "=" * 56)
    print("说明：已实现指标为真实可跑基线；脚手架项待数据/模型就绪后填充，"
          "绝不谎报分数。每个能力都需对照评测（评审 §2.3 硬建议）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
