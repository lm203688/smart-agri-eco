#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/check_mcp_namespace.py —— MCP 命名空间遮蔽守护（CI + 本机通用）

背景（2026-10-08 本机实测发现）：
    mcp/ 是本项目的一级目录（mcp/server.py、mcp/audit_analyzer.py），
    但 Python 的 site-packages 里可能装有官方 pip 版 `mcp` SDK 包。
    Python 解析 import 时 site-packages 优先级高于项目根目录，
    导致 `import mcp.server` 解析到第三方包而非本项目 mcp/server.py，
    使所有针对 mcp.server.TOOLS 的测试静默失败：
      - test_audit_analyzer                -> ModuleNotFoundError: No module named 'mcp.audit_analyzer'
      - test_mcp_tool_count_matches_docs   -> AttributeError: module 'mcp.server' has no attribute 'TOOLS'
      - test_no_third_party_imported_on_package_import -> 误报 {'httpx','uvicorn'}

    本项目运行时零第三方依赖（pyproject.toml dependencies=[]），
    因此 python -S 完全安全 —— 不会缺失任何必需包。

职责：
    1. 探测当前解释器下 `import mcp.server` 是否解析到本项目；
    2. 解析正确 -> 输出 OK 退出码 0；
    3. 被遮蔽  -> 输出具体根因与修复命令（-S -P），退出码 1，CI 红灯。

用法：
    python scripts/check_mcp_namespace.py
    python scripts/check_mcp_namespace.py --fix-hint   # 仅打印修复命令（不执行）

退出码：
    0 = 命名空间干净
    1 = 被第三方 mcp 包遮蔽（CI 应红灯）
"""
from __future__ import annotations

import importlib
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_TOOL_COUNT = 14  # 与 mcp/server.py::TOOLS 保持一致（由 manifest.json 声明）


def main() -> int:
    # 把项目根目录放到 sys.path 首位，模拟 `python mcp/server.py` 的解析路径。
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    # 先看解析结果
    mod = importlib.import_module("mcp.server")
    mod_path = getattr(mod, "__file__", "")
    resolved = os.path.normcase(os.path.abspath(mod_path)) if mod_path else ""
    local_path = os.path.normcase(os.path.abspath(os.path.join(PROJECT_ROOT, "mcp", "server.py")))

    if resolved == local_path:
        # 再核对工具数，防止「路径对了但 TOOLS 漂移」
        tools = getattr(mod, "TOOLS", None)
        n = len(tools) if isinstance(tools, (list, tuple)) else -1
        if n == EXPECTED_TOOL_COUNT:
            print(f"[OK] mcp.server 解析到本项目: {resolved}")
            print(f"[OK] TOOLS 数量 = {n}（符合预期 {EXPECTED_TOOL_COUNT}）")
            return 0
        print(f"[WARN] mcp.server 解析正确，但 TOOLS 数量 = {n}（预期 {EXPECTED_TOOL_COUNT}）")
        return 1

    # 被遮蔽：定位第三方包来源
    print(f"[FAIL] `import mcp.server` 未解析到本项目")
    print(f"       实际解析到: {mod_path}")
    print(f"       期望解析到: {local_path}")
    print()
    print("根因：site-packages 中存在官方 pip 版 `mcp` SDK 包，优先级高于项目根目录。")
    print("      Python 的 import 机制把 `mcp/` 一级目录与第三方 `mcp` 包重名遮蔽。")
    print()
    print("修复（本项目零依赖，-S 完全安全）：")
    print("    python -S -P -m unittest discover -s scripts -p \"test_*.py\"")
    print()
    print("或在本机临时屏蔽（不推荐长期使用）：")
    print("    python -S scripts/check_mcp_namespace.py && python -S -P -m unittest discover -s scripts")
    print()
    print("长期根治建议：在 CI 中把全量单测步骤改为 `python -S -P -m unittest discover scripts/`")
    return 1


if __name__ == "__main__":
    sys.exit(main())