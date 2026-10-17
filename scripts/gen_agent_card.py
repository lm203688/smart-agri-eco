#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_agent_card.py —— 程序化生成 A2A Agent Card（.well-known/agent.json）

解决 GAP_AUDIT §A1：Card 的 skills 数（23）与 skills/registry 的 skills 数（11）
存在概念混淆。本报告 §A1 明确指出"Card 把 MCP 工具直接映射成 skill"，导致
外部 Agent 按 Card 调用会 12 个找不到。

概念对齐（本脚本落地的最终定义）：
  - **Card.skills[]**（A2A v1.0 标准）：声明外部 Agent 通过本 Card 能"发现并调用"
    的能力。A2A 规范没有 tools[] 字段，本项目把 MCP tool 直接映射为 A2A skill，
    skill.id == mcp tool name（如 "agri_env_recipe"）。共 23 项。
  - **Card.x-agri-registry-skills[]**（扩展字段）：声明 skills/registry/ 下的
    AgriSkill 定义文件（"技能的定义与元数据"，用于人读的分工说明）。共 11 项。
  - 两者是**不同概念**，不互为别名；Card 中通过 `x-agri-concept-distinction`
    字段显式说明区别，避免外部调用方误解。

数据源（单一权威源，不手写）：
  - `mcp/server.py` 的 `TOOLS = [ ... ]` 列表 → Card.skills[]
  - `skills/registry/*.json`（排除 schema.json / CONTRIBUTING.md）→ Card.x-agri-registry-skills[]
  - `.well-known/agent.json` 中已有的人格描述字段（description / capabilities /
    provider / additionalInterfaces / securitySchemes / security 等）→ 原样保留

用法：
    python scripts/gen_agent_card.py                # 覆盖写回
    python scripts/gen_agent_card.py --check        # 只校验，不改文件（CI 用）
    python scripts/gen_agent_card.py --dry-run      # 打印 diff 到 stdout

CI 接入：scripts/check_agent_card.py 已改为同时校验 skills 与 registry-skills
两个数组，且 gen_agent_card.py --check 会失败如果 agent.json 与 TOOLS/registry
不一致（防漂移）。
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARD_PATH = ROOT / ".well-known" / "agent.json"
SERVER_PY = ROOT / "mcp" / "server.py"
REGISTRY_DIR = ROOT / "skills" / "registry"

# ---------------------------------------------------------------------------
# 抽取 MCP TOOLS 列表（AST 解析，避免手正则被字符串里的引号骗）
# ---------------------------------------------------------------------------

def extract_tools_from_server() -> list[dict]:
    """用 AST 解析 mcp/server.py，提取 TOOLS 全局列表。

    比正则更稳：字符串里的引号、注释里的字典都不会误伤；同时保留 name /
    description / category 三个字段供 Card 使用。
    """
    src = SERVER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TOOLS":
                    return _tools_to_dicts(node.value)
    raise SystemExit("❌ 无法在 mcp/server.py 中定位 TOOLS 列表")


def _tools_to_dicts(node: ast.AST) -> list[dict]:
    if not isinstance(node, ast.List):
        raise SystemExit("❌ TOOLS 不是列表字面量")
    out: list[dict] = []
    for elt in node.elts:
        try:
            d = ast.literal_eval(elt)
        except Exception:
            # inputSchema 里可能引用变量（如 _STAGES），literal_eval 会失败。
            # 退而求其次：只抽 name/description/category，保留顺序即可。
            d = _partial_dict(elt)
        if isinstance(d, dict):
            out.append(d)
    return out


def _partial_dict(dict_node: ast.Dict) -> dict:
    """只抽字符串字面量键，跳过含变量引用的值。"""
    out: dict = {}
    if not isinstance(dict_node, ast.Dict):
        return out
    for k, v in zip(dict_node.keys, dict_node.values):
        if k is None:
            continue
        try:
            key = ast.literal_eval(k)
            val = ast.literal_eval(v)
            if isinstance(key, str):
                out[key] = val
        except Exception:
            # 若值是引用（如 _STAGES）→ 跳过整个字段（Card 不用它）
            continue
    return out


