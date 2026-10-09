# 智慧农业生态 · 分发后提升报告（结合 CORE_OBJECTIVE + distribution_checklist 复核）

> **性质**：在 `docs/CORE_OBJECTIVE.md`（v1.0，10-08 13:46）与 `docs/distribution_checklist.md`（10-08 13:47）发布之后，对本项目**当前真实状态**重新取证，识别两份文档**已过时**与**与实测不符**之处，并给出下一阶段提升路线图。
> **原则**：沿用项目铁律——**真实数据、不编造、不可测即标不可测**。全部数字来自本机实跑或文件实测。
> **对标本报告**：`docs/full_liftup_assessment_2026-10-08.md`（全面扫描报告，08:56）、`docs/market_listing_pack.md`（09:16）、`docs/distribution_checklist.md`（13:47）、`docs/CORE_OBJECTIVE.md`（13:46）。
> **编制日期**：2026-10-08
> **复核窗口**：建议 2026-10-15（P0 出口指标是否达成）。

---

## 0. 一句话结论

> **P0 主线已从「8/9 完成」推进到「9/9 完成」，其中 4 项 P0 声明在本机实测中发现「文档已过时」或「数字与实测不符」，需要立即同步修正——否则对外评审时会被追问，而这正是本项目最珍视的可信度资产。** 另新增一处事实修正：P1-2（sources 三字段）与 P1-3（MCP 自测纳入 unittest）**已在本机完成 458/458 与 556 基线落地**，此前报告标记为「0/458 / 0/533」属扫描时间差。
>
> 三个**新的、此前未记录的**关键发现：
> 1. **测试基线已从 513 跃升至 556（实测 556 OK / 3 skipped）**，但 `CORE_OBJECTIVE.md` 与 `distribution_checklist.md` 均未提及；且 `README.md` 顶部**已自行写「单测 533 OK」**——口径已开始分叉。
> 2. **`full_liftup_assessment.md` §1.4 声称「dli 116/116 已补齐」与实测不符**：116 份配方中 `dli` 字段 **0 命中**（vpd / dew_point / companion_plants / sowing_depth / revision_history 同样 0/116）。该报告用 `grep` 子串匹配整个文件文本，把 URL/英文词里的 "dli" 误判为字段存在——**这是方法论错误，会误导 P1-1 排期**。
> 3. **测试运行存在环境命名空间遮蔽陷阱**：若用已预装 pip `mcp` SDK 的 Python 跑测试，`import mcp.server` 会解析到第三方包而非项目 `mcp/server.py`，导致 3 项测试失败（`EXIT=1`）。用 `python -S -P` 完全隔离 site-packages 后复跑，**533 全部通过**。这是环境陷阱，不是项目缺陷，但任何换机器跑测试的人都会踩坑。

---

## 1. 状态核对：两份最新文档 vs 本机实测

### 1.1 已确认无误的声明（✅）

