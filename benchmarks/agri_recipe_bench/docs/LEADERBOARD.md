# AgriRecipeBench Leaderboard

> 公开成绩曲线 —— 分数随时间演进，含被棘轮拒绝的退步记录。
> **主张**：本基准不接受「分数上升即视为进步」的口号，只信 CI 门禁实测。

## 当前状态

- **最新运行**：2026-10-14 · 69/69 · pass_rate=1.0
- **四轴分布**：target_prediction 25 · state_rolling 21 · counterfactual 17 · generalization 6
- **对比起点**：2026-10-13 上午 11/11（四轴齐全但规模小）

## 演进历史

| 日期 | 版本 | 用例数 | 通过数 | 通过率 | 变更说明 |
|---|---|---|---|---|---|
| 2026-10-13 | v0.1 | 11 | 11 | 1.0 | 首次四轴齐全（tp 3 + sr 2 + cf 4 + gen 2） |
| 2026-10-14 | v1.0 | 69 | 69 | 1.0 | 主线一扩展：每轴补齐覆盖 8 分区 × 主要作物（M15-B1） |

## 被棘轮拒绝的退步记录

> 「不允许退步」是本项目自进化引擎的核心纪律。任何导致 pass_rate 下降的 PR 都会被 CI 拒绝。
> 目前暂无被拒绝记录（工程门禁生效早期）。

| 日期 | PR | 变更 | 原 pass_rate | 新 pass_rate | 判定 |
|---|---|---|---|---|---|
| （暂无） | — | — | — | — | — |

## 保形覆盖率指标（M5-F1 联动）

split conformal 区间覆盖率作为新指标加入，与 pass_rate 并列。数据待 G1 达成后激活（需外部实测样本 ≥30）。

## 复现

```bash
python benchmarks/agri_recipe_bench/run_bench.py
```

结果 JSON 落 `outputs/bench_<ts>.json`。
