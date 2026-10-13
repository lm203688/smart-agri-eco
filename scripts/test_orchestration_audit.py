"""
scripts/test_orchestration_audit.py — M10-O2 + M10-O4 单测

覆盖：
- TraceRecord 基本功能（trace_id / summary_hash / to_dict / total_ms）
- 一致性检查 5 条规则的通过/触发分支
- _input_summary / _output_summary 各 Agent 分支
- Orchestrator 集成（result 里含 consistency_audit 与 orchestration_trace）
- 审计故障不阻断主流水线
"""
import json
import os
import sys
import tempfile
import time
import unittest
from typing import Any, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.orchestration_audit import (
    _CONSISTENCY_CHECKS,
    _input_summary,
    _output_summary,
    TraceRecord,
    check_cross_agent_consistency,
    export_trace_dict,
    export_trace_json,
)


def _build_result(**overrides: Any) -> Dict[str, Any]:
    """构造最小 pipeline result（4 个 Agent 输出）。"""
    climate = overrides.get("climate", {
        "evidence": {"zone_id": "subtropical_wet"},
        "constraints": {"min_temp": -5, "max_temp": 35},
        "confidence": {"rubric_score": 0.8},
    })
    crop_reco = overrides.get("crop_reco", {
        "recommendation": [
            {"crop": "番茄", "adapt_score": 0.9},
            {"crop": "生菜", "adapt_score": 0.8},
        ],
    })
    growth = overrides.get("growth", {
        "recommendation": {
            "crop": "番茄", "total_days": 90, "phases": [{"name": "育苗"}],
        },
    })
    eco = overrides.get("eco", {
        "recommendation": [
            {"name": "育苗盘", "price_cny": 20},
            {"name": "滴灌套装", "price_cny": 50},
        ],
    })
    return {
        "pipeline_steps": [
            {"agent": "ClimateAgent", "output": climate},
            {"agent": "CropAgent", "output": crop_reco},
            {"agent": "GrowthAgent", "output": growth},
            {"agent": "EcoAgent", "output": eco},
        ],
        "final_recommendation": {
            "zone": climate.get("evidence", {}).get("zone_id"),
            "recommended_crops": crop_reco.get("recommendation"),
            "growth_plan": growth,
            "devices": eco.get("recommendation"),
        },
        "trust_summary": {"overall_rubric_score": 0.8, "known_limitations": []},
    }


class TestTraceRecord(unittest.TestCase):
    def test_basic_construction(self):
        tr = TraceRecord({"lat": 30.0, "lon": 120.0})
        self.assertEqual(len(tr.trace_id), 16)
        self.assertGreater(tr.started_at, 0)
        self.assertIsNone(tr.ended_at)
        self.assertEqual(tr.steps, [])

    def test_add_step_and_finish(self):
        tr = TraceRecord({"x": 1})
        t0 = time.time()
        tr.add_step("ClimateAgent", t0, t0 + 0.1,
                    {"lat": 30}, {"zone_id": "subtropical_wet"})
        self.assertEqual(len(tr.steps), 1)
        self.assertEqual(tr.steps[0]["agent"], "ClimateAgent")
        self.assertAlmostEqual(tr.steps[0]["duration_ms"], 100.0, delta=1.0)
        tr.finish()
        self.assertIsNotNone(tr.ended_at)
        self.assertGreater(tr.total_ms(), 0)

    def test_summary_hash_stable_for_same_input(self):
        t0 = time.time()
        tr1 = TraceRecord({"lat": 30.0, "lon": 120.0})
        tr1.add_step("A", t0, t0 + 0.1, {"a": 1}, {"b": 2})
        tr1.finish()
        tr2 = TraceRecord({"lat": 30.0, "lon": 120.0})
        tr2.add_step("A", t0, t0 + 0.1, {"a": 1}, {"b": 2})
        tr2.finish()
        # 相同输入 + 相同 steps 数 → 相同 hash（trace_id 会变，因为随机）
        self.assertEqual(tr1.summary_hash(), tr2.summary_hash())
        self.assertEqual(len(tr1.summary_hash()), 16)

    def test_to_dict_structure(self):
        tr = TraceRecord({"lat": 30})
        t0 = time.time()
        tr.add_step("ClimateAgent", t0, t0 + 0.1, {}, {"zone_id": "x"})
        tr.finish()
        d = tr.to_dict()
        for key in ("trace_id", "summary_hash", "started_at", "ended_at",
                    "total_ms", "input_request", "steps", "extra"):
            self.assertIn(key, d, f"missing key: {key}")
        self.assertEqual(len(d["steps"]), 1)

    def test_different_inputs_different_hash(self):
        tr1 = TraceRecord({"lat": 30})
        tr2 = TraceRecord({"lat": 40})
        self.assertNotEqual(tr1.summary_hash(), tr2.summary_hash())


