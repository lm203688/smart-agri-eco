# TOOLS REFERENCE · 30 个 MCP 工具契约手册

> **目标读者**：外部 Agent 开发者，需要在自己的系统里调用 `agri-eco` 的 MCP 工具。
> **权威源**：`mcp/server.py` 中的 `TOOLS` 注册表（本文件是文档视图，**禁止手改**——工具增删后请 rerun `scripts/gen_tool_table.py`；本文件仅补充 LLM 选工具时所需的人类语义上下文）。
> **结构**：每个工具三段式——「**何时用** / **输入** / **返回示例**」。
> **总工具数**：30 · **总分类数**：15
>
> **⚠️ 返回示例诚实边界**：下方各工具的「返回示例」为**结构示意**（说明返回了什么类别的信息），**字段名与真实调用可能不完全一致**。真实字段名以 `_tool_*` 函数实际返回为准——最快的验证方式是跑 `examples/*.py`（5 个可运行示例）或 `python scripts/test_mcp_server.py`。字段名可能随版本演进；本文件仅承诺「返回结构类别稳定」。

---

## 目录（按调用频率排序）

| # | 工具 | 分类 | 常见场景 |
|---|---|---|---|
| 1 | `agri_match_zone` | climate | 给定坐标，先判断气候分区 |
| 2 | `agri_recommend_crops` | crop | 阳台 / 温室 / 大田选什么种 |
| 3 | `agri_resolve_recipe` | recipe | 城市名 → 该城市可种的配方清单 |
| 4 | `agri_env_recipe` | recipe | 直接要一份可执行配方 JSON |
| 5 | `agri_recipe_profile` | recipe | 浏览 / 检索 / diff / 导出 152 份配方 |
| 6 | `agri_growth_plan` | phenology | 什么时候播、什么时候收 |
| 7 | `agri_diagnose_pest` | pest | 叶子发黄 / 长虫了怎么办 |
| 8 | `agri_nutrition_plan` | nutrition | 不同阶段施多少肥 |
| 9 | `agri_season_advisory` | meta | 12 月均温 → 无霜期 & 播期窗口 |
| 10 | `agri_soil_profile` | soil | 这块地土壤适合种啥 |
| 11 | `agri_reconcile_climate` | climate | 多源调和验证气候基线 |
| 12 | `agri_forecast` | forecast | 产量 / 采收期预测（含 P10/P50/P90） |
| 13 | `agri_counterfactual_trajectory` | counterfactual | "如果我改 5℃ 会怎样" |
| 14 | `agri_verify_recommendation` | verify | 别人给的产量建议可信吗 |
| 15 | `agri_verify_trust` | meta | 独立复算 AgriTrust 指纹 |
| 16 | `agri_search` | knowledge | 混合检索（关键词+向量） |
| 17 | `agri_knowledge_query` | knowledge | 图谱关系（分区→作物、风险→作物） |
| 18 | `agri_query_lineage` | meta | 这份配方的数据来源可追溯吗 |
| 19 | `agri_list_cities` | climate | 预设城市列表 |
| 20 | `agri_list_ecosystem` | meta | 我们对接了哪些外部生态 |
| 21 | `agri_server_card` | meta | 服务元数据 + ETag 缓存 |
| 22 | `agri_bp_screen` | business | 农业项目投资初筛（六分类+五闸+一票否决） |
| 23 | `agri_decision_path_report` | bp_screen | 批量导出决策路径归因 |
| 24 | `agri_economics` | business | 单位经济模型 / 成本收益测算 |
| 25 | `agri_postharvest` | nutrition | 采后阶段（fresh/storage/transport）管理建议 |
| 26 | `agri_grow_batch_create` | batch | 建立 Plot + GrowBatch 批次对象 |
| 27 | `agri_grow_batch_observe` | batch | 批次生命周期内追加观察记录 |
| 28 | `agri_grow_batch_action` | batch | 记录动作（默认 shadow/dry_run，不真实执行） |
| 29 | `agri_grow_batch_status` | batch | 查询批次状态 + 关联对象（可选含事件日志） |
| 30 | `agri_grow_batch_replay` | batch | 按时间线回放批次事件（无副作用） |

---

## 分类图（15 类）