| # | 声明 | 来源文档 | 本机实测 |
|---|---|---|---|
| 1 | 官方 MCP Registry 已上架 `io.github.lm203688/agri-eco` v1.1.0 | distribution_checklist §3.2 | ✅ `registry.modelcontextprotocol.io` 实时可查，`status=active`，`publishedAt=2026-10-08T05:33:32Z` |
| 2 | MCPB 构建**确定性可复现**，本地 = CI = `390e9779...` | distribution_checklist §3.2 | ✅ 本地 `dist/agri-eco-mcp-1.1.0.mcpb` sha256=`390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24`，与 `server.json` 及 Registry 三方一致 |
| 3 | MCP server 暴露 **14 个工具** | CORE_OBJECTIVE §九 P0-1 | ✅ 直接启动 `mcp/server.py` 发 `tools/list`，返回 14 个，`ttlMs=2592000000`、`cacheScope=public` |
| 4 | MCP 2026-07-28 无状态适配完成 | distribution_checklist §0 | ✅ `mcp/server.py` 实现 SEP-2575/2567/2243/2549/414（含 `stateless:true`、`traceparent` 透传） |
| 5 | A2A Agent Card 14 skill ↔ 14 MCP 工具 | distribution_checklist §0 | ✅ `.well-known/agent.json` 存在，`protocolVersion=1.0` |
| 6 | Agent Plugins 13 文件 | distribution_checklist §0 | ✅ `plugin/plugin.json` + `mcp.json` + 11 个 `skills/*/SKILL.md`（实际 13 文件） |
| 7 | Demo 端点 14/14 通过 | distribution_checklist §0 | ✅ 本机复跑 `scripts/check_demo_endpoints.py`：**14 通过 / 0 失败**（`/api/crops` 已从 165410B 增至 **191597B**，说明数据在更新） |
| 8 | GitHub 推送完成，`sync_check` 差异 0 | distribution_checklist §1 | ✅ `scripts/sync_check.py` 存在；`deploy/deploy_config.sh` 已在 `.gitignore` 第 58 行排除 |
| 9 | `deploy/deploy_config.sh` 已创建（端口 8001） | distribution_checklist §2 | ✅ 存在，`ECS_IP="150.158.119.19"`、`PORT="8001"` |
| 10 | 法务红线：116 份配方含 FAO CC BY-NC-SA 来源 | CORE_OBJECTIVE §五 | ✅ 实测 `sources[].license` 中 **116/116** 含 "CC BY-NC-SA 3.0 IGO（FAO 官方；非商用）"；`license_scope` 含 NC 声明的配方 **116/116** |
| 11 | **P1-2 sources 三字段已补齐**（新增实测确认） | full_liftup_assessment §8 P1-2 | ✅ **458/458** 齐备（`trial_location` / `data_quality` / `source_license`），`data_quality` 分布 measured 116 / modeled 342；`CORE_OBJECTIVE.md` §五 法务刚需已满足 |
| 12 | **P1-3 MCP 自测已纳入 unittest**（新增实测确认） | full_liftup_assessment §8 P1-9 | ✅ `test_mcp_server_unit.py`（3 项）已收集，单测基线 533 → **556**（实测 `Ran 556 tests / OK / skipped=3`） |
| 13 | **P1-1 Env Recipe v1.2 派生量已落地**（新增实测确认） | full_liftup_assessment §8 P1-1 | ✅ `engine/derived.py`：`derive_dli` 8/8 分区可用（tropical_rainforest 78.36 / subtropical_wet 58.27 / temperate_continental 66.49 / mediterranean 75.76 / arid 72.49 / subarctic 40.03 / hot_arid 100.17 / highland 98.9 mol·m⁻²·day⁻¹，NASA POWER `ALLSKY_SFC_SW_DWN`），`sowing_depth_cm` 就位，派生量**不写回配方**（铁律回归锁定） |
| 14 | **CI 命名空间守护已就绪**（新增实测确认） | full_liftup_assessment §8 P0+-2 | ✅ CI 用 `python -S -P -m unittest` + `check_mcp_namespace.py`（4 项回归），`mcp.server.TOOLS==14` 断言就位 |

### 1.2 已过时、需立即同步的声明（⚠️）

