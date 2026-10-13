# 智慧农业生态 · 长期项目记忆

> 本文件是跨会话项目约定与结构性事实的**唯一权威源**。控制 3000 字符以内。
> 单次会话记录请写入 `YYYY-MM-DD.md`；本文件只留**跨会话仍然成立**的东西。

---

## 一、项目定位（单一权威口径）

- 定位：**分布式农业的 Agent-native 知识基座**。做「在哪里种什么、怎么种得好」的可执行配置（Env Recipe），以可审计的数据血缘作为可信度资产。
- 三个关键词：**Agent-native** / **知识基座** / **分布式农业**。
- 详细口径见 `docs/CORE_OBJECTIVE.md`（该文件是所有冲突的裁决源）。

## 二、G1 出口指标与窗口

- 目标：MCP server 累计外部调用 **≥500 次** / 独立调用方 **≥20 个**。
- 窗口：约 2026-09 中旬启动 → 约 **2026-12 中旬截止**。
- 决策门：P0 全绿后仍 3 个月零外部调用 → 项目降级为个人知识库，停止对外投入。
- 当前外部调用：**0**（自 v1.1.0 上架至 2026-10-08 结束）。

## 三、硬约束（AI 每次会话必读）

1. **P1 及以下在 G1 达成前一律不开工**（CORE_OBJECTIVE §八）。任何"全面提升"请求必须先核对是否属于 P0 出口指标直接提升。
2. **不编造数据**：不可测即标不可测；NC 来源不得转售（法务红线，见 CORE_OBJECTIVE §五）。
3. **零依赖**：核心计算与数据路径必须纯标准库；增强能力走 `AGRI_*` 环境变量插拔，未配置时降级且**显式标注**（不静默伪装）。
4. **不改口径**：任何战略文件（`docs/planning/项目战略指引.md` 等）与 CORE_OBJECTIVE 冲突时，一律以 CORE_OBJECTIVE 为准。
5. **凭据不入仓库**：PAT / API Key 走临时文件 + 用完即删；`.workbuddy/` 已加入 `.gitignore`（历史日志曾明文记录 PAT）。

## 四、七层架构当前定性（2026-10-08 定案）

- L0 数据底座 / L1 感知 / L2 模型 AI / L3 执行控制 → ✅ 主线，重点投入
- L4 业务支撑 / L5 消费服务 / L6 运营生态 → ⏸ **正式暂缓**（判定依据见 CORE_OBJECTIVE §三 N6/N7、§六）
- 七层是**分析框架**，不是**交付清单**。README 中此前"已落地"字样已按实测校正。

## 五、P0 完成状态（截至 2026-10-08）

- ✅ P0-1 MCP 2026-07-28 无状态适配（SEP-2575/2567/2243/2549/414 全适配）
- ✅ P0-2 A2A Agent Card（`.well-known/agent.json`，14 skills ↔ 14 MCP 工具）
- ✅ P0-3 Agent Plugins 打包（`plugin/`，13 文件）
- ✅ P0-4a MCPB 分发包（`dist/agri-eco-mcp-1.1.0.mcpb`，确定性可复现 sha `390e9779…`）
- ✅ P0-4c 官方 MCP Registry 上架（`io.github.lm203688/agri-eco` v1.1.0）
- ✅ P0-4d Smithery 自动发现（`smithery.yaml` 免表单抓取，2026-10-08 补）
- ✅ P0-4e 分发就绪度自检（`scripts/check_distribution_readiness.py`，21/21 全绿，含 MCP 命名空间守护）
- ✅ P0-5a Demo 端到端冒烟（14/14 端点通过，已入 CI）
- ✅ P0-6 GitHub 推送（332 文件，`sync_check` 差异 0）
- ✅ P0-7 消除硬编码密钥（`grep secret_key` = 0 命中）
- ✅ P0-4b LobeHub（`lm203688-smart-agri-eco`，2026-10-08 自动发现 + `lhm.plugin.json` 已推送）
- ✅ P0-4b Glama（2026-10-11 通过 CDP 复用主 Edge 登录态自动提交，`POST /api/mcp/servers/submit.data` 200）
- ⏸ P0-5 公网 Demo 部署（需 `ssh-copy-id root@150.158.119.19` 后一键上线）

