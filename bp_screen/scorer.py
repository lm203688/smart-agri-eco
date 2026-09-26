# -*- coding: utf-8 -*-
"""
L7 评分引擎：纯确定性计算，无 LLM。
- 五闸（分类适配）→ 爆雷写预警并对相关维度封顶
- 六张评分卡（每卡 6 维度加权，thresholds 阶梯解释执行）
- 一票否决（结构化条件）→ 直接淘汰
- 三档：≥75 通过 / 60-75 需深挖 / <60 淘汰
- 缺失维度 → 降权 + 区间化
- 归因（决策路径）+ 反事实边界
"""
import re
from .rules import SCORING_CARDS, GATES, CATEGORIES, RULES_VERSION

VERDICTS = {"PASS": "通过", "DIG": "需深挖", "FAIL": "淘汰"}


def _op_ok(op, v, tv):
    return {"gte": v >= tv, "gt": v > tv, "lte": v <= tv, "lt": v < tv, "eq": v == tv}.get(op, False)


# ---------- 五闸 ----------
def run_gates(n: dict, category: str) -> list:
    fired = []
    cat = CATEGORIES.get(category, {})
    for g in GATES:
        metric = g["metric"]
        if metric == "gross_margin_vs_benchmark":
            gm, bench = n.get("gross_margin"), cat.get("benchmarks", {}).get("gross_margin")
            if gm is None or bench is None:
                continue
            val = gm - bench
            display = f"{val:+.1f}pct（毛利 {gm:g}% vs 基准 {bench:g}%）"
        else:
            val = n.get(metric)
            if val is None:
                continue
            unit = "%" if metric in ("cash_to_revenue", "top5_client_pct", "ue_margin", "subsidy_pct") else ""
            display = f"{val:g}{unit}"
        redline = g.get("adaptations", {}).get(category, g["default"])
        if _op_ok(g["op"], val, redline):
            fired.append({**g, "actual": round(val, 2), "redline_effective": redline,
                          "message": f"{g['name']} = {display}，触发红线（{g['op']} {redline:g}）。{g.get('note', '')}"})
    return fired


# ---------- 维度评分 ----------
def _resolve_tv(th: dict, bench: float):
    vs = th.get("vs")
    if vs:
        m = re.match(r"bench(?:([+-]\d+))?", vs)
        return bench + (int(m.group(1)) if m and m.group(1) else 0)
    return th.get("value")


def score_dim(dim: dict, n: dict, bench: float) -> dict:
    v = n.get(dim["field"])
    score, hit = None, None
    if v is not None:
        for th in dim["thresholds"]:
            tv = _resolve_tv(th, bench)
            if tv is None:
                continue
            if _op_ok(th["op"], v, tv):
                score, hit = th["score"], tv
                break
        if score is None:
            score, hit = dim["thresholds"][-1]["score"], _resolve_tv(dim["thresholds"][-1], bench)
    return {"id": dim["id"], "name": dim["name"], "weight": dim["weight"],
            "field": dim["field"], "value": v, "score": score, "threshold_hit": hit,
            "unit": dim.get("unit", "")}


# 闸门 → 封顶维度映射（维度 id）
GATE_DIM_CAP = {"cash_ratio": "cashflow", "unit_economics": "unit_econ", "runway": "cashflow",
                "margin_gap": "finance", "client_concentration": "finance", "bio_asset": None}


def score_card(category: str, n: dict, gates_fired: list) -> dict:
    card = SCORING_CARDS[category]
    bench = CATEGORIES.get(category, {}).get("benchmarks", {}).get("gross_margin", 30.0)
    dims = [score_dim(d, n, bench) for d in card["dims"]]
    # 闸门爆雷 → 对应维度封顶 50
    capped_ids = {GATE_DIM_CAP.get(g["id"]) for g in gates_fired} - {None}
    for d in dims:
        if d["id"] in capped_ids and d["score"] is not None:
            d["score"] = min(d["score"], 50)
            d["capped_by_gate"] = True
    # 加权总分（缺失维度降权：按有分维度权重归一）
    have = [d for d in dims if d["score"] is not None]
    missing = [d for d in dims if d["score"] is None]
    if have:
        wsum = sum(d["weight"] for d in have)
        total = round(sum(d["score"] * d["weight"] for d in have) / wsum, 1)
    else:
        total, wsum = None, 0
    band = min(4 * len(missing), 12) if total is not None else 0
    total_range = [max(0, round(total - band, 1)), min(100, round(total + band, 1))] if total is not None else None
    return {"card_name": card.get("name", CATEGORIES.get(category, {}).get("name", category)), "category": category, "dimensions": dims,
            "total": total, "total_range": total_range,
            "missing_dimensions": [d["name"] for d in missing], "weight_sum_effective": wsum}


# ---------- 一票否决（结构化条件） ----------
def _cond(c: dict, n: dict, prefix: str = "") -> bool:
    f = c.get(prefix + "field")
    if f is None:
        return True
    v = n.get(f)
    if v is None:
        v = 0
    return _op_ok(c.get(prefix + "op", "lt"), v, c.get(prefix + "value", 1))


