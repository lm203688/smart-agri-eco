"""test_engine_v4 —— B 档五项落地回归（跨会话记忆 / 本地检索 / 条件锚定 / 状态机 / 解释链）

覆盖：
  B1  engine/long_term_memory.py  —— 跨会话长期记忆（本地 JSON + 超边扩展）
  B2  engine/local_search.py      —— 本地三层检索（FTS5 + 二元分词 + 向量）
  B3  agent/pest_agent.py         —— 三阶段解释链（预测/解释/映射）
  B4  engine/recipe_scheduler.py  —— 条件锚定执行器（替代固定时间排程）
  B5  engine/work_item.py         —— 工作项状态机（5 模式 + 审计日志）
  集成  agent/orchestrator.py     —— 流水线接入状态机 + 记忆写入/召回
        scripts/harness_sync.py   —— 新模块登记进观测区

隔离约定（与 v2/v3 一致）：
  所有写盘都重定向到 tempfile，绝不污染 data/ 下的真实文件；
  路径通过环境变量覆盖（AGRI_LONG_TERM_MEMORY / AGRI_SEARCH_INDEX），
  tearDown 恢复原值。
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent import pest_agent  # noqa: E402
from engine import long_term_memory as ltm  # noqa: E402
from engine import local_search as ls  # noqa: E402
from engine import recipe_scheduler as rs  # noqa: E402
from engine import work_item as wim  # noqa: E402


class _Isolated(unittest.TestCase):
    """临时目录 + 环境变量隔离基类。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="agri_v4_")
        self._env_saved = {}
        # 合成记录留痕：万一某个用例漏设 AGRI_LONG_TERM_MEMORY 而写穿到真实记忆库，
        # CI 的「数据完整性门禁」按 source_ref 标记拦下。不要靠「文件恰好是空的」来保证。
        self.set_env("AGRI_MEMORY_SYNTHETIC", "1")

    def tearDown(self):
        for k, v in self._env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)
        wim.clear_registry()

    def set_env(self, key, path):
        self._env_saved[key] = os.environ.get(key)
        os.environ[key] = path

    def write_json(self, name, obj):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return p

    def read_json(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)


