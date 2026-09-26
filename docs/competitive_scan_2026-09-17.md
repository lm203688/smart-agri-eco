# 智慧农业生态 · 开源竞品扫描 + 市场需求调研

- 扫描日期：2026-09-17
- 方法：逐个 Web 搜索 + GitHub 仓库页核实（URL / license / star / 最近活跃时间）
- 原则：不确定即标「待核实」，不编造项目名、star 数、URL 或数据
- 对齐基线：本项目已有 110 个 Env Recipe、4+3 Agent、9 Skill、9 MCP 工具、244 单测、纯 Python 零第三方依赖

---

## 1. 结论摘要（按 ROI 排序）

1. **「climate recipe」这个词不是我们发明的——MIT OpenAg 2013 年就用它了，而且他们已经死了。** 概念、命名、愿景（"Open Phenome Library"= 环境输入 × 物种 → 表型输出）与本项目 Env Recipe 几乎同构，但 OpenAg 因缺钱缺人停摆（PFC 项目 2015-09 至 2020-04），代码迁到 `OpenAgricultureFoundation` 且主仓库 3 年未大更新。**ROI 极高：去读 `openag-device-software` 的 recipe JSON 结构，能直接校对 Env Recipe 字段清单，避免闭门造车的字段设计错误。**
2. **PlantVillage「无 license」判断正确，但下游传播了错误的 CC0 声称。** 原仓库 `spMohanty/PlantVillage-Dataset` 文件列表里**没有 LICENSE 文件**（2026-02-05 仍在维护，只加了 HF 集成）；而 HuggingFace / Meta-Album / 部分 Kaggle 镜像单方面声称 CC0 1.0。商用风险真实存在。**可落地的替代：`PlantDoc` 是明确 CC BY 4.0**（仓库内有 LICENSE.txt），2598 张、13 物种、17 类病害，且是网络抓取的真实场景图（非白底棚拍），恰好补 PlantVillage 的短板。
3. **Env Recipe 缺三个物候/光照派生字段：DLI、VPD、Dew Point。** Home Assistant 生态的 `Horticulture-Assistant` 已把这三者做成一等实体（`sensor.<name>_dli` mol·m⁻²·d⁻¹、`_vpd` kPa、`_dew_point`），并派生 Mold Risk Index。**我们 schema 只有 ppfd_umol + photoperiod_h，等于手算 DLI；补 3 个派生字段是小改动、高辨识度。**
4. **Env Recipe 没有版本化/diff/导出协议。** `Horticulture-Assistant` 把每个植物 profile 做成磁盘 JSON，支持 export / import / **diff** / versioning，并在 `services.yaml` 里声明所有可调用动作——这是「Agent-native + 可执行」的正确形态。**抄它的 profile 生命周期设计，比抄任何控制算法都值钱。**
5. **MCP 生态里农业 server 已有一批，但全部是"薄包装 + 外部 API key"。** `FarmerConnect-MCP`（Open-Meteo + LocationIQ + Wikipedia）、`agrobr-mcp`（19 个巴西政府源）、`agrisignal-mcp`（npm，Open-Meteo + SoilGrids）——共同短板：依赖联网、依赖 API key、无本地知识底座。**本项目的零依赖 + 本地 sqlite FTS5 + Env Recipe 是差异化真壁垒，不是空话。**
6. **物候方向有明确的"现成函数清单"可抄。** R 包 `agroclim`（MIT）给出 `gdd / frostDays / firstFrost / lastFrost / frostProb / warmMonth / coldMonth / bedd / ehe / hi`（Huglin 葡萄指数），`vegperiod`（GPL-3+）给出三种生长季判定法（ETCCDI 气象法、NuskeAlbert 7 日移动平均、Ribes uva-crispa 鹅莓展叶生物法），`cropgrowdays`（MIT，CRAN 2025-10 仍在更新）给出 `day_of_harvest`（收获跨年时算收获那年）。**这些是纯数学函数，逐条移植进纯 Python 零依赖完全可行。**
7. **中国市场信号比国际社区强得多，且驱动力是情绪价值不是省钱。** 2024 年中国智能阳台种植系统市场约 58.02 亿元、CAGR 24.7%（Scineer 论文，含置信区间）；2026 年"阳台种菜"商品销量同比 +150%，18–35 岁占四成；武汉农博会已单列"阳台农业"展区。**"治愈 / 亲子 / 掌控感"是购买理由，"省菜钱"不是**——这直接影响我们产品的信息架构（结果反馈要即时可视化，而不是产量报表）。
8. **OpenFarm 的"Growing Guide"字段清单是最直接的参照物。** 它定义了 seed spacing / sowing depth / watering regimen / soil composition / **companion plants** / sun-shade——其中 **companion_plants 和 sowing_depth 是本项目 Env Recipe 完全没有的字段**，而它们对阳台场景（空间极小、伴生植物实用）是刚需。

---

## 2. 方向一：农业开放数据聚合器 / 知识底座

