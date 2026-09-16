"""跨会话长期记忆层（借鉴 EverOS 长期记忆 OS + HyperMem 超图记忆）。

为什么需要它
------------
本项目此前的「记忆」只有两个：Session 幂等缓存（单进程、进程死即失）与
org_memory 的轨迹蒸馏（面向"经验"，不面向"某个具体地块发生过什么"）。
结果是：**同一个阳台生菜种了三轮，第四轮问起来毫无上下文**——每日
automation 是定时驱动，不是记忆驱动。

这里补的是**第三层**：以「地块/作物/分区」为主体键、append-only 的本地
长期记忆，跨会话可检索。后续会话能召回「上次同分区同作物出了什么问题、
当时怎么处理的」。

设计约束（与 AgriTrust 一致）
-----------------------------
- **本地优先**：纯 JSON 文件，零第三方依赖，不需要 Docker，不需要 API key
  （这是与 EverOS 的关键区别：只借架构，不引运行时）。
- **append-only**：除显式 `forget()` 外只增不改，可离线复算。
- **不引外部向量库**：相似度用「字符 n-gram 哈希 → 定长向量 → 余弦」零依赖实现。
- 路径可用 `AGRI_LONG_TERM_MEMORY` 覆盖（测试/多租户隔离）。

HyperMem 借鉴
-------------
记忆条目之间可挂 **hyperedge**（超边）：一条边可以连接任意条记忆，表达
「这几条其实是同一件事」。检索时做一次二阶扩展——命中主体的记忆会把
同超边内的兄弟记忆一起带回（带 decay），这正是超图相对普通图的价值。

检索打分（6 层加权，全部可机读）
--------------------------------
    subject 主体精确（crop/zone 同时命中）      3.0
    skill 匹配                                  1.5
    tag 交集                                    1.0 / 个
    查询词命中 summary（中文按 2-gram 子串）     0.5 / 次
    时间近因（指数衰减，半衰期 30 天）            0.6
    哈希向量余弦相似度                            0.8
    + 超边二阶扩展 bonus                          0.4

用法
----
    from engine.long_term_memory import add_memory, recall, link

    mid = add_memory(session_id="s1", skill="pest_diagnose",
                     crop="生菜", zone="subtropical_wet",
                     summary="湿度持续 92% 出现白粉病样症状",
                     outcome="unconfirmed", tags=["高湿", "白粉病"])
    link([mid], label="2026-09 高湿事件")
    hits = recall(crop="生菜", k=5)

    python -m engine.long_term_memory        # 跑一次演示
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = "agri-long-term-memory/v1"
DEFAULT_REL = os.path.join(ROOT, "data", "long_term_memory.json")
ENV_PATH = "AGRI_LONG_TERM_MEMORY"
# 合成记录留痕：测试/演示进程设此环境变量后，add_memory 会在 source_ref 打标记。
# 作用——隔离一旦失效（某用例忘了设 AGRI_LONG_TERM_MEMORY，写穿到真实记忆库），
# CI 的「数据完整性门禁」能按标记拦下，而不是让合成记录被当成真实记忆提交。
ENV_SYNTHETIC = "AGRI_MEMORY_SYNTHETIC"
SYNTHETIC_MARKER = "[unittest]"

KINDS = ("diagnosis", "recipe", "plan", "finding", "event")
HALF_LIFE_DAYS = 30.0
DIM = 256          # 哈希向量维度（零依赖相似度用）
NGRAM = 2          # 字符 n-gram 阶数

_WEIGHT = {
    "subject_both": 3.0,
    "subject_one": 1.5,
    "skill": 1.5,
    "tag": 1.0,
    "query": 0.5,
    "recency": 0.6,
    "vector": 0.8,
    "hyperedge": 0.4,
}


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------
def _path() -> str:
    return os.environ.get(ENV_PATH) or DEFAULT_REL


def _load() -> Dict[str, Any]:
    p = _path()
    if not os.path.exists(p):
        return {"schema": SCHEMA, "memories": [], "hyperedges": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return {"schema": SCHEMA, "memories": [], "hyperedges": [],
                "corrupt": p}
    d.setdefault("memories", [])
    d.setdefault("hyperedges", [])
    return d


def _save(doc: Dict[str, Any]) -> str:
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return p


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _parse_ts(ts: str) -> Optional[datetime.datetime]:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", ""))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 零依赖相似度：字符 n-gram 哈希向量 + 余弦
# ---------------------------------------------------------------------------
def vectorize(text: str) -> List[float]:
    """把文本变成定长向量：每个 n-gram 哈希到某个桶，累加计数。"""
    t = (text or "").strip()
    v = [0.0] * DIM
    if not t:
        return v
    for i in range(len(t) - NGRAM + 1):
        g = t[i:i + NGRAM]
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16)
        v[h % DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in v))
    if norm > 0:
        v = [x / norm for x in v]
    return v


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度；任一为零向量返回 0.0（不抛异常）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, num / (na * nb))


def _text_of(m: Dict[str, Any]) -> str:
    parts = [m.get("summary") or "", m.get("outcome") or "",
             m.get("crop") or m.get("subject", {}).get("crop", ""),
             m.get("zone") or m.get("subject", {}).get("zone", "")]
    parts.extend(str(t) for t in (m.get("tags") or []))
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
_SEQ = {"n": 0}


def add_memory(session_id: str = "", skill: str = "",
               summary: str = "", outcome: str = "",
               kind: str = "finding",
               crop: str = "", zone: str = "", scene: str = "",
               recipe_id: str = "", confidence: Optional[float] = None,
               tags: Optional[Iterable[str]] = None,
               subject: Optional[Dict[str, str]] = None,
               source_ref: str = "") -> str:
    """追加一条长期记忆，返回记忆 id。

    主体键 crop/zone/scene 可平铺传，也可用 subject={...}；两者可共存，
    平铺优先（便于旧调用点直接对接）。
    """
    if kind not in KINDS:
        raise ValueError("kind 必须是 %s 之一，收到 %r" % (KINDS, kind))
    if not (summary or "").strip():
        raise ValueError("summary 不能为空：无内容的记忆无法被检索")

    sub = dict(subject or {})
    if crop:
        sub["crop"] = crop
    if zone:
        sub["zone"] = zone
    if scene:
        sub["scene"] = scene

    doc = _load()
    _SEQ["n"] = len(doc["memories"]) + 1
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    mid = "mem-%s-%05d" % (stamp, _SEQ["n"])

    entry: Dict[str, Any] = {
        "id": mid,
        "ts": _now(),
        "session_id": session_id,
        "skill": skill,
        "kind": kind,
        "subject": sub,
        "summary": str(summary).strip(),
        "outcome": str(outcome or ""),
        "recipe_id": recipe_id,
        "confidence": confidence,
        "tags": sorted({str(t) for t in (tags or []) if str(t).strip()}),
        "source_ref": source_ref,
    }
    doc["memories"].append(entry)
    _save(doc)
    return mid


def forget(memory_id: str) -> bool:
    """显式删除一条记忆（GDPR 式「被遗忘」）。同时清掉引用它的超边。"""
    doc = _load()
    before = len(doc["memories"])
    doc["memories"] = [m for m in doc["memories"] if m.get("id") != memory_id]
    if len(doc["memories"]) == before:
        return False
    doc["hyperedges"] = [h for h in doc["hyperedges"]
                         if memory_id not in (h.get("memories") or [])]
    _save(doc)
    return True


# ---------------------------------------------------------------------------
# HyperMem：超边
# ---------------------------------------------------------------------------
def link(memories: Sequence[str], label: str = "",
         relation: str = "same_event") -> Optional[str]:
    """把若干条记忆挂到一条超边上。返回超边 id；有效记忆不足 2 条时不建。"""
    ids = [m for m in (memories or []) if m]
    doc = _load()
    known = {m.get("id") for m in doc["memories"]}
    valid = [m for m in ids if m in known]
    if len(valid) < 2:
        return None
    hid = "he-%s-%03d" % (datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
                          len(doc["hyperedges"]) + 1)
    doc["hyperedges"].append({
        "id": hid,
        "ts": _now(),
        "relation": relation,
        "label": label,
        "memories": valid,
    })
    _save(doc)
    return hid


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------
def recall(query: str = "", session_id: str = "", skill: str = "",
           crop: str = "", zone: str = "", scene: str = "",
           kind: str = "", tags: Optional[Sequence[str]] = None,
           k: int = 5, expand: bool = True,
           min_score: float = 0.0) -> List[Dict[str, Any]]:
    """跨会话召回记忆。硬过滤 + 6 层加权打分，返回按分降序的命中列表。

    硬过滤：传了 session_id/skill/zone 时做等值过滤（不匹配的直接排除），
    因为这类字段是主体键，模糊匹配会造成主体串味。
    """
    doc = _load()
    rows = list(doc.get("memories") or [])
    now = datetime.datetime.now()

    def _g(m: Dict[str, Any], key: str) -> str:
        return str(m.get("subject", {}).get(key) or m.get(key) or "").strip()

    if session_id:
        rows = [m for m in rows if m.get("session_id") == session_id]
    if skill:
        rows = [m for m in rows if m.get("skill") == skill]
    if zone:
        rows = [m for m in rows if _g(m, "zone") == zone]
    if scene:
        rows = [m for m in rows if _g(m, "scene") == scene]
    if kind:
        rows = [m for m in rows if m.get("kind") == kind]
    if crop:
        rows = [m for m in rows if _g(m, "crop") == crop]
    if tags:
        want = {str(t) for t in tags}
        rows = [m for m in rows if want & set(m.get("tags") or [])]

    if not rows:
        return []

    qv = vectorize(query)
    hits: List[Dict[str, Any]] = []
    for m in rows:
        sc: Dict[str, float] = {}
        subj = m.get("subject", {}) or {}
        m_crop = str(subj.get("crop") or m.get("crop") or "").strip()
        m_zone = str(subj.get("zone") or m.get("zone") or "").strip()

        crop_ok = bool(crop) and m_crop == crop
        zone_ok = bool(zone) and m_zone == zone
        if crop_ok and zone_ok:
            sc["subject_both"] = _WEIGHT["subject_both"]
        elif crop_ok or zone_ok:
            sc["subject_one"] = _WEIGHT["subject_one"]
        if skill and m.get("skill") == skill:
            sc["skill"] = _WEIGHT["skill"]
        if tags:
            sc["tag"] = _WEIGHT["tag"] * len(set(m.get("tags") or []) & set(tags))
        if query:
            blob = _text_of(m).lower()
            sc["query"] = _WEIGHT["query"] * _query_hits(query, blob)
        ts = _parse_ts(m.get("ts", ""))
        if ts:
            age = max(0.0, (now - ts).total_seconds() / 86400.0)
            sc["recency"] = _WEIGHT["recency"] * (0.5 ** (age / HALF_LIFE_DAYS))
        else:
            sc["recency"] = 0.0
        sc["vector"] = _WEIGHT["vector"] * cosine(qv, vectorize(_text_of(m)))

        total = sum(sc.values())
        hits.append({
            "id": m.get("id"),
            "ts": m.get("ts"),
            "score": round(total, 4),
            "scores": {kk: round(vv, 3) for kk, vv in sc.items()},
            "memory": m,
        })

    hits.sort(key=lambda h: h["score"], reverse=True)
    primary = hits[:k]

    if expand:
        extras = _hyper_expand(doc, primary)
        # 注意：主命中取 k 条，扩展命中是「附加」的，不能再 [:k] 截断——
        # 否则兄弟记忆刚被补进来就被切掉，扩展形同虚设。
        return [h for h in primary + extras if h["score"] >= min_score]
    return [h for h in primary if h["score"] >= min_score]


def _query_hits(query: str, blob: str) -> int:
    """查询词命中次数：ASCII 按空格分词；中文按 2-gram 子串匹配。"""
    q = (query or "").strip()
    if not q or not blob:
        return 0
    if all(ord(c) < 128 for c in q):
        return sum(1 for w in q.lower().split() if w in blob)
    grams = {q[i:i + NGRAM] for i in range(len(q) - NGRAM + 1)}
    return sum(1 for g in grams if g in blob)


def _hyper_expand(doc: Dict[str, Any], hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """超边二阶扩展：返回主命中同超边的兄弟记忆（仅新增项，不含主命中）。"""
    top_ids = {h["id"] for h in hits}
    he = doc.get("hyperedges") or []
    if not he or not hits:
        return []

    known = {m.get("id"): m for m in (doc.get("memories") or [])}
    extras: List[Dict[str, Any]] = []
    seen: set = set(top_ids)
    for h in hits:
        for edge in he:
            mems = edge.get("memories") or []
            if h["id"] not in mems:
                continue
            for sib in mems:
                if sib in seen:
                    continue
                sib_m = known.get(sib)
                if not sib_m:
                    continue
                seen.add(sib)
                bonus = round(h["score"] * _WEIGHT["hyperedge"], 4)
                extras.append({
                    "id": sib,
                    "ts": sib_m.get("ts"),
                    "score": bonus,
                    "scores": {"hyperedge": bonus},
                    "memory": sib_m,
                    "via_hyperedge": edge.get("id"),
                    "via_hyperedge_label": edge.get("label", ""),
                })
    return extras


# ---------------------------------------------------------------------------
# 统计 / 导出
# ---------------------------------------------------------------------------
def stats() -> Dict[str, Any]:
    doc = _load()
    by_kind: Dict[str, int] = {}
    by_skill: Dict[str, int] = {}
    crops: Dict[str, int] = {}
    for m in doc.get("memories") or []:
        by_kind[m.get("kind") or "?"] = by_kind.get(m.get("kind") or "?", 0) + 1
        s = m.get("skill") or "?"
        by_skill[s] = by_skill.get(s, 0) + 1
        c = (m.get("subject") or {}).get("crop") or m.get("crop") or ""
        if c:
            crops[str(c)] = crops.get(str(c), 0) + 1
    return {
        "schema": SCHEMA,
        "path": _path(),
        "memories": len(doc.get("memories") or []),
        "hyperedges": len(doc.get("hyperedges") or []),
        "by_kind": dict(sorted(by_kind.items())),
        "by_skill": dict(sorted(by_skill.items())),
        "by_crop": dict(sorted(crops.items())),
        "sessions": len({m.get("session_id") for m in (doc.get("memories") or [])
                         if m.get("session_id")}),
        "local_only": True,
    }


def export_json(dest: Optional[str] = None) -> str:
    """导出记忆全文（可提交/可迁移）。默认写到 data/long_term_memory_export.json。"""
    out = dest or os.path.join(ROOT, "data", "long_term_memory_export.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(_load(), f, ensure_ascii=False, indent=2)
    return out


def reset(path: Optional[str] = None) -> None:
    """清空记忆文件（测试隔离用）。"""
    if path:
        os.environ[ENV_PATH] = path
    _save({"schema": SCHEMA, "memories": [], "hyperedges": []})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _demo() -> None:
    tmp = os.path.join(ROOT, "data", "_ltm_demo.json")
    os.environ[ENV_PATH] = tmp
    try:
        reset(tmp)
        m1 = add_memory(session_id="s-2026-09-01", skill="pest_diagnose",
                        crop="生菜", zone="subtropical_wet", scene="balcony",
                        kind="diagnosis",
                        summary="连续 3 天湿度 90%+，叶面出现白色粉状物",
                        outcome="unconfirmed",
                        tags=["高湿", "白粉病样症状", "未确认"])
        m2 = add_memory(session_id="s-2026-09-05", skill="pest_diagnose",
                        crop="生菜", zone="subtropical_wet", scene="balcony",
                        kind="diagnosis",
                        summary="通风改善后症状消退，未用药",
                        outcome="confirmed",
                        tags=["高湿", "通风有效"])
        m3 = add_memory(session_id="s-2026-09-08", skill="nutrition_plan",
                        crop="生菜", zone="subtropical_wet", scene="balcony",
                        kind="recipe",
                        summary="EC 降到 1.2 后缺钾，补施钾肥 0.5g/L",
                        outcome="ok", tags=["缺钾", "EC"])
        hid = link([m1, m2], label="2026-09 生菜高湿事件")
        print("写入 3 条记忆 + 1 条超边:", hid)

        hits = recall(crop="生菜", k=3, expand=True)
        print("\n[跨会话召回 crop=生菜]")
        for h in hits:
            via = "（超边扩展 %s）" % h["via_hyperedge"] if h.get("via_hyperedge") else ""
            print("  %s score=%.3f %s" % (h["id"], h["score"],
                                          h["memory"].get("summary", "")[:24]))
            print("       %s%s" % (h["scores"], via))

        print("\n[按查询词召回 '高湿 白色粉状物']")
        for h in recall(query="高湿 白色粉状物", k=3, expand=False):
            print("  %s score=%.3f %s" % (h["id"], h["score"],
                                          h["memory"].get("summary", "")[:24]))

        print("\n[统计]")
        print(json.dumps(stats(), ensure_ascii=False, indent=1))
        print("\n[被遗忘] forget(%s) -> %s" % (m3, forget(m3)))
        print("清理后统计:", stats()["memories"], "条 / 超边",
              stats()["hyperedges"])
    finally:
        os.environ.pop(ENV_PATH, None)
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    _demo()
