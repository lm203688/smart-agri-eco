"""M11-T1 公共复算 API 单测：scripts/verify_trust_mark.py + core.trust_layer 端到端。

覆盖：
  - canonical / sha256_hex 原语
  - verify_certificate_content：证书内部 signature 一致性 + 篡改检测
  - verify_mark_internal：signature_prefix vs signature 前 12 字符
  - verify_mark_end_to_end：固定 issued_at 严格重现 signature + 数据源篡改检测
  - verify_artifact_hashes：磁盘文件哈希一致性 + 篡改/缺失检测
  - CLI：4 个子命令的 exit code 与 JSON 输出
  - MCP 工具 agri_verify_trust：3 种 mode 的路由与参数校验

诚实边界：**signature 是内容一致性哈希，非密码学签名（无密钥）**。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.verify_trust_mark import (  # noqa: E402
    canonical, sha256_hex,
    verify_certificate_content, verify_mark_internal,
    verify_mark_end_to_end, verify_artifact_hashes,
    current_mark_json, current_certificate,
)


REPO = ROOT
SCRIPT = REPO / "scripts" / "verify_trust_mark.py"


def _run(args, cwd=None):
    """运行 CLI，返回 (exit_code, stdout, stderr)。"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, text=True, cwd=cwd or REPO, env=env,
    )
    return r.returncode, r.stdout, r.stderr


