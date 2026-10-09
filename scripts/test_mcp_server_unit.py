#!/usr/bin/env python3
"""scripts/test_mcp_server_unit.py —— 把 scripts/test_mcp_server.py 纳入 unittest 收集。

背景（full_liftup_assessment §5.2 TD-3 后半 + P1-9）：
    scripts/test_mcp_server.py 是**脚本式自测**：用 `check(cond, label)` 收集失败项，
    `def test_` 计数为 0，因此 `python -m unittest discover` 完全不会收集它。
    结果 547 项 unittest 统计里不含 MCP 工具级断言（14 工具 / SEP-2567 / 审计日志）。

    但它的 41 项断言要起子进程 + 依赖 `mcp/server.py` 完整环境，直接重写成 41 个
    `def test_*` 会大幅改变原文件结构、破坏 scripts/test_mcp_server.py 独立可跑性。

    本模块采用**薄适配器**：直接调用原脚本的 `main()`，把它的 returncode
    转成一条 unittest 断言。这样：
      - 原脚本保持独立可跑（`python scripts/test_mcp_server.py` 语义不变）；
      - 原 41 项断言全部进入 unittest 统计（作为 1 个 test method，失败会展开失败项）；
      - 零依赖、零重复实现。

    代价：失败时不区分是哪一项断言失败（原脚本会 print 失败项到 stdout，本测试
    把 stdout 带进断言消息）。这是可接受的——它仍是**真实运行**了 MCP server。

运行：
    python -S -P -m unittest discover -s scripts -p "test_mcp_server_unit.py" -v
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 用 importlib 加载原脚本（文件名带下划线，无法正常 import）
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "test_mcp_server_impl", os.path.join(ROOT, "scripts", "test_mcp_server.py"))
impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(impl)


class TestMcpServerSmoke(unittest.TestCase):
    """把 test_mcp_server.py 的 41 项断言作为一条 unittest 用例纳入统计。"""

    def test_mcp_server_full_smoke(self):
        """真实启动 mcp/server.py 跑完整冒烟（initialize/tools/list/tools/call/审计）。

        原脚本退出码 0 = 全部 41 项通过；非 0 = 有失败项，把 stdout 带进断言消息。
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = impl.main()
        out = buf.getvalue()
        self.assertEqual(
            rc, 0,
            "MCP server 自测失败（rc=%d），输出:\n%s" % (rc, out))


if __name__ == "__main__":
    unittest.main()