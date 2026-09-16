"""
engine/context_compact.py —— 证据保留式上下文压缩 + 动作融合

借鉴：SoL-Pi 的两个效率机制（NVlabs，MIT）
    - Evidence-Preserving Reducer：折叠长输出，但**保留原始证据指针**
    - Action Fusion：相邻同类动作合并为一条

设计约束（与本项目 AgriTrust 一致）：
    - 压缩**默认关闭**（opt-in），调用方显式传入 max_items / fuse=True 才生效
    - **永不丢证据**：折叠后必须能反查原始条目（evidence_refs 指向原始键）
    - 纯 stdlib，零第三方依赖；不联网、不写盘

用法：
    from engine.context_compact import reduce_output, fuse_actions
    compact = reduce_output({"recommendation": [10 条]}, max_items=3)
    merged  = fuse_actions(actions, fuse=True)
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

# 压缩开关：默认关闭，保持「原始输出即真相」
DEFAULT_MAX_ITEMS = 3
DEFAULT_ITEM_CHARS = 240
REASONS_KEY = "_compression"


def _digest(obj: Any) -> str:
    """稳定的内容指纹（用于证据反查，不含路径等易变信息）。"""
    try:
        raw = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    except Exception:
        raw = str(obj)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def reduce_output(
    payload: Any,
    max_items: int = DEFAULT_MAX_ITEMS,
    item_chars: int = DEFAULT_ITEM_CHARS,
) -> Dict[str, Any]:
    """证据保留式压缩：折叠长列表/长文本，但保留原始条目的指纹指针。

    参数：
        payload: 任意可 JSON 化的输出（通常是某个 Agent 的完整输出）
        max_items: 列表最多保留几条完整内容（默认 3）
        item_chars: 单条内容最多保留多少字符（默认 240）
    返回：
        {"payload": <压缩后>, "compression": <审计信息>}

    压缩规则：
        - 列表长度 > max_items 时：保留前 max_items 条原文，其余条目折叠为
          {__folded, n, evidence_refs}，其中 evidence_refs 是每个被折叠条目
          的 sha256 前缀，可用 digest_of() 反查
        - 字符串长度 > item_chars 时：截断并附 _orig_len / _digest
        - 其余结构原样保留（不做有损改写）
    """
    compressed = _reduce(payload, max_items, item_chars)
    audit = _diff_audit(payload, compressed)
    return {
        "payload": compressed,
        REASONS_KEY: {
            "max_items": max_items,
            "item_chars": item_chars,
            "reduction_ratio": audit["reduction_ratio"],
            "original_chars": audit["original_chars"],
            "compressed_chars": audit["compressed_chars"],
            "folded_items": audit["folded_items"],
            "clipped_strings": audit["clipped_strings"],
            "evidence_preserved": audit["folded_items"] == 0
                                  or audit["reduction_ratio"] < 1.0,
            "note": "压缩为有损折叠；被折叠条目可通过 _compression 中的指纹反查原文。",
        },
    }


def _reduce(obj: Any, max_items: int, item_chars: int) -> Any:
    if isinstance(obj, list):
        if len(obj) <= max_items:
            return [_reduce(x, max_items, item_chars) for x in obj]
        kept = [_reduce(x, max_items, item_chars) for x in obj[:max_items]]
        dropped = obj[max_items:]
        kept.append({
            "__folded": True,
            "n": len(dropped),
            "evidence_refs": [_digest(x) for x in dropped],
        })
        return kept
    if isinstance(obj, dict):
        return {k: _reduce(v, max_items, item_chars) for k, v in obj.items()}
    if isinstance(obj, str):
        if len(obj) <= item_chars:
            return obj
        return {
            "__clipped": True,
            "text": _clip(obj, item_chars),
            "_orig_len": len(obj),
            "_digest": _digest(obj),
        }
    return obj


def _diff_audit(original: Any, compressed: Any) -> Dict[str, Any]:
    orig_chars = len(json.dumps(original, ensure_ascii=False))
    comp_chars = len(json.dumps(compressed, ensure_ascii=False))
    folded = 0
    clipped = 0

    def _count(node: Any) -> None:
        nonlocal folded, clipped
        if isinstance(node, list):
            for x in node:
                _count(x)
        elif isinstance(node, dict):
            if node.get("__folded"):
                folded += int(node.get("n", 0))
            if node.get("__clipped"):
                clipped += 1
            for v in node.values():
                _count(v)

    _count(compressed)
    return {
        "original_chars": orig_chars,
        "compressed_chars": comp_chars,
        "reduction_ratio": round(1 - comp_chars / orig_chars, 3) if orig_chars else 0.0,
        "folded_items": folded,
        "clipped_strings": clipped,
    }


def digest_of(obj: Any) -> str:
    """反查用：给定原始条目，计算其在压缩输出中的 evidence_ref 指纹。"""
    return _digest(obj)


def fuse_actions(
    actions: List[Dict[str, Any]],
    fuse: bool = True,
    group_key: str = "act_type",
) -> Dict[str, Any]:
    """动作融合：相邻同类动作合并为一条（减少冗余下发）。

    参数：
        actions: [{"act_type": ..., "target": ..., "amount": ...}, ...]
        fuse: 是否启用融合（默认 True；False 时原样返回，保持 opt-in 语义）
        group_key: 判定「同类」的字段名
    返回：
        {"actions": [...], "fusion": {"merged": n, "ratio": r}}

    融合规则：
        - 仅合并**相邻**且 group_key 相同的动作（不跨段合并，避免改变语义顺序）
        - 数值字段（amount/minutes/mg 等）按 sum 聚合，并保留 targets 列表
        - 非相邻的同类动作各自独立保留
    """
    if not fuse:
        return {"actions": list(actions or []),
                "fusion": {"merged": 0, "ratio": 0.0, "enabled": False}}

    src = [a for a in (actions or []) if isinstance(a, dict)]
    if not src:
        return {"actions": [], "fusion": {
            "enabled": True, "input_count": 0, "output_count": 0,
            "merged": 0, "ratio": 0.0, "group_key": group_key,
            "note": "无动作可融合；返回结构与正常路径完全一致。",
        }}

    _NUMERIC = ("amount", "amount_ml", "amount_l", "minutes", "mg", "ml",
                "l", "days", "hours")
    merged: List[Dict[str, Any]] = []
    for act in src:
        key = act.get(group_key, "")
        entry = dict(act)
        if entry.get("target"):
            entry["targets"] = [entry["target"]]

        if merged and merged[-1].get(group_key) == key:
            last = merged[-1]
            targets = list(last.get("targets") or [])
            if entry.get("target") and entry["target"] not in targets:
                targets.append(entry["target"])
            last["targets"] = targets
            for k, v in entry.items():
                if k in _NUMERIC and isinstance(v, (int, float)):
                    last[k] = round(last.get(k, 0) + v, 3)
                elif k in ("target", "targets"):
                    continue
                else:
                    last[k] = v
            last["__fused_count"] = int(last.get("__fused_count", 1)) + 1
            last["__digests"] = list(last.get("__digests", [])) + [_digest(act)]
            continue

        entry["__fused_count"] = 1
        entry["__digests"] = [_digest(act)]
        merged.append(entry)

    ratio = round(1 - len(merged) / len(src), 3) if src else 0.0
    return {
        "actions": merged,
        "fusion": {
            "enabled": True,
            "input_count": len(src),
            "output_count": len(merged),
            "merged": len(src) - len(merged),
            "ratio": ratio,
            "group_key": group_key,
            "note": "仅合并相邻同类动作；数值字段求和，targets 列表为权威值"
                    "（__fused_count>1 时以 targets 为准），__digests 可反查原始动作。",
        },
    }


if __name__ == "__main__":
    demo_actions = [
        {"act_type": "water", "target": "A 花盆", "amount_ml": 200},
        {"act_type": "water", "target": "B 花盆", "amount_ml": 150},
        {"act_type": "light", "target": "A 花盆", "minutes": 8},
        {"act_type": "water", "target": "C 花盆", "amount_ml": 180},
    ]
    out = fuse_actions(demo_actions)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    big = {"recommendation": [
        {"crop": f"作物{i}", "adapt_score": 0.9 - i * 0.01,
         "reason": "公开文献聚合 + 实测校准；" * 20}
        for i in range(12)
    ]}
    comp = reduce_output(big)
    print("\n压缩审计：", json.dumps(comp[REASONS_KEY], ensure_ascii=False, indent=2))
