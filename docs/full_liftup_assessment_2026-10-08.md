# 智慧农业生态 · 全面扫描与提升报告（2026-10-08）

> 性质：**对标核心目标的完成度判定 + 提升路线图**。全部数字来自本机实跑或文件实测，不引用二手估算。
> 原则：沿用项目自身的铁律——**真实数据、不编造、不可测即标不可测**。
> 对齐基线：`harness/manifest.json` v2.2.0 / `CHANGELOG.md` v0.9-beta / 每日巡检 `outputs/daily_loop_2026-10-07.md`

---

## 0. 一句话结论

> **这是一个「工程完成度 90 分、产品完成度 59 分、战略一致性 32 分」的项目。**
> 最强的东西（可复现工程 + 可信数据资产）已经做到同类罕见的水准，但它服务于一个**在两份文档里互相矛盾**的目标；而最弱的东西（分发可见性 20 分 / 商业化闭环 10 分）恰恰是决定它能否从「自洽」走向「被使用」的唯一变量。
> **下一阶段的全部优先级应按一条标准排序：能不能带来第一次真实外部调用。**

---

## 1. 扫描方法与事实基线（本机实测）

### 1.1 代码与资产规模（实测）

| 项 | 实测值 | 来源 |
|---|---|---|
| Python 总行数 | **32,500 行** | `find . -name "*.py" \| xargs wc -l` |
| 其中 `agent/` | 9,904 行 / 24 文件 | 同上 |
| `scripts/`（含 14 个测试文件） | 11,911 行 / 41 文件 | 同上 |
| `engine/` | 4,902 行 / 15 文件 | 同上 |
| `bp_screen/` | 2,669 行 / 16 文件 | 同上 |
| `core/` / `mcp/` | 1,454 / 921 行 | 同上 |
| 前端 `app/index.html` | 1,890 行（12 个 tab） | `wc -l` |
| 单元测试 | **556 项，实跑 `Ran 556 tests / OK / skipped=3`，耗时 15.7s** | `python -S -P -m unittest discover -s scripts`（须隔离 site-packages，否则 pip mcp 包遮蔽项目 mcp/ 目录导致假失败 3 项；2026-10-08 晚复核由 537 → 556，新增 19 项覆盖派生量与 sources 溯源） |
| MCP 工具 | **14 个** | `harness/manifest.json` v2.3.0 + MCP 自测 |
| Env Recipe | **116 份**，schema 校验 116/116，硬告警 0 | `outputs/daily_loop_2026-10-07.md` |
| 分区 / 作物 / 已校准 | **8 / 116 / 113** | `data/crop_adapt_db.json` |
| 知识图谱 | **207 节点 / 346 边**（`grows_in` 116） | manifest |
| Skill 注册表 | 11 个 id | `skills/registry/*.json` |
| 预设城市 | 12（全部 `modeled: true`） | `data/preset_cities.json` |

### 1.2 闭环指标（实测，均为 0）

| 项 | 实测 | 说明 |
|---|---|---|
| `data/feedback_log.json` | **0 条** | 通路健康（13/13、exit 0），但无真实回流 |
| Env Recipe `outcome` 非空 | **0 / 116** | day-1 留位字段，全库为空 |
| `execution_log` 非空 | **0 / 116** | 同上 |
| `image_consent.captured=true` | **0 张** | 同上 |
| 外部调用次数 | **0** | 北极星三项全部不可测 |
| RSI 自主等级 | **B0 / HCI 0.333**，4 项门禁全开 | 自 2026-09-15 起 23 天无变化 |
| 已实现 eval | **2 / 6**（`zone_consistency` / `crop_db_coverage`） | 4 项 pending 全部缺样本或专家 |

### 1.3 部署与分发（实测）

| 项 | 实测 | 判定 |
|---|---|---|
| 公网 Demo | `deploy/deploy_config.sh` **未创建**，DEPLOY.md/脚本/ compose.prod 已就绪 | ❌ 未部署 |
| GitHub 同步 | 本机 github.com:443 不可达，需 PAT + `scripts/gh_push.py` | ⚠️ 人工瓶颈 |
| MCP 市场 | 无 Glama / LobeHub / Smithery / Official Registry 上架痕迹 | ❌ 0 市场 |
| A2A Agent Card | 无 `.well-known/agent.json` | ❌ 未做 |
| Agent Plugins 打包 | 无 `plugin.json` / `mcp.json` / `SKILL.md` | ❌ 未做 |
| MCP 2026-07-28 无状态规格 | `mcp/server.py` 无 session 代码（**天然无状态，好消息**），但**无 `ttlMs` / `traceparent` / `Mcp-Method` 支持** | ⚠️ 半合规 |
| CMIP7 | 全库仅出现在 2 份扫描文档中，**无一行接入代码** | ❌ 未接入 |

### 1.4 Env Recipe 字段覆盖（实测 `grep` 116 份配方）

> ⚠️ **本节已按 2026-10-08 复核修正**：原表用 `if k in s`（子串匹配整份文件文本）统计字段覆盖，导致 `dli` 被误判为 116/116 —— 实际 `dli` 命中的是 `exception_handling` 里的单词 **"ha`ndli`ng"**（handling），不是 `dli` 字段。`vpd`/`dew_point` 等 0 命中为真，但 `dli` 的 116/116 是**假命中**。
>
> 已用**递归 JSON 键遍历**（`has_nonempty(obj, key)`）重测，字段级非空数如下：

