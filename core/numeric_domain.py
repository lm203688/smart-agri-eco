"""
core/numeric_domain.py —— 机理层数值契约装饰器

解决 H3 硬伤：4 个机理核心函数（theoretical_yield_cap / temp_factor /
water_stress_factor / vpd）**0/4 有边界校验**，34 个探针 27 FAIL-GIGO（79.4%）。

实测失效样本（可运行 scripts/probe_mechanism_garbage_in.py 复核）：
- theoretical_yield_cap(days=-5) → 返回 -3.77 kg/㎡（负产量）
- theoretical_yield_cap(days=99999) → 返回 75,311 kg/㎡（超地球作物上限 400 倍）
- theoretical_yield_cap(crop='quantum_plant') → 静默给默认值 90.37
- vpd(RH=-5%) → 返回 3.17 kPa（负湿度算出正蒸腾压力，物理悖论）
- water_stress_factor(theta=nan) → 返回 0.0（NaN 被静默当作 0）

设计原则：
1. 纯标准库装饰器，用 inspect.signature 做参数解析
2. 支持位置参数、关键字参数、默认值
3. 复合装饰：一个函数可叠多个（如 @bounded @non_negative）
4. 明确的错误类型：InputError（参数错）、DataError（数据错）
5. NaN / inf 默认拒绝（除非显式允许）
6. 类型不匹配（如字符串）显式抛 TypeError，不静默转换
"""
from __future__ import annotations

import inspect
import math
from functools import wraps
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# 错误类型（配合 H6 分层异常契约）
# ---------------------------------------------------------------------------
class InputError(ValueError):
    """参数非法：类型错、超界、越界、枚举外。"""


class DataError(ValueError):
    """数据错：NaN / inf / 未闭合枚举 / 上游数据污染。"""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _resolve_value(fn: Callable, name: str, args, kwargs) -> Any:
    """按参数名解析实际值：优先 kwargs，其次位置参数，最后默认值。"""
    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError):
        return kwargs.get(name)
    params = sig.parameters
    if name not in params:
        # 支持 *args/**kwargs 情况，直接返回 kwargs 里的值
        return kwargs.get(name)
    p = params[name]
    # 1. 显式关键字传入
    if name in kwargs:
        return kwargs[name]
    # 2. 位置参数传入
    if p.kind == p.POSITIONAL_ONLY or p.kind == p.POSITIONAL_OR_KEYWORD:
        pos_idx = _positional_index(params, name)
        if pos_idx is not None and pos_idx < len(args):
            return args[pos_idx]
    # 3. 默认值
    if p.default is not p.empty:
        return p.default
    # 4. 无值
    raise KeyError(name)


def _positional_index(params: dict, name: str) -> int | None:
    """计算 name 在位置参数中的索引（跳过 *args、**kwargs、keyword-only）。"""
    idx = 0
    for pname, p in params.items():
        if pname == name:
            return idx
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
            idx += 1
        elif p.kind == p.VAR_POSITIONAL:
            # *args 之后不能再接位置参数
            return None
    return None


# ---------------------------------------------------------------------------
# 核心契约装饰器
# ---------------------------------------------------------------------------
def finite(*names: str, allow_inf: bool = False, allow_nan: bool = False):
    """参数必须是数值且有限（拒绝 NaN/inf），可选允许 inf/nan。"""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            for n in names:
                v = _resolve_value(fn, n, args, kwargs)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise InputError(
                        f"{fn.__name__}.{n}: expected numeric, got {type(v).__name__}"
                    )
                if not allow_nan and math.isnan(v):
                    raise DataError(f"{fn.__name__}.{n}: NaN not allowed, got {v!r}")
                if not allow_inf and math.isinf(v):
                    raise DataError(f"{fn.__name__}.{n}: ±inf not allowed, got {v!r}")
            return fn(*args, **kwargs)
        return w
    return deco


def bounded(name: str, lo: float, hi: float, *, allow_nan: bool = False, allow_inf: bool = False):
    """
    参数必须在 [lo, hi] 闭区间内。默认拒绝 NaN/inf。

    注意：NaN 与任何比较运算都是 False，因此必须先显式检查；
    bounded 的数值范围检查**不**通过比较能捕捉 NaN，因此本装饰器
    强制先做 NaN/inf 检查（等价于 finite）。
    """
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            v = _resolve_value(fn, name, args, kwargs)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise InputError(
                    f"{fn.__name__}.{name}: expected numeric, got {type(v).__name__}"
                )
            if not allow_nan and math.isnan(v):
                raise DataError(f"{fn.__name__}.{name}: NaN not allowed")
            if not allow_inf and math.isinf(v):
                raise DataError(f"{fn.__name__}.{name}: ±inf not allowed")
            if not (lo <= v <= hi):
                raise InputError(
                    f"{fn.__name__}.{name}={v!r} out of [{lo}, {hi}]"
                )
            return fn(*args, **kwargs)
        return w
    return deco


