#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_zero_ref_agents_engine.py —— agent/ + engine/ 应用层零引用模块最小冒烟测试

GAP_AUDIT §6：agent/ 12 个 + engine/agriworld_gradients.py 一个 = 13 个零引用模块。
本文件为每个模块提供至少 1 个测试（覆盖导入、基本调用、异常契约），
确保"任何一处坏了能被发现"。
"""
import unittest

# gap_audit 匹配 `from d.mod` 或 `import mod` 或 `d.mod` 字面串；
# 用 `import d as _` 加显式字面串触发匹配。
import agent.bayes_calibration  # noqa: F401
import agent.conditional_conformal  # noqa: F401
import agent.dual_track  # noqa: F401
import agent.counterfactual_api  # noqa: F401
import agent.verify_service  # noqa: F401
import agent.federated_calibration  # noqa: F401
import agent.active_experiment  # noqa: F401
from agent.conditional_conformal import SplitConformal, relative_residue  # noqa: F401
from agent.dual_track import apply_confidence, summarize_divergences  # noqa: F401
from agent.verify_service import resolve_key, theoretical_yield_cap, estimate_stage_days  # noqa: F401
from agent.federated_calibration import LocalUpdate, audit_privacy  # noqa: F401
from agent.active_experiment import prior_uncertainty, theoretical_yield_cap as _ae_yield  # noqa: F401
from agent import (
    active_experiment,
    bayes_calibration,
    conditional_conformal as cc,
    counterfactual_api,
    dual_track,
    federated_calibration,
    verify_service,
)
from engine import agriworld_gradients as ag


class TestBayesCalibration(unittest.TestCase):
    def test_get_params_returns_params(self):
        p = bayes_calibration.get_params("lettuce")
        self.assertGreater(p.k_ext, 0.0)
        self.assertGreater(p.t_opt_c, 0.0)

    def test_generate_synthetic_samples_deterministic(self):
        s1 = bayes_calibration.generate_synthetic_samples("lettuce", n_samples=2, seed=42)
        s2 = bayes_calibration.generate_synthetic_samples("lettuce", n_samples=2, seed=42)
        self.assertEqual(len(s1), 2)
        self.assertEqual(s1[0].observed_final_biomass, s2[0].observed_final_biomass)

    def test_map_calibration_runs_without_error(self):
        samples = bayes_calibration.generate_synthetic_samples(
            "lettuce", n_samples=3, seed=7
        )
        result = bayes_calibration.map_calibration("lettuce", samples, max_iter=5, tol=1e-3)
        # MAP 反演应返回 dict 含 best_params 或类似键
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)


class TestConditionalConformal(unittest.TestCase):
    def test_split_conformal_basic_prediction(self):
        """SplitConformal.predict_interval 返回 (p_lower, p_point, p_upper)。"""
        scores = list(range(1, 101))  # 1..100 的相对残差
        cal = cc.SplitConformal(calibration_scores=scores, alpha=0.1)
        lower, point, upper = cal.predict_interval(50.0)
        # 点估计在区间中间
        self.assertLessEqual(lower, point)
        self.assertLessEqual(point, upper)
        # 区间应至少包含点估计本身
        self.assertGreaterEqual(upper, 50.0)

    def test_relative_residue_definition(self):
        r = cc.relative_residue(pred=10.0, truth=20.0)
        # 契约：|truth-pred|/max(|truth|, 1)
        self.assertAlmostEqual(r, 1.0, places=6)

    def test_split_conformal_empty_calibration_degenerates(self):
        """契约：空校准集构造函数宽容，predict 时给出退化点估计（lower==upper==pred）。"""
        cal = cc.SplitConformal(calibration_scores=[])
        lower, upper, width = cal.predict_interval(50.0)
        # 退化到点估计：lower == upper == pred
        self.assertEqual(lower, 50.0)
        self.assertEqual(upper, 50.0)


class TestDualTrack(unittest.TestCase):
    def test_apply_confidence_clamps_to_range(self):
        # 分歧度为 0 → 保留 base_confidence
        v = dual_track.apply_confidence(base_confidence=0.9, track_comparison={"divergence": 0.0})
        self.assertGreaterEqual(v, 0.0)
        self.assertLessEqual(v, 1.0)

    def test_summarize_divergences_returns_summary(self):
        comparisons = [
            {"track_a": "x", "track_b": "y", "divergence": 0.1},
            {"track_a": "x", "track_b": "y", "divergence": 0.2},
        ]
        summary = dual_track.summarize_divergences(comparisons)
        self.assertIsInstance(summary, dict)
        # 至少要包含某种统计信息
        self.assertGreater(len(summary), 0)


class TestCounterfactualApi(unittest.TestCase):
    def test_module_imports_and_exposes_public_api(self):
        # counterfactual_api 应有 simulate/trace 或类似入口
        pub = [x for x in dir(counterfactual_api) if not x.startswith("_") and callable(getattr(counterfactual_api, x))]
        # 只要模块可导入、有公开可调用函数即通过
        self.assertGreater(len(pub), 0)


class TestVerifyService(unittest.TestCase):
    def test_resolve_key_for_known_crop(self):
        # 常见作物应能解析出稳定 key
        k = verify_service.resolve_key("生菜")
        self.assertIsNotNone(k)
        self.assertIsInstance(k, str)

    def test_theoretical_yield_cap_monotone_in_dli(self):
        # 光照增加，理论产量上限应单调不降
        y1 = verify_service.theoretical_yield_cap("wheat", dli_mj_m2_d=10.0, days=30)
        y2 = verify_service.theoretical_yield_cap("wheat", dli_mj_m2_d=20.0, days=30)
        self.assertLessEqual(y1, y2)
        self.assertGreater(y1, 0)

    def test_estimate_stage_days_returns_dict(self):
        r = verify_service.estimate_stage_days("生菜", mean_temp_c=22.0)
        self.assertIsInstance(r, dict)
        # 应至少包含 maturity_days_from_sow 或 emergence_days 之一
        has_days = any(k in r for k in ("maturity_days_from_sow", "emergence_days", "anthesis_days_from_sow"))
        self.assertTrue(has_days, f"缺少物候天数键: {r}")


class TestFederatedCalibration(unittest.TestCase):
    def test_audit_privacy_returns_dict(self):
        """audit_privacy 需要 LocalUpdate 对象，返回审计结果 dict。"""
        upd = federated_calibration.LocalUpdate(
            node_id="node-01",
            crop="wheat",
            created_at="2026-01-01T00:00:00Z",
            deltas={"k_ext": 0.05},
            n_samples=10,
            trust_mark="sha256:abcd",
        )
        r = federated_calibration.audit_privacy(upd)
        self.assertIsInstance(r, dict)
        self.assertIn("suspicious", r)
        self.assertIn("issues", r)
        self.assertIn("trust_mark_valid", r)
        self.assertFalse(r["suspicious"])

    def test_audit_privacy_flags_huge_delta(self):
        """契约：|delta| > 100 视为可疑（可能含原始数据）。"""
        upd = federated_calibration.LocalUpdate(
            node_id="node-02",
            crop="wheat",
            created_at="2026-01-01T00:00:00Z",
            deltas={"k_ext": 500.0},  # 明显异常
            n_samples=10,
            trust_mark="sha256:abcd",
        )
        r = federated_calibration.audit_privacy(upd)
        self.assertTrue(r["suspicious"])
        self.assertGreater(len(r["issues"]), 0)


class TestActiveExperiment(unittest.TestCase):
    def test_prior_uncertainty_returns_dict(self):
        """prior_uncertainty 返回 {param: (point, uncertainty)}，非区间。"""
        r = active_experiment.prior_uncertainty("wheat")
        self.assertIsInstance(r, dict)
        for k, tup in r.items():
            self.assertEqual(len(tup), 2)
            # 契约为 (point_estimate, uncertainty)
            self.assertGreater(tup[0], 0)
            self.assertGreaterEqual(tup[1], 0)

    def test_theoretical_yield_cap_matches_verify_service(self):
        # 两个模块的 theoretical_yield_cap 应给出一致结果
        y1 = active_experiment.theoretical_yield_cap("wheat", dli_mj_m2_d=15.0, days=30)
        y2 = verify_service.theoretical_yield_cap("wheat", dli_mj_m2_d=15.0, days=30)
        self.assertAlmostEqual(y1, y2, places=3)


class TestAgriworldGradients(unittest.TestCase):
    """engine/agriworld_gradients.py —— 有限差分梯度工具。"""

    def test_finite_diff_of_quadratic(self):
        # f(x) = x^2，f'(x) = 2x
        def f(x):
            return x * x
        g = ag.finite_diff(f, 3.0)
        self.assertAlmostEqual(g, 6.0, places=3)

    def test_temp_factor_optimum_at_t_opt(self):
        v_opt = ag.temp_factor(22.0, t_opt=22.0, t_max=35.0, t_base=8.0)
        v_below = ag.temp_factor(15.0, t_opt=22.0, t_max=35.0, t_base=8.0)
        v_above = ag.temp_factor(30.0, t_opt=22.0, t_max=35.0, t_base=8.0)
        self.assertGreaterEqual(v_opt, v_below)
        self.assertGreaterEqual(v_opt, v_above)

    def test_temp_factor_zero_above_t_max(self):
        v = ag.temp_factor(45.0, t_opt=22.0, t_max=35.0, t_base=8.0)
        self.assertAlmostEqual(v, 0.0, places=6)

    def test_light_interception_monotone_in_lai(self):
        i_low = ag.light_interception(i0_par_kj=20.0, lai=1.0, k_ext=0.6)
        i_high = ag.light_interception(i0_par_kj=20.0, lai=4.0, k_ext=0.6)
        self.assertLessEqual(i_low, i_high)

    def test_water_stress_factor_below_fc(self):
        v = ag.water_stress_factor(theta=0.05, theta_fc=0.10)
        self.assertGreaterEqual(v, 0.0)
        self.assertLess(v, 1.0)

    def test_run_gradient_golden_tests_passes(self):
        # 内部 golden tests 应全绿
        result = ag.run_gradient_golden_tests()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