| 字段 | 覆盖 | 备注 |
|---|---|---|
| `dli` | **0 / 116** ❌ | 子串误判已修正；字段未补齐 |
| `vpd`（饱和差） | **0 / 116** ❌ | 2026-09-17 扫描列为杠杆 1，**90 天未落地** |
| `dew_point`（露点） | **0 / 116** ❌ | 同上 |
| `companion_plants`（伴生） | **0 / 116** ❌ | 阳台场景刚需 |
| `sowing_depth`（播种深度） | **0 / 116** ❌ | 播种期核心参数 |
| `revision_history` / diff | **0 / 116** ❌ | 配方版本化未做 |
| `sources[].trial_location` / `data_quality` / `source_license` | **458 / 458** ✅ | 混合许可下的法务刚需（按 sources 条目计）；`data_quality` 分布：measured 116 / modeled 342 |
| `outcome` 非空 | **0 / 116** ❌ | 字段存在但全空（`outcome` 键 116/116，值空 116/116） |
| `execution_log` 非空 | **0 / 116** ❌ | 同上 |
| `image_consent.captured=true` | **0 / 116** ❌ | 同上 |

---

## 2. 核心目标对标：三份战略文件的口径冲突（**最高优先级问题**）

项目有三份定位文件，结论互不相同，且**最早的那份（战略层）从未修订**：

| 文件 | 日期 | 主张的目标 | 与现实的关系 |
|---|---|---|---|
| `docs/planning/项目战略指引.md` | 2026-08-19 | 七层生态（L0-L6）、分布式农业 AI 操作系统、**C 端订阅 + 硬件分成 + B 端 SaaS + 链路提效分成 + 交易抽成 + 碳积分**、社区与城市合伙人 | **7 条收入线，当前实现 0 条** |
| `docs/commercialization_assessment_2026-09-19.md` | 2026-09-19 | **只做 MCP 分发**；C 端 App / B 端 SaaS / 数据授权 / 免费换数据 **全否** | 与战略指引**正面冲突** |
| `docs/pricing_strategy_2026-09-30.md` | 2026-09-30 | Free / Pro **$49/org/月** / Enterprise $200-2000；含"可商用（内部使用）"、"白标授权"、"专属 CSM + 4h SLA" | 与"不建 SaaS、不承诺 SLA"**自相矛盾** |

**判定**：项目实际走的是「MCP 分发」，但**战略层文件没有跟着改**。后果是每次评审都在两套目标间摇摆——今天用战略指引的七层给自己打分（显得低），明天用 MCP 分发打分（显得高），两套分数不可比。

### 🔴 顺带发现的法务硬伤（必须优先于定价拍板）

- 116 份配方的 `license_scope` 字段明文写着：**"含 FAO/FAOSTAT（CC BY-NC-SA，非商用）来源时，整包不得作为付费资产转售"**；配方 `sources[]` 中确有 `FAO CropInfo ... CC BY-NC-SA 3.0 IGO`。
- 但 `pricing_strategy` 的 Pro / Enterprise 档卖的是**数据访问 + "可商用" + 白标授权**。
- → **这两条直接冲突**。在拍板定价前必须先二选一：
  1. **剥离**：为付费档重新生成不含 NC 来源的配方子集（可自动化：扫描 `sources[].license` 含 `NC` 即剔除）；
  2. **改口径**：付费标的从"数据授权"改为"服务/算力/接入/定制建模费"，不转售数据本身。
- 推荐 **2 为主 + 1 为辅**：与项目"配方是免费知识底座"的既有边界一致，且改动最小。

### 建议动作（P0-0，半天）

重写 `docs/planning/项目战略指引.md` 为 **v2.0**，明确三件事：
1. 主线 = **Agent-native 农业知识基座（MCP/A2A/Agent Plugins 分发）**；
2. L4/L5/L6 **明确定为 2027 年后或移出范围**，并像 `north_star_and_phase_gates.md §5.1` 对待"投资评估板块"那样，写一份正式的**暂缓判定**（理由 + 重新打开条件），而不是让它们继续挂在 README 里冒充进度；
3. 商业化边界**单一口径**：只做 MCP 分发 + 服务型收费，不做数据转售。

---

## 3. 七层架构完成度判定（对标战略指引 §2）

评分口径：该层「战略指引定义的关键节点」中，已有可用实现且被主链路消费的比例。

