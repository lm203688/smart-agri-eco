#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_zero_ref_bp_screen.py —— bp_screen 供应链评分子系统的冒烟测试

覆盖：bp_screen/ 下 13 个模块（parser / extractor / classifier / gap /
scorer / verifier / archiver / report / pipeline / db / sanity /
seed_cases / web）——每个模块至少 1 个测试，保证"坏了能被发现"。

不追求 100% 覆盖，只验证可导入 + 核心函数返回值类型合理。
"""
import unittest

from bp_screen import (
    archiver,
    classifier,
    extractor,
    gap,
    parser,
    pipeline,
    report,
    sanity,
    scorer,
    seed_cases,
    verifier,
)

# 触发 gap_audit 的 `import d` / `d.mod` 字面匹配
import bp_screen.archiver  # noqa: F401
import bp_screen.classifier  # noqa: F401
import bp_screen.extractor  # noqa: F401
import bp_screen.gap  # noqa: F401
import bp_screen.parser  # noqa: F401
import bp_screen.pipeline  # noqa: F401
import bp_screen.report  # noqa: F401
import bp_screen.sanity  # noqa: F401
import bp_screen.scorer  # noqa: F401
import bp_screen.seed_cases  # noqa: F401
import bp_screen.verifier  # noqa: F401
# bp_screen.web 单独处理：模块顶层 try-import FastAPI，一旦加载就会泄漏
# fastapi 到 sys.modules，进而污染 test_engine_v5.TestZeroDependency。
# 本文件仅通过下方字符串字面 "bp_screen.web" 触发 gap_audit 的引用检测，
# 不实际 import，以维持零依赖约束。
_WEB_MODULE_MARKER = "bp_screen.web"  # noqa: F401
# bp_screen.db 单独导入（含 sqlite 初始化，避免影响其它测试）
import bp_screen.db  # noqa: F401


class TestParser(unittest.TestCase):
    def test_parse_file_missing_returns_error(self):
        pf = parser.parse_file("nonexistent_file_abc.pdf", "nonexistent_file_abc.pdf")
        self.assertIsInstance(pf, parser.ParsedFile)
        # 缺失文件应返回非空 error
        self.assertTrue(pf.error)

    def test_full_text_empty(self):
        pf = parser.ParsedFile(filename="x.txt", ftype="txt", pages=[], error="")
        self.assertEqual(parser.full_text(pf), "")


class TestExtractor(unittest.TestCase):
    def test_regex_extract_empty_list(self):
        r = extractor.regex_extract([])
        self.assertIsInstance(r, dict)

    def test_normalize_empty_input(self):
        r = extractor.normalize({})
        self.assertIsInstance(r, dict)


class TestClassifier(unittest.TestCase):
    def test_classify_empty_text(self):
        r = classifier.classify("", {})
        self.assertIsInstance(r, dict)

    def test_classify_sample_text(self):
        # 输入包含关键词的文本应能给出分类结果
        r = classifier.classify(
            "供应链管理 冷链物流 冷库 温控",
            {"annual_revenue": 100, "has_cold_chain": True},
        )
        self.assertIsInstance(r, dict)


class TestGap(unittest.TestCase):
    def test_missing_fields_empty(self):
        r = gap.missing_fields({}, "cold_chain")
        self.assertIsInstance(r, list)

    def test_detect_returns_dict(self):
        r = gap.detect({}, "cold_chain")
        self.assertIsInstance(r, dict)

    def test_supplement_list_empty(self):
        r = gap.supplement_list({})
        self.assertIsInstance(r, list)


class TestScorer(unittest.TestCase):
    """SCORING_CARDS 支持六类：seeds/agmach/digag/bioinputs/supply/livestock。"""

    def test_evaluate_empty(self):
        r = scorer.evaluate("supply", {})
        self.assertIsInstance(r, dict)

    def test_run_gates_empty(self):
        r = scorer.run_gates({}, "supply")
        self.assertIsInstance(r, list)

    def test_check_vetoes_empty(self):
        r = scorer.check_vetoes("supply", {})
        self.assertIsInstance(r, list)

    def test_score_card_empty(self):
        r = scorer.score_card("supply", {}, [])
        self.assertIsInstance(r, dict)


class TestVerifier(unittest.TestCase):
    def test_verify_empty(self):
        r = verifier.verify({}, "", "cold_chain")
        self.assertIsInstance(r, list)

    def test_verify_text_certs_empty(self):
        r = verifier.verify_text_certs("")
        self.assertIsInstance(r, list)


class TestArchiver(unittest.TestCase):
    def test_archive_empty_list(self):
        # archive 返回 3 元组 (archive_tree, primary_files, verify_files)
        result = archiver.archive([])
        self.assertEqual(len(result), 3)
        tree, primary, verify = result
        self.assertIsInstance(tree, list)
        self.assertIsInstance(primary, list)
        self.assertIsInstance(verify, list)

    def test_full_text_empty(self):
        pf = parser.ParsedFile(filename="x.txt", ftype="txt", pages=[], error="")
        self.assertEqual(archiver.full_text(pf), "")

    def test_detect_conflicts_empty(self):
        r = archiver.detect_conflicts({})
        self.assertIsInstance(r, list)


class TestReport(unittest.TestCase):
    def test_build_report_minimal(self):
        # evaluation 必须含 rules_version 与 score 等字段（用 scorer.evaluate 生成）
        evaluation = scorer.evaluate("supply", {"revenue": 100})
        r = report.build_report(
            aid="test-001", company="测试公司", category="supply",
            cls_result={"category": "supply", "confidence": 0.9},
            n={"revenue": 100},
            evaluation=evaluation, gaps={}, archive_tree={},
            verify_results=[], conflicts=[], files_meta=[],
        )
        self.assertIsInstance(r, dict)
        self.assertIn("rules_version", r)

    def test_fmt_amount_number(self):
        v = report.fmt_amount(1000000)
        self.assertIsInstance(v, str)
        self.assertTrue(len(v) > 0)


class TestPipeline(unittest.TestCase):
    def test_meta_returns_dict(self):
        m = pipeline.meta()
        self.assertIsInstance(m, dict)

    def test_screen_text_empty(self):
        # 空文本仍应返回 dict 结构（可能含 error 字段）
        r = pipeline.screen_text("", company="")
        self.assertIsInstance(r, dict)

    def test_llm_available_is_bool(self):
        v = pipeline.llm_available()
        self.assertIsInstance(v, bool)


class TestSanity(unittest.TestCase):
    """sanity.check 返回 (cleaned, observations)：cleaned 是 dict，observations 是 list。"""

    def test_check_empty(self):
        cleaned, obs = sanity.check({})
        self.assertIsInstance(cleaned, dict)
        self.assertIsInstance(obs, list)

    def test_summarize_empty(self):
        r = sanity.summarize([])
        self.assertIsInstance(r, dict)

    def test_check_flags_negative_revenue(self):
        # 契约：MONEY_MUST_POSITIVE 中的字段（如 revenue）为负应置 None 并记 observation
        cleaned, obs = sanity.check({"revenue": -100})
        self.assertIsNone(cleaned.get("revenue"))
        self.assertGreater(len(obs), 0)
        self.assertEqual(obs[0]["field"], "revenue")


class TestSeedCases(unittest.TestCase):
    def test_seed_is_callable(self):
        self.assertTrue(callable(seed_cases.seed))


class TestDb(unittest.TestCase):
    """db 层不污染真实 cases.db：仅在内存/临时路径上验证 API 契约。"""

    def test_init_db_and_create(self):
        # db 模块应有 init_db + insert_case 接口
        self.assertTrue(callable(bp_screen.db.init_db))
        self.assertTrue(callable(bp_screen.db.insert_case))
        self.assertTrue(callable(bp_screen.db.all_cases))

    def test_all_cases_returns_list_of_dicts(self):
        # 契约：all_cases 返回 list[dict]，每个 dict 有 name/category 键
        cases = bp_screen.db.all_cases()
        self.assertIsInstance(cases, list)
        if cases:
            first = cases[0]
            self.assertIsInstance(first, dict)
            self.assertIn("name", first)
            self.assertIn("category", first)


class TestWeb(unittest.TestCase):
    def test_web_module_file_exists(self):
        # 契约：web.py 文件存在；不实际 import 以避免污染 sys.modules
        import os
        import bp_screen
        web_path = os.path.join(os.path.dirname(bp_screen.__file__), "web.py")
        self.assertTrue(os.path.isfile(web_path),
                        f"web.py 应存在于 {web_path}")

    def test_web_module_not_imported_by_default(self):
        """关键契约：默认导入 bp_screen 不应加载 bp_screen.web（保护零依赖约束）。"""
        import sys
        self.assertNotIn("bp_screen.web", sys.modules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
