#!/usr/bin/env python3
"""Example 05: 反事实轨迹仿真（AgriWorld-Lite 机理内核）

用法:
    python examples/05_counterfactual.py
    python examples/05_counterfactual.py --crop potato --scenario cool_down_5c
    python examples/05_counterfactual.py --crop wheat --scenario light_12_to_16h --days 60

场景可选:
    light_12_to_16h   光周期 12→16h
    cool_down_5c      降温 5℃
    stop_fertilizer   停止施肥
    high_humidity     高湿
    double_water      加倍灌溉
    baseline          基线（不改任何动作）

底层机理:
    Beer-Lambert 光截获 + CO2 同化 + Q10 呼吸 + Penman-Monteith 蒸腾；
    零第三方依赖。

前置:
    在项目根目录运行；Python ≥ 3.10；零第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import _tool_counterfactual_trajectory  # noqa: E402

SCENARIOS = ["light_12_to_16h", "cool_down_5c", "stop_fertilizer",
             "high_humidity", "double_water", "baseline"]


def main() -> int:
    ap = argparse.ArgumentParser(description="反事实轨迹：如果我改某项参数，产量会怎么变")
    ap.add_argument("--crop", type=str, default="potato")
    ap.add_argument("--scenario", type=str, default="cool_down_5c", choices=SCENARIOS)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--baseline-dli", type=float, default=10.0, help="基线 DLI MJ/m²/d")
    ap.add_argument("--baseline-temp-c", type=float, default=22.0)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    result = _tool_counterfactual_trajectory({
        "crop": args.crop,
        "days": args.days,
        "quick_scenario": args.scenario,
        "baseline_dli_mj": args.baseline_dli,
        "baseline_temp_c": args.baseline_temp_c,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))

    # 高亮对比
    base = result.get("baseline") or {}
    cand = result.get("candidate") or {}
    delta = result.get("delta") or {}
    cap = result.get("theoretical_yield_cap_g_m2")
    dual = result.get("dual_track") or {}
    print("\n--- 轨迹对比 ---")
    print(f"  baseline final biomass: {base.get('final_biomass_g_m2', '?')} g/m²")
    print(f"  scenario  final biomass: {cand.get('final_biomass_g_m2', '?')} g/m²")
    print(f"  delta:                  {delta.get('final_biomass_g_m2', '?')} g/m²")
    print(f"  theoretical cap:        {cap} g/m²")
    if dual:
        print(f"  双轨分歧:               {dual}")
    if result.get("verdict"):
        print(f"  verdict: {result.get('verdict')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
