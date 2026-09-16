# 开源平台扫描 · 互补与借鉴研发清单

> 编制日期：2026-09-07｜方法：6 路 WebSearch 一手情报采集（MCP 农业 / 病害 YOLO / PCSE-WOFOST / farmOS-OpenFarm / 农业 VLM / Home Assistant AeroGarden），交叉核实 license 与可达性
> 目的：对照「智慧农业生态」五模块（全球数据库 / 分区分类 / 病虫害识别 / 城市环境配方生成箱 / 未来生态节点）+ 四 Agent 闭环（Data→Analysis→Recipe→Eco→Feedback），找出可**直接复用 / 架构借鉴 / 数据补充 / 投递合作**的开源项目，形成落地清单
> 关系：**投递合作类**仅在此给研发/对接动作，具体投递渠道与文案见 `docs/p0f_outreach_targets.md`（避免重复）；本清单是研发全集

---

## 〇、我们的现状（互补性基准）

| 维度 | 现状（强项） | 缺口（最该从开源补的） |
|---|---|---|
| MCP 层 | `mcp/server.py` 零依赖 stdlib JSON-RPC over stdio，9 个 agri 工具，协议 2024-11-05 | 缺**环境实时数据层**（天气/霜冻/土壤）、缺**执行日志回流**机制 |
| 编排 | `orchestrator.py` 四 Agent 串行（climate→crop→growth→eco）+ pest/nutrition 按需技能 | growth_agent **无过程式微观模拟**（只有计划，无产量/物候推演） |
| 病虫害 | `pest_agent.py` 规则驱动 + 可插拔视觉后端（`vision.py`，OpenAI 兼容，未配置即降级 None） | 视觉后端**无本地模型**，依赖外部 API；无中文场景留出集 |
| 配方协议 | `env_recipe_protocol_v1.md` CC-BY-4.0，day-1 留 `execution_log`/`outcome`/`image_consent`；MCP 含 `aerogarden_orphan` 设备类 | 缺**真实执行设备**回填 execution_log（闭环数据 A 尚未产生） |
| 评测 | `engine/eval.py` 已落地 `zone_consistency` + `crop_db_coverage` | `pest_diagnosis_topk` / `extraction_accuracy` / `recipe_expert_adoption` / `source_traceability` 均 `NOT_IMPLEMENTED`（缺 PlantVillage 留出集 + 200 张中文图 + 视觉后端） |
| 数据源 | `crop_adapt_db.json` 已洗为 GAEZ v4 + WorldClim 2.1 + USDA + IPNI + 中国通识 | SoilGrids **API 本网络 502 不可达**（见 `data_sources_verified.md`），在线土壤查询暂不可做 |

---

## 一、借鉴研发总表（按互补性分档）

### A 档 · 直接复用 / 对接（零改造或仅写适配器，立刻产生价值）

| # | 项目 | 来源 / License / 可达性 | 对应模块·闭环 | 可落地方案 | 优先级 |
|---|---|---|---|---|---|
| A1 | **mcp-kasvanta**（drewherron/mcp-kasvanta） | GitHub，MIT，Python | 模块⑤生成箱 · 反馈闭环（数据 A） | 它的 SQLite「植物活动日志」天然对接我们的 `execution_log`/`outcome` 字段。动作：① 把 Env Recipe 的 execution_log schema 设计成可被 kasvanta 活动记录导入的格式；② 提案共建「配方→执行→结果」开放标准。补上闭环数据 A 的唯一燃料 | ★★★ |
| A2 | **homeassistant-aerogarden**（jacobdonenfeld 接续 fork） | GitHub，依赖已死的 AeroGarden 云 API | 模块⑤ · P0-G 孤儿设备 | 它是 P0-G 核心目标：云脑已死、设备尚转。用 `device_class: aerogarden_orphan` + Env Recipe 离线配方大脑替换死云逻辑。投递 issue/PR 文稿已备（见 p0f 文档） | ★★★ |
| A3 | **WENDGOUNDI/crop_diseases_detection**（轻量 3MB 模型） | GitHub，license 待查（轻量 YOLO） | 模块③病虫害 · pest_agent 视觉 | 3MB 模型可本地推理，正好补 `vision.py` 的「无本地模型」缺口。动作：① 评估能否在 ECS/本地跑（注意本机无 NVIDIA，需 CPU/ROCm 友好）；② 作为 vision 后端的可选本地 provider，配置 `AGRI_VISION_URL` 指向自建推理服务 | ★★★ |
| A4 | **farmbot-agent**（kieranklaassen） | GitHub，MIT | 模块⑤生成箱 · 硬件执行 | FarmBot 是开源 CNC 种植硬件，可消费 Env Recipe。动作：写一个**适配器**把 `agri_env_recipe` 的输出（温湿/水肥/光照）映射成 FarmBot sequence/REST API。让模块⑤从「配方大脑」进化到「真能下发执行」 | ★★ |

