#!/usr/bin/env python3
"""
智慧农业生态 · P0 气候数据接地单测（仅标准库 unittest，零第三方依赖）

覆盖（docs/data_acquisition_decision.md P0）：
  - fetch_monthly_climate：非法坐标拒绝、缓存命中免联网、provenance 结构完整
  - _aggregate_power_monthly：NASA POWER YYYYMM 键聚合正确
  - SeasonAgent._planting_window：给 lat/lon 时自动抓取（mock 源），响应带 climate_provenance
  - 真实联网用例（AGRI_LIVE_TEST=1 时跑，CI 默认跳过）

运行：
    python -m unittest scripts.test_climate_data -v
"""
import os
import sys
import json
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import climate_data as cd  # noqa: E402
from agent.season_agent import SeasonAgent  # noqa: E402

LIVE = os.environ.get("AGRI_LIVE_TEST") == "1"


class TestAggregation(unittest.TestCase):
    def test_power_monthly_aggregation(self):
        raw = {f"2020{m:02d}": float(m) for m in range(1, 13)}
        raw.update({f"2021{m:02d}": float(m) + 1 for m in range(1, 13)})
        out = cd._aggregate_power_monthly(raw)
        self.assertEqual(len(out), 12)
        # 1月: (1+2)/2 = 1.5
        self.assertAlmostEqual(out[0], 1.5, places=2)
        self.assertAlmostEqual(out[11], 12.5, places=2)

    def test_power_monthly_missing_month(self):
        raw = {"202001": 5.0, "202003": 7.0}  # 2 月缺失
        out = cd._aggregate_power_monthly(raw)
        self.assertEqual(len(out), 12)
        self.assertIsNone(out[1])
        self.assertAlmostEqual(out[0], 5.0, places=2)


class TestFetchOffline(unittest.TestCase):
    def test_invalid_coords_rejected(self):
        r = cd.fetch_monthly_climate(999, 999)
        self.assertIn("error", r)
        self.assertIsNone(r.get("monthly_mean_c"))

    def test_cache_hit_avoids_network(self):
        # 预热缓存（用 mock 源写一条）
        fake = {
            "monthly_mean_c": [10] * 12, "monthly_precip_mm": [1] * 12,
            "monthly_rh_pct": [70] * 12, "monthly_srad_kwh_m2_day": None,
            "source": "MOCK", "license": "mock", "url": "mock://x",
            "accessed_at": "2026-01-01T00:00:00Z", "lat": 12.34, "lon": 56.78,
            "years_used": [2020, 2024], "provenance": {"source": "MOCK"},
        }
        cd._write_cache(12.34, 56.78, cd.DEFAULT_CACHE_DIR, fake)
        r = cd.fetch_monthly_climate(12.34, 56.78, force_refresh=False)
        self.assertTrue(r.get("cached"))
        self.assertEqual(r["source"], "MOCK")
        self.assertEqual(r["monthly_mean_c"], [10] * 12)

    def test_provenance_structure(self):
        fake = {
            "monthly_mean_c": [10] * 12, "monthly_precip_mm": [1] * 12,
            "monthly_rh_pct": [70] * 12, "monthly_srad_kwh_m2_day": None,
            "source": "MOCK", "license": "mock", "url": "mock://x",
            "accessed_at": "2026-01-01T00:00:00Z", "lat": 1.0, "lon": 2.0,
            "years_used": [2020, 2024], "provenance": {
                "source": "MOCK", "url": "mock://x", "license": "mock",
                "accessed_at": "2026-01-01T00:00:00Z", "note": "x"},
        }
        cd._write_cache(1.0, 2.0, cd.DEFAULT_CACHE_DIR, fake)
        r = cd.fetch_monthly_climate(1.0, 2.0)
        prov = r["provenance"]
        for k in ("source", "url", "license", "accessed_at", "note"):
            self.assertIn(k, prov)


class TestSeasonAutoFetch(unittest.TestCase):
    def test_planting_window_autofetch_wires_provenance(self):
        # 用 mock 源替换真实联网，验证 lat/lon -> 自动抓取 -> provenance 透传。
        # 关键：把缓存目录重定向到临时空目录，避免磁盘上已有的 30.27_120.15.json
        # （Open-Meteo 缓存）让 fetch_monthly_climate 直接命中缓存、绕过 mock，
        # 导致断言 climate_provenance.source == "NASA POWER" 非确定性失败。
        orig_power = cd._fetch_power
        orig_om = cd._fetch_open_meteo
        orig_cache_dir = cd.DEFAULT_CACHE_DIR
        tmp_cache = tempfile.mkdtemp(prefix="agri_climcache_")
        cd._fetch_power = lambda *a, **k: {
            "monthly_mean_c": [4, 6, 12, 16, 21, 25, 29, 29, 25, 18, 13, 5],
            "monthly_precip_mm": [2] * 12, "monthly_rh_pct": [75] * 12,
            "monthly_srad_kwh_m2_day": None,
            "source": "NASA POWER", "license": "public domain", "url": "http://power",
        }
        cd.DEFAULT_CACHE_DIR = tmp_cache
        try:
            a = SeasonAgent()
            r = a.run({"mode": "planting_window", "lat": 30.27, "lon": 120.15,
                       "crops": ["马铃薯", "番茄"]})
            self.assertTrue(r["available"], r.get("error"))
            self.assertEqual(r["climate_input"], "auto_fetched_from_latlon")
            self.assertEqual(r["climate_provenance"]["source"], "NASA POWER")
            self.assertIn("windows", r)
        finally:
            cd._fetch_power = orig_power
            cd._fetch_open_meteo = orig_om
            cd.DEFAULT_CACHE_DIR = orig_cache_dir
            shutil.rmtree(tmp_cache, ignore_errors=True)

    def test_planting_window_requires_input_without_latlon(self):
        a = SeasonAgent()
        r = a.run({"mode": "planting_window", "crops": ["马铃薯"]})
        self.assertFalse(r["available"])
        self.assertIn("monthly_mean_c", r["error"])


