#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp/server.py —— 智慧农业生态 · 零依赖 MCP Server（Agent-native 分发层）

实现方式：标准库 JSON-RPC 2.0 over stdio（不依赖 mcp SDK / 任何第三方包），
与本项目「零依赖」理念一致，也契合评审「MCP 成本极低、是最强差异化赌注」的判断。

协议版本：2026-07-28（无状态规格）为主，向后兼容 2024-11-05 / 2025-06-18。

2026-07-28 无状态规格适配（SEP-2575 / SEP-2567 / SEP-2243 / SEP-2549 / SEP-414）：
  - SEP-2575 移除 initialize 握手：`initialize` 仍响应（兼容旧客户端），但**不是必需**；
    未握手直接 `tools/list` / `tools/call` 也完整可用。
  - SEP-2567 移除 `Mcp-Session-Id`：本 server 从设计上即无会话状态，不强校验该头。
  - SEP-2243 强制请求头 `Mcp-Method` / `Mcp-Name`：stdio 传输无 header 概念，
    等价信息从 JSON-RPC 的 `method` / `params.name` 取；HTTP 传输（若部署）由
    ``_http_headers_ok()`` 校验。
  - SEP-2549 缓存提示：`tools/list` 返回 `ttlMs` + `cacheScope`（配方为季度级数据，
    故 TTL 取 30 天；scope=public，无用户态差异）。
  - SEP-414 W3C Trace Context：接受 `_meta.traceparent`，透传进审计日志，
    并在响应 `_meta` 回写 `traceparent` 以便调用方串链。

暴露工具（对接现有 agent 包，不重复造轮子）：
    agri_list_cities       列出预设城市（经纬度 + 气候带），供 Agent 选点
    agri_match_zone        经纬度 → 气候分区匹配
    agri_recommend_crops   分区 + 偏好 → 作物推荐
    agri_growth_plan       作物 + 场景 + 分区 → 种植计划（含微气候修正）
    agri_diagnose_pest     症状/图像 → 病虫害与营养缺乏诊断
    agri_nutrition_plan    作物 + 阶段 → 养分管理方案
    agri_env_recipe        作物 + 阶段 + 设备类 → 一份 Env Recipe v1 合规配方（P0-G 落地）
    agri_season_advisory   逐月均温 → 无霜期 + 霜冻锚定播期窗口；或作物+日均温 → 物候期天数
    agri_soil_profile      经纬度/分区 → 土壤剖面（SoilGrids 在线优先，失败降级为离线分区均值）

启动（stdio，供 MCP 客户端拉起）：
    python mcp/server.py

也可用本项目脚本自测：
    python scripts/test_mcp_server.py

详细工具契约（何时用 / 输入 / 返回示例）见：
    docs/TOOLS_REFERENCE.md         # 23 工具三段式手册
    docs/QUICKSTART.md              # 15 分钟上手指南
    examples/                       # 5 个可运行示例脚本
