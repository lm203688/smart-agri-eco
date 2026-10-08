---
name: 病虫害与营养缺乏诊断
description: 根据症状描述（+ 可选图像识别）+ 作物生长阶段 + 环境数据，诊断病虫害/营养缺乏，输出诊断结果、严重程度、处理建议和替代诊断。已由 agent/pest_agent.py (PestAgent) 真实实现。
version: "1.1"
---

# 病虫害与营养缺乏诊断

> Skill id: `pest_diagnose` · 领域: `pest` · 实现 Agent: `PestAgent`

## 能力说明

根据症状描述（+ 可选图像识别）+ 作物生长阶段 + 环境数据，诊断病虫害/营养缺乏，输出诊断结果、严重程度、处理建议和替代诊断。已由 agent/pest_agent.py (PestAgent) 真实实现。

## 调用方式

本 Skill 已由 MCP 工具 `agri_diagnose_pest` 承接。通过 MCP 调用即可，无需自行实现。

## 输入

| 参数 | 类型 |
|---|---|
| `crop` | str |
| `symptom_description` | str |
| `image_reference` | str, optional |
| `growth_stage` | str |
| `environment` | dict |

## 输出

| 字段 | 类型 |
|---|---|
| `diagnosis` | str |
| `severity` | str: light/medium/severe |
| `actions` | list |
| `alternative_diagnoses` | list |
| `diagnosis_confidence` | float |
| `signature` | str |

## 数据来源

- crop_adapt_db.json (key_risks)
- 内置病虫害知识库
- 中国植物病虫害数据库(IPM)
- 可插拔视觉模型

## 置信度计算

症状-清单关键词匹配度 + 名称片段共享 + 类别信号 + 知识库覆盖度；视觉辅助时加权

## 增强能力（可插拔）

pluggable via env AGRI_VISION_URL/AGRI_VISION_KEY/AGRI_VISION_MODEL (OpenAI-compatible); default rule-based offline

## 安全边界

> 不替代专业植保人员；疑似检疫性病虫害必须上报

## 复用价值

高粘性用户留存 Skill——种死了能救回来是用户不流失的关键

## 依赖

- `climate_match`
- `crop_adapt`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/pest_diagnose.json` 生成，请勿手改。*
