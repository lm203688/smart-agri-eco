"""test_recipe_profile.py — M8-R2 配方 profile 四件套单元测试。

覆盖：
  - list/stats 元信息
  - export 幂等 / _profile_meta 元数据 / 隐私字段剥离
  - import 覆盖前备份
  - diff 三态（identical/different/added/removed）
  - clone 目标已存在拒绝
  - diff 忽略 execution_log/outcome 私有数据
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.recipe_profile import (  # noqa: E402
    export_recipe, import_recipe, diff_recipes, clone_recipe,
    list_recipes, recipe_stats,
)


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


class TestRecipeProfile(unittest.TestCase):
    def setUp(self):
        # 在临时目录构造一份最小合法配方
        self._tmpdir = tempfile.mkdtemp(prefix="recipe_profile_")
        self._recipes_dir = os.path.join(self._tmpdir, "env_recipes")
        os.makedirs(self._recipes_dir)
        self._write_recipe("zoneA__番茄.json", "番茄", "zoneA",
                           temperature_day=32, water_ml_day=350)
        self._write_recipe("zoneB__番茄.json", "番茄", "zoneB",
                           temperature_day=28, water_ml_day=200)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_recipe(self, name, crop, zone, temperature_day, water_ml_day):
        recipe = {
            "protocol": "env-recipe",
            "recipe_version": "1.0.0",
            "crop": {"species": crop, "latin": "Solanum lycopersicum", "family": "茄科"},
            "stage": "full_cycle",
            "device_profile": {"device_class": "other", "zone_id": zone},
            "environment": {
                "temperature": {"day_c": temperature_day, "night_c": 15},
                "water_nutrient": {"ph": 6.4, "water_ml_day": water_ml_day},
            },
            "exception_handling": [],
            "execution_log": [{"run_id": "shadow_x", "source": "shadow"}],
            "outcome": {"yield_actual_g": 400},
            "image_consent": {"captured": False},
            "sources": [{"title": "FAO", "source_license": "CC BY 4.0",
                          "data_quality": "modeled", "trial_location": "全球"}],
            "license": "CC-BY-4.0",
        }
        with open(os.path.join(self._recipes_dir, name), "w", encoding="utf-8") as f:
            json.dump(recipe, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # list / stats
    # ------------------------------------------------------------------
    def test_list_recipes(self):
        items = list_recipes(self._recipes_dir)
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertIn("filename", it)
            self.assertIn("recipe_ref", it)
            self.assertEqual(it["recipe_ref"].split(":")[0], "番茄")

    def test_recipe_stats(self):
        stats = recipe_stats(self._recipes_dir)
        self.assertEqual(stats["total_recipes"], 2)
        self.assertGreater(stats["total_bytes"], 0)
        self.assertIn("by_stage", stats)

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------
    def test_export_default_strips_private_data(self):
        out = os.path.join(self._tmpdir, "exported.json")
        r = export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir)
        self.assertTrue(os.path.exists(out))
        exported = _read(out)
        # 隐私字段被剥离
        self.assertNotIn("execution_log", exported)
        self.assertNotIn("outcome", exported)
        # 溯源保留
        self.assertIn("sources", exported)
        # 元数据写入
        self.assertIn("_profile_meta", exported)
        self.assertIn("source_sha256", exported["_profile_meta"])
        # 返回摘要正确
        self.assertEqual(r["recipe_ref"], "番茄:full_cycle:other")

    def test_export_can_include_private_data(self):
        out = os.path.join(self._tmpdir, "exported_full.json")
        export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir,
                      include_execution_log=True, include_outcome=True)
        exported = _read(out)
        self.assertIn("execution_log", exported)
        self.assertIn("outcome", exported)

    def test_export_can_exclude_sources(self):
        out = os.path.join(self._tmpdir, "exported_nosrc.json")
        export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir,
                      include_sources=False)
        exported = _read(out)
        self.assertNotIn("sources", exported)

    def test_export_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            export_recipe("no_such_recipe.json", "/tmp/x.json",
                          recipes_dir=self._recipes_dir)

    # ------------------------------------------------------------------
    # import
    # ------------------------------------------------------------------
    def test_import_creates_new_recipe(self):
        out = os.path.join(self._tmpdir, "exported.json")
        export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir)
        r = import_recipe(out, "zoneC__番茄.json", recipes_dir=self._recipes_dir)
        self.assertTrue(os.path.exists(
            os.path.join(self._recipes_dir, "zoneC__番茄.json")))
        self.assertFalse(r["overwrote"])
        imported = _read(os.path.join(self._recipes_dir, "zoneC__番茄.json"))
        # _profile_meta 被剥离
        self.assertNotIn("_profile_meta", imported)

    def test_import_overwrite_creates_backup(self):
        out = os.path.join(self._tmpdir, "exported.json")
        export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir)
        # 导入到已存在的 zoneB 应该备份
        r = import_recipe(out, "zoneB__番茄.json", recipes_dir=self._recipes_dir)
        self.assertTrue(r["overwrote"])
        self.assertIsNotNone(r["backup_path"])
        self.assertTrue(os.path.exists(r["backup_path"]))

    def test_import_no_backup_overwrites_directly(self):
        out = os.path.join(self._tmpdir, "exported.json")
        export_recipe("zoneA__番茄.json", out, recipes_dir=self._recipes_dir)
        r = import_recipe(out, "zoneB__番茄.json", recipes_dir=self._recipes_dir,
                          backup=False)
        self.assertTrue(r["overwrote"])
        self.assertIsNone(r["backup_path"])

    # ------------------------------------------------------------------
    # diff
    # ------------------------------------------------------------------
    def test_diff_identical_same_file(self):
        a = os.path.join(self._recipes_dir, "zoneA__番茄.json")
        r = diff_recipes(a, a)
        self.assertEqual(r["status"], "identical")
        self.assertEqual(r["summary"]["changed_keys"], 0)

    def test_diff_different(self):
        a = os.path.join(self._recipes_dir, "zoneA__番茄.json")
        b = os.path.join(self._recipes_dir, "zoneB__番茄.json")
        r = diff_recipes(a, b)
        self.assertEqual(r["status"], "different")
        self.assertGreaterEqual(r["summary"]["changed_keys"], 1)
        # unified_diff 应存在
        self.assertIn("unified_diff", r)
        self.assertIn("--- a:", r["unified_diff"])
        self.assertIn("+++ b:", r["unified_diff"])

    def test_diff_ignores_private_data(self):
        """execution_log/outcome 差异不应被计入。"""
        # 构造两份仅私有字段不同的配方
        same_a = os.path.join(self._tmpdir, "same_a.json")
        same_b = os.path.join(self._tmpdir, "same_b.json")
        for p, outcome in [(same_a, {"yield_actual_g": 400}),
                            (same_b, {"yield_actual_g": 600})]:
            with open(p, "w", encoding="utf-8") as f:
                json.dump({
                    "crop": {"species": "番茄"},
                    "stage": "full_cycle",
                    "execution_log": [{"run_id": "x"}],
                    "outcome": outcome,
                }, f, ensure_ascii=False, indent=2)
        r = diff_recipes(same_a, same_b)
        self.assertEqual(r["status"], "identical")

    def test_diff_added_and_removed_keys(self):
        """结构不同的配方应识别 added/removed。"""
        a = os.path.join(self._tmpdir, "a_struct.json")
        b = os.path.join(self._tmpdir, "b_struct.json")
        with open(a, "w", encoding="utf-8") as f:
            json.dump({"crop": {"species": "番茄"}, "extra_only_a": True},
                      f, ensure_ascii=False)
        with open(b, "w", encoding="utf-8") as f:
            json.dump({"crop": {"species": "番茄"}, "extra_only_b": True},
                      f, ensure_ascii=False)
        r = diff_recipes(a, b)
        self.assertEqual(r["status"], "different")
        self.assertGreaterEqual(r["summary"]["added_keys"], 1)
        self.assertGreaterEqual(r["summary"]["removed_keys"], 1)

    # ------------------------------------------------------------------
    # clone
    # ------------------------------------------------------------------
    def test_clone_creates_new_recipe(self):
        r = clone_recipe("zoneA__番茄.json", "zoneC__番茄.json",
                         recipes_dir=self._recipes_dir)
        self.assertTrue(os.path.exists(
            os.path.join(self._recipes_dir, "zoneC__番茄.json")))
        cloned = _read(os.path.join(self._recipes_dir, "zoneC__番茄.json"))
        self.assertIn("_clone_from", cloned)
        self.assertEqual(cloned["_clone_from"]["source_recipe"], "zoneA__番茄.json")

    def test_clone_target_exists_raises(self):
        with self.assertRaises(FileExistsError):
            clone_recipe("zoneA__番茄.json", "zoneB__番茄.json",
                         recipes_dir=self._recipes_dir)

    def test_clone_source_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            clone_recipe("no_such.json", "new.json",
                         recipes_dir=self._recipes_dir)


if __name__ == "__main__":
    unittest.main()
