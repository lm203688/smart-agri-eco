# field_holdout · L2 田间留出基准层

> **层级定义（对齐 `项目全面提升报告_2026-10-26.md` §四 P0-1 三层分类）**

| 层 | 名称 | 数据源 | 允许用途 |
|---|---|---|---|
| L0 | engineering_regression | 被测模型固定快照（±30% 容差） | 验证"不变"，防回归 |
| L1 | agronomic_reference | 独立文献/专家标注/机理模型 | 证明接近真实农艺 |
| **L2** | **field_holdout** | 按批次/站点/时间隔离 | **评估泛化能力** |

## 本目录是什么

**L2 田间留出基准**：用**真实种植批次**数据，按站点/时间做隔离（out-of-sample 留出），评估模型对**未见过环境**的泛化能力。这是证据金字塔的**最高层**——只有 L2 通过才支持"跨域可用"声明。

## 当前状态：0 用例（等 P1 真实批次）

**本目录目前为空**——因为 L2 需要**真实田间数据**：

- 真实种植批次（Plot/GrowBatch/Observation/Outcome，见 `schemas/grow_batch.schema.json`）
- 按站点/时间隔离的留出集
- 至少一个完整生长周期的实测产量

这些**只能来自真实设备 + 真实用户 + 时间积累**（P0-6 真实批次），AI 无法自造。

## 用例格式约定（未来填充时）

```json
{
  "id": "l2_<crop>_<site>_<season>",
  "axis": "target_prediction",
  "evidence_layer": "L2_field_holdout",
  "holdout_split": "by_site | by_season | by_block",
  "train_sites": ["<站点A>", "<站点B>"],
  "test_site": "<站点C>",
  "expected": {"target_prediction": {"yield_estimate_g": {"value": <实测>, "tol_frac": 0.20}}}
}
```

## 诚实边界

- 在获得第一个 L2 用例前，**不得**声称"模型跨域泛化已验证"。
- L2 是 P1 真实批次 MVP 的**产物**，不是 AI 自主可产生的。

## 前置条件（G1 后 + P1 批次）

L2 填充依赖 P0-6 真实批次执行（需真实设备/用户）+ P1 MVP。按 CORE_OBJECTIVE §八 判据 **G1 前不开工**。本目录仅预置语义与格式。