# ===========================================================================
# B5 工作项状态机
# ===========================================================================
class TestWorkItem(unittest.TestCase):
    def setUp(self):
        wim.clear_registry()

    def test_full_lifecycle_to_done(self):
        wi = wim.new_work_item("t-01", title="x", actor="A")
        self.assertEqual(wi.state, "created")
        wi.transition("execute", actor="ClimateAgent")
        self.assertEqual(wi.state, "executing")
        wi.transition("review", actor="Verifier")
        self.assertEqual(wi.state, "pending_review")
        wi.transition("integrate", actor="Integrator")
        self.assertEqual(wi.state, "integrating")
        wi.transition("integrate", actor="Integrator")
        self.assertEqual(wi.state, "done")
        self.assertTrue(wi.to_dict()["is_terminal"])
        self.assertIsNotNone(wi.finished_at)

    def test_illegal_transition_rejected_and_no_state_change(self):
        wi = wim.new_work_item("t-02")
        wi.transition("execute")
        r = wi.transition("delegate", actor="X")
        self.assertFalse(r["ok"])
        self.assertEqual(wi.state, "executing", "非法转移不得改动状态")
        self.assertIn("非法转移", r["reason"])
        # 审计里不应出现这次失败的转移
        self.assertEqual(wi.audit[-1]["to"], "executing")

    def test_unknown_mode_rejected(self):
        wi = wim.new_work_item("t-03")
        r = wi.transition("explode")
        self.assertFalse(r["ok"])
        self.assertIn("未知模式", r["reason"])
        self.assertEqual(wi.state, "created")

    def test_done_is_terminal_except_rework(self):
        wi = wim.new_work_item("t-04")
        for step in ("execute", "review", "integrate", "integrate"):
            wi.transition(step)
        self.assertEqual(wi.state, "done")
        self.assertEqual(wim.allowed_modes("done"), ["rework"])
        self.assertFalse(wi.transition("execute")["ok"])
        self.assertFalse(wi.transition("integrate")["ok"])
        wi.transition("rework")
        self.assertEqual(wi.state, "rework")
        self.assertEqual(wi.rework_count, 1)

    def test_rework_then_execute_loop(self):
        wi = wim.new_work_item("t-05")
        wi.transition("execute")
        wi.transition("rework")
        self.assertEqual(wi.state, "rework")
        wi.transition("execute")
        self.assertEqual(wi.state, "executing")
        self.assertEqual(wi.attempts, 2, "两次 execute 都应计入 attempts")

    def test_block_and_recover(self):
        wi = wim.new_work_item("t-06")
        wi.transition("execute")
        r = wi.block("视觉后端不可用")
        self.assertTrue(r["ok"])
        self.assertEqual(wi.state, "blocked")
        self.assertEqual(wim.allowed_modes("blocked"), ["delegate", "execute"])
        wi.recover("execute", actor="Ops")
        self.assertEqual(wi.state, "executing")

    def test_block_done_rejected(self):
        wi = wim.new_work_item("t-07")
        for step in ("execute", "review", "integrate", "integrate"):
            wi.transition(step)
        r = wi.block("已完成的不能再阻塞")
        self.assertFalse(r["ok"])
        self.assertEqual(wi.state, "done")

    def test_audit_is_append_only_and_complete(self):
        wi = wim.new_work_item("t-08", title="任务", actor="A")
        wi.transition("execute")
        wi.transition("review")
        kinds = [a["mode"] for a in wi.audit]
        self.assertEqual(kinds, ["init", "execute", "review"])
        # 每条审计必须有关键字段，且 payload_key 是摘要而非全量
        for a in wi.audit:
            self.assertIn("ts", a)
            self.assertIn("to", a)
            self.assertIn("actor", a)
        self.assertIsNone(wi.audit[0].get("payload_key"),
                          "init 条目不应有 payload_key")
        for a in wi.audit[1:]:
            self.assertEqual(len(a["payload_key"]), 16)

    def test_payload_key_is_digest_not_payload(self):
        wi = wim.new_work_item("t-09")
        payload = {"crop": "番茄", "secrets_should_not_appear": "x" * 500}
        wi.transition("execute", payload=payload)
        pk = wi.audit[-1]["payload_key"]
        self.assertEqual(len(pk), 16)
        self.assertNotIn("secrets_should_not_appear", json.dumps(wi.audit))
        self.assertNotIn("番茄", json.dumps(wi.audit))

    def test_new_work_item_idempotent_with_reuse(self):
        a = wim.new_work_item("t-10", title="同一 id")
        b = wim.new_work_item("t-10", title="另一个 title", reuse=True)
        self.assertIs(a, b)
        c = wim.new_work_item("t-10", reuse=False)
        self.assertIsNot(a, c)

    def test_auto_generated_id_when_empty(self):
        wi = wim.new_work_item()
        self.assertTrue(wi.item_id.startswith("wi-"))

    def test_empty_id_rejected(self):
        with self.assertRaises(ValueError):
            wim.WorkItem("", title="x")

    def test_transition_table_covers_all_nonterminal_states(self):
        tbl = wim.transition_table()
        states_in_table = {row["state"] for row in tbl}
        for s in wim.STATES:
            if s in wim.TERMINAL:
                # done 不是纯死路：允许 rework 回炉
                self.assertIn(s, states_in_table)
            else:
                self.assertIn(s, states_in_table)
        for row in tbl:
            self.assertIn(row["mode"], wim.MODES)
            self.assertIn(row["next"], wim.STATES)

    def test_registry_stats_reflects_state(self):
        a = wim.new_work_item("t-11a")
        a.transition("execute")
        b = wim.new_work_item("t-11b")
        st = wim.registry_stats()
        self.assertEqual(st["items"], 2)
        self.assertEqual(st["by_state"].get("executing"), 1)
        self.assertEqual(st["by_state"].get("created"), 1)
        self.assertEqual(st["total_attempts"], 1)

    def test_summary_excludes_audit(self):
        wi = wim.new_work_item("t-12")
        wi.transition("execute")
        self.assertNotIn("audit", wi.summary())
        self.assertIn("audit", wi.to_dict())