def non_negative(*names: str):
    """参数必须 >= 0（拒绝 NaN/inf）。"""
    return bounded_each(names, lo=0, hi=None)


def positive(*names: str):
    """参数必须 > 0（严格正，拒绝 0、NaN、inf）。"""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            for n in names:
                v = _resolve_value(fn, n, args, kwargs)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise InputError(
                        f"{fn.__name__}.{n}: expected numeric, got {type(v).__name__}"
                    )
                if math.isnan(v) or math.isinf(v):
                    raise DataError(f"{fn.__name__}.{n}: not finite, got {v!r}")
                if v <= 0:
                    raise InputError(f"{fn.__name__}.{n}={v!r} must be > 0")
            return fn(*args, **kwargs)
        return w
    return deco


def bounded_each(names: Iterable[str], *, lo: float | None = None, hi: float | None = None):
    """对多个参数施加同一条 [lo, hi] 约束。"""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            for n in names:
                v = _resolve_value(fn, n, args, kwargs)
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise InputError(
                        f"{fn.__name__}.{n}: expected numeric, got {type(v).__name__}"
                    )
                if math.isnan(v) or math.isinf(v):
                    raise DataError(f"{fn.__name__}.{n}: not finite, got {v!r}")
                if lo is not None and v < lo:
                    raise InputError(f"{fn.__name__}.{n}={v!r} below minimum {lo}")
                if hi is not None and v > hi:
                    raise InputError(f"{fn.__name__}.{n}={v!r} above maximum {hi}")
            return fn(*args, **kwargs)
        return w
    return deco


def known_enum(name: str, allowed: Iterable[str]):
    """参数必须是 allowed 集合中的字符串（大小写敏感）。"""
    allowed_set = set(allowed)

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            v = _resolve_value(fn, name, args, kwargs)
            if not isinstance(v, str):
                raise InputError(
                    f"{fn.__name__}.{name}: expected str, got {type(v).__name__}"
                )
            if v not in allowed_set:
                sample = sorted(allowed_set)[:8]
                more = len(allowed_set) - len(sample)
                suffix = f", +{more} more" if more > 0 else ""
                raise InputError(
                    f"{fn.__name__}.{name}={v!r} not in known set {sample}{suffix}"
                )
            return fn(*args, **kwargs)
        return w
    return deco


def not_none(*names: str):
    """参数不得为 None（None 会污染所有下游计算）。"""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            for n in names:
                v = _resolve_value(fn, n, args, kwargs)
                if v is None:
                    raise InputError(f"{fn.__name__}.{n}: must not be None")
            return fn(*args, **kwargs)
        return w
    return deco


def not_empty_string(*names: str):
    """字符串参数不得为空或全空白。"""
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            for n in names:
                v = _resolve_value(fn, n, args, kwargs)
                if not isinstance(v, str):
                    raise InputError(
                        f"{fn.__name__}.{n}: expected str, got {type(v).__name__}"
                    )
                if not v.strip():
                    raise InputError(f"{fn.__name__}.{n}: must not be empty/whitespace")
            return fn(*args, **kwargs)
        return w
    return deco


def monotone_constraints(name_a: str, name_b: str, *, a_le_b: bool = False, a_lt_b: bool = False):
    """参数关系约束：a <= b 或 a < b。用于拒绝 Tmin > Tmax 这类边界错乱。"""
    if not (a_le_b or a_lt_b):
        raise ValueError("monotone_constraints: at least one of a_le_b / a_lt_b must be True")

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def w(*args, **kwargs):
            va = _resolve_value(fn, name_a, args, kwargs)
            vb = _resolve_value(fn, name_b, args, kwargs)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                if a_le_b and not (va <= vb):
                    raise InputError(
                        f"{fn.__name__}: {name_a}={va!r} must be <= {name_b}={vb!r}"
                    )
                if a_lt_b and not (va < vb):
                    raise InputError(
                        f"{fn.__name__}: {name_a}={va!r} must be < {name_b}={vb!r}"
                    )
            return fn(*args, **kwargs)
        return w
    return deco


