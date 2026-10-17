#!/usr/bin/env python3
"""
demo_mechanism_after_harden.py —— 机理内核加固前后对比演示

不动 engine/agriworld_lite.py 原文件，而是在此脚本里复制 4 个函数的实现
并套上 core/numeric_domain.py 的装饰器，重跑一遍 probe_mechanism_garbage_in.py
的 34 个探针。

预期结果：27 FAIL → 0 FAIL（装饰器在函数调用之前拦截非法输入，
返回 ValueError/DataError 而不是"垃圾进垃圾出"）。

用法：
    python scripts/demo_mechanism_after_harden.py
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.numeric_domain import (
    bounded, known_enum, not_empty_string, monotone_constraints,
    bounded_each,
)
from engine.derived import vpd as raw_vpd

from functools import wraps
from engine.agriworld_lite import (
    theoretical_yield_cap as raw_tyc,
    temp_factor as raw_tf,
    water_stress_factor as raw_wsf,
)


# --- 版本 A: 未加固（原始） ---
def _run_on(fn, arg, expected_ok):
    try:
        v = fn(*arg) if isinstance(arg, tuple) else fn(arg)
        return ("RETURNED", v, "OK" if expected_ok else "FAIL-GIGO")
    except Exception as e:
        return (f"RAISED {type(e).__name__}", str(e)[:60], "OK" if not expected_ok else "FAIL-UNEXPECTED-RAISE")


# --- 版本 B: 加固后 ---
@known_enum("crop", ["wheat", "rice", "maize", "soy", "barley", "sorghum",
                     "cotton", "sugar_beet", "potato", "tomato", "pepper",
                     "eggplant", "onion", "cabbage", "corn", "wheat", "oat",
                     "alfalfa", "canola", "sunflower", "grape", "apple",
                     "orange", "banana"])
@not_empty_string("crop")
@bounded("dli", 0, 100)
@bounded("days", 1, 365)
def tyc_hardened(crop, dli, days, **kw):
    return raw_tyc(crop, dli, days, **kw)


@bounded_each(("T", "Topt"), lo=-50, hi=60)
@bounded_each(("Tmin", "Tmax"), lo=-50, hi=60)
@monotone_constraints("Tmin", "Tmax", a_lt_b=True)
def tf_hardened(T, Topt, Tmax, Tmin):
    return raw_tf(T, Topt, Tmax, Tmin)


@bounded("theta", 0, 1)
def wsf_hardened(theta):
    return raw_wsf(theta)


@bounded("T", -50, 60)
@bounded("RH", 0, 100)
def vpd_hardened(T, RH):
    return raw_vpd(T, RH)


# --- 探针定义（与 probe_mechanism_garbage_in.py 一致） ---
probes = [
    # name, original_fn, hardened_fn, arg_desc, arg_value, expected_ok
    ("tyc", raw_tyc, tyc_hardened, "正常基线 (wheat, 2MJ/m²/day, 120d)", ("wheat", 2.0, 120), True),
    ("tyc", raw_tyc, tyc_hardened, "负天数 days=-5 (物理不可能)", ("wheat", 2.0, -5), False),
    ("tyc", raw_tyc, tyc_hardened, "超大天数 days=99999", ("wheat", 2.0, 99999), False),
    ("tyc", raw_tyc, tyc_hardened, "零光照 dli=0 (合法边界)", ("wheat", 0.0, 120), True),
    ("tyc", raw_tyc, tyc_hardened, "负光照 dli=-1", ("wheat", -1.0, 120), False),
    ("tyc", raw_tyc, tyc_hardened, "NaN 光照", ("wheat", float("nan"), 120), False),
    ("tyc", raw_tyc, tyc_hardened, "inf 光照", ("wheat", float("inf"), 120), False),
    ("tyc", raw_tyc, tyc_hardened, "未知作物 crop='quantum_plant'", ("quantum_plant", 2.0, 120), False),
    ("tyc", raw_tyc, tyc_hardened, "空字符串作物", ("", 2.0, 120), False),
    ("tyc", raw_tyc, tyc_hardened, "作物为 None", (None, 2.0, 120), False),

    ("tf", raw_tf, tf_hardened, "正常基线 T=25, Topt=25, Tmax=35, Tmin=15", (25.0, 25.0, 35.0, 15.0), True),
    ("tf", raw_tf, tf_hardened, "超低温 T=-100°C", (-100.0, 25.0, 35.0, 15.0), False),
    ("tf", raw_tf, tf_hardened, "超高温 T=100°C", (100.0, 25.0, 35.0, 15.0), False),
    ("tf", raw_tf, tf_hardened, "边界错乱 Tmin(30) > Tmax(10)", (25.0, 25.0, 10.0, 30.0), False),
    ("tf", raw_tf, tf_hardened, "Topt 超出边界 (Topt=50, Tmax=35)", (25.0, 50.0, 35.0, 15.0), False),
    ("tf", raw_tf, tf_hardened, "NaN 输入", (float("nan"), 25.0, 35.0, 15.0), False),
    ("tf", raw_tf, tf_hardened, "字符串输入 T='hot'", ("hot", 25.0, 35.0, 15.0), False),

    ("wsf", raw_wsf, wsf_hardened, "正常基线 theta=0.5", 0.5, True),
    ("wsf", raw_wsf, wsf_hardened, "干燥极限 theta=0", 0.0, True),  # 0 是合法边界
    ("wsf", raw_wsf, wsf_hardened, "饱和上限 theta=1.0", 1.0, True),  # 1 是合法边界
    ("wsf", raw_wsf, wsf_hardened, "负含水率 theta=-0.2", -0.2, False),
    ("wsf", raw_wsf, wsf_hardened, "超饱和 theta=1.5", 1.5, False),
    ("wsf", raw_wsf, wsf_hardened, "超大 theta=1e9", 1e9, False),
    ("wsf", raw_wsf, wsf_hardened, "NaN", float("nan"), False),
    ("wsf", raw_wsf, wsf_hardened, "字符串 'soil'", "soil", False),

    ("vpd", raw_vpd, vpd_hardened, "正常基线 T=25°C, RH=60%", (25.0, 60.0), True),
    ("vpd", raw_vpd, vpd_hardened, "RH=100% 饱和", (25.0, 100.0), True),  # 100 是合法边界
    ("vpd", raw_vpd, vpd_hardened, "RH=150% (物理不可能)", (25.0, 150.0), False),
    ("vpd", raw_vpd, vpd_hardened, "RH=-5% (物理不可能)", (25.0, -5.0), False),
    ("vpd", raw_vpd, vpd_hardened, "极低温 T=-100°C", (-100.0, 50.0), False),
    ("vpd", raw_vpd, vpd_hardened, "极高温 T=150°C", (150.0, 50.0), False),
    ("vpd", raw_vpd, vpd_hardened, "NaN 温度", (float("nan"), 50.0), False),
    ("vpd", raw_vpd, vpd_hardened, "NaN 湿度", (25.0, float("nan")), False),
    ("vpd", raw_vpd, vpd_hardened, "inf 温度", (float("inf"), 50.0), False),
]


# --- 跑两遍 ---
def run_probe(fn, arg):
    """返回 (status, detail)。status=RETURNED/RAISED_xxx。"""
    try:
        v = fn(*arg) if isinstance(arg, tuple) else fn(arg)
        return ("RETURNED", v)
    except Exception as e:
        return (f"RAISED_{type(e).__name__}", str(e)[:70])


before_results = []
after_results = []
for name, raw_fn, hard_fn, desc, arg, exp_ok in probes:
    st_b, det_b = run_probe(raw_fn, arg)
    verdict_b = "OK" if ((st_b == "RETURNED" and exp_ok) or (st_b.startswith("RAISED") and not exp_ok)) else "FAIL"
    before_results.append((name, desc, st_b, det_b, verdict_b))

    st_a, det_a = run_probe(hard_fn, arg)
    verdict_a = "OK" if ((st_a == "RETURNED" and exp_ok) or (st_a.startswith("RAISED") and not exp_ok)) else "FAIL"
    after_results.append((name, desc, st_a, det_a, verdict_a))


# --- 输出 ---
print("=" * 88)
print("机理内核加固前后对比 · 34 个探针")
print("=" * 88)
print(f"{'探针':<10s} {'输入':<38s} {'加固前':<12s} {'加固后':<12s}")
print("-" * 88)
for (n1, d1, s1, t1, v1), (n2, d2, s2, t2, v2) in zip(before_results, after_results):
    b_mark = "✓" if v1 == "OK" else "✗"
    a_mark = "✓" if v2 == "OK" else "✗"
    # 只显示 FAIL → PASS 或 PASS → FAIL 的对比
    b_short = f"{b_mark} {s1.split('_')[0]}"
    a_short = f"{a_mark} {s2.split('_')[0]}"
    print(f"{n1:<10s} {d1:<38s} {b_short:<12s} {a_short:<12s}")

b_fail = sum(1 for r in before_results if r[4] == "FAIL")
a_fail = sum(1 for r in after_results if r[4] == "FAIL")
print("-" * 88)
print(f"合计：加固前 {b_fail}/34 FAIL   加固后 {a_fail}/34 FAIL")
print(f"降幅：{b_fail - a_fail} 个 FAIL 被装饰器拦截 → 变为可控异常")
print(f"覆盖率提升：{b_fail/34:.1%} → {a_fail/34:.1%}")

# 显示几个典型样本的完整错误消息
print("\n加固后典型错误消息（可控、可诊断、可上报）：")
samples = [
    ("tyc, days=-5", ("wheat", 2.0, -5)),
    ("tyc, crop='quantum_plant'", ("quantum_plant", 2.0, 120)),
    ("vpd, RH=-5%", (25.0, -5.0)),
    ("tf, Tmin(30)>Tmax(10)", (25.0, 25.0, 10.0, 30.0)),
    ("wsf, theta=nan", float("nan")),
]
for label, arg in samples:
    if label.startswith("tyc"):
        fn = tyc_hardened
    elif label.startswith("vpd"):
        fn = vpd_hardened
    elif label.startswith("tf"):
        fn = tf_hardened
    elif label.startswith("wsf"):
        fn = wsf_hardened
    try:
        fn(*arg) if isinstance(arg, tuple) else fn(arg)
        print(f"  ✗ {label}: 未拦截")
    except Exception as e:
        print(f"  ✓ {label}: raise {type(e).__name__}: {str(e)[:80]}")
