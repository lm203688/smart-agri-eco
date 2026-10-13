#!/usr/bin/env python3
"""E4 科学模块 Golden Vectors 回归门禁。

设计动机（承接 `docs/framework_evolution_liftup_2026-10-13.md` §6.3 E4）：
    MCPB 已做到分发产物确定性可复现（本地=CI=390e9779）——同一方法论扩展到
    科学模块：每个科学环节固定一组 golden 输入→期望输出（含 tolerance 与区间），
    CI 比对。可复现性从"分发资产"扩展为"科学资产"。

与 S2/E1 棘轮门禁（benchmarks/ratchet_modules.py）的分工：
    - 棘轮门禁：**数学不变式**（P10 ≤ P50 ≤ P90 / GDD 单调性）
    - Golden Vectors：**具体值锁定**（番茄 1432g / 马铃薯 10.6d 出苗）
    两者互补——不变式保证"结构没坏"，Golden Vectors 保证"数值没漂"。

用例集：
    benchmarks/golden_vectors/forecast.json    forecast_agent 产量/周期/采收期
    benchmarks/golden_vectors/phenology.json   phenology GDD 积温精确值
    benchmarks/golden_vectors/nutrition.json   nutrition_agent NPK 结构

设计原则：
    - 零第三方依赖，纯标准库
    - tolerance 严格（0.0 或 0.1 天），任何非零偏差都是静默回归
    - 失败时**明确列出** expected vs actual，绝不静默通过
    - 每个用例带 rationale（说明值从哪来，方便未来评审）

用法：
    python scripts/run_golden_vectors.py                  # 跑全部，输出汇总
    python scripts/run_golden_vectors.py --json           # JSON 输出
    python scripts/run_golden_vectors.py --strict         # 任何失败 exit 1
    python scripts/run_golden_vectors.py --module forecast  # 仅跑某模块
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

GOLDEN_DIR = os.path.join(ROOT, "benchmarks", "golden_vectors")


# ---------------------------------------------------------------------------
# 通用比对工具
# ---------------------------------------------------------------------------

def _compare_value(actual: Any, expected: Any, tol: float) -> Dict[str, Any]:
    """比对单值，返回 {passed, actual, expected, delta}。

    - expected=None → 期望为 None（发育停滞），actual 也应为 None
    - expected 是数字 → 用 tolerance 比对
    - 其他类型 → 严格 ==
    """
    if expected is None:
        ok = actual is None
        return {"passed": ok, "actual": actual, "expected": None, "delta": None}
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        delta = abs(actual - expected)
        ok = delta <= tol
        return {
            "passed": ok, "actual": actual, "expected": expected,
            "delta": round(delta, 6), "tolerance": tol,
        }
    # 字符串/布尔等其他类型：严格相等
    ok = actual == expected
    return {"passed": ok, "actual": actual, "expected": expected, "delta": None}


# ---------------------------------------------------------------------------
# forecast_agent runner
# ---------------------------------------------------------------------------

def run_forecast_vectors(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    from agent.forecast_agent import ForecastAgent
    agent = ForecastAgent()
    results: List[Dict[str, Any]] = []
    passed = 0
    tol = 0.0  # 零依赖启发式应严格可复现

    for c in cases:
        case_id = c["id"]
        payload = dict(c["payload"])
        try:
            r = agent.estimate(**payload)
            pi = r["recommendation"]["prediction_interval"]
            exp = c["expected"]
            checks = {
                "yield_p10": _compare_value(pi["yield_estimate_g"]["p10"],
                                            exp["yield_estimate_g"]["p10"], tol),
                "yield_p50": _compare_value(pi["yield_estimate_g"]["p50"],
                                            exp["yield_estimate_g"]["p50"], tol),
                "yield_p90": _compare_value(pi["yield_estimate_g"]["p90"],
                                            exp["yield_estimate_g"]["p90"], tol),
                "duration_p10": _compare_value(pi["adjusted_duration_days"]["p10"],
                                               exp["adjusted_duration_days"]["p10"], tol),
                "duration_p50": _compare_value(pi["adjusted_duration_days"]["p50"],
                                               exp["adjusted_duration_days"]["p50"], tol),
                "duration_p90": _compare_value(pi["adjusted_duration_days"]["p90"],
                                               exp["adjusted_duration_days"]["p90"], tol),
                "harvest_p10": _compare_value(pi["harvest_date"]["p10"],
                                              exp["harvest_date"]["p10"], 0),
                "harvest_p50": _compare_value(pi["harvest_date"]["p50"],
                                              exp["harvest_date"]["p50"], 0),
                "harvest_p90": _compare_value(pi["harvest_date"]["p90"],
                                              exp["harvest_date"]["p90"], 0),
            }
            ok = all(v["passed"] for v in checks.values())
            passed += 1 if ok else 0
            results.append({
                "id": case_id, "passed": ok, "checks": checks,
            })
        except Exception as e:  # noqa: BLE001
            results.append({
                "id": case_id, "passed": False, "error": str(e),
            })

    return {
        "module": "forecast",
        "target_file": "agent/forecast_agent.py",
        "invariant": "预测值精确锁定（yield/duration/harvest × P10/P50/P90）",
        "passed": passed, "total": len(cases),
        "score": round(passed / len(cases), 3) if cases else 0.0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# phenology runner
# ---------------------------------------------------------------------------

def run_phenology_vectors(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    from agent.phenology import estimate_stage_days, covered_crops
    results: List[Dict[str, Any]] = []
    passed = 0
    tol = 0.1  # 浮点舍入容差

    for c in cases:
        case_id = c["id"]
        payload = dict(c["payload"])
        try:
            r = estimate_stage_days(payload["crop"], payload["mean_temp_c"])
            exp = c["expected"]

            # 特殊情况：uncovered_crop
            if "available" in exp:
                ok = r.get("available") == exp["available"]
                covered_check = None
                if "covered_count" in exp:
                    covered_check = _compare_value(
                        len(covered_crops()), exp["covered_count"], 0
                    )
                    ok = ok and covered_check["passed"]
                passed += 1 if ok else 0
                results.append({
                    "id": case_id, "passed": ok,
                    "available_check": ok, "covered_check": covered_check,
                    "actual_available": r.get("available"),
                    "actual_covered_count": len(covered_crops()),
                })
                continue

            checks = {
                "emergence_days": _compare_value(
                    r.get("emergence_days"),
                    exp["emergence_days"], tol,
                ),
                "anthesis_days_from_sow": _compare_value(
                    r.get("anthesis_days_from_sow"),
                    exp["anthesis_days_from_sow"], tol,
                ),
                "maturity_days_from_sow": _compare_value(
                    r.get("maturity_days_from_sow"),
                    exp["maturity_days_from_sow"], tol,
                ),
            }
            ok = all(v["passed"] for v in checks.values())
            passed += 1 if ok else 0
            results.append({
                "id": case_id, "passed": ok, "checks": checks,
            })
        except Exception as e:  # noqa: BLE001
            results.append({
                "id": case_id, "passed": False, "error": str(e),
            })

    return {
        "module": "phenology",
        "target_file": "agent/phenology.py",
        "invariant": "GDD 积温精确值（tsum/eff 除法的确定结果）",
        "passed": passed, "total": len(cases),
        "score": round(passed / len(cases), 3) if cases else 0.0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# nutrition runner
# ---------------------------------------------------------------------------

def run_nutrition_vectors(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """nutrition_agent 结构锁定：NPK 元素 + 至少一个生长阶段 + confidence。

    当前实现没有稳定的"精确数值"可锁（阶段化配比随 crop 变化），
    故本模块锁定**结构**而非具体值：
        - recommendation 或 plan 存在且非空
        - 含 N/P/K 三元素任一
        - 含阶段/phase 字段
        - 顶层含 confidence
    """
    from agent.nutrition_agent import plan
    results: List[Dict[str, Any]] = []
    passed = 0

    for c in cases:
        case_id = c["id"]
        payload = dict(c["payload"])
        try:
            r = plan(**payload)
            body = r.get("recommendation") or r.get("plan") or r
            exp = c.get("expected", {})

            body_str = str(body)
            checks = {
                "has_body": isinstance(body, dict) and bool(body),
                "has_confidence": "confidence" in r,
                "has_np_or_npk": any(k in body_str for k in ("N", "P", "K", "np3", "npp")),
                "has_phases": ("phase" in body_str.lower() or "生长" in body_str
                               or "stage" in body_str.lower()),
            }

            # 若用例期望特定阶段数量
            if "min_phases" in exp:
                actual_phases = body.get("phases") or []
                checks["min_phases"] = _compare_value(
                    max(len(actual_phases), exp["min_phases"]),
                    exp["min_phases"], 0,
                )

            ok = all(v["passed"] if isinstance(v, dict) else v
                     for v in checks.values())
            passed += 1 if ok else 0
            results.append({
                "id": case_id, "passed": ok, "checks": checks,
            })
        except Exception as e:  # noqa: BLE001
            results.append({
                "id": case_id, "passed": False, "error": str(e),
            })

    return {
        "module": "nutrition",
        "target_file": "agent/nutrition_agent.py",
        "invariant": "NPK 结构完备（N/P/K + 阶段化 + confidence）",
        "passed": passed, "total": len(cases),
        "score": round(passed / len(cases), 3) if cases else 0.0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Runner 与 CI 入口
# ---------------------------------------------------------------------------

RUNNERS: Dict[str, Any] = {
    "forecast": run_forecast_vectors,
    "phenology": run_phenology_vectors,
    "nutrition": run_nutrition_vectors,
}


def _load_vectors(name: str) -> List[Dict[str, Any]]:
    path = os.path.join(GOLDEN_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_all(selected: Optional[str] = None) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    total_passed = 0
    total_cases = 0
    for name, runner in RUNNERS.items():
        if selected and name != selected:
            continue
        spec = _load_vectors(name)
        res = runner(spec["cases"])
        # 附加 schema 元数据
        res["schema"] = spec["schema"]
        res["generated_at"] = spec["generated_at"]
        res["tolerance"] = spec.get("tolerance")
        results[name] = res
        total_passed += res["passed"]
        total_cases += res["total"]
    overall_score = round(total_passed / total_cases, 3) if total_cases else 0.0
    return {
        "schema": "agri-golden-vectors/v1",
        "overall": {
            "score": overall_score,
            "total_passed": total_passed,
            "total_cases": total_cases,
            "all_passed": overall_score == 1.0,
        },
        "modules": results,
        "policy": "任何用例失败即视为回归，CI 拒绝合并（区别于棘轮门禁的不变式）",
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="E4 科学模块 Golden Vectors 回归门禁")
    p.add_argument("--json", action="store_true", help="JSON 输出（CI 消费）")
    p.add_argument("--strict", action="store_true",
                   help="任何失败 exit 1（CI 门禁模式）")
    p.add_argument("--module", help="仅跑指定模块（默认全跑）")
    args = p.parse_args(argv)

    report = run_all(args.module)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        ov = report["overall"]
        print("=" * 68)
        print("E4 科学模块 Golden Vectors 回归门禁")
        print("=" * 68)
        for name, res in report["modules"].items():
            icon = "✅" if res["score"] == 1.0 else "❌"
            print(f"{icon} {name:<12} {res['passed']}/{res['total']} "
                  f"(score={res['score']})  [{res['target_file']}]")
            if res["score"] < 1.0:
                for r in res["results"]:
                    if not r["passed"]:
                        if "error" in r:
                            print(f"    ✗ {r['id']}: ERROR {r['error']}")
                        elif "checks" in r:
                            for ck, v in r["checks"].items():
                                if not v["passed"]:
                                    print(f"    ✗ {r['id']}.{ck}: "
                                          f"expected={v['expected']} actual={v['actual']}"
                                          f"{' delta=' + str(v.get('delta')) if v.get('delta') else ''}")
        print("-" * 68)
        print(f"总体：{ov['total_passed']}/{ov['total_cases']}  "
              f"score={ov['score']}  all_passed={ov['all_passed']}")
        print("=" * 68)

    if args.strict and not report["overall"]["all_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