# ---------------------------------------------------------------------------
# 自测：python -m core.numeric_domain
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    def _check(fn, *args, **kwargs):
        """调用 fn 并返回结果；用于测试。"""
        return fn(*args, **kwargs)

    @bounded("T", -50, 60)
    def my_temp(T: float) -> float:
        return T * 2

    @known_enum("crop", ["wheat", "rice", "maize"])
    @not_empty_string("crop")
    def my_crop(crop: str) -> str:
        return f"crop={crop}"

    @monotone_constraints("Tmin", "Tmax", a_lt_b=True)
    @bounded_each(("Tmin", "Tmax"), lo=-50, hi=60)
    def my_range(Tmin: float, Tmax: float) -> float:
        return Tmax - Tmin

    @bounded("theta", 0, 1)
    def my_theta(theta: float) -> float:
        return theta

    passed = 0

    # 1. 正常值
    assert my_temp(25) == 50
    assert my_crop("wheat") == "crop=wheat"
    assert my_range(15, 35) == 20
    assert my_theta(0.5) == 0.5
    passed += 4
    print(f"✓ 1-4. 正常值 4 项通过 (累计 {passed})")

    # 2. 边界值：刚好在 [lo, hi] 端点
    assert my_temp(-50) == -100
    assert my_temp(60) == 120
    assert my_theta(0) == 0
    assert my_theta(1) == 1
    passed += 4
    print(f"✓ 5-8. 边界值 4 项通过 (累计 {passed})")

    # 3. 超界应抛 InputError
    for v in (-100, 100, 1e9):
        try:
            my_temp(v)
            raise AssertionError(f"应该抛异常：my_temp({v})")
        except InputError:
            pass
    passed += 3
    print(f"✓ 9-11. 超界 3 项正确抛 InputError (累计 {passed})")

    # 4. NaN/inf 应抛 DataError
    for v in (float("nan"), float("inf"), float("-inf")):
        try:
            my_temp(v)
            raise AssertionError(f"应该抛异常：my_temp({v!r})")
        except DataError:
            pass
    passed += 3
    print(f"✓ 12-14. NaN/inf 3 项正确抛 DataError (累计 {passed})")

    # 5. 类型错应抛 InputError
    for v in ("hot", None, [1], True):
        try:
            my_temp(v)
            raise AssertionError(f"应该抛异常：my_temp({v!r})")
        except InputError:
            pass
    passed += 4
    print(f"✓ 15-18. 类型错 4 项正确抛 InputError (累计 {passed})")

    # 6. 未知枚举应抛 InputError
    try:
        my_crop("quantum_plant")
        raise AssertionError("应该抛异常：未知作物")
    except InputError as e:
        assert "quantum_plant" in str(e)
        passed += 1
    print(f"✓ 19. 未知作物 'quantum_plant' 正确抛 InputError (累计 {passed})")

    # 7. 空字符串应抛 InputError
    try:
        my_crop("")
        raise AssertionError("应该抛异常：空字符串")
    except InputError:
        passed += 1
    print(f"✓ 20. 空字符串正确抛 InputError (累计 {passed})")

    # 8. Tmin > Tmax 应抛 InputError
    try:
        my_range(30, 10)
        raise AssertionError("应该抛异常：Tmin > Tmax")
    except InputError as e:
        assert "must be <" in str(e)
        passed += 1
    print(f"✓ 21. Tmin(30) > Tmax(10) 正确抛 InputError (累计 {passed})")

    # 9. 位置参数 + 关键字参数混合
    @bounded("x", 0, 10)
    @bounded("y", 0, 100)
    def mixed(x: float, y: float) -> float:
        return x + y

    assert mixed(5, 50) == 55
    assert mixed(y=50, x=5) == 55
    assert mixed(5, y=50) == 55
    passed += 3
    print(f"✓ 22-24. 位置/关键字/混合参数 3 项通过 (累计 {passed})")

    # 10. 默认值也应校验
    @bounded("v", 0, 100)
    def with_default(v: float = 50) -> float:
        return v
    assert with_default() == 50
    try:
        with_default(v=-1)
        raise AssertionError("应该抛异常：超界默认值")
    except InputError:
        pass
    passed += 2
    print(f"✓ 25-26. 默认值 + 超界默认值 2 项通过 (累计 {passed})")

    # 11. 错误类型层级
    try:
        my_temp(100)
    except InputError as e:
        assert isinstance(e, ValueError), "InputError 应是 ValueError 子类"
        passed += 1
    try:
        my_temp(float("nan"))
    except DataError as e:
        assert isinstance(e, ValueError), "DataError 应是 ValueError 子类"
        passed += 1
    print(f"✓ 27-28. 错误类型层级正确（InputError/DataError → ValueError） (累计 {passed})")

    print(f"\n数值契约装饰器全部 {passed} 项自测通过。")
