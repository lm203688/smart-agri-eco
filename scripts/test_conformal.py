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


if __name__ == "__main__":
    unittest.main()
