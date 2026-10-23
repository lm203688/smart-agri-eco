#!/usr/bin/env python3
"""Example 04: 配方统计 / 检索 / 加载

用法:
    python examples/04_recipe.py                              # 资产统计
    python examples/04_recipe.py --search --crop 番茄           # 检索番茄配方
    python examples/04_recipe.py --list --mode full            # 列出全部（完整 JSON）
    python examples/04_recipe.py --lookup tomato_fruiting_greenhouse.json   # 加载完整配方

前置:
    在项目根目录运行；Python ≥ 3.10；零第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import _tool_recipe_profile  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="152 份 Env Recipe 的浏览器 / 检索器")
    ap.add_argument("--stats", action="store_true", help="资产统计")
    ap.add_argument("--list", action="store_true", help="列出所有配方元信息")
    ap.add_argument("--search", action="store_true", help="按作物/阶段/设备搜索")
    ap.add_argument("--lookup", type=str, default=None, help="按文件名加载完整配方")
    ap.add_argument("--crop", type=str, default=None)
    ap.add_argument("--stage", type=str, default=None)
    ap.add_argument("--device-class", type=str, default=None)
    ap.add_argument("--mode", type=str, default="brief", choices=["brief", "full"])
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    if args.stats:
        kind = "stats"
    elif args.lookup:
        kind = "lookup"
    elif args.search:
        kind = "search"
    else:
        kind = "list"

    payload = {"kind": kind, "mode": args.mode}
    if args.lookup:
        payload["filename"] = args.lookup
    if args.crop:
        payload["crop"] = args.crop
    if args.stage:
        payload["stage"] = args.stage
    if args.device_class:
        payload["device_class"] = args.device_class

    result = _tool_recipe_profile(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))

    if kind == "stats":
        print("\n--- 资产概览 ---")
        print(f"  total_recipes: {result.get('total_recipes')}")
        print(f"  total_bytes:   {result.get('total_bytes')}")
        print(f"  profile_v:     {result.get('profile_version')}")
        print(f"  by_stage:      {result.get('by_stage')}")
        print(f"  by_device:     {result.get('by_device_class')}")
    elif kind == "search":
        matches = result.get("matches") or result.get("results") or []
        print(f"\n--- 命中 {len(matches)} 份配方 ---")
        for m in matches[:5]:
            if isinstance(m, dict):
                print(f"  {m.get('filename', '?'):<55s} {m.get('crop', '')}/{m.get('stage', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
