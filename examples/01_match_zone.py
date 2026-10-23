#!/usr/bin/env python3
"""Example 01: 经纬度 → 气候分区匹配

用法:
    python examples/01_match_zone.py                       # 默认杭州
    python examples/01_match_zone.py --lat 39.90 --lon 116.40   # 北京

前置:
    在项目根目录运行；Python ≥ 3.10；零第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import _tool_match_zone  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="经纬度 → 气候分区")
    ap.add_argument("--lat", type=float, default=30.27, help="纬度（默认杭州 30.27）")
    ap.add_argument("--lon", type=float, default=120.15, help="经度（默认杭州 120.15）")
    ap.add_argument("--pretty", action="store_true", help="格式化输出")
    args = ap.parse_args()

    result = _tool_match_zone({"lat": args.lat, "lon": args.lon})

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))

    # 高亮关键字段（从 evidence 里取）
    ev = result.get("evidence") or {}
    conf = result.get("confidence") or {}
    print("\n--- 关键字段 ---")
    print(f"  zone_id:          {ev.get('zone_id')}")
    print(f"  zone_name:        {ev.get('zone_name')}")
    print(f"  climate_class:    {ev.get('climate_class')}")
    print(f"  backend:          {ev.get('classification_backend')}")
    print(f"  crop_count:       {ev.get('crop_count_in_db')}")
    print(f"  confidence:       rubric={conf.get('rubric_score')} coverage={conf.get('coverage_pct')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
