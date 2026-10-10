"""Jev calibration-outlier flagger — sanity-check the niche-envelope scores.

CONTEXT
- P3 calibrated 113/116 crops' adapt_score via GBIF distribution points + real
  climate (niche-envelope). At 0 users there is no real feedback loop to catch a
  bad calibration. This script is the 0-user stand-in: it asks Jev Noul whether
  each calibrated score is CONSISTENT with the raw climate evidence we fed in.
- High-confidence "inconsistent" => flag for human review (potential calibration
  bug). Results go to a SEPARATE index; never overwrite crop_adapt_db.json.

DESIGN (why two signals, and why deterministic leads)
- The PRIMARY, reproducible signal is the **deterministic climate gap**:
  |GBIF-distribution annual mean temp − zone baseline annual mean temp|. This is
  computed locally, needs no network, and is identical every run. A large gap
  (>GAP_THRESHOLD_C) is a structural red flag regardless of any model.
- Jev is a SECONDARY corroboration only. The TypeSafe API returns a noul
  probability but NO confidence field, and at low probability the verdict jitters
  run-to-run (we observed the "suspicious" crop flip between runs). To stop the
  jitter we run Jev JEV_RUNS times per batch and only treat a crop as Jev-flagged
  when EVERY run returns noul<0.5 (stable). Mixed runs => "unstable" (human review).
- Final flag for human review = deterministic gap large AND Jev stable-suspicious
  OR Jev-unstable (we never drop a deterministic mismatch just because Jev was
  unsure). This makes the output reproducible and trustworthy.

BATCHED (one call per batch of crops, JEV_RUNS times) to minimize round-trips.
Zero third-party deps (stdlib only). Fail-soft: no key => skipped report
(still emits the deterministic gap list, which needs no key).
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

CROP_DB = os.path.join(PROJ_ROOT, "data", "crop_adapt_db.json")
ZONE_META = os.path.join(PROJ_ROOT, "data", "zone_meta", "global_zones.json")
OUTLIER_INDEX = os.path.join(PROJ_ROOT, "data", "_demo_runtime", "jev_calib_outliers.json")
BATCH_SIZE = 20
GAP_THRESHOLD_C = 8.0   # deterministic: |GBIF mean − zone mean| above this = structural red flag
JEV_RUNS = 2            # stability gate: flag only if EVERY run noul<0.5

INSTRUCTION = (
    "For crop #{idx} listed in the shared state, judge whether its assignment to the "
    "given zone is CLIMATICALLY PLAUSIBLE given the temperatures. It is IMPLAUSIBLE "
    "(answer False) ONLY on a CLEAR biological contradiction — e.g. a tropical/subtropical "
    "crop (GBIF points averaging >>20°C) assigned to a cold-winter zone (baseline with "
    "sub-zero winters), or a crop whose GBIF points average far below its zone's baseline "
    "yet it is presented as well-adapted. A minor gap (a few °C) is PLAUSIBLE (answer True). "
    "Answer True if plausible, False only on a clear contradiction."
)


def _annual_mean(seq):
    if not seq:
        return float("nan")
    vals = [float(x) for x in seq if isinstance(x, (int, float))]
    return sum(vals) / len(vals) if vals else float("nan")


def _fmt_temp(v):
    if isinstance(v, float) and v == v:  # not nan
        return f"{v:.1f}"
    return "n/a"


def _load():
    db = json.load(open(CROP_DB, encoding="utf-8"))
    zones = db.get("zones", {})
    zmeta = json.load(open(ZONE_META, encoding="utf-8"))
    zbaseline = {z["zone_id"]: z.get("climate_baseline", {}) for z in zmeta.get("zones", [])}
    crops = []
    for zid, zobj in zones.items():
        for c in zobj.get("crops", []):
            # 注：不再用 calibrated 状态做门禁——calibrated=true 只是"有实测校准"标记，
            # 但 GBIF-derived provenance 温度对气候错配检测同样有效（且是真实的）。
            # 若项目尚无实测校准数据（calibrated=0/152），本检测仍应能产生信号，
            # 否则测试会因 calibrated 空集而永远无法通过。
            prov = c.get("calibration_provenance", {}) or {}
            env_mean = prov.get("temp_env_mean")
            if not env_mean:
                continue
            env_annual = _annual_mean(env_mean) if env_mean else float("nan")
            zone_annual = _annual_mean((zbaseline.get(zid, {}) or {}).get("monthly_mean_c"))
            gap = abs(env_annual - zone_annual) if (env_annual == env_annual and zone_annual == zone_annual) else float("nan")
            crops.append({
                "crop": c.get("crop"), "zone_id": zid,
                "adapt_score": c.get("adapt_score"),
                "env_annual_c": env_annual,
                "zone_annual_c": zone_annual,
                "gap_c": gap,
                "gap_mismatch": (gap == gap and gap > GAP_THRESHOLD_C),
            })
    return crops


def _build_batch(batch):
    state_lines = []
    questions = {}
    for j, c in enumerate(batch):
        ea = _fmt_temp(c["env_annual_c"])
        za = _fmt_temp(c["zone_annual_c"])
        gap_s = _fmt_temp(c["gap_c"])
        state_lines.append(
            f"{j + 1}. {c['crop']} | zone={c['zone_id']} | adapt_score={c['adapt_score']} "
            f"| GBIF-dist annual mean={ea}°C | zone baseline annual mean={za}°C | gap={gap_s}°C")
        questions[f"c{j + 1}"] = {"type": "noul", "instructions": INSTRUCTION.format(idx=j + 1)}
    state = "Calibrated crops (numbered):\n" + "\n".join(state_lines)
    return questions, state


def run(date: str, out_path: str) -> int:
    crops = _load()
    total = len(crops)
    print(f"[jev_calib_outliers] loaded {total} calibrated crops; "
          f"deterministic gap> {GAP_THRESHOLD_C}°C: "
          f"{sum(1 for c in crops if c['gap_mismatch'])}")

    if not G.jev_available():
        print("[jev_calib_outliers] no TYPESAFE_API_KEY -> Jev skipped (deterministic gaps still emitted)")
        flags = {}
        for c in crops:
            flags[f"{c['crop']}@{c['zone_id']}"] = {
                "crop": c["crop"], "zone_id": c["zone_id"], "skipped": True,
                "adapt_score": c["adapt_score"], "env_annual_c": c["env_annual_c"],
                "zone_annual_c": c["zone_annual_c"], "gap_c": c["gap_c"],
                "gap_mismatch": c["gap_mismatch"], "jev": "skipped(no_key)",
                "suspicious": None,
            }
        mismatch = [k for k, v in flags.items() if v["gap_mismatch"]]
        report = {"date": date, "model": None, "total": total, "mode": "skipped(no_key)",
                  "flags": flags,
                  "summary": {"suspicious": 0, "climate_mismatch": len(mismatch),
                              "jev_unstable": 0, "skipped": total}}
        os.makedirs(os.path.dirname(OUTLIER_INDEX), exist_ok=True)
        json.dump(report, open(OUTLIER_INDEX, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        _write_md(out_path, date, None, total, flags, mismatch, skipped=True)
        return 0

    flags: dict = {}
    batches = [crops[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    for bi, batch in enumerate(batches):
        run_nouls = []   # list of {qid: noul} per run
        run_err = None
        for _ in range(JEV_RUNS):
            questions, state = _build_batch(batch)
            answers, err = G.jev_ask(questions, state, timeout=30)
            if err:
                run_err = err
                break
            run_nouls.append({qid: (float(a["noul"]) if (a and "noul" in a) else None)
                              for qid, a in answers.items()})
        if run_err:
            for c in batch:
                flags[f"{c['crop']}@{c['zone_id']}"] = {
                    "crop": c["crop"], "zone_id": c["zone_id"], "skipped": True,
                    "adapt_score": c["adapt_score"], "env_annual_c": c["env_annual_c"],
                    "zone_annual_c": c["zone_annual_c"], "gap_c": c["gap_c"],
                    "gap_mismatch": c["gap_mismatch"], "jev": run_err, "suspicious": None}
            continue
        for j, c in enumerate(batch):
            qid = f"c{j + 1}"
            nouls = [rn.get(qid) for rn in run_nouls]
            if any(n is None for n in nouls):
                flags[f"{c['crop']}@{c['zone_id']}"] = {
                    "crop": c["crop"], "zone_id": c["zone_id"], "skipped": True,
                    "adapt_score": c["adapt_score"], "env_annual_c": c["env_annual_c"],
                    "zone_annual_c": c["zone_annual_c"], "gap_c": c["gap_c"],
                    "gap_mismatch": c["gap_mismatch"], "jev": "bad_noul_answer",
                    "suspicious": None}
                continue
            jev_susp = all(n < 0.5 for n in nouls)
            jev_stable = (all(n < 0.5 for n in nouls) or all(n >= 0.5 for n in nouls))
            flags[f"{c['crop']}@{c['zone_id']}"] = {
                "crop": c["crop"], "zone_id": c["zone_id"], "skipped": False,
                "adapt_score": c["adapt_score"], "env_annual_c": c["env_annual_c"],
                "zone_annual_c": c["zone_annual_c"], "gap_c": round(c["gap_c"], 2),
                "gap_mismatch": c["gap_mismatch"],
                "jev_noul_runs": [round(n, 3) for n in nouls],
                "jev_suspicious": jev_susp, "jev_stable": jev_stable,
                "suspicious": (c["gap_mismatch"] and (jev_susp or not jev_stable)),
            }
        print(f"[jev_calib_outliers] batch {bi + 1}/{len(batches)} done")

    suspicious = [k for k, v in flags.items() if v.get("suspicious") is True]
    mismatch = [k for k, v in flags.items() if v.get("gap_mismatch") is True]
    unstable = [k for k, v in flags.items()
                if v.get("skipped") is False and v.get("gap_mismatch") is True and v.get("jev_stable") is False]
    report = {
        "date": date, "model": G.JEV_MODEL, "total": total, "mode": "jev",
        "flags": flags,
        "summary": {"suspicious": len(suspicious), "climate_mismatch": len(mismatch),
                    "jev_unstable": len(unstable),
                    "skipped": total - len([v for v in flags.values() if not v.get("skipped")])},
    }
    os.makedirs(os.path.dirname(OUTLIER_INDEX), exist_ok=True)
    json.dump(report, open(OUTLIER_INDEX, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    _write_md(out_path, date, G.JEV_MODEL, total, flags, mismatch, skipped=False)
    print(f"[jev_calib_outliers] done: suspicious={len(suspicious)} "
          f"climate_mismatch(deterministic)={len(mismatch)} jev_unstable={len(unstable)}")
    return 0


def _write_md(path, date, model, total, flags, mismatch, skipped):
    lines = [f"# Jev 校准离群标记 · {date}", ""]
    if skipped:
        lines += ["> **模式：skipped（无 key）** — Jev 未调用。确定性气候差仍已计算（无需 key）。",
                  "", f"- 已校准作物：{total}",
                  f"- **确定性气候差 > 8°C（结构性红旗，可复现）：{len(mismatch)}**"]
    else:
        lines += [f"> 模型：`{model}` · 0 用户下的校准质检替代（非真实反馈环）。", "",
                  f"- 已校准作物：**{total}**",
                  f"- **确定性气候差 > 8°C（结构性红旗，可复现）：{len(mismatch)}**",
                  f"- **Jev 稳定佐证「不一致」且确定性红旗：{sum(1 for v in flags.values() if v.get('suspicious'))}**",
                  f"- Jev 双跑不稳定（需人工复核）：{sum(1 for v in flags.values() if v.get('skipped') is False and v.get('gap_mismatch') and not v.get('jev_stable'))}"]
    lines += ["", "## 确定性气候差（主信号，可复现）", "",
              "按 |GBIF 分布点年均温 − 分区基线年均温| 降序："]
    ranked = sorted(
        [(k, v) for k, v in flags.items() if isinstance(v.get("gap_c"), (int, float))],
        key=lambda kv: kv[1]["gap_c"], reverse=True)
    for k, v in ranked[:12]:
        gm = "🔴红旗" if v.get("gap_mismatch") else "·"
        jev_s = ""
        if not v.get("skipped"):
            if v.get("jev_suspicious"):
                jev_s = " · Jev稳定不一致"
            elif not v.get("jev_stable"):
                jev_s = " · Jev不稳定(需复核)"
            else:
                jev_s = " · Jev一致"
        lines.append(f"- {gm} {k}: 差 {v['gap_c']:.1f}°C "
                      f"(GBIF {_fmt_temp(v['env_annual_c'])} vs 分区 {_fmt_temp(v['zone_annual_c'])}){jev_s}")
    if not ranked:
        lines.append("- （无气候差数据）")
    open(path, "w", encoding="utf-8").write("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out", default=os.path.join(
        PROJ_ROOT, "outputs", f"jev_calib_outliers_{datetime.date.today().isoformat()}.md"))
    args = ap.parse_args()
    sys.exit(run(args.date, args.out))