### B 档 · 架构借鉴（取其设计/数据，不合并代码，保持零依赖）

| # | 项目 | 来源 / License / 可达性 | 对应模块·闭环 | 可落地方案 | 优先级 |
|---|---|---|---|---|---|
| B1 | **PCSE/WOFOST**（ajwdewit/pcse，Wageningen） | GitHub，EUPL 1.2，纯 Python + SQLAlchemy/pandas/numpy | 模块②/④ · growth_agent 微观层 | 我们零依赖哲学与 WOFOST 的重依赖冲突，**不直接依赖**，改为：① 移植其 **22+ 作物 YAML 参数**作为 growth_agent 的微观生长参数参考表（纯数据文件，零依赖）；② 借鉴其「物候/产量过程式推演」思路增强 growth_plan 输出（当前只给计划不给推演）。EUPL 与 CC-BY 兼容，需署名 | ★★ |
| B2 | **@pondlog/mcp-garden**（npm，MIT） | npm/GitHub，MIT，离线 150-crop 日历 + USDA 耐寒区 | 模块② · growth_agent 季节窗 | 我们的 growth_agent 有「计划」但无「霜冻锚定的种植窗口」。动作：移植其 150-crop 日历数据（USDA Cooperative Extension 来源，可署名再分发）为 stdlib 参考表，给每种作物补 `plant_window`/`frost_risk` 字段 | ★★ |
| B3 | **mcp-garden**（avlihachev） | GitHub，MIT，Node + Open-Meteo/SoilGrids | 模块① · MCP 环境数据层 | 它有天气/霜冻/蒸散/土壤，我们没有。动作（保持零依赖）：**只借鉴其 get_frost_risk / get_evapotranspiration 算法逻辑**，用 Python stdlib + Open-Meteo（本网络可达）重写一个 `agri_weather` 对等工具；SoilGrids 部分因 `api.isric.org` 本网络 502 暂跳过（见 data_sources_verified.md） | ★★ |
| B4 | **AgroEvals**（出自 awaisrauf/agroGPT） | WACV 2025，学术 repo | 模块③ · engine/eval.py | 直接补 `eval.py` 的 `eval_pest_diagnosis_topk` 脚手架：借鉴其农业多模态评测协议作为我们病虫害 Top-1/Top-3 基线的参照标准 | ★★ |

### C 档 · 数据 / 模型补充（增强现有能力，需评估许可）

| # | 项目 | 来源 / License / 可达性 | 对应模块·闭环 | 可落地方案 | 优先级 |
|---|---|---|---|---|---|
| C1 | **JK-TK/PlantDiseaseDetection**（YOLOv11x，116 类，mAP50 69.8%） | GitHub，license 待查（训练权重通常 CC-BY-NC/Apache 混合） | 模块③ · pest_agent 视觉 | 116 类覆盖广，可补 `vision.py` 后端。动作：① 确认 license 是否允许商用；② 评估权重体积与本地推理可行性（本机无 NVIDIA，需轻量化/CPU 友好版）；③ 与 C3 的 PlantVillage 留出集联合做 `eval_pest_diagnosis_topk` | ★★ |
| C2 | **PlantVillage**（mohanty/PlantVillage，HuggingFace） | 54,306 图 / 14 作物 / 26 病害，README **无明确 license**（仅要求引用 Mohanty 2016） | 模块③ · 视觉冷启动 | `data_sources_verified.md` 已记录：**规模够但 license 风险**。动作：①P2 视觉上线前发邮件向 EPFL 作者确认再分发条款；② 仅做训练不做再分发规避风险；③ 用其 80/20 划分做留出集喂给 C1/C3 评测 | ★★ |
| C3 | **AgroGPT**（awaisrauf/agroGPT，MBZUAI） | WACV 2025，70k AgroInstruct，**license 待查**（学术 repo，通常 MIT/Apache，商用前需确认） | 模块③ · vision.py 多模态 | 它是「从视觉-only 数据合成指令」的农业 VLM，可作 `vision.py` 的强后端（多模态问答而不仅是分类）。动作：① 评估模型体积与本地/云端部署；② 复用其 AgroEvals（见 B4）做评测；③ license 确认后再决定商用路径 | ★ |
| C4 | **GAEZ v4 / WorldClim 2.1**（FAO / 学界） | CC-BY 4.0（GAEZ 需人工确认条款页） | 模块① · 全球数据库 | 已纳入 `crop_adapt_db.json`（上一轮闭环已洗掉死的 Ecocrop 旧站）。本档记录：持续用 GAEZ（含 Ecocrop 参数）做冷启动，不依赖单一源 | ✅ 已落地 |

