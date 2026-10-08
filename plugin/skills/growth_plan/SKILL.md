---
name: 生长周期管理与种植计划
description: 根据选定作物 + 分区数据 + 种植场景生成完整种植计划（播种→定植→管理→采收），含关键事件、风险提示、兜底救活方案。
version: "1.0"
---

# 生长周期管理与种植计划

> Skill id: `growth_plan` · 领域: `growth` · 实现 Agent: `GrowthAgent`

## 能力说明

根据选定作物 + 分区数据 + 种植场景生成完整种植计划（播种→定植→管理→采收），含关键事件、风险提示、兜底救活方案。

## 调用方式

本 Skill 已由 MCP 工具 `agri_growth_plan` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `crop` | str |
| `zone_data` | dict |
| `start_date` | str |
| `scene` | str |

## 输出

| 字段 | 类型 |
|---|---|
| `phases` | list of {phase, day_range, actions} |
| `key_events` | list |
| `risk_alerts` | list |
| `rescue_plan` | str |

## 数据来源

- FAO FAOSTAT 作物统计
- 中国农业技术知识图谱
- USDA Crop Production

## 置信度计算

基于作物-场景-季节组合的知识覆盖率评分

## 安全边界

> 不替代农艺师现场指导；特殊作物（药用/珍稀）需专业复核

## 复用价值

面向 C 端用户的核心体验 Skill，直接决定用户种植成功率

## 依赖

- `climate_match`
- `crop_adapt`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/growth_plan.json` 生成，请勿手改。*
