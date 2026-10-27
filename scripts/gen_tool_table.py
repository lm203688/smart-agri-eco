#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_tool_table.py —— 程序化生成 MCP 工具表并插入 README.md

解决 GAP_AUDIT §D2：README 里 18 个 MCP 工具只有名字没有说明，导致外部
Agent 开发者第一次看 README 无法了解每个工具的参数、返回格式。

数据源：`mcp/server.py` 的 TOOLS 注册表（单一权威源），不手写。

用法：
    python scripts/gen_tool_table.py                # 写入 README.md
    python scripts/gen_tool_table.py --dry-run      # 打印到 stdout 不写文件
    python scripts/gen_tool_table.py --check        # 校验 README 是否与 TOOLS 一致（CI 用）

README 中的锚点（本脚本自动识别并替换）：
    <!-- GEN_TOOL_TABLE:BEGIN -->
    ...
    <!-- GEN_TOOL_TABLE:END -->
若无锚点则自动追加到 README 末尾（并在 CI 门禁脚本里提示需要手工加锚点）。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = ROOT / "mcp" / "server.py"
README = ROOT / "README.md"

BEGIN = "<!-- GEN_TOOL_TABLE:BEGIN -->"
END = "<!-- GEN_TOOL_TABLE:END -->"


def _load_tools() -> list[dict]:
    src = SERVER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "TOOLS":
                    out: list[dict] = []
                    for elt in node.value.elts:
                        d = {}
                        if isinstance(elt, ast.Dict):
                            for k, v in zip(elt.keys, elt.values):
                                if k is None:
                                    continue
                                try:
                                    key = ast.literal_eval(k)
                                    val = ast.literal_eval(v)
                                    if key in ("name", "description", "category"):
                                        d[key] = val
                                    elif key == "inputSchema":
                                        d["_schema"] = val
                                except Exception:
                                    pass
                        out.append(d)
                    return out
    raise SystemExit("❌ 无法在 mcp/server.py 中定位 TOOLS")


def _extract_required_params(tool: dict) -> str:
    schema = tool.get("_schema") or {}
    req = schema.get("required") or []
    props = schema.get("properties") or {}
    if not req:
        # 检查 properties 中是否有必填（无 required 时都算可选，除非只有一个）
        if len(props) == 0:
            return "无"
        return "见参数详情"
    # 用 props 的 description 补充
    parts: list[str] = []
    for r in req:
        desc = (props.get(r) or {}).get("description", "")
        p = f"`{r}`"
        if desc:
            p += f" — {desc[:24]}"
        parts.append(p)
    return "<br>".join(parts)


def _extract_return_shape(tool: dict) -> str:
    """根据工具名推断返回类型（简单启发式）。"""
    name = tool.get("name", "")
    if name.endswith("_recipe") or name == "agri_env_recipe":
        return "`Env Recipe v1` JSON"
    if name.endswith("_plan"):
        return "`Plan` JSON（阶段化）"
    if name == "agri_match_zone":
        return "`Zone Match` JSON"
    if name == "agri_reconcile_climate":
        return "`Climate Reconcile` JSON"
    if name == "agri_verify_recommendation":
        return "`Verdict` JSON（含 trust_mark）"
    if name == "agri_verify_trust":
        return "`Verification` JSON（含 signature 校验）"
    if name == "agri_forecast":
        return "`Forecast` JSON（含 P10/P50/P90）"
    if name == "agri_counterfactual_trajectory":
        return "`Trajectory` JSON（数组 + CI）"
    if name == "agri_search":
        return "`SearchResult` JSON"
    if name == "agri_knowledge_query":
        return "`KnowledgeGraph` JSON"
    if name == "agri_recipe_profile":
        return "`Profile` JSON（多 mode）"
    if name == "agri_bp_screen":
        return "`BPScreenReport` JSON"
    if name == "agri_decision_path_report":
        return "`DecisionPathReport` JSON"
    if name == "agri_query_lineage":
        return "`Lineage` JSON"
    if name == "agri_soil_profile":
        return "`SoilProfile` JSON"
    if name == "agri_server_card":
        return "`ServerCard` JSON（含 ETag）"
    if name == "agri_list_cities":
        return "`[City]` JSON"
    if name == "agri_list_ecosystem":
        return "`[Ecosystem]` JSON"
    return "`JSON`"


def _truncate(text: str, n: int = 60) -> str:
    text = text.replace("|", "\\|").replace("\n", " ")
    if len(text) > n:
        return text[:n] + "…"
    return text


def build_table() -> str:
    tools = _load_tools()
    lines: list[str] = []
    lines.append(BEGIN)
    lines.append("")
    lines.append(f"### MCP 工具全表（{len(tools)} 个）")
    lines.append("")
    lines.append(f"> 本表由 `scripts/gen_tool_table.py` 从 `mcp/server.py` 的 TOOLS 注册表**程序化生成**，禁止手写。工具总数 {len(tools)}。")
    lines.append("")
    lines.append("| # | 工具名 | 分类 | 一句话说明 | 必填参数 | 返回类型 |")
    lines.append("|---|---|---|---|---|---|")
    for i, t in enumerate(tools, 1):
        name = t.get("name", "")
        cat = t.get("category", "")
        desc = _truncate(t.get("description", ""), 90)
        req = _extract_required_params(t)
        ret = _extract_return_shape(t)
        lines.append(f"| {i} | `{name}` | {cat} | {desc} | {req} | {ret} |")
    lines.append("")
    lines.append(f"> 每个工具的详细参数说明见 `mcp/README.md` 对应章节。")
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()

    table = build_table()

    if args.check:
        text = README.read_text(encoding="utf-8")
        if BEGIN not in text or END not in text:
            print("❌ README.md 缺 GEN_TOOL_TABLE 锚点，请手工加入锚点块")
            return 1
        # 提取当前块
        i = text.index(BEGIN)
        j = text.index(END, i) + len(END)
        current = text[i:j]
        if current.strip() == table.strip():
            print("✅ README 工具表与 mcp/server.py TOOLS 一致")
            return 0
        print("❌ README 工具表与 TOOLS 不一致，请运行 `python scripts/gen_tool_table.py`")
        return 1

    text = README.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        i = text.index(BEGIN)
        j = text.index(END, i) + len(END)
        new_text = text[:i] + table + text[j:]
    else:
        new_text = text.rstrip() + "\n\n" + table + "\n"

    if args.dry_run:
        print(table)
        return 0

    README.write_text(new_text, encoding="utf-8")
    print(f"✅ 已更新 README.md 工具表（{len(_load_tools())} 个工具）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
