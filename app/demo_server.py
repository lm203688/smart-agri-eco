#!/usr/bin/env python3
"""
智慧农业生态 · 交互式 Demo 站点（零依赖）

技术栈：仅 Python 标准库（http.server + json），无需 pip 安装任何包。
启动：
    python app/demo_server.py
    # 默认 http://127.0.0.1:8000

接口：
    GET  /                      返回 index.html（前端页面）
    POST /api/recommend         {"lat","lon","scene","floor","orientation",
                                  "purpose","space_sqm","difficulty","budget_cny"}
                                 -> orchestrator.run_pipeline 结果
    POST /api/certificate       {"scene","crop"} -> trust_layer.issue_certificate 结果
    POST /api/feedback           {"zone_id","crop","survival_rate","yield_rating",
                                  "user_rating","issues","note"} -> 数据飞轮校准 adapt_score
    POST /api/pest_diagnose      {"crop","symptom_description","image_reference",
                                  "growth_stage","environment"} -> PestAgent 病虫害诊断
    POST /api/nutrition_plan      {"crop","scene","growth_stage","growth_days",
                                  "container_volume_l","start_date"} -> NutritionAgent 养分管理
    POST /api/agent              {"skill":"pest_diagnose"|"nutrition_plan"|"season_advisory",
                                  "payload":{...}} -> orchestrator.call_skill 统一路由
    GET  /api/skills             -> 注册表技能目录（含可调用方式）
    GET  /api/recipes?crop=&zone= -> Env Recipe 索引（recipe_id / zone / crop）
    GET  /api/stats              -> 平台能力盘点（数据规模 / Skill / MCP 工具 / 质量基线）
    POST /api/season_advisory    {"monthly_mean_c":[12 个月均温],"crops":[...]} 或 {lat,lon,crops} -> 物候 + 霜冻锚定播期窗口（缺月均温时按经纬度自动获取真实气候）
    POST /api/climate_fetch       {"lat","lon","years","force_refresh"} -> 实时月度气候（NASA POWER 主用 / Open-Meteo 兜底）+ provenance
    POST /api/soil_profile       {"lat","lon","zone_id","crop","online","timeout"} -> 土壤画像（在线优先→离线降级）
    POST /api/search             {"query","corpus","k","mode","min_score"} -> 本地三层检索（FTS5+bigram+向量）
    POST /api/memory_recall      {"query","skill","crop","zone","k","expand"} -> 跨会话长期记忆召回
    POST /api/work_item          {"title","actor"} -> 工作项状态机全链路演示（含追加审计）
    POST /api/schedule           {"crop","zone","observations","symptom_text"} -> Env Recipe 条件锚定调度

所有建议遵循 docs/agent_output_contract.md 输出契约（evidence/confidence/constraints/recommendation）。
"""

from __future__ import annotations

import json
import os
import sys
import base64
import uuid
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.preset_cities import load_preset_cities  # noqa: E402
from agent.pest_agent import PestAgent  # noqa: E402
from agent.nutrition_agent import NutritionAgent  # noqa: E402
from core.trust_layer import issue_certificate  # noqa: E402

PORT = int(os.environ.get("AGRI_DEMO_PORT", "8000"))
HOST = os.environ.get("AGRI_DEMO_HOST", "127.0.0.1")

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

# ---------------------------------------------------------------------------
# 写盘隔离：Demo 默认使用 data/_demo_runtime/ 下的独立存储。
# 原因：run_pipeline 会把每次推荐写入长期记忆、把检索索引落盘。若默认指向真实
# data/long_term_memory.json，用户在前端点几次「生成方案」就会把演示记录混入
# 真实数据基线——而这不会有任何报错（orchestrator 用 try/except 吞掉写盘失败，
# 接口照样返回 200）。因此默认隔离，需要接真实存储时再显式设环境变量。
#   AGRI_LONG_TERM_MEMORY / AGRI_SEARCH_INDEX / AGRI_MEMORY_SYNTHETIC
# 注意：%TEMP% 下的路径在某些沙箱策略下会 PermissionError，故改用工作区内路径。
# AGRI_FEEDBACK_DRY_RUN：record_feedback 会同时写 feedback_log 与 crop_adapt_db（后者
#   把 adapt_score 伪校准成实测分），且这两个文件不受 git 跟踪 → 污染完全静默。
#   demo 里必须整体跳过写入，只隔离 feedback_log 挡不住 crop_db 那一半。
#   2026-09-17 实踩：前端冒烟 3 次，小白菜 adapt_score 0.96 被校准成 0.951。
# ---------------------------------------------------------------------------
_RUNTIME_DIR = os.path.join(ROOT, "data", "_demo_runtime")
os.makedirs(_RUNTIME_DIR, exist_ok=True)
os.environ.setdefault("AGRI_LONG_TERM_MEMORY",
                      os.path.join(_RUNTIME_DIR, "long_term_memory.json"))
