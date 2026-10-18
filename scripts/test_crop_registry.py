#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_crop_registry.py —— 作物注册表契约（S1.4）

为什么需要它
------------
core/crop_registry.py 把"作物"的三套命名（机理层 7 个英文名 / 配方库 120 个
中文名 / 112 个学名）统一为一个单一来源。但单一来源只有两个前提：
  1. **不能漂移** —— ENGINE_CROPS 必须等于机理内核实际建模的作物集合
     （engine.agriworld_lite.CROP_PARAMS 的键）。否则校验口径又会出现两处。
  2. **缺口必须可见** —— 水稻（rice）在 152 份配方里没有任何条目，这必须被
     断言下来而不是被掩盖。

本文件同时锁住这两点。

运行：
    python scripts/test_crop_registry.py
    python -m unittest scripts.test_crop_registry -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import crop_registry  # noqa: E402
from engine.agriworld_lite import CROP_PARAMS  # noqa: E402


class TestEngineCropDrift(unittest.TestCase):
    """ENGINE_CROPS 与机理内核 CROP_PARAMS 必须完全一致（防两处漂移）。"""

    def test_engine_crops_equal_crop_params_keys(self):
        self.assertEqual(
            crop_registry.ENGINE_CROPS, frozenset(CROP_PARAMS.keys()),
            "ENGINE_CROPS 与 CROP_PARAMS 的键不一致 —— 作物枚举出现两个来源"
        )

    def test_engine_crops_has_exactly_7(self):
        self.assertEqual(len(crop_registry.ENGINE_CROPS), 7)

    def test_engine_crops_all_lowercase(self):
        bad = [c for c in crop_registry.ENGINE_CROPS if c != c.lower()]
        self.assertEqual(bad, [], f"非小写的机理作物名：{bad}")

    def test_crop_params_values_are_dataclasses(self):
        """机理参数必须齐全（不能是空壳）。"""
        from dataclasses import fields

        for crop, params in CROP_PARAMS.items():
            self.assertGreater(
                len(fields(type(params))), 5,
                f"{crop} 的机理参数过少，疑似空壳"
            )


class TestRecipeScan(unittest.TestCase):
    """配方库扫描必须可复算，且与 data/env_recipes/ 的实况一致。"""

    def test_scanned_152_recipe_files(self):
        self.assertEqual(
            crop_registry.RECIPE_FILE_COUNT, 152,
            f"应扫描 152 份配方，实际 {crop_registry.RECIPE_FILE_COUNT}"
        )

    def test_distinct_species_count(self):
        self.assertEqual(
            len(crop_registry.RECIPE_SPECIES), 120,
            f"应有 120 个不同中文名，实际 {len(crop_registry.RECIPE_SPECIES)}"
        )

    def test_distinct_latin_count(self):
        self.assertEqual(
            len(crop_registry.RECIPE_LATIN), 112,
            f"应有 112 个不同学名，实际 {len(crop_registry.RECIPE_LATIN)}"
        )

    def test_all_crops_is_union(self):
        expected = (
            crop_registry.ENGINE_CROPS
            | crop_registry.RECIPE_SPECIES
            | crop_registry.RECIPE_LATIN
        )
        self.assertEqual(crop_registry.ALL_CROPS, expected)

    def test_scan_is_idempotent(self):
        """重复扫描结果一致（无随机性）。"""
        s2, l2, n2 = crop_registry.scan_recipes()
        self.assertEqual(s2, crop_registry.RECIPE_SPECIES)
        self.assertEqual(l2, crop_registry.RECIPE_LATIN)
        self.assertEqual(n2, crop_registry.RECIPE_FILE_COUNT)

    def test_scan_degrades_gracefully_when_data_missing(self):
        """data/env_recipes/ 不存在时返回空集，不抛异常（离线可用）。"""
        real = crop_registry._recipes_dir
        try:
            crop_registry._recipes_dir = lambda: Path("/nonexistent/recipes/xyz")
            s, l, n = crop_registry.scan_recipes()
            self.assertEqual(s, frozenset())
            self.assertEqual(l, frozenset())
            self.assertEqual(n, 0)
        finally:
            crop_registry._recipes_dir = real


