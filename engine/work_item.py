"""Work Item 显式状态机 + 5 种协作模式（借鉴 OpenOPC 的 Work Item 状态机）。

为什么需要它
------------
本项目此前的多 Agent 流水线只是「函数调用顺序」——没有状态、没有审计、
失败时无法区分「该重做」还是「该放弃」。OpenOPC 把「Agent 编排成一家公司」
的核心就是给每个工作项一个显式状态机，让协作可被观察、可被拦截、可被追溯。

5 种模式（OpenOPC：execute / delegate / review / integrate / rework）
    execute    自己执行                    -> 进入/回到 executing
    delegate   委派给其他角色              -> 进入/回到 executing
    review     请求复核（对应本项目的 Verifier 阶段） -> pending_review
    integrate  集成产物（合并/落盘）        -> integrating / done
    rework     打回重做                    -> rework

状态流转
--------
    created --execute/delegate--> executing
    executing --review----------> pending_review
    executing --integrate--------> integrating
    executing --rework----------> rework
    pending_review --integrate---> integrating
    pending_review --rework------> rework
    pending_review --execute-----> executing   （复核给出反馈后重跑）
    integrating --integrate------> done
    integrating --rework----------> rework
    rework     --execute/delegate-> executing
    blocked    --execute/delegate-> executing
    done       --rework----------> rework       （部署后回归 → 回炉）

设计约束
--------
- 零第三方依赖，纯 stdlib。
- 转移表是**声明式常量**：非法转移直接拒绝（返回 ok=False），绝不静默推进状态。
- 审计日志 append-only，每条含 from/mode/to/actor/payload_key，可离线复算。
- `blocked` 不是 5 模式之一：它由 `block(reason)` 显式写入（表示外部故障，
  如视觉后端不可用），恢复只能靠 execute/delegate。
- `done` 是正常终态；仅 rework 可从 done 回炉，且这次回炉会留在审计里。

用法
----
    from engine.work_item import new_work_item

    wi = new_work_item("杭州阳台生菜种植方案", actor="ClimateAgent")
    wi.transition("execute", actor="ClimateAgent", payload=zone_data)
    wi.transition("review", actor="Verifier")
    wi.transition("integrate", actor="Verifier")   # pending_review -> integrating
    wi.transition("integrate", actor="EcoAgent")   # integrating -> done

    python -m engine.work_item        # 跑一次演示
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# 声明式契约
# ---------------------------------------------------------------------------
STATES = ("created", "executing", "pending_review", "integrating",
          "done", "rework", "blocked")

MODES = ("execute", "delegate", "review", "integrate", "rework")

#: (当前状态, 模式) -> 下一状态。未列出的组合一律视为非法。
TRANSITIONS: Dict[Tuple[str, str], str] = {
    ("created", "execute"): "executing",
    ("created", "delegate"): "executing",
    ("executing", "review"): "pending_review",
    ("executing", "integrate"): "integrating",
    ("executing", "rework"): "rework",
    ("pending_review", "integrate"): "integrating",
    ("pending_review", "rework"): "rework",
    ("pending_review", "execute"): "executing",
    ("integrating", "integrate"): "done",
    ("integrating", "rework"): "rework",
    ("rework", "execute"): "executing",
    ("rework", "delegate"): "executing",
    ("blocked", "execute"): "executing",
    ("blocked", "delegate"): "executing",
    ("done", "rework"): "rework",
}

#: 终态集合（正常结束）。done 之后只有 rework 一条出路。
TERMINAL = ("done",)

#: 每种模式「谁来做」的角色约定（用于 delegate 校验与审计可读性）。
MODE_ROLE = {
    "execute": "executor",
    "delegate": "orchestrator",
    "review": "reviewer",
    "integrate": "integrator",
    "rework": "orchestrator",
}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _digest(payload: Any) -> str:
    """输入指纹：审计里只存摘要，不存全量产物（避免日志膨胀/泄漏）。"""
    raw = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def allowed_modes(state: str) -> List[str]:
    """列出某状态下合法的模式，便于错误信息与 UI 展示。"""
    return sorted(m for (s, m) in TRANSITIONS if s == state)


def transition_table() -> List[Dict[str, str]]:
    """转移表的机读快照（供 harness 清单与文档同步）。"""
    return [{"state": s, "mode": m, "next": n}
            for (s, m), n in sorted(TRANSITIONS.items())]


class WorkItem:
    """一个工作项 = 状态 + 审计日志。

    线程/进程内单例无关；每个实例独立，状态不共享，便于并行编排多个方案。
    """

    def __init__(self, item_id: str, title: str = "",
                 created_by: str = "system") -> None:
        if not item_id:
            raise ValueError("item_id 不能为空")
        self.item_id = item_id
        self.title = title
        self.state = "created"
        self.created_by = created_by
        self.created_at = _now()
        self.updated_at = self.created_at
        self.finished_at: Optional[str] = None
        self.attempts = 0              # execute/delegate 累计次数
        self.rework_count = 0
        self.audit: List[Dict[str, Any]] = []
        self._log("init", None, "created", created_by, None, "工作项创建")

    # ---------- 审计 ----------
    def _log(self, mode: Optional[str], frm: Optional[str], to: str,
             actor: str, payload_key: Optional[str], note: str = "") -> None:
        self.audit.append({
            "ts": _now(),
            "from": frm,
            "mode": mode,
            "to": to,
            "actor": actor,
            "payload_key": payload_key,
            "note": note,
        })

    # ---------- 转移 ----------
    def transition(self, mode: str, actor: str = "system",
                   payload: Any = None, note: str = "") -> Dict[str, Any]:
        """按模式推进一次状态。**非法转移不改动状态**，只返回错误说明。"""
        self.updated_at = _now()
        if mode not in MODES:
            return {"ok": False, "state": self.state,
                    "reason": "未知模式 %r；合法模式：%s" % (mode, list(MODES))}

        frm = self.state
        nxt = TRANSITIONS.get((frm, mode))
        if nxt is None:
            return {"ok": False, "state": frm,
                    "reason": "非法转移：%s --%s--> ?；该状态下合法模式：%s"
                              % (frm, mode, allowed_modes(frm) or ["（无，终态）"])}

        self.state = nxt
        if mode in ("execute", "delegate"):
            self.attempts += 1
        elif mode == "rework":
            self.rework_count += 1
        if nxt in TERMINAL:
            self.finished_at = self.updated_at

        self._log(mode, frm, nxt, actor, _digest(payload), note)
        return {"ok": True, "from": frm, "state": nxt, "mode": mode,
                "actor": actor, "payload_key": _digest(payload)}

    def block(self, reason: str, actor: str = "system") -> Dict[str, Any]:
        """显式阻塞（外部故障，如视觉后端不可用）。done 不可阻塞。"""
        self.updated_at = _now()
        if self.state == "done":
            return {"ok": False, "state": self.state,
                    "reason": "工作项已结束（done），不能再阻塞"}
        frm = self.state
        self.state = "blocked"
        self._log(None, frm, "blocked", actor, None, "阻塞：%s" % reason)
        return {"ok": True, "from": frm, "state": "blocked", "reason": reason}

    def recover(self, mode: str = "execute", actor: str = "system",
                note: str = "") -> Dict[str, Any]:
        """从 blocked 恢复，等价于 transition(mode) 的便捷写法。"""
        return self.transition(mode, actor=actor, note=note or "从 blocked 恢复")

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "state": self.state,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "attempts": self.attempts,
            "rework_count": self.rework_count,
            "is_terminal": self.state in TERMINAL,
            "audit": list(self.audit),
        }

    def summary(self) -> Dict[str, Any]:
        """不含审计明细的精简视图（供流水线结果内嵌）。"""
        d = self.to_dict()
        return {k: v for k, v in d.items() if k != "audit"}

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return "<WorkItem %s %s>" % (self.item_id, self.state)


# ---------------------------------------------------------------------------
# 注册表：同进程内按 item_id 复用（幂等恢复）
# ---------------------------------------------------------------------------
_REGISTRY: Dict[str, WorkItem] = {}
_SEQ = {"n": 0}


def new_work_item(item_id: str = "", title: str = "",
                  actor: str = "system",
                  reuse: bool = True) -> WorkItem:
    """创建工作项。item_id 为空时自动生成；reuse=True 时同 id 复用已有实例。"""
    if not item_id:
        _SEQ["n"] += 1
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        item_id = "wi-%s-%04d" % (stamp, _SEQ["n"])
    if reuse and item_id in _REGISTRY:
        return _REGISTRY[item_id]
    wi = WorkItem(item_id, title=title, created_by=actor)
    _REGISTRY[item_id] = wi
    return wi


def get_work_item(item_id: str) -> Optional[WorkItem]:
    return _REGISTRY.get(item_id)


def registry_stats() -> Dict[str, Any]:
    """注册表快照：供巡检确认「状态机真的在跑」。"""
    by_state: Dict[str, int] = {}
    for wi in _REGISTRY.values():
        by_state[wi.state] = by_state.get(wi.state, 0) + 1
    return {
        "items": len(_REGISTRY),
        "by_state": dict(sorted(by_state.items())),
        "total_reworks": sum(w.rework_count for w in _REGISTRY.values()),
        "total_attempts": sum(w.attempts for w in _REGISTRY.values()),
        "terminal_items": sum(1 for w in _REGISTRY.values() if w.state in TERMINAL),
        "allowed_modes": {s: allowed_modes(s) for s in STATES},
    }


def clear_registry() -> None:
    """清空进程内注册表（测试隔离用）。"""
    _REGISTRY.clear()
    _SEQ["n"] = 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _demo() -> None:
    clear_registry()
    wi = new_work_item("demo-001", title="杭州阳台生菜种植方案", actor="orchestrator")
    print("初始状态:", wi.state)
    print("created 下合法模式:", allowed_modes("created"))
    for step in [("execute", "ClimateAgent"), ("review", "Verifier")]:
        print(wi.transition(step[0], actor=step[1]))
    # 故意演示一次非法转移：已在复核中，不能再请求一次复核
    illegal = wi.transition("review", actor="Verifier", note="重复复核请求")
    print("非法转移被拒:", illegal["ok"], "|", illegal.get("reason", "")[:60])
    print("pending_review 下合法模式:", allowed_modes("pending_review"))
    print(wi.transition("integrate", actor="EcoAgent"))
    print(wi.transition("integrate", actor="EcoAgent"))
    print("终态:", wi.state, "| attempts:", wi.attempts,
          "| 审计条数:", len(wi.audit))
    print("\n状态机注册表:", json.dumps(registry_stats()["by_state"],
                                     ensure_ascii=False))


if __name__ == "__main__":
    _demo()
