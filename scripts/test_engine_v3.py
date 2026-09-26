#!/usr/bin/env python3
"""
智慧农业生态 · 引擎 v3 单元测试（仅标准库 unittest，零第三方依赖）

覆盖 agent_ecosystem_complementary_2026-09-16.md 第二批 A 档落地项：
    A1  engine/evolution.py         —— 自进化闭环（benchmark + 棘轮 + 快照回滚）
    A2  engine/org_memory.py        —— 组织记忆（轨迹 → 经验 → 共享 Playbook）
    A3  engine/knowledge_graph.py   —— 实体-关系图谱层（反向查询 + 源数据兼容）
    A4  agent/pest_agent.py         —— 零误报证据门控（打不通就不报）
    A5  engine/harness_tree.py      —— 六层组件树（Commands/Hooks/Rules）

隔离原则：所有会写盘的测试都重定向到临时目录，绝不污染 data/ 与 skills/。

运行：
    python scripts/test_engine_v3.py
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

from agent.pest_agent import (diagnose, _evidence_gate,  # noqa: E402
                              _environment_observed)
import engine.evolution as ev_mod  # noqa: E402
import engine.knowledge_graph as kg_mod  # noqa: E402
import engine.org_memory as om_mod  # noqa: E402
import engine.harness_tree as ht_mod  # noqa: E402
import engine.flywheel as fw_mod  # noqa: E402


def _symptom_of_white_powdery():
    return "叶片黄色斑点，背面白色粉状物，像白粉病"


class TestPestEvidenceGate(unittest.TestCase):
    """A4：零误报门控——无双重证据不下确定性结论。"""

    def test_text_only_is_unconfirmed(self):
        """仅症状文本、无图像/环境 → unconfirmed，且诊断带前缀。"""
        r = diagnose(crop="番茄", symptom_description=_symptom_of_white_powdery())
        self.assertEqual(r["confirmation_status"], "unconfirmed")
        self.assertTrue(r["diagnosis"].startswith("（未确认）"))
        self.assertIn("缺少独立佐证", "；".join(r["evidence_gate"]["missing"]))

    def test_symptom_plus_environment_is_confirmed(self):
        """症状命中 + 环境观测（>=2 项有效值）→ confirmed。"""
        r = diagnose(crop="番茄", symptom_description=_symptom_of_white_powdery(),
                     environment={"humidity_pct": 92, "temp_c": 24})
        self.assertEqual(r["confirmation_status"], "confirmed")
        self.assertFalse(r["diagnosis"].startswith("（未确认）"))
        self.assertTrue(r["evidence_gate"]["symptom_hit"])
        self.assertTrue(r["evidence_gate"]["environment_observed"])

    def test_single_env_field_does_not_count(self):
        """只有 1 项环境值不算「已观测」——避免用单点数据下结论。"""
        self.assertFalse(_environment_observed({"humidity_pct": 95}))
        self.assertFalse(_environment_observed({"humidity_pct": 95, "note": "x"}))
        self.assertFalse(_environment_observed(None))
        self.assertTrue(_environment_observed({"humidity_pct": 95, "temp_c": 20}))

    def test_nan_and_bool_are_not_valid_observations(self):
        """NaN 与 bool 不算有效数值（bool 是 int 的子类，必须显式排除）。"""
        self.assertFalse(_environment_observed({"temp_c": float("nan"),
                                                "humidity_pct": 95}))
        self.assertFalse(_environment_observed({"temp_c": True,
                                                "humidity_pct": False}))

    def test_no_symptom_is_unconfirmed(self):
        """无症状输入只能给监测建议，不能给确定性诊断。"""
        r = diagnose(crop="番茄", environment={"humidity_pct": 92, "temp_c": 24})
        self.assertEqual(r["confirmation_status"], "unconfirmed")
        self.assertIn("症状未命中知识库", "；".join(r["evidence_gate"]["missing"]))

    def test_gate_is_machine_readable(self):
        """门控判定必须自解释：三要素 + 缺失项 + 策略来源。"""
        g = _evidence_gate("白粉病", [(1.4, "白粉病", "disease", {})], "白粉病",
                           "rule_based", None)
        self.assertEqual(g["status"], "unconfirmed")
        self.assertTrue(0 <= g["top_score"] <= 2.0)
        self.assertIn("policy", g)
        self.assertIn("Shannon", g["policy"])

    def test_signature_and_no_placeholder(self):
        r = diagnose(crop="番茄", symptom_description=_symptom_of_white_powdery())
        self.assertTrue(r["signature"])
        blob = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("PLACEHOLDER", blob)
        self.assertIn("evidence_gate", r)
        self.assertIn("environment_observed", r["evidence"])


class TestKnowledgeGraph(unittest.TestCase):
    """A3：派生图层——反向查询可用，且绝不修改源 JSON。"""

    def setUp(self):
        self.src = os.path.join(ROOT, "data", "crop_adapt_db.json")
        with open(self.src, "rb") as f:
            self.before_hash = f.read()

    def tearDown(self):
        with open(self.src, "rb") as f:
            after = f.read()
        self.assertEqual(after, self.before_hash,
                         "图层不得修改作物库源文件")

    def test_build_graph_populates_entities_and_edges(self):
        g = kg_mod.build_graph(save=False)
        st = g["stats"]
        self.assertGreater(st["crops"], 50)
        self.assertGreaterEqual(st["edges"], st["nodes"])
        self.assertEqual(g["schema"], "agri-knowledge-graph/v1")
        self.assertIn("grows_in", st["edges_by_rel"])
        self.assertIn("sensitive_to", st["edges_by_rel"])

    def test_reverse_query_finds_affected_crops(self):
        """反向查询是图层的核心价值：扁平 JSON 无法直接回答。"""
        g = kg_mod.build_graph(save=False)
        affected = kg_mod.find_crops_for_risk("叶斑病", g)
        self.assertGreater(len(affected), 0)
        for c in affected:
            self.assertIn("Crop:%s" % c,
                          {e["id"] for e in g["entities"]})

    def test_risky_zones_matches_affecting_edges(self):
        """回归：曾因节点前缀不一致导致暴露度永远为空。"""
        g = kg_mod.build_graph(save=False)
        risk = "叶斑病"
        zones = kg_mod.risky_zones(risk, g)
        if kg_mod.find_crops_for_risk(risk, g):
            self.assertGreater(sum(zones.values()), 0,
                               "有受影响作物时暴露度不得为空")
            self.assertEqual(sum(zones.values()),
                             len(kg_mod.find_crops_for_risk(risk, g)))

    def test_neighbors_exists_for_sink_node(self):
        """回归：sink 节点（如 PestDisease:*）无出边，不得被误判为不存在。"""
        g = kg_mod.build_graph(save=False)
        node = kg_mod._n_risk("叶斑病")
        self.assertTrue(kg_mod.neighbors(g, node)["exists"])
        self.assertEqual(kg_mod.neighbors(g, node)["neighbors"], {})
        rev = kg_mod.neighbors(g, node, relation="sensitive_to", reverse=True)
        self.assertGreater(len(rev["neighbors"]), 0)

    def test_traverse_reverse_crosses_sink(self):
        g = kg_mod.build_graph(save=False)
        fwd = kg_mod.traverse(g, kg_mod._n_risk("叶斑病"), depth=2)
        rev = kg_mod.traverse(g, kg_mod._n_risk("叶斑病"), depth=2, reverse=True)
        self.assertEqual(fwd["direction"], "forward")
        self.assertEqual(rev["direction"], "reverse")
        self.assertGreater(len(rev["visited"]), len(fwd["visited"]))

    def test_find_crops_ordered_by_adapt_score(self):
        g = kg_mod.build_graph(save=False)
        rows = kg_mod.find_crops("subtropical_wet", top_k=5)
        scores = [r["adapt_score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertLessEqual(len(rows), 5)

    def test_missing_source_fails_fast(self):
        """源数据缺失必须抛错，不能静默产出空图。"""
        with self.assertRaises(FileNotFoundError):
            kg_mod.build_graph(crop_db_path=os.path.join(ROOT, "data", "NO_SUCH.json"),
                               save=False)

    def test_rebuild_is_deterministic(self):
        a = json.dumps(kg_mod.build_graph(save=False)["edges"], sort_keys=True)
        b = json.dumps(kg_mod.build_graph(save=False)["edges"], sort_keys=True)
        self.assertEqual(a, b)


class TestOrgMemory(unittest.TestCase):
    """A2：轨迹 → 经验 → 共享 Playbook（支持度门槛防噪声入库）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri_om_")
        self._old = os.environ.get("AGRI_ORG_MEMORY")
        os.environ["AGRI_ORG_MEMORY"] = self.tmp
        # 模块路径常量在导入时绑定，需重算
        om_mod.MEM_DIR = self.tmp
        om_mod.TRAJ_PATH = os.path.join(self.tmp, "trajectories.json")
        om_mod.PLAYBOOK_PATH = os.path.join(self.tmp, "playbook.json")

    def tearDown(self):
        if self._old is None:
            os.environ.pop("AGRI_ORG_MEMORY", None)
        else:
            os.environ["AGRI_ORG_MEMORY"] = self._old
        om_mod.MEM_DIR = os.path.join(ROOT, "data", "org_memory")
        om_mod.TRAJ_PATH = os.path.join(om_mod.MEM_DIR, "trajectories.json")
        om_mod.PLAYBOOK_PATH = os.path.join(om_mod.MEM_DIR, "playbook.json")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_classify_issue_categories(self):
        self.assertEqual(om_mod.classify_issue("设备离线，传感器连接失败"), "设备/执行")
        self.assertEqual(om_mod.classify_issue("未找到该作物数据"), "数据缺失")
        self.assertEqual(om_mod.classify_issue("夏季高温抽苔"), "环境异常")
        self.assertEqual(om_mod.classify_issue("叶片霉层"), "病虫害")
        # 零误报门控产生的轨迹必须归到专属类别，而不是「其他」
        self.assertEqual(om_mod.classify_issue(
            "缺少独立佐证（视觉确认 / 环境观测二选一）"), "证据不足")
        self.assertEqual(om_mod.classify_issue("症状未命中知识库具体条目"), "证据不足")
        self.assertEqual(om_mod.classify_issue(""), "其他")

    def test_record_trajectory_is_append_only(self):
        a = om_mod.record_trajectory("pest_diagnose", {"crop": "番茄"}, "unconfirmed",
                                     "症状未命中知识库具体条目")
        om_mod.record_trajectory("pest_diagnose", {"crop": "番茄"}, "unconfirmed",
                                 "症状未命中知识库具体条目")
        log = om_mod._load_list(om_mod.TRAJ_PATH)
        self.assertEqual(len(log), 2)
        self.assertEqual(a["issue_category"], "证据不足")
        self.assertTrue(a["trace_id"])
        self.assertEqual(a["outcome"], "unconfirmed")

    def test_playbook_requires_min_support(self):
        """单例噪声不得入库——零误报思路在知识层的延伸。"""
        om_mod.record_trajectory("pest_diagnose", {}, "unconfirmed", "症状未命中知识库")
        pb = om_mod.distill_playbook(min_support=2)
        self.assertEqual(len(pb["entries"]), 0)

    def test_playbook_distills_repeated_pattern(self):
        for _ in range(3):
            om_mod.record_trajectory("pest_diagnose", {"crop": "番茄"}, "unconfirmed",
                                     "症状未命中知识库具体条目")
        om_mod.record_trajectory("nutrition_plan", {"crop": "生菜"}, "ok", None)
        pb = om_mod.distill_playbook(min_support=3)
        self.assertEqual(len(pb["entries"]), 1)
        e = pb["entries"][0]
        self.assertEqual(e["support"], 3)
        self.assertEqual(e["issue_category"], "证据不足")
        self.assertEqual(e["confidence"], "high")
        self.assertTrue(e["countermeasures"])
        self.assertEqual(e["outcome_breakdown"].get("unconfirmed"), 3)

    def test_recall_filters_by_skill(self):
        for _ in range(3):
            om_mod.record_trajectory("pest_diagnose", {}, "unconfirmed",
                                     "症状未命中知识库具体条目")
        om_mod.distill_playbook(min_support=3)
        self.assertEqual(len(om_mod.recall("pest_diagnose")), 1)
        self.assertEqual(om_mod.recall("nutrition_plan"), [])

    def test_recall_before_distill_is_empty(self):
        self.assertEqual(om_mod.recall("pest_diagnose"), [])

    def test_stats_shape(self):
        om_mod.record_trajectory("pest_diagnose", {}, "unconfirmed",
                                 "症状未命中知识库具体条目")
        s = om_mod.stats()
        self.assertEqual(s["trajectories"], 1)
        self.assertIn("unconfirmed", s["outcome_breakdown"])
        self.assertIn("pest_diagnose", s["skills_seen"])


