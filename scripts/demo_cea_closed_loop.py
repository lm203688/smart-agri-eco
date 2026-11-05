#!/usr/bin/env python3
"""demo_cea_closed_loop.py —— CEA 单点闭环 demo（技术验证 · 非经济可行）

跑通「传感器 → 控制器 → 执行器 → 回填置信度」完整闭环，并接入
GrowBatchStore（Observation + shadow Action，事件日志 append-only）。

诚实边界（与项目红线一致）：
  - 技术验证，非经济可行（不构成任何真实设备/产线经济性声明）。
  - 动作默认 shadow/dry_run，不真实执行；真实执行需人工确认 + 网关下发。
  - 环境为一阶响应 + 高斯噪声的模拟模型，非真实温室物理模型。

用法：
    python scripts/demo_cea_closed_loop.py [--crop 番茄] [--zone temperate_continental] [--steps 20]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.cea_controller import CEAClosedLoop  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="CEA 单点闭环 demo（技术验证·非经济可行）")
    ap.add_argument("--crop", default="番茄")
    ap.add_argument("--zone", default="temperate_continental")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", default="cea_demo")
    ap.add_argument("--out", default=None, help="结果落盘路径（默认不落盘）")
    args = ap.parse_args()

    loop = CEAClosedLoop(crop=args.crop, zone_id=args.zone, seed=args.seed)
    result = loop.run(steps=args.steps, persist=False)

    print("=" * 80)
    print("CEA 单点闭环 demo · 技术验证（非经济可行）")
    print("=" * 80)
    print(f"crop={args.crop}  zone={args.zone}  steps={args.steps}")
    print(f"recipe_loaded={result['recipe_loaded']}  model={result['model']}")
    print(f"setpoints={result['setpoints']}")
    print(f"closed_loop_confidence={result['feedback']['closed_loop_confidence']}")
    print(f"per_metric={result['feedback']['per_metric']}")
    print("-" * 80)
    print("闭环轨迹（观测 vs 设定，每步）:")
    for rec in result["history"]:
        print(f"  step={rec['step']:>3}  obs={rec['observed']}  "
              f"cmd={rec['n_commands']}")
    print("-" * 80)
    print(f"honest_note: {result['honest_note']}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n结果已落盘: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