**P0 累计：12/12 项自主可推进部分完成**。仅剩公网 Demo 部署需用户 SSH 操作。

**P1 D3 特例（不等外部调用可建的可验证方法层，2026-10-11 落地）**——CORE_OBJECTIVE §八 "P1 一律不开工" 的例外，依据报告 §8.2 D3 "唯一不等外部调用的壁垒" 与 §5.2/§5.4 SNWM 可验证协议 + MCP 2026-08 路线图对标：
- ✅ AgriRecipeBench 骨架（`benchmarks/agri_recipe_bench/`，M1+M2，5/5 通过）
- ✅ T-3 置信区间（`prediction_interval.{p10,p50,p90}` + `confidence.uncertainty` 分解）
- ✅ T-1 可信标记产品化（MCP 所有 tools/call 内嵌 `_trust_mark`）
- ✅ D-4 A2A Card JWS 签名（HMAC-SHA256 零依赖，密钥走 `AGRI_A2A_SIGNING_KEY` 环境变量，不入库）

**P1 D3 特例续（2026-10-13 落地）**——报告 `framework_evolution_liftup_2026-10-13.md` §6.4 S1/S2 + §6.3 E1/E4/E3 + §6.2 W5 + §6.1 F5，全部零依赖外部调用：
- ✅ S1 受控自进化声明（`.well-known/evolution_zones.json` **v3**：8 项不可进化区 + 8 项可进化区 + `gate_version` 版本化 + history）+ CORE_OBJECTIVE §十
- ✅ S2/E1 多模块不变式棘轮（`benchmarks/ratchet_modules.py`，4 模块 27 用例：climate_stability/forecast_interval_bounds/phenology_gdd_monotonicity/nutrition_npk_balance；CI 硬门禁 `--strict`）
- ✅ E4 Golden Vectors（`benchmarks/golden_vectors/{forecast,phenology,nutrition}.json` 16 用例，tolerance 0.0/0.1；`scripts/run_golden_vectors.py` + CI `--strict`）
- ✅ E3 溯源字段门禁（`data_quality_gate.py::_check_env_recipe_sources`，152 配方 × 760 sources 三字段完整性 + 白名单）
- ✅ W5 治理 badge（`scripts/generate_status_badge.py` 纯标准库 SVG，4 指标：data_sources 4/4 · bench 11/11 · ratchet 27/27 · golden 16/16；`artifacts/status_badge.svg` + README 嵌入）
- ✅ **A1 Köppen 栅格抽象层（F5）**（`core/climate_grid.py`，标准库栅格点查询引擎：O(1) 空间索引 + 最近邻 + 3×3 邻居 + 1/d² 权重归一化 → 概率分布；Koppe-Geiger → 项目 8 分区映射表；`NoGridData` 显式异常；合成测试栅格 800 cells/9 类；climate_agent 双后端接入，无栅格显式降级标注）+ `scripts/test_climate_grid.py`（18 项单测）
- ✅ **S2/E1 棘轮 CI 硬门禁**（`scripts/run_evolution_ratchet.py`，读 evolution_zones.json 白名单 → 跑 benchmark 判分数 → 退出码 0/1/2/3；`--min-score`/`--check-files`/`--json` 三模式）+ `scripts/test_evolution_ratchet.py`（6 项单测）