| 项目 | URL | License | 最近活跃 | 它做了什么 | 可借鉴的具体做法 | 与本项目差异/冲突 |
|---|---|---|---|---|---|---|
| **FAOSTAT API** | https://www.fao.org/faostat/en ；API 门户 fenixservices.fao.org/faostat/api/v1 ；bulk bulks-faostat.fao.org/production | CC BY-**NC**-SA 3.0 IGO | 活跃（bulk 页显示 2026-09-03 更新，721MB/759MB） | 全球 245+ 国家、1961 至今的农产品/土地/化肥/农药统计。SDMX 标准，有 OpenAPI 3.0.3 规范，`/catalog.json` 给全量数据集目录+文件大小+更新日期 | 抄 `catalog.json` 的设计：一条端点返回"数据集 × 文件 URL × size × last_updated"，让我们能在 UI 上展示"这个 Env Recipe 引用的 FAOSTAT 数据是 2026-09-03 的"，做成 AgriTrust 溯源的一部分 | **NC（非商用）是硬约束**：本项目若要商用授权高级配方包，不能把 FAOSTAT 数据作为付费资产转售，只能作为溯源引用 |
| **OpenAgData** | https://open-ag-data.com | 平台私有；研究元数据 CC BY 4.0 | 活跃（创始人 Saurav Das，早期阶段） | 把 40 年田间试验论文按"试验地点"地理编码：州/县 × 土壤 × 气候 → 谁资助、测了什么指标（产量/土壤碳/径流/利润）、哪些空白没被测试 | 抄"evidence-by-place"的组织方式：Env Recipe 的 `sources` 字段目前只有 title/url/accessed_at，加一个 `trial_location` + `soil_context` 就能让"这条配方依据的试验是在哪片土做的"可检索 | 它不是开源代码项目（无 GitHub 仓库可核），是单人 SaaS；其数据是论文元数据，不是环境参数 |
| **OADA (Open Ag Data Alliance)** | https://github.com/OADA | 各仓库 Apache-2.0 / MIT（server Apache-2.0，formats MIT） | 活跃（2025-11 仍有提交，61 仓库） | 农场级数据的互操作标准：REST API + OAuth 2.0 + **JSON Schema 定义的 formats**，含 server/client/formats/cli/oada-cache 等 | 抄 `oada/formats` 的做法：用 JSON Schema 定义数据格式而非文档描述，让我们 9 个 MCP 工具的参数契约能直接进 OpenAPI/MCP registry。其 `oada-cache`（JS，2 依赖，9/17 仍有更新）值得看缓存层怎么设计 | OADA 是 TypeScript/JS 栈，且聚焦"农场数据所有权+OAuth"，与本项目"知识底座+配置"定位不同；OAuth 体系对纯本地部署过重 |
| **ESA WorldCereal** | https://github.com/ESA-WorldCereal ；https://esa-worldcereal.org | MIT（classification）、Apache-2.0（docs） | 活跃（worldcereal-classification 89★ MIT，2026-06-18；worldcereal-cropcalendars 2026-04-21） | Sentinel 卫星 10m 全球谷物类型/灌溉地图 + 分类算法 + **作物日历仓库** | `worldcereal-cropcalendars` 是一个直接的物候数据参照——我们做 WOFOST 积温播期窗口，可以对照它的 calendar 粒度定义 | 卫星遥感是大田尺度工具，与本项目明确的"暂缓大田/L1"冲突；但 cropcalendars 的数据结构本身可抄 |
| **Open Food Network** | https://github.com/openfoodfoundation/openfoodnetwork | AGPL-3.0 | 活跃（2026-04-10，~1.2k★，625 issues） | 本地食品 B2C/B2B 市集平台（农场 ↔ 消费者），Ruby on Rails | 不建议借鉴：是交易平台不是数据/配方层；AGPL-3.0 对闭源分发有传染性，与本项目许可策略可能冲突 | 定位完全不同，仅作为"农业开源可持续运营"的样本（Open Food Foundation 资助模型） |
| **farmOS** | https://farmos.org ；https://github.com/farmOS/farmOS | GPL-2.0+ | 活跃（2026-01-27，84 个 release tag，9218 commits） | 农场管理/记账/规划系统，基于 Drupal 11.3，模块化（可只开 Crop 关 Livestock） | 抄"字段级模块化"思路： Drupal 的 feature 机制让不同用户只装需要的模块——Env Recipe 可按 `device_class` 裁剪出 balcony 子集 schema | 它是记录系统（发生了什么），不是配置系统（该怎么设）；GPL 传染性与本项目许可需评估 |
| **OpenSprinkler** | https://github.com/OpenSprinkler | 固件 GPL-3.0（554★，2026-08-02）；App AGPL-3.0（204★）；硬件 CERN-OHL-S-2.0（79★）；Weather TS（69★） | 活跃 | 开源灌溉控制器：8–72 区、天气联动雨延（Weather Underground/OpenWeatherMap）、MQTT、原生 Home Assistant 集成 | 抄"天气联动雨延"逻辑：`OpenSprinkler-Weather` 把降水预报转成 watering scale 的算法，可直接对应我们 `exception_handling` 里的"预报降雨 → 跳过灌溉"规则 | GPL-3.0 传染；且它是执行层（继电器），我们是配置层，互补而非竞争 |
| **GAEZ v4 / WorldClim / ISRIC SoilGrids** | （本项目已有） | GAEZ 需注册；WorldClim 部分收费；SoilGrids CC BY 4.0 | — | 已有数据源 | — | SoilGrids CC BY 4.0 可商用，是最安全的一块；GAEZ 与 WorldClim 商用条款**待核实** |

**要点**：数据层没有颠覆性竞争者。真正的空白是"试验证据按地点可检索"（OpenAgData 在做）和"数据集目录带时间戳"（FAOSTAT catalog.json），两者都能补进 AgriTrust 溯源而不动零依赖约束。FAOSTAT 的 NC 条款是唯一需要注意的法律红线。

---

## 3. 方向二：种植配方 / 环境配置协议类项目

