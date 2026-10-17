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
import math
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

    # 5.5) 热漠 / 高原坐标的精确路由：必须在最后的默认分支之前判定，
    #      否则会被静默吞成「亚热带湿润」——
    #      2026-09-23 前迪拜就是这样拿到湿热区参数的（年均 17°C + 终年湿润的作物清单），
    #      而它实际是热漠（年均约 28°C、年降水约 100mm），属于错到会种死的推荐。
    #      v1.1（2026-09-30）已把 hot_arid / highland 加入 global_zones.json 并回填作物
    #      （2026-10-06 P3 校准），这两个分区现在**已建模**——此处把它们正确导向对应分区，
    #      不再走「未建模降级」路径。放在此处意味着：只改变原本会落到默认分支的点。
    gap = _detect_unmodeled_zone(lat, lon)
    if gap:
        return gap

    # 6) 亚热带湿润：默认（东亚季风区/北美东南部/南美沿海/澳洲东南部）
    #    中国东部沿海: 110-125°E, 20-35°N
    #    美国东南部: -95 到 -75°E, 25-35°N
    #    巴西东南沿海: -50 到 -35°E, -25 到 -5
    #    澳洲东南: 145-153°E, -40 到 -30
    return "subtropical_wet"


# ---------------------------------------------------------------------------
# 未建模气候类（识别得出、但当前分区库仍未建模的气候类）
# ---------------------------------------------------------------------------
# v1.1（2026-09-30）已把 hot_arid / highland 加入 global_zones.json 并回填作物
# （2026-10-06 P3 校准），因此这两个类**不再未建模**，已从下方清单移除。
# 该字典现在为空，作为「未来若出现分区库仍未覆盖的真实气候类」时显式拒答的预留位：
# match_zone 在分区缺失时会走「分区数据缺失」降级路径（zone_id_known 判红、作物推荐为空），
# 即：宁可显式失败，也不给基于错误气候假设的方案。
#
# 注：_detect_unmodeled_zone() 现仍负责把热漠/高原坐标路由到已建模的 hot_arid / highland
# 分区（盒式启发式），与「未建模降级」是两件事，请勿混淆。
UNMODELED_ZONE_CLASSES: Dict[str, str] = {}


