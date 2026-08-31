"""
ClimateAgent - 气候/水文/土壤分区匹配

职责：
  1. 接收地块坐标或环境描述
  2. 匹配全球农业分区（Köppen 气候带 + FAO 农业分区）
  3. 输出分区元数据 + 关键环境约束（温度区间/降水/土壤类型）
  4. 标记"微气候修正因子"（阳台朝向/楼层/遮蔽）

对标 SwarmLabs：相当于世界模型层（world_model.py）的地理子域

输出契约（严格遵循 docs/agent_output_contract.md）：
  {
    "evidence": {"zone_id": "...", "climate_class": "...", "data_sources": [...]},
    "confidence": {"rubric_score": 0.85, "coverage_pct": 0.7},
    "constraints": {"min_temp": -5, "max_temp": 40, "soil_ph_range": [5.5, 8.0]},
    "recommendation": "该地块适合种植 X 类作物，建议关注 Y 风险"
  }
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ZONE_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")

DATA_SOURCES = ["WorldClim 2.1", "FAO GAEZ", "ISRIC SoilGrids", "NASA POWER"]

# 纬度区间近似匹配（精确匹配需栅格数据，此版本用区域启发式）
# 判断顺序：先判亚寒带/热带雨林（纬度优先），再按大陆/沿海判地中海/干旱/湿润
def _match_zone_by_coords(lat: float, lon: float) -> str:
    a = abs(lat)

    # 1) 亚寒带：高纬度
    if a >= 55:
        return "subarctic"

    # 2) 热带雨林：赤道附近（南北纬 10 度内）
    if a < 10:
        return "tropical_rainforest"

    # 3) 中亚/北美内陆干旱带（远离海洋的内陆）
    #    中亚: 60-90°E, 35-50°N
    #    北美内陆: -110 到 -100°E, 32-48°N
    #    澳洲内陆: 115-145°E, -38 到 -20
    if 35 <= a <= 50 and 60 <= lon <= 90:
        return "arid"
    if 32 <= a <= 48 and -110 <= lon <= -100:
        return "arid"
    if -38 <= lat <= -20 and 115 <= lon <= 145:
        return "arid"

    # 4) 地中海带：大陆西岸 25-40 度（地中海沿岸/加州/智利/南非/澳洲南部）
    #    地中海沿岸: -10 到 35°E, 25-42°N（含北非）
    #    加州: -125 到 -117°E, 32-42°N
    #    智利中部: -72 到 -66°E, -42 到 -20
    #    南非西部: 17 到 20°E, -34 到 -28
    #    澳洲西南部: 115-125°E, -38 到 -30
    if 25 <= a <= 42 and -10 <= lon <= 35:
        return "mediterranean"
    if 32 <= a <= 42 and -125 <= lon <= -117:
        return "mediterranean"
    if -42 <= lat <= -20 and -72 <= lon <= -66:
        return "mediterranean"
    if -34 <= lat <= -28 and 17 <= lon <= 20:
        return "mediterranean"
    if -38 <= lat <= -30 and 115 <= lon <= 125:
        return "mediterranean"

    # 5) 温带大陆性：中高纬度内陆/大陆性气候（中国北方/俄罗斯/北美东部/南美内陆）
    #    中国北方: 110-125°E, 35-50°N
    #    俄罗斯/东欧: 25-60°E, 45-60°N
    #    北美东部: -90 到 -60°E, 40-50°N
    if 35 <= a <= 50 and 110 <= lon <= 125:
        return "temperate_continental"
    if 45 <= a <= 60 and 25 <= lon <= 60:
        return "temperate_continental"
    if 40 <= a <= 50 and -90 <= lon <= -60:
        return "temperate_continental"

    # 6) 亚热带湿润：默认（东亚季风区/北美东南部/南美沿海/澳洲东南部）
    #    中国东部沿海: 110-125°E, 20-35°N
    #    美国东南部: -95 到 -75°E, 25-35°N
    #    巴西东南沿海: -50 到 -35°E, -25 到 -5
    #    澳洲东南: 145-153°E, -40 到 -30
    return "subtropical_wet"


class ClimateAgent:
    """全球分区气候/土壤/水文匹配 Agent"""

    NAME = "ClimateAgent"
    VERSION = "1.1"

    def __init__(self, zone_meta_path: str = DEFAULT_ZONE_PATH):
        self.zone_meta_path = zone_meta_path
        self._zones: List[Dict[str, Any]] = []
        self._zone_index: Dict[str, Dict[str, Any]] = {}
        self._load_zones()

    def _load_zones(self) -> None:
        """加载分区元数据；失败时降级为空列表。"""
        try:
            if os.path.exists(self.zone_meta_path):
                with open(self.zone_meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._zones = data.get("zones", [])
                self._zone_index = {z["zone_id"]: z for z in self._zones}
        except Exception:
            self._zones = []
            self._zone_index = {}

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def match_zone(self, lat: float, lon: float) -> Dict[str, Any]:
        """根据经纬度匹配农业分区。"""
        zone_id = _match_zone_by_coords(lat, lon)
        z = self._zone_index.get(zone_id, {})

        if not z:
            # 降级：数据缺失
            return {
                "evidence": {"zone_id": zone_id, "zone_name": "UNKNOWN",
                             "climate_class": "UNKNOWN",
                             "data_sources": DATA_SOURCES,
                             "data_recency_years": None},
                "confidence": {"rubric_score": 0.0, "coverage_pct": 0.0,
                               "data_recency_years": None},
                "constraints": {"min_temp_c": None, "max_temp_c": None,
                                "precipitation_mm_yr": None,
                                "growing_season_days": None,
                                "frost_risk": None,
                                "soil_ph_range": [None, None]},
                "recommendation": "分区数据缺失，需补充分区元数据",
            }

        temp = z.get("temperature_range", {})
        precip = z.get("precipitation_mm_yr", {})
        soil = z.get("soil", {})
        typical = z.get("typical_crops", [])
        risks = z.get("key_constraints", [])
        scene_potential = z.get("distributed_agri_potential", {})

        # 置信度：数据完整度
        has_temp = temp.get("min_c") is not None and temp.get("max_c") is not None
        has_precip = precip.get("min") is not None
        has_soil = bool(soil.get("ph_range"))
        has_risk = len(risks) > 0
        completeness = sum([has_temp, has_precip, has_soil, has_risk]) / 4
        rubric_score = round(0.7 + completeness * 0.25, 2)  # 基准 0.7 + 完整度加权

        # 典型作物示例（前 3 个）
        crop_hint = "、".join(typical[:3]) if typical else "通用作物"

        return {
            "evidence": {
                "zone_id": z.get("zone_id"),
                "zone_name": z.get("zone_name"),
                "climate_class": z.get("koppen_class"),
                "data_sources": DATA_SOURCES,
                "data_recency_years": 2,
                "crop_count_in_db": len(typical),
            },
            "confidence": {
                "rubric_score": rubric_score,
                "coverage_pct": round(completeness, 2),
                "data_recency_years": 2,
                "confidence_note": f"数据完整度 {completeness*100:.0f}%（温度/降水/土壤/风险 4 项）",
            },
            "constraints": {
                "min_temp_c": temp.get("min_c"),
                "max_temp_c": temp.get("max_c"),
                "precipitation_mm_yr": precip.get("min"),
                "precipitation_range": precip,
                "growing_season_days": z.get("growing_season_days"),
                "frost_risk": z.get("frost_risk"),
                "soil_ph_range": soil.get("ph_range"),
                "soil_texture_hint": soil.get("texture_hint"),
                "water_availability": z.get("water_availability"),
                "key_constraints": risks,
                "distributed_agri_potential": scene_potential,
            },
            "recommendation": (
                f"该地块属「{z.get('zone_name')}」({z.get('koppen_class')})，"
                f"典型作物包括 {crop_hint} 等。"
                f"{'需关注：' + '、'.join(risks) if risks else '环境条件适宜。'}"
                f" 分布式农业潜力：{json.dumps(scene_potential, ensure_ascii=False)}"
            ),
        }

    # ------------------------------------------------------------------
    # 微气候修正
    # ------------------------------------------------------------------
    def microclimate_adjustment(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """微气候修正（阳台/屋顶/车载等分布式场景）。"""
        scene = context.get("scene", "balcony")
        floor = context.get("floor", 1)
        orientation = context.get("orientation", "south")
        city = context.get("city", "")
        shading = context.get("shading_ratio", 0.0)

        temp_offset = 0.0
        sun_delta = 0.0
        notes = []

        # 楼层效应
        if scene == "balcony":
            if floor >= 10:
                temp_offset -= 0.8  # 高楼层风大降温
                notes.append(f"{floor}楼高，风大，冬季需保温")
                sun_delta += 0.5  # 日照更足
            elif floor <= 3:
                temp_offset += 0.5
                sun_delta -= 1.0
                notes.append(f"{floor}楼低，日照可能被遮挡")

            # 朝向
            orient_bonus = {"south": 1.5, "southeast": 1.0, "southwest": 1.0,
                            "east": 0.5, "west": 0.5, "north": -2.0}.get(orientation, 0)
            sun_delta += orient_bonus
            if orient_bonus > 0:
                notes.append(f"朝{orientation}，日照充足")
            elif orient_bonus < 0:
                notes.append(f"朝{orientation}，日照不足")

            # 遮蔽
            if shading >= 0.5:
                sun_delta -= 2.0
                notes.append("遮蔽严重，建议改种耐阴品种")
            elif shading >= 0.3:
                sun_delta -= 1.0
                notes.append("部分遮蔽，需注意通风")
        elif scene == "roof":
            temp_offset += 1.5
            sun_delta += 1.0
            notes.append("屋顶直射强，夏季需遮阳")
        elif scene == "car":
            temp_offset += 2.0
            notes.append("车载封闭环境，需通风降温")
        elif scene == "office":
            sun_delta -= 2.0
            notes.append("室内光照不足，建议补光或选耐阴品种")

        return {
            "effective_temp_offset": round(temp_offset, 2),
            "effective_sun_hours_delta": round(sun_delta, 2),
            "micro_climate_note": "；".join(notes) if notes else "标准环境，无需修正",
            "scene": scene,
            "floor": floor,
            "orientation": orientation,
            "city": city,
            "shading_ratio": shading,
        }
