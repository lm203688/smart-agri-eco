#!/usr/bin/env python3
"""Example 03: 症状描述 → 病虫害诊断

用法:
    python examples/03_diagnose.py
    python examples/03_diagnose.py --crop 番茄 --symptom "果实顶端凹陷、发褐"
    python examples/03_diagnose.py --crop 生菜 --symptom "叶片下部先黄化"

诚实边界:
    本工具走「Shannon 零误报」策略——未命中知识库具体条目时返回 unconfirmed，
    而非编造结论。这是设计选择，不是缺陷。

前置:
    在项目根目录运行；Python ≥ 3.10；零第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import _tool_diagnose_pest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="症状 → 病虫害/营养缺乏诊断")
    ap.add_argument("--crop", type=str, default="番茄")
    ap.add_argument("--symptom", type=str, default="果实顶端凹陷、发褐")
    ap.add_argument("--stage", type=str, default="fruiting")
    ap.add_argument("--rh", type=float, default=70)
    ap.add_argument("--temp-c", type=float, default=24)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    payload = {
        "crop": args.crop,
        "symptom_description": args.symptom,
        "growth_stage": args.stage,
        "environment": {"rh_pct": args.rh, "temp_c": args.temp_c},
    }
    result = _tool_diagnose_pest(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))

    print("\n--- 诊断结论 ---")
    print(f"  diagnosis:          {result.get('diagnosis', '?')}")
    print(f"  confirmation:       {result.get('confirmation_status', '?')}")
    print(f"  severity:           {result.get('severity', '?')}")
    print(f"  confidence:         {result.get('diagnosis_confidence', '?')}")
    acts = result.get("actions") or []
    if acts:
        print(f"  建议动作 ({len(acts)}):")
        for a in acts[:3]:
            if isinstance(a, dict):
                print(f"    - {a}")
            else:
                print(f"    - {a}")
    alts = result.get("alternative_diagnoses") or []
    if alts:
        print(f"  备选 ({len(alts)}):", ", ".join(str(x) for x in alts[:5]))
    gate = result.get("evidence_gate") or {}
    if gate.get("missing"):
        print(f"  证据缺口:", "; ".join(gate["missing"][:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