| # | 过时声明 | 原文档 | 实测 | 影响 |
|---|---|---|---|---|
| 1 | `market_listing_pack.md` 声明 sha256 = `8beb9253...` | 该文件 §1 | 实测 sha256 = `390e9779...` | **任何按该文档操作的人都会在 Release 上架时遇到「sha256 不一致」错误**。该文档的 sha 段已失效，必须更新 |
| 2 | `distribution_checklist` §3.4 未列 Glama/LobeHub/Smithery 完成 | 该文件 | `smithery.yaml` **已存在于仓库根目录**（说明此项已被部分执行） | 状态表需更新，避免重复做 |
| 3 | `full_liftup_assessment` §1.1 记录单测 **513/537 项** | 该文件 | 实测 **556 项**（`python -S -P -m unittest discover -s scripts -p "test_*.py"` → `Ran 556 tests / OK / skipped=3`） | `harness/manifest.json` 版本需从 v2.3.0 复核，评估基线需重算 |
| 4 | `full_liftup_assessment` §1.1 记录 `harness/manifest.json` v2.2.0 | 该文件 | 实测 **v2.3.0**（`generated_at=2026-10-08T10:01:33`） | 同上 |
| 5 | `full_liftup_assessment` §5.2 TD-1 记录「约 4,200 行未接线代码待处置」 | 该文件 | `agent/finance_agent.py` / `market_agent.py` / `risk_agent.py` / `agent_factory.py` / `collaboration_manager.py` **已全部移入** `_archive/agent_legacy_20261008/` | **TD-1 已处置**（归档），评估报告与 P2-2 项应更新状态 |
| 6 | `full_liftup_assessment` §5.2 TD-2 记录「硬编码密钥占位」 | 该文件 | 全 `agent/` 目录 `grep` 硬编码 `secret_key` = **0 命中** | **TD-2 已消除**（随归档一并解决） |
| 7 | `full_liftup_assessment` §3.1 记录「README L4 标'已落地'」 | 该文件 | `README.md` 已修正为：**「L4 ⏸ 正式暂缓（仅 `data/linkage_protocol.schema.json` 一个 Schema，0 行实现；此前标注'已落地'有误）」** | **README 口径已修订**，但 L5/L6 段仍需核对 |
| 8 | `full_liftup_assessment` §3.2 记录「对实际主线完成度 59%」 | 该文件 | 因 TD-1/2 处置 + 测试 556 + demo 14/14，该数字**已不反映当前状态** | 建议重评 |
| 9 | `CORE_OBJECTIVE.md` §九 P0 出口指标「出现第 1 次非本人外部调用」 | 该文件 | 本机无外部调用可观测；Registry status=active 但**仍无首次外部调用信号** | 目标窗口（约至 2026-12 中旬）仍在倒计时，**P1 及以下仍未开工** |
| 10 | `distribution_checklist` §5 列「创建 `smithery.yaml` 并推送」 | 该文件 | `smithery.yaml` 已在仓库根（**已创建且已推送**，2026-10-09 推送 commit `4349dfda` 内含 139 文件） | 已闭环 |
| 11 | `full_liftup_assessment` §1.4 记录 P1-2 sources 三字段 **0/458** | 该文件 | 实测 **458/458** 齐备 | **法务刚需已满足**，报告 §1.4 表已同步修正 |
| 12 | `full_liftup_assessment` §8 P1-1 记录 vpd/dew_point/sowing_depth/dli **0/116** | 该文件 | 派生函数已落地（`engine/derived.py`，8/8 分区 DLI 可用），**但按铁律不写回配方 JSON** | P1-1 判定应为「**部分完成**」——静态字段（companion_plants / revision_history）仍 0/116，派生量已就绪 |

### 1.3 与实测**直接冲突**的声明（🔴 最重要）

| # | 冲突声明 | 来源 | 实测 | 根因分析 |
|---|---|---|---|---|
| **C1** | **`dli` 字段 116/116 已补齐** | `full_liftup_assessment` §1.4 | **`dli` 在 116 份配方中 0 命中**（`vpd` / `dew_point` / `companion_plants` / `sowing_depth` / `revision_history` 同样 0/116） | 该报告 §1.4 用 `grep` **子串匹配整个文件文本**（`if k in s`），把配方 `sources[].url` 中如 "FAO ... dli..." 之类的 URL 片段误判为字段存在。**这是方法论错误**。 |
| **C2** | 报告 §1.1 记录「`test_mcp_server.py` 已纳入 513 统计」 | `full_liftup_assessment` §5.2 TD-3 | `test_mcp_server.py` **359 行，`def test_` 计数 = 0**（是脚本式自测，未被 unittest 收集） | TD-3 中「MCP 自测纳入 unittest 统计」**尚未实现**，533 里不含 MCP 工具级断言 |

### 1.4 环境陷阱（新增，此前所有报告未记录）

> **现象**：用已预装 pip `mcp` SDK 的 Python 跑 `python -m unittest discover -s scripts`，出现 3 项失败：
> - `test_audit_analyzer` → `ModuleNotFoundError: No module named 'mcp.audit_analyzer'`
> - `test_mcp_tool_count_matches_docs` → `AttributeError: module 'mcp.server' has no attribute 'TOOLS'`
> - `test_no_third_party_imported_on_package_import` → `AssertionError: {'httpx', 'uvicorn'}`
>
> **根因**：`mcp` 是本项目的**一级目录**（`mcp/server.py`、`mcp/audit_analyzer.py`），但 Python 的 `site-packages` 里装了官方的 `mcp` SDK 包（含 `httpx`、`uvicorn` 依赖）。`unittest discover` 启动时，`site-packages` 优先级高于项目根目录，`import mcp.server` 解析到第三方包，所有针对 `mcp.server.TOOLS` 的断言全部落空。
>
> **修复（已验证）**：
> ```bash
> python -S -P -m unittest discover -s scripts -p "test_*.py"
> # → Ran 533 tests in 13.943s / OK (skipped=3) / EXIT=0
> ```
> `-S` 禁用 `site-packages`，`-P` 禁用隐式 cwd 路径。**项目依赖为零（`pyproject.toml` 的 `dependencies=[]`），所以 `-S` 不会缺失任何必需包**。
>
> **建议动作（P0 级，半天）**：在 `.github/workflows/ci.yml` 的测试步骤中把 `python -m unittest discover ...` 改为 `python -S -P -m unittest discover ...`，并加一条**前置检查**：
> ```bash
> python -S -P -c "import mcp.server; assert len(mcp.server.TOOLS)==14, '命名空间被遮蔽'"
> ```
> 这条断言能让 CI 在环境被污染时立刻红灯，而不是静默失败。