```
climate        3   agri_list_cities / agri_match_zone / agri_reconcile_climate
crop           1   agri_recommend_crops
phenology      1   agri_growth_plan
pest           1   agri_diagnose_pest
nutrition      2   agri_nutrition_plan / agri_postharvest
recipe         3   agri_env_recipe / agri_resolve_recipe / agri_recipe_profile
meta           5   agri_season_advisory / agri_query_lineage / agri_list_ecosystem
                                       / agri_verify_trust / agri_server_card
soil           1   agri_soil_profile
business       2   agri_bp_screen / agri_economics
knowledge      2   agri_search / agri_knowledge_query
forecast       1   agri_forecast
bp_screen      1   agri_decision_path_report
counterfactual 1   agri_counterfactual_trajectory
verify         1   agri_verify_recommendation
batch          5   agri_grow_batch_create / agri_grow_batch_observe / agri_grow_batch_action
                                       / agri_grow_batch_status / agri_grow_batch_replay
```

---

# 详细契约（30 段）

## 1. `agri_match_zone` — 经纬度 → 气候分区

**何时用**
- 拿到用户的 GPS / 城市坐标，需要判断「这里属于哪个气候带」
- 后续要调 `agri_recommend_crops` / `agri_resolve_recipe` / `agri_forecast` 之前的**必要前置**
- 输入：`lat: number`（必填）、`lon: number`（必填）

**返回示例**
```json
{
  "zone_id": "subtropical_wet",
  "zone_name": "亚热带湿润",
  "coppen_class": "Cfa",
  "adapt_score": 0.72,
  "frost_free_days": 245,
  "gdd_annual_c": 4200,
  "limiting_factors": ["高温期降水过多", "梅雨季长"],
  "_trust_mark": {"signature": "sha256:...", "verification_cmd": "..."}
}
```

---

## 2. `agri_recommend_crops` — 分区 + 偏好 → 作物推荐

**何时用**
- 用户说「我在家 / 在 XX 城市，能种什么？」
- 已确定坐标，需要具体作物清单 + 评分
- 输入：`lat/lon` 或 `city` 二选一；`purpose`（食用/观赏/药用）、`space_sqm`、`difficulty`、`scene`（balcony/greenhouse/field 等）

**返回示例**
```json
{
  "city": "杭州",
  "zone_id": "subtropical_wet",
  "recommendations": [
    {"crop": "番茄", "score": 0.87, "reason": "亚热带湿润区主粮蔬菜，光热充足"},
    {"crop": "生菜", "score": 0.82, "reason": "短周期，阳台适配"}
  ]
}
```

---

## 3. `agri_resolve_recipe` — 城市/坐标 → 可种配方清单

**何时用**
- 用户给了城市名（如「成都」），要一份「这里到底能种啥、每份配方在哪」
- 完全离线，2 秒内返回；适合首页展示
- 输入：`query`（城市名或 "lat,lon"）或 `lat/lon` 二选一

**返回示例**
```json
{
  "zone_id": "subtropical_wet",
  "zone_name": "亚热带湿润",
  "matched_recipes": [
    {"crop": "番茄", "stage": "fruiting", "device_class": "greenhouse",
     "filename": "tomato_fruiting_greenhouse.json", "path": "data/env_recipes/..."}
  ]
}
```

---

## 4. `agri_env_recipe` — 直接取一份 Env Recipe v1

**何时用**
- 已知 crop + stage + device_class，需要可直接执行的温湿度 / 水 / 光 / 营养液 JSON
- 输出符合 `schemas/env_recipe.schema.json` v1.2.0
- 输入：`crop` 必填；`stage`（seed/seedling/vegetative/flowering/fruiting/harvest/full_cycle）；`device_class`

**返回示例**
```json
{
  "crop": "番茄",
  "stage": "fruiting",
  "device_class": "greenhouse",
  "temperature": {"day_c": 24, "night_c": 18, "envelope": [15, 32]},
  "humidity_pct": {"nominal": 65, "range": [55, 80]},
  "vpd_kpa": {"nominal": 0.95, "envelope": [0.4, 1.6]},
  "light": {"dli_mj_m2_d": 14, "photoperiod_h": 14},
  "water_ml_day": 500,
  "pH": 6.2,
  "sources": [{"url": "https://...", "license": "CC BY 4.0"}],
  "data_quality": "modeled",
  "_trust_mark": {"signature": "sha256:..."}
}
```

---

## 5. `agri_recipe_profile` — 152 份配方的浏览器 / 检索器

