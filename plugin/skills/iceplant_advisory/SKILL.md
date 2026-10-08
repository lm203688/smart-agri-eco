---
name: 冰菜阳台种植建议
description: 为新增作物冰菜（Mesembryanthemum crystallinum）提供分区适配与阳台种植建议，由 skill_factory 自动生成，扩大 CropAgent 覆盖。
version: "1.0"
---

# 冰菜阳台种植建议

> Skill id: `iceplant_advisory` · 领域: `crop` · 实现 Agent: `CropAgent`

## 能力说明

为新增作物冰菜（Mesembryanthemum crystallinum）提供分区适配与阳台种植建议，由 skill_factory 自动生成，扩大 CropAgent 覆盖。

## 调用方式

**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。
本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；
若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。

## 输入

| 参数 | 类型 |
|---|---|
| `zone_id` | any |
| `scene` | any |
| `space_sqm` | any |

## 输出

| 字段 | 类型 |
|---|---|
| `adapt_score` | any |
| `growth_days` | any |
| `risk_flags` | any |
| `fallback_variety` | any |

## 数据来源

- 用户反馈
- 农艺通识

## 置信度计算

seed 适配分 + flywheel 实测校准

## 安全边界

> 建议结合本地实测，不替代农技人员

## 复用价值

新增作物即自动注册为可复用 Skill，降低重复工程

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/iceplant_advisory.json` 生成，请勿手改。*
