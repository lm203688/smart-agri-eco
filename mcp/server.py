#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp/server.py —— 智慧农业生态 · 零依赖 MCP Server（Agent-native 分发层）

实现方式：标准库 JSON-RPC 2.0 over stdio（不依赖 mcp SDK / 任何第三方包），
与本项目「零依赖」理念一致，也契合评审「MCP 成本极低、是最强差异化赌注」的判断。

协议版本：2024-11-05（initialize 返回此 protocolVersion，兼容 Claude Desktop / 各类 MCP 客户端）

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent import AgriOrchestrator  # noqa: E402
from agent.preset_cities import load_preset_cities  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agri-eco"
SERVER_VERSION = "1.0.0"

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
    lat = float(args.get("lat", 0))
    lon = float(args.get("lon", 0))
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
}


# ---------- JSON-RPC 传输层 ----------

def _send(obj: dict):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {"tools": TOOLS},
        }
    if method == "tools/call":
        params = msg.get("params", {}) or {}
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        fn = _DISPATCH.get(name)
        if not fn:
            return {
                "jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"未知工具: {name}"},
            }
        try:
            result = fn(arguments)
        except Exception as e:  # noqa: BLE001
            result = {"error": f"工具执行失败: {e}"}
        return {
            "jsonrpc": "2.0", "id": mid,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)},
                ],
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "notifications/initialized":
        return None  # 通知，无响应
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