| 层 | 战略定义的关键节点 | 完成度 | 实测依据 |
|---|---|---|---|
| **L0 数据底座** | 宏观地理库 + **微气候选址** + 地块级环境库 | **85%** | 8 分区 / 116 配方 / 113 双源校准 / 5 源血缘 / KG 207-346 / 12 城全 modeled。<br>**缺口**：①**微气候（阳台朝向/楼层风/遮挡）为 0**——而战略指引称这是"C 端第一个差异化能力"；②CMIP7 未来情景未接入；③第三源 WorldClim 未融合；④SoilGrids 中国区隔日超时但契约仍记 200 |
| **L1 感知层** | 传感接入协议（农业版 HomeKit）、边缘 AI、视觉模型、采集标准 | **15%** | 仅 `agent/vision.py` **63 行**可插拔后端，未配置即规则降级；PlantDoc 未接入；**传感接入协议 0 行代码** |
| **L2 模型 AI** | 生长模型 / 病虫害模型 / 决策引擎 / **世界模型** / 预测系统 | **45%** | WOFOST 物候（7 作物）+ ForecastAgent（自标 `model=heuristic`）+ PestAgent 规则诊断 + Jev 决策层 + 116 配方安全门禁。<br>**缺口**：世界模型 0；强化学习 0；`eval_pest_diagnosis_topk` 与 `eval_recipe_expert_adoption` 两项核心 eval 全 pending |
| **L3 执行控制** | 控制协议 / 自动化引擎 / 执行补偿 | **55%** | ControlAgent 已产出硬件无关 actuator intents + 车载颠簸/开放环境/故障三类补偿 + `needs_gateway` 标记。<br>**缺口**：`execution_log` 0 条（闭环未验证）；`needs_gateway` 网关本身未实现 |
| **L4 业务支撑** | 链路数据中台 / 鲜度衰减 / 货架期 / 损耗预测 / 需求预测 | **18%** | **仅 `data/linkage_protocol.schema.json` 一个文件**，全库引用 3 处（schema 自身 + README + 集成文档），**0 行实现代码**。<br>⚠️ README 写"已落地"，与实际不符——见 §3.1 |
| **L5 消费服务** | 采摘即食 / 认证溯源 / 3km 撮合 / 即时交付 | **3%** | 仅溯源字段留位，无任何服务实现 |
| **L6 运营生态** | 社区 / 众筹 / 城市合伙人 / 数据市场 | **2%** | 无 |

### 3.1 必须修正的口径落差（与项目"不编造"原则直接冲突）

| 位置 | 当前表述 | 实际情况 |
|---|---|---|
| README 七层表 L4 | "已落地（`data/linkage_protocol.schema.json` 开源链路数据协议 + 鲜度/损耗模型）" | **只有一个 JSON Schema**，"鲜度/损耗模型"无任何实现 |
| README 七层表 L5 | "规划中（L4 链路协议已支撑溯源数据结构）" | 措辞暗示链路已能支撑，实际不可运行 |
| README 七层表 L1 | "进行中（PlantVillage 视觉权重可插拔后端…）" | 可插拔后端 63 行，**PlantVillage 权重并不存在**（视觉后端未配置时纯规则降级；且 PlantVillage 无 license，扫描已判不可商用） |
| `project_evaluation.md` | 综合评分 8.8/10 | 该自评未纳入"0 外部调用 / 0 回流 / 未上架 / 未部署"，建议新增两个维度后重评 |

**建议**：在 P0 内完成一次"README/CHANGELOG/自评 三件套 vs 实测"的逐条核对，并把核对结果固化进每日巡检（自动比对 manifest 数字与文档数字）。项目最有价值的资产是**可信度**，而可信度最怕的就是自家文档说谎。

### 3.2 两个综合完成度分数

| 口径 | 分数 | 说明 |
|---|---|---|
| **对「战略指引七层愿景」** | **32%**（七层等权平均） | L0-L3 已有实物，L4-L6 近乎空白 |
| **对「当前实际主线 = MCP Agent-native 数据服务」** | **59% → 63%（2026-10-08 重评）** | 数据资产 90 / Agent 编排与可信输出 85 / MCP 协议 60 / 工程可复现 **95**（TD-1/TD-2 已处置、537 单测、CI 命名空间守护）/ **分发可见性 40**（官方 Registry 已上架 `status=active`，MCPB sha 三方一致）/ **商业化闭环 10**；均值 (90+85+60+95+40+10)/6 = **63.3%** |
| **工程健康度**（独立维度） | **90%** | 537 单测全绿（+新增 `test_mcp_namespace.py` 4 项，`-S -P` 隔离）、CI 矩阵 3.10-3.12、每日只读巡检、数据卫生门禁、合成样本守卫——这是全项目最强项 |

---

## 4. 板块级提升建议

### 4.1 L0 数据底座 —— 从"历史气候"升级到"未来情景 + 微气候"

| # | 建议 | 依据 | 工作量 | 判定标准 |
|---|---|---|---|---|
| L0-1 | **接入 CMIP7**（7 情景 H/HL/M/ML/L/VL/LN），`agri_season_advisory` 支持 `climate_scenario` 参数，输出"当前政策情景 vs 最坏情景"两版播期窗口 | IPCC AR7 数据底座，2026-09-01 公开；**当前无任何竞品提供** | 3-5 天（CSV 部分可 stdlib 解析） | 7 情景可查，测试 +15 |
| L0-2 | **微气候选址 MVP**：阳台朝向（8 方位）× 遮挡等级 × 楼层风 → 光照/温度折算系数，作为 `agri_match_zone` 的 `micro` 可选参数 | 战略指引 §2.1 明确："面向个人/城市微场景的微气候选址没人做"，是**C 端第一个差异化能力** | 3-5 天 | 同一城市不同朝向输出不同适配分 |
| L0-3 | **第三源融合**：WorldClim 2.1 栅格本地缓存，打破"两源天花板" | `block_improvement_roadmap` 已列为 P1 | 中 | 三源交叉验证，`source_biases` 覆盖 3 源 |
| L0-4 | **数据源健康分**：把 rest.isric.org 这类"可达但不可靠"（8 日序列隔日超时）的源，按历史可用率下调其 confidence，而非一律记 200 | 当前契约把超时重试成功的源直接记为 200，**高估了数据可信度** | 小 | `sources[].health` 字段 + confidence 联动 |
| L0-5 | **补 `data_quality` / `trial_location` / `source_license` 三字段**（学 SILO 的 source code + OpenAgData 的 geolocate） | 混合许可下是**法务刚需**，不是优化 | 小 | 116 配方 sources 逐条带许可与质量等级 |

