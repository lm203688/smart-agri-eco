"""NutritionAgent - 养分管理与施肥方案（数据驱动 + 阶段化）。

设计原则（与项目其他 Agent 一致）：
- 纯 Python 标准库，零第三方依赖。
- 数据驱动：优先用 ``data/crop_adapt_db.json`` 中每作物的 ``family`` / ``growth_days`` /
  ``water_ml_day`` / ``ph_range`` 作为计算基线，再结合内置养分需求知识库（按作物
  科属/类型的 NPK 侧重）生成阶段化施肥方案。
- 输出遵循 docs/agent_output_contract.md（evidence / confidence / constraints / recommendation），
  并附 ``signature``（内容 sha256）以满足 AgriTrust 可复现要求。
- 安全边界：不替代土壤/基质检测；严格按肥料标签稀释，宁稀勿浓，避免烧根烧叶。

输入:
    crop (str): 作物名（与 crop_adapt_db 的 ``crop`` 字段匹配，允许别名/部分匹配）
    scene (str, optional): 种植场景（balcony/container/garden/office 等）
    growth_stage (str, optional): 当前生长阶段（如 苗期/花期/结果期），用于定位方案切片
    growth_days (int, optional): 覆盖 DB 中的生长周期（用于自定义方案）
    container_volume_l (float, optional): 容器容积（升），用于估算单次施肥量
    start_date (str, optional): 播种/定植日期（用于给出绝对时间节点）

输出:
    {
      "evidence": {...},
      "confidence": {"rubric_score": float, "coverage_pct": float, "confidence_note": str},
      "constraints": [str,...],          # 3 条安全边界
      "recommendation": {
        "crop": str, "profile_label": str, "npk_strategy": str,
        "phases": [ {phase, day_range, fertilizer, npk, frequency, dilution, amount_guidance, notes} ],
        "key_principles": [str,...],
        "deficiency_quickref": {symptom: nutrient},
        "manual_review_note": str,
      },
      "signature": str,
    }
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DATA = os.path.join(PROJECT_ROOT, "data")
CROP_DB_PATH = os.path.join(DATA, "crop_adapt_db.json")

# 安全边界（每次方案都携带）
SAFETY_CONSTRAINTS = [
    "本方案为通用施肥指导，不替代土壤/基质检测；盐碱化或连作障碍需先做淋洗/换土。",
    "严格按肥料标签剂量稀释，宁稀勿浓（建议浓度不超过所列上限），避免烧根烧叶。",
    "忌高温中午施肥；液肥随水施、施后回水；有机肥须充分腐熟，避免生肥烧根与病菌。",
]

# ---------------------------------------------------------------------------
# 内置养分需求知识库（按作物类型/科属的 NPK 侧重）
# 每个 profile:
#   label        类型名
#   npk_veg      营养生长阶段推荐 NPK（高 N 促茎叶）
#   npk_repro    生殖/膨大阶段推荐 NPK（高 K 促果/根，降 N）
#   micro        关键中微量元素
#   leaf         是否为叶菜（True 时采收期仍维持高 N）
#   base_g_per_l 标准水溶肥浓度（g/L，满浓度）
#   freq_days    建议施肥间隔（天）
#   principle    一句话原则
# ---------------------------------------------------------------------------
PROFILES: Dict[str, Dict[str, Any]] = {
    "leafy": {
        "label": "叶菜类（高氮）",
        "npk_veg": "20-10-10", "npk_repro": "18-12-12",
        "micro": ["钙", "镁"], "leaf": True,
        "base_g_per_l": 1.4, "freq_days": 7, "strength": 0.10,
        "principle": "以氮为主促茎叶，采收前仍维持氮，忌施未腐熟有机肥。",
    },
    "solanaceae": {
        "label": "茄果类（苗期氮、花果钾）",
        "npk_veg": "15-15-15", "npk_repro": "10-10-22(+Ca/B)",
        "micro": ["钙", "硼"], "leaf": False,
        "base_g_per_l": 1.6, "freq_days": 10, "strength": 0.15,
        "principle": "苗期均衡，开花坐果后增钾补钙硼，防脐腐与畸形果。",
    },
    "cucurbit": {
        "label": "瓜类（高钾+钙）",
        "npk_veg": "15-10-15", "npk_repro": "12-12-24(+Ca)",
        "micro": ["钙"], "leaf": False,
        "base_g_per_l": 1.6, "freq_days": 10, "strength": 0.15,
        "principle": "幼瓜膨大期需钾钙充足，忌偏氮导致旺长化瓜。",
    },
    "root": {
        "label": "根菜/薯类（低氮高钾磷）",
        "npk_veg": "10-15-15", "npk_repro": "5-10-20",
        "micro": ["钾", "硼"], "leaf": False,
        "base_g_per_l": 1.3, "freq_days": 14, "strength": 0.10,
        "principle": "控氮防地上旺长，重磷钾促膨大，忌中后期偏氮。",
    },
    "legume": {
        "label": "豆类（低氮，重磷钾钼硼）",
        "npk_veg": "5-10-10", "npk_repro": "5-10-15",
        "micro": ["钼", "硼"], "leaf": False,
        "base_g_per_l": 1.0, "freq_days": 14, "strength": 0.08,
        "principle": "根瘤固氮，基肥少氮；花荚期补磷钾与钼硼防落花落荚。",
    },
    "tree": {
        "label": "果树/多年生（高钾+中微）",
        "npk_veg": "15-10-15", "npk_repro": "12-8-20(+Ca/Mg/B/Zn)",
        "micro": ["钙", "镁", "硼", "锌"], "leaf": False,
        "base_g_per_l": 1.6, "freq_days": 21, "strength": 0.15,
        "principle": "梢期氮、果期钾，常年补钙镁硼锌防苦痘/小叶黄化。",
    },
    "herb": {
        "label": "香草/调味（轻肥）",
        "npk_veg": "10-10-10", "npk_repro": "10-10-10",
        "micro": [], "leaf": True,
        "base_g_per_l": 1.0, "freq_days": 14, "strength": 0.08,
        "principle": "需肥量低，稀肥薄施，避免香气变淡与徒长。",
    },
    "succulent": {
        "label": "多浆/特殊（极轻肥）",
        "npk_veg": "5-5-5", "npk_repro": "5-5-5",
        "micro": [], "leaf": True,
        "base_g_per_l": 0.6, "freq_days": 21, "strength": 0.05,
        "principle": "极耐贫瘠，宁缺勿滥；冰菜等忌偏氮导致晶泡稀疏、口感变差。",
    },
    "grain": {
        "label": "粮食/禾本（穗期重钾）",
        "npk_veg": "20-10-10", "npk_repro": "15-5-20",
        "micro": ["锌"], "leaf": False,
        "base_g_per_l": 1.4, "freq_days": 10, "strength": 0.12,
        "principle": "分蘖期氮、抽穗灌浆期钾，补锌防花白苗。",
    },
}

DEFAULT_PROFILE = "leafy"  # 兜底：未知作物按叶菜轻氮处理，偏保守

# 作物名精确覆盖（部分高频作物直接指定 profile）
CROP_OVERRIDE = {
    "冰菜": "succulent", "冰草": "succulent", "芦荟": "succulent",
    "草莓": "solanaceae", "蓝莓": "tree", "香蕉": "tree", "木瓜": "tree",
    "柑橘": "tree", "柠檬": "tree", "苹果": "tree", "葡萄": "tree",
}
# 科属关键词 -> profile
FAMILY_MAP = [
    ("茄科", "solanaceae"),
    ("葫芦科", "cucurbit"),
    ("豆科", "legume"),
    ("蔷薇科", "tree"),
    ("葡萄科", "tree"),
    ("芭蕉科", "tree"),
    ("番木瓜科", "tree"),
    ("芸香科", "tree"),
    ("百合科", "herb"),
    ("唇形科", "herb"),
    ("伞形科", "root"),
    ("旋花科", "root"),
    ("薯蓣科", "root"),
    ("禾本科", "grain"),
    ("菊科", "leafy"),
    ("十字花科", "leafy"),
    ("藜科", "leafy"),
    ("苋科", "leafy"),
    ("锦葵科", "leafy"),
    ("景天科", "succulent"),
    ("番杏科", "succulent"),
]

# 营养缺乏速查（桥接 PestAgent；症状 -> 缺乏元素）
DEFICIENCY_QUICKREF = {
    "老叶均匀发黄、植株矮小": "缺氮 (N)",
    "叶片暗绿带紫、生长迟缓": "缺磷 (P)",
    "老叶叶缘焦枯、易倒伏": "缺钾 (K)",
    "新叶黄白、叶脉仍绿": "缺铁 (Fe)",
    "新叶钩状、顶芽枯死": "缺钙 (Ca)",
    "老叶脉间黄化、易早衰": "缺镁 (Mg)",
    "顶芽畸形、花而不实": "缺硼 (B)",
    "新叶簇生、小叶黄化": "缺锌 (Zn)",
}

# 用户描述的生长阶段关键词 -> 方案阶段索引（0..3）
STAGE_KEYWORD_MAP = [
    (0, ["播种", "育苗", "出苗", "定植前"]),
    (1, ["苗期", "幼苗", "缓苗", "定植"]),
    (2, ["生长", "旺盛", "营养", "茎叶", "发棵"]),
    (3, ["花", "果", "结果", "坐果", "采收", "膨大", "转色", "成熟", "结球"]),
]


def _load_crop_db() -> Dict[str, Any]:
    try:
        if os.path.exists(CROP_DB_PATH):
            with open(CROP_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}
    return {}


def _find_crop(crop: str) -> Optional[Dict[str, Any]]:
    db = _load_crop_db()
    zones = db.get("zones", {})
    crop_l = (crop or "").strip().lower()
    if not crop_l:
        return None
    for zid, zd in zones.items():
        for c in zd.get("crops", []):
            name = (c.get("crop") or "").strip().lower()
            if not name:
                continue
            if name == crop_l:
                return c
            if len(name) >= 2 and len(crop_l) >= 2 and (crop_l in name or name in crop_l):
                return c
    aliases = {
        "香蕉": "蕉", "番茄": "西红柿", "西红柿": "番茄", "玉米": "玉蜀黍",
        "马铃薯": "土豆", "土豆": "马铃薯", "辣椒": "椒", "柑橘": "柑桔",
        "冰菜": "冰草", "冰草": "冰菜",
    }
    alt = aliases.get(crop_l)
    if alt:
        for zid, zd in zones.items():
            for c in zd.get("crops", []):
                name = (c.get("crop") or "").strip().lower()
                if name and (alt in name or name in alt):
                    return c
    return None


def _profile_for(crop: str, family: str) -> str:
    crop_l = (crop or "").strip()
    if crop_l in CROP_OVERRIDE:
        return CROP_OVERRIDE[crop_l]
    fam = family or ""
    for kw, key in FAMILY_MAP:
        if kw in fam:
            return key
    # 名称兜底（含关键类型词）
    for kw, key in [("豆", "legume"), ("瓜", "cucurbit"), ("椒", "solanaceae"),
                    ("茄", "solanaceae"), ("莓", "solanaceae"), ("菜", "leafy"),
                    ("葱", "herb"), ("蒜", "herb"), ("麦", "grain"), ("稻", "grain"),
                    ("玉米", "grain"), ("薯", "root"), ("蕉", "tree"), ("果", "tree")]:
        if kw in crop_l:
            return key
    return DEFAULT_PROFILE


def _build_fert_phases(
    growth_days: int,
    profile: Dict[str, Any],
    water_ml_day: int,
    container_volume_l: Optional[float],
    is_leaf: bool,
) -> List[Dict[str, Any]]:
    gd = max(int(growth_days), 20)
    sow_end = max(7, round(gd * 0.15))
    seedling_end = max(sow_end + 7, round(gd * 0.40))
    preharvest = max(seedling_end + 7, round(gd * 0.85))

    base = profile["base_g_per_l"]
    freq = profile["freq_days"]
    full_strength = profile["strength"]

    # 单次施肥量估算（g/次）：以当日浇水量的约 1/3 淋施，乘标准浓度与强度系数
    def _amount(strength_factor: float) -> str:
        water_l = water_ml_day / 1000.0
        per_feeding_l = water_l * 0.6  # 施肥约占浇水频次的一部分
        g = per_feeding_l * base * strength_factor
        if container_volume_l:
            return "约 %.2f g 水溶肥兑水淋施（容器约 %.0f L）" % (g, container_volume_l)
        return "约 %.2f g 水溶肥兑水淋施（按容器容积估算）" % g

    def _dilution(strength_factor: float) -> str:
        conc = full_strength * strength_factor
        times = round(1.0 / conc) if conc > 0 else 1000
        return "稀释约 %d 倍（浓度约 %.2f%%）" % (times, conc * 100)

    phases = [
        {
            "phase": "播种育苗",
            "day_range": [1, sow_end],
            "fertilizer": "不施肥（基质含底肥则全程免补）",
            "npk": "—",
            "frequency": "—",
            "dilution": "—",
            "amount_guidance": "出真叶前禁肥；若基质无肥，D7 后可极稀 1/4 浓度启动。",
            "notes": "幼苗根系嫩，浓肥极易烧苗。",
        },
        {
            "phase": "苗期管理",
            "day_range": [sow_end + 1, seedling_end],
            "fertilizer": "高氮水溶肥（促茎叶）",
            "npk": profile["npk_veg"],
            "frequency": "每 %d 天 1 次（半浓度）" % freq,
            "dilution": _dilution(0.5),
            "amount_guidance": _amount(0.5),
            "notes": "薄肥勤施，配合见干见湿浇水。",
        },
        {
            "phase": "生长旺盛",
            "day_range": [seedling_end + 1, preharvest],
            "fertilizer": "均衡/类型适配水溶肥（营养高峰）",
            "npk": profile["npk_veg"],
            "frequency": "每 %d 天 1 次（满浓度）" % freq,
            "dilution": _dilution(1.0),
            "amount_guidance": _amount(1.0),
            "notes": "生长量最大，水肥同频；攀援/高大作物同步绑蔓。",
        },
        {
            "phase": "成熟采收",
            "day_range": [preharvest + 1, gd],
            "fertilizer": ("高氮维持（叶菜连续采收）" if is_leaf
                           else "高钾+钙硼水溶肥（膨果/结球/转色）"),
            "npk": profile["npk_repro"],
            "frequency": "每 %d 天 1 次（满浓度）" % freq,
            "dilution": _dilution(1.0),
            "amount_guidance": _amount(1.0),
            "notes": ("叶菜留茬再生、多次采收，持续供氮；"
                      if is_leaf else "控氮防贪青晚熟，重钾提升品质与耐储性。"),
        },
    ]
    return phases


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def plan(
    crop: str = "",
    scene: str = "",
    growth_stage: str = "",
    growth_days: Optional[int] = None,
    container_volume_l: Optional[float] = None,
    start_date: str = "",
    environment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """生成一次养分管理/施肥方案。详见模块 docstring。"""
    crop_info = _find_crop(crop)
    data_loaded = crop_info is not None

    if data_loaded:
        family = crop_info.get("family", "")
        gd = growth_days or crop_info.get("growth_days", 60)
        water = crop_info.get("water_ml_day", 150)
        ph = crop_info.get("ph_range", [6.0, 7.0])
        db_ver = _load_crop_db().get("meta", {}).get("version", "1.0")
    else:
        family = ""
        gd = growth_days or 60
        water = 200
        ph = [6.0, 7.0]
        db_ver = "n/a"

    profile_key = _profile_for(crop, family)
    profile = PROFILES[profile_key]
    is_leaf = profile.get("leaf", False)

    phases = _build_fert_phases(gd, profile, water, container_volume_l, is_leaf)

    # 若用户指定了当前阶段，给出切片提示
    stage_note = ""
    if growth_stage:
        idx = None
        for i, kws in STAGE_KEYWORD_MAP:
            if any(k in growth_stage for k in kws):
                idx = i
                break
        if idx is None:
            for i, p in enumerate(phases):
                if growth_stage in p["phase"]:
                    idx = i
                    break
        if idx is not None:
            mp = phases[idx]
            stage_note = "当前处于「%s」：%s，%s" % (
                mp["phase"], mp["fertilizer"], mp["amount_guidance"])
        else:
            stage_note = "未识别阶段「%s」，已给出全周期方案供参考。" % growth_stage

    # 置信度：数据齐备 + 科属命中
    rubric = 0.82 if data_loaded else 0.35
    coverage = 1.0 if data_loaded else 0.4
    if family:
        rubric = min(0.92, rubric + 0.06)
    note = (
        "基于 %s 真实生长周期 D%d 与科属「%s」养分需求生成阶段化方案"
        % (crop or "未知作物", gd, profile["label"])
    ) if data_loaded else "未匹配到作物数据，按通用轻氮方案给出，建议补充作物名以提升精度"

    result: Dict[str, Any] = {
        "evidence": {
            "crop": crop,
            "family": family,
            "growth_days": gd,
            "water_ml_day": water,
            "ph_range": ph,
            "fert_profile_key": profile_key,
            "fert_profile_label": profile["label"],
            "data_loaded": data_loaded,
            "data_sources": ["crop_adapt_db.json (family/growth_days/water/ph)",
                             "内置养分需求知识库（按科属 NPK 侧重）"],
            "crop_db_version": db_ver,
        },
        "confidence": {
            "rubric_score": round(rubric, 2),
            "coverage_pct": coverage,
            "confidence_note": note,
        },
        "constraints": list(SAFETY_CONSTRAINTS),
        "recommendation": {
            "crop": crop or "未知作物",
            "profile_label": profile["label"],
            "npk_strategy": "苗期 %s → 花果/采收 %s" % (profile["npk_veg"], profile["npk_repro"]),
            "key_principles": [profile["principle"]],
            "phases": phases,
            "deficiency_quickref": DEFICIENCY_QUICKREF,
            "current_stage_guidance": stage_note,
            "scene": scene or "未指定",
            "start_date": start_date or "",
            "manual_review_note": (
                "容器栽培盐渍化风险高，每 4–6 周用清水淋洗一次；"
                "若出现疑似缺素，请先用 PestAgent 诊断并参考上方速查表对应元素。"
            ),
        },
    }

    result["signature"] = hashlib.sha256(_canonical(result).encode("utf-8")).hexdigest()
    return result


class NutritionAgent:
    """养分管理 Agent（包装 plan 函数，对齐其他 Agent 调用风格）。"""

    def plan(self, **kwargs) -> Dict[str, Any]:
        return plan(**kwargs)

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return plan(
            crop=payload.get("crop", ""),
            scene=payload.get("scene", ""),
            growth_stage=payload.get("growth_stage", ""),
            growth_days=payload.get("growth_days"),
            container_volume_l=payload.get("container_volume_l"),
            start_date=payload.get("start_date", ""),
            environment=payload.get("environment"),
        )


if __name__ == "__main__":
    import sys
    c = sys.argv[1] if len(sys.argv) > 1 else "番茄"
    print(json.dumps(plan(crop=c), ensure_ascii=False, indent=2))
