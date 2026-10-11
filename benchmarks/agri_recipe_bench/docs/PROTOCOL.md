# AgriRecipeBench · 评测协议 v0.1

> **定位**：面向「Env Recipe 环境配方」的**可复现评测基准**。
> **挂靠**：借鉴中国农业大学神农·农业世界模型 SNWM 1.0（2026-07）的四轴评价协议，
> 裁剪到本项目当前能力可覆盖的子集。
> **零依赖**：标准库 only，与项目主仓保持同一技术底线。

---

## 1. 与 SNWM 四轴的对应关系

| SNWM 轴 | 本基准对应 | 当前状态 | 备注 |
|---|---|---|---|
| 目标预测 | **M1 · target_prediction** | ✅ 已实现 | 给定 Env Recipe + 气候 → 预测采收期与产量，与真值比 |
| 状态滚动 | **M2 · state_rolling** | ✅ 已实现 | 从第 1 天推到第 N 天，检查累积量单调/边界正确 |
| 反事实响应 | M3 · counterfactual | ⏸ 待实现 | 需要 outcome 回流后才能验证"动作→后果" |
| 跨情境泛化 | M4 · cross_scenario | ⏸ 待实现 | 需要 ≥2 个真实场景的 outcome 数据 |

**为什么先做 M1/M2**：这两轴**不需要外部回流**就能定义真值——M1 用公开农艺基准 + 手工标注真值，M2 用数学性质（单调、边界、单位守恒）作真值。M3/M4 依赖真实 outcome，本项目 G1 未达成前没有真实数据可用（详见 `docs/CORE_OBJECTIVE.md` §七 G2 门槛）。

---

## 2. 评测用例 schema

每个用例是一个 JSON 文件，放在 `benchmarks/agri_recipe_bench/cases/` 下：

```json
{
  "id": "case_luobo_beijing_spring",
  "axis": "target_prediction",
  "description": "北京春季胡萝卜 Env Recipe → 预测采收期与单株产量",
  "input": {
    "crop": "胡萝卜",
    "zone_id": "temperate_subhumid",
    "start_date": "2026-03-15",
    "env_recipe": { ... }        // 完整 Env Recipe 内容
  },
  "expected": {
    "target_prediction": {
      "yield_g_per_plant": {"value": 250, "tolerance_abs": 80},
      "adjusted_duration_days": {"value": 90, "tolerance_abs": 20}
    }
  },
  "provenance": {
    "yield_basis": "公开农艺基准（胡萝卜单株产量 200-300g 典型区间）",
    "duration_basis": "胡萝卜生长周期 80-110 天"
  }
}
```

---

## 3. 通过判据

对每个用例：
- **M1 (target_prediction)**：预测值落入 `[value - tolerance, value + tolerance]`
- **M2 (state_rolling)**：
  - 采收日期不早于种植日期
  - 调整生长天数 ≥ 1
  - 产量估计 > 0

用例通过 = 全部指标满足判据。

---

## 4. 报告指标

- **pass_rate**：通过用例数 / 总用例数
- **per_axis_pass_rate**：按 axis 分组
- **per_metric_deviation**：M1 下每个 metric 的 (pred - expected) / expected 绝对值均值

---

## 5. 与外部基准的差别

| 维度 | 传统 crop model benchmark（如 DSSAT 测试集） | AgriRecipeBench |
|---|---|---|
| 输入 | 气象序列 + 品种参数 | **Env Recipe**（一份可执行的环境配置） |
| 真值 | 田间实测 | **公开农艺基准 + 数学性质**（不需要田间实测） |
| 目标 | 机制模型精度 | **可执行配置的合理性**（能否给出合理决策） |
| 外部依赖 | 田间试验网 | **无**（G1 前即可建） |

---

## 6. 版本演进

- **v0.1**（本版）：M1 + M2，5 个种子用例，标准库 runner
- **v0.2**（依赖 G1 达成）：加入 outcome 回流真值 → 覆盖 M3 反事实
- **v1.0**（依赖 G2 达成）：加入 M4 跨情境泛化 → 提交中立组织

---

## 7. 与项目的关系

- **不替代** env_recipes/ 里的 152 份配方
- **不覆盖** `scripts/test_engine_v*.py` 里的功能回归
- **独立于** `harness/`（不写 manifest，只在需要时读观测区做参考）
- **可独立发布**：本目录打包即可分发给外部复现

后续可能：作为公开 benchmark 提交给 AgStack 或类似中立组织（`docs/CORE_OBJECTIVE.md` §六 D-5）。