# ===========================================================================
# B1 跨会话长期记忆
# ===========================================================================
class TestLongTermMemory(_Isolated):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "mem.json")
        self.set_env("AGRI_LONG_TERM_MEMORY", self.path)

    def test_add_and_recall_by_crop(self):
        m1 = ltm.add_memory(skill="pest_diagnose", crop="生菜",
                            summary="高湿白粉病样症状", outcome="unconfirmed",
                            tags=["高湿"])
        ltm.add_memory(skill="nutrition_plan", crop="辣椒",
                       summary="缺钾补施", outcome="ok")
        hits = ltm.recall(crop="生菜", k=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], m1)
        self.assertGreater(hits[0]["score"], 0)

    def test_hard_filters_are_exact(self):
        ltm.add_memory(skill="pest_diagnose", crop="生菜", zone="a",
                       summary="s1")
        ltm.add_memory(skill="nutrition_plan", crop="生菜", zone="a",
                       summary="s2")
        self.assertEqual(len(ltm.recall(crop="生菜", skill="pest_diagnose")), 1)
        self.assertEqual(len(ltm.recall(crop="生菜", zone="b")), 0)
        self.assertEqual(len(ltm.recall(crop="生菜", tags=["不存在"])), 0)

    def test_recall_empty_when_no_match(self):
        ltm.add_memory(skill="x", crop="生菜", summary="s")
        self.assertEqual(ltm.recall(crop="不存在"), [])
        self.assertEqual(ltm.recall(query="不存在的词", crop="不存在"), [])
        # 完全不带过滤条件 + 空查询 = 最近记忆（这是有意的「近期上下文」语义）
        recent = ltm.recall(query="", k=3)
        self.assertEqual(len(recent), 1)
        self.assertIn("recency", recent[0]["scores"])

    def test_hyperedge_second_order_expansion(self):
        m1 = ltm.add_memory(skill="s", crop="生菜", summary="事件 A")
        m2 = ltm.add_memory(skill="s", crop="生菜", summary="事件 B")
        hid = ltm.link([m1, m2], label="同一高湿事件")
        self.assertIsNotNone(hid)
        # 硬过滤只召回 m1，但超边扩展应把 m2 带回
        hits = ltm.recall(query="事件 A", k=1, expand=True)
        ids = {h["id"] for h in hits}
        self.assertIn(m1, ids)
        self.assertIn(m2, ids)
        sib = [h for h in hits if h["id"] == m2][0]
        self.assertEqual(sib["via_hyperedge"], hid)
        self.assertLess(sib["score"], [h for h in hits if h["id"] == m1][0]["score"])

    def test_expand_false_disables_hyperedge(self):
        m1 = ltm.add_memory(skill="s", crop="生菜", summary="事件 A")
        m2 = ltm.add_memory(skill="s", crop="生菜", summary="事件 B")
        ltm.link([m1, m2])
        # k=1 且不做扩展 → 只回主命中，不带同超边兄弟
        hits_off = ltm.recall(query="事件 A", k=1, expand=False)
        self.assertEqual(len(hits_off), 1)
        self.assertNotIn("via_hyperedge", hits_off[0])
        # 同样查询开扩展 → 兄弟被带回
        hits_on = ltm.recall(query="事件 A", k=1, expand=True)
        self.assertGreater(len(hits_on), len(hits_off))
        self.assertTrue(any(h.get("via_hyperedge") for h in hits_on))

    def test_link_rejected_below_two_valid_memories(self):
        m1 = ltm.add_memory(skill="s", crop="c", summary="s")
        self.assertIsNone(ltm.link([m1]))
        self.assertIsNone(ltm.link(["mem-不存在的-id"]))

    def test_forget_removes_memory_and_dangling_hyperedge(self):
        m1 = ltm.add_memory(skill="s", crop="c", summary="a")
        m2 = ltm.add_memory(skill="s", crop="c", summary="b")
        m3 = ltm.add_memory(skill="s", crop="c", summary="c")
        ltm.link([m1, m2])
        ltm.link([m2, m3])
        self.assertTrue(ltm.forget(m2))
        doc = ltm._load()
        self.assertEqual(ltm.stats()["memories"], 2)
        self.assertEqual(len(doc["hyperedges"]), 0, "引用已删记忆的超边必须清掉")
        self.assertFalse(ltm.forget(m2), "重复删除返回 False")

    def test_empty_summary_rejected(self):
        with self.assertRaises(ValueError):
            ltm.add_memory(skill="s", crop="c", summary="   ")

    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            ltm.add_memory(skill="s", crop="c", summary="s", kind="hacking")

    def test_kind_whitelist(self):
        for kind in ltm.KINDS:
            self.assertIsNotNone(ltm.add_memory(kind=kind, summary="s"))

    def test_tags_are_deduped_and_sorted(self):
        ltm.add_memory(skill="s", crop="c", summary="s",
                       tags=["b", "a", "a", "", "  "])
        m = ltm._load()["memories"][0]
        self.assertEqual(m["tags"], ["a", "b"])

    def test_subject_can_be_given_as_dict(self):
        ltm.add_memory(skill="s", summary="s",
                       subject={"crop": "番茄", "zone": "subtropical_wet"})
        self.assertEqual(len(ltm.recall(crop="番茄", zone="subtropical_wet")), 1)

    def test_flat_args_override_subject(self):
        ltm.add_memory(skill="s", summary="s", crop="番茄", zone="a",
                       subject={"crop": "辣椒", "zone": "b"})
        self.assertEqual(len(ltm.recall(crop="番茄", zone="a")), 1)

    def test_recency_decay(self):
        doc = {"schema": ltm.SCHEMA, "hyperedges": [], "memories": []}
        old = (datetime.datetime.now() - datetime.timedelta(days=90)).isoformat(
            timespec="seconds")
        doc["memories"] = [
            {"id": "m-old", "ts": old, "session_id": "", "skill": "s",
             "kind": "finding", "subject": {"crop": "生菜"},
             "summary": "s", "outcome": "", "recipe_id": "",
             "confidence": None, "tags": [], "source_ref": ""},
            {"id": "m-new", "ts": datetime.datetime.now().isoformat(
                timespec="seconds"), "session_id": "", "skill": "s",
             "kind": "finding", "subject": {"crop": "生菜"},
             "summary": "s", "outcome": "", "recipe_id": "",
             "confidence": None, "tags": [], "source_ref": ""},
        ]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        hits = ltm.recall(crop="生菜", k=2)
        scores = {h["id"]: h["scores"]["recency"] for h in hits}
        self.assertGreater(scores["m-new"], scores["m-old"])
        # 半衰期 30 天：90 天的记忆约衰减到 1/8
        self.assertLess(scores["m-old"], scores["m-new"] / 2)

    def test_min_score_filter(self):
        ltm.add_memory(skill="s", crop="c", summary="内容")
        self.assertEqual(ltm.recall(crop="c", min_score=1e9), [])

    def test_scores_are_all_mechanical(self):
        ltm.add_memory(skill="pest_diagnose", crop="生菜", zone="z",
                       summary="高湿", tags=["高湿"])
        h = ltm.recall(crop="生菜", zone="z", skill="pest_diagnose",
                       tags=["高湿"], k=1)[0]
        for k in ("subject_both", "skill", "tag", "recency"):
            self.assertIn(k, h["scores"])
        self.assertAlmostEqual(h["scores"]["subject_both"], ltm._WEIGHT["subject_both"])

    def test_stats_and_export(self):
        ltm.add_memory(skill="s1", crop="生菜", kind="diagnosis", summary="a",
                       tags=["t"])
        ltm.add_memory(skill="s2", crop="生菜", kind="plan", summary="b")
        s = ltm.stats()
        self.assertEqual(s["memories"], 2)
        self.assertEqual(s["sessions"], 0)
        self.assertTrue(s["local_only"])
        self.assertIn("diagnosis", s["by_kind"])
        out = ltm.export_json(os.path.join(self.tmp, "exp.json"))
        self.assertEqual(self.read_json(out)["memories"][-1]["summary"], "b")

    def test_corrupt_file_degrades_not_crash(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        doc = ltm._load()
        self.assertEqual(doc["memories"], [])
        self.assertTrue(doc.get("corrupt"))

    def test_reset_clears_store(self):
        ltm.add_memory(skill="s", crop="c", summary="s")
        ltm.reset(self.path)
        self.assertEqual(ltm.stats()["memories"], 0)


# ===========================================================================
# B2 本地三层检索
# ===========================================================================
class TestLocalStorage(_Isolated):
    def setUp(self):
        super().setUp()
        self.idx = os.path.join(self.tmp, "idx.db")
        self.set_env("AGRI_SEARCH_INDEX", self.idx)

    # --- 分词一致性（回归：曾出现查询侧单字 / 文档侧 2-gram 导致交集恒空）---
    def test_grams_cjk_query_and_doc_are_consistent(self):
        q = ls.grams("高温 高湿")
        self.assertEqual(q, ["高温", "高湿"])
        doc = ls.grams("叶片出现高温抽苔，湿度偏高")
        self.assertIn("高温", doc)
        self.assertTrue(ls.gram_set("高温") & ls.gram_set(
            "叶片出现高温抽苔，湿度偏高"))

    def test_grams_single_cjk_char_passthrough(self):
        self.assertEqual(ls.grams("生"), ["生"])

    def test_grams_ascii_passthrough(self):
        self.assertEqual(ls.grams("Musa acuminata"), ["musa", "acuminata"])

    def test_grams_empty(self):
        self.assertEqual(ls.grams(""), [])
        self.assertEqual(ls.gram_set(""), set())

    def test_gram_query_escapes_quotes(self):
        mq = ls.gram_query("高温")
        self.assertIn('"高温"', mq)

    def test_gram_query_empty(self):
        self.assertEqual(ls.gram_query(""), "")

    # --- 向量 ---
    def test_vectorize_length_and_normalized(self):
        v = ls.vectorize("生菜适应亚热带湿润带")
        self.assertEqual(len(v), ls.DIM)
        norm = sum(x * x for x in v) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_vectorize_empty_is_zero_vector(self):
        v = ls.vectorize("")
        self.assertEqual(len(v), ls.DIM)
        self.assertEqual(sum(v), 0.0)

    def test_cosine_self_one_zero_vector_zero(self):
        v = ls.vectorize("香蕉高温高湿")
        self.assertAlmostEqual(ls.cosine(v, v), 1.0, places=5)
        self.assertEqual(ls.cosine(v, ls.vectorize("")), 0.0)
        self.assertEqual(ls.cosine([], []), 0.0)

    # --- 建索引与检索 ---
    def test_rebuild_counts_four_corpora(self):
        r = ls.rebuild(force=True)
        self.assertTrue(r["fts"])
        self.assertEqual(r["rows"]["crops"], 110)
        self.assertEqual(r["rows"]["zones"], 6)
        self.assertEqual(r["rows"]["pests"], 23)
        self.assertEqual(r["rows"]["recipes"], 110)
        self.assertEqual(r["total"], 249)

    def test_rebuild_does_not_modify_source_json(self):
        src = os.path.join(ROOT, "data", "crop_adapt_db.json")
        before = open(src, "rb").read()
        ls.rebuild(force=True)
        self.assertEqual(open(src, "rb").read(), before,
                         "建索引不得修改作物库源文件")

    def test_search_exact_beats_semantic(self):
        ls.rebuild(force=True)
        hits = ls.search("香蕉")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["exact"], 1.0)
        self.assertGreater(hits[0]["score"], 1.0)

    def test_search_keyword_layer_works(self):
        ls.rebuild(force=True)
        hits = ls.search("蚜虫 症状", corpus="pests")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["keyword"], 1.0)
        self.assertIn("蚜虫", hits[0]["entity"])

    def test_search_vector_only_mode(self):
        ls.rebuild(force=True)
        hits = ls.search("高温", mode="vector", k=3)
        self.assertTrue(hits)
        for h in hits:
            self.assertEqual(h["exact"], 0.0)
            self.assertEqual(h["keyword"], 0.0)
            self.assertGreater(h["vector"], 0.0)

    def test_search_keyword_only_mode(self):
        ls.rebuild(force=True)
        hits = ls.search("香蕉", mode="keyword", k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["vector"], 0.0)

    def test_search_exact_only_mode(self):
        ls.rebuild(force=True)
        hits = ls.search("香蕉", mode="exact", k=5)
        self.assertTrue(all(h["exact"] == 1.0 for h in hits))

    def test_search_corpus_filter(self):
        ls.rebuild(force=True)
        hits = ls.search("香蕉", corpus="zones")
        for h in hits:
            self.assertEqual(h["corpus"], "zones")

    def test_search_empty_query_returns_empty(self):
        ls.rebuild(force=True)
        self.assertEqual(ls.search(""), [])
        self.assertEqual(ls.search("   "), [])

    def test_search_without_index_returns_empty(self):
        self.assertEqual(ls.search("香蕉"), [])
        self.assertFalse(ls.stats()["built"])

    def test_stats_reports_rows(self):
        ls.rebuild(force=True)
        s = ls.stats()
        self.assertTrue(s["built"])
        self.assertEqual(s["total"], 249)
        self.assertIn("crops", s["rows"])
        self.assertTrue(s["path"], "stats 应报告索引文件路径")

    def test_hits_include_traceability(self):
        ls.rebuild(force=True)
        hits = ls.search("蚜虫", corpus="pests", k=1)
        h = hits[0]
        for k in ("corpus", "entity", "snippet", "meta", "source_file"):
            self.assertIn(k, h)
        self.assertTrue(h["source_file"])
        self.assertIn("蚜虫", h["snippet"])

    def test_snippet_bounded(self):
        ls.rebuild(force=True)
        hits = ls.search("番茄", k=5)
        for h in hits:
            self.assertLessEqual(len(h["snippet"]), 120)

    def test_min_score_filters_noise(self):
        ls.rebuild(force=True)
        all_hits = ls.search("高温 高湿", k=20)
        strict = ls.search("高温 高湿", k=20, min_score=0.5)
        self.assertLessEqual(len(strict), len(all_hits))


