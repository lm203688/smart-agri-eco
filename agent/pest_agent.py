"""PestAgent - 病虫害与营养缺乏诊断（数据驱动 + 可插拔视觉后端）。

设计原则（与项目其他 Agent 一致）：
- 纯 Python 标准库，零第三方依赖。
- 数据驱动：优先用 ``data/crop_adapt_db.json`` 中每作物的 ``key_risks``（已知病虫害清单）
  作为候选集，再结合内置病虫害知识库做症状匹配。
- 可插拔视觉后端：若设置环境变量 ``AGRI_VISION_URL`` / ``AGRI_VISION_KEY`` / ``AGRI_VISION_MODEL``，
  且请求带 ``image_reference``，则调用 OpenAI 兼容的视觉对话接口辅助诊断；
  未配置时纯规则降级，保证离线可用。
- 输出遵循 docs/agent_output_contract.md（evidence / confidence / constraints / recommendation），
  并附 ``signature``（内容 sha256）以满足 AgriTrust 可复现要求。
- 安全边界：不替代专业植保人员；疑似检疫性病虫害必须上报。

输入:
    crop (str): 作物名（与 crop_adapt_db 的 ``crop`` 字段匹配，允许别名/部分匹配）
    symptom_description (str, optional): 用户描述的症状
    image_reference (str, optional): 图像 data URI 或 URL（需配置视觉后端才使用）
    growth_stage (str, optional): 生长阶段（如 苗期/花期/结果期）
    environment (dict, optional): 环境信息（温湿度等，可选）

输出:
    {
      "diagnosis": str,
      "severity": "light"|"medium"|"severe",
      "actions": [str,...],
      "alternative_diagnoses": [str,...],
      "diagnosis_confidence": float,
      "matched_risks": [str,...],
      "knowledge_source": "rule_based"|"vision_assisted",
      "evidence": {...},
      "confidence": {"rubric_score": float, "match_quality": float},
      "constraints": [str,...],
      "recommendation": str,
      "signature": str,
    }
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from .vision import call_vision_backend as _call_vision

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DATA = os.path.join(PROJECT_ROOT, "data")
CROP_DB_PATH = os.path.join(DATA, "crop_adapt_db.json")

# 安全边界（每次诊断都携带）
SAFETY_CONSTRAINTS = [
    "本诊断不替代专业植保人员现场判断；大面积/快速蔓延时请线下送检。",
    "疑似检疫性病虫害（如柑橘黄龙病、番茄溃疡病、小麦条锈病等）须立即上报当地植保站。",
    "任何药剂严格按标签剂量与采前安全间隔期使用；优先物理/生物防治。",
]

# 症状信号词 -> 类别（用于无直接命中时按症状归类）
SYMPTOM_SIGNALS = {
    "pest": ["虫", "蚜", "螨", "蓟马", "介壳", "潜叶", "蛀", "孔", "网", "蜜露", "虫粪", "啃食", "咬"],
    "disease": ["病", "斑", "霉", "粉", "锈", "腐", "枯", "萎", "疫", "炭疽", "溃疡", "疮", "菌", "烂"],
    "nutrient": ["缺", "黄化", "黄叶", "叶黄", "紫", "白化", "边缘焦", "老叶", "新叶"],
    "abiotic": ["灼", "冻", "寒", "涝", "淹", "旱", "盐", "药害", "日烧"],
}

SEVERITY_WORDS = {
    "severe": ["严重", "大面积", "蔓延", "枯萎", "死", "腐烂", "枯死"],
    "medium": ["较多", "明显", "部分", "加重"],
    "light": ["少量", "个别", "刚", "初期", "零星"],
}


# ---------------------------------------------------------------------------
# 内置病虫害知识库（key_risks 命中的具体条目；其余按类别走通用模板）
# 每条: category, symptoms(关键词), actions(处置), prevention(预防), sev(默认严重度)
# ---------------------------------------------------------------------------
KB: Dict[str, Dict[str, Any]] = {
    "蚜虫": {"category": "pest", "symptoms": ["蜜露", "卷叶", "嫩梢", "黄化", "蚂蚁"],
             "actions": ["用高压水冲洗或黄板诱杀", "喷施苦参碱/吡虫啉（按标签）", "保护瓢虫/草蛉等天敌"],
             "prevention": ["合理密植通风", "清除杂草寄主", "定期巡查嫩梢"], "sev": "light"},
    "红蜘蛛": {"category": "pest", "symptoms": ["网", "白点", "叶背", "失绿", "干枯"],
               "actions": ["增加空气湿度", "喷施阿维菌素/螺螨酯（按标签）", "叶背重点喷雾"],
               "prevention": ["避免长期干旱", "不偏施氮肥", "天敌（捕食螨）释放"], "sev": "medium"},
    "白粉病": {"category": "disease", "symptoms": ["白粉", "粉状", "叶背", "嫩叶"],
               "actions": ["及时剪除病叶", "喷施硫磺/醚菌酯（按标签）", "降低湿度、增强通风"],
               "prevention": ["避免密植", "避免傍晚叶面浇水", "选用抗病品种"], "sev": "medium"},
    "霜霉病": {"category": "disease", "symptoms": ["霜", "霉层", "叶背", "黄斑", "水渍"],
               "actions": ["立即摘除病叶", "喷施烯酰吗啉/甲霜灵（按标签）", "雨后及时排水"],
               "prevention": ["高畦栽培", "控制湿度", "轮作"], "sev": "medium"},
    "叶斑病": {"category": "disease", "symptoms": ["斑", "斑点", "褐", "黑点", "穿孔"],
               "actions": ["清除病残体", "喷施苯醚甲环唑/代森锰锌（按标签）", "避免叶面长期湿润"],
               "prevention": ["合理轮作", "避免连作", "种子/种苗消毒"], "sev": "light"},
    "根腐病": {"category": "disease", "symptoms": ["根腐", "腐烂", "萎蔫", "黄", "涝"],
               "actions": ["停水控湿", "拔除重病株", "灌根恶霉灵/噁霉灵（按标签）", "改善排水"],
               "prevention": ["杜绝积水", "基质消毒", "嫁接抗病砧木"], "sev": "severe"},
    "炭疽病": {"category": "disease", "symptoms": ["炭疽", "凹陷", "褐", "轮纹", "果"],
               "actions": ["清除病果病叶", "喷施咪鲜胺/苯醚甲环唑（按标签）"],
               "prevention": ["采后伤口管理", "通风降湿", "轮作"], "sev": "medium"},
    "锈病": {"category": "disease", "symptoms": ["锈", "疱", "橙黄", "粉"],
             "actions": ["清除病叶", "喷施三唑酮/戊唑醇（按标签）"],
             "prevention": ["避免密植", "抗病品种", "轮作"], "sev": "medium"},
    "病毒病": {"category": "disease", "symptoms": ["花叶", "畸形", "黄绿", "皱缩", "矮化"],
               "actions": ["拔除病株销毁", "防治蚜虫/蓟马等传毒媒介", "工具消毒"],
               "prevention": ["选用脱毒种苗", "及时控虫", "避免机械传毒"], "sev": "severe"},
    "介壳虫": {"category": "pest", "symptoms": ["介壳", "蜡质", "枝干", "蜜露", "黑霉"],
               "actions": ["人工刮除", "喷施噻嗪酮/螺虫乙酯（按标签）", "保护寄生蜂"],
               "prevention": ["引种检疫", "定期巡查枝干", "合理修剪"], "sev": "light"},
    "蓟马": {"category": "pest", "symptoms": ["蓟马", "银斑", "畸形", "花", "褐"],
             "actions": ["蓝板诱杀", "喷施乙基多杀菌素/吡虫啉（按标签）", "避免干旱"],
             "prevention": ["清除杂草", "覆膜", "花期重点防控"], "sev": "light"},
    "潜叶蝇": {"category": "pest", "symptoms": ["潜叶", "蛇形", "白斑", "叶"],
               "actions": ["摘除虫叶", "黄板诱杀", "喷施阿维菌素（按标签）"],
               "prevention": ["轮作", "清除老叶", "田园清洁"], "sev": "light"},
    "茎象鼻虫": {"category": "pest", "symptoms": ["象鼻", "蛀", "茎", "假茎", "枯"],
                 "actions": ["清除虫蛀假茎", "喷施噻虫嗪（按标签）", "清理假茎"],
                 "prevention": ["种苗检疫", "残株清理", "冬季清园"], "sev": "medium"},
    "菜青虫": {"category": "pest", "symptoms": ["青虫", "啃食", "孔", "叶"],
               "actions": ["人工捉除", "BT 苏云金杆菌/甲维盐（按标签）", "保护寄生蜂"],
               "prevention": ["防虫网", "轮作", "间作驱虫植物"], "sev": "light"},
    "小菜蛾": {"category": "pest", "symptoms": ["小菜蛾", "啃食", "孔", "叶"],
               "actions": ["BT/甲维盐（按标签）", "性诱剂", "清理残株"],
               "prevention": ["轮作", "防虫网", "避免连作"], "sev": "light"},
    "根结线虫": {"category": "pest", "symptoms": ["根结", "瘤", "根", "萎", "矮"],
                 "actions": ["轮作非寄主", "淡紫拟青霉/阿维菌素灌根（按标签）", "增施有机肥"],
                 "prevention": ["无病土育苗", "太阳能消毒", "抗病砧木"], "sev": "medium"},
    "灰霉病": {"category": "disease", "symptoms": ["灰霉", "灰毛", "腐", "花", "果"],
               "actions": ["清除病花病果", "降湿通风", "喷施腐霉利/异菌脲（按标签）"],
               "prevention": ["避免密植", "控制湿度", "及时摘除残花"], "sev": "medium"},
    "黄龙病": {"category": "disease", "symptoms": ["黄龙", "斑驳", "红鼻果", "柑橘"],
               "actions": ["立即挖除病树销毁", "全园统防木虱", "上报当地植保站（检疫性病）"],
               "prevention": ["种植无病苗", "严格防木虱", "新区检疫"], "sev": "severe"},
    "缺氮": {"category": "nutrient", "symptoms": ["缺氮", "老叶黄", "黄化", "矮小"],
             "actions": ["追施速效氮肥（尿素/硝态氮）", "叶面喷尿素 0.3%"],
             "prevention": ["基施有机肥", "均衡施肥"], "sev": "light"},
    "缺铁": {"category": "nutrient", "symptoms": ["缺铁", "新叶黄", "叶脉绿", "白化"],
             "actions": ["喷施螯合铁（EDDHA-Fe）", "调酸改土"],
             "prevention": ["避免碱土积水", "补充有机质"], "sev": "light"},
    "缺钾": {"category": "nutrient", "symptoms": ["缺钾", "叶缘焦", "老叶", "紫"],
             "actions": ["追施硫酸钾/氯化钾", "叶面喷磷酸二氢钾"],
             "prevention": ["基施钾肥", "采果后补钾"], "sev": "light"},
    "日灼": {"category": "abiotic", "symptoms": ["日灼", "日烧", "白斑", "焦"],
             "actions": ["遮阴降温", "果实套袋/涂白", "叶面喷水"],
             "prevention": ["合理修剪留枝", "高温季遮阴"], "sev": "light"},
    "涝害": {"category": "abiotic", "symptoms": ["涝", "淹", "根腐", "黄", "萎"],
             "actions": ["及时排水", "中耕松土", "病害预防（根腐/疫霉）"],
             "prevention": ["高畦/垄作", "完善排水", "控制浇水"], "sev": "medium"},
}

# 类别通用处置模板（当 key_risks 命中但 KB 无具体条目时使用）
CATEGORY_GENERIC = {
    "pest": {"actions": ["物理清除/诱杀（色板、人工）", "优先生物/植物源药剂（按标签）",
                        "保护天敌，减少广谱农药"], "prevention": ["田园清洁", "合理密植通风", "定期巡查"]},
    "disease": {"actions": ["立即清除病残体", "改善通风降湿", "对症杀菌剂（按标签）"],
                "prevention": ["轮作/无病种苗", "避免叶面长期湿润", "抗病品种"]},
    "nutrient": {"actions": ["叶面追肥快速矫正", "土壤检测后平衡施肥"],
                 "prevention": ["基施有机肥+缓释肥", "定期营养诊断"]},
    "abiotic": {"actions": ["改善栽培环境（遮阴/排水/调温）", "增强植株抗性"],
                "prevention": ["选择适宜季节与场景", "环境调控设备"]},
}


def _load_crop_db() -> Dict[str, Any]:
    try:
        if os.path.exists(CROP_DB_PATH):
            with open(CROP_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}
    return {}


def _find_risks_for_crop(crop: str) -> List[str]:
    """在 crop_adapt_db 中按作物名（部分/别名）查找 key_risks。"""
    db = _load_crop_db()
    zones = db.get("zones", {})
    crop_l = (crop or "").strip().lower()
    if not crop_l:
        return []
    for zid, zd in zones.items():
        for c in zd.get("crops", []):
            name = (c.get("crop") or "").strip().lower()
            if not name:
                continue
            # 精确匹配优先
            if name == crop_l:
                return list(c.get("key_risks", []))
            # 弱包含匹配要求双方均 >=2 字，避免单字名（茄/菜/瓜）误命中
            if (len(name) >= 2 and len(crop_l) >= 2) and (crop_l in name or name in crop_l):
                return list(c.get("key_risks", []))
    aliases = {
        "香蕉": "蕉", "番茄": "西红柿", "西红柿": "番茄", "玉米": "玉蜀黍",
        "马铃薯": "土豆", "土豆": "马铃薯", "辣椒": "椒", "柑橘": "柑桔",
    }
    alt = aliases.get(crop_l)
    if alt:
        for zid, zd in zones.items():
            for c in zd.get("crops", []):
                name = (c.get("crop") or "").strip().lower()
                if name and (alt in name or name in alt):
                    return list(c.get("key_risks", []))
    return []


def _category_of(risk_name: str) -> str:
    n = risk_name
    if "虫" in n or "螨" in n or "蝇" in n or "蛾" in n or "蝶" in n or "甲" in n or "虱" in n or "蚊" in n or "蛛" in n or "蜱" in n or "蝽" in n or "蚧" in n:
        return "pest"
    if "病" in n or "霉" in n or "锈" in n or "腐" in n or "枯" in n or "疫" in n or "炭疽" in n or "溃疡" in n or "疮" in n or "菌" in n or "斑" in n:
        return "disease"
    if "缺" in n:
        return "nutrient"
    if "灼" in n or "冻" in n or "寒" in n or "涝" in n or "旱" in n or "盐" in n or "药害" in n:
        return "abiotic"
    return "disease"


def _detect_signals(text: str) -> Dict[str, int]:
    counts = {k: 0 for k in SYMPTOM_SIGNALS}
    for cat, words in SYMPTOM_SIGNALS.items():
        for w in words:
            if w in text:
                counts[cat] += 1
    return counts


def _severity_from_text(text: str, default: str) -> str:
    for sev, words in SEVERITY_WORDS.items():
        if any(w in text for w in words):
            return sev
    return default


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# 证据门控（借鉴 Shannon 渗透测试「打不通就不报」的零误报策略）
#
# 原则：仅当症状命中具体知识库条目 且 至少一路独立证据（视觉确认 / 环境观测）
# 同时满足时，才给出「确认」诊断结论；否则标注 unconfirmed，只给监测建议，
# 不下确定性结论。宁可少报，不误报——农业处置（用药/拔株/上报检疫）成本高。
#
# 三要素均为可机读判定，不依赖主观打分：
#   symptom_hit        症状文本命中 KB 具体条目（top score >= _HIT_MIN）
#   visual_confirm     视觉后端返回了有效补充（knowledge_source == vision_assisted）
#   environment_observed  调用方提供了 >= 2 项有效环境观测值
# ---------------------------------------------------------------------------
_HIT_MIN = 0.45                      # 命中阈值：低于此值视为「模糊归类」不算命中
_ENV_KEYS = ("humidity", "humidity_pct", "temp", "temperature", "temp_c",
             "ppfd", "light", "ec", "ph", "wind")


def _environment_observed(environment: Optional[Dict[str, Any]]) -> bool:
    """环境是否被真实观测：>= 2 项有效数值。缺项不计入。"""
    if not isinstance(environment, dict):
        return False
    hit = 0
    for k, v in environment.items():
        if k not in _ENV_KEYS:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and v == v:      # 排除 NaN
            hit += 1
    return hit >= 2


def _evidence_gate(sym: str, scored, primary: Optional[str],
                   knowledge_source: str,
                   environment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """产出零误报门控判定。返回 status + 三要素明细 + 缺失项。"""
    top_score = scored[0][0] if scored else 0.0
    symptom_hit = bool(sym) and top_score >= _HIT_MIN and bool(primary)
    visual_confirm = (knowledge_source == "vision_assisted")
    env_observed = _environment_observed(environment)

    status = "confirmed" if (symptom_hit and (visual_confirm or env_observed)) else "unconfirmed"
    missing: List[str] = []
    if not symptom_hit:
        missing.append("症状未命中知识库具体条目（或无症状输入）")
    if not (visual_confirm or env_observed):
        missing.append("缺少独立佐证（视觉确认 / 环境观测二选一）")
    return {
        "status": status,
        "symptom_hit": symptom_hit,
        "top_score": round(top_score, 3),
        "hit_min": _HIT_MIN,
        "visual_confirm": visual_confirm,
        "environment_observed": env_observed,
        "missing": missing,
        "policy": "Shannon 零误报：打不通就不报——无双重证据不下确定性结论",
    }


# ---------------------------------------------------------------------------
# 三阶段解释链（借鉴 AIMe 的 预测 → 解释 → 映射 多智能体范式）
#
# 只有结论没有推理链，用户既无法验证也无法复盘。这里把每次诊断拆成三段：
#   prediction  预测   —— 首选诊断是什么、置信度、备选、严重度
#   explanation 解释   —— 为什么：症状词逐条命中明细、类别信号、环境支持度、
#                          视觉补充、以及零误报策略如何裁决
#   mapping     映射   —— 映射到哪个已知模式（KB 条目 / 类别通用模板）、
#                          候选集、成长阶段、门控状态
# 三段全部由 diagnose() 内部真实计算结果派生，不引入新的判定口径，
# 因此不会与零误报证据门控冲突（门控仍是唯一裁决者）。
# ---------------------------------------------------------------------------
def _build_reasoning_chain(prediction: Dict[str, Any],
                           explanation: Dict[str, Any],
                           mapping: Dict[str, Any]) -> Dict[str, Any]:
    """组装三阶段解释链，并生成一句人可读的因果叙述。"""
    primary = prediction.get("primary")
    ev = (explanation.get("symptom_matches") or {}).get(primary, {}) if primary else {}
    gate_status = mapping.get("gate_status", "")
    kws = ev.get("symptom_keywords") or []
    env_keys = (explanation.get("environment") or {}).get("observed_keys") or []

    parts: List[str] = []
    if ev.get("name_hit"):
        parts.append("症状文本直接点名「%s」" % primary)
    elif ev.get("name_fragment"):
        parts.append("症状与名称共享片段「%s」" % ev["name_fragment"])
    if kws:
        parts.append("命中知识库症状词：%s" % "、".join(kws))
    sig = explanation.get("signal_counts") or {}
    top_sig = max(sig, key=lambda k: sig[k]) if any(sig.values()) else None
    if top_sig:
        parts.append("类别信号以「%s」为主" % top_sig)
    if env_keys:
        parts.append("环境观测到 %s（%d 项）" % ("、".join(env_keys[:4]), len(env_keys)))
    if explanation.get("vision_note"):
        parts.append("视觉模型参与补充")
    if not parts:
        parts.append("无有效症状信号")

    if gate_status == "confirmed":
        verdict = "证据充分，按零误报策略下确定结论"
    else:
        verdict = "证据不足，按零误报策略标注未确认（宁少报不误报）"

    return {
        "prediction": prediction,
        "explanation": explanation,
        "mapping": mapping,
        "narrative": "因为 " + "；".join(parts) + "，所以 " + verdict + "。",
    }


def diagnose(
    crop: str = "",
    symptom_description: str = "",
    image_reference: str = "",
    growth_stage: str = "",
    environment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """执行一次病虫害诊断。详见模块 docstring。"""
    sym = (symptom_description or "").strip()
    risks = _find_risks_for_crop(crop)
    signals = _detect_signals(sym) if sym else {}
    has_image = bool(image_reference)

    vision_note = None
    knowledge_source = "rule_based"
    if has_image:
        vision = _call_vision(image_reference, crop, sym)
        if vision:
            vision_note = vision
            knowledge_source = "vision_assisted"

    # 候选集 = 作物已知清单 + 症状中直接点名的 KB 病害（即使不在该作物清单）
    candidates = list(risks)
    if sym:
        for kb_name in KB:
            if kb_name in sym and kb_name not in candidates:
                candidates.append(kb_name)

    scored = []
    # 每个候选的命中证据（用于三阶段解释链的 explanation / mapping）
    evidence_by_risk: Dict[str, Dict[str, Any]] = {}
    for r in candidates:
        score = 0.0
        rcat = _category_of(r)
        kb = KB.get(r)
        ev: Dict[str, Any] = {"name_hit": False, "name_fragment": None,
                              "symptom_keywords": [], "signal_score": 0.0}
        if sym:
            if r in sym:
                score += 0.5
                ev["name_hit"] = True
            else:
                # 名称与症状共享 2 字片段 → 相关（如「黄化曲叶病毒」命中「黄化」）
                for i in range(len(r) - 1):
                    if r[i:i + 2] in sym:
                        score += 0.3
                        ev["name_fragment"] = r[i:i + 2]
                        break
            if kb:
                for kw in kb.get("symptoms", []):
                    if kw in sym:
                        score += 0.15
                        ev["symptom_keywords"].append(kw)
            if signals.get(rcat, 0) > 0:
                ev["signal_score"] = round(0.2 * signals[rcat], 3)
                score += ev["signal_score"]
        else:
            score = 0.1
        evidence_by_risk[r] = ev
        scored.append((score, r, rcat, kb))

    scored.sort(key=lambda x: x[0], reverse=True)

    primary = None
    severity = "light"
    actions: List[str] = []
    prevention: List[str] = []
    alternatives: List[str] = []

    if sym and scored and scored[0][0] >= 0.3:
        primary = scored[0][1]
        cat = scored[0][2]
        kb = scored[0][3]
        severity = _severity_from_text(sym, kb.get("sev", "light") if kb else "light")
        if kb:
            actions = list(kb.get("actions", []))
            prevention = list(kb.get("prevention", []))
        else:
            gen = CATEGORY_GENERIC.get(cat, CATEGORY_GENERIC["disease"])
            actions = list(gen["actions"])
            prevention = list(gen["prevention"])
        alternatives = [r for (_, r, _, _) in scored[1:3] if r != primary]
        diagnosis = "疑似【%s】（%s）" % (primary, _cat_cn(cat))
    elif sym and scored:
        dom = max(signals, key=lambda k: signals[k]) if any(signals.values()) else "disease"
        cat = dom if dom in CATEGORY_GENERIC else "disease"
        gen = CATEGORY_GENERIC[cat]
        severity = _severity_from_text(sym, "medium")
        actions = list(gen["actions"])
        prevention = list(gen["prevention"])
        diagnosis = "症状指向【%s】类问题，但未匹配到该作物已知清单具体条目；建议按%s处置并持续观察。" % (_cat_cn(cat), _cat_cn(cat))
        alternatives = [r for (_, r, _, _) in scored[:2]]
    else:
        diagnosis = "未提供症状，已基于【%s】的已知病虫害清单生成重点监测项与预防措施。" % (crop or "该作物")
        severity = "light"
        if scored:
            primary = None
            gen = CATEGORY_GENERIC.get(scored[0][2], CATEGORY_GENERIC["disease"])
            actions = ["重点监测：%s" % "、".join([r for (_, r, _, _) in scored[:3]])] + list(gen["actions"])
            prevention = list(gen["prevention"])
            alternatives = [r for (_, r, _, _) in scored[1:4]]
        else:
            actions = ["尚无该作物已知病虫害清单；建议保持巡查并记录异常。"]
            prevention = ["合理水肥", "田园清洁", "增强通风"]

    stage_tip = ""
    if growth_stage:
        stage_tip = "（当前阶段：%s）" % growth_stage

    match_quality = min(0.92, 0.35 + (scored[0][0] if scored else 0.0) * 0.5 + (0.1 if primary and KB.get(primary) else 0.0))
    if knowledge_source == "vision_assisted":
        match_quality = min(0.95, match_quality + 0.05)

    recommendation = "建议：%s%s" % ("；".join(actions[:3]), stage_tip)
    if vision_note:
        recommendation += " ｜ 视觉模型补充：%s" % vision_note[:160]

    # 零误报门控：先判定证据强度，再决定是否下确定性结论
    gate = _evidence_gate(sym, scored, primary, knowledge_source, environment)
    if gate["status"] != "confirmed":
        diagnosis = "（未确认）%s" % diagnosis
        recommendation = "（未确认，建议先采集证据）%s" % recommendation

    # 三阶段解释链：预测 → 解释 → 映射（全部派生自上面已算出的真实结果）
    reasoning_chain = _build_reasoning_chain(
        prediction={
            "primary": primary,
            "category": (scored[0][2] if scored else None),
            "top_score": round(scored[0][0], 3) if scored else 0.0,
            "severity": severity,
            "alternatives": alternatives,
            "match_quality": round(match_quality, 2),
            "diagnosis": diagnosis,
            "hit_min": _HIT_MIN,
        },
        explanation={
            "symptom_matches": {
                r: {
                    "name_hit": evidence_by_risk.get(r, {}).get("name_hit", False),
                    "name_fragment": evidence_by_risk.get(r, {}).get("name_fragment"),
                    "symptom_keywords": list(evidence_by_risk.get(r, {}).get(
                        "symptom_keywords", [])),
                    "signal_score": evidence_by_risk.get(r, {}).get("signal_score", 0.0),
                    "total_score": round(score, 3),
                }
                for (score, r, _, _) in scored[:3]
            },
            "signal_counts": dict(signals),
            "signal_contribution_note": "每类信号按 0.2×次数 计入总分",
            "environment": {
                "observed": _environment_observed(environment),
                "observed_keys": sorted([k for k in (environment or {}) if k in _ENV_KEYS]),
                "threshold": ">= 2 项有效数值（排除 NaN / bool）",
                "values": {k: environment.get(k) for k in sorted((environment or {}))
                           if k in _ENV_KEYS},
            },
            "vision_note": vision_note,
            "knowledge_source": knowledge_source,
        },
        mapping={
            "kb_pattern": (KB.get(primary) if primary else None),
            "kb_pattern_category": (
                _category_of(primary) if primary else None),
            "category_generic": (
                CATEGORY_GENERIC.get(scored[0][2]) if scored else
                CATEGORY_GENERIC.get("disease")),
            "risk_candidates": [r for (_, r, _, _) in scored[:5]],
            "crop_known_risks": risks,
            "growth_stage": growth_stage,
            "gate_status": gate["status"],
            "gate_missing": gate["missing"],
        },
    )

    result: Dict[str, Any] = {
        "diagnosis": diagnosis,
        "confirmation_status": gate["status"],
        "evidence_gate": gate,
        "reasoning_chain": reasoning_chain,
        "severity": severity,
        "actions": actions,
        "alternative_diagnoses": alternatives,
        "diagnosis_confidence": round(match_quality, 2),
        "matched_risks": [r for (_, r, _, _) in scored[:3]],
        "knowledge_source": knowledge_source,
        "evidence": {
            "crop": crop,
            "crop_known_risks": risks,
            "symptom_signals": signals,
            "growth_stage": growth_stage,
            "vision_used": knowledge_source == "vision_assisted",
            "environment_observed": _environment_observed(environment),
            "environment_keys": sorted([k for k in (environment or {}) if k in _ENV_KEYS]),
        },
        "confidence": {"rubric_score": round(match_quality, 2), "match_quality": round(match_quality, 2)},
        "constraints": list(SAFETY_CONSTRAINTS),
        "recommendation": recommendation,
    }
    if vision_note:
        result["vision_finding"] = vision_note

    result["signature"] = hashlib.sha256(_canonical(result).encode("utf-8")).hexdigest()
    return result


def _cat_cn(cat: str) -> str:
    return {"pest": "虫害", "disease": "病害", "nutrient": "营养缺乏", "abiotic": "非生物胁迫"}.get(cat, "病害")


class PestAgent:
    """病虫害诊断 Agent（包装 diagnose 函数，对齐其他 Agent 调用风格）。"""

    def diagnose(self, **kwargs) -> Dict[str, Any]:
        return diagnose(**kwargs)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return diagnose(
            crop=payload.get("crop", ""),
            symptom_description=payload.get("symptom_description", ""),
            image_reference=payload.get("image_reference", ""),
            growth_stage=payload.get("growth_stage", ""),
            environment=payload.get("environment"),
        )


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "番茄"
    s = sys.argv[2] if len(sys.argv) > 2 else "叶片出现黄色斑点，背面有白粉"
    print(json.dumps(diagnose(crop=c, symptom_description=s), ensure_ascii=False, indent=2))