class TestZoneBaseline(unittest.TestCase):
    """P1：6 分区气候基线离线固化（docs/data_acquisition_decision.md）。"""

    ZONE_IDS = ["tropical_rainforest", "mediterranean", "arid",
                "temperate_continental", "subtropical_wet", "subarctic"]

    def test_all_six_zones_solidified(self):
        for zid in self.ZONE_IDS:
            base = cd.get_zone_climate_baseline(zid)
            self.assertIsNotNone(base, f"{zid} 未固化 climate_baseline")
            self.assertEqual(len(base.get("monthly_mean_c") or []), 12,
                             f"{zid} 月均温序列不完整")
            for k in ("source", "license", "accessed_at", "centroid_lat", "centroid_lon"):
                self.assertIn(k, base, f"{zid} baseline 缺 {k}")
            self.assertIn(base["source"], ("NASA POWER", "Open-Meteo"))

    def test_baseline_distinct_across_zones(self):
        # 热带雨林与亚寒带年均温应明显不同（证明是真·分区抓取，非复制）
        tropic = cd.get_zone_climate_baseline("tropical_rainforest")["monthly_mean_c"]
        sub = cd.get_zone_climate_baseline("subarctic")["monthly_mean_c"]
        self.assertGreater(sum(tropic) / 12, sum(sub) / 12 + 15)


class TestLatinVerify(unittest.TestCase):
    """P2：GBIF 校验 110 作物拉丁名（docs/data_acquisition_decision.md）。"""

    CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

    def _crops(self):
        with open(self.CROP_DB, encoding="utf-8") as f:
            data = json.load(f)
        return [c for z in data.get("zones", {}).values() for c in z.get("crops", [])]

    def test_every_crop_has_verification_field(self):
        crops = self._crops()
        self.assertTrue(crops)
        for c in crops:
            self.assertIn("latin_verified", c, f"{c.get('crop')} 缺 latin_verified")

    def test_verified_count_reasonable(self):
        # 不应出现「全 False」（说明 GBIF 全失败 / 脚本未跑）
        crops = self._crops()
        verified = sum(1 for c in crops if c.get("latin_verified"))
        self.assertGreater(verified, 0, "没有任何作物通过 GBIF 校验，疑似脚本未执行")
        # 接受名不应与手写 latin 大面积为空
        with_accepted = sum(1 for c in crops if c.get("latin_verified") and c.get("gbif_accepted_name"))
        self.assertEqual(with_accepted, verified)