| 项目 | URL | License | 最近活跃 | 它做了什么 | 可借鉴的具体做法 | 与本项目差异/冲突 |
|---|---|---|---|---|---|---|
| **⚠️ OpenFarm（已归档，勿接入）** | https://github.com/openfarmcc/OpenFarm | MIT | **2025-04-21 服务器关停，2025-04-22 仓库归档只读** | "种植指南 Growing Guides"：结构化众包文档，含 seed spacing、sowing depth、watering regimen、soil composition、**companion plants**、sun/shade 需求 | **抄字段清单，不抄实现**。它的数据已冻结在 2025 年初，可作 Env Recipe 的 bootstrap 数据源之一，但绝不能有运行时依赖 | 官方原话："never quite got the traction needed to become a self-sustaining resource"。这是本项目最好的反面教材：众包 + 无资金 + 无本地化 = 死。**结论：Env Recipe 必须靠"真实结果回流"养活，不能靠众包填坑** |
| **⚠️ MIT OpenAg / OpenAgricultureFoundation（已停摆，代码可挖）** | https://github.com/OpenAgInitiative （**已清空，无公共仓库**）→ https://github.com/OpenAgricultureFoundation | openag-device-software GPL-3.0；self_hosted_backend MIT；PFC_EDU v3.0 材料 CC BY-**NC**-SA 4.0 | openag-device-software 195★，最后更新 2026-03-02；self_hosted_backend 3★，2026-02-13 | Food Computer 控制平台。核心概念 **climate recipe**（时间序列的温度/湿度/光谱/CO₂ profile）+ **Open Phenome Library**（环境输入 × 物种 → 表型输出的开放数据库） | **最高优先级参照物**。去读 `openag-device-software` 里 recipe 的 JSON 定义和 stage 划分，逐项对照我们的 Env Recipe v1 schema。它的"Open Phenome Library"就是本项目战略里"壁垒②④"的英文原版表述，可以在对外叙事里明确我们的定位关系 | 已停摆：MIT 官方页显示 PFC "active from September 2015 to April 2020"。GPL-3.0 + PFC_EDU 的 NC 条款限制直接复用。但**它的死证明了这个概念是对的、只是没人运营得起** |
| **Horticulture-Assistant（HA 插件，配方层最接近的活项目）** | https://github.com/TraverseJurcisin/Horticulture-Assistant-HASS-REPO | 待核实（README 有 License 章节但未读到具体条目） | 活跃 | 每种植物一个 JSON profile（如 Avocado），支持传感器绑定、派生指标、生长阶段感知、AI 建议审批后写入 profile | **抄三件事**：①profile 是磁盘 JSON + export/import/**diff**/versioning 四件套；②派生实体三件套 DLI(mol·m⁻²·d⁻¹)/VPD(kPa)/Dew Point + **Mold Risk Index**（基于 T/RH 动力学）；③`services.yaml` 显式声明 `create_profile / duplicate_profile / recompute / apply_irrigation_plan / export_profile / import_profiles`——这就是"Agent-native"该有的工具粒度 | 它是 HA 插件（Python，依赖 HA 运行时），不是独立后端；无本地检索/记忆层；无结果回流闭环 |
| **OpenGrowBox-HA** | https://github.com/OpenGrow-Box/OpenGrowBox-HA | 待核实（README 未见） | 活跃（HA 社区帖 2026-03-31 起） | HA 种植房自动化：VPD 24/7 控制、日/夜双 profile、多房间、**标签系统**（把设备拖进房间 + 加标签"Exhaust/Heater/Light/Pump/CO2/Climate"即自动接管，支持 30+ 语言标签识别） | 抄"标签即配置"的低摩擦接入：我们针对 Aerogarden 孤儿设备的自救方案，应该让设备能力探测 → 自动映射 sensor_capability → 自动选 recipe，而不是让用户填 JSON | Premium 层有"40,000+ strain 数据库"和 PID/MPC ±0.05 kPa——说明这个市场愿意为精度付费，反向印证我们"输出可执行配置"的付费点 |
| **HA-Plant-Assistant** | https://github.com/shortmanflee/HA-Plant-Assistant | 待核实 | 活跃 | 单株跟踪、**自动计算 DLI 和 PPFD**、灌溉区调度、**OpenPlantBook 集成取物种养护参数** | 抄"外部物种知识库作 fallback"的架构：我们的 110 个 Env Recipe 覆盖不到的物种，可以先接一个外部 reference library 兜底，而不是留空 | 依赖 OpenPlantBook API（需凭据），与我们零依赖约束冲突，只能作可选扩展 |
| **simple-plant-extended** | https://github.com/jo-anb/simple-plant-extended | 待核实 | 活跃 | 极简植物养护实体：`binary_sensor.<name>_todo` / `_problem`、`date.last_watered`、`number.days_between_waterings`、`button.mark_watered`，覆盖 watering/misting/fertilization/cleaning 四类周期 | 抄实体命名规范：把"该不该做 X"和"上次做 X 是什么时候"分开成独立实体，让 Agent 的调度判断变成简单的状态机读取，不用解析时间序列 | 太简单，无参数级配置，仅适合作 UI 层参照 |
| **FarmBot OS** | https://github.com/farmbot/ | MIT | 活跃（生态 ~1.2k★） | CNC 机器人农场：sequences + regimens，PostgreSQL，TypeScript/Ruby | `regimen` 概念（可复用的动作序列模板）与 Env Recipe 的 `exception_handling` 同构，可参考其 regimen 的引用/继承机制 | 硬件重（CNC 步进电机），与城市箱体场景不符 |
| **⚠️ Plantower（非农业项目，澄清）** | https://github.com/cristeab/plantower | MIT（145 commits，2025-05-05）；node 版 ISC | 活跃（分叉） | **Particulate Matter（PM）空气质量传感器库**，读 PMS5003/PTQS1005/DS-CO2-20，输出 `{value, unit}` 结构 | 无。仅澄清：任务清单里的"Plantower 温室控制"在 GitHub 上不存在，同名项目全部是 PM 传感器驱动。搜索"Plantower + 温室"会持续误导 | 与本任务方向无关 |

**要点**：这一栏是整份报告的重点。结论是——**「climate recipe」概念的原创性归属于 MIT OpenAg（2013/2015），本项目的独立价值在于把它做成了零依赖、可执行、有结果回流的完整栈**。对外叙事建议：明说 OpenAg 是思想源头（这是学术诚信，也让定位更可信），强调 OpenAg 死于运营而非死于技术，我们的差异是执行层闭环。字段层面，Env Recipe v1 至少有 4 个字段缺口可补：`DLI`、`VPD`、`companion_plants`、`sowing_depth`。

---

## 4. 方向三：MCP / Agent-native 农业生态数据服务