os.environ.setdefault("AGRI_SEARCH_INDEX",
                      os.path.join(_RUNTIME_DIR, "search_index.db"))
os.environ.setdefault("AGRI_FEEDBACK_LOG",
                      os.path.join(_RUNTIME_DIR, "feedback_log.json"))
os.environ.setdefault("AGRI_MEMORY_SYNTHETIC", "1")
os.environ.setdefault("AGRI_FEEDBACK_DRY_RUN", "1")
# BP 初筛引擎（bp_screen）：Demo 展示不写入 bp_screen/data/cases.db 真实种子库，
# 该文件不受 git 跟踪、污染完全静默（与 feedback_log 同一类脚枪）。
os.environ.setdefault("AGRI_BP_DB",
                      os.path.join(_RUNTIME_DIR, "bp_screen_demo.db"))

# 预设城市（用于前端下拉，避免依赖地理编码 API）。
# 唯一数据源：data/preset_cities.json（2026-09-23 收敛，此前本文件与 mcp/server.py
# 各持一份硬编码副本 → 漂移风险源）。两侧均经 agent/preset_cities.py 读取。
PRESET_CITIES = load_preset_cities()


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                with open(INDEX_PATH, "r", encoding="utf-8") as f:
                    self._send_html(f.read())
            except Exception as e:
                self._send_html(f"<h1>index.html 缺失：{e}</h1>")
        elif path == "/api/cities":
            self._send_json({"cities": PRESET_CITIES})
        elif path == "/api/skills":
            try:
                orch = AgriOrchestrator()
                self._send_json({"skills": orch.list_skills()})
            except Exception as e:
                self._send_json({"error": f"skills 失败: {e}"}, status=500)
        elif path == "/api/bp_list":
            # 「我的评估」历史列表：读 cases.db（demo 隔离库）
            try:
                self._send_json(_bp_list())
            except Exception as e:
                self._send_json({"error": f"bp_list 失败: {e}"}, status=500)
        elif path == "/api/recipes":
            # 列出 Env Recipe 索引（recipe_id -> 文件名），支持 crop / zone 过滤
            import glob as _glob
            import re as _re
            pattern = f"{os.path.join(ROOT, 'data', 'env_recipes')}/*.json"
            items = []
            for fp in sorted(_glob.glob(pattern)):
                rid = _re.sub(r"\.json$", "", os.path.basename(fp))
                zone, _, crop = rid.partition("__")
                items.append({"recipe_id": rid, "zone": zone, "crop": crop, "file": os.path.basename(fp)})
            qs = parse_qs(urlparse(self.path).query)  # 必须 URL 解码，否则中文过滤条件恒为 0 命中
            crop_f = (qs.get("crop") or [""])[0]
            zone_f = (qs.get("zone") or [""])[0]
            if crop_f:
                items = [i for i in items if crop_f in i["crop"]]
            if zone_f:
                items = [i for i in items if zone_f in i["zone"]]
            self._send_json({"total": len(items), "recipes": items[:60]})
        elif path == "/api/crops":
            # 知识底座·作物库：真实作物条目，支持 zone / q 过滤
            qs = parse_qs(urlparse(self.path).query)
            self._send_json(_crops_browse(
                (qs.get("zone") or [""])[0],
                (qs.get("q") or [""])[0].strip()))
        elif path == "/api/zones":
            # 知识底座·分区库：6 个全球气候分区的完整画像
            self._send_json(_zones_browse())
        elif path == "/api/pests":
            # 知识底座·病虫害库：来自 agent/pest_agent.py 的 KB
            self._send_json(_pests_browse())
        elif path == "/api/recipe_detail":
            # 知识底座·配方库：按 recipe_id（zone__crop）读取一份完整 Env Recipe
            qs = parse_qs(urlparse(self.path).query)
            self._send_json(_recipe_detail((qs.get("recipe_id") or [""])[0]))
        elif path == "/api/stats":
            self._send_json(_platform_stats())
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            payload = {}

        if path == "/api/recommend":
            try:
                orch = AgriOrchestrator()
                result = orch.run_pipeline(payload)
                result["_meta"] = {
                    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "preset_zone_hint": _zone_hint(payload),
                }
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": f"pipeline 失败: {e}"}, status=500)
        elif path == "/api/certificate":
            try:
                cert = issue_certificate(
                    run_id="demo",
                    inputs={"scene": payload.get("scene", "balcony"),
                            "crop": payload.get("crop", "")},
                )
                self._send_json(cert)
            except Exception as e:
                self._send_json({"error": f"certificate 失败: {e}"}, status=500)
        elif path == "/api/feedback":
            try:
                from engine.flywheel import record_feedback
                res = record_feedback(
                    zone_id=payload.get("zone_id", ""),
                    crop=payload.get("crop", ""),
                    survival_rate=float(payload.get("survival_rate", 1.0)),
                    yield_rating=float(payload.get("yield_rating", 5.0)),
                    user_rating=float(payload.get("user_rating", 5.0)),
                    issues=payload.get("issues") or [],
                    note=payload.get("note", ""),
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"feedback 失败: {e}"}, status=500)
        elif path == "/api/pest_diagnose":
            try:
                agent = PestAgent()
                res = agent.run({
                    "crop": payload.get("crop", ""),
                    "symptom_description": payload.get("symptom_description", ""),
                    "image_reference": payload.get("image_reference", ""),
                    "growth_stage": payload.get("growth_stage", ""),
                    "environment": payload.get("environment"),
                })
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"pest_diagnose 失败: {e}"}, status=500)
        elif path == "/api/nutrition_plan":
            try:
                agent = NutritionAgent()
                res = agent.run({
                    "crop": payload.get("crop", ""),
                    "scene": payload.get("scene", ""),
                    "growth_stage": payload.get("growth_stage", ""),
                    "growth_days": payload.get("growth_days"),
                    "container_volume_l": payload.get("container_volume_l"),
                    "start_date": payload.get("start_date", ""),
                })
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"nutrition_plan 失败: {e}"}, status=500)
        elif path == "/api/agent":
            try:
                orch = AgriOrchestrator()
                skill = payload.get("skill", "")
                res = orch.call_skill(skill, payload.get("payload", payload))
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"agent[{payload.get('skill','')}] 失败: {e}"}, status=500)
        elif path == "/api/season_advisory":
            # 物候推演 + 霜冻锚定播期窗口（call_skill 统一路由）
            try:
                orch = AgriOrchestrator()
                self._send_json(orch.call_skill("season_advisory", payload))
            except Exception as e:
                self._send_json({"error": f"season_advisory 失败: {e}"}, status=500)
        elif path == "/api/climate_fetch":
            # P0：按经纬度实时拉取真实月度气候（NASA POWER 主用 / Open-Meteo 兜底）+ provenance
            try:
                from agent.climate_data import fetch_monthly_climate
                cl = fetch_monthly_climate(
                    float(payload.get("lat", 0)), float(payload.get("lon", 0)),
                    years=int(payload.get("years", 5)),
                    force_refresh=bool(payload.get("force_refresh", False)),
                )
                self._send_json(cl)
            except Exception as e:
                self._send_json({"error": f"climate_fetch 失败: {e}"}, status=500)
        elif path == "/api/soil_profile":
            # 土壤画像：在线 SoilGrids 优先 → 离线分区均值降级
            try:
                from agent.soil_profile import get_soil_profile
                res = get_soil_profile(
                    lat=payload.get("lat"), lon=payload.get("lon"),
                    zone_id=payload.get("zone_id"), crop=payload.get("crop"),
                    online=bool(payload.get("online", True)),
                    timeout=float(payload.get("timeout", 6)),
                )
                self._send_json(res)
            except Exception as e:
                self._send_json({"error": f"soil_profile 失败: {e}"}, status=500)
        elif path == "/api/search":
            # 本地三层检索：FTS5 + 中文 bigram + 向量
            try:
                from engine import local_search as ls
                stats = ls.stats()
                # 索引不存在（首次运行 / 路径被重定向）时自动构建，避免静默返回 0 命中
                rebuilt = False
                if not stats.get("built"):
                    ls.rebuild()
                    rebuilt = True
                    stats = ls.stats()
                hits = ls.search(
                    query=payload.get("query", ""),
                    corpus=payload.get("corpus", "all"),
                    k=int(payload.get("k", 10)),
                    mode=payload.get("mode", "hybrid"),
                    min_score=float(payload.get("min_score", 0.02)),
                )
                self._send_json({"query": payload.get("query", ""), "hits": hits,
                                 "stats": stats, "rebuilt": rebuilt})
            except Exception as e:
                self._send_json({"error": f"search 失败: {e}"}, status=500)
        elif path == "/api/memory_recall":
            # 跨会话长期记忆召回（6 层加权 + 超边二阶扩展）
            try:
                from engine import long_term_memory as ltm
                hits = ltm.recall(
                    query=payload.get("query", ""),
                    skill=payload.get("skill", ""), crop=payload.get("crop", ""),
                    zone=payload.get("zone", ""), k=int(payload.get("k", 6)),
                    expand=bool(payload.get("expand", True)),
                    min_score=float(payload.get("min_score", 0.0)),
                )
                self._send_json({"query": payload.get("query", ""), "hits": hits, "stats": ltm.stats()})
            except Exception as e:
                self._send_json({"error": f"memory_recall 失败: {e}"}, status=500)
        elif path == "/api/work_item":
            # 工作项状态机：建单 → 执行 → 复核 → 集成 → 完成（追加式审计）
            try:
                from engine import work_item as wim
                title = payload.get("title") or "前端 Demo 方案生成"
                wi = wim.new_work_item(title=title, actor=payload.get("actor", "demo_web"))
                trace = []
                for mode, note in (("execute", "四 Agent 管线执行"),
                                   ("review", "复核建议与可信证书"),
                                   ("integrate", "集成种植计划与设备清单"),
                                   ("integrate", "写入交付结果")):
                    r = wi.transition(mode, actor=payload.get("actor", "demo_web"),
                                      payload={"note": note, "step": len(trace) + 1})
                    trace.append({"mode": mode, "ok": bool(r.get("ok")), "note": note})
                out = {
                    "item_id": wi.item_id, "state": wi.state, "history": trace,
                    "audit": wi.audit, "allowed_modes": wim.allowed_modes(wi.state),
                    "transition_table": wim.transition_table(), "registry": wim.registry_stats(),
                    "final_state": wi.state,
                }
                if wi.state != "done":
                    r = wi.transition("integrate", actor="demo_web", payload={"note": "补齐集成步"})
                    out["state"] = wi.state
                    out["audit"] = wi.audit
                self._send_json(out)
            except Exception as e:
                self._send_json({"error": f"work_item 失败: {e}"}, status=500)
        elif path == "/api/schedule":
            # 条件锚定调度：Env Recipe → 阈值/关键词锚点 → ready / waiting
            try:
                from engine import recipe_scheduler as rs
                recipe = rs.load_recipe(
                    path=payload.get("path", ""),
                    crop=payload.get("crop", ""), zone=payload.get("zone", ""),
                )
                anchors = rs.anchors_from_recipe(recipe)
                actions = rs.next_actions(
                    recipe, observations=payload.get("observations"),
                    symptom_text=payload.get("symptom_text", ""),
                )
                keep = {k: recipe.get(k) for k in
                        ("protocol", "recipe_version", "stage", "crop", "zone",
                         "device_profile", "environment", "exception_handling", "sources", "license")}
                self._send_json({"recipe": keep, "anchors": anchors, "actions": actions})
            except Exception as e:
                self._send_json({"error": f"schedule 失败: {e}"}, status=500)
        elif path == "/api/bp_screen":
            # BP 投资初筛：文本 → 完备性 + 风险三档结论（不产出 ROI 数字）
            try:
                import bp_screen
                text = payload.get("text", "")
                if not text:
                    self._send_json({"error": "text 为空，请粘贴 BP 文本"}, status=400)
                    return
                r = bp_screen.screen_text(
                    text,
                    company=payload.get("company", ""),
                    category=payload.get("category"),
                )
                out = _bp_out(r)
                out["archived_id"] = _bp_archive(r, payload.get("company", ""), [])
                self._send_json(out)
            except Exception as e:
                self._send_json({"error": f"bp_screen 失败: {e}"}, status=500)
        elif path == "/api/bp_screen_file":
            # BP 投资初筛：上传文件（PDF/DOCX/XLSX/CSV/TXT/MD）→ 解析 → 初筛
            # 文件以 base64 经 JSON 传入（避免 stdlib http.server 手写 multipart 解析）。
            try:
                import bp_screen
                files = payload.get("files") or []
                company = payload.get("company", "")
                if not files:
                    self._send_json({"error": "未收到文件"}, status=400)
                    return
                up_dir = os.path.join(_RUNTIME_DIR, "bp_uploads")
                os.makedirs(up_dir, exist_ok=True)
                saved = []
                parse_notes = []
                for f in files:
                    fn = (f.get("filename") or "upload.bin").replace("/", "_").replace("\\", "_")
                    content = f.get("content_base64") or ""
                    try:
                        raw = base64.b64decode(content)
                    except Exception:
                        parse_notes.append(f"{fn}: base64 解码失败")
                        continue
                    if not raw:
                        parse_notes.append(f"{fn}: 内容为空")
                        continue
                    fp = os.path.join(up_dir, f"{uuid.uuid4().hex[:6]}_{fn}")
                    with open(fp, "wb") as wf:
                        wf.write(raw)
                    saved.append((fp, fn))
                if not saved:
                    self._send_json({"error": "没有可解析的文件", "notes": parse_notes}, status=400)
                    return
                r = bp_screen.run_pipeline(saved, company=company)
                out = _bp_out(r)
                out["archived_id"] = _bp_archive(r, company, [fn for _, fn in saved])
                out["parse_notes"] = parse_notes
                out["files"] = [fn for _, fn in saved]
                self._send_json(out)
            except Exception as e:
                self._send_json({"error": f"bp_screen_file 失败: {e}"}, status=500)
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def log_message(self, fmt, *args):
        sys.stderr.write("[demo] " + (fmt % args) + "\n")