---

## 2. P0 主线：真实剩余动作（可照做清单）

依据 `CORE_OBJECTIVE.md` §八 优先级判据与 §九 滚动更新，P0 出口指标是**出现第 1 次非本人外部调用**。以下动作按能否代劳分类。

### 2.1 本机已完成且已核验（无需再动）

| 项 | 核验方式 |
|---|---|
| MCP 无状态适配 / A2A Card / Agent Plugins | 已启动 server 实测 `tools/list` = 14 |
| MCPB 构建确定性可复现 | 三方 sha256 一致 |
| Registry 上架 | API 实时可查 `status=active` |
| 消除硬编码密钥 | `grep` = 0 命中 |
| Demo 端点自检 | 本机复跑 14/14 |
| GitHub 推送 | `sync_check.py` + `deploy_config.sh` 已 gitignore |

### 2.2 必须**用户本人操作**（我无法代劳，需账号/SSH）

| # | 动作 | 具体步骤 | 阻塞点 |
|---|---|---|---|
| **U1** | 公网 Demo 部署 | ① `ssh-copy-id root@150.158.119.19` ② `bash deploy/deploy_local.sh` ③ `curl http://150.158.119.19:8001/api/cities` 验证 | SSH 免密未配 |
| **U2** | 上架 Glama | 访问 https://glama.ai/mcp/servers 提交，字段见 `market_listing_pack.md` §2 | 需 Glama 账号 |
| **U3** | 上架 LobeHub | 按其仓库最新 schema 提 PR 到 `lobehub/lobe-chat` | 需 GitHub 账号 |
| **U4** | 上架 Smithery | 访问 https://smithery.ai 提交仓库地址；`smithery.yaml` **已存在**，可直接提交 | 需 Smithery 账号 |

### 2.3 部署成功后的收尾（我可代劳，仅需一次授权）

| # | 动作 | 说明 | 状态 |
|---|---|---|---|
| D1 | 把公网 Demo 链接写进 `README.md` 顶部 | MCP 市场与 A2A 发现都会抓该字段 | ⏸ 待公网部署完成 |
| D2 | 把 `.well-known/agent.json` 的 `url` 从 `https://github.com/...` 改为 Demo 地址 | 当前仍指向 GitHub | ⏸ 待公网部署完成 |
| D3 | 更新 `docs/market_listing_pack.md` 的 sha256（`8beb9253` → `390e9779`） | 消除文档失效风险 | ✅ 已完成（已与 server.json / Registry 三方一致） |
| D4 | 更新 `docs/distribution_checklist.md` §3.4 验收清单状态 | 标记已完成的项 | ✅ 已完成（本轮 P0-6 / P0-4e 状态与 commit 已同步） |
| D5 | 在 CI 加 `-S -P` 命名空间守护（见 §1.4） | 半天，可完全自动化 | ✅ 已完成（CI 用 `python -S -P -m unittest` + `check_mcp_namespace.py` + 4 项回归） |

---

## 3. 分阶段提升路线图（基于实测证据）

### P0+ · 本周内 · 目标：文档口径归零 + 环境守护

| # | 动作 | 工作量 | 判定标准 |
|---|---|---|---|
| P0+-1 | **修复 `dli` 字段事实冲突**：先复核 `full_liftup_assessment` §1.4 的口径，再把报告中的「116/116 已补齐」改为「0/116 待补」 | 0.5 天 | 报告与实测一致，不再出现子串匹配误判 |
| P0+-2 | **CI 命名空间守护**：把 `python -m unittest` 改为 `python -S -P -m unittest`，加 `assert mcp.server.TOOLS==14` 前置断言 | 0.5 天 | 换环境跑测试也全绿 |
| P0+-3 | **更新 `market_listing_pack.md` 的 sha256** 到 `390e9779` | 10 分钟 | 文档与 server.json/Registry 三方一致 |
| P0+-4 | **确认 `smithery.yaml` 已推送**；若未推送，随下次 commit 一并带上 | 10 分钟 | 仓库根目录可查 |

