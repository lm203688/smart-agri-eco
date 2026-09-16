#!/usr/bin/env python3
"""
engine/org_memory.py —— 组织记忆：执行轨迹 → 私有经验 → 共享 Playbook

借鉴 OpenOPC（HKUDS）Self-Grown 的三层结构：
    1. Trajectory（轨迹）—— 每次 agent 调用的输入摘要 / 结果 / 问题
    2. Experience（经验）—— 从多条轨迹中聚合出的高频模式（私有）
    3. Playbook（共享剧本）—— 达到支持度的模式被蒸馏为可复用处置建议

与 skill_factory 的关系（互补，不重叠）：
    skill_factory 生产**能力定义**（inputs/outputs/data_sources 契约）；
    本模块生产**处置经验**（「遇到 X 问题应怎么做」），即知识的另一半。
    两者都标注来源与时间戳，可审计、可回溯。

为什么值得做（对应项目缺口）：
    飞轮 L4「经验获取」门禁一直未闭合——不是因为缺度量，而是因为没有机制把
    真实执行结果沉淀成可复用的组织知识。本模块提供这条通路，且不依赖 LLM：
    纯规则聚合格式化轨迹，零第三方依赖。

数据位置（可用环境变量隔离，便于测试）：
    data/org_memory/trajectories.json   —— 原始轨迹（append-only）
    data/org_memory/playbook.json       —— 蒸馏出的共享剧本

用法：
    python -m engine.org_memory                # 打印当前记忆统计
    python -m engine.org_memory --rebuild      # 重新蒸馏 Playbook
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEM_DIR = os.environ.get("AGRI_ORG_MEMORY") or os.path.join(ROOT, "data", "org_memory")
TRAJ_PATH = os.path.join(MEM_DIR, "trajectories.json")
PLAYBOOK_PATH = os.path.join(MEM_DIR, "playbook.json")

# 问题类别关键词（机读归类；与 pest_agent 的 SYMPTOM_SIGNALS 独立实现，
# 避免跨模块耦合。刻意用长匹配词——短词假阳率高，这是踩过的坑。）
ISSUE_CATEGORIES = {
    "数据缺失": ["未找到", "无数据", "数据缺失", "not found", "空数据", "未覆盖"],
    # 「证据不足」是零误报门控（A4）产生轨迹的专属类别，与病虫害/环境异常区分开：
    # 它描述的是**证据链缺失**，不是植物本身的问题。
    "证据不足": ["佐证", "证据", "未确认", "无诊断", "不确定", "缺少独立", "未命中知识库"],
    "环境异常": ["高温", "低温", "霜冻", "涝", "旱", "湿度", "光照不足", "盐", "药害"],
    "病虫害": ["病", "虫", "蚜", "螨", "霉", "锈", "腐", "枯"],
    "设备/执行": ["设备", "执行失败", "超时", "离线", "连接失败", "传感器"],
    "配置/阈值": ["阈值", "配置", "参数", "越限", "校准"],
}

# 类别 → 通用处置建议（Playbook 的骨架；真实经验命中后补充轨迹证据）
PLAYBOOK_SEED = {
    "数据缺失": ["先补数据采集（分区/作物元数据），再重跑；不要凭空输出结论"],
    "证据不足": ["补充图像或环境观测（湿度/温度/光照）后重跑诊断；"
                 "无双重证据只报监测项，不下确定性结论"],
    "环境异常": ["优先调整微环境（遮阴/控湿/排水），其次考虑品种更换"],
    "病虫害": ["先证据门控确认（症状+独立佐证），再按 KB 处置；不确定则只报监测"],
    "设备/执行": ["降级到离线规则路径并记录告警，不要静默跳过"],
    "配置/阈值": ["复核阈值来源与单位，避免把文献默认值当本地实测值"],
}


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_list(path: str) -> List[Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d if isinstance(d, list) else []
        except Exception:
            return []
    return []


def _save(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()[:16]


def classify_issue(text: str) -> str:
    """把问题描述归到类别；无命中返回 '其他'。"""
    t = (text or "").strip()
    if not t:
        return "其他"
    best, hits = "其他", 0
    for cat, words in ISSUE_CATEGORIES.items():
        n = sum(1 for w in words if w in t)
        if n > hits:
            best, hits = cat, n
    return best


def record_trajectory(skill: str,
                      input_digest: Optional[Dict[str, Any]] = None,
                      outcome: str = "",
                      issue: Optional[str] = None,
                      meta: Optional[Dict[str, Any]] = None,
                      write: bool = True) -> Dict[str, Any]:
    """记录一次 agent 执行轨迹（append-only，不去重不覆盖）。

    outcome 约定取值：ok / degraded / failed / unconfirmed
    issue 非空即视为「有问题」，参与经验蒸馏。
    """
    ts = _now()
    entry = {
        "ts": ts,
        "skill": skill or "unknown",
        "input_digest": dict(input_digest or {}),
        "outcome": outcome or ("failed" if issue else "ok"),
        "issue": (issue or "").strip() or None,
        "issue_category": classify_issue(issue or ""),
        "meta": dict(meta or {}),
        "trace_id": _digest([ts, skill, input_digest or {}, issue or "", outcome]),
    }
    if write:
        log = _load_list(TRAJ_PATH)
        log.append(entry)
        _save(TRAJ_PATH, log)
    return entry


def _group_trajectories(trajs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按 (skill, issue_category) 分组。"""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in trajs:
        key = "%s|%s" % (t.get("skill"), t.get("issue_category"))
        groups.setdefault(key, []).append(t)
    return groups


