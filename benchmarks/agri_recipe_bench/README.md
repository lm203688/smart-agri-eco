# AgriRecipeBench · 农业配方评测基准

> **定位**：面向 Env Recipe 环境配方的**可复现评测基准**
> **挂靠**：借鉴中国农业大学神农 SNWM 1.0（2026-07）四轴评价协议
> **当前规模**：**89 用例 / 四轴齐全 + 20 负例**（target_prediction 25 · state_rolling 21 · counterfactual 17 · generalization 6 · **negative 20**：输入合法性 8 / 诚实降级 6 / 反事实不变式 4 / 血缘与信任断裂 2）
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

## 负例（S1.2 · negative control / abstention）

正向回归只证明「会说好」；负例证明系统**会说不**。用例位于 `cases/neg/`，
骨架由 `scripts/gen_negative_cases.py` 生成，由 `negative_runner.py` 映射到
**真实代码路径**执行（禁止用恒 True 的桩函数通过验收）。

| 类 | 数 | 内容 | 真实校验器 |
|---|---|---|---|
| A 输入合法性拒绝 | 8 | 负天数 / 未知作物 / NaN 温度 / RH=150% / dli<0 / theta=1.5 / Tmin>Tmax / 空作物名 | `core/numeric_domain` 的 8 种契约装饰器（`bounded` / `known_enum` / `finite` / `monotone_constraints` / `not_empty_string` …） |
| B 诚实降级与拒识 | 6 | 完全无观测 → low/rule_based · 气候漂移 3.5σ → out-of-domain · 数据源 4 年 → stale · 双源 Topt 差 15℃ → conflict · 日温<夜温 → 传感器矛盾 · 距校准集 >p99 → uncalibrated | `core/honest_policy.py` 6 个确定性判据函数 |
| C 反事实一致性 | 4 | 零扰动恒等 · ±2℃ 方向反转 · 35℃ 饱和约束 · ΔT+ΔD 复合可加性 | `engine/agriworld_lite.simulate` + `agent.counterfactual_api.counterfactual_trajectory`（真机理仿真） |
| D 血缘与信任断裂 | 2 | 篡改 `environment.temperature.day_c` → 签名失效 · 删除 `sources[0]` → 断链 | `core/recipe_signing`（sha256 规范化签名）+ `core/data_lineage.verify_lineage_intact` |

判据按骨架的 `expect_failure_type` 分派：`InputError` / `DataError`（必须抛指定异常）、
`degrade` / `abstain` / `flag`（verdict 字段必须为 True）、`invariant`（不变式必须成立）、
`raise`（信任断裂必须被检测）。

**待作者确认项（不得由脚本代判）**：C4 复合扰动可加性的容差
`negative_runner.C4_ADDITIVITY_TOLERANCE = 0.20`，实测相对偏差 0.2%；
C 类全部不变式的物理口径（最适温锚点、产量上限、扰动幅度）需论文作者定稿后固化。
`negative_runner.USER_TOLERANCE_CASES` 会把这些用例在 CI 输出中标注出来。

## 复现

```bash
git clone <repo>
cd 智慧农业生态
python -V  # 3.10 / 3.11 / 3.12 均可
python benchmarks/agri_recipe_bench/run_bench.py
```

预期输出：`89/89 通过 (pass_rate=1.0)`。

常用参数：

```bash
python benchmarks/agri_recipe_bench/run_bench.py --summary     # 聚合摘要（含 negative: 20/20 passed）
python benchmarks/agri_recipe_bench/run_bench.py --axis negative --strict   # 仅负例，CI 门禁 #40 用
python -m benchmarks.agri_recipe_bench.negative_runner          # 负例自检（逐例明细）
```

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
