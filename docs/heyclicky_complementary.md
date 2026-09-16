# HeyClicky 借鉴研发清单（农业项目版）

> 编制日期：2026-09-14｜方法：WebSearch 一手情报（heyclicky.com / HokAI / DailyDropout / NeatPrompts 评测）+ GitHub `farzaa/clicky` README/CLAUDE.md 技术核实
> 目的：对照「智慧农业生态」五模块 + 四 Agent 闭环，从 HeyClicky 这个**交互范式级**开源项目里，挑出可借鉴/提升的点并给出落地动作
> 定位：本清单是**交互与产品层**借鉴，与 `opensource_scan_complementary.md`（数据/MCP/模型层）互补；不重复后者内容

---

## 〇、HeyClicky 是什么（事实锚定）

| 项 | 事实 |
|---|---|
| 项目 | HeyClicky（开源快照名 `clicky`），github.com/farzaa/clicky，MIT |
| 创始人/融资 | Farza Majeed（曾做 Buildspace，a16z+YComb 支持）；YC S26，$10.1M |
| 形态 | macOS 菜单栏原生 App（Swift 95.2%），住在光标旁 |
| 核心能力 | ① 实时屏幕感知（ScreenCaptureKit 截屏→Claude 视觉）② Push-to-Talk 语音（AssemblyAI 流式 ASR + ElevenLabs TTS）③ 视觉光标指向（`[POINT:x,y:label:screenN]` 驱动透明叠加层）④ 后台 Agent（"clicky agent" 一句话派活）⑤ 原生集成（Notion/Gmail/Calendar/Linear） |
| 密钥架构 | **Cloudflare Worker 代理**：App 只连 Worker，Worker 连三家 API，密钥不入客户端二进制（`worker/src/index.ts` 三路由 `/chat` `/tts` `/transcribe-token`） |
| 交互范式 | "AI 来到你身边"——不让你离开当前窗口去找聊天框，而是看你在看什么、听你说什么、直接指给你看下一步 |
| **重要警示** | **2026-04-27 后新功能已转闭源**，公开 repo 是冻结快照；只能借鉴快照架构，不能指望持续同步 |
| 短板 | macOS-only（无 Win/Linux）；**无公开 API / MCP（API 评分 4/10）**；Agent 月限额（Pro 150 条）；太新无长期可靠记录；复杂任务成功率有限；靠"模拟点击 UI"操作应用，界面一变就失效 |

---

## 一、互补性基准（HeyClicky 强项 vs 农业项目缺口）

| 维度 | HeyClicky 强项 | 农业项目现状 / 缺口 | 可借点 |
|---|---|---|---|
| 交互范式 | 在场、屏幕感知、语音、零设置 | 当前是 **Web 聊天框 Demo + MCP 工具**，用户需"来找 AI" | 学"在场教练"定位，把入口从聊天框前移到大棚/阳台现场 |
| 执行引导 | 光标指向 `[POINT]` 标出"点这里" | Env Recipe 只给**文本参数集**，缺"最后一公里"引导执行 | 做**农业版图标注叠加层**：照片上画箭头/圈出"该拧这个旋钮、设到 X" |
| 语音 | 流式 ASR + 真人 TTS | 无任何语音层 | 种植者手脏/湿，语音天然契合；可加轻量语音层 |
| 后台 Agent | 一句话派后台 Agent 跑全任务 | `orchestrator.py` 四 Agent 流水线**已有**，但无"对话式一键触发 + 进度可见" | 把 `POST /api/agent` 包成"一句话优化我的环境"入口 |
| 密钥隔离 | CF Worker 代理隔离三家密钥 | `vision.py` 用 env 变量，Web Demo 暴露有风险 | 加轻量代理/复用 ATEX 网关的 `host.docker.internal` 模式 |
| 信任叙事 | 开源 + 自托管 + 按键才看屏 + 截图不存 | AgriTrust 雏形（数据本地/可审计）已有 | 把"你的农情数据留在本地、可审计、不强制回传"做成对外核心卖点 |
| **MCP / agent-native** | **弱（无 MCP，API 4/10）** | **强（9 工具零依赖 MCP server，已上架思路）** | **反向强化**：把"MCP-native 可机读、可嵌入任意 Agent"当差异化卖点（强化 P0-F） |
| 平台 | macOS-only | 应做 **Web / 跨端** | 不抄平台；借鉴 UX 不抄 Swift 代码 |