| 项目 | URL | License / 分发 | 最近活跃 | Tools 设计与 schema 粒度 | 可借鉴的具体做法 | 差异/冲突 |
|---|---|---|---|---|---|---|
| **FarmerConnect-MCP** | https://github.com/adr1en360/FarmerConnect-MCP | MIT，Python，可 git clone | 2025-11-06（README）、2026-02-27（分析文档） | 6 个 tool：`calculate_agro_metric`（地块面积/种植密度/产量估算/单位换算合一）、`get_weather_now(lat, lng)`、`forward_geocode(place_name)`、`reverse_geocode(lat, lng)`、`get_current_datetime`、`get_crop_info(crop_name, location)`。SQLite 缓存 30 天 | 抄两点：①`get_crop_info` 把"作物名 + 地点"双参数化（同一作物在不同国家推荐不同做法），我们的 crop Agent 可以加 `location` 参数化召回；②**依赖替换记录可学**——它在 2025-11-05 把 Meteomatics API 换成 Open-Meteo（免 key），说明免 key 是硬趋势 | 依赖 LocationIQ（需 API key），与零依赖冲突；无本地知识底座；tool 粒度太粗（4 类计算塞进 1 个 tool） |
| **agrobr-mcp** | https://github.com/bruno-portfolio/agrobr-mcp ；索引 https://www.mdskills.ai/mcp-servers/agrobr-mcp | MIT，Python，`pip install agrobr-mcp`，`mcp-name: io.github.bruno-portfolio/agrobr` | 2026-02-24（mdskills 更新） | 10 个 tool：`preco_diario` / `futuros_b3` / `estimativa_safra` / `producao_anual` / `balanco` / `progresso_safra` / `clima` / `desmatamento` / `listar_produtos` / `health_check`，接 19 个巴西公共源（CEPEA、CONAB、IBGE、INPE、B3、NASA POWER） | **抄架构分层**：它是"薄 wrapper + 数据逻辑在独立库 `agrobr`"，测试可独立跑（`pytest -m "not integration"`）。我们 9 个 MCP 工具应该把"数据获取层"和"MCP 适配层"拆开，否则每次加数据源都要动 server.py | 单一国家视角、单一语言（PT-BR 文档），无知识底座、无 recipe |
| **agrisignal-mcp** | LobeHub 索引：https://lobehub.com/mcp | npm（作者 govardhansatya） | 2026-08-31（索引时间） | 免 key 合成 Open-Meteo + SoilGrids，输出灌溉建议、**霜冻/高温风险、Growing Degree Days、干旱事件追踪** | 抄"把数据合成决策"的输出形态：不是返回数据让 LLM 自己算，而是返回"结论 + 依据"。这是 Agent-native 的正确粒度 | 免 key 但依赖联网；未读到源码细节 |
| **Agricultural Commodity Climate MCP**（apifyforge） | LobeHub 索引 | 未验证 | 2026-08-31（索引时间） | 编排 8 个公共源，免 key，输出活体天气胁迫分析、**病虫害出齐监测**、贸易集中度评分、价格冲击概率 | "病虫害出齐监测"（pest emergence monitoring）是我们 pest Agent 的现成对标指标 | 大宗商品视角，非种植端 |
| **MCP_USDA_Server** | https://github.com/AntonioPavoni/MCP_USDA_Server_Quantized | 未读到 LICENSE（待核实），Node.js | 较早（模板性质） | 5 个 tool：`usda-psd-regions` / `countries` / `commodities` / `units-of-measure` / `commodity-attributes`；JSON-RPC 2.0；**formatter 层把 API 结果转成 LLM 友好的 markdown** | 抄 **formatter 层**：把"数据获取"和"LLM 呈现格式"分成两个目录（`tools/` + `formatters/` + `handlers/` + `routers/`），这是我们 mcp/server.py 单文件架构的升级方向 | Node.js 栈；PSD 是贸易统计，与种植配置无关 |
| **CropProphEU**（DasClown） | https://github.com/DasClown/CropProphEU | 待核实 | 2026（dev.to 博文） | EU 作物产量预报/市场价值/风险分析，整合土壤+气候+市场 | 仅作分发渠道参考：作者同时维护 `awesome-mcp-servers` 精选清单，**这是 MCP 生态的获客入口** | EU 视角 |
| **LobeHub MCP Marketplace** | https://lobehub.com/mcp?q=农业 | — | 2026-08-31 | 农业类 MCP 已有 10+ 条目（含 FarmerTasksAI 193+ 工作流、India MCP Server、Korea FarmSubsidy、smartfarm-mcp 韩国大数据 API 15121334） | **分发渠道确认**：LobeHub / Glama / mdskills 是 MCP 的实际发现渠道，不是 GitHub trending。我们的 MCP 应注册到至少一个 | 索引质量参差，多个条目标"Unvalidated" |

**要点**：MCP 农业生态的真实状态是**大量薄 wrapper、无知识底座、依赖 API key 或联网**。本项目"零依赖 + 本地三层检索 + Env Recipe 可执行输出"确属空白。但两个可立即抄的工程实践价值高：① formatter/handler/router 分层（MCP_USDA_Server）② data-lib / mcp-adapter 解耦 + 集成测试可跳过（agrobr-mcp）。分发侧要进 LobeHub 而非 GitHub trending。

---

## 5. 方向四：病虫害视觉数据集与开源模型

| 数据集 | URL | License | 规模 | 关键特征 | 可借鉴做法 | 风险 |
|---|---|---|---|---|---|---|
| **PlantVillage**（本项目已有，重新核实） | https://github.com/spMohanty/PlantVillage-Dataset ；HF https://huggingface.co/datasets/mohanty/PlantVillage | **原仓库无 LICENSE 文件**（已核实文件列表：只有 .gitignore / CITATION.cff / README.md / README_HF.md / leaf-map.json 等，无 LICENSE） | 54,306 图、38 类、14 作物、26 病害 + 健康类；256×256 | 白底/黑底棚拍，叶片单独离体。EPFL Digital Epidemiology Lab（Mohanty/Hughes/Salathé 2016） | 仓库 **2026-02-05 仍活跃**（加了 HF 集成、leaf grouping、SVM 数据），说明原作者在维护但**从未声明许可** | **确认用户的判断正确：无明确 license，商用需联系作者。** 注意：HuggingFace `geraldmc/plantvillage-full`、Kaggle `timothylovett/plantvillage-splits`、Meta-Album 都声称"CC0 1.0 inherited from upstream"——**这是下游单方面声称，上游无此声明，不可依赖** |
| **PlantDoc** | https://github.com/pratikkayal/PlantDoc-Dataset （LICENSE.txt 内为 CC BY 4.0） | **CC BY 4.0（已核实，三处交叉确认：仓库 LICENSE.txt / Meta-Album / Roboflow）** | 2,598 图、13 物种、17 类病害；另有 object detection 版 2,569 图 8,851 标签 | **网络抓取的真实场景图**（Google Images/Ecosia），非棚拍；IIT 作者，CoDS-COMAD 2020 | **这是 PlantVillage 的正确商用替代**。它的"非白底、多变光照、含整株"恰好补 PlantVillage 的缺陷，且 CC BY 4.0 允许商用（需署名） | 规模小 1/20；图像来源含第三方版权（作者已用 CC BY 声明承担） |
| **Corn Leaf Disease**（Kaggle ndisan） | https://www.kaggle.com/datasets/ndisan/corn-leaf-disease | 未明确（Kaggle 默认条款，待核实） | 4 类 × 1000 图（healthy / leaf blight / leaf spot / leaf rust） | 印尼采集，手机拍摄，**白纸衬底**，12–14 时统一光照 | 作为玉米单作物的补充；其"每类固定 1000 张 + 固定拍摄协议"的采集规范可抄进我们自建中文数据集的方案 | Kaggle 条款限制再分发 |
| **阿里天池 rice disease** | https://tianchi.aliyun.com/dataset/125957 | **CC BY-SA-NC 4.0**（注意 NC） | 3 类，40 张/类，36.68MB | 中文源，2022-04 | 中文场景价值高，但只有 120 张 | **NC 禁止商用**，不能进商用配方包 |
| **PlantVillage Apple Color** | https://www.kaggle.com/datasets/lextoumbourou/plantvillageapplecolor | 继承 PlantVillage（即无 license） | — | 苹果彩色叶 | — | 同 PlantVillage 风险 |
| **AGRIFOLD**（模型框架，非数据集） | http://github.org/MODAL-UNINA/AGRIFOLD | 待核实 | 12 个异构数据集、9 病害类 + 健康类 | 联邦学习（Flower 框架）+ **VGG16 + ECA 通道注意力** + 剪枝轻量到可上边缘设备 + **NLP 推荐系统给防治建议** + heatmaps | 抄两点：①**"分类 → 防治建议"用 NLP 检索而非硬编码规则**，与我们 pest Agent 的证据门控思路一致；②用 FedAvg/FedProx/SCAFFOLD/FedBN/FedDF 五种聚合器做消融（SCAFFOLD 最好）——如果将来要做社区联合训练，这是实验模板 | 需要 PyTorch + Flower，与零依赖约束冲突，只能作研究参照 |
| **零依赖推理方案** | — | — | — | 本项目已定"先用 PlantVillage 冷启动 + 证据门控零误报" | **建议维持现状**：本扫描未发现"纯 Python 标准库 + 可用"的植物病害视觉模型。视觉推理绕不开图像预处理 + 矩阵运算，零依赖意味着手写 CNN 前向（可行但工作量级"大"，且精度远不如迁移学习）。**更划算的路径是"图像 → 特征统计量（颜色直方图/纹理）→ 规则判定"，这是零依赖能做的，且可解释性强，正合证据门控定位** | 精度上限低；需明确"辅助筛查"而非"诊断"定位 |

