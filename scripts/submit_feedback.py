#!/usr/bin/env python3
"""
scripts/submit_feedback.py —— 内测反馈回流 CLI

用户 / 内测者提交种植结果 → engine.flywheel.record_feedback 校准 crop_adapt_db 的
adapt_score，使下次推荐自动采用实测校准分（数据飞轮闭环的「人工入口」）。

同时，本模块可被 Demo 站点的 /api/feedback 端点 import 复用（record_feedback）。

用法：
    python scripts/submit_feedback.py \
        --zone subtropical_wet --crop 生菜 \
        --survival 0.92 --yield 4.5 --rating 5.0 \
        --issues "梅雨季轻微霜霉病;已控湿" --note "杭州15楼南向阳台春播"

字段：
    --survival  成活率 0-1
    --yield     产量评分 0-5
    --rating    用户主观评分 0-5
    --issues    问题，用分号分隔（可选）
"""

import os
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.flywheel import record_feedback, generate_report  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="提交种植反馈，回流校准 adapt_score")
    p.add_argument("--zone", required=True, help="气候带 zone_id（如 subtropical_wet）")
    p.add_argument("--crop", required=True, help="作物名（如 生菜）")
    p.add_argument("--survival", type=float, default=1.0, help="成活率 0-1")
    p.add_argument("--yield", type=float, default=5.0, dest="yield_", help="产量评分 0-5")
    p.add_argument("--rating", type=float, default=5.0, help="用户主观评分 0-5")
    p.add_argument("--issues", default="", help="遇到的问题，分号分隔")
    p.add_argument("--note", default="", help="备注")
    args = p.parse_args()

    issues = [x.strip() for x in args.issues.split(";") if x.strip()] if args.issues else []

    res = record_feedback(
        zone_id=args.zone,
        crop=args.crop,
        survival_rate=args.survival,
        yield_rating=args.yield_,
        user_rating=args.rating,
        issues=issues,
        note=args.note,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n--- 累计反馈报告 ---")
    print(json.dumps(generate_report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
