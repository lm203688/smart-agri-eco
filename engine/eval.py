"""
engine/eval.py —— AI 评测基线（评审 §2.3 / P0-H）

每个 AI 能力都要有对照评测，否则无法知道是在进步还是自我感觉良好（评审硬建议）。
本模块建立评测 harness 与首个可运行基线：

已实现（真实可跑）：
  - eval_zone_consistency   ：气候分区分类与公开气候带（GAEZ/Köppen 代理）一致率
  - eval_crop_db_coverage   ：评测作物在匹配分区内的数据库覆盖情况（信息性）
  - eval_hci                ：自主权门禁闭合率（北极星，借 Theseus Labs RSI 框架）

双北极星口径：zone_consistency 度量**能力对错**，hci 度量**闭环完成度**。
一个系统可以分区判得准但闭环全开（hci=0），也可以闭环闭合但分区判错。
只看一个会自欺，故两者并列，绝不合并成单一分数。

脚手架（待数据/模型就绪，标注 NOT_IMPLEMENTED 不谎报）：
  - eval_extraction_accuracy  ：补库 Agent 抽取字段准确率（需抽取器 + 标注样本）
  - eval_pest_diagnosis_topk  ：病虫害诊断 Top-1/Top-3（需 PlantVillage 留出集 + 视觉后端）
  - eval_recipe_expert_adoption：配方专家采纳率（需农艺专家盲评 50 份）
  - eval_source_traceability  ：每条建议引用可验证率（需溯源层埋点）

用法：
    python scripts/run_eval.py
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 已实现：分区分类一致率
# ---------------------------------------------------------------------------
def eval_zone_consistency(checks: List[Dict], climate_agent) -> Dict:
    """逐条用 match_zone(lat,lon) 与公开气候带真值比对，算一致率。

    checks: [{lat, lon, expected_zone, note}]
    返回 {total, correct, rate, mismatches:[...]}
    """
    total = len(checks)
    correct = 0
    mismatches = []
    for c in checks:
        got = climate_agent.match_zone(float(c["lat"]), float(c["lon"]))
        got_zone = got.get("evidence", {}).get("zone_id", "UNKNOWN")
        ok = got_zone == c["expected_zone"]
        correct += int(ok)
        if not ok:
            mismatches.append({
                "lat": c["lat"], "lon": c["lon"],
                "expected": c["expected_zone"], "got": got_zone,
                "note": c.get("note", ""),
            })
    return {
        "total": total,
        "correct": correct,
        "rate": round(correct / total, 3) if total else 0.0,
        "mismatches": mismatches,
    }


# ---------------------------------------------------------------------------
# 已实现：作物库覆盖（信息性，不计入通过/失败）
# ---------------------------------------------------------------------------
def eval_crop_db_coverage(samples: List[Dict], climate_agent, crop_db: Dict) -> Dict:
    """samples: [{crop, lat, lon}]，检查该作物是否出现在匹配分区的作物清单中。

    这是「索引覆盖」检查，反映数据库内容广度，不等价于适宜性对错。
    """
    zones = crop_db.get("zones", {})
    total = len(samples)
    covered = 0
    gaps = []
    for s in samples:
        zone = climate_agent.match_zone(float(s["lat"]), float(s["lon"]))
        zid = zone.get("evidence", {}).get("zone_id", "")
        crops = zones.get(zid, {}).get("crops", []) if zid in zones else []
        names = {c.get("crop", "") for c in crops}
        found = s["crop"] in names
        covered += int(found)
        if not found:
            gaps.append({"crop": s["crop"], "zone": zid})
    return {
        "total": total,
        "covered": covered,
        "coverage": round(covered / total, 3) if total else 0.0,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# 已实现：自主权门禁闭合率（HCI 北极星，借 Theseus Labs RSI 框架）
# ---------------------------------------------------------------------------
def eval_hci() -> Dict:
    """度量「闭环是否真的闭合」：已闭合的自主权门禁 / 全部门禁。

    与 zone_consistency 互补：zone_consistency 度量**能力对错**，HCI 度量
    **闭环完成度**。两者并列北极星——一个系统可以「分区判得准」但闭环全开
    （HCI=0），也可以「闭环闭合」但分区判错。只看一个会自欺。

    详见 engine/rsi.py：每级自主权都要有真实产物证据，反复重测不算改进。
    """
    import importlib
    rsi = importlib.import_module("engine.rsi")
    rep = rsi.report()
    return {
        "autonomy_level": rep["autonomy"]["level"],
        "autonomy_name": rep["autonomy"]["name"],
        "hci": rep["hci"]["hci"],
        "closed": rep["hci"]["closed"],
        "total": rep["hci"]["total"],
        "closed_gates": rep["hci"]["closed_gates"],
        "open_gates": rep["hci"]["open_gates"],
        "gate_gaps": {g: rep["gates"][g]["gap"] for g in rep["hci"]["open_gates"]},
        "status": "IMPLEMENTED",
        "note": "HCI 只度量闭环完成度，不度量能力对错；与 eval_zone_consistency 并列。",
    }


# ---------------------------------------------------------------------------
# 脚手架：待数据/模型就绪（绝不谎报指标）
# ---------------------------------------------------------------------------
def eval_extraction_accuracy() -> Dict:
    return {"status": "NOT_IMPLEMENTED",
            "reason": "需补库 Agent 抽取器 + 100 条人工标注样本（评审 §2.3）"}


def eval_pest_diagnosis_topk() -> Dict:
    return {"status": "NOT_IMPLEMENTED",
            "reason": "需 PlantVillage 留出集 + 自建 200 张中文场景图 + 视觉后端（评审 §2.3）"}


def eval_recipe_expert_adoption() -> Dict:
    return {"status": "NOT_IMPLEMENTED",
            "reason": "需 3-5 位农艺专家盲评 50 份配方 vs 现行栽培规程（评审 §2.3）"}


def eval_source_traceability() -> Dict:
    return {"status": "NOT_IMPLEMENTED",
            "reason": "需溯源层埋点：每条建议的引用 url 可访问性校验（评审 §2.3）"}


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
def run_all() -> Dict:
    from agent.climate_agent import ClimateAgent  # noqa: E402

    climate = ClimateAgent()
    crop_db = _load_json(os.path.join(ROOT, "data", "crop_adapt_db.json"))
    checks = _load_json(os.path.join(ROOT, "data", "eval", "zone_checks.json"))

    # 作物库覆盖样例：每个分区挑一个代表性作物（存在=覆盖，缺失=待补）
    coverage_samples = [
        {"crop": "香蕉", "lat": 1.3521, "lon": 103.8198},      # 热带雨林
        {"crop": "番茄", "lat": 30.2741, "lon": 120.1551},     # 亚热带湿润
        {"crop": "葡萄", "lat": 34.0522, "lon": -118.2437},    # 地中海
        {"crop": "小麦", "lat": 39.9042, "lon": 116.4074},     # 温带大陆性
    ]

    return {
        "zone_consistency": eval_zone_consistency(checks, climate),
        "crop_db_coverage": eval_crop_db_coverage(coverage_samples, climate, crop_db),
        "hci": eval_hci(),
        "pending": {
            "extraction_accuracy": eval_extraction_accuracy(),
            "pest_diagnosis_topk": eval_pest_diagnosis_topk(),
            "recipe_expert_adoption": eval_recipe_expert_adoption(),
            "source_traceability": eval_source_traceability(),
        },
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(run_all())
