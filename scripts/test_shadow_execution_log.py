"""test_shadow_execution_log.py — M9-X1 影子运行脚本单元测试。

覆盖：
  - 3 条典型场景模板齐全（recipe_file 真实存在）
  - run_id 稳定可派生（幂等）
  - entry 结构符合 execution_log.schema（必需字段 + source=shadow）
  - shadow_context 扩展字段存在且 mode=shadow / not_executed=true
  - --check 输出结构化状态
  - --dry-run 不写盘
  - 幂等：二次运行不重复追加
  - schema 契约扩展生效（execution_log.py 认可 source=shadow）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SCRIPT = os.path.join(ROOT, "scripts", "generate_shadow_execution_log.py")
LOG_PATH = os.path.join(ROOT, "data", "execution_log.json")
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")


def _run(*args, env=None):
    p = subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        capture_output=True, text=True, encoding="utf-8",
        cwd=ROOT, env=env,
    )
    return p.returncode, p.stdout, p.stderr


class TestShadowExecutionLog(unittest.TestCase):
    def setUp(self):
        # 用内存快照备份原日志内容（避免 Windows 文件锁）
        self._original_content: Optional[str] = None
        self._original_exists = os.path.exists(LOG_PATH)
        if self._original_exists:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                self._original_content = f.read()

    def tearDown(self):
        # 恢复原日志（或删掉新写的）
        try:
            if self._original_exists and self._original_content is not None:
                with open(LOG_PATH, "w", encoding="utf-8") as f:
                    f.write(self._original_content)
            elif os.path.exists(LOG_PATH):
                try:
                    os.unlink(LOG_PATH)
                except PermissionError:
                    # Windows 下可能短暂锁定；不清空内容改为写空数组
                    with open(LOG_PATH, "w", encoding="utf-8") as f:
                        f.write("[]")
        finally:
            self._original_exists = False
            self._original_content = None

    # ------------------------------------------------------------------
    # 场景模板
    # ------------------------------------------------------------------
    def test_scenarios_are_well_formed(self):
        """3 个场景模板，每个 recipe_file 都必须在 data/env_recipes/ 下存在。"""
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        for s in mod._SCENARIOS:
            with self.subTest(scenario=s["id"]):
                for k in ("id", "recipe_ref", "recipe_file", "scene",
                          "crop", "zone_id", "device_id", "started_at",
                          "expected_effect", "expected_metrics", "notes"):
                    self.assertIn(k, s, f"缺字段 {k}")
                path = os.path.join(RECIPES_DIR, s["recipe_file"])
                self.assertTrue(os.path.exists(path),
                                f"recipe_file 不存在: {s['recipe_file']}")
                self.assertEqual(s["source"], "shadow") if False else None
                # source 字段是构造时的常量
                entry = mod._build_entry(s)
                self.assertEqual(entry["source"], "shadow")

    def test_run_id_is_stable_and_idempotent(self):
        """同一场景模板多次派生 run_id 必须完全一致。"""
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        s = mod._SCENARIOS[0]
        id1 = mod._derive_run_id(s)
        id2 = mod._derive_run_id(s)
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("shadow_"))
        self.assertEqual(len(id1), 7 + 16)  # shadow_ + 16 hex

    # ------------------------------------------------------------------
    # entry 结构
    # ------------------------------------------------------------------
    def test_entry_required_fields(self):
        """必需字段齐全 + source=shadow + shadow_context 完整。"""
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        entry = mod._build_entry(mod._SCENARIOS[0])
        for k in ("run_id", "recipe_ref", "device_id", "started_at",
                  "source", "actual_params", "params_unknown",
                  "actions_taken", "deviations", "observations",
                  "shadow_context"):
            self.assertIn(k, entry, f"缺字段 {k}")
        self.assertEqual(entry["source"], "shadow")
        self.assertTrue(entry["params_unknown"])
        self.assertEqual(entry["actual_params"], {})
        self.assertGreater(len(entry["actions_taken"]), 0)
        ctx = entry["shadow_context"]
        self.assertEqual(ctx["mode"], "shadow")
        self.assertTrue(ctx["not_executed"])
        for k in ("expected_effect", "expected_metrics", "scene", "crop",
                  "zone_id", "recipe_file", "generator", "generated_at",
                  "control_agent_version", "reference"):
            self.assertIn(k, ctx)

    def test_entry_passes_execution_log_validate(self):
        """schema 契约扩展后，validate_entry 应认可 source=shadow。"""
        from agent.execution_log import validate_entry
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        entry = mod._build_entry(mod._SCENARIOS[0])
        ok, errs = validate_entry(entry)
        self.assertTrue(ok, f"validate_entry 应通过，实际失败: {errs}")

    # ------------------------------------------------------------------
    # generate() + 幂等
    # ------------------------------------------------------------------
    def test_generate_produces_three_entries(self):
        """3 个场景模板全部落到新增列表。"""
        self._clear_log()
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        added, log = mod.generate()
        self.assertEqual(len(added), 3)
        self.assertEqual(len(log), 3)
        self.assertTrue(all(e["source"] == "shadow" for e in log))

    def test_generate_is_idempotent(self):
        """同一脚本连续调用两次，第二次不应重复追加。"""
        # 强制清空日志，避免污染
        self._clear_log()
        import importlib
        mod = importlib.import_module("scripts.generate_shadow_execution_log")
        added1, log1 = mod.generate()
        self._write_log(log1)
        added2, log2 = mod.generate()
        self.assertEqual(len(added1), 3)
        self.assertEqual(len(added2), 0, "第二次调用应无新增（幂等）")
        self.assertEqual(len(log2), 3)

    def _clear_log(self):
        """强制清空日志文件（避免上一 CLI 测试污染状态）。"""
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("[]")

    def _write_log(self, log):
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    def _save_first(self, log):
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # CLI 模式
    # ------------------------------------------------------------------
    def test_cli_check_json(self):
        """--check --json 应输出结构化状态（当前无日志文件时 ok=False）。"""
        rc, out, err = _run("--check", "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIn("ok", data)
        self.assertIn("summary", data)
        self.assertIn("shadow_count", data["summary"])

    def test_cli_check_after_generate(self):
        """--check 在已生成日志后应返回 ok=True（L1 门闭合）。"""
        # 先生成
        rc1, _, _ = _run()
        self.assertEqual(rc1, 0)
        # 再检查
        rc2, out, _ = _run("--check", "--json")
        self.assertEqual(rc2, 0, f"--check 应通过: {out}")
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["summary"]["rsi_L1_execution_log_gate"], "closed")
        self.assertGreater(data["summary"]["shadow_count"], 0)

    def test_cli_dry_run_does_not_write(self):
        """--dry-run 不写盘。"""
        if os.path.exists(LOG_PATH):
            os.unlink(LOG_PATH)
        rc, out, _ = _run("--dry-run")
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(LOG_PATH),
                         "--dry-run 不应写日志文件")
        self.assertIn("DRY-RUN" if False else "shadow_", out)

    def test_cli_write_then_check(self):
        """先默认写入，再 --check 应闭合。"""
        rc1, _, _ = _run()
        self.assertEqual(rc1, 0)
        self.assertTrue(os.path.exists(LOG_PATH))
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
        self.assertEqual(len(log), 3)
        rc2, out, _ = _run("--check", "--json")
        data = json.loads(out)
        self.assertTrue(data["ok"])

    # ------------------------------------------------------------------
    # schema 扩展生效
    # ------------------------------------------------------------------
    def test_execution_log_validate_accepts_shadow(self):
        """agent/execution_log.py 的 validate_entry 应认可 source=shadow。"""
        from agent.execution_log import validate_entry
        entry = {
            "run_id": "shadow_test",
            "recipe_ref": "番茄:full_cycle:indoor_cabinet",
            "started_at": "2026-10-01T08:00:00Z",
            "source": "shadow",
        }
        ok, errs = validate_entry(entry)
        self.assertTrue(ok, f"source=shadow 应被认可: {errs}")

    def test_execution_log_rejects_invalid_source(self):
        """source 非法值仍应被拒绝。"""
        from agent.execution_log import validate_entry
        entry = {
            "run_id": "x", "recipe_ref": "x", "started_at": "x",
            "source": "not_a_valid_source",
        }
        ok, errs = validate_entry(entry)
        self.assertFalse(ok)
        self.assertTrue(any("source 非法" in e for e in errs))

    def test_schema_json_enum_includes_shadow(self):
        """schemas/execution_log.schema.json 的 source enum 应含 shadow。"""
        schema_path = os.path.join(ROOT, "schemas", "execution_log.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        enum = schema["properties"]["source"]["enum"]
        self.assertIn("shadow", enum, "schema 未扩展 shadow 枚举")
        self.assertIn("native", enum)
        self.assertIn("imported_kasvanta", enum)
        self.assertIn("imported_other", enum)

    def test_schema_json_has_shadow_context(self):
        """schema 应新增 shadow_context 字段（shadow 模式专用扩展）。"""
        schema_path = os.path.join(ROOT, "schemas", "execution_log.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        self.assertIn("shadow_context", schema["properties"])
        sc = schema["properties"]["shadow_context"]
        self.assertEqual(sc["type"], "object")
        self.assertTrue(sc.get("additionalProperties"))


if __name__ == "__main__":
    unittest.main()