# ===========================================================================
# B4 条件锚定执行器
# ===========================================================================
class TestRecipeScheduler(_Isolated):
    def _recipe(self):
        return {
            "crop": {"species": "测试番茄"},
            "stage": "fruiting",
            "environment": {
                "temperature": {"day_c": 32, "night_c": 15},
                "humidity": {"min_pct": 50, "max_pct": 80},
                "water_nutrient": {"ph": 6.4, "water_ml_day": 350},
                "airflow": {"level": "medium"},
            },
            "exception_handling": [
                {"condition": "出现「早疫」相关症状",
                 "action": "诊断后处理", "severity": "warn"},
            ],
        }

    def test_anchors_extracted(self):
        anchors = rs.anchors_from_recipe(self._recipe())
        ids = {a["id"] for a in anchors}
        for expect in ("temp_day_high", "temp_night_low", "humidity_high",
                       "humidity_low", "ph_high", "ph_low", "water_shortfall",
                       "exception_00"):
            self.assertIn(expect, ids)
        self.assertEqual(sum(1 for a in anchors if a["kind"] == "threshold"), 7)

    def test_anchors_from_empty_recipe(self):
        self.assertEqual(rs.anchors_from_recipe({}), [])
        self.assertEqual(rs.anchors_from_recipe({"environment": {}}), [])

    def test_evaluate_satisfied_and_waiting(self):
        a = {"field": "humidity_pct", "op": ">=", "value": 80}
        self.assertTrue(rs.evaluate(a, {"humidity_pct": 92})["satisfied"])
        ev = rs.evaluate(a, {"humidity_pct": 60})
        self.assertFalse(ev["satisfied"])
        self.assertEqual(ev["op"], ">=")
        self.assertEqual(ev["target"], 80)
        self.assertEqual(ev["gap"], 20)

    def test_all_operators_supported(self):
        # (标签, 比较符, 锚点阈值, 观测值, 期望)
        cases = [("gt", ">", 1, 2, True), ("gt2", ">", 2, 2, False),
                 ("ge", ">=", 2, 2, True), ("le", "<=", 2, 2, True),
                 ("lt", "<", 3, 2, True), ("eq", "==", 2, 2, True),
                 ("ne", "!=", 2, 3, True), ("ne2", "!=", 2, 2, False)]
        for _, op, val, cur, expect in cases:
            a = {"field": "x", "op": op, "value": val}
            self.assertEqual(rs.evaluate(a, {"x": cur})["satisfied"], expect,
                             "op=%s val=%s cur=%s" % (op, val, cur))
        self.assertEqual(len(rs.OPS), 6)

    def test_nan_rejected_as_observation(self):
        a = {"field": "humidity_pct", "op": "<=", "value": 50}
        ev = rs.evaluate(a, {"humidity_pct": float("nan")})
        self.assertFalse(ev["satisfied"])
        self.assertIsNone(ev["current"])
        self.assertIn("缺观测", ev["reason"])

    def test_bool_rejected_as_observation(self):
        a = {"field": "humidity_pct", "op": ">=", "value": 1}
        self.assertFalse(rs.evaluate(a, {"humidity_pct": True})["satisfied"])

    def test_missing_observation_is_waiting_not_satisfied(self):
        a = {"field": "ph", "op": ">", "value": 6.4}
        ev = rs.evaluate(a, {})
        self.assertFalse(ev["satisfied"])
        self.assertIn("缺观测字段 ph", ev["reason"])

    def test_unknown_operator_rejected(self):
        ev = rs.evaluate({"field": "x", "op": "~~", "value": 1}, {"x": 1})
        self.assertFalse(ev["satisfied"])
        self.assertIn("未知比较符", ev["reason"])

    def test_bad_value_rejected(self):
        ev = rs.evaluate({"field": "x", "op": ">", "value": "多"}, {"x": 1})
        self.assertFalse(ev["satisfied"])
        self.assertIn("缺省值非法", ev["reason"])

    def test_alias_resolution(self):
        a = {"field": "humidity_pct", "op": ">=", "value": 80}
        for alias in ("humidity_pct", "humidity", "rh"):
            self.assertTrue(rs.evaluate(a, {alias: 92})["satisfied"])
        a2 = {"field": "temp_c", "op": ">=", "value": 30}
        for alias in ("temp_c", "temp", "temperature", "day_temp"):
            self.assertTrue(rs.evaluate(a2, {alias: 35})["satisfied"])

    def test_next_actions_ready_and_waiting(self):
        r = self._recipe()
        out = rs.next_actions(r, {"humidity_pct": 92, "temp_c": 34})
        ready_ids = {x["anchor_id"] for x in out["ready"]}
        self.assertIn("humidity_high", ready_ids)
        self.assertIn("temp_day_high", ready_ids)
        self.assertNotIn("temp_night_low", ready_ids)
        self.assertGreater(out["summary"]["ready_count"], 0)
        self.assertGreater(out["summary"]["waiting_count"], 0)
        self.assertEqual(out["summary"]["anchors_total"],
                         len(rs.anchors_from_recipe(r)))

    def test_next_actions_sorted_by_severity(self):
        r = self._recipe()
        r["exception_handling"][0]["severity"] = "info"
        out = rs.next_actions(r, {"humidity_pct": 92, "temp_c": 34})
        sev = [x["severity"] for x in out["ready"]]
        rank = {"critical": 0, "error": 1, "warn": 2, "info": 3}
        self.assertEqual(sev, sorted(sev, key=lambda s: rank.get(s, 4)))

    def test_keyword_anchor_hits_on_symptom_text(self):
        r = self._recipe()
        out = rs.next_actions(r, {}, symptom_text="叶片出现早疫斑点")
        ready = {x["anchor_id"] for x in out["ready"]}
        self.assertIn("exception_00", ready)
        out2 = rs.next_actions(r, {}, symptom_text="叶片发黄")
        self.assertNotIn("exception_00",
                         {x["anchor_id"] for x in out2["ready"]})

    def test_keywords_extracted_from_quoted_condition(self):
        kws = rs._keywords_of("出现「冻害」相关症状")
        self.assertEqual(kws, ["冻害"])
        self.assertTrue(rs.keyword_hit(
            {"keywords": kws}, "夜间有冻害迹象"))

    def test_fired_dedup_and_cooldown(self):
        r = self._recipe()
        obs = {"humidity_pct": 92, "temp_c": 34}
        first = rs.next_actions(r, obs)
        self.assertGreater(first["summary"]["ready_count"], 0)
        again = rs.next_actions(r, obs, fired=["humidity_high"])
        self.assertNotIn("humidity_high",
                         {x["anchor_id"] for x in again["ready"]})
        self.assertIn("humidity_high", again["skipped"])
        cooled = rs.next_actions(r, obs, cooldown_fields=["humidity_pct"])
        self.assertNotIn("humidity_high",
                         {x["anchor_id"] for x in cooled["ready"]})

    def test_compare_modes_distinguishes(self):
        r = self._recipe()
        obs = {"humidity_pct": 92, "temp_c": 34}
        cmp_ = rs.compare_modes(r, obs)
        self.assertIn("mode_a", cmp_)
        self.assertIn("mode_b", cmp_)
        self.assertTrue(cmp_["interpretation"])
        for key in ("time_only", "condition_only", "both"):
            self.assertIn(key, cmp_)
        self.assertTrue(cmp_["condition_only"],
                        "高温高湿下条件模式应发现时间模式漏做的动作")

    def test_compare_modes_custom_schedule(self):
        r = self._recipe()
        sched = [{"id": "humidity_high", "name": "已有降湿动作"}]
        cmp_ = rs.compare_modes(r, {"humidity_pct": 92}, schedule=sched)
        self.assertEqual([x["anchor_id"] for x in cmp_["both"]],
                         ["humidity_high"])
        self.assertEqual(cmp_["time_only"], [])

    def test_load_recipe_by_crop_and_zone(self):
        r = rs.load_recipe(crop="番茄")
        self.assertEqual(r["crop"]["species"], "番茄")
        # 按分区过滤应命中同名作物在该分区下的配方
        files = [os.path.basename(p) for p in glob.glob(rs.RECIPE_GLOB)
                 if "番茄" in os.path.basename(p)]
        self.assertTrue(files, "番茄配方应存在")
        zone = files[0].split("__")[0]
        r2 = rs.load_recipe(crop="番茄", zone=zone)
        self.assertEqual(r2["crop"]["species"], "番茄")
        self.assertIn(zone, os.path.basename(files[0]))

    def test_load_recipe_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            rs.load_recipe(crop="不存在这种作物")

    def test_anchor_of_real_recipe_is_evaluable(self):
        r = rs.load_recipe(crop="番茄")
        anchors = rs.anchors_from_recipe(r)
        obs = {"temp_c": 999, "humidity_pct": 999, "ph": 999, "water_ml": 999}
        ready = rs.next_actions(r, obs)
        self.assertGreater(len(ready["ready"]), 0)


