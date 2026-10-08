---
name: 养分管理与阶段化施肥方案
description: 根据作物 + 科属养分需求 + 生长周期 + 容器/场景，生成阶段化施肥方案（播种→苗期→生长→采收），给出 NPK 侧重、浓度、频率、单次用量与安全边界。已由 agent/nutrition_agent.py (NutritionAgent) 真实实现。
version: "1.0"
---

# 养分管理与阶段化施肥方案

> Skill id: `nutrition_plan` · 领域: `soil` · 实现 Agent: `NutritionAgent`

## 能力说明

根据作物 + 科属养分需求 + 生长周期 + 容器/场景，生成阶段化施肥方案（播种→苗期→生长→采收），给出 NPK 侧重、浓度、频率、单次用量与安全边界。已由 agent/nutrition_agent.py (NutritionAgent) 真实实现。

## 调用方式

本 Skill 已由 MCP 工具 `agri_nutrition_plan` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `crop` | str |
| `scene` | str |
| `growth_stage` | str |
| `growth_days` | int |
| `container_volume_l` | float |
| `start_date` | str |

## 输出

| 字段 | 类型 |
|---|---|
| `profile_label` | str |
| `npk_strategy` | str |
| `phases` | list of {phase, day_range, fertilizer, npk, frequency, dilution, amount_guidance, notes} |
| `deficiency_quickref` | dict |
| `signature` | str |

## 数据来源

- crop_adapt_db.json (family/growth_days/water_ml_day/ph_range)
- 内置养分需求知识库（按科属 NPK 侧重）

## 置信度计算

数据齐备度（作物命中 DB）+ 科属 NPK 匹配覆盖度；未知作物走保守通用方案

## 安全边界

> 不替代土壤/基质检测；严格按标签稀释、宁稀勿浓、忌高温施肥；有机肥须腐熟

## 复用价值

L3 执行控制层核心 Skill——水肥一体化直接决定产量与品质，是用户高粘性留存能力

## 依赖

- `crop_adapt`
- `growth_plan`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/nutrition_plan.json` 生成，请勿手改。*
