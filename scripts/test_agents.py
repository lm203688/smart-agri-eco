#!/usr/bin/env python3
"""
智慧农业生态 · 单元测试（仅标准库 unittest，零第三方依赖）

运行：
    python -m unittest scripts.test_agents -v
    # 或
    python scripts/test_agents.py

覆盖：
    - 四 Agent 流水线：杭州→亚热带湿润带、无 PLACEHOLDER、rubric 聚合正确
    - 分区覆盖缺口：迪拜（热漠）/拉萨（高原）必须显式拒答，不得静默归入亚热带湿润
    - CropAgent 候选数 / EcoAgent 预算门控
    - Trust Layer 可复现证书 rubric 全通过
    - flywheel 反馈闭环：校准分随反馈变化（数据文件备份/重定向，不污染 seed 数据）
    - 作物库数据完整性：calibrated 标记必须有证据、反馈日志不得含合成样本
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.pest_agent import PestAgent  # noqa: E402
from agent.nutrition_agent import NutritionAgent  # noqa: E402
from agent.vision import call_vision_backend  # noqa: E402
from agent import soil_profile as sp  # noqa: E402
from core.trust_layer import issue_certificate  # noqa: E402
import engine.flywheel as fw  # noqa: E402

CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

BASE_REQ = {
    "lat": 30.2741, "lon": 120.1551,
    "scene": "balcony", "floor": 15, "orientation": "south",
    "purpose": "食用", "space_sqm": 1.5,
    "difficulty": "beginner", "budget_cny": 500,
}


# ---------------------------------------------------------------------------
# 模块级写盘隔离
# ---------------------------------------------------------------------------
# run_pipeline 自 B1/B2 起会写长期记忆与检索索引。本模块早于这两个能力写成，
# 没有 per-test 隔离——若不在此重定向，每次跑测试都会往 data/long_term_memory.json
# 写合成记录，最终被当成真实记忆提交（已踩过：一次跑出 13 条脏数据）。
# AGRI_MEMORY_SYNTHETIC=1 让漏网的合成记录带 [unittest] 标记，由 CI 门禁拦下。
_TMP = None
_ENV_SAVED = {}


def setUpModule():
    global _TMP
    _TMP = tempfile.mkdtemp(prefix="agri_test_agents_")
    for k, v in (("AGRI_LONG_TERM_MEMORY", os.path.join(_TMP, "mem.json")),
                 ("AGRI_SEARCH_INDEX", os.path.join(_TMP, "idx.db")),
                 ("AGRI_MEMORY_SYNTHETIC", "1")):
        _ENV_SAVED[k] = os.environ.get(k)
        os.environ[k] = v


def tearDownModule():
    for k, v in _ENV_SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    if _TMP:
        shutil.rmtree(_TMP, ignore_errors=True)


class TestZoneCoverageGap(unittest.TestCase):
    """守住「已知覆盖缺口 → 显式拒答」，不许再静默给出错误分区的种植方案。

    背景（2026-09-23）：启发式把迪拜/拉萨吞进最后的「亚热带湿润」默认分支，
    运行时 rubric≈0.95、recommendation 还写「环境条件适宜」——错得高置信且
    对调用方完全静默（迪拜实际是热漠：年均约 28°C、年降水约 100mm，按湿热区
    参数种必然失败）。现改为返回真实气候类名（hot_arid / highland），分区库
    没有该区 → 走既有降级路径显式失败（拒答优于错答）。
    """

    def setUp(self):
        from agent.climate_agent import ClimateAgent
        self.ca = ClimateAgent()

    def _out(self, lat, lon):
        return self.ca.match_zone(lat, lon)

    def test_dubai_is_hot_arid_gap_not_humid(self):
        out = self._out(25.2048, 55.2708)  # 迪拜
        ev = out["evidence"]
        self.assertEqual(ev["zone_id"], "hot_arid")
        # 回归守卫：这曾是静默错判的目标值
        self.assertNotEqual(ev["zone_id"], "subtropical_wet")
        self.assertEqual(ev.get("coverage_gap"), "hot_arid")
        # 不再高置信，且说明原因（而不是空泛的「数据缺失」）
        self.assertEqual(out["confidence"]["rubric_score"], 0.0)
        self.assertIn("未建模", out["confidence"]["confidence_note"])
        # 必须给出可行动的替代路径，而不是只报错
        self.assertIn("箱体", out["recommendation"])

    def test_lhasa_is_highland_gap(self):
        out = self._out(29.6520, 91.1721)  # 拉萨
        self.assertEqual(out["evidence"]["zone_id"], "highland")
        self.assertEqual(out["evidence"].get("coverage_gap"), "highland")
        self.assertEqual(out["confidence"]["rubric_score"], 0.0)

    def test_modeled_cities_unchanged(self):
        """缺口识别只允许改变原本落到默认分支的点，不得动已归类正确的坐标。"""
        cases = [
            (1.3521, 103.8198, "tropical_rainforest"),     # 新加坡
            (30.2741, 120.1551, "subtropical_wet"),        # 杭州
            (23.1291, 113.2644, "subtropical_wet"),        # 广州
            (30.5728, 104.0668, "subtropical_wet"),        # 成都（守住高原盒 lon≤100 不吃掉它）
            (39.9042, 116.4074, "temperate_continental"),  # 北京
            (43.8256, 87.6168, "arid"),                    # 乌鲁木齐
            (34.0522, -118.2437, "mediterranean"),         # 洛杉矶
            (55.7558, 37.6173, "subarctic"),               # 莫斯科
        ]
        for lat, lon, want in cases:
            got = self._out(lat, lon)["evidence"]["zone_id"]
            self.assertEqual(got, want, f"({lat},{lon}) 期望 {want}，实得 {got}")

    def test_gap_is_hard_flagged_by_verifier(self):
        """缺口必须在校验层判红（硬标记），不能只是软提示。"""
        from agent.orchestrator import verify_agent_output
        out = self._out(25.2048, 55.2708)
        v = verify_agent_output("ClimateAgent", out)
        self.assertFalse(v["ok"], "未建模分区必须校验不通过")
        zone_check = [c for c in v["checks"] if c["name"] == "zone_id_known"]
        self.assertEqual(len(zone_check), 1)
        self.assertFalse(zone_check[0]["ok"])

    def test_zone_consistency_eval_all_correct(self):
        """评测样本的真值：10 个样本的气候类分类应全对（含两个缺口类）。"""
        import engine.eval as ev
        with open(os.path.join(ROOT, "data", "eval", "zone_checks.json"),
                  encoding="utf-8") as f:
            checks = json.load(f)
        r = ev.eval_zone_consistency(checks, self.ca)
        self.assertEqual(r["total"], 10)
        self.assertEqual(r["rate"], 1.0, f"不一致样本: {r['mismatches']}")


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

    def test_feedback_dry_run_writes_nothing(self):
        """回归：demo 演示模式下 record_feedback 必须只算不写，防污染真实数据。

        2026-09-17 实踩：前端冒烟 3 次把 note="smoke" 写进真实 feedback_log.json，
        并把 crop_adapt_db.json 里小白菜的 adapt_score 从 0.96 伪校准成 0.951。
        这两个文件不受 git 跟踪，git status 恒为 clean，污染完全静默。
        """
        import hashlib
        import engine.flywheel as fw

        fb = os.path.join(ROOT, "data", "feedback_log.json")
        db = os.path.join(ROOT, "data", "crop_adapt_db.json")
        sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
        fb_before, db_before = sha(fb), sha(db)

        saved = dict(os.environ)
        os.environ["AGRI_FEEDBACK_DRY_RUN"] = "1"
        try:
            r = fw.record_feedback("subtropical_wet", "小白菜",
                                   survival_rate=1.0, yield_rating=4.5,
                                   user_rating=4.5, note="unittest")
            self.assertTrue(r.get("dry_run"), r)
            # 计算结果仍在（演示前端还能看到「会校准成多少」）
            self.assertIsNotNone(r.get("after"))
        finally:
            os.environ.clear()
            os.environ.update(saved)

        self.assertEqual(sha(fb), fb_before, "dry-run 仍写了 feedback_log")
        self.assertEqual(sha(db), db_before, "dry-run 仍写了 crop_adapt_db")


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

    def test_nutrition_short_cycle_no_day_inversion(self):
        """回归：短周期（20 天小容器叶菜）曾出现 phases[3].day_range=[22,20] 倒挂。

        修复点 agent/nutrition_agent._phase_boundaries：比例切分 + 最小间隔 +
        上限钳制 + 回向级联，对任意 gd>=20 保证段内 start<=end、段间连续、
        末段终止于 gd。
        """
        from agent.nutrition_agent import _phase_boundaries, _build_fert_phases, PROFILES
        prof = PROFILES["leafy"]
        for gd in (20, 21, 23, 25, 30, 45, 60, 90, 120, 180):
            sow_end, seedling_end, preharvest = _phase_boundaries(gd)
            spans = [(1, sow_end), (sow_end + 1, seedling_end),
                     (seedling_end + 1, preharvest), (preharvest + 1, gd)]
            for i, (s, e) in enumerate(spans):
                self.assertLessEqual(s, e, "gd=%d 第 %d 段倒挂 %s" % (gd, i + 1, spans))
                self.assertLessEqual(e, gd, "gd=%d 第 %d 段越界 %s" % (gd, i + 1, spans))
            for a, b in zip(spans, spans[1:]):
                self.assertEqual(a[1] + 1, b[0], "gd=%d 段间不连续 %s" % (gd, spans))

        # 端到端：plan() 走 orchestrator 的 20 天方案不得出现倒挂
        r = self.orch.call_skill("nutrition_plan", {
            "crop": "生菜", "growth_days": 20, "container_volume_l": 3.0,
        })
        phases = r["recommendation"]["phases"]
        self.assertEqual(len(phases), 4)
        for i, p in enumerate(phases):
            s, e = p["day_range"]
            self.assertLessEqual(s, e, "第 %d 段倒挂 %s" % (i + 1, p["day_range"]))
            self.assertLessEqual(e, 20, "第 %d 段越出 20 天周期 %s" % (i + 1, p["day_range"]))
        self.assertEqual(phases[-1]["day_range"][1], 20)

    def test_nutrition_phase_guard_raises_on_inversion(self):
        """防御性后置校验：人为构造倒挂边界时必须显式抛错，而非静默流出。"""
        from agent.nutrition_agent import _build_fert_phases, PROFILES
        import agent.nutrition_agent as na
        orig = na._phase_boundaries
        try:
            na._phase_boundaries = lambda g: (30, 10, 5)  # 故意乱序
            with self.assertRaises(ValueError):
                _build_fert_phases(20, PROFILES["leafy"], 150, None, True)
        finally:
            na._phase_boundaries = orig

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


class TestSeasonAgent(unittest.TestCase):
    """验证 SeasonAgent（B1 物候推演 + B2 霜冻锚定播期窗口）。"""

    BEIJING = [-4.0, -1.0, 5.0, 14.0, 20.0, 25.0, 27.0, 26.0, 21.0, 14.0, 5.0, -2.0]

    def setUp(self):
        self.orch = AgriOrchestrator()

    def test_planting_window_feasible(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "planting_window", "monthly_mean_c": self.BEIJING,
            "crops": ["马铃薯"],
        })
        self.assertTrue(r["available"])
        w = r["windows"][0]
        self.assertTrue(w["feasible"])
        self.assertIsNotNone(w["latest_sow"])
        self.assertGreater(w["sow_window_days"], 0)

    def test_frost_free_period_sane(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "planting_window", "monthly_mean_c": self.BEIJING, "crops": ["大豆"],
        })
        self.assertGreater(r["frost_free"]["length_days"], 200)

    def test_year_round_freeze_unavailable(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "planting_window", "monthly_mean_c": [-20.0] * 12, "crops": ["马铃薯"],
        })
        self.assertFalse(r["available"])

    def test_tropical_year_round(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "planting_window", "monthly_mean_c": [26.0] * 12, "crops": ["马铃薯"],
        })
        self.assertTrue(r["frost_free"]["year_round"])

    def test_stage_days(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "stage_days", "crop": "马铃薯", "mean_temp_c": 18,
        })
        self.assertTrue(r["available"])
        self.assertGreater(r["maturity_days_from_sow"], r["emergence_days"])

    def test_uncovered_crop_graceful(self):
        r = self.orch.call_skill("season_advisory", {
            "mode": "stage_days", "crop": "番茄", "mean_temp_c": 20,
        })
        self.assertFalse(r["available"])
        self.assertIn("potato", r["covered_crops"])

    def test_bad_mode_graceful(self):
        r = self.orch.call_skill("season_advisory", {"mode": "nope"})
        self.assertFalse(r["available"])

    def test_confidence_not_overclaimed(self):
        """积温推演不得伪装成实测结论：置信度须为 medium 而非 high。"""
        r = self.orch.call_skill("season_advisory", {
            "mode": "planting_window", "monthly_mean_c": self.BEIJING, "crops": ["小麦"],
        })
        self.assertEqual(r["confidence"]["level"], "medium")
        self.assertLessEqual(r["confidence"]["rubric_score"], 0.7)

    def test_registry_entry(self):
        skills = self.orch.list_skills()
        ids = {s["id"] for s in skills}
        self.assertIn("season_advisory", ids)
        for s in skills:
            if s["id"] == "season_advisory":
                self.assertTrue(s["implemented"])
                self.assertEqual(s["callable_via"], "call_skill")


class TestSoilProfile(unittest.TestCase):
    """验证土壤查询的降级路径与诚实标注（SoilGrids 从本机不可靠，离线必须兜住）。"""

    def test_offline_fallback_is_zone_level(self):
        r = sp.get_soil_profile(lat=30.2741, lon=120.1551, online=False)
        self.assertEqual(r["resolution"], "zone")
        self.assertEqual(r["confidence"], "low")
        self.assertIn("global_zones", r["source"])
        self.assertTrue(r["soil"]["ph_range"])

    def test_zone_values_are_real(self):
        """离线值必须来自 global_zones.json 的真实字段，不是占位。"""
        r = sp.get_soil_profile(zone_id="subtropical_wet", online=False)
        self.assertEqual(r["soil"]["ph_range"], [5.5, 7.0])
        r2 = sp.get_soil_profile(zone_id="arid", online=False)
        self.assertEqual(r2["soil"]["ph_range"], [7.0, 9.0])

    def test_unknown_zone_unavailable_not_fabricated(self):
        r = sp.get_soil_profile(zone_id="atlantis", online=False)
        self.assertEqual(r["resolution"], "unavailable")
        self.assertEqual(r["soil"], {})

    def test_ph_fit_suitable_and_unsuitable(self):
        self.assertEqual(sp.ph_fit([5.5, 7.0], [6.0, 7.0])["level"], "suitable")
        self.assertEqual(sp.ph_fit([7.0, 9.0], [5.0, 6.0])["level"], "unsuitable")

    def test_crop_ph_fit_attached(self):
        r = sp.get_soil_profile(zone_id="subtropical_wet", crop="小白菜", online=False)
        self.assertIn("crop_ph_fit", r)
        self.assertIn(r["crop_ph_fit"]["level"],
                      ("suitable", "marginal", "narrow", "unsuitable"))

    def test_online_probe_never_raises_and_uses_correct_host(self):
        """在线探测无论成败都不得抛异常；主机必须是 rest.isric.org（api.isric.org 不存在）。"""
        probe = sp.probe_soilgrids(120.15, 30.27, timeout=3)
        self.assertIn("available", probe)
        self.assertIn("rest.isric.org", probe["url"])
        self.assertNotIn("api.isric.org", probe["url"])

    def test_limitations_present(self):
        r = sp.get_soil_profile(zone_id="temperate_continental", online=False)
        self.assertTrue(r["limitations"])
        self.assertTrue(any("分区" in x for x in r["limitations"]))


class TestPresetCitiesSingleSource(unittest.TestCase):
    """预设城市清单必须是单一数据源（data/preset_cities.json）。

    背景：清单曾在 app/demo_server.py 与 mcp/server.py 各硬编码一份完全相同的
    副本 → 必然漂移（改一处忘另一处，前端与 MCP 给出不同城市集且不报错）。
    2026-09-23 收敛到 data/preset_cities.json + agent/preset_cities.py 唯一读取
    入口。本类锁定：两侧消费方与文件内容逐字节一致，且降级副本也不得漂移。
    """

    CITIES_FILE = os.path.join(ROOT, "data", "preset_cities.json")

    def _cities_in_file(self):
        with open(self.CITIES_FILE, encoding="utf-8") as f:
            return json.load(f)["cities"]

    @staticmethod
    def _load(path, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_file_schema_complete(self):
        """每个城市必须有 name/lat/lon/zone/modeled，且坐标合法。"""
        cities = self._cities_in_file()
        self.assertEqual(len(cities), 12)
        for c in cities:
            for k in ("name", "lat", "lon", "zone", "modeled"):
                self.assertIn(k, c, f"{c.get('name')} 缺字段 {k}")
            self.assertIsInstance(c["lat"], (int, float))
            self.assertIsInstance(c["lon"], (int, float))
            self.assertIsInstance(c["modeled"], bool)
            self.assertTrue(-90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180)

    def test_both_consumers_read_the_single_source(self):
        """demo 站点与 MCP server 必须返回与文件完全一致的城市清单。"""
        from agent.preset_cities import load_preset_cities
        expected = load_preset_cities()
        self.assertEqual(expected, self._cities_in_file())

        demo = self._load(os.path.join(ROOT, "app", "demo_server.py"), "demo_server")
        mcp_srv = self._load(os.path.join(ROOT, "mcp", "server.py"), "mcp_server")
        self.assertEqual(demo.PRESET_CITIES, self._cities_in_file(),
                         "demo_server.PRESET_CITIES 与 data/preset_cities.json 不一致")
        self.assertEqual(mcp_srv._PRESET_CITIES, self._cities_in_file(),
                         "mcp.server._PRESET_CITIES 与 data/preset_cities.json 不一致")

    def test_no_residual_hardcoded_city_block(self):
        """两个消费方文件里不得再出现硬编码城市字典（防副本回归）。"""
        for rel in ("app/demo_server.py", "mcp/server.py"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn('"name": "杭州"', src,
                             f"{rel} 疑似重新硬编码了城市清单（应读 data/preset_cities.json）")
            self.assertIn("load_preset_cities", src, f"{rel} 未接入单一数据源")

    def test_fallback_copy_does_not_drift(self):
        """降级副本必须与主文件一致——否则文件缺失时会静默给出不同的城市集。"""
        from agent.preset_cities import _FALLBACK_CITIES
        self.assertEqual(_FALLBACK_CITIES, self._cities_in_file())

    def test_missing_file_degrades_without_losing_gap_semantics(self):
        """数据文件缺失时不崩，且 coverage_gap 语义（modeled=False）不随之消失。"""
        from agent.preset_cities import load_preset_cities
        cities = load_preset_cities(os.path.join(ROOT, "no_such_cities.json"))
        self.assertEqual(len(cities), 12)
        unmodeled = [c["name"] for c in cities if not c["modeled"]]
        self.assertEqual(sorted(unmodeled), ["拉萨", "迪拜"],
                         "降级副本丢失了未建模城市标记（coverage_gap 语义被降级吞掉）")

    def test_unmodeled_cities_match_eval_truth(self):
        """清单里 modeled=False 的城市，必须与 eval 真值登记的未建模类一致。"""
        from agent.preset_cities import load_preset_cities
        cities = {c["name"]: c for c in load_preset_cities()}
        self.assertFalse(cities["拉萨"]["modeled"])
        self.assertFalse(cities["迪拜"]["modeled"])
        with open(os.path.join(ROOT, "data", "eval", "zone_checks.json"), encoding="utf-8") as f:
            checks = json.load(f)
        samples = checks["samples"] if isinstance(checks, dict) else checks
        eval_unmodeled = {(s.get("lat"), s.get("lon")) for s in samples
                          if s.get("modeled") is False}
        for name in ("拉萨", "迪拜"):
            c = cities[name]
            self.assertIn((c["lat"], c["lon"]), eval_unmodeled,
                          f"{name} 标记为未建模，但 eval 真值未登记")


if __name__ == "__main__":
    unittest.main(verbosity=2)
