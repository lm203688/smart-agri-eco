#!/usr/bin/env python3
"""Example 02: 城市/坐标 → 作物推荐

用法:
    python examples/02_recommend.py                              # 默认杭州 · 食用
    python examples/02_recommend.py --lat 30.27 --lon 120.15 --purpose 观赏
    python examples/02_recommend.py --lat 39.90 --lon 116.40 --scene greenhouse

前置:
    在项目根目录运行；Python ≥ 3.10；零第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server import _tool_recommend_crops  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="坐标 + 偏好 → 作物推荐")
    ap.add_argument("--lat", type=float, default=30.27, help="纬度（默认杭州）")
    ap.add_argument("--lon", type=float, default=120.15, help="经度")
    ap.add_argument("--purpose", type=str, default="食用", help="食用 / 观赏 / 药用")
    ap.add_argument("--scene", type=str, default=None, help="balcony / greenhouse / field / container")
    ap.add_argument("--space-sqm", type=float, default=None)
    ap.add_argument("--difficulty", type=str, default=None, help="easy / medium / hard")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    payload = {"lat": args.lat, "lon": args.lon, "purpose": args.purpose}
    for k, v in [("scene", args.scene), ("difficulty", args.difficulty), ("space_sqm", args.space_sqm)]:
        if v is not None:
            payload[k] = v

    result = _tool_recommend_crops(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))

    recs = result.get("recommendation") or []
    conf = result.get("confidence") or {}
    if recs:
        print("\n--- Top 推荐（按 adapt_score）---")
        for r in recs[:5]:
            print(f"  {r.get('crop', '?'):<8s}  adapt={r.get('adapt_score', '?'):<5}"
                  f"  days={r.get('growth_days', '?'):<4}"
                  f"  water={r.get('water_ml_day', '?')} ml/d")
            print(f"       场景: {r.get('suitable_scenes', [])}")
            print(f"       理由: {r.get('reason', '')}")
    else:
        print(f"\n--- 无推荐（置信度：{conf.get('confidence_note', '?')}）---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