**要点**：数据集侧最重要的一条是——**PlantDoc CC BY 4.0 是 PlantVillage 的合规补位方案，且图像分布互补**（真实场景 vs 棚拍）。模型侧，零依赖约束下不应追求 CNN 精度，而应走"可解释特征统计 + 证据门控"，这是本项目已有的正确路线，本扫描未发现有更好替代。

---

## 6. 方向五：物候 / 播期 / 积温工具

| 项目 | URL | License | 最近活跃 | 具体能力 | 可借鉴的具体做法 | 差异/冲突 |
|---|---|---|---|---|---|---|
| **agroclim（R）** | https://github.com/sherlg/agroclim | **MIT** | 活跃（GitHub 开发版） | 农业气候指数函数集：`gdd(tmin, tmax, base_temp)`、`bedd`（生物有效积温）、`frostDays`、`frostFreqs`、`frostProb`（基于历史）、`firstFrost`、`lastFrost`、`firstTemp`（春季首次阈值）、`warmMonth`、`coldMonth`、`ehe`（过量热事件）、`hi`（**Huglin 葡萄栽培指数**）、`tempDayprob`、`tempProb`；辅助 `calcGrid`（栅格化）、`pentadProbs`（5 日周期概率） | **这是最可直接移植的清单**。全是纯数学函数，无外部数据依赖，逐条翻译进纯 Python 零依赖完全可行。**优先级最高：`frostProb` + `firstFrost`/`lastFrost` 是城市箱体决策的刚需**（无霜期 = 能种什么） | R 语言；需自行实现/校验数值结果 |
| **vegperiod（R）** | https://cran.r-project.org/web/packages/vegperiod/ ；https://github.com/rnuske/vegperiod | **GPL-3+** | CRAN 0.4.0，2022-11-01 | 三种生长季判定法：①**ETCCDI / StdMeteo**：连续 ≥6 天日均温 >5°C 为起点；②**NuskeAlbert**：7 日移动平均，5 连续天 <5°C 为终点（从 7 月 1 日或生长季起点开始搜），叠加短日判据（最后一天 ≤10 月 5 日）；③**Ribes uva-crispa（鹅莓展叶）**：德国气象局 DWD 开发，基于鹅莓展叶物候，**抗假早启动能力强于纯气象法** | 抄**三种方法并存**的设计：我们 WOFOST 积温是单一方法，加"多方法投票/交叉校验"能显著提升播期窗口的可信度，且这是纯规则计算 | GPL-3+ 传染，**只能抄算法不能抄代码**；需从论文重新实现（Menzel 1997；Walther & Linderholm 2006；Janssen 2009 均有公开出处） |
| **cropgrowdays（R）** | https://gitlab.com/petebaker/cropgrowdays | **MIT** | CRAN 打包 **2025-10-15**（v0.2.2） | `growing_degree_days`、`stress_days_over`、`cumulative`、`daily_mean`、`weather_extract`、`day_of_year`、`date_from_day_year`、**`day_of_harvest`**、`get_silodata`（澳洲 SILO 数据） | 抄 `day_of_harvest` 的细节：**作物可能在播种的次年收获，此时算 DOY 应该用收获那年**——这是 WOFOST 积温窗口计算的常见 bug 来源 | 依赖 R 生态；SILO 数据仅澳洲 |
| **Open-Meteo Historical / Climate Normals** | https://open-meteo.com ；https://github.com/open-meteo/open-meteo | **代码 AGPLv3；数据 CC BY 4.0** | 活跃 | 免 API key、免注册（非商用）；80 年历史逐时数据；全球；1km 区域 + 11km 全球模型；~10,000 req/day；另有 Climate API（IPCC 情景） | **这是 ISRIC 不可靠的替代方案**：同样是 REST、同样免 key、同样免第三方依赖（stdlib urllib 即可）。可用作无霜期/积温的**运行时实时数据源**，配合本地 WOFOST 计算 | 非商用限制；AGPLv3 仅约束代码（我们只调用 HTTP API 不修改其代码，无传染）；数据质量与 WorldClim 不同源，需交叉验证 |
| **SILO（澳洲气象局格点数据）** | 经 cropgrowdays `get_silodata` 访问 Queensland DES longpaddock | CC BY 4.0 | 持续更新 | 1889 至今澳洲日气候格点数据，含 radn/maxt/mint/rain/evap/vp 及 source code（0 实测 / 2 插值 / 3 异常插值 / 6 合成） | 抄**source code 字段设计**：每个数据点标注它是实测还是插值，让我们 `sources` 溯源能区分数据质量等级 | 仅澳洲 |
| **NASA POWER** | （被 agrobr-mcp 用作 `clima` tool 数据源） | 公开 | 活跃 | 格点气象数据，免 key | 作为第二气象源做交叉验证 | — |
| **WOFOST**（本项目已有） | （已有 7 作物参数，EUPL 1.2） | EUPL 1.2 | — | 积温物候播期窗口 | — | 唯一方法风险：建议按 vegperiod 加多方法校验 |

**要点**：这一栏给出了**最清晰的可移植清单**——`agroclim` 的 15 个函数 + `vegperiod` 的 3 种生长季判定法 + `cropgrowdays` 的 `day_of_harvest` 跨年细节，全部是纯数学、无数据依赖，翻译成纯 Python 零依赖工作量"中"。且这三者都是开源许可（MIT/GPL-3+/MIT），MIT 两个可自由实现，GPL 的必须从论文重新实现（不能抄代码）。这是本项目 ROI 最高的一个方向。

---

## 7. 方向六：市场需求信号

