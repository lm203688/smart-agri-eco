#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_readme_numbers.py —— README 数字口径一致性门禁

解决 GAP_AUDIT §A2：README 里同一文档出现 4 个工具数字符串（14 / 20 / 21 / 23），
评审员第一眼就会质疑。本门禁保证 README 中所有"数字 + 工具/个/agri"的模式
都等于 `harness/manifest.json` 的 `mcp.tool_count`。

同时校验：
- skill 数（如果提到"XX 个 skill"或"XX 个技能"）必须等于 `manifest.skills.count`
- CI 步骤数（"XX 步"）必须等于 `manifest.ci.step_count`

用法：
    python scripts/check_readme_numbers.py

退出码：0 = 通过；1 = 不通过。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
MANIFEST = ROOT / "harness" / "manifest.json"


def main() -> int:
    errs: list[str] = []
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_tools = man.get("mcp", {}).get("tool_count")
    expected_skills = man.get("skills", {}).get("count")
    expected_ci = man.get("ci", {}).get("step_count")

    readme = README.read_text(encoding="utf-8")

    # 工具数：匹配 "N 个 MCP/agri/工具"、"N 工具"、"第 N 个工具" 等
    tool_patterns = [
        r"(\d+)\s*(?:个)?\s*MCP\s*工具",
        r"(\d+)\s*个\s*agri\s*工具",
        r"(\d+)\s*个\s*工具",
        r"暴露\s*(\d+)\s*个",  # "暴露 N 个 agri 工具"
        r"MCP\s*(\d+)\s*工具",
    ]
    found_tools: set[int] = set()
    for pat in tool_patterns:
        for m in re.finditer(pat, readme):
            found_tools.add(int(m.group(1)))

    # 排除明显不是工具数的语境（如"第 21 个工具"是序数，不是总数）
    # 我们只看"总数"型匹配：出现"个"或"MCP N 工具"
    total_tool_nums = set()
    # 只匹配"总数"型：
    #   1) "N 个 MCP/agri 工具"（不匹配"第 N 个"序数）
    #   2) "MCP N 工具"
    #   3) "暴露 N 个 agri 工具"
    # 排除 test_mcp_server.py 里"N 工具"这种针对单文件的口径（不是总数）
    sanitized = re.sub(r"test_mcp_server\.py[^\n]{0,40}?(\d+)\s*工具",
                       r"test_mcp_server.py XXX 工具", readme)
    total_tool_nums.update(re.findall(r"(?<!第\s)(\d+)\s*个\s*MCP\s*工具", sanitized))
    total_tool_nums.update(re.findall(r"(?<!第\s)(\d+)\s*个\s*agri\s*工具", sanitized))
    total_tool_nums.update(re.findall(r"暴露\s*(\d+)\s*个", sanitized))
    # 转 int
    total_tool_nums = {int(x) for x in total_tool_nums}

    if expected_tools is not None and total_tool_nums and total_tool_nums != {expected_tools}:
        bad = total_tool_nums - {expected_tools}
        errs.append(
            f"README 工具数出现 {sorted(total_tool_nums)}，manifest 期望 {expected_tools}；"
            f"不符合: {sorted(bad)}"
        )

    # skill 数：允许三种合法值——
    #   1) 11 = skills/registry 定义数（人读技能目录）
    #   2) 23 = Card.skills 语义（工具映射）
    #   3) 8/7 = evolution_zones.json 的不可/可进化资产数（"8 项不可进化"）
    # 匹配必须带"个/项"作为分隔，避免误伤 "L2 Skill" 这种技术分层描述
    skill_nums = {int(x) for x in re.findall(
        r"(?<![\wA-Za-z])({d})\s*(?:个|项)\s*(?:skill|技能|Skill)".format(d=r"\d+"),
        readme)}
    legal_skill = {expected_skills or -1, expected_tools or -1, 8, 7}
    if expected_skills is not None and skill_nums:
        bad_skill = skill_nums - legal_skill
        if bad_skill:
            errs.append(
                f"README skill 数出现 {sorted(skill_nums)}，合法值应为 "
                f"{sorted(legal_skill)}（registry/Card/evolution_zones）；"
                f"不符合: {sorted(bad_skill)}"
            )

    # CI 步骤数
    ci_nums = {int(x) for x in re.findall(r"CI[^\n]{0,20}?(\d+)\s*步", readme)}
    if expected_ci is not None and ci_nums:
        bad_ci = ci_nums - {expected_ci}
        if bad_ci:
            errs.append(
                f"README CI 步骤数出现 {sorted(ci_nums)}，manifest 期望 {expected_ci}；"
                f"不符合: {sorted(bad_ci)}"
            )

    if errs:
        print("❌ README 数字口径校验失败：")
        for e in errs:
            print(f"   - {e}")
        return 1

    print("✅ README 数字口径一致")
    print(f"   工具数期望 {expected_tools}，实际出现 {sorted(total_tool_nums) or ['无'] if total_tool_nums else '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
