"""test_verify_recipe.py — M10-O4 单配方结构化验证单元测试。

覆盖：
  - required 缺失检测
  - 枚举越界（stage/device_class/light_type/sensor_capability）
  - 数值范围越界（含 humidity.min > max）
  - 依赖完整性（sources 缺失 / 无 title）
  - reproducibility_score 打分
  - 完整 verify_recipe 报告结构
  - CLI 单文件 / 批量 / --json
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.verify_recipe import (  # noqa: E402
    verify_recipe, check_required, check_enums, check_ranges,
    check_dependencies, compute_reproducibility_score,
)


def _make_recipe(**overrides):
    """构造一份合法基线配方，可覆盖任意顶层字段。"""
    base = {
        "protocol": "env-recipe",
        "recipe_version": "1.2.0",
        "crop": {"species": "番茄", "latin": "Solanum lycopersicum",
                 "family": "茄科"},
        "stage": "full_cycle",
        "device_profile": {"device_class": "greenhouse",
                           "light_type": "full_spectrum_led",
                           "sensor_capability": ["temp", "humidity", "ppfd"]},
        "environment": {
            "temperature": {"day_c": 26.0, "night_c": 20.0},
            "humidity": {"min_pct": 55.0, "max_pct": 75.0},
            "water_nutrient": {"ph": 6.2, "ec_mscm": 2.0,
                               "water_ml_day": 300},
            "light": {"ppfd_umol_m2s": 400.0, "dli_umol_m2_day": 12000.0},
        },
        "exception_handling": [],
        "execution_log": [],
        "outcome": {},
        "image_consent": {"captured": False},
        "sources": [{"title": "FAO", "source_license": "CC BY 4.0",
                     "data_quality": "modeled"}],
        "license": "CC-BY-4.0",
    }
    base.update(overrides)
    return base


class TestRequiredCheck(unittest.TestCase):
    def test_full_recipe_has_no_missing(self):
        self.assertEqual(check_required(_make_recipe()), [])

    def test_missing_protocol_reported(self):
        r = _make_recipe()
        del r["protocol"]
        self.assertIn("protocol", check_required(r))

    def test_missing_crop_reported(self):
        r = _make_recipe()
        del r["crop"]
        self.assertIn("crop", check_required(r))


class TestEnums(unittest.TestCase):
    def test_all_valid_no_violation(self):
        self.assertEqual(check_enums(_make_recipe()), [])

    def test_bad_stage_reported(self):
        self.assertTrue(any("stage" in x for x in
                            check_enums(_make_recipe(stage="bad"))))

    def test_bad_device_class_reported(self):
        r = _make_recipe(device_profile={
            "device_class": "spaceship",
            "light_type": "full_spectrum_led",
            "sensor_capability": ["temp"]})
        self.assertTrue(any("device_class" in x for x in check_enums(r)))

    def test_bad_light_type_reported(self):
        r = _make_recipe(device_profile={
            "device_class": "greenhouse",
            "light_type": "plasma",
            "sensor_capability": ["temp"]})
        self.assertTrue(any("light_type" in x for x in check_enums(r)))

    def test_unknown_sensor_reported(self):
        r = _make_recipe(device_profile={
            "device_class": "greenhouse",
            "light_type": "sunlight",
            "sensor_capability": ["temp", "quantum"]})
        self.assertTrue(any("quantum" in x for x in check_enums(r)))


class TestRanges(unittest.TestCase):
    def test_all_in_range(self):
        self.assertEqual(check_ranges(_make_recipe()), [])

    def test_temperature_out_of_range(self):
        r = _make_recipe(environment={
            "temperature": {"day_c": 60.0, "night_c": 20.0},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {"ph": 6.0, "ec_mscm": 2.0,
                               "water_ml_day": 300},
            "light": {"ppfd_umol_m2s": 400, "dli_umol_m2_day": 12000}})
        self.assertTrue(any("day_c=60.0" in x for x in check_ranges(r)))

    def test_humidity_min_gt_max(self):
        r = _make_recipe(environment={
            "temperature": {"day_c": 25, "night_c": 20},
            "humidity": {"min_pct": 80, "max_pct": 50},
            "water_nutrient": {"ph": 6.0, "ec_mscm": 2.0,
                               "water_ml_day": 300},
            "light": {"ppfd_umol_m2s": 400, "dli_umol_m2_day": 12000}})
        self.assertTrue(any("humidity.min_pct" in x for x in check_ranges(r)))

    def test_ph_out_of_range(self):
        r = _make_recipe(environment={
            "temperature": {"day_c": 25, "night_c": 20},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {"ph": 12.0, "ec_mscm": 2.0,
                               "water_ml_day": 300},
            "light": {"ppfd_umol_m2s": 400, "dli_umol_m2_day": 12000}})
        self.assertTrue(any("ph=12.0" in x for x in check_ranges(r)))


class TestDependencies(unittest.TestCase):
    def test_all_good(self):
        self.assertEqual(check_dependencies(_make_recipe()), [])

    def test_empty_sources_reported(self):
        r = _make_recipe(sources=[])
        self.assertTrue(any("sources" in x for x in check_dependencies(r)))

    def test_source_missing_title(self):
        r = _make_recipe(sources=[{"source_license": "CC BY 4.0"}])
        self.assertTrue(any("title" in x for x in check_dependencies(r)))

    def test_missing_top_license_reported(self):
        r = _make_recipe()
        del r["license"]
        self.assertTrue(any("license" in x for x in check_dependencies(r)))


class TestReproducibilityScore(unittest.TestCase):
    def test_full_recipe_high_score(self):
        score, present, missing = compute_reproducibility_score(_make_recipe())
        self.assertGreaterEqual(score, 0.95)
        self.assertEqual(missing, [])
        self.assertGreaterEqual(len(present), 12)

    def test_minimal_recipe_low_score(self):
        r = {"protocol": "env-recipe", "recipe_version": "1.0.0",
             "crop": {"species": "番茄"}, "stage": "full_cycle",
             "environment": {}}
        score, _, missing = compute_reproducibility_score(r)
        self.assertLess(score, 0.50)
        self.assertGreaterEqual(len(missing), 8)

    def test_empty_recipe_zero_score(self):
        score, _, missing = compute_reproducibility_score({})
        self.assertEqual(score, 0.0)
        self.assertEqual(len(missing), len(
            __import__("scripts.verify_recipe", fromlist=["SCORE_KEYS"]).SCORE_KEYS))


class TestVerifyRecipeIntegration(unittest.TestCase):
    def test_good_recipe_passes(self):
        r = verify_recipe(_make_recipe(), filename="ok.json")
        self.assertTrue(r["ok"])
        self.assertEqual(r["missing_required"], [])
        self.assertEqual(r["enum_violations"], [])
        self.assertEqual(r["dependency_issues"], [])
        self.assertGreaterEqual(r["reproducibility_score"], 0.80)

    def test_bad_recipe_fails(self):
        r = verify_recipe({
            "protocol": "env-recipe",
            "recipe_version": "1.0.0",
            "crop": {"species": "番茄"},
            "stage": "not_a_stage",
            "environment": {},
            "sources": [],
        }, filename="bad.json")
        self.assertFalse(r["ok"])
        self.assertIn("stage='not_a_stage' 不在枚举", " ".join(r["enum_violations"]))
        self.assertTrue(any("sources" in x for x in r["dependency_issues"]))

    def test_low_reproducibility_blocks(self):
        """score < 0.80 强制 ok=False，即使无其他 error。"""
        r = verify_recipe(_make_recipe(environment={
            "temperature": {"day_c": 25, "night_c": 20},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {"ph": 6.2, "ec_mscm": 2.0},
            "light": {},  # ppfd 缺
        }), filename="low.json")
        # 缺 ppfd_umol_m2s + water_ml_day + light.ppfd，score 应低于阈值
        self.assertLess(r["reproducibility_score"], 0.90)
        # 缺足够多关键字段：ok 应为 False
        r2 = verify_recipe(_make_recipe(environment={
            "temperature": {},
            "humidity": {},
            "water_nutrient": {},
            "light": {},
        }), filename="very_low.json")
        self.assertLess(r2["reproducibility_score"], 0.80)
        self.assertFalse(r2["ok"])

    def test_report_contains_all_expected_fields(self):
        r = verify_recipe(_make_recipe(), filename="check.json")
        for key in ["ok", "filename", "missing_required", "enum_violations",
                    "range_warnings", "dependency_issues",
                    "reproducibility_score", "present_paths", "missing_paths",
                    "note"]:
            self.assertIn(key, r)


class TestVerifyRecipeCLI(unittest.TestCase):
    def _run(self, args, cwd=ROOT):
        return subprocess.run(
            [sys.executable, os.path.join("scripts", "verify_recipe.py"), *args],
            cwd=cwd, capture_output=True, text=True, timeout=30,
        )

    def test_single_json_mode(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False, encoding="utf-8")
        json.dump(_make_recipe(), tmp, ensure_ascii=False)
        tmp.close()
        try:
            p = self._run([tmp.name, "--json"])
            self.assertEqual(p.returncode, 0, p.stderr)
            data = json.loads(p.stdout)
            self.assertTrue(data["ok"])
            self.assertIn("reproducibility_score", data)
        finally:
            os.unlink(tmp.name)

    def test_bad_recipe_exits_nonzero(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False, encoding="utf-8")
        json.dump({"protocol": "env-recipe", "recipe_version": "1.0.0",
                   "crop": {"species": "x"}, "stage": "bad",
                   "environment": {}, "sources": [],
                   "license": "CC"}, tmp, ensure_ascii=False)
        tmp.close()
        try:
            p = self._run([tmp.name])
            self.assertNotEqual(p.returncode, 0)
        finally:
            os.unlink(tmp.name)

    def test_batch_mode_all_ok(self):
        # 用真实配方库跑一次（快速路径）
        p = self._run(["--all", "--json"])
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        data = json.loads(p.stdout)
        self.assertEqual(data["mode"], "batch")
        self.assertGreaterEqual(data["total"], 100)
        self.assertGreaterEqual(data["ok"], data["total"] * 0.95)

    def test_no_args_shows_help(self):
        p = self._run([])
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
