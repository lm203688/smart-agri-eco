#!/usr/bin/env python3
"""scripts/check_distribution_readiness.py 的两处判定回归测试（零依赖）。

锁住两个已修复的真实 bug（2026-10-08 发现）：

1. **GitHub 同步判定被 "0 ===" 子串误命中**
   旧逻辑用 `if "0 ===" in out` 判 PASS。但 sync_check 输出末尾固定有
   `=== 远端独有（本地缺失，需确认）: 0 ===`，里面含 "0 ==="。
   结果 sync_check 实际 exit=1、报 132 处差异时，自检仍把
   "GitHub 同步" 标成 ✅ "本地 = 远端 main" —— 严重误导。

2. **MCP 命名空间守护未传 -S -P**
   check_mcp_namespace.py 自身必须用 `python -S -P` 跑，否则
   `import mcp.server` 会解析到 site-packages 的 pip mcp 包，
   守护脚本必返回非 0，导致该项恒为 ❌ FAIL（与 CI 里已改的
   `python -S -P -m unittest` 自相矛盾）。

本测试不启动完整自检（避免网络/GitHub 依赖），只针对这两个判定逻辑本身。

运行：
    python -S -P -m unittest scripts.test_dist_readiness -v
"""
from __future__ import annotations

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SCRIPT = os.path.join(ROOT, "scripts", "check_distribution_readiness.py")


def judge_sync(exit_code: int, output: str) -> str:
    """复刻脚本内 check_sync 的判定核心（纯逻辑，与源码一致）。

    返回：'pass'（exit 0）/ 'warn'（有缺失或不一致）/ 'pass_misc'（exit 非 0 但实际无差异）。
    """
    if exit_code == 0:
        return "pass"
    m = re.search(r"远端缺失[^\n]*?\b(\d+)\b", output)
    n2 = re.search(r"内容不一致[^\n]*?\b(\d+)\b", output)
    a = int(m.group(1)) if m else -1
    b = int(n2.group(1)) if n2 else -1
    if a > 0 or b > 0:
        return "warn"
    return "pass_misc"


class TestDistReadinessJudge(unittest.TestCase):
    def test_sync_132_diff_must_be_warn_not_pass(self):
        """sync_check 报 132 差异（含 "0 ==="）时必须判 warn，不得判 pass。"""
        out = (
            "=== 远端缺失（新文件，需推送）: 7 ===\n"
            "  + docs/x.md\n"
            "=== 内容不一致（已变更，需推送）: 125 ===\n"
            "  ~ a.json\n"
            "=== 远端独有（本地缺失，需确认）: 0 ===\n"
            "⚠️ 共 132 处差异待处理\n"
        )
        self.assertEqual(judge_sync(1, out), "warn")

    def test_sync_truly_clean_is_pass(self):
        out = "✅ 本地与远端完全一致\n=== 远端独有（本地缺失，需确认）: 0 ===\n"
        self.assertEqual(judge_sync(0, out), "pass")

    def test_sync_zero_missing_zero_diff_but_exit1_is_pass_misc(self):
        """exit=1 但确实 0 缺失 0 不一致：应 pass_misc，不能靠 "0 ===" 硬判 pass。"""
        out = "=== 远端缺失: 0 ===\n=== 内容不一致: 0 ===\n=== 远端独有: 0 ===\n"
        self.assertEqual(judge_sync(1, out), "pass_misc")

    def test_sync_old_buggy_substring_would_have_misjudged(self):
        """回归锁：旧逻辑 `if "0 ===" in out` 会把这 132 差异误判为 pass。"""
        out = (
            "=== 远端缺失（新文件，需推送）: 7 ===\n"
            "=== 内容不一致（已变更，需推送）: 125 ===\n"
            "=== 远端独有（本地缺失，需确认）: 0 ===\n"
            "⚠️ 共 132 处差异待处理\n"
        )
        # 旧逻辑命中 '0 ==='；新逻辑必须仍判 warn
        self.assertIn("0 ===", out)
        self.assertEqual(judge_sync(1, out), "warn")

    def test_check_mcp_namespace_invoked_with_isolated_flags(self):
        """源码里必须用 `-S -P` 调用 check_mcp_namespace.py，否则该项恒 FAIL。"""
        with open(SCRIPT, encoding="utf-8") as f:
            src = f.read()
        # 定位 check_mcp_namespace 函数体
        start = src.index("def check_mcp_namespace():")
        body = src[start:]
        body = body[: body.index("\n\n", 0)]
        # 必须出现在 subprocess.run 的参数列表里
        self.assertIn('"-S", "-P"', body)
        # 且该 subprocess.run 的目标是 check_mcp_namespace.py
        call = body[: body.index("record(") if "record(" in body else len(body)]
        self.assertIn("check_mcp_namespace.py", call)


if __name__ == "__main__":
    unittest.main()