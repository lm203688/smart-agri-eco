# -*- coding: utf-8 -*-
"""
bp_screen Web 层（**可选**，依赖 FastAPI / uvicorn）

    pip install fastapi uvicorn
    python -m bp_screen.web          # 起在 8010
    或
    uvicorn bp_screen.web:app --host 0.0.0.0 --port 8010

端口 8010 的原因（重要）：
    8001 已被本项目的 ECS 公网服务占用（宿主 8001 → 容器 8000，8000 被陌生 FastAPI 占用
    故本项目主服务改到 8001）。本 Web 层另起 8010，避免同一台机器上端口撞车。
    原 AgriScreen V1 包的 README/deploy.sh 用 8001，移植时已改。

接口：
    GET  /api/meta                     规则版本 / 门禁 / 分类 / 案例数
    POST /api/screen_text              {text, company}                    → 九层管线
    POST /api/screen_fields            {fields, category, company}        → 跳过 L0-L3
    POST /api/assess                   multipart files + company          → 完整上传流程
    GET  /api/sample_bps               内置样例 BP 清单（含正/负对照）
    POST /api/assess/{aid}/confirm     {category}   人工确认分类后重跑
    POST /api/assess/{aid}/supplement  multipart files 补数后增量重算
    GET  /                             前端单页（若 bp_screen/_web/index.html 存在）

设计：本文件只做协议转换，不写业务逻辑。所有九层数据流都在 pipeline.py，
所以 Web 层与 MCP 层（mcp/server.py）共享同一套评分内核，不会出现两套口径。
"""
from __future__ import annotations

import json
import os
import shutil
import uuid

from . import db, parser, rules
from .pipeline import run_pipeline, screen_fields, screen_text

# FastAPI 是可选依赖：未安装时导入本模块会报清晰错误，但不影响 bp_screen 包其余部分。
try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.responses import JSONResponse
    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False
    FastAPI = None  # type: ignore

UPLOAD_ROOT = os.path.join(os.path.dirname(__file__), "_uploads")


def create_app() -> "FastAPI":
    if not _HAS_FASTAPI:
        raise ImportError(
            "Web 层需要 fastapi/uvicorn：pip install fastapi uvicorn\n"
            "评分内核无需它们 —— 直接 import bp_screen.screen_text 即可。")
    db.init_db()
    app = FastAPI(title="bp_screen · 农业项目投资初筛",
                  version=rules.RULES_VERSION,
                  description="九层管线：归档→解析→提取→归一化→合理性校验→分类→核验→缺口→评分→报告")

    @app.get("/api/meta")
    def api_meta():
        from .pipeline import meta
        return meta()

    @app.post("/api/screen_text")
    def api_screen_text(payload: dict):
        if not payload.get("text"):
            raise HTTPException(400, "缺少 text")
        return screen_text(payload["text"], company=payload.get("company", ""),
                           mode=payload.get("mode", "text"))

    @app.post("/api/screen_fields")
    def api_screen_fields(payload: dict):
        if not payload.get("fields"):
            raise HTTPException(400, "缺少 fields")
        return screen_fields(payload["fields"], category=payload.get("category"),
                             company=payload.get("company", ""),
                             all_text=payload.get("all_text", ""))

    @app.post("/api/assess")
    async def api_assess(files: list[UploadFile] = File(...), company: str = Form("")):
        aid = uuid.uuid4().hex[:8]
        dp = os.path.join(UPLOAD_ROOT, aid)
        os.makedirs(dp, exist_ok=True)
        saved = []
        for f in files:
            name = f.filename or f"upload_{len(saved)}"
            path = os.path.join(dp, name)
            with open(path, "wb") as out:
                shutil.copyfileobj(f.file, out)
            saved.append({"path": path, "filename": name})
        if not saved:
            raise HTTPException(400, "未收到文件")
        db.create_assessment(aid, company, [{"filename": s["filename"]} for s in saved])
        return run_pipeline([(s["path"], s["filename"]) for s in saved], company=company, aid=aid)

    @app.get("/api/sample_bps")
    def api_sample_bps():
        sp = os.path.join(os.path.dirname(__file__), "_sample")
        out = []
        if os.path.isdir(sp):
            for fn in sorted(os.listdir(sp)):
                if fn.endswith(".txt"):
                    out.append({"filename": fn,
                                "path": os.path.join(sp, fn),
                                "size": os.path.getsize(os.path.join(sp, fn))})
        return {"samples": out,
                "note": "样例为合成 BP，仅用于管线自测；指标与结局均为虚构，不可作真实案例引用"}

    @app.post("/api/assess/{aid}/confirm")
    def api_confirm(aid: str, payload: dict):
        a = db.get_assessment(aid)
        if not a:
            raise HTTPException(404, "评估不存在")
        cat = payload.get("category")
        if cat not in rules.CATEGORIES:
            raise HTTPException(400, f"非法分类，可选：{list(rules.CATEGORIES)}")
        rep = db.get_assessment(aid).get("report_json") or "{}"
        try:
            old = json.loads(rep) if rep else {}
        except Exception:
            old = {}
        n = old.get("normalized", {})
        r = screen_fields(n, category=cat, company=a.get("company_name", ""), aid=aid)
        db.set_report(aid, json.dumps(r["report"], ensure_ascii=False), status="done",
                      score=r.get("score"), grade=r.get("verdict"),
                      category=cat, confidence=100.0)
        return r

    @app.post("/api/assess/{aid}/supplement")
    async def api_supplement(aid: str, files: list[UploadFile] = File(...)):
        a = db.get_assessment(aid)
        if not a:
            raise HTTPException(404, "评估不存在")
        dp = os.path.join(UPLOAD_ROOT, aid)
        os.makedirs(dp, exist_ok=True)
        parsed = []
        for f in files:
            name = f.filename or f"supp_{len(parsed)}"
            path = os.path.join(dp, "supp_" + name)
            with open(path, "wb") as out:
                shutil.copyfileobj(f.file, out)
            pf = parser.parse_file(path, name)
            db.add_supplement(aid, name, {"pages": len(pf.pages)})
            parsed.append({"filename": name, "parsed": pf})
        r = run_pipeline([(os.path.join(dp, p["filename"].rsplit("/", 1)[-1]), p["filename"])
                          for p in parsed], company=a.get("company_name", ""), aid=aid)
        db.set_report(aid, json.dumps(r.get("report", {}), ensure_ascii=False),
                      score=r.get("score"), grade=r.get("verdict"),
                      category=r.get("category"))
        return r

    index_html = os.path.join(os.path.dirname(__file__), "_web", "index.html")

    @app.get("/")
    def index():
        if os.path.exists(index_html):
            from fastapi.responses import HTMLResponse
            with open(index_html, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return {"note": "未提供前端页面；直接调 /api/screen_text 或 /api/assess"}

    return app


# 惰性建 app：只有显式 import web 或 `uvicorn bp_screen.web:app` 时才触发 FastAPI 导入。
app = None
if _HAS_FASTAPI:
    try:
        app = create_app()
    except Exception:
        app = None


def main():
    """python -m bp_screen.web 时调用；端口 8010（避开本项目主服务 8001）。"""
    if not _HAS_FASTAPI:
        raise SystemExit("需要 fastapi/uvicorn：pip install fastapi uvicorn")
    import uvicorn
    port = int(os.environ.get("AGRI_BP_WEB_PORT", "8010"))
    uvicorn.run(create_app(), host=os.environ.get("AGRI_BP_WEB_HOST", "0.0.0.0"), port=port)


if __name__ == "__main__":
    main()
