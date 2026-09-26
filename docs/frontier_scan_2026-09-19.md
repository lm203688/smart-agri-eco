# 智慧农业生态 · 2026-06 → 2026-09 前沿扫描

- 扫描日期：2026-09-19
- 方法：Web 搜索（freshness m4 优先）+ GitHub/官方文档交叉核实（URL / license / 最近活跃 / 版本号）
- 原则：不确定即标「待核实」，不编造项目名、star 数、URL 或数据
- 时间范围严格限定 2026-06-01 到 2026-09-19
- 与 2026-09-17 扫描的关系：那份覆盖了 FAO/WorldClim/ISRIC/PlantVillage/PlantDoc/EPPO/WOFOST/Env Recipe 字段缺口/物候工具/中国阳台市场需求——**本报告全部排除**
- 对齐基线：本项目已有 110 个 Env Recipe、4+3 Agent、9 Skill、9 MCP 工具、282 单测、纯 Python 标准库零第三方依赖、已有 MCP server 上架 Glama + npm（对标 aishield-mcp-server v4.2.2，MCP 227 rules / Skill 233 / 6 tools）

---

## 1. 结论摘要（按 ROI 排序）

1. **MCP 协议在 2026-07-28 发生了自发布以来最大的规格变更——彻底移除 session**。SEP-2575 移除 initialize/initialized 握手，SEP-2567 移除 `Mcp-Session-Id` 头，SEP-2243 强制 `Mcp-Method`/`Mcp-Name` 头以便负载均衡，SEP-2549 在 list/resource 结果上加 `ttlMs`/`cacheScope` 字段，SEP-414 补上 W3C Trace Context 传播（`traceparent`/`tracestate`/`baggage`）。**这不是优化，是范式转移**：状态从传输层元数据移到显式 handle（`basket_id`/`workflow_run_id`）由模型自己持有和组合。Env Recipe 天然符合"显式 handle"模式——每个 recipe 就是一个 `recipe_id` 让 agent 在多步工具链里传递。**必须立即适配**，否则我们的 MCP server 会在下一个客户端版本里失效。零依赖可行（纯 JSON-RPC 无状态）。

2. **A2A v1.0 已在 2026-03 定稿并捐入 Linux Foundation AAIF**，与 MCP 同属一个基金会。**关键的可抄字段是 Agent Card**——它是一份放在 `/.well-known/agent.json` 的 JSON，声明 skills、inputs、outputs、auth、SLAs，且现在支持 JWS 签名（RFC 7515 + RFC 8785 canonical JSON）+ OAuth 2.0 Device Code（RFC 8628）+ PKCE + 多租户 `tenant` 字段。**MCP 让 agent 连工具，A2A 让 agent 连 agent**——两层都要有。我们当前只有 MCP server，A2A 是空白。加一个 Agent Card 只需要一个 JSON 文件，零依赖。

3. **Agent Plugins 1.0.0（Google 2026-08-06 发布）是 Skills + MCP 打包分发的统一规范**。一个目录里放 `plugin.json` + `skills/SKILL.md` + `mcp.json`，跨 Claude / Cursor / Copilot / VS Code 通用，TSC 由 Amazon / Cursor / Microsoft / OpenAI / Vercel + Google 联合制定。**这是对 Anthropic Agent Skills 和 MCP 两个独立生态的第一次整合**——之前每个客户端都有自己的插件格式。我们已有 MCP + Skill 生态，但缺少 plugin.json 打包层，**加一层目录约定就能同时进 5 家客户端市场**。

4. **Anthropic Agent Skills 于 2026-08 从 beta 转为正式版**，规范公开在 `agentskills.io`，并附参考 Python SDK。**SKILL.md + YAML frontmatter（`name` ≤64 字符仅小写字母数字连字符 + `description` ≤1024 字符）** 已成为开放标准，不是 Claude 独享。我们的 9 个 Skill 应该对齐这个格式，且 skill 生态已经在建第三方市场（SkillsMP / AgentPowers.ai / LobeHub.com 已列 SKILL.md 格式）。**这是分发机会，不是重复建设。**

5. **CMIP7 于 2026-09-01 公开发布底层排放数据**（high-level 摘要 2026-04 在 GMD 期刊发表）。7 个情景（H/HL/M/ML/L/VL/LN），2100 升温范围 1.6–3.3°C，比之前 SSP 的 1.5–4.7°C 大幅收窄。这是 IPCC AR7 的数据底座，且**气候数据聚合站 climate-resource.com 显示 2026-09-11 已索引 4604 个 CMIP7 数据集（37.44 TB）**。**这是首次真正开放、可比对的下一代气候情景数据**，我们的 climate Agent 应立即接入。零依赖：GMD 期刊 PDF 是开放获取的。

6. **Microsoft Planetary Computer Pro GA（2026-05-27）+ MCP Tools VS Code 扩展发布**，暴露 35+ 个遥感工具（STAC search / GeoCatalog / 可视化 / 摄取监控），是**目前唯一真正企业级的农业/遥感 MCP 生态**，且深度整合 Microsoft Fabric + Foundry + Aurora 天气模型 + Earth 2 模型。**这是我们的直接竞品**，但它是 Azure 云原生，我们是本地零依赖——**定位互补而非冲突**，但需要明确差异化叙事。可抄的具体做法：STAC 目录标准、GeoCatalog 元数据规范、Vector Tile API。

7. **X 于 2026-06-30 上线托管 MCP server，$0.01/call**，是**第一个把 MCP 单价化的头部平台**。同类参考：Bright Data $1.50/1000 requests、Firecrawl $16/5K credits、Exa $7/1000 searches、Arcade $25/月+调用、Zapier MCP $19.99/月（每次调用 2 tasks）、Composio $29/月/20 万调用。**"MCP 单价化"是 2026 下半年的关键商业事件**——之前 MCP 几乎全免费，这是变现窗口打开的信号。我们的 MCP 应该设计成支持 per-call 计费的形态，即使现在不收费。

8. **CesiumJS 1.142/1.143（2026-06-01/07-01）+ Deck.gl v9.4（2026-09-05）是 3D 可视化两个方向的关键版本**。CesiumJS 1.142 加了 3D 矢量瓦片支持（3DTILES_content_gltf_vector 扩展 + KHR_mesh_primitive_restart）+ Cesium Copilot（AI 代码助手，用户自带 key）+ GeoJsonPrimitive（绕过 entity 层，大数据集性能大幅提升）+ MVTDataProvider（Mapbox Vector Tiles 直接作为 3D Tiles 加载）。Deck.gl v9.4 把**所有官方图层迁到 WebGPU**（v10 前的最后兼容版本），GlobeView 加了 pitch/bearing + 惯性自转 + 指针锚定缩放，TileLayer 加了视口中心优先请求。**这是本项目前端"单文件 HTML"升级到"专业可视化"的完整工程路径**——通过 CDN 引入，不破坏后端零依赖。

---

## 2. 方向一：Agent-native 数据/工具协议的新协议（非 MCP）

