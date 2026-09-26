"""Offline tests for agent/jev_gate.py (Jev decision gate).

These tests never touch the network and never require TYPESAFE_API_KEY:
- no-key path must skip safely without calling the API;
- parsing of the documented response schema is verified via an injected fake response;
- HTTP / connection errors must degrade to skipped (fail-closed), never raise.
"""
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("jev_gate", os.path.join(ROOT, "agent", "jev_gate.py"))
jev_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jev_gate)

# Nonexistent path used to disable the credential-file fallback in the
# "no key" tests, so a real key stored on this machine cannot leak in.
_NO_SUCH_CRED = os.path.join(ROOT, "no_such_typesafe_credentials.json")


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def _patch_urlopen(payload):
    return mock.patch.object(jev_gate.urllib.request, "urlopen",
                             lambda *a, **k: _FakeResp(payload))


class TestNoKey(unittest.TestCase):
    """Without a key, every call must skip and must NOT hit the network."""

    def setUp(self):
        self._env = os.environ.pop("TYPESAFE_API_KEY", None)
        os.environ.pop("TYPESAFE_KEY", None)
        # Redirect the credential-file fallback so a real key on this machine
        # cannot leak into the "no key" tests (keeps them hermetic).
        self._cred = os.environ.get("TYPESAFE_CRED_FILE")
        os.environ["TYPESAFE_CRED_FILE"] = _NO_SUCH_CRED

    def tearDown(self):
        if self._env is not None:
            os.environ["TYPESAFE_API_KEY"] = self._env
        if self._cred is not None:
            os.environ["TYPESAFE_CRED_FILE"] = self._cred
        else:
            os.environ.pop("TYPESAFE_CRED_FILE", None)

    def test_available_false_without_key(self):
        self.assertFalse(jev_gate.jev_available())

    def test_noul_skips_without_calling(self):
        with mock.patch.object(jev_gate.urllib.request, "urlopen") as m:
            is_true, prob, skipped, note = jev_gate.jev_noul("x", "is it true?")
        self.assertTrue(skipped)
        self.assertIsNone(is_true)
        self.assertIsNone(prob)
        self.assertEqual(note, "no_key")
        m.assert_not_called()

    def test_score_skips_without_calling(self):
        with mock.patch.object(jev_gate.urllib.request, "urlopen") as m:
            score, conf, skipped, note = jev_gate.jev_score("x", "rate it", ["a", "b"])
        self.assertTrue(skipped)
        self.assertIsNone(score)
        m.assert_not_called()

    def test_choice_skips_without_calling(self):
        with mock.patch.object(jev_gate.urllib.request, "urlopen") as m:
            choice, probs, conf, skipped, note = jev_gate.jev_choice("x", "pick", ["A", "B"])
        self.assertTrue(skipped)
        self.assertIsNone(choice)
        m.assert_not_called()


