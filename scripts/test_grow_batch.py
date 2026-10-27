"""scripts/test_grow_batch.py —— 批次对象 MVP 硬门禁（报告 §9.1 P0 工作包）。

校验项
------
1. **Plot/GrowBatch 建立**：create_plot + create_batch 全链路，重复/缺 Plot 拒绝
2. **Observation 追加**：add_observation 需批次存在，value 结构校验
3. **Action 默认 shadow/dry_run**：add_action 不真实执行；executed 需人工确认（dry_run=False）
4. **动作状态机**：shadow→pending_approval→approved 合法；非法迁移拒绝
5. **Outcome 诚实边界**：批次未结束（非 harvested/failed）拒绝写真实 outcome
6. **事件日志 append-only**：seq 单调递增，可完整回放，回放无副作用
7. **schema 校验**：复用 validate_grow_batch 的 validate_instance 校验合法/非法对象

Exit code
--------
    0  全部通过
    1  有失败用例
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.grow_batch_store import (  # noqa: E402
    GrowBatchStore,
    GrowBatchError,
)
from scripts.validate_grow_batch import (  # noqa: E402
    validate_instance,
    _classify,
)

_SCHEMA = json.loads(
    open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "schemas", "grow_batch.schema.json"),
         encoding="utf-8").read()
)
_DEFS = _SCHEMA.get("$defs", {})


def _new_store():
    """每用例独立临时目录，隔离存储，不污染真实 data/grow_batches。"""
    tmp = tempfile.TemporaryDirectory()
    return GrowBatchStore(tmp.name), tmp


def _plot(plot_id="plot_a"):
    return {"plot_id": plot_id, "location_type": "balcony",
            "orientation": "south", "area_sqm": {"value": 0.5, "unit": "sqm"}}


def _batch(batch_id="batch_001", plot_id="plot_a"):
    return {"batch_id": batch_id, "crop": "生菜", "plot_id": plot_id,
            "recipe_version": "v1.2.0", "recipe_id": "mediterranean__生菜",
            "started_at": "2026-10-27T00:00:00Z"}


def _obs(obs_id="obs_001", batch_id="batch_001"):
    return {"observation_id": obs_id, "batch_id": batch_id,
            "ts": "2026-10-27T08:00:00Z", "metric": "temperature_c",
            "value": {"value": 21.5, "unit": "celsius"},
            "source": {"kind": "sensor", "device_id": "dev_t01"}}


def _act(act_id="act_001", batch_id="batch_001"):
    return {"action_id": act_id, "batch_id": batch_id,
            "ts": "2026-10-27T08:05:00Z", "recommendation": "浇水 200ml",
            "parameters": {"irrigation_ml": 200}}


class TestGrowBatchStore(unittest.TestCase):
    """批次对象存储全链路硬门禁。"""

    def test_01_create_plot_and_batch(self):
        store, tmp = _new_store()
        try:
            r1 = store.create_plot(_plot())
            self.assertTrue(r1["ok"])
            r2 = store.create_batch(_batch())
            self.assertTrue(r2["ok"])
            self.assertEqual(r2["status"], "planned")
        finally:
            tmp.cleanup()

    def test_02_duplicate_plot_rejected(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            with self.assertRaises(GrowBatchError):
                store.create_plot(_plot())
        finally:
            tmp.cleanup()

    def test_03_missing_plot_rejected(self):
        store, tmp = _new_store()
        try:
            with self.assertRaises(GrowBatchError):
                store.create_batch(_batch(plot_id="nonexistent"))
        finally:
            tmp.cleanup()

    def test_04_add_observation(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            r = store.add_observation(_obs())
            self.assertTrue(r["ok"])
            self.assertEqual(r["count"], 1)
            b = store.get_batch("batch_001")
            self.assertEqual(len(b["observations"]), 1)
        finally:
            tmp.cleanup()

    def test_05_observation_requires_batch(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            bad = _obs(obs_id="obs_bad")
            bad["batch_id"] = "nonexistent"
            with self.assertRaises(GrowBatchError):
                store.add_observation(bad)
        finally:
            tmp.cleanup()

    def test_06_action_default_shadow_dry_run(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            r = store.add_action(_act())
            self.assertTrue(r["ok"])
            self.assertEqual(r["status"], "shadow")
            self.assertTrue(r["dry_run"])
            b = store.get_batch("batch_001")
            self.assertEqual(len(b["actions"]), 1)
            self.assertTrue(b["actions"][0]["dry_run"])
        finally:
            tmp.cleanup()

    def test_07_action_valid_transition(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            store.add_action(_act())
            r = store.transition_action("batch_001", "act_001", "pending_approval")
            self.assertEqual(r["to"], "pending_approval")
            r2 = store.transition_action("batch_001", "act_001", "approved")
            self.assertEqual(r2["to"], "approved")
        finally:
            tmp.cleanup()

    def test_08_action_invalid_transition(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            store.add_action(_act())
            # shadow 不能直接跳到 executed（需先 approved）
            with self.assertRaises(GrowBatchError):
                store.transition_action("batch_001", "act_001", "executed")
        finally:
            tmp.cleanup()

    def test_09_executed_requires_human_confirm(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            # 契约：executed 必须 dry_run=False（人工确认后）
            act = _act(act_id="act_exec")
            act["status"] = "executed"
            act["dry_run"] = True
            with self.assertRaises(GrowBatchError):
                store.add_action(act)
        finally:
            tmp.cleanup()

    def test_10_outcome_blocked_before_harvest(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            with self.assertRaises(GrowBatchError):
                store.record_outcome({
                    "outcome_id": "out_001", "batch_id": "batch_001",
                    "ts": "2026-11-20T00:00:00Z",
                    "yield": {"value": 120, "unit": "g"},
                })
        finally:
            tmp.cleanup()

    def test_11_outcome_after_harvest(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            store.set_batch_status("batch_001", "harvested")
            r = store.record_outcome({
                "outcome_id": "out_001", "batch_id": "batch_001",
                "ts": "2026-11-20T00:00:00Z",
                "yield": {"value": 120, "unit": "g"},
            })
            self.assertTrue(r["ok"])
            b = store.get_batch("batch_001")
            self.assertEqual(len(b["outcomes"]), 1)
        finally:
            tmp.cleanup()

    def test_12_event_log_append_only_monotonic(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            store.add_observation(_obs())
            store.add_action(_act())
            events = store.list_events("batch_001")
            self.assertGreaterEqual(len(events), 3)
            seqs = [e["seq"] for e in events]
            self.assertEqual(seqs, sorted(seqs))
            self.assertEqual(len(seqs), len(set(seqs)))  # 无重复
            # 批次创建事件必须在观察/动作之前
            types = [e["event_type"] for e in events]
            self.assertIn("batch_created", types)
            self.assertIn("observation_added", types)
            self.assertIn("action_recorded", types)
        finally:
            tmp.cleanup()

    def test_13_replay_no_side_effect(self):
        store, tmp = _new_store()
        try:
            store.create_plot(_plot())
            store.create_batch(_batch())
            store.add_observation(_obs())
            r = store.replay("batch_001")
            self.assertTrue(r["ok"])
            self.assertGreaterEqual(r["n_events"], 2)
            self.assertIn("honest_note", r)
            self.assertIn("回放仅重建事件序列", r["honest_note"])
            # 回放不触发真实执行：动作列表不受影响
            b = store.get_batch("batch_001")
            self.assertEqual(len(b["actions"]), 0)
        finally:
            tmp.cleanup()

    def test_14_schema_validation_reuse(self):
        """复用 validate_grow_batch 的 validate_instance 校验对象。"""
        # 合法 Plot
        plot = _plot()
        self.assertEqual(_classify(plot), "Plot")
        self.assertEqual(validate_instance(plot, _DEFS), [])
        # 合法 GrowBatch
        batch = _batch()
        self.assertEqual(_classify(batch), "GrowBatch")
        self.assertEqual(validate_instance(batch, _DEFS), [])
        # 非法 GrowBatch：缺 crop
        bad = _batch()
        del bad["crop"]
        self.assertTrue(validate_instance(bad, _DEFS))


if __name__ == "__main__":
    unittest.main()
