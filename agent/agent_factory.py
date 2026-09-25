"""
Agent工厂类

功能：
- 统一管理所有Agent的创建和初始化
- Agent生命周期管理
- Agent配置管理
- Agent依赖注入
- Agent注册和发现

架构：
- Agent工厂（Agent Factory）
- Agent注册表（Agent Registry）
- Agent配置管理器（Configuration Manager）
- 依赖注入容器（Dependency Injection Container）
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Type, Union
from dataclasses import dataclass, asdict
from enum import Enum
import importlib
import inspect

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentStatus(Enum):
    """Agent状态"""
    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class AgentConfig:
    """Agent配置"""
    name: str
    type: str
    class_name: str
    module_path: str
    version: str = "1.0.0"
    enabled: bool = True
    dependencies: List[str] = None
    config_params: Dict[str, Any] = None
    resource_requirements: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.config_params is None:
            self.config_params = {}
        if self.resource_requirements is None:
            self.resource_requirements = {}

class AgentRegistry:
    """Agent注册表"""
    
    def __init__(self):
        self.agents: Dict[str, Dict] = {}
        self.agent_configs: Dict[str, AgentConfig] = {}
        self.agent_instances: Dict[str, Any] = {}
        self.agent_status: Dict[str, AgentStatus] = {}
        
    def register_agent(self, config: AgentConfig):
        """注册Agent"""
        
        agent_id = f"{config.type}_{config.name}"
        
        # 检查是否已存在
        if agent_id in self.agents:
            logger.warning(f"Agent {agent_id} already registered, updating...")
        
        # 存储配置
        self.agent_configs[agent_id] = config
        self.agents[agent_id] = {
            "name": config.name,
            "type": config.type,
            "class_name": config.class_name,
            "module_path": config.module_path,
            "version": config.version,
            "enabled": config.enabled
        }
        
        # 初始化状态
        self.agent_status[agent_id] = AgentStatus.CREATED
        
        logger.info(f"Agent {agent_id} registered")
    
    def unregister_agent(self, agent_id: str):
        """注销Agent"""
        
        if agent_id in self.agents:
            # 停止Agent
            if self.agent_status[agent_id] == AgentStatus.RUNNING:
                self.stop_agent(agent_id)
            
            # 清理实例
            if agent_id in self.agent_instances:
                del self.agent_instances[agent_id]
            
            # 清理配置
            if agent_id in self.agent_configs:
                del self.agent_configs[agent_id]
            
            # 清理注册信息
            del self.agents[agent_id]
            del self.agent_status[agent_id]
            
            logger.info(f"Agent {agent_id} unregistered")
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict]:
        """获取Agent信息"""
        return self.agents.get(agent_id)
    
    def get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """获取Agent配置"""
        return self.agent_configs.get(agent_id)
    
    def get_agent_instance(self, agent_id: str) -> Optional[Any]:
        """获取Agent实例"""
        return self.agent_instances.get(agent_id)
    
    def get_agent_status(self, agent_id: str) -> Optional[AgentStatus]:
        """获取Agent状态"""
        return self.agent_status.get(agent_id)
    
    def list_agents(self, agent_type: str = None, status: AgentStatus = None) -> List[str]:
        """列出Agent"""
        
        agents = []
        for agent_id, info in self.agents.items():
            # 过滤类型
            if agent_type and info["type"] != agent_type:
                continue
            
            # 过滤状态
            if status and self.agent_status.get(agent_id) != status:
                continue
            
            agents.append(agent_id)
        
        return agents
    
    def get_enabled_agents(self, agent_type: str = None) -> List[str]:
        """获取启用的Agent"""
        
        enabled_agents = []
        for agent_id, info in self.agents.items():
            if info["enabled"]:
                if not agent_type or info["type"] == agent_type:
                    enabled_agents.append(agent_id)
        
        return enabled_agents
    
    def update_agent_status(self, agent_id: str, status: AgentStatus):
        """更新Agent状态"""
        self.agent_status[agent_id] = status
        logger.info(f"Agent {agent_id} status updated to {status}")

class DependencyInjectionContainer:
    """依赖注入容器"""
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self.factories: Dict[str, callable] = {}
        self.singletons: Dict[str, Any] = {}
        
    def register_service(self, name: str, service: Any, singleton: bool = True):
        """注册服务"""
        
        if singleton:
            self.singletons[name] = service
        else:
            self.services[name] = service
        
        logger.info(f"Service {name} registered as {'singleton' if singleton else 'transient'}")
    
    def register_factory(self, name: str, factory: callable):
        """注册工厂方法"""
        self.factories[name] = factory
        logger.info(f"Factory {name} registered")
    
    def get_service(self, name: str) -> Optional[Any]:
        """获取服务"""
        
        # 首先检查单例
        if name in self.singletons:
            return self.singletons[name]
        
        # 检查普通服务
        if name in self.services:
            return self.services[name]
        
        # 检查工厂
        if name in self.factories:
            service = self.factories[name]()
            if name in self.singletons:
                self.singletons[name] = service
            return service
        
        return None
    
    def inject_dependencies(self, instance: Any) -> Any:
        """注入依赖"""
        
        # 获取实例的类
        cls = type(instance)
        
        # 检查类的__init__方法参数
        init_signature = inspect.signature(cls.__init__)
        
        for param_name, param in init_signature.parameters.items():
            if param_name == 'self':
                continue
            
            # 跳过非注入参数
            if param.annotation == inspect.Parameter.empty:
                continue
            
            # 尝试获取服务
            service = self.get_service(param_name)
            if service is not None:
                setattr(instance, param_name, service)
                logger.debug(f"Injected {param_name} into {cls.__name__}")
        
        return instance

class ConfigurationManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or os.path.join(os.path.dirname(__file__), "..", "config")
        self.agent_configs: Dict[str, AgentConfig] = {}
        self.global_config: Dict[str, Any] = {}
        
        # 创建配置目录
        os.makedirs(self.config_dir, exist_ok=True)
        
        # 加载配置
        self._load_configs()
    
    def _load_configs(self):
        """加载配置"""
        
        # 加载全局配置
        global_config_file = os.path.join(self.config_dir, "global.json")
        if os.path.exists(global_config_file):
            try:
                with open(global_config_file, 'r', encoding='utf-8') as f:
                    self.global_config = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load global config: {e}")
        
        # 加载Agent配置
        agent_config_dir = os.path.join(self.config_dir, "agents")
        if os.path.exists(agent_config_dir):
            for config_file in os.listdir(agent_config_dir):
                if config_file.endswith('.json'):
                    config_path = os.path.join(agent_config_dir, config_file)
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                            config = AgentConfig(**config_data)
                            self.agent_configs[config.name] = config
                    except Exception as e:
                        logger.error(f"Failed to load agent config {config_file}: {e}")
    
    def save_config(self, config: AgentConfig):
        """保存Agent配置"""
        
        self.agent_configs[config.name] = config
        
        # 保存到文件
        agent_config_dir = os.path.join(self.config_dir, "agents")
        os.makedirs(agent_config_dir, exist_ok=True)
        
        config_file = os.path.join(agent_config_dir, f"{config.name}.json")
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(config), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save agent config {config.name}: {e}")
    
    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """获取Agent配置"""
        return self.agent_configs.get(agent_name)
    
    def get_global_config(self) -> Dict[str, Any]:
        """获取全局配置"""
        return self.global_config
    
    def update_global_config(self, config: Dict[str, Any]):
        """更新全局配置"""
        self.global_config.update(config)
        
        # 保存到文件
        global_config_file = os.path.join(self.config_dir, "global.json")
        try:
            with open(global_config_file, 'w', encoding='utf-8') as f:
                json.dump(self.global_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save global config: {e}")

class AgentFactory:
    """Agent工厂"""
    
    def __init__(self, config_dir: str = None):
        self.registry = AgentRegistry()
        self.container = DependencyInjectionContainer()
        self.config_manager = ConfigurationManager(config_dir)
        
        # 注册默认服务
        self._register_default_services()
        
        # 注册默认Agent
        self._register_default_agents()
    
    def _register_default_services(self):
        """注册默认服务"""
        
        # 注册协作管理器
        from .collaboration_manager import CollaborationManager
        collaboration_manager = CollaborationManager()
        self.container.register_service("collaboration_manager", collaboration_manager)
        
        # 注册数据共享层
        from .collaboration_manager import DataSharingLayer
        data_sharing = DataSharingLayer()
        self.container.register_service("data_sharing", data_sharing)
        
        # 注册决策融合器
        from .collaboration_manager import DecisionFusion
        decision_fusion = DecisionFusion()
        self.container.register_service("decision_fusion", decision_fusion)
        
        # 注册监控系统
        from .collaboration_manager import MonitoringSystem
        monitoring = MonitoringSystem()
        self.container.register_service("monitoring", monitoring)
        
        logger.info("Default services registered")
    
    def _register_default_agents(self):
        """注册默认Agent"""
        
        # 气候Agent
        climate_config = AgentConfig(
            name="climate",
            type="climate",
            class_name="ClimateAgent",
            module_path="agent.climate_agent",
            version="1.0.0",
            enabled=True,
            dependencies=[],
            config_params={
                "data_sources": ["NASA_POWER", "Open-Meteo", "WorldClim"],
                "cache_enabled": True,
                "cache_expiry": 3600
            }
        )
        self.register_agent(climate_config)
        
        # 作物Agent
        crop_config = AgentConfig(
            name="crop",
            type="crop",
            class_name="CropAgent",
            module_path="agent.crop_agent",
            version="1.0.0",
            enabled=True,
            dependencies=[],
            config_params={
                "crop_database": "data/crop_database.json",
                "growth_models": "data/growth_models.json"
            }
        )
        self.register_agent(crop_config)
        
        # 生长Agent
        growth_config = AgentConfig(
            name="growth",
            type="growth",
            class_name="GrowthAgent",
            module_path="agent.growth_agent",
            version="1.0.0",
            enabled=True,
            dependencies=["climate", "crop"],
            config_params={
                "growth_models": "data/growth_models.json",
                "prediction_horizon": 30
            }
        )
        self.register_agent(growth_config)
        
        # 生态Agent
        eco_config = AgentConfig(
            name="eco",
            type="eco",
            class_name="EcoAgent",
            module_path="agent.eco_agent",
            version="1.0.0",
            enabled=True,
            dependencies=["climate", "crop", "growth"],
            config_params={
                "eco_models": "data/eco_models.json",
                "sustainability_metrics": ["biodiversity", "carbon_footprint", "water_usage"]
            }
        )
        self.register_agent(eco_config)
        
        # 市场Agent
        market_config = AgentConfig(
            name="market",
            type="market",
            class_name="MarketAgent",
            module_path="agent.market_agent",
            version="1.0.0",
            # ⚠️ 实验性 mock 原型，使用假数据，违反真实性红线，禁止接入生产链路
            enabled=False,
            dependencies=[],
            config_params={
                "data_sources": ["FAO", "USDA", "local_markets"],
                "prediction_models": ["linear_regression", "neural_network", "random_forest"]
            }
        )
        self.register_agent(market_config)
        
        # 财务Agent
        finance_config = AgentConfig(
            name="finance",
            type="finance",
            class_name="FinanceAgent",
            module_path="agent.finance_agent",
            version="1.0.0",
            # ⚠️ 实验性 mock 原型，使用假数据，违反真实性红线，禁止接入生产链路
            enabled=False,
            dependencies=["market"],
            config_params={
                "economic_indicators": ["GDP", "inflation", "interest_rates"],
                "subsidy_database": "data/subsidy_database.json"
            }
        )
        self.register_agent(finance_config)
        
        # 风险Agent
        risk_config = AgentConfig(
            name="risk",
            type="risk",
            class_name="RiskAgent",
            module_path="agent.risk_agent",
            version="1.0.0",
            # ⚠️ 实验性 mock 原型，使用假数据，违反真实性红线，禁止接入生产链路
            enabled=False,
            dependencies=["climate", "crop", "market", "finance"],
            config_params={
                "risk_types": ["natural", "market", "technical", "policy"],
                "insurance_database": "data/insurance_database.json"
            }
        )
        self.register_agent(risk_config)
        
        logger.info("Default agents registered")
    
    def register_agent(self, config: AgentConfig):
        """注册Agent"""
        self.registry.register_agent(config)
        self.config_manager.save_config(config)
    
    def create_agent(self, agent_name: str) -> Optional[Any]:
        """创建Agent实例"""
        
        # 获取配置
        config = self.registry.get_agent_config(agent_name)
        if not config:
            logger.error(f"Agent config not found: {agent_name}")
            return None
        
        # 检查是否已创建
        agent_id = f"{config.type}_{config.name}"
        if agent_id in self.registry.agent_instances:
            logger.info(f"Agent instance already exists: {agent_id}")
            return self.registry.agent_instances[agent_id]
        
        try:
            # 动态导入模块
            module = importlib.import_module(config.module_path)
            agent_class = getattr(module, config.class_name)
            
            # 创建实例
            agent_instance = agent_class()
            
            # 注入依赖
            agent_instance = self.container.inject_dependencies(agent_instance)
            
            # 注册到容器
            self.container.register_service(agent_id, agent_instance)
            
            # 存储实例
            self.registry.agent_instances[agent_id] = agent_instance
            self.registry.update_agent_status(agent_id, AgentStatus.INITIALIZED)
            
            logger.info(f"Agent instance created: {agent_id}")
            return agent_instance
            
        except Exception as e:
            logger.error(f"Failed to create agent {agent_name}: {e}")
            self.registry.update_agent_status(agent_id, AgentStatus.ERROR)
            return None
    
    def start_agent(self, agent_name: str) -> bool:
        """启动Agent"""
        
        # 获取配置
        config = self.registry.get_agent_config(agent_name)
        if not config:
            logger.error(f"Agent config not found: {agent_name}")
            return False
        
        agent_id = f"{config.type}_{config.name}"
        
        # 检查状态
        if self.registry.get_agent_status(agent_id) == AgentStatus.RUNNING:
            logger.info(f"Agent already running: {agent_id}")
            return True
        
        # 创建实例（如果不存在）
        if agent_id not in self.registry.agent_instances:
            if not self.create_agent(agent_name):
                return False
        
        # 启动Agent
        agent_instance = self.registry.agent_instances[agent_id]
        
        try:
            # 如果Agent有start方法，调用它
            if hasattr(agent_instance, 'start'):
                agent_instance.start()
            
            # 注册到协作管理器
            collaboration_manager = self.container.get_service("collaboration_manager")
            if collaboration_manager:
                collaboration_manager.register_agent(
                    agent_id,
                    config.type,
                    agent_instance
                )
            
            # 更新状态
            self.registry.update_agent_status(agent_id, AgentStatus.RUNNING)
            
            logger.info(f"Agent started: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start agent {agent_id}: {e}")
            self.registry.update_agent_status(agent_id, AgentStatus.ERROR)
            return False
    
    def stop_agent(self, agent_name: str) -> bool:
        """停止Agent"""
        
        # 获取配置
        config = self.registry.get_agent_config(agent_name)
        if not config:
            logger.error(f"Agent config not found: {agent_name}")
            return False
        
        agent_id = f"{config.type}_{config.name}"
        
        # 检查状态
        if self.registry.get_agent_status(agent_id) != AgentStatus.RUNNING:
            logger.info(f"Agent not running: {agent_id}")
            return True
        
        # 停止Agent
        agent_instance = self.registry.agent_instances.get(agent_id)
        
        try:
            # 如果Agent有stop方法，调用它
            if agent_instance and hasattr(agent_instance, 'stop'):
                agent_instance.stop()
            
            # 从协作管理器注销
            collaboration_manager = self.container.get_service("collaboration_manager")
            if collaboration_manager:
                collaboration_manager.agents.pop(agent_id, None)
            
            # 更新状态
            self.registry.update_agent_status(agent_id, AgentStatus.STOPPED)
            
            logger.info(f"Agent stopped: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop agent {agent_id}: {e}")
            return False
    
    def get_agent(self, agent_name: str) -> Optional[Any]:
        """获取Agent实例"""
        
        config = self.registry.get_agent_config(agent_name)
        if not config:
            return None
        
        agent_id = f"{config.type}_{config.name}"
        
        # 如果实例不存在，创建它
        if agent_id not in self.registry.agent_instances:
            return self.create_agent(agent_name)
        
        return self.registry.agent_instances[agent_id]
    
    def list_agents(self, agent_type: str = None, status: AgentStatus = None) -> List[str]:
        """列出Agent"""
        return self.registry.list_agents(agent_type, status)
    
    def get_enabled_agents(self, agent_type: str = None) -> List[str]:
        """获取启用的Agent"""
        return self.registry.get_enabled_agents(agent_type)
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        
        status = {
            "total_agents": len(self.registry.agents),
            "enabled_agents": len(self.registry.get_enabled_agents()),
            "running_agents": len(self.registry.list_agents(status=AgentStatus.RUNNING)),
            "initialized_agents": len(self.registry.list_agents(status=AgentStatus.INITIALIZED)),
            "error_agents": len(self.registry.list_agents(status=AgentStatus.ERROR)),
            "agent_details": {}
        }
        
        # 获取每个Agent的详细信息
        for agent_id, agent_info in self.registry.agents.items():
            status["agent_details"][agent_id] = {
                "name": agent_info["name"],
                "type": agent_info["type"],
                "version": agent_info["version"],
                "enabled": agent_info["enabled"],
                "status": self.registry.get_agent_status(agent_id).value,
                "dependencies": self.registry.get_agent_config(agent_id).dependencies
            }
        
        return status
    
    def start_all_agents(self) -> Dict[str, bool]:
        """启动所有启用的Agent"""
        
        results = {}
        enabled_agents = self.registry.get_enabled_agents()
        
        for agent_name in enabled_agents:
            results[agent_name] = self.start_agent(agent_name)
        
        return results
    
    def stop_all_agents(self) -> Dict[str, bool]:
        """停止所有运行的Agent"""
        
        results = {}
        running_agents = self.registry.list_agents(status=AgentStatus.RUNNING)
        
        for agent_id in running_agents:
            # 从agent_id中提取名称
            agent_name = agent_id.split('_', 1)[1]
            results[agent_name] = self.stop_agent(agent_name)
        
        return results
    
    def restart_agent(self, agent_name: str) -> bool:
        """重启Agent"""
        
        # 先停止
        if not self.stop_agent(agent_name):
            return False
        
        # 再启动
        return self.start_agent(agent_name)
    
    def update_agent_config(self, agent_name: str, config_params: Dict[str, Any]) -> bool:
        """更新Agent配置"""
        
        config = self.registry.get_agent_config(agent_name)
        if not config:
            return False
        
        # 更新配置参数
        config.config_params.update(config_params)
        
        # 保存配置
        self.config_manager.save_config(config)
        
        # 如果Agent正在运行，重启它以应用新配置
        agent_id = f"{config.type}_{config.name}"
        if self.registry.get_agent_status(agent_id) == AgentStatus.RUNNING:
            self.restart_agent(agent_name)
        
        logger.info(f"Agent config updated: {agent_name}")
        return True
    
    def get_agent_dependencies(self, agent_name: str) -> List[str]:
        """获取Agent依赖"""
        
        config = self.registry.get_agent_config(agent_name)
        if not config:
            return []
        
        return config.dependencies
    
    def resolve_dependencies(self, agent_name: str) -> List[str]:
        """解析Agent依赖"""
        
        config = self.registry.get_agent_config(agent_name)
        if not config:
            return []
        
        resolved = []
        to_resolve = config.dependencies.copy()
        
        while to_resolve:
            dependency = to_resolve.pop(0)
            
            if dependency not in resolved:
                resolved.append(dependency)
                
                # 获取依赖的配置
                dep_config = self.registry.get_agent_config(dependency)
                if dep_config:
                    # 添加依赖的依赖
                    for dep_dep in dep_config.dependencies:
                        if dep_dep not in resolved and dep_dep not in to_resolve:
                            to_resolve.append(dep_dep)
        
        return resolved
    
    def validate_dependencies(self, agent_name: str) -> Dict[str, bool]:
        """验证Agent依赖"""
        
        config = self.registry.get_agent_config(agent_name)
        if not config:
            return {"valid": False, "errors": ["Agent config not found"]}
        
        errors = []
        resolved = self.resolve_dependencies(agent_name)
        
        # 检查所有依赖是否都已注册
        for dependency in config.dependencies:
            if dependency not in resolved:
                errors.append(f"Dependency '{dependency}' not found or has circular dependencies")
        
        # 检查是否有循环依赖
        if len(resolved) != len(set(resolved)):
            errors.append("Circular dependencies detected")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "resolved_dependencies": resolved
        }