# ---------------------------------------------------------------------------
# 抽取 registry skills
# ---------------------------------------------------------------------------

def load_registry_skills() -> list[dict]:
    """读 skills/registry/*.json（排除 schema.json 等非 skill 文件）。"""
    out: list[dict] = []
    for p in sorted(REGISTRY_DIR.glob("*.json")):
        if p.name == "schema.json":
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"⚠  跳过非法 JSON {p.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict) or "id" not in obj:
            continue
        obj["_file"] = p.name
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# 构建 Card
# ---------------------------------------------------------------------------

# 保留（不覆盖）的顶层字段——这些字段是"人格化描述"，不是自动生成内容
PRESERVE_KEYS = {
    "protocolVersion", "name", "description", "url", "preferredTransport",
    "additionalInterfaces", "provider", "version", "documentationUrl",
    "capabilities", "defaultInputModes", "defaultOutputModes",
    "securitySchemes", "security", "supportsAuthenticatedExtendedCard",
    "x-agri-integrity",
}

# 保留字段（会被覆盖）
GENERATED_KEYS = {
    "skills", "x-agri-registry-skills", "x-agri-concept-distinction",
    "generated_by",
}

# A2A 允许在 Card 中声明的扩展字段前缀
# （RFC 8259 允许任意 key；A2A 规范用 x- 前缀做非标准化扩展）
CONCEPT_DISTINCTION = {
    "skills_semantics": (
        "A2A v1.0 skill = 外部 Agent 可发现并调用的能力。"
        "本项目把每个 MCP 工具（mcp/server.py 的 TOOLS 注册表）映射为一个 skill，"
        "skill.id 与 MCP tool name 完全一致（如 'agri_env_recipe'）。"
        "外部 Agent 按此 skills[] 调 tools/call 会命中同名 MCP 工具。"
    ),
    "registry_skills_semantics": (
        "x-agri-registry-skills[] 是 skills/registry/ 目录下的 AgriSkill 定义"
        "（用于人读的分工说明：谁负责什么、输入输出是什么、数据来源、安全边界）。"
        "这些 id（如 'climate_match'）不是 MCP 工具名，不能被外部 Agent 直接调用；"
        "它们是内部技能目录，用于工程治理和审计。"
    ),
    "counts": {},  # 由 _build_card 填入
    "authority": "本 Card 由 scripts/gen_agent_card.py 程序化生成，禁止手改。"
}


def _build_skill_entry(tool: dict, mcp_tool_name: str) -> dict:
    """把 MCP tool 条目转成 A2A skill 条目。"""
    description = tool.get("description") or mcp_tool_name
    category = tool.get("category") or "general"
    tags = [category, "mcp-tool"]
    return {
        "id": mcp_tool_name,
        "name": _humanize(mcp_tool_name),
        "description": description,
        "tags": tags,
        "inputModes": ["application/json"],
        "outputModes": ["application/json"],
    }


def _humanize(tool_name: str) -> str:
    """agri_env_recipe → 环境配方生成（简单兜底，真实中文名在 mcp/README.md）。"""
    mapping = {
        "agri_list_cities": "预设城市列表",
        "agri_match_zone": "气候分区匹配",
        "agri_recommend_crops": "作物推荐",
        "agi_growth_plan": "生长计划",
        "agri_growth_plan": "生长计划",
        "agri_diagnose_pest": "病虫害诊断",
        "agri_nutrition_plan": "养分管理计划",
        "agri_env_recipe": "环境配方生成",
        "agri_season_advisory": "物候与播期建议",
        "agri_soil_profile": "土壤剖面分析",
        "agri_bp_screen": "农业投资初筛",
        "agri_reconcile_climate": "多源气候调和",
        "agri_resolve_recipe": "配方解析",
        "agri_query_lineage": "数据血缘查询",
        "agri_list_ecosystem": "生态对接清单",
        "agri_search": "知识检索",
        "agri_knowledge_query": "知识图谱查询",
        "agri_forecast": "预测（含保形区间）",
        "agri_recipe_profile": "配方 profile",
        "agri_verify_trust": "可信标记复算",
        "agri_server_card": "Server Card",
        "agri_decision_path_report": "决策路径报告",
        "agri_counterfactual_trajectory": "反事实轨迹",
        "agri_verify_recommendation": "主张验证服务",
    }
    return mapping.get(tool_name, tool_name)