"""
from __future__ import annotations

import json
import os
import sys
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.clock import CLOCK  # noqa: E402

# H1: 原子写入底座（MCP 对外服务层崩溃不损坏审计日志）
from core.atomic_io import atomic_append_jsonl, atomic_write_json

from agent import AgriOrchestrator  # noqa: E402
from agent.preset_cities import load_preset_cities  # noqa: E402
from agent.grow_batch_store import GrowBatchStore, get_store as get_grow_batch_store, GrowBatchError  # noqa: E402
from core.trust_layer import get_trust_mark  # noqa: E402
from core.tool_schema import validate_tool_args  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
# 兼容声明的历史版本：新客户端取 PROTOCOL_VERSION，旧客户端接受以下任一。
SUPPORTED_PROTOCOL_VERSIONS = ("2026-07-28", "2025-06-18", "2024-11-05")
SERVER_NAME = "agri-eco"
SERVER_VERSION = "1.1.0"


# ===========================================================================
# H5: MCP 工具参数 JSON Schema（FOUNDATION_AUDIT 2026-10-16）
# 每个 _tool_* handler 前必须有同名 TOOL_SCHEMA_xxx = {...} 定义。
# 缺失 → CI 门禁 gate_tool_schema.py 失败。
# ===========================================================================

TOOL_SCHEMA_list_cities = {
    "type": "object",
    "properties": {},
}

TOOL_SCHEMA_match_zone = {
    "type": "object",
    "required": ["lat", "lon"],
    "properties": {
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0},
    },
}

TOOL_SCHEMA_recommend_crops = {
    "type": "object",
    "properties": {
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0, "nullable": True},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0, "nullable": True},
        "purpose": {"type": "string"},
        "space_sqm": {"type": "number", "minimum": 0.0},
        "difficulty": {"type": "string", "enum": ["beginner", "intermediate", "expert"]},
        "scene": {"type": "string", "enum": ["balcony", "office", "windowsill", "indoor", "outdoor"]},
    },
}

TOOL_SCHEMA_diagnose_pest = {
    "type": "object",
    "required": ["crop"],
    "properties": {
        "crop": {"type": "string", "nullable": False},
        "symptom_description": {"type": "string"},
        "image_reference": {"type": "string"},
        "growth_stage": {"type": "string"},
        "environment": {"type": "object", "nullable": True},
    },
}

TOOL_SCHEMA_nutrition_plan = {
    "type": "object",
    "required": ["crop"],
    "properties": {
        "crop": {"type": "string", "nullable": False},
        "scene": {"type": "string"},
        "growth_stage": {"type": "string"},
        "growth_days": {"type": "integer", "minimum": 1, "maximum": 365, "nullable": True},
        "container_volume_l": {"type": "number", "minimum": 0.0, "nullable": True},
        "start_date": {"type": "string"},
    },
}

TOOL_SCHEMA_season_advisory = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["planting_window", "stage_days", "calendar", "phenology"]},
        "monthly_mean_c": {"type": "array", "items": {"type": "number"}, "nullable": True},
        "crops": {"type": "array", "items": {"type": "string"}, "nullable": True},
        "frost_threshold_c": {"type": "number", "nullable": True},
        "safety_margin_days": {"type": "integer", "minimum": 0, "nullable": True},
        "crop": {"type": "string"},
        "mean_temp_c": {"type": "number", "nullable": True},
        "zone": {"type": "string"},
        "date": {"type": "string"},
        "category": {"type": "string"},
    },
}

TOOL_SCHEMA_soil_profile = {
    "type": "object",
    "properties": {
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0, "nullable": True},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0, "nullable": True},
        "zone_id": {"type": "string", "nullable": True},
        "crop": {"type": "string", "nullable": True},
        "online": {"type": "boolean"},
        "timeout_s": {"type": "number", "minimum": 0.5, "maximum": 60.0},
    },
}

TOOL_SCHEMA_bp_screen = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "nullable": True},
        "fields": {"type": "object", "nullable": True},
        "category": {"type": "string", "nullable": True},
        "company": {"type": "string"},
        "mode": {"type": "string", "enum": ["text", "fields", "audit"]},
        "filename": {"type": "string", "nullable": True},
    },
}

TOOL_SCHEMA_resolve_recipe = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "nullable": True},
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0, "nullable": True},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0, "nullable": True},
    },
}

TOOL_SCHEMA_query_lineage = {
    "type": "object",
    "properties": {
        "crop": {"type": "string", "nullable": True},
        "zone_id": {"type": "string", "nullable": True},
    },
}

TOOL_SCHEMA_counterfactual_trajectory = {
    "type": "object",
    "properties": {
        "crop": {"type": "string"},
        "days": {"type": "integer", "minimum": 1, "maximum": 365},
        "baseline_dli_mj": {"type": "number", "minimum": 0.0},
        "baseline_temp_c": {"type": "number", "minimum": -50.0, "maximum": 80.0},
        "quick_scenario": {"type": "string", "enum": [
            "baseline", "light_12_to_16h", "cool_down_5c",
            "stop_fertilizer", "high_humidity", "double_water"
        ]},
        "heuristic_engine_est": {"type": "number", "nullable": True},
    },
}

TOOL_SCHEMA_verify_recommendation = {
    "type": "object",
    "properties": {
        "claim": {"type": "object", "nullable": True},
        "context": {"type": "object", "nullable": True},
        "heuristic_engine_est": {"type": "number", "nullable": True},
    },
}

# --- 新增 10 个 handler schema（H5 补漏） ---

TOOL_SCHEMA_growth_plan = {
    "type": "object",
    "required": ["crop"],
    "properties": {
        "crop": {"type": "string", "nullable": False},
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0, "nullable": True},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0, "nullable": True},
        "scene": {"type": "string"},
        "floor": {"type": "integer", "minimum": 0},
        "orientation": {"type": "string"},
        "city": {"type": "string"},
        "start_date": {"type": "string"},
    },
}

TOOL_SCHEMA_env_recipe = {
    "type": "object",
    "required": ["crop"],
    "properties": {
        "crop": {"type": "string", "nullable": False},
        "stage": {"type": "string", "enum": [
            "seed", "seedling", "vegetative", "flowering",
            "fruiting", "harvest", "full_cycle",
        ]},
        "device_class": {"type": "string", "enum": [
            "balcony", "windowsill", "indoor_cabinet", "aerogarden_orphan",
            "greenhouse", "open_field", "other",
        ]},
    },
}

TOOL_SCHEMA_reconcile_climate = {
    "type": "object",
    "required": ["lat", "lon"],
    "properties": {
        "lat": {"type": "number", "minimum": -90.0, "maximum": 90.0},
        "lon": {"type": "number", "minimum": -180.0, "maximum": 180.0},
        "years": {"type": "integer", "minimum": 1, "maximum": 30},
        "sources": {"type": "array", "items": {"type": "string"}, "nullable": True},
    },
}

TOOL_SCHEMA_search = {
    "type": "object",
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "nullable": False},
        "corpus": {"type": "string", "enum": ["all", "crops", "zones", "pests", "recipes"]},
        "k": {"type": "integer", "minimum": 1, "maximum": 50},
        "mode": {"type": "string", "enum": ["exact", "keyword", "vector", "hybrid"]},
    },
}

TOOL_SCHEMA_knowledge_query = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [
            "summary", "crops_by_zone", "crops_by_risk", "neighbors", "traverse",
        ]},
        "zone_id": {"type": "string", "nullable": True},
        "risk": {"type": "string", "nullable": True},
        "node": {"type": "string", "nullable": True},
        "relation": {"type": "string", "nullable": True},
        "reverse": {"type": "boolean"},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 100},
        "depth": {"type": "integer", "minimum": 1, "maximum": 5},
    },
}

TOOL_SCHEMA_forecast = {
    "type": "object",
    "required": ["crop"],
    "properties": {
        "crop": {"type": "string", "nullable": False},
        "zone_id": {"type": "string", "nullable": True},
        "start_date": {"type": "string", "nullable": True},
        "adapt_score": {"type": "number", "minimum": 0.0, "maximum": 1.0, "nullable": True},
        "env_recipe": {"type": "object", "nullable": True},
        "growth_plan": {"type": "object", "nullable": True},
        "zone_climate": {"type": "array", "nullable": True},
    },
}

TOOL_SCHEMA_recipe_profile = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [
            "list", "search", "stats", "lookup", "diff", "export",
        ]},
        "mode": {"type": "string", "enum": ["brief", "full"]},
        "keyword": {"type": "string"},
        "crop": {"type": "string"},
        "stage": {"type": "string"},
        "device_class": {"type": "string"},
        "filename": {"type": "string", "nullable": True},
        "a": {"type": "string", "nullable": True},
        "b": {"type": "string", "nullable": True},
        "no_sources": {"type": "boolean"},
        "include_execution_log": {"type": "boolean"},
        "include_outcome": {"type": "boolean"},
    },
}

TOOL_SCHEMA_verify_trust = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["current", "check_prefix", "end_to_end"]},
        "mark": {"type": "object", "nullable": True},
    },
}

TOOL_SCHEMA_list_ecosystem = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": [
            "integrated", "partial", "planned_mapping",
            "evaluating", "competitor_reference", "not_evaluated",
        ], "nullable": True},
    },
}

TOOL_SCHEMA_decision_path_report = {
    "type": "object",
    "properties": {
        "case_ids": {"type": "array", "items": {"type": "string"}, "nullable": True},
        "format": {"type": "string", "enum": ["json", "summary"]},
    },
}

TOOL_SCHEMA_economics = {
    "type": "object",
    "properties": {
        "crop": {"type": "string"},
        "zone": {"type": "string", "nullable": True},
        "area_sqm": {"type": "number", "nullable": True},
        "labor_cny_day": {"type": "number", "nullable": True},
    },
    "required": ["crop"],
}

TOOL_SCHEMA_postharvest = {
    "type": "object",
    "properties": {
        "crop": {"type": "string"},
        "stage": {"type": "string", "enum": ["fresh", "storage", "transport"], "nullable": True},
    },
    "required": ["crop"],
}

# ---------- Stage 批次对象 MVP（2026-10-27，报告 §9.1 P0 工作包） ----------
# 5 个工具：create/observe/action/status/replay，围绕 grow_batch.schema.json
# 五类对象协作。MVP 阶段动作默认 shadow/dry_run，不真实执行。

TOOL_SCHEMA_grow_batch_create = {
    "type": "object",
    "properties": {
        "plot": {
            "type": "object",
            "description": "Plot 对象（见 schemas/grow_batch.schema.json）。plot_id/location_type 必填。",
            "properties": {
                "plot_id": {"type": "string", "minLength": 1},
                "location_type": {"type": "string",
                                   "enum": ["balcony", "indoor", "greenhouse", "field", "teaching"]},
            },
            "required": ["plot_id", "location_type"],
        },
        "batch": {
            "type": "object",
            "description": "GrowBatch 对象（见 schemas/grow_batch.schema.json）。batch_id/crop/plot_id/recipe_version/started_at 必填。",
            "properties": {
                "batch_id": {"type": "string", "minLength": 1},
                "crop": {"type": "string", "minLength": 1},
                "plot_id": {"type": "string", "minLength": 1},
                "recipe_version": {"type": "string"},
                "recipe_id": {"type": "string"},
                "started_at": {"type": "string"},
            },
            "required": ["batch_id", "crop", "plot_id", "recipe_version", "started_at"],
        },
    },
    "required": ["plot", "batch"],
}

TOOL_SCHEMA_grow_batch_observe = {
    "type": "object",
    "properties": {
        "observation": {
            "type": "object",
            "description": "Observation 对象。observation_id/batch_id/ts/metric/source 必填。",
            "properties": {
                "observation_id": {"type": "string", "minLength": 1},
                "batch_id": {"type": "string", "minLength": 1},
                "ts": {"type": "string"},
                "metric": {"type": "string", "minLength": 1},
                "value": {"type": "object"},
                "text": {"type": "string"},
                "source": {"type": "object"},
                "quality": {"type": "string",
                            "enum": ["high", "medium", "low", "uncertain", "missing"]},
            },
            "required": ["observation_id", "batch_id", "ts", "metric", "source"],
        },
    },
    "required": ["observation"],
}

TOOL_SCHEMA_grow_batch_action = {
    "type": "object",
    "properties": {
        "action": {
            "type": "object",
            "description": "Action 对象。action_id/batch_id/ts/recommendation 必填。MVP 默认 shadow/dry_run。",
            "properties": {
                "action_id": {"type": "string", "minLength": 1},
                "batch_id": {"type": "string", "minLength": 1},
                "ts": {"type": "string"},
                "recommendation": {"type": "string", "minLength": 1},
                "parameters": {"type": "object"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["action_id", "batch_id", "ts", "recommendation"],
        },
    },
    "required": ["action"],
}

TOOL_SCHEMA_grow_batch_status = {
    "type": "object",
    "properties": {
        "batch_id": {"type": "string"},
        "include_events": {"type": "boolean", "nullable": True},
    },
    "required": ["batch_id"],
}

TOOL_SCHEMA_grow_batch_replay = {
    "type": "object",
    "properties": {
        "batch_id": {"type": "string"},
    },
    "required": ["batch_id"],
}

# M13-P3 Server Card + ETags：稳定 ETag 种子（内容变更才改变），
# 让客户端可缓存 tools/list 与 server card 而不必每次重拉。
_CARD_PATH = os.path.join(ROOT, ".well-known", "mcp-card.json")
_CARD_CACHE = {"body": None, "etag": None, "etag_tools_list": None}


def _card_body() -> dict | None:
    """懒加载 mcp-card.json，首次读取后缓存到进程内。"""
    if _CARD_CACHE["body"] is not None:
        return _CARD_CACHE["body"]
    try:
        with open(_CARD_PATH, "r", encoding="utf-8") as f:
            body = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    _CARD_CACHE["body"] = body
    _CARD_CACHE["etag"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return body


def _card_etag() -> str | None:
    """返回 mcp-card.json 的稳定 ETag（基于 sha256 前 16 hex）。"""
    if _CARD_CACHE["etag"] is None:
        _card_body()
    return _CARD_CACHE["etag"]


def _tools_list_etag() -> str:
    """tools/list 响应的稳定 ETag：基于全量 TOOLS 内容 hash（分类过滤后 hash 不同）。"""
    if _CARD_CACHE["etag_tools_list"] is None:
        _CARD_CACHE["etag_tools_list"] = hashlib.sha256(
            json.dumps(TOOLS, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
    return _CARD_CACHE["etag_tools_list"]

# SEP-2549 缓存提示：Env Recipe / 分区 / 作物库均为季度级低频变更数据，
# 30 天 TTL 足够且能显著减少客户端重复拉取。cacheScope=public 表示
# 响应与调用方身份无关（本 server 无用户态），可被共享缓存复用。
TOOLS_LIST_TTL_MS = 2592000000  # 30 天
TOOLS_LIST_CACHE_SCOPE = "public"

# 安全护栏：单次请求最大字节数，防止超长载荷导致内存耗尽（MCP 分发通道）
MAX_LINE_BYTES = 1 << 20  # 1 MiB

# 预设城市：唯一数据源 data/preset_cities.json（2026-09-23 收敛）。
# 此前本文件与 app/demo_server.py 各持一份完全相同的硬编码副本 → 必然漂移
# （改一处忘另一处，两侧给出不同城市集且不报错）。现两侧统一经
# agent/preset_cities.py 读取，测试锁定一致性。
_PRESET_CITIES = load_preset_cities()

_STAGES = ["seed", "seedling", "vegetative", "flowering", "fruiting", "harvest", "full_cycle"]
_DEVICE_CLASSES = ["balcony", "windowsill", "indoor_cabinet", "aerogarden_orphan",
                   "greenhouse", "open_field", "other"]

# 懒加载编排器（首次工具调用时实例化）
# 注意：单例变量不可与访问器同名——否则 def 会把 `_orch = None` 覆盖为函数对象，
# 使 `if _orch is None` 恒为 False，访问器返回自身而非编排器（曾致全部 Agent 工具静默失败）。
_ORCH_SINGLETON: AgriOrchestrator | None = None


def _orch() -> AgriOrchestrator:
    global _ORCH_SINGLETON
    if _ORCH_SINGLETON is None:
        _ORCH_SINGLETON = AgriOrchestrator()
    return _ORCH_SINGLETON


# ---------- 工具实现 ----------

def _tool_list_cities(args: dict) -> dict:
    errs = validate_tool_args("agri_list_cities", TOOL_SCHEMA_list_cities, args)
    if errs:
        return {"error": "; ".join(errs)}
    return {"cities": _PRESET_CITIES}


def _tool_match_zone(args: dict) -> dict:
    errs = validate_tool_args("agri_match_zone", TOOL_SCHEMA_match_zone, args)
    if errs:
        return {"error": "; ".join(errs)}
    lat = float(args["lat"])
    lon = float(args["lon"])
    return _orch().climate.match_zone(lat, lon)


def _tool_recommend_crops(args: dict) -> dict:
    errs = validate_tool_args("agri_recommend_crops", TOOL_SCHEMA_recommend_crops, args)
    if errs:
        return {"error": "; ".join(errs)}
    # 需要分区数据：优先用传入 lat/lon 匹配，否则尝试 city 名称匹配
    if args.get("lat") is not None and args.get("lon") is not None:
        zone = _orch().climate.match_zone(float(args["lat"]), float(args["lon"]))
    else:
        zone = {"evidence": {"zone_id": "unspecified"}}
    prefs = {
        "purpose": args.get("purpose", "食用"),
        "space_sqm": float(args.get("space_sqm", 1.0)),
        "difficulty": args.get("difficulty", "beginner"),
        "container": args.get("scene") in ["balcony", "office", "windowsill"],
    }
    return _orch().crop.recommend(zone_data=zone, preferences=prefs)


def _tool_growth_plan(args: dict) -> dict:
    errs = validate_tool_args("agri_growth_plan", TOOL_SCHEMA_growth_plan, args)
    if errs:
        return {"error": "; ".join(errs)}
    crop = args.get("crop", "")
    if not crop:
        return {"error": "缺少 crop（作物名）"}
    if args.get("lat") is not None and args.get("lon") is not None:
        zone = _orch().climate.match_zone(float(args["lat"]), float(args["lon"]))
    else:
        zone = {"evidence": {"zone_id": "unspecified"}}
    micro = _orch().climate.microclimate_adjustment({
        "scene": args.get("scene", "balcony"),
        "floor": args.get("floor", 1),
        "orientation": args.get("orientation", "south"),
        "city": args.get("city", ""),
    })
    return _orch().growth.generate_growth_plan(
        crop=crop,
        zone_data=zone,
        start_date=args.get("start_date", ""),
        scene=args.get("scene", "balcony"),
        microclimate=micro,
    )


def _tool_diagnose_pest(args: dict) -> dict:
    errs = validate_tool_args("agri_diagnose_pest", TOOL_SCHEMA_diagnose_pest, args)
    if errs:
        return {"error": "; ".join(errs)}
    return _orch().pest.run({
        "crop": args.get("crop", ""),
        "symptom_description": args.get("symptom_description", ""),
        "image_reference": args.get("image_reference", ""),
        "growth_stage": args.get("growth_stage", ""),
        "environment": args.get("environment"),
    })


def _tool_nutrition_plan(args: dict) -> dict:
    errs = validate_tool_args("agri_nutrition_plan", TOOL_SCHEMA_nutrition_plan, args)
    if errs:
        return {"error": "; ".join(errs)}
    return _orch().nutrition.run({
        "crop": args.get("crop", ""),
        "scene": args.get("scene", ""),
        "growth_stage": args.get("growth_stage", ""),
        "growth_days": args.get("growth_days"),
        "container_volume_l": args.get("container_volume_l"),
        "start_date": args.get("start_date", ""),
    })


def _lookup_stored_recipe(crop_name: str, stage: str, device_class: str) -> dict | None:
    """优先从 data/env_recipes/ 配方库查（generate_env_recipes.py 的产物）。"""
    rdir = os.path.join(ROOT, "data", "env_recipes")
    if not os.path.isdir(rdir):
        return None
    best = None  # (score, recipe)
    for name in sorted(os.listdir(rdir)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(rdir, name), "r", encoding="utf-8") as f:
                r = json.load(f)
        except Exception:
            continue
        sp = r.get("crop", {}).get("species", "")
        if crop_name and (crop_name == sp or crop_name in sp or sp in crop_name):
            score = 0
            if r.get("stage") == stage:
                score += 2
            if r.get("device_profile", {}).get("device_class") == device_class:
                score += 1
            if best is None or score > best[0]:
                best = (score, r)
    return best[1] if best else None


def _tool_env_recipe(args: dict) -> dict:
    """优先返回配方库中的 Env Recipe v1；未入库作物回退为 crop_adapt_db 现场派生。"""
    errs = validate_tool_args("agri_env_recipe", TOOL_SCHEMA_env_recipe, args)
    if errs:
        return {"error": "; ".join(errs)}
    crop_name = (args.get("crop") or "").strip()
    stage = args.get("stage", "full_cycle")
    device_class = args.get("device_class", "indoor_cabinet")
    if stage not in _STAGES:
        return {"error": f"stage 非法，允许：{_STAGES}"}
    if device_class not in _DEVICE_CLASSES:
        return {"error": f"device_class 非法，允许：{_DEVICE_CLASSES}"}
    if not crop_name:
        return {"error": "缺少 crop（作物名）"}

    stored = _lookup_stored_recipe(crop_name, stage, device_class)
    if stored:
        return stored

    db_path = os.path.join(ROOT, "data", "crop_adapt_db.json")
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception as e:
        return {"error": f"读取作物库失败: {e}"}

    found = None
    for _zname, zdata in db.get("zones", {}).items():
        for entry in zdata.get("crops", []):
            if (crop_name == entry.get("crop")
                    or crop_name in entry.get("crop", "")
                    or entry.get("crop", "") in crop_name):
                found = entry
                break
        if found:
            break

    if not found:
        return {
            "found": False,
            "hint": f"作物「{crop_name}」尚未入库；欢迎按 schemas/env_recipe.schema.json 贡献一份配方（见 docs/env_recipe_protocol_v1.md）。",
        }

    temp = found.get("temp_range_c", [20, 28])
    ph = found.get("ph_range", [6.0, 7.0])
    recipe = {
        "protocol": "env-recipe",
        "recipe_version": "1.0.0",
        "crop": {
            "species": found.get("crop", crop_name),
            "latin": found.get("latin", ""),
            "family": found.get("family", ""),
        },
        "stage": stage,
        "device_profile": {
            "device_class": device_class,
            "sensor_capability": ["temp", "humidity"],
        },
        "environment": {
            "temperature": {"day_c": temp[1] if len(temp) > 1 else temp[0],
                            "night_c": temp[0]},
            "humidity": {"min_pct": 50, "max_pct": 80},
            "water_nutrient": {
                "ph": round((ph[0] + ph[1]) / 2, 2) if len(ph) > 1 else ph[0],
                "water_ml_day": found.get("water_ml_day", 300),
            },
            "airflow": {"level": "medium"},
        },
        "exception_handling": [
            {"condition": "湿度持续 > 85%", "action": "加强通风，防真菌",
             "severity": "warn"},
        ],
        "execution_log": [],
        "outcome": {},
        "image_consent": {"captured": False, "license": "", "attribution": ""},
        "sources": (db.get("meta", {}).get("data_sources", [])
                    and [{"title": s, "url": "", "accessed_at": db.get("meta", {}).get("last_updated", "")}
                         for s in db["meta"]["data_sources"]]),
        "license": "CC-BY-4.0",
    }
    return recipe


def _tool_season_advisory(args: dict) -> dict:
    errs = validate_tool_args("agri_season_advisory", TOOL_SCHEMA_season_advisory, args)
    if errs:
        return {"error": "; ".join(errs)}
    return _orch().season.run({
        "mode": args.get("mode", "planting_window"),
        "monthly_mean_c": args.get("monthly_mean_c"),
        "crops": args.get("crops"),
        "frost_threshold_c": args.get("frost_threshold_c", 0.0),
        "safety_margin_days": args.get("safety_margin_days", 7),
        "crop": args.get("crop", ""),
        "mean_temp_c": args.get("mean_temp_c"),
        "zone": args.get("zone"),
        "date": args.get("date", ""),
        "category": args.get("category", ""),
    })


def _tool_soil_profile(args: dict) -> dict:
    """土壤剖面：在线 SoilGrids 优先；不可用则降级为离线分区均值（明确标注 resolution）。"""
    errs = validate_tool_args("agri_soil_profile", TOOL_SCHEMA_soil_profile, args)
    if errs:
        return {"error": "; ".join(errs)}
    from agent.soil_profile import get_soil_profile
    lat = args.get("lat")
    lon = args.get("lon")
    return get_soil_profile(
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        zone_id=args.get("zone_id"),
        crop=args.get("crop"),
        online=bool(args.get("online", True)),
        timeout=float(args.get("timeout_s", 10)),
    )


def _tool_bp_screen(args: dict) -> dict:
    """农业项目投资初筛（AgriScreen 移植版）：BP/审计/流水文本或已抽取字段 → 六分类 + 五闸 +
    六评分卡 + 一票否决 → 三档结论（≥75 通过 / 60-75 需深挖 / <60 淘汰）+ 归因 + 反事实边界。

    只输出初筛参考，不构成投资决策建议。输入是 BP 文本，不依赖本项目的种植数据，
    也不生成 ROI 数字（agri_project_roi 仍不做，理由见 docs/agriscreen_integration_assessment.md）。
    """
    errs = validate_tool_args("agri_bp_screen", TOOL_SCHEMA_bp_screen, args)
    if errs:
        return {"error": "; ".join(errs)}
    import bp_screen

    text = (args.get("text") or "").strip()
    fields = args.get("fields") or None
    category = args.get("category")

    if fields:
        r = bp_screen.screen_fields(dict(fields), category=category,
                                    company=args.get("company", ""),
                                    all_text=text)
    elif text:
        r = bp_screen.screen_text(text, company=args.get("company", ""),
                                  mode=args.get("mode", "text"),
                                  filename=args.get("filename"),
                                  category=category)
    else:
        return {"error": "需要 text（BP/审计文本）或 fields（已抽取字段 dict）之一"}

    ev = r.get("evaluation") or {}
    card = ev.get("card") or {}
    return {
        "verdict": r.get("verdict"),
        "verdict_name": ev.get("verdict_name"),
        "verdict_reason": ev.get("verdict_reason"),
        "score": r.get("score"),
        "score_range": r.get("score_range"),
        "missing_dimensions": card.get("missing_dimensions"),
        "category": r.get("category"),
        "category_name": r.get("category_name"),
        "classify": r.get("cls"),
        "status": r.get("status"),
        "gates_fired": ev.get("gates_fired"),
        "vetoes_fired": ev.get("vetoes_fired"),
        "decision_path": (ev.get("decision_path") or [])[:6],
        "counterfactual": ev.get("counterfactual"),
        "gaps": r.get("gaps"),
        "verify_results": r.get("verify_results"),
        "sanity_summary": (r.get("channel_flags") or {}).get("sanity_summary"),
        "sanity_observations": (r.get("channel_flags") or {}).get("sanity_observations"),
        "llm_mode": r.get("llm_mode"),
        "rules_version": r.get("rules_version"),
        "boundary": [
            "输出为初筛参考，不构成投资决策建议",
            "verify_results 中 local_hit 仅为本地示例库字符串匹配，不是官方核验；"
            "正式结论须按 official_source 指向的官方系统复核",
            "score_range 表达数据不完整带来的不确定性；禁止用估算值冒充实际值",
            "分类置信度低于 70 时 status=need_classify，不自动评分，请人工指定 category 后重跑",
        ],
    }


def _tool_reconcile_climate(args: dict) -> dict:
    """多源气候调和：给定 lat/lon，并行拉 NASA POWER + Open-Meteo，逐月平均得调和基线 +
    一致度 + 分歧告警（壁垒④ 真实结果回流校准）。WorldClim 列为扩展点。无网络时优雅降级。
    """
    errs = validate_tool_args("agri_reconcile_climate", TOOL_SCHEMA_reconcile_climate, args)
    if errs:
        return {"error": "; ".join(errs)}
    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except (KeyError, TypeError, ValueError):
        return {"error": "需要数值 lat/lon"}
    if not (-90.0 <= lat <= 90.0):
        return {"error": f"lat 超出合法范围 [-90, 90]，收到 {lat}"}
    if not (-180.0 <= lon <= 180.0):
        return {"error": f"lon 超出合法范围 [-180, 180]，收到 {lon}"}
    # years 校验：必须是正整数（bool 是 int 子类，需显式排除）
    years_raw = args.get("years", 5)
    if isinstance(years_raw, bool) or not isinstance(years_raw, int):
        return {"error": f"years 必须是整数（1-30），收到 {type(years_raw).__name__}={years_raw!r}"}
    if not (1 <= years_raw <= 30):
        return {"error": f"years 超出合法范围 [1, 30]，收到 {years_raw}"}
    years = years_raw
    sources = tuple(args["sources"]) if args.get("sources") else None
    from core.climate_reconcile import reconcile_climate
    return reconcile_climate(lat, lon, years=years, sources=sources)


def _tool_resolve_recipe(args: dict) -> dict:
    """地理编码 → 分区 → 配方：城市名（中文/英文）或经纬度 → 匹配气候分区 + 检索 Env Recipe。
    核心「城市种植生成箱」分发价值，完全离线。
    """
    errs = validate_tool_args("agri_resolve_recipe", TOOL_SCHEMA_resolve_recipe, args)
    if errs:
        return {"error": "; ".join(errs)}
    from core.geo_recipe import resolve
    query = args.get("query")
    lat = args.get("lat")
    lon = args.get("lon")
    return resolve(query=query, lat=lat, lon=lon)


def _tool_query_lineage(args: dict) -> dict:
    """数据血缘查询：按作物/分区查配方的数据溯源（外部 API 参与 + 本地文件指纹 + 校准实证）。
    对齐 GOAI DataFlow-Agent 提升点3 + 壁垒④。"""
    errs = validate_tool_args("agri_query_lineage", TOOL_SCHEMA_query_lineage, args)
    if errs:
        return {"error": "; ".join(errs)}
    from core.data_lineage import query_lineage
    crop = args.get("crop")
    zone = args.get("zone_id")
    return query_lineage(crop=crop or None, zone_id=zone or None)


def _tool_search(args: dict) -> dict:
    """知识检索：跨作物/分区/病虫害/配方 4 语料做词法+向量混合检索（M12-K1）。

    底层走 engine/local_search.py（char n-gram + cosine + SQLite FTS5），
    纯 stdlib 零依赖。这是把 565 行检索引擎从"无调用"变为主链路可查的入口。

    参数：
      query: 查询串（必填）
      corpus: 语料过滤 crops/zones/pests/recipes/all（默认 all）
      k: 返回条数（默认 10，最大 50）
      mode: exact/keyword/vector/hybrid（默认 hybrid）
    返回：evidence（索引统计）+ results（含 corpus/entity/snippet/score 分解）。
    """
    errs = validate_tool_args("agri_search", TOOL_SCHEMA_search, args)
    if errs:
        return {"error": "; ".join(errs)}
    from engine import local_search
    query = (args.get("query") or "").strip()
    if not query:
        return {"error": "query 必填"}
    corpus = args.get("corpus") or "all"
    if corpus not in ("all", "crops", "zones", "pests", "recipes"):
        return {"error": f"非法 corpus='{corpus}'，合法值: all/crops/zones/pests/recipes"}
    try:
        k = int(args.get("k") or 10)
    except (TypeError, ValueError):
        return {"error": "k 必须是整数"}
    k = max(1, min(k, 50))
    mode = args.get("mode") or "hybrid"
    if mode not in ("exact", "keyword", "vector", "hybrid"):
        return {"error": f"非法 mode='{mode}'，合法值: exact/keyword/vector/hybrid"}
    try:
        # 惰性构建：新 runner / 首次调用时索引未落盘。rebuild() 幂等（~0.8s，
        # stdlib sqlite3 FTS5），保证 evidence/index_built=True 与 results 稳定
        # 可查——否则空索引会让 count=0 静默通过但结果无用。
        st0 = local_search.stats()
        if not st0.get("built"):
            local_search.rebuild()
        results = local_search.search(query=query, corpus=corpus, k=k, mode=mode)
        st = local_search.stats()
        return {
            "query": query,
            "corpus": corpus,
            "mode": mode,
            "evidence": {
                "index_built": bool(st.get("built")),
                "index_path": st.get("path"),
                "total_docs": st.get("total", 0),
                "corpus_rows": st.get("rows", {}),
                "fts_available": st.get("fts", False),
                "schema_ver": st.get("schema_ver"),
                "engine": "char n-gram + cosine + SQLite FTS5 (stdlib-only)",
            },
            "count": len(results),
            "results": results,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"检索失败: {e}"}


def _tool_knowledge_query(args: dict) -> dict:
    """知识图谱查询：分区→作物 / 风险→作物 / 邻居 / 遍历（M12-K1）。

    底层走 engine/knowledge_graph.py（261 实体 / 446 边，纯 stdlib）。
    把图谱从"无调用"变为可查——是 M12-K1 的主链路接通点。

    参数（按 kind 分派）：
      kind=crops_by_zone: zone_id 必填，返回该分区 crop + adapt_score 排序
      kind=crops_by_risk: risk 必填，返回该病虫害关联作物
      kind=neighbors: node 必填，返回该节点邻居（正/反向）
      kind=traverse: node 必填，depth 可选，返回 BFS 遍历路径
      kind=summary: 返回图谱整体统计（实体数/边数/类型分布）
    """
    errs = validate_tool_args("agri_knowledge_query", TOOL_SCHEMA_knowledge_query, args)
    if errs:
        return {"error": "; ".join(errs)}
    from engine import knowledge_graph as kg
    kind = args.get("kind") or "summary"
    if kind == "summary":
        g = kg.load_graph()
        entities = g.get("entities", [])
        edges = g.get("edges", [])
        by_type: dict = {}
        for e in entities:
            t = e.get("type", "?")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "kind": "summary",
            "total_entities": len(entities),
            "total_edges": len(edges),
            "entities_by_type": by_type,
            "sources": g.get("sources", []),
            "built_at": g.get("built_at"),
        }
    if kind == "crops_by_zone":
        zone = (args.get("zone_id") or "").strip()
        if not zone:
            return {"error": "kind=crops_by_zone 时 zone_id 必填"}
        top_k = int(args.get("top_k") or 5)
        return {"kind": "crops_by_zone", "zone_id": zone,
                "crops": kg.find_crops(zone_id=zone, top_k=top_k)}
    if kind == "crops_by_risk":
        risk = (args.get("risk") or "").strip()
        if not risk:
            return {"error": "kind=crops_by_risk 时 risk 必填"}
        top_k = int(args.get("top_k") or 5)
        try:
            return {"kind": "crops_by_risk", "risk": risk,
                    "crops": kg.find_crops_for_risk(risk=risk, top_k=top_k)}
        except TypeError:
            # 老版本 find_crops_for_risk 签名可能不同，尝试兜底
            try:
                r = kg.find_crops_for_risk(risk)
                return {"kind": "crops_by_risk", "risk": risk, "crops": r}
            except Exception as e:  # noqa: BLE001
                return {"error": f"风险反查失败: {e}"}
    if kind == "neighbors":
        node = (args.get("node") or "").strip()
        if not node:
            return {"error": "kind=neighbors 时 node 必填"}
        reverse = bool(args.get("reverse", False))
        relation = args.get("relation") or None
        return {"kind": "neighbors",
                "neighbors": kg.neighbors(node=node, reverse=reverse, relation=relation)}
    if kind == "traverse":
        node = (args.get("node") or "").strip()
        if not node:
            return {"error": "kind=traverse 时 node 必填"}
        depth = int(args.get("depth") or 2)
        depth = max(1, min(depth, 5))
        return {"kind": "traverse",
                "traversal": kg.traverse(start=node, depth=depth)}
    return {"error": f"非法 kind='{kind}'，合法值: summary/crops_by_zone/crops_by_risk/neighbors/traverse"}


def _tool_forecast(args: dict) -> dict:
    """独立产量/采收预测：含 T-3 置信区间（M13-P1，把 M5 从"无入口"变可查）。

    底层走 agent/forecast_agent.py，与 agri_growth_plan 里的 recommend 部分同源，
    但作为独立工具暴露，让 MCP 客户端不必先跑 growth_plan 再解 recommendation。

    参数：
      crop: 必填，作物中文名
      zone_id: 可选，分区 ID（决定气候因子）
      start_date: 可选，YYYY-MM-DD（决定采收期）
      adapt_score: 可选，0-1 分区适配度（影响产量基准）
      env_recipe: 可选，Env Recipe dict（含 light/temperature → 影响产量）
      growth_plan: 可选，growth_plan 输出（提供 phases → 决定基础周期）
    返回：完整 forecast 输出（含 evidence/confidence/constraints/recommendation
          + prediction_interval P10/P50/P90）。
    """
    errs = validate_tool_args("agri_forecast", TOOL_SCHEMA_forecast, args)
    if errs:
        return {"error": "; ".join(errs)}
    from agent.forecast_agent import ForecastAgent
    crop = (args.get("crop") or "").strip()
    if not crop:
        return {"error": "crop 必填"}
    zone_id = (args.get("zone_id") or "").strip()
    start_date = (args.get("start_date") or "").strip()
    adapt_score = args.get("adapt_score")
    if adapt_score is not None:
        try:
            adapt_score = float(adapt_score)
        except (TypeError, ValueError):
            return {"error": "adapt_score 必须是数值 0-1"}
    if adapt_score is not None and not (0.0 <= adapt_score <= 1.0):
        return {"error": f"adapt_score 超出 [0,1] 范围: {adapt_score}"}
    env_recipe = args.get("env_recipe")
    if env_recipe is not None and not isinstance(env_recipe, dict):
        return {"error": "env_recipe 必须是对象"}
    growth_plan = args.get("growth_plan")
    if growth_plan is not None and not isinstance(growth_plan, dict):
        return {"error": "growth_plan 必须是对象"}
    zone_climate = args.get("zone_climate")
    if zone_climate is not None and not isinstance(zone_climate, list):
        return {"error": "zone_climate 必须是数组"}
    try:
        agent = ForecastAgent()
        return agent.estimate(
            crop=crop,
            zone_id=zone_id,
            start_date=start_date,
            growth_plan=growth_plan,
            zone_climate=zone_climate,
            env_recipe=env_recipe,
            adapt_score=adapt_score,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"预测失败: {e}"}


def _tool_recipe_profile(args: dict) -> dict:
    """Env Recipe profile 四件套（M8-R2）：让 152 份配方从"资产厚但流转弱"变活。

    底层走 scripts/recipe_profile.py（stdlib + difflib，零依赖）。
    支持 5 种 kind：
      kind=list:   列出所有配方元信息（152 份 × filename/recipe_ref/size/sha256）
      kind=stats:  资产统计（总数/字节/stage 分布/device_class 分布）
      kind=diff:   结构化 diff 两份配方（a, b 必填；difflib 统一 diff）
      kind=export: 导出到临时文件并返回内容（供分享/备份；隐私字段默认剥离）
      kind=lookup: 按文件名加载完整配方内容

    import/clone 涉及写盘，不进 MCP（保持分发通道只读）——
    需写盘请直接用 CLI: python scripts/recipe_profile.py import|clone ...
    """
    errs = validate_tool_args("agri_recipe_profile", TOOL_SCHEMA_recipe_profile, args)
    if errs:
        return {"error": "; ".join(errs)}
    kind = (args.get("kind") or "list").strip()
    try:
        # 懒加载：避免 MCP 主进程启动时加载 recipe 库
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from recipe_profile import (export_recipe, diff_recipes,
                                    list_recipes, recipe_stats, search_recipes)
        import tempfile
    except ImportError as e:
        return {"error": f"recipe_profile 模块加载失败: {e}"}

    if kind == "list":
        return {"kind": "list", "recipes": list_recipes()}
    if kind == "search":
        # M13-P2 渐进式发现：结构化过滤 + mode=brief/full
        mode = (args.get("mode") or "brief").strip().lower()
        if mode not in ("brief", "full"):
            return {"error": f"非法 mode='{mode}'，合法值: brief/full"}
        try:
            results = search_recipes(
                keyword=args.get("keyword", ""),
                crop=args.get("crop", ""),
                stage=args.get("stage", ""),
                device_class=args.get("device_class", ""),
                mode=mode,
            )
            return {
                "kind": "search",
                "mode": mode,
                "count": len(results),
                "recipes": results,
            }
        except ValueError as e:
            return {"error": str(e)}
    if kind == "stats":
        return {"kind": "stats", **recipe_stats()}
    if kind == "lookup":
        name = (args.get("filename") or "").strip()
        if not name:
            return {"error": "kind=lookup 时 filename 必填"}
        from scripts.recipe_profile import _recipe_path, _load
        path = _recipe_path(name)
        if not os.path.exists(path):
            return {"error": f"配方不存在: {name}"}
        return {"kind": "lookup", "filename": name, "recipe": _load(path)}
    if kind == "diff":
        a = (args.get("a") or "").strip()
        b = (args.get("b") or "").strip()
        if not a or not b:
            return {"error": "kind=diff 时 a 与 b 均必填"}
        try:
            return {"kind": "diff", **diff_recipes(a, b)}
        except FileNotFoundError as e:
            return {"error": f"配方文件不存在: {e}"}
    if kind == "export":
        name = (args.get("filename") or "").strip()
        if not name:
            return {"error": "kind=export 时 filename 必填"}
        try:
            # 导出到临时文件，再读回内容作为 JSON 返回
            with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False,
                    encoding="utf-8") as tmp:
                tmp_path = tmp.name
            r = export_recipe(name, tmp_path,
                              include_sources=not args.get("no_sources", False),
                              include_execution_log=args.get("include_execution_log", False),
                              include_outcome=args.get("include_outcome", False))
            with open(tmp_path, "r", encoding="utf-8") as f:
                content = f.read()
            os.unlink(tmp_path)
            r["content"] = content
            r.pop("exported_path", None)  # 不暴露本机临时路径
            return {"kind": "export", "meta": r}
        except FileNotFoundError as e:
            return {"error": f"配方不存在: {e}"}
    return {"error": f"非法 kind='{kind}'，合法值: list/search/stats/lookup/diff/export"}


def _tool_verify_trust(args: dict) -> dict:
    """M11-T1 可信标记公共复算 API：外部独立验证 Trust Mark / Certificate。

    支持 3 种模式：
      - current:      返回当前信任标记 JSON（含 signature 与复算命令）
      - check_prefix: 检查外部提供的 mark 内部一致性（signature_prefix vs signature 前 12 字符）
      - end_to_end:   用外部 mark 的 issued_at + 本地数据源严格重现 signature 对比

    诚实边界：signature 是内容一致性 SHA256，非密码学签名（无密钥）——
    证明数据未被修改，不证明签发者身份。
    """
    errs = validate_tool_args("agri_verify_trust", TOOL_SCHEMA_verify_trust, args)
    if errs:
        return {"error": "; ".join(errs)}
    mode = args.get("mode") or "current"
    if mode not in ("current", "check_prefix", "end_to_end"):
        return {"error": f"非法 mode='{mode}'，合法值: current/check_prefix/end_to_end"}

    try:
        from scripts.verify_trust_mark import (
            current_mark_json, verify_mark_internal, verify_mark_end_to_end,
        )
    except Exception as e:  # noqa: BLE001
        return {"error": f"导入 verify_trust_mark 失败: {e}"}

    if mode == "current":
        return current_mark_json()

    mark = args.get("mark")
    if not isinstance(mark, dict):
        return {"error": f"mode={mode} 需要提供 mark 对象"}

    if mode == "check_prefix":
        return verify_mark_internal(mark)
    # mode == end_to_end
    return verify_mark_end_to_end(mark)


def _tool_list_ecosystem(args: dict) -> dict:
    """生态对接清单：返回 config/ecosystem.json 声明的开源/商业生态清单。
    声明对接状态（integrated/partial/planned_mapping/evaluating/competitor_reference/not_evaluated），
    让 MCP 客户端知道我们的开放生态策略与差异化定位。"""
    errs = validate_tool_args("agri_list_ecosystem", TOOL_SCHEMA_list_ecosystem, args)
    if errs:
        return {"error": "; ".join(errs)}
    import json as _json
    cfg_path = os.path.join(ROOT, "config", "ecosystem.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError) as e:
        return {"error": "ecosystem.json 未找到或解析失败", "detail": str(e)}
    status_filter = args.get("status")
    ecosystems = cfg.get("ecosystems", [])
    if status_filter:
        valid = {"integrated", "partial", "planned_mapping",
                 "evaluating", "competitor_reference", "not_evaluated"}
        if status_filter not in valid:
            return {
                "error": f"非法 status='{status_filter}'，合法值: {sorted(valid)}",
                "count": 0,
                "ecosystems": [],
            }
        ecosystems = [e for e in ecosystems if e.get("status") == status_filter]
    return {
        "meta": cfg.get("meta", {}),
        "ecosystems": ecosystems,
        "integration_matrix": cfg.get("integration_matrix", {}),
        "count": len(ecosystems),
    }


TOOLS = [
    {
        "name": "agri_list_cities",
        "category": "climate",
        "description": "列出预设城市（经纬度 + 气候带），供 Agent 选点或核对分区。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "agri_match_zone",
        "category": "climate",
        "description": "输入经纬度，返回气候分区匹配结果（含证据与限制因子）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "纬度"},
                "lon": {"type": "number", "description": "经度"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "agri_recommend_crops",
        "category": "crop",
        "description": "根据分区（lat/lon 或 city）与偏好（用途/空间/难度）推荐作物。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "city": {"type": "string"},
                "purpose": {"type": "string", "description": "食用/观赏/药用"},
                "space_sqm": {"type": "number"},
                "difficulty": {"type": "string"},
                "scene": {"type": "string"},
            },
        },
    },
    {
        "name": "agri_growth_plan",
        "category": "phenology",
        "description": "作物 + 场景 + 分区 → 生成种植计划（含微气候修正）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物名，如 番茄"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "scene": {"type": "string"},
                "floor": {"type": "integer"},
                "orientation": {"type": "string"},
                "city": {"type": "string"},
                "start_date": {"type": "string"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_diagnose_pest",
        "category": "pest",
        "description": "病虫害与营养缺乏诊断：输入作物、症状描述（可选图像引用、生长阶段、环境）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string"},
                "symptom_description": {"type": "string"},
                "image_reference": {"type": "string"},
                "growth_stage": {"type": "string"},
                "environment": {"type": "object"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_nutrition_plan",
        "category": "nutrition",
        "description": "养分管理：作物 + 阶段 → 阶段化施肥方案。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string"},
                "scene": {"type": "string"},
                "growth_stage": {"type": "string"},
                "growth_days": {"type": "integer"},
                "container_volume_l": {"type": "number"},
                "start_date": {"type": "string"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_env_recipe",
        "category": "recipe",
        "description": "（P0-G）作物 + 生长阶段 + 设备类别 → 返回一份 Env Recipe v1 合规配方 JSON。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物名"},
                "stage": {"type": "string", "enum": _STAGES},
                "device_class": {"type": "string", "enum": _DEVICE_CLASSES},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_season_advisory",
        "category": "meta",
        "description": "（B1+B2）物候与播期：mode=planting_window 时给 12 个月均温返回无霜期与各作物最早/最晚安全播种日；mode=stage_days 时给作物+日均温返回出苗/开花/成熟天数；mode=calendar 时按 USDA 区+日期查外部日历（需数据到位）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["planting_window", "stage_days", "calendar"],
                         "description": "默认 planting_window"},
                "monthly_mean_c": {"type": "array", "items": {"type": "number"},
                                   "description": "12 个月均温（℃），1 月起；planting_window 必填"},
                "crops": {"type": "array", "items": {"type": "string"},
                          "description": "限定作物（中文名或英文 key），默认全部已移植作物"},
                "frost_threshold_c": {"type": "number", "description": "霜冻阈值，默认 0"},
                "safety_margin_days": {"type": "integer", "description": "成熟安全边际天数，默认 7"},
                "crop": {"type": "string", "description": "stage_days 模式必填"},
                "mean_temp_c": {"type": "number", "description": "stage_days 模式必填"},
                "zone": {"type": "integer", "description": "USDA 耐寒区；calendar 模式必填"},
                "date": {"type": "string", "description": "YYYY-MM-DD；calendar 模式必填"},
                "category": {"type": "string"},
            },
        },
    },
    {
        "name": "agri_soil_profile",
        "category": "soil",
        "description": "（土壤降级路径）经纬度或分区 → 土壤剖面。优先查 ISRIC SoilGrids v2.0（在线点数据），不可用时降级为离线分区均值并明确标注 resolution=zone、confidence=low。可选传入 crop 做 pH 适宜性拟合。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "纬度（与 lon 同用；可与 zone_id 二选一）"},
                "lon": {"type": "number", "description": "经度"},
                "zone_id": {"type": "string",
                            "description": "分区 ID，如 subtropical_wet / temperate_continental / arid"},
                "crop": {"type": "string", "description": "可选：作物名，用于 pH 适宜性拟合"},
                "online": {"type": "boolean",
                           "description": "是否尝试在线 SoilGrids 点查询，默认 true；设 false 直接走离线分区数据（更快）"},
                "timeout_s": {"type": "number", "description": "在线查询超时秒数，默认 10"},
            },
        },
    },
    {
        "name": "agri_bp_screen",
        "category": "business",
        "description": (
            "（投资初筛）农业项目投资初筛系统：传入 BP/审计/流水文本（text）或已抽取字段（fields），"
            "跑九层管线 → 六分类（种业/农机/数字农业/生物投入品/供应链/养殖）+ 五闸爆雷 + "
            "六评分卡 + 一票否决 → 三档结论（≥75 通过 / 60-75 需深挖 / <60 淘汰），"
            "并返回归因决策路径、反事实边界（补齐哪几项可翻档）、三级数据缺口清单、"
            "证照核验结果与合理性校验摘要。输入是 BP 文本，不依赖本项目种植数据，也不生成 ROI 数字。"
            "输出为初筛参考，不构成投资决策建议；核验层 local_hit 仅为本地示例库字符串匹配，"
            "不是官方核验。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "BP / 审计报告 / 银行流水 / 证书文本。与 fields 二选一"},
                "fields": {"type": "object",
                           "description": "已抽取的结构化字段 dict（跳过归档/解析/提取/归一化层）。"
                                          "常见键：revenue, gross_margin, net_margin, ue_margin, "
                                          "runway_months, top5_client_pct, subsidy_pct, "
                                          "approved_varieties, safety_certs, reg_certs, eia_passed 等。"
                                          "与 text 二选一"},
                "category": {"type": "string",
                             "enum": ["seeds", "agmach", "digag", "bioinputs", "supply", "livestock"],
                             "description": "可选：强制指定分类，跳过自动分类（用于人工确认后再评）"},
                "company": {"type": "string", "description": "公司名称（可选，报告与溯源用）"},
                "mode": {"type": "string", "enum": ["text", "md", "docx"],
                         "description": "text 模式下的解析类型，默认 text"},
                "filename": {"type": "string", "description": "可选：虚拟文件名，用于报告溯源"},
            },
        },
    },
    {
        "name": "agri_reconcile_climate",
        "category": "climate",
        "description": (
            "（多源气候校准）给定经纬度，并行拉 NASA POWER + Open-Meteo，逐月平均得调和月均温基线，"
            "并计算逐月一致度（多源标准差）与分歧月份告警（标准差超 3℃ 标记）。"
            "WorldClim 2.1 列为扩展点（暂未接逐点取数）。无网络时优雅降级（reconciled=null + "
            "provenance_complete=false），绝不返回编造值。对齐壁垒④ 真实结果回流校准。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "纬度"},
                "lon": {"type": "number", "description": "经度"},
                "years": {"type": "integer", "description": "取数年数，默认 5"},
                "sources": {"type": "array", "items": {"type": "string"},
                            "description": "源 id 列表，默认 [power, open_meteo]；可含 worldclim（扩展点）"},
            },
            "required": ["lat", "lon"],
        },
    },
    {
        "name": "agri_resolve_recipe",
        "category": "recipe",
        "description": (
            "（地理编码→配方）城市名（中文/英文）或经纬度 → 匹配气候分区 → 检索该分区的 Env Recipe 清单。"
            "返回 zone_id / zone_name / 坐标 / 匹配配方（作物名+阶段+设备类+路径）。"
            "核心「城市种植生成箱」分发价值，完全离线。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "城市名（如 杭州）或 \"lat,lon\" 坐标串；与 lat/lon 二选一"},
                "lat": {"type": "number", "description": "纬度（与 lon 同用；可与 query 二选一）"},
                "lon": {"type": "number", "description": "经度"},
            },
        },
    },
    {
        "name": "agri_query_lineage",
        "category": "meta",
        "description": (
            "（数据血缘查询）按作物/分区查配方的数据溯源：外部 API 参与情况 + 本地权威文件 SHA256 指纹 + "
            "校准实证（壁垒④）。传入 crop+zone_id 做单点追踪；仅 crop 查全分区；仅 zone_id 查全作物；"
            "皆空返回全局摘要。对齐 GOAI DataFlow-Agent 提升点3。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物名（中文）；与 zone_id 可组合"},
                "zone_id": {"type": "string",
                            "description": "分区 ID，如 subtropical_wet / temperate_continental / arid"},
            },
        },
    },
    {
        "name": "agri_list_ecosystem",
        "category": "meta",
        "description": (
            "（生态对接清单）返回智慧农业生态对接的开源/商业生态清单（config/ecosystem.json），"
            "含对接状态（integrated/partial/planned_mapping/evaluating/competitor_reference/not_evaluated）、"
            "许可、URL、用途说明与集成计划。让 MCP 客户端一次看清我们的开放生态策略：能对接的不重复造轮子，"
            "只做 MCP 分发不做 SaaS。可选按 status 过滤。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "description": "可选过滤：integrated/partial/planned_mapping/evaluating/competitor_reference/not_evaluated",
                           "enum": ["integrated", "partial", "planned_mapping",
                                    "evaluating", "competitor_reference", "not_evaluated"]},
            },
        },
    },
    {
        "name": "agri_search",
        "category": "knowledge",
        "description": (
            "（知识检索 M12-K1）跨 4 语料（crops/zones/pests/recipes，共 335 条）做词法+向量混合检索，"
            "底层是 stdlib-only 的 char n-gram + cosine + SQLite FTS5（engine/local_search.py，565 行零依赖引擎）。"
            "把 M12 板块从『有引擎无调用』变为主链路可查。默认 hybrid 模式，"
            "可切 exact/keyword/vector。返回含 corpus/entity/snippet/score 分解与索引统计。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询串（必填）"},
                "corpus": {"type": "string", "description": "语料过滤",
                           "enum": ["all", "crops", "zones", "pests", "recipes"]},
                "k": {"type": "integer", "description": "返回条数，默认 10，最大 50", "default": 10},
                "mode": {"type": "string", "description": "检索模式",
                         "enum": ["exact", "keyword", "vector", "hybrid"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "agri_knowledge_query",
        "category": "knowledge",
        "description": (
            "（知识图谱查询 M12-K1）查 261 实体 / 446 边的农业知识图谱（engine/knowledge_graph.py）。"
            "支持 5 种 kind：summary=整体统计；crops_by_zone=分区→作物排序；crops_by_risk=病虫害→受影响作物；"
            "neighbors=节点邻居；traverse=BFS 遍历。把图谱从『无调用』变为可查入口。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "查询类型",
                         "enum": ["summary", "crops_by_zone", "crops_by_risk",
                                  "neighbors", "traverse"],
                         "default": "summary"},
                "zone_id": {"type": "string", "description": "crops_by_zone 时必填"},
                "risk": {"type": "string", "description": "crops_by_risk 时必填"},
                "node": {"type": "string", "description": "neighbors/traverse 时必填"},
                "relation": {"type": "string", "description": "neighbors 时可选，只查指定关系"},
                "reverse": {"type": "boolean", "description": "neighbors 时反向（沿入边），默认 false"},
                "depth": {"type": "integer", "description": "traverse 深度，1-5，默认 2"},
                "top_k": {"type": "integer", "description": "返回前 K，默认 5"},
            },
        },
    },
    {
        "name": "agri_forecast",
        "category": "forecast",
        "description": (
            "（独立预测 M13-P1）产量/采收期预测，含 T-3 置信区间（P10/P50/P90）。"
            "底层与 agri_growth_plan 内的推荐部分同源（ForecastAgent），但独立暴露，"
            "让 MCP 客户端不必先跑 growth_plan 再解 recommendation。"
            "含 heuristic_spread_based 区间与诚实的 model=heuristic 标注。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物中文名（必填）"},
                "zone_id": {"type": "string", "description": "分区 ID（可选，决定气候因子）"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD（可选，决定采收期）"},
                "adapt_score": {"type": "number", "description": "分区适配度 0-1（可选）",
                                "minimum": 0, "maximum": 1},
                "env_recipe": {"type": "object", "description": "Env Recipe 对象（可选，含 light/temperature）"},
                "growth_plan": {"type": "object", "description": "growth_plan 输出（可选，含 phases 决定周期）"},
                "zone_climate": {"type": "array", "description": "分区月度均温列表（可选，覆盖默认）",
                                 "items": {"type": "number"}},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_recipe_profile",
        "category": "recipe",
        "description": (
            "（配方 profile 五件套 M8-R2 + M13-P2）152 份 Env Recipe 资产的浏览、检索、比对、导出、加载。"
            "支持 6 种 kind：list=列出所有配方元信息（brief）；"
            "search=结构化过滤（keyword/crop/stage/device_class）+ mode=brief/full（渐进式发现，节省 context）；"
            "stats=资产统计（总数/字节/分布）；lookup=按文件名加载完整配方；"
            "diff=结构化 diff（difflib 统一 diff）；export=导出到 JSON 字符串（隐私字段默认剥离）。"
            "import/clone 涉及写盘，不进 MCP——请用 CLI scripts/recipe_profile.py。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "操作类型",
                         "enum": ["list", "search", "stats", "lookup", "diff", "export"],
                         "default": "list"},
                "filename": {"type": "string", "description": "lookup/export 时必填"},
                "a": {"type": "string", "description": "diff 时必填，配方 A 路径或文件名"},
                "b": {"type": "string", "description": "diff 时必填，配方 B 路径或文件名"},
                "no_sources": {"type": "boolean", "description": "export 时是否剥离 sources"},
                "include_execution_log": {"type": "boolean", "description": "export 时是否含私有 execution_log"},
                "include_outcome": {"type": "boolean", "description": "export 时是否含私有 outcome"},
                "mode": {"type": "string", "description": "search/list 输出粒度：brief=仅关键属性+可信度信号（默认，节省 context）；full=完整 JSON",
                         "enum": ["brief", "full"], "default": "brief"},
                "keyword": {"type": "string", "description": "search 时按作物/学名/科做模糊匹配"},
                "crop": {"type": "string", "description": "search 时按作物名精确或子串匹配"},
                "stage": {"type": "string", "description": "search 时按阶段过滤（seed/seedling/vegetative/flowering/fruiting/harvest/full_cycle）"},
                "device_class": {"type": "string", "description": "search 时按设备类别过滤"},
            },
        },
    },
    {
        "name": "agri_verify_trust",
        "category": "meta",
        "description": (
            "（可信标记公共复算 API M11-T1）外部独立验证 AgriTrust 可信标记 / 证书。"
            "支持 3 种 mode：current=返回当前信任标记（含 signature 与复算命令）；"
            "check_prefix=检查外部提供的 mark 内部一致性（signature_prefix 是否为 signature 前 12 字符）；"
            "end_to_end=用外部 mark 的 issued_at + 本地数据源严格重现 signature 对比。"
            "诚实边界：signature 是内容一致性 SHA256，非密码学签名（无密钥）——"
            "证明数据未被修改，不证明签发者身份。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string",
                         "description": "验证模式：current/check_prefix/end_to_end",
                         "enum": ["current", "check_prefix", "end_to_end"],
                         "default": "current"},
                "mark": {"type": "object",
                         "description": "check_prefix / end_to_end 时必填：外部提供的 trust_mark JSON"},
            },
            "required": ["mode"],
        },
    },
    {
        "name": "agri_server_card",
        "category": "meta",
        "description": (
            "（Server Card + ETags M13-P3）返回 MCP 服务元数据卡（能力/分类/协议/URL 等），"
            "带稳定 ETag（sha256 前 16 hex）。客户端可缓存；带 if_none_match 命中时返回 "
            "not_modified 短路。与 .well-known/mcp-card.json 同源；24h 建议缓存 TTL。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "if_none_match": {"type": "string",
                                  "description": "客户端缓存的 ETag；命中时返回 not_modified 短路"},
            },
        },
    },
    {
        "name": "agri_decision_path_report",
        "category": "bp_screen",
        "description": (
            "（决策路径可视化报告 M16-B2）将 bp_screen 评分引擎的 decision_path 归因数据"
            "导出为可视化报告。返回结构化 JSON：每个案例含 verdict/decision_path/counterfactual/"
            "dimensions 完整数据。支持 case_id 筛选。输出格式为可解析的归因树，"
            "供前端渲染或下游报告系统消费。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_ids": {"type": "array",
                             "items": {"type": "integer"},
                             "description": "案例 ID 列表（可选，默认全量非 benchmark 案例）"},
                "format": {"type": "string",
                           "enum": ["json", "summary"],
                           "default": "json",
                           "description": "输出格式：json=完整结构化数据，summary=精简摘要"},
            },
        },
    },
    {
        "name": "agri_counterfactual_trajectory",
        "category": "counterfactual",
        "description": (
            "（反事实轨迹 API · Phase N+1 #6）给定作物与基线动作序列，"
            "用 AgriWorld-Lite 机理内核（光截获 Beer-Lambert + CO2 同化 + Q10 呼吸 + "
            "Penman-Monteith 蒸腾）仿真 45 天生物量轨迹。支持 quick_scenario 快速对比"
            "（光周期 12→16h / 降温 5℃ / 停肥 / 高湿等），返回 Δ生物量、归因分解"
            "（光/温/水/肥/发育）与机理-启发式双轨分歧告警。零依赖纯标准库。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物名，如 potato/番茄/生菜"},
                "days": {"type": "integer", "default": 45, "description": "种植天数"},
                "quick_scenario": {"type": "string",
                    "enum": ["light_12_to_16h", "cool_down_5c", "stop_fertilizer",
                             "high_humidity", "double_water", "baseline"],
                    "default": "baseline",
                    "description": "预设场景，非 baseline 会覆盖 baseline_actions"},
                "baseline_dli_mj": {"type": "number", "default": 10.0,
                                    "description": "基线日累积辐射 MJ/m²/d"},
                "baseline_temp_c": {"type": "number", "default": 22.0,
                                    "description": "基线日均温 ℃"},
                "heuristic_est": {"type": "number",
                                   "description": "启发式轨点估计 g/m²，用于双轨分歧告警"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_verify_recommendation",
        "category": "verify",
        "description": (
            "（Verify-as-a-Service · Phase N+3 #14 · 支柱五）作为「农业 Agent 的裁判」"
            "验证第三方（另一个 Agent、大模型、BP、农艺师）给出的农业主张。"
            "支持三类冲突检测：① 物理约束（光能转化效率、物质守恒）"
            "② 物候（积温-发育期一致性）③ 环境-品种（生态位适宜度）。"
            "输出 verdict=supported|contradicted|caution|unverifiable、保形区间 p10/p50/p90、"
            "矛盾清单、可复算 trust_mark（SHA256）。"
            "本工具是支柱五的核心：让「不能验证的建议永远免费」变成工程能力。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim": {"type": "object",
                          "description": "被验证主张，如 {crop, yield_g_m2, duration_days}",
                          "required": ["crop"]},
                "context": {"type": "object",
                            "description": "上下文，如 {dli_mj_m2_d, days, temp_mean_c, "
                                          "latitude, rh, co2_ppm, zone}"},
                "heuristic_engine_est": {"type": "number",
                                          "description": "启发式引擎点估计，用于双轨"},
            },
            "required": ["claim", "context"],
        },
    },
    {
        "name": "agri_economics",
        "category": "business",
        "description": (
            "（Stage 2.3 · 2026-10-24 新增）农业经济测算：输入 crop / zone / area_sqm / 投入参数，"
            "输出投入成本 CNY / 预期产量 kg / 收益区间 / ROI / 回本周期。"
            "诚实边界：成本随地区/年份/规模差异大，输出**区间**而非单点；"
            "数据年份 2024-2025 全国均价，不含人工；标注 data_quality=modeled（非实测）。"
            "支持主粮 5 作物（水稻/小麦/玉米/大豆/马铃薯）+ 蔬果（番茄/生菜/草莓/黄瓜/辣椒）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物中文名"},
                "zone": {"type": "string", "description": "气候分区，可选；默认 auto"},
                "area_sqm": {"type": "number", "description": "种植面积 ㎡，默认 100"},
                "labor_cny_day": {"type": "number", "description": "人工日成本，可选（不含）"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_postharvest",
        "category": "nutrition",
        "description": (
            "（Stage 2.6 · 2026-10-24 新增）采后处理/储藏：输入 crop，"
            "返回最佳储藏温湿度 / 损耗率 / 保鲜期 / 采后病害风险。"
            "诚实边界：数据来自 FAO Codex Alimentarius 通用值，非本地验证；"
            "标 data_quality=modeled；不含冷藏能耗成本。"
            "支持 8 类常见果蔬（生菜/番茄/草莓/黄瓜/苹果/香蕉/叶菜/根茎）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "crop": {"type": "string", "description": "作物中文名"},
                "stage": {"type": "string", "description": "采后阶段 fresh / storage / transport，默认 storage"},
            },
            "required": ["crop"],
        },
    },
    {
        "name": "agri_grow_batch_create",
        "category": "batch",
        "description": (
            "（批次对象 MVP · 2026-10-27 新增）建立 Plot + GrowBatch：把 MCP/UI/校准/审计"
            "的局部上下文收束到批次对象链。MVP 阶段可建立并回放一个模拟批次，"
            "动作默认 shadow/dry_run，不写真实 outcome（P1 才人工确认执行）。"
            "输入 plot（plot_id/location_type）+ batch（batch_id/crop/plot_id/recipe_version/started_at）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "plot": {"type": "object", "description": "Plot 对象（grow_batch.schema.json）"},
                "batch": {"type": "object", "description": "GrowBatch 对象（grow_batch.schema.json）"},
            },
            "required": ["plot", "batch"],
        },
    },
    {
        "name": "agri_grow_batch_observe",
        "category": "batch",
        "description": (
            "（批次对象 MVP · 2026-10-27 新增）追加 Observation：批次生命周期内的一次观察"
            "（传感自动或人工/图像补充）。输入 observation（observation_id/batch_id/ts/metric/source）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "observation": {"type": "object", "description": "Observation 对象（grow_batch.schema.json）"},
            },
            "required": ["observation"],
        },
    },
    {
        "name": "agri_grow_batch_action",
        "category": "batch",
        "description": (
            "（批次对象 MVP · 2026-10-27 新增）记录 Action：一次建议→审批→执行→确认的动作链。"
            "MVP 默认 shadow/dry_run，不真实执行；真实执行（executed）需人工确认且 dry_run=False。"
            "输入 action（action_id/batch_id/ts/recommendation）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "object", "description": "Action 对象（grow_batch.schema.json）"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "agri_grow_batch_status",
        "category": "batch",
        "description": (
            "（批次对象 MVP · 2026-10-27 新增）查询批次状态 + 关联对象（Plot/Observation/Action/Outcome）。"
            "可选 include_events=true 附带 append-only 事件日志。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string", "description": "批次唯一 ID"},
                "include_events": {"type": "boolean", "description": "是否附带事件日志，默认 false"},
            },
            "required": ["batch_id"],
        },
    },
    {
        "name": "agri_grow_batch_replay",
        "category": "batch",
        "description": (
            "（批次对象 MVP · 2026-10-27 新增）按时间线回放批次事件：重建事件序列，"
            "不触发任何真实执行或副作用（诚实标注）。"),
        "inputSchema": {
            "type": "object",
            "properties": {
                "batch_id": {"type": "string", "description": "批次唯一 ID"},
            },
            "required": ["batch_id"],
        },
    },
]

def _tool_server_card(args: dict) -> dict:
    """M13-P3 Server Card：返回 MCP 服务元数据（能力/分类/ETag/URL 等）。

    与 .well-known/mcp-card.json 同源；客户端可缓存此结果，
    后续请求带 If-None-Match（走 _meta.if_none_match 或 headers）
    命中时直接返回 304 等价（result={"not_modified": true, "etag": ...}）。
    """
    etag = _card_etag()
    if etag is None:
        return {"error": "mcp-card.json 未找到或解析失败", "path": _CARD_PATH}
    ifn = args.get("if_none_match") or ""
    if isinstance(ifn, str) and ifn.strip().strip('"') == etag:
        return {"not_modified": True, "etag": etag}
    body = _card_body()
    return {
        "card": body,
        "etag": etag,
        "cache_hint": {
            "ttl_ms": 86400000,  # 24h，server card 属慢变数据
            "scope": "public",
            "algorithm": "sha256",
            "usage": "客户端可缓存 card；带 if_none_match 命中时返回 not_modified",
        },
    }


def _tool_decision_path_report(args: dict) -> dict:
    """M16-B2 决策路径可视化报告：将 bp_screen 评分引擎的 decision_path 归因数据
    导出为结构化报告。支持按案例筛选、JSON/摘要两种格式。

    与 _tool_bp_screen 的关系：bp_screen 是单次评估入口（输入文本/字段 → 评分），
    本工具是批量归因导出（读 DB 存量案例 → 决策路径报告），供前端可视化或报告系统消费。
    """
    errs = validate_tool_args("agri_decision_path_report", TOOL_SCHEMA_decision_path_report, args)
    if errs:
        return {"error": "; ".join(errs)}
    import json as _json
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bp_screen import db, scorer

    case_ids = args.get("case_ids") or None
    fmt = args.get("format", "json")

    cases = db.all_cases()
    cases = [c for c in cases if not c["is_benchmark"]]
    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]

    results = []
    for c in cases:
        m = c["metrics"]
        if isinstance(m, str):
            m = _json.loads(m) if m else {}
        elif m is None:
            m = {}
        n = dict(m)
        if "revenue" in n and "revenue_prev" in n and n["revenue_prev"]:
            n["revenue_growth"] = round((n["revenue"] - n["revenue_prev"]) / n["revenue_prev"] * 100, 1)
        if "cash_balance" in n and "monthly_burn" in n and n["monthly_burn"]:
            n["cash_months"] = round(n["cash_balance"] / n["monthly_burn"], 1)
            n["runway_months"] = round(n["cash_balance"] / n["monthly_burn"], 1)

        ev = scorer.evaluate(c["category"], n)
        card = ev.get("card", {})

        if fmt == "summary":
            results.append({
                "case_id": c["id"],
                "name": c["name"],
                "category": c["category"],
                "verdict": ev.get("verdict"),
                "verdict_name": ev.get("verdict_name"),
                "total_score": card.get("total"),
                "verdict_reason": ev.get("verdict_reason"),
                "gates_count": len(ev.get("gates_fired", [])),
                "vetoes_count": len(ev.get("vetoes_fired", [])),
                "path_item_count": len(ev.get("decision_path", [])),
                "counterfactual_type": (ev.get("counterfactual") or {}).get("type"),
            })
        else:
            results.append({
                "case_id": c["id"],
                "name": c["name"],
                "category": c["category"],
                "verdict": ev.get("verdict"),
                "verdict_name": ev.get("verdict_name"),
                "total_score": card.get("total"),
                "total_range": card.get("total_range"),
                "verdict_reason": ev.get("verdict_reason"),
                "gates_fired": ev.get("gates_fired"),
                "vetoes_fired": ev.get("vetoes_fired"),
                "decision_path": ev.get("decision_path"),
                "counterfactual": ev.get("counterfactual"),
                "dimensions": card.get("dimensions"),
                "rules_version": ev.get("rules_version"),
            })

    return {
        "report_type": "decision_path_report",
        "generated_at": _now_iso(),
        "case_count": len(results),
        "format": fmt,
        "results": results,
    }


def _tool_counterfactual_trajectory(args: dict) -> dict:
    """反事实轨迹 API（MCP #22）：给定作物与场景，用 AgriWorld-Lite 机理内核
    仿真基线与候选动作序列，返回轨迹对比、Δ归因、双轨分歧告警。

    设计：Phase N+1 动作 #6 —— 把 17 个 bench 用例升级为产品能力。
    """
    errs = validate_tool_args("agri_counterfactual_trajectory", TOOL_SCHEMA_counterfactual_trajectory, args)
    if errs:
        return {"error": "; ".join(errs)}
    from engine.agriworld_lite import DailyInput, simulate, get_params, theoretical_yield_cap
    from agent.dual_track import compare_tracks
    import copy

    crop = args.get("crop", "potato")
    days = int(args.get("days", 45))
    dli = float(args.get("baseline_dli_mj", 10.0))
    t_mean = float(args.get("baseline_temp_c", 22.0))
    scenario = args.get("quick_scenario", "baseline")
    heuristic_est = args.get("heuristic_engine_est")

    base = DailyInput(
        dli=dli, temp_mean_c=t_mean,
        temp_min_c=t_mean - 5.0, temp_max_c=t_mean + 5.0,
        rh=0.60, wind_ms=1.5, co2_ppm=420.0,
        irrigation_l_m2=2.0, fert_n_mg_l=30.0,
    )
    cand = copy.deepcopy(base)
    if scenario == "light_12_to_16h":
        cand.light_ext_kj_m2_h = 40.0  # 高功率补光
        cand.light_ext_hours = 4.0
    elif scenario == "cool_down_5c":
        cand.temp_mean_c = t_mean - 5.0
        cand.temp_min_c = cand.temp_mean_c - 5.0
        cand.temp_max_c = cand.temp_mean_c + 5.0
    elif scenario == "stop_fertilizer":
        cand.fert_n_mg_l = 0.0
    elif scenario == "high_humidity":
        cand.rh = 0.85
    elif scenario == "double_water":
        cand.irrigation_l_m2 = base.irrigation_l_m2 * 2.0

    base_sim = simulate(crop, [copy.deepcopy(base)] * days)
    cand_sim = simulate(crop, [copy.deepcopy(cand)] * days)

    b_bm = base_sim["final_biomass"]["total"]
    c_bm = cand_sim["final_biomass"]["total"]
    delta_pct = (c_bm - b_bm) / max(b_bm, 1e-6) * 100

    # 理论上限
    cap = theoretical_yield_cap(crop, dli, days)

    # 双轨
    dual = None
    if heuristic_est is not None:
        dual = compare_tracks(c_bm, heuristic_est, unit="g/m²",
                              dimension="final_biomass")

    # 归因（用 quick 场景直接给出定性说明）
    scenario_note = {
        "baseline": "基线：无变化",
        "light_12_to_16h": "补光 4h × 40 kJ/m²/h（+24k·J/m² 光能）",
        "cool_down_5c": "降温 5℃（Q10 呼吸减半，同化率可能受抑）",
        "stop_fertilizer": "停止施肥（蒸腾驱动 N 吸收归零）",
        "high_humidity": "高湿 RH=0.85（VPD 减半，蒸腾下降）",
        "double_water": "灌溉翻倍（θ 上升，缓解水分胁迫）",
    }.get(scenario, "自定义")

    return {
        "crop": crop,
        "days": days,
        "scenario": scenario,
        "scenario_note": scenario_note,
        "baseline": {
            "final_biomass_g_m2": round(b_bm, 4),
            "w_lv": round(base_sim["final_biomass"]["w_lv"], 4),
            "w_st": round(base_sim["final_biomass"]["w_st"], 4),
            "w_so": round(base_sim["final_biomass"]["w_so"], 4),
            "lai_final": round(base_sim["final_state"]["lai"], 4),
            "totals": base_sim["totals"],
        },
        "candidate": {
            "final_biomass_g_m2": round(c_bm, 4),
            "w_lv": round(cand_sim["final_biomass"]["w_lv"], 4),
            "w_st": round(cand_sim["final_biomass"]["w_st"], 4),
            "w_so": round(cand_sim["final_biomass"]["w_so"], 4),
            "lai_final": round(cand_sim["final_state"]["lai"], 4),
            "totals": cand_sim["totals"],
        },
        "delta": {
            "biomass": round(c_bm - b_bm, 4),
            "biomass_pct": round(delta_pct, 2),
            "w_so": round(cand_sim["final_biomass"]["w_so"] - b_bm + base_sim["final_biomass"]["w_so"], 4),
        },
        "theoretical_yield_cap_g_m2": round(cap, 2),
        "dual_track": dual,
        "verdict": (
            "materially_different" if abs(delta_pct) >= 5
            else "marginal" if abs(delta_pct) >= 2
            else "similar"
        ),
        "engine": "AgriWorld-Lite v0 (stdlib-only, zero deps)",
    }


def _tool_verify_recommendation(args: dict) -> dict:
    """Verify-as-a-Service（MCP #23 · 支柱五）：验证第三方农业主张。

    支持三类冲突检测：物理/物候/环境-品种。
    """
    errs = validate_tool_args("agri_verify_recommendation", TOOL_SCHEMA_verify_recommendation, args)
    if errs:
        return {"error": "; ".join(errs)}
    from agent.verify_service import verify_recommendation

    claim = args.get("claim") or {}
    context = args.get("context") or {}
    heuristic_est = args.get("heuristic_engine_est")

    return verify_recommendation(
        claim=claim, context=context,
        heuristic_engine_est=heuristic_est,
        use_conformal=True,
    )


_DISPATCH = {
    "agri_list_cities": _tool_list_cities,
    "agri_match_zone": _tool_match_zone,
    "agri_recommend_crops": _tool_recommend_crops,
    "agri_growth_plan": _tool_growth_plan,
    "agri_diagnose_pest": _tool_diagnose_pest,
    "agri_nutrition_plan": _tool_nutrition_plan,
    "agri_env_recipe": _tool_env_recipe,
    "agri_season_advisory": _tool_season_advisory,
    "agri_soil_profile": _tool_soil_profile,
    "agri_bp_screen": _tool_bp_screen,
    "agri_reconcile_climate": _tool_reconcile_climate,
    "agri_resolve_recipe": _tool_resolve_recipe,
    "agri_query_lineage": _tool_query_lineage,
    "agri_list_ecosystem": _tool_list_ecosystem,
    "agri_search": _tool_search,
    "agri_knowledge_query": _tool_knowledge_query,
    "agri_forecast": _tool_forecast,
    "agri_recipe_profile": _tool_recipe_profile,
    "agri_verify_trust": _tool_verify_trust,
    "agri_server_card": _tool_server_card,
    "agri_decision_path_report": _tool_decision_path_report,
    "agri_counterfactual_trajectory": _tool_counterfactual_trajectory,
    "agri_verify_recommendation": _tool_verify_recommendation,
}


# ---------- Stage 2.3 经济学层 + 2.6 采后模块（2026-10-24） ----------

# 主粮 5 作物 + 常见蔬果的经济学参考值（数据年份 2024-2025，全国均价，
# 不含人工；单位 CNY/kg 投入 / kg/㎡ 产量 / CNY/kg 市场价）
# 诚实边界：modeled，非实测；区间反映不同气候带与规模差异
_ECONOMICS_TABLE = {
    # 主粮
    "水稻": {"yield_low": 4.5, "yield_high": 7.0, "cost_input": 800, "price_low": 2.5, "price_high": 3.8, "gdd_requirement": 2800},
    "小麦": {"yield_low": 4.0, "yield_high": 6.0, "cost_input": 700, "price_low": 2.6, "price_high": 3.5, "gdd_requirement": 1900},
    "玉米": {"yield_low": 5.0, "yield_high": 8.0, "cost_input": 750, "price_low": 2.4, "price_high": 3.3, "gdd_requirement": 2400},
    "大豆": {"yield_low": 1.5, "yield_high": 2.5, "cost_input": 600, "price_low": 5.5, "price_high": 7.0, "gdd_requirement": 2200},
    "马铃薯": {"yield_low": 15.0, "yield_high": 25.0, "cost_input": 900, "price_low": 2.0, "price_high": 3.5, "gdd_requirement": 1500},
    # 蔬果
    "番茄": {"yield_low": 20.0, "yield_high": 40.0, "cost_input": 1200, "price_low": 4.0, "price_high": 8.0, "gdd_requirement": 1800},
    "生菜": {"yield_low": 8.0, "yield_high": 15.0, "cost_input": 900, "price_low": 6.0, "price_high": 12.0, "gdd_requirement": 1000},
    "草莓": {"yield_low": 15.0, "yield_high": 30.0, "cost_input": 2000, "price_low": 25.0, "price_high": 50.0, "gdd_requirement": 1200},
    "黄瓜": {"yield_low": 25.0, "yield_high": 50.0, "cost_input": 1100, "price_low": 3.0, "price_high": 6.0, "gdd_requirement": 1500},
    "辣椒": {"yield_low": 12.0, "yield_high": 25.0, "cost_input": 1300, "price_low": 8.0, "price_high": 15.0, "gdd_requirement": 1400},
}

# 采后处理参考值（FAO Codex Alimentarius 通用值）
_POSTHARVEST_TABLE = {
    "生菜": {"storage_temp_c": [0, 4], "storage_humidity_pct": [90, 98], "shelf_life_days": [3, 7], "loss_rate_pct": [15, 30], "key_risks": ["叶斑病", "软腐", "失水"]},
    "番茄": {"storage_temp_c": [10, 13], "storage_humidity_pct": [85, 90], "shelf_life_days": [7, 14], "loss_rate_pct": [10, 20], "key_risks": ["脐腐病", "青果", "裂果"]},
    "草莓": {"storage_temp_c": [0, 2], "storage_humidity_pct": [90, 95], "shelf_life_days": [2, 5], "loss_rate_pct": [20, 40], "key_risks": ["灰霉病", "机械损伤", "呼吸衰败"]},
    "黄瓜": {"storage_temp_c": [10, 13], "storage_humidity_pct": [90, 95], "shelf_life_days": [3, 7], "loss_rate_pct": [15, 25], "key_risks": ["冷害", "失水", "菌核病"]},
    "苹果": {"storage_temp_c": [-1, 4], "storage_humidity_pct": [90, 95], "shelf_life_days": [30, 90], "loss_rate_pct": [5, 15], "key_risks": ["轮纹病", "霉心病", "生理性贮藏病"]},
    "香蕉": {"storage_temp_c": [13, 14], "storage_humidity_pct": [85, 90], "shelf_life_days": [7, 14], "loss_rate_pct": [10, 20], "key_risks": ["冷害", "黑斑", "机械损伤"]},
    "叶菜": {"storage_temp_c": [0, 4], "storage_humidity_pct": [90, 98], "shelf_life_days": [3, 10], "loss_rate_pct": [15, 35], "key_risks": ["失水", "软腐", "叶斑病"]},
    "根茎": {"storage_temp_c": [0, 10], "storage_humidity_pct": [85, 90], "shelf_life_days": [30, 180], "loss_rate_pct": [5, 15], "key_risks": ["发芽", "腐烂", "低温损伤"]},
}


def _tool_economics(args: dict) -> dict:
    """Stage 2.3 经济学测算：投入成本 / 产量 / 收益区间 / ROI / 回本周期。"""
    errs = validate_tool_args("agri_economics", TOOL_SCHEMA_economics, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    crop = args.get("crop", "")
    area = float(args.get("area_sqm", 100))
    labor_cny_day = args.get("labor_cny_day")
    entry = _ECONOMICS_TABLE.get(crop)
    if not entry:
        return {
            "contract_violation": True,
            "error": f"作物「{crop}」暂不支持。已支持：{', '.join(_ECONOMICS_TABLE.keys())}",
            "supported_crops": list(_ECONOMICS_TABLE.keys()),
        }
    yield_low = entry["yield_low"] * area
    yield_high = entry["yield_high"] * area
    cost_input = entry["cost_input"] * (area / 100)  # 按面积线性放大
    price_low = entry["price_low"]
    price_high = entry["price_high"]
    revenue_low = yield_low * price_low
    revenue_high = yield_high * price_high
    roi_low = (revenue_low - cost_input) / cost_input * 100
    roi_high = (revenue_high - cost_input) / cost_input * 100
    # 回本周期（年）：1.0 / (roi_low/100) 下限，roi_high 上限
    payback_low = round(1.0 / (roi_high / 100), 2) if roi_high > 0 else None
    payback_high = round(1.0 / (roi_low / 100), 2) if roi_low > 0 else None
    labor_note = ""
    if labor_cny_day:
        # 粗略估算：主粮 5 人日/100㎡，蔬果 10 人日/100㎡
        days = 10 if crop in ("番茄", "生菜", "草莓", "黄瓜", "辣椒") else 5
        labor_cost = labor_cny_day * days * (area / 100)
        labor_note = f"含人工 {labor_cost:.0f} CNY（按 {days} 人日/100㎡ 估）"
        cost_input += labor_cost
    return {
        "crop": crop,
        "area_sqm": area,
        "yield_range_kg": [round(yield_low, 1), round(yield_high, 1)],
        "input_cost_cny": round(cost_input, 0),
        "price_range_cny_kg": [price_low, price_high],
        "revenue_range_cny": [round(revenue_low, 0), round(revenue_high, 0)],
        "roi_range_pct": [round(roi_low, 1), round(roi_high, 1)],
        "payback_years": [payback_low, payback_high],
        "labor_note": labor_note or "不含人工",
        "data_quality": "modeled",
        "data_year": "2024-2025",
        "data_source": "全国农业统计年鉴 + FAOSTAT 参考区间（模型推算，非本地实测）",
        "boundary": [
            "成本随地区/规模/年份差异大，区间反映不确定性",
            "yield 为模型推算，非田间验证",
            "price 为全国均价，未考虑本地市场价",
            "不含土地租金、人工、能源、灌溉、冷链",
            "ROI 未考虑自然风险（病虫害、极端天气）",
        ],
    }


def _tool_postharvest(args: dict) -> dict:
    """Stage 2.6 采后处理：储藏温湿度 / 损耗率 / 保鲜期 / 采后病害风险。"""
    errs = validate_tool_args("agri_postharvest", TOOL_SCHEMA_postharvest, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    crop = args.get("crop", "")
    stage = args.get("stage", "storage")
    entry = _POSTHARVEST_TABLE.get(crop)
    if not entry:
        return {
            "contract_violation": True,
            "error": f"作物「{crop}」暂不支持。已支持：{', '.join(_POSTHARVEST_TABLE.keys())}",
            "supported_crops": list(_POSTHARVEST_TABLE.keys()),
        }
    return {
        "crop": crop,
        "stage": stage,
        "storage_temp_c": entry["storage_temp_c"],
        "storage_humidity_pct": entry["storage_humidity_pct"],
        "shelf_life_days": entry["shelf_life_days"],
        "loss_rate_pct": entry["loss_rate_pct"],
        "key_risks": entry["key_risks"],
        "data_quality": "modeled",
        "data_source": "FAO Codex Alimentarius 通用值（非本地验证）",
        "boundary": [
            "FAO 通用值，非本地田间试验",
            "不含冷藏能耗成本",
            "loss_rate 为行业经验值，实际受储运条件影响",
        ],
    }


# ---------- Stage 批次对象 MVP（2026-10-27） ----------

def _tool_grow_batch_create(args: dict) -> dict:
    """建立 Plot + GrowBatch（MVP：可建立并回放一个模拟批次，不写真实 outcome）。"""
    errs = validate_tool_args("agri_grow_batch_create", TOOL_SCHEMA_grow_batch_create, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    store = get_grow_batch_store()
    try:
        plot = args.get("plot", {})
        batch = args.get("batch", {})
        store.create_plot(plot)
        r = store.create_batch(batch)
        return {"ok": True, "batch_id": r["batch_id"], "plot_id": plot["plot_id"],
                "status": r["status"],
                "honest_note": "MVP：模拟批次已建立，动作默认 shadow/dry_run，真实执行需人工确认"}
    except GrowBatchError as e:
        return {"contract_violation": True, "error": str(e)}


def _tool_grow_batch_observe(args: dict) -> dict:
    """追加 Observation（批次生命周期内的观察记录）。"""
    errs = validate_tool_args("agri_grow_batch_observe", TOOL_SCHEMA_grow_batch_observe, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    store = get_grow_batch_store()
    try:
        r = store.add_observation(args.get("observation", {}))
        return {"ok": True, "observation_id": r["observation_id"], "count": r["count"]}
    except GrowBatchError as e:
        return {"contract_violation": True, "error": str(e)}


def _tool_grow_batch_action(args: dict) -> dict:
    """记录 Action（MVP 默认 shadow/dry_run，不真实执行；executed 需人工确认）。"""
    errs = validate_tool_args("agri_grow_batch_action", TOOL_SCHEMA_grow_batch_action, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    store = get_grow_batch_store()
    try:
        r = store.add_action(args.get("action", {}))
        return {"ok": True, "action_id": r["action_id"], "status": r["status"], "dry_run": r["dry_run"]}
    except GrowBatchError as e:
        return {"contract_violation": True, "error": str(e)}


def _tool_grow_batch_status(args: dict) -> dict:
    """查询批次状态 + 关联对象（可选含事件日志）。"""
    errs = validate_tool_args("agri_grow_batch_status", TOOL_SCHEMA_grow_batch_status, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    store = get_grow_batch_store()
    try:
        b = store.get_batch(args["batch_id"], include_events=bool(args.get("include_events")))
        return {"ok": True, "batch": b["batch"], "plot": b["plot"],
                "n_observations": len(b["observations"]), "n_actions": len(b["actions"]),
                "n_outcomes": len(b["outcomes"]),
                "observations": b["observations"][-10:],  # 最近 10 条
                "actions": b["actions"][-10:],
                "events": b.get("events")}
    except GrowBatchError as e:
        return {"contract_violation": True, "error": str(e)}


def _tool_grow_batch_replay(args: dict) -> dict:
    """按时间线回放批次事件（不触发任何真实执行或副作用）。"""
    errs = validate_tool_args("agri_grow_batch_replay", TOOL_SCHEMA_grow_batch_replay, args)
    if errs:
        return {"contract_violation": True, "errors": errs}
    store = get_grow_batch_store()
    try:
        r = store.replay(args["batch_id"])
        return {"ok": True, "batch_id": r["batch_id"], "n_events": r["n_events"],
                "timeline": r["timeline"], "honest_note": r["honest_note"]}
    except GrowBatchError as e:
        return {"contract_violation": True, "error": str(e)}


# 两个新工具在 _DISPATCH 之后定义，故在此补注册（避免前向引用 NameError）
_DISPATCH["agri_economics"] = _tool_economics
_DISPATCH["agri_postharvest"] = _tool_postharvest
# 批次对象 MVP 工具补注册（同前向引用原因）
_DISPATCH["agri_grow_batch_create"] = _tool_grow_batch_create
_DISPATCH["agri_grow_batch_observe"] = _tool_grow_batch_observe
_DISPATCH["agri_grow_batch_action"] = _tool_grow_batch_action
_DISPATCH["agri_grow_batch_status"] = _tool_grow_batch_status
_DISPATCH["agri_grow_batch_replay"] = _tool_grow_batch_replay


# ---------- JSON-RPC 传输层 ----------

def _send(obj: dict):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


# ---------- SEP-414 W3C Trace Context ----------

def _meta_traceparent(msg: dict) -> str:
    """从 JSON-RPC 请求的 ``_meta.traceparent`` 取 W3C Trace Context（SEP-414）。

    格式：``00-<32hex trace-id>-<16hex parent-id>-<2hex flags>``。
    非法或缺失时返回空串，绝不编造——审计日志里宁缺勿假。
    """
    meta = msg.get("_meta")
    if not isinstance(meta, dict):
        # 兼容 camelCase 与 params 内嵌两种历史写法
        meta = msg.get("meta") if isinstance(msg.get("meta"), dict) else {}
    tp = meta.get("traceparent") or ""
    return tp if isinstance(tp, str) else ""


def _valid_traceparent(tp: str) -> bool:
    """轻量校验 W3C traceparent 形态（不引入正则依赖，逐段判长与字符集）。"""
    if not tp:
        return False
    parts = tp.split("-")
    if len(parts) != 4:
        return False
    ver, tid, pid, flags = parts
    if len(ver) != 2 or len(tid) != 32 or len(pid) != 16 or len(flags) != 2:
        return False
    hexset = set("0123456789abcdef")
    return (all(c in hexset for c in (ver + tid + pid + flags).lower())
            and tid != "0" * 32 and pid != "0" * 16)


def _select_tools_by_category(params: dict) -> dict:
    """M13-P2 渐进式发现：按 category 过滤工具子集。

    支持三种参数形式（向后兼容，不传时返回全量）：
      - 无 category / categories：返回全量 TOOLS
      - params.category = "climate"：返回该分类工具（单分类快捷形式）
      - params.categories = ["climate", "crop"]：返回多分类工具
        · 空数组 = 全量（与"不传"等价）
        · 不存在的分类会被忽略（不报错，保持渐进式发现的宽松语义）
        · 重复分类去重

    返回 ``{"tools": [过滤后的 tool 对象], "categories": [server 支持的所有分类]}``。
    ``categories`` 始终返回完整分类列表，客户端可据此了解 server 全貌，
    即使当前只加载了子集。
    """
    cats = set()
    if isinstance(params, dict):
        single = params.get("category")
        if isinstance(single, str) and single.strip():
            cats.add(single.strip())
        multi = params.get("categories")
        if isinstance(multi, list):
            for c in multi:
                if isinstance(c, str) and c.strip():
                    cats.add(c.strip())
    all_cats = sorted({t.get("category", "misc") for t in TOOLS})
    if not cats:
        return {"tools": list(TOOLS), "categories": all_cats}
    # 已声明的分类中，命中即返回（不存在的分类静默忽略）
    known = {c for c in cats if c in set(all_cats)}
    if not known:
        # 用户指定的分类全部不存在时，仍返回空列表 + 完整分类提示，让客户端感知
        return {"tools": [], "categories": all_cats}
    filtered = [t for t in TOOLS if t.get("category") in known]
    return {"tools": filtered, "categories": all_cats}


def _http_headers_ok(method: str, name: str) -> tuple:
    """SEP-2243 头部一致性校验（仅 HTTP 传输适用）。

    stdio 传输没有 HTTP header，本函数在 stdio 下恒返回 (True, "")；
    一旦本 server 以 HTTP 形态部署（如 ``AGRI_MCP_HTTP=1``），则要求
    ``Mcp-Method`` / ``Mcp-Name`` 与 JSON-RPC body 一致，防止代理篡改导致
    路由与执行错位。

    返回 ``(ok, reason)``。
    """
    if not os.environ.get("AGRI_MCP_HTTP"):
        return True, ""
    hdr_method = os.environ.get("AGRI_MCP_HEADER_MCP_METHOD", "")
    hdr_name = os.environ.get("AGRI_MCP_HEADER_MCP_NAME", "")
    if hdr_method and hdr_method != method:
        return False, "Mcp-Method 头与 body 不一致"
    if name and hdr_name and hdr_name != name:
        return False, "Mcp-Name 头与 body 不一致"
    if method in ("tools/call",) and not hdr_name:
        return False, "缺少 Mcp-Name 头"
    return True, ""


def _audit(event: dict):
    """安全审计日志（对齐 GOAI CyberGuard 提升点3 安全审计）。

    默认写 stderr（JSON 行），绝不写 stdout（stdout 是 JSON-RPC 协议通道，
    任何写 stdout 的字节都会破坏协议）。若设 ``AGRI_MCP_AUDIT_LOG`` 环境变量，
    则追加写该路径（落盘由调用方自担；默认不落盘，避免产生未跟踪文件）。

    不记录参数明文：仅记方法/工具名 + 参数指纹 + 时间戳 + 状态。
    """
    import datetime
    event.setdefault("ts", CLOCK.now().isoformat(timespec="seconds"))
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    log_path = os.environ.get("AGRI_MCP_AUDIT_LOG")
    if log_path:
        try:
            # H1: 原子追加（读-写-替换），避免半截 JSONL 损坏
            atomic_append_jsonl(log_path, event)
        except Exception:
            sys.stderr.write("[mcp_audit] " + line + "\n")
            sys.stderr.flush()
    else:
        sys.stderr.write("[mcp_audit] " + line + "\n")
        sys.stderr.flush()


def _handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")

    # SEP-414：把调用方 W3C trace context 串进本次处理，响应原样回写。
    traceparent = _meta_traceparent(msg)
    resp_meta = {"traceparent": traceparent} if _valid_traceparent(traceparent) else {}

    if method == "initialize":
        # SEP-2575 后 initialize 已非必需；仍响应以兼容旧客户端。
        # 客户端若声明 protocolVersion，回落在共同支持的最高版本（版本协商）。
        client_ver = ""
        params = msg.get("params")
        if isinstance(params, dict):
            client_ver = params.get("protocolVersion") or ""
        negotiated = PROTOCOL_VERSION
        if client_ver and client_ver not in SUPPORTED_PROTOCOL_VERSIONS:
            negotiated = PROTOCOL_VERSION  # 未知版本按最新回，客户端自决是否继续
        elif client_ver:
            negotiated = client_ver
        result = {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            # 显式声明无状态（SEP-2567）：客户端不应期待 session header
            "stateless": True,
        }
        if resp_meta:
            result["_meta"] = resp_meta
        _audit({"event": "initialize", "client_protocol": client_ver,
                "negotiated": negotiated, "traceparent": traceparent})
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "tools/list":
        # SEP-2549：list 类响应带缓存提示，客户端可据 ttlMs 复用。
        # M13-P2 渐进式发现：支持 params.category / params.categories 按分类过滤，
        # 客户端只需加载自己关心的子集（如只装 climate 类），不必拉全 19 工具。
        # 向后兼容：不传 category / categories 时返回全量，行为与旧版一致。
        # M13-P3 ETags：返回 ETag（全量 TOOLS 内容 hash），客户端可缓存；
        # 带 params.if_none_match 或 _meta.if_none_match 命中时返回 304 等价短路。
        params = msg.get("params", {}) or {}
        etag = _tools_list_etag()
        ifn = params.get("if_none_match") or ""
        # 也支持 HTTP 形态下的 header 透传（走环境变量）
        if not ifn:
            ifn = os.environ.get("AGRI_MCP_HEADER_IF_NONE_MATCH", "")
        if isinstance(ifn, str) and ifn.strip().strip('"') == etag:
            result = {
                "not_modified": True,
                "etag": etag,
                "ttlMs": TOOLS_LIST_TTL_MS,
                "cacheScope": TOOLS_LIST_CACHE_SCOPE,
            }
            if resp_meta:
                result["_meta"] = resp_meta
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        selected = _select_tools_by_category(params)
        result = {
            "tools": selected["tools"],
            "ttlMs": TOOLS_LIST_TTL_MS,
            "cacheScope": TOOLS_LIST_CACHE_SCOPE,
            # 客户端可据此了解 server 支持哪些分类，无需先拉全量。
            "categories": selected["categories"],
            # M13-P3：稳定 ETag，客户端可缓存并带 If-None-Match 复用
            "etag": etag,
        }
        if resp_meta:
            result["_meta"] = resp_meta
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "tools/call":
        params = msg.get("params", {}) or {}
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}

        # SEP-2243：HTTP 形态下校验头部一致性（stdio 恒通过）。
        ok, reason = _http_headers_ok(method, name)
        if not ok:
            _audit({"event": "tools_call_rejected", "tool": name,
                    "reason": "header_mismatch", "detail": reason,
                    "traceparent": traceparent})
            return {
                "jsonrpc": "2.0", "id": mid,
                "error": {"code": -32600, "message": reason},
            }

        arg_hash = hashlib.sha256(
            json.dumps(arguments, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        _audit({"event": "tools_call_request", "tool": name,
                "arg_hash": arg_hash, "traceparent": traceparent})
        fn = _DISPATCH.get(name)
        if not fn:
            _audit({"event": "tools_call_rejected", "tool": name,
                    "reason": "unknown_tool", "arg_hash": arg_hash,
                    "traceparent": traceparent})
            return {
                "jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"未知工具: {name}"},
            }
        try:
            result = fn(arguments)
        except Exception as e:  # noqa: BLE001
            _audit({"event": "tools_call_error", "tool": name,
                    "arg_hash": arg_hash, "error": str(e)[:120],
                    "traceparent": traceparent})
            result = {"error": f"工具执行失败: {e}"}

        # T-1 可信标记产品化：所有工具输出内嵌紧凑 trust_mark，外部消费者可
        # 用 verification_cmd 独立复算 signature，校验数据一致性。
        # 不改动 result 顶层字段以避免破坏既有客户端契约，走 _meta 扩展字段。
        try:
            if isinstance(result, dict):
                result["_trust_mark"] = get_trust_mark()
        except Exception:  # noqa: BLE001
            # trust_mark 生成失败不应阻塞业务响应
            pass

        has_err = isinstance(result, dict) and "error" in result
        _audit({"event": "tools_call_done", "tool": name,
                "arg_hash": arg_hash, "has_error": bool(has_err),
                "traceparent": traceparent})
        payload = {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)},
            ],
        }
        if resp_meta:
            payload["_meta"] = resp_meta
        # 工具执行结果含实时/半实时数据（在线土壤、气候调和），不做长缓存；
        # 仅声明「可短时复用」，避免客户端误当季度级数据缓存。
        payload["ttlMs"] = 60000
        payload["cacheScope"] = "public"
        return {"jsonrpc": "2.0", "id": mid, "result": payload}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "notifications/initialized":
        return None  # 通知，无响应（SEP-2575 后此通知亦非必需）
    # 其他通知（无 id）忽略
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"不支持的方法: {method}"}}


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break  # EOF：客户端关闭 stdin
        # 安全护栏：拒绝超长行，防止内存耗尽型 DoS（MCP 分发通道）
        if len(line.encode("utf-8", "ignore")) > MAX_LINE_BYTES:
            _audit({"event": "request_rejected", "reason": "oversize",
                    "bytes": len(line.encode("utf-8", "ignore"))})
            _send({"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "请求过长，已拒绝"}})
            continue
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = _handle(msg)
        if resp is not None:
            _send(resp)


if __name__ == "__main__":
    main()
