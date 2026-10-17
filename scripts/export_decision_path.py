#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M16-B2：决策路径可视化报告导出

将 bp_screen 评分引擎的 decision_path 归因数据导出为
可交互的 HTML 报告，包含：
  - 三档结论总览
  - 一票否决 / 五闸爆雷 / 得分贡献 流程图
  - 维度贡献度条形图（纯 CSS，无外部依赖）
  - 反事实边界分析

用法：
  python scripts/export_decision_path.py                     # 全量案例
  python scripts/export_decision_path.py --case 3            # 指定案例 ID
  python scripts/export_decision_path.py --output my_report.html
  python scripts/export_decision_path.py --stdout            # 输出到 stdout

零外部依赖，纯标准库。
"""
import argparse
import html
import json
import os
import sys
import time

# ---------- 路径 ----------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = PROJECT_DIR  # 报告默认输出到项目根目录
sys.path.insert(0, PROJECT_DIR)

from bp_screen import db, scorer  # noqa: E402


# ============================================================
#  HTML 渲染引擎
# ============================================================

CSS = """
:root {
  --bg: #0f1117;
  --card: #1a1d27;
  --card-alt: #222633;
  --border: #2e3345;
  --text: #e2e4ed;
  --text-dim: #8b8fa3;
  --pass: #34d399;
  --dig: #fbbf24;
  --fail: #f87171;
  --veto: #ef4444;
  --gate: #fb923c;
  --score: #60a5fa;
  --accent: #818cf8;
  --bar-bg: #2a2e3d;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}
h1 { font-size: 1.8em; margin-bottom: 6px; }
h2 { font-size: 1.3em; margin: 28px 0 12px; color: var(--accent);
     border-bottom: 1px solid var(--border); padding-bottom: 6px; }
h3 { font-size: 1.05em; margin: 18px 0 8px; }
.meta { color: var(--text-dim); font-size: 0.85em; margin-bottom: 20px; }
.meta span { margin-right: 18px; }

/* 结论卡 */
.verdict-box {
  display: flex; align-items: center; gap: 20px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; margin-bottom: 8px;
}
.verdict-badge {
  font-size: 2em; font-weight: 700; padding: 8px 22px;
  border-radius: 10px; color: #fff; min-width: 80px; text-align: center;
}
.verdict-badge.PASS { background: rgba(52,211,153,0.2); color: var(--pass); }
.verdict-badge.DIG  { background: rgba(251,191,36,0.2); color: var(--dig); }
.verdict-badge.FAIL { background: rgba(248,113,113,0.2); color: var(--fail); }
.verdict-info { flex: 1; }
.verdict-info .score { font-size: 1.5em; font-weight: 600; }
.verdict-info .reason { color: var(--text-dim); font-size: 0.9em; margin-top: 4px; }

/* 路径卡 */
.path-item {
  display: flex; align-items: flex-start; gap: 14px;
  background: var(--card); border: 1px solid var(--border);
  border-left: 4px solid var(--border);
  border-radius: 8px; padding: 12px 16px; margin: 8px 0;
  transition: background 0.15s;
}
.path-item:hover { background: var(--card-alt); }
.path-item.veto  { border-left-color: var(--veto); }
.path-item.gate  { border-left-color: var(--gate); }
.path-item.score { border-left-color: var(--score); }

.path-rank {
  font-size: 1.4em; font-weight: 700; color: var(--text-dim);
  min-width: 32px; text-align: center; padding-top: 2px;
}
.path-content { flex: 1; }
.path-type {
  display: inline-block; font-size: 0.75em; font-weight: 600;
  padding: 2px 8px; border-radius: 4px; margin-bottom: 4px;
}
.path-type.veto  { background: rgba(239,68,68,0.2);  color: var(--veto); }
.path-type.gate  { background: rgba(251,146,60,0.2);  color: var(--gate); }
.path-type.score { background: rgba(96,165,250,0.2);  color: var(--score); }
.path-name { font-weight: 600; font-size: 0.95em; }
.path-detail { color: var(--text-dim); font-size: 0.85em; margin-top: 2px; }
.path-impact { color: var(--accent); font-size: 0.82em; margin-top: 3px;
               font-style: italic; }

/* 反事实 */
.cf-box {
  background: var(--card); border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px; padding: 14px 18px; margin: 12px 0;
}
.cf-label { font-size: 0.78em; font-weight: 600; color: var(--accent);
            text-transform: uppercase; letter-spacing: 0.5px; }
.cf-text { font-size: 0.92em; margin-top: 4px; }

/* 条形图 */
.bar-chart { margin: 12px 0; }
.bar-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
.bar-label { width: 180px; font-size: 0.85em; text-align: right;
             color: var(--text-dim); flex-shrink: 0; }
.bar-track { flex: 1; height: 22px; background: var(--bar-bg);
             border-radius: 4px; overflow: hidden; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s; }
.bar-value { width: 60px; font-size: 0.85em; font-weight: 600;
             flex-shrink: 0; }

/* 维度总览 */
.dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 10px; margin: 12px 0; }
.dim-card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px;
}
.dim-name { font-size: 0.85em; color: var(--text-dim); }
.dim-score { font-size: 1.3em; font-weight: 700; }
.dim-weight { font-size: 0.8em; color: var(--text-dim); }
.dim-bar { height: 4px; background: var(--bar-bg); border-radius: 2px;
           margin-top: 6px; overflow: hidden; }
