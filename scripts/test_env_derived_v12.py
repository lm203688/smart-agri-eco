#!/usr/bin/env python3
"""scripts/test_env_derived_v12.py —— Env Recipe v1.2 派生量（DLI / 播种深度）回归。

锁住三个性质（对齐项目铁律「派生量不落盘 / 不编造」）：

1. **DLI 从分区级输入数据推导**：`derive_dli(zone_id)` 读 global_zones.json 的
   climate_baseline.dli_annual_mol_m2_day，8 个 zone 全部可推导，且值非负。
2. **未知分区/缺数据不编造**：未知 zone_id 与无 DLI 的分区返回 available=False。
3. **播种深度复用既有公式**：sowing_depth_cm(growth_days) = max(0.1, round(gd/200,1))，
   与 agent/growth_agent.py 的 "覆土 {round(gd/200,1)} cm" 一致；缺失返回 None。
4. **派生量不写回配方**：调用后配方 JSON 不应出现 dli / sowing_depth 键。

运行：
    python -S -P -m unittest discover -s scripts -p "test_env_derived_v12.py" -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import derived as dv  # noqa: E402

ZONE_META = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")


class TestDliDerive(unittest.TestCase):
    def test_all_8_zones_have_dli(self):
        """8 个分区 DLI 全部可推导（NASA POWER 已回填到 climate_baseline）。"""
        meta = json.load(open(ZONE_META, encoding="utf-8"))
        zones = [z["zone_id"] for z in meta["zones"]]
        self.assertEqual(len(zones), 8)
        for zid in zones:
            d = dv.derive_dli(zid)
            self.assertTrue(d["available"], "%s 应可推导 DLI" % zid)
            self.assertIsInstance(d["mol_m2_day"], float)
            self.assertGreater(d["mol_m2_day"], 0.0, "%s DLI 应为正" % zid)

    def test_dli_values_physically_reasonable(self):
        """全谱短波辐射光子当量的合理区间：热带 > 亚寒带；均 < 150 mol/m²/day。"""
        v_tr = dv.derive_dli("tropical_rainforest")["mol_m2_day"]
        v_sa = dv.derive_dli("subarctic")["mol_m2_day"]
        v_ha = dv.derive_dli("hot_arid")["mol_m2_day"]
        self.assertGreater(v_tr, v_sa, "热带 DLI 应高于亚寒带")
        self.assertGreater(v_ha, v_tr, "热漠 DLI 应高于热带（更少云）")
        for v in (v_tr, v_sa, v_ha):
            self.assertLess(v, 150.0, "全谱光子当量不应超过 150 mol/m²/day")

    def test_unknown_zone_does_not_fabricate(self):
        d = dv.derive_dli("不存在的分区")
        self.assertFalse(d["available"])
        self.assertIsNone(d["mol_m2_day"])
        self.assertIn("未知分区", d["note"])

    def test_source_license_is_explicit(self):
        d = dv.derive_dli("arid")
        src = d["source"] or {}
        self.assertEqual(src.get("provider"), "NASA POWER ALLSKY_SFC_SW_DWN")
        self.assertIn("非标准", src.get("conversion", "") or "")


class TestSowingDepthDerive(unittest.TestCase):
    def test_matches_growth_agent_formula(self):
        """与 agent/growth_agent.py 的 round(gd/200,1) 一致。"""
        self.assertEqual(dv.sowing_depth_cm(365), round(365 / 200, 1))
        self.assertEqual(dv.sowing_depth_cm(90), 0.5)
        self.assertEqual(dv.sowing_depth_cm(30), 0.1)

    def test_missing_growth_days_returns_none(self):
        self.assertIsNone(dv.sowing_depth_cm(None))
        self.assertIsNone(dv.sowing_depth_cm(0))
        self.assertIsNone(dv.sowing_depth_cm(-5))

    def test_minimum_floor_applied(self):
        """超短生长周期不落到 0 cm（浅表播种下限 0.1）。"""
        self.assertEqual(dv.sowing_depth_cm(5), 0.1)


class TestDerivedNotWrittenBack(unittest.TestCase):
    def test_derive_does_not_mutate_recipe(self):
        """铁律：派生量不写回配方 JSON。"""
        import copy
        sample = {
            "environment": {"temperature": {"day_c": 25, "night_c": 18},
                            "humidity": {"min_pct": 50, "max_pct": 75}},
            "crop": {"species": "番茄"},
        }
        before = json.dumps(sample, sort_keys=True)
        dv.derive_from_recipe(sample)
        dv.derive_dli("arid")
        dv.sowing_depth_cm(90)
        after = json.dumps(sample, sort_keys=True)
        self.assertEqual(before, after, "派生函数不应修改配方")


if __name__ == "__main__":
    unittest.main()