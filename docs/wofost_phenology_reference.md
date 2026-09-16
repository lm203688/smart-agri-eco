# WOFOST 物候参考 · 移植与应用（B1 · growth_agent 微观推演）

> 状态：v1.0.0 · 2026-09-07
> 配套：`data/wofost_phenology_reference.json`（移植参数表）、`agent/phenology.py`（零依赖推演器）
> 来源：借鉴研发清单 `docs/opensource_scan_complementary.md` 的 B1 项（PCSE/WOFOST 作物模拟 → growth_agent）

---

## 1. 为什么只移植物候子集

PCSE/WOFOST（Wageningen，EUPL 1.2）是过程式作物生长模拟引擎，参数 100+ 项/作物且依赖 SQLAlchemy/pandas/numpy —— 与本项目零依赖哲学冲突，故**不直接依赖引擎**。但其**物候温度总和模型**（积温→发育期）是通用农艺知识，可零依赖移植为参考表，给 `growth_agent` 增加「积温→物候期天数」的微观推演，弥补当前 `growth_plan` 只给计划、不给发育期推演的缺口。

## 2. 移植内容（已核实的真实值，非编造）

从 `ajwdewit/WOFOST_crop_parameters` 的 `wofost81` 分支逐项抓取 7 种与本项目 recipes 重叠的作物，提取品种级物候参数：

| 作物 | 代表品种 | TSUMEM | TSUM1 | TSUM2 | TBASE(℃) | 光合 | 春化 |
|---|---|---|---|---|---|---|---|
| 马铃薯 | Potato_701 | 170 | 150 | 1550 | 2.0 | C3 | 有 |
| 小麦 | Winter_wheat_101 | 120 | 543 | 1194 | 0.0 | C3 | **需(IDSL=1)** |
| 大豆 | Soybean_901 | 70 | 350 | 850 | 7.0 | C3 | 有 |
| 向日葵 | Sunflower_1101 | 130 | 1050 | 1000 | 3.0 | C3 | 有 |
| 水稻 | Rice_501 | 100 | 875 | 625 | 10.0 | C3 | 有 |
| 红薯 | Sweetpotato_VH_1988 | 200 | 416 | 1436 | 10.0 | C3 | 有 |
| 绿豆 | Mungbean_VH_1988 | 60 | 640 | 753 | 10.0 | C3 | 有 |

完整字段与品种范围见 `data/wofost_phenology_reference.json`。

## 3. 推演器用法

```python
from agent import phenology as ph

ph.estimate_stage_days("马铃薯", 18.0)
# {'available': True, 'emergence_days': 10.6, 'anthesis_days_from_sow': 20.0,
#  'maturity_days_from_sow': 116.9, 'requires_vernalization': False, ...}

ph.estimate_stage_days("番茄", 20.0)   # {'available': False, 'covered_crops': [...]}
```

模型：`阶段天数 ≈ TSUM / max(0, 日均温 − TBASE)`。日均温 ≤ TBASE 时发育停滞，天数置 `None` 并说明。自测：`python agent/phenology.py`（零依赖）。

## 4. 与 growth_agent 的集成建议

- **非侵入**：`phenology.py` 独立可用，不改动现有 `growth_agent.py`。`generate_growth_plan` 可在返回中追加可选 `phenology_estimate`（调用 `ph.estimate_stage_days`），仅对覆盖作物生效，未覆盖作物静默跳过。
- **闭环校准**：推演结果可写入 Env Recipe 的 `outcome`/实际发育期，反向校正 TSUM（数据 A 闭环的微观层）。
- **许可**：WOFOST 参数 EUPL 1.2，引用需署名 Wageningen WOFOST crop parameters；本项目配方 CC-BY-4.0，二者兼容。

## 5. 后续扩展

1. 增补更多重叠作物（barley/rapeseed/groundnut/chickpea/cowpea/cassava 等 wofost81 已有品种）。
2. 番茄/生菜等城市高频作物 WOFOST 未覆盖 —— 用公开文献积温值手工补表（标注来源，非 WOFOST）。
3. 春化依赖作物（小麦）的简化模型未含春化期，后续可在 `vernalization.idls=1` 时叠加春化需求天数估算。
