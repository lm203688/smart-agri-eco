#!/usr/bin/env python3
"""
智慧农业生态 · Demo 板块完整性自检

启动 demo server 的进程内实例，逐一探测 11 个前端板块对应的后端端点，
区分三种状态：
  OK    端点返回 200 且含有效业务字段（非 error / 非空壳）
  ERR   端点返回非 200 或响应含 error 字段（后端异常）
  EMPTY 端点返回 200 但业务字段为空 / 占位 / 缺关键结构（前端会显示空白或「暂无」）

用法：
  python scripts/assess_completeness.py
输出：ASCII 表格 + 每板块诊断说明，便于定位「很多板块不完整」的真因。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

import demo_server  # noqa: E402

PORT = int(os.environ.get("AGRI_ASSESS_PORT", "8011"))
HOST = "127.0.0.1"
BASE = f"http://{HOST}:{PORT}"

# ---------------------------------------------------------------------------
# 样本 payload：尽量贴近前端真实调用，覆盖每个板块的最小可跑输入
# ---------------------------------------------------------------------------
SAMPLES = {
    "recommend": ("POST", "/api/recommend", {
        "lat": 30.2741, "lon": 120.1551, "scene": "balcony", "floor": "3",
        "orientation": "south", "purpose": "home", "space_sqm": 5,
        "difficulty": "easy", "budget_cny": 500,
    }),
    "diagnose": ("POST", "/api/pest_diagnose", {
        "crop": "tomato", "symptom_description": "下部叶片发黄卷曲",
        "growth_stage": "vegetative",
    }),
    "nutrition": ("POST", "/api/nutrition_plan", {
        "crop": "tomato", "scene": "balcony", "growth_stage": "vegetative",
        "growth_days": 20, "container_volume_l": 10,
    }),
    "phenology": ("POST", "/api/season_advisory", {
        "monthly_mean_c": [5, 7, 12, 18, 23, 27, 31, 30, 26, 20, 13, 7],
        "crops": ["tomato"],
    }),
    "soil": ("POST", "/api/soil_profile", {
        "lat": 30.2741, "lon": 120.1551,
        "crop": "番茄", "online": False, "timeout": 4,
    }),
    "recipe": ("POST", "/api/schedule", {
        "crop": "生菜", "zone": "subtropical_wet",
    }),
    "search": ("POST", "/api/search", {"query": "番茄 温度", "corpus": "all", "k": 5}),
    "memory": ("POST", "/api/memory_recall", {"query": "番茄 种植", "k": 3}),
    "feedback": ("POST", "/api/feedback", {
        "zone_id": "Z_ASSESS", "crop": "tomato", "survival_rate": 0.9,
        "yield_rating": 4, "user_rating": 4, "note": "完整性自检",
    }),
    "skills": ("GET", "/api/skills", None),
    "work_item": ("POST", "/api/work_item", {"title": "完整性自检", "actor": "assess"}),
    "bpscreen": ("POST", "/api/bp_screen", {
        "company": "评估测试公司", "category": "垂直农场",
        "text": (
            "评估测试公司是一家做垂直农场的企业，本轮拟融资 3000 万人民币用于建设 5 层"
            "植物工厂。团队 12 人，核心来自温室自动化。当前已签约 2 家商超渠道，月营收约"
            "40 万，毛利率 28%。已获 1 项 LED 光谱专利。本轮资金主要用于扩产，预计 18 个月"
            "内实现盈亏平衡。竞品包括某上市设施农业企业。风险在于电费占成本 35%，若电价"
            "上涨将明显压缩毛利。种子库未能核验其专利号。"
        ),
    }),
}


def _post(path, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _get(path):
    req = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _call(method, path, payload):
    if method == "GET":
        return _get(path)
    return _post(path, payload)


def _is_empty(name, body):
    """判断业务字段是否为空壳/占位。每个板块定义自己的关键字段。"""
    if not isinstance(body, dict):
        return "响应非 JSON 对象"
    if body.get("error"):
        return f"error: {body['error']}"
    if name == "recommend":
        fr = body.get("final_recommendation") or {}
        if not (fr.get("recommended_crops") or body.get("crops") or body.get("plan")):
            return "无作物/方案字段"
    elif name == "diagnose":
        if not body.get("diagnosis") and not body.get("disease") and not body.get("result"):
            return "无诊断结果"
    elif name == "nutrition":
        if not body.get("recommendation") and not body.get("plan") and not body.get("result"):
            return "无养分方案"
    elif name == "phenology":
        if not body.get("windows") and not body.get("advice") and not body.get("report"):
            return "无播期窗口"
    elif name == "soil":
        soil = body.get("soil") or {}
        if body.get("resolution") == "unavailable":
            return "无土壤数据字段（resolution=unavailable）"
        if not (soil.get("ph_range") or soil.get("texture_hint") or soil.get("properties")):
            if not (body.get("online_attempt") or {}).get("available"):
                return "无土壤数据字段"
    elif name == "recipe":
        if not body.get("recipe") and not body.get("anchors") and not body.get("actions"):
            return "无配方/锚点/动作"
    elif name == "search":
        if not body.get("hits"):
            return "检索命中为空"
    elif name == "memory":
        if not body.get("hits"):
            return "记忆召回为空"
    elif name == "feedback":
        if not body.get("ok") and not body.get("recorded") and not body.get("adapt_score"):
            return "无反馈回写结果"
    elif name == "skills":
        if not body.get("skills"):
            return "技能列表为空"
    elif name == "work_item":
        if not body.get("item_id") and not body.get("state"):
            return "无工作项返回"
    elif name == "bpscreen":
        if not body.get("verdict") and body.get("status") != "invalid_category":
            return "无初筛结论"
    return None


def main():
    srv = ThreadingHTTPServer((HOST, PORT), demo_server.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.6)

    rows = []
    diag = []
    try:
        for name, (method, path, payload) in SAMPLES.items():
            try:
                status, body = _call(method, path, payload)
            except Exception as e:
                rows.append((name, "ERR", f"异常: {type(e).__name__}: {str(e)[:80]}"))
                diag.append(f"[{name}] 调用异常：{e}")
                continue
            if status != 200:
                rows.append((name, "ERR", f"HTTP {status}"))
                diag.append(f"[{name}] HTTP {status}：{json.dumps(body, ensure_ascii=False)[:200]}")
                continue
            empty_reason = _is_empty(name, body)
            if empty_reason:
                if empty_reason.startswith("error:"):
                    rows.append((name, "ERR", empty_reason[6:].strip()[:90]))
                    diag.append(f"[{name}] 后端报错：{empty_reason}")
                else:
                    rows.append((name, "EMPTY", empty_reason[:90]))
                    diag.append(f"[{name}] 空壳/占位：{empty_reason}")
            else:
                rows.append((name, "OK", "正常"))
    finally:
        srv.shutdown()

    print("\n=== 智慧农业生态 · Demo 板块完整性自检 ===")
    print(f"{'板块':<10}{'状态':<7}{'说明'}")
    print("-" * 70)
    for name, state, note in rows:
        print(f"{name:<10}{state:<7}{note}")
    print("-" * 70)
    ok = sum(1 for _, s, _ in rows if s == "OK")
    print(f"汇总: {ok}/{len(rows)} OK, "
          f"{sum(1 for _,s,_ in rows if s=='ERR')} ERR, "
          f"{sum(1 for _,s,_ in rows if s=='EMPTY')} EMPTY")
    if diag:
        print("\n--- 诊断详情 ---")
        for d in diag:
            print(d)
    # 写出 JSON 报告，便于后续对比
    with open(os.path.join(ROOT, "outputs", "completeness_assess.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": rows, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  f, ensure_ascii=False, indent=2)
    print("\n报告已写 outputs/completeness_assess.json")


if __name__ == "__main__":
    main()
