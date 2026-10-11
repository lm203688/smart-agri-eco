#!/usr/bin/env python3
"""AgriRecipeBench 评测 runner —— 零依赖，标准库 only。

用法：
    python benchmarks/agri_recipe_bench/run_bench.py                # 跑全部
    python benchmarks/agri_recipe_bench/run_bench.py --axis target_prediction
    python benchmarks/agri_recipe_bench/run_bench.py --case case_xxx
    python benchmarks/agri_recipe_bench/run_bench.py --json         # 输出机器可读
    python benchmarks/agri_recipe_bench/run_bench.py --strict       # 有失败即退出 1

退出码：
    0 = 全部通过（或 --strict 未开启）
    1 = 至少一个用例失败且 --strict
    2 = 用例加载失败 / 内部错误
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

# 让 runner 无论从何处调用都能 import 项目根下的 agent/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.forecast_agent import ForecastAgent  # noqa: E402

CASES_DIR = os.path.join(HERE, "cases")


# ---------- Env Recipe 加载 ----------

def _load_env_recipe_from_path(case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """用例里给的是 env_recipe_path（相对仓库根），这里读成 dict 后再喂给 Agent。

    返回 None 表示用例没要求 recipe（例如测试无 recipe 分支），或路径不存在。
    """
    path = case.get("input", {}).get("env_recipe_path")
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(ROOT, path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _normalize_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """把用例的 input 字典补齐：env_recipe_path → env_recipe 实际 dict。

    如果 payload 里已经显式给了 env_recipe（比如内联测试），则不覆盖。
    """
    out = dict(payload)
    if "env_recipe" not in out:
        # 用一个只带 path 的临时 case 结构走同一路径解析
        recipe = _load_env_recipe_from_path({"input": out})
        if recipe is not None:
            out["env_recipe"] = recipe
        # 顺带清掉路径字段，避免下游误读
        out.pop("env_recipe_path", None)
    return out


# ---------- 用例加载 ----------

def load_cases() -> List[Dict[str, Any]]:
    """扫描 cases/ 下所有 JSON，返回按 id 排序的用例列表。"""
    if not os.path.isdir(CASES_DIR):
        raise FileNotFoundError(f"cases 目录不存在: {CASES_DIR}")
    out = []
    for name in sorted(os.listdir(CASES_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CASES_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            c = json.load(f)
        # 必填字段校验
        for k in ("id", "axis", "input"):
            if k not in c:
                raise ValueError(f"{name}: 缺 {k}")
        out.append(c)
    return out


# ---------- 各轴的判定 ----------

def _in_tolerance(pred: float, spec: Dict[str, Any]) -> Tuple[bool, float, str]:
    """检查预测值是否落在 spec 定义的容差范围内。

    spec 支持两种口径：
        {"value": 250, "tolerance_abs": 80}    绝对容差
        {"value": 250, "tolerance_rel": 0.25}  相对容差（默认口径）
    """
    exp = float(spec["value"])
    if "tolerance_abs" in spec:
        tol = float(spec["tolerance_abs"])
    else:
        rel = float(spec.get("tolerance_rel", 0.25))
        tol = abs(exp) * rel
    dev = (pred - exp) / exp if exp else 0.0
    ok = abs(pred - exp) <= tol
    return ok, dev, f"pred={pred:.2f} exp={exp:.2f} tol=±{tol:.2f} dev={dev:+.1%}"


def run_target_prediction(case: Dict[str, Any]) -> Dict[str, Any]:
    """M1 · 目标预测：跑 ForecastAgent，检查产出 vs expected。"""
    payload = _normalize_input(dict(case["input"]))
    agent = ForecastAgent()
    try:
        result = agent.estimate(
            crop=payload.get("crop", ""),
            zone_id=payload.get("zone_id", ""),
            start_date=payload.get("start_date", ""),
            growth_plan=payload.get("growth_plan"),
            zone_climate=payload.get("zone_climate"),
            env_recipe=payload.get("env_recipe"),
            adapt_score=payload.get("adapt_score"),
        )
    except Exception as e:
        return {"ok": False, "error": f"ForecastAgent 抛错: {e}", "detail": {}}

    rec = result.get("recommendation", {})
    checks = case["expected"].get("target_prediction", {})
    per_metric = {}
    all_ok = True
    for metric, spec in checks.items():
        pred = rec.get(metric)
        if pred is None:
            per_metric[metric] = {"ok": False, "detail": f"ForecastAgent 未返回 {metric}"}
            all_ok = False
            continue
        try:
            ok, dev, detail = _in_tolerance(float(pred), spec)
        except (TypeError, ValueError) as e:
            per_metric[metric] = {"ok": False, "detail": f"无法数值化 pred={pred!r}: {e}"}
            all_ok = False
            continue
        per_metric[metric] = {"ok": ok, "pred": pred, "expected": spec.get("value"),
                              "dev": round(dev, 4), "detail": detail}
        if not ok:
            all_ok = False
    return {"ok": all_ok, "checks": per_metric, "agent_output": rec,
            "confidence": result.get("confidence"), "evidence": result.get("evidence")}


def run_state_rolling(case: Dict[str, Any]) -> Dict[str, Any]:
    """M2 · 状态滚动：只检查数学性质（不需要外部真值）。

    判据：
        1. adjusted_duration_days ≥ 1
        2. harvest_date ≥ start_date
        3. yield_estimate_g > 0
    """
    payload = _normalize_input(dict(case["input"]))
    agent = ForecastAgent()
    try:
        result = agent.estimate(
            crop=payload.get("crop", ""),
            zone_id=payload.get("zone_id", ""),
            start_date=payload.get("start_date", ""),
            growth_plan=payload.get("growth_plan"),
            zone_climate=payload.get("zone_climate"),
            env_recipe=payload.get("env_recipe"),
            adapt_score=payload.get("adapt_score"),
        )
    except Exception as e:
        return {"ok": False, "error": f"ForecastAgent 抛错: {e}"}

    rec = result.get("recommendation", {})
    checks = case["expected"].get("state_rolling", {})

    # 1. duration >= 1
    dur = rec.get("adjusted_duration_days")
    ok_dur = isinstance(dur, (int, float)) and dur >= 1

    # 2. harvest_date >= start_date
    harvest = rec.get("harvest_date")
    start = payload.get("start_date", "")
    ok_dates = False
    if isinstance(harvest, str) and isinstance(start, str) and len(harvest) >= 10 and len(start) >= 10:
        try:
            d_h = datetime.date.fromisoformat(harvest[:10])
            d_s = datetime.date.fromisoformat(start[:10])
            ok_dates = d_h >= d_s
        except ValueError:
            ok_dates = False

    # 3. yield > 0
    y = rec.get("yield_estimate_g")
    ok_yield = isinstance(y, (int, float)) and y > 0

    detail = {
        "adjusted_duration_days": {"pred": dur, "min_required": 1, "ok": ok_dur},
        "harvest_vs_start": {"harvest": harvest, "start": start, "ok": ok_dates},
        "yield_g": {"pred": y, "min_required": 0, "ok": ok_yield,
                    "note": "仅检查 > 0，非精度评价（精度由 M1 覆盖）"},
    }
    all_ok = ok_dur and ok_dates and ok_yield
    return {"ok": all_ok, "checks": detail, "agent_output": rec,
            "confidence": result.get("confidence"), "evidence": result.get("evidence")}


AXIS_RUNNERS = {
    "target_prediction": run_target_prediction,
    "state_rolling": run_state_rolling,
}


# ---------- 主流程 ----------

def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    axis = case.get("axis")
    runner = AXIS_RUNNERS.get(axis)
    if runner is None:
        return {"case_id": case["id"], "axis": axis, "ok": False,
                "error": f"axis={axis!r} 未实现（当前支持: {list(AXIS_RUNNERS)}）"}
    out = runner(case)
    out["case_id"] = case["id"]
    out["axis"] = axis
    return out


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("ok"))
    by_axis: Dict[str, Dict[str, int]] = {}
    for r in results:
        a = r.get("axis", "?")
        by_axis.setdefault(a, {"total": 0, "passed": 0})
        by_axis[a]["total"] += 1
        if r.get("ok"):
            by_axis[a]["passed"] += 1
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "by_axis": {a: dict(v, pass_rate=round(v["passed"] / v["total"], 3) if v["total"] else 0)
                    for a, v in sorted(by_axis.items())},
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="AgriRecipeBench runner")
    p.add_argument("--axis", choices=list(AXIS_RUNNERS) + ["all"], default="all")
    p.add_argument("--case", help="仅跑指定 id")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--strict", action="store_true", help="失败即退出 1")
    args = p.parse_args(argv)

    try:
        cases = load_cases()
    except Exception as e:
        print(f"❌ 用例加载失败: {e}", file=sys.stderr)
        return 2

    if args.axis != "all":
        cases = [c for c in cases if c.get("axis") == args.axis]
    if args.case:
        cases = [c for c in cases if c.get("id") == args.case]

    if not cases:
        print("⏭ 无匹配用例")
        return 0

    results = []
    for c in cases:
        try:
            r = run_case(c)
        except Exception as e:
            r = {"case_id": c["id"], "axis": c.get("axis"), "ok": False,
                 "error": f"内部错误: {e}\n{traceback.format_exc()}"}
        results.append(r)

    summary = summarize(results)

    if args.json:
        print(json.dumps({"summary": summary, "results": results},
                         ensure_ascii=False, indent=2, default=str))
    else:
        print(f"=== AgriRecipeBench @ {summary['generated_at']} ===")
        for r in results:
            mark = "✅" if r.get("ok") else "❌"
            err = r.get("error", "")
            print(f"  {mark} [{r.get('axis')}] {r.get('case_id')}")
            if err:
                print(f"      error: {err}")
            checks = r.get("checks") or {}
            for k, v in checks.items():
                if isinstance(v, dict) and "detail" in v:
                    print(f"      {k}: {'✅' if v.get('ok') else '❌'} {v['detail']}")
        print()
        print(f"总计 {summary['passed']}/{summary['total']} 通过 "
              f"(pass_rate={summary['pass_rate']})")
        for axis, v in summary["by_axis"].items():
            print(f"  · {axis}: {v['passed']}/{v['total']} ({v['pass_rate']})")

    if summary["failed"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