class TestEvolutionRatchet(unittest.TestCase):
    """A1：benchmark + 棘轮门禁 + 快照回滚。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri_evo_")
        self.crop_db = os.path.join(self.tmp, "crop_adapt_db.json")
        self.fb_log = os.path.join(self.tmp, "feedback_log.json")
        self.bm_path = os.path.join(self.tmp, "benchmark.json")
        self.snap_root = os.path.join(self.tmp, "snaps")
        self._write_crop_db(0.5)
        with open(self.fb_log, "w", encoding="utf-8") as f:
            f.write("[]")
        self._write_benchmark()
        self._old = {k: os.environ.get(k) for k in
                     ("AGRI_CROP_DB", "AGRI_FEEDBACK_LOG",
                      "AGRI_EVOLUTION_BENCHMARK", "AGRI_EVOLUTION_SNAPSHOTS")}
        os.environ["AGRI_CROP_DB"] = self.crop_db
        os.environ["AGRI_FEEDBACK_LOG"] = self.fb_log
        ev_mod.BENCHMARK_PATH = self.bm_path
        ev_mod.SNAPSHOT_ROOT = self.snap_root

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        ev_mod.BENCHMARK_PATH = os.path.join(ROOT, "data", "eval",
                                              "evolution_benchmark.json")
        ev_mod.SNAPSHOT_ROOT = os.path.join(ROOT, "data", "snapshots")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_crop_db(self, score):
        data = {"zones": {"z1": {"zone_name": "t", "crops": [
            {"crop": "X", "adapt_score": score}]}}}
        with open(self.crop_db, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def _write_benchmark(self):
        bm = {"cases": [
            {"id": "b1", "zone_id": "z1", "crop": "X",
             "feedback": {"survival_rate": 0.98, "yield_rating": 5.0,
                          "user_rating": 5.0}, "expect": "up"},
            {"id": "b2", "zone_id": "z1", "crop": "X",
             "feedback": {"survival_rate": 0.25, "yield_rating": 1.0,
                          "user_rating": 1.0}, "expect": "up"},
        ]}
        with open(self.bm_path, "w", encoding="utf-8") as f:
            json.dump(bm, f, ensure_ascii=False)
        return self._read_json(self.bm_path)

    def _read_json(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _set_score(self, path, score):
        """测试专用：改写作物 X 的 adapt_score，模拟一次「候选变更」。"""
        d = self._read_json(path)
        d["zones"]["z1"]["crops"][0]["adapt_score"] = score
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    def _read(self):
        return self._read_json(self.crop_db)[
            "zones"]["z1"]["crops"][0]["adapt_score"]

    def test_cases_are_independently_scored(self):
        """回归：同一作物的好/坏用例若共享副本，后者评分会被前者污染。"""
        bm = self._write_benchmark()
        sc = ev_mod.score_benchmark(bm)
        by_id = {r["id"]: r for r in sc["results"]}
        self.assertEqual(by_id["b1"]["verdict"], "up")
        self.assertEqual(by_id["b2"]["verdict"], "down")
        self.assertEqual(by_id["b2"]["before"], 0.5,
                         "b2 的 before 必须是原始值，不能继承 b1 的校准结果")

    def test_scoring_never_touches_real_data(self):
        bm = self._write_benchmark()
        ev_mod.score_benchmark(bm)
        self.assertEqual(self._read(), 0.5)
        with open(self.fb_log, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "[]")

    def test_measure_only_makes_no_change(self):
        """measure_only 只测基线：不改文件，也不留快照空壳。

        回归点：曾把 snapshot() 放在 mutate 判空之前，导致每次只读测量都在
        data/snapshots 净增一个无回滚价值的空目录（需手工清理）。
        """
        bm = self._write_benchmark()
        r = ev_mod.ratchet(benchmark=bm)
        self.assertIsNone(r["accepted"])
        self.assertEqual(r["action"], "measure_only")
        self.assertIsNone(r["snap_id"])
        self.assertEqual(self._read(), 0.5)
        self.assertEqual(len(ev_mod.list_snapshots()), 0,
                         "measure_only 不得创建快照（无变更可回滚）")

    def test_flat_change_is_rejected_and_reverted(self):
        """持平（Δ=0）不算改进——棘轮必须拒绝并回滚。"""
        bm = self._write_benchmark()

        def mutate(db, log):
            self._set_score(db, 0.95)
            return {"set": 0.95}

        r = ev_mod.ratchet(mutate=mutate, benchmark=bm, label="t_flat")
        self.assertFalse(r["accepted"])
        self.assertEqual(r["delta"], 0.0)
        self.assertEqual(r["action"], "revert")
        self.assertEqual(self._read(), 0.5, "被拒绝的变更必须完整回滚")

    def test_improving_change_is_accepted(self):
        bm = self._write_benchmark()

        def mutate(db, log):
            self._set_score(db, 0.0)
            return {"set": 0.0}

        r = ev_mod.ratchet(mutate=mutate, benchmark=bm, label="t_improve")
        self.assertTrue(r["accepted"])
        self.assertGreater(r["delta"], 0)
        self.assertEqual(r["action"], "accept")
        self.assertEqual(self._read(), 0.0)

    def test_min_gain_enforces_strict_threshold(self):
        """min_gain>0 时，小幅提升也必须被拒。"""
        bm = self._write_benchmark()

        def mutate(db, log):
            d = json.load(open(db, encoding="utf-8"))
            d["zones"]["z1"]["crops"][0]["adapt_score"] = 0.0
            json.dump(d, open(db, "w", encoding="utf-8"))
            return {}

        r = ev_mod.ratchet(mutate=mutate, benchmark=bm, min_gain=0.99,
                           label="t_strict")
        self.assertFalse(r["accepted"])
        self.assertEqual(self._read(), 0.5)

    def test_snapshot_and_restore_roundtrip(self):
        before = self._read()
        snap = ev_mod.snapshot(label="t_snap", paths=[self.crop_db])
        self.assertTrue(snap["created"])
        self.assertIn(self.crop_db, snap["files"])
        self._write_crop_db(0.99)
        self.assertEqual(self._read(), 0.99)
        r = ev_mod.restore(snap["snap_id"])
        self.assertTrue(r["restored"])
        self.assertEqual(self._read(), before)
        self.assertTrue(ev_mod.list_snapshots()[0]["restored"])

    def test_snapshot_absolute_paths_are_stored_as_alias(self):
        """回归：绝对路径必须走别名，否则快照树会被盘符/多级路径污染。"""
        snap = ev_mod.snapshot(label="t_abs", paths=[self.crop_db])
        with open(os.path.join(snap["path"], "_meta.json"),
                  encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(len(meta["file_map"]), 1)
        stored = next(iter(meta["file_map"]))
        self.assertTrue(stored.startswith("abs__"))
        self.assertEqual(meta["file_map"][stored], self.crop_db)

    def test_seed_benchmark_uses_real_crops(self):
        """评测集必须从真实作物库派生，不能手写魔法值。"""
        bm = ev_mod.seed_benchmark(zone_pick=2, cases_per_pair=2, save=False)
        self.assertGreater(len(bm["cases"]), 0)
        real = self._read_json(fw_mod.crop_db_path())
        zones = real["zones"]
        for c in bm["cases"]:
            self.assertIn(c["zone_id"], zones)
            self.assertIn(c["crop"],
                          [x["crop"] for x in zones[c["zone_id"]]["crops"]])
            self.assertIn(c["expect"], ("up", "down"))

    def test_report_shape(self):
        r = ev_mod.report()
        self.assertIn("benchmark", r)
        self.assertIn("score", r)
        self.assertIn("policy", r)
        self.assertIn("棘轮", r["policy"])


class TestHarnessTree(unittest.TestCase):
    """A5：六层组件树——Commands/Hooks/Rules 可机读校验。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri_ht_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lint_passes_on_shipped_tree(self):
        r = ht_mod.lint()
        self.assertTrue(r["ok"], "组件树 lint 必须通过：%s" % r["issues"])
        self.assertEqual(r["issue_count"], 0)

    def test_lint_catches_duplicate_ids(self):
        t = ht_mod.tree()
        t["layers"]["commands"]["items"].append(
            dict(t["layers"]["commands"]["items"][0]))
        r = ht_mod.lint(t)
        self.assertFalse(r["ok"])
        self.assertTrue(any("重复" in i["issue"] for i in r["issues"]))

    def test_lint_catches_unreadable_trigger(self):
        t = ht_mod.tree()
        t["layers"]["hooks"]["items"][0]["trigger"] = {"field": "x", "op": "???"}
        r = ht_mod.lint(t)
        self.assertFalse(r["ok"])
        self.assertTrue(any("不可机读" in i["issue"] for i in r["issues"]))

    def test_lint_catches_bad_severity(self):
        t = ht_mod.tree()
        t["layers"]["rules"]["items"][0]["severity"] = "catastrophic"
        r = ht_mod.lint(t)
        self.assertTrue(any("severity 非法" in i["issue"] for i in r["issues"]))

    def test_lint_catches_empty_applies_to(self):
        t = ht_mod.tree()
        t["layers"]["rules"]["items"][0]["applies_to"] = []
        r = ht_mod.lint(t)
        self.assertTrue(any("applies_to 为空" in i["issue"] for i in r["issues"]))

    def test_lint_catches_dangling_hook_command(self):
        t = ht_mod.tree()
        t["layers"]["hooks"]["items"][0]["action"]["command"] = "no_such_command"
        r = ht_mod.lint(t)
        self.assertTrue(any("command 不存在" in i["issue"] for i in r["issues"]))

    def test_export_writes_four_files(self):
        ht_mod.HARNESS_DIR = self.tmp
        written = ht_mod.export(skills_count=9, mcp_count=9)
        for key in ("commands", "hooks", "rules", "index"):
            self.assertIn(key, written)
            self.assertTrue(os.path.exists(os.path.join(ROOT, written[key])))
        with open(os.path.join(self.tmp, "commands.json"), encoding="utf-8") as f:
            cmds = json.load(f)
        with open(os.path.join(self.tmp, "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
        self.assertEqual(cmds["count"], len(ht_mod.COMMANDS))
        self.assertEqual(idx["layers"]["skills"]["count"], 9)
        self.assertEqual(idx["layers"]["mcp_tools"]["count"], 9)
        ht_mod.HARNESS_DIR = os.path.join(ROOT, "skills", "harness")

    def test_stats_and_six_layers(self):
        s = ht_mod.stats()
        self.assertGreaterEqual(s["commands"], 4)
        self.assertGreaterEqual(s["hooks"], 3)
        self.assertGreaterEqual(s["rules"], 5)
        self.assertTrue(s["lint_ok"])
        self.assertGreaterEqual(s["blocker_rules"], 1)
        t = ht_mod.tree()
        layers = set(t["layers"].keys())
        for need in ("agents", "skills", "commands", "hooks", "rules", "mcp_tools"):
            self.assertIn(need, layers)

    def test_blocker_rule_for_evidence_gate_exists(self):
        """零误报约束必须作为常驻规则登记，而不是只写在 agent 代码里。"""
        ids = [r["id"] for r in ht_mod.RULES]
        self.assertIn("no_unconfirmed_diagnosis", ids)
        blocker = [r for r in ht_mod.RULES if r["id"] == "no_unconfirmed_diagnosis"]
        self.assertEqual(blocker[0]["severity"], "blocker")

    def test_manifest_harness_tree_blockers_listed(self):
        """manifest.harness_tree 必须显式列出 blocker 规则 id 列表。

        理由：巡检 automation 每日读 manifest 判断「哪 3 条是硬门禁」，
        若清单里没有 blockers 字段，只能回读 engine/harness_tree.py，
        一旦有人改 severity 而没重跑 harness_sync init，manifest 会静默漂移。
        显式列出后本测试就能直接发现。
        """
        mpath = os.path.join(ROOT, "harness", "manifest.json")
        with open(mpath, "r", encoding="utf-8") as f:
            m = json.load(f)
        ht_m = m.get("harness_tree") or {}
        self.assertIn("blockers", ht_m,
                      "manifest.harness_tree 必须含 blockers 字段（否则巡检脚本无法判硬门禁）")
        expected = {r["id"] for r in ht_mod.RULES if r.get("severity") == "blocker"}
        self.assertEqual(set(ht_m["blockers"]), expected,
                         "manifest 的 blockers 清单必须与 engine.harness_tree.RULES 中 severity=blocker 完全一致")
        self.assertGreater(len(ht_m["blockers"]), 0, "blockers 不得为空（否则所有门禁都失效）")


class TestHarnessManifestIntegration(unittest.TestCase):
    """A1-A5 必须体现在 harness 清单里（防静默漂移）。"""

    def test_manifest_declares_tree_and_observes_new_layers(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        if "harness_sync" in sys.modules:
            del sys.modules["harness_sync"]
        import harness_sync
        m = harness_sync.build_manifest()
        self.assertIn("harness_tree", m)
        self.assertEqual(m["harness_tree"]["rules"]["count"], len(ht_mod.RULES))
        self.assertTrue(m["harness_tree"]["lint_ok"])
        self.assertIn("harness_tree", harness_sync.DECLARED_SECTIONS)
        for obs in ("knowledge_graph", "org_memory"):
            self.assertIn(obs, m)
            self.assertIn(obs, harness_sync.OBSERVED_SECTIONS)
            self.assertNotIn("error", m[obs], "观测段不得报错：%s" % m[obs])
        self.assertIn("grows_in", m["knowledge_graph"]["edges_by_rel"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()
    unittest.main(verbosity=2 if args.verbose else 1)
