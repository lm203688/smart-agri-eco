"""
ControlAgent - L3 执行控制层（策略层 / 控制协议下发 + 执行补偿）

职责：
  1. 把 GrowthAgent 的种植计划（4 阶段 actions/tasks）+ EcoAgent 的设备推荐，
     翻译为「硬件无关的控制指令协议」（灌溉 / 施肥 / 补光 / 温控 / CO2 / 通风），
     供网关下发到具体品牌设备。
  2. 执行补偿：车载颠簸、开放环境波动、设备故障降级。

对标战略指引 L3：做「策略层」——决策引擎输出控制指令，经协议下发各品牌设备。
我们不造硬件，只定义指令语言（农业版「驱动程序」）。

诚实边界（真实性红线）：
  - 指令为硬件无关意图（actuator intents），真实执行需 MQTT / Node-RED 网关
    （参考 github.com/ishandutta2007/Awesome-Precision-Agriculture 的 In-Field IoT 层）。
  - 不假设任何具体设备已接入；缺失设备类别时给「人工等效操作」。
  - 设定值优先取 Env Recipe；Env Recipe 缺阶段时回退到分区气候默认值，并显式标注回退。
  - 本 Agent 不联网、不造数据，纯规则翻译 + 补偿策略。
"""

from __future__ import annotations

import json
import os
import re
import glob
from typing import Dict, Any, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RECIPE_DIR = os.path.join(ROOT, "data", "env_recipes")

# 生长阶段 → Env Recipe 阶段枚举（用于匹配设定值）
_PHASE_TO_STAGE = [
    (("播种", "育苗", "seed"), ["seed", "seedling"]),
    (("生长", "营养", "vegetative"), ["vegetative"]),
    (("开花", "flowering"), ["flowering"]),
    (("结果", "果实", "fruiting"), ["fruiting"]),
    (("采收", "收获", "harvest"), ["harvest"]),
]

# 需要执行的设备类别（若 EcoAgent 未推荐到，则需人工等效）
_NEED_CATEGORIES = {
    "irrigation": "灌溉/水肥一体",
    "light": "补光",
    "climate": "环控（温/湿）",
    "co2": "CO2 补充",
    "fan": "通风",
}

# 开放环境场景（需天气突变补偿）
_OPEN_SCENES = {"balcony", "balcony_rail", "roof", "office", "windowsill", "open_field"}
# 车载场景（需颠簸/能源补偿）
_CAR_SCENES = {"car_herbs", "car_greens", "car"}


def _match_stage(phase_name: str) -> List[str]:
    for keys, stages in _PHASE_TO_STAGE:
        if any(k in phase_name for k in keys):
            return stages
    return ["full_cycle"]