def _zone_hint(payload: dict) -> str:
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None:
        return ""
    for c in PRESET_CITIES:
        if abs(c["lat"] - lat) < 0.5 and abs(c["lon"] - (lon or 0)) < 0.5:
            return c["zone"]
    return ""


# ---------------------------------------------------------------------------
# 投资初筛（bp_screen）公共 helper
# ---------------------------------------------------------------------------
def _bp_out(r: dict) -> dict:
    """把 bp_screen.screen_text / run_pipeline 的结果扁平化，供前端展示。

    screen_text 顶层 verdict 是中文结论，但 verdict_name / verdict_reason /
    gates_fired / vetoes_fired / decision_path / counterfactual 都在 evaluation 子块，
    需要展开到顶层方便前端读取。
    """
    ev = r.get("evaluation") or {}
    out = {
        "status": r.get("status"),
        "report_id": r.get("report_id") or r.get("aid"),
        "rules_version": r.get("rules_version"),
        "llm_mode": r.get("llm_mode"),
        "company": r.get("company"),
        "category": r.get("category"),
        "category_name": r.get("category_name"),
        "cls": r.get("cls"),
        "score": r.get("score"),
        "score_range": r.get("score_range"),
        "verdict": r.get("verdict"),
        "verdict_name": ev.get("verdict_name") or r.get("verdict_name"),
        "verdict_reason": ev.get("verdict_reason") or r.get("verdict_reason"),
        "gates_fired": ev.get("gates_fired"),
        "vetoes_fired": ev.get("vetoes_fired"),
        "decision_path": ev.get("decision_path"),
        "counterfactual": ev.get("counterfactual"),
        "gaps": r.get("gaps"),
        "verify_results": r.get("verify_results"),
        "sanity_summary": r.get("sanity_summary"),
        "sanity_observations": r.get("sanity_observations"),
        "benchmarks": r.get("benchmarks"),
        "boundary": r.get("boundary"),
        "note": r.get("note"),
    }
    if not out["boundary"]:
        out["boundary"] = [
            "本工具不构成投资决策建议，仅做字段完备度与红旗检测。",
            "本地核验库是演示数据，local_hit 不代表官方核验通过。",
            "分数带区间（score_range），区间宽度反映缺失维度的不确定性。",
            "未配置 LLM 时仅走正则通道，可能漏抽长文本或表格内的字段。",
        ]
    return out