| 项目 | URL | 类型 | 最近活跃 | 它做了什么 | 本项目可借鉴的具体做法 | 差异/冲突 | 零依赖可行？ |
|---|---|---|---|---|---|---|---|
| **A2A v1.0/v1.2** | https://github.com/a2aproject/A2A · https://a2a-protocol.org | Agent ↔ Agent 协议 | v1.0 于 2026-03 定稿，v1.2 于 2026-03 末；2026-04-09 一周年宣布 22,000+ GitHub star、150+ 生产组织；2026-07-16 Google Dev Forum 官方博客（sampathm） | Agent 之间通信的开放标准：Agent Card（`/.well-known/agent.json`）+ Task 生命周期 + JSON-RPC 2.0 over HTTPS + SSE 流式；v1.0 加：JWS 签名的 Agent Card、OAuth 2.0 Device Code + PKCE、多租户、多协议绑定、`google.rpc.Status` 统一错误、`A2A-Version` 头版本协商；v1.2 加 gRPC 支持、延迟广播 | **抄 Agent Card schema**：把我们的 MCP server 声明为 A2A agent，暴露 `skills`（我们的 4 流水线 Agent + 3 反应式 Agent）+ `inputs/outputs`（Env Recipe 结构）+ `auth`（none/optional key）+ `SLAs`；文件放到 `/.well-known/agent.json`，用 stdlib `hmac`+`hashlib` 做 JWS ES256 签名 | 它是 agent 互操作，我们是数据/工具提供方；不冲突，是补一层。A2A 是 JSON-RPC over HTTP，零依赖可行 | ✅ 是（Python stdlib + 一个 JSON 文件） |
| **Agent Plugins 1.0.0** | https://google.github.io/agent-plugins · https://agent-plugins.org | 打包分发规范 | 2026-08-06 Google 发布，TSC：Amazon/Cursor/Microsoft/OpenAI/Vercel + Google | 统一 Skills + MCP 的插件目录格式：`plugin.json`（manifest）+ `skills/SKILL.md`（YAML frontmatter + Markdown）+ `mcp.json`（MCP server 定义）；目标是让一个插件目录跨 Claude/Cursor/Copilot/VS Code 通用 | **抄目录约定**：加一个 `plugin.json` 描述我们整个项目（skills/ 目录 + mcp/ 目录 + 版本 + 依赖声明），把 9 个 Skill 打包成 SKILL.md 格式，把 9 个 MCP 工具打包成 mcp.json。**这是分发升级，不是功能开发** | 与现有 SKILL.md 目录约定兼容（都是 YAML frontmatter + Markdown），只需加一层 manifest | ✅ 是（纯目录约定，无任何代码） |
| **Anthropic Agent Skills 开放标准** | https://agentskills.io · https://console.anthropic.com/docs/agents-and-tools/agent-skills/overview | 规范 + SDK | 2026-08 从 beta 转正；参考 Python SDK 公开 | 一个 Skill 是一个目录：`SKILL.md`（YAML frontmatter `name` ≤64 字符仅小写字母数字连字符 + `description` ≤1024 字符）+ 可选 scripts/ + templates/；progressive disclosure 模型：agent 启动时只读 frontmatter，任务匹配时才加载 body；已建第三方市场：SkillsMP / AgentPowers.ai / LobeHub.com | **对齐 SKILL.md 格式**：把我们的 9 个 Skill 从当前格式（若不一致）迁移到官方 schema，重点校验 `description` 字段是否 ≤1024 字符且明确说明"何时触发"；参考 SDK 可写一个纯 stdlib 的 skill loader | 已有 9 个 Skill，若已按此格式则无需改动；这是"规范化"不是"新增功能" | ✅ 是（Python SDK 可纯 stdlib 重写） |
| **⚠️ ACP（IBM Agent Communication Protocol）已并入 A2A** | https://ibm.github.io/beeai/ | 已合并 | 2025-08 并入 A2A | IBM 的 ACP 在 2025-08 并入 A2A，Kate Blair 加入 A2A TSC；BeeAI 加了 A2A 适配器 | **抄 A2A 而非 ACP**：所有资料里还出现"ACP"作为独立协议的图都是 2025-08 之前的过时快照，别踩这个坑 | 已合并，无独立价值 | — |
| **⚠️ ACP（Agentic Commerce Protocol，Stripe+OpenAI）是另一个 ACP** | https://stripe.com/blog/agentic-commerce-protocol | 支付协议 | Apache 2.0，2026 已在生产 | Stripe + OpenAI 的电商场景支付协议，让 ChatGPT 能读取 merchant catalog 并结账 | 与我们的农业场景**完全不相关**，不要误把 commerce ACP 当作 agent ACP | 支付领域，与农业无交集 | — |
| **⚠️ ACP（Agent Connect Protocol，Amazon+Microsoft+OpenAI+Vercel）** | https://forum.gnoppix.org/t/amazon-cursor-microsoft-openai-and-vercel-unite-on-a-shared-standard-for-ai-agent-plugins/6987 | 工具协议（早期中止） | 2025-08 公告，2025 末规划 v1.0 稳定版 | 4 家共同发起的 REST-based 工具发现/执行/认证协议 | **这个 ACP 后来基本被 MCP 吸收了**——工具层没有形成独立生态。Google 未加入是重要信号 | 已实质中止，不要投入 | — |
| **MCP 2026-07-28 无状态规格** | https://modelcontextprotocol.io · SEP-2575/2567/2243/2549/414 | MCP 核心变更 | 2026-07-28 生效，是发布以来最大变更 | 移除 initialize/initialized 握手（SEP-2575）+ 移除 `Mcp-Session-Id`（SEP-2567）+ 强制 `Mcp-Method`/`Mcp-Name` 头（SEP-2243）+ list/resource 结果加 `ttlMs`/`cacheScope`（SEP-2549）+ W3C Trace Context 传播 `_meta.traceparent`（SEP-414）；新 `server/discover` 方法按需取能力 | **必须适配**：①我们的 server 移除所有 session 状态；②Env Recipe 作为"显式 handle"暴露（`recipe_id` 而非隐式缓存）；③所有 tool 返回加 `ttlMs`（Env Recipe 更新频率=季度级 → `ttlMs: 2592000000`）；④tool 调用加 `traceparent` 头便于分布式追踪；⑤`Mcp-Method` 头让上游负载均衡可直接路由 | 是协议合规问题，不是功能扩展；不做会失效 | ✅ 是（JSON-RPC 无状态，本就是我们架构的强项） |
| **MCP Apps（Anthropic + OpenAI 联合规格）** | https://modelcontextprotocol.io/apps | MCP UI 扩展 | 2026-01 发布（时间稍早但影响在 6-9 月集中爆发）；Claude/ChatGPT/Goose/VS Code 已支持 | MCP tool 可以返回 `ui://` resource，宿主在沙盒 iframe 内渲染工作 UI（表格/表单/仪表盘）而非纯文本 JSON；JSON-RPC 回传通道；build once, render anywhere | 我们的前端目前是"单文件 HTML"，MCP Apps 提供了**让 agent 直接把可视化 UI 送进对话窗口**的机制。前端可视化升级后，可以把"某个 recipe 的时间序列曲线"、"某个作物的物候窗口"作为 `ui://` resource 返回，让 agent 调用它 | MCP Apps 是 2026-01 的规格（时间早于本扫描范围），但支持客户端在 6-9 月陆续上线；本扫描只列"新出现的客户端支持" | ✅ 是（前端是 HTML/JS，后端只是声明 resource） |
| **x402 Foundation** | https://x402.foundation · https://github.com/x402 | 支付协议（Linux Foundation） | 2026-07-14 宣布，40 家创始成员（Visa/Mastercard/Stripe/Google/AWS/Cloudflare/Coinbase 等） | 402 Payment Required 语义化，让 agent 能自动付 USDC 给付费 HTTP 端点；@x402/mcp 包可 wrap MCP tool 加计费；已索引 251+ 服务 | 与我们的 MCP 商业化直接相关。**先记方案不实施**：把我们的 MCP tool 加 `@x402/mcp` 中间件（未来版本），支持 agent 按次付费调用高级配方生成 | 现在实施过重：需要 USDC 钱包+facilitator，与零依赖冲突；但架构上要留出扩展点 | ❌ 否（涉及以太坊链上签名） |
| **AP2（Agent Payments Protocol）** | https://github.com/google-agentic-commerce/AP2 | 支付授权协议 | v0.2.0 于 2026-04-28，参考实现（Python/TS/Kotlin/Go），Apache 2.0 | Google 的 agent 支付授权协议，Cart Mandate + Payment Mandate 双签名 | 与本项目无关，仅作为"支付层仍在碎片化"的证据 | 支付领域 | — |
| **ARD（Agent Resource Discovery）/ `ai-catalog.json`** | 由 Google/Microsoft/Cisco/NVIDIA/Hugging Face/Snowflake 联合 | 发现协议 | 2026 年出现（细节未深搜） | `/.well-known/ai-catalog.json` 域名锚定的 agent/tool 目录格式，让客户端能自动发现一个域名下的所有 agent 资源 | 与 A2A Agent Card 高度互补：Agent Card 是单个 agent，ai-catalog 是"这个域名下的所有 agent/tool"清单。**未来版本可加** | 尚不成熟，等 v1.0 | ✅ 是（JSON 文件） |
| **OKF（Open Knowledge Format）** | https://okf.io | 知识格式 | Google 2026 发布 | 人 + agent 都可读的知识格式，目标是"人写、agent 生成、跨组织交换" | 与我们的 Env Recipe JSON 结构**思路高度一致**（都是结构化领域知识）。值得对照其字段设计看有无遗漏 | 尚不成熟 | ✅ 是（JSON） |

**要点**：这个方向最核心的洞察是——**Agent 协议层已定型（MCP + A2A 都进了 Linux Foundation），而支付层仍在碎片化（x402 vs ACP vs AP2）**。我们应立即做的是三件事：①适配 MCP 2026-07-28 无状态规格（合规必需）；②加一个 A2A Agent Card（新增一层可发现性，零依赖）；③用 Agent Plugins 1.0.0 打包（跨 5 家客户端分发）。其他协议（支付层/发现层/知识格式）等 v1.0 稳定再考虑。

---

## 3. 方向二：农业/生态/气候近期新项目（2026-06 起）

