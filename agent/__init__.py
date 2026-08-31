# 智慧农业生态 · 多 Agent 协同框架
#
# 架构：ClimateAgent → CropAgent → GrowthAgent → EcoAgent
# 对标 SwarmLabs Planner→Executor→Verifier 三 Agent 串行模式
# 差异：增加 EcoAgent（生态撮合层），形成四 Agent 串行+反馈闭环

from .climate_agent import ClimateAgent
from .crop_agent import CropAgent
from .growth_agent import GrowthAgent
from .eco_agent import EcoAgent
from .orchestrator import AgriOrchestrator

__all__ = [
    "ClimateAgent",
    "CropAgent",
    "GrowthAgent",
    "EcoAgent",
    "AgriOrchestrator",
]