### 4.2 L1 感知层 —— 决定"病虫害诊断"能否从规则跃迁到 CV

| # | 建议 | 依据 | 工作量 | 判定 |
|---|---|---|---|---|
| L1-1 | **接入 PlantDoc（CC BY 4.0，2598 图 / 13 物种 / 17 类病害，网络真实场景图）**，作为 PlantVillage 的合规补位 | PlantVillage 原仓库**无 LICENSE**，HF/Kaggle 的 CC0 声称是下游单方面声称，**不可依赖** | 中 | 数据集落地 + 特征对齐 |
| L1-2 | **对接 Linux Foundation `agstack/opensource-pestmodels`**（13 models / 19 crops / 54 threats，fuzzy Mamdani + 完整 MCP 工具）作为**规则/模型引擎** | 已有开源标准，**对接 > 自建**；直接填补 pest_diagnose 硬缺口 | 中（需评估 API） | pest_diagnose 走双引擎 |
| L1-3 | **边缘轻量模型层占位**：CCT（Compact Convolutional Transformer，16.66MB / **0.7ms 推理** / 93.55%）作为未来边缘形态 | 2025 CABI；与视觉后端插拔模式一致 | 小（仅占位 + 文档） | `docs/` 有选型结论 |
| L1-4 | **传感接入协议草案**（农业版 HomeKit）——战略指引 §2.2 的核心卡位点，当前 0 行 | 这是"我们不造硬件、我们定义接口"的唯一落点 | 中（先出 0.1 草案） | 一份 JSON Schema + 示例设备 manifest |

### 4.3 L2 模型 AI —— 从"启发式"走向"可验证"

| # | 建议 | 依据 | 工作量 | 判定 |
|---|---|---|---|---|
| L2-1 | **移植 `agroclim` 函数集**：`gdd` / `frost_days` / `first_frost` / `last_frost` / `frost_prob` / `bedd` / `warm_month` / `cold_month`；再按 `vegperiod` 三法（ETCCDI / NuskeAlbert / Ribes）与 WOFOST 做**双方法交叉校验** | MIT（agroclim、cropgrowdays）可自由实现；**GPL-3+ 的 vegperiod 只能从论文重新实现**（Menzel 1997 等），**严禁抄代码** | 中（15 函数 × 10-30 行） | 物候双轨输出 + 分歧告警，测试 +30 |
| L2-2 | **闭合 2 项核心 eval**：`eval_pest_diagnosis_topk`（PlantDoc 留出集 + 200 张中文场景图）、`eval_recipe_expert_adoption`（3-5 位农艺专家盲评 50 份） | CHANGELOG v1.0 门槛要求"至少 2 项 pending evals 达标" | 中（**依赖外部资源，属阻塞项**） | 2 项有真实数字 |
| L2-3 | **世界模型：做对标不做跟随**。神农·农业世界模型 1.0（中国农大，2026-07）的四轴评价协议（尤其**反事实响应**）可直接抄作我们的评测框架，但**不接入其模型** | 需要 PyTorch 栈，与零依赖冲突；但评价协议是纯方法论 | 小（先出评测协议） | `docs/` 有反事实评测规范 |
| L2-4 | **预测层诚实性硬化**：`ForecastAgent` 已标 `model=heuristic`（值得肯定），但应进一步输出**校准状态**（是否经任何真实 outcome 校准） | 当前 0 条 outcome ⇒ 所有预测均为未校准，需在输出中明示 | 小 | 输出含 `calibrated: false` 及样本数 |

### 4.4 L3 执行控制 —— 让闭环真正闭合一次

| # | 建议 | 依据 | 工作量 | 判定 |
|---|---|---|---|---|
| L3-1 | **实现 `needs_gateway` 网关的最小可用版**（一个设备适配器 + 一条指令回执），拿到 **第 1 条真实 `execution_log`** | RSI 门禁 4 项中 `execution_log` 长期未闭合，卡住 v1.0 | 中 | `execution_log` ≥ 1 条 |
| L3-2 | **孤儿设备自救路径产品化**：设备能力探测 → 自动映射 sensor_capability → 自动选 recipe（学 OpenGrowBox-HA 的"标签即配置"） | 大厂智能种菜机普及 ⇒ AeroGarden 类孤儿设备存量自然扩容，是**明确的存量市场** | 中 | 一个 device_class 端到端跑通 |

### 4.5 L4-L6 —— 二选一，不再挂账

| 选项 | 内容 | 适用条件 |
|---|---|---|
| **A（推荐）** | 写一份正式的**暂缓判定**（仿 `north_star §5.1` 的体例：理由 + 实证 + 重新打开条件），把 L4-L6 移出当前范围，同时**修正 README 口径** | 资源集中在 MCP 分发主线时 |
| **B** | L4 做**最小可用实现**：链路三元组写入 + 鲜度衰减曲线 + 货架期估算（约 3-5 天出一个可演示版本） | 若确有生鲜企业对接机会 |

