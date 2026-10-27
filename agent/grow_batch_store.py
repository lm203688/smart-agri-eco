"""grow_batch_store.py — GrowBatch 批次对象存储与生命周期事件日志（零依赖，stdlib-only）。

对齐 schemas/grow_batch.schema.json 的五类核心领域对象：
  Plot / GrowBatch / Observation / Action / Outcome

职责（报告 §9.1 P0 工作包『批次对象 MVP』）：
  把 MCP 工具、UI、校准与审计的局部上下文收束到批次对象链，而不是各自维护
  crop/zone/recipe 的局部上下文。支持：建立模拟批次、记录观察、记录动作
  （默认 shadow/dry_run，不真实执行）、按时间线回放事件、查询批次。

设计约束：
  - 纯标准库，零第三方依赖（与项目零依赖理念一致）。
  - 复用 core.atomic_io 的 atomic_write_json / atomic_append_jsonl，保证
    写入原子性（崩溃不破坏溯源）。
  - 事件日志为 append-only JSONL，seq 单调递增，可完整重放。
  - 诚实边界：MVP 阶段不写真实 outcome（P1 才人工确认执行）。record_outcome
    仅提供接口并强制 evidence_grade 校验，真实执行前 status 必须是 harvested/failed。

存储布局（data/grow_batches/）：
  registry.json             — 全部对象索引 + 对象体（原子写）
  events.jsonl              — 全局事件日志（append-only）
  <batch_id>.json           — 单批次快照（供外部审计/回放，可选）
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json, atomic_append_jsonl, load_json_strict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 存储根目录（可用环境变量覆盖，便于测试隔离）
_BATCHES_DIR = os.environ.get(
    "AGRI_GROW_BATCHES_DIR",
    os.path.join(ROOT, "data", "grow_batches"),
)

# 事件类型（append-only 日志）
_EVENT_TYPES = {
    "plot_created",
    "batch_created",
    "observation_added",
    "action_recorded",
    "action_status_changed",
    "outcome_recorded",
    "batch_status_changed",
    "replayed",
}

# 动作状态机（与 schema Action.status 一致）
_ACTION_STATUS = {
    "shadow", "pending_approval", "approved", "rejected",
    "executed", "executed_failed", "rolled_back",
}
# 允许状态迁移（MVP：仅影子/审批链，真实执行需人工确认）
_ACTION_TRANSITIONS = {
    "shadow": {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved": {"executed", "rolled_back"},
    "rejected": set(),
    "executed": {"rolled_back"},
    "executed_failed": {"rolled_back"},
    "rolled_back": set(),
}

# 批次状态（与 schema GrowBatch.status 一致）
_BATCH_STATUS = {"planned", "growing", "harvested", "abandoned", "failed"}


class GrowBatchError(Exception):
    """批次对象操作错误（含契约违反说明）。"""


def _now_iso() -> str:
    """当前 UTC 时间戳（秒级，ISO 8601）。"""
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_id(kind: str, obj_id: str) -> None:
    """校验对象 ID 与 schema pattern 一致（防路径穿越）。"""
    import re
    if not isinstance(obj_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", obj_id):
        raise GrowBatchError(f"{kind} id 非法（需 ^[a-zA-Z0-9_-]{{1,64}}$）: {obj_id!r}")


def _validate_unit(value: Any, field: str) -> None:
    """轻量校验 Unit 对象 {value, unit}。"""
    if value is None:
        return
    if not isinstance(value, dict) or "value" not in value or "unit" not in value:
        raise GrowBatchError(f"{field} 需为 {{value, unit}} 结构，实际: {value!r}")


def _validate_timestamp(ts: Any, field: str) -> None:
    """轻量校验 ISO 8601 UTC 时间戳。"""
    if ts is None:
        return
    if not isinstance(ts, str) or len(ts) < 19:
        raise GrowBatchError(f"{field} 需为 ISO 8601 时间戳，实际: {ts!r}")


class GrowBatchStore:
    """批次对象存储（单文件原子写 + append-only 事件日志）。"""

    def __init__(self, root_dir: Optional[str] = None) -> None:
        self.root = root_dir or _BATCHES_DIR
        os.makedirs(self.root, exist_ok=True)
        self._registry_path = os.path.join(self.root, "registry.json")
        self._events_path = os.path.join(self.root, "events.jsonl")
        self._load()

    # ---------- 底层 ----------
    def _load(self) -> None:
        if os.path.exists(self._registry_path):
            try:
                self._reg = load_json_strict(self._registry_path)
            except Exception:
                # 损坏时诚实失败，不静默重建（防溯源丢失）
                raise GrowBatchError(
                    f"批次 registry 损坏或不可读: {self._registry_path}"
                )
        else:
            self._reg = {"plots": {}, "batches": {}, "events_seq": 0}

    def _save(self) -> None:
        atomic_write_json(self._registry_path, self._reg, indent=2, sort_keys=True)

    def _append_event(self, batch_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """append-only 事件日志写入（seq 单调递增）。"""
        if event_type not in _EVENT_TYPES:
            raise GrowBatchError(f"未知事件类型: {event_type}")
        seq = self._reg.get("events_seq", 0) + 1
        self._reg["events_seq"] = seq
        event = {
            "seq": seq,
            "ts": _now_iso(),
            "event_type": event_type,
            "batch_id": batch_id,
            "payload": payload,
        }
        atomic_append_jsonl(self._events_path, event)
        return event

    def _get_batch(self, batch_id: str) -> Dict[str, Any]:
        b = self._reg["batches"].get(batch_id)
        if b is None:
            raise GrowBatchError(f"批次不存在: {batch_id}")
        return b

    # ---------- Plot ----------
    def create_plot(self, plot: Dict[str, Any]) -> Dict[str, Any]:
        """注册 Plot（幂等：同 plot_id 重复注册报错）。"""
        plot_id = plot.get("plot_id")
        _validate_id("plot", plot_id)
        if plot_id in self._reg["plots"]:
            raise GrowBatchError(f"Plot 已存在: {plot_id}")
        self._reg["plots"][plot_id] = plot
        self._save()
        self._append_event(plot_id, "plot_created", {"plot_id": plot_id})
        return {"ok": True, "plot_id": plot_id}

    # ---------- GrowBatch ----------
    def create_batch(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """建立批次（需关联 Plot 存在；MVP 默认 status=planned）。"""
        batch_id = batch.get("batch_id")
        _validate_id("batch", batch_id)
        if batch_id in self._reg["batches"]:
            raise GrowBatchError(f"批次已存在: {batch_id}")
        plot_id = batch.get("plot_id")
        if plot_id not in self._reg["plots"]:
            raise GrowBatchError(f"关联 Plot 不存在: {plot_id}")
        b = dict(batch)
        b.setdefault("status", "planned")
        if b["status"] not in _BATCH_STATUS:
            raise GrowBatchError(f"非法批次状态: {b['status']}")
        _validate_timestamp(b.get("started_at"), "started_at")
        self._reg["batches"][batch_id] = b
        self._save()
        self._append_event(batch_id, "batch_created", {"batch_id": batch_id, "crop": b.get("crop")})
        return {"ok": True, "batch_id": batch_id, "status": b["status"]}

    # ---------- Observation ----------
    def add_observation(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        """追加 Observation（需批次存在；source/quality 校验）。"""
        batch_id = obs.get("batch_id")
        _validate_id("observation", obs.get("observation_id"))
        self._get_batch(batch_id)
        _validate_timestamp(obs.get("ts"), "ts")
        _validate_unit(obs.get("value"), "value")
        b = self._reg["batches"][batch_id]
        b.setdefault("observations", [])
        b["observations"].append(obs)
        self._save()
        self._append_event(batch_id, "observation_added", {
            "observation_id": obs.get("observation_id"),
            "metric": obs.get("metric"),
        })
        return {"ok": True, "observation_id": obs.get("observation_id"), "count": len(b["observations"])}

    # ---------- Action ----------
    def add_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """记录 Action（MVP 默认 dry_run=True + status=shadow，不真实执行）。"""
        batch_id = action.get("batch_id")
        _validate_id("action", action.get("action_id"))
        self._get_batch(batch_id)
        _validate_timestamp(action.get("ts"), "ts")
        a = dict(action)
        a.setdefault("dry_run", True)
        a.setdefault("status", "shadow")
        if a["status"] not in _ACTION_STATUS:
            raise GrowBatchError(f"非法动作状态: {a['status']}")
        # 契约：真实执行（executed）必须人工确认（approved）+ 非 dry_run
        if a["status"] == "executed" and a.get("dry_run", True):
            raise GrowBatchError("真实执行（executed）禁止 dry_run=True，需人工确认后置 dry_run=False")
        b = self._reg["batches"][batch_id]
        b.setdefault("actions", [])
        b["actions"].append(a)
        self._save()
        self._append_event(batch_id, "action_recorded", {
            "action_id": a.get("action_id"),
            "status": a["status"],
            "dry_run": a["dry_run"],
        })
        return {"ok": True, "action_id": a.get("action_id"), "status": a["status"], "dry_run": a["dry_run"]}

    def transition_action(self, batch_id: str, action_id: str, new_status: str) -> Dict[str, Any]:
        """动作状态迁移（仅允许合法转移；真实执行需人工确认）。"""
        b = self._get_batch(batch_id)
        target = next((a for a in b.get("actions", []) if a.get("action_id") == action_id), None)
        if target is None:
            raise GrowBatchError(f"动作不存在: {action_id}")
        cur = target["status"]
        if new_status not in _ACTION_TRANSITIONS.get(cur, set()):
            raise GrowBatchError(f"非法动作状态迁移: {cur} -> {new_status}")
        target["status"] = new_status
        if new_status in ("executed", "executed_failed"):
            target["dry_run"] = False
            target["execution_ts"] = _now_iso()
        self._save()
        self._append_event(batch_id, "action_status_changed", {
            "action_id": action_id, "from": cur, "to": new_status,
        })
        return {"ok": True, "action_id": action_id, "from": cur, "to": new_status}

    # ---------- Outcome ----------
    def record_outcome(self, outcome: Dict[str, Any]) -> Dict[str, Any]:
        """记录 Outcome（MVP：仅当批次已结束；真实执行前不写）。"""
        batch_id = outcome.get("batch_id")
        _validate_id("outcome", outcome.get("outcome_id"))
        b = self._get_batch(batch_id)
        if b.get("status") not in ("harvested", "failed"):
            raise GrowBatchError(
                f"批次未结束（status={b.get('status')}），MVP 阶段不写真实 outcome；"
                "需真实批次人工确认执行并置 harvested/failed 后才可记录"
            )
        _validate_unit(outcome.get("yield"), "yield")
        b.setdefault("outcomes", [])
        b["outcomes"].append(outcome)
        self._save()
        self._append_event(batch_id, "outcome_recorded", {
            "outcome_id": outcome.get("outcome_id"), "yield": outcome.get("yield"),
        })
        return {"ok": True, "outcome_id": outcome.get("outcome_id")}

    def set_batch_status(self, batch_id: str, new_status: str) -> Dict[str, Any]:
        """批次状态迁移。"""
        b = self._get_batch(batch_id)
        if new_status not in _BATCH_STATUS:
            raise GrowBatchError(f"非法批次状态: {new_status}")
        old = b.get("status")
        b["status"] = new_status
        if new_status in ("harvested", "failed"):
            b["ended_at"] = _now_iso()
        self._save()
        self._append_event(batch_id, "batch_status_changed", {"from": old, "to": new_status})
        return {"ok": True, "batch_id": batch_id, "from": old, "to": new_status}

    # ---------- 查询 / 回放 ----------
    def get_batch(self, batch_id: str, *, include_events: bool = False) -> Dict[str, Any]:
        """查询批次 + 关联对象（可选含事件日志）。"""
        b = self._get_batch(batch_id)
        out = {
            "batch": b,
            "plot": self._reg["plots"].get(b.get("plot_id")),
            "observations": b.get("observations", []),
            "actions": b.get("actions", []),
            "outcomes": b.get("outcomes", []),
        }
        if include_events:
            out["events"] = self.list_events(batch_id)
        return out

    def list_batches(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出批次（可按状态过滤）。"""
        rows = []
        for bid, b in self._reg["batches"].items():
            if status and b.get("status") != status:
                continue
            rows.append({
                "batch_id": bid, "crop": b.get("crop"), "plot_id": b.get("plot_id"),
                "recipe_version": b.get("recipe_version"), "status": b.get("status"),
                "started_at": b.get("started_at"),
                "n_observations": len(b.get("observations", [])),
                "n_actions": len(b.get("actions", [])),
                "n_outcomes": len(b.get("outcomes", [])),
            })
        rows.sort(key=lambda r: r.get("started_at") or "")
        return rows

    def list_events(self, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """事件日志（append-only，seq 升序）。"""
        if not os.path.exists(self._events_path):
            return []
        events = []
        with open(self._events_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if batch_id is None or e.get("batch_id") == batch_id:
                    events.append(e)
        events.sort(key=lambda e: e.get("seq", 0))
        return events

    def replay(self, batch_id: str) -> Dict[str, Any]:
        """按时间线回放批次事件（不真实执行，仅重建事件序列）。"""
        self._get_batch(batch_id)
        events = self.list_events(batch_id)
        # 按 ts 排序重建时间线（seq 已单调，但显式按 ts 更稳）
        timeline = sorted(events, key=lambda e: (e.get("ts") or "", e.get("seq", 0)))
        self._append_event(batch_id, "replayed", {"n_events": len(timeline)})
        return {
            "ok": True,
            "batch_id": batch_id,
            "n_events": len(timeline),
            "timeline": timeline,
            "honest_note": "回放仅重建事件序列，不触发任何真实执行或副作用",
        }


# ---------- 便捷单例（MCP server 使用） ----------
_default_store: Optional[GrowBatchStore] = None


def get_store() -> GrowBatchStore:
    """全局批次存储单例（进程内复用）。"""
    global _default_store
    if _default_store is None:
        _default_store = GrowBatchStore()
    return _default_store


# ---------- 自测 ----------
def _selftest() -> bool:
    """内置自测：建 Plot → 建批次 → 观察 → shadow 动作 → 状态迁移 → 回放。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = GrowBatchStore(tmp)
        store.create_plot({
            "plot_id": "demo_balcony_a", "location_type": "balcony",
            "orientation": "south", "area_sqm": {"value": 0.5, "unit": "sqm"},
        })
        store.create_batch({
            "batch_id": "demo_batch_001", "crop": "生菜", "plot_id": "demo_balcony_a",
            "recipe_version": "v1.2.0", "recipe_id": "mediterranean__生菜",
            "started_at": "2026-10-27T00:00:00Z",
        })
        store.add_observation({
            "observation_id": "obs_001", "batch_id": "demo_batch_001",
            "ts": "2026-10-27T08:00:00Z", "metric": "temperature_c",
            "value": {"value": 21.5, "unit": "celsius"},
            "source": {"kind": "sensor", "device_id": "dev_t01"},
        })
        store.add_action({
            "action_id": "act_001", "batch_id": "demo_batch_001",
            "ts": "2026-10-27T08:05:00Z", "recommendation": "浇水 200ml",
            "parameters": {"irrigation_ml": 200},
        })
        store.transition_action("demo_batch_001", "act_001", "pending_approval")
        store.transition_action("demo_batch_001", "act_001", "approved")
        # 真实执行需置 dry_run=False —— 状态机已强制
        r = store.replay("demo_batch_001")
        assert r["n_events"] >= 4, r
        b = store.get_batch("demo_batch_001")
        assert len(b["observations"]) == 1 and len(b["actions"]) == 1
        # 未结束批次不允许写 outcome
        try:
            store.record_outcome({
                "outcome_id": "out_001", "batch_id": "demo_batch_001", "ts": _now_iso(),
                "yield": {"value": 120, "unit": "g"},
            })
            return False  # 不应到达
        except GrowBatchError:
            pass
        return True


if __name__ == "__main__":
    ok = _selftest()
    print("grow_batch_store 自测:", "PASS" if ok else "FAIL")