---

## 二、借鉴研发总表

### A 档 · 直接可改造（高 ROI、低新增依赖，建议近期做）

| # | 借鉴点 | 对应模块·闭环 | 可落地方案（具体到文件） | 优先级 |
|---|---|---|---|---|
| A1 | **图标注引导叠加层（Visual Annotation Overlay）** | 模块⑤生成箱 · 反馈闭环（数据 A 的执行引导） | 把 HeyClicky 的 `[POINT:x,y:label]` 协议改造成**农业执行引导**：用户上传一张种植箱/传感器面板/病叶照片 → `vision.py`（或 VisionAgent）识别 → 输出**标注坐标 JSON**（圈出"该调这里"、箭头指向"这个旋钮"）→ 前端 `app/index.html` 用 canvas/SVG 画叠加层。这是 Env Recipe 执行层最缺的"最后一公里"。零新增后端依赖（前端 canvas + 现有 vision 后端） | ★★★ |
| A2 | **语音交互层（Push-to-Talk）** | 模块③病虫害 / 全链路查询 | 借鉴"按住说话→语音指导"：前端用 **Web Speech API** 做零后端 ASR（浏览器原生，零成本），把识别文本喂给现有 MCP 工具 / `POST /api/agent`；回合用 TTS（浏览器 SpeechSynthesis 或 ATEX 网关）播报。种植者手脏场景直接命中 | ★★ |
| A3 | **一键后台 Agent 触发（"clicky agent" 模式）** | 四 Agent 编排闭环 | 现有 `orchestrator.py` 已有 climate→crop→growth→eco 串行 + pest/nutrition 按需。借 HeyClicky 的"一句话派后台"：在 Demo 加"优化我的环境"入口，一句话触发全流水线并在前端显示进度（参照 `CompanionManager.swift` 的状态机思路），跑完直接产出 Env Recipe | ★★ |

### B 档 · 架构 / 战略借鉴（取其设计，不抄代码）

| # | 借鉴点 | 对应动作 | 优先级 |
|---|---|---|---|
| B1 | **API 密钥经代理隔离（Cloudflare Worker 三路由）** | 把 agri 的视觉/LLM 密钥从 Web 客户端隔离：加一个轻量代理（或复用 ATEX 网关的 `host.docker.internal:8420` 模式），Web Demo 只连代理不连密钥。对应 `worker/src/index.ts` 的 `/chat` `/tts` `/transcribe-token` 思路 | ★★ |
| B2 | **"AI 来你身边"的范式定位** | 战略层最该借的：v2.1 已定"免费入口换数据"，HeyClicky 用产品证明"入口=在场交互"比聊天框转化高。把对外定位从"全球农业知识底座"升级为"**在场教练 / 配置执行引导器**" | ★★★ |
| B3 | **开源 + 自托管 + 零强制遥测 的信任叙事** | 对标 HeyClicky 的"代码全摊开 + 按键才看屏 + 截图不存"。农业数据（大棚布局/产量）敏感，把 AgriTrust（数据本地、可审计、不强制回传、可自托管 MCP server）做成对外核心信任卖点 | ★★ |
| B4 | **Build-in-public 发布打法** | 借其病毒逻辑：① 做"30 秒在场演示"（站大棚里问一句→屏幕标出该拧哪个旋钮）而非架构宣讲；② 用每日闭环报告（`outputs/daily_loop_*.md`）做**诚实公开指标**（对标其"is my product trash?"自审）；③ 文案结构照抄"我不做 10/10 产品，只是个还行的起点"的谦诚实风格 | ★★ |

### C 档 · 反向借鉴（agri 已领先，应强化而非抄）