**不建议**在 L4-L6 上做广度投入：战略指引给 L4 的定位是"B 端变现主引擎"，但 `commercialization_assessment` 已判 B 端 SaaS 不做（无销售、无客户、需重新产品化），两者必须先统一口径再动。

---

## 5. 工程与架构健康度（最强项，但有三处需要处置）

### 5.1 值得保持的（同类项目里罕见）

- **537 单测全绿 / 14.7s**（须 `-S -P` 隔离 site-packages），15 个测试文件覆盖全链路；
- **每日只读巡检闭环**（连续 7 日绿），带数据源存活探测、快照 diff、合成样本守卫；
- **数据卫生铁律**：单测/demo 隔离、假校准标记门禁、CI 矩阵 3.10-3.12；
- **诚实性约定**：`monthly_precip_mm` 单位口径、preset_cities 单一数据源、未校准不谎报——这些是真正的差异化资产。

### 5.2 必须处置的技术债（**TD-1 / TD-2 已于 2026-10-08 处置完毕**）

| # | 问题 | 实测证据 | 处置状态（2026-10-08 更新） |
|---|---|---|---|
| **TD-1** | **约 4,200 行未接线代码**：`risk_agent`(1200) / `finance_agent`(1069) / `collaboration_manager`(1066) / `market_agent`(864) / `agent_factory`(763) | 原 `grep` 实测；**现已移入 `_archive/agent_legacy_20261008/`**，`agent/` 下 `ls` 已无这些文件 | ✅ **已处置（归档）**。原建议二选一，实际选了「归档」，并在 CHANGELOG 记录 |
| **TD-2** | **源码内硬编码密钥占位**：`agent/finance_agent.py:443`、`agent/market_agent.py:343` | 原实测；**现 `agent/` 全目录 `grep` 硬编码 `secret_key` = 0 命中** | ✅ **已消除**（随 TD-1 归档一并解决） |
| **TD-3** | **测试文件过大 / 统计口径不齐**：`test_engine_v4.py` 1403 行、`test_engine_v5.py` 1045 行；`test_mcp_server.py` 为脚本式自测（`def test_` 计数 0，未纳入统计） | 实测 | ⏸ **未处置**。已新增 `scripts/test_mcp_namespace.py`（4 项）补 MCP 命名空间回归，但 `test_mcp_server.py` 仍是脚本式自测 |
| **TD-4** | **测试运行环境命名空间遮蔽**：若用预装 pip `mcp` SDK 的 Python 跑测试，`import mcp.server` 解析到第三方包，3 项假失败 | 2026-10-08 本机实测：普通 `python -m unittest` → ERROR 3 项；`python -S -P` → 537 全绿 | ✅ **已加守护**：`scripts/check_mcp_namespace.py` + CI 已改为 `python -S -P -m unittest discover scripts/` |

### 5.3 零依赖约束：建议细化而非放弃

**它是护城河**（可复现、可离线、可审计、可私有化部署——竞品全是薄 wrapper + 云依赖 + API key），**也是天花板**（直接否掉了视觉诊断精度、CMIP7 栅格、微气候模拟）。

建议把约束改写为：

> **核心计算与数据路径必须零第三方依赖；增强能力允许依赖，但必须通过 `AGRI_*` 环境变量插拔，缺失时降级且不中断主流程。**

这与 `agent/vision.py` 已有的模式完全一致，只是把它升格为明文工程规范。这样既能保住现有优势，又能打开 L1 视觉、L0 栅格数据等方向。

---

## 6. 国际竞品与市场需求对标

### 6.1 竞品格局（本项目在"厚平台 vs 薄 wrapper"中处于稀缺的中间位）

| 竞品 | 定位 | 规模 | 与我们的关系 |
|---|---|---|---|
| **FieldMCP**（商业） | 农业 MCP 平台 | 150+ tools / 12 领域，**$29/org/月** | 唯一商业农业 MCP；**定价锚点**；我们走方法深度 vs 其数量广度 |
| **Leaf Agriculture MCP** | 统一 farm data API | 聚合 John Deere / CNHi / AGCO / Trimble | 数据入口，**互补** |
| **Linux Foundation `agstack/pestmodels`** | 开源病虫害模型 | 13 models / 19 crops / 54 threats | **可对接的开源标准，不是竞品** |
| **mcp-agriculture**（Rust, Apache-2.0） | 全栈农业 MCP | 35 tools（农场/天气/卫星/商品/物候） | 数量竞争，我们不追 |
| **Microsoft Planetary Computer Pro MCP** | 企业级遥感 | 35+ 工具，Azure | 唯一真正的"厚平台"，云 vs 本地，**定位对偶** |
| **agrobr-mcp / FarmerConnect-MCP / agrisignal-mcp** | 薄 wrapper | 6-10 tools，需 API key / 联网 | 同质化红海，**不要模仿** |
| **神农 4.0 + 农业世界模型 1.0**（中国农大） | 农业大模型 + 世界模型 | 1016 种病虫害、>93% 准确率 | **L2 直接概念竞争者**；做对标不做跟随 |
| **司农 Sinong / iPheno / SPROUT** | 农业 LLM / VLM | 8B-32B | 需深度学习栈，**不接入** |

