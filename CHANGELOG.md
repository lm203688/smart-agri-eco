# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。所有条目以 `harness/manifest.json` 与单元测试实际输出为准，非人工断言。

---

## [Unreleased · v1.1.2 待发] - 2026-10-09（P1 能力落地 + 文档口径同步）

> **性质**：承接 10-08 分发通道补齐后的**首批 P1 能力落地**，非 MCP 协议变更，MCP server 本体未动，因此版本号暂未升（server.json / plugin.json 仍为 1.1.0），下次真正需要重建 MCPB 时随 v1.1.2 一并发布。
>
> **判定依据**：P0 主线的**可自主推进部分**已全部落地；剩余 2 项（公网 Demo + 3 家站内提交）需用户人工操作。

### 新增

- **Env Recipe v1.2 派生量**（`engine/derived.py`）：
  - `derive_dli(zone_id)`：按分区从 `global_zones.json` 的 `climate_baseline.dli_annual_mol_m2_day` 推导每日光积分（NASA POWER `ALLSKY_SFC_SW_DWN` 全谱短波辐射光子当量，**非标准 PAR DLI**），8/8 分区可用，`available=False` 时绝不编造
  - `sowing_depth_cm(growth_days)`：复用 growth_agent 公式 `round(gd/200,1)`，缺失时返回 None
  - `vpd()` / `dew_point()`：既有函数，补入 v1.2 派生量回归
  - **铁律遵守**：派生量不写回配方 JSON，运行时推导（`test_env_derived_v12.py` 显式锁定「调用后配方不应出现 dli/sowing_depth 键」）
- **sources 三字段补齐**：`scripts/backfill_source_provenance.py` 为 458 条 sources 逐条补齐 `trial_location` / `data_quality` / `source_license`，458/458 齐备（`data_quality` 分布 measured 116 / modeled 342），`CORE_OBJECTIVE.md` §五 法务刚需已满足
- **MCP 自测纳入 unittest**：`scripts/test_mcp_server_unit.py` 适配层（3 项 unittest），不改动 `test_mcp_server.py` 原文件独立可跑性
- **MCP 命名空间守护**：`scripts/check_mcp_namespace.py` + 4 项回归测试，防 pip `mcp` SDK 遮蔽项目 `mcp/` 目录（`python -S -P` 双保险）
- **分发就绪度修复**：`scripts/check_distribution_readiness.py` 修正两处判定 bug（命名空间检查未加 `-S -P`、GitHub 同步误判 `"0 ==="` 子串）

### 补强

- **CI 已就绪**：`.github/workflows/ci.yml` 测试步骤已用 `python -S -P -m unittest`，并新增 `check_mcp_namespace.py` 守护步骤（10-08 完成，本轮确认）

### 验证结果（本机实跑 2026-10-09）

| 门禁 | 结果 |
|---|---|
| `python -S -P -m unittest discover -s scripts` | **Ran 556 tests / OK / skipped=3**（较 10-08 晚的 533 新增 23 项） |
| `python scripts/check_distribution_readiness.py --full` | **21 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待用户执行） |
| `python scripts/check_demo_endpoints.py` | ✅ 14 通过 / 0 失败 |
| `python scripts/test_mcp_server.py` | ✅ MCP server 自测全部通过 |
| Env Recipe v1.2 派生量（8 分区 DLI + 播种深度） | ✅ 8/8 分区可用，铁律（不写回配方）回归锁定 |
| sources 三字段 | ✅ 458/458 齐备 |
| GitHub 本地 ↔ 远端 main | ✅ 完全一致（353 文件，`sync_check` 差异 0） |

### 文档口径同步（本轮修正）