### D 档 · 投递合作 / 参考警示（外部关系，研发动作最小）

| # | 项目 | 来源 / License | 对应动作 | 优先级 |
|---|---|---|---|---|
| D1 | **gap-agriculture-mcp**（eagleisbatman，东非天气情报，StreamableHTTP） | GitHub | 互引 + 学其 StreamableHTTP 传输（我们当前仅 stdio）；投递见 p0f 文档 | ★★ |
| D2 | **microfarm-mcp**（omardaaboul，地块可行性评估） | GitHub | 其「evidence-backed, never invented」原则与我们的 AgriTrust 同调，联合叙事；互引 | ★★ |
| D3 | **garden-mcp-server**（day-in-the-country-llc，Plant.id 识别，GPL-3.0） | GitHub，**GPL 强传染性** | **只互引不合并代码**；Plant.id 识别交流（我们走 PlantVillage + 中文图） | ★ |
| D4 | **farmOS**（Drupal，GPL） | 农场记录/资产/库存 | 仅**参考其资产数据模型**用于 EcoAgent 设备追踪；GPL 不合并 | ★ |
| D5 | **OpenFarm**（2025-04 已归档死） | CC0 数据 / MIT 代码 | **警示：不可依赖**。它曾想做「种植指南 Wikipedia」但已死——确认我们不该走「农业维基」路线，专注协议/配置而非内容堆砌 | ⚠️ 警示 |
| D6 | **MyCodo**（kizniche，树莓派环境控制） | 老牌开源控制器 | 备选投递目标，star 数/现状**未单独核验**，核验后再触达 | ★ |

---

## 二、优先级总排序与工作量估算

### P0（近期最高优先，直接补核心闭环缺口）
| 项 | 动作 | 工作量 | 阻塞 |
|---|---|---|---|
| A3 + C1/C2 | 本地轻量视觉模型补 `vision.py`（3MB 模型优先，JK-TK 备选），并建 PlantVillage 留出集 | 中（需验证本机 CPU 推理可行性 + license 确认） | 本机无 NVIDIA；license 待查 |
| B4 + C3 | 用 AgroEvals 协议落地 `eval.py` 的 `pest_diagnosis_topk` 基线 | 中 | 需留出集 + 视觉后端 |
| A1 | execution_log ↔ kasvanta 活动日志对接设计（数据 A 闭环） | 低（先定 schema，后对接） | 需对方社区响应（投递） |

### P1（架构借鉴 / 数据补充，提升模块能力）
| 项 | 动作 | 工作量 | 状态 |
|---|---|---|---|
| B1 | 移植 WOFOST 作物参数 YAML → growth_agent 微观参数表（零依赖） | 中 | ✅ **已完成**（2026-09-08） |
| B2 | 移植 @pondlog 150-crop 日历 → growth_agent 季节窗字段 | 低（数据文件） | ⚠️ **改道完成**（2026-09-08） |
| B3 | 用 stdlib + Open-Meteo 重写 mcp-garden 天气层为 `agri_weather` 对等工具 | 中 | 未开始 |
| A4 | Env Recipe → FarmBot 适配器（模块⑤真执行） | 中（需 FarmBot API 文档） | 未开始 |

