#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 skills/registry/*.json 生成 Agent Plugins 1.0.0 交付物（零依赖）。

背景：
    skills/registry/*.json 是本项目自定义的 Skill 描述格式（11 个）。第三方
    Agent 客户端（Claude / Cursor / Copilot / VS Code 等）消费的是两种开放标准：
      1. Agent Plugins 1.0.0（Google 2026-08-06）：plugin.json + skills/*/SKILL.md + mcp.json
      2. Anthropic Agent Skills：SKILL.md + YAML frontmatter（name ≤64、description ≤1024）

    为避免「手抄 11 份 SKILL.md」造成注册表与插件包必然漂移，本脚本是
    唯一生成入口 —— registry JSON 是唯一数据源，SKILL.md 是派生产物。

产物：
    plugin.json                       插件清单（Agent Plugins 1.0.0）
    mcp.json                          MCP server 声明（stdio，指向 mcp/server.py）
    skills/<id>/SKILL.md              11 份，YAML frontmatter + 正文

用法：
    python scripts/build_agent_plugin.py            # 生成
    python scripts/build_agent_plugin.py --check    # 只校验是否与注册表一致（CI 用）

退出码：0 = 成功/一致；1 = 不一致或生成失败。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "skills", "registry")
OUT_DIR = os.path.join(ROOT, "plugin")
PLUGIN_NAME = "agri-eco"
PLUGIN_VERSION = "1.1.0"

# skill id → MCP 工具名。注册表用 domain 语义名，MCP 用 agri_ 前缀。
# 无同名 MCP 工具的 skill（如 supply_match / device_recommend）标为「规划中」，
# 不谎称已可由 MCP 调用 —— 与项目「不编造」原则一致。
SKILL_TO_MCP = {
    "climate_match": "agri_match_zone",
    "crop_adapt": "agri_recommend_crops",
    "growth_plan": "agri_growth_plan",
    "pest_diagnose": "agri_diagnose_pest",
    "nutrition_plan": "agri_nutrition_plan",
    "season_advisory": "agri_season_advisory",
    "harvest_forecast": None,
    "control_commands": None,
    "device_recommend": None,
    "iceplant_advisory": None,
    "supply_match": None,
}

# 注册表的 inputs 形如 "lat (float)"，SKILL.md 需要干净的参数名 + 类型。
def _split_param(spec: str) -> tuple:
    spec = spec.strip()
    if "(" in spec and spec.endswith(")"):
        name, ty = spec.rsplit("(", 1)
        return name.strip(), ty[:-1].strip()
    return spec, "any"