| 项目 | URL | License | 最近活跃 | 它做了什么 | 本项目可借鉴的具体做法 | 与本项目差异/冲突 | 零依赖可行？ |
|---|---|---|---|---|---|---|---|
| **CMIP7 情景数据集** | https://gmd.copernicus.org · https://scenario.mip.ipsl.jussieu.fr · 数据索引 https://www.climate-resource.com/tools/esm-model/cmip7-availability | IPCC 开放（CC BY 4.0） | high-level 摘要 2026-04 在 GMD 期刊；底层排放数据 2026-09-01 公开；2026-09-11 已索引 4604 数据集 / 37.44 TB | IPCC AR7 的数据底座：7 个新情景（H/HL/M/ML/L/VL/LN），2100 升温 1.6–3.3°C，比 SSP 的 1.5–4.7°C 大幅收窄；无 baseline 情景（SSP1-2.6 → Very-low、SSP5-8.5 → High 重命名）；每情景含 CDR 累计移除量（2150 年 655–2360 Gt CO₂） | **立即接入**：把 7 个情景作为 `climate_scenario` 参数加进 climate Agent 的输出；对每个 Env Recipe 提供"当前政策情景（M）"和"最坏情景（H）"两版生长窗口对比；参考 IAM 模型对应关系（GCAM/WITCH/IMAGE/COFFEE/MESSAGEix-GLOBIOM/REMIND-MAgPIE/AIM）做情景标签的准确引用 | 我们之前只用 WorldClim（历史气候），没有未来情景维度。CMIP7 是首次真正开放、可比对的下一代数据 | ✅ 是（数据是 NetCDF/CSV，可用 stdlib 读 CSV 部分） |
| **CMIP7 气溶胶强迫更新** | https://www.iup.uni-heidelberg.de/de/node/798 | CC BY 4.0（Zenodo） | 2026 Fiedler/Leibensperger/Azoulay 论文 | 新气溶胶光学深度数据 1850–2023 历史 + 7 个未来情景，Simple Plumes 参数化，与 CMIP7 排放数据配套 | 与主 CMIP7 数据配对使用；对"高排放→高气溶胶冷却效应"的情景分析有价值 | 数据颗粒度比主情景更细，我们不需要独立用 | ✅ 是 |
| **⚠️ 司农 Sinong LLM（南京农大）** | 魔搭 + GitHub（8B / 32B） | Apache 2.0（8B/32B） | 2026-01-12 发布（**早于本扫描范围，仅作背景**） | 国内首个通用农业开源垂直 LLM，8B/32B 两个版本，40 亿 token 农业数据（近 9000 册书籍 + 24 万篇论文 + 2 万份政策/标准），跨学科覆盖 | **不接入**：8B/32B 参数规模远超本项目"零依赖"约束（纯 Python 手写推理至少 2000+ 行且精度远逊）。**可参考其数据源清单**做知识底座对照 | 与本项目定位冲突（我们是知识底座+配置，不是 LLM）；仅可作学术参照 | ❌ 否 |
| **神农大模型 4.0 + 神农·农业世界模型 1.0（中国农大）** | https://ciee.cau.edu.cn | Apache 2.0（世界模型部分） | 2026-07-14 发布 | 4.0 版本：病虫害识别扩到 1016 种、准确率 >93%、新增 25 种热带作物；世界模型 1.0：全球首个动作条件化 + 设施+大田双域验证的农业世界模型，"数字试验田"概念，四轴评价协议（目标预测/状态滚动/反事实响应/跨情境泛化） | **⚠️ 这是本项目 Env Recipe 的直接概念竞争者**——他们的"给定当前状态 → 推演不同动作下的产量/风险变化"与我们的"作物×阶段×箱体条件 → 环境参数"思路互补但同向。**可抄的具体做法**：①四轴评价协议（特别是"反事实响应"，对应我们异常处理场景）；②"数字试验田"的隐喻可用于对外叙事；③1016 种病虫害种类是 pest Agent 的对照基准 | **定位差异**：他们有大模型+大规模数据+中国农大 7 年积累；我们有零依赖+本地+Agent-native。做对标不做跟随 | ❌ 否（他们是 PyTorch 模型） |
| **iPheno 视觉-语言模型** | https://www.cell.com/plant-communications/fulltext/S2590-3462(26)00404-9 · https://ipheno.ai4bread.com · https://github.com/2997029323/iPheno-PC-Client | CC BY-NC-ND 4.0（论文）；代码待核实 | 2026-09-08 在线发表（Cell Plant Communications） | 作物表型双感知 VLM：spatial-aware（KNN 图）+ task-aware（MoE 路由），iPheno-120K 数据集，F1 提升 17.1-28.9%（对比 LLaVA-1.6-13B / MiniCPM-o-9B） | **⚠️ 论文 license 是 CC BY-NC-ND，禁止衍生，商用受限**。可参考其"细粒度空间推理 + MoE 任务路由"的架构思路，但不接入模型本身。其 iPheno-120K 数据集作为植物表型的公开对照有价值 | 需要深度学习栈，与零依赖冲突；ND 限制不能衍生 | ❌ 否 |
| **PlantCV v4** | https://github.com/danforthcenter/plantcv · https://doi.org/10.1002/ppj2.70065 | GPL-3.0 | 2026-12 出版（Plant Phenome Journal） | 图像分析 v4：降低无编程经验用户门槛（大量 tutorial + 简化 API）；CMYK/HSV/LAB 色彩空间支持；深度集成 ML | 已在 2026-09-17 扫描中标记"暂缓自建视觉数据集"，**v4 无新增可移植算法**——仍是纯图像分析工具，需要 numpy/PIL | 无新增价值（v3 已覆盖大部分能力） | ❌ 否 |
| **PhytoScan3D** | https://github.com/kovimallik/phytoscan3d · https://preprints.epiforecasts.io/paper/10.64898/2026.06.01.729298 | **MIT** | 2026-06-04 preprint | 首个开源 Python 3D 点云表型提取管线：从 Phenospex PlantEye F500/F600 传感器读 PLY/PCD，提取株高、3D 叶面积、数字生物量、凸包体积、叶倾角、冠层几何、NDVI、色相、植被指数；对 936 大麦观察 Pearson r = 0.913-0.999 | **可移植 1-2 个函数**：其"凸包体积 + 数字生物量"估计是纯几何计算，可抄算法（不抄代码，MIT 允许但可参考论文） | 依赖 3D 传感器数据（PlantEye 硬件），我们无硬件；但**算法本身可零依赖实现**（凸包 + 体积） | ✅ 是（几何计算纯 stdlib） |
| **SPROUT 农业视觉基础模型** | https://arcxiv.org/abs/2603.27519 | 待核实 | 2026-03-27（**早于扫描范围，仅作背景**） | Diffusion 基础模型，2.6M 无标签野外图像预训练（MCD-2.6M），pixel-space Diffusion Transformer | 与本项目定位冲突；仅作为"农业视觉基础模型"的存在证明 | PyTorch 栈 | ❌ 否 |
| **GEE 2026-08 新数据集批次** | https://earthengine.google.com/catalog/ | 各异（PML V2.2a CC BY 4.0；GEDI CC BY 4.0；MAPL-EMIT 待核实） | 2026-08 GEE Data Catalog 更新 | 500m 全球 GPP/ET（PML V2.2a VIIRS Edition，2012-2025，8 天粒度）+ 30m GEDI 森林结构/生物量 L4D + 60m 甲烷羽流（MAPL-EMIT）+ VIIRS 反照率 VNP43MA3 + NOAA CFSR 气象再分析 | **PML V2.2a 是我们的 climate Agent 可直接引用的派生量**——500m GPP/ET 是作物生长潜能的直接指标，比原始 T/RH 数据更接近"生长能力"。可用作 Env Recipe 的季节参考基准 | 需要 GEE 账号 + JavaScript SDK；但**数据本身是开放获取的**，可下载 CSV/NetCDF 本地缓存 | ✅ 是（下载到本地后 stdlib 可读 CSV） |
| **Google Maps Custom Satellite Embeddings** | https://cloud.google.com/maps-platform/custom-satellite-embeddings | 商业（Private Preview） | 2026-08 公告，申请截止 2026-09-01 | AlphaEarth Foundations 模型：64 维 embedding 每位置每年，1.4T 年度嵌入足迹；新客户可按季度/月/周/自定义（最短 5 天）周期请求自定义区域 embedding | **不接入**：需申请 Private Preview + 商业合同；且 embedding 是黑盒，与我们的可解释 Env Recipe 哲学冲突 | 商业闭源 | ❌ 否 |
| **Google Earth AI UK Hedgerow Dataset** | 通过 GEE / Google Earth AI 发布 | 待核实（可能 CC BY 4.0） | 2026（具体日期未标） | 英国农田细粒度生态特征（树篱、石墙、小树林、带状林地）向量化数据集，Polsby-Popper 紧凑度评分分类，基于 FarmScapes 2020 | **架构思路可参考**：把非结构化遥感像素转成"可行动清单"的思路与我们的 Env Recipe 一致——把"能种什么"从连续空间转成离散配置。**但本项目暂缓大田**，不接入数据 | 是英国农田场景，与城市箱体不匹配；且属于大田尺度 | ✅ 是（若只作思路参考） |
| **Microsoft Planetary Computer Pro GA** | https://aka.ms/MPCP_GA · https://learn.microsoft.com/azure/planetary-computer/microsoft-planetary-computer-pro-overview | 商业（Azure） | 2026-05-27 GA；2026-05 更新日志；支持 Zarr V2/V3 + NetCDF + GRIB2 + Shapefile/GeoJSON/GeoParquet（预览） | 企业级地理空间数据平台：STAC 目录 + GeoCatalog 私有数据管理 + 摄取工作流 + Vector Tile API + 与 Fabric/Foundry 深度集成；Earth 2 天气模型 + Aurora（Nature 发表）+ 卫星/雷达/激光雷达/矢量统一平台 | **是本项目最接近的企业级竞品**。可抄的具体做法：①STAC 作为目录标准（我们 Env Recipe 可加一个 STAC-compliant catalog.json）；②"摄取-治理-分发"三层工作流；③Vector Tile API 用于前端渲染；④"数据 + 模型 + 目录"三位一体的思路 | **定位互补**：它是 Azure 云原生+企业级，我们是本地零依赖+可执行配置。差异化叙事：MPC Pro 是"企业级数据平台"，我们是"个人可执行的种植知识" | ❌ 否（需 Azure 账号） |
| **Microsoft Foundry Labs EO/OS Object Detection** | https://techcommunity.microsoft.com/tag/microsoft%20planetary%20computer | 商业（Foundry Labs） | 2026-04-13 发布 | 卫星/航拍影像物体检测模型，Foundry Labs 中的 GeoAI 类别，托管端点 | 仅作为"卫星物体检测已有托管方案"的证据，不接入 | 商业托管，与零依赖冲突 | ❌ 否 |
| **Microsoft Aurora 天气模型** | https://github.com/microsoft/aurora | MIT | 2024-06 首发，2025-11 宣布开源 | 局部运行、按需的全球天气预报 + 风暴路径模型，Nature 发表，微软在 Planetary Computer 上托管 | 可作为气候 Agent 的"未来 10 天预报"参考，但需 GPU 运行；本项目可考虑把其开源数据接入作为"下一年气象基准"对照 | 需 GPU + PyTorch | ❌ 否 |

**要点**：这个方向的核心信号是——**下一代气候数据（CMIP7）已在 2026-09 公开发布，是我们的 climate Agent 应立即接入的最大变量**。其他新出现的农业 AI 模型（司农/神农/iPheno/SPROUT）都与我们定位互补而非竞争，且都需要深度学习栈，与零依赖约束冲突。**Microsoft Planetary Computer Pro 是最需要关注的"企业级竞品"**，但它与我们在"云端 vs 本地"、"数据平台 vs 可执行配置"两条维度上都是对偶的，是定位差异而非功能差异。

---

## 4. 方向三：MCP 生态里的农业/环境/植物新项目

