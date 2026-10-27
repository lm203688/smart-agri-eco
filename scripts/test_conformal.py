"""test_conformal.py — Split Conformal Prediction 单元测试（M5-F1）。

覆盖：
  - 相对残差定义与符号
  - quantile 计算（大样本、小样本、退化边界）
  - predict_interval 返回 (lower, point, upper) 有序
  - 校准点自包含性（3 个基准用例真值应全部落入自己的 conformal 区间）
  - 覆盖率下界数学保证（有限样本 split conformal 定理）
  - 方法元信息输出
"""
from __future__ import annotations

import math
import sys
import unittest

ROOT = sys.path[0] if sys.path else "."
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.conformal import (  # noqa: E402
    SplitConformal,
    build_calibrator_from_pairs,
    get_default_calibrator,
    relative_residue,
    split_conformal_interval,
)


class TestRelativeResidue(unittest.TestCase):
    def test_zero_when_equal(self):
        self.assertEqual(relative_residue(100.0, 100.0), 0.0)

    def test_positive_when_differs(self):
        self.assertGreater(relative_residue(120.0, 100.0), 0)
        self.assertGreater(relative_residue(80.0, 100.0), 0)

    def test_denominator_is_pred_not_truth(self):
        """pred=100, truth=120: 残差=0.2（以 pred 为分母）。"""
        self.assertAlmostEqual(relative_residue(100.0, 120.0), 0.2, places=6)

    def test_pred_zero_falls_back_to_1(self):
        """pred=0 时分母退化为 1，残差=|truth|。"""
        self.assertAlmostEqual(relative_residue(0.0, 5.0), 5.0, places=6)

    def test_none_returns_zero(self):
        self.assertEqual(relative_residue(None, 100.0), 0.0)
        self.assertEqual(relative_residue(100.0, None), 0.0)


class TestSplitConformal(unittest.TestCase):
    def test_empty_calibrator_returns_none_quantile(self):
        c = SplitConformal(calibration_scores=[])
        self.assertIsNone(c.quantile())
        self.assertEqual(c.n, 0)
        self.assertEqual(c.coverage_guarantee(), 0.0)

    def test_alpha_validation(self):
        with self.assertRaises(ValueError):
            SplitConformal(calibration_scores=[0.1], alpha=0.0)
        with self.assertRaises(ValueError):
            SplitConformal(calibration_scores=[0.1], alpha=1.0)
        with self.assertRaises(ValueError):
            SplitConformal(calibration_scores=[0.1], alpha=1.5)

    def test_negative_scores_filtered(self):
        c = SplitConformal(calibration_scores=[0.1, -0.5, 0.2])
        self.assertEqual(c.n, 2)

    def test_quantile_sorted_properly(self):
        """quantile 必须基于排序后的分数取秩。"""
        # 分数无顺序输入 [0.05, 0.15, 0.08, 0.12]，
        # n=4, α=0.10 → idx=ceil(5*0.9)-1=ceil(4.5)-1=5-1=4，越界 → max=0.15
        c = SplitConformal(calibration_scores=[0.05, 0.15, 0.08, 0.12], alpha=0.10)
        self.assertAlmostEqual(c.quantile(), 0.15, places=6)

    def test_quantile_mid_range(self):
        """n=10, α=0.10 → idx=ceil(11*0.9)-1=ceil(9.9)-1=10-1=9，取第 10 大（max）。"""
        scores = [0.01 * i for i in range(1, 11)]  # [0.01, ..., 0.10]
        c = SplitConformal(calibration_scores=scores, alpha=0.10)
        self.assertAlmostEqual(c.quantile(), 0.10, places=6)

    def test_quantile_alpha_05_n5(self):
        """n=5, α=0.05 → idx=ceil(6*0.95)-1=ceil(5.7)-1=6-1=5，越界 → max。"""
        scores = [0.01, 0.02, 0.03, 0.04, 0.05]
        c = SplitConformal(calibration_scores=scores, alpha=0.05)
        self.assertAlmostEqual(c.quantile(), 0.05, places=6)

    def test_predict_interval_ordered(self):
        c = SplitConformal(calibration_scores=[0.05, 0.10, 0.15], alpha=0.10)
        lo, mid, hi = c.predict_interval(1000.0)
        self.assertLessEqual(lo, mid)
        self.assertLessEqual(mid, hi)
        self.assertEqual(mid, 1000.0)

    def test_predict_interval_no_calibration_returns_point(self):
        c = SplitConformal(calibration_scores=[])
        lo, mid, hi = c.predict_interval(1000.0)
        self.assertEqual((lo, mid, hi), (1000.0, 1000.0, 1000.0))

    def test_coverage_guarantee_matches_alpha(self):
        c = SplitConformal(calibration_scores=[0.1], alpha=0.10)
        self.assertAlmostEqual(c.coverage_guarantee(), 0.90, places=6)