| 信号源 | 时间 | 具体内容 | 对本项目的含义 |
|---|---|---|---|
| **Scineer 期刊论文《Smart Balcony Garden Technology Progress (2024-2025)》** | 2024–2025 数据，近期发表 | 中国智能阳台种植系统市场 2024 年达 **58.02 亿元人民币**（95% 置信区间 49.32–66.72 亿），2024–2030 **CAGR 24.7%**。核心创新：LoRaWAN 混合通信、**AgriQA Net 多模态 AI 养护**、雨污回收+光伏储能。提出"感知-通信-决策-执行-低碳"五维框架 | 有量化市场空间。**"多模态 AI 养护"与我们的 pest Agent + 视觉诊断方向一致**；但 LoRaWAN 通信层与我们的零依赖本地架构冲突——我们应做决策层，不做通信层 |
| **武汉农博会（第二十届）** | 2026-06-05 | 3 万㎡展区、800+ 企业、6000+ 产品，**"阳台农业"意外成为流量担当**。武汉农业集团：全国阳台农业已入**千亿级赛道**；武汉全市约 408 万户家庭。4 品类 16 款标准化产品首秀（向日葵 28 天开花、免土朱顶红、药食同源盆栽菜、活体菌菇包、智能种菜机、鱼菜共生柜） | **产业化的关键趋势是"标准化套餐 + 服务闭环"**：种苗+基质+设备+耗材+技术指导。我们的 Env Recipe 是这条闭环里唯一开源的"技术指导"层——这是清晰的卡位点 |
| **今日头条《城里人阳台种菜，治愈还是被收割》** | 2026 | **2026 年以来阳台种菜相关商品销量同比 +150%**；主力 85/90 后，银发群体增速最快；18–35 岁占四成以上。原话："我不是为了省买菜钱，就是每天下班看看那盆菜长了没有，觉得很治愈" | **决定性洞察：购买理由是情绪价值，不是经济性**。产品必须提供即时可视化反馈（"今天长了多少"），而不是产量报表。这直接反对我们做"专业农艺师界面"，应做"成长日志/日历"界面 |
| **中国报告大厅《2025 农场产业布局》** | 2025 | 2024 家庭园艺线上销售破 8 亿元；**智能种植设备日均搜索量 8 万次**；蓝莓盆栽销量 +300%；2025 家庭园艺市场预计破 120 亿元，智能设备占 40% | "日均搜索 8 万次"证明存在**未被满足的信息需求**——用户搜智能设备说明他们在找解决方案而非只买东西。这正是知识底座的入口机会 |
| **新京报（资本视角）** | 2023 | 智能种菜机销售额同比 +200%；95 后占购买者 60%；共享菜地年租几百到几千"上线即秒空"；海尔、小米入局 | 大厂入局 = 硬件普及 = **孤儿设备（Aerogarden/智能种菜机）存量快速增长**，正是我们 `device_class: aerogarden_orphan` 的战略对象在自然扩容 |
| **Home Assistant 社区（国际）** | 2026-03–04 | OpenGrowBox-HA 发布帖获 21×970 关注；同日 plantlab-ai 提出"视觉植物健康诊断 → 结构化 JSON → HA 自动执行"（30 类问题含单项缺素，免费层 3 次/日） | **国际社区正在验证"环境控制 + 视觉诊断闭环"**，且已出现付费点（免费层限次）。评论区原话："OpenGrowBox controls the environment, but nothing tells it whether the plant is actually responding well"——**这句话精准描述了本项目的价值主张** |

**要点**：中国市场（58 亿元、CAGR 24.7%、+150% 销量）的量级远超国际社区。三条直接行动含义：①驱动力是情绪价值 → 界面必须做成长日志而非产量报表；②"日均 8 万次搜索智能种植设备"= 未被满足的信息需求，知识底座有真实入口；③大厂硬件普及 = 孤儿设备存量扩容，`aerogarden_orphan` 卡位正确。

---

## 8. 本项目提升杠杆点（按 ROI 排序）

### 杠杆 1：Env Recipe 补 3 个派生字段（DLI / VPD / Dew Point）+ Mold Risk Index
- **做什么**：在 `environment` 下新增 `light.dli_umol`（mol·m⁻²·d⁻¹，可由 ppfd_umol × photoperiod_h 派生但需显式留位）、`humidity.vpd_kpa`（由 T/RH 计算）、`humidity.dew_point_c`，并在 `exception_handling` 支持 `mold_risk` 条件。
- **为什么**：`Horticulture-Assistant` 已把这三者做成一等实体并派生 Mold Risk Index；这是行业事实标准，缺了就等于让所有 Agent 手算。
- **工作量**：**小**（schema 加 3 字段 + 一个纯 Python 函数 `calc_vpd(t_c, rh_pct)`）。
- **零依赖影响**：**无**（VPD 是 Magnus 公式，纯算术）。

### 杠杆 2：Env Recipe 补 OpenFarm 遗留的 2 个字段（companion_plants / sowing_depth）
- **做什么**：`environment` 新增 `companion_plants: [{species, latin, relation: positive|neutral|negative}]`；`stage == seed` 时新增 `sowing_depth_cm`、`seed_spacing_cm`。
- **为什么**：OpenFarm 归档证明了这套字段清单是对的（10 年众包共识）；阳台场景空间极小，伴生植物是刚需；`sowing_depth` 是播种配方的核心参数，我们现在完全没有。
- **工作量**：**小**。
- **零依赖影响**：**无**。

### 杠杆 3：配方版本化 + diff（抄 Horticulture-Assistant 的四件套）
- **做什么**：Env Recipe 增加 `revision_history: [{rev, changed_by, changed_at, diff_summary}]`，实现 `export_recipe / import_recipe / diff_recipe / clone_recipe` 4 个 Skill，并在 MCP 暴露为工具。
- **为什么**：`Horticulture-Assistant` 的 export/import/diff/version 四件套是"配方作为可迁移资产"的最小完备集。我们要做"结果回流校准"，就必须能 diff 出"哪一版配方产生了哪个结果"。
- **工作量**：**中**（diff 算法用 stdlib `difflib`，零依赖可行）。
- **零依赖影响**：**无**（`difflib` 是标准库）。

### 杠杆 4：移植 agroclim 的无霜期/积温函数集（ROI 最高）
- **做什么**：用纯 Python 实现 `gdd(tmin, tmax, base=10)`、`frost_days`、`first_frost`、`last_frost`、`frost_prob`（历史概率）、`bedd`、`warm_month`、`cold_month`；再按 vegperiod 的 ETCCDI 法实现生长季起止判定，与现有 WOFOST 积温做**双方法交叉校验**。
- **为什么**：`agroclim`（MIT）+ `vegperiod`（GPL-3+，需从 Menzel 1997 / Walther & Linderholm 2006 论文重新实现）+ `cropgrowdays`（MIT，注意 `day_of_harvest` 跨年细节）提供了完整且已验证的函数清单。单一 WOFOST 方法是已知弱点。
- **工作量**：**中**（15 个函数，每个 10–30 行）。
- **零依赖影响**：**无**（纯算术）。