| 项目 | URL | License / 分发 | 最近活跃 | Tools 设计与 schema 粒度 | 可借鉴的具体做法 | 差异/冲突 | 零依赖可行？ |
|---|---|---|---|---|---|---|---|
| **Microsoft Planetary Computer Pro MCP Tools（VS Code 扩展）** | https://marketplace.visualstudio.com/items?itemName=ms-iot.planetary-computer-pro-mcp-tools · https://techcommunity.microsoft.com/blog/planetary-computer-blog | MIT（扩展本身）；数据源各异 | 2026-05-27 发布；VS Code Marketplace 显示 173 installs | 35+ 工具：STAC Search & Discovery（含交互式地图）+ GeoCatalog 管理（渲染选项/镶嵌/缩略图）+ PC → GeoCatalog 摄取 + 摄取监控 + 可视化 + 自然语言接口（GitHub Copilot） | **抄三点**：①**STAC Search 作为 tool 的第一优先级**（我们的工具目前是"生成配置"，它把"数据发现"独立成 tool）；②"从自然语言到 STAC 查询"的翻译层——我们可以在 crop Agent 内部实现类似翻译；③VS Code Marketplace 作为分发渠道 | **是竞品**：它覆盖"数据侧"，我们覆盖"配置侧"，互补 | ❌ 否（依赖 Azure） |
| **Pipeworx mcp-noaa-spc** | https://lobehub.com/mcp/pipeworx-io-mcp-noaa-spc · https://gateway.pipeworx.io/noaa-spc/mcp | MIT，TypeScript，云端 MCP | 2026-09-08（v0.1.0） | 7 工具，接 NOAA Storm Prediction Center：outlooks/风暴报告/watch；Pipeworx 网关统一接入 250+ 数据源，可 `ask_pipeworx(question)` 用自然语言查询 | 抄**"网关 + 多源"架构**：Pipeworx 把 250+ MCP 数据源统一到一个 endpoint，agent 只接一个 URL 就能访问全部数据。这是比"单一 MCP server"更省分发成本的策略。**未来可考虑接入而非自建** | 单一数据源（风暴），无本地知识 | ✅ 是（若只作数据源调用） |
| **PixelGust MCP** | https://pixelgust.com/mcp · https://wpnews.pro/news/show-hn-an-mcp-server-that-gives-ai-assistants-live-weather-and-hazard-data | 待核实（免费层 50 调用/日） | 2026（Show HN） | 9 工具：get_current_weather / get_weather_forecast / get_historical_climate / get_climate_timeseries / get_terrain / get_hazards / get_environment / get_proximity / get_polygon_stats；数据源：NOAA GFS / ERA5 / Copernicus DEM / MODIS / ESA WorldCover / SoilGrids / 加拿大火险指数 | **抄"9 工具矩阵"的粒度设计**——它是把"气象/气候/地形/灾害/生态/邻近"6 类信息合成 9 个正交 tool，比 agrobr-mcp 的 10 个但覆盖单一国家视角要更"国际化"。我们的 climate Agent 可以对齐这个粒度 | 需 API key（付费层）；与"零依赖本地"冲突 | ✅ 是（若只作调用） |
| **CropProphEU**（DasClown） | https://github.com/DasClown/CropProphEU · https://dev.to/dasclown/croppropheu | MIT | 2026（dev.to 博文） | EU 作物智能：yield 预报（土壤+气候+历史）+ 市场价值 + 风险分析（气候/病虫害/供应链）；`uvx crop-proph-eu` 一键启动；已上架 Smithery + Glama | **仅作为分发渠道参考**：作者维护 `awesome-mcp-servers` 精选清单，是 MCP 生态的重要获客入口。**已在 2026-09-17 扫描中出现，本次不重复推荐** | EU 视角 | — |
| **⚠️ MEOK AI Labs 系列（agriculture-robotics-mcp / gardening-ai-mcp）** | https://github.com/CSOAI-ORG/agriculture-robotics-mcp · https://github.com/CSOAI-ORG/gardening-ai-mcp | MIT，PyPI 分发 | 2026-09-04 更新（v1.0.4） | 都是薄包装，metadata 少，主要是"EU AI Act 合规"叙事 + 付费咨询 | **⚠️ 警示：这是 MCP 生态的"注水现象"**——MEOK AI Labs 号称有 300+ MCP server（councilof.ai/safetyof.ai/meok.ai/cobolbridge.ai 等），全部是薄包装 + 合规营销，无实际工具文档。这类 server 会污染 MCP 索引质量 | 与我们无关，仅作生态质量参照 | — |
| **FarmerTasksAI MCP** | https://github.com/TasksAI-Official/tasksai-mcp-wrappers/tree/main/verticals/farmer | 商业（需 FarmerTasksAI license key） | 2026 | 193+ 农业行政工作流（USDA 项目/作物记录/财务/家畜/安全/合规/营销），但**server 不处理内容，只做鉴权+目录+技能交付**；隐私模型清晰 | 抄**"薄网关 + 上游内容"的架构**：他们的 MCP 只做身份+目录+授权，实际内容在 FarmerTasksAI SaaS 后端。这是 B 端商业化的成熟形态。**但本项目无内容后端，此模式不适用** | 商业闭源后端 | — |
| **⚠️ 各种 Weather MCP Server（isdaniel/mufens/first-it-consulting/CodeByWaqas）** | https://github.com/isdaniel/mcp_weather_server 等 | MIT / 待核实 | 2026-07 到 09 陆续更新 | 都是 Open-Meteo 或 OpenWeatherMap 的薄包装，工具集几乎相同 | **不要接入，不要模仿**：这些是"薄 wrapper 泛滥"的典型。Open-Meteo 已经免费，套一层 MCP 无差异化价值。**我们的气候数据应该来自自有 Env Recipe + CMIP7 + GEE 派生量，而非又一个 Open-Meteo wrapper** | 与本项目定位冲突 | — |
| **LobeHub MCP Marketplace 农业类** | https://lobehub.com/mcp | — | 2026-09 索引同步 | 农业类条目已 10+（FarmerTasksAI / India / Korea FarmSubsidy / smartfarm-mcp / agrobr-mcp 等） | 分发渠道：**本项目应注册 Glama + npm（已有），再补 LobeHub**（农业条目多但"Unvalidated"标多，占位空间大） | 已在 2026-09-17 扫描中确认 | — |

**要点**：MCP 农业生态的真实状态是——**"厚平台 vs 薄 wrapper"的分化已经很清楚**。Microsoft Planetary Computer Pro MCP（35+ 工具，Azure 后端）是唯一真正的"厚平台"，其余绝大多数是薄 wrapper + 合规营销（MEOK 系列是极端案例）。**我们的定位介于两者之间**：零依赖本地知识底座 + 9 个真正有实质内容的工具（不是 Open-Meteo wrapper）。这个定位是稀缺的。

---

## 5. 方向四：前沿数据可视化设计

| 项目 | URL | License | 最近活跃 | 它做了什么 | 本项目可借鉴的具体做法 | 与本项目差异/冲突 | 零依赖可行？ |
|---|---|---|---|---|---|---|---|
| **CesiumJS 1.142 / 1.143** | https://cesium.com/blog/2026/06/01/cesium-releases-in-june-2026/ · https://cesium.com/blog/2026/07/01/cesium-releases-in-july-2026/ | **Apache-2.0**；GitHub 15.4k★；123.6k npm 周下载 | 1.142 于 2026-06-01；1.143 于 2026-07-01 | 1.142：**3D 矢量瓦片**（3DTILES_content_gltf_vector 扩展 + KHR_mesh_primitive_restart + EXT_mesh_primitive）+ **Cesium Copilot**（AI 代码助手，用户自带 key：Google Gemini/Anthropic Claude/Google Vertex AI）+ GeoJsonPrimitive（绕过 entity 层，大数据集性能）+ MVTDataProvider（Mapbox Vector Tiles 直接作 3D Tiles）；1.143：KHR_meshopt_compression glTF 扩展（更小 3D 模型）+ PathGraphics.materialMode=PORTIONS（路径分段不同材质） | **对前端"单文件 HTML + UN 机构级风格"的具体升级路径**：①CesiumJS 提供 3D 地球 + 全球矢量数据 + 时间切片，与我们的"全球农业环境配置"定位完美匹配；②`GeoJsonPrimitive` 让我们能直接把 GAEZ 全球分区数据加载到 3D 地球上（不经过 entity 层，10 万点级性能）；③`PathGraphics.materialMode=PORTIONS` 可让"某个作物的一整个生长期路径"按阶段着色（种子期/生长期/成熟期）；④`MVTDataProvider` 让 GEE 的 PML V2.2a 500m GPP/ET 数据能以矢量瓦片形式叠在地球上；⑤**CDN 引入 cesium@1.143 一个 script 标签即可**，不破坏后端零依赖 | **定位互补**：Cesium 是"3D 地球可视化引擎"，我们之前是"表格 + 表单"。它解决了"如何让人看到 110 个 Env Recipe 在全球的分布"这个具体问题 | ✅ 是（CDN 引入，纯前端，后端无变化） |
| **Cesium Sandcastle + Copilot** | https://sandcastle.cesium.com/ | Apache-2.0（Copilot 用户自带 key） | 2026-06-01 集成 | Sandcastle（在线 CesiumJS 游乐场）新增内置 Cesium Copilot：AI 编码助手与代码预览同面板，apply_diff 工具编辑代码，流式思考+工具调用，可自修复运行时错误 | **抄"AI 编辑 + 实时预览"的交互模式**：我们的 Env Recipe 编辑器可以加入 AI 辅助（用户输入"给水稻种子期加一个高温异常处理"→ AI 生成 recipe diff → 实时预览 → 用户确认）。这是 agent-native UI 的成熟形态 | Copilot 用户自带 key，我们可用自己的 MCP 或纯客户端逻辑实现 | ✅ 是（前端交互模式） |
| **Deck.gl v9.4** | https://deck.gl/docs/whats-new · https://classic.yarnpkg.com/en/package/deck.gl | MIT（Yarn 显示 1M 下载） | 2026-09-05（v9.4，v9 系列最终版本，v10 预告 luma.gl v10 + loaders.gl v5） | **所有官方图层迁到 WebGPU**（含 MVTLayer + Tile3DLayer），WebGL-WebGPU 渲染等价；GlobeView 加 pitch/bearing + 惯性自转 + 指针锚定缩放 + 触屏多指；ViewLayout 声明式多视图；Multi-canvas 实验性；`@deck.gl/maplibre` 支持 MapLibre GL v4/v5/v6；picking 用 shader builtins 优化 | **具体到"哪个组件可抄"**：①`ScatterplotLayer` 展示全球 GAEZ 分区中心点 + 分区等级色阶；②`HexagonLayer` 展示 Env Recipe 覆盖密度（每个 hex 有多少个配方）；③`TileLayer` 加载 GEE 的 500m GPP/ET 瓦片；④`ArcLayer` 展示作物贸易流或基因流（未来扩展）；⑤**CDN 引入 `deck.gl@9.4` 一个 script 标签即可** | Deck.gl 是"GPU 大数据可视化"，CesiumJS 是"3D 地球"，两者可组合：Cesium 做地球底图，Deck.gl 做数据层叠加 | ✅ 是（CDN 引入，纯前端） |
| **Earth NullSchool** | https://earth.nullschool.net | GPL-3.0 | 长期活跃（2026-09 仍在用） | 全球风场流线动画：默认全球流线+可切高度层（1000hPa/850hPa/500hPa/250hPa）+ 多图层（Air/Ocean/Chem/Particulates/Space）+ 时间轴回溯+预测 + 多投影（正交/墨卡托/等距圆锥/Waterman 蝴蝶）；数据来源 NOAA GFS 每 3 小时 | **抄"时间轴 + 空间切片 + 投影切换"的交互模式**：我们的 climate Agent 展示某个 Env Recipe 的"季节性演化"时，应提供"选一个时间 → 看全球风场+温度+降水 → 判断这个配方在这一时刻的风险"这种交互。**具体参考：GFS 数据 3 小时更新节奏 → 我们 Env Recipe 的"每日刷新"节奏** | Earth NullSchool 是气象可视化标杆（3D 流线动画），我们主要做表格+表单。可以借鉴其"时间轴驱动空间切片"的 UX 哲学 | ✅ 是（前端交互模式参考） |
| **VAPOR（Visualization and Analysis Platform for Ocean, Atmosphere, and Solar Researchers）** | https://github.com/NCAR/VAPOR | **BSD-3-Clause**（宽松，可商用） | 长期活跃（NCAR） | 交互式 3D 科学数据可视化，直接导入 WRF/MOM/POP/ROMS 数据，支持 GRIB/NetCDF，Python 内建解释器可即时创建衍生变量；terascale 数据可在消费级硬件上可视化（progressive access 到不同保真度） | **抄"progressive access"（渐进式加载）**：我们的前端可以按视口动态加载 110 个 Env Recipe 的不同粒度（缩略图 → 关键参数 → 完整配置），VAPOR 是这一模式在科学可视化的成熟实现 | VAPOR 是桌面应用（不是 Web），我们只能参考架构思路 | ✅ 是（架构思路） |
| **2026 Pacific Dataviz Challenge** | https://www.stats.org.nz/2026-pacific-dataviz-challenge-climate-change/ | — | 第 5 届，2026-08-31 截止 | 数据可视化比赛，2026 主题是 Climate Change，提交形式几乎无限制（信息图/动画/dashboard/web app/海报/PDF/绘图） | 可作为"气候可视化设计灵感"的定期扫描源；关注获奖作品的具体交互模式 | 是比赛不是项目 | — |
| **Creative Data at Cannes Lions 2026** | https://www.adgully.com/post/17353/anupriya-acharya-identifies-three-trends-shaping-creative-data-at-cannes-lions-2026 | — | 2026-06-24 Cannes Lions 颁奖 | 三大趋势：①**Sophisticated data, made powerfully useful**（复杂数据解决实际问题）；②**Simple data, elevated by human ingenuity**（简单数据 + 创造性跳跃）；③**Unseen data, becoming systems of change**（把不可见数据变成改变系统） | **抄第 1 条的具体案例 Suncorp Haven**：把气候+房产+灾害数据合成"个性化家庭韧性计划"——这正是我们"气候 Agent + 作物 Agent + 环境配置"的合成思路。抄第 3 条 Forests Without Names（Hyundai）：把碎片化海带数据做成共享环境测绘标准——Env Recipe 就是植物配置的"共享标准"。**这是"如何对外叙事"的具体模板** | 广告奖项，非技术项目；但趋势洞察有借鉴价值 | — |
| **D3.js**（v7.9.0 仍在活跃；v8 未见明确发布） | https://d3js.org · https://d3js.org/api | ISC | 2026 仍在维护（v7.9.0） | 数据驱动文档库：SVG 核心，scales/axes/shapes/interactions/layouts/geographic maps 全套 | **不建议整体替换**：D3 灵活度极高但学习曲线陡；本项目前端是"UN 机构级风格"（表格+表单+简洁），D3 的价值在自定义图表。可考虑用 D3 只做"物候时间序列"这一个特定组件（d3-scale + d3-shape 两个模块足够） | 若引入 D3 会增加前端复杂度，与"单文件 HTML"目标冲突 | ✅ 是（CDN 引入，纯前端） |
| **Vega-Lite / Observable Plot**（补充参考，未在本次搜索中详列） | https://vega.github.io/vega-lite/ · https://.observablehq.com/plot | Vega-Lite BSD-3-Clause；Observable ISC | 长期活跃 | Vega-Lite 是声明式可视化语言，JSON spec 描述图表；Observable Plot 是 D3 团队的高层 API | 若我们的 Env Recipe JSON 结构稳定，可让前端直接用 Vega-Lite spec 渲染所有表格+图表。**这是"JSON 数据 → 图表"的最简路径** | 需前端 JSON schema 设计 | ✅ 是 |

