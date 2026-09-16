#!/usr/bin/env python3
"""
智慧农业生态 · 引擎 v2 单元测试（仅标准库 unittest，零第三方依赖）

覆盖 A1-A7 借鉴落地项：
    A1  engine/rsi.py            —— RSI 五级自主权分级 + HCI 门禁闭合率
    A2  scripts/harness_sync.py  —— Git-native harness 清单（声明区/观测区分离）
    A3  agent/orchestrator.py    —— Executor/Verifier 分离 + Session 幂等恢复
    A4  engine/context_compact.py—— 证据保留式压缩 + 动作融合（opt-in）
    A5  engine/skill_factory.py  —— CLS 安全分级（S/A/B/C/D）
    A6  engine/skill_factory.py  —— YAGNI 精简
    A7  engine/skill_factory.py  —— Anti-Rot 腐化检查

运行：
    python scripts/test_engine_v2.py
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.orchestrator import (AgriOrchestrator, verify_agent_output,  # noqa: E402
                                verify_pipeline_result)
import engine.rsi as rsi_mod  # noqa: E402
import engine.context_compact as cc  # noqa: E402
import engine.skill_factory as sf  # noqa: E402
import engine.eval as ev  # noqa: E402

BASE_REQ = {
    "lat": 30.2741, "lon": 120.1551,
    "scene": "balcony", "floor": 15, "orientation": "south",
    "purpose": "食用", "space_sqm": 1.5,
    "difficulty": "beginner", "budget_cny": 500,
}


# ---------------------------------------------------------------------------
# 模块级写盘隔离
# ---------------------------------------------------------------------------
# 与 test_agents 同一问题：run_pipeline 自 B1/B2 起会写长期记忆与检索索引，
# 本模块（A 档时期）没有 per-test 隔离。一次跑出 7 条合成记录写进真实记忆库。
# AGRI_MEMORY_SYNTHETIC=1 让漏网的合成记录带 [unittest] 标记，由 CI 门禁拦下。
_TMP = None
_ENV_SAVED = {}


def setUpModule():
    global _TMP
    _TMP = tempfile.mkdtemp(prefix="agri_test_v2_")
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


class TestRsiGates(unittest.TestCase):
    """A1：自主权分级必须锚定真实产物，不能靠重测自我满足。"""

    def setUp(self):
        # 隔离：临时数据目录 + 临时 harness 清单，绝不污染仓库
        self.tmp = tempfile.mkdtemp(prefix="agri_rsi_")
        self.old_crop = os.environ.get("AGRI_CROP_DB")
        self.old_fb = os.environ.get("AGRI_FEEDBACK_LOG")
        self.old_manifest = rsi_mod._HARNESS_MANIFEST
        self.crop_db = os.path.join(self.tmp, "crop_adapt_db.json")
        self.feedback = os.path.join(self.tmp, "feedback_log.json")
        self.manifest = os.path.join(self.tmp, "manifest.json")
        os.environ["AGRI_CROP_DB"] = self.crop_db
        os.environ["AGRI_FEEDBACK_LOG"] = self.feedback
        rsi_mod._HARNESS_MANIFEST = self.manifest

    def tearDown(self):
        for k, v in (("AGRI_CROP_DB", self.old_crop),
                     ("AGRI_FEEDBACK_LOG", self.old_fb)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        rsi_mod._HARNESS_MANIFEST = self.old_manifest
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_crop_db(self, zones):
        with open(self.crop_db, "w", encoding="utf-8") as f:
            json.dump({"zones": zones}, f, ensure_ascii=False)

    def _write_feedback(self, entries):
        with open(self.feedback, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)

    def test_empty_evidence_is_B0(self):
        rep = rsi_mod.report()
        self.assertEqual(rep["autonomy"]["level"], "B0")
        self.assertEqual(rep["hci"]["hci"], 0.0)
        self.assertEqual(rep["hci"]["closed"], 0)
        self.assertEqual(rep["hci"]["total"], len(rsi_mod.ALL_GATES))

    def test_synthetic_feedback_excluded(self):
        """单测/demo 样本不得计为真实回流证据。"""
        self._write_feedback([
            {"note": "unittest", "zone_id": "z", "crop": "c"},
            {"note": "[demo] 冒烟", "zone_id": "z", "crop": "c"},
            {"note": "真实用户：杭州阳台", "zone_id": "z", "crop": "c"},
        ])
        state = rsi_mod.project_state()
        self.assertEqual(state["real_feedback_entries"], 1)
        self.assertEqual(state["synthetic_feedback_excluded"], 2)
        self.assertTrue(rsi_mod.evaluate_gates(state)[rsi_mod.GATE_FEEDBACK]["closed"])

    def _write_execution_log(self, entries):
        p = os.path.join(self.tmp, "execution_log.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        return p

    def test_calibration_gate_threshold(self):
        self._write_feedback([{"note": "真实用户", "zone_id": "z", "crop": "c"}])
        g = rsi_mod.evaluate_gates()
        self.assertFalse(g[rsi_mod.GATE_CALIBRATION]["closed"])
        self._write_crop_db({"subtropical_wet": {"crops": [
            {"crop": "生菜", "calibrated": True,
             "measured_calibration": {"n_feedback": 1}}]}})
        g = rsi_mod.evaluate_gates()
        self.assertTrue(g[rsi_mod.GATE_CALIBRATION]["closed"])
        self.assertFalse(g[rsi_mod.GATE_GENERALIZATION]["closed"])
        self.assertIn("3", g[rsi_mod.GATE_GENERALIZATION]["gap"])

    def test_calibration_flag_without_evidence_not_counted(self):
        """calibrated:true 但无 measured_calibration 不算证据（防假标记）。"""
        self._write_crop_db({"z": {"crops": [
            {"crop": "生菜", "calibrated": True}]}})
        state = rsi_mod.project_state()
        self.assertEqual(state["calibrated_crops"], 0)

    def test_generalization_needs_three_crops(self):
        """L3 需要 execution + feedback + calibration 三条门禁都闭合。"""
        self._write_feedback([{"note": "真实用户", "zone_id": "z", "crop": "c"}])
        old_exec = rsi_mod._EXECUTION_LOG
        rsi_mod._EXECUTION_LOG = self._write_execution_log([{"recipe_id": "r1"}])
        try:
            self._write_crop_db({"z": {"crops": [
                {"crop": f"c{i}", "calibrated": True,
                 "measured_calibration": {"n_feedback": 1}} for i in range(3)]}})
            rep = rsi_mod.report()
            self.assertTrue(rep["gates"][rsi_mod.GATE_GENERALIZATION]["closed"])
            self.assertEqual(rep["autonomy"]["level"], "L3")
        finally:
            rsi_mod._EXECUTION_LOG = old_exec

    def test_l1_requires_execution_and_feedback(self):
        """只有反馈、没有执行记录 → 不达标 L1（防止「自评」冒充闭环）。"""
        self._write_feedback([{"note": "真实用户", "zone_id": "z", "crop": "c"}])
        rep = rsi_mod.report()
        self.assertEqual(rep["autonomy"]["level"], "B0")
        self.assertEqual(rep["autonomy"]["per_level"]["L1"]["open_gates"],
                         [rsi_mod.GATE_EXECUTION])

    def test_meta_gate_not_self_fulfilling_by_history(self):
        """历史快照增长但 gate_version 未 bump、hci 未变化 → L5 仍不闭合。"""
        self._write_feedback([{"note": "真实用户", "zone_id": "z", "crop": "c"}])
        self._write_crop_db({"z": {"crops": [
            {"crop": f"c{i}", "calibrated": True,
             "measured_calibration": {"n_feedback": 1}} for i in range(3)]}})
        with open(self.manifest, "w", encoding="utf-8") as f:
            json.dump({"version": "2.0.0", "rsi": {"gate_version": "1.0",
                        "history": [{"ts": "a", "hci": 0.5},
                                    {"ts": "b", "hci": 0.5},
                                    {"ts": "c", "hci": 0.5}]}}, f)
        g = rsi_mod.evaluate_gates()
        self.assertFalse(g[rsi_mod.GATE_META]["closed"])
        self.assertIn("反复重测", g[rsi_mod.GATE_META]["gap"])

    def test_meta_gate_requires_real_improvement(self):
        """gate_version bump + hci 曾变化 → L5 可闭合（需六门禁全闭合）。"""
        self._write_feedback([{"note": "真实用户", "zone_id": "z", "crop": "c"}])
        self._write_crop_db({"z": {"crops": [
            {"crop": f"c{i}", "calibrated": True,
             "measured_calibration": {"n_feedback": 1}} for i in range(3)]}})
        old_exec = rsi_mod._EXECUTION_LOG
        rsi_mod._EXECUTION_LOG = self._write_execution_log([{"recipe_id": "r1"}])
        # skill_generation 门禁：临时注册表中放一个被编排层引用的自动生成技能
        old_skills_dir = rsi_mod._SKILLS_DIR
        reg = os.path.join(self.tmp, "registry")
        os.makedirs(reg, exist_ok=True)
        with open(os.path.join(reg, "pest_diagnose.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"id": "pest_diagnose", "auto_generated": True}, f)
        rsi_mod._SKILLS_DIR = reg
        try:
            with open(self.manifest, "w", encoding="utf-8") as f:
                json.dump({"version": "2.0.0", "rsi": {
                    "gate_version": "2.0",
                    "history": [{"ts": "a", "hci": 0.167},
                                {"ts": "b", "hci": 0.333}]}}, f)
            rep = rsi_mod.report()
            for gname in rsi_mod.ALL_GATES:
                self.assertTrue(rep["gates"][gname]["closed"],
                                f"{gname} 未闭合: {rep['gates'][gname]['gap']}")
            self.assertEqual(rep["autonomy"]["level"], "L5")
            self.assertEqual(rep["hci"]["hci"], 1.0)
        finally:
            rsi_mod._EXECUTION_LOG = old_exec
            rsi_mod._SKILLS_DIR = old_skills_dir

    def test_hci_bounded(self):
        rep = rsi_mod.report()
        self.assertGreaterEqual(rep["hci"]["hci"], 0.0)
        self.assertLessEqual(rep["hci"]["hci"], 1.0)
        self.assertEqual(rep["hci"]["closed"] + len(rep["hci"]["open_gates"]),
                         rep["hci"]["total"])

    def test_eval_hci_wired_into_run_all(self):
        """A1 北极星必须接入 eval.run_all()，不能只写在报告里。"""
        r = ev.run_all()
        self.assertIn("hci", r)
        self.assertEqual(r["hci"]["status"], "IMPLEMENTED")
        self.assertIn("autonomy_level", r["hci"])
        self.assertIn(r["hci"]["autonomy_level"], ("B0", "L1", "L2", "L3", "L4", "L5"))


class TestHarnessSync(unittest.TestCase):
    """A2：清单由代码反算；声明区门禁、观测区仅信息。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri_harness_")
        self.old_path = rsi_mod._HARNESS_MANIFEST

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _sync(self):
        """加载 harness_sync.py 为真实模块对象。

        注意：不用 runpy.run_path——它返回 globals 的**副本**，
        改返回值不会影响函数内部的同名全局变量（实测踩坑）。
        """
        import importlib.util
        p = os.path.join(ROOT, "scripts", "harness_sync.py")
        mod_name = "harness_sync_under_test"
        sys.modules.pop(mod_name, None)
        spec = importlib.util.spec_from_file_location(mod_name, p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        # 记录真实清单路径，测试重定向后可还原（不污染仓库）
        mod.ORIGINAL_MANIFEST_PATH = mod.MANIFEST_PATH
        return mod

    def test_manifest_build_matches_code(self):
        h = self._sync()
        m = h.build_manifest()
        self.assertEqual(m["mcp"]["tool_count"], len(m["mcp"]["tools"]))
        self.assertGreaterEqual(m["mcp"]["tool_count"], 9)
        # 工具名必须来自 mcp/server.py 的真实定义（不手写）
        for t in m["mcp"]["tools"]:
            self.assertTrue(t.startswith("agri_"))

    def test_env_vars_introspected_not_hardcoded(self):
        h = self._sync()
        names = h._env_vars()
        self.assertIn("AGRI_VISION_URL", names)
        self.assertIn("AGRI_CROP_DB", names)
        # 回归守卫：曾经硬编码了不存在的 AGRI_SOIL_TIMEOUT
        self.assertNotIn("AGRI_SOIL_TIMEOUT", names)

    def test_declared_vs_observed_separation(self):
        """观测区（rsi.*）不得参与漂移门禁，否则 init 后必然假漂移。"""
        h = self._sync()
        self.assertIn("rsi", h.OBSERVED_SECTIONS)
        self.assertNotIn("rsi", h.DECLARED_SECTIONS)
        self.assertIn("mcp", h.DECLARED_SECTIONS)

    def test_init_then_check_has_no_false_drift(self):
        """真实回归：曾出现 init 后立刻 check 报漂移（自指字段导致）。"""
        h = self._sync()
        h.MANIFEST_PATH = os.path.join(self.tmp, "manifest.json")
        try:
            self.assertEqual(h.cmd_init(), 0)
            self.assertTrue(os.path.exists(h.MANIFEST_PATH))
            self.assertEqual(h.cmd_check(), 0, "init 后 check 不应报漂移")
            self.assertEqual(h.cmd_dry_run(), 0)
        finally:
            h.MANIFEST_PATH = h.ORIGINAL_MANIFEST_PATH

    def test_push_never_commits(self):
        """push 子命令必须拒绝提交并指向既有 gh_push.py 链路。"""
        h = self._sync()
        self.assertEqual(h.cmd_push(), 0)

    def test_digest_ignores_timestamp(self):
        h = self._sync()
        a = h.build_manifest()
        b = json.loads(json.dumps(a))
        b["generated_at"] = "1999-01-01T00:00:00"
        self.assertEqual(h._digest(a), h._digest(b))

    def test_drift_detected_on_real_change(self):
        """人为改 manifest 后 check 必须报红。"""
        h = self._sync()
        h.MANIFEST_PATH = os.path.join(self.tmp, "manifest.json")
        try:
            h.cmd_init()
            with open(h.MANIFEST_PATH, "r", encoding="utf-8") as f:
                m = json.load(f)
            m["mcp"]["tool_count"] = 99  # 篡改
            with open(h.MANIFEST_PATH, "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False)
            self.assertEqual(h.cmd_check(), 1, "篡改后 check 应报红")
        finally:
            h.MANIFEST_PATH = h.ORIGINAL_MANIFEST_PATH


class TestContextCompact(unittest.TestCase):
    """A4：压缩必须证据保留、默认关闭、动作融合不改变语义顺序。"""

    def test_reduce_preserves_evidence_refs(self):
        payload = {"items": [{"i": i, "note": "内容" * 40} for i in range(10)]}
        out = cc.reduce_output(payload, max_items=3)
        folded = [x for x in out["payload"]["items"] if x.get("__folded")]
        self.assertEqual(len(folded), 1)
        self.assertEqual(folded[0]["n"], 7)
        self.assertEqual(len(folded[0]["evidence_refs"]), 7)
        # 指纹可反查
        for ref, dropped in zip(folded[0]["evidence_refs"], payload["items"][3:]):
            self.assertEqual(ref, cc.digest_of(dropped))

    def test_reduce_reports_real_reduction(self):
        payload = {"items": [{"i": i, "note": "内容" * 40} for i in range(10)]}
        out = cc.reduce_output(payload, max_items=3)
        a = out[cc.REASONS_KEY]
        self.assertGreater(a["reduction_ratio"], 0.0)
        self.assertLess(a["compressed_chars"], a["original_chars"])
        self.assertGreater(a["folded_items"], 0)

    def test_reduce_small_payload_not_folded(self):
        payload = {"items": [1, 2, 3]}
        out = cc.reduce_output(payload, max_items=3)
        self.assertEqual(out["payload"]["items"], [1, 2, 3])
        self.assertEqual(out[cc.REASONS_KEY]["folded_items"], 0)

    def test_digest_stable(self):
        self.assertEqual(cc.digest_of({"a": 1, "b": 2}),
                         cc.digest_of({"b": 2, "a": 1}))
        self.assertNotEqual(cc.digest_of({"a": 1}), cc.digest_of({"a": 2}))

    def test_fuse_merges_adjacent_same_type(self):
        actions = [
            {"act_type": "water", "target": "A", "amount_ml": 200},
            {"act_type": "water", "target": "B", "amount_ml": 150},
            {"act_type": "light", "target": "A", "minutes": 8},
        ]
        out = cc.fuse_actions(actions)
        self.assertEqual(out["fusion"]["merged"], 1)
        self.assertEqual(len(out["actions"]), 2)
        water = out["actions"][0]
        self.assertEqual(water["amount_ml"], 350)
        self.assertEqual(water["targets"], ["A", "B"])
        self.assertEqual(len(water["__digests"]), 2)
        self.assertEqual(water["__fused_count"], 2)

    def test_fuse_does_not_merge_across_different_types(self):
        """非相邻同类动作不得跨段合并（否则会改变下发顺序语义）。"""
        actions = [
            {"act_type": "water", "target": "A", "amount_ml": 200},
            {"act_type": "light", "target": "A", "minutes": 8},
            {"act_type": "water", "target": "B", "amount_ml": 100},
        ]
        out = cc.fuse_actions(actions)
        self.assertEqual(out["fusion"]["merged"], 0)
        self.assertEqual(len(out["actions"]), 3)

    def test_fuse_opt_in_disabled(self):
        actions = [{"act_type": "water", "target": "A"},
                   {"act_type": "water", "target": "B"}]
        out = cc.fuse_actions(actions, fuse=False)
        self.assertEqual(out["fusion"]["enabled"], False)
        self.assertEqual(len(out["actions"]), 2)
        self.assertEqual(out["fusion"]["merged"], 0)

    def test_fuse_empty_safe(self):
        out = cc.fuse_actions([])
        self.assertEqual(out["actions"], [])
        self.assertEqual(out["fusion"]["output_count"], 0)


class TestClsGrading(unittest.TestCase):
    """A5：CLS 分级必须机读可复算，且不得中文关键词假阳。"""

    def test_local_readonly_with_boundary_is_S(self):
        s = {"description": "基于本地 data/ 目录离线查询",
             "data_sources": ["data/crop_adapt_db.json"],
             "safety_boundary": "仅建议，不替代农技人员"}
        self.assertEqual(sf.classify_skill_risk(s)["cls"], "S")

    def test_external_network_is_C(self):
        s = {"description": "调用 https://rest.isric.org 在线查询土壤",
             "data_sources": ["https://rest.isric.org/v2"]}
        self.assertEqual(sf.classify_skill_risk(s)["cls"], "C")

    def test_credentials_is_D(self):
        s = {"description": "读取 AGRI_VISION_KEY 调用外部模型",
             "data_sources": ["https://api.openai.com"]}
        r = sf.classify_skill_risk(s)
        self.assertEqual(r["cls"], "D")
        self.assertTrue(r["signals"]["reads_credentials"])

    def test_write_files_is_B(self):
        s = {"description": "本地离线生成配置并写入 data/ 目录",
             "data_sources": ["data/"], "safety_boundary": "可逆，可回滚"}
        r = sf.classify_skill_risk(s)
        self.assertEqual(r["cls"], "B")
        self.assertTrue(r["signals"]["writes_files"])

    def test_no_false_positive_on_coverage_wording(self):
        """回归守卫：「扩大覆盖」不得被误判成「覆盖写入」。"""
        s = {"description": "扩大 CropAgent 覆盖",
             "data_sources": ["data/"], "safety_boundary": "建议结合本地实测"}
        r = sf.classify_skill_risk(s)
        self.assertFalse(r["signals"]["writes_files"])
        self.assertNotEqual(r["cls"], "D")

    def test_cls_is_computable_and_stable(self):
        s = {"description": "本地离线查询", "data_sources": ["data/"],
             "safety_boundary": "x"}
        self.assertEqual(sf.classify_skill_risk(s)["cls"],
                         sf.classify_skill_risk(s)["cls"])
        self.assertIn("rationale", sf.classify_skill_risk(s))


class TestYagni(unittest.TestCase):
    """A6：只删零引用字段，required 字段永不裁剪。"""

    def _skill(self):
        return {
            "id": "t", "name": "t", "description": "d", "domain": "crop",
            "inputs": ["a", "b", "c"], "outputs": ["p", "q"],
            "data_sources": ["data/"], "version": "",
            "safety_boundary": "", "dependencies": [],
        }

    def test_drops_unused_outputs_only_when_whitelisted(self):
        r = sf.yagni_trim(self._skill(), used_outputs=["p"])
        self.assertEqual(r["skill"]["outputs"], ["p"])
        self.assertEqual(r["yagni"]["dropped"]["outputs"], ["q"])

    def test_no_whitelist_keeps_lists(self):
        """未显式传白名单时不得裁剪 inputs/outputs（避免误删真实能力）。"""
        r = sf.yagni_trim(self._skill())
        self.assertEqual(r["skill"]["inputs"], ["a", "b", "c"])
        self.assertEqual(r["skill"]["outputs"], ["p", "q"])
        self.assertEqual(r["yagni"]["dropped_count"], 3)

    def test_drops_empty_optional_fields(self):
        r = sf.yagni_trim(self._skill())
        self.assertNotIn("version", r["skill"])
        self.assertNotIn("safety_boundary", r["skill"])
        self.assertNotIn("dependencies", r["skill"])

    def test_required_fields_never_dropped(self):
        r = sf.yagni_trim(self._skill(), used_inputs=["a"], used_outputs=["p"])
        for k in ("id", "name", "description", "domain", "inputs",
                  "outputs", "data_sources"):
            self.assertIn(k, r["skill"], f"{k} 被误删")

    def test_reduction_ratio_bounded(self):
        r = sf.yagni_trim(self._skill(), used_inputs=["a"], used_outputs=["p"])
        self.assertGreaterEqual(r["yagni"]["reduction_ratio"], 0.0)
        self.assertLessEqual(r["yagni"]["reduction_ratio"], 1.0)

    def test_generate_skill_writes_cls(self):
        """生成的 skill 必须自带 CLS 分级，且不影响校验。"""
        old = sf.REGISTRY
        tmp = tempfile.mkdtemp(prefix="agri_reg_")
        sf.REGISTRY = tmp
        try:
            r = sf.generate_skill(
                skill_id="t_stress_test", name="压测", domain="crop",
                description="本地离线查询 data/", data_sources=["data/"],
                inputs=["zone_id"], outputs=["adapt_score"],
                safety_boundary="建议结合本地实测",
            )
            self.assertEqual(r["cls"], "S")
            with open(r["path"], "r", encoding="utf-8") as f:
                disk = json.load(f)
            self.assertEqual(disk["cls"], "S")
            self.assertTrue(r["validated"])
        finally:
            sf.REGISTRY = old
            shutil.rmtree(tmp, ignore_errors=True)


class TestAntiRot(unittest.TestCase):
    """A7：零引用技能必须被标记，流水线技能不得误报。"""

    def test_pipeline_skill_not_rot(self):
        skills = {s["id"]: s for s in sf.list_skills()}
        for sid in ("climate_match", "crop_adapt", "growth_plan", "device_recommend"):
            self.assertIn(sid, skills, f"注册表缺 {sid}")
            r = sf.lint_skill(skills[sid])
            self.assertFalse(r["rot"], f"{sid} 被误报腐化: {r['issues']}")
            self.assertEqual(r["reference_path"], "run_pipeline")

    def test_ondemand_skill_not_rot(self):
        skills = {s["id"]: s for s in sf.list_skills()}
        for sid in ("pest_diagnose", "nutrition_plan", "season_advisory"):
            self.assertIn(sid, skills, f"注册表缺 {sid}")
            r = sf.lint_skill(skills[sid])
            self.assertEqual(r["reference_path"], "call_skill")
            self.assertFalse(r["rot"], f"{sid} 被误报腐化: {r['issues']}")

    def test_unknown_agent_is_rot(self):
        r = sf.lint_skill({"id": "ghost", "name": "幽灵",
                           "description": "d", "domain": "crop",
                           "inputs": ["a"], "outputs": ["b"],
                           "data_sources": ["data/"], "agent": "GhostAgent"})
        self.assertTrue(r["rot"])
        self.assertIn("零调用路径引用", r["issues"][0])

    def test_empty_contract_is_rot(self):
        r = sf.lint_skill({"id": "empty", "name": "空", "description": "",
                           "domain": "crop", "inputs": [], "outputs": [],
                           "data_sources": [], "agent": "CropAgent"})
        self.assertTrue(r["rot"])
        self.assertGreaterEqual(r["rot_score"], 3)

    def test_registry_audit_clean(self):
        """回归守卫：当前注册表应零腐化（season_advisory 顶层契约已补齐）。"""
        a = sf.audit()
        self.assertEqual(a["rot_count"], 0,
                         f"腐化技能: {[(r['id'], r['rot']['issues']) for r in a['skills'] if r['rot']['rot']]}")
        for row in a["skills"]:
            self.assertIn(row["cls"], ("S", "A", "B", "C", "D"))


class TestVerifierAndSession(unittest.TestCase):
    """A3：Verifier 必须做语义校验；Session 必须幂等且防冲突。"""

    def setUp(self):
        self.orch = AgriOrchestrator()

    def test_pipeline_passes_verification(self):
        r = self.orch.run_pipeline(BASE_REQ)
        self.assertTrue(r["verification"]["passed"])
        self.assertEqual(r["verification"]["verified_agents"], 4)
        self.assertEqual(r["verification"]["failures"], [])

    def test_verifier_catches_bad_crop_output(self):
        """Verifier 不得只看「有字段」：adapt_score 越界必须报不通过。"""
        bad = {"recommendation": [{"crop": "", "adapt_score": 5.0}]}
        r = verify_agent_output("CropAgent", bad)
        self.assertFalse(r["ok"])
        names = {c["name"] for c in r["checks"]}
        self.assertIn("recommendation_items_valid", names)

    def test_verifier_catches_error_payload(self):
        r = verify_agent_output("CropAgent", {"error": "boom", "recommendation": []})
        self.assertFalse(r["ok"])
        self.assertFalse(r["checks"][1]["ok"])

    def test_verifier_catches_non_dict(self):
        self.assertFalse(verify_agent_output("CropAgent", "oops")["ok"])

    def test_verify_off_flag(self):
        r = self.orch.run_pipeline(BASE_REQ, verify=False)
        self.assertIsNone(r["verification"]["passed"])
        self.assertTrue(r["verification"]["skipped"])

    def test_session_idempotent(self):
        r1 = self.orch.run_pipeline(BASE_REQ, session_id="s1")
        r2 = self.orch.run_pipeline(BASE_REQ, session_id="s1")
        self.assertFalse(r1["session"]["from_cache"])
        self.assertTrue(r2["session"]["from_cache"])
        self.assertEqual(r1["final_recommendation"], r2["final_recommendation"])
        self.assertEqual(self.orch.session_stats()["active_sessions"], 1)

    def test_session_conflict_raises(self):
        self.orch.run_pipeline(BASE_REQ, session_id="s2")
        with self.assertRaises(ValueError):
            self.orch.run_pipeline({**BASE_REQ, "lat": 39.9042}, session_id="s2")

    def test_get_session_returns_cached(self):
        self.orch.run_pipeline(BASE_REQ, session_id="s3")
        got = self.orch.get_session("s3")
        self.assertIsNotNone(got)
        self.assertIn("final_recommendation", got["result"])
        self.assertIsNone(self.orch.get_session("nope"))

    def test_result_never_leaks_sentinel(self):
        """Verifier 元数据不得污染输出（曾触发回归守卫）。"""
        r = self.orch.run_pipeline(BASE_REQ)
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("PLACEHOLDER", blob)

    def test_pipeline_backward_compatible(self):
        """新增字段不得破坏既有调用方对 pipeline_steps/final_recommendation 的依赖。"""
        r = self.orch.run_pipeline(BASE_REQ)
        self.assertEqual(len(r["pipeline_steps"]), 4)
        self.assertIn("final_recommendation", r)
        self.assertIn("trust_summary", r)
        self.assertEqual(r["pipeline_steps"][0]["agent"], "ClimateAgent")


class TestAgriCli(unittest.TestCase):
    """A7：按需 CLI 必须白名单 + 只读默认 + 路径逃逸防护。"""

    def _cli(self):
        import importlib.util
        p = os.path.join(ROOT, "scripts", "agri_cli.py")
        name = "agri_cli_under_test"
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, p)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_path_escape_rejected(self):
        a = self._cli()
        for bad in ("../etc/passwd", "../../x", os.path.join(os.path.dirname(ROOT), "nope.json")):
            with self.assertRaises(ValueError, msg=bad):
                a.resolve_inside_root(bad)

    def test_inside_root_allowed(self):
        a = self._cli()
        got = a.resolve_inside_root("data/crop_adapt_db.json")
        self.assertTrue(got.startswith(os.path.realpath(ROOT)))
        self.assertEqual(a.sha_of(got), a.sha_of(got))  # 指纹稳定

    def test_unknown_skill_denied(self):
        a = self._cli()
        args = argparse.Namespace(name="rm_rf_everything", input_file=None,
                                  json=False, crop=None, symptom=None,
                                  lat=None, lon=None, zone_id=None,
                                  container_l=None)
        self.assertEqual(a.cmd_skill(args), 2)

    def test_read_only_by_default(self):
        """写盘动作不加 --write 时不得创建文件（只读默认）。"""
        a = self._cli()
        tmp = tempfile.mkdtemp(prefix="agri_cli_")
        a.ROOT = tmp
        target = os.path.join(tmp, "data", "execution_log.json")
        try:
            args = argparse.Namespace(write=False, json=False)
            self.assertEqual(a.cmd_recipe_init(args), 0)
            self.assertFalse(os.path.exists(target), "只读模式不应创建文件")
            args.write = True
            self.assertEqual(a.cmd_recipe_init(args), 0)
            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), [])
            # 已存在时不得覆盖
            with open(target, "w", encoding="utf-8") as f:
                json.dump([{"x": 1}], f)
            self.assertEqual(a.cmd_recipe_init(args), 0)
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), [{"x": 1}])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hci_action_runs(self):
        a = self._cli()
        self.assertEqual(a.cmd_hci(argparse.Namespace(json=True)), 0)

    def test_command_allowlist_exhaustive(self):
        """每个声明的动作都必须可调用且写盘动作被正确标注。"""
        a = self._cli()
        self.assertEqual(set(a.COMMANDS),
                         {"pipeline", "skill", "hci", "audit", "verify",
                          "feedback-log", "recipe-init",
                          "search", "schedule", "recall", "state-machine"})
        self.assertEqual(a.WRITE_ACTIONS, {"recipe-init"})
        for name, spec in a.COMMANDS.items():
            self.assertTrue(callable(spec["func"]), f"{name} 缺 func")

    def test_no_shell_invocation(self):
        """CLI 不得依赖 shell/subprocess（避免命令注入面）。

        只查真实调用点：注释与文档字符串里提到这些词不算使用。
        """
        import re
        src = open(os.path.join(ROOT, "scripts", "agri_cli.py"),
                   encoding="utf-8").read()
        for pat, why in (
            (r"^\s*(import\s+subprocess|from\s+subprocess\b)", "import subprocess"),
            (r"os\.(system|popen)\s*\(", "os.system/os.popen 调用"),
            (r"shell\s*=\s*True", "shell=True 调用"),
            (r"subprocess\.(run|Popen|call|check_output)\s*\(", "subprocess.* 调用"),
        ):
            m = re.search(pat, src, flags=re.MULTILINE)
            self.assertIsNone(m, f"agri_cli.py 不应包含{why}：{m.group(0) if m else ''}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
