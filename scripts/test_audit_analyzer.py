#!/usr/bin/env python3
"""
智慧农业生态 · audit_analyzer 单元测试

覆盖：analyze / load_events / THRESH 常量
对齐 GOAI CyberGuard 提升点3 行为监控机制
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from mcp.audit_analyzer import (  # noqa: E402
    THRESH,
    analyze,
    load_events,
)


def _make_entry(event, **kwargs):
    """构造事件 dict（不是 JSON 字符串，analyze 需要 dict 列表）"""
    return {"ts": "2026-09-25T12:00:00", "server": "agri-eco", "event": event, **kwargs}


def _make_json_line(event, **kwargs):
    """构造 JSON 字符串行（用于 load_events 测试）"""
    return json.dumps({"ts": "2026-09-25T12:00:00", "server": "agri-eco", "event": event, **kwargs}, ensure_ascii=False)


class TestLoadEvents(unittest.TestCase):
    """日志加载（load_events 读取审计日志文件路径）"""

    @classmethod
    def setUpClass(cls):
        cls._tmpd = tempfile.mkdtemp(prefix="agri_audit_test_")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls._tmpd, ignore_errors=True)

    def _write_log(self, content, name="log.txt"):
        p = os.path.join(self._tmpd, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p

    def test_missing_file_returns_empty(self):
        """空内容日志文件返回 []"""
        p = self._write_log("")
        self.assertEqual(load_events(p), [])

    def test_single_valid_line(self):
        p = self._write_log(_make_json_line("tools_call_request", tool="x"))
        evs = load_events(p)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "tools_call_request")

    def test_multiple_lines(self):
        lines = [_make_json_line("a"), _make_json_line("b"), _make_json_line("c")]
        p = self._write_log("\n".join(lines), "multi.txt")
        evs = load_events(p)
        self.assertEqual(len(evs), 3)

    def test_invalid_line_skipped(self):
        """非法 JSON 行应被静默跳过"""
        p = self._write_log("not json\n" + _make_json_line("tools_call_request"),
                            "mixed.txt")
        evs = load_events(p)
        self.assertEqual(len(evs), 1)

    def test_prefixed_line_supported(self):
        """[mcp_audit] 前缀行应被兼容解析（stderr 混排场景）"""
        prefix_line = '[mcp_audit] ' + _make_json_line("tools_call_done", tool="y")
        p = self._write_log(prefix_line, "prefixed.txt")
        evs = load_events(p)
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "tools_call_done")


class TestAnalyze(unittest.TestCase):
    """分析逻辑"""

    def test_empty_events(self):
        issues, info, stats = analyze([])
        self.assertEqual(issues, [])
        self.assertEqual(info, [])
        self.assertEqual(stats["total"], 0)

    def test_normal_operations_no_alerts(self):
        """正常调用序列不应触发告警"""
        evs = [
            _make_entry("tools_call_request", tool="agri_match_zone", arg_hash="abc"),
            _make_entry("tools_call_done", tool="agri_match_zone"),
            _make_entry("tools_call_request", tool="agri_recommend_crops", arg_hash="def"),
            _make_entry("tools_call_done", tool="agri_recommend_crops"),
        ]
        issues, info, stats = analyze(evs)
        self.assertEqual(issues, [])
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["done"], 2)
        self.assertEqual(stats["errs"], 0)

    def test_oversize_ratio_triggers_warn(self):
        """超长拒绝占比 > 20% 应触发 WARN"""
        evs = []
        for _ in range(100):
            evs.append(_make_entry("request_rejected", reason="oversize"))
        for _ in range(5):
            evs.append(_make_entry("tools_call_request", tool="x", arg_hash="h"))
        issues, _, stats = analyze(evs)
        self.assertTrue(any("超长" in msg for _, msg in issues))
        self.assertEqual(stats["oversize"], 100)

    def test_unknown_tool_probing_triggers_warn(self):
        """未知工具调用 > 5 次应触发 WARN"""
        evs = []
        for _ in range(6):
            evs.append(_make_entry("tools_call_rejected", tool="unknown"))
        issues, _, _ = analyze(evs)
        self.assertTrue(any("未知工具" in msg or "探测" in msg for _, msg in issues))

    def test_error_rate_triggers_warn(self):
        """错误率 > 30% 应触发 WARN"""
        evs = []
        for _ in range(35):
            evs.append(_make_entry("tools_call_error", tool="x", code=-32601))
        for _ in range(15):
            evs.append(_make_entry("tools_call_done", tool="y"))
        issues, _, _ = analyze(evs)
        self.assertTrue(any("错误率" in msg for _, msg in issues))

    def test_missing_arg_hash_triggers_warn(self):
        """tools_call_request 缺 arg_hash 应触发 WARN"""
        evs = [
            _make_entry("tools_call_request", tool="x"),  # 缺少 arg_hash
            _make_entry("tools_call_done", tool="x"),
        ]
        issues, _, _ = analyze(evs)
        self.assertTrue(any("arg_hash" in msg for _, msg in issues))

    def test_top_tools_info(self):
        """高频工具 Top3 应作为 INFO 返回"""
        evs = [
            _make_entry("tools_call_done", tool="agri_match_zone"),
            _make_entry("tools_call_done", tool="agri_match_zone"),
            _make_entry("tools_call_done", tool="agri_recommend_crops"),
        ]
        _, info, _ = analyze(evs)
        self.assertTrue(any("Top3" in msg for _, msg in info))

    def test_stats_structure(self):
        evs = [_make_entry("tools_call_request", tool="x", arg_hash="h"),
               _make_entry("tools_call_done", tool="x")]
        _, _, stats = analyze(evs)
        self.assertIn("total", stats)
        self.assertIn("oversize", stats)
        self.assertIn("unknown", stats)
        self.assertIn("done", stats)
        self.assertIn("errs", stats)


class TestThreshConstants(unittest.TestCase):
    """阈值常量"""

    def test_oversize_ratio(self):
        self.assertEqual(THRESH["oversize_ratio"], 0.2)

    def test_unknown_tool_max(self):
        self.assertEqual(THRESH["unknown_tool_max"], 5)

    def test_error_ratio(self):
        self.assertEqual(THRESH["error_ratio"], 0.3)


if __name__ == "__main__":
    unittest.main()
