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
    - flywheel 反馈闭环：校准分随反馈变化（数据文件备份/重定向，不污染 seed 数据）
    - 作物库数据完整性：calibrated 标记必须有证据、反馈日志不得含合成样本
"""

import os
import sys
import json
import shutil
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.pest_agent import PestAgent  # noqa: E402
from agent.nutrition_agent import NutritionAgent  # noqa: E402
from agent.vision import call_vision_backend  # noqa: E402
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
    """校准会写盘：crop_adapt_db.json 用备份还原，feedback_log.json 重定向到临时文件。

    后者修复的是真实缺陷：record_feedback 原本只写固定的 data/feedback_log.json，
    单测 / CI 每次运行都会追加「单测样本」，造成该 git 跟踪文件无限膨胀 + git 噪音。
    """

    def setUp(self):
        self.backup = CROP_DB + ".test.bak"
        shutil.copy(CROP_DB, self.backup)
        # 反馈日志重定向到临时文件，绝不污染仓库内的 data/feedback_log.json
        self.test_log = os.path.join(ROOT, "data", "_test_feedback_log.json")
        os.environ["AGRI_FEEDBACK_LOG"] = self.test_log

    def tearDown(self):
        if os.path.exists(self.backup):
            shutil.move(self.backup, CROP_DB)
        os.environ.pop("AGRI_FEEDBACK_LOG", None)
        if os.path.exists(self.test_log):
            os.remove(self.test_log)

    def test_calibration_changes_score(self):
        # 环境变量必须真的生效（否则测试会污染仓库数据）
        self.assertEqual(fw.feedback_log_path(), self.test_log)
        res = fw.record_feedback(
            zone_id="subtropical_wet", crop="生菜",
            survival_rate=0.9, yield_rating=4.0, user_rating=5.0,
            issues=["单测样本"], note="unittest",
        )
        self.assertTrue(res["changed"])
        self.assertNotEqual(res["before"], res["after"])
        self.assertTrue(res["calibrated"])

    def test_feedback_log_not_polluted(self):
        """回归守卫：单测绝不能向仓库内的真实 feedback_log.json 写入测试样本。"""
        fw.record_feedback(
            zone_id="subtropical_wet", crop="生菜",
            survival_rate=0.9, yield_rating=4.0, user_rating=5.0,
            issues=["单测样本"], note="unittest",
        )
        real_log = fw._DEFAULT_FEEDBACK_LOG
        if os.path.exists(real_log):
            with open(real_log, "r", encoding="utf-8") as f:
                entries = json.load(f)
            self.assertIsInstance(entries, list)
            polluted = [e for e in entries if e.get("note") == "unittest"]
            self.assertEqual(polluted, [], "真实反馈日志被单测污染")

    def test_bad_crop_db_override_fails_fast(self):
        """回归守卫：指向不存在文件的环境变量覆盖必须明确报错。

        静默降级会让查询全空、校准全「未找到」、demo 输出全 None 且无任何报错。
        """
        os.environ["AGRI_CROP_DB"] = os.path.join(ROOT, "data", "_no_such_file.json")
        try:
            with self.assertRaises(ValueError):
                fw.crop_db_path()
        finally:
            os.environ.pop("AGRI_CROP_DB", None)


class TestCropDataIntegrity(unittest.TestCase):
    """守住作物库的诚实性：可信层会把 calibrated 标记透给用户，标记就必须有证据。"""

    @classmethod
    def setUpClass(cls):
        with open(CROP_DB, "r", encoding="utf-8") as f:
            cls.db = json.load(f)

    def _crops(self):
        for zone in self.db.get("zones", {}).values():
            for crop in zone.get("crops", []):
                yield crop

    def test_calibration_flag_has_evidence(self):
        """回归守卫：曾出现 34 个作物只有 calibrated:true 却零校准证据。"""
        bad = [c["crop"] for c in self._crops()
               if c.get("calibrated") and "measured_calibration" not in c]
        self.assertEqual(bad, [], f"{len(bad)} 个作物 calibrated 标记无校准证据: {bad[:5]}")

    def test_seed_score_consistent(self):
        """有 seed 记录时，adapt_score 必须等于校准分或 seed 分（防半写状态）。"""
        bad = []
        for c in self._crops():
            seed = c.get("seed_adapt_score")
            if seed is not None:
                calib = c.get("measured_calibration") or {}
                if c.get("adapt_score") not in (seed, calib.get("calibrated_score")):
                    bad.append(c["crop"])
        self.assertEqual(bad, [], f"{len(bad)} 个作物分数状态不一致: {bad[:5]}")

    def test_feedback_log_has_no_synthetic_entries(self):
        """回归守卫：feedback_log 只存真实用户反馈，demo/单测/冒烟样本不得入库。

        历史事实：仓库里曾累积 12 条合成样本，制造出「已有真实数据回流」的假象。
        """
        log_path = os.path.join(ROOT, "data", "feedback_log.json")
        if not os.path.exists(log_path):
            self.skipTest("feedback_log.json 不存在")
        with open(log_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            self.fail("feedback_log.json 不是数组")
        synthetic = {"unittest", "smoke"}
        bad = []
        for e in entries:
            text = " ".join(
                [str(e.get("note", ""))] + [str(i) for i in e.get("issues", [])]
            ).lower()
            if any(k in text for k in synthetic) or "[demo]" in text:
                bad.append(e.get("note", ""))
        self.assertEqual(bad, [], f"反馈日志含 {len(bad)} 条合成样本")


class TestPestAgent(unittest.TestCase):
    def setUp(self):
        self.agent = PestAgent()

    def test_no_placeholder_and_signature(self):
        r = self.agent.run({"crop": "番茄", "symptom_description": "叶片黄色斑点，背面白色粉状物，像白粉病"})
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("PLACEHOLDER", blob)
        self.assertTrue(r["signature"])
        self.assertIn("constraints", r)
        self.assertEqual(len(r["constraints"]), 3)

    def test_symptom_diagnosis_returns_actions(self):
        r = self.agent.run({"crop": "番茄", "symptom_description": "叶背有白色小点，结网，失绿，像是红蜘蛛"})
        self.assertIn("红蜘蛛", r["diagnosis"])
        self.assertIn("虫害", r["diagnosis"])
        self.assertTrue(len(r["actions"]) >= 1)
        self.assertGreater(r["diagnosis_confidence"], 0.5)

    def test_monitoring_without_symptom(self):
        r = self.agent.run({"crop": "香蕉"})
        self.assertIn("监测", r["diagnosis"])
        self.assertEqual(r["severity"], "light")
        self.assertTrue(len(r["matched_risks"]) >= 1)

    def test_unknown_crop_safe(self):
        r = self.agent.run({"crop": "不存在的作物XYZ", "symptom_description": "叶片发黄"})
        self.assertIn("signature", r)
        self.assertNotIn("PLACEHOLDER", json.dumps(r, ensure_ascii=False))

    def test_vision_graceful_when_unset(self):
        # 未配置视觉后端环境变量时应安全降级（返回 None，不抛异常，不触发网络）
        os.environ.pop("AGRI_VISION_URL", None)
        os.environ.pop("AGRI_VISION_KEY", None)
        self.assertIsNone(call_vision_backend("http://example/x.jpg", "番茄"))
        # 即便配置了端点，image_reference 为空也必须返回 None（不触发网络）
        os.environ["AGRI_VISION_URL"] = "http://127.0.0.1:9/nope"
        os.environ["AGRI_VISION_KEY"] = "fake"
        self.assertIsNone(call_vision_backend("", "番茄"))
        os.environ.pop("AGRI_VISION_URL", None)
        os.environ.pop("AGRI_VISION_KEY", None)


class TestNutritionAgent(unittest.TestCase):
    def setUp(self):
        self.agent = NutritionAgent()

    def test_no_placeholder_and_signature(self):
        r = self.agent.run({"crop": "番茄", "scene": "balcony", "container_volume_l": 10.0})
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("PLACEHOLDER", blob)
        self.assertTrue(r["signature"])
        self.assertEqual(len(r["constraints"]), 3)
        self.assertIn("phases", r["recommendation"])

    def test_leafy_keeps_nitrogen_at_harvest(self):
        r = self.agent.run({"crop": "生菜"})
        phases = r["recommendation"]["phases"]
        # 叶菜采收期应维持高氮（npk_repro 首项 > 15）
        harvest = phases[-1]
        self.assertIn("高氮", harvest["fertilizer"])
        self.assertTrue(r["evidence"]["data_loaded"])

    def test_fruiting_switches_to_high_potassium(self):
        r = self.agent.run({"crop": "番茄"})
        phases = r["recommendation"]["phases"]
        harvest = phases[-1]
        self.assertIn("高钾", harvest["fertilizer"])
        # 至少四个阶段，且采收期给出浓度/用量
        self.assertEqual(len(phases), 4)
        self.assertNotEqual(harvest["amount_guidance"], "—")

    def test_unknown_crop_safe_fallback(self):
        r = self.agent.run({"crop": "不存在的作物XYZ"})
        self.assertIn("signature", r)
        self.assertFalse(r["evidence"]["data_loaded"])
        self.assertNotIn("PLACEHOLDER", json.dumps(r, ensure_ascii=False))
        # 兜底仍给出 4 阶段方案
        self.assertEqual(len(r["recommendation"]["phases"]), 4)


class TestOrchestratorSkills(unittest.TestCase):
    """验证 orchestrator.call_skill 统一路由 + 技能目录。"""

    def setUp(self):
        self.orch = AgriOrchestrator()

    def test_call_skill_pest(self):
        r = self.orch.call_skill("pest_diagnose", {
            "crop": "番茄",
            "symptom_description": "叶片黄色斑点，背面白色粉状物，像白粉病",
        })
        self.assertNotIn("PLACEHOLDER", json.dumps(r, ensure_ascii=False))
        self.assertTrue(r["signature"])
        self.assertIn("diagnosis", r)
        self.assertIn("constraints", r)

    def test_call_skill_nutrition(self):
        r = self.orch.call_skill("nutrition_plan", {
            "crop": "番茄", "container_volume_l": 10.0,
        })
        self.assertNotIn("PLACEHOLDER", json.dumps(r, ensure_ascii=False))
        self.assertTrue(r["signature"])
        self.assertEqual(len(r["recommendation"]["phases"]), 4)

    def test_unknown_skill_raises(self):
        with self.assertRaises(ValueError):
            self.orch.call_skill("not_a_skill", {"crop": "番茄"})

    def test_list_skills_includes_on_demand(self):
        skills = self.orch.list_skills()
        ids = {s["id"] for s in skills}
        self.assertIn("pest_diagnose", ids)
        self.assertIn("nutrition_plan", ids)
        for s in skills:
            if s["id"] in ("pest_diagnose", "nutrition_plan"):
                self.assertTrue(s["implemented"])
                self.assertEqual(s["callable_via"], "call_skill")


if __name__ == "__main__":
    unittest.main(verbosity=2)
