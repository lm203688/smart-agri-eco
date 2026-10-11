#!/usr/bin/env python3
"""
数据完整性门禁（防假数据冒充真实数据 + 防机读基线口径漂移）

用途：
    在 CI 与本地把守仓库内**四类**风险。之所以从 ci.yml 的内联 heredoc
    提成独立脚本，是因为原内联版有一个**真实且隐蔽的 bug**：

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
    4. harness/manifest.json —— 观测区数字必须与实际一致（口径漂移检测）
       * local_search.rows.recipes == len(data/env_recipes/*.json)
       * local_search.rows.crops   == crop_adapt_db.json 内作物条目总数
       * knowledge_graph.edges_by_rel.grows_in == 同上作物总数
         （KG 的 grows_in 边按"每 zone × crop"重复计，故与 crops 总数一致）

退出码：0 = 全部通过；1 = 命中污染、读文件失败或口径漂移。
"""

from __future__ import annotations

import glob
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


def check_manifest_drift() -> int:
    """检查 4：harness/manifest.json 观测区数字与实际一致（防口径漂移）。

    背景：harness/manifest.json 是「唯一机读基线」，被 CI、审计、外部工具
    读取引用。若观测区（knowledge_graph / local_search）的数字与真实
    env_recipes 数量不符，比 README 漂移更危险——因为它会被程序直接消费。
    2026-10-11 实测发现 manifest.local_search.rows.recipes = 116 而
    实际 env_recipes 已增长到 152 份，属此类真实漂移。

    检查三条硬约束：
        - local_search.rows.recipes == len(data/env_recipes/*.json)
        - local_search.rows.crops   == crop_adapt_db.json 内作物条目总数
        - knowledge_graph.edges_by_rel.grows_in == crop_adapt_db.json 内作物条目总数
          （KG 的 grows_in 按 zone×crop 展开，与 crops 总数一致）

    口径说明：grows_in 与 crops 相等是本项目的既定性质（每作物每分区一条
    grows_in 边）。若未来改成"每作物一条边"，此处需同步调整。
    """
    mpath = os.path.join(ROOT, "harness", "manifest.json")
    if not os.path.exists(mpath):
        print("  ⏭  harness/manifest.json 不存在，跳过")
        return 0
    try:
        m = json.load(open(mpath, encoding="utf-8"))
    except Exception as e:
        print(f"  ❌ manifest 读取失败: {e}")
        return 1

    # 实际值：env_recipes 目录文件数
    recipe_files = glob.glob(os.path.join(ROOT, "data", "env_recipes", "*.json"))
    actual_recipes = len(recipe_files)

    # 实际值：crop_adapt_db 内作物条目总数
    db_path = os.path.join(ROOT, "data", "crop_adapt_db.json")
    if not os.path.exists(db_path):
        print("  ⏭  crop_adapt_db.json 不存在，跳过 crops 比对")
        actual_crops = None
    else:
        db = json.load(open(db_path, encoding="utf-8"))
        actual_crops = sum(len(z.get("crops", [])) for z in db.get("zones", {}).values())

    bad = 0
    checks = []
    manifest_recipes = (m.get("local_search") or {}).get("rows", {}).get("recipes")
    manifest_crops = (m.get("local_search") or {}).get("rows", {}).get("crops")
    manifest_grows = ((m.get("knowledge_graph") or {}).get("edges_by_rel") or {}).get("grows_in")

    if actual_recipes is not None and manifest_recipes != actual_recipes:
        checks.append(
            f"manifest.local_search.rows.recipes={manifest_recipes} != 实际 {actual_recipes}")
        bad += 1
    if actual_crops is not None:
        if manifest_crops != actual_crops:
            checks.append(
                f"manifest.local_search.rows.crops={manifest_crops} != 实际 {actual_crops}")
            bad += 1
        if manifest_grows != actual_crops:
            checks.append(
                f"manifest.knowledge_graph.edges_by_rel.grows_in={manifest_grows} != 实际 {actual_crops}")
            bad += 1

    if bad:
        print(f"  ❌ manifest 口径漂移 {bad} 项：")
        for c in checks:
            print(f"       - {c}")
        return 1
    print(f"  ✅ manifest 数字对齐 (recipes={actual_recipes}, crops={actual_crops}, grows_in={manifest_grows})")
    return 0


def main() -> int:
    print("=== 数据完整性门禁 ===")
    rc = 0
    rc |= check_calibrated_evidence()
    rc |= check_feedback_log()
    rc |= check_long_term_memory()
    rc |= check_manifest_drift()
    if rc:
        print("\n❌ 数据完整性门禁未通过")
        return 1
    print("\n✅ 数据完整性门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
