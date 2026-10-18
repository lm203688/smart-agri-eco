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

from agent.conformal import SplitConformal, relative_residue

from agent.forecast_agent import ForecastAgent  # noqa: E402
from core.clock import CLOCK  # noqa: E402

CASES_DIR = os.path.join(HERE, "cases")
NEG_CASES_DIR = os.path.join(HERE, "cases", "neg")
NEG_RUNNER_PATH = os.path.join(HERE, "negative_runner.py")
HISTORY_PATH = os.path.join(HERE, "results_history.json")
LEADERBOARD_PATH = os.path.join(HERE, "leaderboard.html")


def _record_to_leaderboard(summary: Dict[str, Any],
                          results: List[Dict[str, Any]],
                          args) -> None:
    """M15-B3 leaderboard：每次 run_bench 后追加一行到 results_history.json 并渲染 leaderboard.html。

    设计要点（诚实性优先）：
      1. **每次运行都记**——无论通过与否。"不允许退步"必须可视化。
      2. **保留失败记录**——即使 pass_rate < 1.0 也入库，让"被棘轮拒绝的退步"可查。
      3. **零依赖 HTML**——纯字符串模板，无 CDN、无第三方 JS，本地可打开。
      4. **不删历史**——只追加，形成单调递增的时间序列。
    """
    import subprocess as _sp
    commit = ""
    try:
        commit = _sp.check_output(["git", "rev-parse", "--short", "HEAD"],
                                  cwd=ROOT, stderr=_sp.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        pass

    entry = {
        "timestamp": summary.get("generated_at"),
        "commit": commit or "unknown",
        "total": summary.get("total"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "pass_rate": summary.get("pass_rate"),
        "by_axis": summary.get("by_axis", {}),
        "conformal_coverage": (summary.get("conformal_coverage", {}) or {}).get("coverage"),
        "conformal_guarantee": (summary.get("conformal_coverage", {}) or {}).get("coverage_guarantee"),
        "axis": args.axis if args.axis != "all" else "all",
        "case": args.case or "all",
        "failed_cases": [r.get("case_id") for r in results if not r.get("ok")],
    }

    # 1) 追加到 results_history.json
    history: List[Dict[str, Any]] = []
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
            if not isinstance(history, list):
                history = []
        except Exception:  # noqa: BLE001
            history = []
    history.append(entry)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 2) 渲染 leaderboard.html（最近 50 条，倒序）
    _render_leaderboard_html(history[-50:][::-1])


def _render_leaderboard_html(entries: List[Dict[str, Any]]) -> None:
    """零依赖 HTML 渲染：把 leaderboard 记录渲成静态页（倒序，最新在上）。"""
    if not entries:
        return
    total_rows = len(entries)
    peak_rate = max(e.get("pass_rate", 0) for e in entries)
    latest = entries[0]

    rows = []
    for i, e in enumerate(entries):
        rate = e.get("pass_rate", 0) or 0
        bar_width = int(rate * 100)
        color = "#4ade80" if rate >= 1.0 else ("#fbbf24" if rate >= 0.7 else "#f87171")
        failed_str = ", ".join(e.get("failed_cases", []))[:120] if e.get("failed_cases") else "—"
        cov = e.get("conformal_coverage")
        cov_str = f"{cov*100:.1f}%" if cov is not None else "—"
        rows.append(
            f'<tr>'
            f'<td>{total_rows - i}</td>'
            f'<td>{e.get("timestamp", "")}</td>'
            f'<td><code>{e.get("commit", "")}</code></td>'
            f'<td>{e.get("passed", 0)}/{e.get("total", 0)}</td>'
            f'<td>'
            f'<div style="background:#1e293b;border-radius:4px;height:14px;overflow:hidden">'
            f'<div style="background:{color};width:{bar_width}%;height:100%"></div>'
            f'</div>'
            f'<span style="font-size:0.85em;color:{color}">{rate*100:.1f}%</span>'
            f'</td>'
            f'<td>{cov_str}</td>'
            f'<td style="max-width:280px;font-size:0.8em;color:#94a3b8">{failed_str}</td>'
            f'</tr>'
        )

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>AgriRecipeBench · Leaderboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
          background:#0f172a; color:#e2e8f0; padding:32px; }}
  h1 {{ font-size:1.6em; margin-bottom:8px; }}
  .subtitle {{ color:#94a3b8; margin-bottom:24px; font-size:0.95em; }}
  .stats {{ display:flex; gap:24px; margin-bottom:24px; flex-wrap:wrap; }}
  .stat {{ background:#1e293b; padding:16px 24px; border-radius:8px; min-width:180px; }}
  .stat .num {{ font-size:2em; font-weight:700; color:#4ade80; }}
  .stat .lbl {{ font-size:0.85em; color:#94a3b8; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:0.9em;
           background:#1e293b; border-radius:8px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #334155; }}
  th {{ background:#334155; font-weight:600; color:#f1f5f9; }}
  tr:hover {{ background:#253048; }}
  code {{ background:#0f172a; padding:2px 6px; border-radius:3px; font-size:0.85em; }}
  footer {{ margin-top:24px; color:#64748b; font-size:0.85em; text-align:center; }}
</style>
</head>
<body>
<h1>AgriRecipeBench · 历史分数曲线</h1>
<div class="subtitle">SNWM 四轴协议裁剪 · 零依赖 · 公开可复现 · 每次运行自动入库（含被棘轮拒绝的退步）</div>

<div class="stats">
  <div class="stat"><div class="num">{latest.get("pass_rate", 0)*100:.1f}%</div><div class="lbl">最新通过率</div></div>
  <div class="stat"><div class="num">{peak_rate*100:.1f}%</div><div class="lbl">历史峰值</div></div>
  <div class="stat"><div class="num">{len(entries)}</div><div class="lbl">历史记录</div></div>
  <div class="stat"><div class="num">{latest.get("total", 0)}</div><div class="lbl">当前用例数</div></div>
  <div class="stat"><div class="num">{latest.get("conformal_coverage", 0)*100:.1f}%</div><div class="lbl">保形覆盖率 (M15-B4)</div></div>
</div>

<table>
<thead><tr><th>#</th><th>时间</th><th>commit</th><th>通过</th><th>通过率</th><th>保形覆盖率</th><th>失败用例</th></tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>

<footer>
生成于 {latest.get("timestamp", "")} · commit {latest.get("commit", "unknown")} · 
数据源: results_history.json · 判定依据: benchmarks/agri_recipe_bench/
</footer>
</body>
</html>
'''
    with open(LEADERBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)


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

def load_cases(include_negative: bool = True) -> List[Dict[str, Any]]:
    """扫描 cases/ 下所有 JSON，返回按 id 排序的用例列表。

    S1.2：cases/neg/ 下的负例骨架（case_type=negative）一并纳入，
    由 run_case 分派给 negative_runner 的真实校验器。
    """
    if not os.path.isdir(CASES_DIR):
        raise FileNotFoundError(f"cases 目录不存在: {CASES_DIR}")
    out = []
    dirs = [CASES_DIR]
    if include_negative and os.path.isdir(NEG_CASES_DIR):
        dirs.append(NEG_CASES_DIR)
    for base in dirs:
        for name in sorted(os.listdir(base)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(base, name)
            with open(path, "r", encoding="utf-8") as f:
                c = json.load(f)
            # 必填字段校验（负例同样具备 id/axis/input，只是无 expected 数值期望）
            for k in ("id", "axis", "input"):
                if k not in c:
                    raise ValueError(f"{name}: 缺 {k}")
            out.append(c)
    return out


# ---------- S1.2 负例（case_type=negative）真实校验器接入 ----------

def _import_negative_runner():
    """延迟导入 negative_runner（其拉入 engine.agriworld_lite，避免拖慢 bench 启动）。

    benchmarks/ 无 __init__.py，直接按文件路径装载最稳。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("agri_bench_negative_runner", NEG_RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def run_negative_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """负例执行：按 axis/expect_failure_type 分派到真实校验器（不得用桩函数）。"""
    runner = _import_negative_runner()
    r = runner.run_negative_case(case)
    return {
        "case_id": case["id"],
        "axis": case.get("axis"),
        "ok": bool(r.get("ok")),
        "detail": r.get("detail", ""),
        "checks": {"verdict": {"ok": bool(r.get("ok")), "detail": r.get("detail", "")}},
        "expect_failure_type": case.get("expect_failure_type"),
    }


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


def _run_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    """统一调用 ForecastAgent，返回 result 字典。"""
    payload = _normalize_input(dict(payload))
    agent = ForecastAgent()
    return agent.estimate(
        crop=payload.get("crop", ""),
        zone_id=payload.get("zone_id", ""),
        start_date=payload.get("start_date", ""),
        growth_plan=payload.get("growth_plan"),
        zone_climate=payload.get("zone_climate"),
        env_recipe=payload.get("env_recipe"),
        adapt_score=payload.get("adapt_score"),
    )


def run_counterfactual(case: Dict[str, Any]) -> Dict[str, Any]:
    """M3 · 反事实响应（Counterfactual）：扰动输入，检查产出变化方向。

    用例结构：
        input: 基准场景
        perturbation: {field: {before, after}}  -- 要扰动的字段与前后值
        expected:
            counterfactual:
              metric: {direction: "increase"|"decrease"|"change", min_delta_pct: 0.1}

    判据：产出指标必须按 expected.direction 变化，且相对变化 >= min_delta_pct。
    这是「机制内核响应合理性」的直接证据——若温度升高产量反而下降，就是缺陷。
    """
    base_payload = dict(case["input"])
    try:
        base_result = _run_agent(base_payload)
    except Exception as e:
        return {"ok": False, "error": f"基准场景失败: {e}"}

    perturbed_payload = dict(base_payload)
    perturb = case.get("perturbation", {})
    for field, vals in perturb.items():
        perturbed_payload[field] = vals.get("after", vals)

    try:
        perturbed_result = _run_agent(perturbed_payload)
    except Exception as e:
        return {"ok": False, "error": f"扰动场景失败: {e}"}

    base_rec = base_result.get("recommendation", {})
    perturbed_rec = perturbed_result.get("recommendation", {})
    checks = case.get("expected", {}).get("counterfactual", {})

    per_metric = {}
    all_ok = True
    for metric, spec in checks.items():
        v_before = base_rec.get(metric)
        v_after = perturbed_rec.get(metric)
        if v_before is None or v_after is None:
            per_metric[metric] = {"ok": False, "detail": f"指标 {metric} 缺失"}
            all_ok = False
            continue
        try:
            vb, va = float(v_before), float(v_after)
        except (TypeError, ValueError):
            per_metric[metric] = {"ok": False, "detail": f"非数值: {metric}"}
            all_ok = False
            continue

        direction = spec.get("direction", "change")
        min_delta_pct = float(spec.get("min_delta_pct", 0.0))
        if vb == 0:
            delta_pct = 0.0 if va == 0 else 1.0
        else:
            delta_pct = (va - vb) / abs(vb)

        if direction == "increase":
            ok = delta_pct >= min_delta_pct
        elif direction == "decrease":
            ok = delta_pct <= -min_delta_pct
        else:  # "change"
            ok = abs(delta_pct) >= min_delta_pct

        per_metric[metric] = {
            "ok": ok, "before": vb, "after": va,
            "delta_pct": round(delta_pct, 4),
            "expected_direction": direction,
            "min_delta_pct": min_delta_pct,
        }
        if not ok:
            all_ok = False

    return {"ok": all_ok, "checks": per_metric,
            "base_output": base_rec, "perturbed_output": perturbed_rec,
            "perturbation": perturb,
            "confidence_base": base_result.get("confidence"),
            "confidence_perturbed": perturbed_result.get("confidence")}


def run_generalization(case: Dict[str, Any]) -> Dict[str, Any]:
    """M4 · 跨情境泛化（Cross-context Generalization）：同作物跨多分区，检查输出合理性。

    用例结构：
        input:
            crop: 固定作物
            zones: [{zone_id, start_date, adapt_score, growth_plan?}, ...]
        expected:
            generalization:
                all_valid: true  -- 所有分区都产出合法结果
                outputs_vary: true  -- 不同分区输出不完全相同（非退化解）
                metric_bounds: {yield_estimate_g: {min: 50, max: 5000}, ...}

    判据：
        1. 每个分区都能产出合法结果（yield>0, duration>=1）
        2. 输出不完全相同（避免"无视分区永远给同答案"的退化实现）
        3. 所有输出都落在合理范围内（min/max 由农艺常识锚定）
    """
    inp = case.get("input", {})
    crop = inp.get("crop")
    zones = inp.get("zones", [])
    if not crop or not zones:
        return {"ok": False, "error": "M4 用例缺 crop 或 zones"}

    checks_spec = case.get("expected", {}).get("generalization", {})
    bounds = checks_spec.get("metric_bounds", {})
    expect_valid = checks_spec.get("all_valid", True)
    expect_vary = checks_spec.get("outputs_vary", True)

    runs = []
    all_ok = True
    for zi, zone_cfg in enumerate(zones):
        payload = {
            "crop": crop,
            "zone_id": zone_cfg.get("zone_id"),
            "start_date": zone_cfg.get("start_date", "2026-03-01"),
            "adapt_score": zone_cfg.get("adapt_score"),
            "growth_plan": zone_cfg.get("growth_plan"),
            "env_recipe_path": zone_cfg.get("env_recipe_path"),
        }
        try:
            result = _run_agent(payload)
            rec = result.get("recommendation", {})
        except Exception as e:
            runs.append({"zone_id": zone_cfg.get("zone_id"), "error": str(e)})
            all_ok = False
            continue

        run_out = {
            "zone_id": zone_cfg.get("zone_id"),
            "yield": rec.get("yield_estimate_g"),
            "duration": rec.get("adjusted_duration_days"),
            "harvest": rec.get("harvest_date"),
        }
        runs.append(run_out)

        # 合法性检查
        if expect_valid:
            y, d = run_out["yield"], run_out["duration"]
            if not (isinstance(y, (int, float)) and y > 0
                    and isinstance(d, (int, float)) and d >= 1):
                all_ok = False
                run_out["valid"] = False
            else:
                run_out["valid"] = True

        # 范围检查
        for metric_key, bound in bounds.items():
            val = rec.get(metric_key)
            if val is None:
                continue
            try:
                v = float(val)
            except (TypeError, ValueError):
                continue
            lo = float(bound.get("min", float("-inf")))
            hi = float(bound.get("max", float("inf")))
            if not (lo <= v <= hi):
                all_ok = False
                run_out.setdefault("bounds_violation", []).append(
                    f"{metric_key}={v} not in [{lo},{hi}]"
                )

    # 泛化性检查：不同分区输出必须不完全相同
    if expect_vary and len(runs) >= 2:
        yield_vals = [r.get("yield") for r in runs if isinstance(r.get("yield"), (int, float))]
        if len(yield_vals) < 2 or max(yield_vals) == min(yield_vals):
            all_ok = False
            return {"ok": False, "error": "跨分区产量完全相同——退化实现",
                    "runs": runs, "yield_values": yield_vals}

    return {"ok": all_ok, "runs": runs,
            "yield_values": [r.get("yield") for r in runs],
            "crop": crop, "n_zones": len(zones)}


AXIS_RUNNERS = {
    "target_prediction": run_target_prediction,
    "state_rolling": run_state_rolling,
    "counterfactual": run_counterfactual,
    "generalization": run_generalization,
}


# ---------- M15-B4 保形覆盖率指标 ----------

def _compute_conformal_coverage(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """M15-B4：跨 target_prediction 用例计算 Split Conformal 覆盖率。

    方法：
      1. 收集所有 target_prediction 用例的 (pred, expected) 对
      2. 用全部对构建 SplitConformal 校准器（full calibration）
      3. 对每个用例，检查 expected 是否落在 conformal 区间 [pred*(1-q), pred*(1+q)] 内
      4. 覆盖率 = 被区间覆盖的用例数 / 总用例数

    诚实边界：
      - full calibration 略乐观（测试点也在校准集中），G2 接入真实回流后
        可用 holdout 或 sliding window 提升严谨性
      - n<20 时 q 保守（偏宽），覆盖率可能高于 1-α
    """
    tp_results = [r for r in results if r.get("axis") == "target_prediction" and r.get("ok")]
    if not tp_results:
        return {"enabled": False, "reason": "无 target_prediction 用例", "coverage": None}

    # 收集 (pred, expected) 对
    pairs: List[Tuple[float, float]] = []
    case_details: List[Dict[str, Any]] = []
    for r in tp_results:
        checks = r.get("checks") or {}
        for metric, spec in checks.items():
            if not isinstance(spec, dict):
                continue
            pred = spec.get("pred")
            expected = spec.get("expected")
            if pred is None or expected is None:
                continue
            try:
                p, e = float(pred), float(expected)
            except (TypeError, ValueError):
                continue
            pairs.append((p, e))
            case_details.append({
                "case_id": r.get("case_id"),
                "metric": metric,
                "pred": p,
                "expected": e,
                "residue": relative_residue(p, e),
            })

    if not pairs:
        return {"enabled": False, "reason": "无有效 (pred, expected) 对", "coverage": None}

    # 构建校准器
    calibrator = SplitConformal(
        calibration_scores=[relative_residue(p, e) for p, e in pairs],
        alpha=0.10,  # 90% 覆盖率
    )
    q = calibrator.quantile()

    # 计算覆盖率
    covered = 0
    for d in case_details:
        pred, expected = d["pred"], d["expected"]
        if q is None:
            d["covered"] = False
            continue
        lower = pred * (1.0 - q)
        upper = pred * (1.0 + q)
        is_covered = lower <= expected <= upper
        d["covered"] = is_covered
        if is_covered:
            covered += 1

    coverage = covered / len(case_details) if case_details else 0.0

    return {
        "enabled": True,
        "method": "split_conformal",
        "alpha": 0.10,
        "coverage_guarantee": round(calibrator.coverage_guarantee(), 4),
        "calibration_n": calibrator.n,
        "quantile_q": round(q, 4) if q is not None else None,
        "total_metrics": len(case_details),
        "covered": covered,
        "coverage": round(coverage, 4),
        "above_guarantee": coverage >= calibrator.coverage_guarantee(),
        "details": case_details,
    }


# ---------- 主流程 ----------

def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    axis = case.get("axis")
    # S1.2：负例（negative_input_bounds / negative_honest_degradation /
    # negative_counterfactual_invariant / negative_trust_breakage）走真实校验器
    if case.get("case_type") == "negative" or str(axis or "").startswith("negative_"):
        return run_negative_case(case)
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

    # S1.2：把所有 negative_* 轴聚合成单一 "negative" 桶，供 --summary 输出
    # "negative: 20/20 passed"；同时保留细粒度轴便于 CI 分诊。
    neg_total = sum(v["total"] for k, v in by_axis.items() if k.startswith("negative_"))
    neg_passed = sum(v["passed"] for k, v in by_axis.items() if k.startswith("negative_"))

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "negative": {"total": neg_total, "passed": neg_passed, "failed": neg_total - neg_passed},
        "by_axis": {a: dict(v, pass_rate=round(v["passed"] / v["total"], 3) if v["total"] else 0)
                    for a, v in sorted(by_axis.items())},
        "generated_at": CLOCK.now().isoformat(timespec="seconds"),
    }


def _filter_cases(cases: List[Dict[str, Any]], axis: str = "all",
                  case_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """按轴 / 用例 id 过滤。negative 是 S1.2 四类负例的聚合别名。

    单一实现：stat_report.filter_cases 委托到本函数，避免判据漂移。
    """
    out = list(cases)
    if axis != "all":
        if axis == "negative":
            out = [c for c in out
                   if c.get("case_type") == "negative"
                   or str(c.get("axis") or "").startswith("negative_")]
        else:
            out = [c for c in out if c.get("axis") == axis]
    if case_id:
        out = [c for c in out if c.get("id") == case_id]
    return out


def _run_repeats(args) -> int:
    """S1.3：多次随机划分实验，报告每个指标 mean±std。

    与单次运行不同：本分支**不写 leaderboard / results_history.json** ——
    否则 N 次重复会向 M15-B3 历史序列注入抽样噪声，而那里要证明的恰恰是
    "方差为零"这一事实。统计判据（mean/std/抽样）复用 stat_report.py。
    """
    try:
        import stat_report  # 同目录；脚本模式下 HERE 在 sys.path[0]
    except ImportError:  # noqa: BLE001
        from benchmarks.agri_recipe_bench import stat_report  # type: ignore[no-redef]

    try:
        cases = _filter_cases(load_cases(), args.axis, args.case)
    except Exception as e:  # noqa: BLE001
        print(f"❌ 用例加载失败: {e}", file=sys.stderr)
        return 2
    if not cases:
        print("⏭ 无匹配用例")
        return 0

    rep = stat_report.repeat_experiment(args.repeats, args.seed, args.fraction, cases=cases)

    if args.json:
        print(json.dumps({"repeat_experiment": rep}, ensure_ascii=False, indent=2, default=str))
        return 0

    total_runs = sum(r["n_cases"] for r in rep["runs"])
    total_failed = sum(r["failed"] for r in rep["runs"])
    print(f"=== AgriRecipeBench 多种子实验（S1.3）：{rep['n_repeats']} 次重复，"
          f"seed={rep['seed']}，fraction={rep['fraction']}，共 {total_runs} 次运行 ===")
    for k, v in rep["metrics"].items():
        print(f"  {k:<20} : {stat_report._fmt(v)}")

    if total_failed:
        print(f"\n❌ 重复实验中 {total_failed} 个用例失败")
        return 1 if args.strict else 0
    print(f"\n✅ {total_runs} 次运行零失败")
    return 0


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="AgriRecipeBench runner")
    p.add_argument("--axis", choices=list(AXIS_RUNNERS) + ["negative", "all"], default="all",
                   help="仅跑某轴；negative = S1.2 负例四类聚合")
    p.add_argument("--case", help="仅跑指定 id")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--summary", action="store_true",
                   help="只输出聚合摘要（含 negative: X/Y passed），适合 CI")
    p.add_argument("--strict", action="store_true", help="失败即退出 1")
    # S1.3 统计纪律：多次随机划分实验，报告 mean±std（治"648 次恒 1.0"）
    p.add_argument("--repeats", type=int, default=1,
                   help="重复运行次数（S1.3）；>1 时每次随机抽样一次用例，报告 mean±std")
    p.add_argument("--seed", type=int, default=20241018,
                   help="随机种子基准（S1.3）；第 r 次重复用 seed+r，可完全复现")
    p.add_argument("--fraction", type=float, default=0.8,
                   help="每次重复抽取的用例比例（S1.3）；<1 才会产生子集波动")
    args = p.parse_args(argv)

    # S1.3：重复实验走独立分支（不写 leaderboard，避免污染 results_history.json）
    if args.repeats and args.repeats > 1:
        return _run_repeats(args)

    try:
        cases = load_cases()
    except Exception as e:
        print(f"❌ 用例加载失败: {e}", file=sys.stderr)
        return 2

    cases = _filter_cases(cases, args.axis, args.case)

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

    # M15-B4 保形覆盖率：跨 target_prediction 用例计算 conformal coverage
    try:
        summary["conformal_coverage"] = _compute_conformal_coverage(results)
    except Exception as e:  # noqa: BLE001
        summary["conformal_coverage"] = {"enabled": False, "error": str(e)}

    # M15-B3 公开 leaderboard：把本次结果追加到 results_history.json（含被棘轮拒绝的退步）
    # 与 leaderboard.html，让"不允许退步"可视化。写入失败不阻塞 benchmark 主流程。
    try:
        _record_to_leaderboard(summary, results, args)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ leaderboard 写入失败（不影响 bench 主流程）: {e}", file=sys.stderr)

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

        # M15-B4 保形覆盖率
        cc = summary.get("conformal_coverage", {})
        if cc.get("enabled"):
            cov = cc.get("coverage", 0)
            guarantee = cc.get("coverage_guarantee", 0)
            mark = "✅" if cc.get("above_guarantee") else "⚠️"
            print(f"  · conformal_coverage: {mark} {cc['covered']}/{cc['total_metrics']} "
                  f"(coverage={cov:.1%} guarantee≥{guarantee:.1%} q={cc.get('quantile_q')})")
        elif cc.get("reason"):
            print(f"  · conformal_coverage: ⏭ {cc['reason']}")

    # S1.2 / CI：--summary 输出紧凑聚合行，验收判据为 "negative: 20/20 passed"
    if args.summary:
        print(f"=== AgriRecipeBench summary @ {summary['generated_at']} ===")
        for axis, v in summary["by_axis"].items():
            print(f"  · {axis}: {v['passed']}/{v['total']} passed")
        neg = summary.get("negative", {})
        mark = "✅" if neg.get("failed", 0) == 0 else "❌"
        print(f"  · negative: {mark} {neg.get('passed', 0)}/{neg.get('total', 0)} passed")
        print(f"总计 {summary['passed']}/{summary['total']} 通过 "
              f"(pass_rate={summary['pass_rate']})")

    if summary["failed"] and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