### 杠杆 5：MCP 工具分层重构（formatter / handler / data-lib 三层）
- **做什么**：把 `mcp/server.py` 拆成 `mcp/`（适配层，只有 JSON-RPC 路由）+ `core/data_sources/`（数据获取，可独立测试）+ `core/formatters/`（LLM 友好输出格式）。集成测试可独立跳过（学 `agrobr-mcp` 的 `pytest -m "not integration"`）。
- **为什么**：`MCP_USDA_Server` 的 `tools/` + `handlers/` + `formatters/` + `routers/` 分层和 `agrobr-mcp` 的"薄 wrapper + 独立库"，都证明单文件 server.py 在工具数超过 9 个后会失控。我们已有 9 个工具，正好到临界点。
- **工作量**：**中**（重构，不改对外接口）。
- **零依赖影响**：**无**。

### 杠杆 6：PlantDoc 接入，作为 PlantVillage 的合规补位
- **做什么**：在病虫害视觉诊断中并行加载 PlantDoc（CC BY 4.0）作为第二数据集，特别是真实场景图（非白底）样本，用于验证 PlantVillage 冷启动模型在自然光照下的表现。
- **为什么**：PlantDoc 明确 CC BY 4.0（三处交叉确认），可商用；其图像分布与 PlantVillage 互补（真实场景 vs 棚拍）。
- **工作量**：**中**（需下载 + 特征对齐）。
- **零依赖影响**：**无**（只是数据）。

### 杠杆 7：AgriTrust 溯源增强——sources 增加 trial_location + data_quality
- **做什么**：`sources[]` 每项增加 `trial_location`（试验地点/州县，学 OpenAgData 的 geolocate 思路）、`data_quality`（`measured | interpolated | modeled | estimated`，学 SILO 的 source code 字段）、`source_license`（每条来源独立许可，因为现在只有 recipe 级 license）。
- **为什么**：FAOSTAT 是 NC、PlantVillage 无 license、天池是 NC——**混合许可下必须有逐条来源许可字段**，否则整包无法确认可商用范围。这是法律刚需，不是优化。
- **工作量**：**小**。
- **零依赖影响**：**无**。

### 杠杆 8：MCP 注册到 LobeHub / Glama 分发渠道
- **做什么**：把我们的 MCP 提交到 LobeHub MCP Marketplace（农业类已有 10+ 条目，多个标"Unvalidated"，占位空间大）与 Glama。
- **为什么**：扫描确认 MCP 的实际发现渠道是 LobeHub / Glama / mdskills，**不是 GitHub trending**。不注册 = 不可见。
- **工作量**：**小**（填写索引元数据）。
- **零依赖影响**：**无**。

---

## 9. 不建议做的事

1. **⛔ 不要接入 OpenFarm API 或其任何运行时依赖。** 2025-04-21 服务器关停、2025-04-22 仓库归档只读。可取其冻结数据作 bootstrap，但任何运行时调用都会失败。**这是 OpenFarm 官方留下的最清晰警告。**
2. **⛔ 不要把 FAOSTAT 数据作为付费资产转售。** 其许可是 CC BY-**NC**-SA 3.0 IGO（NC = 非商用）。可作为溯源引用，不能作为高级配方包的付费组件。
3. **⛔ 不要复用 PlantVillage 上游的"CC0"声称。** HuggingFace/Meta-Album/Kaggle 的 CC0 声明在源仓库中找不到依据（原仓库无 LICENSE 文件）。商用路径必须走 PlantDoc（CC BY 4.0）或联系 EPFL 作者。
4. **⛔ 不要抄 vegperiod 的代码，只能抄算法。** 它是 GPL-3+，会传染本项目。三种生长季判定法（ETCCDI / NuskeAlbert / Ribes uva-crispa）须从 Menzel 1997、Walther & Linderholm 2006、Janssen 2009 三篇公开论文重新实现。
5. **⛔ 不要在零依赖约束下追求 CNN 级病害诊断精度。** 本扫描未发现"纯 Python 标准库 + 可用"的植物病害视觉模型。手写 CNN 前向的工作量"大"且精度远逊迁移学习。**应走"颜色直方图/纹理统计 → 可解释规则判定"路线**，这与已有的证据门控零误报定位完全一致，且可解释性是竞品没有的优势。
6. **⛔ 不要做通信层（LoRaWAN/MQTT 网关）。** Scineer 论文的"感知-通信-决策-执行"五维框架里，通信层已被大厂（海尔、小米）占据，我们的壁垒在决策层（知识底座 + Env Recipe）。做通信层 = 用短板打别人长板。
7. **⛔ 不要接 Open Food Network / farmOS 作为组件。** 前者 AGPL-3.0、后者 GPL-2.0+，都是传染性许可，且分别是交易平台和记账系统，与本项目的"配置层"定位无交集，只有许可风险没有功能收益。
8. **⛔ 不要做"专业农艺师界面"。** 市场数据显示购买理由是情绪价值（"每天下班看看那盆菜长了没有"），不是产量优化。界面应是成长日志/日历，不是参数仪表板。
9. **⛔ 不要依赖 OADA 的 OAuth 2.0 体系。** 它适合"农场数据所有权"场景，对纯本地单机部署过重；抄它的 JSON Schema formats 做法即可，不必引入 OAuth。
10. **⛔ 不要推荐 ESA WorldCrops（已归档）和 EarthCereal 卫星方案作为主路径。** WorldCrops 仓库已归档（23★，MIT）；WorldCereal 虽活跃但 10m 卫星遥感是大田尺度工具，与本项目明确暂缓的"大田/L1"冲突。

---

## 10. 待核实清单

以下信息未在扫描中 100% 确认，使用前必须人工复核：

