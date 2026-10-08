---
name: 作物-分区适配推荐
description: 根据气候分区数据 + 用户偏好（食用/观赏/香料、空间、难度、采收周期）推荐适配作物，输出适配度评分、种植周期、易失败风险和兜底品种。
version: "1.0"
---

# 作物-分区适配推荐

> Skill id: `crop_adapt` · 领域: `crop` · 实现 Agent: `CropAgent`

## 能力说明

根据气候分区数据 + 用户偏好（食用/观赏/香料、空间、难度、采收周期）推荐适配作物，输出适配度评分、种植周期、易失败风险和兜底品种。

## 调用方式

本 Skill 已由 MCP 工具 `agri_recommend_crops` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `zone_data` | dict, from climate_match |
| `purpose` | str |
| `space_sqm` | float |
| `difficulty` | str |
| `harvest_time_days` | int, optional |
| `container` | bool |

## 输出

| 字段 | 类型 |
|---|---|
| `crop_name` | str |
| `adapt_score` | float 0-1 |
| `growth_days` | int |
| `reason` | str |
| `risk_flags` | list |
| `fallback_variety` | str |

## 数据来源

- FAO CropInfo
- 中国作物栽培数据库
- IPNI 植物名称索引

## 置信度计算

作物-环境约束匹配度评分 + 品种适应性数据密度

## 安全边界

> 仅供种植参考，不替代当地农技站指导；不推荐有检疫风险的品种

## 复用价值

连接地理数据和用户需求的枢纽 Skill，是产品差异化的核心

## 依赖

- `climate_match`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/crop_adapt.json` 生成，请勿手改。*
