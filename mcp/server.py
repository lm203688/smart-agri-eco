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
"""
from __future__ import annotations

import json
import os
import sys
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.preset_cities import load_preset_cities  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
# 兼容声明的历史版本：新客户端取 PROTOCOL_VERSION，旧客户端接受以下任一。
SUPPORTED_PROTOCOL_VERSIONS = ("2026-07-28", "2025-06-18", "2024-11-05")
SERVER_NAME = "agri-eco"
SERVER_VERSION = "1.1.0"

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
    return {"cities": _PRESET_CITIES}


def _tool_match_zone(args: dict) -> dict:
    try:
        lat = float(args["lat"])
        lon = float(args["lon"])
    except (KeyError, TypeError, ValueError):
        return {"error": "需要数值 lat/lon"}
    if not (-90.0 <= lat <= 90.0):
        return {"error": f"lat 超出合法范围 [-90, 90]，收到 {lat}"}
    if not (-180.0 <= lon <= 180.0):
        return {"error": f"lon 超出合法范围 [-180, 180]，收到 {lon}"}
    return _orch().climate.match_zone(lat, lon)


def _tool_recommend_crops(args: dict) -> dict:
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
    return _orch().pest.run({
        "crop": args.get("crop", ""),
        "symptom_description": args.get("symptom_description", ""),
        "image_reference": args.get("image_reference", ""),
        "growth_stage": args.get("growth_stage", ""),
        "environment": args.get("environment"),
    })


def _tool_nutrition_plan(args: dict) -> dict:
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
    from core.geo_recipe import resolve
    query = args.get("query")
    lat = args.get("lat")
    lon = args.get("lon")
    return resolve(query=query, lat=lat, lon=lon)


def _tool_query_lineage(args: dict) -> dict:
    """数据血缘查询：按作物/分区查配方的数据溯源（外部 API 参与 + 本地文件指纹 + 校准实证）。
    对齐 GOAI DataFlow-Agent 提升点3 + 壁垒④。"""
    from core.data_lineage import query_lineage
    crop = args.get("crop")
    zone = args.get("zone_id")
    return query_lineage(crop=crop or None, zone_id=zone or None)


def _tool_list_ecosystem(args: dict) -> dict:
    """生态对接清单：返回 config/ecosystem.json 声明的开源/商业生态清单。
    声明对接状态（integrated/partial/planned_mapping/evaluating/competitor_reference/not_evaluated），
    让 MCP 客户端知道我们的开放生态策略与差异化定位。"""
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
        "description": "列出预设城市（经纬度 + 气候带），供 Agent 选点或核对分区。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "agri_match_zone",
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
]

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
}


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
    event.setdefault("ts", datetime.datetime.now().isoformat(timespec="seconds"))
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    log_path = os.environ.get("AGRI_MCP_AUDIT_LOG")
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
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
        result = {
            "tools": TOOLS,
            "ttlMs": TOOLS_LIST_TTL_MS,
            "cacheScope": TOOLS_LIST_CACHE_SCOPE,
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