**P1 D3 特例续（2026-10-13/14 主线一批次）**——报告 `per_module_deep_assessment_2026-10-13.md`，主线一「接通」大部分前几轮已落地，本轮补齐 M10 编排层：
- ✅ **M9-X1 影子执行日志**（`data/execution_log.json` 3 条 + `agent/execution_log.py` + `scripts/generate_shadow_execution_log.py` + `schemas/execution_log.schema.json` + tests）——RSI L1 门闭合证据
- ✅ **M8-R2 配方 profile 四件套**（`scripts/recipe_profile.py` export/import/diff/clone + tests）
- ✅ **M5-F1 Split Conformal 保形预测**（`agent/conformal.py` 204 行，零依赖 Split Conformal 校准器，90% 覆盖率下界；`agent/forecast_agent.py` 已接入 + `scripts/test_conformal.py`）
- ✅ **M10-O2 跨 Agent 一致性检查 + M10-O4 编排 trace 导出**（`agent/orchestration_audit.py` ~400 行，5 条规则：climate_constraints_coverage / growth_crop_match / eco_devices_budget_fit / top_crop_device_match / growth_start_date_frost，含 error/warning/info 三级严重度；`TraceRecord` + `summary_hash` SHA256 稳定可复算；`orchestrator.run_pipeline` 挂 audit hook 写 `result["consistency_audit"]` + `result["orchestration_trace"]`；`scripts/test_orchestration_audit.py` 29 项单测 + CI 硬门禁）
- ✅ **M11-T1 可信标记产品化徽章**（`scripts/generate_trust_badge.py`）
- ✅ **M12-K1 检索/图谱 MCP 接入**（`mcp/server.py` 新增 `agri_search` + `agri_knowledge_query`，工具数 14 → 18）
- ✅ **gate_version v2 → v3**（`.well-known/evolution_zones.json`，M10 编排层可审计性资产纳入棘轮管控 + history 记录变更理由）
- ✅ **14→18 工具漂移同步**（`scripts/check_mcp_namespace.py` `EXPECTED_TOOL_COUNT=18` / `scripts/test_engine_v5.py` / `README.md` / `mcp/README.md`）

**不做**（超出 D3 特例范围或需外部数据）：A2 机制作物模型（PCSE/WOFOST 论文重实现 7-10 天）、L1 视觉、L0-2 CMIP7 情景、M-1 激励机制、L2-5 两项 eval pending（需真实数据 / 专家盲评）。

**A1 后续（等数据接入）**：Koppe-Geiger 栅格真实数据（Beck et al. 2018/2023，CC BY 4.0）需用户手动下载放入 `data/zone_meta/koppen_grid.json`，抽象层已就绪，数据到位即自动启用栅格后端。

## 六、门禁与自检（每次评审/发布前跑一遍）

```bash
python scripts/check_distribution_readiness.py       # 分发就绪度（10 类分发入口）
python scripts/check_agent_card.py                   # A2A Card + 与 MCP 一致性
python scripts/build_agent_plugin.py --check         # Plugin 与 skills/registry 一致
python scripts/test_mcp_server.py                    # MCP 41 项断言
python scripts/check_demo_endpoints.py               # Demo 14 端点
python scripts/verify_all.py                         # 端到端 8 阶段
python scripts/data_quality_gate.py                  # 数据质量 + E3 溯源字段
python benchmarks/agri_recipe_bench/run_bench.py     # AgriRecipeBench 5/5
python -m benchmarks.ratchet_modules --strict        # S2/E1 棘轮 27/27
python scripts/run_golden_vectors.py --strict        # E4 Golden 16/16
python scripts/generate_status_badge.py --ci         # W5 治理 badge
python scripts/run_evolution_ratchet.py --json       # S2/E1 棘轮 CI 硬门禁（score≥0.5）
python -m unittest discover -s scripts -p "test_*.py"  # 631 单测（skipped=4）
python scripts/sync_check.py                         # 与远端 GitHub 差异
```

当前基线：全绿（本地 = 远端，438 文件，CI 28 步，`verify_all` PASS）。任何一条变红即视为不可上线。

**已知工具冲突（2026-10-11 修）**：`scripts/clean_demo_data.py` 剥离校准标记后曾把 `calibrated` 字段整个 pop 掉，但 `scripts/data_quality_gate.py` 强制要求该字段显式存在且为 bool → 每次跑 clean 后 verify_all 都会变红。现已修复：`strip_calibration` 剥完 CALIB_FIELDS 后回填 `crop["calibrated"] = False`，语义从「字段缺失」改为「未实测校准」，两脚本对齐，clean 变幂等。