def _bp_archive(r: dict, company: str, files):
    """把一次初筛结果归档进 cases.db（AGRI_BP_DB 指向的库，demo 已隔离）。

    归档失败不影响初筛返回——只记 stderr。返回归档用的 aid。
    """
    try:
        from bp_screen import db as bpdb
        bpdb.ensure_ready()
        aid = r.get("report_id") or r.get("aid")
        if not aid:
            return None
        existing = bpdb.get_assessment(aid)
        if existing is None:
            bpdb.create_assessment(aid, company or r.get("company", ""), files or [])
        bpdb.set_report(
            aid,
            json.dumps(r.get("report"), ensure_ascii=False) if r.get("report") is not None else None,
            status=("done" if r.get("status") == "done" else r.get("status")),
            score=r.get("score"),
            grade=(r.get("evaluation") or {}).get("grade") if r.get("evaluation") else None,
            category=r.get("category"),
            confidence=(r.get("cls") or {}).get("confidence") if r.get("cls") else None,
        )
        return aid
    except Exception as e:  # noqa: BLE001  归档是增强，绝不断主流水线
        sys.stderr.write("[demo][bp_archive] 归档失败（不影响初筛）: %s\n" % e)
        return None


def _bp_list():
    """「我的评估」历史列表：读 cases.db 的 assessments 表，补充分类名。"""
    from bp_screen import db as bpdb
    import bp_screen
    bpdb.ensure_ready()
    rows = bpdb.list_assessments(limit=50)
    cat_names = {k: v["name"] for k, v in bp_screen.rules.CATEGORIES.items()}
    items = [{
        "id": r["id"],
        "company": r["company_name"],
        "category": r["category"],
        "category_name": cat_names.get(r["category"], r["category"]),
        "score": r["score"],
        "grade": r["grade"],
        "status": r["status"],
        "created": r["created"],
    } for r in rows]
    return {"total": len(items), "items": items}