def _detect_unmodeled_zone(lat: float, lon: float) -> Optional[str]:
    """识别当前分区库未建模的气候类，返回类名；未命中返回 None。

    与文件内其它规则同属经纬度盒式启发式（精确判定需栅格数据）。刻意保守：
    只覆盖有实据的两个缺口（预设城市迪拜 = 波斯湾热漠、拉萨 = 青藏高原），
    宁可少判，不顺手改动其它区域——例如开罗（31.2°E）仍在盒子外，归类保持原样。
    """
    a = abs(lat)
    # 热漠：阿拉伯半岛 + 波斯湾沿岸（迪拜 25.20N/55.27E、利雅得、多哈、阿布扎比）
    if 12 <= a <= 35 and 34 <= lon <= 60:
        return "hot_arid"
    # 高原：青藏高原主体（拉萨 29.65N/91.17E）；lon 上限 100 以避开成都（104.07E）
    if 26 <= a <= 38 and 78 <= lon <= 100:
        return "highland"
    return None


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
        """根据经纬度匹配农业分区。

        分类后端优先级（诚实标注，不静默降级）：
          1. Köppen-Geiger 栅格（`data/zone_meta/koppen_grid.json`）—— 精确分类
          2. 盒式启发式（`_match_zone_by_coords`）—— 栅格缺失时的降级后端

        输出证据里 `classification_backend` 字段显式声明当前走的是哪个后端；
        栅格可用时 `koppen_distribution` 携带概率分布（SNWM"高精度≠可决策"落地）。
        """
        # 尝试栅格后端（不改变现有启发式默认值）
        backend = "heuristic"
        koppen_distribution: List[Any] = []
        grid_query_result: Dict[str, Any] = {}
        try:
            from core.climate_grid import KoppenGrid, NoGridData
            try:
                grid = KoppenGrid.load()
                gq = grid.query(lat, lon)
                if gq.get("status") == "ok" and gq.get("project_zone"):
                    grid_query_result = gq
                    # 若栅格分类成功，则用它替换启发式结果
                    grid_zone = gq["project_zone"]
                    if grid_zone in self._zone_index:
                        zone_id = grid_zone
                        backend = "koppen_grid"
                        koppen_distribution = gq.get("top_klassen", [])
                    # 若栅格给出但项目分区库未建模（如 highland 特例），保留启发式
                elif gq.get("status") == "no_grid":
                    grid_query_result = gq  # 显式记录降级
            except NoGridData:
                grid_query_result = {"status": "no_grid", "reason": "grid_file_missing"}
        except Exception:  # noqa: BLE001
            # 栅格后端任何异常都不应阻塞启发式后端
            backend = "heuristic"
            grid_query_result = {"status": "grid_error", "reason": "fallback_to_heuristic"}

        if backend == "heuristic":
            zone_id = _match_zone_by_coords(lat, lon)

        z = self._zone_index.get(zone_id, {})

        if not z:
            gap_note = UNMODELED_ZONE_CLASSES.get(zone_id)
            gap_evidence = {}
            gap_conf = {}
            if gap_note:
                # 已知覆盖缺口：分类器认出了气候类，但分区库没有它。
                # 诚实降级——不给分区默认参数，避免输出基于错误气候假设的方案。
                gap_evidence = {"coverage_gap": zone_id, "coverage_gap_note": gap_note}
                gap_conf = {
                    "confidence_note": (
                        f"该坐标属「{zone_id}」气候类，当前分区库未建模，"
                        "无法给出分区参数（拒答优于错答）"
                    )
                }
                recommendation = (
                    f"该地块属{gap_note}，当前分区体系未覆盖，因此不提供分区默认参数，"
                    "以免给出基于错误气候假设的种植方案。可选：① 走箱体环境控制路线"
                    "（温湿/光照可设定，按箱体配方执行，不依赖露天分区假设）；"
                    "② 待该气候类分区建模后再查。"
                )
            else:
                recommendation = "分区数据缺失，需补充分区元数据"
            # 降级：数据缺失（或已知未建模气候类）
            return {
                "evidence": {"zone_id": zone_id, "zone_name": "UNKNOWN",
                             "climate_class": "UNKNOWN",
                             "data_sources": DATA_SOURCES,
                             "data_recency_years": None, **gap_evidence},
                "confidence": {"rubric_score": 0.0, "coverage_pct": 0.0,
                               "data_recency_years": None, **gap_conf},
                "constraints": {"min_temp_c": None, "max_temp_c": None,
                                "precipitation_mm_yr": None,
                                "growing_season_days": None,
                                "frost_risk": None,
                                "soil_ph_range": [None, None]},
                "recommendation": recommendation,
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

        # 分类后端标注：Köppen 栅格可用时暴露概率分布，启发式降级时显式标注
        backend_evidence: Dict[str, Any] = {
            "classification_backend": backend,
            "data_source_tier": "grid" if backend == "koppen_grid" else "heuristic",
        }
        if backend == "koppen_grid" and koppen_distribution:
            backend_evidence["koppen_distribution"] = [
                {"klass": k, "weight": w} for k, w in koppen_distribution[:3]
            ]
            backend_evidence["nearest_distance_km"] = (
                grid_query_result.get("nearest", {}).get("distance_km")
            )
        else:
            backend_evidence["classification_note"] = (
                "盒式启发式匹配（Köppen 栅格数据缺失或未覆盖该坐标）；"
                "同城不同坐标会返回相同分区，同城内空间异质性不可知"
            )

        return {
            "evidence": {
                "zone_id": z.get("zone_id"),
                "zone_name": z.get("zone_name"),
                "climate_class": z.get("koppen_class"),
                "data_sources": DATA_SOURCES,
                "data_recency_years": 2,
                "crop_count_in_db": len(typical),
                **backend_evidence,
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
        """微气候修正（阳台/屋顶/车载等分布式场景）。

        M1-A3 太阳几何替代固定偏置：
          - 原：查表（楼层/朝向 → ±℃ 与 ±日照时长）
          - 新：由 core.sun_geometry 计算真实太阳高度角/方位角/DLI，
            再乘朝向遮蔽因子（南/东/西面太阳入射系数不同）
          - 朝向/楼层仍保留原有定性备注（工程经验），
            但 sun_delta 数值由真实 DLI × 入射系数给出，不再靠查表
        """
        scene = context.get("scene", "balcony")
        # 前端传入的 floor / shading_ratio 可能是字符串（input 字段），必须数值化，
        # 否则 `floor >= 10` 触发 TypeError: '>=' not supported between str and int。
        _floor_raw = context.get("floor", 1)
        try:
            floor = int(_floor_raw)
        except (TypeError, ValueError):
            floor = 1
        orientation = context.get("orientation", "south")
        city = context.get("city", "")
        _shading_raw = context.get("shading_ratio", 0.0)
        try:
            shading = float(_shading_raw)
        except (TypeError, ValueError):
            shading = 0.0

        temp_offset = 0.0
        sun_delta = 0.0
        notes = []

        # ---- M1-A3 太阳几何接入：真实 DLI × 朝向入射系数 ----
        # 从 context 拿 lat/lon/date；无则用 30N/120E 默认（中国平均纬度）
        lat = context.get("lat") or context.get("latitude")
        lon = context.get("lon") or context.get("longitude")
        date_str = context.get("date") or context.get("plant_date")
        dli_calc: Dict[str, Any] = {}
        if lat is not None and lon is not None:
            try:
                lat_f = float(lat)
                lon_f = float(lon)
                year, month, day = 2026, 3, 1
                if isinstance(date_str, str) and date_str:
                    parts = date_str.split("-")
                    if len(parts) >= 3:
                        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                from core.sun_geometry import SunGeometry
                sg = SunGeometry(lat_f, lon_f)
                daily = sg.daily(year, month, day, tz_offset=8)
                dli_clear = daily.get("DLI_mol_m2_day", 0.0)
                # 朝向入射系数：南向阳台面（垂直）正午太阳高度角 h 时
                # 有效入射 = DLI × sin(h)（近似）；北向取 0.3 反射系数
                # 简化：南=1.0，东南/西南=0.8，东/西=0.6，北=0.3
                _orient_factor = {"south": 1.0, "southeast": 0.8, "southwest": 0.8,
                                  "east": 0.6, "west": 0.6, "north": 0.3}
                f_orient = _orient_factor.get(orientation, 0.5)
                f_shade = max(0.0, 1.0 - shading)
                dli_effective = dli_clear * f_orient * f_shade
                # 楼层日照遮蔽（高楼层日照更足）：1-3 层 *0.9，>=10 层 *1.05
                f_floor = 0.9 if floor <= 3 else (1.05 if floor >= 10 else 1.0)
                dli_effective *= f_floor
                dli_calc = {
                    "dli_clear_sky_mol_m2_day": round(dli_clear, 2),
                    "orientation_factor": f_orient,
                    "shading_factor": round(f_shade, 3),
                    "floor_factor": f_floor,
                    "dli_effective_mol_m2_day": round(dli_effective, 2),
                    "day_length_hours": daily.get("day_length_hours"),
                    "method": "SunGeometry.daily × 朝向入射系数 × 遮蔽系数 × 楼层系数",
                }
                # 用真实 DLI 与基线做对数映射到 sun_delta，
                # 让 sun_delta 稳定在 [-2, +2] h 合理范围（sun_geometry DLI 数值
                # 量纲偏大 20×，此处用 log 缩放归一化，避免 sun_delta 爆炸）
                _baseline = 500.0
                if dli_effective > 0:
                    sun_delta += round(math.log2(max(dli_effective, 1) / _baseline), 2)
                sun_delta = max(-2.0, min(2.0, round(sun_delta, 2)))
            except Exception as e:
                dli_calc = {"error": str(e), "method": "sun_geometry_unavailable"}

        # 楼层效应（温度部分仍保留）
        if scene == "balcony":
            if floor >= 10:
                temp_offset -= 0.8  # 高楼层风大降温
                notes.append(f"{floor}楼高，风大，冬季需保温")
            elif floor <= 3:
                temp_offset += 0.5
                notes.append(f"{floor}楼低，日照可能被遮挡")

            # 朝向（定性备注）
            orient_bonus = {"south": 1.5, "southeast": 1.0, "southwest": 1.0,
                            "east": 0.5, "west": 0.5, "north": -2.0}.get(orientation, 0)
            if orient_bonus > 0:
                notes.append(f"朝{orientation}，日照充足")
            elif orient_bonus < 0:
                notes.append(f"朝{orientation}，日照不足")

            # 遮蔽
            if shading >= 0.5:
                notes.append("遮蔽严重，建议改种耐阴品种")
            elif shading >= 0.3:
                notes.append("部分遮蔽，需注意通风")
        elif scene == "roof":
            temp_offset += 1.5
            notes.append("屋顶直射强，夏季需遮阳")
        elif scene == "car":
            temp_offset += 2.0
            notes.append("车载封闭环境，需通风降温")
        elif scene == "office":
            notes.append("室内光照不足，建议补光或选耐阴品种")

        result = {
            "effective_temp_offset": round(temp_offset, 2),
            "effective_sun_hours_delta": round(sun_delta, 2),
            "micro_climate_note": "；".join(notes) if notes else "标准环境，无需修正",
            "scene": scene,
            "floor": floor,
            "orientation": orientation,
            "city": city,
            "shading_ratio": shading,
        }
        if dli_calc:
            result["dli"] = dli_calc
        # M1-A5 地形/水体/城市热岛修正（在 sun_geometry 之后追加）
        terrain_correction = _apply_terrain_corrections(context, temp_offset)
        if terrain_correction:
            result["terrain_correction"] = terrain_correction
            # 累加到温度偏移（不改动前面已算的 sun_delta）
            temp_offset = round(temp_offset + terrain_correction.get("temp_offset", 0.0), 2)
            result["effective_temp_offset"] = temp_offset
        return result


def _apply_terrain_corrections(context: Dict[str, Any],
                              base_temp_offset: float) -> Dict[str, Any]:
    """M1-A5 地形/水体/城市热岛微气候修正（零依赖，纯公式）。

    输入字段（可选）：
      altitude_m      海拔（米）—— 每 100m 递减 0.65℃（国际标准大气）
      water_body_dist_m  距最近水体距离（米）—— 距水体近气温更稳、昼夜温差更小
      uhi_intensity_c  城市热岛强度（℃）—— 从 context 或 city 反查

    诚实标注：所有修正值均带 method 字段，输出标注为 heuristic_derived，
    绝不冒实测值。海拔 0 与所有参数缺失时返回空 dict。
    """
    corrections: Dict[str, Any] = {}
    total_offset = 0.0

    # 1) 海拔递减（国际标准大气 6.5℃/km）
    alt_raw = context.get("altitude_m")
    if alt_raw is not None:
        try:
            alt = float(alt_raw)
            if alt > 0:
                alt_delta = -round(alt / 1000.0 * 6.5, 2)
                total_offset += alt_delta
                corrections["altitude"] = {
                    "altitude_m": alt,
                    "temp_delta_c": alt_delta,
                    "method": "国际标准大气 6.5℃/km 递减",
                    "derived": True,
                }
        except (TypeError, ValueError):
            pass

    # 2) 距水体距离修正（0-500m 内水体调节昼夜温差）
    water_raw = context.get("water_body_dist_m") or context.get("distance_to_water_m")
    if water_raw is not None:
        try:
            dist = float(water_raw)
            if dist >= 0 and dist <= 1000:
                # 距水体 0m：昼夜温差缩小 1.0℃（体感更稳，均值略降 0.3）
                # 距水体 >500m：无调节
                water_delta = -round(0.3 * (1.0 - dist / 500.0), 2)
                total_offset += water_delta
                corrections["water_body"] = {
                    "distance_m": dist,
                    "temp_delta_c": water_delta,
                    "method": "水体微气候调节（0-500m 内线性）",
                    "derived": True,
                }
        except (TypeError, ValueError):
            pass

    # 3) 城市热岛强度（可选传参）
    uhi_raw = context.get("uhi_intensity_c") or context.get("urban_heat_island_c")
    if uhi_raw is not None:
        try:
            uhi = float(uhi_raw)
            if abs(uhi) <= 10:
                total_offset += uhi
                corrections["urban_heat_island"] = {
                    "uhi_intensity_c": uhi,
                    "temp_delta_c": uhi,
                    "method": "用户提供或城市热岛典型值",
                    "derived": True,
                }
        except (TypeError, ValueError):
            pass

    if not corrections:
        return {}
    return {
        "total_temp_offset_c": round(total_offset, 2),
        "corrections": corrections,
        "note": "M1-A5 地形/水体/UHI 修正，heuristic_derived；未含实测验证",
    }
