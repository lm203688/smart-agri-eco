#!/usr/bin/env python3
"""
engine/evolution.py —— 自进化闭环：benchmark → 评估 → 编辑 → 仅改进才接受 + 快照回滚

借鉴 PenguinHarness（Prism-Shadow）的两条硬规则，直接移植为本模块的门禁：
    1. Ratchet（棘轮）—— 候选变更只有在 benchmark 分数**严格提升**时才接受；
       持平或下降一律回滚。这是「不允许退步」的工程化表达。
    2. 快照回滚 —— 每轮变更前后都做快照，任何一步可回到已知良好状态。

为什么值得做（对应项目缺口）：
    飞轮 RSI 框架（engine/rsi.py）解决了「度量自主性到哪个级别」，但度量本身
    不产生改进。本模块补上改进循环：把「校准权重是否合理」「反馈是否真的
    提升了推荐质量」变成可重复跑、可回滚的实验，而不是凭直觉改常量。

Benchmark 设计（刻意非永真）：
    用例 = (真实分区, 真实作物, 反馈样本) + 人工语义期望方向：
        good 反馈（成活/产量/评分均高）→ 期望 adapt_score 上升
        bad  反馈（三项均低）           → 期望 adapt_score 下降
    方向正确=1，无变化=0.5，方向错误=0。
    这是真实的单调性检验：若校准权重被改错（例如实测权重过低），good 反馈对
    高分作物将不再提升，分数立刻下降——棘轮就会拒绝。

设计约束：
    - 零第三方依赖（stdlib only）
    - 评分全程在**临时隔离副本**上进行，绝不污染 data/crop_adapt_db.json
    - 快照仅包含被保护的数据文件，不含密钥

用法：
    python -m engine.evolution                     # 跑一次演示循环
    python -m engine.evolution --rebuild-benchmark # 从真实数据重建评测集
    python -m engine.evolution --list-snapshots
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional

import engine.flywheel as fw
import engine.rsi as rsi_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BENCHMARK_PATH = os.environ.get(
    "AGRI_EVOLUTION_BENCHMARK") or os.path.join(ROOT, "data", "eval", "evolution_benchmark.json")
SNAPSHOT_ROOT = os.environ.get(
    "AGRI_EVOLUTION_SNAPSHOTS") or os.path.join(ROOT, "data", "snapshots")

# 被快照保护的数据文件（相对 ROOT）
PROTECTED_FILES = [
    "data/crop_adapt_db.json",
    "data/zone_meta/global_zones.json",
    "data/feedback_log.json",
    "harness/manifest.json",
]

# good / bad 反馈样本的判定阈值（与 flywheel._observed_score 的 0-1 口径对齐）
GOOD_MIN = {"survival_rate": 0.9, "yield_rating": 4.5, "user_rating": 4.5}
BAD_MAX = {"survival_rate": 0.4, "yield_rating": 2.0, "user_rating": 2.0}
GOOD_FEEDBACK = {"survival_rate": 0.98, "yield_rating": 5.0, "user_rating": 5.0}
BAD_FEEDBACK = {"survival_rate": 0.25, "yield_rating": 1.0, "user_rating": 1.0}

# 每轮快照保留数量（超出最旧的自动淘汰；避免 data/snapshots 无限膨胀）
KEEP_SNAPSHOTS = 10


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dedup(paths: List[str]) -> List[str]:
    """按规范化后的路径去重，保持顺序（快照输入用）。"""
    seen = set()
    out: List[str] = []
    for p in paths:
        key = os.path.normcase(os.path.normpath(p))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _load(path: str) -> Any:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _find_crop(db: Dict[str, Any], zone_id: str, crop: str) -> Optional[Dict[str, Any]]:
    zd = db.get("zones", {}).get(zone_id)
    if zd:
        for c in zd.get("crops", []):
            if c.get("crop") == crop:
                return c
    return None


def seed_benchmark(zone_pick: int = 2, cases_per_pair: int = 2,
                   save: bool = True) -> Dict[str, Any]:
    """从真实作物库派生 benchmark 用例集（可复算，不手写魔法值）。

    选分区 → 每分区取若干真实作物 → 每个作物生成 good / bad 两个用例，
    期望方向由反馈语义决定（good→up，bad→down）。
    """
    db_path = fw.crop_db_path()
    db = _load(db_path) or {}
    zones = sorted(db.get("zones", {}).keys())[:max(1, zone_pick)]

    cases: List[Dict[str, Any]] = []
    for zid in zones:
        zm = db.get("zones", {}).get(zid) or {}
        picked = [c.get("crop") for c in zm.get("crops", [])
                  if c.get("crop")][:cases_per_pair]
        for crop in picked:
            cases.append({
                "id": "good_%s_%s" % (zid, crop),
                "zone_id": zid, "crop": crop,
                "feedback": dict(GOOD_FEEDBACK),
                "expect": "up",
                "rationale": "high-survival feedback should raise adapt_score",
            })
            cases.append({
                "id": "bad_%s_%s" % (zid, crop),
                "zone_id": zid, "crop": crop,
                "feedback": dict(BAD_FEEDBACK),
                "expect": "down",
                "rationale": "low-survival feedback should lower adapt_score",
            })

    bm = {
        "schema": "agri-evolution-benchmark/v1",
        "generated_at": _now(),
        "source": os.path.relpath(db_path, ROOT),
        "scoring": "direction-correct=1.0, unchanged=0.5, wrong-direction=0.0",
        "cases": cases,
    }
    if save:
        _save(BENCHMARK_PATH, bm)
    return bm


def load_benchmark() -> Dict[str, Any]:
    bm = _load(BENCHMARK_PATH)
    if not bm or not bm.get("cases"):
        return seed_benchmark()
    return bm


def _isolated(paths: Dict[str, str]) -> List[str]:
    """把被评测的数据文件复制到临时目录，返回临时根路径。"""
    tmp = tempfile.mkdtemp(prefix="agri_evo_")
    for src, dst in paths.items():
        dst = os.path.join(tmp, dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return [tmp]


def _score_case_inplace(case: Dict[str, Any],
                        crop_db: str, feedback_log: str) -> Dict[str, Any]:
    """在**已给定**的文件上应用单条反馈并判定方向。不做任何隔离。"""
    db = _load(crop_db) or {}
    t = _find_crop(db, case["zone_id"], case["crop"])
    if not t:
        return {"id": case["id"], "score": 0.0,
                "detail": "crop not found in isolated copy"}

    before = float(t.get("adapt_score", 0.0))
    res = fw.record_feedback(
        zone_id=case["zone_id"], crop=case["crop"],
        survival_rate=case["feedback"]["survival_rate"],
        yield_rating=case["feedback"]["yield_rating"],
        user_rating=case["feedback"]["user_rating"],
        note="[evolution-benchmark] 自动评测用例，非真实用户反馈",
    )
    after = float(res.get("after") or before)
    delta = after - before

    if abs(delta) < 1e-9:
        score, verdict = 0.5, "unchanged"
    elif delta > 0:
        score, verdict = (1.0 if case["expect"] == "up" else 0.0), "up"
    else:
        score, verdict = (1.0 if case["expect"] == "down" else 0.0), "down"

    return {
        "id": case["id"], "score": score, "verdict": verdict,
        "expect": case["expect"], "before": before, "after": round(after, 3),
        "delta": round(delta, 3),
    }


def score_case(case: Dict[str, Any],
               crop_db: Optional[str] = None,
               feedback_log: Optional[str] = None) -> Dict[str, Any]:
    """在**每例独立的**临时副本上评分。

    为什么必须逐例隔离：同一作物可能出现 good / bad 两个用例，若共享一份
    副本，前一条反馈会改写 adapt_score，后一条的 before 就变成被污染的值，
    评分会顺序依赖（实测：bad 用例永远判错）。逐例复制让评测集真正可复算。
    """
    src_db = crop_db or fw.crop_db_path()
    src_log = feedback_log or fw.feedback_log_path()
    tmp_root = _isolated({src_db: "crop_adapt_db.json",
                          src_log: "feedback_log.json"})[0]
    env_old: Dict[str, Optional[str]] = {}
    try:
        for k, v in (("AGRI_CROP_DB", os.path.join(tmp_root, "crop_adapt_db.json")),
                     ("AGRI_FEEDBACK_LOG", os.path.join(tmp_root, "feedback_log.json"))):
            env_old[k] = os.environ.get(k)
            os.environ[k] = v
        return _score_case_inplace(case, os.path.join(tmp_root, "crop_adapt_db.json"),
                                   os.path.join(tmp_root, "feedback_log.json"))
    finally:
        for k, v in env_old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp_root, ignore_errors=True)


def score_benchmark(benchmark: Optional[Dict[str, Any]] = None,
                    crop_db: Optional[str] = None,
                    feedback_log: Optional[str] = None) -> Dict[str, Any]:
    """跑完整评测集（每例独立隔离），返回 0-1 分数与逐例明细。"""
    bm = benchmark or load_benchmark()
    cases = bm.get("cases") or []
    if not cases:
        return {"score": 0.0, "n": 0, "results": [], "errors": ["benchmark 无用例"]}

    results = [score_case(c, crop_db, feedback_log) for c in cases]
    scores = [r.get("score", 0.0) for r in results]
    return {
        "score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "n": len(results),
        "perfect": sum(1 for s in scores if s == 1.0),
        "neutral": sum(1 for s in scores if s == 0.5),
        "wrong": sum(1 for s in scores if s == 0.0),
        "results": results,
    }


# ---------------------------------------------------------------------------
# 快照与回滚
# ---------------------------------------------------------------------------

def _snap_id(label: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(c for c in label if c.isalnum() or c in "_-")[:32]
    return "%s__%s" % (ts, safe or "snap")


def snapshot(label: str = "pre-change",
             paths: Optional[List[str]] = None) -> Dict[str, Any]:
    """把受保护文件复制到 data/snapshots/<id>/。已存在同名时幂等复用。

    paths 可含绝对路径（测试隔离副本）与相对 ROOT 路径（真实数据文件）。
    绝对路径会以哈希别名存放，restore 时按 file_map 精确还原到原位置——
    否则棘轮在「评测跑在临时副本」的隔离模式下，回滚会变成空操作。
    """
    rels = paths or PROTECTED_FILES
    sid = _snap_id(label)
    dest = os.path.join(SNAPSHOT_ROOT, sid)
    if os.path.isdir(dest):
        meta = _load(os.path.join(dest, "_meta.json")) or {}
        return {"snap_id": sid, "path": dest, "created": False,
                "files": meta.get("files", [])}
    os.makedirs(dest, exist_ok=True)
    copied: List[str] = []
    file_map: Dict[str, str] = {}
    for p in rels:
        is_abs = os.path.isabs(p)
        src = p if is_abs else os.path.join(ROOT, p)
        if not os.path.exists(src):
            continue
        # 绝对路径压平为别名，避免把 Windows 盘符/多级目录写进快照树
        stored = ("abs__%s__%s" % (_sha1(p)[:12], os.path.basename(p))
                  if is_abs else p)
        d = os.path.join(dest, stored)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(src, d)
        copied.append(p)
        file_map[stored] = p
    _save(os.path.join(dest, "_meta.json"),
          {"snap_id": sid, "label": label, "created_at": _now(),
           "files": copied, "file_map": file_map, "restored": False})
    _prune_snapshots()
    return {"snap_id": sid, "path": dest, "created": True, "files": copied}


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _files(dest: str) -> List[str]:
    meta = _load(os.path.join(dest, "_meta.json")) or {}
    return meta.get("files", [])


def restore(snap_id: str) -> Dict[str, Any]:
    """回滚到某个快照。优先按 file_map 精确还原（支持绝对路径别名）。"""
    src = os.path.join(SNAPSHOT_ROOT, snap_id)
    if not os.path.isdir(src):
        return {"restored": False, "reason": "快照不存在: %r" % snap_id}
    meta = _load(os.path.join(src, "_meta.json")) or {}
    file_map = meta.get("file_map") or {}
    restored: List[str] = []
    if file_map:
        for stored, original in file_map.items():
            s = os.path.join(src, stored)
            if not os.path.exists(s):
                continue
            d = original if os.path.isabs(original) else os.path.join(ROOT, original)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
            restored.append(original)
    else:
        for rel in (meta.get("files", []) or _files(src)):
            s = os.path.join(src, rel)
            d = os.path.join(ROOT, rel)
            if os.path.exists(s):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
                restored.append(rel)
    meta["restored"] = True
    meta["restored_at"] = _now()
    _save(os.path.join(src, "_meta.json"), meta)
    return {"restored": bool(restored), "snap_id": snap_id, "files": restored}


def list_snapshots() -> List[Dict[str, Any]]:
    if not os.path.isdir(SNAPSHOT_ROOT):
        return []
    out = []
    for name in sorted(os.listdir(SNAPSHOT_ROOT)):
        meta = _load(os.path.join(SNAPSHOT_ROOT, name, "_meta.json")) or {}
        out.append({"snap_id": name, "label": meta.get("label"),
                    "created_at": meta.get("created_at"),
                    "restored": bool(meta.get("restored")),
                    "n_files": len(meta.get("files", []))})
    return out


def _prune_snapshots() -> None:
    """保留最近 KEEP_SNAPSHOTS 个快照，防止 data/snapshots 无限膨胀。"""
    snaps = [s for s in list_snapshots() if not s["restored"]]
    if len(snaps) <= KEEP_SNAPSHOTS:
        return
    for s in snaps[:-KEEP_SNAPSHOTS]:
        shutil.rmtree(os.path.join(SNAPSHOT_ROOT, s["snap_id"]), ignore_errors=True)


# ---------------------------------------------------------------------------
# Ratchet 门禁与完整循环
# ---------------------------------------------------------------------------

Mutate = Callable[[str, str], Dict[str, Any]]


def ratchet(mutate: Optional[Mutate] = None,
            benchmark: Optional[Dict[str, Any]] = None,
            min_gain: float = 0.0,
            label: str = "ratchet") -> Dict[str, Any]:
    """棘轮门禁：快照 → 测 baseline → 应用候选变更 → 测 candidate → 仅改进才接受。

    mutate 签名：mutate(crop_db_path, feedback_log_path) -> dict（说明改了什么）。
    mutate=None 时只做「基线测量」，不改动任何文件（用于巡检/CI）。
    """
    src_db = fw.crop_db_path()
    src_log = fw.feedback_log_path()
    baseline = score_benchmark(benchmark)

    # measure_only 不创建快照：没有任何变更可回滚，留着快照只会让
    # data/snapshots 每天净增一个空壳（实测踩过，需手工清理）。
    if mutate is None:
        return {
            "accepted": None, "action": "measure_only", "snap_id": None,
            "baseline": baseline["score"], "candidate": None, "delta": 0.0,
            "reason": "未提供候选变更，仅测量基线（无变更故未创建快照）",
        }

    snap = snapshot(label="pre-%s" % label,
                    paths=_dedup([src_db, src_log] + PROTECTED_FILES))

    # 候选变更在**真实文件**上应用（mutate 自己负责修改），随后评分再决定去留
    change = mutate(src_db, src_log) or {}
    candidate = score_benchmark(benchmark)
    delta = round(candidate["score"] - baseline["score"], 3)

    accepted = delta > max(0.0, float(min_gain))
    if not accepted:
        restore(snap["snap_id"])
        reason = ("候选变更未带来分数提升（%s → %s，Δ=%s），已回滚"
                  % (baseline["score"], candidate["score"], delta))
    else:
        reason = ("候选变更被接受：%s → %s（Δ=%s）"
                  % (baseline["score"], candidate["score"], delta))
        if snap["created"]:
            shutil.rmtree(snap["path"], ignore_errors=True)
            _prune_snapshots()

    return {
        "accepted": accepted, "action": "accept" if accepted else "revert",
        "snap_id": snap["snap_id"],
        "baseline": baseline["score"], "candidate": candidate["score"],
        "delta": delta, "change": change, "reason": reason,
    }


def run_cycle(label: str = "cycle") -> Dict[str, Any]:
    """一次完整自进化循环（度量 → 棘轮 → 记录 RSI 历史），供 automation 调用。"""
    res = ratchet(label=label)
    rep: Dict[str, Any] = {
        "ts": _now(), "result": res,
        "rsi": {"level": None, "hci": None},
    }
    try:
        r = rsi_mod.report()
        rep["rsi"] = {
            "level": (r.get("autonomy") or {}).get("level"),
            "hci": (r.get("hci") or {}).get("hci"),
            "closed_gates": (r.get("hci") or {}).get("closed_gates"),
        }
    except Exception as exc:  # pragma: no cover - rsi 不可用时降级
        rep["rsi"] = {"error": str(exc)}
    return rep


def report() -> Dict[str, Any]:
    """当前状态摘要：benchmark 分数 + 快照数量 + RSI 联动，供 harness/巡检引用。"""
    bm = load_benchmark()
    snaps = list_snapshots()
    out = {
        "benchmark": {
            "path": os.path.relpath(BENCHMARK_PATH, ROOT),
            "schema": bm.get("schema"),
            "cases": len(bm.get("cases", [])),
            "generated_at": bm.get("generated_at"),
        },
        "score": None,
        "snapshots": {"total": len(snaps), "latest": snaps[-1]["snap_id"] if snaps else None},
        "policy": "棘轮门禁：候选变更仅在 benchmark 分数严格提升时接受，否则快照回滚",
    }
    try:
        sc = score_benchmark(bm)
        out["score"] = {"score": sc["score"], "perfect": sc["perfect"],
                        "neutral": sc["neutral"], "wrong": sc["wrong"], "n": sc["n"]}
    except Exception as exc:  # pragma: no cover
        out["score"] = {"error": str(exc)}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild-benchmark", action="store_true")
    p.add_argument("--list-snapshots", action="store_true")
    args = p.parse_args()

    if args.list_snapshots:
        for s in list_snapshots():
            print("  %s  %s  restored=%s  files=%s"
                  % (s["snap_id"], s["label"], s["restored"], s["n_files"]))
        return
    if args.rebuild_benchmark:
        bm = seed_benchmark()
        print("已重建评测集：%s（%d 条用例）"
              % (os.path.relpath(BENCHMARK_PATH, ROOT), len(bm["cases"])))
        return

    r = run_cycle()
    print("=" * 60)
    print("自进化闭环（benchmark → 棘轮 → 快照）")
    print("=" * 60)
    res = r["result"]
    print("动作: %s | 基线 %s → 候选 %s | 判定: %s"
          % (res["action"], res["baseline"], res["candidate"], res["reason"]))
    print("RSI 联动: %s / HCI %s" % (r["rsi"].get("level"), r["rsi"].get("hci")))
    print("快照保留 %d 个（上限 %d）" % (len(list_snapshots()), KEEP_SNAPSHOTS))
    print("=" * 60)


if __name__ == "__main__":
    main()