def _yaml_str(s: str, limit: int) -> str:
    """frontmatter 单行字符串：去掉换行、按标准截断。"""
    flat = " ".join(str(s).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def load_registry() -> list:
    out = []
    for fn in sorted(os.listdir(REGISTRY)):
        if not fn.endswith(".json") or fn in ("schema.json",):
            continue
        with open(os.path.join(REGISTRY, fn), "r", encoding="utf-8") as f:
            d = json.load(f)
        d["_file"] = fn
        out.append(d)
    return out


def render_skill_md(sk: dict) -> str:
    sid = sk["id"]
    tool = SKILL_TO_MCP.get(sid)
    name = _yaml_str(sk.get("name", sid), 64)
    desc = _yaml_str(sk.get("description", ""), 1024)
    version = sk.get("version", "1.0")
    domain = sk.get("domain", "")

    L = []
    # Anthropic Agent Skills 要求 name/description 位于 YAML frontmatter
    L.append("---")
    L.append("name: %s" % name)
    L.append("description: %s" % desc)
    L.append("version: \"%s\"" % version)
    L.append("---")
    L.append("")
    L.append("# %s" % sk.get("name", sid))
    L.append("")
    L.append("> Skill id: `%s` · 领域: `%s` · 实现 Agent: `%s`" % (sid, domain, sk.get("agent", "-")))
    L.append("")
    L.append("## 能力说明")
    L.append("")
    L.append(sk.get("description", "(无描述)"))
    L.append("")

    if tool:
        L.append("## 调用方式")
        L.append("")
        L.append("本 Skill 已由 MCP 工具 `%s` 承接。通过 MCP 调用即可，无需自行实现。" % tool)
        L.append("")
    else:
        L.append("## 调用方式")
        L.append("")
        L.append("**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。")
        L.append("本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；")
        L.append("若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。")
        L.append("")

    inputs = sk.get("inputs") or []
    if inputs:
        L.append("## 输入")
        L.append("")
        L.append("| 参数 | 类型 |")
        L.append("|---|---|")
        for p in inputs:
            pn, pt = _split_param(p)
            L.append("| `%s` | %s |" % (pn, pt))
        L.append("")

    outputs = sk.get("outputs") or []
    if outputs:
        L.append("## 输出")
        L.append("")
        L.append("| 字段 | 类型 |")
        L.append("|---|---|")
        for o in outputs:
            on, ot = _split_param(o)
            L.append("| `%s` | %s |" % (on, ot))
        L.append("")

    if sk.get("data_sources"):
        L.append("## 数据来源")
        L.append("")
        for s in sk["data_sources"]:
            L.append("- %s" % s)
        L.append("")

    if sk.get("confidence_method"):
        L.append("## 置信度计算")
        L.append("")
        L.append(sk["confidence_method"])
        L.append("")

    if sk.get("vision"):
        L.append("## 增强能力（可插拔）")
        L.append("")
        L.append(sk["vision"])
        L.append("")

    if sk.get("safety_boundary"):
        L.append("## 安全边界")
        L.append("")
        L.append("> %s" % sk["safety_boundary"])
        L.append("")

    if sk.get("reuse_value"):
        L.append("## 复用价值")
        L.append("")
        L.append(sk["reuse_value"])
        L.append("")

    deps = sk.get("dependencies") or []
    if deps:
        L.append("## 依赖")
        L.append("")
        for d in deps:
            L.append("- `%s`" % d)
        L.append("")

    if sk.get("implemented") is False:
        L.append("## 实现状态")
        L.append("")
        L.append("⚠️ 注册表标记为**未实现**（`implemented: false`）。")
        L.append("")

    L.append("---")
    L.append("")
    L.append("*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/%s` 生成，请勿手改。*"
             % sk["_file"])
    L.append("")
    return "\n".join(L)


def render_plugin_json(skills: list) -> str:
    doc = {
        "$schema": "https://agent-plugins.org/schema/1.0.0/plugin.json",
        "name": PLUGIN_NAME,
        "displayName": "智慧农业生态 Agri-Eco",
        "version": PLUGIN_VERSION,
        "description": (
            "面向分布式农业的 Agent-native 知识基座。提供可执行的 Env Recipe 环境配方、"
            "多源气候校准、物候与播期推演、土壤剖面、农业分区匹配、病虫害与养分诊断、"
            "数据血缘溯源与农业项目投资初筛。零第三方依赖、可离线运行、输出带来源与置信度标注。"
        ),
        "author": {
            "name": "smart-agri-eco",
            "url": "https://github.com/lm203688/smart-agri-eco",
        },
        "license": "见仓库 LICENSE（代码）；数据为混合许可，含 CC BY-NC-SA 来源，不得转售",
        "homepage": "https://github.com/lm203688/smart-agri-eco",
        "repository": "https://github.com/lm203688/smart-agri-eco",
        "keywords": [
            "agriculture", "agritech", "mcp", "a2a", "agent",
            "env-recipe", "phenology", "climate", "soil", "pest-diagnosis",
            "offline-first", "zero-dependency",
        ],
        "mcpServers": "./mcp.json",
        "skills": ["./skills/%s" % s["id"] for s in skills],
        "engines": {
            "python": ">=3.10",
        },
        "runtime": "local",
        "capabilities": {
            "network": "optional",
            "note": (
                "核心计算与数据路径零第三方依赖、可完全离线。"
                "联网仅在 agri_soil_profile（SoilGrids）与 agri_reconcile_climate"
                "（NASA POWER / Open-Meteo）两个工具上使用，不可达时优雅降级并明确标注，"
                "绝不返回编造值。"
            ),
        },
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def render_mcp_json() -> str:
    doc = {
        "$schema": "https://agent-plugins.org/schema/1.0.0/mcp.json",
        "mcpServers": {
            "agri-eco": {
                "command": "python",
                "args": ["mcp/server.py"],
                "transport": "stdio",
                "env": {
                    "AGRI_VISION_URL": "",
                    "AGRI_VISION_KEY": "",
                    "AGRI_VISION_MODEL": "",
                    "AGRI_MCP_AUDIT_LOG": "",
                },
                "description": (
                    "零依赖 MCP server（标准库 JSON-RPC 2.0 over stdio）。"
                    "协议版本 2026-07-28（无状态），向后兼容 2024-11-05 / 2025-06-18。"
                    "暴露 14 个农业工具。"
                ),
            }
        },
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def build() -> dict:
    """返回 {相对路径: 内容} 的完整产物映射。"""
    skills = load_registry()
    files = {
        "plugin/plugin.json": render_plugin_json(skills),
        "plugin/mcp.json": render_mcp_json(),
    }
    for sk in skills:
        files["plugin/skills/%s/SKILL.md" % sk["id"]] = render_skill_md(sk)
    return files


def main() -> int:
    check = "--check" in sys.argv
    files = build()

    if check:
        bad = []
        for rel, content in files.items():
            full = os.path.join(ROOT, rel)
            if not os.path.exists(full):
                bad.append("缺失: %s" % rel)
                continue
            with open(full, "r", encoding="utf-8") as f:
                if f.read() != content:
                    bad.append("不一致: %s" % rel)
        if bad:
            print("❌ Agent Plugin 与注册表不一致：")
            for b in bad:
                print("   " + b)
            print("\n修复：python scripts/build_agent_plugin.py")
            return 1
        print("✅ Agent Plugin 与 skills/registry 一致（%d 个文件）" % len(files))
        return 0

    for rel, content in files.items():
        full = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    print("已生成 %d 个文件：" % len(files))
    for rel in sorted(files):
        print("  + %s" % rel)

    # 自校验：SKILL.md frontmatter 长度合规
    problems = []
    for rel, content in files.items():
        if not rel.endswith("SKILL.md"):
            continue
        lines = content.split("\n")
        for ln in lines[1:5]:
            if ln.startswith("name:") and len(ln[5:].strip()) > 64:
                problems.append("%s name 超 64 字符" % rel)
            if ln.startswith("description:") and len(ln[12:].strip()) > 1024:
                problems.append("%s description 超 1024 字符" % rel)
        if not lines[0].strip() == "---":
            problems.append("%s 缺 frontmatter 起始" % rel)
    if problems:
        print("\n❌ 校验失败：")
        for p in problems:
            print("   " + p)
        return 1
    print("\n✅ frontmatter 长度校验通过（name ≤64 / description ≤1024）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
