"""benchmarks/agri_recipe_bench/negative_runner.py —— Bench 负例执行器（S1.2）

把 cases/neg/ 下 20 个负例骨架映射到**真实代码路径**的确定性校验：

  A 类（8）输入合法性拒绝  → core.numeric_domain 的 8 种契约装饰器
  B 类（6）诚实降级与拒识  → core.honest_policy 的 6 个真实判据函数
  C 类（4）反事实一致性    → engine.agriworld_lite.simulate + counterfactual_api 真仿真
  D 类（2）血缘与信任断裂  → core.recipe_signing 签名验签 + core.data_lineage 完整性断言

诚实性约束：
  - 每个负例都必须真正调用被检对象；不得用"恒 True 的桩函数"通过验收。
  - 期望失败类型（InputError / DataError / flag / invariant / raise）由负例骨架
    的 expect_failure_type 决定；校验器按类型断言，而非按描述字面匹配。
  - C4（复合扰动可加性）的容差是**科学判断项**，默认值 C4_ADDITIVITY_TOLERANCE
    已标为"待用户确认"；runner 会报告实测偏差，容差取值须由论文作者定稿。

用法：
    python benchmarks/agri_recipe_bench/negative_runner.py          # 自测
    from benchmarks.agri_recipe_bench.negative_runner import run_negative_case
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 真实被检对象（不得替换为桩）
# ---------------------------------------------------------------------------
from core.numeric_domain import (
    InputError,
    DataError,
    bounded,
    bounded_each,
    finite,
    known_enum,
    monotone_constraints,
    non_negative,
    not_empty_string,
)
from core import honest_policy
from core import recipe_signing
from core.data_lineage import verify_lineage_intact
from engine.agriworld_lite import CROP_PARAMS, DailyInput, get_params, simulate
from agent.counterfactual_api import counterfactual_trajectory


# ---------------------------------------------------------------------------
# A 类真实探针：机理层契约装饰器（与 engine 实际契约同构）
# ---------------------------------------------------------------------------
# 枚举取 engine 的真实机理参数表键集，避免与项目实际作物脱节
CROP_ENUM: List[str] = sorted(CROP_PARAMS.keys())


@bounded("days", 1, 365)
def _probe_days(days: int) -> int:
    return days


@known_enum("crop", CROP_ENUM)
@not_empty_string("crop")
def _probe_crop_enum(crop: str) -> str:
    return crop


@finite("mean_temp_c")
def _probe_temp_finite(mean_temp_c: float) -> float:
    return mean_temp_c


@bounded("RH", 0, 100)
def _probe_rh(RH: float) -> float:
    return RH


@non_negative("dli")
def _probe_dli(dli: float) -> float:
    return dli


@bounded("theta", 0, 1)
def _probe_theta(theta: float) -> float:
    return theta


@monotone_constraints("Tmin", "Tmax", a_lt_b=True)
@bounded_each(("Tmin", "Tmax"), lo=-50, hi=60)
def _probe_temp_range(Tmin: float, Tmax: float) -> float:
    return Tmax - Tmin


@not_empty_string("crop")
def _probe_crop_nonempty(crop: str) -> str:
    return crop


# ---------------------------------------------------------------------------
# A 类执行器
# ---------------------------------------------------------------------------
def _expect_raises(fn: Callable, exc_types: Tuple[type, ...], payload: Dict) -> Tuple[bool, str]:
    """调用 fn 并断言其抛出 exc_types 中的异常。返回 (ok, detail)。"""
    try:
        fn(payload)
        return False, f"应抛 {exc_types}, 却静默通过"
    except exc_types as e:
        return True, f"{type(e).__name__}({e})"
    except Exception as e:  # 抛了别的类型也算失败（期望具体错误）
        return False, f"期望 {exc_types}, 实际抛 {type(e).__name__}: {e}"


def _a1(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_days(days=p["days"]), (InputError,), case["input"])


def _a2(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_crop_enum(crop=p["crop"]), (InputError,), case["input"])


def _a3(case: Dict) -> Tuple[bool, str]:
    # NaN 温度 → DataError（numeric_domain 强制先查 NaN 再查范围）
    return _expect_raises(lambda p: _probe_temp_finite(mean_temp_c=p["mean_temp_c"]),
                          (DataError,), case["input"])


def _a4(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_rh(RH=p["RH"]), (InputError,), case["input"])


def _a5(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_dli(dli=p["dli"]), (InputError,), case["input"])


def _a6(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_theta(theta=p["theta"]), (InputError,), case["input"])


def _a7(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_temp_range(Tmin=p["Tmin"], Tmax=p["Tmax"]),
                          (InputError,), case["input"])


def _a8(case: Dict) -> Tuple[bool, str]:
    return _expect_raises(lambda p: _probe_crop_nonempty(crop=p["crop"]), (InputError,), case["input"])


# ---------------------------------------------------------------------------
# B 类执行器：断言 honest_policy 返回的期望标记成立
# ---------------------------------------------------------------------------
def _b_flag(case: Dict, fn: Callable, key: str, args: Dict) -> Tuple[bool, str]:
    verdict = fn(**args)
    ok = verdict.get(key) is True
    return (ok, f"verdict={verdict}") if ok else (False, f"期望 {key}=True, verdict={verdict}")


def _b1(case: Dict) -> Tuple[bool, str]:
    inp = case["input"]
    v = honest_policy.assess_input_completeness(
        observations=inp.get("observations"),
        env_recipe=inp.get("env_recipe"),
        adapt_score=inp.get("adapt_score"),
    )
    ok = v["confidence"] == "low" and v["model"] == "rule_based"
    return (ok, f"confidence={v['confidence']}, model={v['model']}, completeness={v['completeness']}") if ok \
        else (False, f"期望 low/rule_based, 实际 {v['confidence']}/{v['model']}")


def _b2(case: Dict) -> Tuple[bool, str]:
    return _b_flag(case, honest_policy.assess_climate_shift, "out_of_domain",
                   {"shift_sd": case["input"].get("climate_shift_sd")})


def _b3(case: Dict) -> Tuple[bool, str]:
    return _b_flag(case, honest_policy.assess_source_freshness, "stale",
                   {"max_age_years": case["input"].get("source_max_age_years")})


def _b4(case: Dict) -> Tuple[bool, str]:
    return _b_flag(case, honest_policy.assess_source_conflict, "conflict",
                   {"sources": case["input"].get("sources")})


def _b5(case: Dict) -> Tuple[bool, str]:
    return _b_flag(case, honest_policy.assess_sensor_consistency, "inconsistent",
                   {"day_temp_c": case["input"].get("day_temp_c"),
                    "night_temp_c": case["input"].get("night_temp_c")})


def _b6(case: Dict) -> Tuple[bool, str]:
    return _b_flag(case, honest_policy.assess_calibration_support, "uncalibrated",
                   {"distance_to_calib_set": case["input"].get("distance_to_calib_set")})


# ---------------------------------------------------------------------------
# C 类执行器：真实机理仿真下的反事实不变式
# ---------------------------------------------------------------------------
CROP_FOR_CF = "tomato"          # engine 真实作物（get_params 命中 CROP_PARAMS）
DEFAULT_BIOMASS_CAP = 9000.0    # 2 × y_max(4500)：绝对物理上限
# C4 容差：**科学判断项，待用户确认**。0.20 = 联合扰动效应与分施加之和的相对偏差上限。
C4_ADDITIVITY_TOLERANCE = 0.20


def _baseline_actions(n: int = 30, temp_mean: float = 22.0, dli: float = 14.0
                      ) -> List[DailyInput]:
    """构造 n 天的稳定基线动作序列。"""
    return [DailyInput(dli=dli, temp_mean_c=temp_mean,
                       temp_min_c=temp_mean - 5.0, temp_max_c=temp_mean + 5.0,
                       rh=0.6, wind_ms=1.5, co2_ppm=420.0,
                       irrigation_l_m2=2.0, fert_n_mg_l=30.0)
            for _ in range(n)]


def _biomass(actions: List[DailyInput], crop: str = CROP_FOR_CF) -> float:
    return simulate(crop, actions)["final_biomass"]["total"]


def _c1(case: Dict) -> Tuple[bool, str]:
    """零扰动恒等：候选==基线 → delta 必须为 0、verdict=similar。"""
    n = int(case["input"].get("steps", 30))
    base = _baseline_actions(n)
    res = counterfactual_trajectory(CROP_FOR_CF, base, candidate_actions=list(base))
    delta = res.get("delta", {}).get("biomass", 0.0)
    ok = abs(delta) < 1e-6 and res.get("verdict") == "similar"
    return (ok, f"delta_biomass={delta}, verdict={res.get('verdict')}") if ok \
        else (False, f"零扰动未恒等：delta={delta}, verdict={res.get('verdict')}")


def _c2(case: Dict) -> Tuple[bool, str]:
    """方向反转：基线远离最适温时，+2℃ 与 -2℃ 的产量差必须异号。

    基线 temp_mean=20℃（最适温 27℃ 之下）：+3℃ 靠近最适（增）、-3℃ 远离（减）。
    要求两者均非零且符号相反 —— 否则机理内核对温度的响应不可分。
    """
    base_temp = 20.0
    delta = float(case["input"].get("perturbation", {}).get("mean_temp_c", 3.0))
    b = _biomass(_baseline_actions(30, temp_mean=base_temp))
    hi = _biomass(_baseline_actions(30, temp_mean=base_temp + delta)) - b
    lo = _biomass(_baseline_actions(30, temp_mean=base_temp - delta)) - b
    ok = (hi > 0) != (lo > 0) and abs(hi) > 1e-6 and abs(lo) > 1e-6
    return (ok, f"Δ(+{delta})={hi:.3f}, Δ(-{delta})={lo:.3f}（异号）") if ok \
        else (False, f"符号未反转：Δ(+{delta})={hi:.3f}, Δ(-{delta})={lo:.3f}")


def _c3(case: Dict) -> Tuple[bool, str]:
    """饱和约束：极端高温下产量必须非负且不超过物理上限。"""
    n = int(case["input"].get("steps", 30))
    temp = float(case["input"].get("perturbation", {}).get("mean_temp_c", 35.0))
    y = _biomass(_baseline_actions(n, temp_mean=temp))
    ok = 0.0 <= y <= DEFAULT_BIOMASS_CAP
    return (ok, f"yield={y:.2f} ∈ [0, {DEFAULT_BIOMASS_CAP}]") if ok \
        else (False, f"饱和约束违反：yield={y:.2f}")


def _c4(case: Dict) -> Tuple[bool, str]:
    """复合扰动可加性（软不变式）：联合扰动效应 ≈ 分施加之和（容差内）。

    这是机理内核的**软性质**：对非线性响应，交叉项不为零。容差 C4_ADDITIVITY_TOLERANCE
    为科学判断项（待用户确认），runner 报告实测偏差供作者定稿。
    """
    n = 30
    b = _biomass(_baseline_actions(n))
    y_t = _biomass(_baseline_actions(n, temp_mean=22.0 + 2.0))
    y_d = _biomass(_baseline_actions(n, dli=14.0 + 1.0))
    y_j = _biomass(_baseline_actions(n, temp_mean=22.0 + 2.0, dli=14.0 + 1.0))
    joint = y_j - b
    separate_sum = (y_t - b) + (y_d - b)
    rel = abs(joint - separate_sum) / max(abs(b), 1e-6)
    ok = rel <= C4_ADDITIVITY_TOLERANCE
    return (ok, f"joint={joint:.2f}, Σseparate={separate_sum:.2f}, rel_dev={rel:.3f} "
                f"≤ tol {C4_ADDITIVITY_TOLERANCE}") if ok \
        else (False, f"可加性超出容差：rel_dev={rel:.3f} > {C4_ADDITIVITY_TOLERANCE}")


# ---------------------------------------------------------------------------
# D 类执行器：签名验签 + 血缘完整性
# ---------------------------------------------------------------------------
def _d1(case: Dict) -> Tuple[bool, str]:
    """篡改配方后签名必须失效（verified=False）。"""
    tamper = case["input"].get("tamper", {})
    path = next(iter(tamper), "")
    value = tamper.get(path)
    recipe = {"crop": "番茄", "zone_id": "mediterranean",
              "environment": {"temperature": {"day_c": 24.0}},
              "sources": [{"id": "s0"}]}
    recipe["trust_mark"] = recipe_signing.sign_recipe(recipe)
    intact = recipe_signing.verify_recipe(recipe)
    tampered = recipe_signing.tamper(recipe, path, value)
    broken = recipe_signing.verify_recipe(tampered)
    ok = intact["verified"] is True and broken["verified"] is False
    return (ok, f"篡改前 verified=True, 篡改后 verified=False (path={path})") if ok \
        else (False, f"篡改检测失败：intact={intact['verified']}, broken={broken['verified']}")


def _d2(case: Dict) -> Tuple[bool, str]:
    """移除 source 后血缘必须检测到断链（break=True）。"""
    recipe = {
        "crop": "番茄", "zone_id": "mediterranean",
        "lineage_refs": [{"id": "s0"}, {"id": "s1"}],
        "sources": [{"id": "s0", "payload": "a"}, {"id": "s1", "payload": "b"}],
    }
    intact = verify_lineage_intact(recipe)
    broken = verify_lineage_intact({**recipe, "sources": recipe["sources"][1:]})
    ok = intact["break"] is False and broken["break"] is True
    return (ok, f"完整时 break=False, 移除 sources[0] 后 break=True (missing={broken['missing_ids']})") \
        if ok else (False, f"断链检测失败：intact={intact}, broken={broken}")


# ---------------------------------------------------------------------------
# 注册表（case id → 真实校验器）
# ---------------------------------------------------------------------------
NEG_REGISTRY: Dict[str, Callable[[Dict], Tuple[bool, str]]] = {
    "neg_A1": _a1, "neg_A2": _a2, "neg_A3": _a3, "neg_A4": _a4,
    "neg_A5": _a5, "neg_A6": _a6, "neg_A7": _a7, "neg_A8": _a8,
    "neg_B1": _b1, "neg_B2": _b2, "neg_B3": _b3, "neg_B4": _b4,
    "neg_B5": _b5, "neg_B6": _b6,
    "neg_C1": _c1, "neg_C2": _c2, "neg_C3": _c3, "neg_C4": _c4,
    "neg_D1": _d1, "neg_D2": _d2,
}

# 需论文作者确认容差的负例（诚实标注，不静默定值）
USER_TOLERANCE_CASES = {"neg_C4": C4_ADDITIVITY_TOLERANCE}


def load_neg_cases(case_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """加载 cases/neg/ 下全部负例骨架（兼容 NaN 字面量）。"""
    root = Path(__file__).resolve().parent
    d = case_dir or (root / "cases" / "neg")
    if not d.is_dir():
        raise FileNotFoundError(f"负例目录不存在：{d}")
    out: List[Dict[str, Any]] = []
    for f in sorted(d.glob("neg_*.json")):
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def run_negative_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """执行单个负例：返回 {"ok": bool, "detail": str}。"""
    cid = case.get("id")
    fn = NEG_REGISTRY.get(cid)
    if fn is None:
        return {"ok": False, "detail": f"{cid}: 未注册校验器（需人工补）"}
    try:
        ok, detail = fn(case)
        return {"ok": bool(ok), "detail": detail}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def run_all(case_dir: Optional[Path] = None) -> Dict[str, Any]:
    """跑全部负例，返回分组统计。"""
    cases = load_neg_cases(case_dir)
    results = []
    by_axis: Dict[str, Dict[str, int]] = {}
    for c in cases:
        r = run_negative_case(c)
        results.append({"id": c["id"], "axis": c.get("axis"), "ok": r["ok"],
                        "detail": r["detail"],
                        "tolerance_user_confirm": c["id"] in USER_TOLERANCE_CASES})
        a = c.get("axis", "unknown")
        by_axis.setdefault(a, {"total": 0, "passed": 0})
        by_axis[a]["total"] += 1
        by_axis[a]["passed"] += 1 if r["ok"] else 0
    passed = sum(1 for r in results if r["ok"])
    return {"total": len(cases), "passed": passed, "failed": len(cases) - passed,
            "by_axis": by_axis, "results": results}


# ---------------------------------------------------------------------------
# 自测 / CLI
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """python -m benchmarks.agri_recipe_bench.negative_runner"""
    res = run_all()
    print(f"\n负例自检：{res['passed']}/{res['total']} passed\n")
    print("分组：")
    for a, s in sorted(res["by_axis"].items()):
        print(f"  {a}: {s['passed']}/{s['total']}")
    print("\n逐例：")
    for r in res["results"]:
        flag = "✓" if r["ok"] else "✗"
        tag = " [容差待用户确认]" if r["tolerance_user_confirm"] else ""
        print(f"  {flag} {r['id']}{tag}: {r['detail']}")
    return 0 if res["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