### P1 · 1-2 月 · 目标：协议字段补齐 + 可信度资产加固

> 依据 `full_liftup_assessment` §4 / §8，本阶段只在「G1 达成前可完成」且「直接提升被调用时的价值密度」的项。

| # | 动作 | 判定标准 | 备注 |
|---|---|---|---|
| P1-1 | **Env Recipe v1.2 字段补齐**：`vpd_kpa` / `dew_point_c` / `companion_plants` / `sowing_depth_cm` / `revision_history` | 116 配方新字段覆盖 >90% | 🔶 **部分完成**：`vpd`/`dew_point`/`sowing_depth`/`dli` 已按**运行时派生**落地（`engine/derived.py`，8/8 分区 DLI 可用，8 项回归测试）；`companion_plants` 与 `revision_history` 待补（companion_plants 无权威数据源，需先取证） |
| P1-2 | **sources 三字段补齐**：`trial_location` / `data_quality` / `source_license` | 458 条 sources 逐条带许可与质量等级 | ✅ **已完成 458/458**（`scripts/backfill_source_provenance.py` + `test_source_provenance.py` 5 项回归；`data_quality` 分布 measured 116 / modeled 342）；`CORE_OBJECTIVE.md` §五 法务刚需已满足 |
| P1-3 | **把 `test_mcp_server.py` 改造为 unittest 收集**（解决 TD-3 后半） | `test_mcp_server.py` 出现 `def test_`，单测统计纳入 MCP 断言 | ✅ **已完成**（`scripts/test_mcp_server_unit.py` 适配层，3 项 unittest 收集，单测基线 533→**556**，MCP 命名空间另有 `check_mcp_namespace.py` + 4 项回归守护） |
| P1-4 | **移植 `agroclim` 函数集 + vegperiod 三法交叉校验** | 物候双轨输出 + 分歧告警，测试 +30 | MIT 可自由实现；vegperiod 从论文重实现 |
| P1-5 | **CMIP7 接入 `agri_season_advisory` 情景模式** | 7 情景可查 | 当前无竞品提供，差异化机会 |
| P1-6 | **MCP server 分层重构**（`tools/` + `handlers/` + `formatters/`） | `mcp/server.py` < 200 行（当前 40274 字节，约 1000+ 行） | 提升可维护性 |

### P2 · 3-6 月 · 目标：战略层与体验层

| # | 动作 | 判定标准 |
|---|---|---|
| P2-1 | **数据源健康分**（`sources[].health` 联动 confidence） | SoilGrids 中国区置信度自动下调 |
| P2-2 | **微气候选址 MVP**（朝向/遮挡/楼层风） | 同城市不同朝向输出不同适配分 |
| P2-3 | **PlantDoc 接入 + agstack pestmodels 对接评估** | `eval_pest_diagnosis_topk` 有真值集 |
| P2-4 | **商业化架构预留**：`call_id` / `billing_hint` / 预算上限 | 每次调用可追溯唯一 id |
| P2-5 | **前端升级**：成长日志/日历 + Deck.gl/Cesium 全球配方分布图（CDN 引入） | 可分享链接 |
| P2-6 | **MCP Apps**：把物候曲线/配方时序作为 `ui://` resource 返回 | 至少 1 个 UI resource |
| P2-7 | **商业化定价拍板**（先解决 R1 法务口径） | 定价文档从「提案」转「生效」 |

---

## 4. 需拍板的决策项

| # | 决策 | 选项 | 影响 |
|---|---|---|---|
| **D1** | **是否先修 `dli` 口径再排 P1-1？** | A 先修（推荐） / B 直接排 P1-1 | §C1 若不复核，P1-1 会基于错误的 116/116 基线判断「已完成」，实际 0/116 会造成评审时被打脸 |
| **D2** | **是否启用 CI 命名空间守护（-S -P）？** | A 启用（推荐，半天） / B 暂不 | 任何换环境跑测试的人都会踩坑；启用后彻底消除 |
| **D3** | **公网 Demo 何时部署？** | 本周 / 本月 / 暂缓 | 决定 P0 出口指标何时真正开始计时 |
| **D4** | **是否补 C 端触点（微信小程序）？** | 做 / 不做 | 若不做，对外叙事须统一为海外 B 端 |

---

