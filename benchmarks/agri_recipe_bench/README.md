# AgriRecipeBench · 农业配方评测基准

> **定位**：面向 Env Recipe 环境配方的**可复现评测基准**
> **挂靠**：借鉴中国农业大学神农 SNWM 1.0（2026-07）四轴评价协议
> **当前规模**：**69 用例 / 四轴齐全**（target_prediction 25 · state_rolling 21 · counterfactual 17 · generalization 6）
> **零依赖**：仅标准库

## 快速开始

```bash
# 运行完整基准（本地可跑）
python benchmarks/agri_recipe_bench/run_bench.py

# 通过 CI 脚本跑
python scripts/test_agri_recipe_bench.py

# 查看结果 JSON
ls outputs/bench_*.json
```

## 四轴协议

| 轴 | 用例数 | 含义 |
|---|---|---|
| target_prediction | 25 | 给定配方+气候 → 预测采收期与产量，与真值比对（含 p10/p50/p90 区间） |
| state_rolling | 21 | 从第 1 天推到第 N 天，检查累积量单调/边界正确 |
| counterfactual | 17 | 改变一个动作（温度+5°C、日照-3h），预测变化方向正确 |
| generalization | 6 | 跨分区/作物泛化能力（未直接测过的组合） |

## 复现

```bash
git clone <repo>
cd 智慧农业生态
python -V  # 3.10 / 3.11 / 3.12 均可
python benchmarks/agri_recipe_bench/run_bench.py
```

预期输出：`69/69 通过 (pass_rate=1.0)`。

## 结果归档

每次运行输出 JSON 到 `outputs/bench_<timestamp>.json`，字段包含：
- 每用例的期望/实测/偏差百分比
- 每轴通过数与通过率
- 总 pass_rate

## Leaderboard

见 [`docs/LEADERBOARD.md`](docs/LEADERBOARD.md) — 分数随时间演进的可复现曲线，含被棘轮拒绝的退步记录。

## 与 SNWM 对齐声明

本基准协议设计参考 SNWM 四轴评价框架，用例真值来源标注为 `methodology_sourced_from`，不复制 SNWM 数据资产，仅对齐方法论与协议结构。

## 评测先行门禁

任何科学内核模块进主干前必须先在 benchmarks/agri_recipe_bench/cases/ 提交用例并跑通（详见 `docs/CORE_OBJECTIVE.md`）。