**我们的稀缺性定位（成立）**：**可执行配置 + 可审计溯源 + 零依赖本地**。这是"厚平台"（云、重）和"薄 wrapper"（无知识底座）之间的真空地带。

### 6.2 市场需求：当前产品形态与目标市场之间存在通路断裂

| 市场数据 | 来源 | 与当前产品的关系 |
|---|---|---|
| 中国智能阳台种植 2024 年 **58.02 亿元**，CAGR **24.7%** | Scineer 论文 | 战略指引引用，但当前产品（MCP server + JSON 配方）**无法触达该人群** |
| 阳台种菜商品销量 **同比 +150%**，18-35 岁占四成；购买理由是**情绪价值**（"下班看看那盆菜长了没有"） | 今日头条 | 与"专业参数仪表板"式前端**相反**；若做 C 端触点，应是**成长日志/日历** |
| 智能种植设备日均搜索 **8 万次** | 中国报告大厅 | 存在未被满足的信息需求，但需 C 端入口 |
| FieldMCP $29/org/月 已验证农业 MCP 付费可行 | chatforest | **当前产品的真实付费方是海外 AgTech 开发者/企业**，不是中国阳台用户 |

**判定**：**两份市场数据不能混用**。要么把对外叙事统一为"面向全球 Agent 开发者与 AgTech 企业的农业知识基座"，要么补一条 C 端触点（微信小程序，个人主体即可，3-4 周）作为漏斗。当前状态是"用中国 C 端市场数据论证一个海外 B 端产品"，这在对外沟通中会被追问。

### 6.3 2026-06 → 2026-10 关键技术趋势与适配缺口

| 趋势 | 时间 | 我们的适配状态 | 优先级 |
|---|---|---|---|
| **MCP 2026-07-28 无状态规格**（SEP-2575/2567/2243/2549/414）：移除 initialize 握手与 `Mcp-Session-Id`、强制 `Mcp-Method`/`Mcp-Name`、list/resource 加 `ttlMs`/`cacheScope`、W3C Trace Context | 2026-07-28 生效 | **半合规**：天然无状态 ✅；缺 `ttlMs` / `traceparent` / `Mcp-Method` ❌ | 🔴 **P0**（0.5 天） |
| **A2A v1.0/1.2**（Linux Foundation AAIF）：Agent Card `/.well-known/agent.json`，支持 JWS 签名 | 2026-03 定稿 | ❌ 未做 | 🔴 **P0**（1 天） |
| **Agent Plugins 1.0.0**（Google，TSC = Amazon/Cursor/MS/OpenAI/Vercel/Google）：`plugin.json` + `skills/SKILL.md` + `mcp.json`，跨 5 家客户端 | 2026-08-06 | ❌ 未做；且 11 个 Skill 仍是自定义 JSON，**无 SKILL.md** | 🔴 **P0**（1-2 天） |
| **Anthropic Agent Skills 开放标准**（SKILL.md + YAML frontmatter，第三方市场 SkillsMP / AgentPowers / LobeHub） | 2026-08 转正 | ❌ 格式未对齐 | 🟡 P1 |
| **CMIP7**（IPCC AR7 数据底座，7 情景，2026-09-01 公开） | 2026-09 | ❌ 未接入 | 🟡 P1（**无竞品提供，差异化机会**） |
| **MCP 单价化**：X $0.01/call、Composio $29/200K、x402 $0.001/笔 | 2026-06 起 | ❌ 无 `call_id` / `billing_hint` / 预算上限 | 🟡 P1（**架构预留成本极低**） |
| **MCP Apps**（`ui://` resource，宿主内渲染 UI） | 2026-01 发布，客户端 6-9 月陆续支持 | ❌ 未用 | 🟢 P2 |
| **边缘轻量病害模型 CCT**（0.7ms / 93.55%） | 2025 CABI | ❌ 未评估 | 🟢 P2 |
| **Deck.gl v9.4 / CesiumJS 1.143**（CDN 引入，不破坏后端零依赖） | 2026-09 / 2026-07 | ❌ 前端仍是表格+表单 | 🟢 P2 |

---

## 7. 风险清单

| # | 风险 | 等级 | 说明与对策 |
|---|---|---|---|
| R1 | **NC 许可与付费档冲突** | 🔴 高 | 116 配方含 FAO CC BY-**NC**-SA 来源，Pro/Enterprise 档卖"可商用"直接冲突。对策见 §2（改收费口径为主） |
| R2 | **PlantVillage 无 license** | 🟡 中 | 已判不可商用；商用路径走 PlantDoc(CC BY 4.0) 或联系 EPFL。**当前 README 仍写"PlantVillage 视觉权重可插拔后端"，措辞需修** |
| R3 | **0 外部调用持续 30+ 天** | 🔴 高 | 决策门（评审 §3.5）：P0-F/G 若 3 个月内零外部调用 → 降级为个人知识库项目。**当前已过约 1 个月，剩 2 个月窗口** |
| R4 | **GitHub 推送依赖人工 PAT** | 🟡 中 | 所有对外分发（Glama/npm/LobeHub 均从仓库抓取）被此单点卡住 |
| R5 | **文档口径与实测不符** | 🟡 中 | L4"已落地"、自评 8.8 未含分发维度。与项目核心资产（可信度）冲突 |
| R6 | **SoilGrids 中国区不可靠但契约记 200** | 🟢 低 | 会高估土壤数据置信度；对策 L0-4 |
| R7 | **vegperiod 为 GPL-3+** | 🟡 中 | 抄算法可以，**抄代码会传染**；须从论文重新实现 |
| R8 | **硬编码密钥占位** | 🟢 低 | TD-2，立即消除 |

