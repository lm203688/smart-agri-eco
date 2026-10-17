# W2 Eval-First Gate Template

> 目的：新增科学模块进入主干前，先补 AgriRecipeBench 用例，再谈合并。
>
> 这不是装饰文档，是给“新模块准入”用的最小模板。它只描述用例骨架，不落进 `cases/`，所以不会被 runner 当成真实用例执行。

## 1. 适用对象

- 新增科学模块：气候引擎、作物模型、无土基质模型、营养/病虫害/物候相关新内核
- 规则：先提交 M1-M4 四轴用例，跑通后再合并代码

## 2. 用例目录

所有新增用例必须放在：

- `benchmarks/agri_recipe_bench/cases/*.json`

模板文件本身放在：

- `benchmarks/agri_recipe_bench/templates/`

## 3. 用例字段约定

每个新增用例至少包含：

```json
{
  "id": "case_<module>_<axis>_<short_name>",
  "axis": "target_prediction | state_rolling | counterfactual | generalization",
  "description": "说明这条用例在验证什么",
  "input": {
    "crop": "作物名",
    "zone_id": "分区 id",
    "start_date": "YYYY-MM-DD",
    "adapt_score": 0.85,
    "growth_plan": {},
    "env_recipe": {},
    "env_recipe_path": "data/env_recipes/xxx.json"
  },
  "perturbation": {
    "字段名": {
      "after": "扰动后的值"
    }
  },
  "expected": {
    "target_prediction": {},
    "state_rolling": {},
    "counterfactual": {},
    "generalization": {}
  },
  "provenance": {
    "note": "为什么需要这条用例"
  }
}
```

### 字段说明

- `id`：唯一，最好带模块名和轴名
- `axis`：只能选四轴之一
- `input`：给 runner 的基准输入
- `perturbation`：只在 `counterfactual` 轴使用
- `expected`：按轴填写对应判据
- `provenance`：写清这条用例的判定动机，避免“拍脑袋”用例

## 4. 四轴模板

### target_prediction

验证预测值是否落在容差范围内。

- 适用：产量、采收日、关键指标估算
- 关键判据：
  - `yield_estimate_g`
  - `adjusted_duration_days`
  - `harvest_date`
  - 其他模块自定义预测指标

### state_rolling

验证状态推进的数学性质。

- 适用：滚动累计、单调性、边界合法性
- 关键判据：
  - `adjusted_duration_days >= 1`
  - `harvest_date >= start_date`
  - `yield_estimate_g > 0`

### counterfactual

验证扰动后的变化方向。

- 适用：温度、湿度、日照、EC、基质、养分变化
- 关键判据：
  - `direction`: `increase` / `decrease` / `change`
  - `min_delta_pct`

### generalization

验证跨分区、跨情境的泛化能力。

- 适用：同一作物跨多个气候区
- 关键判据：
  - `all_zones_legal`
  - `yields_distinct`
  - `metric_bounds`

## 5. 提交流程

1. 复制最接近的用例到 `benchmarks/agri_recipe_bench/cases/`
2. 按目标轴改写 `id` / `axis` / `input` / `expected`
3. 运行 `python scripts/check_bench_coverage.py`
4. 运行 `python benchmarks/agri_recipe_bench/run_bench.py`
5. 运行完整门禁后再提交代码

## 6. 最低准入门槛

新增科学模块必须至少满足：

- 至少 1 条 `target_prediction` 用例
- 至少 1 条 `state_rolling` 用例
- 至少 1 条 `counterfactual` 用例
- 至少 1 条 `generalization` 用例
- 四条用例都能被现有 runner 直接消费
- `scripts/check_bench_coverage.py` 通过

## 7. 备注

- 不要把模板文件命名为 `case_*.json`，否则会被 runner 当成真实用例扫描
- 不要在这个目录下放可执行 JSON 用例；真实用例只进 `cases/`
- 如果新模块改变了 agent 输出字段，先补 runner，再补用例