def distill_playbook(min_support: int = 2,
                     max_entries: int = 20,
                     write: bool = True) -> Dict[str, Any]:
    """从轨迹蒸馏共享 Playbook。

    支持度门槛（min_support）：同一 (skill, 问题类别) 至少出现 N 次才值得成为
    共享经验——单例噪声不入库，这是「零误报」思路在知识层的延伸。
    """
    trajs = _load_list(TRAJ_PATH)
    groups = _group_trajectories(trajs)

    entries: List[Dict[str, Any]] = []
    for key, items in groups.items():
        if len(items) < max(2, int(min_support)):
            continue
        skill, _, cat = key.partition("|")
        outcomes = Counter(t.get("outcome") for t in items)
        samples = [t.get("issue") for t in items if t.get("issue")][-3:]
        entries.append({
            "id": "pb_%s_%s" % (skill, cat),
            "skill": skill,
            "issue_category": cat,
            "support": len(items),
            "outcome_breakdown": dict(outcomes),
            "first_seen": items[0].get("ts"),
            "last_seen": items[-1].get("ts"),
            "sample_issues": [s for s in samples if s],
            "countermeasures": list(PLAYBOOK_SEED.get(cat, [])) or [
                "尚无通用处置建议；请结合具体场景人工确认后补充。"
            ],
            "confidence": "high" if len(items) >= max_support(3) else "medium",
            "provenance": "distilled_from_trajectories",
        })

    entries.sort(key=lambda e: (-e["support"], e["id"]))
    entries = entries[:max(1, int(max_entries))]

    playbook = {
        "schema": "agri-org-playbook/v1",
        "generated_at": _now(),
        "min_support": int(min_support),
        "entries": entries,
        "stats": {
            "total_trajectories": len(trajs),
            "groups_observed": len(groups),
            "entries_emitted": len(entries),
            "distinct_skills": len({t.get("skill") for t in trajs}),
            "category_counts": dict(Counter(t.get("issue_category") for t in trajs)),
        },
    }
    if write:
        _save(PLAYBOOK_PATH, playbook)
    return playbook


def max_support(n: int = 3) -> int:
    """支持度到「高置信」的门槛。独立函数便于调用方引用同一口径。"""
    return int(n)


def recall(skill: Optional[str] = None,
           issue_category: Optional[str] = None,
           limit: int = 5) -> List[Dict[str, Any]]:
    """按 skill / 问题类别检索 Playbook 条目（供 orchestrator 在诊断前预取经验）。"""
    if not os.path.exists(PLAYBOOK_PATH):
        return []
    with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
        pb = json.load(f)
    rows = pb.get("entries", []) if isinstance(pb, dict) else []
    out = []
    for e in rows:
        if skill and e.get("skill") != skill:
            continue
        if issue_category and e.get("issue_category") != issue_category:
            continue
        out.append(e)
    out.sort(key=lambda e: -int(e.get("support", 0)))
    return out[:max(1, int(limit))]


def stats() -> Dict[str, Any]:
    """记忆统计摘要（供 harness/巡检引用）。"""
    trajs = _load_list(TRAJ_PATH)
    pb = {}
    if os.path.exists(PLAYBOOK_PATH):
        try:
            with open(PLAYBOOK_PATH, "r", encoding="utf-8") as f:
                pb = json.load(f) or {}
        except Exception:
            pb = {}
    return {
        "trajectories": len(trajs),
        "playbook_entries": len(pb.get("entries", [])) if isinstance(pb, dict) else 0,
        "playbook_updated_at": pb.get("generated_at") if isinstance(pb, dict) else None,
        "outcome_breakdown": dict(Counter(t.get("outcome") for t in trajs)),
        "category_breakdown": dict(Counter(t.get("issue_category") for t in trajs)),
        "skills_seen": sorted({t.get("skill") for t in trajs if t.get("skill")}),
        "note": "轨迹为 append-only；Playbook 由 distill_playbook() 重蒸馏。",
    }


def main() -> None:
    s = stats()
    print("=" * 60)
    print("组织记忆（轨迹 → 经验 → 共享 Playbook）")
    print("=" * 60)
    print("轨迹 %s 条 | Playbook %s 条 | 重蒸馏于 %s"
          % (s["trajectories"], s["playbook_entries"], s["playbook_updated_at"]))
    print("结果分布:", s["outcome_breakdown"])
    print("问题类别:", s["category_breakdown"])
    print("已见技能:", s["skills_seen"])
    print("=" * 60)


if __name__ == "__main__":
    main()