class TestConsistencyChecks(unittest.TestCase):
    def test_baseline_scenario_passes(self):
        """典型场景（subtropical_wet + 番茄 + 常规设备）应无 error。"""
        r = check_cross_agent_consistency(_build_result(),
                                          {"budget_cny": 200, "start_date": "2026-03-01"})
        self.assertTrue(r["passed"])
        self.assertEqual(r["severity_counts"]["error"], 0)

    def test_budget_overflow_triggers_warning(self):
        eco = {"recommendation": [
            {"name": "育苗盘", "price_cny": 200},
            {"name": "滴灌套装", "price_cny": 150},
            {"name": "营养液泵", "price_cny": 200},
        ]}
        r = check_cross_agent_consistency(_build_result(eco=eco),
                                          {"budget_cny": 300, "start_date": "2026-03-01"})
        conflicts = [c for c in r["conflicts"] if c["check"] == "eco_devices_budget_fit"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["severity"], "warning")
        self.assertEqual(conflicts[0]["recommended_total"], 550)
        # 但 passed 仍为 True（warning 不阻断）
        self.assertTrue(r["passed"])

    def test_cold_zone_winter_frost_warning(self):
        """寒冷分区 + 冬季月份播种 → info 级警告。"""
        climate = {
            "evidence": {"zone_id": "subarctic"},
            "constraints": {"min_temp": -25, "max_temp": 15},
            "confidence": {"rubric_score": 0.7},
        }
        r = check_cross_agent_consistency(
            _build_result(climate=climate),
            {"budget_cny": 100, "start_date": "2026-01-15"},
        )
        frost = [c for c in r["conflicts"] if c["check"] == "growth_start_date_frost"]
        self.assertEqual(len(frost), 1)
        self.assertEqual(frost[0]["severity"], "info")

    def test_warm_start_date_no_frost_warning(self):
        """寒冷分区但春播不触发冻害警告。"""
        climate = {
            "evidence": {"zone_id": "subarctic"},
            "constraints": {"min_temp": -25, "max_temp": 15},
            "confidence": {"rubric_score": 0.7},
        }
        r = check_cross_agent_consistency(
            _build_result(climate=climate),
            {"budget_cny": 100, "start_date": "2026-04-01"},
        )
        frost = [c for c in r["conflicts"] if c["check"] == "growth_start_date_frost"]
        self.assertEqual(len(frost), 0)

    def test_growth_crop_mismatch_info(self):
        """GrowthAgent 与 CropAgent 首推不一致 → info 级记录。"""
        growth = {"recommendation": {"crop": "生菜", "phases": []}}
        r = check_cross_agent_consistency(_build_result(growth=growth),
                                          {"budget_cny": 200})
        info = [c for c in r["conflicts"] if c["check"] == "growth_crop_match"]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0]["severity"], "info")

    def test_climate_constraints_coverage_warning(self):
        """CropAgent 首推作物温度窗口未被 ClimateAgent 分区覆盖 → warning。"""
        # 分区窗口 [15, 30] 覆盖不了番茄经验窗口 [-5, 40]
        climate = {
            "evidence": {"zone_id": "tropical_rainforest"},
            "constraints": {"min_temp": 15, "max_temp": 30},
            "confidence": {"rubric_score": 0.7},
        }
        r = check_cross_agent_consistency(_build_result(climate=climate), {})
        cov = [c for c in r["conflicts"] if c["check"] == "climate_constraints_coverage"]
        self.assertEqual(len(cov), 1)
        self.assertEqual(cov[0]["severity"], "warning")

    def test_no_crop_skips_crop_checks(self):
        """CropAgent 无推荐 → 依赖 crop 的检查应跳过。"""
        crop_reco = {"recommendation": []}
        r = check_cross_agent_consistency(_build_result(crop_reco=crop_reco), {})
        # growth_crop_match 与 climate_constraints_coverage 依赖 top_crop
        # 无 top_crop 时不触发
        self.assertFalse(any(c["check"] == "growth_crop_match" for c in r["conflicts"]))
        self.assertFalse(any(c["check"] == "climate_constraints_coverage" for c in r["conflicts"]))

    def test_advisory_only_passes_even_with_conflicts(self):
        """核心纪律：警告不阻断通过。"""
        eco = {"recommendation": [{"name": "贵设备", "price_cny": 5000}]}
        climate = {
            "evidence": {"zone_id": "subarctic"},
            "constraints": {"min_temp": -25, "max_temp": 15},
            "confidence": {"rubric_score": 0.7},
        }
        r = check_cross_agent_consistency(
            _build_result(climate=climate, eco=eco),
            {"budget_cny": 100, "start_date": "2026-12-01"},
        )
        self.assertTrue(r["passed"], "warning/info 不阻断通过")
        self.assertGreaterEqual(r["conflicts_count"], 2)

    def test_conflict_agents_reference_both_agents(self):
        """冲突条目应显式引用涉及的 Agent 名。"""
        eco = {"recommendation": [{"name": "贵设备", "price_cny": 500}]}
        r = check_cross_agent_consistency(_build_result(eco=eco),
                                          {"budget_cny": 100})
        budget_c = [c for c in r["conflicts"] if c["check"] == "eco_devices_budget_fit"][0]
        self.assertIn("EcoAgent", budget_c["agents"])

    def test_checked_count_matches_rules(self):
        r = check_cross_agent_consistency(_build_result(), {})
        self.assertEqual(r["checked"], len(_CONSISTENCY_CHECKS))


