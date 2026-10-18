#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_mechanism_domain.py —— 机理内核边界契约的正式单测（S1.4）

来源：把 scripts/probe_mechanism_garbage_in.py 的 34 个"垃圾进垃圾出"探针
      转为 unittest 契约测试。原探针脚本只打印 verdict、不参与门禁失败；
      本文件让每一个契约在 CI 里**必须**成立。

被测函数与真实签名（以源码为准，勿照抄路线图里的伪代码）：
    theoretical_yield_cap(crop: str, dli_mj_m2_d: float, days: int) -> float
    temp_factor(t_c: float, t_opt: float, t_max: float, t_base: float = 5.0) -> float
    water_stress_factor(theta: float, theta_fc: float = 0.10) -> float
    vpd(temp_c: float, humidity_pct: float) -> float

契约分两类：
  RAISE  —— 输入物理不可能，必须抛 ValueError（InputError / DataError 均是其子类）
  RETURN —— 输入合法（含物理边界），必须返回有限值且落在语义范围内

关于探针脚本的口径差异（重要，避免误读）：
  probe_mechanism_garbage_in.py 的判定是
      verdict = OK if RAISED or (RETURNED and expected_ok)
  即 **expected_ok=True 的探针即使抛异常也算 OK**。这导致两个探针被"宽容放行"：
    - theoretical_yield_cap(wheat, 0.0, 120)：零光照，实际抛 InputError
      （@positive 要求 > 0）
    - water_stress_factor(1.0)：实际抛 InputError（@bounded 上限是 0.6，
      不是田间持水量 1.0）
  本文件按**实测行为**写断言，并在此显式记录，不沿用探针脚本的宽容口径。

运行：
    python scripts/test_mechanism_domain.py
    python -m unittest scripts.test_mechanism_domain -v
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.agriworld_lite import (  # noqa: E402
    temp_factor,
    theoretical_yield_cap,
    water_stress_factor,
)
from engine.derived import vpd  # noqa: E402

NAN = float("nan")
INF = float("inf")

FUNCS = {
    "tyc": theoretical_yield_cap,
    "tf": temp_factor,
    "wsf": water_stress_factor,
    "vpd": vpd,
}

# ---------------------------------------------------------------------------
# 34 个契约用例（逐条实测确认，2026-10-18）
# ---------------------------------------------------------------------------
# (id, fn, args, 说明, expect, exc, bounds)
#   expect = "raise" | "return"
#   exc    = 期望异常类名（仅 raise 时有效）；"ValueError" 表示仅要求基类
#   bounds = (lo, hi) 返回值的语义范围；exact=(v,) 表示要求精确相等
PROBES = [
    # --- 1. theoretical_yield_cap(crop, dli_mj_m2_d, days) ---
    ("T01", "tyc", ("wheat", 2.0, 120), "正常基线：小麦 / 2MJ·m⁻²·d⁻¹ / 120 天",
     "return", None, (0.0, 1e6)),
    ("T02", "tyc", ("wheat", 2.0, -5), "负天数：生长周期不可能为负",
     "raise", "InputError", None),
    ("T03", "tyc", ("wheat", 2.0, 99999), "超大天数：超出任何作物全生长期",
     "raise", "InputError", None),
    ("T04", "tyc", ("wheat", 0.0, 120), "零光照：@positive 要求 > 0（探针脚本曾宽容放行）",
     "raise", "InputError", None),
    ("T05", "tyc", ("wheat", -1.0, 120), "负光照：物理不可能",
     "raise", "InputError", None),
    ("T06", "tyc", ("wheat", NAN, 120), "NaN 光照：禁止静默当 0",
     "raise", "DataError", None),
    ("T07", "tyc", ("wheat", INF, 120), "inf 光照：禁止静默返回极大值",
     "raise", "DataError", None),
    ("T08", "tyc", ("quantum_plant", 2.0, 120), "未知作物：禁止静默给默认值",
     "raise", "InputError", None),
    ("T09", "tyc", ("", 2.0, 120), "空字符串作物",
     "raise", "InputError", None),
    ("T10", "tyc", (None, 2.0, 120), "作物为 None",
     "raise", "InputError", None),

    # --- 2. temp_factor(t_c, t_opt, t_max, t_base) ---
    ("T11", "tf", (25.0, 25.0, 35.0, 15.0), "正常基线：恰在最适温度",
     "return", None, (0.0, 1.0)),
    ("T12", "tf", (-100.0, 25.0, 35.0, 15.0), "超低温：地球外温度",
     "raise", "InputError", None),
    ("T13", "tf", (100.0, 25.0, 35.0, 15.0), "超高温：沸水",
     "raise", "InputError", None),
    ("T14", "tf", (25.0, 25.0, 10.0, 30.0), "边界错乱：t_base(30) > t_max(10)",
     "raise", "InputError", None),
    ("T15", "tf", (25.0, 50.0, 35.0, 15.0), "最适温度越上限：t_opt(50) > t_max(35)",
     "raise", "ValueError", None),
    ("T16", "tf", (NAN, 25.0, 35.0, 15.0), "NaN 输入",
     "raise", "DataError", None),
    ("T17", "tf", ("hot", 25.0, 35.0, 15.0), "字符串输入：禁止静默转换",
     "raise", "InputError", None),

    # --- 3. water_stress_factor(theta, theta_fc=0.10) ---
    ("T18", "wsf", (0.5,), "正常基线：土壤含水率 0.5",
     "return", None, (0.0, 1.0)),
    ("T19", "wsf", (0.0,), "干燥极限：theta=0 合法边界，返回 0",
     "return", None, (0.0, 1.0)),
    ("T20", "wsf", (1.0,), "theta=1.0：超契约上限 0.6（探针脚本曾宽容放行）",
     "raise", "InputError", None),
    ("T21", "wsf", (-0.2,), "负含水率：物理不可能",
     "raise", "InputError", None),
    ("T22", "wsf", (1.5,), "超饱和",
     "raise", "InputError", None),
    ("T23", "wsf", (1e9,), "极端大值",
     "raise", "InputError", None),
    ("T24", "wsf", (NAN,), "NaN：禁止静默当 0",
     "raise", "DataError", None),
    ("T25", "wsf", ("soil",), "字符串输入",
     "raise", "InputError", None),

    # --- 4. vpd(temp_c, humidity_pct) ---
    ("T26", "vpd", (25.0, 60.0), "正常基线：25℃ / 60%",
     "return", None, (0.0, 10.0)),
    ("T27", "vpd", (25.0, 100.0), "饱和湿度：VPD 必为 0",
     "return", None, (0.0, 0.0)),
    ("T28", "vpd", (25.0, 150.0), "RH=150%：物理不可能",
     "raise", "InputError", None),
    ("T29", "vpd", (25.0, -5.0), "RH=-5%：禁止算出正的蒸腾压力",
     "raise", "InputError", None),
    ("T30", "vpd", (-100.0, 50.0), "极低温",
     "raise", "InputError", None),
    ("T31", "vpd", (150.0, 50.0), "极高温",
     "raise", "InputError", None),
    ("T32", "vpd", (NAN, 50.0), "NaN 温度",
     "raise", "DataError", None),
    ("T33", "vpd", (25.0, NAN), "NaN 湿度",
     "raise", "DataError", None),
    ("T34", "vpd", (INF, 50.0), "inf 温度",
     "raise", "DataError", None),
]

