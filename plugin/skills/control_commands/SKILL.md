---
name: L3 执行控制指令生成
description: 把 GrowthAgent 种植计划 + EcoAgent 设备推荐翻译为硬件无关的控制指令协议（灌溉/施肥/补光/温控/CO2/通风），并给出执行补偿（车载颠簸、开放环境波动、设备故障降级）。经 orchestrator.call_skill('control_commands') 统一调用。
version: "1.0"
---

# L3 执行控制指令生成

> Skill id: `control_commands` · 领域: `control` · 实现 Agent: `ControlAgent`

## 能力说明

把 GrowthAgent 种植计划 + EcoAgent 设备推荐翻译为硬件无关的控制指令协议（灌溉/施肥/补光/温控/CO2/通风），并给出执行补偿（车载颠簸、开放环境波动、设备故障降级）。经 orchestrator.call_skill('control_commands') 统一调用。

## 调用方式

**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。
本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；
若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。

## 输入

| 参数 | 类型 |
|---|---|
| `scene` | str |
| `crop` | str |
| `zone_id` | str |
| `growth_plan` | dict |
| `devices` | list |
| `env_recipe` | dict, optional |

## 输出

| 字段 | 类型 |
|---|---|
| `actuator` | str |
| `command` | str |
| `value` | any |
| `unit` | str |
| `schedule` | str |
| `compensation` | dict |

## 数据来源

- Env Recipe 协议 v1
- global_zones 气候基线
- device_catalog

## 置信度计算

阶段覆盖度 + 设备类别覆盖度评分

## 安全边界

> 指令为硬件无关意图，真实执行需经 MQTT/Node-RED 网关下发；不假设具体设备已接入，缺失设备给人工等效操作

## 复用价值

执行控制层核心——把决策引擎输出变成可下发的『驱动语言』，对应战略指引 L3 卡位

## 依赖

- `growth_plan`
- `device_recommend`
- `env_recipe`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/control_commands.json` 生成，请勿手改。*