# ===========================================================================
# B3 三阶段解释链
# ===========================================================================
class TestReasoningChain(unittest.TestCase):
    SYMPTOM = "叶片背面有白色粉状物，像白粉病"

    def test_chain_present_with_three_stages(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        rc = r["reasoning_chain"]
        for stage in ("prediction", "explanation", "mapping"):
            self.assertIn(stage, rc)
        self.assertIn("narrative", rc)
        self.assertTrue(rc["narrative"])

    def test_chain_reflects_gate_status(self):
        env = {"humidity_pct": 92, "temp_c": 24}
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment=env)
        self.assertEqual(r["reasoning_chain"]["mapping"]["gate_status"],
                         r["confirmation_status"])

    def test_confirmed_narrative_says_confirmed(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        self.assertIn("证据充分", r["reasoning_chain"]["narrative"])

    def test_unconfirmed_narrative_says_not_confirmed(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM)
        self.assertEqual(r["confirmation_status"], "unconfirmed")
        self.assertIn("证据不足", r["reasoning_chain"]["narrative"])

    def test_symptom_matches_recorded(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        matches = r["reasoning_chain"]["explanation"]["symptom_matches"]
        primary = r["reasoning_chain"]["prediction"]["primary"]
        self.assertIn(primary, matches)
        self.assertTrue(matches[primary]["name_hit"])
        self.assertIn("白粉", matches[primary]["symptom_keywords"])
        self.assertGreater(matches[primary]["total_score"], 0)

    def test_alternatives_have_lower_score(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        m = r["reasoning_chain"]["explanation"]["symptom_matches"]
        top = r["reasoning_chain"]["prediction"]["primary"]
        top_score = m[top]["total_score"]
        for k, v in m.items():
            if k != top:
                self.assertLessEqual(v["total_score"], top_score)

    def test_mapping_points_to_kb_pattern(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        mp = r["reasoning_chain"]["mapping"]
        self.assertIsNotNone(mp["kb_pattern"])
        self.assertIn("symptoms", mp["kb_pattern"])
        self.assertEqual(mp["kb_pattern_category"], "disease")
        self.assertIn("category_generic", mp)

    def test_environment_section_reports_observation(self):
        env = {"humidity_pct": 92, "temp_c": 24, "ec": 2.1}
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment=env)
        e = r["reasoning_chain"]["explanation"]["environment"]
        self.assertTrue(e["observed"])
        self.assertIn("humidity_pct", e["observed_keys"])
        self.assertEqual(e["values"]["ec"], 2.1)

    def test_environment_section_empty_when_no_observation(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM)
        e = r["reasoning_chain"]["explanation"]["environment"]
        self.assertFalse(e["observed"])
        self.assertEqual(e["observed_keys"], [])
        self.assertEqual(e["values"], {})

    def test_no_symptom_still_has_chain(self):
        r = pest_agent.diagnose(crop="番茄")
        rc = r["reasoning_chain"]
        self.assertIsNone(rc["prediction"]["primary"])
        # 无症状时给每个候选一个 0.1 的底分（不是 0，便于排序稳定）
        self.assertEqual(rc["prediction"]["top_score"], 0.1)
        self.assertIn("无有效症状信号", rc["narrative"])
        # 候选仍会列出，但没有任何一项真正命中症状
        matches = rc["explanation"]["symptom_matches"]
        self.assertTrue(matches)
        for _, v in matches.items():
            self.assertFalse(v["name_hit"])
            self.assertIsNone(v["name_fragment"])
            self.assertEqual(v["symptom_keywords"], [])
            self.assertEqual(v["total_score"], 0.1)

    def test_signature_covers_chain(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM)
        sig = r["signature"]
        self.assertEqual(len(sig), 64)
        # 篡改解释链后签名必须不一致
        r["reasoning_chain"]["prediction"]["match_quality"] = 0.01
        import hashlib
        import agent.pest_agent as pa
        r.pop("signature")
        self.assertNotEqual(
            sig,
            hashlib.sha256(pa._canonical(r).encode("utf-8")).hexdigest())

    def test_no_placeholder_in_result(self):
        r = pest_agent.diagnose(crop="番茄", symptom_description=self.SYMPTOM,
                                environment={"humidity_pct": 92, "temp_c": 24})
        self.assertNotIn("PLACEHOLDER", json.dumps(r, ensure_ascii=False))

    def test_pestagent_class_wrapper_passes_chain(self):
        a = pest_agent.PestAgent()
        r = a.run({"crop": "番茄", "symptom_description": self.SYMPTOM,
                   "environment": {"humidity_pct": 92, "temp_c": 24}})
        self.assertIn("reasoning_chain", r)


# ===========================================================================
# 集成：编排器 + harness 清单
# ===========================================================================
class TestIntegration(_Isolated):
    def setUp(self):
        super().setUp()
        self.set_env("AGRI_LONG_TERM_MEMORY",
                     os.path.join(self.tmp, "mem.json"))
        self.set_env("AGRI_SEARCH_INDEX", os.path.join(self.tmp, "idx.db"))
        wim.clear_registry()

    def _req(self, lat=30.2741, lon=120.1551):
        return {"lat": lat, "lon": lon, "scene": "balcony", "floor": 15,
                "orientation": "south", "purpose": "食用", "space_sqm": 1.5,
                "difficulty": "beginner", "budget_cny": 500}

    def test_pipeline_attaches_work_item_done(self):
        from agent.orchestrator import AgriOrchestrator
        o = AgriOrchestrator()
        r = o.run_pipeline(self._req(), work_item_id="wi-it-1")
        self.assertEqual(r["work_item"]["state"], "done")
        self.assertEqual(r["work_item"]["item_id"], "wi-it-1")
        states = [a["to"] for a in r["work_item_audit"]]
        self.assertEqual(states, ["created", "executing", "pending_review",
                                  "integrating", "done"])

    def test_pipeline_records_and_recalls_memory(self):
        from agent.orchestrator import AgriOrchestrator
        o = AgriOrchestrator()
        r1 = o.run_pipeline(self._req(), work_item_id="wi-it-2")
        self.assertTrue(r1.get("memory_id"))
        self.assertEqual(r1["prior_memory"], [])
        r2 = o.run_pipeline(self._req(), session_id="s-2",
                            work_item_id="wi-it-3")
        self.assertGreater(len(r2["prior_memory"]), 0)
        self.assertIn("分区", r2["prior_memory"][0]["summary"])
        self.assertEqual(ltm.stats()["memories"], 2)

    def test_pipeline_memory_can_be_disabled(self):
        from agent.orchestrator import AgriOrchestrator
        o = AgriOrchestrator()
        o.run_pipeline(self._req(), record_memory=False)
        self.assertEqual(ltm.stats()["memories"], 0)

    def test_pipeline_work_item_can_be_skipped(self):
        from agent.orchestrator import AgriOrchestrator
        o = AgriOrchestrator()
        r = o.run_pipeline(self._req(), verify=False)
        self.assertEqual(r["work_item"]["state"], "done")
        # verify=False 走 review(跳过复核) → integrate → done
        notes = [a.get("note", "") for a in r["work_item_audit"]]
        self.assertTrue(any("跳过复核" in n for n in notes))

    def test_pipeline_failure_goes_to_rework(self):
        from agent.orchestrator import AgriOrchestrator
        o = AgriOrchestrator()
        # 0,0 坐标会落在非真实分区，制造复核失败
        r = o.run_pipeline({"lat": 0, "lon": 0, "scene": "balcony",
                            "budget_cny": 0}, work_item_id="wi-it-4",
                           verify=True)
        if r["verification"].get("passed"):
            self.skipTest("该输入未触发复核失败")
        self.assertEqual(r["work_item"]["state"], "rework")
        self.assertEqual(r["work_item"]["rework_count"], 1)
        self.assertTrue(r["work_item_audit"][-1]["note"])

    def test_harness_manifest_registers_new_sections(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hs_v4", os.path.join(ROOT, "scripts", "harness_sync.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        m = mod.build_manifest()
        for k in ("long_term_memory", "local_search", "recipe_scheduler"):
            self.assertIn(k, m)
            self.assertNotIn("error", m[k], "%s 不应报错" % k)
        for k in ("long_term_memory", "local_search", "recipe_scheduler"):
            self.assertIn(k, mod.OBSERVED_SECTIONS)
        self.assertEqual(m["version"], "2.2.0")

    def test_manifest_new_sections_have_no_paths(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hs_v4b", os.path.join(ROOT, "scripts", "harness_sync.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        m = mod.build_manifest()
        self.assertNotIn("path", m["long_term_memory"])
        self.assertNotIn("path", m["local_search"])

    def test_recipe_scheduler_obs_counts_real_recipes(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hs_v4c", os.path.join(ROOT, "scripts", "harness_sync.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        obs = mod._recipe_scheduler_obs()
        self.assertEqual(obs["recipes_scanned"], 110)
        self.assertGreater(obs["anchors_total"], 0)
        self.assertEqual(sum(obs["anchors_by_kind"].values()),
                         obs["anchors_total"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()
    unittest.main(verbosity=2 if args.verbose else 1)
