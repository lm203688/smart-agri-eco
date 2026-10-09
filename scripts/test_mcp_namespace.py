#!/usr/bin/env python3
"""scripts/check_mcp_namespace.py 的离线回归测试（零依赖）。

背景（2026-10-08 本机实测）：
    box-agent runtime 预装 pip `mcp` SDK 包，与项目 `mcp/` 一级目录重名，
    导致 `import mcp.server` 解析到第三方包，测试假失败 3 项。

本测试锁住两个性质：

1. **`import mcp.server` 必须解析到本项目 mcp/server.py** —— 一旦
   site-packages 里的 pip `mcp` 包把路径遮蔽，这里立即红灯。

   注意：这里刻意使用 `importlib.import_module` 而不是 `PathFinder.find_spec`。
   `mcp/` 是 PEP 420 隐式命名空间包（无 `__init__.py`），
   `PathFinder.find_spec` 单独调用不会走完整的 namespace 查找链，
   会恒返回 None，测不到遮蔽。而 `import_module` 走完整 import 机制，
   与守卫脚本 `check_mcp_namespace.py` 的行为完全一致。

2. **`scripts/check_mcp_namespace.py` 的常量 `EXPECTED_TOOL_COUNT` 必须与
   `harness/manifest.json` 声明的 `mcp.tool_count` 一致** ——防止守卫脚本
   因常量漂移而给出「假 OK」。

运行：python -S -P -m unittest discover -s scripts -p "test_mcp_namespace.py"
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.check_mcp_namespace as G  # noqa: E402


def _expected_local_path() -> str:
    return os.path.normcase(os.path.abspath(os.path.join(ROOT, "mcp", "server.py")))


def _resolve(module: str):
    """与守卫脚本一致：用 import_module 触发完整 import 机制。"""
    return importlib.import_module(module)


class TestMcpNamespaceNotShadowed(unittest.TestCase):
    def test_project_mcp_server_resolves_to_local(self):
        """`import mcp.server` 必须解析到本项目 mcp/server.py，而非 pip mcp 包。"""
        mod = _resolve("mcp.server")
        resolved = os.path.normcase(os.path.abspath(getattr(mod, "__file__", "") or ""))
        self.assertEqual(
            resolved,
            _expected_local_path(),
            f"mcp.server 被遮蔽：解析到 {resolved}\n"
            f"期望解析到 {_expected_local_path()}\n"
            f"根因：site-packages 里有 pip 版 mcp 包（含 mcp.audit_analyzer 不存在、"
            f"mcp.server.TOOLS 不存在）。\n"
            f"修复：python -S -P -m unittest discover -s scripts",
        )

    def test_project_mcp_audit_analyzer_resolves_to_local(self):
        """`import mcp.audit_analyzer` 必须解析到本项目文件。"""
        mod = _resolve("mcp.audit_analyzer")
        resolved = os.path.normcase(os.path.abspath(getattr(mod, "__file__", "") or ""))
        expected = os.path.normcase(
            os.path.abspath(os.path.join(ROOT, "mcp", "audit_analyzer.py"))
        )
        self.assertEqual(
            resolved,
            expected,
            f"mcp.audit_analyzer 被遮蔽：解析到 {resolved}",
        )

    def test_guard_script_reports_ok_in_clean_env(self):
        """守卫脚本在主流程里必须给出 exit 0（此处复现其判定逻辑）。"""
        mod = _resolve("mcp.server")
        tools = getattr(mod, "TOOLS", None)
        n = len(tools) if isinstance(tools, (list, tuple)) else -1
        self.assertEqual(
            n,
            G.EXPECTED_TOOL_COUNT,
            f"mcp.server.TOOLS 数量 = {n}，守卫脚本常量 EXPECTED_TOOL_COUNT = "
            f"{G.EXPECTED_TOOL_COUNT}，不一致",
        )

    def test_guard_script_expected_tool_count_matches_manifest(self):
        """守卫脚本常量必须与 manifest 声明值一致。"""
        with open(os.path.join(ROOT, "harness", "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        declared = manifest.get("mcp", {}).get("tool_count")
        self.assertEqual(
            G.EXPECTED_TOOL_COUNT,
            declared,
            "守卫脚本常量与 manifest 声明值不一致：%s vs %s"
            % (G.EXPECTED_TOOL_COUNT, declared),
        )


if __name__ == "__main__":
    unittest.main()