- `README.md`：单测 533 → **556**；回归项列表由「十三项 513」补至「十八项 556」（新增 dist_readiness / env_derived_v12 / source_provenance / mcp_server_unit / mcp_namespace 五项）
- `docs/full_liftup_assessment_2026-10-08.md`：§1.1 单测基线 537 → 556；§1.4 P1-2 sources 三字段 0/458 → **458/458**；§8 P1-1 标「部分完成」（派生量已落地、companion_plants/revision_history 待补）；P1-9 标「部分完成」（MCP 自测已纳入、v4/v5 拆分待做）
- `docs/liftup_post_distribution_2026-10-08.md`：P1-1 / P1-2 / P1-3 三行状态更新；引言与结论段同步 533→556 与 P1-2 已完成；§2.3 收尾清单 D3/D4/D5 标记已完成
- `docs/distribution_checklist.md`：§0 状态表 P0-6 commit `6ef8b6c8cdeb` → `4349dfdacf5c`（139 文件 / 353 总），P0-4e 20→21 通过；§1 推送结果段落同步
- **未改动**：`docs/CORE_OBJECTIVE.md`（其 §九 仅列 P0 进度，P1 尚未开工口径待 G1 达成后更新）

### 已知剩余项（需用户操作，非代码问题）

- 公网 Demo 部署：`ssh-copy-id root@150.158.119.19` 后 `bash deploy/deploy_local.sh`
- Glama / LobeHub 三家站内确认（Smithery 大概率自动抓取，其余两家需填表单）
- 建议撤销已使用过的 GitHub PAT（最小暴露原则）

---

## [Unreleased · v1.1.1 待发] - 2026-10-08 下午（分发就绪度补齐）

> **性质**：v1.1.0 的**分发通道补齐**，非功能变更。MCP server 本体、Env Recipe、Agent 层均无改动，
> 因此版本号暂未升（server.json / plugin.json 仍为 1.1.0），下一次真正需要重建 MCPB 时随 v1.1.1 一并发布。
>
> **判定依据**：P0-4 主线的**自主可推进部分**——凡是本机可做、直接提升 G1 出口指标的动作全部落地；剩余 2 项（公网 Demo + 3 家站内提交）需用户人工操作。

### 新增

- **Smithery 自动发现入口**：新增 `smithery.yaml`（仓库根目录）
  - Smithery 从公开仓库抓取该文件即可生成服务器条目，**无需填提交表单**
  - 覆盖字段：schemaVersion / name / startCommand / configSchema / mcpServers / tools 摘要 / limitations 边界声明
- **分发就绪度一键自检**：新增 `scripts/check_distribution_readiness.py`
  - 一次性验证 **10 类分发入口**：MCP server（14 工具 + SEP 合规）/ A2A Card / Agent Plugin / Smithery / 官方 Registry 元数据 / MCPB 包 / CI workflow / Demo 部署 / 市场材料 / GitHub 同步
  - 内嵌 Registry `fileSha256` 与 MCPB 产物**逐字节回读比对**，杜绝"声明与实际不符"
  - 支持 `--full`（详细）与 `--ci`（非零退出即失败）
- **市场材料细化**：`docs/market_listing_pack.md` §2/§3/§4 补齐 Glama 一键表单字段、LobeHub 官方入口 URL、Smithery 自动发现已就绪说明

### 补强

- **A2A Agent Card**（`.well-known/agent.json`）：
  - `additionalInterfaces` 由 2 项扩至 **5 项**（追加官方 Registry / Smithery / Glama 搜索入口，供 A2A 客户端跳转）
  - `provider` 补 `organizationType`、`email`
  - `capabilities` 显式声明 `stateless: true`（对应 SEP-2567）
  - `x-agri-integrity` 新增 `mcpProtocol`（版本号 + 5 个 SEP 逐条说明）、`distribution`（Registry 上架时间 + Smithery 自动发现状态 + MCPB sha256）
- **README** 顶部新增 4 家市场入口横幅 + 分发就绪度自检命令

### 验证结果（本机实跑 2026-10-08）

| 门禁 | 结果 |
|---|---|
| `python scripts/check_distribution_readiness.py` | **20 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待用户执行） |
| `python scripts/check_agent_card.py` | ✅ 通过（14 skills ↔ 14 MCP 工具，协议 1.0） |
| `python scripts/test_mcp_server.py` | ✅ 41 项断言全通过 |
| `python scripts/build_agent_plugin.py --check` | ✅ 与 skills/registry 一致（13 文件） |
| Registry `fileSha256` ↔ MCPB 实际 sha | ✅ 一致（`390e9779…`） |
| GitHub 本地 ↔ 远端 main | ✅ 完全一致 |

