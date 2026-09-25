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

import atexit
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# 写盘隔离
# ---------------------------------------------------------------------------
# run_pipeline 自 B1/B2 起会写长期记忆与检索索引。本脚本是「验证」而不是「生产」，
# 6 次 pipeline 的输出不应沉入真实记忆库——否则每跑一次验证就往仓库数据里写 6 条
# 合成记录，harness 观测区随之漂移（已踩过）。
# 需要真实验证记忆写入路径时，设 AGRI_VERIFY_NO_ISOLATE=1 关闭隔离。
_TMPD = None
_SAVED_ENV = {k: os.environ.get(k) for k in
              ("AGRI_LONG_TERM_MEMORY", "AGRI_SEARCH_INDEX")}


def _restore_env():
    """退出时还原环境变量并清掉临时目录。"""
    for k, v in _SAVED_ENV.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.environ.pop("AGRI_MEMORY_SYNTHETIC", None)
    if _TMPD:
        shutil.rmtree(_TMPD, ignore_errors=True)


if not os.environ.get("AGRI_VERIFY_NO_ISOLATE"):
    _TMPD = tempfile.mkdtemp(prefix="agri_verify_")
    os.environ["AGRI_LONG_TERM_MEMORY"] = os.path.join(_TMPD, "mem.json")
    os.environ["AGRI_SEARCH_INDEX"] = os.path.join(_TMPD, "idx.db")
    os.environ["AGRI_MEMORY_SYNTHETIC"] = "1"
    atexit.register(_restore_env)

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

    print("\n[5] 引擎 v2（RSI / HCI / 技能审计 / harness 漂移）")
    from engine.eval import eval_hci
    import engine.skill_factory as sf

    hci = eval_hci()
    _check(hci["status"] == "IMPLEMENTED", "HCI 北极星已接入 eval")
    _check(hci["autonomy_level"] in ("B0", "L1", "L2", "L3", "L4", "L5"),
           f"自主权级别 {hci['autonomy_level']}（HCI={hci['hci']}，"
           f"{hci['closed']}/{hci['total']} 门禁闭合）")
    _check(all(isinstance(hci['gate_gaps'][g], str) for g in hci["open_gates"]),
           f"未闭合门禁均给出缺口说明（{len(hci['open_gates'])} 条）")

    audit = sf.audit()
    _check(audit["rot_count"] == 0, f"技能零腐化（{audit['total']} 个技能，"
                                     f"CLS 分布 {audit['cls_distribution']}）")

    harness_path = os.path.join(ROOT, "harness", "manifest.json")
    _check(os.path.exists(harness_path), "harness 清单已生成")
    if os.path.exists(harness_path):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import harness_sync
        _check(harness_sync.cmd_check() == 0, "harness 声明区无漂移")

    print("\n[6] 数据质量门禁（真实性红线 + 数值口径）")
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    try:
        import data_quality_gate
        dq_exit = data_quality_gate.run()
    except Exception as e:  # noqa: BLE001
        dq_exit = 1
        print(f"  ⚠️ 数据质量门禁异常: {e}")
    _check(dq_exit == 0, f"数据质量门禁全通过（exit={dq_exit}）")

    import engine.context_compact as cc
    fused = cc.fuse_actions([
        {"act_type": "water", "target": "A", "amount_ml": 200},
        {"act_type": "water", "target": "B", "amount_ml": 150},
    ])
    _check(fused["fusion"]["merged"] == 1 and fused["actions"][0]["amount_ml"] == 350,
           "动作融合正确（相邻同类合并、数值求和）")
    compact = cc.reduce_output({"items": [{"i": i} for i in range(10)]}, max_items=3)
    _check(compact["payload"]["items"][-1].get("__folded")
           and len(compact["payload"]["items"][-1]["evidence_refs"]) == 7,
           "上下文压缩保留证据指纹")

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
