#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_wofost_crossval.py —— S2-A1 物候交叉验证交付脚本（SCI 报告 P0）

用途
----
按 `docs/SCI_READINESS_2026-10-19.md` §5 P0「跑 G2 交叉验证」的验收：
  * 交付脚本路径：scripts/run_wofost_crossval.py
  * 输出：stat_summary.json 中含 `rmse / mae / ccc` 与 WOFOST 对比的 35 组结果

本脚本是 S2-A1（`scripts/s2_a1_phenology_consistency.py`）的**交付入口 + 合并器**：
  1. 调用 s2_a1.build_report() 现场复算 35 组 (crop, T) 物候结果；
  2. 将其 `numeric_stats / grid_results / acceptance` 抽出，合并进
     `benchmarks/results/stat_summary.json` 的顶层 `wofost_crossval` 字段；
  3. 打印一段面向审稿人的短表（35 组 / RMSE / MAE / CCC / 边界 / 停滞）。

为何不重复实现
--------------
S2-A1 已经完成 35 组网格扫描、TBASE 边界、停滞契约、单调性、TSUM 漂移
5 项验收，且 `--strict` 可作 CI 硬门禁。本脚本只做「调 S2-A1 + 合入 stat_summary」，
避免两处公式漂移。这与项目的**口径唯一原则**（CORE_OBJECTIVE §八）一致。

诚实边界（写入 stat_summary.wofost_crossval.honesty）
-----------------------------------------------------
本项目 estimate_stage_days 与 WOFOST 参数表 TSUM/TBASE **同源**（TSUM/(T-TBASE)）。
因此本表的 RMSE≈0、CCC=1 是**代码正确性验证**，不是「与外部田间观测的对比」。
真正的外部交叉验证由 S1.5（NASA POWER + Köppen-Geiger）承担；与真实田间的差异
属 S2-B（物理采集），agent 无法代劳。这三条主动披露是**增信项**。

用法
----
    python scripts/run_wofost_crossval.py
    python scripts/run_wofost_crossval.py --json        # 完整 JSON
    python scripts/run_wofost_crossval.py --strict      # 任一门禁不达标 exit 1

零依赖：只用标准库；调 S2-A1 也是 stdlib。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 让脚本可以按绝对路径 import s2_a1（脚本目录已在 sys.path 中）
sys.path.insert(0, HERE)

import s2_a1_phenology_consistency as s2a1  # noqa: E402

STAT_SUMMARY_PATH = os.path.join(ROOT, "benchmarks", "results", "stat_summary.json")
PHENO_OUT_PATH = s2a1.OUT_PATH


# ---------------------------------------------------------------------------
# 合并逻辑
# ---------------------------------------------------------------------------
def extract_crossval_summary(s2a1_report: Dict[str, Any]) -> Dict[str, Any]:
    """从 S2-A1 报告中抽取面向论文的聚合指标（rmse/mae/ccc/wofost 对比）。"""
    ns = s2a1_report.get("numeric_stats") or {}
    acceptance = s2a1_report.get("acceptance") or {}
    grid = s2a1_report.get("grid_results") or {}

    stages = ("emergence", "anthesis", "maturity")
    per_stage: Dict[str, Dict[str, Any]] = {}
    for s in stages:
        st = ns.get(s) or {}
        per_stage[s] = {
            "rmse_days": st.get("rmse_days"),
            "mae_days": st.get("mae_days"),
            "ccc": st.get("ccc"),
            "n_points": st.get("n_points"),
        }

    # 全 35 组聚合（三阶段合并）
    all_rmse = [per_stage[s]["rmse_days"] for s in stages if per_stage[s]["rmse_days"] is not None]
    all_mae = [per_stage[s]["mae_days"] for s in stages if per_stage[s]["mae_days"] is not None]
    all_ccc = [per_stage[s]["ccc"] for s in stages if per_stage[s]["ccc"] is not None]

    def _mean(vals: List[float]) -> Optional[float]:
        return round(sum(vals) / len(vals), 4) if vals else None

    overall = {
        "n_combinations": grid.get("n_combinations", 35),
        "rmse_days": _mean(all_rmse),
        "mae_days": _mean(all_mae),
        "ccc": _mean(all_ccc),
        "stages_covered": list(stages),
    }

    return {
        "generated_by": "scripts/run_wofost_crossval.py",
        "roadmap_task": "S2-A1 / SCI_G2",
        "source_script": "scripts/s2_a1_phenology_consistency.py",
        "grid": {"crops": 7, "temperatures_c": s2a1.TEMPERATURES,
                 "n_combinations": grid.get("n_combinations")},
        "overall": overall,
        "per_stage": per_stage,
        "acceptance": {
            "rmse_days_le_1": acceptance.get("rmse_days_le_1"),
            "overall_rmse_days": acceptance.get("overall_rmse_days"),
            "zero_negative_days": acceptance.get("zero_negative_days"),
            "stall_contract_ok": acceptance.get("stall_contract_ok"),
            "monotonicity_ok": acceptance.get("monotonicity_ok"),
            "tsum_drift_ok": acceptance.get("tsum_drift_ok"),
            "wheat_below_tbase_stalled": acceptance.get("wheat_below_tbase_stalled"),
            "all_pass": acceptance.get("all_pass"),
        },
        "tbase_boundary": s2a1_report.get("tbase_boundary"),
        "monotonicity_violations": s2a1_report.get("monotonicity_violations"),
        "counts": s2a1_report.get("counts"),
        "honesty": {
            "same_source": True,
            "note": (
                "本项目 estimate_stage_days 与 WOFOST 参数表同源（TSUM/(T-TBASE)），"
                "RMSE≈0/CCC=1 是代码正确性验证，非外部田间对比；"
                "外部交叉验证见 S1.5（NASA POWER + Köppen-Geiger），"
                "真实田间差异见 S2-B（物理采集，agent 无法代劳）。"
            ),
        },
        "grid_rows_sample": grid.get("rows", [])[:3],  # 前三行样例，便于论文表格引用
        "n_grid_rows_total": len(grid.get("rows", [])),
    }


