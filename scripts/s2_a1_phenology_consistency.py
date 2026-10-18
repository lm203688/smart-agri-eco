#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2-A1：物候一致性交叉验证 —— `estimate_stage_days` 对 7×5=35 组 (crop, T)
逐点复算 + 边界契约 + 单调性。

路线要求（docs/SCI_ROADMAP_2026-10-18.md §S2-A1）：
  - 7 个 WOFOST 作物 × 5 个温度水平（10/15/20/25/30°C）跑全套
  - 与 WOFOST 参数表复算值对比，报告 RMSE / MAE / CCC (Lin 1989)
  - TBASE 边界：T < TBASE 必须返回"停滞"（None），不得返回负天数
  - 验收：35 组对比，RMSE ≤ 1 天，且 0 组出现负天数

**诚实标注**（必须与论文一致）：
本项目的 `estimate_stage_days` 直接实现了 WOFOST 的积温公式
`days = TSUM / max(0, T - TBASE)`，与"WOFOST 参数表复算值"
在数学上同源。因此本脚本的**主检查是代码正确性**（防公式被误改、
防除零、防负数漏检），而非外部独立基线。真正的**外部交叉验证**
由两条互补链路承担：
  1. S1.5（`benchmarks/baseline_external/run_baseline.py`）——
     用 NASA POWER 气候基线 + Köppen-Geiger 决策树复算分区；
  2. S2-A2（`scripts/s2_a2_koppen_consistency.py`）——
     用 Köppen 栅格 + 分区元数据做内部一致性检验。
审稿人若问"物候与真实田间观测差多少"，本脚本给不出答案——
那是 S2-B（物理采集）的职责；S1.5 + S2-A1 + S2-A2 组合是
"内部数学一致性 + 外部权威参数源"的诚实边界。

用法：
    python scripts/s2_a1_phenology_consistency.py
    python scripts/s2_a1_phenology_consistency.py --json
    python scripts/s2_a1_phenology_consistency.py --strict
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.phenology import estimate_stage_days  # noqa: E402

REF_PATH = ROOT / "data" / "wofost_phenology_reference.json"
OUT_DIR = ROOT / "benchmarks" / "results"
OUT_PATH = OUT_DIR / "phenology_consistency.json"

# 路线要求的温度网格
TEMPERATURES = [10.0, 15.0, 20.0, 25.0, 30.0]
STAGES = ("emergence_days", "anthesis_days_from_sow", "maturity_days_from_sow")

# 独立复算参考用的 TSUM 参数（与 wofost_phenology_reference.json 保持位对齐；
# 若文件被改，本脚本会因一致性检查失败而暴露——这正是守卫目的）
EXPECTED_TSUM: Dict[str, Dict[str, float]] = {
    "potato":     {"tsum_em": 170, "tsum1": 150,  "tsum2": 1550, "tbase_c": 2.0},
    "wheat":      {"tsum_em": 120, "tsum1": 543,  "tsum2": 1194, "tbase_c": 0.0},
    "soybean":    {"tsum_em": 70,  "tsum1": 350,  "tsum2": 850,  "tbase_c": 7.0},
    "sunflower":  {"tsum_em": 130, "tsum1": 1050, "tsum2": 1000, "tbase_c": 3.0},
    "rice":       {"tsum_em": 100, "tsum1": 875,  "tsum2": 625,  "tbase_c": 10.0},
    "sweetpotato": {"tsum_em": 200, "tsum1": 416, "tsum2": 1436, "tbase_c": 10.0},
    "mungbean":   {"tsum_em": 60,  "tsum1": 640,  "tsum2": 753,  "tbase_c": 10.0},
}


# ---------------------------------------------------------------------------
# 统计工具
# ---------------------------------------------------------------------------
def mean(v: List[float]) -> float:
    return sum(v) / len(v)


def rmse(pred: List[float], obs: List[float]) -> float:
    n = min(len(pred), len(obs))
    if n == 0:
        return float("nan")
    return math.sqrt(sum((p - o) ** 2 for p, o in zip(pred[:n], obs[:n])) / n)


def mae(pred: List[float], obs: List[float]) -> float:
    n = min(len(pred), len(obs))
    if n == 0:
        return float("nan")
    return sum(abs(p - o) for p, o in zip(pred[:n], obs[:n])) / n


