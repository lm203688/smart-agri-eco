#!/usr/bin/env python3
"""
智慧农业生态 · data_lineage 单元测试

覆盖：trace_recipe / trace_local_files / trace_external_apis / render_text
对齐 GOAI DataFlow-Agent 提升点3 + 壁垒④真实结果回流校准
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # 确保所有路径解析基于项目根目录

from core.data_lineage import (  # noqa: E402
    EXTERNAL_APIS,
    LOCAL_FILES,
    _cache_hit,
    _calibration_present,
    _sha256_file,
    query_lineage,
    render_text,
    trace_external_apis,
    trace_local_files,
    trace_pipeline_result,
    trace_recipe,
)


class TestTraceRecipe(unittest.TestCase):
    """trace_recipe 基础链路"""

    def test_returns_structured_report(self):
        rep = trace_recipe("tomato", "temperate")
        self.assertIn("trace_id", rep)
        self.assertIn("query", rep)
        self.assertIn("external_apis", rep)
        self.assertIn("local_files", rep)
        self.assertIn("calibration", rep)
        self.assertIn("lineage_statement", rep)
        self.assertEqual(rep["query"]["crop"], "tomato")
        self.assertEqual(rep["query"]["zone_id"], "temperate")

    def test_trace_id_format(self):
        rep = trace_recipe("lettuce", "tropical_rainforest")
        self.assertTrue(rep["trace_id"].startswith("lineage-"))
        self.assertIn("lettuce", rep["trace_id"])
        self.assertIn("tropical_rainforest", rep["trace_id"])

    def test_external_apis_count(self):
        rep = trace_recipe("tomato", "temperate")
        apis = rep["external_apis"]
        self.assertEqual(len(apis), 5, "必须登记全部 5 个外部 API")
        api_ids = {a["id"] for a in apis}
        expected = {"nasa_power", "open_meteo", "worldclim_2_1", "gbif", "soilgrids"}
        self.assertEqual(api_ids, expected)

    def test_local_files_count(self):
        rep = trace_recipe("tomato", "temperate")
        files = rep["local_files"]
        self.assertEqual(len(files), 4, "必须登记全部 4 个本地权威文件")
        file_ids = {f["id"] for f in files}
        expected = {"global_zones", "crop_adapt_db", "preset_cities", "zone_checks"}
        self.assertEqual(file_ids, expected)

    def test_local_files_all_present(self):
        rep = trace_recipe("tomato", "temperate")
        for f in rep["local_files"]:
            self.assertTrue(f["present"], f"{f['id']} 必须存在")
            self.assertIsNotNone(f["sha256"], f"{f['id']} 必须有 sha256 指纹")
            self.assertGreater(len(f["sha256"]), 0, f"{f['id']} sha256 非空")

    def test_sha256_deterministic(self):
        """同一文件两次调用 sha256 必须一致"""
        rep1 = trace_recipe("tomato", "temperate")
        rep2 = trace_recipe("tomato", "temperate")
        sha1 = rep1["local_files"][0]["sha256"]
        sha2 = rep2["local_files"][0]["sha256"]
        self.assertEqual(sha1, sha2, "sha256 必须确定复现")


class TestTraceExternalApis(unittest.TestCase):
    """外部 API 追踪"""

    def test_all_reachable(self):
        apis = trace_external_apis()
        for a in apis:
            self.assertTrue(a["reachable"], f"{a['id']} 应标记为可达")

    def test_cache_hit_structure(self):
        apis = trace_external_apis()
        for a in apis:
            self.assertIn("cache_present", a)
            self.assertIn("cache_file_count", a)
            self.assertIn("note", a)

    def test_cache_present_not_none_for_cached_apis(self):
        """有 cache_dir 的 API 必须返回布尔 present，不能是 None"""
        apis = trace_external_apis()
        for a in apis:
            if a.get("cache_dir"):
                self.assertIsNotNone(a["cache_present"],
                                    f"{a['id']} 有 cache_dir 但 cache_present=None")


class TestTraceLocalFiles(unittest.TestCase):
    """本地文件追踪"""

    def test_missing_file_falls_back_gracefully(self):
        """故意指向不存在的文件路径验证降级（保存/恢复原始 path，避免污染共享 dict）"""
        from core.data_lineage import LOCAL_FILES
        target = LOCAL_FILES[0]
        orig_path = target["path"]
        try:
            target["path"] = os.path.join(tempfile.gettempdir(),
                                           "nonexistent_agri_test_xyz.json")
            files = trace_local_files()
            self.assertFalse(files[0]["present"], "不存在的文件应降级为 present=False")
            self.assertIsNone(files[0]["sha256"])
        finally:
            target["path"] = orig_path
        # 恢复后必须能再次看到文件（防测试间污染）
        self.assertTrue(trace_local_files()[0]["present"], "路径恢复后文件应重新可见")

    def test_all_expected_ids(self):
        files = trace_local_files()
        ids = [f["id"] for f in files]
        self.assertIn("global_zones", ids)
        self.assertIn("crop_adapt_db", ids)
        self.assertIn("preset_cities", ids)
        self.assertIn("zone_checks", ids)


class TestCalibrationPresent(unittest.TestCase):
    """校准实证追踪（壁垒④核心）"""

    def test_known_crop_zone_returns_found(self):
        """已知作物+分区应返回 found=True"""
        # 从真实数据找一对有效组合
        db_path = os.path.join(ROOT, "data", "crop_adapt_db.json")
        if not os.path.exists(db_path):
            self.skipTest("crop_adapt_db.json 不存在")
        with open(db_path, encoding="utf-8") as f:
            db = json.load(f)
        zones = db.get("zones", {})
        for zone_id, zd in zones.items():
            crops = zd.get("crops", [])
            if crops:
                crop = crops[0].get("crop", "")
                if crop:
                    result = _calibration_present(crop, zone_id)
                    self.assertTrue(result["found"],
                                    f"{crop}@{zone_id} 应被找到")
                    break
        else:
            self.fail("数据库中找不到任何作物-分区组合")

    def test_unknown_crop_returns_not_found(self):
        result = _calibration_present("nonexistent_crop_xyz", "temperate")
        self.assertFalse(result["found"])
        self.assertIsNone(result["calibrated"])


class TestRenderText(unittest.TestCase):
    """文本渲染"""

    def test_render_contains_header(self):
        rep = trace_recipe("tomato", "temperate")
        txt = render_text(rep)
        self.assertIn("数据血缘追踪报告", txt)

    def test_render_contains_local_files_section(self):
        rep = trace_recipe("tomato", "temperate")
        txt = render_text(rep)
        self.assertIn("本地权威文件", txt)

    def test_render_contains_calibration_section(self):
        rep = trace_recipe("tomato", "temperate")
        txt = render_text(rep)
        self.assertIn("校准实证", txt)

    def test_render_contains_lineage_statement(self):
        rep = trace_recipe("tomato", "temperate")
        txt = render_text(rep)
        self.assertIn("真实来源", txt)


class TestTracePipelineResult(unittest.TestCase):
    """流水线结果血缘追踪"""

    def test_with_full_result(self):
        result = {
            "final_recommendation": {
                "zone": "temperate",
                "recommended_crops": [{"crop": "tomato", "score": 0.85}],
            }
        }
        rep = trace_pipeline_result(result)
        self.assertEqual(rep["query"]["crop"], "tomato")
        self.assertEqual(rep["query"]["zone_id"], "temperate")
        self.assertTrue(rep["trace_id"].startswith("lineage-"))

    def test_with_missing_zone_falls_back_global(self):
        result = {
            "final_recommendation": {
                "zone": "",
                "recommended_crops": [],
            }
        }
        rep = trace_pipeline_result(result)
        self.assertEqual(rep["query"]["crop"], "")
        self.assertEqual(rep["query"]["zone_id"], "")
        self.assertIn("lineage-pipeline-global", rep["trace_id"])


class TestSha256File(unittest.TestCase):
    """sha256 工具函数"""

    def test_existing_file(self):
        test_file = os.path.join(ROOT, "data", "crop_adapt_db.json")
        sha = _sha256_file(test_file)
        self.assertIsNotNone(sha)
        self.assertEqual(len(sha), 64)  # SHA256 十六进制长度

    def test_missing_file_returns_none(self):
        sha = _sha256_file("/tmp/nonexistent_agri_test_xyz.json")
        self.assertIsNone(sha)


class TestQueryLineage(unittest.TestCase):
    """query_lineage 查询能力（对照 trace_recipe 的单点追踪）"""

    def test_crop_and_zone_is_single_trace(self):
        rep = query_lineage(crop="番茄", zone_id="subtropical_wet")
        self.assertIn("trace_id", rep)
        self.assertEqual(rep["query"]["crop"], "番茄")
        self.assertEqual(rep["query"]["zone_id"], "subtropical_wet")

    def test_crop_only_finds_all_zones(self):
        rep = query_lineage(crop="番茄")
        self.assertIn("match_count", rep)
        self.assertGreaterEqual(rep["match_count"], 1)
        self.assertIn("traces", rep)
        self.assertLessEqual(len(rep["traces"]), 50)

    def test_zone_only_finds_all_crops(self):
        rep = query_lineage(zone_id="subtropical_wet")
        self.assertIn("match_count", rep)
        self.assertGreaterEqual(rep["match_count"], 1)
        self.assertIn("traces", rep)

    def test_empty_query_returns_summary(self):
        rep = query_lineage()
        self.assertTrue(rep.get("summary"))
        self.assertIn("zone_count", rep)
        self.assertIn("crop_entry_count", rep)
        self.assertIn("local_files", rep)
        self.assertIn("hint", rep)


if __name__ == "__main__":
    unittest.main()