class TestParsing(unittest.TestCase):
    """With a key + injected OK response, parsing must match the documented schema."""

    def setUp(self):
        os.environ["TYPESAFE_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("TYPESAFE_API_KEY", None)

    def test_noul_parsing(self):
        payload = {"model": "jev-1.13.0",
                   "answers": {"q1": {"type": "noul", "noul": 0.93}}}
        with _patch_urlopen(payload):
            is_true, prob, skipped, note = jev_gate.jev_noul("state", "urgent?", threshold=0.5)
        self.assertFalse(skipped)
        self.assertTrue(is_true)
        self.assertAlmostEqual(prob, 0.93)

    def test_noul_threshold_boundary(self):
        payload = {"model": "jev-1.13.0",
                   "answers": {"q1": {"type": "noul", "noul": 0.4}}}
        with _patch_urlopen(payload):
            is_true, prob, skipped, _ = jev_gate.jev_noul("state", "x?", threshold=0.5)
        self.assertFalse(skipped)
        self.assertFalse(is_true)
        self.assertAlmostEqual(prob, 0.4)

    def test_score_parsing(self):
        payload = {"model": "jev-1.13.0",
                   "answers": {"q1": {"type": "score", "score": 1.4, "confidence": 0.9,
                                      "probabilities": {"0": 0.1, "1": 0.9, "2": 0.0}}}}
        with _patch_urlopen(payload):
            score, conf, skipped, _ = jev_gate.jev_score("state", "frustration",
                                                         ["calm", "civil", "angry"])
        self.assertFalse(skipped)
        self.assertAlmostEqual(score, 1.4)
        self.assertAlmostEqual(conf, 0.9)

    def test_choice_parsing_and_other_escape(self):
        payload = {"model": "jev-1.13.0",
                   "answers": {"q1": {"type": "choice", "choice": "technical",
                                      "confidence": 0.78,
                                      "probabilities": {"technical": 0.85, "sales": 0.0,
                                                        "billing": 0.15, "__other__": 0.0}}}}
        with _patch_urlopen(payload):
            choice, probs, conf, skipped, _ = jev_gate.jev_choice(
                "state", "which team", ["technical", "sales", "billing"])
        self.assertFalse(skipped)
        self.assertEqual(choice, "technical")
        self.assertAlmostEqual(conf, 0.78)

    def test_choice_other_maps_to_none(self):
        payload = {"model": "jev-1.13.0",
                   "answers": {"q1": {"type": "choice", "choice": "__other__",
                                      "confidence": 0.5,
                                      "probabilities": {"__other__": 1.0}}}}
        with _patch_urlopen(payload):
            choice, probs, conf, skipped, _ = jev_gate.jev_choice("state", "pick", ["A", "B"])
        self.assertFalse(skipped)
        self.assertIsNone(choice)  # explicit escape -> uncertain, not a forced pick


class TestFailClosed(unittest.TestCase):
    """HTTP / connection errors must degrade to skipped, never raise into the loop."""

    def setUp(self):
        os.environ["TYPESAFE_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("TYPESAFE_API_KEY", None)

    def test_http_429_skips(self):
        import urllib.error as ue
        with mock.patch.object(jev_gate.urllib.request, "urlopen",
                               side_effect=ue.HTTPError(jev_gate.JEV_URL, 429, "rate", None, None)):
            is_true, prob, skipped, note = jev_gate.jev_noul("state", "x?")
        self.assertTrue(skipped)
        self.assertEqual(note, "http_429")

    def test_conn_error_skips(self):
        import urllib.error as ue
        with mock.patch.object(jev_gate.urllib.request, "urlopen",
                               side_effect=ue.URLError("boom")):
            score, conf, skipped, note = jev_gate.jev_score("state", "rate", ["a", "b"])
        self.assertTrue(skipped)
        self.assertEqual(note, "conn_error")


class TestRecordGate(unittest.TestCase):
    """jev_gate_record: advisory data-quality GATE before main-chain writes."""

    def setUp(self):
        self._env = os.environ.pop("TYPESAFE_API_KEY", None)
        os.environ.pop("TYPESAFE_KEY", None)
        # Redirect the credential-file fallback so a real key on this machine
        # cannot leak into the "no key" tests (keeps them hermetic).
        self._cred = os.environ.get("TYPESAFE_CRED_FILE")
        os.environ["TYPESAFE_CRED_FILE"] = _NO_SUCH_CRED

    def tearDown(self):
        if self._env is not None:
            os.environ["TYPESAFE_API_KEY"] = self._env
        if self._cred is not None:
            os.environ["TYPESAFE_CRED_FILE"] = self._cred
        else:
            os.environ.pop("TYPESAFE_CRED_FILE", None)
        if self._env is None:
            os.environ.pop("TYPESAFE_API_KEY", None)

    def _patch_post(self, noul, conf):
        ans = {"gate": {"type": "noul", "noul": noul, "confidence": conf}}
        return mock.patch.object(jev_gate, "_post", return_value=(ans, None))

    def test_no_key_never_blocks(self):
        rec = {"adapt_score": 0.5}
        base = {"adapt_score_range": [0, 1]}
        block, conf, skipped, note = jev_gate.jev_gate_record(rec, base, "consistent?")
        self.assertTrue(skipped)
        self.assertFalse(block)
        self.assertEqual(note, "no_key")

    def test_high_conf_anomaly_blocks(self):
        os.environ["TYPESAFE_API_KEY"] = "k"
        rec = {"adapt_score": 99.0}  # absurd vs baseline
        base = {"adapt_score_range": [0, 1]}
        with self._patch_post(noul=0.05, conf=0.97):
            block, conf, skipped, note = jev_gate.jev_gate_record(
                rec, base, "该候选与基线一致且可信？")
        self.assertFalse(skipped)
        self.assertTrue(block)
        self.assertIn("jev_quarantine", note)

    def test_low_noul_but_low_conf_does_not_block(self):
        # escalate, don't quarantine, when confidence is below threshold
        os.environ["TYPESAFE_API_KEY"] = "k"
        rec = {"adapt_score": 99.0}
        base = {"adapt_score_range": [0, 1]}
        with self._patch_post(noul=0.1, conf=0.4):
            block, conf, skipped, note = jev_gate.jev_gate_record(rec, base, "consistent?")
        self.assertFalse(skipped)
        self.assertFalse(block)  # uncertain -> let deterministic validation + human decide

    def test_consistent_record_passes(self):
        os.environ["TYPESAFE_API_KEY"] = "k"
        rec = {"adapt_score": 0.62}
        base = {"adapt_score_range": [0, 1]}
        with self._patch_post(noul=0.9, conf=0.95):
            block, conf, skipped, note = jev_gate.jev_gate_record(rec, base, "consistent?")
        self.assertFalse(skipped)
        self.assertFalse(block)


if __name__ == "__main__":
    unittest.main()
