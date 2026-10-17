#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gate_atomic_write.py · 门禁扫描：AST 扫 open(..., 'w') / open(..., 'a')

背景（FOUNDATION_AUDIT H1）：
    项目曾有 108 处 open('w') 直写 vs 4 处 os.replace，原子写占比 3.6%。
    生产点（engine/agent/mcp）一次崩溃即可能数据损坏。经 H1 迁移后，
    生产目录的写入必须走 core.atomic_io.atomic_write* —— 本门禁阻止回退。

扫描规则：
    1. 遍历 ast.Call 节点，检查函数名是否为 open
    2. 提取第二个参数（mode），若为 'w' / 'a' / 'w+' / 'a+' 且不在白名单 → FAIL
    3. 白名单：
       - core/atomic_io.py 自身
       - scripts/ 全目录（测试/构建脚本）
       - _archive/
       - *.tmp / *.log / *.pyc 目标
       - 显式带 `# atomic-ok:` 注释的行

CLI：
    python scripts/gate_atomic_write.py          # 默认扫生产目录
    python scripts/gate_atomic_write.py --all     # 全项目
    python scripts/gate_atomic_write.py --json    # JSON 输出

退出码：
    0 = 生产点无违规（PASS）
    1 = 发现违规（FAIL，阻断合并）
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

# 需要拦截的写模式
BAD_MODES = {"w", "a", "w+", "a+", "x"}

# 生产扫描根目录（默认）
DEFAULT_ROOTS = ["engine", "agent", "core", "mcp", "bp_screen"]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_whitelisted(path: Path) -> bool:
    """白名单：atomic_io 自身 / 测试脚本 / 归档目录。"""
    parts = path.parts
    if "_archive" in parts or "__pycache__" in parts:
        return True
    # atomic_io.py 自身必然 open('w') 写 tmp 文件
    if path.name == "atomic_io.py":
        return True
    return False


def _is_test_script(path: Path) -> bool:
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py")


def _has_atomic_ok_comment(lines: list[str], lineno: int) -> bool:
    """检查该 Call 节点对应行的上方 3 行是否有 # atomic-ok: 注释。"""
    for i in range(max(0, lineno - 4), lineno):
        if i < len(lines) and "atomic-ok" in lines[i]:
            return True
    return False


def _resolve_str_literal(node: ast.AST) -> str | None:
    """尝试从 AST 节点解析出字符串字面量值。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan_file(path: Path) -> dict:
    """扫描单个 .py 文件，返回 {path, fails: [...]}。"""
    fails = []
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        return {"path": str(path.relative_to(REPO_ROOT)), "fails": []}
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return {"path": str(path.relative_to(REPO_ROOT)),
                "fails": [f"SyntaxError: {e}"]}
    lines = src.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # 提取被调函数名（open(...)）
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            # 提取 mode 参数
            mode = None
            for arg in node.args:
                if len(node.args) >= 2 and isinstance(arg, ast.Constant):
                    pass
            # mode 通常是第二个位置参数
            if len(node.args) >= 2:
                mode = _resolve_str_literal(node.args[1])
            else:
                # 关键字参数 mode=
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode = _resolve_str_literal(kw.value)

            if mode in BAD_MODES:
                # 排除白名单
                if _has_atomic_ok_comment(lines, node.lineno):
                    continue
                fails.append(f"open(..., {mode!r}) at line {node.lineno}")

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "fails": fails,
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
    ap = argparse.ArgumentParser(description="AST 门禁：生产代码禁止 open(..., 'w')/open(..., 'a')")
    ap.add_argument("--all", action="store_true", help="同时扫描 scripts/（白名单化 test_*）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--roots", nargs="*", default=DEFAULT_ROOTS, help=f"扫描目录（默认 {DEFAULT_ROOTS}）")
    args = ap.parse_args()

    all_fails = 0
    total_files = 0
    results = []

    for py in iter_py_files(args.roots, include_scripts=args.all):
        if _is_whitelisted(py):
            continue
        if args.all and _is_test_script(py):
            continue
        total_files += 1
        r = scan_file(py)
        if r["fails"]:
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
        print(f"[gate_atomic_write] 扫描 {total_files} 文件")
        if not results:
            print("✅ 生产代码无 open('w')/open('a') 直写（原子写门禁 PASS）")
            return 0
        for r in results:
            for f in r["fails"]:
                print(f"[FAIL] {r['path']}: {f}")
        print(f"\n共 {all_fails} 处违规直写 → 阻断合并")
    return 1 if all_fails else 0


if __name__ == "__main__":
    sys.exit(main())
