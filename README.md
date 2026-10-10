# 智慧农业生态 · 全球分区农业 AI 助手

> 以数据平台分析为基座，孵化多层级农业 AI 关键节点生态

> 🎯 **项目目标口径（单一权威）**：见 [`docs/CORE_OBJECTIVE.md`](docs/CORE_OBJECTIVE.md) —— 分布式农业的 **Agent-native 知识基座**。
> 一句话：把「在哪里种什么、怎么种得好」做成**可被任何 AI Agent 直接调用**的可执行配置（Env Recipe），以**可审计的数据血缘**作为可信度资产。
> **一级目标**：让 MCP server 被外部 agent 真实调用（≥500 次 / ≥20 独立调用方）。
> 阶段门禁数字见 [`docs/north_star_and_phase_gates.md`](docs/north_star_and_phase_gates.md)；全面扫描与提升报告见 [`docs/full_liftup_assessment_2026-10-08.md`](docs/full_liftup_assessment_2026-10-08.md)。

**🚀 已上架官方 MCP Registry**：`io.github.lm203688/agri-eco` v1.1.0（2026-10-08）

```bash
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.lm203688/agri-eco"
```

**🔎 市场入口（4 家，其中官方 Registry + Smithery 已就绪）**：

- 官方 MCP Registry：`io.github.lm203688/agri-eco` v1.1.0 ✅
- Smithery：`smithery.yaml` 已就绪，仓库自动发现（[搜索入口](https://smithery.ai/search?q=agri-eco)）✅
- Glama：[提交表单](https://glama.ai/mcp/servers)（待你提交，材料见 `docs/market_listing_pack.md` §2）
- LobeHub：[站内提交](https://lobehub.com/mcp)（待你提交，材料见 `docs/market_listing_pack.md` §3）

**📋 分发就绪度自检**（每次评审/发布前跑一次）：

```bash
python scripts/check_distribution_readiness.py
```

一次性验证 10 类分发入口：MCP server / A2A Card / Agent Plugin / Smithery / 官方 Registry /
MCPB 包 / CI workflow / Demo 部署 / 市场材料 / GitHub 同步。

CI：22 步 × Python 3.10/3.11/3.12 全绿 · 单测 556 OK · Demo 端点 14/14 · MCPB 构建确定性可复现 · GitHub 本地=远端（353 文件差异 0）。

---

## 项目定位

**一句话**：做分布式农业的 AI 操作系统与数据网络——回答「在哪里种什么、怎么种得好、怎么送到消费者」。

**核心架构（对标 SwarmLabs 科研 Agent Infra 的工程路径）**：

```
输入（地块信息 / 种植者需求 / 环境参数）
  │
  ▼
┌──────────────────────────────────────────────────────────┐
│  L0  数据底座层   全球分区气候/土壤/水文元数据               │
│    └─ data/zone_meta/ (Köppen 气候带 + FAO 农业分区)      │
├──────────────────────────────────────────────────────────┤
│  L1  多 Agent 协同层（含 L2/L3 专项 Agent）               │
│    ├─ ClimateAgent  气候/水文/土壤分区匹配                  │
│    ├─ CropAgent     作物-分区适配推荐                       │
│    ├─ GrowthAgent   生长周期管理 + 病虫害诊断               │
│    ├─ EcoAgent      多层级生态撮合（供需/社区/设备）        │
│    ├─ PestAgent / NutritionAgent / SeasonAgent 按需调用    │
│    ├─ ForecastAgent(L2) 采收期 / 产量 / 风险预测           │
│    └─ ControlAgent(L3)  生长计划→执行指令 + 执行补偿        │
├──────────────────────────────────────────────────────────┤
│  L2  Skill 注册表   可复用能力模块                         │
│    └─ skills/registry/ (climate_match / crop_adapt / ...) │
├──────────────────────────────────────────────────────────┤
│  L3  可信输出层  evidence + confidence + constraints        │
│    └─ docs/agent_output_contract.md                       │
└──────────────────────────────────────────────────────────┘
```

---

---

> **覆盖边界（已闭环）**：分区库现建模 **8 个气候带**（含 v1.1 新增的**热漠 hot_arid** 与**高原 highland**）。
> 迪拜（波斯湾热漠）→ `hot_arid`、拉萨（青藏高原）→ `highland` 现由 ClimateAgent 正确路由（rubric 0.95、给出真实作物推荐），
> 不再静默归入「亚热带湿润」给出错误方案；v1.1 之前的「显式拒答」降级路径已随分区补齐而关闭。
> 两新分区的 Env Recipe 与 P3 校准作物已于 2026-10-06 回填，详见 `outputs/zone_coverage_decision_2026-09-23.md`（历史背景）。
>
> **两个诚实性约定（2026-09-23 起生效，均有测试锁死）**：
> 1. `monthly_precip_mm` 虽是月度序列，但**每个元素是月内日均降水（mm/day），不是月累计量**。
>    NASA POWER 与 Open-Meteo 两条路径口径一致，`agent/climate_data.py` 统一以 `PRECIP_UNITS` 声明并透传
>    `monthly_precip_mm_units`。生态位校准的降水通道依赖「同口径区间命中」，**不得**对该字段乘天数换算。
> 2. 预设城市清单的**唯一数据源**是 `data/preset_cities.json`，前端与 MCP Server 均经
>    `agent/preset_cities.py` 读取；拉萨/迪拜随 v1.1 已建模（`modeled: true`），12 城全部有对应分区。

## 七层生态架构（来自项目战略指引）

> ⚠️ **口径已修订（2026-10-08）**：七层是**分析框架**，不是交付清单。当前阶段只交付 **L0-L3**；**L4/L5/L6 已正式暂缓**（判定依据与重新打开条件见 [`docs/CORE_OBJECTIVE.md`](docs/CORE_OBJECTIVE.md) §三 N6/N7、§六）。
> 下表"本项目状态"列已按**实测**校正，此前"已落地/进行中"的表述存在与代码不符之处，此处一并修正。

| 层级 | 名称 | 关键节点 | 本项目状态（实测校正） |
|------|------|---------|-----------|
| L6 | 运营生态 | 社区/城市合伙人/数据市场 | ⏸ **正式暂缓**（无实现） |
| L5 | 消费服务 | 采摘即食/本地撮合/认证溯源 | ⏸ **正式暂缓**（仅溯源字段留位，无服务实现） |
| L4 | 业务支撑 | 链路数据/鲜度中枢/损耗预测 | ⏸ **正式暂缓**（**仅 `data/linkage_protocol.schema.json` 一个 Schema，0 行实现**；此前标注"已落地"有误） |
| L3 | 执行控制 | 水肥一体化/环境调控/执行补偿 | ✅ 已落地（NutritionAgent 水肥 + **ControlAgent** L3：生长计划→硬件无关 actuator 指令 + 车载/开放环境/设备故障执行补偿）。**缺口**：`execution_log` 0 条，闭环未真实验证；`needs_gateway` 网关未实现 |
| L2 | 模型 AI | 生长模型/病虫害/决策引擎/世界模型 | 🟡 部分落地（**ForecastAgent** L2：采收期/产量/风险预测，诚实标注 `model=heuristic` + WOFOST 物候 + 病虫害规则诊断）。**缺口**：世界模型未做；`eval_pest_diagnosis_topk` / `eval_recipe_expert_adoption` 两项核心 eval pending |
| L1 | 感知层 | 传感器/摄像头/边缘AI | 🟡 最弱环节（`agent/vision.py` **63 行**可插拔后端，未配置即规则降级）。**注意**：PlantVillage **无 license**（原仓库无 LICENSE 文件），不可商用；合规替代为 PlantDoc (CC BY 4.0)。传感接入协议 0 行代码 |
| L0 | 数据底座 | 气候/土壤/水文/光照 | ★ 当前重点（8 分区已闭环 / 152 配方 / 113 双源校准 / 8 源血缘）。**缺口**：微气候选址未做；CMIP7 未接入；第三源未融合 |

---

## 核心模块

| 模块 | 路径 | 用途 |
|------|------|------|
| 多 Agent 协同框架 | `agent/` | 气候/作物/生长/生态四 Agent + 病虫害(PestAgent) + 养分(NutritionAgent) 按需调用 |
| 统一编排器 | `agent/orchestrator.py` | 四 Agent 流水线（run_pipeline）+ call_skill 按需技能路由 + 技能目录（list_skills） |
| 农业分区数据 | `data/zone_meta/` | 全球农业分区元数据 |
| Skill 注册表 | `skills/registry/` | 可复用农业 AI 能力 |
| 可信输出契约 | `docs/agent_output_contract.md` | 每条建议的证据/置信度/适用条件 |
| 项目评估 | `docs/project_evaluation.md` | 评审维度逐项自评 |
| 战略指引 | `docs/planning/项目战略指引.md` | 七层架构与商业设计 |
| 执行方案 | `docs/planning/项目执行方案.md` | 分阶段路线图 |
| 规划/战略/GOAI 合集 | `docs/planning/` | 10 份早期规划、战略与 GOAI 竞品分析（已归档归类，便于溯源） |
| 开源生态对接 | `docs/OPEN_SOURCE_INTEGRATION.md` | 七层架构生态位补全映射（扫描→对接）+ 用户分步操作指引（启用 cropgraph MCP / 配置视觉后端 / 提供 PAT 推送） |
| 反馈闭环引擎 | `engine/flywheel.py` | 种植结果回流 → 适配评分校准（主动学习） |
| 交互式 Demo | `app/` | 零依赖 http.server 站点：坐标 → 四 Agent 方案 + AgriTrust 证书 |
| 数据扩展脚本 | `scripts/enrich_crop_data.py` | 每气候带补充适生作物至 ≥18 种 |
| 端到端验证 | `scripts/verify_all.py` | 多城市 pipeline + Trust 证书 PASS/FAIL |
| Skill 自动生成 | `engine/skill_factory.py` | 新作物/能力点 → 自动生成符合 Schema 的 Skill |
| 单元测试 | `scripts/test_agents.py` | **66 项** unittest（零依赖），覆盖四 Agent + PestAgent + NutritionAgent + SeasonAgent + SoilProfile + ForecastAgent(L2) + ControlAgent(L3) + Orchestrator 统一路由 + 视觉后端降级 + Trust + flywheel + **作物库数据完整性守卫** |
| MCP server（Agent-native 分发） | `mcp/` | 零依赖 JSON-RPC over stdio，暴露 **14 个** agri 工具（分区匹配/作物推荐/种植计划/病虫害诊断/养分管理/Env Recipe 配方/物候播期/土壤剖面/BP 投资初筛/多源气候调和/地理编码→配方/数据血缘查询/预设城市/生态对接清单）；协议版本 **2026-07-28（无状态）**，兼容 2025-06-18 / 2024-11-05；已适配 SEP-2575（免握手）/ SEP-2567（无 session）/ SEP-2243（`Mcp-Method`）/ SEP-2549（`ttlMs` 缓存）/ SEP-414（W3C traceparent）；注册与投递见 `mcp/README.md` |
| A2A Agent Card | `.well-known/agent.json` | A2A v1.0 标准发现入口：声明 14 个 skill（与 MCP 工具一一对应）、`securitySchemes={}`、输入输出模式与许可红线（NC 来源不得转售）；校验 `scripts/check_agent_card.py` |
| Agent Plugins 打包 | `plugin/` | Agent Plugins 1.0.0 标准：`plugin.json` + `mcp.json` + `skills/<id>/SKILL.md` × 11（含 Anthropic Agent Skills YAML frontmatter）；**由注册表生成，禁止手改**，`scripts/build_agent_plugin.py` 为唯一入口，CI 用 `--check` 防漂移 |
| Env Recipe 协议 | `schemas/env_recipe.schema.json` + `docs/env_recipe_protocol_v1.md` | 配置协议 v1：作物×阶段×箱体 → 可执行环境参数；day-1 留位 `execution_log`/`outcome`/`image_consent` 独占数据字段；校验 `scripts/validate_env_recipe.py` |
| AI 评测基线 | `engine/eval.py` + `scripts/run_eval.py` | P0-H：分区分类一致率（真实基线）+ 4 个脚手架项（绝不谎报）；评测集 `data/eval/zone_checks.json` |
| 预览残留清理 | `scripts/clean_preview_artifacts.py` | 清除预览工具注入 HTML 的 `data-page-node-id` 属性（曾一次性注入 115 处） |
| 演示数据重置 | `scripts/clean_demo_data.py` | 清空 demo/单测污染的 feedback_log + 剥离作物库假校准标记 |
| Demo 端点冒烟 | `scripts/check_demo_endpoints.py` | 零依赖端到端自检：自动选空闲端口拉起 `app/demo_server.py`，打 **14 个端点**（8 GET + 6 POST），校验状态码 / 体积下限 / 响应契约键，部署前先在本机消除哑端点风险；已入 CI |
| 同步状态检查 | `scripts/sync_check.py` | 本地工作区 vs GitHub main 逐文件 blob sha 比对（本仓非 git clone，无法用 git status） |
| 反馈回流 CLI | `scripts/submit_feedback.py` | 内测用户提交种植结果 → 校准 adapt_score |
| 物候/播期层 | `agent/phenology.py` + `agent/plant_calendar.py` + `agent/season_agent.py` | WOFOST 积温物候（7 作物，EUPL 1.2 署名）+ 霜冻锚定播期窗口；技能 `season_advisory` |
| L3 执行控制 Agent | `agent/control_agent.py` | 生长计划 → 硬件无关 actuator intents（灌溉/施肥/补光/气候/CO₂/风机）+ `needs_gateway` 网关标记 + 车载颠簸/开放环境/设备故障执行补偿；技能 `control_commands` |
| L2 预测 Agent | `agent/forecast_agent.py` | 采收期（GDD-lite 积温）/ 产量（基准×气候×适配×光照）/ 风险（霜冻/高温/计划）预测，诚实标注 `model=heuristic`、未知作物安全回退；技能 `harvest_forecast` |
| L4 链路数据协议 | `data/linkage_protocol.schema.json` | 开源标准链路数据（batch→product→7 环节三元组 + 鲜度/损耗/货架期模型），支撑 L5 认证溯源 |
| 土壤剖面（降级源） | `agent/soil_profile.py` | 在线 SoilGrids 优先 → 离线分区均值降级；`resolution=zone` / `confidence=low`，不虚构指标 |
| 文档死链扫描 | `scripts/check_doc_links.py` | 全量 md 外链四态判定（ALIVE / DEAD_CONFIRMED / UNREACHABLE / UNPROBEABLE） |
| 回流通路自检 | `scripts/check_feedback_loop.py` | 用 `AGRI_FEEDBACK_LOG` 隔离，13 项验证 record → calibrate → report 全链路，零污染真实数据 |
| 巡检报告 diff | `scripts/diff_daily_loop.py` | 报告跨日 diff（`--selftest` 守护解析器） |
| 生产部署 | `deploy/` | 一键部署（`deploy_local.sh` 上传 + `setup_ecs.sh` 远端构建启动）+ nginx 反代 + DEPLOY.md |
| CI | `.github/workflows/ci.yml` | push 自动跑单测/verify/trust/flywheel/数据自检，Python 3.10-3.12 矩阵 |

---

## 工程路径（对标 SwarmLabs）

| SwarmLabs 做法 | 农业项目映射 |
|----------------|------------|
| `traceability.py`（可追溯层） | 每条种植建议的溯源链（数据来源+分区依据+作物研究） |
| `trust_layer.py`（可复现证书） | 农业建议的可信度评分（rubric + 数据覆盖度） |
| `skills/registry/`（机读注册表） | 农业 Skill 的 JSON Schema 注册表 |
| `docs/agent_output_contract.md` | 农业可信输出契约 |
| `engine/flywheel.py`（飞轮主循环） | ✅ 已落地：record_feedback() 校准 adapt_score，闭环生效 |

---

## 快速验证

> 工程化入口见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)；常用命令可用 `make`（如 `make gate` = 单测+端到端+数据质量三件套）。

```bash
# 查看农业分区数据
python -c "import json; d=json.load(open('data/zone_meta/global_zones.json')); print(len(d))"

# 查看 Skill 注册表
for f in skills/registry/*.json; do python -c "import json; s=json.load(open('$f')); print(s['id'])"; done
```

---

## v2.1 提升项落地（Agent-native 分发 + 配置协议 + 评测）

> 依据 `docs/planning/项目方案评审-商业模式与AI专业分析.md`：商业主线重排为「免费资产 → 免费入口换数据 → 产业端收钱」；
> 模块⑤生成箱降级为「配方大脑授权硬件厂/存量设备」；Env Recipe 协议与 MCP 分发为近期最高优先。

| 提升项 | 交付物 | 验证 |
|---|---|---|
| P0-G Env Recipe v1 协议 | `schemas/env_recipe.schema.json`（schema v1.1.0）+ `docs/env_recipe_protocol_v1.md` + `data/examples/sample_env_recipe.json` | `python scripts/validate_env_recipe.py data/env_recipes` |
| P0-E/F 零依赖 MCP server | `mcp/server.py`（14 工具）+ `mcp/README.md`（含外部投递模板，对标 aishield 上架 Glama/npm） | `python scripts/test_mcp_server.py` |
| P0-H 评测基线 | `engine/eval.py` + `scripts/run_eval.py` + `data/eval/zone_checks.json` | `python scripts/run_eval.py` |

**决策门**（评审 §3.5）：P0-F/G 若 3 个月内零外部调用 / 零社区响应 → 降级为个人知识库项目，停止对外投入。

---

## v2.2 提升项落地（分发协议适配，2026-10-08）

> 依据 `docs/full_liftup_assessment_2026-10-08.md` §8 P0 路线图；判定铁律——**凡是能产生第一次真实外部调用的动作，优先级高于一切新增功能**。
> 权威目标口径见 `docs/CORE_OBJECTIVE.md`（本项目唯一战略来源）。

| 提升项 | 交付物 | 验证 |
|---|---|---|
| P0-1 MCP 2026-07-28 无状态适配 | `mcp/server.py`：免 initialize 握手（SEP-2575）、显式 `stateless`（SEP-2567）、`Mcp-Method`/`Mcp-Name` 头校验（SEP-2243，HTTP 形态生效）、`ttlMs`/`cacheScope` 缓存提示（SEP-2549）、W3C `traceparent` 透传与回写（SEP-414） | `python scripts/test_mcp_server.py` |
| P0-2 A2A Agent Card | `.well-known/agent.json`（A2A v1.0）：14 skill 声明 + 输入输出模式 + 许可红线 | `python scripts/check_agent_card.py` |
| P0-3 Agent Plugins 打包 | `plugin/plugin.json` + `plugin/mcp.json` + `plugin/skills/*/SKILL.md` × 11 | `python scripts/build_agent_plugin.py --check` |
| P0-7 消除硬编码密钥 | `agent/finance_agent.py` / `market_agent.py` 的 `secret_key` 占位随模块一并移出主链路 | `grep -rn "secret_key" --include=*.py .` = 0 命中 |

**P0 出口指标：出现第 1 次非本人外部调用。**

---

## 数据卫生（重要）

`engine/flywheel.py` 的 `record_feedback()` **真的会写盘**——这是为了让反馈闭环真实生效。
代价是：demo 与单测如果不隔离，就会把合成样本混进真实数据。本项目已踩过的两类事故及防护：

| 事故 | 现象 | 防护 |
|---|---|---|
| 单测污染反馈日志 | `data/feedback_log.json` 累积 12 条 `unittest`/`smoke` 样本，制造「已有真实数据回流」的假象 | 单测把 `AGRI_FEEDBACK_LOG` 重定向到临时文件 |
| 作物库假校准标记 | 34 个作物只有 `calibrated: true` 却**零校准证据**，被可信层当成实测数据透出 | `scripts/clean_demo_data.py` 清洗 + CI/单测双门禁 |

规则：

1. **`data/feedback_log.json` 只允许真实用户反馈**。demo 记录带 `[demo]` 前缀，门禁会拦截未标注的合成数据。
2. **`python -m engine.flywheel` 跑过之后**，提交前必须执行：
   ```bash
   python scripts/clean_demo_data.py --dry-run   # 先看会清多少
   python scripts/clean_demo_data.py             # 实际清理
   ```
3. **隔离运行**（不碰仓库数据）：
   ```bash
   AGRI_CROP_DB=<绝对路径>/crop.json AGRI_FEEDBACK_LOG=<绝对路径>/fb.json python -m engine.flywheel
   ```
   ⚠️ Windows 注意：Git Bash 的 `/tmp` 映射到 `%LOCALAPPDATA%\Temp`，Python 按 `C:\tmp` 解析，
   **必须用 Windows 风格绝对路径**，否则 `AGRI_CROP_DB` 找不到文件会直接报错（故意 fail fast，避免静默输出全 None）。
4. CI 中的 flywheel 步骤已改为写入 `$RUNNER_TEMP` 隔离目录，并加了数据完整性门禁。

---

## 快速启动

### 1. 交互式 Demo 站点（零依赖，仅标准库）
```bash
python app/demo_server.py
# 浏览器打开 http://127.0.0.1:8000
# 选择城市 / 场景 / 预算 → 四 Agent 协同方案 + 可点击 AgriTrust 证书
```

### 2. 端到端验证
```bash
python scripts/verify_all.py          # 五城市 pipeline + Trust 证书，输出 PASS/FAIL
python -m engine.flywheel              # 跑一次反馈闭环示例，校准「生菜」adapt_score
python scripts/enrich_crop_data.py     # 扩展作物数据密度至每带 ≥18 种
```

### 3. Docker 部署
```bash
docker compose up --build                                  # 本地 verify 模式（跑端到端验证即退出）
docker compose -f deploy/docker-compose.prod.yml up -d --build   # 生产 serving 模式（宿主机 :8001 → 容器 :8000）
```

### 3b. 公网部署（一条命令）
```bash
cp deploy/deploy_config.example.sh deploy/deploy_config.sh   # 一次性：按需改 IP/端口
bash deploy/deploy_local.sh                                   # 同步代码 + 远端构建 + 启动 + 验证
# 站点：http://<ECS_IP>:8001   详细流程见 deploy/DEPLOY.md
```

### 3b-2. 视觉诊断后端（可选，接 ATEX 多模态网关）
PestAgent 的视觉诊断走可插拔后端：配置以下环境变量（读 `agent/vision.py`）即启用，未配置则规则降级。
密钥放仓库外的 `.env`（已被 `.gitignore` 忽略，部署时由 `deploy_local.sh` 同步到 ECS，不进 GitHub）：

```bash
# .env（项目根目录，不要提交）
AGRI_VISION_URL=http://host.docker.internal:8420/v1   # ATEX 网关，容器内用 host 网桥访问
AGRI_VISION_KEY=<你的 ATEX 网关 Key>
AGRI_VISION_MODEL=gpt-4o                              # 须为多模态模型
```
`deploy/docker-compose.prod.yml` 已默认读取这三个变量；若 ATEX 仅监听 `127.0.0.1`，可把 `AGRI_VISION_URL` 改为宿主内网 IP。

### 3c. CI（push 自动验证）
```
.github/workflows/ci.yml
```
push 到 main 后自动跑：单测 → verify_all → trust_layer → flywheel（隔离到 $RUNNER_TEMP）→ **数据完整性门禁**（禁假校准标记、禁合成反馈样本）→ Skill 注册表合法性 → 数据自检（每带 ≥18 种作物），Python 3.10/3.11/3.12 矩阵。
状态：GitHub Actions 已验证可用（fine-grained PAT 含 `Workflows:write`，push 后 CI 自动跑通，最近一次 run 结论 success）。

### 3d. 本地 → GitHub 同步（无 git push 环境）

本机 github.com:443 不可达，且本地目录不是 git clone，**不能用 `git push` / `git status`**。
统一走这两个脚本：

```bash
# 1) 查看待推差异（只读，公开仓库可匿名）
python scripts/sync_check.py

# 2) 推送（单 commit，推送后自动回读校验）
python scripts/gh_push.py <token临时文件> "<提交信息>" file1 file2 ...
```

- 需要 fine-grained PAT（Contents: read/write），建议含 `Workflows:write` 以便改 CI
- token 放临时文件、用完即删，不要留在命令行历史里
- 推送后 CI 会自动跑；确认 success 再关掉本地改动

### 4. 单元测试（零依赖）
```bash
python -m unittest scripts.test_agents -v     # 66 项用例全过
```

### 4b. MCP / 协议 / 评测（v2.1 提升项）
```bash
python scripts/test_mcp_server.py                  # MCP server 自测：initialize/tools/list/tools/call
python scripts/validate_env_recipe.py data/examples/sample_env_recipe.json  # Env Recipe v1 Schema 校验
python scripts/run_eval.py                          # AI 评测基线（分区一致率真实数字 + 脚手架项）
```

注册到 Claude Desktop（stdio）：见 `mcp/README.md`。Env Recipe 协议说明与 AeroGarden 孤儿设备接入路径：见 `docs/env_recipe_protocol_v1.md`。

### 5. Skill 自动生成（闭环触发）
```bash
python -m engine.skill_factory            # 演示：新作物冰菜 → 自动 Skill
python -m engine.skill_factory --list     # 列出当前所有 Skill
```

### 6. 提交种植反馈（内测回流 → flywheel 校准）
```bash
python scripts/submit_feedback.py --zone subtropical_wet --crop 生菜 \
  --survival 0.92 --yield 4.5 --rating 5 --issues "梅雨季霜霉病" --note "杭州阳台春播"
# 或直接调用 Demo 站点 POST /api/feedback
```

---

## 自动化定时闭环（每日单口巡检）

本仓的每日治理巡检由专属 Automation 承担：**「智慧农业生态 每日治理校验」**（id `c8668b59-2488-4e21-9962-ab3fa7d69d26`，每日 05:00，ACTIVE）。

> 注：列表里另有一个同名风格、名为「AOCI 每日治理校验」（`1db296e6`）的自动化，实际是 `aoci-code` 工具对 `swarmlabs` / `算力共享平台` 两个**其他仓库**的校验（每日 03:00），并非本仓任务——其命名易混淆但职责不属本项目，此处仅说明、不做改动。

| 闭环 | 频率 | 产出文件 | 作用 |
|------|------|---------|------|
| 智慧农业生态 每日治理校验 | 每日 05:00 | `outputs/daily_loop_<YYYY-MM-DD>.md` | `verify_all` + `data_quality_gate` + 全量单测三件套，非零退出即暴露漂移，**只读巡检** |

执行内容（全部只读，禁改代码 / 禁 git / 禁推送）：

1. **回归十八项（556 项单测 + MCP 自测）**：`test_engine_v4.py`（137 项）、`test_engine_v3.py`（43 项）、`test_engine_v2.py`（59 项）、`test_agents.py`（66 项）、`test_engine_v5.py`（94 项，BP 初筛引擎）、`test_climate_data.py`（19 项）、`test_climate_reconcile.py`（14 项）、`test_data_lineage.py`（25 项）、`test_geo_recipe.py`（7 项）、`test_audit_analyzer.py`（16 项）、`test_jev_gate.py`（15 项）、`test_jev_decision.py`（10 项）、`test_jev_attribution.py`（8 项）、`test_mcp_server.py`（14 工具）、`test_dist_readiness.py`（5 项）、`test_env_derived_v12.py`（8 项）、`test_source_provenance.py`（5 项）、`test_mcp_server_unit.py`（3 项）、`test_mcp_namespace.py`（4 项）、`verify_all.py`（5 城 PLACEHOLDER=0）、`diff_daily_loop.py --selftest`
2. **数据源存活探测**：GAEZ / WorldClim / SoilGrids(`rest.isric.org`) / PlantVillage / EPPO / GitHub 等 7 个外部源 —— 防止引用死数据源（Ecocrop / OpenFarm / @pondlog 三次教训）
3. **回流通路健康检查**：跑 `check_feedback_loop.py`，**区分「通路故障（≠0 报警）」与「数据量缺口（=0 条、不报警）」**（JSON 字段 `snapshot.feedback_path` = ok/broken）
4. **状态快照 + 跨日 diff**：feedback 条数 / recipes 数 / wofost 作物数；与昨日报告对比，零漂移即静默，漂移即暴露

**已知长期缺口**：`data/feedback_log.json` 持续 0 条 = 通路可用但无真实用户回流数据（属产品/增长问题，非代码缺陷——不得以合成数据充数）。

---

## 开源协议

待确定。核心数据标准与协议倾向开源（抢生态话语权），应用层与决策引擎闭源（保利润）。
