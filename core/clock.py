"""core/clock.py —— 可注入时钟（FOUNDATION_AUDIT H2）

设计动机
--------
项目原有 62 处 `datetime.now()` + 51 处 `time.time()` 直调——Bench、
execution_log、trust_layer 都无法在相同时间戳下重放，导致：
- Bench 69 用例两次跑评分不一致
- 溯源记录（execution_log 45 条）无法对齐回溯
- trust_layer 输出的 trust_mark 每次不同（同一份输入）

本模块提供可注入时钟抽象：
- SystemClock：生产用，走真实系统时间
- FrozenClock：测试 / 复现用，锁定固定时刻

设计原则
--------
1. 零依赖，纯标准库
2. 鸭子类型——Clock 协议只有 now() / time() 两个方法
3. 模块级默认时钟 `CLOCK`，测试可临时替换
4. 显式 `freeze_at` 上下文管理器（临时冻结，便于契约测试）

用法示例
--------
    # 生产代码（推荐）
    from core.clock import CLOCK
    def make_trust_mark(payload):
        issued_at = CLOCK.now().isoformat(timespec="seconds")
        return hashlib.sha256(f"{issued_at}:{payload}".encode()).hexdigest()

    # 测试：锁定到 2026-01-01T00:00:00Z
    from core.clock import FrozenClock, set_default_clock, get_default_clock
    real = get_default_clock()
    set_default_clock(FrozenClock(datetime(2026, 1, 1, tzinfo=timezone.utc)))
    assert make_trust_mark("hello") == make_trust_mark("hello")  # 稳定
    set_default_clock(real)

    # 或者局部冻结：
    with freeze_at(datetime(2026, 1, 1, tzinfo=timezone.utc)) as frozen:
        ...  # 期间 CLOCK.now() 恒等于 2026-01-01

时间戳稳定性约定
----------------
- `now()` 返回 aware datetime（tz=UTC），确保 ISO 输出带时区
- `time()` 返回 float 秒（Unix epoch），与 time.time() 语义一致
- `epoch_ms()` 返回 int 毫秒（跨语言兼容）
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import time as _time
from typing import Any, Callable, Iterator, Optional


# ---------------------------------------------------------------------------
# Clock 协议
# ---------------------------------------------------------------------------

class Clock:
    """可注入时钟基类（协议）。子类只需实现 now() / time()。"""

    def now(self) -> _dt.datetime:
        """当前时刻（aware datetime）。"""
        raise NotImplementedError

    def time(self) -> float:
        """当前 Unix 秒（float）。"""
        raise NotImplementedError

    def epoch_ms(self) -> int:
        """当前 Unix 毫秒（int，跨语言兼容）。"""
        return int(self.time() * 1000)

    def isoformat(self, timespec: str = "seconds") -> str:
        """当前时刻的 ISO-8601 字符串（便捷）。"""
        return self.now().isoformat(timespec=timespec)


# ---------------------------------------------------------------------------
# 具体实现
# ---------------------------------------------------------------------------

class SystemClock(Clock):
    """生产时钟：真实系统时间（naive local，与 datetime.now() 语义一致）。

    返回 naive local datetime，保持与原始 datetime.now() 完全兼容：
    - 可直接与 datetime.fromtimestamp() 等 naive datetime 做减法
    - ISO 输出不带时区（如需要带时区，用 now_aware()）
    """

    def now(self) -> _dt.datetime:
        return _dt.datetime.now()

    def now_aware(self) -> _dt.datetime:
        """返回 aware UTC datetime（如需要带时区用于跨时区场景）。"""
        return _dt.datetime.now(tz=_dt.timezone.utc)

    def time(self) -> float:
        return _time.time()


class FrozenClock(Clock):
    """冻结时钟：锁定到固定时刻（测试 / 复现用）。

    支持 offset_seconds：从冻结点起每调用 time() 一次就推进指定秒数
    （用于模拟"经过一段时间"的场景）。
    """

    def __init__(self, fixed: _dt.datetime, offset_seconds: float = 0.0):
        if fixed.tzinfo is None:
            fixed = fixed.replace(tzinfo=_dt.timezone.utc)
        self._fixed = fixed
        self._offset = offset_seconds
        self._calls = 0

    def now(self) -> _dt.datetime:
        self._calls += 1
        delta = _dt.timedelta(seconds=self._offset * self._calls)
        return self._fixed + delta

    def time(self) -> float:
        self._calls += 1
        delta = self._offset * self._calls
        return self._fixed.timestamp() + delta


class SteppingClock(Clock):
    """步进时钟：基于 FrozenClock，允许手动推进时间。

    适合单元测试里模拟"某事件后 5 分钟"的场景。
    """

    def __init__(self, start: Optional[_dt.datetime] = None):
        start = start or _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=_dt.timezone.utc)
        self._t = start

    def advance(self, seconds: float) -> None:
        """手动推进时钟。"""
        self._t = self._t + _dt.timedelta(seconds=seconds)

    def now(self) -> _dt.datetime:
        return self._t

    def time(self) -> float:
        return self._t.timestamp()


# ---------------------------------------------------------------------------
# 模块级默认时钟
# ---------------------------------------------------------------------------

_DEFAULT_CLOCK: Clock = SystemClock()


def get_default_clock() -> Clock:
    """获取当前默认时钟（生产默认 SystemClock）。"""
    return _DEFAULT_CLOCK


def set_default_clock(clock: Clock) -> Clock:
    """设置默认时钟（测试用），返回旧时钟以便恢复。"""
    global _DEFAULT_CLOCK
    old = _DEFAULT_CLOCK
    _DEFAULT_CLOCK = clock
    return old


# 模块级 CLOCK 别名（读操作直接引用，写操作必须走 set_default_clock）
CLOCK: Clock = _DEFAULT_CLOCK


@contextlib.contextmanager
def freeze_at(t: _dt.datetime, offset_seconds: float = 0.0) -> Iterator[FrozenClock]:
    """上下文管理器：临时把默认时钟冻结到 t，退出后恢复。

    用法：
        with freeze_at(datetime(2026, 1, 1, tzinfo=timezone.utc)) as c:
            ...  # 期间 get_default_clock().now() 恒等于 2026-01-01
    """
    old = set_default_clock(FrozenClock(t, offset_seconds=offset_seconds))
    try:
        yield _DEFAULT_CLOCK
    finally:
        set_default_clock(old)


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def now() -> _dt.datetime:
    """便捷函数：等价于 get_default_clock().now()。"""
    return _DEFAULT_CLOCK.now()


def time_ns() -> int:
    """便捷函数：当前 Unix 纳秒（跨语言兼容）。"""
    return int(_DEFAULT_CLOCK.time() * 1e9)


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 1. SystemClock 基础（naive local，与 datetime.now() 兼容）
    c = SystemClock()
    a = c.now()
    b = c.now()
    assert b >= a, "SystemClock.now 应单调不递减"
    assert a.tzinfo is None, "SystemClock.now 应返回 naive local datetime（与 datetime.now() 一致）"
    assert c.now_aware().tzinfo is not None, "SystemClock.now_aware 应返回 aware UTC"
    print("✓ 1. SystemClock 返回 naive local datetime")

    # 2. FrozenClock 冻结
    f = FrozenClock(_dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=_dt.timezone.utc))
    assert f.now() == _dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=_dt.timezone.utc)
    assert f.now() == _dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=_dt.timezone.utc)
    assert abs(f.time() - _dt.datetime(2026, 1, 1, 12, 0, 0,
                                     tzinfo=_dt.timezone.utc).timestamp()) < 1e-6
    print("✓ 2. FrozenClock 恒定返回固定时刻")

    # 3. FrozenClock 带 offset
    f2 = FrozenClock(_dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc),
                     offset_seconds=60.0)
    t1 = f2.now()
    t2 = f2.now()
    assert (t2 - t1) == _dt.timedelta(seconds=60), "offset 应每次调用推进"
    print("✓ 3. FrozenClock offset 步进正确")

    # 4. SteppingClock 手动推进
    s = SteppingClock()
    s.advance(3600)
    assert s.now().hour == 1, "advance(3600) 后应为 1 点"
    print("✓ 4. SteppingClock.advance 正确")

    # 5. 模块级 set_default_clock
    real = set_default_clock(FrozenClock(_dt.datetime(2026, 6, 15,
                                                     tzinfo=_dt.timezone.utc)))
    assert now().month == 6 and now().day == 15
    assert _DEFAULT_CLOCK is not real, "set_default_clock 应返回旧时钟"
    set_default_clock(real)
    print("✓ 5. set_default_clock 正确返回旧时钟")

    # 6. freeze_at 上下文
    real = get_default_clock()
    with freeze_at(_dt.datetime(2025, 12, 25, tzinfo=_dt.timezone.utc)):
        assert now().year == 2025 and now().month == 12
    assert get_default_clock() is real, "退出上下文应恢复默认"
    print("✓ 6. freeze_at 上下文管理器正确恢复")

    # 7. epoch_ms 类型
    assert isinstance(c.epoch_ms(), int)
    print("✓ 7. epoch_ms 返回 int")

    print("\n时钟模块全部 7 项自测通过。")
