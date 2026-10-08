---
name: L2 采收期/产量/风险预测
description: 基于 start_date + 种植计划阶段时长 + 分区气候（GDD-lite 修正）+ Env Recipe 环境完备度，预测采收日期、产量与风险。经 orchestrator.call_skill('harvest_forecast') 统一调用。
version: "1.0"
---

# L2 采收期/产量/风险预测

> Skill id: `harvest_forecast` · 领域: `forecast` · 实现 Agent: `ForecastAgent`

## 能力说明

基于 start_date + 种植计划阶段时长 + 分区气候（GDD-lite 修正）+ Env Recipe 环境完备度，预测采收日期、产量与风险。经 orchestrator.call_skill('harvest_forecast') 统一调用。

## 调用方式

**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。
本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；
若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。

## 输入

| 参数 | 类型 |
|---|---|
| `crop` | str |
| `zone_id` | str |
| `start_date` | str |
| `growth_plan` | dict |
| `zone_climate` | list, optional |
| `env_recipe` | dict, optional |
| `adapt_score` | float, optional |

## 输出

| 字段 | 类型 |
|---|---|
| `harvest_date` | str |
| `adjusted_duration_days` | int |
| `yield_estimate_g` | int |
| `risk_forecast` | list |

## 数据来源

- global_zones 气候基线
- Env Recipe 协议 v1
- 公开农艺基准产量表

## 置信度计算

环境完备度 + 气候适宜度 + 校准数据有无综合评分

## 安全边界

> 产量为启发式估计（公开农艺基准 × 气候适宜度 × 环境完备度），非 WOFOST 机制模型；无实测校准时置信度压低并标注需 execution_log/outcome 回流

## 复用价值

预测系统（L2）补齐——决策引擎之上的产量/采收/风险预判，是 AI 介入点清单第 4 项

## 依赖

- `growth_plan`
- `env_recipe`
- `climate_match`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/harvest_forecast.json` 生成，请勿手改。*