### 已知剩余项（需用户操作，非代码问题）

- 公网 Demo 部署：`ssh-copy-id root@150.158.119.19` 后 `bash deploy/deploy_local.sh`
- Glama / LobeHub / Smithery 三家站内确认（Smithery 大概率自动抓取，其余两家需填表单）

---

## [v1.1.0] - 2026-10-08（官方 MCP Registry 上架）

**发行形态**：MCPB 分发包 · GitHub Release · 官方 MCP Registry

### 上架结果
- 官方 MCP Registry：**`io.github.lm203688/agri-eco` v1.1.0** 已发布（2026-10-08T05:33:32Z）
- `registryType: mcpb`，产物 `agri-eco-mcp-1.1.0.mcpb`（200 文件 / 0.44 MB）
- `fileSha256 = 390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24`
- 发布链路已 CI 化（`.github/workflows/publish-mcp-registry.yml`），GitHub OIDC 免人工

### 工程指标
- 单元测试 **533 OK**（3 skip 为 live API 探针），较 v0.9-beta 的 505 新增 28 项
- `verify_all.py` **PASS**（8 阶段全过）
- CI 22 步 × Python 3.10/3.11/3.12 **全绿**
- Demo 端点冒烟 **14/14 通过**（`scripts/check_demo_endpoints.py`，已入 CI）

### 本版修复（均为 CI 上真实失败后定位）
- **MCPB 确定性构建**：zip 曾写入文件 mtime，同一份源码两次构建 sha 不同，
  导致 `server.json` 的 `fileSha256` 永远追不上产物。改为固定 `ZipInfo`
  （`date_time=(1980,1,1,0,0,0)` / `create_system=3` / 权限 `0644`）。
- **打包清单排除未入库文件**：本地遗留 `.bak` 混入包内（本地 201 / CI 200 文件），
  新增 `EXCLUDE_FILE_MARKERS`，现本地 = CI = `390e9779`。
- **CI 发布一条龙**：改为 CI 内构建 → `gh release upload --clobber` → 回读校验 →
  发布，消除"本地构建 / 手工传资产"的手工同步环节。
- **Publish 幂等**：同版本重复发布（400）视为成功；但内容变而版本未升时，
  由「版本漂移检测」显式报错，防止新代码静默发不出去。
- **CI 数据门禁**：修复推导式作用域 bug（`NameError: name 'k' is not defined`），
  提取为 `scripts/check_data_integrity.py` + 13 项回归。
- **作物库补齐**：`hot_arid` / `highland` 各补 18 条，8 分区全部 ≥18（116 → 152 作物）。
- **安全**：`.workbuddy/` 加入 `.gitignore`（旧会话日志曾明文记录 PAT），
  历史日志就地脱敏，全盘残留审计 = 0。

### 已知限制（需用户操作，非代码问题）
- 公网 Demo 部署待执行：需先 `ssh-copy-id root@150.158.119.19`
- Glama / LobeHub / Smithery 上架待提交：各需独立账号

---

## [v0.9-beta] - 2026-10-06（发行）

**发行形态**：开发者预览版 · 邀请制 · GitHub Release

### 工程指标
- 单元测试 **505 OK**（3 skip 为 live API 探针）
- `verify_all.py` **PASS**（8 阶段全过）
- `data_quality_gate.py` **全部通过**（6 文件）
- MCP 工具 **14 个**（自测冒烟通过）
- Harness manifest 版本 **2.2.0**（数据基线：8 区 / 116 作物 / 113 校准）

### 核心能力
- **7 Agent 编排**：ClimateAgent → CropAgent → GrowthAgent → EcoAgent 串联，加 PestAgent / NutritionAgent / SeasonAgent 按需调用
- **Env Recipe**：116 份可执行配方（`data/env_recipes/<zone>__<crop>.json`），温湿/光谱/PPFD/CO₂/EC/pH/水肥/气流/异常九维参数集
- **作物覆盖**：116 种（8 分区 × 作物），**113 已用 NASA POWER + Open-Meteo 双源校准**（含 `measured_calibration` 实证）
- **权威数据源**：NASA POWER / Open-Meteo / WorldClim / GBIF / SoilGrids（5 API + 4 本地文件），全量可血缘追溯
- **决策层**：TypeSafe Jev System One 决策模型，配方门禁 116 安全 / 0 可疑