def ccc(pred: List[float], obs: List[float]) -> float:
    """CCC (Lin 1989)：一致性相关系数 = 1 - Σ(a-b)² / Σ[(|a-ā| + |b-b̄|)²]。"""
    n = min(len(pred), len(obs))
    if n == 0:
        return float("nan")
    p, o = pred[:n], obs[:n]
    mp, mo = sum(p) / n, sum(o) / n
    num = sum((a - b) ** 2 for a, b in zip(p, o))
    den = sum((abs(a - mp) + abs(b - mo)) ** 2 for a, b in zip(p, o))
    if den == 0:
        return float("nan")
    return 1.0 - num / den


# ---------------------------------------------------------------------------
# 独立复算参考（不 import estimate_stage_days 的中间量，从 TSUM 直接算）
# ---------------------------------------------------------------------------
def reference_days(crop: str, T: float) -> Dict[str, Optional[float]]:
    """用 EXPECTED_TSUM 直接算参考值；T - TBASE <= 0 时全部置 None（停滞）。"""
    p = EXPECTED_TSUM[crop]
    tbase = p["tbase_c"]
    eff = T - tbase
    if eff <= 0:
        return {"emergence_days": None, "anthesis_days_from_sow": None,
                "maturity_days_from_sow": None}
    return {
        "emergence_days": round(p["tsum_em"] / eff, 1),
        "anthesis_days_from_sow": round((p["tsum_em"] + p["tsum1"]) / eff, 1),
        "maturity_days_from_sow": round((p["tsum_em"] + p["tsum1"] + p["tsum2"]) / eff, 1),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_report() -> Dict[str, Any]:
    ref = json.loads(REF_PATH.read_text(encoding="utf-8"))
    ref_crops = ref.get("crops", {})

    # ---- Part 1: TSUM 参数一致性（防 wofost_phenology_reference.json 漂移）----
    tsum_check = {"total": 0, "matched": 0, "mismatched": []}
    for crop, exp in EXPECTED_TSUM.items():
        got = ref_crops.get(crop)
        if got is None:
            tsum_check["mismatched"].append({"crop": crop, "reason": "missing_in_reference"})
            continue
        tsum_check["total"] += 1
        keys = ("tsum_em", "tsum1", "tsum2", "tbase_c")
        for k in keys:
            if float(got.get(k)) != float(exp[k]):
                tsum_check["mismatched"].append({
                    "crop": crop, "key": k,
                    "expected": exp[k], "got": got.get(k),
                })
        else:
            tsum_check["matched"] += 1

    # ---- Part 2: 35 组 (crop × T) 复算对比 ----
    rows: List[Dict[str, Any]] = []
    neg_days = 0
    mismatched = 0
    stall_expected = 0
    stall_correct = 0
    stall_wrong = 0

    for crop, _ in EXPECTED_TSUM.items():
        for T in TEMPERATURES:
            got = estimate_stage_days(crop, T)
            want = reference_days(crop, T)
            stall_ref = want["emergence_days"] is None  # 参考判定为停滞
            eff = T - EXPECTED_TSUM[crop]["tbase_c"]

            row: Dict[str, Any] = {"crop": crop, "T_c": T, "tbase_c": EXPECTED_TSUM[crop]["tbase_c"],
                                   "eff_c": round(eff, 3), "expected_stall": stall_ref}

            if not got.get("available"):
                mismatched += 1
                row.update({"got_available": False, "note": got.get("note")})
                rows.append(row)
                continue

            if stall_ref:
                stall_expected += 1
                # 停滞契约：三个 stage 必须是 None，且 note 提到"停滞"
                gs = [got.get(s) for s in STAGES]
                if all(x is None for x in gs) and "停滞" in str(got.get("note", "")):
                    stall_correct += 1
                    row["got"] = {"stalled": True}
                else:
                    stall_wrong += 1
                    row.update({"got": {s: got.get(s) for s in STAGES},
                                "note": got.get("note"), "stall_contract_violated": True})
            else:
                # 正常路径：逐 stage 对比
                per_stage = {}
                for s in STAGES:
                    g = got.get(s)
                    w = want[s]
                    if g is None:
                        mismatched += 1
                        per_stage[s] = {"got": None, "expected": w, "err": None, "verdict": "missing"}
                        continue
                    if g < 0:
                        neg_days += 1
                    per_stage[s] = {
                        "got": g, "expected": w,
                        "abs_err": round(abs(g - w), 6),
                        "verdict": "match" if abs(g - w) < 1e-6 else "mismatch",
                    }
                    if per_stage[s]["verdict"] == "mismatch":
                        mismatched += 1
                row["got"] = per_stage
            rows.append(row)

    # ---- Part 3: 数值指标（正常路径的对比；停滞点不计入 RMSE）----
    preds_em, obs_em = [], []
    preds_an, obs_an = [], []
    preds_ma, obs_ma = [], []
    for r in rows:
        if r.get("expected_stall"):
            continue
        g = r.get("got")
        if not isinstance(g, dict) or "emergence_days" not in g:
            continue
        preds_em.append(g["emergence_days"]["got"])
        obs_em.append(g["emergence_days"]["expected"])
        preds_an.append(g["anthesis_days_from_sow"]["got"])
        obs_an.append(g["anthesis_days_from_sow"]["expected"])
        preds_ma.append(g["maturity_days_from_sow"]["got"])
        obs_ma.append(g["maturity_days_from_sow"]["expected"])

    def _block(name, p, o):
        return {
            "n": len(p),
            "rmse_days": round(rmse(p, o), 6),
            "mae_days": round(mae(p, o), 6),
            "ccc": round(ccc(p, o), 6),
        }

    stats = {
        "emergence": _block("emergence", preds_em, obs_em),
        "anthesis": _block("anthesis", preds_an, obs_an),
        "maturity": _block("maturity", preds_ma, obs_ma),
    }

    # ---- Part 4: 单调性（温度↑ → 天数↓）----
    monotonicity_violations: List[Dict[str, Any]] = []
    for crop in EXPECTED_TSUM:
        series = [(T, estimate_stage_days(crop, T).get("emergence_days")) for T in TEMPERATURES]
        for (t1, d1), (t2, d2) in zip(series, series[1:]):
            if d1 is None or d2 is None:
                continue  # 停滞段跳过
            if d2 > d1:  # 温度升高但天数不降
                monotonicity_violations.append({
                    "crop": crop, "T1": t1, "T2": t2,
                    "days1": d1, "days2": d2,
                })

    # ---- Part 5: TBASE 边界契约（含路线明确点名的 wheat_below_tbase_stalled）----
    boundary_cases: List[Dict[str, Any]] = []
    for crop, p in EXPECTED_TSUM.items():
        tbase = p["tbase_c"]
        # 严格停滞：T < TBASE
        T_stall = tbase - 1.0
        # 恰好等于：T == TBASE（eff=0，也应停滞）
        T_edge = tbase
        # 刚超过：T == TBASE + 0.5
        T_above = tbase + 0.5
        for tag, T in (("below", T_stall), ("at", T_edge), ("above", T_above)):
            got = estimate_stage_days(crop, T)
            expected_stall = T <= tbase
            is_stalled = got.get("emergence_days") is None
            neg = any(isinstance(got.get(s), (int, float)) and got.get(s) < 0 for s in STAGES)
            boundary_cases.append({
                "crop": crop, "tag": tag, "T_c": T, "tbase_c": tbase,
                "expected_stall": expected_stall,
                "got_stalled": is_stalled,
                "got_negative_days": neg,
                "verdict": "pass" if (is_stalled == expected_stall and not neg) else "FAIL",
            })
    # 路线点名：wheat_below_tbase_stalled（wheat TBASE=0，取 T=-5）
    wb = estimate_stage_days("wheat", -5.0)
    wheat_below_tbase_stalled = {
        "crop": "wheat", "T_c": -5.0, "tbase_c": 0.0,
        "got_emergence_days": wb.get("emergence_days"),
        "got_note": wb.get("note"),
        "expected": "停滞（None）",
        "verdict": "pass" if wb.get("emergence_days") is None else "FAIL",
    }

    # ---- Part 6: 路线验收 ----
    overall_rmse = max(stats["emergence"]["rmse_days"],
                       stats["anthesis"]["rmse_days"],
                       stats["maturity"]["rmse_days"])
    acceptance = {
        "rmse_days_le_1": bool(overall_rmse <= 1.0),
        "overall_rmse_days": overall_rmse,
        "zero_negative_days": bool(neg_days == 0),
        "negative_days_count": neg_days,
        "stall_contract_ok": bool(stall_wrong == 0),
        "monotonicity_ok": len(monotonicity_violations) == 0,
        "tsum_drift_ok": len(tsum_check["mismatched"]) == 0,
        "wheat_below_tbase_stalled": wheat_below_tbase_stalled["verdict"] == "pass",
        "boundary_all_pass": all(b["verdict"] == "pass" for b in boundary_cases),
    }
    acceptance["all_pass"] = all(acceptance[k] for k in (
        "rmse_days_le_1", "zero_negative_days", "stall_contract_ok",
        "monotonicity_ok", "tsum_drift_ok", "wheat_below_tbase_stalled",
        "boundary_all_pass",
    ))

    return {
        "generated_by": "scripts/s2_a1_phenology_consistency.py",
        "roadmap_task": "S2-A1",
        "scope": f"{len(EXPECTED_TSUM)} crops × {len(TEMPERATURES)} T levels = "
                 f"{len(EXPECTED_TSUM) * len(TEMPERATURES)} (crop, T) combinations",
        "honesty_notes": [
            "本项目的 estimate_stage_days 与 WOFOST 参数表**同源**（TSUM/(T-TBASE)）；"
            "本脚本的主检查是**代码正确性**（防公式误改、防负数漏检、防 TSUM 漂移），"
            "而非外部独立基线。真正的外部交叉验证由 S1.5（NASA POWER + Köppen）与 "
            "S2-A2（Köppen 栅格一致性）承担；物候与真实田间观测的差异属 S2-B（物理采集）。",
            "CCC 采用 Lin 1989 定义；因公式同源，理论上 CCC 应恒为 1，任何 <1 都表明实现被改坏。",
            "TBASE 边界共 21 组（7 作物 × 3 温度档：below/at/above）；路线点名的 "
            "wheat_below_tbase_stalled 单独列入报告。",
        ],
        "tsum_parameter_drift_check": tsum_check,
        "grid_results": {"n_combinations": len(rows), "rows": rows},
        "numeric_stats": stats,
        "monotonicity_violations": monotonicity_violations,
        "tbase_boundary": {
            "cases": boundary_cases,
            "wheat_below_tbase_stalled": wheat_below_tbase_stalled,
        },
        "counts": {
            "normal_combinations": len(rows) - stall_expected,
            "stall_expected": stall_expected,
            "stall_correct": stall_correct,
            "stall_wrong": stall_wrong,
            "mismatched_stage_values": mismatched,
            "negative_days": neg_days,
            "monotonicity_violations": len(monotonicity_violations),
        },
        "acceptance": acceptance,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="S2-A1 物候一致性交叉验证")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    p.add_argument("--strict", action="store_true", help="任一验收不通过即 exit 1")
    args = p.parse_args(argv)

    report = build_report()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    acc = report["acceptance"]
    st = report["numeric_stats"]
    c = report["counts"]
    print("=== S2-A1 物候一致性交叉验证 ===")
    print(f"范围: {report['scope']}")
    print(f"正常路径 n={c['normal_combinations']}，停滞路径 n={c['stall_expected']}")
    print()
    print(f"emergence:  RMSE={st['emergence']['rmse_days']}d  "
          f"MAE={st['emergence']['mae_days']}d  CCC={st['emergence']['ccc']}")
    print(f"anthesis:   RMSE={st['anthesis']['rmse_days']}d  "
          f"MAE={st['anthesis']['mae_days']}d  CCC={st['anthesis']['ccc']}")
    print(f"maturity:   RMSE={st['maturity']['rmse_days']}d  "
          f"MAE={st['maturity']['mae_days']}d  CCC={st['maturity']['ccc']}")
    print()
    print("验收（全部 True 即通过）：")
    for k, v in acc.items():
        # 浮点数型指标（overall_rmse_days / negative_days_count）单独显示数值
        if isinstance(v, bool):
            mark = "✅" if v else "❌"
            print(f"  {mark} {k}: {v}")
        else:
            print(f"     {k}: {v}")
    print()
    print(f"停滞契约: {c['stall_correct']}/{c['stall_expected']} 正确（错误 {c['stall_wrong']}）")
    print(f"负天数: {c['negative_days']}")
    print(f"单调性违反: {c['monotonicity_violations']}")
    print(f"TSUM 漂移: {len(report['tsum_parameter_drift_check']['mismatched'])}")
    print(f"wheat_below_tbase_stalled: "
          f"{report['tbase_boundary']['wheat_below_tbase_stalled']['verdict']} "
          f"(got emergence_days={report['tbase_boundary']['wheat_below_tbase_stalled']['got_emergence_days']})")

    if args.strict and not acc["all_pass"]:
        print("\n❌ --strict 未通过")
        return 1
    if args.json:
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print(f"\n已写入 {os.path.relpath(OUT_PATH, ROOT)}")
    return 0 if acc["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
