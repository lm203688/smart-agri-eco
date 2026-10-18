#!/usr/bin/env python3
"""AgriRecipeBench 统计纪律报告（S1.3）—— 治"648 次恒 1.0"

问题：results_history.json 里 pass_rate 恒为 1.0，无统计波动 → "通过率"作为
指标在统计上无意义（一个回归测试套件全绿，不等于"92% 准确"）。审稿人必问。

本脚本给两份证据，不掩盖、也不美化：
  1. 历史分析：对 results_history.json 全部条目做 mean±std/n 统计，并给出
     时间趋势（OLS 斜率 + Pearson r），检测性能漂移。
  2. 多种子重复实验：现场跑 N 次不同随机划分的 Bench，报告每个指标的
     mean ± std。其中
       - pass_rate        → 预期 std=0（用例全通过，是回归套件不是统计实验）
       - conformal_coverage / mean_abs_dev → 随子集组成真实波动（有效统计内容）

输出：benchmarks/results/stat_summary.json（论文 Table 1 的数据源）

用法：
    python benchmarks/agri_recipe_bench/stat_report.py
    python benchmarks/agri_recipe_bench/stat_report.py --repeats 5 --seed 20241018 --fraction 0.8 --json

诚实边界（写进报告，不藏）：
  - 测试集是固定的、确定性的；pass_rate 无方差是**事实**，不是 bug。
    论文必须把"回归全绿"与"预测精度"分开陈述。
  - 真正有方差的是 conformal_coverage 与 mean_abs_dev；论文报 mean±std 时应引用这两者。
  - fraction<1.0 会改变 conformal 校准集组成，因而改变 q 与覆盖率 —— 这是
    **子集效应**，不是模型不确定性；报告中已标注。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HISTORY_PATH = os.path.join(HERE, "results_history.json")
OUT_DIR = os.path.join(ROOT, "benchmarks", "results")
OUT_PATH = os.path.join(OUT_DIR, "stat_summary.json")

# 供 run_bench.py --repeats 复用
import run_bench  # noqa: E402

# ---------------------------------------------------------------------------
# 复用的过滤 / 抽样（run_bench.py --repeats 与 stat_report 共用同一套判据）
# ---------------------------------------------------------------------------
def filter_cases(cases: List[Dict[str, Any]], axis: str = "all",
                 case_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """按轴 / 用例 id 过滤 —— 委托给 run_bench._filter_cases（单一判据源）。

    保留本函数仅为外部调用便利；实现不在这里，避免两处判据漂移。
    """
    return run_bench._filter_cases(cases, axis, case_id)


def sample_cases(cases: List[Dict[str, Any]], seed: int,
                 fraction: float = 1.0) -> List[Dict[str, Any]]:
    """按 fraction 抽不重复子集。fraction=1.0（或 ≥1）→ 原顺序返回，确定性。

    种子决定子集构成，因此每次重复的 conformal 校准集 / 预测子集都不同 ——
    这是"多种子实验"产生真实波动的唯一来源（模型本身确定性）。
    """
    if fraction is None or fraction >= 1.0:
        return list(cases)
    if fraction <= 0.0:
        return []
    rng = random.Random(seed)
    k = max(1, int(round(len(cases) * fraction)))
    if k >= len(cases):
        return list(cases)
    return rng.sample(cases, k)


# ---------------------------------------------------------------------------
# 统计工具（标准库，零依赖）
# ---------------------------------------------------------------------------
def mean(vals: List[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def std(vals: List[float]) -> Optional[float]:
    """样本标准差（ddof=1）。n<2 返回 None（无法估计）。"""
    n = len(vals)
    if n < 2:
        return None
    m = sum(vals) / n
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))


def mean_std_n(vals: List[float]) -> Dict[str, Any]:
    return {
        "mean": round(mean(vals), 4) if vals else None,
        "std": round(std(vals), 4) if std(vals) is not None else None,
        "n": len(vals),
    }


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    mx, my = sum(xs[:n]) / n, sum(ys[:n]) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs[:n], ys[:n]))
    sxx = sum((x - mx) ** 2 for x in xs[:n])
    syy = sum((y - my) ** 2 for y in ys[:n])
    if sxx <= 0 or syy <= 0:
        return None
    return round(sxy / math.sqrt(sxx * syy), 4)


def ols_slope(xs: List[float], ys: List[float]) -> Optional[float]:
    """简单线性回归斜率；自变量全同（方差 0）时返回 None（不可估）。"""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    mx, my = sum(xs[:n]) / n, sum(ys[:n]) / n
    sxx = sum((x - mx) ** 2 for x in xs[:n])
    if sxx <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs[:n], ys[:n])) / sxx


def _fmt(m: Dict[str, Any]) -> str:
    if not m.get("n"):
        return "n=0"
    if m.get("std") is None:
        return f"{m['mean']} ± n/a (n={m['n']})"
    return f"{m['mean']} ± {m['std']} (n={m['n']})"


# ---------------------------------------------------------------------------
# 1) 历史分析
# ---------------------------------------------------------------------------
def analyze_history(path: str = HISTORY_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"enabled": False, "reason": f"历史文件不存在：{path}"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception as e:  # noqa: BLE001
        return {"enabled": False, "reason": f"历史文件解析失败：{e}"}
    if not isinstance(entries, list):
        return {"enabled": False, "reason": "历史文件不是 list"}

    pass_rates = [e["pass_rate"] for e in entries
                  if isinstance(e.get("pass_rate"), (int, float))]
    covs = [e["conformal_coverage"] for e in entries
            if isinstance(e.get("conformal_coverage"), (int, float))]

    # 按 total（用例总数）分段：用例集扩容后，不同段不可混算
    by_total: Dict[int, Dict[str, Any]] = {}
    for e in entries:
        t = e.get("total")
        if not isinstance(t, int):
            continue
        by_total.setdefault(t, {"n": 0, "pass_rates": [], "covs": []})
        by_total[t]["n"] += 1
        if isinstance(e.get("pass_rate"), (int, float)):
            by_total[t]["pass_rates"].append(e["pass_rate"])
        if isinstance(e.get("conformal_coverage"), (int, float)):
            by_total[t]["covs"].append(e["conformal_coverage"])

    # 按轴统计 pass_rate 分布
    per_axis: Dict[str, List[float]] = {}
    for e in entries:
        for axis, v in (e.get("by_axis") or {}).items():
            if isinstance(v, dict) and v.get("total"):
                pr = v["passed"] / v["total"]
                per_axis.setdefault(axis, []).append(pr)

    # 时间趋势：以条目序号为自变量（历史文件按追加顺序，非严格等间隔）
    xs = list(range(len(pass_rates)))
    slope = ols_slope(xs, pass_rates)
    r = pearson(xs, pass_rates)

    return {
        "enabled": True,
        "file": os.path.relpath(path, ROOT),
        "entries": len(entries),
        "date_span": {
            "first": entries[0].get("timestamp") if entries else None,
            "last": entries[-1].get("timestamp") if entries else None,
        },
        "pass_rate": mean_std_n(pass_rates),
        "conformal_coverage": mean_std_n(covs),
        "by_total": {str(k): {"n": v["n"],
                              "pass_rate": mean_std_n(v["pass_rates"]),
                              "conformal_coverage": mean_std_n(v["covs"])}
                     for k, v in sorted(by_total.items())},
        "by_axis": {a: mean_std_n(vs) for a, vs in sorted(per_axis.items())},
        "trend": {"method": "ols_on_entry_index", "slope": slope, "pearson_r": r},
    }


# ---------------------------------------------------------------------------
# 2) 多种子重复实验
# ---------------------------------------------------------------------------
def _mean_abs_dev(results: List[Dict[str, Any]]) -> Optional[float]:
    """预测类指标的 |相对偏差| 均值 —— 真正的"精度"指标（非 pass/fail）。"""
    devs: List[float] = []
    for r in results:
        if r.get("axis") != "target_prediction":
            continue
        for spec in (r.get("checks") or {}).values():
            if isinstance(spec, dict) and isinstance(spec.get("dev"), (int, float)):
                devs.append(abs(float(spec["dev"])))
    return mean(devs) if devs else None


def repeat_experiment(n_repeats: int, seed: int, fraction: float = 1.0,
                      cases: Optional[List[Dict[str, Any]]] = None
                      ) -> Dict[str, Any]:
    """N 次随机抽样运行，报告每个指标的 mean ± std。

    fraction<1.0 时每次抽不重复子集（seed=seed+r）—— 子集组成变化会带来
    **真实波动**（conformal 校准集组成 → q → 覆盖率；预测子集 → 精度）。
    fraction=1.0 时确定性，pass_rate/conformal 均无方差，如实报告。
    """
    if cases is None:
        cases = run_bench.load_cases()
    runs: List[Dict[str, Any]] = []
    metrics: Dict[str, List[float]] = {
        "pass_rate": [], "conformal_coverage": [], "mean_abs_dev": [],
        "n_cases": [], "negative_passed": [],
    }

    for rep in range(n_repeats):
        sampled = sample_cases(cases, seed + rep, fraction)

        results: List[Dict[str, Any]] = []
        for c in sampled:
            try:
                results.append(run_bench.run_case(c))
            except Exception as e:  # noqa: BLE001
                results.append({"case_id": c.get("id"), "axis": c.get("axis"),
                                "ok": False, "error": str(e)})

        summary = run_bench.summarize(results)
        cc = run_bench._compute_conformal_coverage(results)
        dev = _mean_abs_dev(results)

        runs.append({
            "repeat": rep + 1,
            "seed": seed + rep,
            "n_cases": summary["total"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "pass_rate": summary["pass_rate"],
            "conformal_coverage": cc.get("coverage"),
            "conformal_quantile": cc.get("quantile_q"),
            "mean_abs_dev": dev,
        })

        metrics["pass_rate"].append(float(summary["pass_rate"]))
        metrics["n_cases"].append(float(summary["total"]))
        if isinstance(cc.get("coverage"), (int, float)):
            metrics["conformal_coverage"].append(float(cc["coverage"]))
        if dev is not None:
            metrics["mean_abs_dev"].append(float(dev))
        neg = summary.get("negative", {})
        metrics["negative_passed"].append(float(neg.get("passed", 0)))

    return {
        "n_repeats": n_repeats,
        "seed": seed,
        "fraction": fraction,
        "metrics": {k: mean_std_n(v) for k, v in metrics.items()},
        "runs": runs,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_report(n_repeats: int, seed: int, fraction: float) -> Dict[str, Any]:
    hist = analyze_history()
    rep = repeat_experiment(n_repeats, seed, fraction)

    # 诚实判定：哪些指标有方差、哪些没有，直接写进报告供论文引用
    pr = rep["metrics"]["pass_rate"]
    cov = rep["metrics"]["conformal_coverage"]
    dev = rep["metrics"]["mean_abs_dev"]
    verdict = {
        "pass_rate_varies": bool(pr.get("std") not in (None, 0.0)),
        "conformal_coverage_varies": bool(cov.get("std") not in (None, 0.0)),
        "mean_abs_dev_varies": bool(dev.get("std") not in (None, 0.0)),
        "statement": (
            "pass_rate 为回归判定（全用例通过即 1.0），在测试集固定时为确定性指标，"
            "无方差是事实而非缺陷；论文不得把 pass_rate=1.0 表述为预测精度。"
            "应引用 mean_abs_dev（预测相对偏差均值）与 conformal_coverage（保形覆盖率）"
            "的 mean±std 作为带不确定度的效果指标。"
        ),
    }

    return {
        "generated_by": "benchmarks/agri_recipe_bench/stat_report.py",
        "roadmap_task": "S1.3",
        "history": hist,
        "repeat_experiment": rep,
        "verdict": verdict,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="AgriRecipeBench 统计纪律报告（S1.3）")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--seed", type=int, default=20241018)
    p.add_argument("--fraction", type=float, default=0.8,
                   help="每次重复抽取的用例比例（<1 才有子集波动）")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    report = build_report(args.repeats, args.seed, args.fraction)

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    h = report["history"]
    if h.get("enabled"):
        print(f"=== 历史分析：{h['entries']} 条记录 "
              f"({h['date_span']['first']} → {h['date_span']['last']}) ===")
        print(f"  pass_rate          : {_fmt(h['pass_rate'])}")
        print(f"  conformal_coverage : {_fmt(h['conformal_coverage'])}")
        print(f"  趋势 OLS slope={h['trend']['slope']}  pearson_r={h['trend']['pearson_r']}")
    else:
        print(f"⏭ 历史分析：{h.get('reason')}")

    rep = report["repeat_experiment"]
    print(f"\n=== 多种子重复实验：{rep['n_repeats']} 次，seed={rep['seed']}，"
          f"fraction={rep['fraction']} ===")
    for k, v in rep["metrics"].items():
        print(f"  {k:<20} : {_fmt(v)}")

    v = report["verdict"]
    print(f"\n诚实判定：pass_rate 有方差={v['pass_rate_varies']} · "
          f"conformal_coverage 有方差={v['conformal_coverage_varies']} · "
          f"mean_abs_dev 有方差={v['mean_abs_dev_varies']}")

    if args.json:
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2, default=str))

    print(f"\n已写入 {os.path.relpath(OUT_PATH, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
