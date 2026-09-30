#!/usr/bin/env python3
"""
智慧农业生态 · 多源气候校准单元测试（仅标准库 unittest，零第三方依赖）

覆盖 core/climate_reconcile.reconcile_climate：
  - 双源可用 → 调和基线=两源逐月均值、一致度=标准差、provenance_complete=true
  - 双源分歧超阈 → disagreement_months 标记对应月份
  - 单源可用 → 不交叉验证（provenance_complete=false，reconciled=该源原值）
  - 全源失败 → reconciled=null + error，绝不编造
  - worldclim 列为扩展点（available=false + 明确注释）

mock 取代真实联网（与 test_climate_data 同源思路），断言真实业务值而非"有字段"。
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from agent import climate_data as cd  # noqa: E402
from core.climate_reconcile import reconcile_climate  # noqa: E402

POWER = [4.0, 6.0, 12.0, 16.0, 21.0, 25.0, 29.0, 29.0, 25.0, 18.0, 13.0, 5.0]
OPEN = [5.0, 7.0, 13.0, 17.0, 22.0, 26.0, 30.0, 30.0, 26.0, 19.0, 14.0, 6.0]


def _mk(source: str, series):
    return {
        "monthly_mean_c": list(series),
        "monthly_precip_mm": [2] * 12,
        "monthly_rh_pct": [75] * 12,
        "monthly_srad_kwh_m2_day": None,
        "source": source, "license": "test", "url": "http://test",
        "accessed_at": "2026-09-26T00:00:00Z", "provenance": {},
    }


class ReconcileTwoSources(unittest.TestCase):
    def setUp(self):
        self.orig_p = cd._fetch_power
        self.orig_o = cd._fetch_open_meteo
        cd._fetch_power = lambda *a, **k: _mk("NASA POWER", POWER)
        cd._fetch_open_meteo = lambda *a, **k: _mk("Open-Meteo", OPEN)

    def tearDown(self):
        cd._fetch_power = self.orig_p
        cd._fetch_open_meteo = self.orig_o

    def test_reconciled_is_two_source_mean(self):
        r = reconcile_climate(30.27, 120.15)
        self.assertEqual(r["n_sources"], 2)
        self.assertTrue(r["provenance_complete"])
        self.assertEqual(len(r["reconciled"]), 12)
        for i in range(12):
            self.assertAlmostEqual(r["reconciled"][i], (POWER[i] + OPEN[i]) / 2, places=1)

    def test_agreement_per_month(self):
        r = reconcile_climate(30.27, 120.15)
        self.assertEqual(len(r["agreement"]), 12)
        # 两源逐月差 1℃ → 总体标准差 ~0.5
        for sd in r["agreement"]:
            self.assertAlmostEqual(sd, 0.5, places=1)

    def test_no_false_disagreement(self):
        r = reconcile_climate(30.27, 120.15)
        self.assertEqual(r["disagreement_months"], [],
                         "两源一致时不应有任何分歧标记")


class ReconcileDisagreement(unittest.TestCase):
    def setUp(self):
        self.orig_p = cd._fetch_power
        self.orig_o = cd._fetch_open_meteo
        cd._fetch_power = lambda *a, **k: _mk("NASA POWER", POWER)
        # 7 月（index 6）严重偏离
        divergent = list(OPEN)
        divergent[6] = 50.0
        cd._fetch_open_meteo = lambda *a, **k: _mk("Open-Meteo", divergent)

    def tearDown(self):
        cd._fetch_power = self.orig_p
        cd._fetch_open_meteo = self.orig_o

    def test_disagreement_flagged(self):
        r = reconcile_climate(30.27, 120.15)
        months = [d["month"] for d in r["disagreement_months"]]
        self.assertIn(7, months)
        hit = [d for d in r["disagreement_months"] if d["month"] == 7][0]
        self.assertGreater(hit["std_c"], 3.0)


class ReconcileSingleAndFail(unittest.TestCase):
    def setUp(self):
        self.orig_p = cd._fetch_power
        self.orig_o = cd._fetch_open_meteo

    def tearDown(self):
        cd._fetch_power = self.orig_p
        cd._fetch_open_meteo = self.orig_o

    def test_single_source_no_cross_check(self):
        cd._fetch_power = lambda *a, **k: _mk("NASA POWER", POWER)
        cd._fetch_open_meteo = lambda *a, **k: None  # 失败
        r = reconcile_climate(30.27, 120.15, sources=("power", "open_meteo"))
        self.assertEqual(r["n_sources"], 1)
        self.assertFalse(r["provenance_complete"])
        self.assertEqual(r["reconciled"], POWER)
        self.assertIn("note", r)

    def test_all_fail_no_fabrication(self):
        cd._fetch_power = lambda *a, **k: None
        cd._fetch_open_meteo = lambda *a, **k: None
        r = reconcile_climate(30.27, 120.15)
        self.assertEqual(r["n_sources"], 0)
        self.assertIsNone(r["reconciled"])
        self.assertFalse(r["provenance_complete"])
        self.assertIn("error", r)

    def test_worldclim_is_extension_point(self):
        # 仅 worldclim：应标注为扩展点，不产生编造值
        r = reconcile_climate(30.27, 120.15, sources=("worldclim",))
        self.assertEqual(r["n_sources"], 0)
        self.assertIsNone(r["reconciled"])
        self.assertTrue(any(s["id"] == "worldclim" and not s["available"]
                            and "扩展点" in (s.get("error") or "")
                            for s in r["sources"]))


class ReconcileBiasCorrection(unittest.TestCase):
    """偏差校正（v2 硬骨头改进）——多源系统偏差估计与校正。

    动机：NASA POWER 0.5° 分辨率在数据稀缺区（高原/热漠）存在系统性偏差
    （Verpeta et al. 2025, Ravindu & Dias 2025），纯算术平均会保留偏差。
    """

    def setUp(self):
        self.orig_p = cd._fetch_power
        self.orig_o = cd._fetch_open_meteo
        cd._fetch_power = lambda *a, **k: _mk("NASA POWER", POWER)
        cd._fetch_open_meteo = lambda *a, **k: _mk("Open-Meteo", OPEN)

    def tearDown(self):
        cd._fetch_power = self.orig_p
        cd._fetch_open_meteo = self.orig_o

    def test_bias_correction_produces_all_fields(self):
        """双源可用 + bias_corrected=True → 所有校正字段齐全且结构完整。"""
        r = reconcile_climate(30.27, 120.15, bias_corrected=True)
        self.assertTrue(r["bias_corrected"])
        # source_biases 每源结构
        for sid, b in r["source_biases"].items():
            self.assertEqual(len(b["monthly_bias_c"]), 12)
            self.assertIn("mean_bias_c", b)
            self.assertIn("std_bias_c", b)
            self.assertEqual(b["reference"], "multi-source median per month")
        # corrected_mean 长度 12
        self.assertEqual(len(r["corrected_mean"]), 12)
        # 校正幅度是标量
        self.assertIsInstance(r["correction_magnitude_c"], (int, float))
        self.assertGreaterEqual(r["correction_magnitude_c"], 0.0)

    def test_two_source_bias_sums_to_zero(self):
        """两源相对中位数偏差应互抵（中位数 = 均值 for n=2，偏差和为 0）。

        这是数学恒等式，用来验证偏差估计的一致性——即使系统偏差真实存在，
        两源相对中位数取差后仍应满足 Σbias = 0。
        """
        r = reconcile_climate(30.27, 120.15)
        for m in range(12):
            b1 = r["source_biases"]["power"]["monthly_bias_c"][m]
            b2 = r["source_biases"]["open_meteo"]["monthly_bias_c"][m]
            self.assertAlmostEqual(b1 + b2, 0.0, places=1,
                                   msg="两源相对中位数偏差每月应互抵")

    def test_open_meteo_bias_is_positive_for_power_minus_one(self):
        """本测试数据 OPEN = POWER + 1 → Open-Meteo 系统偏高 1℃，POWER 偏低 1℃。

        偏差估计应正确捕捉到这个系统偏移，验证方法是：
        两源相对中位数偏差，Open-Meteo 均值 ≈ +0.5，POWER 均值 ≈ -0.5。
        """
        r = reconcile_climate(30.27, 120.15)
        b_open = r["source_biases"]["open_meteo"]["mean_bias_c"]
        b_power = r["source_biases"]["power"]["mean_bias_c"]
        # 两源差 1℃ → 中位数 = 均值 = POWER + 0.5
        # Open-Meteo - 中位数 = (POWER + 1) - (POWER + 0.5) = +0.5
        # POWER - 中位数 = POWER - (POWER + 0.5) = -0.5
        self.assertAlmostEqual(b_open, 0.5, places=1,
                               msg="Open-Meteo 应偏高约 0.5℃")
        self.assertAlmostEqual(b_power, -0.5, places=1,
                               msg="POWER 应偏低约 0.5℃")

    def test_bias_correction_disabled_preserves_v1_contract(self):
        """bias_corrected=False → 保持 v1 行为（回归兼容），无校正字段。"""
        r = reconcile_climate(30.27, 120.15, bias_corrected=False)
        self.assertFalse(r["bias_corrected"])
        self.assertNotIn("source_biases", r)
        self.assertNotIn("corrected_mean", r)
        self.assertNotIn("correction_magnitude_c", r)
        # 但 v1 原有字段保留
        self.assertEqual(r["n_sources"], 2)
        self.assertEqual(len(r["reconciled"]), 12)
        self.assertEqual(len(r["agreement"]), 12)

    def test_single_source_skips_bias_correction(self):
        """单源可用时不产生偏差校正（数学上无意义），只给 note 说明。"""
        cd._fetch_open_meteo = lambda *a, **k: None
        r = reconcile_climate(30.27, 120.15)
        self.assertEqual(r["n_sources"], 1)
        self.assertFalse(r["bias_corrected"])
        self.assertNotIn("source_biases", r)
        self.assertNotIn("corrected_mean", r)
        self.assertIn("偏差校正跳过", r.get("note", ""))

    def test_zero_bias_both_sources_identical(self):
        """两源完全一致 → 各源偏差 ≈ 0，校正幅度 ≈ 0。"""
        cd._fetch_open_meteo = lambda *a, **k: _mk("Open-Meteo", list(POWER))
        r = reconcile_climate(30.27, 120.15)
        self.assertTrue(r["bias_corrected"])
        for sid, b in r["source_biases"].items():
            self.assertAlmostEqual(b["mean_bias_c"], 0.0, places=1)
            self.assertAlmostEqual(b["std_bias_c"], 0.0, places=1)
        self.assertAlmostEqual(r["correction_magnitude_c"], 0.0, places=1)

    def test_corrected_mean_finite_and_valid_range(self):
        """校正后调和值必须是有限浮点数，且在合理气候温度范围 [-40, +50]℃ 内。"""
        r = reconcile_climate(30.27, 120.15)
        for v in r["corrected_mean"]:
            self.assertGreaterEqual(v, -40.0)
            self.assertLessEqual(v, 50.0)
            # 排除 NaN/Inf
            self.assertEqual(v, v)  # NaN != NaN
            self.assertNotIn(v, (float("inf"), float("-inf")))


if __name__ == "__main__":
    unittest.main()
