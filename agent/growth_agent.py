"""
GrowthAgent - 生长周期管理 + 病虫害诊断

职责：
  1. 接收已选定作物 + 分区数据 + 微气候约束
  2. 基于 crop_adapt_db.json 的真实生长周期生成种植计划（播种→苗期→生长→采收）
  3. 结合分区温度约束与作物 key_risks 生成阶段化风险预警
  4. 视觉/文本输入诊断病虫害（当前用症状关键词 + 作物风险知识库做轻量诊断）
  5. 输出农事指令 + 兜底救活方案（fallback_variety）

对标 SwarmLabs：相当于 VerifierAgent + active_learning Skill
数据来源：data/crop_adapt_db.json（FAO CropInfo + 中国农艺通识）
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

# 症状关键词 → 诊断 + 处置（通用轻量知识库，覆盖家庭/阳台种植高频问题）
SYMPTOM_RISK_MAP = {
    "蚜虫": ("蚜虫危害（轻度）", ["黄板诱杀", "肥皂水喷洒", "吡虫啉（按说明稀释）"]),
    "白粉": ("白粉病", ["增通风降湿", "摘除病叶", "喷施硫磺/醚菌酯"]),
    "霜霉": ("霜霉病", ["降湿控水", "摘除病叶", "烯酰吗啉喷雾"]),
    "炭疽": ("炭疽病", ["控湿", "清除病残体", "咪鲜胺喷雾"]),
    "病毒": ("病毒病", ["灭蚜防传播", "拔除重病株", "无病苗替换"]),
    "抽苔": ("高温/长日照诱导抽苔", ["遮阳降温", "及时采收", "改种晚抽苔品种"]),
    "徒长": ("光照不足徒长", ["补光", "间苗稀植", "控氮"]),
    "黄叶": ("缺素/渍水黄化", ["查湿度计防烂根", "补施均衡肥", "排涝"]),
    "烂根": ("浇水过多烂根", ["控水松土", "换疏松基质", "剪腐根重栽"]),
    "日灼": ("强光日灼", ["午后遮阳", "叶面喷水降温"]),
    "虫": ("食叶害虫（菜青虫/跳甲/螟）", ["人工捉虫", "黄板诱杀", "苏云金杆菌 Bt 喷雾"]),
    "锈": ("锈病", ["控湿", "摘除病叶", "三唑酮喷雾"]),
    "青枯": ("青枯病（细菌性）", ["拔除病株", "嫁接抗病砧木", "轮作"]),
    "线虫": ("根结线虫", ["太阳能消毒土壤", "种抗病品种", "淡紫拟青霉"]),
}


def _load_crop_db(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"meta": {}, "zones": {}}


def _find_crop(zones: Dict[str, Any], zone_id: str, crop_name: str) -> Optional[Dict[str, Any]]:
    """在指定分区内查找作物；找不到则在全库按名称查找（兜底）。"""
    zone_meta = zones.get(zone_id)
    if zone_meta:
        for c in zone_meta.get("crops", []):
            if c.get("crop") == crop_name:
                return c
    for zid, zm in zones.items():
        for c in zm.get("crops", []):
            if c.get("crop") == crop_name:
                return c
    return None


def _build_phases(growth_days: int, crop: Dict[str, Any]) -> List[Dict[str, Any]]:
    gd = max(int(growth_days), 20)
    sow_end = max(7, round(gd * 0.15))
    seedling_end = max(sow_end + 7, round(gd * 0.40))
    preharvest = max(seedling_end + 7, round(gd * 0.85))

    water = crop.get("water_ml_day", 150)
    ph = crop.get("ph_range", [6.0, 7.0])
    temp = crop.get("temp_range_c", [10, 30])

    phases = [
        {
            "phase": "播种育苗",
            "day_range": [1, sow_end],
            "actions": [
                f"育苗基质湿润后播种，覆土 {round(gd/200, 1)} cm，保持 18-25℃",
                f"出苗前保持基质湿润（约 {max(20, water//5)} ml/天），忌积水",
            ],
            "tasks": ["浸种/催芽（可选）", "覆膜保湿", "出苗后揭膜见光"],
        },
        {
            "phase": "苗期管理",
            "day_range": [sow_end + 1, seedling_end],
            "actions": [
                f"间苗/定苗，株距按品种，保证通风",
                f"见干见湿浇水，约 {water} ml/天；基质 pH 维持 {ph[0]}-{ph[1]}",
                f"适温 {temp[0]}-{temp[1]}℃，超界需遮阳/保温",
            ],
            "tasks": ["追施稀薄氮肥 1 次", "预防猝倒病（控湿通风）"],
        },
        {
            "phase": "生长管理",
            "day_range": [seedling_end + 1, preharvest],
            "actions": [
                f"旺盛生长期水肥加倍，约 {water} ml/天 + 均衡水溶肥每周 1 次",
                "观察叶色/虫斑，发现病虫害按诊断处置",
                "攀援/高大作物及时绑蔓支架",
            ],
            "tasks": ["整枝/打杈（茄果类）", "挂黄板防虫", "记录生长数据（回流平台）"],
        },
        {
            "phase": "成熟采收",
            "day_range": [preharvest + 1, gd],
            "actions": [
                "按品种采收标准分批采收，采后即时食用/冷藏",
                "叶菜可留茬再生，多次采收",
            ],
            "tasks": ["首次采收", "清理残株/轮作规划"],
        },
    ]
    return phases


class GrowthAgent:
    """生长周期管理 + 病虫害诊断 Agent"""

    NAME = "GrowthAgent"
    VERSION = "1.2"

    def __init__(self, crop_db_path: str = DEFAULT_CROP_DB):
        self.crop_db_path = crop_db_path
        self._db = _load_crop_db(self.crop_db_path)
        self._zones = self._db.get("zones", {})
        self._db_version = self._db.get("meta", {}).get("version", "1.0")
        self._db_sources = self._db.get("meta", {}).get("data_sources", [])

    def generate_growth_plan(
        self,
        crop: str,
        zone_data: Dict[str, Any],
        start_date: str = "",
        scene: str = "balcony",
        microclimate: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """生成基于真实作物数据的种植计划。"""
        zone_id = zone_data.get("evidence", {}).get("zone_id", "")
        crop_info = _find_crop(self._zones, zone_id, crop)

        if not crop_info:
            return {
                "evidence": {"crop": crop, "zone_id": zone_id, "plan_version": "1.2",
                             "data_loaded": False},
                "confidence": {"rubric_score": 0.0, "coverage_pct": 0.0,
                               "confidence_note": f"未找到作物 {crop} 的种植数据"},
                "constraints": {},
                "recommendation": {"phases": [], "key_events": [], "risk_alerts": [],
                                   "rescue_plan": ""},
            }

        gd = crop_info.get("growth_days", 45)
        phases = _build_phases(gd, crop_info)
        risks = crop_info.get("key_risks", [])
        fallback = crop_info.get("fallback_variety", "")
        temp_crop = crop_info.get("temp_range_c", [10, 30])

        # 区温度约束 → 风险预警
        zone_constraints = zone_data.get("constraints", {})
        zone_max = zone_constraints.get("max_temp_c")
        zone_min = zone_constraints.get("min_temp_c")
        risk_alerts = []
        if zone_max is not None and zone_max > temp_crop[1]:
            risk_alerts.append(
                f"分区夏季高温 {zone_max}℃ 超过 {crop} 适温上限 {temp_crop[1]}℃，"
                f"需遮阳网/改种耐热兜底品种（{fallback}）"
            )
        if zone_min is not None and zone_min < temp_crop[0]:
            risk_alerts.append(
                f"分区冬季低温 {zone_min}℃ 低于 {crop} 适温下限 {temp_crop[0]}℃，"
                f"需保温棚/移入室内"
            )
        # 作物自身关键风险（取前 2 条作为阶段提醒）
        for r in risks[:2]:
            risk_alerts.append(f"{crop} 易发：{r}（苗期/生长期重点预防）")

        # 微气候修正（如有）
        micro_note = ""
        if microclimate:
            off = microclimate.get("effective_temp_offset")
            if off is not None:
                micro_note = (
                    f"微气候修正：有效温度偏移 {off}℃；"
                    f"{microclimate.get('micro_climate_note', '')}"
                )

        key_events = [f"出苗/定植：约 D{phases[0]['day_range'][1]}"]
        if gd > 40:
            key_events.append(f"移栽/间苗时机：约 D{round(gd*0.12)}")
        key_events.append(f"首次采收：约 D{gd}")

        rescue_plan = (
            f"若遭遇「{risks[0]}」等主要症状，立即执行对应处置并改用兜底品种"
            f"「{fallback}」重播；叶菜可缩短周期抢收避害。"
            if risks else "保持基质疏松、控水控湿，发现异常及时隔离病株。"
        )

        rubric_score = 0.82  # 数据齐备基线
        coverage = 1.0 if crop_info.get("growth_days") else 0.5

        return {
            "evidence": {
                "crop": crop,
                "latin": crop_info.get("latin"),
                "zone_id": zone_id,
                "plan_version": "1.2",
                "data_loaded": True,
                "data_sources": self._db_sources,
                "crop_db_version": self._db_version,
            },
            "confidence": {
                "rubric_score": round(rubric_score, 2),
                "coverage_pct": coverage,
                "confidence_note": f"基于 {crop} 真实生长周期 D{gd} 生成四阶段计划",
            },
            "constraints": {
                "expected_days": gd,
                "tolerance_days": max(5, round(gd * 0.15)),
                "temp_range_c": temp_crop,
                "ph_range": crop_info.get("ph_range"),
                "water_ml_day": crop_info.get("water_ml_day"),
            },
            "recommendation": {
                "phases": phases,
                "key_events": key_events,
                "risk_alerts": risk_alerts,
                "rescue_plan": rescue_plan,
                "microclimate_note": micro_note,
            },
        }

    def diagnose(
        self,
        crop: str,
        symptom_description: str = "",
        image_reference: str = "",
        growth_stage: str = "",
        environment: Dict[str, Any] = {},
    ) -> Dict[str, Any]:
        """病虫害/营养缺乏诊断（轻量：症状关键词 + 作物风险知识库）。"""
        sym = symptom_description or ""
        matched = []
        for kw, (diag, acts) in SYMPTOM_RISK_MAP.items():
            if kw in sym:
                matched.append((kw, diag, acts))

        # 作物自身风险作为候选鉴别诊断
        crop_info = None
        for zid, zm in self._zones.items():
            for c in zm.get("crops", []):
                if c.get("crop") == crop:
                    crop_info = c
                    break
            if crop_info:
                break
        alt = crop_info.get("key_risks", []) if crop_info else []

        if matched:
            kw, diag, acts = matched[0]
            return {
                "evidence": {"symptom": sym, "diagnosis_source": "symptom_kb+crop_risk",
                             "match_keyword": kw},
                "confidence": {"diagnosis_confidence": 0.7, "alternatives": len(alt)},
                "constraints": {"applicability": f"{crop}（{growth_stage or '全期'}）"},
                "recommendation": {
                    "diagnosis": diag,
                    "severity": "light",
                    "actions": acts,
                    "alternative_diagnoses": alt[:3],
                },
            }

        return {
            "evidence": {"symptom": sym, "diagnosis_source": "crop_risk_only"},
            "confidence": {"diagnosis_confidence": 0.4, "alternatives": len(alt)},
            "constraints": {"applicability": f"{crop}（症状未命中关键词库）"},
            "recommendation": {
                "diagnosis": "无法确定，建议补充照片/描述（叶色、斑型、发生部位）",
                "severity": "unknown",
                "actions": ["拍照记录症状", "隔离疑似病株", "控水控湿观察"],
                "alternative_diagnoses": alt[:3],
            },
        }
