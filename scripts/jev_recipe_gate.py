"""Jev recipe safety gate — batch judgment over all 110 Env Recipes.

WHAT THIS DOES
- Loads every Env Recipe (data/env_recipes/*.json, `_`-prefixed snapshots skipped).
- Sends them to Jev in BATCHES (one API call per batch, many Noul questions) asking
  "is this recipe's parameter set internally consistent and physically plausible?"
- Writes verdicts to a SEPARATE index (data/_demo_runtime/jev_recipe_gates.json) and a
  human report. It NEVER modifies the recipes themselves.

WHY BATCHED
- One call carries many questions => "squeeze" the free/cheap window with minimal
  round-trips. ~110 recipes / 20 per batch = ~6 calls total.

FAIL-SOFT
- No TYPESAFE_API_KEY => writes a "skipped" report, exit 0. Never crashes.
- Jev answers live in-schema; "valid" != correct. Callers must set a confidence
  threshold and escalate low-confidence flags to human review.

Zero third-party deps (stdlib only).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ_ROOT not in sys.path:
    sys.path.insert(0, PROJ_ROOT)

import agent.jev_gate as G  # noqa: E402

RECIPE_DIR = os.path.join(PROJ_ROOT, "data", "env_recipes")
GATE_INDEX = os.path.join(PROJ_ROOT, "data", "_demo_runtime", "jev_recipe_gates.json")
BATCH_SIZE = 20

# Bounds mirrored from agent.jev_gate.RECIPE_SANITY (flat keys for the prompt).
BOUNDS = {
    "temperature.day_c": (-5.0, 45.0),
    "temperature.night_c": (-15.0, 40.0),
    "humidity.min_pct": (30.0, 95.0),
    "humidity.max_pct": (30.0, 95.0),
    "water_nutrient.ph": (4.5, 8.5),
}
BOUNDS_STR = "; ".join(f"{k}: {lo}–{hi}" for k, (lo, hi) in BOUNDS.items())

INSTRUCTION = (
    "For recipe #{idx} listed in the shared state, check ONLY physical plausibility "
    "and internal consistency — NOT agronomic quality. The recipe is IMPLAUSIBLE "
    "(answer False) if ANY of these hold: (a) a parameter lies outside its stated "
    f"bound ({BOUNDS_STR}); (b) humidity.min_pct > humidity.max_pct; "
    "(c) night temperature > day temperature. Otherwise answer True. "
    "Answer True only if NO genuine problem exists; answer False if ANY exists."
)


def _extract_params(recipe: dict) -> dict:
    env = recipe.get("environment", {}) or {}
    out: dict = {}
    t = env.get("temperature", {}) or {}
    for k in ("day_c", "night_c"):
        if isinstance(t.get(k), (int, float)):
            out[f"temperature.{k}"] = float(t[k])
    h = env.get("humidity", {}) or {}
    for k in ("min_pct", "max_pct"):
        if isinstance(h.get(k), (int, float)):
            out[f"humidity.{k}"] = float(h[k])
    wn = env.get("water_nutrient", {}) or {}
    if isinstance(wn.get("ph"), (int, float)):
        out["water_nutrient.ph"] = float(wn["ph"])
    return out


def _load_recipes() -> list:
    out = []
    for fn in sorted(os.listdir(RECIPE_DIR)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        p = os.path.join(RECIPE_DIR, fn)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        rid = (d.get("crop", {}) or {}).get("species") or d.get("recipe_id") or fn[:-5]
        out.append({"recipe_id": fn[:-5], "crop": rid, "data": d})
    return out


def run(date: str, out_path: str) -> int:
    recipes = _load_recipes()
    total = len(recipes)
    print(f"[jev_recipe_gate] loaded {total} recipes")

    if not G.jev_available():
        print("[jev_recipe_gate] no TYPESAFE_API_KEY -> skipped (deterministic only)")
        report = {
            "date": date, "model": None, "total": total, "mode": "skipped(no_key)",
            "gates": {}, "summary": {"safe": 0, "implausible": 0, "low_conf": 0,
                                     "skipped": total},
        }
        os.makedirs(os.path.dirname(GATE_INDEX), exist_ok=True)
        json.dump(report, open(GATE_INDEX, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        _write_md(out_path, date, None, total, [], skipped=True)
        return 0

    gates: dict = {}
    batches = [recipes[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    for bi, batch in enumerate(batches):
        state_lines = []
        questions = {}
        for j, rec in enumerate(batch):
            params = _extract_params(rec["data"])
            state_lines.append(f"{j + 1}. {rec['crop']}: {json.dumps(params, ensure_ascii=False)}")
            qid = f"r{j + 1}"
            questions[qid] = {
                "type": "noul",
                "instructions": INSTRUCTION.format(idx=j + 1),
            }
        state = "Recipes (numbered):\n" + "\n".join(state_lines)
        answers, err = G.jev_ask(questions, state, timeout=30)
        if err:
            # whole batch failed -> mark skipped, never crash
            for rec in batch:
                gates[rec["recipe_id"]] = {
                    "crop": rec["crop"], "skipped": True, "note": err,
                    "safe": None, "noul_prob": None, "confidence": None,
                }
            continue
        for j, rec in enumerate(batch):
            qid = f"r{j + 1}"
            a = answers.get(qid)
            if not a or "noul" not in a:
                gates[rec["recipe_id"]] = {
                    "crop": rec["crop"], "skipped": True, "note": "bad_noul_answer",
                    "safe": None, "noul_prob": None, "confidence": None,
                }
                continue
            prob = float(a["noul"])
            conf = float(a.get("confidence", 0.0))
            gates[rec["recipe_id"]] = {
                "crop": rec["crop"],
                "skipped": False,
                "safe": prob >= 0.5,
                "noul_prob": round(prob, 3),
                "confidence": round(conf, 3),
                "note": None,
            }
        print(f"[jev_recipe_gate] batch {bi + 1}/{len(batches)} done")

    safe = sum(1 for v in gates.values() if v.get("safe") is True)
    impl = sum(1 for v in gates.values() if v.get("safe") is False)
    low = sum(1 for v in gates.values()
              if v.get("skipped") is False and v.get("confidence", 0) < 0.7)
    report = {
        "date": date, "model": G.JEV_MODEL, "total": total, "mode": "jev",
        "gates": gates,
        "summary": {"safe": safe, "implausible": impl, "low_conf": low,
                    "skipped": total - len([v for v in gates.values() if not v.get("skipped")])},
    }
    os.makedirs(os.path.dirname(GATE_INDEX), exist_ok=True)
    json.dump(report, open(GATE_INDEX, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    _write_md(out_path, date, G.JEV_MODEL, total,
              [v for v in gates.values() if v.get("safe") is False], skipped=False)
    print(f"[jev_recipe_gate] done: safe={safe} implausible={impl} low_conf={low}")
    return 0


def _write_md(path: str, date: str, model, total: int, implausible: list, skipped: bool) -> None:
    lines = [f"# Jev 配方安全门禁 · {date}", ""]
    if skipped:
        lines.append("> **模式：skipped（无 TYPESAFE_API_KEY）** — 未调用 Jev，"
                     "仅记录确定性基线。设置 key 后重跑即出真实归因。")
        lines.append("")
        lines.append(f"- 配方总数：{total}")
        lines.append("- 本次未判定（无 key）")
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        return
    lines.append(f"> 模型：`{model}` · 判定层副驾，绝不回写配方主链。")
    lines.append("")
    lines.append(f"- 配方总数：**{total}**")
    lines.append(f"- 内部一致/物理合理：**{total - len(implausible)}**")
    lines.append(f"- **可疑（需人工复核）：{len(implausible)}**")
    lines.append("")
    if implausible:
        lines.append("## 可疑配方（高置信 implausible，建议人工核验）")
        lines.append("")
        lines.append("| 作物 | recipe_id | noul_prob | confidence |")
        lines.append("|---|---|---|---|")
        for v in implausible:
            rid = next((k for k, gv in _gates_of(path) if gv["crop"] == v["crop"]), v["crop"])
            lines.append(f"| {v['crop']} | {rid} | {v.get('noul_prob')} | {v.get('confidence')} |")
    else:
        lines.append("无高置信可疑项。Jev 判定全部配方参数集内部一致、物理合理 "
                     "（低置信项仍建议抽样人工复核）。")
    open(path, "w", encoding="utf-8").write("\n".join(lines))


def _gates_of(path: str):
    # helper to recover recipe_id->crop from the index; not used in skipped mode
    try:
        idx = json.load(open(GATE_INDEX, encoding="utf-8"))
        return [(k, v) for k, v in idx.get("gates", {}).items()]
    except Exception:
        return []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out", default=os.path.join(
        PROJ_ROOT, "outputs", f"jev_recipe_gate_{datetime.date.today().isoformat()}.md"))
    args = ap.parse_args()
    sys.exit(run(args.date, args.out))