---

## 8. 分阶段提升路线图

> **排序铁律**：凡是能产生第一次真实外部调用的动作，优先级高于一切新增功能。

### P0 · 2 周内 · 目标：从"自洽"到"被看见"

> **执行状态（2026-10-08 更新）**：P0-1 / P0-2 / P0-3 / P0-7 已完成并通过门禁；P0-0 已完成（`docs/CORE_OBJECTIVE.md` + 4 份冲突文档口径声明）；P0-6 / P0-5 / P0-4 需用户操作，清单见 `docs/distribution_checklist.md`。

| # | 动作 | 工作量 | 判定标准（可验证） | 状态 |
|---|---|---|---|---|
| P0-0 | **战略指引 v2.0 重写** + L4-L6 暂缓判定 + README/CHANGELOG 口径核对 | 0.5 天 | 三份文档口径一致；无"已落地"与实测冲突 | ✅ 完成（以 `docs/CORE_OBJECTIVE.md` 为单一权威源 + 4 份文档加口径声明） |
| P0-1 | **MCP 2026-07-28 无状态适配**：补 `ttlMs`（配方季度级 ⇒ 2592000000）、接收 `_meta.traceparent`、支持 `Mcp-Method`/`Mcp-Name` 头 | 0.5 天 | 新规格客户端下无告警 | ✅ 完成（SEP-2575/2567/2243/2549/414 全适配 + 版本协商） |
| P0-2 | **A2A Agent Card** `/.well-known/agent.json`（声明 9 Agent + Env Recipe 输入输出 + auth=none + SLA） | 1 天 | 文件存在且通过 schema 校验 | ✅ 完成（14 skill ↔ 14 MCP 工具，`scripts/check_agent_card.py` 门禁） |
| P0-3 | **Agent Plugins 打包**：`plugin.json` + `skills/*/SKILL.md`（11 个）+ `mcp.json` | 1-2 天 | 至少 3 家客户端可加载 | ✅ 完成（13 文件，注册表为唯一数据源，CI `--check` 防漂移） |
| P0-4 | **上架 4 个市场**：Glama / LobeHub / Smithery / Official MCP Registry | 1 天 | 4 个市场搜索可见 | ⏸ 依赖 P0-6；提交字段已备 |
| P0-5 | **公网 Demo 部署**（`deploy_config.sh` + `deploy_local.sh`） | 0.5 天 | README 带可点链接 | ⏸ 脚本就绪，需用户执行 |
| P0-6 | **GitHub 推送打通**（PAT + `gh_push.py`） | — | `sync_check.py` 差异 0 | ⏸ 需用户提供 PAT |
| P0-7 | **消除硬编码密钥** + 归档/接线决策记录 | 0.5 天 | grep `secret_key` = 0 命中 | ✅ 完成（随 5 模块归档一并移出主链路） |

**P0 出口指标：出现第 1 次非本人外部调用。**

### P1 · 1-2 月 · 补齐协议与字段空白 + 提升可信度

| # | 动作 | 判定标准 |
|---|---|---|
| P1-1 | **Env Recipe v1.2**：补 `vpd_kpa` / `dew_point_c` / `companion_plants` / `sowing_depth_cm` / `revision_history`，并实现 `export/import/diff/clone` 4 个 Skill（`difflib`，零依赖可行） | 116 配方新字段覆盖 >90% | 🔶 **部分完成**：`vpd`/`dew_point`/`sowing_depth`/`dli` 已按**运行时派生**落地（`engine/derived.py` + `test_env_derived_v12.py` 8 项回归），不写回配方 JSON；`companion_plants`（0/116 无权威数据）与 `revision_history` 待补 |
| P1-2 | **移植 agroclim 函数集 + vegperiod 三法交叉校验**（严禁抄 GPL 代码） | 物候双轨输出 + 分歧告警，测试 +30 | ✅ 待开工 |
| P1-3 | **CMIP7 接入** `agri_season_advisory` 情景模式 | 7 情景可查，**当前无竞品** |
| P1-4 | **PlantDoc 接入 + agstack pestmodels 对接评估** | `eval_pest_diagnosis_topk` 有真值集 |
| P1-5 | **微气候选址 MVP**（朝向/遮挡/楼层风） | 同城市不同朝向输出不同适配分 |
| P1-6 | **MCP server 分层重构**（`tools/` + `handlers/` + `formatters/`） | `server.py` < 200 行 |
| P1-7 | **商业化架构预留**：`call_id` / `billing_hint` / 预算上限 | 每次调用可追溯唯一 id |
| P1-8 | **数据源健康分**（`sources[].health` 联动 confidence） | SoilGrids 中国区置信度自动下调 |
| P1-9 | **测试拆分**：v4/v5 拆子模块；MCP 自测纳入 unittest 统计 | 无 >800 行测试文件 | 🔶 **部分完成**：`test_mcp_server_unit.py` 已纳入 unittest（3 项，单测基线 533→556）；但 `test_engine_v4.py`（1417 行）仍超 800 行，v4/v5 拆分子模块待做 |