**要点**：这个方向的核心洞察是——**3D 可视化在 2026-06 到 09 有两次关键版本发布（CesiumJS 1.142/1.143 + Deck.gl v9.4），都提供了"零依赖引入"的路径**（CDN script 标签即可）。对本项目"单文件 HTML + UN 机构级风格"的具体升级路径：
- **主路径**：CDN 引入 CesiumJS 1.143 → 展示全球农业环境配置地图（GAEZ 分区 + Env Recipe 分布）
- **补充路径**：CDN 引入 Deck.gl v9.4 → 展示 Env Recipe 密度热力图（HexagonLayer）+ 数据层叠加（TileLayer）
- **交互模式**：参考 Earth NullSchool 的"时间轴驱动空间切片"
- **叙事灵感**：参考 Cannes Lions 2026 Creative Data 三大趋势（Suncorp Haven / Forests Without Names）
- **不推荐**：整体替换前端为 D3（学习曲线陡 + 与简洁风格冲突）

---

## 6. 方向五：Agent + 领域数据的商业化案例

| 项目 | URL | 商业模式 | 最近活跃 | 它做了什么 | 本项目可借鉴的具体做法 | 差异/冲突 | 零依赖可行？ |
|---|---|---|---|---|---|---|---|
| **⚠️ X（Twitter）托管 MCP Server** | https://ai-cost-estimator.com/blog/x-hosted-mcp-launch-per-call-pricing-agent-data-access-cost-baseline | **$0.01/call**（1000 calls = $1） | 2026-06-30 上线 | 让 agent 通过 MCP 访问 X API，个人层 $0.01/次；早期用户报告拉三天 bookmarks 花费 $0.10 | **这是第一个把 MCP 单价化的头部平台**，为所有 MCP 变现设定了心理锚点。**可抄的具体做法**：①把我们的 MCP tool 加"每次调用记录+用量报告"端点（未来接计费）；②免费层限制（参考 PixelGust 50 调用/日）+ 付费层无限；③"agent 每 run 调用预算上限"作为防滥用机制 | X 是社交媒体数据，我们是农业知识，但**商业模式直接可复用** | ✅ 是（架构留扩展点） |
| **Legal MCP 集群（iManage / NetDocuments / Casepoint / Docusign / Relativity / Everlaw / Ironclad）** | https://thelegalwire.ai/mcp-the-protocol-thats-redrawing-the-legal-ai-stack/ | 各自商业 | iManage 2026-05-14；NetDocuments 2026-05-12（与 Anthropic 合作）；Casepoint 2026-07-30 | 律所文档管理系统的 MCP server 集中爆发：iManage 让任何 MCP 兼容的 AI 系统访问治理下的 iManage 内容，无自定义集成、无批量数据导出、保留道德墙和权限；Casepoint 于 7 月底跟进 | **⚠️ 这是本项目 MCP 商业化的最直接对标——垂直行业的"薄 wrapper + 强治理"模式**。可抄的具体做法：①"道德墙/访问控制保留"（我们的 recipe 可加"仅限某地区/某作物可访问"）；②"无批量导出，只有单查询"（避免被大规模爬取）；③"厂商 gain reach, lose stickiness"（iManage 的取舍），我们要在"广覆盖 vs 深度定制"间做明确选择 | Legal 是强治理行业，我们是农业，但**治理模型直接可复用** | ✅ 是 |
| **值得买 "海纳" MCP Server** | https://pdf.dfcfw.com/pdf/H2_AN202604271821633205_1.pdf | **三种模式**：调用计费 + CPS 佣金（商品点击转化）+ 数据服务（脱敏查询关键词卖品牌方） | 投资者关系记录 2026-04-27 | 每月 3 亿+ 次内容输出，接入国内主流大模型厂商，2025 双十一 + 2026 春节双高峰；官方 Skill 未来内置到 Agent 产品 | **⚠️ 这是国内最真实的 MCP 商业化案例**。可抄的具体做法：①**CPS 佣金模式**——如果我们 recipe 推荐了某个品种的种子/设备链接，可以从转化中抽成；②**数据服务模式**——把"用户查询哪些作物/气候条件"作为脱敏洞察卖给厂商（B 端）；③"Skill 内置到 Agent 产品"——我们的 9 个 Skill 未来可以内置到 Agent 生态 | 我们是农业 B 端 + C 端，他们是消费品 C 端；CPS 模式在农业硬件场景可行（推荐智能种植设备+抽成） | ✅ 是（架构留扩展点） |
| **MCP Hub 中国商业化报告** | https://yitb.com/archives/1313 | 各种（每张发票 0.8 元等） | 2026 首发 | 75 个 Server 已跑通 AI Agent 变现闭环，443 万+ 真实调用，服务 59 位开发者，平均单服务日均 180+ 次；案例：杭州"智链财税"用 invoice-ocr + tax-rules-validator + dingtalk-notifier 组成发票自动化 Agent，0.8 元/张，月均 2.3 万张，毛利 62% | **抄"三点串联"的组合模式**：我们的 pest Agent + nutrition Agent + climate Agent 可以打包成"一站式种植顾问"，按调用次数或按诊断次数计费。**具体参考定价**：0.8 元/次在财税场景已验证可行；我们的"高级配方生成"可对标 | 国内报告，数据可信度待独立验证 | ✅ 是 |
| **MCP 市场分成率对比** | AgenticMarket / ClawdMarket / MuleRun Creator Studio / x402 | AgenticMarket 80-90%（Wise/Razorpay 打款）；ClawdMarket 5%；MuleRun Creator Studio ~100% 减 launch bonus；x402 自控制 USDC | 2026-07 数据 | MCP 市场分成率 80-95%，远超传统 App Store 15-30% | **抄"多市场并行上架"策略**：我们的 MCP 上架 Glama + npm（已有），应补 AgenticMarket（80-90% 分成）+ LobeHub + Smithery + MCPize。**具体目标**：至少 3 个市场覆盖不同用户群 | — | ✅ 是（分发层，无技术依赖） |
| **付费 MCP 生态的实际定价（Bright Data / Firecrawl / Exa / Browserbase / Arcade / Zapier / Composio / Wayforth）** | https://stealwhatworks.com/blogs/news/mcp-servers-people-paying-for-now | 各异 | 2026 | Bright Data $1.50/1000 requests；Firecrawl $16/5K credits / $83/100K / $333/500K；Exa $7/1000 搜索 / $12-15/1000 深度搜索 / $1/1000 页取回；Browserbase 云浏览器订阅；Arcade $25/月 Team + $0.10/授权 + $0.01/工具调用；Zapier MCP $19.99/月起（每次调用 2 tasks）；Composio $29/月/20 万调用 | **抄"定价梯度"设计**：①免费层（限量）+ Pro 层（月订阅）+ 超量（per-call）；②参考 Arcade 的"平台费 + 授权事件 + 工具调用"三层计费（我们的"基础访问 + 高级 recipe + 单点诊断"可对齐）；③**Composio 的"29 美元 20 万次"换算 ≈ $0.00015/次**——这是当前市场上单工具调用的最低价锚点，说明"超便宜 per-call"是可行的 | 与我们的 MCP 商业化路径直接相关，可对标 | ✅ 是 |
| **MCP Gateway 商业定价** | https://tulimoa.com/blog/mcp-gateway-pricing | Tulimoa Free 25K credits/mo, Pro $29/250K, Scale $99/3M；Composio Free 20K/mo, $29/200K, $229/2M；Zapier 集成；TrueFoundry Pro $499/mo；Kong AI $100/月/模型 | 2026-07 数据 | MCP 网关从免费（开源）到 $2,999/月（企业级）全谱系；企业治理 camp（Traefik Hub / MintMCP / Lunar MCPX 等）全部 quote-only 无公开定价 | **抄"免费层 + Pro 层"的入门路径**：我们的 MCP 未来若提供托管版本，可对标 Composio 的"$29/200K"定价。目前只作记录 | 是网关不是内容，与我们不直接竞争 | — |
| **AgentPay Labs（个人开发者案例）** | https://dev.to/rumblingb/how-i-monetize-mcp-servers-in-2026-real-numbers-no-hustle-bros-4ekf | 五跳分发：MCP Server → npm → Smithery → Stripe payment link → Dev.to 文章 → Stripe Checkout | 2026-07 | 26 个 MCP server、61 npm 包、92 周下载、$0 收入（早期）；"~88% 感兴趣的用户在安装步骤流失"；解法是"MCP Bridge Chrome 扩展一键安装" | **⚠️ 这是反面教材 + 反面验证**：①"88% 安装流失"是行业问题，说明我们的 MCP 需要有"一键安装"体验（`claude mcp add ...` 单行命令 + 无需 env）；②"61 包 0 用户"说明"数量 ≠ 收入"，我们应聚焦少数高质量工具而非堆量；③"5 分钟变现清单"（npm 发布 → Smithery 部署 → Stripe 产品 → Dev.to 文章 → README 链接）是最小闭环 | 个人开发者，与我们规模不同 | ✅ 是 |
| **x402 微支付生态** | https://x402.foundation · https://docs.x402.org · https://lobehub.com/mcp/kten-agent-x402-mcp-server | 每笔 $0.001（1000 笔/月免费，之后 $0.001/笔） | 2026-07-14 x402 Foundation 成立；251+ 服务已索引，每 6 小时扫描新端点 | HTTP 402 语义化的微支付协议，USDC on Base/Solana；已用于 Hermes Asia x402 MCP（11 工具，$0.001-0.03/次）、@cryptoapis-io/mcp-x402-pay 买家侧工具 | **架构留扩展点，暂不实施**：我们的 MCP 未来可加 `@x402/mcp` 中间件让 agent 按次付费。**现在的准备**：①每次调用记录唯一 `call_id`（便于未来对账）；②tool 声明加 `billing_hint` 字段（`free` / `per_call` / `subscription`）；③预留"预算上限"参数 | 需以太坊链上签名，与零依赖冲突 | ❌ 否（现在）；✅ 是（架构预留） |
| **Moody's MCP（信贷备忘录自动化案例）** | https://softjourn.com/insights/what-is-mcp-server | 商业（内部工具） | 2026 | Moody's 的 MCP 应用把信贷备忘录准备时间从 40 小时降到 2 分钟（200 倍提升） | **对外叙事可参考**："把 X 小时的工作压缩到 Y 分钟"是 MCP 商业化的最强说服点。我们的对应指标："把'从零到生成一份针对某地某作物的完整种植配置'从 X 小时压缩到 Y 分钟" | Moody's 是金融专业用户，我们是农业 | — |
| **Expensify MCP（2026-06 官方）** | https://softjourn.com/insights/what-is-mcp-server | 官方托管 MCP | 2026-06 上线 | 官方 MCP server 让用户用自然语言查询账户消费（如"我上个月旅行花了多少"） | 仅作为"官方 MCP server 普及速度"的证据 | 报销工具，与农业无关 | — |
| **Docebo MCP GA** | https://softjourn.com/insights/what-is-mcp-server | 商业（企业 LMS） | 2026-07-22 GA | 企业 LMS 官方 MCP，把学习内容/注册/课程数据接入 AI 助手；CTO 直言："第一天那些工具不了解你的学习项目、技能数据、人员。MCP 改变了这一点" | 抄 CTO 的原话作为对外叙事："第一天那些 agent 不了解你的作物知识、气候数据、种植场景。MCP 改变了这一点" | 教育 SaaS | — |
| **iManage MCP 关键洞察** | https://thelegalwire.ai/mcp-the-protocol-thats-redrawing-the-legal-ai-stack/ | 商业 | 2026-05-14 | iManage 的 MCP 是"substrate"（基座）而非"产品"：让上层法律 AI 产品更容易部署、更容易治理、更容易替换，也让它们**从律所视角变得可互换** | **⚠️ 关键洞察**：iManage 用"基座"策略换取"分发广度"，代价是"厂商 stickiness 下降"。**我们的选择**：做"基座"还是"产品"？当前是"产品"（有 110 个 recipe 的专有资产），应继续保持，不要走"纯基座"路线 | — | — |

