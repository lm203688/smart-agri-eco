# -*- coding: utf-8 -*-
"""
bp_screen —— 农业项目投资初筛引擎（AgriScreen，零第三方依赖）

从用户自研的「农眼 AgriScreen」V1 包移植而来（作者自有，无版权问题）。
保留九层数据流（归档→解析→提取→归一化→分类→核验→缺口→评分→报告），
去掉 FastAPI 耦合，使评分内核可在无 Web 层的环境下运行。

公共 API（推荐只从本包导入这三个入口，不要直接摸子模块）：
    screen_text(text, company, mode, aid, filename)  直接给文本，不落盘 —— MCP / 单测用
    screen_fields(fields, category, company, ...)    直接给已抽取字段，跳过 L0-L3
    run_pipeline(files, company, aid)                给文件路径列表 —— Web 层用
    meta()                                           规则版本 / 门禁 / 分类清单

依赖分层（判断第三方能否并入的关键）：
    - 本包除 web.py 外全部零第三方依赖，只用标准库（re/json/sqlite3/urllib/zipfile/...）
    - parser.py 里 pdfplumber / pandas / openpyxl 是 **函数内 lazy import**（indent≥4），
      导入本包不会触发；只有解析 PDF/CSV/Excel 文件时才会尝试 import，
      缺依赖时该文件降级为 error 状态、其余格式照常处理。
    - web.py 依赖 FastAPI/uvicorn，是**可选的**入口；不装也能用 MCP 或直接调函数。

与本项目「投资评估板块」判定的关系（重要）：
    本项目此前判定 `agri_project_roi`（用种植数据算 ROI）不做，理由是 110 份配方的
    outcome / yield / 经济字段全为 0，输入不存在。
    本包是**另一回事**：输入是 BP / 审计 / 流水 / 证书文本，输出是完备性 + 风险初筛
    三档，不依赖本项目的种植数据，也不生成 ROI 数字。两者不冲突。
    详见 docs/agriscreen_integration_assessment.md。
"""
from . import (archiver, classifier, db, extractor, gap, llm, parser, report, rules,
               sanity, scorer, seed_cases, verifier)
from .pipeline import CONFIDENCE_THRESHOLD, meta, run_pipeline, screen_fields, screen_text

__version__ = "2.0.0"

__all__ = [
    "screen_text", "screen_fields", "run_pipeline", "meta",
    "CONFIDENCE_THRESHOLD",
    "archiver", "classifier", "db", "extractor", "gap", "llm", "parser",
    "report", "rules", "sanity", "scorer", "seed_cases", "verifier",
    "__version__",
]
