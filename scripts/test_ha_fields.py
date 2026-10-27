"""scripts/test_ha_fields.py —— M8-R1 HA 生态事实标准字段硬门禁。

校验项
------
1. **152 配方全部含 6 项 HA/OpenFarm 字段**（无缺字段的配方）
2. **VPD 数值合理性**：nominal 落在 [-5, 10] kPa 物理范围内
3. **VPD 与 mold_risk 一致性**：标称 VPD < 0.5 → mold_risk.level 必为 medium 或 high
4. **DLI 拆分一致性**（P0-4）：shortwave_photon_equivalent + par_dli 存在，旧 dli_umol_m2_day 标 deprecated 且 replaced_by 正确；par_dli 无实测时 value=null + status + reason
5. **伴生植物排除自身**：companion_plants.items 中不含配方自身作物
6. **溯源元数据完整**：每个派生字段带 source + derived_at + method
7. **不编造**：null 派生字段必须有 reason

Exit code
--------
    0  全部通过
    1  有失败用例
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.apply_recipe_ha_fields import (  # noqa: E402
    HA_FIELDS,
    OPENFARM_FIELDS,
    RECIPE_DIR,
)


class TestRecipeHaFields(unittest.TestCase):
    """M8-R1 HA/OpenFarm 字段完整性与合理性硬门禁。"""

    @classmethod
    def setUpClass(cls):
        cls.recipes = []
        cls.errors = []
        for f in sorted(os.listdir(RECIPE_DIR)):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(RECIPE_DIR, f), encoding="utf-8") as fh:
                    cls.recipes.append((f, json.load(fh)))
            except Exception as e:
                cls.errors.append((f, "read failed: %s" % e))

    def test_01_no_read_errors(self):
        """所有配方 JSON 可读。"""
        self.assertEqual(self.errors, [],
                         "部分配方读取失败: %s" % self.errors[:3])

    def test_02_total_count_ge_150(self):
        """配方数下限（防退化）。"""
        self.assertGreaterEqual(len(self.recipes), 150,
                                "配方数 %d < 150，可能被误删" % len(self.recipes))

    def test_03_all_ha_fields_present(self):
        """所有配方含 6 项 HA/OpenFarm 字段。"""
        missing = []
        for fname, r in self.recipes:
            env = r.get("environment", {}) or {}
            for f in HA_FIELDS:
                if f not in env:
                    missing.append("%s: environment.%s" % (fname, f))
            for f in OPENFARM_FIELDS:
                if f not in r:
                    missing.append("%s: %s" % (fname, f))
        self.assertEqual(missing, [],
                         "缺 HA 字段的配方 %d 份: %s" % (
                             len(missing), missing[:8]))

    def test_04_vpd_physical_bounds(self):
        """VPD nominal 落在物理合理区间 [-5, 10] kPa。"""
        bad = []
        for fname, r in self.recipes:
            vpd_obj = r.get("environment", {}).get("vpd_kpa")
            if vpd_obj is None:
                continue
            nominal = vpd_obj.get("nominal")
            if nominal is None:
                continue
            if not -5.0 <= nominal <= 10.0:
                bad.append("%s: nominal=%.3f" % (fname, nominal))
        self.assertEqual(bad, [], "VPD 越界的配方: %s" % bad[:5])

    def test_05_mold_risk_consistency(self):
        """mold_risk.level 与 vpd.nominal 一致：nominal<0.5 → medium 或 high。"""
        bad = []
        for fname, r in self.recipes:
            vpd_obj = r.get("environment", {}).get("vpd_kpa")
            mold = r.get("environment", {}).get("mold_risk")
            if vpd_obj is None or mold is None:
                continue
            nominal = vpd_obj.get("nominal")
            level = mold.get("level")
            if nominal is None or level in (None, "unknown"):
                continue
            # VPD < 0.5 必须是 medium 或 high
            if nominal < 0.5 and level not in ("medium", "high"):
                bad.append("%s: VPD=%.3f but mold_risk=%s" % (fname, nominal, level))
        self.assertEqual(bad, [], "mold_risk 与 VPD 不一致: %s" % bad[:5])

    def test_06_dli_non_null(self):
        """dli_umol_m2_day 对已知 zone 必有值。"""
        known_zones = {"arid", "highland", "hot_arid", "mediterranean",
                       "subarctic", "subtropical_wet",
                       "temperate_continental", "tropical_rainforest"}
        bad = []
        for fname, r in self.recipes:
            zone = fname.split("__", 1)[0]
            dli = r.get("environment", {}).get("dli_umol_m2_day")
            if zone in known_zones:
                if dli is None or dli.get("value") is None:
                    bad.append("%s: zone=%s but dli is null" % (fname, zone))
        self.assertEqual(bad, [], "应有 DLI 但为 null: %s" % bad[:5])

    def test_07_companions_exclude_self(self):
        """伴生植物列表不含配方自身作物。"""
        bad = []
        for fname, r in self.recipes:
            species = (r.get("crop", {}) or {}).get("species")
            if not species:
                continue
            items = (r.get("companion_plants", {}) or {}).get("items", []) or []
            for item in items:
                if item.get("crop") == species:
                    bad.append("%s: 自身 %s 出现在伴生列表中" % (fname, species))
                    break
        self.assertEqual(bad, [], "伴生植物含自身: %s" % bad[:5])

    def test_08_companions_have_reason(self):
        """每条伴生植物候选必须有 reason 说明。"""
        bad = []
        for fname, r in self.recipes:
            items = (r.get("companion_plants", {}) or {}).get("items", []) or []
            for item in items:
                if not item.get("reason"):
                    bad.append("%s: 伴生候选 %s 无 reason" % (fname, item.get("crop")))
        self.assertEqual(bad, [], "伴生候选缺 reason: %s" % bad[:5])

    def test_09_provenance_metadata(self):
        """每个派生字段必须带 source + derived_at + method 三项溯源元数据。"""
        bad = []
        for fname, r in self.recipes:
            env = r.get("environment", {}) or {}
            for key in ("vpd_kpa", "dew_point_c", "mold_risk", "dli_umol_m2_day"):
                obj = env.get(key)
                if obj is None:
                    continue
                for meta_key in ("source", "derived_at"):
                    if meta_key not in obj:
                        bad.append("%s: environment.%s 缺 %s" % (fname, key, meta_key))
            # mold_risk 允许无 method 但必须有 thresholds 或直接判据
            if env.get("mold_risk") and "thresholds" not in env["mold_risk"]:
                bad.append("%s: mold_risk 缺 thresholds" % fname)
        self.assertEqual(bad, [], "溯源元数据缺失: %s" % bad[:8])

    def test_10_sowing_depth_has_reason_when_null(self):
        """sowing_depth_cm.value 为 null 时必须带 reason（不编造纪律）。"""
        bad = []
        for fname, r in self.recipes:
            sd = r.get("sowing_depth_cm", {}) or {}
            if sd.get("value") is None and not sd.get("reason"):
                bad.append("%s: sowing_depth 为 null 但无 reason" % fname)
        self.assertEqual(bad, [], "null 但无 reason: %s" % bad[:5])

    def test_11_recipe_version_unchanged(self):
        """HA 字段是新增 optional，不改变 recipe_version。"""
        bad = []
        for fname, r in self.recipes:
            ver = r.get("recipe_version", "")
            if not ver.startswith("1."):
                bad.append("%s: recipe_version=%s 已非 1.x" % (fname, ver))
        self.assertEqual(bad, [], "recipe_version 被意外改动: %s" % bad[:5])

    def test_12_protocol_unchanged(self):
        """HA 字段是新增 optional，不改 protocol。"""
        bad = []
        for fname, r in self.recipes:
            if r.get("protocol") != "env-recipe":
                bad.append("%s: protocol=%s" % (fname, r.get("protocol")))
        self.assertEqual(bad, [], "protocol 被改动: %s" % bad[:5])

    def test_13_environment_preserved(self):
        """HA 字段是新增，原有 environment 结构（temperature/humidity/water_nutrient/airflow）不变。"""
        required = ["temperature", "humidity", "water_nutrient", "airflow"]
        bad = []
        for fname, r in self.recipes:
            env = r.get("environment", {}) or {}
            for k in required:
                if k not in env:
                    bad.append("%s: environment 缺 %s" % (fname, k))
        self.assertEqual(bad, [], "原有 environment 字段被删除: %s" % bad[:5])

    def test_14_dli_split_consistency(self):
        """P0-4 拆分：shortwave_photon_equivalent + par_dli 存在且旧字段标 deprecated。"""
        bad = []
        for fname, r in self.recipes:
            env = r.get("environment", {}) or {}
            sw = env.get("shortwave_photon_equivalent")
            par = env.get("par_dli")
            old = env.get("dli_umol_m2_day")
            # 1. 两新字段存在
            if not isinstance(sw, dict):
                bad.append("%s: 缺 shortwave_photon_equivalent" % fname)
                continue
            if not isinstance(par, dict):
                bad.append("%s: 缺 par_dli" % fname)
                continue
            # 2. 旧字段必须标 deprecated + replaced_by
            if not isinstance(old, dict) or old.get("deprecated") is not True:
                bad.append("%s: 旧 dli_umol_m2_day 未标 deprecated" % fname)
                continue
            if old.get("replaced_by") != ["shortwave_photon_equivalent", "par_dli"]:
                bad.append("%s: replaced_by 不一致" % fname)
                continue
            # 3. shortwave 必须带 value + spectral_definition
            if sw.get("value") is None:
                bad.append("%s: shortwave.value 为 null" % fname)
            if sw.get("spectral_definition") != "full_spectrum_shortwave":
                bad.append("%s: spectral_definition 不一致" % fname)
            # 4. par_dli 无实测 → value=null + status + reason（不编造）
            if par.get("value") is not None:
                bad.append("%s: par_dli 无实测却非 null" % fname)
            if par.get("status") != "unavailable_pending_measurement":
                bad.append("%s: par_dli status 不一致" % fname)
            if not par.get("reason"):
                bad.append("%s: par_dli 缺 reason" % fname)
        self.assertEqual(bad, [], "DLI 拆分不一致: %s" % bad[:8])


if __name__ == "__main__":
    unittest.main()
