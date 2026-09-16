"""本地优先三层检索层（借鉴 zvec-grep：全文 + 关键词 + 向量 统一入口）。

为什么需要它
------------
本项目 4 类数据底座（作物库 / 分区元数据 / 病虫害 KB / Env Recipe）此前只能
靠**硬编码路径 + 精确键**读取。Agent 想回答「哪些作物怕高温？」只能写死
遍历逻辑；用户问「阳台能种什么」也得先知道去哪个文件找哪个字段。

zvec-grep 的价值不在「又一个 grep」，而在**一套入口同时跑三种检索**：
精确全文（FTS）、关键词打分（BM25 类）、向量语义，结果混排后交给人或 Agent。

这里用**零第三方依赖**复刻同样形态：
    全文层   sqlite3 FTS5（stdlib），中文走**二元分词扩展**
             —— FTS5 默认 unicode61 把整段中文当一个 token，查「生菜」查不到，
                必须先把文本拆成 2-gram 再索引，这是中文检索的硬门槛。
    关键词层 bigram overlap 比率（不依赖 bm25 的负值怪癖，结果可解释）
    向量层   字符 n-gram 哈希 → 定长向量 → 余弦（零依赖，见 long_term_memory）
    混合层   1.0·exact + 0.5·keyword + 0.4·vector，全部归一化到 0..1

硬约束
------
- 索引是**派生缓存**（data/search_index/），可随时 `rebuild()` 重建，
  **绝不修改任何源 JSON**（与知识图谱层同一约定）。
- FTS5 不可用时**降级为全量扫描**，不抛异常、不硬依赖。
- 路径可用 `AGRI_SEARCH_INDEX` 覆盖（测试隔离）。
- 每条命中必须带**出处**（corpus / entity / source_file），可离线复核。

用法
----
    from engine.local_search import search, rebuild

    rebuild(force=True)
    hits = search("高温 高湿", corpus="crops", k=5)
    for h in hits:
        print(h["entity"], h["score"], h["snippet"])

    python -m engine.local_search        # 跑一次演示
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import json
import math
import os
import sqlite3
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INDEX_DIR = os.path.join(ROOT, "data", "search_index")
ENV_INDEX = "AGRI_SEARCH_INDEX"
DB_NAME = "agri_index.db"
SCHEMA_VER = 2

CROP_DB_REL = "data/crop_adapt_db.json"
ZONE_META_REL = "data/zone_meta/global_zones.json"
RECIPE_GLOB = "data/env_recipes/*.json"

#: 混合排序权重（exact 最强：主体键命中必须压过语义近似）
_W_EXACT, _W_KW, _W_VEC = 1.0, 0.5, 0.4

DIM = 256          # 向量维度
NGRAM = 2          # 二元分词
MIN_DOC_HIT = 0.02  # 低于此分直接丢弃（噪声过滤）


# ---------------------------------------------------------------------------
# 分词 / 向量（与 long_term_memory 同构，保持零依赖）
# ---------------------------------------------------------------------------
def grams(text: str) -> List[str]:
    """二元分词：连续 CJK 字符按 2-gram 切；ASCII 词整体保留。

    关键：查询侧与文档侧必须用**同一套切法**。早期版本把 CJK 拆成单字、
    文档侧却是 2-gram，导致交集恒为空、关键词层永远打 0 分。
    """
    t = (text or "").strip()
    tokens: List[str] = []
    cjk_buf: List[str] = []
    ascii_buf = ""

    def flush_cjk() -> None:
        nonlocal cjk_buf
        if not cjk_buf:
            return
        run = "".join(cjk_buf)
        if len(run) == 1:
            tokens.append(run)          # 单字无法成对，原样保留
        else:
            for i in range(len(run) - 1):
                tokens.append(run[i:i + 2])
        cjk_buf = []

    for ch in t:
        if ord(ch) >= 0x2E80:            # CJK / 日文假名 / 韩文
            if ascii_buf:
                tokens.append(ascii_buf.lower())
                ascii_buf = ""
            cjk_buf.append(ch)
        else:
            flush_cjk()
            if ch.isalnum() or ch in "-_":
                ascii_buf += ch
            else:
                if ascii_buf:
                    tokens.append(ascii_buf.lower())
                    ascii_buf = ""
    if ascii_buf:
        tokens.append(ascii_buf.lower())
    flush_cjk()
    return tokens


def gram_set(text: str) -> Set[str]:
    return set(grams(text))


def gram_query(text: str) -> str:
    """把查询展开成 FTS5 MATCH 表达式（OR 语义，取候选集）。"""
    gs = [g for g in grams(text) if g]
    if not gs:
        return ""
    return " OR ".join('"%s"' % g.replace('"', '""') for g in set(gs))


def vectorize(text: str) -> List[float]:
    """字符 n-gram 哈希向量（零依赖），已 L2 归一化。"""
    t = (text or "").strip()
    v = [0.0] * DIM
    if not t:
        return v
    for i in range(len(t) - NGRAM + 1):
        g = t[i:i + NGRAM]
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16)
        v[h % DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v))
    if n > 0:
        v = [x / n for x in v]
    return v


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, sum(x * y for x, y in zip(a, b)) / (na * nb))


# ---------------------------------------------------------------------------
# 语料构建（只读源 JSON）
# ---------------------------------------------------------------------------
def _read_json(rel: str) -> Any:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def corpus_crops() -> Iterator[Dict[str, Any]]:
    """作物语料：一行 = 某分区下的某个作物条目。"""
    db = _read_json(CROP_DB_REL) or {}
    for zone_id, zmeta in (db.get("zones") or {}).items():
        for c in (zmeta.get("crops") or []):
            text = " ".join(str(x) for x in [
                c.get("crop"), c.get("latin"), c.get("family"),
                c.get("growth_days") and "%s天" % c.get("growth_days"),
                c.get("temp_range_c") and "适温%s-%sc" % tuple(c.get("temp_range_c")),
                c.get("ph_range") and "pH%s-%s" % tuple(c.get("ph_range")),
                c.get("water_ml_day") and "日耗水%s毫升" % c.get("water_ml_day"),
                "、".join(c.get("suitable_scenes") or []),
                "关键风险：" + "、".join(c.get("key_risks") or []),
                c.get("fallback_variety") and "备选品种：" + str(c.get("fallback_variety")),
            ] if x)
            yield {
                "corpus": "crops",
                "entity": "crop:%s@%s" % (c.get("crop"), zone_id),
                "text": text,
                "meta": {"crop": c.get("crop"), "zone_id": zone_id,
                         "zone_name": zmeta.get("zone_name"),
                         "adapt_score": c.get("adapt_score")},
                "source_file": CROP_DB_REL,
            }


def corpus_zones() -> Iterator[Dict[str, Any]]:
    """分区语料：一行 = 一个全球气候分区。"""
    gm = _read_json(ZONE_META_REL) or {}
    for z in (gm.get("zones") or []):
        soil = z.get("soil") or {}
        tr = z.get("temperature_range") or {}
        pr = z.get("precipitation_mm_yr") or {}
        text = " ".join(str(x) for x in [
            z.get("zone_id"), z.get("zone_name"),
            z.get("koppen_class") and "柯本%s" % z.get("koppen_class"),
            tr and "气温%s~%sc" % (tr.get("min_c"), tr.get("max_c")),
            pr and "年降水%s~%smm" % (pr.get("min"), pr.get("max")),
            z.get("growing_season_days") and "生长期%s天" % z.get("growing_season_days"),
            "霜冻风险" + ("有" if z.get("frost_risk") else "无"),
            soil.get("texture_hint"), soil.get("ph_range") and "pH%s-%s" % tuple(soil.get("ph_range")),
            z.get("water_availability"),
            "典型作物：" + "、".join(z.get("typical_crops") or []),
            "主要限制：" + "、".join(str(x) for x in (z.get("key_constraints") or [])),
        ] if x)
        yield {
            "corpus": "zones",
            "entity": "zone:%s" % z.get("zone_id"),
            "text": text,
            "meta": {"zone_id": z.get("zone_id"), "zone_name": z.get("zone_name"),
                     "koppen": z.get("koppen_class")},
            "source_file": ZONE_META_REL,
        }


def corpus_pests() -> Iterator[Dict[str, Any]]:
    """病虫害语料：一行 = 一条 KB 条目。延迟导入，避免循环依赖。"""
    try:
        import sys
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from agent import pest_agent as pa
    except Exception:
        return
    for name, kb in (getattr(pa, "KB", None) or {}).items():
        cat = (pa._category_of(name) if hasattr(pa, "_category_of") else "")
        text = " ".join(str(x) for x in [
            name, "类别：%s" % cat,
            "症状：" + "、".join(kb.get("symptoms") or []),
            "处置：" + "、".join(kb.get("actions") or []),
            "预防：" + "、".join(kb.get("prevention") or []),
            kb.get("sev") and "严重度：%s" % kb.get("sev"),
        ] if x)
        yield {
            "corpus": "pests",
            "entity": "pest:%s" % name,
            "text": text,
            "meta": {"name": name, "category": cat, "sev": kb.get("sev")},
            "source_file": "agent/pest_agent.py:KB",
        }


def corpus_recipes() -> Iterator[Dict[str, Any]]:
    """配方语料：一行 = 一份 Env Recipe。"""
    for path in sorted(glob.glob(os.path.join(ROOT, RECIPE_GLOB))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                r = json.load(f)
        except Exception:
            continue
        env = r.get("environment") or {}
        temp = env.get("temperature") or {}
        hum = env.get("humidity") or {}
        wn = env.get("water_nutrient") or {}
        crop = (r.get("crop") or {}).get("species", "")
        cond_txt = "异常处理：" + "；".join(
            "%s → %s" % (e.get("condition", ""), e.get("action", ""))
            for e in (r.get("exception_handling") or [])
        )
        text = " ".join(str(x) for x in [
            crop, (r.get("crop") or {}).get("latin"), r.get("stage"),
            "设备类：" + str((r.get("device_profile") or {}).get("device_class")),
            temp and "温度白天%s夜间%s℃" % (temp.get("day_c"), temp.get("night_c")),
            hum and "湿度%s~%s%%" % (hum.get("min_pct"), hum.get("max_pct")),
            wn.get("ph") and "pH %s" % wn.get("ph"),
            wn.get("water_ml_day") and "日灌溉%s毫升" % wn.get("water_ml_day"),
            "气流：" + str((env.get("airflow") or {}).get("level")),
            cond_txt,
        ] if x)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        yield {
            "corpus": "recipes",
            "entity": "recipe:%s" % os.path.splitext(os.path.basename(path))[0],
            "text": text,
            "meta": {"crop": crop, "stage": r.get("stage")},
            "source_file": rel,
        }


CORPUS_BUILDERS = {
    "crops": corpus_crops,
    "zones": corpus_zones,
    "pests": corpus_pests,
    "recipes": corpus_recipes,
}


# ---------------------------------------------------------------------------
# 索引（派生缓存，可重建）
# ---------------------------------------------------------------------------
def index_path() -> str:
    return os.environ.get(ENV_INDEX) or os.path.join(INDEX_DIR, DB_NAME)


def _connect() -> sqlite3.Connection:
    p = index_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return sqlite3.connect(p)


def _fts_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)')
        conn.execute('DROP TABLE _fts_probe')
        return True
    except Exception:
        return False


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                       (name,)).fetchone()
    return row is not None


def rebuild(force: bool = False, corpora: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """（重）建索引。返回各语料行数与是否启用 FTS5。"""
    conn = _connect()
    fts_ok = _fts_available(conn)
    if fts_ok:
        conn.execute("DROP TABLE IF EXISTS docs")
        conn.execute("DROP TABLE IF EXISTS docs_fts")
        conn.execute("""CREATE TABLE docs (
                            rowid INTEGER PRIMARY KEY,
                            corpus TEXT NOT NULL,
                            entity TEXT NOT NULL,
                            text TEXT NOT NULL,
                            grams TEXT NOT NULL,
                            vec TEXT NOT NULL,
                            meta TEXT NOT NULL,
                            source TEXT NOT NULL)""")
        conn.execute("""CREATE VIRTUAL TABLE docs_fts USING fts5(
                            corpus, entity, body, tokenize='unicode61')""")
    elif not force and _table_exists(conn, "docs"):
        return {"reused": True, "rows": _count(conn), "fts": fts_ok}
    else:  # FTS5 不可用：退化为普通表，检索走全量扫描
        conn.execute("DROP TABLE IF EXISTS docs")
        conn.execute("""CREATE TABLE docs (
                            rowid INTEGER PRIMARY KEY,
                            corpus TEXT NOT NULL,
                            entity TEXT NOT NULL,
                            text TEXT NOT NULL,
                            grams TEXT NOT NULL,
                            vec TEXT NOT NULL,
                            meta TEXT NOT NULL,
                            source TEXT NOT NULL)""")

    targets = list(corpora or CORPUS_BUILDERS.keys())
    counts: Dict[str, int] = {}
    for name in targets:
        builder = CORPUS_BUILDERS.get(name)
        if not builder:
            counts[name] = -1
            continue
        n = 0
        for doc in builder():
            gs = grams(doc["text"])
            gv = json.dumps(gs, ensure_ascii=False)
            vec = json.dumps(vectorize(doc["text"]), ensure_ascii=False)
            meta = json.dumps(doc["meta"], ensure_ascii=False)
            conn.execute(
                "INSERT INTO docs (corpus, entity, text, grams, vec, meta, source) "
                "VALUES (?,?,?,?,?,?,?)",
                (doc["corpus"], doc["entity"], doc["text"], gv, vec, meta,
                 doc["source_file"]))
            if fts_ok:
                # body 必须同时含分词结果与原文：FTS5 默认分词器不切中文，
                # 只存原文时 MATCH 中文二元组永远命中 0。
                body = " ".join(gs) + " " + doc["text"]
                conn.execute(
                    "INSERT INTO docs_fts (rowid, corpus, entity, body) "
                    "VALUES (last_insert_rowid(), ?, ?, ?)",
                    (doc["corpus"], doc["entity"], body))
            n += 1
        counts[name] = n
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_corpus ON docs(corpus)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_entity ON docs(entity)")
    conn.commit()
    conn.close()
    return {"reused": False, "rows": counts, "total": sum(v for v in counts.values() if v > 0),
            "fts": fts_ok, "index": index_path(),
            "built_at": datetime.datetime.now().isoformat(timespec="seconds")}


def _count(conn: sqlite3.Connection) -> Dict[str, int]:
    rows = conn.execute("SELECT corpus, COUNT(*) FROM docs GROUP BY corpus").fetchall()
    return {c: n for c, n in rows}


def stats() -> Dict[str, Any]:
    p = index_path()
    if not os.path.exists(p):
        return {"built": False, "path": p, "rows": {}}
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        return {"built": True, "path": p, "rows": _count(conn), "total": n,
                "fts": _table_exists(conn, "docs_fts"), "schema_ver": SCHEMA_VER}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------
def search(query: str, corpus: str = "all", k: int = 10,
           mode: str = "hybrid",
           min_score: float = MIN_DOC_HIT) -> List[Dict[str, Any]]:
    """统一检索入口。

    mode:
      exact   仅主体键精确匹配
      keyword 仅二元分词重叠比率
      vector  仅向量余弦
      hybrid  三层加权混排（默认）

    返回按 score 降序，每条含 corpus/entity/snippet/meta/score 分解与出处。
    """
    q = (query or "").strip()
    if not q:
        return []
    st = stats()
    if not st.get("built"):
        return []

    conn = _connect()
    try:
        corpus_filter = None if corpus in ("all", "", None) else corpus
        where = ["1=1"]
        params: List[Any] = []
        if corpus_filter:
            where.append("corpus=?")
            params.append(corpus_filter)

        fts_ok = st.get("fts", False)
        candidates = []

        if fts_ok and mode in ("hybrid", "keyword"):
            mq = gram_query(q)
            if mq:
                sql = ("SELECT d.rowid, d.corpus, d.entity, d.text, d.grams, d.vec, "
                       "d.meta, d.source FROM docs d JOIN docs_fts f ON f.rowid=d.rowid "
                       "WHERE " + " AND ".join(where) + " AND docs_fts MATCH ?")
                try:
                    candidates = conn.execute(sql, tuple(params) + (mq,)).fetchall()
                except Exception:
                    candidates = []
            # FTS 空命中时兜底全量扫描（查「生菜」这类短词很常见）
            if not candidates:
                candidates = conn.execute(
                    "SELECT rowid, corpus, entity, text, grams, vec, meta, source FROM docs "
                    "WHERE " + " AND ".join(where), params).fetchall()
        else:
            candidates = conn.execute(
                "SELECT rowid, corpus, entity, text, grams, vec, meta, source FROM docs "
                "WHERE " + " AND ".join(where), params).fetchall()
    finally:
        conn.close()

    qgrams = gram_set(q)
    qvec = vectorize(q)
    qlow = q.lower()

    rows: List[Dict[str, Any]] = []
    for r in candidates:
        rowid, c, entity, text, gstr, vstr, mstr, source = r
        try:
            doc_grams = set(json.loads(gstr))
        except Exception:
            doc_grams = set(grams(text))
        try:
            vec = json.loads(vstr)
        except Exception:
            vec = vectorize(text)
        try:
            meta = json.loads(mstr)
        except Exception:
            meta = {}

        # 精确层：主体键/作物名/分区 id 完全等于查询（仅 exact/hybrid 计入）
        exact = 0.0
        if mode in ("hybrid", "exact") and (
                entity.lower() == qlow or any(
                    str(v).lower() == qlow for v in meta.values() if v)):
            exact = 1.0

        # 关键词层：查询二元分词在文档中的覆盖率（仅 keyword/hybrid 计入）
        kw = 0.0
        if mode in ("hybrid", "keyword") and qgrams:
            kw = len(qgrams & doc_grams) / len(qgrams)

        vec_score = cosine(qvec, vec) if mode in ("hybrid", "vector") else 0.0

        if mode == "exact":
            score = exact
        elif mode == "keyword":
            score = kw
        elif mode == "vector":
            score = vec_score
        else:
            score = _W_EXACT * exact + _W_KW * kw + _W_VEC * vec_score

        if score < min_score:
            continue

        rows.append({
            "corpus": c,
            "entity": entity,
            "score": round(score, 4),
            "exact": round(exact, 3),
            "keyword": round(kw, 3),
            "vector": round(vec_score, 3),
            "snippet": _snippet(text, q, 90),
            "meta": meta,
            "source_file": source,
        })

    rows.sort(key=lambda x: x["score"], reverse=True)
    return rows[:k]


def _snippet(text: str, query: str, width: int) -> str:
    """截取命中词附近的文本片段。"""
    t = (text or "").strip()
    idx = -1
    for probe in grams(query):
        idx = t.find(probe)
        if idx >= 0:
            break
    if idx < 0 or len(t) <= width:
        return t[:width]
    start = max(0, idx - width // 3)
    frag = t[start:start + width]
    return ("…" if start > 0 else "") + frag + ("…" if start + width < len(t) else "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _demo() -> None:
    st = stats()
    print("索引状态:", json.dumps(st, ensure_ascii=False))
    if not st.get("built") or st.get("total", 0) < 10:
        print("\n建索引 ...")
        print(json.dumps(rebuild(force=True), ensure_ascii=False, indent=1))

    for q in ["高温 高湿", "香蕉", "阳台 容器", "蚜虫 症状"]:
        print("\n[查询] %s" % q)
        for h in search(q, k=4):
            print("  %-24s %-8s s=%.3f (e=%.1f k=%.2f v=%.2f) %s"
                  % (h["entity"], h["corpus"], h["score"], h["exact"],
                     h["keyword"], h["vector"], h["snippet"][:40]))
        print("  [向量语义层单独] %s"
              % [h["entity"] for h in search(q, k=3, mode="vector")])


if __name__ == "__main__":
    _demo()
