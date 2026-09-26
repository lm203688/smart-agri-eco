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


if __name__ == "__main__":
    unittest.main()
