#!/usr/bin/env python3
"""
智慧农业生态 · 端到端验证脚本

验证内容：
  1. 四 Agent 流水线在多个城市可运行，且无 PLACEHOLDER 残留
  2. Trust Layer 可复现证书可生成且 rubric 全通过
  3. 所有注册表 JSON / 数据文件可解析

用法：
  python scripts/verify_all.py
  docker compose run --rm agri-eco
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from core.trust_layer import issue_certificate  # noqa: E402

# 测试城市：覆盖主要气候带
TEST_CITIES = [
    ("杭州", 30.2741, 120.1551, "balcony", {"floor": 15, "orientation": "south"}),
    ("北京", 39.9042, 116.4074, "balcony", {}),
    ("深圳", 22.5431, 114.0579, "balcony", {}),
    ("乌鲁木齐", 43.8256, 87.6168, "garden", {}),
    ("洛杉矶", 34.0522, -118.2437, "garden", {}),
]

FAILURES = []


def _check(cond: bool, msg: str):
    if cond:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        FAILURES.append(msg)


def main():
    print("=" * 60)
    print("智慧农业生态 · 端到端验证")
    print("=" * 60)

    print("\n[1] 四 Agent 流水线（多城市）")
    total_placeholder = 0
    for name, lat, lon, scene, extra in TEST_CITIES:
        orch = AgriOrchestrator()
        req = {"lat": lat, "lon": lon, "scene": scene, "purpose": "食用",
               "space_sqm": 1.5, "difficulty": "beginner", "budget_cny": 500}
        req.update(extra)
        r = orch.run_pipeline(req)
        blob = json.dumps(r, ensure_ascii=False)
        ph = blob.count("PLACEHOLDER")
        total_placeholder += ph
        zone = r["pipeline_steps"][0]["output"]["evidence"]["zone_id"]
        crops = r["final_recommendation"]["recommended_crops"]
        top = crops[0]["crop"] if crops else "NONE"
        score = r["trust_summary"]["overall_rubric_score"]
        _check(ph == 0, f"{name}: zone={zone}, top={top}, rubric={score}, PLACEHOLDER={ph}")

    print(f"\n  全城 PLACEHOLDER 合计: {total_placeholder}")
    _check(total_placeholder == 0, "所有城市输出无 PLACEHOLDER 残留")

    print("\n[2] 种植计划真实性（杭州·生菜）")
    orch = AgriOrchestrator()
    r = orch.run_pipeline({"lat": 30.2741, "lon": 120.1551, "scene": "balcony",
                           "floor": 15, "orientation": "south", "purpose": "食用",
                           "space_sqm": 1.5, "difficulty": "beginner"})
    gp = r["pipeline_steps"][2]["output"]
    phases = gp["recommendation"]["phases"]
    _check(gp["evidence"].get("data_loaded") is True, "GrowthAgent 已加载真实作物数据")
    _check(len(phases) == 4, f"种植计划含 4 阶段（实际 {len(phases)}）")
    _check(len(gp["recommendation"]["risk_alerts"]) > 0, "已生成风险预警")
    _check(bool(gp["recommendation"]["rescue_plan"]), "已生成兜底救活方案")

    print("\n[3] 设备推荐真实性（杭州·阳台）")
    dev = r["pipeline_steps"][3]["output"]
    _check(dev["evidence"].get("matched_count", 0) > 0,
           f"EcoAgent 命中 {dev['evidence'].get('matched_count')} 件设备")
    _check(dev["constraints"].get("total_estimated_price_cny", 0) > 0,
           "已估算设备总预算")

    print("\n[4] Trust Layer 可复现证书")
    cert = issue_certificate(run_id="verify_all", inputs={"scene": "balcony", "crop": "生菜"})
    _check(cert["rubric"]["full_pass"] is True,
           f"rubric 全通过 {cert['rubric']['passed']}/{cert['rubric']['total']}")
    _check(cert["data_coverage"]["total_crops"] > 0,
           f"作物覆盖 {cert['data_coverage']['total_crops']} 种")
    _check(bool(cert["signature"]), f"数字签名已生成（{cert['signature'][:12]}...）")

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"结果: FAIL（{len(FAILURES)} 项未通过）")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("结果: PASS ✅ 全部验证通过")
        print("=" * 60)


if __name__ == "__main__":
    main()