**何时用**
- 想看「我们有多少配方、按分区/作物分布如何」→ `kind=list` 或 `stats`
- 想找「某作物所有阶段的配方」→ `kind=search, crop=...`
- 想加载某份完整 JSON → `kind=lookup, filename=...`
- 想对比两份 → `kind=diff, a=..., b=...`
- 想批量导出（可选剥离隐私字段）→ `kind=export`
- 模式：`mode=brief`（默认，节省 context）或 `full`（完整 JSON）

**返回示例（`kind=stats`）**
```json
{
  "kind": "stats",
  "total": 152,
  "by_zone": {"subtropical_wet": 42, "temperate_continental": 31, ...},
  "by_device_class": {"greenhouse": 68, "open_field": 51, "vertical": 22, ...},
  "data_quality_distribution": {"modeled": 137, "field_trial": 15}
}
```

---

## 6. `agri_growth_plan` — 作物 + 场景 + 分区 → 种植计划

**何时用**
- 用户说「我打算 X 月种番茄，什么时候收、中间要注意啥」
- 输入：`crop`（必填）、`lat/lon` 或 `city`；`scene`；`start_date`（可选）；`floor` / `orientation`（阳台场景）

**返回示例**
```json
{
  "crop": "番茄",
  "sow_date": "2026-03-15",
  "transplant_date": "2026-04-05",
  "harvest_start": "2026-06-20",
  "growth_cycle_days": 96,
  "phases": [
    {"name": "seedling", "start": "2026-03-15", "end": "2026-04-05", "gdd": 220}
  ],
  "recommendation": {
    "prediction_interval": {"p10": 82, "p50": 96, "p90": 112},
    "confidence": {"uncertainty": 0.15}
  }
}
```

---

## 7. `agri_diagnose_pest` — 症状 / 图像 → 诊断

**何时用**
- 用户描述症状（「叶子边缘发黄」）或引用图像 ID
- 输入：`crop`（必填）、`symptom_description`、`image_reference`、`growth_stage`、`environment`（对象）

**返回示例**
```json
{
  "crop": "番茄",
  "suspected_issues": [
    {"cause": "缺钾", "confidence": 0.71, "action": "补 K2SO4 200ppm"},
    {"cause": "晚疫病", "confidence": 0.45, "action": "减湿 + 铜制剂"}
  ],
  "next_steps": ["降低湿度至 60% 以下", "检查土壤 pH"]
}
```

---

## 8. `agri_nutrition_plan` — 阶段化施肥

**何时用**
- 用户要「现在这个阶段该怎么施肥」
- 输入：`crop`（必填）、`growth_stage`、`growth_days`、`container_volume_l`（水培时必填）

**返回示例**
```json
{
  "crop": "生菜",
  "stage": "vegetative",
  "days_into_stage": 12,
  "ec_mscm": {"range": [1.2, 1.8]},
  "pH": {"range": [5.8, 6.2]},
  "nppm": 150,
  "weekly_schedule": [{"day": 1, "dose_g_l": 0.3}, ...]
}
```

---

## 9. `agri_season_advisory` — 播期 / 积温 / 日历

**何时用**
- 3 种 mode：
  - `planting_window`：给定 12 月均温，算无霜期 + 各作物最早/最晚安全播种日
  - `stage_days`：给定 crop + 日均温，算出苗 / 开花 / 成熟天数
  - `calendar`：给定 USDA 区 + 日期，查外部日历事件（需外部数据到位）

**输入示例（`planting_window`）**
```json
{
  "mode": "planting_window",
  "monthly_mean_c": [5, 6, 10, 15, 20, 24, 28, 27, 23, 18, 12, 7]
}
```

**返回示例**
```json
{
  "mode": "planting_window",
  "frost_free_days": 205,
  "first_frost_safe": "04-05",
  "last_frost_safe": "10-30",
  "crop_windows": [
    {"crop": "番茄", "earliest": "2026-04-10", "latest": "2026-06-15"}
  ]
}
```

---

## 10. `agri_soil_profile` — 土壤剖面

**何时用**
- 用户给坐标，问「这块地的土壤适合种啥」
- 在线优先查 ISRIC SoilGrids v2.0；失败降级为分区均值（明确标注 `resolution=zone`、`confidence=low`）
- 输入：`lat/lon` 或 `zone_id`；`crop`（可选，用于 pH 适宜性拟合）；`online=true|false`；`timeout_s`