class TestNicheEnvelope(unittest.TestCase):
    """P3：生态位包络反推校准 adapt_score（docs/data_acquisition_decision.md）。"""

    CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

    def _crops(self):
        with open(self.CROP_DB, encoding="utf-8") as f:
            data = json.load(f)
        return [c for z in data.get("zones", {}).values() for c in z.get("crops", [])]

    def test_niche_calibration_applied(self):
        crops = self._crops()
        calibrated = [c for c in crops if c.get("calibrated") and c.get("calibration_method") == "niche_envelope"]
        if not calibrated:
            self.skipTest("P3 脚本尚未运行（niche_envelope 校准为 0）")
        for c in calibrated[:5]:
            prov = c.get("calibration_provenance") or {}
            self.assertIn("gbif_occurrence_points", prov)
            self.assertIn("climate_samples", prov)
            self.assertIn("sources", prov)
            self.assertTrue(0 <= c["adapt_score"] <= 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPrecipUnitsContract(unittest.TestCase):
    """降水口径契约（2026-09-23 核实并固化）。

    `monthly_precip_mm` 的元素单位是 **mm/day**（月内日均降水），不是月累计。
    两个源同口径：NASA POWER 月度接口的 PRECTOTCORR 聚合即日均值（实测杭州
    [2,2,...]、12 个月合计 24，真实月累计约 120mm）；Open-Meteo 走日值再按月
    取均值。两者一致很重要——niche_envelope_calibrate.score_zone 的降水通道
    （权重 0.4）是拿作物包络与分区基线做同口径区间命中比较。

    本类锁死这条口径，防止将来有人「顺手」乘天数改成月累计：那会把 107 个已固化
    adapt_score 整体改写，harness 数据基线与测试基线同时失效。
    """

    def test_units_constant_is_mm_per_day(self):
        self.assertEqual(cd.PRECIP_UNITS, "mm/day")

    def test_both_fetch_paths_emit_units(self):
        orig_power, orig_om = cd._fetch_power, cd._fetch_open_meteo
        cd._fetch_power = lambda *a, **k: {
            "monthly_mean_c": [4, 6, 12, 16, 21, 25, 29, 29, 25, 18, 13, 5],
            "monthly_precip_mm": [2.0] * 12, "monthly_precip_mm_units": cd.PRECIP_UNITS,
            "monthly_rh_pct": [75] * 12, "monthly_srad_kwh_m2_day": None,
            "source": "NASA POWER", "license": "public domain", "url": "http://power",
            "accessed_at": "2026-01-01T00:00:00Z", "lat": 30.27, "lon": 120.15,
            "years_used": [2020, 2024], "provenance": {"source": "NASA POWER"},
        }
        cd._fetch_open_meteo = lambda *a, **k: {
            "monthly_mean_c": [4, 6, 12, 16, 21, 25, 29, 29, 25, 18, 13, 5],
            "monthly_precip_mm": [1.8] * 12, "monthly_precip_mm_units": cd.PRECIP_UNITS,
            "monthly_rh_pct": [75] * 12, "monthly_srad_kwh_m2_day": None,
            "source": "Open-Meteo", "license": "cc", "url": "http://om",
            "accessed_at": "2026-01-01T00:00:00Z", "lat": 30.27, "lon": 120.15,
            "years_used": [2020, 2024], "provenance": {"source": "Open-Meteo"},
        }
        try:
            for prefer in ("power", "open_meteo"):
                r = cd.fetch_monthly_climate(30.27, 120.15, prefer=prefer,
                                             force_refresh=True)
                self.assertNotIn("error", r, r.get("error"))
                self.assertEqual(r["monthly_precip_mm_units"], cd.PRECIP_UNITS,
                                 f"prefer={prefer} 未透传单位口径")
        finally:
            cd._fetch_power, cd._fetch_open_meteo = orig_power, orig_om

    def test_cache_normalization_backfills_units(self):
        """老缓存写于口径标注之前，读回时必须补齐 units 字段（不静默缺失）。"""
        fake = {
            "monthly_mean_c": [10] * 12, "monthly_precip_mm": [1] * 12,
            "monthly_rh_pct": [70] * 12, "monthly_srad_kwh_m2_day": None,
            "source": "MOCK", "license": "mock", "url": "mock://x",
            "accessed_at": "2026-01-01T00:00:00Z", "lat": 33.33, "lon": 55.55,
            "years_used": [2020, 2024], "provenance": {"source": "MOCK"},
        }
        cd._write_cache(33.33, 55.55, cd.DEFAULT_CACHE_DIR, fake)
        r = cd.fetch_monthly_climate(33.33, 55.55)
        self.assertTrue(r.get("cached"))
        self.assertEqual(r.get("monthly_precip_mm_units"), cd.PRECIP_UNITS)

    def test_zone_baseline_carries_units(self):
        """离线固化的分区基线同样必须带口径字段（与实时数据同构）。"""
        for zid in ("subtropical_wet", "arid", "subarctic"):
            base = cd.get_zone_climate_baseline(zid)
            self.assertIsNotNone(base, f"{zid} 未固化")
            self.assertEqual(base.get("monthly_precip_mm_units"), cd.PRECIP_UNITS,
                             f"{zid} 基线缺单位口径字段")

    def test_no_day_scaling_in_calibration(self):
        """回归守卫：校准脚本不得对降水乘天数（那会把 mm/日改成 mm/月）。"""
        cal = os.path.join(ROOT, "scripts", "niche_envelope_calibrate.py")
        with open(cal, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("* 30", src, "校准脚本疑似把月日均降水乘天数改成月累计")
        self.assertNotIn("* 31", src, "校准脚本疑似把月日均降水乘天数改成月累计")
        # 降水通道必须是「同口径区间命中」，不得对某一侧做单位换算
        self.assertIn("precip_env", src)
        self.assertIn("bprec", src)


@unittest.skipUnless(LIVE, "set AGRI_LIVE_TEST=1 to hit real NASA POWER / Open-Meteo")
class TestFetchLive(unittest.TestCase):
    def test_live_hangzhou(self):
        r = cd.fetch_monthly_climate(30.2741, 120.1551, years=5, force_refresh=True)
        self.assertNotIn("error", r)
        self.assertEqual(len(r["monthly_mean_c"]), 12)
        self.assertIn(r["source"], ("NASA POWER", "Open-Meteo"))
        self.assertIn("provenance", r)

    def test_live_season_autofetch(self):
        a = SeasonAgent()
        r = a.run({"mode": "planting_window", "lat": 30.2741, "lon": 120.1551,
                   "crops": ["马铃薯"]})
        self.assertTrue(r["available"], r.get("error"))
        self.assertEqual(r["climate_input"], "auto_fetched_from_latlon")


if __name__ == "__main__":
    unittest.main(verbosity=2)
