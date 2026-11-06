#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_g1_counter.py —— G1 计数机制单测

覆盖 mcp/g1_counter.py 核心逻辑：
- 调用方指纹提取（client_id / traceparent / tool+arg_hash 三优先级回退）
- G1 统计（只计 tools_call_done 成功；累计 + 独立调用方去重）
- 持久化（reconcile 保留历史峰值防回退）
- 阈值判断（500 / 20）
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.g1_counter import (
    G1_CALLERS_THRESHOLD,
    G1_TOTAL_THRESHOLD,
    caller_fingerprint,
    compute_g1,
    load_events,
    load_counter_state,
    reconcile,
    save_counter_state,
)


class TestCallerFingerprint(unittest.TestCase):
    def test_client_id_priority(self):
        """client_id 是最高优先级去重键（稳定、带 cid: 前缀）。"""
        ev = {"client_id": "agent-alpha", "traceparent": "00-abc123-def456-01",
              "tool": "agri_list_cities", "arg_hash": "h1"}
        fp = caller_fingerprint(ev)
        self.assertTrue(fp.startswith("cid:"))
        self.assertEqual(len(fp), 16)  # "cid:" + 12hex

    def test_traceparent_fallback(self):
        """无 client_id 时回退 traceparent trace-id（tp: 前缀）。"""
        ev = {"traceparent": "00-00112233445566778899aabbccddeeff-0011223344556677-01",
              "tool": "agri_list_cities", "arg_hash": "h1"}
        fp = caller_fingerprint(ev)
        self.assertTrue(fp.startswith("tp:"))

    def test_arg_hash_fallback(self):
        """无 client_id/traceparent 时回退 tool+arg_hash（weak: 前缀）。"""
        ev = {"tool": "agri_match_zone", "arg_hash": "deadbeef"}
        fp = caller_fingerprint(ev)
        self.assertTrue(fp.startswith("weak:"))

    def test_no_identity_gives_empty(self):
        """全空事件返回空串（不计入独立调用方）。"""
        ev = {}
        self.assertEqual(caller_fingerprint(ev), "")

    def test_stability(self):
        """同一 client_id 多次调用产生相同指纹（去重键稳定）。"""
        fp1 = caller_fingerprint({"client_id": "agent-alpha", "tool": "a", "arg_hash": "h1"})
        fp2 = caller_fingerprint({"client_id": "agent-alpha", "tool": "b", "arg_hash": "h2"})
        self.assertEqual(fp1, fp2)


class TestComputeG1(unittest.TestCase):
    def test_counts_only_success(self):
        """只计 tools_call_done（成功），tools_call_error/rejected 不计。"""
        evs = [
            {"event": "tools_call_done", "tool": "a", "arg_hash": "h1",
             "client_id": "alpha"},
            {"event": "tools_call_done", "tool": "b", "arg_hash": "h2",
             "client_id": "alpha"},
            {"event": "tools_call_error", "tool": "c", "arg_hash": "h3",
             "client_id": "beta"},
            {"event": "tools_call_rejected", "tool": "d", "arg_hash": "h4",
             "client_id": "beta"},
        ]
        g = compute_g1(evs)
        self.assertEqual(g["total_calls"], 2)
        self.assertEqual(g["unique_callers"], 1)

    def test_unique_callers(self):
        """多个调用方正确去重。"""
        evs = [
            {"event": "tools_call_done", "tool": "a", "arg_hash": "h1",
             "client_id": "alpha"},
            {"event": "tools_call_done", "tool": "b", "arg_hash": "h2",
             "client_id": "beta"},
            {"event": "tools_call_done", "tool": "c", "arg_hash": "h3",
             "client_id": "alpha"},  # alpha 重复
        ]
        g = compute_g1(evs)
        self.assertEqual(g["total_calls"], 3)
        self.assertEqual(g["unique_callers"], 2)

    def test_empty(self):
        """空审计 = 0/0。"""
        g = compute_g1([])
        self.assertEqual(g["total_calls"], 0)
        self.assertEqual(g["unique_callers"], 0)

    def test_thresholds(self):
        """阈值常量正确（门槛7=500、门槛8=20）。"""
        self.assertEqual(G1_TOTAL_THRESHOLD, 500)
        self.assertEqual(G1_CALLERS_THRESHOLD, 20)


class TestPersistence(unittest.TestCase):
    def test_reconcile_keeps_peak(self):
        """reconcile 保留历史峰值，防计数回退。"""
        state = {"total_calls": 10, "unique_callers": 3}
        events = [
            {"event": "tools_call_done", "tool": "a", "arg_hash": "h1",
             "client_id": "alpha"},
            {"event": "tools_call_done", "tool": "b", "arg_hash": "h2",
             "client_id": "beta"},
        ]
        g = reconcile(events, state)
        # 新事件 2 次/1 调用方，但历史峰值 10/3 保留
        self.assertEqual(g["total_calls"], 10)
        self.assertEqual(g["unique_callers"], 3)

    def test_reconcile_without_state(self):
        """无历史状态时从事件计算。"""
        events = [
            {"event": "tools_call_done", "tool": "a", "arg_hash": "h1",
             "client_id": "alpha"},
        ]
        g = reconcile(events, None)
        self.assertEqual(g["total_calls"], 1)
        self.assertEqual(g["unique_callers"], 1)

    def test_save_load_roundtrip(self):
        """save/load 往返一致。"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "g1_counter.json")
            state = {"total_calls": 42, "unique_callers": 7,
                     "caller_top": [{"key": "alpha", "calls": 42}]}
            save_counter_state(path, state)
            loaded = load_counter_state(path)
            self.assertEqual(loaded["total_calls"], 42)
            self.assertEqual(loaded["unique_callers"], 7)


class TestLoadEvents(unittest.TestCase):
    def test_load_missing_returns_empty(self):
        """缺失审计日志 = 空列表（不抛错）。"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "nonexistent.jsonl")
            self.assertEqual(load_events(path), [])

    def test_load_skips_bad_lines(self):
        """损坏行跳过，不中断。"""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "audit.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"event": "tools_call_done", "tool": "a"}\n')
                f.write('{bad json}\n')
                f.write('{"event": "tools_call_done", "tool": "b"}\n')
            evs = load_events(path)
            self.assertEqual(len(evs), 2)


if __name__ == "__main__":
    unittest.main()
