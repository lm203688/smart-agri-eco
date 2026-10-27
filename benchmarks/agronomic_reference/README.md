# agronomic_reference · L1 农艺参考基准层

> **层级定义（对齐 `项目全面提升报告_2026-10-26.md` §四 P0-1 三层分类）**

| 层 | 名称 | 数据源 | 允许用途 |
|---|---|---|---|
| L0 | engineering_regression | 被测模型固定快照（±30% 容差） | 验证"不变"，防回归 |
| **L1** | **agronomic_reference** | 独立文献/专家标注/机理模型 | **证明接近真实农艺** |
| L2 | field_holdout | 按批次/站点/时间隔离 | 评估泛化能力 |

## 本目录是什么

**L1 农艺参考基准**：用**独立于被测模型**的农艺真值（同行评议文献、农艺专家标注、独立机理模型如 WOFOST/PCSE）作为 `expected`，证明模型输出**接近真实农艺**，而非仅"行为不变"。

## 当前状态：0 用例（TODO）

**本目录目前为空**——因为 L1 需要外部真值数据：

- **文献真值**：需从同行评议文献提取特定作物×气候带的实测产量区间（AI 不能凭空编造）。
- **专家标注**：需农艺专家（E1 签署）对关键案例给出独立判断。
- **机理模型**：需独立运行 WOFOST/PCSE 或引入其官方校准参数（当前项目为轻量内核，非 WOFOST 本体）。

这三类数据**都不是 AI 自主可产生的**——需外部资源（文献检索/专家/独立模型运行）。

## 用例格式约定（未来填充时）

每个 L1 用例应带：
```json
{
  "id": "l1_<crop>_<zone>",
  "axis": "target_prediction",
  "evidence_layer": "L1_agronomic_reference",
  "truth_source": "peer_reviewed_paper | expert_annotation | woFost",
  "truth_reference": "<DOI 或专家 ID 或 WOFOST 配置指纹>",
  "expected": {"target_prediction": {"yield_estimate_g": {"value": <独立真值>, "tol_frac": 0.15}}}
}
```

## 诚实边界

- 在获得第一个 L1 用例前，**不得**声称"项目有农艺准确率"。
- 当前所有 89 用例均为 L0（见 `../engineering_regression/README.md`）。

## 前置条件（G1 后）

L1 填充属 P1 工作包，按 CORE_OBJECTIVE §八 判据 **G1 前不开工**。本目录仅预置语义与格式。