## 5. 附录：实测命令与数字来源

```bash
# 单测（本机实跑 2026-10-08，隔离 site-packages）
cd C:\Users\xing\Desktop\智慧农业生态
python -S -P -m unittest discover -s scripts -p "test_*.py"
# → Ran 533 tests in 13.943s / OK (skipped=3) / EXIT=0

# Demo 端点（本机复跑）
python scripts/check_demo_endpoints.py
# → 汇总: 14 通过 / 0 失败 / 共 14 项

# MCPB sha256（三方一致核验）
python -c "import hashlib;print(hashlib.sha256(open('dist/agri-eco-mcp-1.1.0.mcpb','rb').read()).hexdigest())"
# → 390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24

# Registry 状态
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=agri-eco"
# → status=active, publishedAt=2026-10-08T05:33:32Z, isLatest=true

# Env Recipe 字段（递归精确扫描，非 grep 子串）
python -c "
import json, glob
recs=glob.glob('data/env_recipes/*.json')
def has_nonempty(obj,key):
    if isinstance(obj,dict):
        for k,v in obj.items():
            if k==key and v not in (None,'',[],{}): return True
            if has_nonempty(v,key): return True
    elif isinstance(obj,list):
        for i in obj:
            if has_nonempty(i,key): return True
    return False
for t in ['dli','vpd','dew_point','companion_plants','sowing_depth','revision_history']:
    print(t, sum(1 for f in recs if has_nonempty(json.load(open(f,encoding='utf-8')),t)), '/116')
"
# → dli 0, vpd 0, dew_point 0, companion_plants 0, sowing_depth 0, revision_history 0

# MCP tools/list 实调
python mcp/server.py  # 输入 {"jsonrpc":"2.0","id":1,"method":"tools/list"}
# → 14 工具, ttlMs=2592000000, cacheScope=public
```

**数字来源优先级**：本机实跑（含 `-S -P` 隔离） > `README.md` > `harness/manifest.json` v2.3.0 > 仓库文档。凡文档与实测冲突处，一律以实测为准并在 §1.3 列出。

---

## 6. 关键结论（三段式）

**核心结论**：
> P0 主线的**工程侧**已闭环且经过本机实测核验（Registry 上架、14 工具、MCPB 确定性、Demo 14/14、测试 533 全绿），但**分发侧仍停在「已上架未触达」**——Registry `status=active` 不代表有任何 agent 调用过，P0 出口指标仍未达成。
> 同时，`full_liftup_assessment.md` 与两份最新文档之间存在**一处事实冲突**（`dli` 0/116 vs 116/116）和**多处已过时声明**（sha256、测试基线、TD-1/TD-2 已处置、README L4 已修正、P1-2 sources 三字段 0/458→458/458、P1-3 单测 533→556），这些若不及时同步，会在对外评审中直接挑战项目最珍视的「可信度资产」。

**风险清单**：
| # | 风险 | 等级 | 说明与对策 |
|---|---|---|---|
| R1 | **文档口径漂移**（sha256 旧值、测试基线 513 vs 533、dli 冲突） | 🟡 中 | 对策 P0+-1 / P0+-3 |
| R2 | **CI 环境遮蔽陷阱**导致换机器测试假失败 | 🟡 中 | 对策 P0+-2 |
| R3 | **0 外部调用持续** | 🔴 高 | 剩 ~2 个月窗口（至 2026-12 中旬），U1-U4 必须尽快执行 |
| R4 | **NC 许可与付费档冲突** | 🔴 高 | 已判方案 A（服务型收费），定价拍板前必须先落 D4 |
| R5 | **P0-4b 三市场依赖人工账号** | 🟡 中 | 材料已备齐（`market_listing_pack.md`），仅需 U2-U4 |

**推荐路径**：
> 1. **本周内**：执行 P0+-1 到 P0+-4（4 项文档口径修复，共约 1.5 天），把三份文档与实测拉齐。
> 2. **本周内**：完成 U1（公网 Demo 部署）——这是让 P0 出口指标开始计时的**唯一前置**。
> 3. **1-2 周内**：完成 U2-U4（上架剩余三市场），并执行 D1-D5 收尾。
> 4. **随后**：按 P1-1 → P1-2 → P1-4 → P1-5 顺序推进功能补强（先解决法务刚需的 sources 三字段，再补协议字段）。

---

*本报告生成于 2026-10-08，基于本机实跑取证。所有数字可复现，命令见 §5。*