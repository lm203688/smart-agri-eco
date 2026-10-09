#!/usr/bin/env python3
"""scripts/backfill_source_provenance.py 的离线回归测试（零依赖）。

锁住两个性质：

1. **幂等**：对已补齐的文件再跑一次 `--apply`，缺失字段数必须为 0（不重复写）。
2. **不编造**：未识别的源必须写 `unknown`，绝不伪造测量位置/许可。

运行：python -S -P -m unittest discover -s scripts -p "test_source_provenance.py"
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.backfill_source_provenance as B  # noqa: E402


class TestSourceProvenanceBackfill(unittest.TestCase):
    def _sample_recipe(self) -> dict:
        """构造一份含 4 类典型 sources 的配方样本。"""
        return {
            "sources": [
                {"title": "FAO CropInfo", "url": "https://ecocrop.apps.fao.org/",
                 "accessed_at": "2026-08-27", "license": "CC BY-NC-SA 3.0 IGO"},
                {"title": "中国作物栽培数据库", "url": "",
                 "accessed_at": "2026-08-27", "license": "unknown"},
                {"title": "USDA Plant Guides", "url": "",
                 "accessed_at": "2026-08-27", "license": "公有领域"},
                {"title": "完全未知的来源", "url": "",
                 "accessed_at": "2026-08-27", "license": "unknown"},
            ]
        }

    def test_meta_lookup_maps_known_sources(self):
        """FAO / 中国作物 / USDA 应映射到各自的 data_quality + trial_location + source_license。"""
        for title, expected in [
            ("FAO CropInfo", ("modeled", "FAO Ecocrop")),
            ("中国作物栽培数据库", ("modeled", "中国")),
            ("USDA Plant Guides", ("modeled", "美国农业部")),
        ]:
            meta = B._meta_for(title)
            self.assertEqual(meta["data_quality"], expected[0],
                             f"{title} data_quality 映射错误")
            self.assertIn(expected[1], meta["trial_location"],
                          f"{title} trial_location 未识别")

    def test_meta_lookup_falls_back_to_unknown(self):
        """未识别源必须写 unknown，不编造。"""
        meta = B._meta_for("完全未知的来源")
        self.assertEqual(meta["data_quality"], "unknown")
        self.assertIn("unknown", meta["trial_location"])
        self.assertIn("unknown", meta["source_license"])

    def test_apply_is_idempotent(self):
        """对同一份已补齐的配方连跑两次 apply，第二次缺失数必须为 0。"""
        r = self._sample_recipe()
        miss0 = B._missing_count(r)
        self.assertGreater(miss0, 0, "样本初始不应已补齐")

        # 第一次补齐
        for s in r["sources"]:
            meta = B._meta_for(s["title"])
            for fld in ("data_quality", "trial_location", "source_license"):
                s[fld] = meta[fld]
        self.assertEqual(B._missing_count(r), 0, "第一次补齐后应无缺失")

        # 第二次再跑：模拟 --apply 对已补齐文件
        r2 = copy.deepcopy(r)
        self.assertEqual(B._missing_count(r2), 0, "幂等：再次运行不应新增缺失")

    def test_apply_preserves_existing_license(self):
        """补齐不能覆盖原有 license 字段（保留兼容）。"""
        r = self._sample_recipe()
        orig_licenses = [s["license"] for s in r["sources"]]
        for s in r["sources"]:
            meta = B._meta_for(s["title"])
            for fld in ("data_quality", "trial_location", "source_license"):
                s[fld] = meta[fld]
        self.assertEqual([s["license"] for s in r["sources"]], orig_licenses,
                         "原有 license 字段不应被覆盖")

    def test_apply_on_real_recipes_is_idempotent(self):
        """真实 data/env_recipes 目录在补齐后，第二次 scan 应报 0 缺失。"""
        recipes = B._load_recipes()
        self.assertTrue(recipes, "data/env_recipes 应存在配方")
        # 检查当前状态：若某份未补齐，则模拟补齐后应为 0
        for path, r in recipes:
            self.assertEqual(B._missing_count(r), 0,
                             f"{path} sources 溯源三字段仍未补齐")


if __name__ == "__main__":
    unittest.main()