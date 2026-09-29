# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。所有条目以 `harness/manifest.json` 与单元测试实际输出为准，非人工断言。

---

## [v0.9-beta] - 2026-09-29（待发行）

**发行形态**：开发者预览版 · 邀请制 · GitHub Release

### 工程指标
- 单元测试 **477 OK**（3 skip 为 live API 探针）
- `verify_all.py` **PASS**（8 阶段全过）
- MCP 工具 **13 个**（自测冒烟通过）
- Harness manifest 版本 **2.2.0**，指纹 `7e073c0073973625`

### 核心能力
- **4 Agent 编排**：ClimateAgent → CropAgent → GrowthAgent → EcoAgent 串联，加 PestAgent / NutritionAgent / SeasonAgent 按需调用
- **Env Recipe**：110 份可执行配方（`data/env_recipes/<zone>__<crop>.json`），温湿/光谱/PPFD/CO₂/EC/pH/水肥/气流/异常九维参数集
- **作物覆盖**：110 种（6 分区 × 作物），**107 已用 NASA POWER + Open-Meteo 双源校准**（含 `measured_calibration` 实证）
- **权威数据源**：NASA POWER / Open-Meteo / WorldClim / GBIF / SoilGrids（5 API + 4 本地文件），全量可血缘追溯
- **决策层**：TypeSafe Jev System One 决策模型，配方门禁 110 安全 / 0 可疑

### 新增 MCP 工具（3 个）
| 工具 | 用途 |
|---|---|
| `agri_reconcile_climate` | 多源气候调和：`(lat, lon)` 并行拉 NASA POWER + Open-Meteo，产出逐月调和均值/一致度/分歧告警 |
| `agri_resolve_recipe` | 地理编码 → 分区 → Env Recipe 解析：城市名或坐标匹配 `<zone>__<crop>.json` |
| `agri_query_lineage` | 数据血缘查询：作物 × 分区 × 数据源四档查询模式 |

### 分区覆盖
- **6 个已建模分区**（含 `subtropical_wet` / `temperate_continental` 等）
- **2 个已知未建模分区**：`hot_arid`（迪拜等）/ `highland`（拉萨等），运行时降级为 `coverage_gap`，**不编造 recommendation**，明示箱体替代路径

### 已修复
- **合成样本污染守卫**：`agent/execution_log.py::_is_synthetic()` 与 `engine/rsi.py::_is_synthetic()` 统一扩展为 `.lower()` + 覆盖 `run_id/device_id/source`，防 `Demo feedback` 大写变体绕过（2026-09-27 复发教训）
- **测试缓存隔离**：`test_planting_window_autofetch_wires_provenance` 用 `tempfile.mkdtemp()` 隔离默认缓存目录，防磁盘缓存短路 mock
- **测试临时文件排除**：`.gitignore` 追加 `data/_test_feedback_log.json` / `data/*.bak` / `data/*.test.*`
- **文档 stale 数字**：`README.md` / `docs/intel_log.md` / `docs/commercialization_assessment_2026-09-19.md` 中 `358 → 477`、`MCP 10 → 13`

---

## [v0.9-alpha] - 2026-09-27（内部研发里程碑）

- MCP 工具 10 → 13（climate_reconcile / geo_recipe / lineage 三项能力）
- `core/climate_reconcile.py` 多源气候调和模块
- `core/geo_recipe.py` 地理编码→配方解析模块
- `core/data_lineage.py` 新增 `query_lineage()` 四档查询
- `harness/manifest.json` `tool_count` 10 → 13
- 单元测试 358 → 477

---

## [v0.8] - 2026-09-25（数据血缘与审计闭环）

- 新增 `core/data_lineage.py`（数据血缘追踪模块）
- 新增 `mcp/audit_analyzer.py`（CyberGuard 行为审计分析器）
- `scripts/data_quality_gate.py`（数据清洗门禁）
- `scripts/harness_sync.py` 支持 baseline 吸收
- `data/preset_cities.json` 单一数据源（12 城市）

---

## [v0.7] - 2026-09-24（Agent 生态实查 + 决策层接入）

