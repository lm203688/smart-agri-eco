"""Offline tests for scripts/jev_attribution.py (Jev daily-loop anomaly node).

No real network, no real Jev key. Network is simulated by monkeypatching
urllib.request.urlopen; Jev is simulated by monkeypatching agent.jev_gate.jev_choice.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

# allow `import agent.jev_gate` and `import scripts.jev_attribution` from repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.jev_attribution as ja  # noqa: E402
import agent.jev_gate as jg  # noqa: E402


class _Tmp:
    def __init__(self):
        # .workbuddy/ 在 .gitignore 里（含旧版会话日志），干净 checkout 中不存在，
        # 故不能假设它已存在 —— 必须自己建，否则 CI 上 mkdtemp 直接 FileNotFoundError。
        tmp_root = os.path.join(ROOT, ".workbuddy", "tmp")
        os.makedirs(tmp_root, exist_ok=True)
        self.d = tempfile.mkdtemp(prefix="jev_attr_", dir=tmp_root)
        self.probe = os.path.join(self.d, "probe.json")
        self.out = os.path.join(self.d, "attrib.md")

    def write_probe(self, sources):
        with open(self.probe, "w", encoding="utf-8") as f:
            json.dump({"date": "2026-09-22", "sources": sources}, f)

    def cleanup(self):
        for p in (self.probe, self.out):
            if os.path.exists(p):
                os.remove(p)
        try:
            os.rmdir(self.d)
        except OSError:
            pass


class TestNoKeyFallback(unittest.TestCase):
    def setUp(self):
        self.t = _Tmp()
        self._old = os.environ.pop("TYPESAFE_API_KEY", None)
        os.environ.pop("TYPESAFE_KEY", None)
        # Redirect the credential-file fallback so a real key on this machine
        # cannot leak into the "no key" fallback tests (keeps them hermetic).
        self._cred = os.environ.get("TYPESAFE_CRED_FILE")
        os.environ["TYPESAFE_CRED_FILE"] = os.path.join(
            self.t.d, "does-not-exist.json")

    def tearDown(self):
        self.t.cleanup()
        if self._old is not None:
            os.environ["TYPESAFE_API_KEY"] = self._old
        if self._cred is not None:
            os.environ["TYPESAFE_CRED_FILE"] = self._cred
        else:
            os.environ.pop("TYPESAFE_CRED_FILE", None)

    def test_timeout_source_gets_deterministic_fallback(self):
        # exit 28 (timeout) with no key => deterministic "区域慢" fallback text
        self.t.write_probe([
            {"name": "rest.isric.org", "url": "https://rest.isric.org/x",
             "http_code": "000", "time": 61.0, "exit_code": 28},
        ])
        rc = ja.main(["--probe-json", self.t.probe, "--out", self.t.out, "--date", "2026-09-22"])
        self.assertEqual(rc, 0)
        with open(self.t.out, encoding="utf-8") as _f:
            md = _f.read()
        self.assertIn("未启用（无 key", md)
        self.assertIn("exit 28", md)
        self.assertIn("区域慢", md)
        # must NOT claim a Jev verdict
        self.assertNotIn("Jev 启用", md)

    def test_all_200_no_attribution(self):
        self.t.write_probe([
            {"name": "gaez.fao.org", "url": "https://gaez.fao.org/",
             "http_code": "200", "time": 1.1, "exit_code": 0},
        ])
        ja.main(["--probe-json", self.t.probe, "--out", self.t.out, "--date", "2026-09-22"])
        with open(self.t.out, encoding="utf-8") as _f:
            md = _f.read()
        self.assertIn("全部 200，无需归因", md)


class TestWithKeyAttribution(unittest.TestCase):
    def setUp(self):
        self.t = _Tmp()
        os.environ["TYPESAFE_API_KEY"] = "fake-test-key"

    def tearDown(self):
        self.t.cleanup()
        os.environ.pop("TYPESAFE_API_KEY", None)

    def test_jev_choice_drives_label(self):
        self.t.write_probe([
            {"name": "rest.isric.org", "url": "https://rest.isric.org/x",
             "http_code": "000", "time": 61.0, "exit_code": 28},
        ])
        with mock.patch.object(jg, "jev_choice",
                               return_value=("区域网络慢或临时超时", {"x": 0.9},
                                             0.9, False, None)):
            ja.main(["--probe-json", self.t.probe, "--out", self.t.out, "--date", "2026-09-22"])
        with open(self.t.out, encoding="utf-8") as _f:
            md = _f.read()
        self.assertIn("启用（TYPESAFE_API_KEY 已设）", md)
        self.assertIn("区域网络慢或临时超时", md)
        self.assertIn("conf=0.90", md)

    def test_jev_low_conf_escalates(self):
        # jev_choice returns skipped (uncertain) => escalate to human
        self.t.write_probe([
            {"name": "gd.eppo.int", "url": "https://gd.eppo.int/",
             "http_code": "503", "time": 2.0, "exit_code": 0},
        ])
        with mock.patch.object(jg, "jev_choice",
                               return_value=(None, None, None, True, "low confidence")):
            ja.main(["--probe-json", self.t.probe, "--out", self.t.out, "--date", "2026-09-22"])
        with open(self.t.out, encoding="utf-8") as _f:
            md = _f.read()
        self.assertIn("升级人工", md)


class TestSelfProbeMapping(unittest.TestCase):
    """Verify probe_source maps urllib errors to curl exit codes without real net."""

    def test_timeout_maps_to_28(self):
        err = urllib_error_with_reason("timed out")
        with mock.patch.object(ja.urllib.request, "urlopen", side_effect=err):
            r = ja.probe_source("https://rest.isric.org/x")
        self.assertEqual(r["exit_code"], 28)
        self.assertEqual(r["http_code"], "000")

    def test_dns_fail_maps_to_6(self):
        err = urllib_error_with_reason("getaddrinfo failed")
        with mock.patch.object(ja.urllib.request, "urlopen", side_effect=err):
            r = ja.probe_source("https://nonexistent.invalid/x")
        self.assertEqual(r["exit_code"], 6)

    def test_200_ok(self):
        fake = mock.Mock()
        fake.status = 200
        fake.__enter__ = lambda s: s
        fake.__exit__ = lambda s, *a: False
        with mock.patch.object(ja.urllib.request, "urlopen", return_value=fake):
            r = ja.probe_source("https://gaez.fao.org/")
        self.assertEqual(r["exit_code"], 0)
        self.assertEqual(r["http_code"], "200")


def urllib_error_with_reason(reason: str):
    import urllib.error as ue
    return ue.URLError(reason)


class TestDirectInvocationImportsAgent(unittest.TestCase):
    """Regression guard for the real-run bug (2026-09-22): running
    `python scripts/jev_attribution.py` directly left `agent` off sys.path
    and crashed with ModuleNotFoundError inside attribute_source. After the
    sys.path fix, the script must degrade gracefully even with a bogus key
    (Jev returns 401 -> skipped -> no crash, md still written). This is the
    only test that reproduces the actual invocation shape (sys.path[0]=scripts/).
    """

    def setUp(self):
        self.t = _Tmp()
        self.t.write_probe([
            {"name": "rest.isric.org", "url": "https://rest.isric.org/x",
             "http_code": "000", "time": 61.0, "exit_code": 28},
        ])

    def tearDown(self):
        self.t.cleanup()

    def test_direct_run_does_not_crash(self):
        import subprocess
        env = dict(os.environ)
        env["TYPESAFE_API_KEY"] = "fake-invalid-key-for-test"
        proc = subprocess.run(
            [sys.executable, "scripts/jev_attribution.py",
             "--probe-json", self.t.probe, "--out", self.t.out, "--date", "2026-09-22"],
            cwd=ROOT, capture_output=True, text=True, timeout=40, env=env)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[:600])
        self.assertTrue(os.path.exists(self.t.out), "归因报告应已写出")
        with open(self.t.out, encoding="utf-8") as _f:
            md = _f.read()
        self.assertIn("rest.isric.org", md)


if __name__ == "__main__":
    unittest.main()
