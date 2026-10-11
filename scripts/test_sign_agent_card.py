"""D-4 A2A Card JWS 签名回归守卫。

覆盖点：
  1. sign/verify 往返一致（round-trip）
  2. 错密钥拒绝（不同 key → 签名不匹配）
  3. payload 篡改检测（改 header 或 payload → 签名不匹配）
  4. 无 padding base64url（RFC 7515 兼容）
  5. 缺密钥时脚本明确失败（不静默降级）
"""
import base64
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.sign_agent_card import (  # noqa: E402
    CARD_PATH, _load_card, extract_signature_from_card, sign, verify,
)


class JWSAgentCardTests(unittest.TestCase):

    KEY = b"test-key-2026"
    ALTERNATE_KEY = b"wrong-key"

    def setUp(self):
        self.card = _load_card()
        self.jws = sign(self.card, self.KEY)

    def test_round_trip_verify(self):
        """签名→校验应通过"""
        ok, msg = verify(self.jws, self.KEY)
        self.assertTrue(ok, f"round-trip 失败: {msg}")
        self.assertIn("校验通过", msg)

    def test_three_segment_compact(self):
        """JWS compact serialization 必须 3 段（header.payload.signature）"""
        parts = self.jws.split(".")
        self.assertEqual(len(parts), 3, f"段数 {len(parts)} != 3")
        for p in parts:
            self.assertGreater(len(p), 0, "有段为空")

    def test_header_declares_hs256(self):
        """header 必须声明 alg=HS256 / typ=JWS"""
        h_bytes = base64.urlsafe_b64decode(self.jws.split(".")[0] + "==")
        header = json.loads(h_bytes)
        self.assertEqual(header["alg"], "HS256")
        self.assertEqual(header["typ"], "JWS")
        self.assertIn("kid", header)

    def test_wrong_key_rejected(self):
        """错密钥应拒绝（HMAC 完整性校验）"""
        ok, msg = verify(self.jws, self.ALTERNATE_KEY)
        self.assertFalse(ok, "错密钥竟通过")
        self.assertIn("签名不匹配", msg)

    def test_tampered_payload_rejected(self):
        """篡改 payload 应拒绝"""
        h, p, s = self.jws.split(".")
        tampered = json.dumps({
            "name": "Tampered Agent", "version": "0.0.1",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        p_bad = base64.urlsafe_b64encode(tampered.encode()).rstrip(b"=").decode()
        ok, msg = verify(f"{h}.{p_bad}.{s}", self.KEY)
        self.assertFalse(ok, "篡改 payload 竟通过")

    def test_tampered_signature_rejected(self):
        """篡改 signature 段应拒绝"""
        h, p, s = self.jws.split(".")
        # 翻转最后一个字符
        s_last = s[-1]
        s_bad_char = "A" if s_last != "A" else "B"
        s_bad = s[:-1] + s_bad_char
        # base64url 允许 A-Z a-z 0-9 - _；替换后仍合法字符
        ok, msg = verify(f"{h}.{p}.{s_bad}", self.KEY)
        self.assertFalse(ok, f"篡改 signature 竟通过：{msg}")

    def test_no_padding_base64url(self):
        """RFC 7515 要求 base64url 无 padding（=）"""
        for segment in self.jws.split("."):
            self.assertNotIn("=", segment, f"段含 padding: {segment[-5:]}")

    def test_cli_missing_key_fails_cleanly(self):
        """缺 AGRI_A2A_SIGNING_KEY 时脚本应退出码 2（不静默降级）"""
        env = os.environ.copy()
        env.pop("AGRI_A2A_SIGNING_KEY", None)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "sign_agent_card.py")],
            capture_output=True, text=True, env=env, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 2,
                         f"缺密钥应退出码 2，实际 {proc.returncode}：{proc.stderr}")

    def test_cli_verify_round_trip(self):
        """CLI --verify 与直接调用 verify 一致"""
        # 先写签名到独立文件
        sign_path = os.path.join(ROOT, ".well-known", "agent.json.jws")
        if os.path.exists(sign_path):
            os.unlink(sign_path)
        try:
            env = os.environ.copy()
            env["AGRI_A2A_SIGNING_KEY"] = "test-key-2026"
            # 生成
            p1 = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "sign_agent_card.py")],
                capture_output=True, text=True, env=env, encoding="utf-8", cwd=ROOT,
            )
            self.assertEqual(p1.returncode, 0, f"sign 失败：{p1.stderr}")
            # 校验
            p2 = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "verify_agent_card.py")],
                capture_output=True, text=True, env=env, encoding="utf-8", cwd=ROOT,
            )
            self.assertEqual(p2.returncode, 0, f"verify 失败：{p2.stdout} / {p2.stderr}")
            self.assertIn("校验通过", p2.stdout)
        finally:
            # 清理测试签名文件，避免污染仓库
            if os.path.exists(sign_path):
                os.unlink(sign_path)


if __name__ == "__main__":
    unittest.main()
