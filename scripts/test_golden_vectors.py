"""E4 Golden Vectors runner 单元守卫。

覆盖点：
  1. runner 三模块齐全（forecast / phenology / nutrition）
  2. 每个 golden json 存在且 schema 完整
  3. --strict 模式在失败时返回 exit 1
  4. 用例总数与预期一致（防静默丢失）
"""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(ROOT, "benchmarks", "golden_vectors")
RUNNER = os.path.join(ROOT, "scripts", "run_golden_vectors.py")


class GoldenVectorsRunnerTests(unittest.TestCase):

    def test_three_modules_present(self):
        files = sorted(os.listdir(GOLDEN_DIR))
        for name in ("forecast", "phenology", "nutrition"):
            self.assertIn(f"{name}.json", files,
                          f"缺 golden vector: {name}.json")

    def test_all_schemas_v1(self):
        for name in ("forecast", "phenology", "nutrition"):
            with open(os.path.join(GOLDEN_DIR, f"{name}.json"),
                      encoding="utf-8") as f:
                spec = json.load(f)
            self.assertTrue(spec["schema"].endswith("/v1"),
                            f"{name} schema 非 v1: {spec['schema']}")
            self.assertIn("target_module", spec)
            self.assertIn("cases", spec)
            self.assertGreaterEqual(len(spec["cases"]), 3,
                                    f"{name} 用例数 <3")

    def test_each_case_has_rationale(self):
        """每个 golden 用例必须有 rationale（说明值从哪来）。"""
        for name in ("forecast", "phenology", "nutrition"):
            with open(os.path.join(GOLDEN_DIR, f"{name}.json"),
                      encoding="utf-8") as f:
                spec = json.load(f)
            for c in spec["cases"]:
                self.assertIn("rationale", c,
                              f"{name}/{c['id']} 缺 rationale")
                self.assertTrue(c["rationale"],
                                f"{name}/{c['id']} rationale 为空")

    def test_runner_returns_success(self):
        """runner 默认应 exit 0（当前代码库下所有 golden 值匹配）。"""
        proc = subprocess.run(
            [sys.executable, RUNNER],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0,
                         f"runner 应 exit 0，实际 {proc.returncode}：{proc.stdout}")

    def test_runner_strict_all_pass(self):
        """--strict 模式当前应通过（score=1.0）。"""
        proc = subprocess.run(
            [sys.executable, RUNNER, "--strict"],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0,
                         f"--strict 应通过，实际 {proc.returncode}：{proc.stdout}")
        self.assertIn("all_passed=True", proc.stdout)

    def test_runner_json_output_valid(self):
        proc = subprocess.run(
            [sys.executable, RUNNER, "--json"],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["schema"], "agri-golden-vectors/v1")
        self.assertIn("overall", report)
        self.assertIn("modules", report)
        self.assertEqual(report["overall"]["all_passed"], True)
        # 三个模块齐全
        self.assertEqual(
            set(report["modules"].keys()),
            {"forecast", "phenology", "nutrition"},
        )

    def test_total_case_count(self):
        """用例总数锁定（forecast 4 + phenology 7 + nutrition 5 = 16）。"""
        proc = subprocess.run(
            [sys.executable, RUNNER, "--json"],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["overall"]["total_cases"], 16,
                         f"用例总数 {report['overall']['total_cases']} != 16")


if __name__ == "__main__":
    unittest.main()