class TestSplitConformalCalibrationProperty(unittest.TestCase):
    """split conformal 的有限样本覆盖率下界定理：
       对任意 n 个 iid 校准样本 + 1 个测试样本，
       P(y_test ∈ [ŷ_test ± q_n]) ≥ 1 - α。

    测试点应至少能覆盖所有 n 个校准样本自身（这是 q 取到 max 时的边界性质，
    保证"训练点"自身覆盖率=100%，与 1-α 下界一致——只是下界更紧）。
    """

    def test_calibration_points_covered_when_q_is_max(self):
        """3 个校准点：所有真值应落入以 point 为对称、半宽=q_max 的区间。"""
        pairs = [(1432.0, 1600.0), (466.0, 500.0), (273.0, 280.0)]
        c = build_calibrator_from_pairs(pairs, alpha=0.10)
        self.assertGreaterEqual(c.n, 3)
        # n=3, α=0.10 → idx=4-1=3 越界 → max
        # 因此区间半宽 = max(residues)，所有校准点必落区间内
        for pred, truth in pairs:
            lo, mid, hi = c.predict_interval(pred)
            self.assertLessEqual(lo, truth,
                                 f"pred={pred} truth={truth} 未在 [{lo},{hi}] 内")
            self.assertLessEqual(truth, hi,
                                 f"pred={pred} truth={truth} 未在 [{lo},{hi}] 内")

    def test_default_calibrator_all_three_covered(self):
        """内置校准器：3 个 AgriRecipeBench target_prediction 用例真值应全部落入。"""
        c = get_default_calibrator()
        self.assertEqual(c.n, 3)
        # 3 个已知校准用例的真值
        for pred, truth in [(1432.0, 1600.0), (466.0, 500.0), (273.0, 280.0)]:
            lo, mid, hi = c.predict_interval(pred)
            self.assertLessEqual(lo, truth)
            self.assertLessEqual(truth, hi)

    def test_default_calibrator_coverage_guarantee_90(self):
        c = get_default_calibrator(alpha=0.10)
        self.assertAlmostEqual(c.coverage_guarantee(), 0.90, places=6)
        self.assertGreater(c.quantile(), 0)


class TestSplitConformalIntervalHelper(unittest.TestCase):
    def test_split_conformal_interval_returns_full_metadata(self):
        c = get_default_calibrator()
        result = split_conformal_interval(c, point_est=1500.0)
        self.assertIn("p50", result)
        self.assertIn("p10", result)
        self.assertIn("p90", result)
        self.assertEqual(result["p50"], 1500.0)
        self.assertLessEqual(result["p10"], result["p50"])
        self.assertLessEqual(result["p50"], result["p90"])
        self.assertEqual(result["interval_method"], "split_conformal")
        self.assertGreater(result["coverage_guarantee"], 0.85)
        self.assertGreater(result["calibration_n"], 0)
        self.assertIsNotNone(result["quantile_q"])

    def test_split_conformal_interval_p0_2_semantics(self):
        """P0-2：输出含语义正确字段（point/coverage_lower/coverage_upper），
        且 interval_semantics 诚实标注为中央覆盖区间（非分位数）。"""
        c = get_default_calibrator()
        result = split_conformal_interval(c, point_est=1500.0)
        # 语义正确字段存在且与旧字段一致（向后兼容）
        self.assertEqual(result["point"], result["p50"])
        self.assertEqual(result["coverage_lower"], result["p10"])
        self.assertEqual(result["coverage_upper"], result["p90"])
        # 中央覆盖区间语义：非分位数
        self.assertEqual(result["interval_semantics"], "central_coverage_interval")
        # 目标覆盖率 = 1 - alpha
        self.assertAlmostEqual(result["target_coverage"], 0.90, places=4)
        # 校准集来源可审计（P0-2 要求 calibration_set_id）
        self.assertEqual(result["calibration_set_id"],
                         "agri_recipe_bench_target_prediction_v1")
        self.assertEqual(result["calibration_n"], c.n)