**要点**：这个方向的核心洞察是——**MCP 商业化在 2026 年 6-9 月第一次形成了完整的价格光谱**：
- 免费（大量 wrapper）
- Per-call 微支付（x402 $0.001/次、X $0.01/次）
- Per-call 中量（Arcade $0.10/授权、Composio ≈ $0.00015/次）
- 月订阅（Zapier $19.99/月、Arcade $25/月、Composio $29/月）
- 混合（Bright Data 基础设施费 + 按次；Firecrawl credit 包）
- 结果计费（每张发票 0.8 元、CPS 佣金、Moody's 时间节省）

**本项目应对**：不追求单一模式，而是**留架构扩展点**——每次调用记录 `call_id`、tool 声明加 `billing_hint` 字段、预留预算上限参数。**现在实施计费过重，但架构预留成本极低**。

---

## 7. 本项目立即可叠加的具体改进（按 ROI 排序）

| # | 做什么 | 参考哪个项目/哪一段代码 | 工作量级 | 是否破坏零依赖 | 预期收益 |
|---|---|---|---|---|---|
| **1** | **MCP 2026-07-28 无状态适配**：移除 server 端 session 状态；tool 返回加 `ttlMs` 字段（Env Recipe 更新频率=季度 → `ttlMs: 2592000000`）；tool 调用加 `Mcp-Method`/`Mcp-Name` 头支持；`_meta.traceparent` 头接收；Env Recipe 作为显式 handle 暴露（`recipe_id` 而非隐式缓存） | MCP SEP-2575/2567/2243/2549/414（https://modelcontextprotocol.io 2026-07-28 spec） | **中**（重构 mcp/server.py，估计 2-3 天） | ✅ 否（JSON-RPC 无状态本就是纯 stdlib） | **合规必需**：不做会在新客户端版本失效；且无状态化让我们能横向扩展到多个实例 |
| **2** | **加 A2A Agent Card**：创建 `/.well-known/agent.json`，声明 4+3 Agent 的 skills、inputs/outputs（Env Recipe schema）、auth（none）、SLAs；用 stdlib `hmac`+`hashlib` 实现 JWS ES256 签名（RFC 7515 + RFC 8785 canonical JSON） | A2A v1.0 spec + Google Dev Forum 2026-07-16 官方博文 | **中**（JSON 文件 + 签名算法 ~200 行） | ✅ 否 | **新增一层可发现性**：让 peer agent 能自动发现我们；对标 aishield-mcp-server 先例 |
| **3** | **用 Agent Plugins 1.0.0 打包分发**：创建 `plugin.json`（manifest）+ `skills/` 目录（9 个 Skill 按 SKILL.md 格式）+ `mcp.json`（9 个 MCP 工具定义）；跨 Claude / Cursor / Copilot / VS Code 通用 | Google Agent Plugins 1.0.0 规范（2026-08-06 发布） | **小-中**（目录约定 + manifest 编辑，1-2 天） | ✅ 否 | **分发升级**：从"2 家市场"扩到"5 家客户端市场"，且不用改代码 |
| **4** | **对齐 Anthropic Agent Skills 官方 schema**：校验现有 9 个 Skill 的 `SKILL.md` 是否符合 `name ≤64 字符仅小写字母数字连字符` + `description ≤1024 字符`；参考 SDK 写一个纯 stdlib 的 skill loader | Anthropic Agent Skills spec（agentskills.io） | **小**（校验 + 微调，半天） | ✅ 否 | **规范化**：确保 Skill 能被第三方市场收录（SkillsMP / AgentPowers.ai / LobeHub.com） |
| **5** | **接入 CMIP7 情景数据**：把 7 个情景（H/HL/M/ML/L/VL/LN）作为 `climate_scenario` 参数加入 climate Agent 输出；为每个 Env Recipe 提供"当前政策情景（M）"和"最坏情景（H）"两版生长窗口对比 | CMIP7 high-level 摘要（GMD 期刊 2026-04）+ 数据索引 climate-resource.com | **中**（数据解析 + Agent 逻辑，3-5 天） | ✅ 否（CSV 数据可用 stdlib 读） | **数据护城河**：首次接入 AR7 数据底座，与所有历史气候工具形成代差 |
| **6** | **前端 CDN 引入 CesiumJS 1.143**：单文件 HTML 加 `<script src="https://cesium.com/downloads/cesiumjs/releases/1.143/Build/Cesium/Cesium.js">`；用 `GeoJsonPrimitive` 加载 GAEZ 全球分区（绕过 entity 层，10 万点级性能）；用 `PathGraphics.materialMode=PORTIONS` 展示作物生长期路径分段着色 | CesiumJS 1.142/1.143 release notes | **中**（前端重写，3-5 天） | ✅ 否（后端不变，前端 CDN） | **用户体验飞跃**：从"表格+表单"升级到"3D 全球农业地图"，与 UN 机构级风格兼容 |
| **7** | **前端 CDN 引入 Deck.gl v9.4**：加 `<script src="https://unpkg.com/deck.gl@9.4/dist.min.js">`；用 `HexagonLayer` 展示 Env Recipe 覆盖密度（每个 hex 有多少个配方）；用 `TileLayer` 加载 GEE 的 PML V2.2a 500m GPP/ET 瓦片 | Deck.gl v9.4 What's New（2026-09-05） | **中**（前端组件，2-3 天） | ✅ 否（CDN） | **可视化升级**：从静态表格到交互热力图 |
| **8** | **交互模式参考 Earth NullSchool**：climate Agent 展示 Env Recipe 时加"时间轴驱动空间切片"——用户选一个时间 → 看全球气候切片 → 判断该时刻配方风险 | Earth NullSchool UX 哲学 | **中**（前端交互，2-3 天） | ✅ 否（前端） | **用户体验**：从"看配置"升级到"看场景" |
| **9** | **注册到 AgenticMarket + LobeHub + Smithery + MCPize**：4 家市场并行上架，目标分成率 80-90%（AgenticMarket） | AgenticMarket / LobeHub / Smithery / MCPize 上架流程 | **小**（填写索引元数据，1 天） | ✅ 否 | **分发广度**：从 2 家（Glama+npm）扩到 6 家，覆盖不同用户群 |
| **10** | **MCP 商业化架构预留**：①每次调用记录唯一 `call_id`；②tool 声明加 `billing_hint` 字段（`free` / `per_call` / `subscription`）；③预留"预算上限"参数；④免费层限制（参考 PixelGust 50 调用/日） | X Hosted MCP $0.01/call + Composio $29/200K + 值得买海纳三种模式 | **小**（架构调整，1 天） | ✅ 否 | **商业化基础**：现在不收费但架构就位，未来切换零成本 |
| **11** | **Pipeworx 式"网关 + 多源"评估**：评估是否接入 Pipeworx 网关而非自建所有数据源 MCP；`ask_pipeworx(question)` 自然语言查询接口 | Pipeworx mcp-noaa-spc 架构（2026-09-08） | **小-中**（评估 + 集成，1-2 天） | ✅ 否（作数据源调用） | **分发效率**：一个 URL 接入 250+ 数据源 |
| **12** | **对外叙事升级**：参考 Cannes Lions 2026 Creative Data 三大趋势 + Moody's "40 小时 → 2 分钟" 说服点 + Docebo CTO 原话；重写项目介绍页 | Cannes Lions 2026 趋势报告 + Moody's 案例 + Docebo CTO 引言 | **小**（文档，半天） | ✅ 否 | **叙事说服力**：从"技术描述"升级到"商业价值" |

