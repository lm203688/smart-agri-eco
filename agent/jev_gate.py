"""Jev (TypeSafe System One) decision gate — OPTIONAL judgment layer.

Design rules (do NOT violate):
- This module is a JUDGMENT / ROUTING / GATE layer only. It MUST NOT write any
  Jev output back into calibrated real data (e.g. data/crop_adapt_db.json).
  Jev answers are advisory: route / escalate / gate, never authoritative data.
- Requires a key from EITHER the TYPESAFE_API_KEY / TYPESAFE_KEY env var OR the
  credential file ~/.config/typesafe/credentials.json (see `_api_key`). If no key
  is resolvable by either route, every call returns skipped=True so callers fall
  back to deterministic logic (fail-soft, never crash the loop). Tests point
  TYPESAFE_CRED_FILE at a nonexistent path to stay hermetic.
- Jev answers live inside the supplied schema; "valid label" != semantically
  correct. Callers MUST set a confidence threshold and escalate low-confidence
  cases to human review. Do not auto-trust.
- Network / HTTP errors are fail-closed: return skipped, never raise.

Endpoint contract (docs.typesafe.ai, verified 2026-09-22):
  POST https://api.typesafe.ai/v1/systemone
  Authorization: Bearer <TYPESAFE_API_KEY>
  body:  {"state": <text|object|array>, "model": "jev-latest",
          "questions": { "<qid>": {"type":"noul|score|choice", "instructions": "...",
                                   "criteria": {...} | [...]} }}
  resp:  {"model": "...", "answers": { "<qid>": {"type":..., "noul"|"score"|"choice":...,
                                                 "confidence":..., "probabilities":{...}} },
          "usage": {...}}

Zero third-party deps (stdlib urllib only), consistent with the project's
stdlib-only deployment philosophy. The optional `typesafe-sdk` is NOT used.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
_DEFAULT_TIMEOUT = 8

# Escape label injected into every Choice question so the model is never forced
# to pick a wrong option when none fits.
_OTHER_LABEL = "__other__"


# Credential file fallback (added 2026-09-23). The key lives OUTSIDE the repo at
# ~/.config/typesafe/credentials.json ({"api_key": "..."}), which keeps it out of
# git while letting scheduled / non-interactive runs (daily-loop automation) reach
# the Jev layer without anyone exporting TYPESAFE_API_KEY by hand. Only the *path*
# is referenced here — never the key itself. Override with TYPESAFE_CRED_FILE.
_CRED_FILE_ENV = "TYPESAFE_CRED_FILE"
_DEFAULT_CRED_FILE = os.path.join("~", ".config", "typesafe", "credentials.json")


def _api_key() -> Optional[str]:
    env_key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_KEY")
    if env_key:
        return env_key
    cred = os.path.expanduser(os.environ.get(_CRED_FILE_ENV, _DEFAULT_CRED_FILE))
    try:
        with open(cred, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 - missing/unreadable file is a silent no-key
        return None
    if isinstance(data, dict):
        value = data.get("api_key") or data.get("apiKey") or data.get("key")
        return value if isinstance(value, str) and value else None
    return None


def jev_available() -> bool:
    """True if a key is present (caller may branch to deterministic logic otherwise)."""
    return bool(_api_key())


def _post(questions: Dict[str, Any], state: Any,
          model: str = JEV_MODEL, timeout: int = _DEFAULT_TIMEOUT
          ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return (answers_dict, error_str). error None = success; non-None = skipped reason."""
    key = _api_key()
    if not key:
        return None, "no_key"
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
    req = urllib.request.Request(
        JEV_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("answers", {}), None
    except urllib.error.HTTPError as e:
        return None, f"http_{e.code}"
    except Exception:  # noqa: BLE001 - fail-closed, never raise into the caller loop
        return None, "conn_error"


def jev_noul(state: Any, instructions: str, qid: str = "q1",
             threshold: float = 0.5) -> Tuple[Optional[bool], Optional[float], bool, Optional[str]]:
    """Noul: is `instructions` true of state? Returns (is_true, prob, skipped, note).

    `is_true` is only meaningful when skipped is False and prob >= threshold.
    """
    ans, err = _post({qid: {"type": "noul", "instructions": instructions}}, state)
    if err:
        return None, None, True, err
    a = ans.get(qid)
    if not a or a.get("type") != "noul" or "noul" not in a:
        return None, None, True, "bad_noul_answer"
    prob = float(a["noul"])
    return (prob >= threshold), prob, False, None


def jev_score(state: Any, instructions: str, levels: list, qid: str = "q1"
              ) -> Tuple[Optional[float], Optional[float], bool, Optional[str]]:
    """Score state on an ordered rubric `levels` (list of descriptions, low->high).
    Returns (score, confidence, skipped, note). score may fall between levels.
    """
    ans, err = _post(
        {qid: {"type": "score", "instructions": instructions, "criteria": list(levels)}}, state)
    if err:
        return None, None, True, err
    a = ans.get(qid)
    if not a or a.get("type") != "score" or "score" not in a:
        return None, None, True, "bad_score_answer"
    return float(a["score"]), float(a.get("confidence", 0.0)), False, None


def jev_choice(state: Any, instructions: str, options: list, qid: str = "q1",
               add_other: bool = True
               ) -> Tuple[Optional[str], Optional[Dict[str, float]], Optional[float], bool, Optional[str]]:
    """Choice among `options` (list of labels). Returns
    (choice, probabilities, confidence, skipped, note).

    An explicit escape label is always appended so the model can say "none fit"
    instead of forcing a wrong pick; that maps to choice=None (uncertain).
    """
    opts: Dict[str, str] = {o: o for o in options}
    if add_other:
        opts[_OTHER_LABEL] = "其他 / 不确定"
    ans, err = _post(
        {qid: {"type": "choice", "instructions": instructions, "criteria": opts}}, state)
    if err:
        return None, None, None, True, err
    a = ans.get(qid)
    if not a or a.get("type") != "choice" or "choice" not in a:
        return None, None, None, True, "bad_choice_answer"
    choice = a["choice"]
    if choice == _OTHER_LABEL:
        choice = None
    return choice, a.get("probabilities"), float(a.get("confidence", 0.0)), False, None


def jev_gate_record(record: Dict[str, Any], baseline: Dict[str, Any],
                    instructions: str, qid: str = "gate",
                    noul_threshold: float = 0.5,
                    conf_threshold: float = 0.85
                    ) -> Tuple[bool, Optional[float], bool, Optional[str]]:
    """Data-quality GATE before a candidate record enters the calibrated main chain.

    Asks Jev Noul "is `instructions` (i.e. is this record consistent & trustworthy
    vs baseline) true of the record?". Returns (block, confidence, skipped, note).

    - block=True ONLY when Jev is confident (conf >= conf_threshold) that the record
      is INCONSISTENT (noul prob < noul_threshold). Everything else proceeds.
    - skipped=True (no key / network error) => NEVER block (fail-soft; the caller's
      deterministic validation still runs). This keeps the gate advisory, never a
      hard dependency that could silently freeze the data pipeline.
    - Jev answers live in-schema; "valid label" != semantically correct, hence the
      high conf_threshold before we will actually quarantine a record.
    """
    ans, err = _post(
        {qid: {"type": "noul", "instructions": instructions}},
        {"candidate_record": record, "baseline": baseline},
    )
    if err:
        return False, None, True, err
    a = ans.get(qid)
    if not a or a.get("type") != "noul" or "noul" not in a:
        return False, None, True, "bad_noul_answer"
    prob = float(a["noul"])
    conf = float(a.get("confidence", 0.0))
    # "consistent & trustworthy" == noul True. Inconsistent (== block) needs both
    # a low prob AND high confidence, else we escalate rather than block.
    if prob < noul_threshold and conf >= conf_threshold:
        return True, conf, False, f"jev_quarantine noul={prob:.2f} conf={conf:.2f}"
    return False, conf, False, None


def jev_ask(questions: Dict[str, Any], state: Any,
            model: str = JEV_MODEL, timeout: int = 30
            ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Public batch wrapper around `_post`. Use to send MANY questions in ONE call
    (efficient: one API round-trip for a whole batch). Returns (answers_dict, error).

    `questions` is a dict keyed by qid; `state` is shared text/object for the batch.
    Callers iterate the returned answers dict by qid. Fail-soft: error != None when
    no key / network down (never raises).
    """
    return _post(questions, state, model=model, timeout=timeout)


# ---------------------------------------------------------------------------
# Domain helpers: recipe safety gate + calibration-outlier flagger.
# Both are JUDGMENT-only: they never write results back into main-chain data.
# ---------------------------------------------------------------------------

# Crop-agnostic agronomic sanity envelope used by the recipe gate. These are
# deliberately wide "physical plausibility" bounds, not optimal-growing ranges —
# the gate's job is to catch impossible / self-contradictory values, not to
# judge agronomic quality (which is the human's call). Recipe JSON stores these
# nested under `environment.*` (confirmed against real recipe files 2026-09-23).
RECIPE_SANITY = {
    "temperature.day_c": (-5.0, 45.0),
    "temperature.night_c": (-15.0, 40.0),
    "humidity.min_pct": (30.0, 95.0),
    "humidity.max_pct": (30.0, 95.0),
    "water_nutrient.ph": (4.5, 8.5),
}


def _recipe_params(recipe: Dict[str, Any]) -> Dict[str, float]:
    """Extract the sanity-checkable params from a real (nested) recipe JSON."""
    env = recipe.get("environment", {}) or {}
    out: Dict[str, float] = {}
    t = env.get("temperature", {}) or {}
    if isinstance(t.get("day_c"), (int, float)):
        out["temperature.day_c"] = float(t["day_c"])
    if isinstance(t.get("night_c"), (int, float)):
        out["temperature.night_c"] = float(t["night_c"])
    h = env.get("humidity", {}) or {}
    if isinstance(h.get("min_pct"), (int, float)):
        out["humidity.min_pct"] = float(h["min_pct"])
    if isinstance(h.get("max_pct"), (int, float)):
        out["humidity.max_pct"] = float(h["max_pct"])
    wn = env.get("water_nutrient", {}) or {}
    if isinstance(wn.get("ph"), (int, float)):
        out["water_nutrient.ph"] = float(wn["ph"])
    return out


def jev_gate_recipe(recipe: Dict[str, Any],
                    ranges: Dict[str, tuple] = RECIPE_SANITY,
                    qid: str = "g1"
                    ) -> Tuple[Optional[bool], Optional[float], bool, Optional[str]]:
    """Single-recipe safety gate. Asks Jev Noul: is this recipe's parameter set
    internally consistent and free of physically-impossible / self-contradictory
    values? Returns (safe, confidence, skipped, note).

    `safe` is only meaningful when skipped=False and confidence is high. The batch
    script does the real work; this single-item form exists for unit tests + a
    per-recipe fallback path.
    """
    rid = (recipe.get("crop", {}) or {}).get("species") or recipe.get("recipe_id") or "?"
    params = _recipe_params(recipe)
    if not params:
        return None, None, True, "no_checkable_params"
    bounds = "; ".join(f"{k}: {lo}–{hi}" for k, (lo, hi) in ranges.items())
    state = (
        f"Recipe for crop {rid}. Extracted parameters: "
        f"{json.dumps(params, ensure_ascii=False)}.\n"
        f"Safe agronomic plausibility bounds: {bounds}.\n"
        "Consistency rules: humidity.min_pct must be <= humidity.max_pct; "
        "day_c should be >= night_c (a warmer night than day is contradictory); "
        "every value must lie within its stated bound."
    )
    instr = (
        "Is this recipe's parameter set internally consistent and free of any "
        "physically-impossible or self-contradictory value (any param outside its "
        "stated bound, or min humidity > max humidity, or night temp > day temp)? "
        "Answer True only if NO such problem exists; answer False if ANY genuine "
        "problem exists. Do not judge agronomic quality, only physical plausibility "
        "and internal consistency."
    )
    is_true, prob, skipped, note = jev_noul(state, instr, qid=qid)
    if skipped:
        return None, None, True, note
    # noul True == consistent/safe. We report safe = is_true, conf = prob.
    return is_true, prob, False, note


def jev_flag_calib_outlier(crop: Dict[str, Any], adapt_score: float,
                           zone_climate: Dict[str, Any],
                           envelope: Dict[str, Any],
                           qid: str = "o1"
                           ) -> Tuple[Optional[bool], Optional[float], bool, Optional[str]]:
    """Single-crop calibration-outlier flagger. Asks Jev Noul: is this crop's
    calibrated adapt_score consistent with the climate evidence? Returns
    (suspicious, confidence, skipped, note). suspicious=True => score contradicts
    the climate match (potential calibration bug worth human review).

    This is the 0-user stand-in for a real feedback-calibration loop: instead of
    waiting for growers to report mismatches, we use Jev to sanity-check the
    niche-envelope-derived score against the raw climate evidence we fed in.
    """
    name = crop.get("crop") or crop.get("latin") or "?"
    zid = crop.get("zone_id") or "?"
    state = (
        f"Crop {name} assigned to zone {zid}. Calibrated adapt_score = {adapt_score:.2f} "
        f"(0–1, higher = better climatic suit). Zone climate baseline: "
        f"{json.dumps(zone_climate, ensure_ascii=False)}. Real GBIF distribution climate "
        f"envelope used to derive the score: {json.dumps(envelope, ensure_ascii=False)}."
    )
    instr = (
        "Is this calibrated adapt_score consistent with the climate evidence? It is "
        "SUSPICIOUS (answer False) only on a CLEAR contradiction — e.g. a crop whose "
        "real distribution points sit entirely in tropical/subtropical climates but "
        "scored <0.3 for a tropical zone, or a crop clearly mismatched to its zone yet "
        "scored >0.9. Minor disagreements are NOT suspicious (answer True)."
    )
    is_true, prob, skipped, note = jev_noul(state, instr, qid=qid)
    if skipped:
        return None, None, True, note
    # noul True == consistent. suspicious = NOT consistent (low prob).
    suspicious = (not is_true) and (prob is not None)
    return suspicious, prob, False, note
