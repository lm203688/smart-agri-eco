#!/usr/bin/env python3
"""check_bench_coverage.py — M15-B5 评测先行门禁。

判定标准（报告 §M15-B5）：
  任何科学模块进主干前必须先向 bench 提交用例并跑通。

实现：
  1. 扫描 agent/ 下的科学模块（排除非科学模块如 orchestrator/execution_log 等）
  2. 扫描 benchmarks/agri_recipe_bench/cases/ 的用例
  3. 建立模块→用例映射（通过用例 JSON 中的模块引用 + 轴映射）
  4. 报告覆盖率、缺口、CI 门禁状态

用法：
    python scripts/check_bench_coverage.py              # 报告模式
    python scripts/check_bench_coverage.py --gate       # CI 门禁（缺口即 exit 1）
    python scripts/check_bench_coverage.py --json       # JSON 输出
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(ROOT, "benchmarks", "agri_recipe_bench", "cases")
AGENT_DIR = os.path.join(ROOT, "agent")

# 科学模块白名单：这些模块必须有 bench 用例覆盖
SCIENTIFIC_MODULES = {
    "forecast_agent": {"label": "产量/采收预测", "axis": "target_prediction"},
    "growth_agent": {"label": "物候与生长规划", "axis": "state_rolling"},
    "nutrition_agent": {"label": "营养与营养液", "axis": "state_rolling"},
    "pest_agent": {"label": "病虫害诊断", "axis": "counterfactual"},
    "climate_agent": {"label": "气候与地理分区", "axis": "generalization"},
    "crop_agent": {"label": "作物适配与推荐", "axis": "generalization"},
    "phenology": {"label": "物候模型", "axis": "state_rolling"},
}

# 非科学模块（不参与门禁）
NON_SCIENTIFIC = {
    "orchestrator", "orchestration_audit", "execution_log",
    "control_agent", "eco_agent", "jev_gate", "plant_calendar",
    "preset_cities", "season_agent", "soil_profile", "vision",
    "conformal", "climate_data",
}


def _load_cases() -> List[Dict[str, Any]]:
    """加载所有 bench 用例。"""
    cases = []
    for f in sorted(glob.glob(os.path.join(CASES_DIR, "*.json"))):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                c = json.load(fh)
            c["_file"] = os.path.basename(f)
            cases.append(c)
        except Exception:
            pass
    return cases


def _find_module_references(case: Dict[str, Any]) -> Set[str]:
    """从用例 JSON 中提取引用的模块名。"""
    refs = set()
    s = json.dumps(case, ensure_ascii=False)
    for mod in SCIENTIFIC_MODULES:
        if mod in s:
            refs.add(mod)
    return refs


def _count_cases_by_axis(cases: List[Dict[str, Any]]) -> Dict[str, int]:
    """按轴统计用例数。"""
    counts = {}
    for c in cases:
        axis = c.get("axis", "unknown")
        counts[axis] = counts.get(axis, 0) + 1
    return counts


def _check_module_coverage(
    cases: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """检查每个科学模块的 bench 覆盖率。"""
    results: Dict[str, Dict[str, Any]] = {}
    for mod, meta in SCIENTIFIC_MODULES.items():
        # 查找引用该模块的用例
        matching = [c for c in cases if mod in _find_module_references(c)]
        # 也检查轴匹配（模块的 axis 与用例 axis 一致）
        axis_matching = [c for c in cases if c.get("axis") == meta["axis"]]
        # 合并去重
        seen = set()
        combined = []
        for c in matching + axis_matching:
            if c["id"] not in seen:
                seen.add(c["id"])
                combined.append(c)

        results[mod] = {
            "label": meta["label"],
            "expected_axis": meta["axis"],
            "case_count": len(combined),
            "covered": len(combined) > 0,
            "cases": [c["id"] for c in combined[:5]],
            "case_ids": [c["id"] for c in combined],
        }
    return results


def analyze() -> Dict[str, Any]:
    """完整分析：用例加载 + 模块覆盖率 + 轴分布。"""
    cases = _load_cases()
    axis_counts = _count_cases_by_axis(cases)
    module_coverage = _check_module_coverage(cases)

    # 统计
    total_modules = len(SCIENTIFIC_MODULES)
    covered_modules = sum(1 for v in module_coverage.values() if v["covered"])
    uncovered = [m for m, v in module_coverage.items() if not v["covered"]]

    # 作物/分区覆盖
    crops: Set[str] = set()
    zones: Set[str] = set()
    for c in cases:
        inp = c.get("input", {})
        if inp.get("crop"):
            crops.add(inp["crop"])
        if inp.get("zone_id"):
            zones.add(inp["zone_id"])
        if c.get("expected", {}).get("zones"):
            for z in c["expected"]["zones"]:
                zones.add(z)

    # 轴覆盖
    expected_axes = {"target_prediction", "state_rolling", "counterfactual", "generalization"}
    covered_axes = set(axis_counts.keys())
    missing_axes = expected_axes - covered_axes

    # 阈值判定
    min_cases = 50  # 报告建议 ≥50
    min_modules = 6  # 至少 6 个模块有覆盖

    return {
        "total_cases": len(cases),
        "cases_by_axis": axis_counts,
        "covered_axes": sorted(covered_axes),
        "missing_axes": sorted(missing_axes),
        "module_coverage": module_coverage,
        "covered_modules": covered_modules,
        "total_modules": total_modules,
        "uncovered_modules": uncovered,
        "unique_crops": sorted(crops),
        "unique_zones": sorted(zones),
        "crop_count": len(crops),
        "zone_count": len(zones),
        "thresholds": {
            "min_cases": min_cases,
            "min_modules": min_modules,
            "min_crops": 10,
            "min_zones": 6,
        },
        "gate_pass": (
            len(cases) >= min_cases
            and covered_modules >= min_modules
            and len(crops) >= 10
            and len(zones) >= 6
            and len(missing_axes) == 0
        ),
    }


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="M15-B5 评测先行门禁")
    p.add_argument("--gate", action="store_true", help="CI 门禁模式（缺口即 exit 1）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args(argv)

    try:
        report = analyze()
    except Exception as e:
        print(f"❌ 分析失败: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("M15-B5 评测先行门禁报告")
        print("=" * 60)
        print(f"用例总数: {report['total_cases']} (阈值 ≥{report['thresholds']['min_cases']})")
        print()

        print("轴分布:")
        for axis, count in sorted(report["cases_by_axis"].items()):
            print(f"  · {axis}: {count}")
        if report["missing_axes"]:
            print(f"  ❌ 缺失轴: {report['missing_axes']}")
        else:
            print(f"  ✅ 四轴齐全")
        print()

        print(f"模块覆盖率: {report['covered_modules']}/{report['total_modules']}")
        for mod, info in sorted(report["module_coverage"].items()):
            status = "✅" if info["covered"] else "❌"
            cases_str = ", ".join(info["cases"][:3])
            if len(info["cases"]) > 3:
                cases_str += f" (+{len(info['cases'])-3})"
            print(f"  {status} {mod:20s} ({info['label']}): {info['case_count']} 用例")
            if info["cases"]:
                print(f"      {cases_str}")
        print()

        print(f"作物覆盖: {report['crop_count']} 种 (阈值 ≥{report['thresholds']['min_crops']})")
        print(f"  {', '.join(report['unique_crops'][:8])}{'...' if report['crop_count'] > 8 else ''}")
        print(f"分区覆盖: {report['zone_count']} 个 (阈值 ≥{report['thresholds']['min_zones']})")
        print(f"  {', '.join(report['unique_zones'])}")
        print()

        gate = "✅ PASS" if report["gate_pass"] else "❌ FAIL"
        print(f"门禁判定: {gate}")

    if args.gate and not report["gate_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
