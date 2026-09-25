"""
⚠️ EXPERIMENTAL MOCK — 禁止生产使用 / NOT FOR PRODUCTION
======================================================
本模块是**实验性原型**，所有输出来自 `_generate_mock_*()` **假数据**，
不接入任何真实数据源。它**未接入** AgriOrchestrator / MCP Server / 前端 / 单测，
不代表项目具备真实市场情报能力。

与项目核心原则冲突，故保持孤儿态（已实现但不接线）：
  · 真实性红线：「真实数据、不编造」（0 用户跑不起来）——本模块使用假数据，违反此红线；
  · 商业化铁律：「只做 MCP 分发，B 端 SaaS 全否」——市场/财务/风险属 B 端 SaaS，不应进入生产路径。
保留仅为探索记录，禁止在任何生产链路中调用。若需真实市场能力，应通过 MCP 分发外部权威源，
而非在本仓内造壳。

MarketAgent - 农产品市场情报与价格预测（实验性原型）

功能：
- 农产品价格历史数据查询（MOCK）
- 区域市场供需状况监测（MOCK）
- 价格趋势预测与预警（MOCK）
- 政策影响评估（MOCK）
- 竞品分析（MOCK）

作者：智慧农业生态团队
创建日期：2026-01-15
"""

import json
try:  # 零依赖保护：requests 非本项目依赖，仅实验性代码可能引用
    import requests
except ImportError:
    requests = None  # 生产环境无此依赖；本模块不可用于生产
import re
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
class AnalysisType(Enum):
    PRICE = "price"
    TREND = "trend"
    SUPPLY = "supply"
    DEMAND = "demand"
    POLICY = "policy"
    COMPETITOR = "competitor"