---

## 8. 不建议做的事

1. **⛔ 不要接入司农 Sinong / 神农大模型 4.0 / iPheno / SPROUT 任何一个作为 LLM/视觉模型后端。** 需要深度学习栈，与本项目"零依赖纯 Python 标准库"的硬约束直接冲突。它们是我们的**概念参照**，不是**技术组件**。
2. **⛔ 不要接入神农·农业世界模型 1.0 作为决策引擎。** 他们做的是"给定状态→推演不同动作的产量/风险"，我们做的是"给定作物×阶段×箱体条件→输出环境参数"，思路互补但同向。**做对标不做跟随**——我们有零依赖+本地+Agent-native 的差异化。
3. **⛔ 不要实施 x402 微支付。** 现在实施过重：需 USDC 钱包 + facilitator + 以太坊链上签名，与零依赖冲突。**只做架构预留**（call_id + billing_hint + 预算上限参数）。
4. **⛔ 不要模仿 MEOK AI Labs 系列的"薄 wrapper + 合规营销"策略。** agriculture-robotics-mcp / gardening-ai-mcp 号称 300+ MCP server，全部是薄包装 + "EU AI Act 合规"营销，无实际工具文档。这是 MCP 生态的注水现象，会污染索引质量，也会拉低我们的品牌。
5. **⛔ 不要再接一个 Open-Meteo wrapper。** 已至少有 4 个类似的薄 MCP（isdaniel / mufens / first-it-consulting / CodeByWaqas），同质化严重。我们的气候数据应来自自有 Env Recipe + CMIP7 + GEE 派生量，而非又一个 wrapper。
6. **⛔ 不要接入 Google Maps Custom Satellite Embeddings。** 需 Private Preview 申请 + 商业合同；且 embedding 是黑盒，与我们的可解释 Env Recipe 哲学冲突。
7. **⛔ 不要整体替换前端为 D3.js。** D3 灵活度极高但学习曲线陡，与"单文件 HTML + UN 机构级风格"冲突。可考虑用 D3 只做"物候时间序列"这一个特定组件（d3-scale + d3-shape），不要全面替换。
8. **⛔ 不要接入 Google Earth AI / Microsoft Planetary Computer Pro 作为数据后端。** 两者都需要云账号 + 商业合同，与"零依赖本地部署"冲突。可作**架构参照**（STAC 目录标准、GeoCatalog 元数据规范、Vector Tile API），不可作**运行时依赖**。
9. **⛔ 不要走"纯基座"路线。** iManage MCP 的"基座"策略换取了分发广度但损失了 stickiness。**我们继续保持"产品"定位**——有 110 个 recipe 的专有资产、有 Agent 生态、有 MCP server，这是完整的闭环，不要拆散。
10. **⛔ 不要堆量。** AgentPay Labs 案例证明"61 个 MCP server、92 周下载、$0 收入"是常见失败模式。**聚焦少数高质量工具**，不追求覆盖广度。
11. **⛔ 不要重复 2026-09-17 扫描中已覆盖的项目**：FAOSTAT、OpenAg、Horticulture-Assistant、OpenGrowBox-HA、HA-Plant-Assistant、simple-plant-extended、FarmerConnect-MCP、agrobr-mcp、agrisignal-mcp、MCP_USDA_Server、CropProphEU（分发渠道参考除外）、PlantVillage、PlantDoc、Corn Leaf Disease、天池 rice disease、AGRIFOLD、agroclim、vegperiod、cropgrowdays、Open-Meteo、SILO、NASA POWER、LobeHub MCP Marketplace（渠道确认除外）、Scineer 论文、武汉农博会、今日头条、中国报告大厅、新京报、Home Assistant 社区。**本报告严格限定 2026-06 到 2026-09 的新信号**。

---

## 9. 待核实清单

以下信息未在扫描中 100% 确认，使用前必须人工复核：

1. **Agent Plugins 1.0.0 的完整 spec 文本** —— 仅通过 atmarkit 日文报道和 Google 官方博客获得概要，未读到完整规范。`plugin.json` 的具体字段清单（name/version/author/skills/mcp/dependencies 等）待核实。
2. **Anthropic Agent Skills 参考 Python SDK 的具体位置** —— 官方文档提及有 SDK 但 URL 未直接读到；`agentskills.io` 域名是否可访问待验证。
3. **A2A Agent Card 的完整字段清单** —— 已知支持 JWS 签名、OAuth 2.0 Device Code、多租户、`google.rpc.Status` 错误、`A2A-Version` 头，但完整 schema 需查 a2a-protocol.org。
4. **CMIP7 7 个情景的完整定义** —— 已获得名称（H/HL/M/ML/L/VL/LN）和 2100 升温范围，但每个情景的完整排放/CDR 时间序列需从 GMD 期刊或 scenario.mip.ipsl.jussieu.fr 下载核实。
5. **CMIP7 气溶胶强迫数据的完整 license** —— Zenodo 存储，具体 CC 版本待核实。
6. **司农 Sinong 8B/32B 的实际 license** —— 百度百科描述"魔搭社区 + GitHub 开源"，具体 license 类型（Apache 2.0? MIT?）待 GitHub 仓库核实。
7. **神农大模型 4.0 与神农·农业世界模型 1.0 的完整 license** —— 中国农大新闻页仅提"开源"，具体 license 类型待核实。
8. **iPheno 代码仓库的实际 license** —— 论文是 CC BY-NC-ND 4.0（禁止衍生），代码仓库 `2997029323/iPheno-PC-Client` 的 license 可能不同，需 GitHub 页面核实。
9. **PhytoScan3D 的 MIT license 具体范围** —— preprint 声明 MIT，但仓库 `kovimallik/phytoscan3d` 是否包含 LICENSE 文件、以及是否覆盖所有算法需核实。
10. **GEE 2026-08 新数据集批次的完整 license 清单** —— PML V2.2a 已确认为 CC BY 4.0，GEDI L4D / MAPL-EMIT / VIIRS VNP43MA3 / NOAA CFSR 的具体 license 需从 GEE Data Catalog 逐条核实。
11. **Microsoft Planetary Computer Pro MCP Tools VS Code 扩展的 173 installs 是否包含真实用户** —— Marketplace 显示 173 installs，但可能是内部/测试安装，真实用户数待核实。
12. **Pipeworx 网关的 250+ 数据源清单** —— 已确认 mcp-noaa-spc 是其中之一，但完整清单、稳定性、SLA 需查 gateway.pipeworx.io。
13. **PixelGust MCP 的实际 license 和付费层定价** —— 免费层 50 调用/日已确认，付费层价格待 pixelgust.com/app 核实。
14. **X Hosted MCP $0.01/call 的实际生效条款** —— 已确认"1000 calls = $1"，但企业层（$5K/月起）的具体条款需查 X developer dashboard。
15. **值得买"海纳" MCP Server 的 3 亿+/月 数据可信度** —— 投资者关系活动记录，未经独立第三方审计。可能口径不同（是"调用次数"还是"内容展示次数"）。
16. **MCP Hub 中国报告（yitb.com/archives/1313）的 75 server / 443 万调用数据可信度** —— 首发报告，数据可信度待独立验证。特别是"0.8 元/张发票、月均 2.3 万张、毛利 62%"的具体案例。
17. **AgenticMarket 80-90% 分成率的具体条件** —— 已确认 Wise/Razorpay 打款，但分成率的具体条件（是否含启动期补贴、是否有最低交易量要求）待查。
18. **CesiumJS 1.143 的 Apache-2.0 具体范围** —— 已确认 Apache-2.0（Snyk 数据库、npm 元数据、GitHub 一致），但 `3DTILES_content_gltf_vector` 等扩展的专利条款需查 Khronos Group。
19. **Deck.gl v9.4 的 MIT license 具体范围** —— Yarn 显示 MIT，但 `@deck.gl/maplibre` 等子包的 license 需逐个核实。
20. **Cesium Copilot 的 AI 后端具体供应商** —— 已知支持 Google Gemini / Anthropic Claude / Google Vertex AI（用户自带 key），但具体 API 调用方式、prompt 模板待 Sandcastle 实测。
21. **Earth NullSchool 的 GPL-3.0 传染性范围** —— 已确认 GPL-3.0，但若我们前端参考其交互模式（不复制代码）无传染风险；若复制代码有传染风险。需明确"参考 UX 哲学"而非"复制代码"。
22. **VAPOR 的 BSD-3-Clause 具体范围** —— LinuxLinks 描述为 BSD-3-Clause，需 GitHub `NCAR/VAPOR` 仓库 LICENSE 文件核实。
23. **Cannes Lions 2026 Creative Data 三大趋势报告的具体引用来源** —— adgully.com 报道，具体案例（Suncorp Haven / Forests Without Names / SOS POS）的原始获奖页待 Cannes Lions 官方核实。
24. **D3.js v8 是否真的存在** —— 搜索未发现 v8 明确发布，最新仍是 v7.9.0。任务清单中"D3 v8 相关生态"的描述可能基于过时信息或误解。
25. **"Agent2Agent" 与 "Agent Connect Protocol" 术语混淆** —— A2A 是 Google 的 agent-to-agent 协议（Linux Foundation），ACP 有三个不同含义（IBM 已并入 A2A / Stripe+OpenAI 电商 / Amazon+Microsoft+OpenAI+Vercel 工具协议）。对外叙事时需精确区分。
26. **aishield-mcp-server v4.2.2 的具体规则/技能/工具数量** —— 用户描述"MCP 227 rules / Skill 233 / 6 tools"，本次未直接核实；本项目对标时需以最新版本为准。
27. **本项目当前 SKILL.md 格式是否已符合 Anthropic 官方 schema** —— 需读取现有 `skills/registry/*.json` 或 SKILL.md 文件核对；本次扫描未检查现有 Skill 格式。