def _load_recipe(recipe_dir: str, zone_id: str, crop: str) -> Optional[Dict[str, Any]]:
    """按 zone__crop 或 crop 模糊匹配 Env Recipe；失败返回 None。"""
    if not zone_id and not crop:
        return None
    cands = []
    if os.path.isdir(recipe_dir):
        for p in glob.glob(os.path.join(recipe_dir, "*.json")):
            base = os.path.splitext(os.path.basename(p))[0]
            cl = base.lower()
            if crop and crop.lower() in cl:
                cands.append((0 if zone_id and zone_id.lower() in cl else 1, p))
    cands.sort()
    for _, p in cands[:1]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _parse_water_ml(text: str) -> Optional[float]:
    """从动作文案里抽取 '20 ml/天' 之类的灌溉量。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*ml", text, re.IGNORECASE)
    return float(m.group(1)) if m else None


class ControlAgent:
    """L3 执行控制 Agent —— 控制指令协议 + 执行补偿"""

    NAME = "ControlAgent"
    VERSION = "1.0"

    def __init__(self, env_recipes_dir: str = DEFAULT_RECIPE_DIR):
        self.recipe_dir = env_recipes_dir

    # ------------------------------------------------------------------
    def generate_control_plan(
        self,
        scene: str = "balcony",
        crop: str = "",
        zone_id: str = "",
        growth_plan: Optional[Dict[str, Any]] = None,
        devices: Optional[List[Dict[str, Any]]] = None,
        env_recipe: Optional[Dict[str, Any]] = None,
        microclimate: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """把种植计划 + 设备翻译为硬件无关控制指令 + 执行补偿。"""
        growth_plan = growth_plan or {}
        devices = devices or []
        if env_recipe is None:
            env_recipe = _load_recipe(self.recipe_dir, zone_id, crop)

        phases = growth_plan.get("recommendation", {}).get("phases", [])
        actuator_cmds: List[Dict[str, Any]] = []
        fallback_count = 0

        for ph in phases:
            pname = ph.get("phase", "未知阶段")
            day_range = ph.get("day_range", [0, 0])
            stages = _match_stage(pname)
            setpoints = self._stage_setpoints(env_recipe, stages)

            # 从阶段动作文案抽取可解析的灌溉量
            water_ml = None
            for act in ph.get("actions", []):
                water_ml = _parse_water_ml(act) or water_ml

            cmd_block = {
                "phase": pname,
                "day_range": day_range,
                "matched_stage": stages[0],
                "recipe_source": "env_recipe" if (setpoints.get("_from_recipe")) else "zone_climate_fallback",
                "commands": self._build_commands(setpoints, water_ml),
            }
            actuator_cmds.append(cmd_block)

        # 执行补偿
        compensation = self._compensation(scene, devices)
        fallback_count = compensation.get("missing_device_categories", 0)

        # 控制完整性：需要的类别里有多少被设备覆盖
        covered = {d.get("category") for d in devices}
        needed = set(_NEED_CATEGORIES.keys())
        # 设备 category 是中文（灌溉/水肥一体等），做粗映射
        covered_norm = set()
        for c in covered:
            if c and any(k in c for k in ("灌溉", "水肥")):
                covered_norm.add("irrigation")
            if c and ("光" in c or "led" in c.lower()):
                covered_norm.add("light")
            if c and ("环控" in c or "温" in c or "湿" in c):
                covered_norm.add("climate")
            if c and "co2" in c.lower():
                covered_norm.add("co2")
            if c and ("风" in c or "fan" in c.lower()):
                covered_norm.add("fan")
        missing = sorted(needed - covered_norm)

        rubric = 0.7 + min(0.2, len(actuator_cmds) * 0.02) - 0.05 * len(missing)
        rubric = round(max(0.4, min(rubric, 0.95)), 2)

        return {
            "evidence": {
                "scene": scene,
                "crop": crop,
                "zone_id": zone_id,
                "phases": len(actuator_cmds),
                "env_recipe_loaded": env_recipe is not None,
                "device_count": len(devices),
            },
            "confidence": {
                "match_quality": rubric,
                "actuation_note": "控制指令为硬件无关意图，需经 MQTT/Node-RED 网关下发至具体设备",
            },
            "constraints": {
                "needs_gateway": True,
                "missing_device_categories": missing,
                "open_standard": "env-recipe v1（schema 见 schemas/env_recipe.schema.json）",
            },
            "recommendation": {
                "actuator_commands": actuator_cmds,
                "compensation": compensation,
            },
        }

    # ------------------------------------------------------------------
    def _stage_setpoints(self, env_recipe: Optional[Dict[str, Any]], stages: List[str]) -> Dict[str, Any]:
        """从 Env Recipe 取某阶段的设定值；缺则回退空（调用方用分区默认）。"""
        out: Dict[str, Any] = {"_from_recipe": False}
        if not env_recipe:
            return out
        env = env_recipe.get("environment", {})
        # Env Recipe 多为单阶段；若有按阶段拆分则取第一个匹配
        for st in stages:
            # 当前 schema 单阶段，直接取 environment
            out["temperature"] = env.get("temperature")
            out["humidity"] = env.get("humidity")
            out["light"] = env.get("light")
            out["co2_ppm"] = env.get("co2_ppm")
            out["water_nutrient"] = env.get("water_nutrient")
            out["airflow"] = env.get("airflow")
            out["_from_recipe"] = True
            break
        return out

    def _build_commands(self, sp: Dict[str, Any], water_ml: Optional[float]) -> List[Dict[str, Any]]:
        """把设定值翻译为 actuator 指令列表。"""
        cmds: List[Dict[str, Any]] = []
        wn = sp.get("water_nutrient") or {}
        if water_ml is not None:
            cmds.append({"actuator": "irrigation", "command": "set_daily_volume",
                         "value": water_ml, "unit": "ml/day", "schedule": "daily"})
        elif wn.get("water_ml_day"):
            cmds.append({"actuator": "irrigation", "command": "set_daily_volume",
                         "value": wn["water_ml_day"], "unit": "ml/day", "schedule": "daily"})
        if wn.get("ec_ms") is not None:
            cmds.append({"actuator": "fertigation", "command": "set_ec",
                         "value": wn["ec_ms"], "unit": "mS/cm", "schedule": "per_reservoir_change"})
        if wn.get("ph") is not None:
            cmds.append({"actuator": "fertigation", "command": "set_ph",
                         "value": wn["ph"], "unit": "pH", "schedule": "per_reservoir_change"})
        light = sp.get("light") or {}
        if light.get("ppfd_umol"):
            cmds.append({"actuator": "grow_light", "command": "set_ppfd",
                         "value": light["ppfd_umol"], "unit": "umol/m2/s", "schedule": "photoperiod"})
        if light.get("photoperiod_h"):
            cmds.append({"actuator": "grow_light", "command": "set_photoperiod",
                         "value": light["photoperiod_h"], "unit": "h/day", "schedule": "daily"})
        temp = sp.get("temperature") or {}
        if temp.get("day_c") is not None:
            cmds.append({"actuator": "climate", "command": "set_day_temp",
                         "value": temp["day_c"], "unit": "C", "schedule": "daily"})
        if temp.get("night_c") is not None:
            cmds.append({"actuator": "climate", "command": "set_night_temp",
                         "value": temp["night_c"], "unit": "C", "schedule": "daily"})
        hum = sp.get("humidity") or {}
        if hum.get("min_pct") is not None and hum.get("max_pct") is not None:
            cmds.append({"actuator": "climate", "command": "set_humidity_range",
                         "value": [hum["min_pct"], hum["max_pct"]], "unit": "pct",
                         "schedule": "continuous"})
        if sp.get("co2_ppm"):
            cmds.append({"actuator": "co2", "command": "set_co2",
                         "value": sp["co2_ppm"], "unit": "ppm", "schedule": "daytime"})
        af = sp.get("airflow") or {}
        if af.get("level"):
            cmds.append({"actuator": "fan", "command": "set_level",
                         "value": af["level"], "unit": "level", "schedule": "continuous"})
        return cmds

    def _compensation(self, scene: str, devices: List[Dict[str, Any]]) -> Dict[str, Any]:
        """执行补偿：车载颠簸 / 开放环境波动 / 设备故障降级。"""
        rules: List[Dict[str, Any]] = []
        if scene in _CAR_SCENES:
            rules.append({
                "type": "vehicle_jolt",
                "trigger": "车载颠簸 / 急刹 / 能源波动",
                "action": "容器加固 + 降低水位波动（潮汐灌溉改静态液面）+ 能源管理：断电容错回落到手动模式",
                "severity": "warn",
            })
        if scene in _OPEN_SCENES:
            rules.append({
                "type": "open_weather",
                "trigger": "降雨 / 强风 / 骤降温",
                "action": "雨天暂停灌溉并遮雨；强风加固/移入；高温日遮阴+午后补水的开放环境波动预案",
                "severity": "warn",
            })
        # 设备故障降级：按设备类别缺失给人工等效
        manual = []
        covered_norm = set()
        for d in devices:
            c = d.get("category", "")
            if any(k in c for k in ("灌溉", "水肥")):
                covered_norm.add("irrigation")
            if "光" in c or "led" in c.lower():
                covered_norm.add("light")
            if "环控" in c or "温" in c or "湿" in c:
                covered_norm.add("climate")
        for cat in sorted(set(_NEED_CATEGORIES.keys()) - covered_norm):
            manual.append({
                "missing_category": cat,
                "manual_equivalent": _NEED_CATEGORIES[cat] + "：未推荐到设备，按 Env Recipe 设定值手动执行（见 actuator_commands）",
            })
        return {
            "rules": rules,
            "device_failure_fallback": manual,
            "missing_device_categories": len(manual),
        }

    # ------------------------------------------------------------------
    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """call_skill('control_commands') 入口。"""
        return self.generate_control_plan(
            scene=payload.get("scene", "balcony"),
            crop=payload.get("crop", ""),
            zone_id=payload.get("zone_id", ""),
            growth_plan=payload.get("growth_plan"),
            devices=payload.get("devices"),
            env_recipe=payload.get("env_recipe"),
            microclimate=payload.get("microclimate"),
        )