.dim-bar-fill { height: 100%; border-radius: 2px; }

/* 案例导航 */
.case-nav { display: flex; gap: 6px; flex-wrap: wrap; margin: 16px 0; }
.case-nav a {
  display: inline-block; padding: 4px 12px; font-size: 0.82em;
  background: var(--card); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text); text-decoration: none;
}
.case-nav a:hover { border-color: var(--accent); }
.case-nav a.active { border-color: var(--accent); background: rgba(129,140,248,0.1); }

/* 页脚 */
footer { margin-top: 36px; padding-top: 16px;
         border-top: 1px solid var(--border);
         color: var(--text-dim); font-size: 0.78em; text-align: center; }

/* 响应式 */
@media (max-width: 768px) {
  body { padding: 12px; }
  .verdict-box { flex-direction: column; align-items: flex-start; }
  .bar-label { width: 120px; }
  .dim-grid { grid-template-columns: 1fr 1fr; }
}
"""


def _color_bar(score):
    if score is None:
        return "#4a4e5e"
    if score >= 80:
        return "var(--pass)"
    if score >= 60:
        return "var(--dig)"
    if score >= 40:
        return "var(--gate)"
    return "var(--fail)"


def _escape(s):
    return html.escape(str(s or ""))


def render_verdict(ev):
    verdict = ev["verdict"] or "NONE"
    cls = {"PASS": "PASS", "DIG": "DIG", "FAIL": "FAIL"}.get(verdict, "FAIL")
    score = ev["card"]["total"]
    score_range = ev["card"]["total_range"]
    total_text = f"{score} / 100" if score is not None else "N/A"
    range_text = f"区间 {score_range[0]}–{score_range[1]}" if score is not None else ""
    reason = ev["verdict_reason"]
    v_name = ev["verdict_name"]
    veto_n = len(ev["vetoes_fired"])
    gate_n = len(ev["gates_fired"])
    flags = ""
    if veto_n:
        flags += f" · {veto_n} 项否决"
    if gate_n:
        flags += f" · {gate_n} 项爆雷"
    return f"""
<div class="verdict-box">
  <div class="verdict-badge {cls}">{_escape(v_name)}</div>
  <div class="verdict-info">
    <div class="score">{total_text} <span style="font-size:0.55em;color:var(--text-dim)">{range_text}</span></div>
    <div class="reason">{_escape(reason)}{flags}</div>
  </div>
</div>"""


def render_path_items(ev):
    items = ev["decision_path"]
    if not items:
        return '<p style="color:var(--text-dim)">无决策路径数据</p>'
    html_parts = []
    for item in items:
        itype = item["type"]
        if "否决" in itype:
            cls = "veto"
        elif "爆雷" in itype:
            cls = "gate"
        else:
            cls = "score"
        rank_html = f'<div class="path-rank">{item["rank"]}</div>' if item.get("rank") else '<div class="path-rank"></div>'
        detail = _escape(item["detail"])
        impact = _escape(item.get("impact", ""))
        name = _escape(item["name"])
        html_parts.append(f"""