def merge_into_stat_summary(crossval: Dict[str, Any],
                            out_path: str = STAT_SUMMARY_PATH) -> Dict[str, Any]:
    """把 wofost_crossval 字段合入 stat_summary.json；若文件不存在则新建骨架。"""
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            base = json.load(f)
    else:
        base = {
            "generated_by": "benchmarks/agri_recipe_bench/stat_report.py",
            "roadmap_task": "S1.3+S2-A1",
            "history": {"enabled": False, "reason": "stat_summary.json 不存在"},
            "repeat_experiment": {},
            "verdict": {},
        }
    base["wofost_crossval"] = crossval
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=2, default=str)
    return base


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _print_table(cv: Dict[str, Any]) -> None:
    print("=== S2-A1 WOFOST 交叉验证（合并入 stat_summary.json）===")
    g = cv["grid"]
    print(f"网格: 7 crops × {len(g['temperatures_c'])} T levels "
          f"({', '.join(str(t) for t in g['temperatures_c'])} °C) "
          f"= {cv['overall']['n_combinations']} 组")
    print(f"阶段: {', '.join(cv['overall']['stages_covered'])}")
    print()
    print(f"{'stage':<12} {'RMSE[d]':>10} {'MAE[d]':>10} {'CCC':>8}")
    for s, m in cv["per_stage"].items():
        print(f"{s:<12} {_fmt(m['rmse_days']):>10} {_fmt(m['mae_days']):>10} "
              f"{_fmt(m['ccc']):>8}")
    ov = cv["overall"]
    print(f"{'OVERALL':<12} {_fmt(ov['rmse_days']):>10} {_fmt(ov['mae_days']):>10} "
          f"{_fmt(ov['ccc']):>8}")
    print()
    acc = cv["acceptance"]
    print("门禁（bool=True 才算通过；数值类是测量结果，不带判定）：")
    # 数值型门禁：单独列，不做 ✅/❌ 判定
    numeric_keys = {"overall_rmse_days"}
    for k, v in acc.items():
        if k in numeric_keys:
            print(f"  ·   {k}: {v}")
            continue
        mark = "✅" if v else "❌"
        print(f"  {mark} {k}: {v}")
    print()
    print(f"停滞契约: {cv['counts'].get('stall_correct')}/{cv['counts'].get('stall_expected')} "
          f"正确 · 负天数={cv['counts'].get('negative_days')} · "
          f"单调性违反={cv['counts'].get('monotonicity_violations')}")
    print()
    print(f"诚实边界: {cv['honesty']['note']}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="S2-A1 交叉验证交付 + 合入 stat_summary.json")
    p.add_argument("--json", action="store_true", help="输出完整合并结果 JSON")
    p.add_argument("--strict", action="store_true",
                   help="门禁不达标时 exit 1（供 CI 使用）")
    p.add_argument("--no-merge", action="store_true",
                   help="仅生成，不写入 stat_summary.json")
    args = p.parse_args(argv)

    # 1) 调 S2-A1 现场复算
    s2a1_report = s2a1.build_report()
    # 顺便落一份 phenology_consistency.json（若不存在也覆盖写）
    os.makedirs(os.path.dirname(PHENO_OUT_PATH), exist_ok=True)
    with open(PHENO_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(s2a1_report, f, ensure_ascii=False, indent=2, default=str)

    # 2) 抽取并合入
    cv = extract_crossval_summary(s2a1_report)
    if not args.no_merge:
        merged = merge_into_stat_summary(cv)
        print(f"已合入 {os.path.relpath(STAT_SUMMARY_PATH, ROOT)} "
              f"(顶层键: {list(merged.keys())})")
    else:
        print("（--no-merge，未写 stat_summary.json）")

    # 3) 打印短表
    _print_table(cv)

    # 4) --json 输出完整合并结果
    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(cv, ensure_ascii=False, indent=2, default=str))

    # 5) --strict 门禁（数值型不参与布尔判定）
    acc = cv["acceptance"]
    numeric_keys = {"overall_rmse_days"}
    if args.strict:
        bool_items = [(k, v) for k, v in acc.items()
                      if k not in numeric_keys and v is not None]
        failed = [k for k, v in bool_items if not v]
        if failed:
            print(f"\n❌ --strict 门禁失败：{failed}", file=sys.stderr)
            return 1
        # 数值型也检查 rmse ≤ 1
        rmse = acc.get("overall_rmse_days")
        if isinstance(rmse, (int, float)) and rmse > 1.0:
            print(f"\n❌ --strict 门禁失败：overall_rmse_days={rmse} > 1.0",
                  file=sys.stderr)
            return 1
        print("\n✅ --strict 全部门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