1. **`Horticulture-Assistant` 的 license 具体条目** —— README 有 License 章节但扫描未读到具体条目（MIT? GPL?）。若要抄其 profile 设计，需确认传染性。
2. **`OpenGrowBox-HA`、`HA-Plant-Assistant`、`simple-plant-extended` 的 license** —— 均标"待核实"，README 未见明确条目。
3. **`MCP_USDA_Server` 的 license** —— 仓库未读到 LICENSE 文件。
4. **`CropProphEU` 的 license** —— 仅见 dev.to 博文，未见仓库 LICENSE。
5. **`agrisignal-mcp` 与 `Agricultural Commodity Climate MCP` 的源码细节** —— 仅通过 LobeHub 索引获得描述，未直接读到源码。索引标"Unvalidated"，star 数与工具清单不可信。
6. **`agrisignal-mcp` 的 star 数（LobeHub 显示 3）** —— 与 GitHub 实际值可能不符，索引数据时效性差。
7. **OpenSprinkler 的 license 冲突** —— PiStack 比较文称"CC BY-SA 4.0"，但实际仓库显示固件 GPL-3.0 / App AGPL-3.0 / 硬件 CERN-OHL-S-2.0。**以仓库为准**，比较文有误。同类错误：该文称 MudPi 为 MIT，实际是 **BSD-4-Clause**。
8. **PiStack 比较文的所有 star 数** —— 该文显示 OpenSprinkler 540★ / OSPi 415★ / AIS 769★，与仓库实际值（554★）已有偏差，整篇数字不宜直接引用。
9. **GAEZ v4 与 WorldClim 的商用条款** —— 本项目已有但本次未复核。GAEZ 需注册，WorldClim 部分数据集收费，商用范围需查原始条款。
10. **天池 rice disease 的实际数据规模** —— 页面显示"3-class-riceleafdisease (40 per class)"但文件名截断，实际类别数与总量待下载确认。
11. **"VGG Plant Disease 数据集"** —— **本扫描未发现此名称的独立数据集**。检索到的"VGG"均指 VGG16/VGG-16 模型架构（如 AGRIFOLD 用 VGG16+ECA），不是数据集。任务清单中的此项疑似概念混淆，建议删除。
12. **"CropX"** —— 任务清单中的此项**未能核实为真实开源项目**。找到的是同名商业公司（IoT 农业传感器），非开源数据项目。建议删除。
13. **"LandGEM 土地生产力模型"** —— 任务清单中的此项**是错的**。LandGEM 是 **US EPA 的 Landfill Gas Emissions Model**（填埋场气体排放 Excel 工具，v3.1，2024 更新），与农业/土地生产力无关。建议从调研清单中删除，避免污染调研结论。
14. **"Plantower 温室控制"** —— 同"LandGEM"：同名项目全部是 Plantower PM 空气质量传感器库（cristeab/plantower MIT、e7h4n/node-plantower ISC、FEEprojects/plantower），**不存在名为 Plantower 的温室控制系统**。
15. **PlantVillage 的实际商用可行性** —— 结论是"无 license，需联系 EPFL 作者"。若需确认作者当前立场，可邮件 sharada.mohanty@epfl.ch / Marcel.Salathe@epfl.ch（仓库 README 中的作者邮箱，注意第一个邮箱已疑似失效）。
16. **Scineer 论文的 58.02 亿元数据来源** —— 该论文引用"中国农机工业协会 2025 年报告"，但原报告未找到公开全文。置信区间 [49.32, 66.72] 亿是论文自算，建议交叉验证。
17. **"千亿级赛道"（武汉农业集团可行性研究）** —— 该数字来自单一企业提供的可行性研究，未见独立第三方验证，量级与 Scineer 论文的 58 亿元差距大（可能口径不同：前者含种苗+基质+设备+服务全链条，后者仅"智能系统"）。引用时需注明口径。
18. **`openag-device-software` 的 recipe JSON 具体结构** —— 已知仓库存在（195★，GPL-3.0，2026-03-02 更新），但**本扫描未读到其 recipe 定义的具体字段**。杠杆 1/2 的字段建议基于 OpenAg 公开文档的"climate recipe"描述，未基于源码逐字段对照。**这是杠杆 1 的前置工作**。
19. **`worldcereal-cropcalendars` 的 calendar 数据结构** —— 仅知仓库存在（1★，MIT，2026-04-21 更新），未读到 schema。
20. **`awesome-mcp-servers`（DasClown）的收录门槛** —— 若要注册 MCP，需确认其收录标准。

---

## 附录：本次扫描核实的 URL 清单

FAOSTAT · https://www.fao.org/faostat/en
FAOSTAT API 门户 · https://fenixservices.fao.org/faostat/api/v1
FAOSTAT Bulk Catalog · https://bulks-faostat.fao.org/production/catalog.json
OpenAgData · https://open-ag-data.com/about
OADA · https://github.com/OADA
ESA WorldCrops（已归档）· https://github.com/ESA-PhiLab/WorldCrops
ESA WorldCereal · https://github.com/ESA-WorldCereal · https://esa-worldcereal.org
Open Farm Network · https://github.com/openfoodfoundation/openfoodnetwork
farmOS · https://farmos.org · https://github.com/farmOS/farmOS
OpenSprinkler · https://github.com/OpenSprinkler
OpenFarm（已归档 2025-04）· https://github.com/openfarmcc/OpenFarm
OpenFarm 关停公告 · https://farm.bot/blogs/news/sunsetting-openfarm
OpenAgInitiative（已清空）· https://github.com/OpenAgInitiative
OpenAgricultureFoundation · https://github.com/OpenAgricultureFoundation
openag-device-software · https://github.com/OpenAgricultureFoundation/openag-device-software
MIT PFC 项目页 · https://www.media.mit.edu/projects/personal-food-computer/overview/
Horticulture-Assistant · https://github.com/TraverseJurcisin/Horticulture-Assistant-HASS-REPO
OpenGrowBox-HA · https://github.com/OpenGrow-Box/OpenGrowBox-HA
HA-Plant-Assistant · https://github.com/shortmanflee/HA-Plant-Assistant
simple-plant-extended · https://github.com/jo-anb/simple-plant-extended
MudPi · https://github.com/mudpi/mudpi-core
FarmerConnect-MCP · https://github.com/adr1en360/FarmerConnect-MCP
agrobr-mcp · https://github.com/bruno-portfolio/agrobr-mcp
MCP_USDA_Server · https://github.com/AntonioPavoni/MCP_USDA_Server_Quantized
LobeHub MCP Marketplace · https://lobehub.com/mcp?q=农业
PlantVillage · https://github.com/spMohanty/PlantVillage-Dataset · https://huggingface.co/datasets/mohanty/PlantVillage
PlantDoc · https://github.com/pratikkayal/PlantDoc-Dataset
Corn Leaf Disease · https://www.kaggle.com/datasets/ndisan/corn-leaf-disease
天池 rice disease · https://tianchi.aliyun.com/dataset/125957
AGRIFOLD · http://github.org/MODAL-UNINA/AGRIFOLD
agroclim · https://github.com/sherlg/agroclim
vegperiod · https://cran.r-project.org/web/packages/vegperiod/refman/vegperiod.html
cropgrowdays · https://gitlab.com/petebaker/cropgrowdays
Open-Meteo · https://open-meteo.com · https://github.com/open-meteo/open-meteo
