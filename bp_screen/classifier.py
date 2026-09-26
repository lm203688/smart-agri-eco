# -*- coding: utf-8 -*-
"""L5 分类器：规则关键词匹配 + 信号特征复核 → 分类 + 置信度；<70% 需人工确认"""
from .rules import CATEGORIES


def classify(all_text: str, normalized: dict) -> dict:
    scores = {}
    for cid, conf in CATEGORIES.items():
        s = 0
        for kw in conf["keywords"]:
            if kw in all_text:
                s += 3
        # 财务结构信号加分
        if cid == "seeds" and (normalized.get("approved_varieties") or normalized.get("safety_certs")):
            s += 8
        if cid == "agmach" and normalized.get("units_sold"):
            s += 8
        if cid == "digag" and (normalized.get("arr") or normalized.get("arr_ratio") is not None):
            s += 8
        if cid == "bioinputs" and (normalized.get("reg_certs") or normalized.get("pipeline_certs")):
            s += 8
        if cid == "supply" and (normalized.get("store_count") or normalized.get("sku_count")):
            s += 8
        if cid == "livestock" and (normalized.get("output_volume") or normalized.get("invest_output_ratio")):
            s += 8
        scores[cid] = s

    total = sum(scores.values())
    best = max(scores, key=scores.get)
    best_s = scores[best]
    # 置信度：得分占比 × 信号强度
    if total == 0 or best_s == 0:
        return {"category": None, "confidence": 0, "scores": scores,
                "need_confirm": True, "reason": "未识别到任何分类信号，请人工选择分类"}
    share = best_s / total
    strength = min(best_s / 20.0, 1.0)   # 满分约20
    confidence = round((0.55 * share + 0.45 * strength) * 100, 1)
    return {
        "category": best,
        "confidence": confidence,
        "need_confirm": confidence < 70,
        "scores": scores,
        "reason": f"关键词命中 {best_s} 分（第二名 {sorted(scores.values())[-2] if len(scores) > 1 else 0} 分），"
                  f"财务结构信号{'命中' if strength >= 0.4 else '未命中'}",
    }