- 否决接入 osiris（地缘政治/RECON 扫描，与农业零相关）
- 3 份 GOAI 分析文档顶部加"未落地方案分析"声明
- `agent/jev_gate.py` TypeSafe Jev 决策层封装（零依赖 urllib）
- Jev 三级 key 解析回退：env → 凭证文件 `~/.config/typesafe/credentials.json`

---

## [v0.6] - 2026-09-23（分区覆盖缺口定案）

- **A2 路线修复**：`climate_agent.py` 新增 `UNMODELED_ZONE_CLASSES` + `_detect_unmodeled_zone()`，`hot_arid` / `highland` 显式降级
- 降级输出加 `evidence.coverage_gap` + `confidence_note` + 箱体替代路径
- 预设城市清单带 `modeled: false` 字段，调用方可在**不请求分区**时先知道覆盖缺口
- 477 单测基线；`TestPrecipUnitsContract` 锁定 mm/day 口径
- 校准基线 107（NASA POWER + Open-Meteo 双源）

---

## [v0.5] - 2026-09-20（物候与季节 Agent）

- 新增 `agent/phenology.py`（WOFOST 物候模型，7 作物，EUPL 1.2）
- 新增 `agent/season_agent.py`（霜冻锚定播期窗口）
- 前端 `app/index.html` 11 tab / 20 端点

---

## [v0.4] - 2026-09-16（初筛与商业边界）

- 新增 `bp_screen/` 农眼 AgriScreen 投资初筛系统（规则库 v2.0.0，15 case / 6 gate）
- 初筛核验只出 `local_hit` / `unverified` / `not_found`，**绝不产 verified**（EPPO 不能用于证照核验）
- 确立商业边界：**只做 MCP 分发**（Agent-native 通道），C 端 App / B 端 SaaS / 配方授权 / 免费换数据 **全否**

---

## [v0.3] - 2026-09-15（首个自动生成的 Skill）

- `skills/registry/iceplant_advisory.json`（首个 auto_generated skill）
- 确立 skill_factory 模式：新增作物即自动注册为可复用 Skill

---

## [v0.2] - 2026-09-12（4 Agent 编排基线）

- ClimateAgent / CropAgent / GrowthAgent / EcoAgent 四 Agent 串行编排
- `AgriOrchestrator` 统一技能路由（`run_pipeline` + `call_skill`）
- Session 幂等缓存 + 长期记忆（跨会话上下文）

---

## [v0.1] - 2026-09-10（项目启动）

- 项目定位：全球农业环境配置知识底座 + 城市种植生成箱
- MCP server 骨架（JSON-RPC 2.0 over stdio，零依赖）
- 初始 Env Recipe schema 定义

---

## [Unreleased · v1.0 目标]

### 前置条件（4 项 RSI 门禁 + 4 项 pending evals）
- [ ] **execution_log**：至少 1 条真实 Env Recipe 执行回流（需硬件接入）
- [ ] **feedback_inflow**：至少 1 条真实用户反馈回流（需用户）
- [ ] **skill_generation**：auto-generated skill 接入 orchestrator（需产品拍板入口形态）
- [ ] **meta_improvement**：gate_version bump + 历史快照演化（需一次真实产品迭代）
- [ ] **eval_extraction_accuracy**：100 条人工标注样本
- [ ] **eval_pest_diagnosis_topk**：PlantVillage + 200 张中文场景图 + 视觉后端
- [ ] **eval_recipe_expert_adoption**：3-5 位农艺专家盲评 50 份配方
- [ ] **eval_source_traceability**：溯源层埋点 + 引用 URL 可访问性校验

### 待用户拍板的产品决策
- [ ] 是否新增 hot_arid / highland 分区建模（产品扩张）
- [ ] 高原是否改"就近已建模分区 + 显式近似标记"
- [ ] 视觉后端选型（病虫害诊断方向）

---

## 版本策略

- **v0.x**：内部研发 / 邀请制 beta。允许已知产品限制明示。
- **v1.0**：需 4 项 RSI 门禁闭合 + 至少 2 项 pending evals 达标（工程门槛）。
- **v2.0**：商业化发行（需 eval_recipe_expert_adoption + eval_source_traceability）。

---

*本 CHANGELOG 生成于 2026-09-29，与 `harness/manifest.json` v2.2.0 对齐。*
