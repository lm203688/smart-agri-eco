#!/usr/bin/env python3
"""
数据完整性门禁（防假数据冒充真实数据）

用途：
    在 CI 与本地把守仓库内三类"被合成样本污染"的风险。之所以从 ci.yml 的
    内联 heredoc 提成独立脚本，是因为原内联版有一个**真实且隐蔽的 bug**：

        内联写法把多个 ``any(... for k in synth)`` 用 ``or`` 串在多行里，
        而 Python 的推导式作用域规则会使其中一处 ``k`` 被解析为全局名，
        于是 ``NameError: name 'k' is not defined``。该分支此前因
        ``data/long_term_memory.json`` 为空而从未被执行，一直没暴露；
        2026-10-08 记忆库有了真实条目后，CI 在 3 个 Python 版本上
        整齐地全红——定位花了不少功夫。

    提成脚本 + 显式函数后，作用域不再有歧义，且可被单测覆盖。

检查项：
    1. crop_adapt_db.json —— 打了 ``calibrated`` 标记的作物必须有
       ``measured_calibration`` 可复算证据（不许"自称已校准"）
    2. feedback_log.json —— 不得含 demo / unittest / smoke 合成样本
    3. long_term_memory.json —— source_ref / skill / tags 不得带合成标记

退出码：0 = 全部通过；1 = 命中污染或读文件失败。
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 合成样本标记（子串匹配，转小写后比较）：命中任一即视为污染。
SYNTHETIC_MARKERS = ("unittest", "smoke", "[demo]")

# 需要按"整词"匹配的标记。
#
# 为什么不用简单的子串匹配 "demo"：那样 "demography"、"demolish" 之类
# 都会误报。但完全不管裸 demo 又会漏 —— 老内联版只查 "[demo]"（带方括号），
# 于是 tags 里裸写 "demo" 的记忆能溜过去。折中是按词边界匹配。
SYNTHETIC_WORDS = ("demo",)


def has_synthetic_marker(*values: object) -> bool:
    """判断给定字段里是否含合成样本标记。

    显式抽成函数，避免在推导式内联多个 ``any(... for k in ...)``——
    那正是原内联版踩的坑（作用域解析成全局名，NameError）。

    子串标记直接查；词标记按 ``\\b`` 词边界查，避免误伤
    "demography" 这类含 demo 前缀的正常词。
    """
    text = " ".join(str(v).lower() for v in values if v is not None)
    if any(marker in text for marker in SYNTHETIC_MARKERS):
        return True
    return any(re.search(r"\b%s\b" % re.escape(w), text) for w in SYNTHETIC_WORDS)


def check_calibrated_evidence() -> int:
    """检查 1：calibrated 标记必须有可复算证据。"""
    path = os.path.join(ROOT, "data", "crop_adapt_db.json")
    db = json.load(open(path, encoding="utf-8"))
    crops = [c for z in db["zones"].values() for c in z.get("crops", [])]
    bad = [c.get("crop") for c in crops
           if c.get("calibrated") and "measured_calibration" not in c]
    if bad:
        print(f"  ❌ {len(bad)} 个作物 calibrated 无证据: {bad[:5]}")
        return 1
    print(f"  ✅ crop_adapt_db OK ({len(crops)} crops)")
    return 0


def check_feedback_log() -> int:
    """检查 2：反馈日志不得含合成样本。"""
    path = os.path.join(ROOT, "data", "feedback_log.json")
    if not os.path.exists(path):
        print("  ⏭  feedback_log.json 不存在，跳过")
        return 0
    entries = json.load(open(path, encoding="utf-8"))
    bad = [e for e in entries
           if has_synthetic_marker(e.get("note"), e.get("issues"))]
    if bad:
        print(f"  ❌ 反馈日志含 {len(bad)} 条合成样本")
        return 1
    print(f"  ✅ feedback_log OK ({len(entries)} entries)")
    return 0


def check_long_term_memory() -> int:
    """检查 3：长期记忆库不得含合成样本。"""
    path = os.path.join(ROOT, "data", "long_term_memory.json")
    if not os.path.exists(path):
        print("  ⏭  long_term_memory.json 不存在，跳过")
        return 0
    doc = json.load(open(path, encoding="utf-8"))
    mems = doc.get("memories", [])
    bad = [m.get("id") for m in mems
           if has_synthetic_marker(m.get("source_ref"), m.get("skill"), m.get("tags"))]
    if bad:
        print(f"  ❌ 长期记忆库含 {len(bad)} 条合成样本: {bad[:5]}")
        return 1
    print(f"  ✅ long_term_memory OK ({len(mems)} memories)")
    return 0


def main() -> int:
    print("=== 数据完整性门禁 ===")
    rc = 0
    rc |= check_calibrated_evidence()
    rc |= check_feedback_log()
    rc |= check_long_term_memory()
    if rc:
        print("\n❌ 数据完整性门禁未通过")
        return 1
    print("\n✅ 数据完整性门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