<div class="path-item {cls}">
  {rank_html}
  <div class="path-content">
    <span class="path-type {cls}">{_escape(itype)}</span>
    <div class="path-name">{name}</div>
    <div class="path-detail">{detail}</div>
    {"<div class='path-impact'>" + impact + "</div>" if impact else ""}
  </div>
</div>""")
    return "\n".join(html_parts)


def render_counterfactual(ev):
    cf = ev.get("counterfactual")
    if not cf or not cf.get("text"):
        return ""
    return f"""
<div class="cf-box">
  <div class="cf-label">反事实分析 · {_escape(cf.get('type', '翻档边界'))}</div>
  <div class="cf-text">{_escape(cf['text'])}</div>
</div>"""


def render_bar_chart(ev):
    """维度贡献度条形图"""
    items = [p for p in ev["decision_path"] if p["type"] == "得分贡献"]
    if not items:
        return ""
    # 按贡献降序
    items.sort(key=lambda x: -x.get("contribution", 0))
    max_contrib = max(p.get("contribution", 0) for p in items) if items else 1

    bars = []
    for p in items:
        contrib = p.get("contribution", 0)
        gap = p.get("gap_to_full", 0)
        width_pct = (contrib / max_contrib * 100) if max_contrib > 0 else 0
        name = _escape(p["name"])
        contrib_val = f"{contrib:.1f}分"
        gap_val = f"距满分+{gap:.1f}"
        bars.append(f"""
<div class="bar-row">
  <div class="bar-label">{name}</div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{width_pct}%;background:var(--score)"
         title="贡献 {contrib_val}，{gap_val}"></div>
  </div>
  <div class="bar-value">{contrib_val}</div>
</div>""")

    return f"""
<h3>维度贡献度（按贡献排序）</h3>
<div class="bar-chart">
{''.join(bars)}
</div>"""


def render_dimension_cards(ev):
    """六维评分卡总览"""
    dims = ev["card"]["dimensions"]
    if not dims:
        return ""
    cards = []
    for d in dims:
        score = d["score"]
        color = _color_bar(score)
        score_text = f"{score}" if score is not None else "N/A"
        missing = " ⚠️ 缺失" if score is None else ""
        cards.append(f"""
<div class="dim-card">
  <div class="dim-name">{_escape(d['name'])}</div>
  <div class="dim-score" style="color:{color}">{score_text}<span style="font-size:0.5em;color:var(--text-dim)">/100</span></div>
  <div class="dim-weight">权重 {d['weight']}%{missing}</div>
  <div class="dim-bar"><div class="dim-bar-fill" style="width:{score or 0}%;background:{color}"></div></div>
</div>""")
    return f"""
<h3>维度评分总览</h3>
<div class="dim-grid">
{''.join(cards)}
</div>"""


def render_case_report(case, ev, n):
    """单个案例的完整报告"""
    category_name = ""
    try:
        from bp_screen.rules import CATEGORIES
        category_name = CATEGORIES.get(case["category"], {}).get("name", case["category"])
    except Exception:
        category_name = case["category"]

    return f"""
<h2>{_escape(case['name'])}</h2>
<div class="meta">
  <span>分类: {_escape(category_name)}</span>
  <span>规则: {_escape(ev['rules_version'])}</span>
  <span>案例ID: {case['id']}</span>
</div>
{render_verdict(ev)}
{render_dimension_cards(ev)}
{render_path_items(ev)}
{render_counterfactual(ev)}
{render_bar_chart(ev)}
"""


def render_index(all_reports):
    """全量案例索引页"""
    nav_items = []
    for i, r in enumerate(all_reports):
        case = r["case"]
        ev = r["ev"]
        verdict = ev["verdict"] or "NONE"
        v_color = {"PASS": "var(--pass)", "DIG": "var(--dig)", "FAIL": "var(--fail)"}.get(verdict, "var(--text-dim)")
        score = ev["card"]["total"]
        score_text = f"{score}" if score is not None else "—"
        active = " active" if i == 0 else ""
        nav_items.append(
            f'<a href="#case-{case["id"]}" class="{active.strip()}">'
            f'{_escape(case["name"])}'
            f' <span style="color:{v_color};font-weight:700">{score_text}</span></a>'
        )

    return f"""
