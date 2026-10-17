# 反事实轨迹（Counterfactual Trajectory）

> 六大支柱之一 · Phase N+1 #6 · MCP 工具 `agri_counterfactual_trajectory`

## 1. 什么是反事实轨迹

**"如果当时温度高 2°C，产量会怎样？"** —— 反事实轨迹就是回答这种"假如"的问题。

- **事实轨迹**（`agri_growth_plan` 产出）：给定基线环境（温度/水分/光照/养分），机理内核模拟出日度生物量/产量/采收期轨迹。
- **反事实轨迹**（`agri_counterfactual_trajectory` 产出）：在基线上做**受控扰动**（如温度 +2°C / 灌溉 -30% / 光照 -25%），模拟"另一个世界"的轨迹，并给出与事实轨迹的对比。

两者的关系：

|  | 事实轨迹 | 反事实轨迹 |
|---|---|---|
| 用途 | 计划 / 预期产出 | 敏感性分析 / 决策支持 |
| 输入 | 基线动作序列 | 基线 + 扰动参数 |
| 输出 | 单条轨迹 | 基线 vs 反事实双轨迹 + 差值 |
| 底层内核 | AgriWorld-Lite | 同（AgriWorld-Lite） |

## 2. 输入参数

```json
{
  "recipe_ref": "arid__番茄",              // 已发布的 Env Recipe 引用
  "perturbation": {
    "type": "temperature_offset_c",       // 扰动类型
    "value": 2.0,                         // 扰动幅度（可负）
    "duration_days": 30                    // 持续天数（0 = 全程）
  },
  "steps": 90,                            // 模拟天数
  "confidence": "p90"                     // 置信区间档位：p50 / p80 / p90
}
```

### 2.1 支持的扰动类型

| type | 含义 | 单位 |
|---|---|---|
| `temperature_offset_c` | 温度偏移 | ℃ |
| `water_factor` | 灌溉倍率 | 0-2（1=基线） |
| `light_factor` | 光照倍率 | 0-2 |
| `co2_offset_ppm` | CO₂ 偏移 | ppm |
| `ph_offset` | pH 偏移 | -2 到 +2 |
| `ec_factor` | EC 倍率 | 0-2 |
| `disease_incident` | 病虫害事件 | 布尔（true=触发） |

### 2.2 多扰动组合

`perturbation` 支持数组形式，模拟"温度 +2°C 且灌溉 -20%"这种复合扰动：

```json
{
  "perturbation": [
    {"type": "temperature_offset_c", "value": 2.0},
    {"type": "water_factor", "value": 0.8, "duration_days": 15}
  ]
}
```

## 3. 输出格式

```json
{
  "baseline": {
    "trajectory": [{"day": 1, "biomass_g_m2": 12.3, "yield_g_m2": 0}, ...],
    "final_yield_g_m2": 4850.2,
    "harvest_day": 82
  },
  "counterfactual": {
    "trajectory": [{"day": 1, "biomass_g_m2": 11.8, ...}, ...],
    "final_yield_g_m2": 4210.5,
    "harvest_day": 85
  },
  "delta": {
    "yield_change_g_m2": -639.7,
    "yield_change_pct": -13.2,
    "harvest_delay_days": 3
  },
  "confidence_interval": {
    "p90_low": -18.5,
    "p90_high": -8.1
  },
  "trust_mark": {"cert_id": "...", "signature": "sha256:..."},
  "model": "agriworld-lite/v0",
  "limitations": [
    "机理模型基于公开文献参数，非本项目实测校准",
    "反事实仅在扰动幅度 ≤±30% 时有物理意义，超出范围视为极端假设"
  ]
}
```

## 4. 与 `agri_growth_plan` 的分工

- `agri_growth_plan`：**回答"应该怎么做"** —— 输出种植计划（阶段/周期/环境参数）。
- `agri_counterfactual_trajectory`：**回答"如果做别的会怎样"** —— 敏感性分析、决策支持。

典型组合用法：

```
Agent: 用 agri_growth_plan 得到基线计划（120 天，4850 g/m²）
Agent: 用 agri_counterfactual_trajectory 探测三种扰动：
       - 温度 +2°C → 产量 -13%
       - 灌溉 -30% → 产量 -22%
       - CO₂ +200ppm → 产量 +18%
Agent: 综合判断：CO₂ 富集是本情境下最高 ROI 的干预。
```

## 5. 底层机理内核

- 引擎：`engine/agriworld_lite.py`（AgriWorld-Lite v0）
- 主要过程：Beer-Lambert 光截获 · Farquhar 光合 · Penman-Monteith 蒸腾 · 水量平衡 · 养分质量流 · 器官分流 · Q10 呼吸
- 边界校验：`core/numeric_domain.py`（`@bounded` / `@non_negative` / `@positive`）+ `core/exceptions.py`（`InputError`）
- 测试：`scripts/probe_mechanism_garbage_in.py`（34 探针，验证 GIGO 防御）
- 可信标记：`_trust_mark.{cert_id, signature, verification_cmd}`，外部可独立复算

## 6. 使用示例

```python
from mcp.server import handle_call

result = handle_call("tools/call", {
    "name": "agri_counterfactual_trajectory",
    "arguments": {
        "recipe_ref": "arid__番茄",
        "perturbation": {"type": "temperature_offset_c", "value": 2.0},
        "steps": 90,
        "confidence": "p90"
    }
})
print(result["delta"])  # {'yield_change_g_m2': -639.7, ...}
```

## 7. 与 AgriTrust 的关联

反事实输出必须带 `_trust_mark`。外部消费者可用：

```bash
python -m core.trust_layer --check <output.json>
```

独立复算 signature，验证反事实模拟未被篡改。

---

*本文档由 GAP_AUDIT §D3 触发补齐（原 0 文档）。*
