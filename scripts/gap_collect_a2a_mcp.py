#!/usr/bin/env python3
"""查漏补缺扫描 · A：A2A Card skills vs MCP tools 真实对应"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A2A card skills
card_path = ROOT / ".well-known" / "agent.json"
skills = []
if card_path.exists():
    try:
        card = json.loads(card_path.read_text(encoding="utf-8", errors="ignore"))
        skills = card.get("skills") or []
    except Exception as e:
        print("A2A card 读取失败:", e)
print(f"A2A Agent Card 声明 skills 数: {len(skills)}")
for s in skills:
    print(f"  - {s.get('id') or s.get('name')}")

# MCP tools
m = (ROOT / "mcp" / "server.py").read_text(encoding="utf-8", errors="ignore")
tools = re.findall(r'^(?:async\s+)?def\s+_tool_(\w+)\s*\(', m, re.M)
print(f"\nMCP server _tool_ 数: {len(tools)}")
mm = re.search(r'TOOLS\s*=\s*(\d+)', m)
print(f"MCP TOOLS 常量声明: {mm.group(1) if mm else '未找到'}")
for t in tools:
    print(f"  - agri_{t}")

# 对应性分析
print("\n=== 对应关系 ===")
print(f"README/CORE 声称: A2A 14 skill ↔ MCP 14 tool (CORE_OBJECTIVE P0-2)")
print(f"README 声称: MCP 暴露 30 个 agri 工具")
print(f"实际: A2A {len(skills)} skill vs MCP {len(tools)} tool")
print(f"差异: {len(tools) - len(skills)} 个 MCP 工具无对应 A2A skill 声明")
print(f"  若 A2A 必须 1:1 对应 MCP（README 第243行要求），则 A2A 缺 {len(tools)-len(skills)} 个 skill")
print(f"  若以 A2A 为准（CORE P0-2 已完成），则 MCP 多暴露 {len(tools)-len(skills)} 个工具无 A2A 入口")
