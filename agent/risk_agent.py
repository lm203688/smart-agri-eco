"""
⚠️ EXPERIMENTAL MOCK — 禁止生产使用 / NOT FOR PRODUCTION
======================================================
本模块是**实验性原型**，其市场风险评估依赖 MarketAgent 的**假数据**，
其余风险项亦为规则示例，不接入任何真实数据源。它**未接入** AgriOrchestrator /
MCP Server / 前端 / 单测，不代表项目具备真实风险评估能力。

与项目核心原则冲突，故保持孤儿态（已实现但不接线）：
  · 真实性红线：「真实数据、不编造」（0 用户跑不起来）——本模块使用假数据，违反此红线；
  · 商业化铁律：「只做 MCP 分发，B 端 SaaS 全否」——市场/财务/风险属 B 端 SaaS，不应进入生产路径。
保留仅为探索记录，禁止在任何生产链路中调用。

RiskAgent - 农业风险评估与管理Agent（实验性原型）

功能：
- 自然灾害风险评估（示例规则）
- 市场风险评估（依赖 MarketAgent 假数据）
- 技术风险评估（示例规则）
- 政策风险评估（示例规则）
- 风险预警与应对建议（示例）
- 风险保险推荐（示例）

数据源（原型阶段）：
- 气象数据（ClimateAgent提供）
- 市场数据（MarketAgent提供，MOCK）
- 作物数据（CropAgent提供）
- 历史风险事件库（示例）
- 保险产品数据库（示例）

输出：
- 风险评估报告（示例）
- 预警信号（示例）
- 应对建议（示例）
- 保险方案（示例）
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

# 实验性原型标记：CI / 编排器可据此跳过，禁止接入生产链路
EXPERIMENTAL = True
import math

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskAgent:
    """农业风险评估与管理Agent"""
    
    def __init__(self, orch=None):
        self.orch = orch
        self.name = "risk_agent"
        self.description = "农业风险评估与管理"
        self.version = "1.0.0"
        
        # 风险类型定义
        self.risk_types = {
            "natural": {
                "name": "自然灾害风险",
                "description": "洪涝、干旱、霜冻、台风等自然灾害风险",
                "weight": 0.4,
                "indicators": ["precipitation", "temperature", "wind_speed", "humidity"]
            },
            "market": {
                "name": "市场风险",
                "description": "价格波动、供需失衡、贸易政策等市场风险",
                "weight": 0.3,
                "indicators": ["price_volatility", "supply_demand_ratio", "trade_policy", "market_trend"]
            },
            "technical": {
                "name": "技术风险",
                "description": "病虫害、技术故障、操作失误等技术风险",
                "weight": 0.2,
                "indicators": ["disease_risk", "equipment_status", "operator_skill", "tech_reliability"]
            },
            "policy": {
                "name": "政策风险",
                "description": "补贴政策、环保要求、贸易壁垒等政策风险",
                "weight": 0.1,
                "indicators": ["subsidy_policy", "environmental_regulation", "trade_barrier", "policy_stability"]
            }
        }
        
        # 风险等级定义
        self.risk_levels = {
            "low": {"name": "低风险", "color": "green", "threshold": 0.3},
            "medium": {"name": "中等风险", "color": "yellow", "threshold": 0.6},
            "high": {"name": "高风险", "color": "orange", "threshold": 0.8},
            "critical": {"name": "极高风险", "color": "red", "threshold": 1.0}
        }
        
        # 保险产品数据库（简化版）
        self.insurance_products = {
            "crop_disaster": {
                "name": "农作物灾害保险",
                "coverage": ["洪水", "干旱", "台风", "霜冻"],
                "premium_rate": 0.02,
                "compensation_rate": 0.8,
                "requirements": ["种植面积证明", "土地承包合同"]
            },
            "price_fluctuation": {
                "name": "价格波动保险",
                "coverage": ["价格下跌", "市场波动"],
                "premium_rate": 0.015,
                "compensation_rate": 0.6,
                "requirements": ["市场价格监测", "销售合同"]
            },
            "technology_loss": {
                "name": "技术损失保险",
                "coverage": ["设备故障", "技术失误", "病虫害"],
                "premium_rate": 0.025,
                "compensation_rate": 0.7,
                "requirements": ["技术培训证明", "设备维护记录"]
            }
        }
        
        # 风险应对策略
        self.risk_strategies = {
            "avoid": {
                "name": "风险规避",
                "description": "改变种植计划，选择风险较低的作物或地区",
                "applicable_risks": ["natural", "technical"],
                "effectiveness": 0.8
            },
            "mitigate": {
                "name": "风险缓解",
                "description": "采取防护措施，降低风险发生的概率",
                "applicable_risks": ["natural", "technical"],
                "effectiveness": 0.6
            },
            "transfer": {
                "name": "风险转移",
                "description": "通过保险等方式转移风险",
                "applicable_risks": ["natural", "market", "technical"],
                "effectiveness": 0.9
            },
            "accept": {
                "name": "风险接受",
                "description": "接受风险，准备应急资金",
                "applicable_risks": ["policy", "market"],
                "effectiveness": 0.4
            }
        }
        
        # 初始化缓存
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "data", "risk_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        logger.info(f"RiskAgent initialized with {len(self.risk_types)} risk types")
    
    def assess_risk(self, location: str, crop: str, planting_date: str, 
                   current_conditions: Dict = None) -> Dict[str, Any]:
        """
        评估特定位置和作物的风险
        
        Args:
            location: 位置信息
            crop: 作物类型
            planting_date: 种植日期
            current_conditions: 当前环境条件
            
        Returns:
            风险评估结果
        """
        logger.info(f"Assessing risk for {crop} at {location}")
        
        # 获取基础数据
        climate_data = self._get_climate_data(location)
        crop_data = self._get_crop_data(crop)
        market_data = self._get_market_data(crop)
        
        # 计算各类风险评分
        risk_assessments = {}
        
        for risk_type, risk_config in self.risk_types.items():
            score = self._calculate_risk_score(
                risk_type, location, crop, planting_date,
                climate_data, crop_data, market_data, current_conditions
            )
            risk_assessments[risk_type] = {
                "score": score,
                "level": self._get_risk_level(score),
                "indicators": self._calculate_indicators(
                    risk_type, climate_data, crop_data, market_data
                ),
                "recommendations": self._get_risk_recommendations(
                    risk_type, score, location, crop
                )
            }
        
        # 计算综合风险评分
        overall_score = self._calculate_overall_risk(risk_assessments)
        
        # 生成风险预警
        warnings = self._generate_warnings(risk_assessments, location, crop)
        
        # 生成保险建议
        insurance_recommendations = self._get_insurance_recommendations(
            risk_assessments, crop, location
        )
        
        # 生成应对策略
        mitigation_strategies = self._get_mitigation_strategies(risk_assessments)
        
        # 构建完整的风险评估报告
        risk_report = {
            "location": location,
            "crop": crop,
            "planting_date": planting_date,
            "assessment_date": datetime.now().isoformat(),
            "overall_risk": {
                "score": overall_score,
                "level": self._get_risk_level(overall_score),
                "description": self._get_risk_description(overall_score)
            },
            "risk_assessments": risk_assessments,
            "warnings": warnings,
            "insurance_recommendations": insurance_recommendations,
            "mitigation_strategies": mitigation_strategies,
            "action_items": self._generate_action_items(risk_assessments),
            "confidence_score": self._calculate_confidence_score(risk_assessments)
        }
        
        # 缓存结果
        self._cache_risk_assessment(risk_report)
        
        logger.info(f"Risk assessment completed for {crop} at {location}")
        return risk_report
    
    def _calculate_risk_score(self, risk_type: str, location: str, crop: str,
                           planting_date: str, climate_data: Dict, crop_data: Dict,
                           market_data: Dict, current_conditions: Dict) -> float:
        """计算特定风险类型的评分"""
        
        if risk_type == "natural":
            return self._calculate_natural_risk(location, crop, planting_date, climate_data, current_conditions)
        elif risk_type == "market":
            return self._calculate_market_risk(crop, market_data)
        elif risk_type == "technical":
            return self._calculate_technical_risk(crop, crop_data)
        elif risk_type == "policy":
            return self._calculate_policy_risk(crop, location)
        else:
            return 0.5
    
    def _calculate_natural_risk(self, location: str, crop: str, planting_date: str,
                               climate_data: Dict, current_conditions: Dict) -> float:
        """计算自然灾害风险"""
        
        # 获取作物对气候的敏感性
        crop_sensitivity = self._get_crop_climate_sensitivity(crop)
        
        # 计算各气象因子的风险
        precipitation_risk = self._calculate_precipitation_risk(
            climate_data.get("precipitation", {}), current_conditions
        )
        temperature_risk = self._calculate_temperature_risk(
            climate_data.get("temperature", {}), current_conditions
        )
        wind_risk = self._calculate_wind_risk(climate_data.get("wind_speed", {}))
        
        # 综合计算自然灾害风险
        natural_risk = (
            precipitation_risk * 0.4 +
            temperature_risk * 0.4 +
            wind_risk * 0.2
        ) * crop_sensitivity
        
        return min(natural_risk, 1.0)
    
    def _calculate_market_risk(self, crop: str, market_data: Dict) -> float:
        """计算市场风险"""
        
        # 获取历史价格波动
        price_volatility = self._calculate_price_volatility(market_data.get("price_history", []))
        
        # 计算供需比
        supply_demand_ratio = self._calculate_supply_demand_ratio(
            market_data.get("supply", 0), market_data.get("demand", 0)
        )
        
        # 贸易政策风险
        trade_policy_risk = self._calculate_trade_policy_risk(
            market_data.get("trade_policy", {})
        )
        
        # 综合市场风险
        market_risk = (
            price_volatility * 0.4 +
            supply_demand_ratio * 0.4 +
            trade_policy_risk * 0.2
        )
        
        return min(market_risk, 1.0)
    
    def _calculate_technical_risk(self, crop: str, crop_data: Dict) -> float:
        """计算技术风险"""
        
        # 病虫害风险
        disease_risk = self._calculate_disease_risk(crop, crop_data)
        
        # 技术复杂度风险
        tech_complexity_risk = self._calculate_tech_complexity_risk(crop_data)
        
        # 操作风险
        operation_risk = self._calculate_operation_risk(crop_data)
        
        # 综合技术风险
        technical_risk = (
            disease_risk * 0.5 +
            tech_complexity_risk * 0.3 +
            operation_risk * 0.2
        )
        
        return min(technical_risk, 1.0)
    
    def _calculate_policy_risk(self, crop: str, location: str) -> float:
        """计算政策风险"""
        
        # 补贴政策风险
        subsidy_risk = self._calculate_subsidy_risk(crop, location)
        
        # 环保政策风险
        environmental_risk = self._calculate_environmental_risk(crop, location)
        
        # 贸易壁垒风险
        trade_barrier_risk = self._calculate_trade_barrier_risk(crop, location)
        
        # 综合政策风险
        policy_risk = (
            subsidy_risk * 0.4 +
            environmental_risk * 0.4 +
            trade_barrier_risk * 0.2
        )
        
        return min(policy_risk, 1.0)
    
    def _calculate_precipitation_risk(self, precipitation_data: Dict, 
                                   current_conditions: Dict) -> float:
        """计算降水风险"""
        
        if not precipitation_data:
            return 0.5
        
        # 获取月度降水数据
        monthly_precip = precipitation_data.get("monthly_precip_mm", [])
        
        if not monthly_precip:
            return 0.5
        
        # 计算降水异常度
        avg_precip = sum(monthly_precip) / len(monthly_precip)
        max_precip = max(monthly_precip)
        min_precip = min(monthly_precip)
        
        # 当前降水条件
        current_precip = current_conditions.get("precipitation", 0) if current_conditions else 0
        
        # 计算风险
        if current_precip > max_precip * 1.5:  # 过度降水
            risk = 0.8
        elif current_precip < min_precip * 0.5:  # 严重干旱
            risk = 0.9
        elif current_precip > avg_precip * 1.2:  # 偏多
            risk = 0.6
        elif current_precip < avg_precip * 0.8:  # 偏少
            risk = 0.6
        else:
            risk = 0.3
        
        return risk
    
    def _calculate_temperature_risk(self, temperature_data: Dict,
                                 current_conditions: Dict) -> float:
        """计算温度风险"""
        
        if not temperature_data:
            return 0.5
        
        # 获取月度温度数据
        monthly_temp = temperature_data.get("monthly_temp_c", [])
        
        if not monthly_temp:
            return 0.5
        
        # 计算温度范围
        avg_temp = sum(monthly_temp) / len(monthly_temp)
        max_temp = max(monthly_temp)
        min_temp = min(monthly_temp)
        
        # 当前温度条件
        current_temp = current_conditions.get("temperature", 20) if current_conditions else 20
        
        # 计算风险
        if current_temp > max_temp + 5:  # 极端高温
            risk = 0.9
        elif current_temp < min_temp - 5:  # 极端低温
            risk = 0.9
        elif current_temp > avg_temp + 3:  # 高温
            risk = 0.7
        elif current_temp < avg_temp - 3:  # 低温
            risk = 0.7
        else:
            risk = 0.3
        
        return risk
    
    def _calculate_wind_risk(self, wind_data: Dict) -> float:
        """计算风力风险"""
        
        if not wind_data:
            return 0.3
        
        # 获取风力数据
        avg_wind = wind_data.get("avg_wind_speed", 0)
        max_wind = wind_data.get("max_wind_speed", 0)
        
        # 计算风险
        if max_wind > 50:  # 台风级别
            risk = 0.9
        elif max_wind > 30:  # 大风级别
            risk = 0.7
        elif avg_wind > 20:  # 较大风力
            risk = 0.5
        else:
            risk = 0.3
        
        return risk
    
    def _calculate_price_volatility(self, price_history: List[float]) -> float:
        """计算价格波动风险"""
        
        if len(price_history) < 2:
            return 0.5
        
        # 计算价格标准差
        avg_price = sum(price_history) / len(price_history)
        variance = sum((p - avg_price) ** 2 for p in price_history) / len(price_history)
        std_dev = math.sqrt(variance)
        
        # 计算变异系数
        coefficient_of_variation = std_dev / avg_price if avg_price > 0 else 0
        
        # 转换为风险评分
        if coefficient_of_variation > 0.5:
            return 0.9
        elif coefficient_of_variation > 0.3:
            return 0.7
        elif coefficient_of_variation > 0.1:
            return 0.5
        else:
            return 0.3
    
    def _calculate_supply_demand_ratio(self, supply: float, demand: float) -> float:
        """计算供需比风险"""
        
        if supply == 0 or demand == 0:
            return 0.5
        
        ratio = supply / demand
        
        # 计算风险
        if ratio > 2.0:  # 严重供过于求
            return 0.8
        elif ratio > 1.5:  # 供过于求
            return 0.6
        elif ratio < 0.5:  # 严重供不应求
            return 0.8
        elif ratio < 0.8:  # 供不应求
            return 0.6
        else:
            return 0.3
    
    def _calculate_trade_policy_risk(self, trade_policy: Dict) -> float:
        """计算贸易政策风险"""
        
        if not trade_policy:
            return 0.3
        
        # 获取政策信息
        restrictions = trade_policy.get("restrictions", [])
        tariffs = trade_policy.get("tariffs", {})
        sanctions = trade_policy.get("sanctions", [])
        
        # 计算风险
        risk = 0.3
        
        if restrictions:
            risk += 0.2
        if tariffs:
            risk += 0.2
        if sanctions:
            risk += 0.3
        
        return min(risk, 1.0)
    
    def _calculate_disease_risk(self, crop: str, crop_data: Dict) -> float:
        """计算病虫害风险"""
        
        # 获取作物病虫害历史
        disease_history = crop_data.get("disease_history", [])
        
        if not disease_history:
            return 0.3
        
        # 计算病虫害频率
        disease_frequency = len(disease_history) / 10  # 假设10年历史
        
        # 转换为风险评分
        if disease_frequency > 0.5:
            return 0.8
        elif disease_frequency > 0.3:
            return 0.6
        elif disease_frequency > 0.1:
            return 0.4
        else:
            return 0.2
    
    def _calculate_tech_complexity_risk(self, crop_data: Dict) -> float:
        """计算技术复杂度风险"""
        
        # 获取技术复杂度指标
        tech_requirements = crop_data.get("tech_requirements", {})
        equipment_needs = crop_data.get("equipment_needs", [])
        skill_level = crop_data.get("required_skill_level", "basic")
        
        # 计算风险
        risk = 0.3
        
        if tech_requirements:
            risk += 0.2
        if len(equipment_needs) > 3:
            risk += 0.2
        
        if skill_level == "advanced":
            risk += 0.3
        elif skill_level == "intermediate":
            risk += 0.1
        
        return min(risk, 1.0)
    
    def _calculate_operation_risk(self, crop_data: Dict) -> float:
        """计算操作风险"""
        
        # 获取操作复杂度
        operation_steps = crop_data.get("operation_steps", [])
        error_rate = crop_data.get("historical_error_rate", 0.05)
        
        # 计算风险
        risk = 0.3
        
        if len(operation_steps) > 10:
            risk += 0.2
        if error_rate > 0.1:
            risk += 0.3
        elif error_rate > 0.05:
            risk += 0.1
        
        return min(risk, 1.0)
    
    def _calculate_subsidy_risk(self, crop: str, location: str) -> float:
        """计算补贴政策风险"""
        
        # 获取补贴政策变化
        policy_changes = self._get_policy_changes(crop, location, "subsidy")
        
        # 计算风险
        if len(policy_changes) > 3:
            return 0.7
        elif len(policy_changes) > 1:
            return 0.5
        else:
            return 0.3
    
    def _calculate_environmental_risk(self, crop: str, location: str) -> float:
        """计算环保政策风险"""
        
        # 获取环保要求
        environmental_requirements = self._get_environmental_requirements(crop, location)
        
        # 计算风险
        if environmental_requirements:
            return 0.6
        else:
            return 0.3
    
    def _calculate_trade_barrier_risk(self, crop: str, location: str) -> float:
        """计算贸易壁垒风险"""
        
        # 获取贸易壁垒信息
        trade_barriers = self._get_trade_barriers(crop, location)
        
        # 计算风险
        if trade_barriers:
            return 0.8
        else:
            return 0.3
    
    def _get_risk_level(self, score: float) -> str:
        """根据评分获取风险等级"""
        
        if score >= self.risk_levels["critical"]["threshold"]:
            return "critical"
        elif score >= self.risk_levels["high"]["threshold"]:
            return "high"
        elif score >= self.risk_levels["medium"]["threshold"]:
            return "medium"
        else:
            return "low"
    
    def _get_risk_description(self, score: float) -> str:
        """获取风险描述"""
        
        level = self._get_risk_level(score)
        
        descriptions = {
            "low": "风险较低，可以正常进行农业生产",
            "medium": "存在一定风险，需要关注并采取适当措施",
            "high": "风险较高，建议采取积极的风险管理措施",
            "critical": "风险极高，建议重新评估生产计划"
        }
        
        return descriptions.get(level, "风险未知")
    
    def _calculate_indicators(self, risk_type: str, climate_data: Dict,
                            crop_data: Dict, market_data: Dict) -> Dict[str, float]:
        """计算风险指标"""
        
        indicators = {}
        
        if risk_type == "natural":
            indicators["precipitation_risk"] = self._calculate_precipitation_risk(
                climate_data.get("precipitation", {}), {}
            )
            indicators["temperature_risk"] = self._calculate_temperature_risk(
                climate_data.get("temperature", {}), {}
            )
            indicators["wind_risk"] = self._calculate_wind_risk(
                climate_data.get("wind_speed", {})
            )
        
        elif risk_type == "market":
            indicators["price_volatility"] = self._calculate_price_volatility(
                market_data.get("price_history", [])
            )
            indicators["supply_demand_ratio"] = self._calculate_supply_demand_ratio(
                market_data.get("supply", 0), market_data.get("demand", 0)
            )
            indicators["trade_policy_risk"] = self._calculate_trade_policy_risk(
                market_data.get("trade_policy", {})
            )
        
        elif risk_type == "technical":
            indicators["disease_risk"] = self._calculate_disease_risk(
                crop_data.get("crop_type", ""), crop_data
            )
            indicators["tech_complexity_risk"] = self._calculate_tech_complexity_risk(
                crop_data
            )
            indicators["operation_risk"] = self._calculate_operation_risk(
                crop_data
            )
        
        elif risk_type == "policy":
            indicators["subsidy_risk"] = 0.5  # 简化处理
            indicators["environmental_risk"] = self._calculate_environmental_risk(
                crop_data.get("crop_type", ""), ""
            )
            indicators["trade_barrier_risk"] = self._calculate_trade_barrier_risk(
                crop_data.get("crop_type", ""), ""
            )
        
        return indicators
    
    def _get_risk_recommendations(self, risk_type: str, score: float,
                                location: str, crop: str) -> List[str]:
        """获取风险建议"""
        
        recommendations = []
        
        if risk_type == "natural":
            if score > 0.7:
                recommendations.extend([
                    "考虑购买农业保险",
                    "加强农田水利设施建设",
                    "建立灾害预警系统",
                    "准备应急物资"
                ])
            elif score > 0.5:
                recommendations.extend([
                    "关注天气预报",
                    "加强田间管理",
                    "准备防护设施"
                ])
        
        elif risk_type == "market":
            if score > 0.7:
                recommendations.extend([
                    "多元化销售渠道",
                    "考虑价格保险",
                    "与加工企业签订长期合同",
                    "关注市场动态"
                ])
            elif score > 0.5:
                recommendations.extend([
                    "定期分析市场趋势",
                    "优化生产计划",
                    "建立客户关系"
                ])
        
        elif risk_type == "technical":
            if score > 0.7:
                recommendations.extend([
                    "加强技术培训",
                    "更新生产设备",
                    "建立病虫害监测系统",
                    "制定应急预案"
                ])
            elif score > 0.5:
                recommendations.extend([
                    "定期维护设备",
                    "加强技术学习",
                    "记录生产数据"
                ])
        
        elif risk_type == "policy":
            if score > 0.7:
                recommendations.extend([
                    "关注政策变化",
                    "咨询专业意见",
                    "调整生产结构",
                    "寻求政策支持"
                ])
            elif score > 0.5:
                recommendations.extend([
                    "定期了解政策信息",
                    "合规经营",
                    "参与行业协会"
                ])
        
        return recommendations
    
    def _calculate_overall_risk(self, risk_assessments: Dict) -> float:
        """计算综合风险评分"""
        
        total_score = 0.0
        total_weight = 0.0
        
        for risk_type, assessment in risk_assessments.items():
            weight = self.risk_types[risk_type]["weight"]
            score = assessment["score"]
            total_score += score * weight
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.5
    
    def _generate_warnings(self, risk_assessments: Dict, location: str, crop: str) -> List[Dict]:
        """生成风险预警"""
        
        warnings = []
        
        for risk_type, assessment in risk_assessments.items():
            if assessment["score"] > 0.7:
                warnings.append({
                    "type": risk_type,
                    "level": assessment["level"],
                    "message": f"{self.risk_types[risk_type]['name']}风险较高：{assessment['score']:.2f}",
                    "recommendations": assessment["recommendations"][:3]  # 取前3个建议
                })
        
        return warnings
    
    def _get_insurance_recommendations(self, risk_assessments: Dict, crop: str,
                                    location: str) -> List[Dict]:
        """获取保险建议"""
        
        recommendations = []
        
        # 根据风险评估结果推荐保险
        if any(assessment["score"] > 0.6 for assessment in risk_assessments.values()):
            # 自然灾害风险高
            if risk_assessments["natural"]["score"] > 0.6:
                recommendations.append({
                    "type": "crop_disaster",
                    "product": self.insurance_products["crop_disaster"],
                    "priority": "high"
                })
            
            # 市场风险高
            if risk_assessments["market"]["score"] > 0.6:
                recommendations.append({
                    "type": "price_fluctuation",
                    "product": self.insurance_products["price_fluctuation"],
                    "priority": "medium"
                })
            
            # 技术风险高
            if risk_assessments["technical"]["score"] > 0.6:
                recommendations.append({
                    "type": "technology_loss",
                    "product": self.insurance_products["technology_loss"],
                    "priority": "medium"
                })
        
        return recommendations
    
    def _get_mitigation_strategies(self, risk_assessments: Dict) -> List[Dict]:
        """获取缓解策略"""
        
        strategies = []
        
        for risk_type, assessment in risk_assessments.items():
            if assessment["score"] > 0.5:
                # 选择最合适的策略
                if risk_type in ["natural", "technical"]:
                    strategy = self.risk_strategies["mitigate"]
                elif risk_type in ["market", "technical"]:
                    strategy = self.risk_strategies["transfer"]
                else:
                    strategy = self.risk_strategies["accept"]
                
                strategies.append({
                    "type": risk_type,
                    "strategy": strategy,
                    "effectiveness": strategy["effectiveness"],
                    "applicability": self._assess_strategy_applicability(
                        strategy, risk_type, assessment["score"]
                    )
                })
        
        return strategies
    
    def _assess_strategy_applicability(self, strategy: Dict, risk_type: str,
                                     score: float) -> float:
        """评估策略适用性"""
        
        if risk_type not in strategy["applicable_risks"]:
            return 0.0
        
        # 根据风险评分调整适用性
        if score > 0.8:
            return strategy["effectiveness"] * 1.0
        elif score > 0.6:
            return strategy["effectiveness"] * 0.8
        elif score > 0.4:
            return strategy["effectiveness"] * 0.6
        else:
            return strategy["effectiveness"] * 0.4
    
    def _generate_action_items(self, risk_assessments: Dict) -> List[Dict]:
        """生成行动项目"""
        
        action_items = []
        
        for risk_type, assessment in risk_assessments.items():
            if assessment["score"] > 0.5:
                action_items.append({
                    "type": "monitor",
                    "risk_type": risk_type,
                    "description": f"持续监控{self.risk_types[risk_type]['name']}",
                    "priority": "high" if assessment["score"] > 0.7 else "medium"
                })
                
                action_items.append({
                    "type": "mitigate",
                    "risk_type": risk_type,
                    "description": f"实施{self.risk_types[risk_type]['name']}缓解措施",
                    "priority": "high" if assessment["score"] > 0.7 else "medium"
                })
        
        return action_items
    
    def _calculate_confidence_score(self, risk_assessments: Dict) -> float:
        """计算风险评估置信度"""
        
        # 简化的置信度计算
        total_score = 0.0
        count = 0
        
        for assessment in risk_assessments.values():
            # 基于数据完整性和历史准确性计算置信度
            confidence = 0.7  # 基础置信度
            if assessment["score"] > 0.8:
                confidence += 0.1
            elif assessment["score"] < 0.3:
                confidence += 0.05
            
            total_score += confidence
            count += 1
        
        return total_score / count if count > 0 else 0.5
    
    def _get_climate_data(self, location: str) -> Dict:
        """获取气候数据"""
        
        # 简化的气候数据获取
        # 实际应用中应该从ClimateAgent获取
        return {
            "precipitation": {
                "monthly_precip_mm": [50, 60, 80, 120, 180, 200, 150, 120, 80, 60, 40, 30]
            },
            "temperature": {
                "monthly_temp_c": [5, 8, 15, 20, 25, 30, 32, 30, 25, 18, 10, 6]
            },
            "wind_speed": {
                "avg_wind_speed": 15,
                "max_wind_speed": 35
            }
        }
    
    def _get_crop_data(self, crop: str) -> Dict:
        """获取作物数据"""
        
        # 简化的作物数据获取
        # 实际应用中应该从CropAgent获取
        return {
            "crop_type": crop,
            "tech_requirements": {
                "irrigation": True,
                "fertilization": True,
                "pest_control": True
            },
            "equipment_needs": ["tractor", "irrigation_system", "harvester"],
            "required_skill_level": "intermediate",
            "operation_steps": ["land_preparation", "planting", "irrigation", "fertilization", "pest_control", "harvesting"],
            "historical_error_rate": 0.05,
            "disease_history": ["rust_2020", "blight_2021"]
        }
    
    def _get_market_data(self, crop: str) -> Dict:
        """获取市场数据"""
        
        # 简化的市场数据获取
        # 实际应用中应该从MarketAgent获取
        return {
            "price_history": [2.5, 2.8, 3.2, 2.9, 3.5, 3.1, 2.7, 3.0, 3.3, 2.8, 3.1, 2.9],
            "supply": 1000,
            "demand": 800,
            "trade_policy": {
                "restrictions": [],
                "tariffs": {},
                "sanctions": []
            }
        }
    
    def _get_crop_climate_sensitivity(self, crop: str) -> float:
        """获取作物对气候的敏感性"""
        
        sensitivities = {
            "wheat": 0.6,
            "corn": 0.7,
            "rice": 0.5,
            "vegetables": 0.8,
            "fruits": 0.9
        }
        
        return sensitivities.get(crop, 0.6)
    
    def _get_policy_changes(self, crop: str, location: str, policy_type: str) -> List[str]:
        """获取政策变化"""
        
        # 简化的政策变化获取
        return []
    
    def _get_environmental_requirements(self, crop: str, location: str) -> List[str]:
        """获取环保要求"""
        
        # 简化的环保要求获取
        return []
    
    def _get_trade_barriers(self, crop: str, location: str) -> List[str]:
        """获取贸易壁垒"""
        
        # 简化的贸易壁垒获取
        return []
    
    def _cache_risk_assessment(self, risk_report: Dict):
        """缓存风险评估结果"""
        
        cache_file = os.path.join(
            self.cache_dir,
            f"risk_assessment_{risk_report['location']}_{risk_report['crop']}.json"
        )
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(risk_report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to cache risk assessment: {e}")
    
    def get_risk_alerts(self, location: str, crop: str) -> List[Dict]:
        """获取风险预警"""
        
        alerts = []
        
        # 检查缓存中的风险评估
        cache_file = os.path.join(
            self.cache_dir,
            f"risk_assessment_{location}_{crop}.json"
        )
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    risk_report = json.load(f)
                
                # 检查是否有高风险预警
                for warning in risk_report.get("warnings", []):
                    if warning["level"] in ["high", "critical"]:
                        alerts.append(warning)
                
            except Exception as e:
                logger.error(f"Failed to load risk assessment from cache: {e}")
        
        return alerts
    
    def get_risk_summary(self, location: str) -> Dict:
        """获取风险摘要"""
        
        summary = {
            "location": location,
            "total_crops": 0,
            "high_risk_crops": 0,
            "medium_risk_crops": 0,
            "low_risk_crops": 0,
            "risk_distribution": {},
            "top_risks": []
        }
        
        # 获取所有作物的风险评估
        cache_files = [f for f in os.listdir(self.cache_dir) if f.startswith("risk_assessment_")]
        
        for cache_file in cache_files:
            try:
                with open(os.path.join(self.cache_dir, cache_file), 'r', encoding='utf-8') as f:
                    risk_report = json.load(f)
                
                crop = risk_report["crop"]
                overall_score = risk_report["overall_risk"]["score"]
                level = risk_report["overall_risk"]["level"]
                
                summary["total_crops"] += 1
                
                if level == "high":
                    summary["high_risk_crops"] += 1
                elif level == "medium":
                    summary["medium_risk_crops"] += 1
                else:
                    summary["low_risk_crops"] += 1
                
                # 记录风险分布
                if level not in summary["risk_distribution"]:
                    summary["risk_distribution"][level] = 0
                summary["risk_distribution"][level] += 1
                
                # 记录主要风险
                for risk_type, assessment in risk_report["risk_assessments"].items():
                    if assessment["score"] > 0.6:
                        summary["top_risks"].append({
                            "crop": crop,
                            "risk_type": risk_type,
                            "score": assessment["score"],
                            "level": assessment["level"]
                        })
                
            except Exception as e:
                logger.error(f"Failed to load risk assessment from {cache_file}: {e}")
        
        return summary
    
    def analyze_risk_trends(self, location: str, days: int = 30) -> Dict:
        """分析风险趋势"""
        
        trends = {
            "location": location,
            "period_days": days,
            "trend_data": {},
            "trend_analysis": {},
            "recommendations": []
        }
        
        # 简化的趋势分析
        # 实际应用中应该分析历史风险评估数据
        
        for risk_type in self.risk_types.keys():
            trends["trend_data"][risk_type] = {
                "current_score": 0.5,
                "previous_score": 0.4,
                "change": 0.1,
                "trend": "increasing"
            }
            
            # 趋势分析
            if trends["trend_data"][risk_type]["change"] > 0.1:
                trends["trend_analysis"][risk_type] = "风险呈上升趋势，需要关注"
            elif trends["trend_data"][risk_type]["change"] < -0.1:
                trends["trend_analysis"][risk_type] = "风险呈下降趋势，情况有所改善"
            else:
                trends["trend_analysis"][risk_type] = "风险相对稳定"
        
        # 生成建议
        for risk_type, analysis in trends["trend_analysis"].items():
            if "上升趋势" in analysis:
                trends["recommendations"].append(
                    f"{self.risk_types[risk_type]['name']}呈上升趋势，建议加强防范"
                )
        
        return trends
    
    def export_risk_report(self, risk_report: Dict, format_type: str = "json") -> str:
        """导出风险报告"""
        
        if format_type == "json":
            return json.dumps(risk_report, ensure_ascii=False, indent=2)
        elif format_type == "csv":
            # 简化的CSV格式
            lines = ["风险类型,评分,等级,建议"]
            for risk_type, assessment in risk_report["risk_assessments"].items():
                line = f"{self.risk_types[risk_type]['name']},{assessment['score']:.2f},{assessment['level']},"
                line += ";".join(assessment["recommendations"][:2])
                lines.append(line)
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format_type}")
    
    def get_risk_insights(self, location: str) -> Dict:
        """获取风险洞察"""
        
        insights = {
            "location": location,
            "risk_patterns": {},
            "seasonal_risks": {},
            "recommendations": []
        }
        
        # 分析风险模式
        cache_files = [f for f in os.listdir(self.cache_dir) if f.startswith("risk_assessment_")]
        
        for cache_file in cache_files:
            try:
                with open(os.path.join(self.cache_dir, cache_file), 'r', encoding='utf-8') as f:
                    risk_report = json.load(f)
                
                # 分析季节性风险
                planting_month = int(risk_report["planting_date"].split("-")[1])
                season = self._get_season(planting_month)
                
                if season not in insights["seasonal_risks"]:
                    insights["seasonal_risks"][season] = {
                        "total_risk": 0,
                        "count": 0,
                        "risk_types": {}
                    }
                
                season_data = insights["seasonal_risks"][season]
                season_data["total_risk"] += risk_report["overall_risk"]["score"]
                season_data["count"] += 1
                
                for risk_type, assessment in risk_report["risk_assessments"].items():
                    if risk_type not in season_data["risk_types"]:
                        season_data["risk_types"][risk_type] = []
                    season_data["risk_types"][risk_type].append(assessment["score"])
                
            except Exception as e:
                logger.error(f"Failed to load risk assessment from {cache_file}: {e}")
        
        # 计算平均风险
        for season, data in insights["seasonal_risks"].items():
            if data["count"] > 0:
                data["avg_risk"] = data["total_risk"] / data["count"]
            else:
                data["avg_risk"] = 0
            
            # 计算各风险类型的平均风险
            for risk_type, scores in data["risk_types"].items():
                data["risk_types"][risk_type] = sum(scores) / len(scores)
        
        # 生成洞察
        for season, data in insights["seasonal_risks"].items():
            if data["avg_risk"] > 0.7:
                insights["recommendations"].append(
                    f"{season}季节风险较高，建议加强风险管理"
                )
        
        return insights
    
    def _get_season(self, month: int) -> str:
        """根据月份获取季节"""
        
        if month in [12, 1, 2]:
            return "冬季"
        elif month in [3, 4, 5]:
            return "春季"
        elif month in [6, 7, 8]:
            return "夏季"
        else:
            return "秋季"