**返回示例**
```json
{
  "resolution": "point",
  "confidence": "high",
  "z_horizon": {"depth_cm": [0, 20, 60], "pH": [6.8, 6.5, 6.3]},
  "organic_carbon_g_kg": 18.5,
  "clay_pct": 32,
  "crop_fit": {"tomato": "good (pH 适宜)"}
}
```

---

## 11. `agri_reconcile_climate` — 多源气候调和

**何时用**
- 想验证「这个坐标的月均温基线是否可信」
- 并行拉 NASA POWER + Open-Meteo，逐月一致度（标准差），分歧月份告警（>3℃）
- 无网络时**优雅降级**：`reconciled=null, provenance_complete=false`，绝不返回编造值
- 输入：`lat/lon`（必填）、`years`（默认 5）、`sources`（默认 `[power, open_meteo]`）

**返回示例**
```json
{
  "lat": 30.27,
  "lon": 120.15,
  "monthly_mean_c": [6.2, 7.1, 11.0, 16.5, 21.4, 25.2, 29.1, 28.7, 23.5, 18.3, 12.8, 7.5],
  "monthly_consistency": [0.3, 0.4, 0.5, 0.7, 0.6, 0.9, 1.2, 1.1, 0.8, 0.7, 0.6, 0.4],
  "divergence_alerts": [],
  "provenance_complete": true
}
```

---

## 12. `agri_forecast` — 产量 / 采收期预测

**何时用**
- 想给一个「预测区间」而不是单点
- 输出含 T-3 置信区间 `p10 / p50 / p90`，并诚实标注 `model=heuristic`
- 输入：`crop`（必填）、`zone_id`、`start_date`、`adapt_score`（0-1）、`env_recipe`、`growth_plan`、`zone_climate`

**返回示例**
```json
{
  "crop": "番茄",
  "yield_g_m2": {
    "p50": 4800,
    "interval": {"p10": 3600, "p90": 6200}
  },
  "harvest_window": {"start": "2026-06-20", "end": "2026-08-15"},
  "model": "heuristic",
  "confidence": {"uncertainty": 0.18, "spread_reason": "adapt_score=0.72 中等"}
}
```

---

## 13. `agri_counterfactual_trajectory` — 机理内核反事实仿真

**何时用**
- 「如果我把日均温降 5℃，产量会怎么变？」
- 底层用 AgriWorld-Lite：光截获 Beer-Lambert + CO2 同化 + Q10 呼吸 + Penman-Monteith 蒸腾
- 6 种 `quick_scenario`：`light_12_to_16h` / `cool_down_5c` / `stop_fertilizer` / `high_humidity` / `double_water` / `baseline`
- 输入：`crop`（必填）、`days`（默认 45）、`quick_scenario`、`baseline_dli_mj`、`baseline_temp_c`、`heuristic_est`（用于双轨分歧告警）

**返回示例**
```json
{
  "crop": "potato",
  "days": 45,
  "baseline": {"final_biomass_g_m2": 1280},
  "scenario": {"name": "cool_down_5c", "final_biomass_g_m2": 950},
  "delta_g_m2": -330,
  "attribution": {"light": -40, "temp": -220, "water": 20, "fert": 0, "dev": -90},
  "dual_track_divergence": {"alert": false, "heuristic_vs_mechanistic_pct": 8.2}
}
```

---

## 14. `agri_verify_recommendation` — Verify-as-a-Service

**何时用**
- 别的 Agent / 大模型 / 农艺师给你「番茄能产 8 kg/m²」——你信不信？
- 三类冲突检测：物理约束 / 物候 / 环境-品种
- 输入：`claim`（含 `crop` 必填 + `yield_g_m2` / `duration_days` 等）、`context`（`dli_mj_m2_d` / `temp_mean_c` / `rh` / `zone` 等）、`heuristic_engine_est`（用于双轨）

**返回示例**
```json
{
  "verdict": "contradicted",
  "verdict_reason": "光能转化效率超出物理上限（claim 8kg/m² vs 光能上限 5.6kg/m²）",
  "checks": [
    {"type": "photochemistry", "status": "fail", "detail": "..."},
    {"type": "phenology", "status": "pass"}
  ],
  "prediction_interval": {"p10": 3200, "p50": 4500, "p90": 5600},
  "_trust_mark": {"signature": "sha256:..."}
}
```

