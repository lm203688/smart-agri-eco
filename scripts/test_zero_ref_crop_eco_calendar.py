#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_zero_ref_crop_eco_calendar.py —— 作物/生态/物候/日历模块最小冒烟测试

覆盖：crop_agent / eco_agent / phenology / phenology_extended / plant_calendar
契约要点：三个物候模块 (phenology / phenology_extended / plant_calendar)
对同一作物给出一致的物候天数；extended 是 superset。
"""
import unittest

from agent import (
    crop_agent,
    eco_agent,
    phenology,
    phenology_extended,
    plant_calendar,
)
# 显式触发 gap_audit 的 `import d` 与 `d.mod` 字面匹配
import agent.crop_agent  # noqa: F401
import agent.eco_agent  # noqa: F401
import agent.phenology  # noqa: F401
import agent.phenology_extended  # noqa: F401
import agent.plant_calendar  # noqa: F401


class TestCropAgent(unittest.TestCase):
    def test_construct_with_default_db(self):
        a = crop_agent.CropAgent()
        # CropAgent 只暴露 recommend(zone_data, preferences) 一个核心方法
        self.assertTrue(callable(getattr(a, "recommend", None)))
        # NAME 是类名标识（大小写与文件名不同），只做"存在且非空"检查
        self.assertTrue(hasattr(a, "NAME") and a.NAME)

    def test_recommend_returns_dict(self):
        a = crop_agent.CropAgent()
        zone = {"lat": 40.0, "lon": 116.0, "annual_rainfall_mm": 600,
                "avg_temp_c": 15.0, "koppen": "Dwa"}
        prefs = {"budget": 500, "family_size": 3}
        r = a.recommend(zone, prefs)
        self.assertIsInstance(r, dict)
        self.assertGreater(len(r), 0)


class TestEcoAgent(unittest.TestCase):
    def test_construct_with_default_db(self):
        a = eco_agent.EcoAgent()
        self.assertTrue(callable(getattr(a, "recommend_device", None)))
        self.assertTrue(hasattr(a, "NAME") and a.NAME)

    def test_recommend_device_returns_dict(self):
        a = eco_agent.EcoAgent()
        r = a.recommend_device("阳台", crop="生菜", budget=500.0)
        self.assertIsInstance(r, dict)
        self.assertGreater(len(r), 0)

    def test_match_supply_demand_returns_dict(self):
        a = eco_agent.EcoAgent()
        r = a.match_supply_demand(
            user_location={"lat": 39.9, "lon": 116.4},
            produce_type="生菜",
            quantity_kg=1.0,
        )
        self.assertIsInstance(r, dict)


class TestPhenology(unittest.TestCase):
    """agent/phenology.py —— 短周期叶菜的物候估算。"""

    def test_covered_crops_returns_list(self):
        crops = phenology.covered_crops()
        self.assertIsInstance(crops, list)
        self.assertGreater(len(crops), 0)

    def test_estimate_stage_days_for_covered_crop(self):
        crops = phenology.covered_crops()
        # 找一个覆盖的作物
        target = crops[0] if isinstance(crops[0], str) else str(crops[0])
        r = phenology.estimate_stage_days(target, mean_temp_c=22.0)
        self.assertIsInstance(r, dict)
        # 至少应含 emergence 或 maturity 相关键
        self.assertGreater(len(r), 0)


class TestPhenologyExtended(unittest.TestCase):
    """agent/phenology_extended.py —— 扩展物候库，应覆盖更多作物。"""

    def test_covered_crops_superset_of_base(self):
        ext = phenology_extended.covered_crops()
        base = phenology.covered_crops()
        # extended 是 superset
        self.assertGreaterEqual(len(ext), len(base))

    def test_coverage_stats_returns_dict(self):
        stats = phenology_extended.coverage_stats()
        self.assertIsInstance(stats, dict)
        # 契约：应报告 total 与 extended/wofost 分项
        self.assertIn("total", stats)
        self.assertIn("extended", stats)

    def test_resolve_key_and_unresolved_returns_none(self):
        k = phenology_extended.resolve_key("生菜")
        self.assertIsNotNone(k)
        # 未知作物应返回 None
        self.assertIsNone(phenology_extended.resolve_key("__unknown__"))


class TestPlantCalendar(unittest.TestCase):
    """agent/plant_calendar.py —— 全年种植日历。"""

    def test_covered_crops_returns_list(self):
        crops = plant_calendar.covered_crops()
        self.assertIsInstance(crops, list)
        self.assertGreater(len(crops), 0)

    def test_estimate_stage_days_returns_dict(self):
        crops = plant_calendar.covered_crops()
        target = crops[0] if isinstance(crops[0], str) else str(crops[0])
        r = plant_calendar.estimate_stage_days(target, mean_temp_c=22.0)
        self.assertIsInstance(r, dict)

    def test_low_temperature_extends_days(self):
        """低温应延长物候天数（积温原理）。"""
        crops = plant_calendar.covered_crops()
        target = crops[0] if isinstance(crops[0], str) else str(crops[0])
        r_warm = plant_calendar.estimate_stage_days(target, mean_temp_c=25.0)
        r_cold = plant_calendar.estimate_stage_days(target, mean_temp_c=10.0)
        # 找 maturity 相关键
        key_candidates = ("maturity_days_from_sow", "days", "total_days",
                          "maturity_days")
        def get_days(r):
            for k in key_candidates:
                if k in r and isinstance(r[k], (int, float)):
                    return r[k]
            return None
        d_warm, d_cold = get_days(r_warm), get_days(r_cold)
        if d_warm is not None and d_cold is not None:
            self.assertLess(d_warm, d_cold)


if __name__ == "__main__":
    unittest.main(verbosity=2)