class TestMappingContract(unittest.TestCase):
    """中文名 / 学名 → 机理作物的映射契约。"""

    def test_six_engine_crops_have_recipe_names(self):
        covered = crop_registry.engine_crops_with_recipe_coverage()
        self.assertEqual(len(covered), 6, f"应有 6 个有对照，实际 {len(covered)}")
        for crop in covered:
            name = crop_registry.recipe_name_for_engine_crop(crop)
            self.assertIn(
                name, crop_registry.RECIPE_SPECIES,
                f"{crop} 的中文名 {name!r} 不在配方库扫描结果中"
            )

    def test_rice_is_the_only_uncovered_engine_crop(self):
        """水稻缺口必须被显式锁定 —— 不得静默消失或悄悄补上。"""
        self.assertEqual(
            crop_registry.uncovered_engine_crops(), ["rice"],
            "水稻覆盖缺口发生了变化，请同步更新 provenance() 与论文 Materials"
        )

    def test_all_mapping_names_exist_in_recipes(self):
        for crop, species in crop_registry.ENGINE_TO_SPECIES.items():
            self.assertIn(crop, crop_registry.ENGINE_CROPS, f"{crop} 不是机理作物")
            self.assertIn(species, crop_registry.RECIPE_SPECIES, f"{species} 不在配方库")

    def test_genus_map_targets_valid_engine_crops(self):
        for genus, crop in crop_registry.GENUS_TO_ENGINE_CROP.items():
            self.assertIn(crop, crop_registry.ENGINE_CROPS, f"{genus} → {crop} 非法")

    def test_unknown_names_map_to_none(self):
        self.assertIsNone(crop_registry.species_to_engine_crop("不存在的花"))
        self.assertIsNone(crop_registry.genus_to_engine_crop("Nonexistentia sp."))
        self.assertIsNone(crop_registry.species_to_engine_crop(None))
        self.assertIsNone(crop_registry.genus_to_engine_crop(""))

    def test_species_lookup_roundtrip(self):
        """中文名 → 机理作物 应能再查回同一个中文名。"""
        for crop in crop_registry.engine_crops_with_recipe_coverage():
            species = crop_registry.recipe_name_for_engine_crop(crop)
            self.assertEqual(
                crop_registry.species_to_engine_crop(species), crop
            )

    def test_genus_lookup_for_each_covered_crop(self):
        """每个有对照的机理作物，至少有一个配方学名能映射回它。"""
        for crop in crop_registry.engine_crops_with_recipe_coverage():
            hit = any(
                crop_registry.genus_to_engine_crop(l) == crop
                for l in crop_registry.RECIPE_LATIN
            )
            self.assertTrue(hit, f"{crop} 没有任何学名能映射回它")


class TestLookupHelpers(unittest.TestCase):
    """归一化与查询接口的边界行为。"""

    def test_is_known_crop_accepts_all_three_namings(self):
        self.assertTrue(crop_registry.is_known_crop("wheat"))            # 英文名
        self.assertTrue(crop_registry.is_known_crop("向日葵"))           # 中文名
        self.assertTrue(crop_registry.is_known_crop("Helianthus annuus"))  # 学名

    def test_is_known_crop_rejects_unknown(self):
        for bad in ("quantum_plant", "", "  ", None, 42):
            self.assertFalse(crop_registry.is_known_crop(bad), f"{bad!r} 不应被接受")

    def test_normalize_crop(self):
        self.assertEqual(crop_registry.normalize_crop(" Wheat "), "wheat")
        self.assertEqual(crop_registry.normalize_crop(None), "")
        self.assertEqual(crop_registry.normalize_crop(""), "")

    def test_none_of_all_crops_are_blank(self):
        for name in crop_registry.ALL_CROPS:
            self.assertTrue(name.strip(), f"注册表存在空白条目：{name!r}")

    def test_provenance_shape(self):
        p = crop_registry.provenance()
        for key in ("engine_crops", "recipe_species", "recipe_latin",
                    "all_crops", "uncovered_engine_crops"):
            self.assertIn(key, p, f"provenance 缺 {key}")
        self.assertEqual(p["engine_crops"]["n"], 7)
        self.assertEqual(p["recipe_species"]["n"], 120)
        self.assertEqual(p["recipe_latin"]["n"], 112)
        self.assertGreater(p["all_crops"]["n"], p["engine_crops"]["n"])

    def test_notes_are_not_empty(self):
        """诚实边界声明必须存在，论文需逐条引用。"""
        self.assertGreaterEqual(len(crop_registry.notes()), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
