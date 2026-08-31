#!/usr/bin/env python3
"""
智慧农业生态 · 单元测试（仅标准库 unittest，零第三方依赖）

运行：
    python -m unittest scripts.test_agents -v
    # 或
    python scripts/test_agents.py

覆盖：
    - 四 Agent 流水线：杭州→亚热带湿润带、无 PLACEHOLDER、rubric 聚合正确
    - CropAgent 候选数 / EcoAgent 预算门控
    - Trust Layer 可复现证书 rubric 全通过
    - flywheel 反馈闭环：校准分随反馈变化（文件备份还原，不污染 seed 数据）
"""

import os
import sys
import json
import shutil
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from core.trust_layer import issue_certificate  # noqa: E402
import engine.flywheel as fw  # noqa: E402

CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

BASE_REQ = {
    "lat": 30.2741, "lon": 120.1551,
    "scene": "balcony", "floor": 15, "orientation": "south",
    "purpose": "食用", "space_sqm": 1.5,
    "difficulty": "beginner", "budget_cny": 500,
}


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.orch = AgriOrchestrator()

    def test_zone_match_hangzhou(self):
        r = self.orch.run_pipeline(BASE_REQ)
        zone = r["pipeline_steps"][0]["output"]["evidence"]["zone_id"]
        self.assertEqual(zone, "subtropical_wet")

    def test_no_placeholder(self):
        r = self.orch.run_pipeline(BASE_REQ)
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("PLACEHOLDER", blob)

    def test_rubric_aggregation(self):
        r = self.orch.run_pipeline(BASE_REQ)
        self.assertGreaterEqual(r["trust_summary"]["overall_rubric_score"], 0.8)

    def test_crop_recommendation_count(self):
        r = self.orch.run_pipeline(BASE_REQ)
        crops = r["final_recommendation"]["recommended_crops"]
        self.assertGreaterEqual(len(crops), 3)

    def test_growth_plan_four_phases(self):
        r = self.orch.run_pipeline(BASE_REQ)
        gp = r["pipeline_steps"][2]["output"]
        self.assertTrue(gp["evidence"].get("data_loaded"))
        self.assertEqual(len(gp["recommendation"]["phases"]), 4)
        self.assertTrue(len(gp["recommendation"]["risk_alerts"]) > 0)

    def test_device_budget_gate(self):
        r = self.orch.run_pipeline({**BASE_REQ, "budget_cny": 200})
        dev = r["pipeline_steps"][3]["output"]
        total = dev["constraints"]["total_estimated_price_cny"]
        self.assertLessEqual(total, 200)
        # 超预算时总价应 <= 预算
        self.assertLessEqual(total, 200)


class TestTrustLayer(unittest.TestCase):
    def test_certificate_full_pass(self):
        cert = issue_certificate(run_id="unittest", inputs={"scene": "balcony", "crop": "生菜"})
        self.assertTrue(cert["rubric"]["full_pass"])
        self.assertEqual(cert["rubric"]["passed"], cert["rubric"]["total"])
        self.assertTrue(cert["signature"])


class TestFlywheel(unittest.TestCase):
    """校准会写盘 crop_adapt_db.json，用备份还原避免污染 seed 数据。"""

    def setUp(self):
        self.backup = CROP_DB + ".test.bak"
        shutil.copy(CROP_DB, self.backup)

    def tearDown(self):
        if os.path.exists(self.backup):
            shutil.move(self.backup, CROP_DB)

    def test_calibration_changes_score(self):
        res = fw.record_feedback(
            zone_id="subtropical_wet", crop="生菜",
            survival_rate=0.9, yield_rating=4.0, user_rating=5.0,
            issues=["单测样本"], note="unittest",
        )
        self.assertTrue(res["changed"])
        self.assertNotEqual(res["before"], res["after"])
        self.assertTrue(res["calibrated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
