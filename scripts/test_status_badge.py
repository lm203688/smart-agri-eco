"""W5 status badge generator 单元守卫。

覆盖点：
  1. collect_all 返回结构完整
  2. 四个指标都能采集（无 error）
  3. --ci 模式返回 0（当前全绿）
  4. SVG 渲染产物含关键 SVG 标签
  5. JSON 输出可解析
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "scripts", "generate_status_badge.py")


class StatusBadgeGeneratorTests(unittest.TestCase):

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, GEN, *extra],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
            timeout=180,
        )

    def test_default_run_exit_zero(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0,
                         f"默认运行应 exit 0，实际 {proc.returncode}：{proc.stderr}")

    def test_json_output_parseable(self):
        proc = self._run("--json")
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["project"], "agri-eco")
        self.assertIn("metrics", data)
        self.assertIn("generated_at", data)
        self.assertIn("status_version", data)

    def test_ci_mode_all_pass(self):
        """当前所有指标应达标，--ci 应 exit 0。"""
        proc = self._run("--ci")
        self.assertEqual(proc.returncode, 0,
                         f"--ci 应通过（所有指标达标），实际 {proc.returncode}：{proc.stderr}")

    def test_metrics_completeness(self):
        """四个指标都必须采集成功（total > 0，无 error 字段或 error 为空）。"""
        proc = self._run("--json")
        data = json.loads(proc.stdout)
        m = data["metrics"]
        for key in ("data_sources", "agri_recipe_bench", "ratchet_gates", "golden_vectors"):
            self.assertIn(key, m, f"缺指标 {key}")
            # 成功的指标不会带 error 字段（或用 None 表示）；失败的才会带字符串
            err = m[key].get("error")
            if err:
                self.fail(f"{key} 采集失败: {err}")

    def test_svg_export_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            svg_path = os.path.join(td, "test_badge.svg")
            proc = self._run("--svg", svg_path, "--quiet")
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(os.path.exists(svg_path))
            with open(svg_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("<svg", content)
            self.assertIn("agri-eco", content)

    def test_metric_values_sane(self):
        """数值合理性：total >= passed，total > 0。"""
        proc = self._run("--json")
        data = json.loads(proc.stdout)
        m = data["metrics"]
        for key in ("agri_recipe_bench", "ratchet_gates", "golden_vectors"):
            self.assertGreater(m[key]["total"], 0)
            self.assertLessEqual(m[key]["passed"], m[key]["total"])
            self.assertTrue(m[key]["ok"],
                            f"{key} ok=False（passed={m[key]['passed']}/"
                            f"total={m[key]['total']}）")
        # data_sources 特殊：alive vs total
        self.assertGreater(m["data_sources"]["total"], 0)
        self.assertLessEqual(m["data_sources"]["alive"], m["data_sources"]["total"])


if __name__ == "__main__":
    unittest.main()