---

## 15. `agri_verify_trust` — 独立复算可信标记

**何时用**
- 外部消费者拿到一份 `_trust_mark.signature`，想独立复算是否一致
- 3 种 mode：
  - `current`：返回当前信任标记（含复算命令）
  - `check_prefix`：检查外部 mark 的内部一致性（signature_prefix 是否为 signature 前 12 字符）
  - `end_to_end`：用 mark.issued_at + 本地数据源严格重现 signature
- 诚实边界：SHA256 是**内容一致性**，非密码学签名（无密钥）——证明数据未被修改，不证明签发者身份

**输入示例**
```json
{"mode": "current"}
```

**返回示例**
```json
{
  "cert_id": "AGRI-2026-10-19-001",
  "signature": "sha256:a1b2c3d4...",
  "signature_prefix": "a1b2c3d4e5f6",
  "verification_cmd": "python -m core.trust_layer verify",
  "coverage": ["env_recipes", "engine_params", "wofost_registry"]
}
```

---

## 16. `agri_search` — 混合知识检索

**何时用**
- 想跨 crops / zones / pests / recipes 四个语料（共 335 条）混合检索
- 底层是 stdlib-only 的 char n-gram + cosine + SQLite FTS5（`engine/local_search.py`，565 行零依赖引擎）
- 4 种 `mode`：`exact` / `keyword` / `vector` / `hybrid`（默认）
- 输入：`query`（必填）、`corpus`（all/crops/zones/pests/recipes）、`k`（默认 10，最大 50）

**返回示例**
```json
{
  "query": "晚疫病",
  "mode": "hybrid",
  "results": [
    {"corpus": "pests", "entity": "late_blight", "score": 0.89,
     "snippet": "晚疫病（Phytophthora infestans）...", "score_breakdown": {"keyword": 0.7, "vector": 0.9}}
  ],
  "index_stats": {"total": 335, "crops": 128, "zones": 12, "pests": 46, "recipes": 152}
}
```

---

## 17. `agri_knowledge_query` — 图谱查询（261 实体 / 446 边）

**何时用**
- 想看「分区 → 该分区适配的作物清单」→ `kind=crops_by_zone`
- 想看「某病虫害 → 影响哪些作物」→ `kind=crops_by_risk`
- 想看某节点邻居 → `kind=neighbors`；BFS 遍历 → `kind=traverse`
- 输入：`kind` + 视 kind 而定的 `zone_id` / `risk` / `node` / `relation` / `depth` / `top_k`

**返回示例（`kind=crops_by_zone`）**
```json
{
  "kind": "crops_by_zone",
  "zone_id": "subtropical_wet",
  "crops": [
    {"crop": "番茄", "score": 0.87, "via": "climate_fit"},
    {"crop": "生菜", "score": 0.82, "via": "climate_fit"}
  ]
}
```

---

## 18. `agri_query_lineage` — 数据血缘

**何时用**
- 想知道「这份配方的数据来源到底是啥、有没有被 AI 改过」
- 组合：`crop` + `zone_id` 单点追踪；仅一个查全局；皆空返回全局摘要
- 输出含外部 API 参与情况 + 本地权威文件 SHA256 指纹 + 校准实证

**返回示例**
```json
{
  "crop": "番茄",
  "zone_id": "subtropical_wet",
  "external_apis": ["NASA POWER", "Open-Meteo"],
  "local_sources": [
    {"path": "data/env_recipes/tomato_fruiting_greenhouse.json", "sha256": "..."}
  ],
  "calibration_evidence": {"r2": 0.87, "sample_size": 12}
}
```

---

## 19. `agri_list_cities` — 预设城市列表

**何时用**
- 用户说「我在这个附近」但没给具体坐标时，先让他从预设城市里挑一个
- 无参数

**返回示例**
```json
{
  "count": 47,
  "cities": [
    {"name": "杭州", "lat": 30.27, "lon": 120.15, "zone": "subtropical_wet"},
    {"name": "北京", "lat": 39.90, "lon": 116.40, "zone": "temperate_continental"}
  ]
}
```

---

## 20. `agri_list_ecosystem` — 外部生态对接清单

