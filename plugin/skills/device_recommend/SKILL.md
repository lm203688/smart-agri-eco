---
name: 种植设备与工具推荐
description: 根据种植场景（阳台/车载/屋顶/教育）+ 作物类型 + 分区数据 + 预算，推荐适配的设备/工具组合（种植机/传感器/水肥/补光），输出设备清单、价格和推荐理由。
version: "1.0"
---

# 种植设备与工具推荐

> Skill id: `device_recommend` · 领域: `eco` · 实现 Agent: `EcoAgent`

## 能力说明

根据种植场景（阳台/车载/屋顶/教育）+ 作物类型 + 分区数据 + 预算，推荐适配的设备/工具组合（种植机/传感器/水肥/补光），输出设备清单、价格和推荐理由。

## 调用方式

**尚未暴露为 MCP 工具**（注册表已定义，但当前无可直接调用的 MCP 入口）。
本 Skill 的语义与 I/O 契约如下，供 Agent 规划链路时参考；
若要落地调用，请先确认其在 `docs/CORE_OBJECTIVE.md` §八 优先级判据下的排期。

## 输入

| 参数 | 类型 |
|---|---|
| `scene` | str |
| `crop` | str |
| `zone_data` | dict |
| `budget_cny` | float |

## 输出

| 字段 | 类型 |
|---|---|
| `device_name` | str |
| `category` | str |
| `price_cny` | float |
| `reason` | str |

## 数据来源

- 设备商合作数据库
- 电商平台价格数据
- 场景适配经验库

## 置信度计算

基于场景-作物-预算三维匹配度评分

## 安全边界

> 不替代设备商官方建议；涉及电气安全的设备需确认认证

## 复用价值

生态化原则的核心变现 Skill——通过设备分成实现硬件生态收入

## 依赖

- `climate_match`
- `crop_adapt`

---

*本文件由 `scripts/build_agent_plugin.py` 从 `skills/registry/device_recommend.json` 生成，请勿手改。*
