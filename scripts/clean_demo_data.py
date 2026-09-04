#!/usr/bin/env python3
"""
重置被 demo / 单测污染的演示数据。

为什么需要：
    - `python -m engine.flywheel` 每次运行都会向 data/feedback_log.json 追加 demo 样本，
      并向 data/crop_adapt_db.json 写入校准字段。
    - 这些数据**不是真实用户反馈**。若不重置，仓库里会出现「看起来像真实数据」的假记录，
      与项目「数据回流 = 0」的真实状态自相矛盾。

本脚本做的事：
    1. 把 data/feedback_log.json 重置为 []
    2. 从 data/crop_adapt_db.json 剥离 flywheel 写入的校准字段
       （measured_calibration / calibrated / seed_adapt_score），并把 adapt_score
        还原为 seed 值（仅当 seed_adapt_score 存在时才能安全还原）

用法：
    python scripts/clean_demo_data.py              # 直接重置
    python scripts/clean_demo_data.py --dry-run    # 只报告，不改文件
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
FEEDBACK_LOG = os.path.join(ROOT, "data", "feedback_log.json")

CALIB_FIELDS = ("measured_calibration", "calibrated", "seed_adapt_score")


def reset_feedback_log(dry_run: bool) -> int:
    if not os.path.exists(FEEDBACK_LOG):
        print(f"✅ feedback_log.json 不存在，无需重置")
        return 0
    with open(FEEDBACK_LOG, "r", encoding="utf-8") as f:
        data = json.load(f)
    n = len(data) if isinstance(data, list) else -1
    if n == 0:
        print("✅ feedback_log.json 已为空，无需重置")
        return 0
    if not dry_run:
        with open(FEEDBACK_LOG, "w", encoding="utf-8") as f:
            f.write("[]\n")
    print(f"🧹 feedback_log.json: 清空 {n} 条 demo/测试记录"
          + ("（dry-run）" if dry_run else ""))
    return n


def strip_calibration(dry_run: bool) -> dict:
    """剥离 demo / 单测写入的校准字段。

    按污染形态分三类处理（实测发现三种都存在）：
      A. 有 seed_adapt_score + measured_calibration → 可完整还原 adapt_score
      B. 只有孤立的 calibrated: true 标记（无任何证据字段）→ 仅删标记，
         adapt_score 未被 flywheel 写过，保持原样（安全）
      C. 有 measured_calibration 但缺 seed_adapt_score → 无法还原 adapt_score，
         删除标记并 loudly 告警（不可逆）
    """
    if not os.path.exists(CROP_DB):
        print("⚠️ crop_adapt_db.json 不存在")
        return {"A": 0, "B": 0, "C": 0}
    with open(CROP_DB, "r", encoding="utf-8") as f:
        db = json.load(f)

    counts = {"A": 0, "B": 0, "C": 0}
    for zone in db.get("zones", {}).values():
        for crop in zone.get("crops", []):
            has_calib = "measured_calibration" in crop
            has_seed = "seed_adapt_score" in crop
            has_flag = "calibrated" in crop
            if not (has_calib or has_seed or has_flag):
                continue
            if has_seed:
                crop["adapt_score"] = float(crop["seed_adapt_score"])
                counts["A"] += 1
            elif has_calib:
                counts["C"] += 1
            else:
                counts["B"] += 1
            for k in CALIB_FIELDS:
                crop.pop(k, None)

    if (counts["A"] + counts["B"] + counts["C"]) and not dry_run:
        with open(CROP_DB, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

    print(
        f"🧹 crop_adapt_db.json: 清洗 {sum(counts.values())} 个作物"
        f"（可还原 {counts['A']} / 仅删空标记 {counts['B']}"
        f" / ⚠️不可还原 {counts['C']}）"
        + ("（dry-run）" if dry_run else "")
    )
    if counts["C"]:
        print(f"   ⚠️ {counts['C']} 个作物缺 seed 值，adapt_score 无法还原，请人工核对")
    return counts


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    print("=" * 52)
    print("🌱 重置演示数据" + ("（dry-run 模式）" if dry_run else ""))
    print("=" * 52)
    reset_feedback_log(dry_run)
    strip_calibration(dry_run)
    print("=" * 52)
    return 0


if __name__ == "__main__":
    sys.exit(main())