def _platform_stats() -> dict:
    """平台能力盘点：数据规模 / Skill / MCP 工具 / 引擎 / 质量基线。"""
    import glob as _glob
    import re as _re

    def _count(pattern: str) -> int:
        return len(_glob.glob(pattern))

    def _safe(fn, default):
        try:
            return fn()
        except Exception as e:  # 单个统计项失败不阻断整体，但必须暴露错误
            out = dict(default) if isinstance(default, dict) else {}
            out["error"] = str(e)[:160]
            return out

    try:
        zone_path = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
        zones = json.load(open(zone_path, encoding="utf-8"))
        zone_count = len(zones) if isinstance(zones, list) else len(zones.get("zones", zones))
    except Exception:
        zone_count = _safe(lambda: 0, 0)

    # 去重作物数（配方文件名为 zone__crop，作物可跨分区出现）
    crop_set = set()
    for fp in _glob.glob(os.path.join(ROOT, "data", "env_recipes", "*.json")):
        rid = _re.sub(r"\.json$", "", os.path.basename(fp))
        if "__" in rid:
            crop_set.add(rid.partition("__")[2])

    orch = AgriOrchestrator()
    skills = orch.list_skills()
    mcp_tools = _re.findall(
        r'"name":\s*"(agri_[a-z_]+)"',
        open(os.path.join(ROOT, "mcp", "server.py"), encoding="utf-8").read(),
    )
    try:
        from agent.phenology import covered_crops as _pcrops
        phenology_crops = _pcrops()
    except Exception:
        phenology_crops = []
    try:
        from agent.soil_profile import probe_soilgrids
        soil_probe = probe_soilgrids(4.9, 52.4, timeout=3)
    except Exception as e:
        soil_probe = {"error": str(e)[:120]}

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "cities": len(PRESET_CITIES),
        "zones": zone_count,
        "crops": len(crop_set),
        "env_recipes": _count(os.path.join(ROOT, "data", "env_recipes", "*.json")),
        "skills": len(skills),
        "mcp_tools": len(mcp_tools),
        "mcp_tool_names": mcp_tools,
        "phenology_crops": phenology_crops,
        "soil_probe_europe": soil_probe,
        "search_index": _safe(lambda: __import__(
            "engine.local_search", fromlist=["x"]).stats(), {}),
        "memory_store": _safe(lambda: __import__(
            "engine.long_term_memory", fromlist=["x"]).stats(), {}),
        "trust": {
            "rsi": "B0", "hci": 0.0, "gates_closed": "0/6",
            "note": "指标未随前端改造变化，诚实基线保持",
        },
    }