class Timeframe(Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"

@dataclass
class MarketData:
    """市场数据模型"""
    crop: str
    region: str
    timestamp: datetime
    price: float
    supply: float
    demand: float
    trend: str
    confidence: float
    source: str

@dataclass
class PriceForecast:
    """价格预测模型"""
    crop: str
    region: str
    timeframe: Timeframe
    current_price: float
    predicted_price: float
    confidence: float
    trend_direction: str
    volatility: float
    factors: List[str]

@dataclass
class TrendAnalysis:
    """趋势分析模型"""
    crop: str
    region: str
    timeframe: Timeframe
    historical_trend: str
    seasonal_patterns: List[str]
    market_indicators: Dict[str, float]
    forecast: str
    confidence: float

@dataclass
class RiskIndicator:
    """风险指标模型"""
    type: str
    level: str
    description: str
    probability: float
    impact: str
    mitigation: List[str]
    timestamp: datetime

class MarketAgent:
    """农产品市场情报与价格预测Agent"""
    
    def __init__(self):
        self.data_sources = {
            'national_bureau': self._fetch_national_bureau_data,
            'agricultural_markets': self._fetch_agricultural_markets,
            'commodity_exchanges': self._fetch_commodity_exchanges,
            'weather_impact': self._fetch_weather_impact
        }
        
        self.price_models = {
            'linear_regression': self._linear_regression_forecast,
            'time_series': self._time_series_forecast,
            'machine_learning': self._ml_forecast
        }
        
        self.risk_factors = {
            'weather': self._assess_weather_risk,
            'policy': self._assess_policy_risk,
            'market': self._assess_market_risk,
            'supply_chain': self._assess_supply_chain_risk
        }
        
        self.cache = {}
        self.cache_ttl = 3600  # 1小时缓存
        
    def analyze_market(self, crop: str, region: str = None, timeframe: str = "monthly", 
                      analysis_type: str = "price") -> Dict[str, Any]:
        """
        分析农产品市场
        
        Args:
            crop: 作物名称
            region: 区域（可选）
            timeframe: 时间范围（weekly/monthly/quarterly/yearly）
            analysis_type: 分析类型（price/trend/supply/demand/policy/competitor）
            
        Returns:
            {
                "market_data": {...},
                "price_forecast": {...},
                "trend_analysis": {...},
                "risk_indicators": [...],
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
            region = region.strip() if region else None
            
            # 检查缓存
            cache_key = f"{crop}_{region}_{timeframe}_{analysis_type}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result
                
            # 执行分析
            result = {
                "market_data": self._collect_market_data(crop, region, timeframe),
                "price_forecast": self._generate_price_forecast(crop, region, timeframe),
                "trend_analysis": self._analyze_trends(crop, region, timeframe),
                "risk_indicators": self._assess_risks(crop, region, timeframe),
                "recommendations": self._generate_recommendations(crop, region, analysis_type),
                "confidence": self._calculate_confidence(crop, region, analysis_type),
                "signature": self._generate_signature(crop, region, analysis_type)
            }
            
            # 缓存结果
            self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "crop": crop,
                "region": region,
                "timestamp": datetime.now().isoformat(),
                "analysis_type": analysis_type
            }
    
    def _collect_market_data(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """收集市场数据"""
        data = {}
        
        # 从多个数据源收集数据
        for source_name, source_func in self.data_sources.items():
            try:
                source_data = source_func(crop, region, timeframe)
                data[source_name] = source_data
            except Exception as e:
                data[source_name] = {"error": str(e)}
                
        return data
    
    def _generate_price_forecast(self, crop: str, region: str, timeframe: str) -> PriceForecast:
        """生成价格预测"""
        # 获取历史价格数据
        historical_prices = self._get_historical_prices(crop, region, timeframe)
        
        if not historical_prices:
            raise ValueError("无法获取历史价格数据")
            
        # 使用多种模型进行预测
        forecasts = []
        for model_name, model_func in self.price_models.items():
            try:
                forecast = model_func(historical_prices, timeframe)
                forecasts.append(forecast)
            except Exception as e:
                print(f"模型 {model_name} 预测失败: {e}")
                
        # 综合预测结果
        if forecasts:
            # 使用加权平均
            weights = [0.3, 0.4, 0.3]  # 线性回归、时间序列、机器学习的权重
            final_forecast = self._combine_forecasts(forecasts, weights)
        else:
            # 如果所有模型都失败，使用简单趋势外推
            final_forecast = self._simple_trend_forecast(historical_prices, timeframe)
            
        return final_forecast
    
    def _analyze_trends(self, crop: str, region: str, timeframe: str) -> TrendAnalysis:
        """分析市场趋势"""
        # 获取历史数据
        historical_data = self._get_historical_market_data(crop, region, timeframe)
        
        if not historical_data:
            raise ValueError("无法获取历史市场数据")
            
        # 分析历史趋势
        historical_trend = self._analyze_historical_trend(historical_data)
        
        # 识别季节性模式
        seasonal_patterns = self._identify_seasonal_patterns(historical_data)
        
        # 分析市场指标
        market_indicators = self._calculate_market_indicators(historical_data)
        
        # 生成预测
        forecast = self._generate_trend_forecast(historical_trend, seasonal_patterns, market_indicators)
        
        # 计算置信度
        confidence = self._calculate_trend_confidence(historical_data, seasonal_patterns)
        
        return TrendAnalysis(
            crop=crop,
            region=region,
            timeframe=Timeframe(timeframe),
            historical_trend=historical_trend,
            seasonal_patterns=seasonal_patterns,
            market_indicators=market_indicators,
            forecast=forecast,
            confidence=confidence
        )
    
    def _assess_risks(self, crop: str, region: str, timeframe: str) -> List[RiskIndicator]:
        """评估风险"""
        risks = []
        
        for risk_type, risk_func in self.risk_factors.items():
            try:
                risk_indicators = risk_func(crop, region, timeframe)
                risks.extend(risk_indicators)
            except Exception as e:
                print(f"风险评估 {risk_type} 失败: {e}")
                
        return risks
    
    def _generate_recommendations(self, crop: str, region: str, analysis_type: str) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于分析类型生成建议
        if analysis_type == "price":
            recommendations.append("建议关注价格波动，适时调整种植计划")
            recommendations.append("考虑与收购方签订长期合同锁定价格")
            
        elif analysis_type == "trend":
            recommendations.append("建议关注市场趋势变化，及时调整种植品种")
            recommendations.append("加强市场信息收集，提高决策准确性")
            
        elif analysis_type == "supply":
            recommendations.append("建议关注供应链稳定性，建立多元化供应渠道")
            recommendations.append("考虑与当地供应商建立长期合作关系")
            
        elif analysis_type == "demand":
            recommendations.append("建议关注市场需求变化，调整种植规模")
            recommendations.append("加强市场调研，了解消费者偏好")
            
        elif analysis_type == "policy":
            recommendations.append("建议关注政策变化，及时调整经营策略")
            recommendations.append("积极参与政策制定，争取政策支持")
            
        elif analysis_type == "competitor":
            recommendations.append("建议关注竞争对手动态，制定差异化策略")
            recommendations.append("加强产品创新，提高市场竞争力")
            
        return recommendations
    
    def _calculate_confidence(self, crop: str, region: str, analysis_type: str) -> Dict[str, float]:
        """计算置信度"""
        confidence = {
            "data_quality": 0.8,  # 数据质量置信度
            "model_accuracy": 0.75,  # 模型准确度置信度
            "market_stability": 0.7,  # 市场稳定性置信度
            "overall": 0.75  # 总体置信度
        }
        
        # 根据具体情况调整置信度
        if region:
            confidence["data_quality"] += 0.1
            confidence["overall"] += 0.05
            
        if analysis_type in ["price", "trend"]:
            confidence["model_accuracy"] += 0.1
            confidence["overall"] += 0.05
            
        return confidence
    
    def _generate_signature(self, crop: str, region: str, analysis_type: str) -> str:
        """生成数字签名"""
        timestamp = datetime.now().isoformat()
        data_str = f"{crop}_{region}_{analysis_type}_{timestamp}"
        
        # 使用HMAC-SHA256生成签名
        key = "market_agent_secret_key"  # 在实际应用中应该使用安全的密钥管理
        signature = hmac.new(key.encode(), data_str.encode(), hashlib.sha256).hexdigest()
        
        return signature
    
    # 数据源方法
    def _fetch_national_bureau_data(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """从国家统计局获取数据"""
        # 模拟数据获取
        return {
            "source": "national_bureau",
            "crop": crop,
            "region": region,
            "timeframe": timeframe,
            "price_data": self._generate_mock_price_data(),
            "supply_data": self._generate_mock_supply_data(),
            "demand_data": self._generate_mock_demand_data()
        }
    
    def _fetch_agricultural_markets(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """从农业市场获取数据"""
        # 模拟数据获取
        return {
            "source": "agricultural_markets",
            "crop": crop,
            "region": region,
            "timeframe": timeframe,
            "market_prices": self._generate_mock_market_prices(),
            "trading_volume": self._generate_mock_trading_volume()
        }
    
    def _fetch_commodity_exchanges(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """从商品交易所获取数据"""
        # 模拟数据获取
        return {
            "source": "commodity_exchanges",
            "crop": crop,
            "region": region,
            "timeframe": timeframe,
            "futures_prices": self._generate_mock_futures_prices(),
            "trading_volume": self._generate_mock_trading_volume()
        }
    
    def _fetch_weather_impact(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """获取天气影响数据"""
        # 模拟数据获取
        return {
            "source": "weather_impact",
            "crop": crop,
            "region": region,
            "timeframe": timeframe,
            "weather_impact_score": self._generate_mock_weather_impact(),
            "climate_risk": self._generate_mock_climate_risk()
        }
    
    # 预测模型方法
    def _linear_regression_forecast(self, historical_prices: List[float], timeframe: str) -> PriceForecast:
        """线性回归预测"""
        # 简单的线性回归实现
        if len(historical_prices) < 2:
            raise ValueError("历史价格数据不足")
            
        # 计算线性回归参数
        n = len(historical_prices)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(historical_prices)
        sum_xy = sum(x[i] * historical_prices[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        intercept = (sum_y - slope * sum_x) / n
        
        # 预测下一个时间点
        next_x = n
        predicted_price = slope * next_x + intercept
        
        # 计算置信度
        confidence = min(0.9, 0.6 + (n - 2) * 0.05)  # 数据越多，置信度越高
        
        return PriceForecast(
            crop="unknown",
            region="unknown",
            timeframe=Timeframe(timeframe),
            current_price=historical_prices[-1],
            predicted_price=predicted_price,
            confidence=confidence,
            trend_direction="up" if slope > 0 else "down",
            volatility=self._calculate_volatility(historical_prices),
            factors=["linear_regression_trend"]
        )
    
    def _time_series_forecast(self, historical_prices: List[float], timeframe: str) -> PriceForecast:
        """时间序列预测"""
        # 简单的移动平均预测
        if len(historical_prices) < 3:
            raise ValueError("历史价格数据不足")
            
        # 使用最近3个时间点的移动平均
        window_size = min(3, len(historical_prices))
        recent_prices = historical_prices[-window_size:]
        moving_avg = sum(recent_prices) / window_size
        
        # 简单的趋势调整
        trend = (historical_prices[-1] - historical_prices[-2]) if len(historical_prices) >= 2 else 0
        predicted_price = moving_avg + trend * 0.5
        
        # 计算置信度
        confidence = min(0.85, 0.5 + (len(historical_prices) - 3) * 0.05)
        
        return PriceForecast(
            crop="unknown",
            region="unknown",
            timeframe=Timeframe(timeframe),
            current_price=historical_prices[-1],
            predicted_price=predicted_price,
            confidence=confidence,
            trend_direction="up" if trend > 0 else "down",
            volatility=self._calculate_volatility(historical_prices),
            factors=["moving_average_trend"]
        )
    
    def _ml_forecast(self, historical_prices: List[float], timeframe: str) -> PriceForecast:
        """机器学习预测"""
        # 模拟机器学习预测
        if len(historical_prices) < 5:
            raise ValueError("历史价格数据不足")
            
        # 使用简单的模式识别
        pattern = self._identify_price_pattern(historical_prices)
        
        # 基于模式预测
        if pattern == "increasing":
            predicted_price = historical_prices[-1] * 1.05
        elif pattern == "decreasing":
            predicted_price = historical_prices[-1] * 0.95
        else:  # stable
            predicted_price = historical_prices[-1]
            
        # 计算置信度
        confidence = min(0.8, 0.6 + (len(historical_prices) - 5) * 0.03)
        
        return PriceForecast(
            crop="unknown",
            region="unknown",
            timeframe=Timeframe(timeframe),
            current_price=historical_prices[-1],
            predicted_price=predicted_price,
            confidence=confidence,
            trend_direction=pattern,
            volatility=self._calculate_volatility(historical_prices),
            factors=["machine_learning_pattern"]
        )
    
    # 辅助方法
    def _get_historical_prices(self, crop: str, region: str, timeframe: str) -> List[float]:
        """获取历史价格数据"""
        # 模拟历史价格数据
        base_price = 100 + hash(crop) % 50  # 基于作物名称生成基础价格
        num_points = {"weekly": 12, "monthly": 12, "quarterly": 8, "yearly": 5}[timeframe]
        
        prices = []
        for i in range(num_points):
            # 添加一些随机波动
            variation = (hash(f"{crop}_{region}_{i}") % 20) - 10
            price = base_price + variation + i * 2  # 简单上升趋势
            prices.append(max(price, 10))  # 确保价格为正
            
        return prices
    
    def _get_historical_market_data(self, crop: str, region: str, timeframe: str) -> Dict[str, Any]:
        """获取历史市场数据"""
        return {
            "prices": self._get_historical_prices(crop, region, timeframe),
            "supply": self._generate_mock_supply_data(),
            "demand": self._generate_mock_demand_data(),
            "trading_volume": self._generate_mock_trading_volume()
        }
    
    def _combine_forecasts(self, forecasts: List[PriceForecast], weights: List[float]) -> PriceForecast:
        """综合多个预测结果"""
        if not forecasts or len(forecasts) != len(weights):
            raise ValueError("预测结果和权重不匹配")
            
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("权重总和不能为零")
            
        # 加权平均预测价格
        weighted_price = sum(f.predicted_price * w for f, w in zip(forecasts, weights)) / total_weight
        
        # 平均置信度
        avg_confidence = sum(f.confidence * w for f, w in zip(forecasts, weights)) / total_weight
        
        # 综合趋势方向
        trend_scores = {"up": 0, "down": 0, "stable": 0}
        for f, w in zip(forecasts, weights):
            if f.trend_direction == "up":
                trend_scores["up"] += w
            elif f.trend_direction == "down":
                trend_scores["down"] += w
            else:
                trend_scores["stable"] += w
                
        final_trend = max(trend_scores, key=trend_scores.get)
        
        # 平均波动率
        avg_volatility = sum(f.volatility * w for f, w in zip(forecasts, weights)) / total_weight
        
        return PriceForecast(
            crop=forecasts[0].crop,
            region=forecasts[0].region,
            timeframe=forecasts[0].timeframe,
            current_price=forecasts[0].current_price,
            predicted_price=weighted_price,
            confidence=avg_confidence,
            trend_direction=final_trend,
            volatility=avg_volatility,
            factors=[f"factors_{i}" for i in range(len(forecasts))]
        )
    
    def _simple_trend_forecast(self, historical_prices: List[float], timeframe: str) -> PriceForecast:
        """简单趋势预测"""
        if not historical_prices:
            raise ValueError("历史价格数据为空")
            
        # 使用最近的价格变化趋势
        if len(historical_prices) >= 2:
            recent_change = historical_prices[-1] - historical_prices[-2]
            predicted_price = historical_prices[-1] + recent_change * 0.5
        else:
            predicted_price = historical_prices[-1]
            
        return PriceForecast(
            crop="unknown",
            region="unknown",
            timeframe=Timeframe(timeframe),
            current_price=historical_prices[-1],
            predicted_price=predicted_price,
            confidence=0.5,  # 简单预测置信度较低
            trend_direction="stable",
            volatility=self._calculate_volatility(historical_prices),
            factors=["simple_trend"]
        )
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """计算价格波动率"""
        if len(prices) < 2:
            return 0.0
            
        # 计算价格变化的标准差
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        if not changes:
            return 0.0
            
        mean_change = sum(changes) / len(changes)
        variance = sum((c - mean_change) ** 2 for c in changes) / len(changes)
        volatility = (variance ** 0.5) / mean_change if mean_change != 0 else 0.0
        
        return min(volatility, 1.0)  # 限制波动率在0-1之间
    
    def _identify_price_pattern(self, prices: List[float]) -> str:
        """识别价格模式"""
        if len(prices) < 3:
            return "stable"
            
        # 计算趋势
        if prices[-1] > prices[0] * 1.1:  # 上涨超过10%
            return "increasing"
        elif prices[-1] < prices[0] * 0.9:  # 下跌超过10%
            return "decreasing"
        else:
            return "stable"
    
    def _analyze_historical_trend(self, historical_data: Dict[str, Any]) -> str:
        """分析历史趋势"""
        prices = historical_data.get("prices", [])
        if len(prices) < 2:
            return "insufficient_data"
            
        # 简单的趋势分析
        if prices[-1] > prices[0] * 1.05:
            return "上升"
        elif prices[-1] < prices[0] * 0.95:
            return "下降"
        else:
            return "稳定"
    
    def _identify_seasonal_patterns(self, historical_data: Dict[str, Any]) -> List[str]:
        """识别季节性模式"""
        # 模拟季节性模式识别
        return ["春季需求增长", "夏季供应充足", "秋季价格波动", "冬季需求稳定"]
    
    def _calculate_market_indicators(self, historical_data: Dict[str, Any]) -> Dict[str, float]:
        """计算市场指标"""
        prices = historical_data.get("prices", [])
        supply = historical_data.get("supply", {})
        demand = historical_data.get("demand", {})
        
        indicators = {
            "price_volatility": self._calculate_volatility(prices),
            "supply_demand_ratio": supply.get("current", 100) / demand.get("current", 100),
            "price_trend": 0.5 if len(prices) >= 2 else 0.0,
            "market_liquidity": 0.7
        }
        
        return indicators
    
    def _generate_trend_forecast(self, historical_trend: str, seasonal_patterns: List[str], 
                               market_indicators: Dict[str, float]) -> str:
        """生成趋势预测"""
        # 基于历史趋势和市场指标生成预测
        if historical_trend == "上升":
            return "预计将继续上涨"
        elif historical_trend == "下降":
            return "预计将继续下跌"
        else:
            return "预计将保持稳定"
    
    def _calculate_trend_confidence(self, historical_data: Dict[str, Any], seasonal_patterns: List[str]) -> float:
        """计算趋势置信度"""
        prices = historical_data.get("prices", [])
        num_patterns = len(seasonal_patterns)
        
        # 基于数据量和季节性模式数量计算置信度
        base_confidence = 0.6
        data_bonus = min(0.2, len(prices) * 0.02)
        pattern_bonus = min(0.2, num_patterns * 0.05)
        
        return min(0.95, base_confidence + data_bonus + pattern_bonus)
    
    # 风险评估方法
    def _assess_weather_risk(self, crop: str, region: str, timeframe: str) -> List[RiskIndicator]:
        """评估天气风险"""
        risks = []
        
        # 模拟天气风险评估
        risk_level = "中等"
        probability = 0.3
        impact = "中等"
        
        risks.append(RiskIndicator(
            type="weather",
            level=risk_level,
            description=f"预计{timeframe}内天气变化可能影响{crop}生产",
            probability=probability,
            impact=impact,
            mitigation=["关注天气预报", "准备防涝/抗旱措施", "购买农业保险"],
            timestamp=datetime.now()
        ))
        
        return risks
    
    def _assess_policy_risk(self, crop: str, region: str, timeframe: str) -> List[RiskIndicator]:
        """评估政策风险"""
        risks = []
        
        # 模拟政策风险评估
        risk_level = "低"
        probability = 0.1
        impact = "低"
        
        risks.append(RiskIndicator(
            type="policy",
            level=risk_level,
            description=f"预计{timeframe}内政策变化对{crop}影响较小",
            probability=probability,
            impact=impact,
            mitigation=["关注政策动向", "及时调整种植计划", "参与政策制定"],
            timestamp=datetime.now()
        ))
        
        return risks
    
    def _assess_market_risk(self, crop: str, region: str, timeframe: str) -> List[RiskIndicator]:
        """评估市场风险"""
        risks = []
        
        # 模拟市场风险评估
        risk_level = "中等"
        probability = 0.4
        impact = "中等"
        
        risks.append(RiskIndicator(
            type="market",
            level=risk_level,
            description=f"预计{timeframe}内市场波动可能影响{crop}价格",
            probability=probability,
            impact=impact,
            mitigation=["多元化销售渠道", "签订长期合同", "关注市场动态"],
            timestamp=datetime.now()
        ))
        
        return risks
    
    def _assess_supply_chain_risk(self, crop: str, region: str, timeframe: str) -> List[RiskIndicator]:
        """评估供应链风险"""
        risks = []
        
        # 模拟供应链风险评估
        risk_level = "低"
        probability = 0.2
        impact = "低"
        
        risks.append(RiskIndicator(
            type="supply_chain",
            level=risk_level,
            description=f"预计{timeframe}内供应链稳定性较好",
            probability=probability,
            impact=impact,
            mitigation=["建立多元化供应商", "优化物流路线", "建立应急储备"],
            timestamp=datetime.now()
        ))
        
        return risks
    
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
    
    # 模拟数据生成方法
    def _generate_mock_price_data(self) -> Dict[str, Any]:
        """生成模拟价格数据"""
        return {
            "current_price": 100 + hash("price") % 50,
            "historical_prices": [90 + i * 2 + hash(f"price_{i}") % 10 for i in range(12)],
            "price_trend": "上升",
            "volatility": 0.15
        }
    
    def _generate_mock_supply_data(self) -> Dict[str, Any]:
        """生成模拟供应数据"""
        return {
            "current_supply": 1000 + hash("supply") % 200,
            "historical_supply": [800 + i * 20 + hash(f"supply_{i}") % 50 for i in range(12)],
            "supply_trend": "稳定"
        }
    
    def _generate_mock_demand_data(self) -> Dict[str, Any]:
        """生成模拟需求数据"""
        return {
            "current_demand": 950 + hash("demand") % 150,
            "historical_demand": [750 + i * 25 + hash(f"demand_{i}") % 40 for i in range(12)],
            "demand_trend": "增长"
        }
    
    def _generate_mock_market_prices(self) -> Dict[str, Any]:
        """生成模拟市场价格数据"""
        return {
            "wholesale_price": 95 + hash("wholesale") % 20,
            "retail_price": 120 + hash("retail") % 30,
            "export_price": 110 + hash("export") % 25
        }
    
    def _generate_mock_trading_volume(self) -> Dict[str, Any]:
        """生成模拟交易量数据"""
        return {
            "daily_volume": 10000 + hash("volume") % 5000,
            "weekly_volume": 70000 + hash("weekly_volume") % 20000,
            "monthly_volume": 300000 + hash("monthly_volume") % 100000
        }
    
    def _generate_mock_futures_prices(self) -> Dict[str, Any]:
        """生成模拟期货价格数据"""
        return {
            "near_month": 105 + hash("near_month") % 15,
            "far_month": 110 + hash("far_month") % 20,
            "spread": 5 + hash("spread") % 10
        }
    
    def _generate_mock_weather_impact(self) -> float:
        """生成模拟天气影响分数"""
        return 0.3 + hash("weather_impact") % 40 / 100
    
    def _generate_mock_climate_risk(self) -> str:
        """生成模拟气候风险等级"""
        risks = ["低", "中等", "高"]
        return risks[hash("climate_risk") % len(risks)]
    
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
    # 创建MarketAgent实例
    agent = MarketAgent()
    
    # 测试市场分析
    result = agent.analyze_market("水稻", "华东地区", "monthly", "price")
    print("市场分析结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    # 测试缓存功能
    print("\n缓存状态:")
    print(json.dumps(agent.get_cache_status(), indent=2, ensure_ascii=False, default=str))