**何时用**
- 想知道「agri-eco 与哪些开源 / 商业生态对接了」
- 状态：`integrated` / `partial` / `planned_mapping` / `evaluating` / `competitor_reference` / `not_evaluated`
- 输入：`status`（可选过滤）

**返回示例**
```json
{
  "count": 34,
  "ecosystems": [
    {"name": "Open Food Network", "status": "planned_mapping", "license": "AGPL-3.0",
     "url": "https://thenounproject.com/...", "purpose": "..."}
  ]
}
```

---

## 21. `agri_server_card` — MCP Server Card（含 ETag）

**何时用**
- MCP 客户端在会话开始时先拉一次拿能力清单、缓存
- 返回稳定 ETag（sha256 前 16 hex）；后续请求带 `if_none_match` 命中返回 `not_modified` 短路
- 与 `.well-known/mcp-card.json` 同源；建议 24h TTL
- 输入：`if_none_match`（可选，客户端缓存的 ETag）

**返回示例**
```json
{
  "card": {"name": "agri-eco", "version": "1.1.0", "capabilities": {...}, "tools_count": 23},
  "etag": "a1b2c3d4e5f60718",
  "cache_hint": {"ttl_ms": 86400000, "scope": "public", "algorithm": "sha256"}
}
```

---

## 22. `agri_bp_screen` — 农业项目投资初筛

**何时用**
- 收到一份 BP / 审计报告 / 银行流水 / 证书文本，需要机器初筛
- 六分类（种业/农机/数字农业/生物投入品/供应链/养殖）+ 五闸爆雷 + 六评分卡 + 一票否决 → 三档结论（≥75 通过 / 60-75 深挖 / <60 淘汰）
- 输入：`text` 或 `fields` 二选一；`category` / `company` / `mode` / `filename` 可选
- **诚实边界**：输出为初筛参考，不构成投资决策建议；`local_hit` 仅为本地示例库字符串匹配，不是官方核验

**返回示例**
```json
{
  "category": "digag",
  "verdict": "deep_dive",
  "total_score": 68.5,
  "gates_fired": ["revenue_growth_negative"],
  "vetoes_fired": [],
  "decision_path": [...],
  "counterfactual": {"type": "margin_improvement", "if": "gross_margin → 40%", "then": "score → 78"},
  "data_gaps": [...],
  "license": "internal_only"
}
```

---

## 23. `agri_decision_path_report` — 决策路径批量导出

**何时用**
- 已跑过 `agri_bp_screen`，想把评分引擎的决策路径批量导出为可视化报告
- 读 DB 存量案例（排除 benchmark），按 case_id 或全量
- 输入：`case_ids`（可选）、`format`（json/summary）

**返回示例（`format=summary`）**
```json
{
  "report_type": "decision_path_report",
  "case_count": 7,
  "format": "summary",
  "results": [
    {"case_id": 3, "name": "某农业科技公司", "verdict": "deep_dive", "total_score": 68.5,
     "gates_count": 2, "vetoes_count": 0, "path_item_count": 12}
  ]
}
```

---

## 24. `agri_economics` — 单位经济模型 / 成本收益测算

**何时用**
- 已有作物 + 场景 + 分区，想算亩产成本、收入、毛利率与盈亏平衡点
- 输入：`crop`（必填）+ 可选 `zone_id` / `scenario` / `plot_area_sqm` / `market_price`

**返回示例（结构示意）**
```json
{
  "crop": "番茄",
  "unit_economics": {
    "revenue": {"value": 8.4, "unit": "yuan/sqm"},
    "cost": {"value": 5.2, "unit": "yuan/sqm"},
    "gross_margin": 0.38,
    "breakeven_price": {"value": 3.1, "unit": "yuan/kg"}
  },
  "assumptions": ["本地均价", "种子/肥/水电/人工分摊"]
}
```

---

## 25. `agri_postharvest` — 采后阶段管理建议

**何时用**
- 作物已采收，需要 fresh / storage / transport 阶段的温湿度、预冷、包装建议
- 输入：`crop`（必填）+ 可选 `stage`（fresh/storage/transport，默认 storage）

**返回示例（结构示意）**
```json
{
  "crop": "生菜",
  "stage": "storage",
  "recommendations": [
    {"phase": "storage", "temp_c": {"min": 0, "max": 4}, "rh_pct": 90,
     "advice": "冷链 0-4℃，高湿防萎蔫"}
  ]
}
```

---

