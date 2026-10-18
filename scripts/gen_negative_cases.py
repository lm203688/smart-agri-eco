#!/usr/bin/env python3
"""
gen_negative_cases.py —— 生成 20 个 Bench 负例用例骨架（SCI Rigor 补齐 · S1.2）

对应 docs/SCI_ROADMAP_2026-10-18.md 任务 S1.2。
按四类组织：
  A. 输入合法性拒绝      (8 个) — 参数越界/NaN/未知枚举/类型错
  B. 诚实降级与拒识      (6 个) — 观测缺失/数据漂移/多源冲突/超校准域
  C. 反事实一致性        (4 个) — 零扰动恒等/方向反转/饱和/复合可加性
  D. 血缘与信任断裂      (2 个) — 签名篡改/来源移除

生成物：benchmarks/agri_recipe_bench/cases/neg/ 下 20 个 JSON 骨架。
骨架只含 id / axis / case_type / description / input / expect_failure /
expect_error_type，expected 字段留待逐个人工确认（这是科学内容，不能自动编造）。

用法：
    python scripts/gen_negative_cases.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "benchmarks/agri_recipe_bench/cases/neg"

# --------------------------------------------------------------------------
# A 类：输入合法性拒绝（直接对应 core/numeric_domain.py 的 8 种装饰器）
# --------------------------------------------------------------------------
CASES_A = [
    ("A1", "negative_input_bounds", "负天数：days=-5 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "days": -5},
     "InputError", "core/numeric_domain.bounded"),
    ("A2", "negative_input_bounds", "未知作物：crop=quantum_plant 应被拒绝",
     {"crop": "quantum_plant", "zone_id": "mediterranean", "days": 120},
     "InputError", "core/numeric_domain.known_enum"),
    ("A3", "negative_input_bounds", "NaN 温度：mean_temp_c=NaN 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "mean_temp_c": float("nan")},
     "DataError", "core/numeric_domain.bounded"),
    ("A4", "negative_input_bounds", "超饱和湿度：RH=150% 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "RH": 150.0},
     "InputError", "core/numeric_domain.bounded"),
    ("A5", "negative_input_bounds", "光照负值：dli=-1 MJ/m²/day 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "dli": -1.0, "days": 120},
     "InputError", "core/numeric_domain.non_negative"),
    ("A6", "negative_input_bounds", "超饱和含水率：theta=1.5 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "theta": 1.5},
     "InputError", "core/numeric_domain.bounded"),
    ("A7", "negative_input_bounds", "边界错乱：Tmin=30 > Tmax=10 应被拒绝",
     {"crop": "番茄", "zone_id": "mediterranean", "T": 20.0, "Tmin": 30.0, "Tmax": 10.0},
     "InputError", "core/numeric_domain.monotone_constraints"),
    ("A8", "negative_input_bounds", "空字符串作物：crop='' 应被拒绝",
     {"crop": "", "zone_id": "mediterranean", "days": 120},
     "InputError", "core/numeric_domain.not_empty_string"),
]

# --------------------------------------------------------------------------
# B 类：诚实降级与拒识（honest degradation / abstention）
# --------------------------------------------------------------------------
CASES_B = [
    ("B1", "negative_honest_degradation", "完全无观测输入：应降级且 confidence=low，不得给出高置信推荐",
     {"crop": "番茄", "zone_id": "mediterranean", "observations": None},
     "degrade", "confidence=low & model=rule_based"),
    ("B2", "negative_honest_degradation", "气候漂移超 3σ：目标气候远离历史校准域，应拒绝或标注 out-of-domain",
     {"crop": "番茄", "zone_id": "mediterranean", "climate_shift_sd": 3.5},
     "abstain", "out_of_domain"),
    ("B3", "negative_honest_degradation", "数据源过期：sources[] 中最新 trial_location 时间戳早于 3 年，应标 stale",
     {"crop": "番茄", "zone_id": "mediterranean", "source_max_age_years": 4},
     "flag", "stale_sources"),
    ("B4", "negative_honest_degradation", "多源冲突：两源给出互斥的 Topt（25 vs 40°C），应拒绝合并并报冲突",
     {"crop": "番茄", "zone_id": "mediterranean",
      "sources": [{"Topt": 25.0}, {"Topt": 40.0}]},
     "abstain", "source_conflict"),
    ("B5", "negative_honest_degradation", "自相矛盾传感器读数：day_temp < night_temp，应 flag 数据异常",
     {"crop": "番茄", "zone_id": "mediterranean",
      "day_temp_c": 15.0, "night_temp_c": 22.0},
     "flag", "sensor_inconsistency"),
    ("B6", "negative_honest_degradation", "超出保形校准域：新样本偏离校准集支持，区间不得保证 90% 覆盖，需标注 uncalibrated",
     {"crop": "番茄", "zone_id": "mediterranean", "distance_to_calib_set": ">p99"},
     "flag", "conformal_uncalibrated"),
]

# --------------------------------------------------------------------------
# C 类：反事实一致性（counterfactual invariants）
# --------------------------------------------------------------------------
CASES_C = [
    ("C1", "negative_counterfactual_invariant", "零扰动恒等：perturbation={} 时反事实轨迹必须等于事实轨迹",
     {"recipe_ref": "番茄:full_cycle:indoor_cabinet", "perturbation": {}, "steps": 30},
     "invariant", "cf == factual"),
    ("C2", "negative_counterfactual_invariant", "方向反转：温度扰动 +2°C 与 -2°C 的产量差必须异号",
     {"recipe_ref": "番茄:full_cycle:indoor_cabinet",
      "perturbation": {"mean_temp_c": 2.0}, "steps": 30},
     "invariant", "sign(yield(+2) - yield(-2)) != 0"),
    ("C3", "negative_counterfactual_invariant", "饱和约束：perturbation 使 mean_temp_c = 60°C 时产量不得超过 0 且不得为负",
     {"recipe_ref": "番茄:full_cycle:indoor_cabinet",
      "perturbation": {"mean_temp_c": 35.0}, "steps": 30},
     "invariant", "0 <= yield <= yield_cap"),
    ("C4", "negative_counterfactual_invariant", "复合扰动可加性检验：ΔT 与 ΔD 同时施加 vs 分别施加之差应在容差内",
     {"recipe_ref": "番茄:full_cycle:indoor_cabinet",
      "perturbation": {"mean_temp_c": 2.0, "dli": 1.0}, "steps": 30},
     "invariant", "|joint - (t1 + t2)| <= tolerance"),
]

# --------------------------------------------------------------------------
# D 类：血缘与信任断裂（lineage / trust breakage）
# --------------------------------------------------------------------------
CASES_D = [
    ("D1", "negative_trust_breakage", "篡改配方后签名失效：修改 environment.temperature 后 trust_mark 必须 verify 失败",
     {"recipe_ref": "tamper_test_001", "tamper": {"environment.temperature.day_c": 99.0}},
     "raise", "TrustVerificationError"),
    ("D2", "negative_trust_breakage", "移除 source 后血缘断裂：删掉 sources[0] 后 data_lineage 必须检测到断链",
     {"recipe_ref": "lineage_test_001", "tamper": {"remove_source_index": 0}},
     "raise", "LineageBreakError"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    groups = [("A", CASES_A), ("B", CASES_B), ("C", CASES_C), ("D", CASES_D)]

    for _, cases in groups:
        for cid, axis, desc, payload, expect, expect_detail in cases:
            obj = {
                "id": f"neg_{cid}",
                "axis": axis,
                "case_type": "negative",
                "description": desc,
                "input": payload,
                "expect_failure": True,
                "expect_failure_type": expect,
                "expect_failure_detail": expect_detail,
                "expected": None,   # 待人工确认：负例的"正确行为"是结构化的，
                                    # 不是数值，由 gate_*.py 逐类校验
                "provenance": {
                    "generated_by": "scripts/gen_negative_cases.py",
                    "purpose": "SCI Rigor 补齐（negative control / abstention / invariant）",
                    "roadmap_task": "S1.2",
                    "reference_required": True,
                },
            }
            p = OUT / f"neg_{cid}.json"
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                    default=str) + "\n", encoding="utf-8")
            written += 1

    print(f"已生成 {written} 个负例骨架 → {OUT.relative_to(ROOT)}")
    print("\n分类统计：")
    for name, cases in groups:
        print(f"  {name} 类 {len(cases)} 个")
    print("\n下一步（人工，不可自动）：")
    print("  1. 逐个确认 expected 行为描述是否准确（尤其 C 类不变量的容差取值）")
    print("  2. 为每个负例补 reference 字段（文献/协议出处）")
    print("  3. 扩 run_bench.py 识别 case_type=negative，接入 CI 第 40 步")


if __name__ == "__main__":
    main()