EXC_CLASSES = {
    "InputError": (ValueError,),
    "DataError": (ValueError,),
    "ValueError": (ValueError,),
}


def _short_desc(pid: str, fn: str, args: Tuple) -> str:
    return f"{pid} {fn}{args!r}"


def _make_test(pid, fn_key, args, desc, expect, exc, bounds):
    fn: Callable = FUNCS[fn_key]

    def test(self):
        if expect == "return":
            v = fn(*args)
            self.assertIsInstance(v, (int, float), _short_desc(pid, fn_key, args))
            self.assertTrue(
                math.isfinite(v),
                f"{_short_desc(pid, fn_key, args)}：期望有限值，实际 {v!r}",
            )
            if bounds is not None:
                lo, hi = bounds
                self.assertGreaterEqual(
                    v, lo,
                    f"{_short_desc(pid, fn_key, args)}：{v} 低于下界 {lo}",
                )
                self.assertLessEqual(
                    v, hi,
                    f"{_short_desc(pid, fn_key, args)}：{v} 高于上界 {hi}",
                )
            return

        # expect == "raise"
        try:
            fn(*args)
        except ValueError as e:
            if exc and exc != "ValueError":
                self.assertEqual(
                    type(e).__name__, exc,
                    f"{_short_desc(pid, fn_key, args)}：期望 {exc}，实际 {type(e).__name__}"
                )
            self.assertTrue(
                str(e).strip(),
                f"{_short_desc(pid, fn_key, args)}：异常消息为空，无法向用户解释原因",
            )
            return
        self.fail(
            f"{_short_desc(pid, fn_key, args)}：{desc} —— "
            f"输入物理不可能但函数未抛异常（GIGO）"
        )

    name = "test_%s_%s" % (pid.lower(), desc.split("：")[0].strip().replace(" ", "_")
                           .replace("，", "_")[:28])
    test.__name__ = name
    test.__doc__ = f"{pid} {desc}"
    return test


def _install_tests() -> None:
    """把 34 个契约动态装进 TestCase 类（每个探针一个测试方法）。"""
    cls = unittest.TestCase
    for pid, fn_key, args, desc, expect, exc, bounds in PROBES:
        method = _make_test(pid, fn_key, args, desc, expect, exc, bounds)
        if not hasattr(cls, method.__name__):  # pragma: no cover  防御重名
            setattr(MechanismDomainContract, method.__name__, method)


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------
class MechanismDomainContract(unittest.TestCase):
    """机理内核 4 个函数的输入契约：不可接受的输入必须 raise，合法输入必须返回有限值。"""

    @classmethod
    def setUpClass(cls):
        # 守卫：本文件必须恰好覆盖 34 个探针（与 probe_mechanism_garbage_in.py 对齐）
        super().setUpClass()
        assert len(PROBES) == 34, f"探针数应为 34，实际 {len(PROBES)}"
        ids = [p[0] for p in PROBES]
        assert len(set(ids)) == 34, "探针 id 有重复"
        by_fn: dict = {}
        for p in PROBES:
            by_fn[p[1]] = by_fn.get(p[1], 0) + 1
        assert len(by_fn) == 4, f"应覆盖 4 个函数，实际 {len(by_fn)}"


_install_tests()


if __name__ == "__main__":
    unittest.main(verbosity=2)
