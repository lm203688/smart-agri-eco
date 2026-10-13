"""S2/E1 棘轮 CI 硬门禁回归守卫。

覆盖点：
  1. 白名单文件全部存在时通过
  2. 缺白名单文件时明确 config_error
  3. 阈值 0.5 通过（当前 benchmark 0.875）
  4. 阈值 0.99 失败（正确拒绝）
  5. --check-files 只检查文件不跑 benchmark
  6. JSON 输出含 status / score / exit_code
  7. CLI exit_code 规范：0=passed, 1=failed, 2=config_error, 3=exec_error
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "run_evolution_ratchet.py")
ZONES = os.path.join(ROOT, ".well-known", "evolution_zones.json")


def _run(args, cwd=None):
    """子进程运行 ratchet 脚本。

    关键：显式清理 AGRI_* 环境变量——全量测试时早先的 test_engine_v3 等
    测试可能在父进程设置了 AGRI_CROP_DB / AGRI_FEEDBACK_LOG 指向临时路径，
    子进程继承后会找不到文件（WinError 2）。传干净环境保证可复现。
    """
    clean_env = {k: v for k, v in os.environ.items()
                if not k.startswith("AGRI_")}
    p = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, encoding="utf-8",
        cwd=cwd or ROOT,
        env=clean_env,
    )
    return p.returncode, p.stdout, p.stderr


class EvolutionRatchetTests(unittest.TestCase):

    def setUp(self):
        # 保存原始 zones 文件（可能被下面的测试修改）
        self._orig = open(ZONES, "r", encoding="utf-8").read()

    def tearDown(self):
        with open(ZONES, "w", encoding="utf-8") as f:
            f.write(self._orig)

    # ------------------------------------------------------------------
    # 基本通过路径
    # ------------------------------------------------------------------

    def test_check_files_only(self):
        """--check-files 模式：只检查白名单文件存在。"""
        rc, out, err = _run(["--check-files"])
        self.assertEqual(rc, 0, f"应通过，stderr={err}")
        self.assertIn("passed", out)
        self.assertIn("--check-files", out)

    def test_default_pass(self):
        """默认阈值 0.5，当前 benchmark 0.875 → passed。"""
        rc, out, err = _run([])
        self.assertEqual(rc, 0, f"应通过：{out}\n{err}")
        self.assertIn("passed", out)
        self.assertIn("0.8750", out)

    def test_high_threshold_fails(self):
        """阈值 0.99 时应失败（当前分数 0.875 < 0.99）。"""
        rc, out, err = _run(["--min-score", "0.99"])
        self.assertEqual(rc, 1, f"应拒绝，实际 rc={rc}：{out}")
        self.assertIn("failed", out)
        self.assertIn("未严格提升", out)

    def test_json_output(self):
        """--json 模式输出可解析 JSON，含关键字段。"""
        rc, out, err = _run(["--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIn("status", data)
        self.assertIn("score", data)
        self.assertIn("exit_code", data)
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["status"], "passed")

    # ------------------------------------------------------------------
    # 配置错误
    # ------------------------------------------------------------------

    def test_missing_whitelist_file_returns_config_error(self):
        """白名单指向不存在的路径时应 config_error。"""
        with open(ZONES, "r", encoding="utf-8") as f:
            zones = json.load(f)
        zones["meta_policy"]["enforcement"]["ratchet_required_for"] = [
            "nonexistent_dir_xyz/",
            "agent/",
        ]
        with open(ZONES, "w", encoding="utf-8") as f:
            json.dump(zones, f, ensure_ascii=False, indent=2)

        rc, out, err = _run(["--check-files", "--json"])
        self.assertEqual(rc, 2, f"应 config_error，rc={rc}")
        data = json.loads(out)
        self.assertEqual(data["status"], "config_error")
        self.assertEqual(data["exit_code"], 2)
        self.assertGreater(len(data.get("missing_files", [])), 0)

    def test_exit_code_semantics(self):
        """退出码语义：0=passed, 1=failed, 2=config_error。"""
        # 0 = passed
        rc_pass, _, _ = _run(["--min-score", "0.0"])
        self.assertEqual(rc_pass, 0)
        # 1 = failed
        rc_fail, _, _ = _run(["--min-score", "1.01"])
        self.assertEqual(rc_fail, 1)


if __name__ == "__main__":
    unittest.main()
