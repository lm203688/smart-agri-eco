"""T-1 可信标记回归守卫。

覆盖点：
  1. get_trust_mark() 返回紧凑质量标记（cert_id / signature / status / verification_cmd）
  2. 完整数据下 status=trusted、rubric_passed=5/5
  3. MCP 工具响应内嵌 _trust_mark（通过 tools/call 契约测试）
  4. A2A Card 声明 capabilities.trustMarking
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.trust_layer import get_trust_mark


class TrustMarkTests(unittest.TestCase):

    def test_mark_fields_complete(self):
        mark = get_trust_mark()
        for k in ("cert_id", "signature", "signature_prefix", "issued_at",
                  "verification_cmd", "status", "degraded_reasons", "note"):
            self.assertIn(k, mark, f"trust_mark 缺 {k}")

    def test_status_trusted_and_rubric_full(self):
        mark = get_trust_mark()
        self.assertEqual(mark["status"], "trusted",
                         f"预期 trusted，实际 {mark['status']}，degraded={mark['degraded_reasons']}")
        self.assertEqual(mark["rubric_passed"], "5/5")

    def test_signature_format(self):
        """signature 为 64 字符 sha256 hex，prefix 为前 12 字符。"""
        mark = get_trust_mark()
        self.assertEqual(len(mark["signature"]), 64,
                         f"signature 长度 {len(mark['signature'])} != 64")
        self.assertEqual(mark["signature_prefix"], mark["signature"][:12])

    def test_verification_cmd_non_empty(self):
        mark = get_trust_mark()
        self.assertTrue(mark["verification_cmd"].startswith("python"),
                        f"verification_cmd 应可执行: {mark['verification_cmd']}")

    def test_deterministic_signature_for_same_data(self):
        """同一数据集合下 signature 应稳定（不含时间戳等易变字段）。

        注意：signature 覆盖 issued_at，所以两次调用不同；但 cert_id 稳定，
        且用同一 issued_at 时 signature 完全一致。
        """
        m1 = get_trust_mark()
        m2 = get_trust_mark()
        self.assertEqual(m1["cert_id"], m2["cert_id"],
                         "cert_id 应跨调用稳定")
        # signature 若数据未变，两次应一致（除非 issued_at 恰好跨秒）
        if m1["issued_at"] == m2["issued_at"]:
            self.assertEqual(m1["signature"], m2["signature"],
                             "同一时刻 signature 应稳定")

    def test_agent_card_declares_trust_marking(self):
        """A2A Card 应声明 trustMarking 能力（供 A2A 消费者发现）。"""
        card_path = os.path.join(ROOT, ".well-known", "agent.json")
        with open(card_path, "r", encoding="utf-8") as f:
            card = json.load(f)
        caps = card.get("capabilities", {})
        self.assertIn("trustMarking", caps, "A2A Card 缺 capabilities.trustMarking")
        self.assertTrue(caps["trustMarking"]["supported"])
        self.assertEqual(caps["trustMarking"]["responseField"], "_trust_mark")

    def test_agent_card_declares_confidence_intervals(self):
        """A2A Card 应声明 confidenceIntervals 能力（T-3 产品化）。"""
        card_path = os.path.join(ROOT, ".well-known", "agent.json")
        with open(card_path, "r", encoding="utf-8") as f:
            card = json.load(f)
        caps = card.get("capabilities", {})
        self.assertIn("confidenceIntervals", caps, "A2A Card 缺 capabilities.confidenceIntervals")
        self.assertTrue(caps["confidenceIntervals"]["supported"])
        self.assertEqual(caps["confidenceIntervals"]["responseField"], "prediction_interval")


if __name__ == "__main__":
    unittest.main()