def _read_json_safe(rel: str):
    """读 ROOT 下的 JSON，失败返回 None（不抛异常，避免单文件缺失拖垮整页）。"""
    p = os.path.join(ROOT, rel)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _crops_browse(zone_filter: str = "", q: str = "") -> dict:
    """知识底座·作物库：列出真实作物条目，支持按分区 / 关键词过滤。

    这是此前「数据底座只是空架子」的根因修复——底座内容现在可被浏览器真正
    调阅与检索，而不只是被规则引擎在后台计算。
    """
    cdb = _read_json_safe("data/crop_adapt_db.json") or {}
    zones = cdb.get("zones", {}) or {}
    items = []
    ql = (q or "").lower()
    for zid, zmeta in zones.items():
        if zone_filter and zid != zone_filter:
            continue
        for c in (zmeta.get("crops") or []):
            if ql:
                hay = " ".join(str(x) for x in [
                    c.get("crop"), c.get("latin"), c.get("family"),
                    "、".join(c.get("key_risks") or []),
                    "、".join(c.get("suitable_scenes") or []),
                ]).lower()
                if ql not in hay:
                    continue
            items.append({
                "crop": c.get("crop"), "latin": c.get("latin"),
                "family": c.get("family"), "zone_id": zid,
                "zone_name": zmeta.get("zone_name"),
                "adapt_score": c.get("adapt_score"),
                "growth_days": c.get("growth_days"),
                "temp_range_c": c.get("temp_range_c"),
                "ph_range": c.get("ph_range"),
                "water_ml_day": c.get("water_ml_day"),
                "suitable_scenes": c.get("suitable_scenes"),
                "key_risks": c.get("key_risks"),
                "fallback_variety": c.get("fallback_variety"),
                # 校准证据（P3 生态位包络反推；test_agents 契约：calibrated 必须有 measured_calibration）
                "calibrated": c.get("calibrated"),
                "calibration_method": c.get("calibration_method"),
                "calibration_note": c.get("calibration_note"),
                "measured_calibration": c.get("measured_calibration"),
                "latin_verified": c.get("latin_verified"),
                "gbif_accepted_name": c.get("gbif_accepted_name"),
            })
    return {"total": len(items), "crops": items}


