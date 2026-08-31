"""
AgriOrchestrator - 四 Agent 串行 + 反馈闭环编排

编排逻辑：
  用户输入
    → ClimateAgent  分区匹配
    → CropAgent     作物推荐
    → GrowthAgent   种植计划生成
    → EcoAgent      生态撮合（设备/社区/供需）
    → 反馈闭环：用户种植结果 → 数据回流 → 模型迭代

对标 SwarmLabs engine/flywheel.py 的 multi-agent 串行 + 主动学习反馈闭环
"""

from typing import Dict, Any, Optional

from .climate_agent import ClimateAgent
from .crop_agent import CropAgent
from .growth_agent import GrowthAgent
from .eco_agent import EcoAgent


def _agent_score(output: Dict[str, Any]) -> float:
    """统一取 Agent 置信度：rubric_score 优先，其次 match_quality。"""
    conf = output.get("confidence", {})
    return float(conf.get("rubric_score", conf.get("match_quality", 0.0)))


class AgriOrchestrator:
    """四 Agent 串联编排器"""

    def __init__(self):
        self.climate = ClimateAgent()
        self.crop = CropAgent()
        self.growth = GrowthAgent()
        self.eco = EcoAgent()

    def run_pipeline(
        self,
        user_request: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        完整流水线：从地块信息到可执行种植方案

        参数：
            user_request: {
                "lat": 30.2741, "lon": 120.1551,  # 杭州
                "scene": "balcony",
                "floor": 15, "orientation": "south",
                "purpose": "食用",
                "space_sqm": 1.5,
                "difficulty": "beginner",
                "budget_cny": 500,
            }

        返回：
            {
                "pipeline_steps": [
                    {"agent": "ClimateAgent", "status": "ok", "output": {...}},
                    {"agent": "CropAgent", "status": "ok", "output": {...}},
                    {"agent": "GrowthAgent", "status": "ok", "output": {...}},
                    {"agent": "EcoAgent", "status": "ok", "output": {...}},
                ],
                "final_recommendation": {
                    "zone": "...",
                    "recommended_crops": [...],
                    "growth_plan": {...},
                    "devices": [...],
                    "confidence_summary": {...}
                },
                "trust_summary": {
                    "overall_rubric_score": 0.8,
                    "data_coverage": "...",
                    "known_limitations": [...]
                }
            }
        """
        # Step 1: 分区匹配
        lat, lon = user_request.get("lat", 0), user_request.get("lon", 0)
        zone_data = self.climate.match_zone(lat, lon)

        # Step 2: 微气候修正
        micro = self.climate.microclimate_adjustment(
            {
                "scene": user_request.get("scene", "balcony"),
                "floor": user_request.get("floor", 1),
                "orientation": user_request.get("orientation", "south"),
                "city": user_request.get("city", ""),
            }
        )

        # Step 3: 作物推荐
        crop_reco = self.crop.recommend(
            zone_data=zone_data,
            preferences={
                "purpose": user_request.get("purpose", "食用"),
                "space_sqm": user_request.get("space_sqm", 1.0),
                "difficulty": user_request.get("difficulty", "beginner"),
                "container": user_request.get("scene") in ["balcony", "office"],
            },
        )

        # Step 4: 种植计划（选第一个推荐作物，传入微气候与分区约束）
        growth_plan = {}
        top_crop = ""
        if crop_reco.get("recommendation"):
            top_crop = crop_reco["recommendation"][0].get("crop", "")
            growth_plan = self.growth.generate_growth_plan(
                crop=top_crop,
                zone_data=zone_data,
                start_date=user_request.get("start_date", ""),
                scene=user_request.get("scene", "balcony"),
                microclimate=micro,
            )

        # Step 5: 生态撮合
        devices = self.eco.recommend_device(
            scene=user_request.get("scene", "balcony"),
            crop=top_crop if crop_reco.get("recommendation") else "",
            zone_data=zone_data,
            budget=user_request.get("budget_cny", 0),
        )

        return {
            "pipeline_steps": [
                {"agent": "ClimateAgent", "status": "ok", "output": zone_data, "microclimate": micro},
                {"agent": "CropAgent", "status": "ok", "output": crop_reco},
                {"agent": "GrowthAgent", "status": "ok", "output": growth_plan},
                {"agent": "EcoAgent", "status": "ok", "output": devices},
            ],
            "final_recommendation": {
                "zone": zone_data.get("evidence", {}).get("zone_id", "UNKNOWN"),
                "recommended_crops": crop_reco.get("recommendation", []),
                "growth_plan": growth_plan,
                "devices": devices.get("recommendation", []),
            },
            "trust_summary": {
                "overall_rubric_score": round(
                    sum(
                        _agent_score(s["output"])
                        for s in [
                            {"output": zone_data},
                            {"output": crop_reco},
                            {"output": growth_plan},
                            {"output": devices},
                        ]
                    ) / 4, 2
                ),
                "known_limitations": [
                    "作物-分区适配为公开文献聚合，未叠加本地实测校准",
                    "病虫害诊断为轻量症状关键词匹配，未接入视觉模型",
                    "供需撮合为结构化模板，需接入真实供给方数据后生效",
                ],
            },
        }