class TestSummaryHelpers(unittest.TestCase):
    def test_input_summary_keeps_key_fields(self):
        s = _input_summary("ClimateAgent",
                           {"lat": 30, "lon": 120, "scene": "balcony",
                            "unknown_key": "ignored"})
        self.assertEqual(s["lat"], 30)
        self.assertEqual(s["lon"], 120)
        self.assertNotIn("unknown_key", s)

    def test_input_summary_truncates_nested(self):
        zone_data = {k: v for k, v in zip(
            ["a", "b", "c", "d", "e", "f", "g", "h"], [1, 2, 3, 4, 5, 6, 7, 8]
        )}
        s = _input_summary("CropAgent", {"zone_data": zone_data})
        # zone_data 摘要只保留前 6 键
        self.assertEqual(len(s["zone_data"]), 6)

    def test_output_summary_climate_agent(self):
        out = _output_summary("ClimateAgent", {
            "evidence": {"zone_id": "x", "climate_class": "Cfa",
                         "data_sources": ["A", "B"]},
            "constraints": {"min_temp": -5, "max_temp": 40},
            "confidence": {"rubric_score": 0.85},
        })
        self.assertEqual(out["zone_id"], "x")
        self.assertEqual(out["min_temp"], -5)
        self.assertEqual(out["rubric_score"], 0.85)

    def test_output_summary_crop_agent_top3(self):
        recos = [{"crop": f"c{i}", "adapt_score": 0.5 + i * 0.1,
                  "reason": "x" * 100} for i in range(5)]
        out = _output_summary("CropAgent", {"recommendation": recos})
        self.assertEqual(len(out["top3_crops"]), 3)
        self.assertLessEqual(len(out["top3_crops"][0]["reason"]), 60)
        self.assertEqual(out["total_reco"], 5)

    def test_output_summary_eco_agent_devices(self):
        recos = [{"name": f"d{i}", "price_cny": 100, "category": "irrigation"} for i in range(5)]
        out = _output_summary("EcoAgent", {"recommendation": recos})
        self.assertEqual(out["devices_count"], 5)
        self.assertEqual(out["devices"][0]["name"], "d0")

    def test_output_summary_handles_non_dict(self):
        out = _output_summary("UnknownAgent", None)
        self.assertEqual(out["type"], "NoneType")