---

## 附录：本次扫描核实的关键 URL

**方向一：Agent-native 协议**
- A2A 项目仓库 · https://github.com/a2aproject/A2A
- A2A v1.0 官方博客 · https://discuss.google.dev/t/what-s-new-in-a2a-v1-0-a-python-dx-glow-up-and-a-fresh-new-look/381896
- A2A 加入 AAIF · https://aaif.io/blog/a2a-joins-aaif
- A2A 完整指南 · https://rapidclaw.dev/blog/a2a-protocol-ai-agent-hosting
- MCP 2026-07-28 spec · https://modelcontextprotocol.io · SEP-2575/2567/2243/2549/414
- MCP Apps 规格 · https://modelcontextprotocol.io/apps
- MCP Dev Summit NY 2026 · https://mcp.devsummit.org
- Agent Plugins 1.0.0 日文报道 · https://atmarkit.itmedia.co.jp/ait/spv/2609/10/news034.html
- Anthropic Agent Skills · https://console.anthropic.com/docs/agents-and-tools/agent-skills/overview
- Anthropic Skills 开放标准 · https://support.anthropic.com/en/articles/12512176-what-are-skills
- Agent Skills 完整指南 · https://likeone.ai/blog/claude-agent-skills-guide-2026
- x402 Foundation · https://x402.foundation
- AP2 · https://github.com/google-agentic-commerce/AP2
- ACP（Stripe+OpenAI） · https://stripe.com/blog/agentic-commerce-protocol
- ACP（Amazon+MS+OpenAI+Vercel） · https://forum.gnoppix.org/t/amazon-cursor-microsoft-openai-and-vercel-unite-on-a-shared-standard-for-ai-agent-plugins/6987
- Agent 协议地图 · https://originpi.com/blog/agent-protocol-map-2026
- Agentic Commerce 生产实践 · https://www.reactify-solutions.com/articles/agentic-commerce-protocols-2026

**方向二：农业/气候新项目**
- CMIP7 high-level 摘要 · https://www.scitechpulse.com/en/news/cmip7-climate-model-emissions-scenarios
- CMIP7 数据可用性索引 · https://www.climate-resource.com/tools/esm-model/cmip7-availability
- CMIP7 情景解释 · http://breakingclimatechange.com/explainer-the-cmip7-emissions-scenarios-and-how-they-explore-future-climate-change
- CMIP7 气溶胶强迫 · https://www.iup.uni-heidelberg.de/de/node/798
- 司农 Sinong 百科 · https://baike.baidu.com/item/%E5%8F%B8%E5%86%9C/68098246
- 神农 4.0 + 世界模型 1.0 · https://ciee.cau.edu.cn/art/2026/7/14/art_50389_1122523.html
- 神农世界模型发布新闻 · https://news.sciencenet.cn/htmlnews/2026/7/568595.shtm
- iPheno · https://www.cell.com/plant-communications/fulltext/S2590-3462(26)00404-9
- PlantCV v4 · https://doi.org/10.1002/ppj2.70065
- PhytoScan3D · https://github.com/kovimallik/phytoscan3d · https://preprints.epiforecasts.io/paper/10.64898/2026.06.01.729298
- SPROUT · https://arcxiv.org/abs/2603.27519
- GEE 2026-08 新数据集 · https://m.toutiao.com/article/7681985346657124870
- AlphaEarth Foundations · https://www.toolai.io/ja/v5/info/3447
- Google Maps Custom Satellite Embeddings · https://android.gadgethacks.com/news/google-maps-custom-satellite-embeddings-5-day-monitoring
- Google Earth AI UK Hedgerow · https://esgnews.com/google-releases-earth-ai-dataset-to-map-hidden-nature-assets-across-uk-farmland
- Microsoft Planetary Computer Pro GA · https://aka.ms/MPCP_GA
- Microsoft Planetary Computer Pro 更新日志 · https://learn.microsoft.com/azure/planetary-computer/whats-new
- Microsoft Planetary Explorer · https://github.com/microsoft/Planetary-Explorer

**方向三：MCP 农业生态**
- Microsoft Planetary Computer Pro MCP Tools（VS Code） · https://marketplace.visualstudio.com/items?itemName=ms-iot.planetary-computer-pro-mcp-tools
- Microsoft Planetary Computer Pro 博客 · https://techcommunity.microsoft.com/tag/microsoft%20planetary%20computer
- Pipeworx mcp-noaa-spc · https://lobehub.com/mcp/pipeworx-io-mcp-noaa-spc
- PixelGust MCP · https://pixelgust.com/mcp
- CropProphEU · https://github.com/DasClown/CropProphEU
- MEOK AI Labs agriculture-robotics-mcp · https://github.com/CSOAI-ORG/agriculture-robotics-mcp
- MEOK AI Labs gardening-ai-mcp · https://github.com/CSOAI-ORG/gardening-ai-mcp
- FarmerTasksAI MCP · https://github.com/TasksAI-Official/tasksai-mcp-wrappers/tree/main/verticals/farmer
- Weather MCP Server（isdaniel） · https://github.com/isdaniel/mcp_weather_server

**方向四：数据可视化**
- CesiumJS 2026-06 release · https://cesium.com/blog/2026/06/01/cesium-releases-in-june-2026/
- CesiumJS 2026-07 release · https://cesium.com/blog/2026/07/01/cesium-releases-in-july-2026/
- CesiumJS Snyk 数据库 · https://security.snyk.io/package/npm/cesium
- Deck.gl What's New · https://deck.gl/docs/whats-new
- Deck.gl Yarn · https://classic.yarnpkg.com/en/package/deck.gl
- 近期发布速报 · https://geo.malagis.com/recent-releases-cesiumjs-geopandas-deckgl-osrm-eoreader.html
- Earth NullSchool · https://earth.nullschool.net
- VAPOR · https://github.com/NCAR/VAPOR
- 2026 Pacific Dataviz Challenge · https://www.stats.org.nz/2026-pacific-dataviz-challenge-climate-change/
- Cannes Lions 2026 Creative Data · https://www.adgully.com/post/17353/anupriya-acharya-identifies-three-trends-shaping-creative-data-at-cannes-lions-2026
- D3.js · https://d3js.org

**方向五：商业化案例**
- X Hosted MCP $0.01/call · https://ai-cost-estimator.com/blog/x-hosted-mcp-launch-per-call-pricing-agent-data-access-cost-baseline
- Legal MCP 生态 · https://thelegalwire.ai/mcp-the-protocol-thats-redrawing-the-legal-ai-stack/
- MCP 服务器已付案例 · https://stealwhatworks.com/blogs/news/mcp-servers-people-paying-for-now
- 值得买海纳 MCP · https://pdf.dfcfw.com/pdf/H2_AN202604271821633205_1.pdf
- MCP Hub 中国报告 · https://yitb.com/archives/1313
- MCP 变现 5 分钟清单 · https://dev.to/rumblingb/how-i-monetize-mcp-servers-in-2026-real-numbers-no-hustle-bros-4ekf
- AgentPay Labs 案例 · https://dev.to/rumblingb/mcp-monetization-how-agentpay-labs-turns-mcp-servers-into-revenue-streams-4cb3
- 2 小时构建案例 · https://clawdbytes.com/article/2026-07-01-how-to-make-money-building-mcp-servers-in-2026-i-just-shipped-one-in-2-hours
- MCP 计费综述 · https://usagebox.com/articles/how-to-charge-for-mcp-server-2026-per-call-subscription-x402
- MCP 网关定价 · https://tulimoa.com/blog/mcp-gateway-pricing
- x402 Coinbase 案例 · https://theagenttimes.com/agents/article/coinbase-x402-protocol-gives-us-a-working-path-to-autonomous-83ca3fc1
- x402 Build Log · https://niteagent.com/blog/ai-crypto-x402-pay-per-call-build-log-2026
- x402 Hermes Asia · https://lobehub.com/mcp/kten-agent-x402-mcp-server
- MCP 商业化综述（Softjourn） · https://softjourn.com/insights/what-is-mcp-server
- MCP 深度解析（中文） · https://siuleeboss.com/ai-news/mcp-2026-ai-infrastructure-2026-08-10

---

*报告完成于 2026-09-19。所有结论基于本次扫描时间窗内的公开信息，遵循"不确定即标注"原则。下次扫描建议窗口：2026-10-19 至 2026-12-19。*

