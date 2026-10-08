---
name: 农业分区气候匹配
description: 根据地块经纬度匹配 Köppen-Geiger 气候带 + FAO 农业分区，输出分区元数据和关键环境约束（温度/降水/土壤/pH/霜冻风险）。支持微气候修正（阳台朝向/楼层/遮蔽）。
version: "1.0"
---

# 农业分区气候匹配

> Skill id: `climate_match` · 领域: `climate` · 实现 Agent: `ClimateAgent`

## 能力说明

根据地块经纬度匹配 Köppen-Geiger 气候带 + FAO 农业分区，输出分区元数据和关键环境约束（温度/降水/土壤/pH/霜冻风险）。支持微气候修正（阳台朝向/楼层/遮蔽）。

## 调用方式

本 Skill 已由 MCP 工具 `agri_match_zone` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `lat` | float |
| `lon` | float |
| `scene` | str |
| `floor` | int |
| `orientation` | str |
| `city` | str |

## 输出

| 字段 | 类型 |
|---|---|
| `zone_id` | str |
| `zone_name` | str |
| `koppen_class` | str |
| `temperature_range` | dict |
| `precipitation_mm_yr` | int |
| `soil_constraint` | dict |
| `frost_risk` | bool |
| `growing_season_days` | int |
| `confidence` | dict |

## 数据来源

- WorldClim 2.1
- FAO GAEZ
- ISRIC SoilGrids
- NASA POWER

## 置信度计算

基于数据覆盖度 + 数据新鲜度 + 分区精度综合评分

## 安全边界

> 不替代专业农业气象咨询；极区/极端气候区需人工复核

## 复用价值

是整个系统的地理基准层，所有作物推荐/生长计划/设备建议均依赖此 Skill 的输出

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/climate_match.json` 生成，请勿手改。*