class TestExportTrace(unittest.TestCase):
    def test_export_trace_dict_with_audit(self):
        tr = TraceRecord({"lat": 30})
        t0 = time.time()
        tr.add_step("ClimateAgent", t0, t0 + 0.1, {}, {"zone_id": "x"})
        tr.finish()
        result = {
            "consistency_audit": {"passed": True, "conflicts_count": 0},
            "verification": {"passed": True},
            "trust_summary": {"overall_rubric_score": 0.8},
        }
        d = export_trace_dict(tr, result)
        self.assertIn("audit", d)
        self.assertTrue(d["audit"]["consistency"]["passed"])
        self.assertIn("trace_id", d)
        self.assertIn("summary_hash", d)

    def test_export_trace_json_roundtrip(self):
        tr = TraceRecord({"lat": 30})
        t0 = time.time()
        tr.add_step("ClimateAgent", t0, t0 + 0.1, {}, {"zone_id": "x"})
        tr.finish()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trace.json")
            export_trace_json(tr, path)
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.assertEqual(d["trace_id"], tr.trace_id)
            self.assertEqual(len(d["steps"]), 1)

    def test_export_trace_without_audit(self):
        tr = TraceRecord({})
        tr.finish()
        d = export_trace_dict(tr, None)
        self.assertNotIn("audit", d)


class TestOrchestratorIntegration(unittest.TestCase):
    """集成测试：orchestrator.run_pipeline 应写入 consistency_audit 与 orchestration_trace。"""

    def _run_pipeline(self, user_request: Dict[str, Any]):
        from agent.orchestrator import AgriOrchestrator
        return AgriOrchestrator().run_pipeline(
            user_request, session_id=None, verify=True, record_memory=False)

    def test_pipeline_result_contains_audit(self):
        result = self._run_pipeline({
            "lat": 30.0, "lon": 120.0, "scene": "balcony",
            "floor": 5, "orientation": "south", "purpose": "食用",
            "space_sqm": 1.5, "difficulty": "beginner", "budget_cny": 300,
        })
        self.assertIn("consistency_audit", result)
        self.assertIn("orchestration_trace", result)
        self.assertNotIn("audit_error", result)

    def test_pipeline_trace_has_all_agents(self):
        result = self._run_pipeline({
            "lat": 30.0, "lon": 120.0, "scene": "balcony",
            "budget_cny": 300,
        })
        trace = result["orchestration_trace"]
        agent_names = [s["agent"] for s in trace["steps"]]
        for expected in ("ClimateAgent", "CropAgent", "GrowthAgent", "EcoAgent"):
            self.assertIn(expected, agent_names)

    def test_pipeline_trace_duration_is_positive(self):
        result = self._run_pipeline({
            "lat": 30.0, "lon": 120.0, "scene": "balcony", "budget_cny": 300,
        })
        self.assertGreater(result["orchestration_trace"]["total_ms"], 0)

    def test_pipeline_trace_summary_hash_stable_for_same_input(self):
        """同一输入多次跑 → summary_hash 应稳定（trace_id 会变）。"""
        req = {"lat": 30.0, "lon": 120.0, "scene": "balcony", "budget_cny": 300}
        r1 = self._run_pipeline(req)
        r2 = self._run_pipeline(req)
        h1 = r1["orchestration_trace"]["summary_hash"]
        h2 = r2["orchestration_trace"]["summary_hash"]
        self.assertEqual(h1, h2, "同输入 trace 摘要应稳定（可复算）")
        self.assertNotEqual(
            r1["orchestration_trace"]["trace_id"],
            r2["orchestration_trace"]["trace_id"],
            "trace_id 应唯一（每次生成新 id）",
        )

    def test_pipeline_advisory_only_never_raises(self):
        """审计故障不阻断主流水线（此处仅验证结构完整性）。"""
        # 传入极端场景，触发多个检查冲突
        result = self._run_pipeline({
            "lat": 78.0, "lon": 15.0, "scene": "greenhouse",
            "budget_cny": 50, "start_date": "2026-01-15",
        })
        # 无论审计结果如何，主流水线应完整
        self.assertIn("final_recommendation", result)
        self.assertIn("trust_summary", result)
        # 一致性检查应已执行（可能 passed=False 或有冲突）
        self.assertIn("consistency_audit", result)


if __name__ == "__main__":
    unittest.main()
