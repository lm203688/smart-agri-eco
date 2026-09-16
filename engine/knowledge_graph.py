#!/usr/bin/env python3
"""
engine/knowledge_graph.py —— 实体-关系知识图谱索引层

借鉴 WeKnora（Tencent）「无文档只有实体+关系」范式：把数据底座从扁平 JSON
升级为可跨维度遍历的图。但**不删任何原 JSON**——本模块只是从
crop_adapt_db.json / zone_meta/global_zones.json **派生**一份图索引，
保留 JSON 兼容层：任何 Agent 仍可直接读原文件，图层提供的是新增查询能力。

为什么值得做（对应项目缺口）：
    原扁平结构只能按 zone → crops 单向下钻。反向问题——「叶斑病影响哪些作物？」「
    哪些作物共生于地中海带且同时易感蚜虫？」——要手写两次遍历。图层把这些变成
    一条 neighbors()/traverse() 调用，也让后续 RAG/检索层（B2）有稳定锚点。

实体类型：Zone / Crop / PestDisease
关系类型：grows_in（带 adapt_score 权重）/ sensitive_to / koppen_of / constrains

设计约束：
    - 零第三方依赖（stdlib only），邻接表用 dict 实现
    - 图是派生索引：build_graph() 可随时从源 JSON 重建，源数据唯一权威
    - 不写入任何原数据文件；仅写 data/knowledge_graph.json 缓存

用法：
    python -m engine.knowledge_graph            # 构建并打印统计
    python -m engine.knowledge_graph --rebuild  # 强制重建缓存
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CROP_DB_PATH = os.environ.get(
    "AGRI_CROP_DB") or os.path.join(ROOT, "data", "crop_adapt_db.json")
ZONE_META_PATH = os.environ.get(
    "AGRI_ZONE_META") or os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
GRAPH_PATH = os.environ.get(
    "AGRI_KG_PATH") or os.path.join(ROOT, "data", "knowledge_graph.json")

# 实体/关系类型常量（机读，供调用方稳定引用）
T_ZONE, T_CROP, T_PEST = "Zone", "Crop", "PestDisease"
R_GROWS_IN, R_SENSITIVE_TO = "grows_in", "sensitive_to"
R_KOPPEN, R_CONSTRAINS = "koppen_of", "constrains"

RELATIONS = [R_GROWS_IN, R_SENSITIVE_TO, R_KOPPEN, R_CONSTRAINS]


def _load(path: str) -> Any:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _n_crop(name: str) -> str:
    return "Crop:%s" % name


def _n_zone(zone_id: str) -> str:
    return "Zone:%s" % zone_id


def _n_risk(name: str) -> str:
    return "PestDisease:%s" % name


def build_graph(crop_db_path: Optional[str] = None,
                zone_meta_path: Optional[str] = None,
                save: bool = True) -> Dict[str, Any]:
    """从源 JSON 派生图索引。源数据缺失时 fail fast（不静默降级）。

    返回：{"schema","generated_at","entities":[...],"edges":[...],"stats":{...}}
    """
    db_path = crop_db_path or CROP_DB_PATH
    zm_path = zone_meta_path or ZONE_META_PATH
    db = _load(db_path)
    if not db:
        raise FileNotFoundError("作物库不存在: %r" % db_path)

    entities: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}

    def add_entity(node: str, typ: str, props: Optional[Dict[str, Any]] = None) -> None:
        if node in seen:
            return
        seen[node] = typ
        e = {"id": node, "type": typ}
        if props:
            e.update(props)
        entities.append(e)

    zone_names = {}
    zones = db.get("zones", {})
    for zone_id, zm in zones.items():
        add_entity(_n_zone(zone_id), T_ZONE, {"zone_name": zm.get("zone_name")})
        zone_names[zone_id] = zm.get("zone_name", zone_id)
        for c in zm.get("crops", []):
            name = c.get("crop")
            if not name:
                continue
            add_entity(_n_crop(name), T_CROP, {
                "latin": c.get("latin"),
                "family": c.get("family"),
                "adapt_score": c.get("adapt_score"),
                "growth_days": c.get("growth_days"),
            })
            edges.append({
                "src": _n_crop(name), "rel": R_GROWS_IN, "dst": _n_zone(zone_id),
                "weight": c.get("adapt_score"),
                "evidence": {"source": "crop_adapt_db.json", "zone": zone_id},
            })
            for risk in (c.get("key_risks") or []):
                if not risk:
                    continue
                add_entity(_n_risk(risk), T_PEST)
                edges.append({
                    "src": _n_crop(name), "rel": R_SENSITIVE_TO, "dst": _n_risk(risk),
                    "evidence": {"source": "crop_adapt_db.json", "zone": zone_id},
                })

    # zone_meta 提供 Köppen 分类与带级约束
    zm_data = _load(zm_path)
    if isinstance(zm_data, dict):
        for z in (zm_data.get("zones") or []):
            zid = z.get("zone_id")
            if not zid:
                continue
            add_entity(_n_zone(zid), T_ZONE,
                       {"zone_name": z.get("zone_name"),
                        "frost_risk": z.get("frost_risk"),
                        "growing_season_days": z.get("growing_season_days")})
            if z.get("koppen_class"):
                edges.append({
                    "src": _n_zone(zid), "rel": R_KOPPEN,
                    "dst": "Koppen:%s" % z["koppen_class"],
                    "evidence": {"source": "zone_meta/global_zones.json"},
                })
            for cs in (z.get("key_constraints") or []):
                if cs:
                    edges.append({
                        "src": _n_zone(zid), "rel": R_CONSTRAINS,
                        "dst": "Constraint:%s" % cs,
                        "evidence": {"source": "zone_meta/global_zones.json"},
                    })

    by_type: Dict[str, int] = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    by_rel: Dict[str, int] = {}
    for e in edges:
        by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1

    graph = {
        "schema": "agri-knowledge-graph/v1",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sources": [os.path.relpath(db_path, ROOT),
                    os.path.relpath(zm_path, ROOT) if zm_data else None],
        "entities": entities,
        "edges": edges,
        "stats": {
            "nodes": len(entities),
            "edges": len(edges),
            "nodes_by_type": by_type,
            "edges_by_rel": by_rel,
            "zones": len(zone_names),
            "crops": by_type.get(T_CROP, 0),
            "risks": by_type.get(T_PEST, 0),
        },
    }
    if save:
        _save(GRAPH_PATH, graph)
    return graph


def load_graph(rebuild: bool = False) -> Dict[str, Any]:
    """读缓存图；缺失或 rebuild=True 时重建。"""
    if not rebuild and os.path.exists(GRAPH_PATH):
        g = _load(GRAPH_PATH)
        if g and g.get("entities"):
            return g
    return build_graph()


def _index(graph: Dict[str, Any], reverse: bool = False
           ) -> Tuple[Dict[str, Dict[str, List[str]]], List[Dict[str, Any]]]:
    """构建邻接表。reverse=False 为正向 src→dst；reverse=True 为反向 dst→src。

    反向遍历是图层的核心价值之一：从「叶斑病」这类 sink 实体反查到
    「哪些作物 / 哪些分区暴露」，扁平 JSON 结构做不到。
    """
    out: Dict[str, Dict[str, List[str]]] = {}
    for e in graph.get("edges", []):
        src, dst = (e["dst"], e["src"]) if reverse else (e["src"], e["dst"])
        out.setdefault(src, {}).setdefault(e["rel"], []).append(dst)
    return out, graph.get("edges", [])


def neighbors(graph: Optional[Dict[str, Any]] = None, node: str = "",
              relation: Optional[str] = None, reverse: bool = False) -> Dict[str, Any]:
    """查询邻居。relation=None 时返回所有邻居（按关系分组）。reverse 沿入边查。

    未知节点返回空结果 + exists=False（不抛异常，便于批量遍历）。
    """
    g = graph or load_graph()
    adj, _ = _index(g, reverse=reverse)
    # 存在性判定不能依赖邻接表：sink 节点（如 PestDisease:*）在正向图中无出边，
    # 会被误判为不存在。以实体表 ∪ 边端点为权威集合。
    entity_ids = {e["id"] for e in g.get("entities", [])}
    for e in g.get("edges", []):
        entity_ids.add(e["src"])
        entity_ids.add(e["dst"])
    exists = node in entity_ids
    if relation:
        return {"node": node, "relation": relation, "reverse": reverse,
                "exists": exists,
                "neighbors": sorted(adj.get(node, {}).get(relation, []))}
    return {"node": node, "relation": None, "reverse": reverse,
            "exists": exists,
            "neighbors": {r: sorted(v) for r, v in sorted(adj.get(node, {}).items())}}


def traverse(graph: Optional[Dict[str, Any]] = None, start: str = "",
             depth: int = 2, relation: Optional[str] = None,
             reverse: bool = False) -> Dict[str, Any]:
    """BFS 多跳遍历。用于「叶斑病 → 共生病害的作物 → 所在分区」这类跨维度问答。

    reverse=True 时沿入边遍历（从病虫害反查作物/分区），默认 False 沿出边。
    """
    g = graph or load_graph()
    adj, _ = _index(g, reverse=reverse)
    visited = {start}
    frontier = [start]
    layers: List[Dict[str, Any]] = []
    for d in range(1, max(1, int(depth)) + 1):
        nxt: List[str] = []
        layer: Dict[str, Any] = {}
        for cur in frontier:
            rels = adj.get(cur, {})
            targets = rels.get(relation, []) if relation else \
                [t for v in rels.values() for t in v]
            for t in targets:
                if t not in visited:
                    visited.add(t)
                    nxt.append(t)
                    layer[t] = {"via": cur, "depth": d}
        layers.append({"depth": d, "nodes": layer})
        if not nxt:
            break
        frontier = nxt
    return {"start": start, "depth": depth, "relation": relation,
            "direction": "reverse" if reverse else "forward",
            "visited": sorted(visited), "layers": layers}


def find_crops(zone_id: str, top_k: int = 5,
               graph: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """分区 → 作物（按 adapt_score 降序）。图层等价物，保留与扁平结构一致的语义。"""
    g = graph or load_graph()
    node = _n_zone(zone_id)
    rows = []
    for e in g.get("edges", []):
        if e.get("rel") == R_GROWS_IN and e.get("dst") == node:
            ent = next((x for x in g.get("entities", [])
                        if x["id"] == e["src"]), {})
            rows.append({"crop": e["src"].split(":", 1)[1],
                         "latin": ent.get("latin"),
                         "family": ent.get("family"),
                         "adapt_score": e.get("weight"),
                         "entity": e["src"]})
    rows.sort(key=lambda r: (r.get("adapt_score") or 0), reverse=True)
    return rows[:max(1, int(top_k))]


def find_crops_for_risk(risk: str,
                        graph: Optional[Dict[str, Any]] = None) -> List[str]:
    """反向查询：某病虫害影响哪些作物（扁平结构无法直接回答的问题）。"""
    g = graph or load_graph()
    node = _n_risk(risk)
    out = []
    for e in g.get("edges", []):
        if e.get("rel") == R_SENSITIVE_TO and e.get("dst") == node:
            out.append(e["src"].split(":", 1)[1])
    return sorted(set(out))


def risky_zones(risk: str,
                graph: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """某病虫害的分区暴露度：{zone_id: 受影响作物数}，降序。"""
    g = graph or load_graph()
    # find_crops_for_risk 返回的是已剥前缀的作物名，需还原为图节点名才能匹配边
    affected = {"%s" % _n_crop(c) for c in find_crops_for_risk(risk, g)}
    zones: Dict[str, int] = {}
    for e in g.get("edges", []):
        if e.get("rel") == R_GROWS_IN and e.get("src") in affected:
            zid = e["dst"].split(":", 1)[1]
            zones[zid] = zones.get(zid, 0) + 1
    return dict(sorted(zones.items(), key=lambda kv: kv[1], reverse=True))


def report(graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """统计摘要 + 反向查询示例，供 harness / 巡检引用。"""
    g = graph or load_graph()
    st = g.get("stats", {})
    return {
        "schema": g.get("schema"),
        "generated_at": g.get("generated_at"),
        # stats 是上面四键的机器可读汇总（巡检/清单常整体引用，避免各自拼）
        "stats": {
            "nodes": st.get("nodes"),
            "edges": st.get("edges"),
            "nodes_by_type": st.get("nodes_by_type"),
            "edges_by_rel": st.get("edges_by_rel"),
        },
        "nodes": st.get("nodes"),
        "edges": st.get("edges"),
        "nodes_by_type": st.get("nodes_by_type"),
        "edges_by_rel": st.get("edges_by_rel"),
        "reverse_query_examples": {
            "affected_by_leaf_spot": find_crops_for_risk("叶斑病", g),
            "exposure_by_zone": risky_zones("叶斑病", g),
        },
        "compat_note": "本图为派生索引；源 JSON（crop_adapt_db / zone_meta）仍为唯一权威，"
                       "可用 build_graph() 随时重建。",
    }


def main() -> None:
    g = build_graph()
    r = report(g)
    print("=" * 60)
    print("知识图谱索引（派生层，源 JSON 不变）")
    print("=" * 60)
    print("实体 %s 个 / 边 %s 条" % (r["nodes"], r["edges"]))
    print("实体分布:", r["nodes_by_type"])
    print("关系分布:", r["edges_by_rel"])
    print("反向查询示例——「叶斑病」受影响作物:", r["reverse_query_examples"]["affected_by_leaf_spot"])
    print("分区暴露度:", r["reverse_query_examples"]["exposure_by_zone"])
    print("=" * 60)


if __name__ == "__main__":
    main()