def check_vetoes(category: str, n: dict) -> list:
    fired = []
    for v in SCORING_CARDS[category]["vetoes"]:
        c = v["condition"]
        if _cond(c, n) and _cond(c, n, "and_"):
            fired.append({"name": v["name"], "message": v.get("message", ""),
                          "fields": [c["field"]] + ([c["and_field"]] if c.get("and_field") else [])})
    return fired


# ---------- 反事实 ----------
def _counterfactual(card_result: dict, verdict: str) -> dict:
    if card_result["total"] is None:
        return {"type": "翻档边界", "text": "数据不足，无法计算翻档边界（请先补数）", "dimension": None}
    order = ["FAIL", "DIG", "PASS"]
    i = order.index(verdict)
    if verdict == "FAIL" and card_result["total"] < 50:
        return {"type": "翻档边界", "text": "总分距「需深挖」档较远，建议优先解决否决项/爆雷项后重新评估", "dimension": None}
    if i < 2:
        up_to = VERDICTS[order[i + 1]]
        need = round((75 if order[i + 1] == "PASS" else 60) - card_result["total"], 1)
    else:
        up_to, need = None, 0
        return {"type": "稳态", "text": "结论已为最高档「通过」，关注维持项：现金跑道与客户集中度", "dimension": None}
    dims = [d for d in card_result["dimensions"] if d["score"] is not None]
    wsum = card_result.get("weight_sum_effective") or sum(d["weight"] for d in dims)
    candidates = []
    for d in dims:
        recoverable = round((100 - d["score"]) * d["weight"] / wsum, 1)
        if recoverable >= need:
            candidates.append({**d, "recoverable": recoverable})
    if not candidates:
        return {"type": "翻档边界", "text": f"距「{up_to}」档需 {need} 分，单一维度补足难以翻档，需多维改善", "dimension": None}
    best = min(candidates, key=lambda d: d["recoverable"])
    val_desc = f"当前值 {d_val_desc(best)}"
    return {"type": "翻档边界", "text": f"距「{up_to}」档需 {need} 分。最短路径：改善「{best['name']}」维度"
            f"（{val_desc}，维度得分 {best['score']}），补齐后最多可提回 {best['recoverable']} 分",
            "dimension": best["name"]}


def d_val_desc(d):
    unit = {"pct": "%", "month": "个月", "count": "个/台"}.get(d.get("unit", ""), "")
    v = d.get("value")
    if v is None:
        return "数据缺失"
    return f"当前 {v:g}{unit}"


# ---------- 主入口 ----------
def evaluate(category: str, n: dict) -> dict:
    gates_fired = run_gates(n, category)
    vetoes_fired = check_vetoes(category, n)
    card_result = score_card(category, n, gates_fired)

    if vetoes_fired:
        verdict = "FAIL"
        verdict_reason = "一票否决触发：" + "；".join(v["name"] for v in vetoes_fired)
    elif card_result["total"] is None:
        verdict, verdict_reason = None, "致命数据缺失，无法给出结论"
    else:
        total = card_result["total"]
        verdict = "PASS" if total >= 75 else ("DIG" if total >= 60 else "FAIL")
        verdict_reason = f"总分 {total}（区间 {card_result['total_range'][0]}–{card_result['total_range'][1]}）"
        if card_result["missing_dimensions"]:
            verdict_reason += f"；{len(card_result['missing_dimensions'])} 个维度因缺数据降权"
    if gates_fired and verdict in ("PASS", "DIG"):
        verdict_reason += "；五闸爆雷，建议优先核查"

    # 归因：决策路径
    path = []
    for v in vetoes_fired:
        path.append({"rank": 0, "type": "一票否决", "name": v["name"],
                     "detail": v["message"], "impact": "直接淘汰", "trace": v.get("fields", [])})
    for g in gates_fired:
        path.append({"type": "五闸爆雷", "name": g["name"], "detail": g["message"],
                     "impact": "相关维度封顶50分", "trace": [g["metric"]]})
    if card_result["total"] is not None:
        wsum = card_result.get("weight_sum_effective") or sum(
            d["weight"] for d in card_result["dimensions"] if d["score"] is not None)
        contribs = []
        for d in card_result["dimensions"]:
            if d["score"] is None:
                continue
            contrib = round(d["score"] * d["weight"] / wsum, 1)
            gap = round((100 - d["score"]) * d["weight"] / wsum, 1)
            contribs.append({**d, "contribution": contrib, "gap_to_full": gap})
        contribs.sort(key=lambda x: -x["contribution"])
        for rank, c in enumerate(contribs[:5], 1):
            path.append({"rank": rank, "type": "得分贡献", "name": c["name"],
                         "detail": f"维度得分 {c['score']} × 权重{c['weight']}% → 贡献 {c['contribution']} 分",
                         "impact": f"距满分还可提回 {c['gap_to_full']} 分",
                         "trace": [c["field"]]})
    cf = _counterfactual(card_result, verdict or "FAIL")
    return {
        "rules_version": RULES_VERSION,
        "category": category,
        "card": card_result,
        "gates_fired": gates_fired,
        "vetoes_fired": vetoes_fired,
        "decision_path": path,
        "counterfactual": cf,
        "verdict": verdict,
        "verdict_name": VERDICTS.get(verdict, "无法判断"),
        "verdict_reason": verdict_reason,
    }
