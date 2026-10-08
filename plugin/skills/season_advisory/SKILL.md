---
name: 物候推演与霜冻锚定播期窗口
description: 按调用方提供的 12 个月均温推导无霜期，并结合 WOFOST 积温参数给出各作物的最早/最晚安全播种日；也可单查某作物在给定日均温下的出苗/开花/成熟天数。已由 agent/season_agent.py (SeasonAgent) 真实实现。
version: "1.0"
---

# 物候推演与霜冻锚定播期窗口

> Skill id: `season_advisory` · 领域: `growth` · 实现 Agent: `SeasonAgent`

## 能力说明

按调用方提供的 12 个月均温推导无霜期，并结合 WOFOST 积温参数给出各作物的最早/最晚安全播种日；也可单查某作物在给定日均温下的出苗/开花/成熟天数。已由 agent/season_agent.py (SeasonAgent) 真实实现。

## 调用方式

本 Skill 已由 MCP 工具 `agri_season_advisory` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `mode` | any |
| `monthly_mean_c` | any |
| `crops` | any |
| `crop` | any |
| `mean_temp_c` | any |
| `zone` | any |
| `date` | any |
| `frost_threshold_c` | any |
| `safety_margin_days` | any |

## 输出

| 字段 | 类型 |
|---|---|
| `frost_free` | any |
| `windows` | any |
| `emergence_days` | any |
| `anthesis_days_from_sow` | any |
| `maturity_days_from_sow` | any |
| `in_window` | any |

## 数据来源

- data/wofost_phenology_reference.json（移植自 ajwdewit/WOFOST_crop_parameters @ wofost81，EUPL 1.2，需署名）
- 气候输入由调用方提供（WorldClim 2.1 / Open-Meteo / 本地气象站）

## 置信度计算

仅模型可用+作物被覆盖时给 0.6（medium）：理论积温推演、未本地校准、不含春化与光周期机制；不可用 0.0

## 安全边界

> 播期为理论推演，实际播种须结合当地天气预报、土壤温度与品种说明

## 复用价值

补上 growth_agent 此前完全缺失的『何时种 / 长多快』微观层，是 Env Recipe 从静态参数走向动态时序的关键一步

## 依赖

- `growth_plan`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/season_advisory.json` 生成，请勿手改。*
