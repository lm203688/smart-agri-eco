"""core/exceptions.py —— 分层异常契约（FOUNDATION_AUDIT H6）

设计动机
--------
项目原有异常处理过于分散：`except:pass`、`except Exception: pass`、`except: return []`
变体遍地开花，异常被静默吞掉、根因丢失。同时错误类型不分级，无法区分：
  - 参数错（用户输入非法）
  - 数据错（NaN/inf/上游污染）
  - 计算错（数值溢出/除零）
  - 外部服务错（网络/API 失败）

本模块定义四层异常，并给出**允许吞掉的异常白名单**：
只有 UpstreamError（外部网络/API 失败）可以 `except: pass`（降级场景）；
其它一律不得吞，必须至少记录一次 warning 或打点。

层次结构
--------
AgriException            ← 项目通用根异常
├── InputError           ← 参数非法（用户可修正）—— 不允许吞
├── DataError            ← 数据错（NaN/inf/未闭合枚举）—— 不允许吞
├── ComputeError         ← 数值溢出/除零/矩阵奇异 —— 不允许吞
└── UpstreamError        ← 外部服务失败（网络/API）—— 允许吞（降级）

使用约定
--------
1. **禁止裸 except**：`except:` 一律不允许，必须写具体类型。
2. **允许吞的白名单**：
   - `except UpstreamError: ...`  网络/API 失败降级（必须至少日志一次）
   - `except KeyboardInterrupt:` 用户主动中断
   - `except SystemExit:`        进程退出
   - `except (UnicodeDecodeError, PermissionError):` 沙箱兼容（见 atomic_io）
3. **门禁**：`scripts/gate_no_silent_except.py`（后续补齐）用 AST 扫
   `except:pass` / `except:continue` / `except: return <默认>` 三类模式。

兼容说明
--------
core/numeric_domain.py 已独立定义过 InputError/DataError，为兼容历史
（H3 已加固的机理层调用），本模块的 InputError/DataError 与其同名同义，
但保持各自类独立——避免循环导入。**上层代码统一 from core.exceptions
import ... 即可**；底层机理函数可直接 from core.numeric_domain import。
"""
from __future__ import annotations

from typing import Any, Optional


class AgriException(Exception):
    """智慧农业生态项目所有异常的根类。"""


# ---------------------------------------------------------------------------
# 层级 1：输入 / 数据错（用户或上游可修正）
# ---------------------------------------------------------------------------

class InputError(AgriException, ValueError):
    """参数非法：类型错、越界、枚举外、关系约束不满足。

    例：`theoretical_yield_cap(crop='quantum_plant')` → InputError
    例：`temp_factor(T=150)` → InputError
    例：MCP handler 收到非法 payload → InputError

    继承 ValueError 保证既有 `except ValueError` 仍能捕获。
    """


class DataError(AgriException, ValueError):
    """数据错：NaN / inf / 未闭合枚举 / 上游数据污染。

    例：`vpd(T=nan)` → DataError
    例：`water_stress_factor(theta=inf)` → DataError
    例：从 JSON 读到非法字段 → DataError
    """


# ---------------------------------------------------------------------------
# 层级 2：计算错（算法内部）
# ---------------------------------------------------------------------------

class ComputeError(AgriException, ArithmeticError):
    """数值/计算错：溢出、除零、矩阵奇异、迭代不收敛。

    例：贝叶斯 MAP 坐标下降发散 → ComputeError
    例：解析梯度除零 → ComputeError

    继承 ArithmeticError 保证既有 `except ZeroDivisionError` 等仍能被捕获
    （因为 ZeroDivisionError 本身是 ArithmeticError 子类）。
    """


# ---------------------------------------------------------------------------
# 层级 3：外部服务错（唯一允许吞的类型）
# ---------------------------------------------------------------------------

class UpstreamError(AgriException):
    """外部服务/API/网络失败。

    这是**唯一允许静默吞掉的异常类型**（用于降级场景）。
    但即使吞掉，也建议至少记录一次 warning 日志，避免根因丢失。

    例：`urllib.request.urlopen` 超时 → UpstreamError
    例：MCP 客户端断开 → UpstreamError
    例：Cloudflare Pages 5xx → UpstreamError
    """


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def is_swallowed_safe(exc_type: type) -> bool:
    """判断异常类型是否允许被静默吞掉（用于 gate_no_silent_except 门禁）。

    返回 True 表示 `except <exc_type>: pass` 是允许的。
    返回 False 表示必须至少做一件事（日志/打点/re-raise）。
    """
    if not isinstance(exc_type, type) or not issubclass(exc_type, BaseException):
        return False
    return issubclass(exc_type, (UpstreamError, KeyboardInterrupt, SystemExit,
                                 UnicodeDecodeError, PermissionError))


def describe(exc: BaseException) -> str:
    """异常的一句话描述，用于日志打点。"""
    return f"{type(exc).__module__}.{type(exc).__name__}: {exc}"


def wrap_upstream(exc: BaseException, context: Optional[str] = None) -> UpstreamError:
    """把底层网络/IO 异常包装成 UpstreamError，保留原始错误链。"""
    msg = describe(exc)
    if context:
        msg = f"{context} | {msg}"
    return UpstreamError(msg)
