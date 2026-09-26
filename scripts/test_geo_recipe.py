#!/usr/bin/env python3
"""
智慧农业生态 · 地理编码→配方 单元测试（仅标准库 unittest，零第三方依赖，完全离线）

覆盖 core/geo_recipe.resolve：
  - 城市名 → 坐标解析 → 分区 → 配方清单
  - 经纬度直输 → 分区
  - 未知城市 → resolved=false + error（不编造坐标）
  - 未建模气候类（迪拜=hot_arid）→ zone_modeled=false + 显式 note
  - 配方检索命名一致性：data/env_recipes/<zone>__*.json
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from core.geo_recipe import resolve  # noqa: E402


class ResolveCity(unittest.TestCase):
    def test_city_name_hangzhou(self):
        r = resolve(query="杭州")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["zone_id"], "subtropical_wet")
        self.assertIsNotNone(r["zone_name"])
        self.assertGreaterEqual(r["recipe_count"], 0)

    def test_city_recipes_named_correctly(self):
        r = resolve(query="杭州")
        for rec in r["recipes"]:
            base = os.path.basename(rec["path"])
            self.assertTrue(
                base.startswith("subtropical_wet__"),
                "配方文件名应以 <zone>__ 前缀：%s" % rec["path"])

    def test_latlon_direct(self):
        r = resolve(lat=30.27, lon=120.15)
        self.assertTrue(r["resolved"])
        self.assertEqual(r["zone_id"], "subtropical_wet")

    def test_latlon_string(self):
        r = resolve(query="30.27,120.15")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["zone_id"], "subtropical_wet")


class ResolveFailures(unittest.TestCase):
    def test_unknown_city(self):
        r = resolve(query="不存在的城市XYZ")
        self.assertFalse(r["resolved"])
        self.assertIn("error", r)

    def test_missing_input(self):
        r = resolve()
        self.assertFalse(r["resolved"])
        self.assertIn("error", r)

    def test_unmodeled_zone_flagged(self):
        # 迪拜 25.20N/55.27E → hot_arid（已知未建模）
        r = resolve(lat=25.20, lon=55.27)
        self.assertTrue(r["resolved"])
        self.assertEqual(r["zone_id"], "hot_arid")
        self.assertFalse(r["zone_modeled"])
        self.assertIsNotNone(r["note"])
        self.assertEqual(r["recipe_count"], 0)


if __name__ == "__main__":
    unittest.main()
