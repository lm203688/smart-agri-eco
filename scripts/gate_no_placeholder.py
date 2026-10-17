#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gate_no_placeholder.py · 门禁扫描：AST 源码级检查占位/存根函数名

背景（FOUNDATION_AUDIT H4）：
    项目曾有 `agent/orchestrator.py` 门禁只扫输出字符串是否含 "placeholder"
    —— 只要源码里函数名含占位字样但不返回该字符串，就永远能过。本次改为
    AST 扫源码函数名。

扫描规则：
    1. 遍历 FunctionDef / AsyncFunctionDef 节点，若函数名（小写）含
       {placeholder, stub, todo, fixme, xxx, work_in_progress} 之一 → FAIL
    2. 字符串字面量中出现 "TODO:" 或 "FIXME:" → WARN（仅提示，不阻断）

白名单（不扫的目录/文件）：
    - tests/ · *_test.py · test_*.py（测试函数名可含 placeholder 字样）
    - scripts/test_*.py（同上）
    - _archive/（历史遗留）
    - docs/（非代码）

CLI：
    python scripts/gate_no_placeholder.py            # 默认扫 engine/ agent/ core/ mcp/ bp_screen/ benchmarks/
    python scripts/gate_no_placeholder.py --all      # 全项目（含 scripts/ 但白名单化 test_*）
    python scripts/gate_no_placeholder.py --json     # JSON 输出

退出码：
    0 = 无占位函数（PASS）
    1 = 发现占位函数（FAIL，阻断合并）
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# 触发 FAIL 的关键字（函数名子串）
BAD_NAMES = {"placeholder", "stub", "todo", "fixme", "xxx", "work_in_progress"}

# 触发 WARN 的字符串字面量模式
BAD_LITERALS = ("TODO:", "FIXME:", "HACK:", "XXX:")

# 生产扫描根目录（默认）
DEFAULT_ROOTS = ["engine", "agent", "core", "mcp", "bp_screen", "benchmarks"]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_test_file(path: Path) -> bool:
    name = path.name
    return name == "test_no_placeholder.py" or name.startswith("test_") or name.endswith("_test.py")


def _should_skip(path: Path) -> bool:
    parts = path.parts
    if "_archive" in parts or "docs" in parts or "__pycache__" in parts or "data" in parts:
        return True
    return _is_test_file(path)


def scan_file(path: Path) -> dict:
    """扫描单个 .py 文件，返回 {path, fails: [...], warns: [...]}。"""
    fails, warns = [], []
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError) as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "fails": [], "warns": [], "skip": str(e)}
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return {"path": str(path.relative_to(REPO_ROOT)), "fails": [f"SyntaxError: {e}"], "warns": []}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            low = node.name.lower()
            for kw in BAD_NAMES:
                if kw in low:
                    fails.append(f"def {node.name} (line {node.lineno})")
                    break
        # 字符串字面量检查（仅 WARN）
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for marker in BAD_LITERALS:
                if marker in node.value:
                    warns.append(f"literal at line {node.lineno}: {marker!r}")
                    break

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "fails": fails,
        "warns": warns,
    }


def iter_py_files(roots: list[str], include_scripts: bool = False):
    for r in roots:
        d = REPO_ROOT / r
        if d.is_dir():
            yield from d.rglob("*.py")
    if include_scripts:
        d = REPO_ROOT / "scripts"
        if d.is_dir():
            yield from d.rglob("*.py")


def main() -> int:
    ap = argparse.ArgumentParser(description="AST 门禁：禁止占位/存根函数名进入生产代码")
    ap.add_argument("--all", action="store_true", help="同时扫描 scripts/（白名单化 test_*）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS, help=f"扫描目录（默认 {DEFAULT_ROOTS}）")
    args = ap.parse_args()

    all_fails = 0
    total_files = 0
    results = []

    for py in iter_py_files(args.roots, include_scripts=args.all):
        if _should_skip(py):
            continue
        total_files += 1
        r = scan_file(py)
        if r["fails"] or r["warns"]:
            results.append(r)
        all_fails += len(r["fails"])

    if args.json:
        print(json.dumps({
            "files_scanned": total_files,
            "total_fails": all_fails,
            "results": results,
            "pass": all_fails == 0,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[gate_no_placeholder] 扫描 {total_files} 文件")
        if not results:
            print("✅ 无占位/存根函数（AST 门禁 PASS）")
            return 0
        for r in results:
            for f in r["fails"]:
                print(f"[FAIL] {r['path']}: {f}")
            for w in r["warns"][:3]:  # 最多显示 3 条 warn
                print(f"[WARN] {r['path']}: {w}")
        print(f"\n共 {all_fails} 处占位函数 → 阻断合并")
    return 1 if all_fails else 0


if __name__ == "__main__":
    sys.exit(main())
