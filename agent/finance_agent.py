"""
⚠️ EXPERIMENTAL MOCK — 禁止生产使用 / NOT FOR PRODUCTION
======================================================
本模块是**实验性原型**，成本核算/收益/ROI 等为**硬编码公式与示例数据**，
不接入任何真实数据源。它**未接入** AgriOrchestrator / MCP Server / 前端 / 单测，
不代表项目具备真实财务分析能力。

与项目核心原则冲突，故保持孤儿态（已实现但不接线）：
  · 真实性红线：「真实数据、不编造」（0 用户跑不起来）——本模块使用假数据，违反此红线；
  · 商业化铁律：「只做 MCP 分发，B 端 SaaS 全否」——市场/财务/风险属 B 端 SaaS，不应进入生产路径。
保留仅为探索记录，禁止在任何生产链路中调用。

FinanceAgent - 农业财务规划与投资分析（实验性原型）

功能：
- 种植成本核算（MOCK）
- 收益预测模型（MOCK）
- 投资回报分析（MOCK）
- 补贴政策查询（MOCK）
- 融资方案推荐（MOCK）

作者：智慧农业生态团队
创建日期：2026-01-15
"""

import json
try:  # 零依赖保护：requests 非本项目依赖，仅实验性代码可能引用
    import requests
except ImportError:
    requests = None  # 生产环境无此依赖；本模块不可用于生产
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import time

# 实验性原型标记：CI / 编排器可据此跳过，禁止接入生产链路
EXPERIMENTAL = True