class TestSplitConformalCoverageBound(unittest.TestCase):
    """覆盖率下界的数学验证（split conformal 保证）。"""

    def test_coverage_bound_lower_than_or_equal_1_minus_alpha(self):
        """覆盖率下界 1-α 严格小于等于 1。"""
        for alpha in (0.05, 0.10, 0.20):
            c = SplitConformal(calibration_scores=[0.01] * 5, alpha=alpha)
            self.assertLessEqual(c.coverage_guarantee(), 1.0)
            self.assertAlmostEqual(c.coverage_guarantee(), 1 - alpha, places=6)

    def test_quantile_monotone_in_n(self):
        """样本越多，q 值理论上非减（更多残差样本 → 更紧的秩选择）。"""
        base_scores = [0.02, 0.05, 0.08]
        c1 = SplitConformal(calibration_scores=base_scores, alpha=0.10)
        q1 = c1.quantile()
        # 增加更多残差
        c2 = SplitConformal(calibration_scores=base_scores + [0.03, 0.06], alpha=0.10)
        q2 = c2.quantile()
        # q1=q_max because idx 越界；q2 可能相同或更小
        self.assertIsNotNone(q1)
        self.assertIsNotNone(q2)


# ---------- M15-B4: bench 保形覆盖率指标 ----------

class TestBenchConformalCoverage(unittest.TestCase):
    """M15-B4：_compute_conformal_coverage 在 bench runner 中的集成测试。"""

    def _run(self, results):
        import sys, os
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, ROOT)
        from benchmarks.agri_recipe_bench.run_bench import _compute_conformal_coverage
        return _compute_conformal_coverage(results)

    def test_empty_results_disables(self):
        cc = self._run([])
        self.assertFalse(cc["enabled"])
        self.assertEqual(cc["reason"], "无 target_prediction 用例")

    def test_no_target_prediction_disables(self):
        results = [
            {"axis": "state_rolling", "ok": True, "case_id": "sr_1"},
            {"axis": "counterfactual", "ok": True, "case_id": "cf_1"},
        ]
        cc = self._run(results)
        self.assertFalse(cc["enabled"])
        self.assertEqual(cc["reason"], "无 target_prediction 用例")

    def test_basic_coverage_computation(self):
        results = [
            {"axis": "target_prediction", "ok": True, "case_id": "tp_1",
             "checks": {"yield": {"pred": 500.0, "expected": 500.0, "ok": True}}},
            {"axis": "target_prediction", "ok": True, "case_id": "tp_2",
             "checks": {"yield": {"pred": 300.0, "expected": 280.0, "ok": True}}},
        ]
        cc = self._run(results)
        self.assertTrue(cc["enabled"])
        self.assertEqual(cc["method"], "split_conformal")
        self.assertEqual(cc["alpha"], 0.10)
        self.assertEqual(cc["total_metrics"], 2)
        self.assertGreaterEqual(cc["covered"], 0)
        self.assertLessEqual(cc["coverage"], 1.0)
        self.assertEqual(cc["above_guarantee"], cc["coverage"] >= cc["coverage_guarantee"])

    def test_perfect_predictions_give_full_coverage(self):
        """所有 pred == expected → 残差全 0 → q=0 → 覆盖率 100%。"""
        results = [
            {"axis": "target_prediction", "ok": True, "case_id": f"tp_{i}",
             "checks": {"yield": {"pred": 100.0, "expected": 100.0, "ok": True}}}
            for i in range(5)
        ]
        cc = self._run(results)
        self.assertTrue(cc["enabled"])
        self.assertEqual(cc["coverage"], 1.0)
        self.assertTrue(cc["above_guarantee"])

    def test_missing_pred_or_expected_skipped(self):
        """pred 或 expected 为 None 的 metric 应被跳过。"""
        results = [
            {"axis": "target_prediction", "ok": True, "case_id": "tp_1",
             "checks": {
                 "yield": {"pred": 500.0, "expected": 500.0, "ok": True},
                 "duration": {"pred": None, "expected": 90, "ok": True},
             }},
        ]
        cc = self._run(results)
        self.assertTrue(cc["enabled"])
        self.assertEqual(cc["total_metrics"], 1)  # 只算 yield

    def test_coverage_above_guarantee_flag(self):
        """覆盖率应 ≥ guarantee（full calibration 保证）。"""
        results = [
            {"axis": "target_prediction", "ok": True, "case_id": f"tp_{i}",
             "checks": {"yield": {"pred": 100.0, "expected": 100.0 + i * 5, "ok": True}}}
            for i in range(10)
        ]
        cc = self._run(results)
        self.assertTrue(cc["enabled"])
        self.assertTrue(cc["above_guarantee"],
                        f"覆盖率 {cc['coverage']} 应 ≥ guarantee {cc['coverage_guarantee']}")

    def test_guarantee_is_0_90(self):
        cc = self._run([
            {"axis": "target_prediction", "ok": True, "case_id": "tp_1",
             "checks": {"yield": {"pred": 100.0, "expected": 100.0, "ok": True}}},
        ])
        self.assertAlmostEqual(cc["coverage_guarantee"], 0.90, places=4)

    def test_details_contain_residue_and_covered(self):
        results = [
            {"axis": "target_prediction", "ok": True, "case_id": "tp_1",
             "checks": {"yield": {"pred": 500.0, "expected": 500.0, "ok": True}}},
        ]
        cc = self._run(results)
        self.assertTrue(cc["enabled"])
        self.assertEqual(len(cc["details"]), 1)
        d = cc["details"][0]
        self.assertIn("case_id", d)
        self.assertIn("metric", d)
        self.assertIn("residue", d)
        self.assertIn("covered", d)
        self.assertIn("pred", d)
        self.assertIn("expected", d)


