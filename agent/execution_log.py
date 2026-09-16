"""execution_log.py — Env Recipe 执行回流日志导入器（零依赖，stdlib-only）。

用途（A1，见 docs/opensource_scan_complementary.md）：
  把外部花园活动日志（当前实现 mcp-kasvanta 的 SQLite 活动记录）转换为
  schemas/execution_log.schema.json 规范条目，追加进 Env Recipe 的 execution_log 数组，
  以填补『配方→执行→结果』闭环（独占数据 A）的真实执行数据。

设计约束：
  - 纯标准库，零第三方依赖（与项目零依赖理念一致）。
  - 不实现完整 JSON Schema 校验器（过重），仅做轻量结构校验（必需字段 + enum）。
  - 导入单向、非破坏：原 kasvanta 记录不改动，仅生成映射后的 entry。

kasvanta 活动记录形态（推断，逐字段映射见 docs/execution_log_import.md）：
  {plant, location, activity, timestamp, notes}   # SQLite 一行
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_VALID_SOURCES = {"native", "imported_kasvanta", "imported_other"}


def _derive_run_id(source: str, device_id: str, started_at: str) -> str:
    """无原生 run_id 时，按 source+device_id+started_at 派生稳定 ID。"""
    raw = "%s|%s|%s" % (source, device_id or "", started_at or "")
    return "run_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def import_kasvanta_record(rec: Dict[str, Any], recipe_ref: Optional[str] = None) -> Dict[str, Any]:
    """把一条 kasvanta 风格活动记录映射为规范 execution_log 条目。

    参数：
        rec: {plant, location, activity, timestamp, notes}（缺字段容错）
        recipe_ref: 显式配方引用；省略时尝试用 plant 推导 crop:full_cycle:other
    返回：符合 schemas/execution_log.schema.json 的 entry dict
    """
    plant = (rec.get("plant") or "").strip()
    location = (rec.get("location") or "").strip()
    activity = (rec.get("activity") or "").strip()
    timestamp = (rec.get("timestamp") or "").strip()
    notes = (rec.get("notes") or "")

    ref = recipe_ref or (("%s:full_cycle:other" % plant) if plant else "unknown:full_cycle:other")
    started_at = timestamp or "1970-01-01T00:00:00Z"

    return {
        "run_id": _derive_run_id("imported_kasvanta", location, started_at),
        "recipe_ref": ref,
        "device_id": location or "unknown_location",
        "started_at": started_at,
        "source": "imported_kasvanta",
        "actual_params": {},
        "params_unknown": True,  # kasvanta 记录人工活动，无设备参数遥测
        "actions_taken": [activity] if activity else [],
        "deviations": [],
        "observations": notes if isinstance(notes, str) else json.dumps(notes, ensure_ascii=False),
        # outcome_ref 不填：kasvanta 不追踪产量，需用户/农艺师后续补全
    }


def import_kasvanta_batch(records: List[Dict[str, Any]],
                          recipe_ref: Optional[str] = None) -> List[Dict[str, Any]]:
    """批量导入 kasvanta 活动记录列表。"""
    return [import_kasvanta_record(r, recipe_ref) for r in records]


def validate_entry(entry: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """轻量结构校验（非完整 JSON Schema 校验）。返回 (ok, errors)。"""
    errors: List[str] = []
    for key in ("run_id", "recipe_ref", "started_at", "source"):
        if not entry.get(key):
            errors.append("缺少必需字段: %s" % key)
    src = entry.get("source")
    if src is not None and src not in _VALID_SOURCES:
        errors.append("source 非法: %s（允许 %s）" % (src, "/".join(sorted(_VALID_SOURCES))))
    return (len(errors) == 0, errors)


def attach_entry(recipe: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """把一条 entry 追加进 recipe['execution_log']（就地修改并返回 recipe）。"""
    ok, errs = validate_entry(entry)
    if not ok:
        raise ValueError("entry 校验失败: %s" % "; ".join(errs))
    recipe.setdefault("execution_log", [])
    recipe["execution_log"].append(entry)
    return recipe


def load_recipe(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_recipe(path: str, recipe: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(recipe, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 自测（零依赖；python agent/execution_log.py）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 构造一条模拟 kasvanta 活动记录
    sample = {
        "plant": "番茄",
        "location": "阳台A",
        "activity": "浇水",
        "timestamp": "2026-09-07T08:30:00Z",
        "notes": "叶尖轻微萎蔫，补 200ml",
    }
    entry = import_kasvanta_record(sample)
    ok, errs = validate_entry(entry)
    assert ok, errs
    # 挂到一份样例配方并回写校验
    recipe = load_recipe(os.path.join(ROOT, "data", "examples", "sample_env_recipe.json"))
    attach_entry(recipe, entry)
    assert recipe["execution_log"][0]["source"] == "imported_kasvanta"
    print(json.dumps({
        "status": "ok",
        "entry": entry,
        "recipe_execution_log_len": len(recipe["execution_log"]),
    }, ensure_ascii=False, indent=2))
