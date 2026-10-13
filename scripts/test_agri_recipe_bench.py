"""AgriRecipeBench 回归守卫：把 run_bench.py 变成 unittest 可发现的入口。

设计原则：
  - 只保证「种子用例集全部通过」，不重复 runner 的判定逻辑（避免双写判据）
  - runner 本身已提供 --strict 与 --json 两种模式；此处直接 shell out 一次
  - 若 runner 缺失或用例目录为空，视为失败（防止后续 refactor 静默失效）
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BENCH = os.path.join(ROOT, "benchmarks", "agri_recipe_bench")
RUNNER = os.path.join(BENCH, "run_bench.py")
CASES = os.path.join(BENCH, "cases")


class AgriRecipeBenchTests(unittest.TestCase):

    def test_runner_exists_and_executable(self):
        self.assertTrue(os.path.isfile(RUNNER), f"runner 缺失: {RUNNER}")

    def test_cases_dir_not_empty(self):
        self.assertTrue(os.path.isdir(CASES), f"cases 目录缺失: {CASES}")
        names = [n for n in os.listdir(CASES) if n.endswith(".json")]
        self.assertGreaterEqual(
            len(names), 3,
            f"种子用例过少（<3），无法形成有效基准：{names}",
        )

    def test_runner_strict_passes(self):
        """--strict 退出码必须为 0，表示所有种子用例通过。"""
        proc = subprocess.run(
            [sys.executable, RUNNER, "--strict", "--json"],
            capture_output=True, text=True, cwd=ROOT, encoding="utf-8",
        )
        self.assertEqual(
            proc.returncode, 0,
            f"AgriRecipeBench 有失败用例：\nstdout={proc.stdout[:2000]}\nstderr={proc.stderr[:1000]}",
        )
        payload = json.loads(proc.stdout)
        self.assertGreaterEqual(payload["summary"]["passed"], 3,
                               "通过用例过少（<3），基准可信度不足")
        self.assertEqual(payload["summary"]["failed"], 0,
                         f"失败用例：{json.dumps(payload['results'], ensure_ascii=False)[:2000]}")

    def test_axes_covered(self):
        """M1 与 M2 至少各有 1 个用例，防止后续只堆单轴。"""
        axes = set()
        for name in os.listdir(CASES):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(CASES, name), "r", encoding="utf-8") as f:
                axes.add(json.load(f).get("axis"))
        self.assertIn("target_prediction", axes, "M1 target_prediction 用例缺失")
        self.assertIn("state_rolling", axes, "M2 state_rolling 用例缺失")

    def test_case_schema_wellformed(self):
        """每个 case 必须含 id/axis/input/expected 且 axis 是已知值。"""
        # 2026-10-13 扩展：AgriRecipeBench 从 2 轴（M1/M2）扩到 4 轴，
        # 新增 M3 counterfactual（反事实响应）与 M4 generalization（跨情境泛化），
        # 对齐 SNWM 神农世界模型四轴协议完整版。
        valid_axes = {
            "target_prediction",   # M1：目标预测
            "state_rolling",       # M2：状态滚动
            "counterfactual",      # M3：反事实响应（换动作会怎样）
            "generalization",      # M4：跨情境泛化（换带还成立吗）
        }
        for name in sorted(os.listdir(CASES)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(CASES, name)
            with open(path, "r", encoding="utf-8") as f:
                c = json.load(f)
            for k in ("id", "axis", "input", "expected"):
                self.assertIn(k, c, f"{name}: 缺字段 {k}")
            self.assertIn(c["axis"], valid_axes,
                          f"{name}: 未知 axis={c['axis']!r}（当前支持 {valid_axes}）")


if __name__ == "__main__":
    unittest.main()