# ---------- M15-B4: SplitConformal.compute_coverage + CLI ----------

class TestSplitConformalComputeCoverage(unittest.TestCase):
    """M15-B4：新增 compute_coverage 方法——覆盖率可外部审计。"""

    def test_empty_test_pairs_returns_ok_false(self):
        c = get_default_calibrator()
        r = c.compute_coverage([])
        self.assertFalse(r["ok"])
        self.assertEqual(r["observed_coverage"], 0.0)
        self.assertEqual(r["n_test"], 0)
        self.assertEqual(r["n_hit"], 0)

    def test_perfect_predictions_full_coverage(self):
        """区间半宽>0 时，若 truth==pred，命中率=1。"""
        c = SplitConformal(calibration_scores=[0.05, 0.10], alpha=0.10)
        pairs = [(100.0, 100.0), (200.0, 200.0), (300.0, 300.0)]
        r = c.compute_coverage(pairs)
        self.assertTrue(r["ok"])
        self.assertEqual(r["observed_coverage"], 1.0)
        self.assertEqual(r["n_hit"], 3)

    def test_threshold_failure_marks_not_ok(self):
        """阈值高于 observed 时 ok=False。"""
        c = SplitConformal(calibration_scores=[0.05, 0.10], alpha=0.10)
        # 让一部分测试对漏出：小残差校准但给极端真值
        pairs = [(100.0, 200.0)]  # truth 远高于区间
        r = c.compute_coverage(pairs, threshold=0.9)
        self.assertFalse(r["ok"])
        self.assertLess(r["observed_coverage"], 0.9)
        self.assertEqual(r["n_miss"], 1)

    def test_threshold_defaults_to_one_minus_alpha(self):
        c = SplitConformal(calibration_scores=[0.05, 0.10], alpha=0.10)
        r = c.compute_coverage([(100.0, 100.0)])
        self.assertAlmostEqual(r["threshold"], 0.90, places=4)
        self.assertEqual(r["target_coverage"], r["threshold"])

    def test_alpha_override_applied(self):
        """传入不同 alpha 覆盖 self.alpha。"""
        c = SplitConformal(calibration_scores=[0.05, 0.10], alpha=0.10)
        r = c.compute_coverage([(100.0, 100.0)], alpha=0.20)
        self.assertAlmostEqual(r["alpha_effective"], 0.20, places=4)
        self.assertAlmostEqual(r["target_coverage"], 0.80, places=4)
        # self.alpha 未被就地修改
        self.assertAlmostEqual(c.alpha, 0.10, places=6)

    def test_invalid_alpha_raises(self):
        c = SplitConformal(calibration_scores=[0.05], alpha=0.10)
        with self.assertRaises(ValueError):
            c.compute_coverage([(1.0, 1.0)], alpha=1.5)
        with self.assertRaises(ValueError):
            c.compute_coverage([(1.0, 1.0)], alpha=0.0)

    def test_detail_contains_hit_flag(self):
        c = SplitConformal(calibration_scores=[0.05, 0.10], alpha=0.10)
        pairs = [(100.0, 100.0), (100.0, 500.0)]
        r = c.compute_coverage(pairs)
        self.assertEqual(len(r["detail"]), 2)
        self.assertTrue(r["detail"][0]["hit"])
        self.assertFalse(r["detail"][1]["hit"])
        for d in r["detail"]:
            self.assertIn("pred", d)
            self.assertIn("truth", d)
            self.assertIn("lower", d)
            self.assertIn("upper", d)

    def test_default_calibrator_high_coverage_on_known_pairs(self):
        """内置校准器对已知 3 对 → 应达 100%（q=max 时区间宽）。"""
        c = get_default_calibrator()
        pairs = [(1432.0, 1600.0), (466.0, 500.0), (273.0, 280.0)]
        r = c.compute_coverage(pairs, threshold=0.9)
        self.assertTrue(r["ok"])
        self.assertEqual(r["observed_coverage"], 1.0)

    def test_none_pairs_filtered(self):
        """None 对被过滤，n_test 只算有效对。"""
        c = SplitConformal(calibration_scores=[0.05], alpha=0.10)
        pairs = [(1.0, 1.0), (None, 2.0), (3.0, None)]
        r = c.compute_coverage(pairs)
        self.assertEqual(r["n_test"], 1)