def _zones_browse() -> dict:
    """知识底座·分区库：6 个全球气候分区的完整画像。"""
    gz = _read_json_safe("data/zone_meta/global_zones.json") or {}
    zones = gz.get("zones", []) if isinstance(gz, dict) else []
    return {"total": len(zones), "zones": zones}


def _pests_browse() -> dict:
    """知识底座·病虫害库：来自 agent/pest_agent.py 的 KB。"""
    try:
        import sys as _sys
        if ROOT not in _sys.path:
            _sys.path.insert(0, ROOT)
        from agent import pest_agent as _pa
        kb = getattr(_pa, "KB", {}) or {}
        cat = getattr(_pa, "_category_of", None)
        items = [{
            "name": n,
            "category": cat(n) if callable(cat) else "",
            "symptoms": v.get("symptoms"),
            "actions": v.get("actions"),
            "prevention": v.get("prevention"),
            "sev": v.get("sev"),
        } for n, v in kb.items()]
        return {"total": len(items), "pests": items}
    except Exception as e:  # 单个库读取失败不影响整体
        return {"total": 0, "pests": [], "error": str(e)[:160]}


def _recipe_detail(rid: str) -> dict:
    """知识底座·配方库：按 recipe_id（zone__crop）读取一份完整 Env Recipe。"""
    if not rid:
        return {"error": "recipe_id 为空"}
    fp = os.path.join(ROOT, "data", "env_recipes", rid + ".json")
    if not os.path.exists(fp):
        return {"error": "未找到配方: " + rid}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return {"recipe_id": rid, "data": json.load(f)}
    except Exception as e:
        return {"error": str(e)[:160]}


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 56)
    print("🌱 智慧农业生态 · 交互式 Demo")
    print(f"   访问: http://{HOST}:{PORT}")
    print("   零依赖：仅 Python 标准库（http.server）")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