**B1 已完成**：从 `ajwdewit/WOFOST_crop_parameters@wofost81` 抓取真实 YAML，提取积温物候参数
（TSUMEM/TSUM1/TSUM2/TBASE/C3-C4/春化），移植到 `data/wofost_phenology_reference.json`（7 种与我们
配方库有交集的作物），并实现零依赖推演 `agent/phenology.py`。详见 `docs/wofost_phenology_reference.md`。

**B2 改道（重要）**：@pondlog 的日历数据**实测不可达**——npm tarball 解压后仅含 `package.json`；
GitHub raw / Contents API / tree API 三路均无 `crop-calendar.json`（证据见 `docs/plant_calendar.md` §2）。
故**未**搬运其数据，改为实现本地推导通路：调用方给 12 个月均温 → 环形日序列求最长无霜段 →
结合 B1 的积温参数反推安全播期。已落地为 `agent/plant_calendar.py` + `agent/season_agent.py`，
并注册为 `season_advisory` 技能与 `agri_season_advisory` MCP 工具。详见 `docs/plant_calendar.md`。

### P2（投递合作 / 远期参考）
D1–D6 的互引与投递，渠道与文稿见 `docs/p0f_outreach_targets.md`。

---

## 三、关键风险与信息缺口（诚实标注）

1. **License 缺口**：C1（JK-TK）、C3（AgroGPT）、A3（WENDGOUNDI）的 license 未逐字核实，商用前必须确认——尤其 AgroGPT 学术权重常带 NC 条款。
2. **本机算力**：用户主机为 GMKtec NucBox（AMD 集成显卡、无 NVIDIA、32GB 内存），本地跑 YOLOv11x/AgroGPT 不可行；视觉推理要么走云端 API（ATEX 网关 / SenseNova），要么用 3MB 级超轻量模型 + CPU。
3. **SoilGrids API 不可达**：`api.isric.org` 本网络 502（B3 中已规避），ECS 侧需复测。
4. **OpenFarm 已死（D5）**：不构成依赖，但警示「农业维基」路线不可行——与 v2.0 定案「配置协议而非内容堆砌」一致。
5. **GPL 传染性（D3/D4）**：garden-mcp-server、farmOS 均为 GPL，只参考设计、绝不合并代码。

---

## 四、下一步动作清单（建议执行顺序）

1. **（已完成 2026-09-08）** 零阻塞项落地：A1（execution_log 导入 schema + `agent/execution_log.py`）、
   B1（WOFOST 积温参数移植）、B2（改道为本地推导播期窗口 + `season_advisory` 技能/MCP 工具）。
   顺带修复 MCP server 一处**潜伏 bug**：`_orch` 单例变量与访问器同名，`def` 覆盖了 `_orch = None`，
   导致懒加载从不生效，`_orch()` 返回函数对象——`agri_match_zone`/`recommend_crops`/`growth_plan`/
   `diagnose_pest`/`nutrition_plan` **五个工具此前一直在静默返回「工具执行失败」**，旧测试只断言
   "响应含 text" 未能发现。已修（`_ORCH_SINGLETON`）并把测试改为断言真实分区 ID。
2. **（需确认）** 视觉模型三选一（A3 轻量 3MB / C1 JK-TK / C3 AgroGPT）：先核实各自 license 与本机/云端推理可行性，再决定 `vision.py` 后端路线。
3. **（用户硬阻塞，延续 p0f 文档）** GitHub PAT 提供后发 A1/A2 issue；Reddit r/AeroGarden 帖子由用户发布。
4. **（评测）** B4 + C2 联合：PlantVillage 留出集 + AgroEvals 协议，把 `eval.py` 的 `pest_diagnosis_topk` 从 NOT_IMPLEMENTED 推进到首个基线。
5. 每次借鉴/对接结果记 `docs/intel_log.md`；3 个月决策门（P0-F/P0-G）自首次投递起算。

---

## 五、与既有文档的关系

- `docs/p0f_outreach_targets.md`：本清单 D 档的**投递子集**（MCP 目录上架 + AeroGarden 社区 + issue 文稿）。本清单是研发全集，D 档只给对接动作，不重复渠道与文案。
- `docs/data_sources_verified.md`：本清单 C4/D 档的数据可达性与 license 一手核实来源。
- `docs/env_recipe_protocol_v1.md`：A1/A2/A4 的协议规范与 `aerogarden_orphan` 设备类定义来源。
- `engine/eval.py`：B4/C3 的评测脚手架落地目标。