def build_card() -> dict:
    """从 MCP TOOLS + registry 构建完整 Card。

    保留 agent.json 已有的人格化字段（capabilities / provider / x-agri-integrity
    等），只重写 skills[]、x-agri-registry-skills[]、x-agri-concept-distinction。
    """
    tools = extract_tools_from_server()
    registry = load_registry_skills()

    # 保留已有 Card 的字段
    base: dict = {}
    if CARD_PATH.exists():
        base = json.loads(CARD_PATH.read_text(encoding="utf-8"))

    skills: list[dict] = []
    for t in tools:
        name = t.get("name")
        if not name:
            continue
        skills.append(_build_skill_entry(t, name))

    registry_entries = [
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "domain": s.get("domain"),
            "agent": s.get("agent"),
            "description": s.get("description"),
            "file": s.get("_file"),
        }
        for s in registry
    ]

    card = dict(base)  # shallow copy 保留人格字段

    # 显式说明两个概念
    distinction = dict(CONCEPT_DISTINCTION)
    distinction["counts"] = {
        "skills": len(skills),
        "x-agri-registry-skills": len(registry_entries),
    }

    card["skills"] = skills
    card["x-agri-registry-skills"] = registry_entries
    card["x-agri-concept-distinction"] = distinction
    card["generated_by"] = "scripts/gen_agent_card.py"

    # 保留顺序：把 skills 放前面（A2A 主要字段），扩展字段放后面
    ordered: dict = {}
    for k in ("protocolVersion", "name", "description", "url", "preferredTransport",
              "additionalInterfaces", "provider", "version", "documentationUrl",
              "capabilities", "defaultInputModes", "defaultOutputModes",
              "skills", "x-agri-registry-skills", "x-agri-concept-distinction",
              "securitySchemes", "security", "supportsAuthenticatedExtendedCard",
              "x-agri-integrity", "generated_by"):
        if k in card:
            ordered[k] = card[k]
    for k in card:  # 兜底：其他 key 追加
        if k not in ordered:
            ordered[k] = card[k]
    return ordered


def diff_card(old: dict, new: dict) -> str:
    """打印两个 Card 的字段级 diff（简单版）。"""
    lines: list[str] = []
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            lines.append(f"  CHANGED: {k}")
    return "\n".join(lines) if lines else "  (no change)"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true",
                   help="只校验当前 agent.json 是否为最新生成版本（CI 用）")
    p.add_argument("--dry-run", action="store_true", help="打印 diff 到 stdout，不改文件")
    args = p.parse_args()

    new_card = build_card()

    if not CARD_PATH.exists():
        print("❌ 缺少 .well-known/agent.json，请先初始化")
        return 1

    old_card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    diff = diff_card(old_card, new_card)

    if args.check:
        # check 模式：忽略人格字段（capabilities / provider / x-agri-integrity 等），
        # 只比较我们生成的一部分
        gen_only_old = {k: old_card.get(k) for k in GENERATED_KEYS}
        gen_only_new = {k: new_card.get(k) for k in GENERATED_KEYS}
        if gen_only_old == gen_only_new:
            print("✅ agent.json 生成字段与 mcp/server.py TOOLS + skills/registry 一致")
            print(f"   skills: {len(new_card['skills'])} 个（MCP 工具）")
            print(f"   x-agri-registry-skills: {len(new_card['x-agri-registry-skills'])} 个（registry 定义）")
            return 0
        print("❌ agent.json 与源不同步，请运行 `python scripts/gen_agent_card.py` 重新生成")
        print("差异字段：")
        print(diff_card(gen_only_old, gen_only_new))
        return 1

    if args.dry_run:
        print(diff)
        return 0

    CARD_PATH.write_text(json.dumps(new_card, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print("✅ 已生成 .well-known/agent.json")
    print(f"   skills: {len(new_card['skills'])} 个（MCP 工具）")
    print(f"   x-agri-registry-skills: {len(new_card['x-agri-registry-skills'])} 个（registry 定义）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