# 数据模型
class Scale(Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

class InvestmentType(Enum):
    SEEDS = "seeds"
    FERTILIZERS = "fertilizers"
    EQUIPMENT = "equipment"
    LABOR = "labor"
    LAND = "land"
    INFRASTRUCTURE = "infrastructure"

@dataclass
class CostBreakdown:
    """成本分解模型"""
    crop: str
    scale: Scale
    location: str
    total_cost: float
    cost_by_category: Dict[str, float]
    cost_by_item: Dict[str, float]
    cost_trend: str
    cost_efficiency: float

@dataclass
class RevenueProjection:
    """收益预测模型"""
    crop: str
    scale: Scale
    location: str
    total_revenue: float
    revenue_by_source: Dict[str, float]
    revenue_trend: str
    market_price: float
    expected_yield: float
    revenue_confidence: float

@dataclass
class ROIAnalysis:
    """投资回报分析模型"""
    crop: str
    scale: Scale
    location: str
    total_investment: float
    total_revenue: float
    net_profit: float
    roi_percentage: float
    payback_period: float
    npv: float
    irr: float
    risk_level: str

@dataclass
class SubsidyInfo:
    """补贴信息模型"""
    subsidy_type: str
    amount: float
    eligibility_criteria: List[str]
    application_deadline: Optional[datetime]
    contact_info: Dict[str, str]
    approval_rate: float
    processing_time: str

@dataclass
class FinancingOption:
    """融资方案模型"""
    option_type: str
    provider: str
    interest_rate: float
    term_years: int
    max_amount: float
    requirements: List[str]
    advantages: List[str]
    disadvantages: List[str]
    approval_rate: float

class FinanceAgent:
    """农业财务规划与投资分析Agent"""
    
    def __init__(self):
        self.cost_models = {
            'small_scale': self._calculate_small_scale_costs,
            'medium_scale': self._calculate_medium_scale_costs,
            'large_scale': self._calculate_large_scale_costs
        }
        
        self.revenue_models = {
            'basic': self._basic_revenue_projection,
            'market_adjusted': self._market_adjusted_revenue,
            'optimistic': self._optimistic_revenue_projection
        }
        
        self.roi_models = {
            'simple': self._simple_roi_calculation,
            'detailed': self._detailed_roi_analysis,
            'risk_adjusted': self._risk_adjusted_roi
        }
        
        self.subsidy_database = self._load_subsidy_database()
        self.financing_options = self._load_financing_options()
        
        self.cache = {}
        self.cache_ttl = 3600  # 1小时缓存
        
    def analyze_finance(self, crop: str, scale: str, location: str, 
                       investment_budget: float = None, timeframe: str = "1年") -> Dict[str, Any]:
        """
        分析农业财务状况
        
        Args:
            crop: 作物名称
            scale: 种植规模（small/medium/large）
            location: 种植地点
            investment_budget: 投资预算（可选）
            timeframe: 投资期限（可选）
            
        Returns:
            {
                "cost_breakdown": {...},
                "revenue_projection": {...},
                "roi_analysis": {...},
                "subsidy_info": [...],
                "financing_options": [...],
                "risk_assessment": {...},
                "recommendations": [...],
                "confidence": {...},
                "signature": str
            }
        """
        try:
            # 验证输入
            if not crop or not crop.strip():
                raise ValueError("作物名称不能为空")
                
            crop = crop.strip()
            scale = Scale(scale.lower())
            location = location.strip() if location else None
            
            # 检查缓存
            cache_key = f"{crop}_{scale.value}_{location}_{investment_budget}_{timeframe}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
                
            # 执行财务分析
            result = {
                "cost_breakdown": self._calculate_cost_breakdown(crop, scale, location),
                "revenue_projection": self._calculate_revenue_projection(crop, scale, location),
                "roi_analysis": self._calculate_roi_analysis(crop, scale, location, investment_budget),
                "subsidy_info": self._get_subsidy_info(crop, location),
                "financing_options": self._get_financing_options(crop, scale, investment_budget),
                "risk_assessment": self._assess_financial_risk(crop, scale, location),
                "recommendations": self._generate_recommendations(crop, scale, location, investment_budget),
                "confidence": self._calculate_confidence(crop, scale, location),
                "signature": self._generate_signature(crop, scale, location)
            }
            
            # 缓存结果
            self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "crop": crop,
                "scale": scale.value,
                "location": location,
                "timestamp": datetime.now().isoformat(),
                "timeframe": timeframe
            }
    
    def _calculate_cost_breakdown(self, crop: str, scale: Scale, location: str) -> CostBreakdown:
        """计算成本分解"""
        # 根据规模选择成本模型
        cost_model = self.cost_models.get(f'{scale.value}_scale')
        if not cost_model:
            raise ValueError(f"不支持的规模类型: {scale}")
            
        cost_data = cost_model(crop, location)
        
        # 计算成本效率
        cost_efficiency = self._calculate_cost_efficiency(cost_data)
        
        return CostBreakdown(
            crop=crop,
            scale=scale,
            location=location,
            total_cost=cost_data['total_cost'],
            cost_by_category=cost_data['by_category'],
            cost_by_item=cost_data['by_item'],
            cost_trend=cost_data['trend'],
            cost_efficiency=cost_efficiency
        )
    
    def _calculate_revenue_projection(self, crop: str, scale: Scale, location: str) -> RevenueProjection:
        """计算收益预测"""
        # 获取市场价格
        market_price = self._get_market_price(crop, location)
        
        # 计算预期产量
        expected_yield = self._calculate_expected_yield(crop, scale, location)
        
        # 使用多种收益模型
        revenue_projections = []
        for model_name, model_func in self.revenue_models.items():
            try:
                projection = model_func(crop, scale, location, market_price, expected_yield)
                revenue_projections.append(projection)
            except Exception as e:
                print(f"收益模型 {model_name} 失败: {e}")
                
        # 综合收益预测
        if revenue_projections:
            # 使用加权平均
            weights = [0.4, 0.4, 0.2]  # 基础模型、市场调整模型、乐观模型的权重
            final_projection = self._combine_revenue_projections(revenue_projections, weights)
        else:
            # 如果所有模型都失败，使用简单计算
            final_projection = self._simple_revenue_projection(crop, scale, location, market_price, expected_yield)
            
        return final_projection
    
    def _calculate_roi_analysis(self, crop: str, scale: Scale, location: str, 
                              investment_budget: float = None) -> ROIAnalysis:
        """计算投资回报分析"""
        # 获取成本分解
        cost_breakdown = self._calculate_cost_breakdown(crop, scale, location)
        
        # 获取收益预测
        revenue_projection = self._calculate_revenue_projection(crop, scale, location)
        
        # 计算总投资
        if investment_budget:
            total_investment = investment_budget
        else:
            total_investment = cost_breakdown.total_cost
            
        # 计算净收益
        net_profit = revenue_projection.total_revenue - total_investment
        
        # 计算ROI
        roi_percentage = (net_profit / total_investment) * 100 if total_investment > 0 else 0
        
        # 计算回收期
        payback_period = self._calculate_payback_period(total_investment, revenue_projection.total_revenue)
        
        # 计算NPV和IRR
        npv, irr = self._calculate_npv_irr(total_investment, revenue_projection.total_revenue, 5)  # 5年期限
        
        # 评估风险等级
        risk_level = self._assess_financial_risk_level(roi_percentage, payback_period, npv, irr)
        
        return ROIAnalysis(
            crop=crop,
            scale=scale,
            location=location,
            total_investment=total_investment,
            total_revenue=revenue_projection.total_revenue,
            net_profit=net_profit,
            roi_percentage=roi_percentage,
            payback_period=payback_period,
            npv=npv,
            irr=irr,
            risk_level=risk_level
        )
    
    def _get_subsidy_info(self, crop: str, location: str) -> List[SubsidyInfo]:
        """获取补贴信息"""
        subsidies = []
        
        # 从补贴数据库中查找相关补贴
        for subsidy in self.subsidy_database:
            if subsidy['crop'] == crop or subsidy['crop'] == 'all':
                if subsidy['region'] == location or subsidy['region'] == 'all':
                    subsidies.append(SubsidyInfo(
                        subsidy_type=subsidy['type'],
                        amount=subsidy['amount'],
                        eligibility_criteria=subsidy['criteria'],
                        application_deadline=subsidy.get('deadline'),
                        contact_info=subsidy['contact'],
                        approval_rate=subsidy['approval_rate'],
                        processing_time=subsidy['processing_time']
                    ))
                    
        return subsidies
    
    def _get_financing_options(self, crop: str, scale: Scale, investment_budget: float = None) -> List[FinancingOption]:
        """获取融资方案"""
        options = []
        
        # 根据作物和规模筛选融资方案
        for option in self.financing_options:
            # 检作物匹配
            if option['crop'] == crop or option['crop'] == 'all':
                # 检规模匹配
                if option['scale'] == scale.value or option['scale'] == 'all':
                    # 检预算匹配
                    if not investment_budget or option['min_amount'] <= investment_budget <= option['max_amount']:
                        options.append(FinancingOption(
                            option_type=option['type'],
                            provider=option['provider'],
                            interest_rate=option['interest_rate'],
                            term_years=option['term'],
                            max_amount=option['max_amount'],
                            requirements=option['requirements'],
                            advantages=option['advantages'],
                            disadvantages=option['disadvantages'],
                            approval_rate=option['approval_rate']
                        ))
                        
        return options
    
    def _assess_financial_risk(self, crop: str, scale: Scale, location: str) -> Dict[str, Any]:
        """评估财务风险"""
        # 获取ROI分析
        roi_analysis = self._calculate_roi_analysis(crop, scale, location)
        
        # 评估各种风险
        risks = {
            "market_risk": self._assess_market_risk(crop, location),
            "operational_risk": self._assess_operational_risk(crop, scale, location),
            "financial_risk": self._assess_financial_risk_level_details(roi_analysis),
            "policy_risk": self._assess_policy_risk(crop, location)
        }
        
        # 计算总体风险评分
        overall_risk = self._calculate_overall_risk(risks)
        
        return {
            "risks": risks,
            "overall_risk": overall_risk,
            "risk_level": self._get_risk_level(overall_risk),
            "risk_mitigation": self._generate_risk_mitigation_strategies(risks)
        }
    
    def _generate_recommendations(self, crop: str, scale: Scale, location: str, 
                                investment_budget: float = None) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于ROI分析生成建议
        roi_analysis = self._calculate_roi_analysis(crop, scale, location, investment_budget)
        
        if roi_analysis.roi_percentage > 20:
            recommendations.append(f"投资回报率 {roi_analysis.roi_percentage:.1f}% 较高，建议投资")
        elif roi_analysis.roi_percentage > 10:
            recommendations.append(f"投资回报率 {roi_analysis.roi_percentage:.1f}% 一般，建议谨慎考虑")
        else:
            recommendations.append(f"投资回报率 {roi_analysis.roi_percentage:.1f}% 较低，建议重新评估")
            
        # 基于回收期生成建议
        if roi_analysis.payback_period < 2:
            recommendations.append(f"回收期 {roi_analysis.payback_period:.1f} 年较短，资金周转快")
        elif roi_analysis.payback_period < 4:
            recommendations.append(f"回收期 {roi_analysis.payback_period:.1f} 年适中")
        else:
            recommendations.append(f"回收期 {roi_analysis.payback_period:.1f} 年较长，需考虑资金压力")
            
        # 基于补贴信息生成建议
        subsidies = self._get_subsidy_info(crop, location)
        if subsidies:
            total_subsidy = sum(s.amount for s in subsidies)
            recommendations.append(f"可获得补贴共计 {total_subsidy:.0f} 元，建议申请")
            
        # 基于融资方案生成建议
        financing_options = self._get_financing_options(crop, scale, investment_budget)
        if financing_options:
            best_option = min(financing_options, key=lambda x: x.interest_rate)
            recommendations.append(f"建议考虑 {best_option.provider} 的融资方案，利率 {best_option.interest_rate:.1f}%")
            
        return recommendations
    
    def _calculate_confidence(self, crop: str, scale: Scale, location: str) -> Dict[str, float]:
        """计算置信度"""
        confidence = {
            "data_quality": 0.8,  # 数据质量置信度
            "model_accuracy": 0.75,  # 模型准确度置信度
            "market_stability": 0.7,  # 市场稳定性置信度
            "overall": 0.75  # 总体置信度
        }
        
        # 根据具体情况调整置信度
        if location:
            confidence["data_quality"] += 0.1
            confidence["overall"] += 0.05
            
        if scale == Scale.LARGE:
            confidence["model_accuracy"] += 0.1
            confidence["overall"] += 0.05
            
        return confidence
    
    def _generate_signature(self, crop: str, scale: Scale, location: str) -> str:
        """生成数字签名"""
        timestamp = datetime.now().isoformat()
        data_str = f"{crop}_{scale.value}_{location}_{timestamp}"
        
        # 使用HMAC-SHA256生成签名
        key = "finance_agent_secret_key"  # 在实际应用中应该使用安全的密钥管理
        signature = hmac.new(key.encode(), data_str.encode(), hashlib.sha256).hexdigest()
        
        return signature
    
    # 成本计算方法
    def _calculate_small_scale_costs(self, crop: str, location: str) -> Dict[str, Any]:
        """计算小规模种植成本"""
        base_cost = 5000 + hash(crop) % 2000  # 基础成本
        
        # 按类别分解
        by_category = {
            "种子": base_cost * 0.15,
            "肥料": base_cost * 0.20,
            "农药": base_cost * 0.10,
            "人工": base_cost * 0.35,
            "设备": base_cost * 0.15,
            "其他": base_cost * 0.05
        }
        
        # 按项目分解
        by_item = {
            "种子费用": by_category["种子"],
            "肥料费用": by_category["肥料"],
            "农药费用": by_category["农药"],
            "人工费用": by_category["人工"],
            "设备折旧": by_category["设备"],
            "土地租金": base_cost * 0.08,
            "水电费": base_cost * 0.07,
            "其他杂费": by_category["其他"]
        }
        
        return {
            "total_cost": base_cost,
            "by_category": by_category,
            "by_item": by_item,
            "trend": "稳定",
            "unit_cost": base_cost / 10  # 假设10亩
        }
    
    def _calculate_medium_scale_costs(self, crop: str, location: str) -> Dict[str, Any]:
        """计算中等规模种植成本"""
        base_cost = 20000 + hash(crop) % 8000  # 基础成本
        
        # 按类别分解
        by_category = {
            "种子": base_cost * 0.10,
            "肥料": base_cost * 0.18,
            "农药": base_cost * 0.08,
            "人工": base_cost * 0.30,
            "设备": base_cost * 0.25,
            "其他": base_cost * 0.07
        }
        
        # 按项目分解
        by_item = {
            "种子费用": by_category["种子"],
            "肥料费用": by_category["肥料"],
            "农药费用": by_category["农药"],
            "人工费用": by_category["人工"],
            "设备折旧": by_category["设备"],
            "土地租金": base_cost * 0.12,
            "水电费": base_cost * 0.10,
            "其他杂费": by_category["其他"]
        }
        
        return {
            "total_cost": base_cost,
            "by_category": by_category,
            "by_item": by_item,
            "trend": "微涨",
            "unit_cost": base_cost / 50  # 假设50亩
        }
    
    def _calculate_large_scale_costs(self, crop: str, location: str) -> Dict[str, Any]:
        """计算大规模种植成本"""
        base_cost = 100000 + hash(crop) % 40000  # 基础成本
        
        # 按类别分解
        by_category = {
            "种子": base_cost * 0.08,
            "肥料": base_cost * 0.15,
            "农药": base_cost * 0.06,
            "人工": base_cost * 0.25,
            "设备": base_cost * 0.35,
            "其他": base_cost * 0.09
        }
        
        # 按项目分解
        by_item = {
            "种子费用": by_category["种子"],
            "肥料费用": by_category["肥料"],
            "农药费用": by_category["农药"],
            "人工费用": by_category["人工"],
            "设备折旧": by_category["设备"],
            "土地租金": base_cost * 0.15,
            "水电费": base_cost * 0.12,
            "其他杂费": by_category["其他"]
        }
        
        return {
            "total_cost": base_cost,
            "by_category": by_category,
            "by_item": by_item,
            "trend": "稳定",
            "unit_cost": base_cost / 200  # 假设200亩
        }
    
    # 收益预测方法
    def _basic_revenue_projection(self, crop: str, scale: Scale, location: str, 
                                market_price: float, expected_yield: float) -> RevenueProjection:
        """基础收益预测"""
        total_revenue = market_price * expected_yield
        
        # 按来源分解
        by_source = {
            "批发销售": total_revenue * 0.7,
            "零售销售": total_revenue * 0.2,
            "加工销售": total_revenue * 0.1
        }
        
        return RevenueProjection(
            crop=crop,
            scale=scale,
            location=location,
            total_revenue=total_revenue,
            revenue_by_source=by_source,
            revenue_trend="稳定",
            market_price=market_price,
            expected_yield=expected_yield,
            revenue_confidence=0.8
        )
    
    def _market_adjusted_revenue(self, crop: str, scale: Scale, location: str, 
                                market_price: float, expected_yield: float) -> RevenueProjection:
        """市场调整收益预测"""
        # 考虑市场波动
        market_adjustment = 1.0 + (hash(f"market_{crop}_{location}") % 20 - 10) / 100
        adjusted_price = market_price * market_adjustment
        
        total_revenue = adjusted_price * expected_yield
        
        # 按来源分解
        by_source = {
            "批发销售": total_revenue * 0.65,
            "零售销售": total_revenue * 0.25,
            "加工销售": total_revenue * 0.1
        }
        
        return RevenueProjection(
            crop=crop,
            scale=scale,
            location=location,
            total_revenue=total_revenue,
            revenue_by_source=by_source,
            revenue_trend="波动",
            market_price=adjusted_price,
            expected_yield=expected_yield,
            revenue_confidence=0.7
        )
    
    def _optimistic_revenue_projection(self, crop: str, scale: Scale, location: str, 
                                     market_price: float, expected_yield: float) -> RevenueProjection:
        """乐观收益预测"""
        # 考虑优化因素
        optimization_factor = 1.1  # 10%的优化空间
        optimistic_yield = expected_yield * optimization_factor
        
        total_revenue = market_price * optimistic_yield
        
        # 按来源分解
        by_source = {
            "批发销售": total_revenue * 0.6,
            "零售销售": total_revenue * 0.3,
            "加工销售": total_revenue * 0.1
        }
        
        return RevenueProjection(
            crop=crop,
            scale=scale,
            location=location,
            total_revenue=total_revenue,
            revenue_by_source=by_source,
            revenue_trend="增长",
            market_price=market_price,
            expected_yield=optimistic_yield,
            revenue_confidence=0.6
        )
    
    # ROI计算方法
    def _simple_roi_calculation(self, crop: str, scale: Scale, location: str, 
                              investment: float, revenue: float) -> ROIAnalysis:
        """简单ROI计算"""
        net_profit = revenue - investment
        roi_percentage = (net_profit / investment) * 100 if investment > 0 else 0
        payback_period = investment / revenue if revenue > 0 else float('inf')
        
        return ROIAnalysis(
            crop=crop,
            scale=scale,
            location=location,
            total_investment=investment,
            total_revenue=revenue,
            net_profit=net_profit,
            roi_percentage=roi_percentage,
            payback_period=payback_period,
            npv=net_profit,
            irr=roi_percentage / 100,
            risk_level="中等"
        )
    
    def _detailed_roi_analysis(self, crop: str, scale: Scale, location: str, 
                             investment: float, revenue: float) -> ROIAnalysis:
        """详细ROI分析"""
        # 计算现金流
        annual_cash_flow = revenue - (investment * 0.1)  # 假设每年10%的运营成本
        
        # 计算NPV（假设5年期限，10%贴现率）
        npv = 0
        discount_rate = 0.1
        for year in range(1, 6):
            npv += annual_cash_flow / ((1 + discount_rate) ** year)
        npv -= investment
        
        # 计算IRR（简化计算）
        irr = 0.15  # 假设IRR为15%
        
        # 计算回收期
        payback_period = investment / annual_cash_flow if annual_cash_flow > 0 else float('inf')
        
        # 计算ROI
        roi_percentage = ((revenue * 5 - investment) / investment) * 100  # 5年总ROI
        
        return ROIAnalysis(
            crop=crop,
            scale=scale,
            location=location,
            total_investment=investment,
            total_revenue=revenue,
            net_profit=revenue - investment,
            roi_percentage=roi_percentage,
            payback_period=payback_period,
            npv=npv,
            irr=irr,
            risk_level="中等"
        )
    
    def _risk_adjusted_roi(self, crop: str, scale: Scale, location: str, 
                          investment: float, revenue: float) -> ROIAnalysis:
        """风险调整ROI分析"""
        # 基础ROI
        base_roi = self._simple_roi_calculation(crop, scale, location, investment, revenue)
        
        # 风险调整因子
        risk_adjustment = self._get_risk_adjustment_factor(crop, scale, location)
        adjusted_roi = base_roi.roi_percentage * risk_adjustment
        
        # 调整回收期
        adjusted_payback_period = base_roi.payback_period / risk_adjustment
        
        # 调整NPV和IRR
        adjusted_npv = base_roi.npv * risk_adjustment
        adjusted_irr = base_roi.irr * risk_adjustment
        
        return ROIAnalysis(
            crop=crop,
            scale=scale,
            location=location,
            total_investment=investment,
            total_revenue=revenue,
            net_profit=revenue - investment,
            roi_percentage=adjusted_roi,
            payback_period=adjusted_payback_period,
            npv=adjusted_npv,
            irr=adjusted_irr,
            risk_level="根据风险调整"
        )
    
    # 辅助计算方法
    def _calculate_cost_efficiency(self, cost_data: Dict[str, Any]) -> float:
        """计算成本效率"""
        # 简化的成本效率计算
        base_efficiency = 0.7
        cost_factor = 1.0 - (cost_data['total_cost'] / 100000) * 0.2  # 成本越高，效率越低
        return min(1.0, max(0.0, base_efficiency * cost_factor))
    
    def _get_market_price(self, crop: str, location: str) -> float:
        """获取市场价格"""
        base_price = 100 + hash(crop) % 50
        location_adjustment = hash(f"location_{location}") % 20 - 10
        return base_price + location_adjustment
    
    def _calculate_expected_yield(self, crop: str, scale: Scale, location: str) -> float:
        """计算预期产量"""
        base_yield = {
            Scale.SMALL: 1000,
            Scale.MEDIUM: 5000,
            Scale.LARGE: 20000
        }[scale]
        
        crop_adjustment = hash(crop) % 500 - 250
        location_adjustment = hash(f"location_{location}") % 200 - 100
        
        return base_yield + crop_adjustment + location_adjustment
    
    def _combine_revenue_projections(self, projections: List[RevenueProjection], 
                                   weights: List[float]) -> RevenueProjection:
        """综合收益预测"""
        if not projections or len(projections) != len(weights):
            raise ValueError("预测结果和权重不匹配")
            
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("权重总和不能为零")
            
        # 加权平均总收益
        weighted_revenue = sum(p.total_revenue * w for p, w in zip(projections, weights)) / total_weight
        
        # 加权平均置信度
        weighted_confidence = sum(p.revenue_confidence * w for p, w in zip(projections, weights)) / total_weight
        
        # 使用第一个预测的其他信息
        base_projection = projections[0]
        
        return RevenueProjection(
            crop=base_projection.crop,
            scale=base_projection.scale,
            location=base_projection.location,
            total_revenue=weighted_revenue,
            revenue_by_source=base_projection.revenue_by_source,
            revenue_trend=base_projection.revenue_trend,
            market_price=base_projection.market_price,
            expected_yield=base_projection.expected_yield,
            revenue_confidence=weighted_confidence
        )
    
    def _simple_revenue_projection(self, crop: str, scale: Scale, location: str, 
                                 market_price: float, expected_yield: float) -> RevenueProjection:
        """简单收益预测"""
        total_revenue = market_price * expected_yield
        
        return RevenueProjection(
            crop=crop,
            scale=scale,
            location=location,
            total_revenue=total_revenue,
            revenue_by_source={"主要销售": total_revenue},
            revenue_trend="稳定",
            market_price=market_price,
            expected_yield=expected_yield,
            revenue_confidence=0.5
        )
    
    def _calculate_payback_period(self, investment: float, annual_revenue: float) -> float:
        """计算回收期"""
        if annual_revenue <= 0:
            return float('inf')
        return investment / annual_revenue
    
    def _calculate_npv_irr(self, investment: float, annual_revenue: float, years: int) -> tuple:
        """计算NPV和IRR"""
        # 简化的NPV计算
        discount_rate = 0.1
        npv = 0
        for year in range(1, years + 1):
            npv += annual_revenue / ((1 + discount_rate) ** year)
        npv -= investment
        
        # 简化的IRR计算
        irr = annual_revenue / investment - 1
        
        return npv, irr
    
    def _assess_financial_risk_level(self, roi_percentage: float, payback_period: float, 
                                   npv: float, irr: float) -> str:
        """评估财务风险等级"""
        if roi_percentage > 20 and payback_period < 2 and npv > 0 and irr > 0.15:
            return "低"
        elif roi_percentage > 10 and payback_period < 4 and npv > 0 and irr > 0.1:
            return "中等"
        else:
            return "高"
    
    def _assess_financial_risk_level_details(self, roi_analysis: ROIAnalysis) -> Dict[str, Any]:
        """评估财务风险详情"""
        risk_factors = {
            "roi_risk": "低" if roi_analysis.roi_percentage > 15 else "中等" if roi_analysis.roi_percentage > 5 else "高",
            "payback_risk": "低" if roi_analysis.payback_period < 3 else "中等" if roi_analysis.payback_period < 5 else "高",
            "npv_risk": "低" if roi_analysis.npv > 0 else "高",
            "irr_risk": "低" if roi_analysis.irr > 0.1 else "中等" if roi_analysis.irr > 0.05 else "高"
        }
        
        overall_risk = sum(1 for risk in risk_factors.values() if risk == "高")
        risk_level = "高" if overall_risk >= 3 else "中等" if overall_risk >= 2 else "低"
        
        return {
            "risk_factors": risk_factors,
            "overall_risk": risk_level,
            "risk_score": overall_risk
        }
    
    def _assess_market_risk(self, crop: str, location: str) -> Dict[str, Any]:
        """评估市场风险"""
        return {
            "price_volatility": "中等",
            "demand_stability": "稳定",
            "competition_level": "中等",
            "market_access": "良好"
        }
    
    def _assess_operational_risk(self, crop: str, scale: Scale, location: str) -> Dict[str, Any]:
        """评估运营风险"""
        return {
            "technical_risk": "低",
            "supply_risk": "中等",
            "labor_risk": "低",
            "weather_risk": "中等"
        }
    
    def _assess_policy_risk(self, crop: str, location: str) -> Dict[str, Any]:
        """评估政策风险"""
        return {
            "policy_stability": "稳定",
            "regulatory_risk": "低",
            "subsidy_risk": "低",
            "trade_risk": "中等"
        }
    
    def _calculate_overall_risk(self, risks: Dict[str, Dict[str, Any]]) -> float:
        """计算总体风险评分"""
        risk_scores = []
        for risk_type, risk_details in risks.items():
            if isinstance(risk_details, dict):
                for risk_name, risk_level in risk_details.items():
                    if risk_level == "高":
                        risk_scores.append(3)
                    elif risk_level == "中等":
                        risk_scores.append(2)
                    else:
                        risk_scores.append(1)
        
        return sum(risk_scores) / len(risk_scores) if risk_scores else 0
    
    def _get_risk_level(self, risk_score: float) -> str:
        """获取风险等级"""
        if risk_score >= 2.5:
            return "高"
        elif risk_score >= 1.5:
            return "中等"
        else:
            return "低"
    
    def _generate_risk_mitigation_strategies(self, risks: Dict[str, Dict[str, Any]]) -> List[str]:
        """生成风险缓解策略"""
        strategies = []
        
        # 市场风险缓解
        if any(risk == "高" for risk in risks.get("market_risk", {}).values()):
            strategies.append("多元化销售渠道，降低市场依赖")
            
        # 运营风险缓解
        if any(risk == "高" for risk in risks.get("operational_risk", {}).values()):
            strategies.append("加强供应链管理，建立应急储备")
            
        # 财务风险缓解
        if any(risk == "高" for risk in risks.get("financial_risk", {}).values()):
            strategies.append("优化资金结构，合理安排投资计划")
            
        # 政策风险缓解
        if any(risk == "高" for risk in risks.get("policy_risk", {}).values()):
            strategies.append("关注政策动向，及时调整经营策略")
            
        return strategies
    
    def _get_risk_adjustment_factor(self, crop: str, scale: Scale, location: str) -> float:
        """获取风险调整因子"""
        # 基于作物、规模和位置计算风险调整因子
        base_factor = 1.0
        
        # 作物风险调整
        crop_risk = hash(crop) % 20 + 80  # 80-100
        crop_factor = crop_risk / 100
        
        # 规模风险调整
        scale_factor = 1.0 if scale == Scale.MEDIUM else 0.9 if scale == Scale.SMALL else 1.1
        
        # 位置风险调整
        location_risk = hash(f"location_{location}") % 30 + 70  # 70-100
        location_factor = location_risk / 100
        
        return base_factor * crop_factor * scale_factor * location_factor
    
    # 数据加载方法
    def _load_subsidy_database(self) -> List[Dict[str, Any]]:
        """加载补贴数据库"""
        # 模拟补贴数据库
        return [
            {
                "type": "种植补贴",
                "crop": "水稻",
                "region": "all",
                "amount": 2000,
                "criteria": ["种植面积超过10亩", "符合绿色种植标准"],
                "deadline": datetime(2026, 12, 31),
                "contact": {"部门": "农业农村局", "电话": "1234567890"},
                "approval_rate": 0.8,
                "processing_time": "3个月"
            },
            {
                "type": "设备补贴",
                "crop": "all",
                "region": "华东地区",
                "amount": 5000,
                "criteria": ["购买新型农业设备", "设备符合环保标准"],
                "deadline": datetime(2026, 6, 30),
                "contact": {"部门": "农机局", "电话": "1234567891"},
                "approval_rate": 0.7,
                "processing_time": "2个月"
            },
            {
                "type": "技术补贴",
                "crop": "all",
                "region": "all",
                "amount": 3000,
                "criteria": ["采用先进种植技术", "技术培训合格"],
                "deadline": datetime(2026, 9, 30),
                "contact": {"部门": "科技局", "电话": "1234567892"},
                "approval_rate": 0.9,
                "processing_time": "1个月"
            }
        ]
    
    def _load_financing_options(self) -> List[Dict[str, Any]]:
        """加载融资方案"""
        # 模拟融资方案
        return [
            {
                "type": "银行贷款",
                "crop": "all",
                "region": "all",
                "scale": "all",
                "min_amount": 10000,
                "max_amount": 1000000,
                "interest_rate": 4.5,
                "term": 5,
                "requirements": ["良好的信用记录", "稳定的收入来源", "抵押物"],
                "advantages": ["利率较低", "期限较长", "手续相对简单"],
                "disadvantages": ["审批严格", "需要抵押", "额度有限"],
                "approval_rate": 0.6
            },
            {
                "type": "农业信贷",
                "crop": "水稻",
                "region": "华东地区",
                "scale": "medium",
                "min_amount": 20000,
                "max_amount": 500000,
                "interest_rate": 3.8,
                "term": 3,
                "requirements": ["农业种植经验", "土地承包合同", "合作社成员"],
                "advantages": ["专门针对农业", "利率优惠", "审批较快"],
                "disadvantages": ["额度有限", "期限较短", "需要合作社担保"],
                "approval_rate": 0.8
            },
            {
                "type": "创业贷款",
                "crop": "all",
                "region": "all",
                "scale": "small",
                "min_amount": 5000,
                "max_amount": 200000,
                "interest_rate": 5.2,
                "term": 2,
                "requirements": ["创业计划书", "个人担保", "项目可行性分析"],
                "advantages": ["额度灵活", "审批快速", "无需抵押"],
                "disadvantages": ["利率较高", "期限较短", "需要详细计划"],
                "approval_rate": 0.7
            }
        ]
    
    # 缓存方法
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据"""
        if key in self.cache:
            cached_data, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data
            else:
                del self.cache[key]
        return None
    
    def _cache_result(self, key: str, result: Dict[str, Any]):
        """缓存结果"""
        self.cache[key] = (result, time.time())
        
        # 清理过期缓存
        current_time = time.time()
        expired_keys = [k for k, (_, t) in self.cache.items() if current_time - t > self.cache_ttl]
        for k in expired_keys:
            del self.cache[k]
    
    # 清理缓存
    def clear_cache(self):
        """清理缓存"""
        self.cache.clear()
    
    # 获取缓存状态
    def get_cache_status(self) -> Dict[str, Any]:
        """获取缓存状态"""
        return {
            "cache_size": len(self.cache),
            "cache_keys": list(self.cache.keys()),
            "cache_ttl": self.cache_ttl
        }

# 测试代码
if __name__ == "__main__":
    # 创建FinanceAgent实例
    agent = FinanceAgent()
    
    # 测试财务分析
    result = agent.analyze_finance("水稻", "medium", "华东地区", 50000, "1年")
    print("财务分析结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    # 测试缓存功能
    print("\n缓存状态:")
    print(json.dumps(agent.get_cache_status(), indent=2, ensure_ascii=False, default=str))