**AgriRecipeBench（P1 壁垒，G1 前不等外部调用的唯一例外）**：`benchmarks/agri_recipe_bench/` 落地 SNWM 神农世界模型四轴协议裁剪版 v0.1，含 M1 target_prediction（3 用例：地中海番茄/地中海胡萝卜/亚热带生菜）+ M2 state_rolling（2 用例：保护地黄瓜/空输入降级），5/5 全通过。CI 已挂 `--strict` + `unittest scripts.test_agri_recipe_bench`。M3 反事实 / M4 跨情境泛化需 G1/G2 outcome 回流后开启。种子用例的 expected 值原则：不是"标准答案"，而是"引擎启发式输出 × 农艺常识"的交叉锚点，provenance 显式写明来源（`_BASE_YIELD_G` 或文献）。

## 七、关键资产与文件地图

- **权威源**：`docs/CORE_OBJECTIVE.md`
- **门禁数字**：`docs/north_star_and_phase_gates.md`
- **全面提升基线**：`docs/full_liftup_assessment_2026-10-08.md`
- **分发操作手册**：`docs/distribution_checklist.md`
- **市场提交材料**：`docs/market_listing_pack.md`
- **MCP server**：`mcp/server.py`（40KB / 14 工具）
- **A2A Card**：`.well-known/agent.json`
- **Agent Plugins**：`plugin/plugin.json` + `plugin/mcp.json` + `plugin/skills/*/SKILL.md`
- **Smithery 入口**：`smithery.yaml`
- **Registry 元数据**：`server.json`（含 fileSha256）
- **MCPB 产物**：`dist/agri-eco-mcp-1.1.0.mcpb`（452KB / sha 390e9779…）
- **AgriRecipeBench**：`benchmarks/agri_recipe_bench/`（M1+M2+M3+M4 四轴，11 用例，5/5 通过）
- **受控自进化**：`.well-known/evolution_zones.json`（S1 二元划分，gate_version v2）+ `benchmarks/ratchet_modules.py`（S2/E1 棘轮 27 用例）+ `benchmarks/golden_vectors/`（E4 16 用例）+ `scripts/generate_status_badge.py`（W5 治理 badge）+ `artifacts/status_badge.svg` + `scripts/run_evolution_ratchet.py`（S2/E1 CI 硬门禁，score≥0.5）
- **A1 Köppen 栅格抽象**：`core/climate_grid.py`（标准库栅格点查询引擎 + 概率分布 + 双后端接入）+ `scripts/test_climate_grid.py`（18 项单测）
- **可验证 AI 三件套**：
  - 置信区间：`agent/forecast_agent.py`（`prediction_interval.{p10,p50,p90}` + `confidence.uncertainty`）
  - 可信标记：`core/trust_layer.get_trust_mark()` + MCP `tools/call` 内嵌 `_trust_mark`
  - A2A Card 签名：`scripts/sign_agent_card.py` / `scripts/verify_agent_card.py`（HS256，密钥走 `AGRI_A2A_SIGNING_KEY` 环境变量，不入库）

## 八、竞品与差异化（简版）

- **FieldMCP** $29/org/月，150+ tools（数量竞争，不追）
- **agstack/pestmodels**（Linux Foundation，13 models，**对接非竞争**）
- **神农·农业世界模型 1.0**（L2 概念竞争者，做对标不做跟随）
- **我们**：可执行配置 + 可审计溯源 + 零依赖本地。**厚平台与薄 wrapper 之间的真空地带**

## 九、AI 助手行为规范（本项目）

- **零附和**：任何"全面提升""帮我做完""加油"指令，先核对是否符合 CORE_OBJECTIVE 判据，不符合即主动反对。
- **诚实非讨好**：能做的直接做完；本机不可代劳（账号/凭据/登录）明确列出让用户操作，不隐瞒。
- **推送前必跑门禁**：本地改完必须跑齐 §六 8 条命令，任一失败即停止推送。
- **推送走 `scripts/gh_push.py`**（Contents API），因本机 github.com:443 被封；PAT 需含 Workflows:write。
- **每次收尾写当日日志**：`.workbuddy/memory/YYYY-MM-DD.md`；跨会话结构性事实沉淀到本文件。