<h1>决策路径可视化报告</h1>
<div class="meta">
  <span>生成时间: {time.strftime('%Y-%m-%d %H:%M')}</span>
  <span>案例数: {len(all_reports)}</span>
  <span>规则版本: {all_reports[0]['ev']['rules_version'] if all_reports else 'N/A'}</span>
</div>
<div class="case-nav">
{''.join(nav_items)}
</div>
{''.join(f'<div id="case-{r["case"]["id"]}">{render_case_report(r["case"], r["ev"], r["n"])}</div>' for r in all_reports)}
"""


# ============================================================
#  数据采集
# ============================================================

def render_mermaid(ev, case):
    """M16-B2 Mermaid flowchart 输出：把决策路径渲染为 Mermaid 文本。

    Mermaid 支持 GitHub/VSCode/Notion 等主流平台的原生渲染，
    把"决策路径"从 HTML 报告延伸到代码评审/文档嵌入场景。

    结构：
      TD 图 · 起点(案例) → 一票否决检查 → 五闸检查 → 得分卡 → 结论
      每个节点用类名标注色彩（veto/gate/score/pass/dig/fail）。
    """
    cid = case["id"]
    name = case.get("name", f"case-{cid}")
    verdict = ev["verdict"]
    lines = [
        "flowchart TD",
        f'    START(["案例 {cid}: {name}"])',
        '    START --> VETO{{"一票否决检查"}}',
    ]
    vetoes = ev.get("vetoes_fired", [])
    if vetoes:
        v0 = vetoes[0]
        vname = v0.get("name", v0) if isinstance(v0, dict) else v0
        lines.append(f'    VETO --> VETO_HIT["一票否决: {vname}"]:::veto')
        lines.append(f'    VETO_HIT --> END_FAIL(["结论: FAIL"]):::fail')
    else:
        lines.append(f'    VETO --> GATE{{"五闸检查"}}')
        gates = ev.get("gates_fired", [])
        if gates:
            for g in gates:
                gname = g.get("name", g) if isinstance(g, dict) else g
                lines.append(f'    GATE --> GATE_HIT["爆雷: {gname}"]:::gate')
            lines.append(f'    GATE_HIT --> END_FAIL2(["结论: DIG/FAIL"]):::fail')
        else:
            lines.append(f'    GATE --> SCORE["得分卡 {ev["card"]["total"]}/100"]:::score')
            lines.append(f'    SCORE --> END(["结论: {verdict}"]):::{verdict.lower()}')

    # 得分贡献明细
    score_items = [p for p in ev.get("decision_path", []) if p["type"] == "得分贡献"]
    if score_items and verdict != "FAIL":
        def _impact_abs(x):
            try:
                return abs(float(x.get("impact", 0) or 0))
            except (TypeError, ValueError):
                return 0.0
        top = sorted(score_items, key=_impact_abs, reverse=True)[:5]
        for i, it in enumerate(top):
            try:
                impact = float(it.get("impact", 0) or 0)
                sign = "+" if impact >= 0 else ""
                impact_str = f"{sign}{impact:.1f}"
            except (TypeError, ValueError):
                impact_str = str(it.get("impact", 0))
            lines.append(
                f'    SCORE --> S{i}[ "{it["name"]} ({impact_str})"]:::score')

    lines.append("")
    lines.append("classDef veto fill:#ef4444,stroke:#b91c1c,color:#fff;")
    lines.append("classDef gate fill:#fb923c,stroke:#c2410c,color:#fff;")
    lines.append("classDef score fill:#60a5fa,stroke:#1d4ed8,color:#fff;")
    lines.append("classDef pass fill:#34d399,stroke:#059669,color:#fff;")
    lines.append("classDef dig fill:#fbbf24,stroke:#d97706,color:#1f2937;")
    lines.append("classDef fail fill:#f87171,stroke:#b91c1c,color:#fff;")
    return "\n".join(lines)


def collect_case_evaluation(case):
    """对一个案例运行评分引擎，返回 (case, evaluation, normalized)"""
    m = case["metrics"]
    if isinstance(m, str):
        m = json.loads(m) if m else {}
    elif m is None:
        m = {}

    n = dict(m)
    # 归一化派生字段
    if "revenue" in n and "revenue_prev" in n and n["revenue_prev"]:
        n["revenue_growth"] = round((n["revenue"] - n["revenue_prev"]) / n["revenue_prev"] * 100, 1)
    if "cash_balance" in n and "monthly_burn" in n and n["monthly_burn"]:
        n["cash_months"] = round(n["cash_balance"] / n["monthly_burn"], 1)
    if "cash_balance" in n and "monthly_burn" in n and n["monthly_burn"]:
        n["runway_months"] = round(n["cash_balance"] / n["monthly_burn"], 1)

    ev = scorer.evaluate(case["category"], n)
    return {"case": case, "ev": ev, "n": n}


# ============================================================
#  CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="M16-B2 决策路径可视化报告导出")
    parser.add_argument("--case", type=int, help="指定案例 ID（逗号分隔多个）")
    parser.add_argument("--output", "-o", default="decision_path_report.html",
                        help="输出 HTML 文件路径")
    parser.add_argument("--stdout", action="store_true", help="输出到 stdout")
    parser.add_argument("--stdout-json", action="store_true",
                        help="输出结构化 JSON 到 stdout")
    parser.add_argument("--mermaid", action="store_true",
                        help="输出 Mermaid flowchart 到 stdout（供 GitHub/VSCode 渲染）")
    args = parser.parse_args()

    # 获取案例
    cases = db.all_cases()
    if args.case:
        ids = {int(x.strip()) for x in str(args.case).split(",")}
        cases = [c for c in cases if c["id"] in ids]
        if not cases:
            print(f"未找到案例 ID: {args.case}", file=sys.stderr)
            sys.exit(1)

    # 过滤掉 benchmark（它们是基准数据，不是评估对象）
    cases = [c for c in cases if not c["is_benchmark"]]

    if not cases:
        print("无可用案例", file=sys.stderr)
        sys.exit(1)

    # 采集评估数据
    all_reports = []
    for c in cases:
        try:
            all_reports.append(collect_case_evaluation(c))
        except Exception as e:
            print(f"案例 {c['id']} 评估失败: {e}", file=sys.stderr)

    if not all_reports:
        print("所有案例评估失败", file=sys.stderr)
        sys.exit(1)

    # JSON 输出
    if args.stdout_json:
        output = []
        for r in all_reports:
            output.append({
                "case_id": r["case"]["id"],
                "name": r["case"]["name"],
                "category": r["case"]["category"],
                "verdict": r["ev"]["verdict"],
                "verdict_name": r["ev"]["verdict_name"],
                "total_score": r["ev"]["card"]["total"],
                "total_range": r["ev"]["card"]["total_range"],
                "verdict_reason": r["ev"]["verdict_reason"],
                "gates_fired": r["ev"]["gates_fired"],
                "vetoes_fired": r["ev"]["vetoes_fired"],
                "decision_path": r["ev"]["decision_path"],
                "counterfactual": r["ev"].get("counterfactual"),
                "dimensions": r["ev"]["card"]["dimensions"],
            })
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    if args.mermaid:
        # Mermaid flowchart 输出（多案例拼接，用 --- 分隔）
        parts = []
        for r in all_reports:
            parts.append(f'%% 案例 {r["case"]["id"]}: {r["case"]["name"]}\n'
                         f'{render_mermaid(r["ev"], r["case"])}')
        print("\n---\n\n".join(parts))
        return

    # HTML 输出
    nav = render_index(all_reports)
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>决策路径可视化报告</title>
<style>
{CSS}
</style>
</head>
<body>
{nav}
<footer>
  智慧农业生态 · 决策路径可视化报告 · M16-B2 · 由 bp_screen 评分引擎自动生成
</footer>
</body>
</html>"""

    if args.stdout:
        print(full_html)
    else:
        output_path = os.path.join(OUTPUT_DIR, args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_html)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"✅ 报告已导出: {output_path} ({size_kb:.1f} KB)")
        print(f"   案例数: {len(all_reports)}")


if __name__ == "__main__":
    main()