## 26. `agri_grow_batch_create` — 建立 Plot + GrowBatch 批次对象

**何时用**
- 把 MCP / UI / 校准 / 审计的局部上下文收束到批次对象链，而非各自维护 crop/zone/recipe
- 输入：`plot`（plot_id/location_type）+ `batch`（batch_id/crop/plot_id/recipe_version/started_at）
- **MVP 诚实边界**：动作默认 shadow/dry_run，不写真实 outcome（P1 才人工确认执行）

**返回示例（结构示意）**
```json
{
  "ok": true, "batch_id": "demo_batch_001", "plot_id": "demo_balcony_a",
  "status": "planned",
  "honest_note": "MVP：模拟批次已建立，动作默认 shadow/dry_run，真实执行需人工确认"
}
```

---

## 27. `agri_grow_batch_observe` — 批次生命周期内追加观察

**何时用**
- 批次已建立，追加一次观察（传感器自动或人工/图像补充）
- 输入：`observation`（observation_id/batch_id/ts/metric/source，value 可选）

**返回示例（结构示意）**
```json
{"ok": true, "observation_id": "obs_001", "count": 1}
```

---

## 28. `agri_grow_batch_action` — 记录动作（默认 shadow/dry_run）

**何时用**
- 记录一次建议→审批→执行→确认的动作链起点
- 输入：`action`（action_id/batch_id/ts/recommendation，parameters/dry_run 可选）
- **契约**：真实执行（executed）禁止 dry_run=True，需人工确认后置 dry_run=False

**返回示例（结构示意）**
```json
{"ok": true, "action_id": "act_001", "status": "shadow", "dry_run": true}
```

---

## 29. `agri_grow_batch_status` — 查询批次状态 + 关联对象

**何时用**
- 想看某批次当前状态、累计观察/动作/结果，或附带 append-only 事件日志
- 输入：`batch_id`（必填）+ 可选 `include_events`（默认 false）

**返回示例（结构示意）**
```json
{
  "ok": true, "batch": {"batch_id": "demo_batch_001", "crop": "生菜", "status": "planned"},
  "plot": {"plot_id": "demo_balcony_a"},
  "n_observations": 1, "n_actions": 1, "n_outcomes": 0,
  "observations": ["…最近 10 条…"], "actions": ["…最近 10 条…"],
  "events": null
}
```

---

## 30. `agri_grow_batch_replay` — 按时间线回放批次事件

**何时用**
- 审计 / 复现一个批次的完整事件序列；只重建事件，不触发任何真实执行
- 输入：`batch_id`（必填）

**返回示例（结构示意）**
```json
{
  "ok": true, "batch_id": "demo_batch_001", "n_events": 5,
  "timeline": [{"seq": 1, "event_type": "batch_created", "ts": "…"}, "…"],
  "honest_note": "回放仅重建事件序列，不触发任何真实执行或副作用"
}
```

---

## 全局约定

### 所有工具都会返回 `_trust_mark`（除 meta 类元工具本身）

```json
{
  "_trust_mark": {
    "cert_id": "AGRI-YYYY-MM-DD-XXX",
    "signature": "sha256:...",
    "signature_prefix": "12-hex",
    "verification_cmd": "python -m core.trust_layer verify",
    "issued_at": "2026-10-23T00:00:00Z"
  }
}
```

### 独立复算命令

```bash
python -m core.trust_layer verify
python scripts/verify_trust_mark.py --cert-id AGRI-2026-10-19-001
```

### 常见错误

- `contract_violation: required key missing` — 必填字段缺失
- `contract_violation: out of range` — 数值越界
- `data_quality_warning: modeled` — 结果基于模型推算，非田间验证
- `not_modified: true` — ETag 命中，无需重新渲染

---

## 相关文档

- **协议规范**：`mcp/README.md`（MCP 2026-07-28 无状态协议）
- **A2A Card**：`.well-known/agent.json`
- **MCP Server Card**：`.well-known/mcp-card.json`
- **Env Recipe Schema**：`schemas/env_recipe.schema.json`
- **数据血缘**：`docs/DATA_LINEAGE.md`
- **快速上手**：`docs/QUICKSTART.md`
- **可运行示例**：`examples/`

---

*文档版本：2026-10-28 · 工具总数：30 · 分类数：15 · 权威源：`mcp/server.py:TOOLS`*
