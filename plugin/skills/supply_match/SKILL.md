---
name: 供需撮合（采摘即食）
description: 根据地理位置 + 农产品类型 + 数量 + 新鲜度要求，撮合本地供需双方。先做社区内循环（3km 内），逐步扩展到城市级。
version: "1.0"
---

# 供需撮合（采摘即食）

> Skill id: `supply_match` · 领域: `eco` · 实现 Agent: `EcoAgent`

## 能力说明

根据地理位置 + 农产品类型 + 数量 + 新鲜度要求，撮合本地供需双方。先做社区内循环（3km 内），逐步扩展到城市级。

## 调用方式

**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。
本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；
若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。

## 输入

| 参数 | 类型 |
|---|---|
| `user_location` | dict |
| `produce_type` | str |
| `quantity_kg` | float |
| `freshness_requirement` | str |

## 输出

| 字段 | 类型 |
|---|---|
| `provider_type` | str |
| `distance_km` | float |
| `freshness_score` | float |
| `match_quality` | float |

## 数据来源

- 社区用户种植数据
- 本地农场数据
- 物流时效数据

## 置信度计算

基于地理距离 + 新鲜度要求匹配 + 供需量平衡

## 安全边界

> 不处理大规模商业交易；食品安全责任由交易双方自行负责

## 复用价值

L5 消费服务层的核心 Skill——实现'采摘即食'愿景的关键技术出口

## 依赖

- `climate_match`
- `growth_plan`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/supply_match.json` 生成，请勿手改。*
