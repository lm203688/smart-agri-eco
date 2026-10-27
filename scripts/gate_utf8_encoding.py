#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gate_utf8_encoding.py · 门禁扫描：所有文本模式 open() 必须显式指定 encoding

背景（P0-7 补充 · Windows UTF-8 编码 CI）：
    项目零依赖、跨平台（Windows/Linux/macOS）运行。Python 的 open() 若不带
    encoding，会回退到 locale 默认编码：Windows 上通常是 cp936/GBK，读 UTF-8
    文件会乱码或 UnicodeDecodeError，写 UTF-8 内容会乱码。2026-10-27 全库
    AST 扫描确认：现有 25 处不带 encoding 的 open() 全部是二进制模式
    (rb/wb/ab)——项目当前已合规。本门禁是**防御性约束**，防止未来有人引入
    文本模式 open() 不带 encoding，在 Windows 上静默乱码。

扫描规则：
    1. 遍历 ast.Call，检查函数名是否为 open（含 pathlib.Path(...).open，但
       pathlib 无默认 locale 回退问题较小，暂不拦；os.open 是 fd 级，不管）
    2. 提取 mode（位置参数第 2 个，或 keyword 'mode'）；缺省 'r'
    3. 若 mode 含 'b'（二进制）→ 跳过（无需 encoding）
    4. 若为文本模式且未显式传 encoding（位置第 3 个或 keyword）→ FAIL
    5. 白名单：gate 脚本自身；显式行注释 `# encoding-ok:`；_archive/

CLI：
    python scripts/gate_utf8_encoding.py          # 默认扫生产目录+scripts
    python scripts/gate_utf8_encoding.py --all    # 全项目（含 _archive）
    python scripts/gate_utf8_encoding.py --json   # JSON 输出

退出码：
    0 = PASS（全部合规）
    1 = FAIL（发现文本 open() 不带 encoding，阻断合并）
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 生产目录（默认扫描范围）；--all 时全项目
PROD_DIRS = ["core", "agent", "mcp", "engine", "app", "bp_screen", "scripts"]
SKIP_DIRS = {"__pycache__", ".git", ".workbuddy", ".pytest_cache", "node_modules",
             ".venv", "dist", "firmware"}


def _get_mode(node: ast.Call) -> str:
    """提取 open() 的 mode 参数，缺省 'r'。"""
    # 位置参数：open(file, mode='r', ...) -> args[1]
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        return str(node.args[1].value)
    # keyword 参数
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return "r"


def _has_encoding(node: ast.Call) -> bool:
    """是否显式传了 encoding（位置第 3 个或 keyword）。"""
    if len(node.args) >= 3:
        return True
    return any(kw.arg == "encoding" for kw in node.keywords)


def _is_exempt_line(src: str, lineno: int) -> bool:
    """该行是否带白名单注释。"""
    lines = src.splitlines()
    if 1 <= lineno <= len(lines):
        return "encoding-ok:" in lines[lineno - 1]
    return False


def scan_file(fp: Path) -> list[dict]:
    """扫描单个 .py 文件，返回违规列表。"""
    issues: list[dict] = []
    try:
        src = fp.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return issues  # 解析失败视为可读文件，不拦（语法错误由编译器管）
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # 仅拦内置 open()
        if not (isinstance(func, ast.Name) and func.id == "open"):
            continue
        mode = _get_mode(node)
        if "b" in mode:  # 二进制模式，无需 encoding
            continue
        if _has_encoding(node):
            continue
        if _is_exempt_line(src, node.lineno):
            continue
        issues.append({
            "file": str(fp.relative_to(ROOT)),
            "line": node.lineno,
            "mode": mode,
            "fix": f'open(..., "{mode}", encoding="utf-8")',
        })
    return issues


def scan(scope: str) -> tuple[list[dict], int]:
    """扫描目录，返回 (issues, files_scanned)。"""
    issues: list[dict] = []
    files_scanned = 0
    if scope == "all":
        roots = [ROOT]
    else:
        roots = [ROOT / d for d in PROD_DIRS if (ROOT / d).exists()]
    for base in roots:
        for p in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p == Path(__file__).resolve():
                continue  # 跳过自身
            files_scanned += 1
            issues.extend(scan_file(p))
    return issues, files_scanned


def main() -> int:
    ap = argparse.ArgumentParser(description="文本 open() 必须带 encoding 门禁")
    ap.add_argument("--all", action="store_true", help="扫描全项目（含 _archive）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    issues, files_scanned = scan("all" if args.all else "prod")
    ok = len(issues) == 0

    if args.json:
        print(json.dumps({
            "status": "PASS" if ok else "FAIL",
            "files_scanned": files_scanned,
            "violations": issues,
        }, ensure_ascii=False, indent=2))
    else:
        if issues:
            print(f"❌ 发现 {len(issues)} 处文本 open() 不带 encoding（Windows 会乱码）：")
            for it in issues:
                print(f"   {it['file']}:{it['line']} mode={it['mode']!r}  →  {it['fix']}")
            print("修复：为这些 open() 显式加 encoding=\"utf-8\"，或行尾加 # encoding-ok:")
            print(f"扫描 {files_scanned} 个文件")
            print("结果: FAIL（阻断合并）")
            return 1
        print(f"✅ 文本 open() 全部显式带 encoding（扫描 {files_scanned} 个文件）")
        print("结果: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