class TestCanonical(unittest.TestCase):
    """规范化和哈希原语。"""

    def test_canonical_deterministic(self):
        a = {"b": 1, "a": 2}
        b = {"a": 2, "b": 1}
        self.assertEqual(canonical(a), canonical(b))

    def test_canonical_matches_trust_layer(self):
        """与 core.trust_layer._canonical 保持一致（相同 canonical 语义）。"""
        from core.trust_layer import _canonical
        sample = {"x": [1, 2, {"y": "中文"}], "z": None}
        self.assertEqual(canonical(sample), _canonical(sample))

    def test_sha256_hex_known(self):
        # 已知向量：空字符串
        self.assertEqual(sha256_hex(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")


class TestVerifyCertificateContent(unittest.TestCase):
    def setUp(self):
        self.cert = current_certificate()

    def test_clean_certificate_verifies(self):
        r = verify_certificate_content(self.cert)
        self.assertTrue(r["verified"])
        self.assertEqual(r["mode"], "certificate_content")
        self.assertEqual(r["provided_signature"], r["recomputed_signature"])

    def test_tampered_field_fails(self):
        c = dict(self.cert)
        c["data_coverage"] = dict(c["data_coverage"])
        c["data_coverage"]["total_crops"] = 999
        r = verify_certificate_content(c)
        self.assertFalse(r["verified"])
        self.assertNotEqual(r["provided_signature"], r["recomputed_signature"])

    def test_missing_signature_fails(self):
        c = dict(self.cert)
        c.pop("signature")
        r = verify_certificate_content(c)
        self.assertFalse(r["verified"])
        self.assertIn("signature", r["error"])

    def test_non_dict_input(self):
        r = verify_certificate_content([])
        self.assertFalse(r["verified"])
        self.assertIn("不是 JSON 对象", r["error"])


class TestVerifyMarkInternal(unittest.TestCase):
    def test_clean_mark_verifies(self):
        mark = current_mark_json()
        r = verify_mark_internal(mark)
        self.assertTrue(r["verified"])
        self.assertEqual(r["provided_prefix"], mark["signature_prefix"])
        self.assertEqual(r["expected_prefix"], mark["signature"][:12])

    def test_wrong_prefix_fails(self):
        mark = current_mark_json()
        bad = dict(mark)
        bad["signature_prefix"] = "000000000000"
        r = verify_mark_internal(bad)
        self.assertFalse(r["verified"])

    def test_missing_field_fails(self):
        r = verify_mark_internal({"signature": "abc"})
        self.assertFalse(r["verified"])
        self.assertIn("signature_prefix", r["error"])


class TestVerifyMarkEndToEnd(unittest.TestCase):
    def setUp(self):
        # 生成一份 mark（含 issued_at）并保存
        self.mark = current_mark_json()

    def test_self_verification_matches(self):
        """用自己的 issued_at + 本地数据重算，必须完全一致。"""
        r = verify_mark_end_to_end(self.mark)
        self.assertTrue(r["verified"], f"self verify failed: {r}")
        self.assertEqual(r["recomputed_signature_at_issued_at"], self.mark["signature"])
        self.assertEqual(r["recomputed_issued_at"], self.mark["issued_at"])

    def test_wrong_issued_at_mismatches(self):
        """篡改 issued_at → signature 不匹配。"""
        bad = dict(self.mark)
        bad["issued_at"] = "2000-01-01T00:00:00"
        r = verify_mark_end_to_end(bad)
        self.assertFalse(r["verified"])

    def test_provided_signature_tampered(self):
        """篡改 signature 值本身 → 不匹配。"""
        bad = dict(self.mark)
        bad["signature"] = "0" * 64
        r = verify_mark_end_to_end(bad)
        self.assertFalse(r["verified"])

    def test_returns_current_local_reference(self):
        r = verify_mark_end_to_end(self.mark)
        # 应始终附带"本地此刻"参考 signature
        self.assertIn("current_local_signature", r)
        self.assertIn("current_local_prefix", r)


class TestVerifyArtifactHashes(unittest.TestCase):
    def setUp(self):
        self.cert = current_certificate()

    def test_clean_artifacts_match(self):
        r = verify_artifact_hashes(self.cert, str(REPO))
        self.assertTrue(r["verified"])
        self.assertEqual(r["artifacts_checked"], 2)
        for art in r["artifacts"]:
            self.assertTrue(art["exists"])
            self.assertTrue(art["matched"])
            self.assertEqual(art["declared_sha256"], art["actual_sha256"])

    def test_missing_artifact_fails(self):
        c = dict(self.cert)
        c["artifacts"] = [{"path": "does_not_exist.json", "sha256": "0" * 64}]
        r = verify_artifact_hashes(c, str(REPO))
        self.assertFalse(r["verified"])
        self.assertFalse(r["artifacts"][0]["exists"])

    def test_empty_artifacts_fails(self):
        c = {"artifacts": []}
        r = verify_artifact_hashes(c, str(REPO))
        self.assertFalse(r["verified"])


class TestCLI(unittest.TestCase):
    """CLI 子命令与退出码。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trust_test_")

    def tearDown(self):
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def _write_mark(self):
        p = os.path.join(self.tmp, "mark.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(current_mark_json(), f, ensure_ascii=False)
        return p

    def _write_cert(self):
        p = os.path.join(self.tmp, "cert.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(current_certificate(), f, ensure_ascii=False)
        return p

    def test_current_command_json(self):
        # current 默认就输出 JSON，不需要 --json
        code, out, _ = _run(["current"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("signature", data)
        self.assertIn("status", data)
        self.assertIn(data["status"], ("trusted", "degraded", "partial"))

    def test_current_certificate_mode(self):
        code, out, _ = _run(["current", "--certificate"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("layer", data)
        self.assertIn("signature", data)
        self.assertIn("artifacts", data)

    def test_check_prefix_clean(self):
        p = self._write_mark()
        code, out, _ = _run(["check-prefix", p, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verified"], True)

    def test_from_mark_clean(self):
        p = self._write_mark()
        code, out, _ = _run(["from-mark", p, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verified"], True)

    def test_from_certificate_content_only(self):
        p = self._write_cert()
        code, out, _ = _run(["from-certificate", p, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["mode"], "certificate_content")
        self.assertEqual(json.loads(out)["verified"], True)

    def test_from_certificate_with_artifacts(self):
        p = self._write_cert()
        code, out, _ = _run(["from-certificate", p, "--verify-artifacts", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["mode"], "artifact_hashes")
        self.assertEqual(data["verified"], True)
        self.assertEqual(data["artifacts_checked"], 2)

    def test_tampered_certificate_returns_1(self):
        p = self._write_cert()
        with open(p, "r", encoding="utf-8") as f:
            c = json.load(f)
        c["data_coverage"]["total_crops"] = 999
        with open(p, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
        code, _, _ = _run(["from-certificate", p, "--json"])
        self.assertEqual(code, 1, "篡改后应返回 exit=1")

    def test_missing_file_returns_2(self):
        code, _, _ = _run(["check-prefix", "/no/such/file.json"])
        self.assertEqual(code, 2)


class TestMCPTool(unittest.TestCase):
    """MCP 工具 agri_verify_trust 的三模式路由。"""

    def setUp(self):
        # 通过直接调用 handler 测试，避免启动 MCP server
        from mcp.server import _tool_verify_trust
        self.tool = _tool_verify_trust

    def test_current_mode(self):
        r = self.tool({"mode": "current"})
        self.assertIn("signature", r)
        self.assertIn("status", r)
        self.assertNotIn("error", r)

    def test_check_prefix_valid(self):
        from scripts.verify_trust_mark import current_mark_json
        mark = current_mark_json()
        r = self.tool({"mode": "check_prefix", "mark": mark})
        self.assertTrue(r["verified"])
        self.assertEqual(r["mode"], "mark_internal")

    def test_end_to_end_valid(self):
        from scripts.verify_trust_mark import current_mark_json
        mark = current_mark_json()
        r = self.tool({"mode": "end_to_end", "mark": mark})
        self.assertTrue(r["verified"])
        self.assertEqual(r["mode"], "mark_end_to_end")

    def test_invalid_mode(self):
        r = self.tool({"mode": "bogus"})
        self.assertIn("error", r)
        # H5 加固：schema enum 校验给出 "not in enum"，或 fallback 到原 "非法 mode" 文案
        self.assertTrue(
            "非法 mode" in r["error"] or "not in enum" in r["error"],
            f"unexpected error message: {r['error']}",
        )

    def test_check_prefix_requires_mark(self):
        r = self.tool({"mode": "check_prefix"})
        self.assertIn("error", r)
        self.assertIn("mark", r["error"])

    def test_mark_must_be_object(self):
        r = self.tool({"mode": "check_prefix", "mark": "not-a-dict"})
        self.assertIn("error", r)


class TestTrustLayerFixedIssuedAt(unittest.TestCase):
    """验证 core.trust_layer.issue_certificate 的 fixed_issued_at 参数。"""

    def test_fixed_timestamp_deterministic(self):
        from core.trust_layer import issue_certificate
        fixed = "2026-10-14T12:00:00"
        c1 = issue_certificate(run_id="t1", inputs={"x": 1}, fixed_issued_at=fixed)
        c2 = issue_certificate(run_id="t1", inputs={"x": 1}, fixed_issued_at=fixed)
        self.assertEqual(c1["signature"], c2["signature"])
        self.assertEqual(c1["issued_at"], fixed)

    def test_default_timestamp_varies(self):
        import time
        from core.trust_layer import issue_certificate
        c1 = issue_certificate(run_id="tv1", inputs={"x": 1})
        time.sleep(1.1)
        c2 = issue_certificate(run_id="tv1", inputs={"x": 1})
        self.assertNotEqual(c1["issued_at"], c2["issued_at"])
        self.assertNotEqual(c1["signature"], c2["signature"])

    def test_verification_cmd_points_to_verify_api(self):
        from core.trust_layer import get_trust_mark
        mark = get_trust_mark()
        self.assertIn("verify_trust_mark.py", mark["verification_cmd"])
        self.assertIn("from-mark", mark["verification_cmd"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
