#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验 A2A Agent Card（.well-known/agent.json）合法性 + 与 MCP 工具集的一致性。

为什么要一致性校验：Agent Card 的 skills[] 是对外的能力声明。若它声明的
skill 在 MCP 层根本不存在，调用方按 A2A 发现后会调用失败——这属于「对外
文档说谎」，与本项目最核心的资产（可信度）直接冲突，必须由 CI 拦住。

用法：
    python scripts/check_agent_card.py

退出码：0 = 通过；1 = 不通过。
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD = os.path.join(ROOT, ".well-known", "agent.json")

REQUIRED_TOP = [
    "protocolVersion", "name", "description", "url", "version",
    "capabilities", "defaultInputModes", "defaultOutputModes", "skills",
]
REQUIRED_SKILL = ["id", "name", "description", "tags"]


def mcp_tool_names() -> set:
    """从 mcp/server.py 提取 TOOLS 声明里的 name 字段（不 import，避免副作用）。"""
    path = os.path.join(ROOT, "mcp", "server.py")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    # 只取 TOOLS = [ ... ] 区块
    m = re.search(r"^TOOLS\s*=\s*\[(.*?)^\]", src, re.S | re.M)
    if not m:
        raise SystemExit("无法在 mcp/server.py 中定位 TOOLS 声明块")
    return set(re.findall(r'"name"\s*:\s*"([a-z_]+)"', m.group(1)))


def main() -> int:
    errs = []
    if not os.path.exists(CARD):
        print("❌ 缺少 .well-known/agent.json")
        return 1
    with open(CARD, "r", encoding="utf-8") as f:
        try:
            card = json.load(f)
        except json.JSONDecodeError as e:
            print("❌ agent.json 不是合法 JSON: %s" % e)
            return 1

    for k in REQUIRED_TOP:
        if k not in card:
            errs.append("顶层缺必填字段: %s" % k)

    if not isinstance(card.get("skills"), list) or not card["skills"]:
        errs.append("skills 必须是非空数组")
        skills = []
    else:
        skills = card["skills"]

    ids = []
    for i, s in enumerate(skills):
        if not isinstance(s, dict):
            errs.append("skills[%d] 不是对象" % i)
            continue
        for k in REQUIRED_SKILL:
            if k not in s:
                errs.append("skills[%d] 缺字段 %s" % (i, k))
        if isinstance(s.get("tags"), list) and len(s["tags"]) == 0:
            errs.append("skills[%d].tags 不得为空数组" % i)
        if s.get("id"):
            ids.append(s["id"])
        if not s.get("description") or len(str(s.get("description", ""))) < 10:
            errs.append("skills[%d].description 过短" % i)

    dup = {x for x in ids if ids.count(x) > 1}
    if dup:
        errs.append("skill id 重复: %s" % sorted(dup))

    # 与 MCP 工具集一致性：Card 声明的 skill id 必须都有对应 MCP 工具
    try:
        tools = mcp_tool_names()
    except SystemExit as e:
        errs.append(str(e))
        tools = set()
    if tools:
        orphan = [i for i in ids if i not in tools]
        if orphan:
            errs.append(
                "Agent Card 声明了 MCP 层不存在的 skill（对外能力声明与实现不符）: %s"
                % orphan)
        declared = set(ids)
        missing = sorted(tools - declared)
        if missing:
            errs.append(
                "MCP 工具未在 Agent Card 中声明（调用方无法通过 A2A 发现）: %s" % missing)

    # 许可声明必须存在（法务红线：NC 来源不得用于付费转售）
    integ = card.get("x-agri-integrity") or {}
    if not integ.get("dataLicenseWarning"):
        errs.append("x-agri-integrity.dataLicenseWarning 缺失（NC 许可红线需对外声明）")

    if errs:
        print("❌ Agent Card 校验失败：")
        for e in errs:
            print("   - %s" % e)
        return 1

    print("✅ Agent Card 校验通过")
    print("   skills: %d 个" % len(ids))
    print("   MCP 工具: %d 个，与 skills 一一对应" % len(tools))
    print("   协议版本: %s" % card.get("protocolVersion"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