| # | 点 | 动作 |
|---|---|---|
| C1 | **HeyClicky 无 MCP / API 弱（4/10）** | agri 已有 9 工具零依赖 MCP server（P0-F）。把"**MCP-native、可机读、可嵌入任意 Agent、不止是聊天框**"当相对 HeyClicky 的差异化卖点，强化 Glama/npm 投递叙事 |
| C2 | **HeyClicky 靠"模拟点击 UI"（脆弱）** | agri 走 **Env Recipe 协议下发**（P0-G）比模拟点击稳——设备界面/固件一变，模拟点击就失效，而协议字段稳定。明确在对外材料里讲清"我们不下发点击、下发可执行配置"的架构优势 |

---

## 三、优先级总排序与工作量（建议先做 A1）

### P0（最高 ROI，直接补"执行引导"缺口）
| 项 | 动作 | 工作量 | 阻塞 |
|---|---|---|---|
| **A1** | 农业图标注叠加层：照片→识别→`[POINT]` 式坐标 JSON→前端 canvas 画箭头。先接现有 `vision.py`（未配则降级规则识别 + 用户手动标） | 中（前端 canvas + 一个 `agent/guided_overlay.py` 输出标注 JSON） | 视觉后端未配置（可先用规则/手动标兜底）；本机无 NVIDIA |
| A3 | Demo 加"一句话优化环境"入口，触发 orchestrator 全流水线 + 进度 + 出 Env Recipe | 低–中（前端入口 + 复用 `POST /api/agent`） | 无 |

### P1（语音 / 密钥隔离 / 信任叙事）
| 项 | 动作 | 工作量 | 状态 |
|---|---|---|---|
| A2 | Web Speech API 零后端 ASR + TTS 播报，接 MCP 工具 | 低（纯前端） | 未开始 |
| B1 | 密钥代理隔离（复用 ATEX 网关模式） | 低 | 未开始 |
| B3 | AgriTrust 信任叙事对外化 | 低（文案/文档） | 未开始 |

### P2（战略 / 发布）
B2 定位升级、B4 build-in-public 打法、C1/C2 差异化卖点——随下轮对外/投递推进。

---

## 四、关键风险与诚实标注

1. **HeyClicky 已闭源**：公开 repo 是 2026-04-27 冻结快照，新功能私有。只能借鉴快照架构，不能指望上游持续同步；不要做"实时跟随 fork"。
2. **平台不可移植**：Swift/macOS 技术栈，农业项目是 Python/Web。只能借 **UX/架构范式**，不能抄代码；我们反而应做 Web/跨端覆盖它不做的 80% 用户。
3. **模拟点击脆弱**：HeyClicky 靠模拟操作第三方 UI，农业硬件场景不适用。agri 坚持 Env Recipe 协议下发路线（P0-G），更稳，这是我们的架构优势而非要抄的点。
4. **复杂任务成功率有限**：HeyClicky 自身承认后台 Agent 偶尔"想偏"。agri 应坚持"**引导 + 人确认**"的 Env Recipe 模式，不做全自动托管幻觉。
5. **语音/视觉算力**：本机无 NVIDIA（GMKtec NucBox 集成显卡 32GB）。A1 视觉标注优先走云端 API（ATEX 网关 / SenseNova）或超轻量 CPU 模型；A2 语音用浏览器原生 ASR 零算力。

---

## 五、与既有文档的关系

- `docs/opensource_scan_complementary.md`：本清单的**交互/产品层**补充；前者覆盖数据/MCP/模型层，本清单覆盖"在场交互范式"，不重叠。
- `docs/env_recipe_protocol_v1.md`：A1 图标注叠加层是 Env Recipe 的**执行引导前端**，协议字段不变，只是多了"在设备上标出该调哪"的呈现。
- `mcp/README.md` + P0-F 投递：C1 反向借鉴的差异化卖点来源（9 工具 MCP server）。
- `docs/project_evaluation.md`：B2 定位升级、B3 信任叙事可回流到评审的"方法创新性 / 场景价值"维度。