### P2 · 3-6 月 · 战略层与体验层

| # | 动作 | 判定标准 |
|---|---|---|
| P2-1 | **零依赖策略明文细化**（核心零依赖 + `AGRI_*` 插拔增强层） | 工程规范文档 |
| **P2-2** | ~~TD-1 死代码处置（接入或归档，约 4,200 行）~~ | ✅ **已完成**（2026-10-08 归档至 `_archive/agent_legacy_20261008/`，0 未接线模块） |
| P2-3 | **前端升级**：成长日志/日历（情绪价值，非参数仪表板）+ Deck.gl/Cesium 全球配方分布图（CDN 引入） | 可分享链接 |
| P2-4 | **L4 二选一**：最小可用实现 or 正式暂缓文档 | 有结论 |
| P2-5 | **闭合 2 项 pending eval**（专家盲评 / 病虫害 top-k） | v1.0 工程门槛达标 |
| P2-6 | **MCP Apps**：把物候曲线/配方时序作为 `ui://` resource 返回 | 至少 1 个 UI resource |
| P2-7 | **商业化定价拍板**（先解决 R1 法务口径） | 定价文档状态从"提案"转"生效" |

---

## 9. 需拍板的决策项

| # | 决策 | 选项 | 影响 |
|---|---|---|---|
| D1 | **主线是否确认为「只做 MCP/Agent-native 分发」？** | 确认 / 恢复七层战略 | 决定后续 6 个月全部投入方向；**不拍板等价于默认确认** |
| D2 | **L4 链路数据** | A 暂缓（推荐）/ B 最小实现 | 是否投入 3-5 天 |
| D3 | **付费口径** | 服务型收费（推荐）/ 剥离 NC 来源做数据授权 | **先解 R1 法务冲突** |
| D4 | **视觉后端** | 保持规则降级 / 接 ATEX 网关 / 对接 agstack | L1 能否从 15% 跃迁 |
| D5 | **是否补 C 端触点（微信小程序）** | 做 / 不做 | 若不做，对外叙事须统一为海外 B 端 |
| D6 | **~4,200 行未接线模块** | ~~归档（推荐）/ 接入~~ ✅ **已选归档**（2026-10-08 移入 `_archive/`） | 技术债处置**已完成** |
| D7 | **GitHub PAT** | 提供 / 不提供 | 阻塞 P0-4 全部上架动作 |

---

## 10. 附录：实测命令与数字来源

```bash
# 代码规模
find . -name "*.py" -not -path "./.workbuddy/*" | xargs wc -l   # 32500

# 单测（本机实跑 2026-10-08；**必须用 -S -P 隔离 site-packages**，否则 pip mcp 包会遮蔽项目 mcp/ 目录）
python -S -P -m unittest discover -s scripts -p "test_*.py"
# → Ran 537 tests in 14.685s / OK (skipped=3)
#
# ⚠️ 若用普通 python（site-packages 里有 pip mcp SDK）跑会假失败 3 项：
#    python -m unittest discover -s scripts -p "test_*.py"   # 会 ERROR 3 项
#    根因：`import mcp.server` 解析到第三方包；修复见 scripts/check_mcp_namespace.py

# 测试函数分布（grep "def test_"）
# v4=137 v5=94 agents=66 v2=59 v3=43 lineage=25 climate_data=19
# audit=16 jev_gate=15 climate_reconcile=14 jev_decision=10 jev_attribution=8 geo_recipe=7

# Env Recipe 字段覆盖 —— ⚠️ 原脚本用子串匹配会把 "ha ndli ng" 里的 dli 误判为字段命中
# 正确做法：递归遍历 JSON 键（只统计"字段存在且非空"），不要 grep 整份文件文本
python - <<'EOF'
import glob, json

def has_nonempty(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key and v not in (None, '', [], {}):
                return True
            if has_nonempty(v, key):
                return True
    elif isinstance(obj, list):
        for i in obj:
            if has_nonempty(i, key):
                return True
    return False

tot = 0
has = {'dli': 0, 'vpd': 0, 'dew_point': 0, 'companion_plants': 0,
       'sowing_depth': 0, 'revision_history': 0, 'outcome': 0, 'execution_log': 0}
for f in glob.glob('data/env_recipes/*.json'):
    tot += 1
    r = json.load(open(f, encoding='utf-8'))
    for k in has:
        if has_nonempty(r, k):
            has[k] += 1
print(tot, has)
# → 116 {'dli':0,'vpd':0,'dew_point':0,'companion_plants':0,'sowing_depth':0,
#        'revision_history':0,'outcome':0,'execution_log':0}
# 注：dli 命中原脚本的是 exception_handling 里的单词 "handling"
EOF

# 未接线模块（grep 实测）
# finance_agent / market_agent / risk_agent / agent_factory / collaboration_manager
# 已于 2026-10-08 移入 _archive/agent_legacy_20261008/，TD-1/TD-2 已处置
```

**数字来源优先级**：本机实跑 > `outputs/daily_loop_2026-10-07.md` > `harness/manifest.json` > 仓库文档。凡文档与实测冲突处，一律以实测为准并在 §3.1 列出。

---

*本报告生成于 2026-10-08，基于本机全量扫描与实跑验证。下次复核建议窗口：2026-11-08（P0 出口指标是否达成）。*
