"""T-3 置信区间回归守卫。

覆盖点：
  1. 所有输出包含 prediction_interval（yield / duration / harvest_date 三组）
  2. P50 与旧单点字段向后兼容（yield_estimate_g == prediction_interval.yield_estimate_g.p50）
  3. P10 ≤ P50 ≤ P90（数学单调性）
  4. 空输入时 uncertainty_uplift > 完整输入时（数据越缺区间越宽）
  5. 未知作物 fallback 到默认 spread（不误报异常）
"""
import unittest

from agent.forecast_agent import ForecastAgent


class ConfidenceIntervalTests(unittest.TestCase):

    def setUp(self):
        self.agent = ForecastAgent()

    def _full_input(self):
        return self.agent.estimate(
            crop="番茄", zone_id="mediterranean", start_date="2026-02-15",
            adapt_score=0.9,
            growth_plan={"recommendation": {"phases": [
                {"day_range": [1, 30]}, {"day_range": [31, 60]},
                {"day_range": [61, 95]}, {"day_range": [96, 130]},
            ]}},
            env_recipe={"environment": {"temperature": {"day_c": 32}}},
        )

    def _empty_input(self):
        return self.agent.estimate(
            crop="生菜", zone_id="subtropical_wet", start_date="2026-03-20",
        )

    def test_prediction_interval_present(self):
        r = self._full_input()
        pi = r["recommendation"]["prediction_interval"]
        for key in ("yield_estimate_g", "adjusted_duration_days", "harvest_date"):
            self.assertIn(key, pi, f"prediction_interval 缺 {key}")
            for p in ("p50", "p10", "p90"):
                self.assertIn(p, pi[key], f"{key} 缺 {p}")

    def test_p50_backward_compat(self):
        """P50 与旧单点字段一致——这是向后兼容契约。"""
        r = self._full_input()
        rec = r["recommendation"]
        pi = rec["prediction_interval"]
        self.assertEqual(rec["yield_estimate_g"], pi["yield_estimate_g"]["p50"])
        self.assertEqual(rec["adjusted_duration_days"], pi["adjusted_duration_days"]["p50"])
        self.assertEqual(rec["harvest_date"], pi["harvest_date"]["p50"])

    def test_numeric_monotonicity(self):
        """P10 ≤ P50 ≤ P90（数值型字段）"""
        r = self._full_input()
        for metric in ("yield_estimate_g", "adjusted_duration_days"):
            vals = r["recommendation"]["prediction_interval"][metric]
            self.assertLessEqual(vals["p10"], vals["p50"], f"{metric}: p10 > p50")
            self.assertLessEqual(vals["p50"], vals["p90"], f"{metric}: p50 > p90")
            self.assertGreater(vals["p10"], 0, f"{metric}: p10 应为正数")

    def test_date_monotonicity(self):
        """采收日期区间：p10 日期 ≤ p50 日期 ≤ p90 日期"""
        r = self._full_input()
        d = r["recommendation"]["prediction_interval"]["harvest_date"]
        self.assertLessEqual(d["p10"], d["p50"], "harvest p10 > p50")
        self.assertLessEqual(d["p50"], d["p90"], "harvest p50 > p90")

    def test_empty_input_wider_than_full(self):
        """空输入的数据完备度惩罚使区间更宽（相对散布系数增大）"""
        full = self._full_input()["confidence"]["uncertainty"]["yield_spread_fraction"]
        empty = self._empty_input()["confidence"]["uncertainty"]["yield_spread_fraction"]
        self.assertGreater(empty, full,
                          f"空输入 spread={empty} 应 > 完整输入 spread={full}")
        self.assertGreater(
            self._empty_input()["confidence"]["uncertainty"]["uncertainty_uplift"],
            self._full_input()["confidence"]["uncertainty"]["uncertainty_uplift"],
            "空输入 uncertainty_uplift 应更大",
        )

    def test_unknown_crop_uses_fallback(self):
        """未知作物走 fallback spread（不抛异常）"""
        r = self.agent.estimate(
            crop="不存在作物xyz", zone_id="temperate_subhumid", start_date="2026-04-01",
            adapt_score=0.7,
        )
        # 有 interval 且不崩溃即通过；yield 走 fallback=500g 基准
        self.assertIn("prediction_interval", r["recommendation"])
        self.assertGreater(r["recommendation"]["yield_estimate_g"], 0)
        uplift = r["confidence"]["uncertainty"]["yield_spread_fraction"]
        # fallback spread=0.4，无 env_recipe 加 25% = 0.5
        self.assertAlmostEqual(uplift, 0.5, places=2)

    def test_uncertainty_decomposition_present(self):
        """confidence.uncertainty 应含 method / 散布系数 / 输入惩罚 / 说明"""
        r = self._full_input()
        u = r["confidence"]["uncertainty"]
        for k in ("method", "yield_spread_fraction", "duration_spread_fraction",
                  "uncertainty_uplift", "note"):
            self.assertIn(k, u, f"confidence.uncertainty 缺 {k}")
        self.assertEqual(u["method"], "heuristic_spread_based")


if __name__ == "__main__":
    unittest.main()
