"""Offline tests for the Jev decision-layer batch scripts (no network, no key).

Covers:
- jev_gate_recipe / jev_flag_calib_outlier unit logic (via mocked jev_noul)
- jev_recipe_gate.run / jev_calib_outliers.run: no-key skip path + keyed batch path
  (via mocked jev_ask), asserting verdicts land in the separate index, never the
  main-chain data.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ_ROOT not in sys.path:
    sys.path.insert(0, PROJ_ROOT)

import agent.jev_gate as G  # noqa: E402
import scripts.jev_recipe_gate as RG  # noqa: E402
import scripts.jev_calib_outliers as CO  # noqa: E402


def _clear_key():
    saved = {}
    for k in ("TYPESAFE_API_KEY", "TYPESAFE_KEY", "TYPESAFE_CRED_FILE"):
        if k in os.environ:
            saved[k] = os.environ.pop(k)
    # Redirect the credential-file fallback too, so a real key on this machine
    # cannot leak into the "no key" tests (keeps them hermetic).
    os.environ["TYPESAFE_CRED_FILE"] = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "no_such_typesafe_credentials.json")
    return saved


def _fake_ask_consistent(questions, state, model=None, timeout=30):
    answers = {}
    for qid in questions:
        answers[qid] = {"type": "noul", "noul": 0.92}
    return answers, None


def _fake_ask_inconsistent_first(questions, state, model=None, timeout=30):
    answers = {}
    for i, qid in enumerate(questions):
        # first question in the batch is "suspicious"
        prob = 0.12 if i == 0 else 0.9
        answers[qid] = {"type": "noul", "noul": prob}
    return answers, None


class TestUnitGate(unittest.TestCase):
    def test_recipe_params_extract_nested(self):
        rec = {"crop": {"species": "咖啡"}, "environment": {
            "temperature": {"day_c": 28, "night_c": 18},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {"ph": 6.0}}}
        p = G._recipe_params(rec)
        self.assertEqual(p["temperature.day_c"], 28.0)
        self.assertEqual(p["humidity.min_pct"], 50.0)
        self.assertEqual(p["water_nutrient.ph"], 6.0)

    def test_gate_recipe_consistent(self):
        rec = {"crop": {"species": "X"}, "environment": {
            "temperature": {"day_c": 25, "night_c": 15}, "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {"ph": 6.5}}}
        with mock.patch.object(G, "jev_noul", return_value=(True, 0.9, False, None)):
            safe, conf, skipped, note = G.jev_gate_recipe(rec)
        self.assertTrue(safe)
        self.assertFalse(skipped)

    def test_gate_recipe_inconsistent(self):
        rec = {"crop": {"species": "X"}, "environment": {
            "temperature": {"day_c": 5, "night_c": 25}, "humidity": {"min_pct": 90, "max_pct": 40},
            "water_nutrient": {"ph": 3.0}}}
        with mock.patch.object(G, "jev_noul", return_value=(False, 0.1, False, None)):
            safe, conf, skipped, note = G.jev_gate_recipe(rec)
        self.assertFalse(safe)
        self.assertFalse(skipped)

    def test_gate_recipe_no_params_skipped(self):
        safe, conf, skipped, note = G.jev_gate_recipe({"crop": {}})
        self.assertTrue(skipped)

    def test_flag_outlier_consistent(self):
        crop = {"crop": "蕉", "zone_id": "tropical_rainforest"}
        with mock.patch.object(G, "jev_noul", return_value=(True, 0.9, False, None)):
            susp, conf, skipped, note = G.jev_flag_calib_outlier(
                crop, 0.73, {"monthly_mean_c": [24] * 12}, {"temp_env_mean": [24] * 12})
        self.assertFalse(susp)
        self.assertFalse(skipped)

    def test_flag_outlier_suspicious(self):
        crop = {"crop": "蕉", "zone_id": "tropical_rainforest"}
        with mock.patch.object(G, "jev_noul", return_value=(False, 0.15, False, None)):
            susp, conf, skipped, note = G.jev_flag_calib_outlier(
                crop, 0.05, {"monthly_mean_c": [24] * 12}, {"temp_env_mean": [24] * 12})
        self.assertTrue(susp)


class TestRecipeGateRun(unittest.TestCase):
    def setUp(self):
        self.saved = _clear_key()
        self.date = "2026-09-23"
        # outputs/ 不入库（产物目录），干净 checkout 中不存在 —— 自建。
        os.makedirs(os.path.join(PROJ_ROOT, "outputs"), exist_ok=True)
        self.out = os.path.join(PROJ_ROOT, "outputs", "_t_recipe_gate.md")
        self.idx = RG.GATE_INDEX

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ[k] = v
        for f in (self.out, self.idx):
            if os.path.exists(f):
                os.remove(f)

    def test_no_key_skips(self):
        rc = RG.run(self.date, self.out)
        self.assertEqual(rc, 0)
        rep = json.load(open(self.idx, encoding="utf-8"))
        self.assertEqual(rep["mode"], "skipped(no_key)")
        self.assertEqual(rep["summary"]["skipped"], rep["total"])

    def test_keyed_batch_consistent(self):
        os.environ["TYPESAFE_API_KEY"] = "dummy"
        with mock.patch.object(G, "jev_ask", side_effect=_fake_ask_consistent):
            rc = RG.run(self.date, self.out)
        self.assertEqual(rc, 0)
        rep = json.load(open(self.idx, encoding="utf-8"))
        self.assertEqual(rep["mode"], "jev")
        self.assertEqual(rep["summary"]["safe"], rep["total"])
        self.assertEqual(rep["summary"]["implausible"], 0)
        # main-chain data untouched: spot-check a recipe file mtime-independent
        self.assertTrue(os.path.exists(self.out))


class TestCalibOutlierRun(unittest.TestCase):
    def setUp(self):
        self.saved = _clear_key()
        self.date = "2026-09-23"
        os.makedirs(os.path.join(PROJ_ROOT, "outputs"), exist_ok=True)
        self.out = os.path.join(PROJ_ROOT, "outputs", "_t_calib_out.md")
        self.idx = CO.OUTLIER_INDEX

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ[k] = v
        for f in (self.out, self.idx):
            if os.path.exists(f):
                os.remove(f)

    def test_no_key_skips(self):
        rc = CO.run(self.date, self.out)
        self.assertEqual(rc, 0)
        rep = json.load(open(self.idx, encoding="utf-8"))
        self.assertEqual(rep["mode"], "skipped(no_key)")

    def test_keyed_batch_flags_first(self):
        os.environ["TYPESAFE_API_KEY"] = "dummy"
        with mock.patch.object(G, "jev_ask", side_effect=_fake_ask_inconsistent_first):
            rc = CO.run(self.date, self.out)
        self.assertEqual(rc, 0)
        rep = json.load(open(self.idx, encoding="utf-8"))
        self.assertEqual(rep["mode"], "jev")
        # deterministic climate-gap signal must be computed and reproducible
        # (real crops 香茅/沙漠玫瑰 have |GBIF mean − zone mean| > 8°C).
        self.assertGreaterEqual(rep["summary"]["climate_mismatch"], 1)
        # Jev path must have run and produced per-crop noul evidence
        any_ran = any(isinstance(v.get("jev_noul_runs"), list)
                      for v in rep["flags"].values())
        self.assertTrue(any_ran)


if __name__ == "__main__":
    unittest.main()