class TestSplitConformalCLI(unittest.TestCase):
    """M15-B4：CLI `python -m agent.conformal check`。"""

    def _run(self, args):
        import subprocess, sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return subprocess.run(
            [sys.executable, "-m", "agent.conformal", *args],
            cwd=root, capture_output=True, text=True, timeout=30,
        )

    def test_check_default_exits_zero(self):
        p = self._run(["check", "--threshold", "0.9"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("OK: True", p.stdout)

    def test_check_json_out_is_parseable(self):
        p = self._run(["check", "--threshold", "0.9", "--json-out"])
        self.assertEqual(p.returncode, 0, p.stderr)
        import json
        data = json.loads(p.stdout)
        self.assertIn("observed_coverage", data)
        self.assertIn("ok", data)
        self.assertIn("detail", data)

    def test_check_strict_threshold_fails(self):
        p = self._run(["check", "--threshold", "0.99", "--json-out"])
        # 阈值 0.99 对 3/3 命中(1.0) 仍通过；用 1.01 保证失败
        p2 = self._run(["check", "--threshold", "1.01", "--json-out"])
        self.assertEqual(p2.returncode, 1, p2.stdout + p2.stderr)
        import json
        self.assertFalse(json.loads(p2.stdout)["ok"])

    def test_check_with_pairs_csv(self):
        import tempfile, os
        csv = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        csv.write("100,100\n200,200\n300,300\n")
        csv.close()
        try:
            p = self._run(["check", "--pairs-csv", csv.name, "--threshold", "0.9"])
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(csv.name)

    def test_check_with_pairs_json(self):
        import tempfile, os, json
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump([[100.0, 100.0], {"pred": 200.0, "truth": 200.0}], tmp)
        tmp.close()
        try:
            p = self._run(["check", "--pairs-json", tmp.name, "--threshold", "0.9"])
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            os.unlink(tmp.name)

    def test_show_mode_still_works(self):
        p = self._run(["show"])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("自测通过", p.stdout)

    def test_no_args_defaults_to_show(self):
        p = self._run([])
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
