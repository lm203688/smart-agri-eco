#!/usr/bin/env python3
"""
数据完整性门禁的回归测试

背景：该门禁原本内联在 .github/workflows/ci.yml 的 heredoc 里，含一个隐蔽的
作用域 bug —— 多个 ``any(... for k in synth)`` 用 ``or`` 串在多行时，有一处
``k`` 被解析为全局名而抛 NameError。由于 ``data/long_term_memory.json`` 当时
为空，该分支从未执行，CI 一直"绿的假象"；2026-10-08 记忆库有真实条目后，
三个 Python 版本同步骤全红。

本测试锁死两件事：
    1. 检测函数对合成样本判定正确（含 None 容忍）
    2. 真实的 data/ 目录干净 —— 若有人手动灌入 demo/unittest 样本，此处即报错

运行：python -m unittest scripts.test_data_integrity -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import check_data_integrity as G  # noqa: E402


class TestSyntheticMarker(unittest.TestCase):
    """标记检测函数：这是原 bug 的所在处，必须覆盖多种组合。"""

    def test_unittest_marker(self):
        self.assertTrue(G.has_synthetic_marker("[unittest] sync", "run_pipeline", []))

    def test_smoke_marker(self):
        self.assertTrue(G.has_synthetic_marker("", "smoke_test", []))

    def test_demo_marker(self):
        self.assertTrue(G.has_synthetic_marker("[demo] 演示", "", ["x"]))

    def test_clean_data(self):
        self.assertFalse(G.has_synthetic_marker("", "run_pipeline", ["hot_arid"]))

    def test_none_tolerant(self):
        # 真实记忆里 source_ref 常为空串或缺失；None 不得炸
        self.assertFalse(G.has_synthetic_marker(None, None, None))

    def test_case_insensitive(self):
        self.assertTrue(G.has_synthetic_marker("UNITTEST", "", []))

    def test_marker_in_tags_list(self):
        self.assertTrue(G.has_synthetic_marker("", "ok", ["demo"]))

    def test_empty_strings(self):
        self.assertFalse(G.has_synthetic_marker("", "", []))


class TestRealDataClean(unittest.TestCase):
    """仓库真实数据必须干净。"""

    def test_crop_adapt_db_calibrated_has_evidence(self):
        self.assertEqual(G.check_calibrated_evidence(), 0)

    def test_feedback_log_clean(self):
        self.assertEqual(G.check_feedback_log(), 0)

    def test_long_term_memory_clean(self):
        self.assertEqual(G.check_long_term_memory(), 0)

    def test_main_returns_zero(self):
        self.assertEqual(G.main(), 0)


class TestGateCanFail(unittest.TestCase):
    """门禁必须真的能失败——不能是永远返回 0 的摆设。"""

    def test_injected_pollution_detected(self):
        path = os.path.join(G.ROOT, "data", "long_term_memory.json")
        if not os.path.exists(path):
            self.skipTest("long_term_memory.json 不存在")

        with open(path, encoding="utf-8") as f:
            original = f.read()
        try:
            doc = json.loads(original)
            doc.setdefault("memories", []).append({
                "id": "mem-REGRESSION-POISON",
                "source_ref": "[unittest] injected by test",
                "skill": "test",
                "tags": [],
            })
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            self.assertEqual(G.check_long_term_memory(), 1,
                             "注入合成样本后门禁未报错——门禁失效！")
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
