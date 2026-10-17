#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gate_tool_schema.py · 门禁：MCP 工具 schema 覆盖检查（FOUNDATION_AUDIT H5）

背景：
    23 个 _tool_* handler 中，10 个裸奔（43.5%）—— 用户传 -30°C / days=-5 /
    crop='quantum_plant' 会静默进机理层，产出看似合理但完全错误的种植计划。

扫描规则：
    1. AST 提取 mcp/server.py 中所有 `_tool_xxx` 函数名
    2. 检查每个函数前是否有对应的 `TOOL_SCHEMA_xxx = {...}` 定义
    3. 检查每个函数体内第一行是否调用了 `validate_tool_args(...)`
    4. 白名单：`_tool_server_card`（纯元数据查询，无用户参数）

CLI：
    python scripts/gate_tool_schema.py          # 默认扫 mcp/server.py
    python scripts/gate_tool_schema.py --json   # JSON 输出

退出码：
    0 = 全部工具都有 schema + 校验调用（PASS）
    1 = 发现缺失（FAIL，阻断合并）
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "mcp" / "server.py"

# 无用户参数的工具（纯元数据查询），白名单化
WHITELIST_TOOLS = {"_tool_server_card"}


def extract_tools(src: str) -> dict[str, dict]:
    """AST 提取所有 _tool_xxx 函数及其行号。"""
    tree = ast.parse(src, filename=str(SERVER_PATH))
    tools = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_tool_"):
            tools[node.name] = {
                "lineno": node.lineno,
                "body_first": node.body[0].lineno if node.body else node.lineno,
                "has_validate_call": False,
            }
            # 检查函数体内是否有 validate_tool_args 调用
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name) and func.id == "validate_tool_args":
                        tools[node.name]["has_validate_call"] = True
                        break
    return tools


def extract_schemas(src: str) -> set[str]:
    """提取所有 TOOL_SCHEMA_xxx 定义名。"""
    tree = ast.parse(src, filename=str(SERVER_PATH))
    schemas = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("TOOL_SCHEMA_"):
                    schemas.add(target.id)
    return schemas


def main() -> int:
    ap = argparse.ArgumentParser(description="门禁：MCP 工具 schema 覆盖检查")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    src = SERVER_PATH.read_text(encoding="utf-8")
    tools = extract_tools(src)
    schemas = extract_schemas(src)

    missing_schema = []
    missing_validate = []
    missing_tools = set()

    for tool_name, info in tools.items():
        # 白名单跳过
        if tool_name in WHITELIST_TOOLS:
            continue

        # 检查 schema 定义
        schema_name = "TOOL_SCHEMA_" + tool_name.replace("_tool_", "")
        if schema_name not in schemas:
            missing_schema.append(tool_name)
            missing_tools.add(tool_name)

        # 检查 validate 调用
        if not info["has_validate_call"]:
            missing_validate.append(tool_name)
            missing_tools.add(tool_name)

    total_tools = len(tools)
    covered = total_tools - len(missing_tools)
    pass_status = len(missing_tools) == 0

    result = {
        "total_tools": total_tools,
        "covered": covered,
        "missing": len(missing_tools),
        "coverage_pct": round(covered / total_tools * 100, 1) if total_tools else 0,
        "missing_schema": missing_schema,
        "missing_validate": missing_validate,
        "whitelist": sorted(WHITELIST_TOOLS),
        "pass": pass_status,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[gate_tool_schema] 扫描 mcp/server.py")
        print(f"  工具总数: {total_tools}")
        print(f"  有 schema + 校验: {covered}")
        print(f"  覆盖率: {result['coverage_pct']}%")
        if pass_status:
            print(f"✅ 全部工具都有 schema + 校验（白名单 {len(WHITELIST_TOOLS)} 个）")
        else:
            if missing_schema:
                print(f"❌ 缺 schema 定义: {missing_schema}")
            if missing_validate:
                print(f"❌ 缺 validate 调用: {missing_validate}")
            print(f"共 {len(missing_tools)} 个工具未覆盖 → 阻断合并")

    return 0 if pass_status else 1


if __name__ == "__main__":
    sys.exit(main())