### 分区覆盖（闭环）
- **8 个已建模分区**：tropical_rainforest / subtropical_wet / temperate_continental / mediterranean / arid / subarctic / **hot_arid（迪拜等）/ highland（拉萨等）**
- 2026-10-06 补 hot_arid / highland 真实气候基线 + 6 配套作物定向 P3 校准（椰枣/骆驼刺/沙葱/藜麦/青稞/洋姜），KG `grows_in` 110 → 116（8 区全有作物邻接），迪拜/拉萨跨元数据+测试全链路翻标 `modeled=True`，气候 Agent 死代码 `UNMODELED_ZONE_CLASSES` 已清

### 病虫害诊断视觉后端（2026-10-06 决策）
- **选型：离线规则降级（无外部依赖）**。`agent/vision.py` 未配置 `AGRI_VISION_*` 时返回 None，调用方 `pest_agent.diagnose()` 自动降级为 `rule_based`；任何异常/超时均不中断主流程。云端 VLM（ATEX / OpenAI）为可选插拔，不强制。

### 新增 MCP 工具（3 个，2026-09-29 起）
| 工具 | 用途 |
|---|---|
| `agri_reconcile_climate` | 多源气候调和：`(lat, lon)` 并行拉 NASA POWER + Open-Meteo，产出逐月调和均值/一致度/分歧告警 |
| `agri_resolve_recipe` | 地理编码 → 分区 → Env Recipe 解析：城市名或坐标匹配 `<zone>__<crop>.json` |
| `agri_query_lineage` | 数据血缘查询：作物 × 分区 × 数据源四档查询模式 |

### 已修复（2026-09-27 → 2026-10-06）
- **合成样本污染守卫硬化**：`engine/rsi._is_synthetic` 改为大小写不敏感 + 独立词匹配（原只匹小写 `[demo]`，大写 `Demo` 可绕过）；测试同源复用并新增回归用例 `test_is_synthetic_catches_uppercase_demo`
- **测试缓存隔离**：`test_planting_window_autofetch_wires_provenance` 用 `tempfile.mkdtemp()` 隔离默认缓存目录，防磁盘缓存短路 mock
- **测试临时文件排除**：`.gitignore` 追加 `data/_test_feedback_log.json` / `data/*.bak` / `data/*.test.*`
- **文档 stale 数字**：README / CHANGELOG / release_checklist 同步 6→8 分区、110→116 配方、107→113 校准、单测 477→504、MCP 13→14
- **气候 Agent 死代码清除**：`UNMODELED_ZONE_CLASSES` 清空（v1.1 已建模），保留 `_detect_unmodeled_zone` 做热漠/高原精确路由（迪拜→BWh/rubric 0.95，拉萨→H/rubric 0.95，均无 coverage_gap）

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

### 产品决策（2026-10-06 已拍板）
- [x] ~~是否新增 hot_arid / highland 分区建模~~ → **已闭环**：8 分区全建模，hot_arid/highland 补真实气候基线 + 6 作物定向 P3 校准（见 v0.9-beta）
- [x] ~~高原是否改"就近已建模分区 + 显式近似标记"~~ → 已建模闭环，无需近似标记
- [x] ~~视觉后端选型（病虫害诊断方向）~~ → **离线规则降级**（无外部依赖，AGRI_VISION_* 未配置自动 rule_based）

---

## 版本策略

- **v0.x**：内部研发 / 邀请制 beta。允许已知产品限制明示。
- **v1.0**：需 4 项 RSI 门禁闭合 + 至少 2 项 pending evals 达标（工程门槛）。
- **v2.0**：商业化发行（需 eval_recipe_expert_adoption + eval_source_traceability）。

---

*本 CHANGELOG 更新于 2026-10-06，与 `harness/manifest.json` v2.2.0 对齐（数据基线：8 区 / 116 作物 / 113 校准）。*
