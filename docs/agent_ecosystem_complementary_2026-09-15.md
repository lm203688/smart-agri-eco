# AI Agent 生态项目借鉴研发清单（2026-09-15）

> 配套文档：`docs/heyclicky_complementary.md`（HeyClicky 单项目）、`docs/opensource_scan_complementary.md`（农业垂直开源基准）。
> 目标：对一批「通用 AI Agent / 多智能体 / 自我改进」开源与商用项目，判定其对「智慧农业生态」项目的借鉴价值，落到 A/B/C 档可研发清单。
> 方法：只借**架构 / UX / 技能分发 / 自我改进框架**模式，**不合并代码**（多数项目是 TS/Node/Electron/Swift/macOS 栈，与本项目 Python/Web 零依赖栈冲突；且多为 coding/research/desktop 智能体，非农业领域）。

---

## 〇 本批项目一手事实速查表

| # | 项目 | 性质 / 许可 | 一句话定位 | 关键技术点 |
|---|------|------------|-----------|-----------|
| 1 | OpenAI Agents API（2026-09-10 beta） | 托管 API（beta） | Codex 背后的基础架构托管化 | context compaction、tool search、原生 subagents、MCP 支持、开源 harness |
| 2 | Karpathy/autoresearch | 开源 MIT | 「编程程序」棘轮循环 | prepare.py/train.py/program.md 三文件 ratchet；需单卡 NVIDIA；附带 microgpt 轻量小模型代理框架 |
| 3 | Qwen-UI-Agent（Tongyi-MAI/MAI-UI） | 开源（阿里） | GUI 操作智能体基模 | 27B/35B-A3B/4B；控制手机/桌面/web/DeepSearch |
| 4 | HyperResearch（jordan-gibbs/hyperresearch） | 开源 MIT | 智能体驱动研究 wiki | 16 步管线、多智能体、来源溯源、绑定 Claude、Python 3.11-3.13 |
| 5 | Theseus Labs RSI 报告（arXiv 2609.11873） | 论文/报告 | 五级自主权框架 | B0→L1→L2→L3→L4→L5 + HCI（Headroom-Closed Index）度量 |
| 6 | CocoLoop（hub.cocoloop.cn） | 平台/生态 | agent Skills 合集 + 安全检查 | 12k–46k skills；CLS 安全分级 S/A/B/C/D；VM 隔离；OpenClaw 生态 |
| 7 | ponytail（DietrichGebert/ponytail） | 开源 | YAGNI agent 策略 | agent 写更少代码（~54% 更少）；14+ host |
| 8 | ElizaOS（elizaOS/eliza） | 开源 MIT | TS 多智能体框架 | HTN 任务分解、RAG、Web3 聚焦 |
| 9 | QoderWake（阿里） | 开源 | Harness-First 长时智能体 | Orchestrator 确定性 + Executor/Verifier 分离 + Session 幂等恢复；5 维经验；Anti-Rot 治理；7×24 事件触发 |
| 10 | SoL-Pi（NVlabs/SoL-Pi） | 开源 MIT | 长上下文效率机制 | Action Fusion / ObservationPack / Evidence-Preserving Reducer / Online Context Compact；默认 off；45–54% token 削减 |
| 11 | HeyClicky | 见 `heyclicky_complementary.md` | 视觉光标 + 语音桌面智能体 | 已单文档完成，本表交叉引用 |
| 12 | OpenMausBot（milind-soni/OpenMausBot） | 开源（MIT/Apache-2.0 表述不一） | 本地优先多智能体桌面壳 | claude/codex/grok CLI + 自定义 ACP/OpenAI 端点（Ollama 等）；harness 聚合事件流；本地存 `~/.openmausbot`；Allow/Deny 卡；本地 MCP server；定时 routine + webhook |
| 13 | bash+脚本 CLI「按需调用」 | 通用模式（多实现） | 受控按需执行 | just-bash（OverlayFS 丢弃写）、AIGNE（allow/deny + guard agent）、agentic-bash（白名单）、orchestrator（YAML 路由） |
| 14 | TeamAI（腾讯 teamai-cli v0.22.0） | 开源（npm） | Git-native 团队 harness 同步 | 三层 Execute→Understand→Learn→Self-Improve；摩擦信号学习共享；知识图谱；**明确支持 WorkBuddy** |

---

## 一 互补基线（我们的现状 vs 这批项目的共性能力）

| 我们的缺口 / 现状 | 这批项目提供的对应能力 | 结论 |
|---|---|---|
| 四 Agent 流水线（climate/crop/growth/eco）+ 按需 Agent，但**缺显式 Verifier 与长对话压缩** | OpenAI Agents API（subagent+compaction）、QoderWake（Executor/Verifier 分离）、SoL-Pi（Online Context Compact） | B→A：补齐 Verifier + 压缩 |
| Env Recipe 协议 v1 有执行字段，但**缺「最后一公里」设备端执行安全模型** | OpenMausBot（Allow/Deny 卡）、bash-CLI 模式（allow/deny + OverlayFS + guard agent） | B→A：设备端执行权限模型 |
| 数据飞轮（flywheel.py）+ skill_factory，**缺自主权分级与团队级学习共享** | Theseus RSI（L1–L5 + HCI）、TeamAI（三层自改进 + 摩擦学习）、QoderWake（5 维经验）、Karpathy ratchet | A：飞轮向 RSI 演进 + 采纳 TeamAI 自改进闭环 |
| 9 个 `agri_*` MCP 工具，**技能分发 / 安全检查 / 上架渠道弱** | CocoLoop（CLS 分级 + VM 隔离 + 分发）、OpenAI Agents API（MCP 生态）、OpenMausBot（本地 MCP server）、TeamAI（harness 分发） | A：技能安全分级 + 分发上架（与 aishield Glama 打法协同） |
| AgriTrust（本地数据 / 可审计 / 无强制遥测）**需更多「本地优先」叙事佐证** | OpenMausBot（本地优先）、bash-CLI（沙箱内执行）、CocoLoop（VM 隔离）、SoL-Pi（默认 off 可opt-in） | B：强化 AgriTrust 叙事与实现 |
| 无语音交互层 | HeyClicky（A2 语音层，见单文档）、OpenMausBot（可选 ElevenLabs TTS） | A2 已在 HeyClicky 文档落地 |
| 每日 05:00 单口闭环自动化，**仅定时、无事件/webhook 触发** | QoderWake（7×24 事件触发）、OpenMausBot（webhook + 定时 routine）、TeamAI（SessionStart hook 自动同步） | B→A：加事件/webhook 触发 + 幂等恢复 |

---

## 二 借鉴研发主表（A/B/C 档）

### A 档（直接采纳 / 最高优先，建议近期排期）

| 编号 | 来源项目 | 借鉴点 | 对应我们缺口 | 落地动作 | 风险 / 注意 |
|---|---|---|---|---|---|
| **A1** | Theseus Labs RSI | 五级自主权框架 B0→L5 + HCI 度量 | 飞轮缺自主权分级与北极星指标 | 把 flywheel 演进路线重排为：L1 执行（配方在固定规则内优化）→ L2 策略（跨城市/作物调参）→ L3 经验获取（execution_log 回流）→ L4 部署适应（skill_factory 自动生成技能）→ L5 递归元改进（未来）。HCI 作为与 P0-H eval 一致率并列的北极星 | 报告为 arXiv 预印本，编号 2609.11873 需复核实测可达性；先借框架不改底层 |
| **A2** | TeamAI（腾讯 teamai-cli） | Git-native harness 同步 + 三层自改进闭环 + 摩擦学习共享 | flywheel/skill_factory 需团队级规模化、且**原生支持 WorkBuddy** | 将我们的 skills/rules/agents/MCP/env 纳入 Git 仓库、走 MR 评审（与本机 gh_push.py 推送链路天然契合）；采纳「Execute→Understand→Learn→Self-Improve」作为飞轮对外表述；用摩擦信号（执行失败/用户纠正）触发 skill 改进 | 商用 SaaS teamai.com 无关；仅借开源 CLI 方法论，不引入其依赖 |
| **A3** | QoderWake | Harness-First + Executor/Verifier 分离 + Session 幂等恢复 + Anti-Rot 治理 | 流水线缺 Verifier；自动化崩溃不可恢复；技能会腐化 | 在 orchestrator 给每个 Agent 加显式 Verifier（如 eco Agent 校验 recipe 是否落到 execution_log）；自动化加 Session 幂等恢复（崩溃从 checkpoint 续跑）；skill_factory 生成后跑 Anti-Rot 自检（与 ponytail YAGNI 互补） | 阿里内部项目，公开实现细节有限，借架构不抄代码 |
| **A4** | SoL-Pi | Online Context Compact + Evidence-Preserving Reducer（默认 off） | 本地 Ollama（ornith-1.5:35b）上下文/成本受限 | 在 orchestrator 长对话接入在线压缩：保留证据（配方→执行→结果三元组）的压缩式摘要，削减 45–54% token；默认关闭、opt-in，与 AgriTrust 无强制一致 | 原假设 GPU，我们走 CPU/本地 Ollama，压缩逻辑与硬件无关可直接借 |
| **A5** | CocoLoop | CLS 安全分级 S/A/B/C/D + VM 隔离 + 技能分发生态 | 9 MCP 工具缺安全分级与上架渠道 | 给 agri skills 做 CLS 分级（S=可联网/A=本地只读/B=本地写/C=需审批/D=禁用）；走类 CocoLoop 平台分发（与 aishield 上架 Glama/npm 打法一致） | 平台为第三方，仅借分级标准与分发思路 |
| **A6** | ponytail | YAGNI agent 策略（写更少代码 ~54%） | 项目追求零依赖，但技能易过度工程 | 把 YAGNI 作为 skill_factory 生成技能时的硬约束：生成「最小可用技能」，不堆功能；与 A3 Anti-Rot 互补防腐化 | 零成本、纯纪律，直接落地 |
| **A7** | OpenMausBot | 多智能体团队范式 + Allow/Deny 权限卡 + 本地 MCP server + 定时/ webhook routine | 多 Agent 流水线同构为「团队」；缺执行审批与事件触发 | 把 climate/crop/growth/eco + 按需 Agent 显式建模为「团队」（各自身份/记忆/工具）；Env Recipe 设备端执行前弹 Allow/Deny 审批（对应 AgriTrust 设备安全）；每日闭环升级支持 webhook 触发 | TS/Electron 桌面栈，不迁移代码；仅借范式 |

### B 档（架构 / 方法论借鉴，排期中后段）

| 编号 | 来源项目 | 借鉴点 | 对应我们缺口 | 落地动作 | 风险 / 注意 |
|---|---|---|---|---|---|
| **B1** | OpenAI Agents API | subagent + context compaction + tool search + MCP | orchestrator 四 Agent 流水线已类似但缺 compaction/tool search | 借「子智能体 + 上下文压缩」模式增强 orchestrator；**不接入托管 API**（与 AgriTrust 本地优先冲突，会 lock-in） | 托管 API 锁定风险，仅参考架构 |
| **B2** | Karpathy/autoresearch | ratchet loop（只保留正向改进、锁死基线） | flywheel 每次回流需「只进不退」的改进纪律 | 把 ratchet 引入 skill_factory：每次配方→执行→结果回流，仅保留正向 diff，基线不可回退 | autoresearch 面向 ML 训练需 NVIDIA，我们无 GPU，只借方法论 |
| **B3** | HyperResearch | 来源溯源（source provenance）+ 研究 wiki | 全球数据底座需每个事实/配方带溯源（FAO/WorldClim/ISRIC） | 给数据底座与 Env Recipe 加溯源字段（来源 + 许可 + 抓取时间），呼应 AgriTrust 可审计 | 绑定 Claude（非本地），不迁移 |
| **B4** | bash+脚本 CLI「按需调用」 | 受控按需执行（allow/deny 白名单 + OverlayFS 写时复制 + guard agent 审批） | MCP `agri_*` 工具已是按需调用，缺沙箱/权限模型 | 给 Env Recipe 设备端执行加：命令白名单 + 写隔离（OverlayFS 式丢弃）+ guard agent 审批，强化 AgriTrust | 多实现（just-bash/AIGNE/agentic-bash），选模式不绑具体库 |
| **B5** | OpenMausBot（信任侧） | 本地优先、数据在本地 `~/.openmausbot`、密钥写仅 UI | AgriTrust 需更多「本地优先」实现佐证 | 把 OpenMausBot 的「本地存 + 密钥不可读」作为 AgriTrust 叙事对标案例 | 同 A7，仅借叙事 |

### C 档（反向借鉴 / 弱相关 / 不迁移）

| 编号 | 来源项目 | 判定 | 原因 |
|---|---|---|---|
| **C1** | Qwen-UI-Agent | 不迁移 | GUI 操作智能体（控制手机/桌面界面），与农业领域无关；其「模拟点击/坐标操控」范式与我们的 Env Recipe **结构化参数下发**冲突（我们走稳定下发而非模拟点击，见 HeyClicky C2） |
| **C2** | ElizaOS | 弱相关 | Web3/加密社交智能体框架，HTN 任务分解思路可参考，但 TS/Node + Web3 栈与本项目不符、领域无关 |
| **C3** | HeyClicky（互补性反向） | 见单文档 C1/C2 | 无 MCP（我们已有 9 工具，强化差异化）；模拟点击脆弱（我们走协议下发更稳） |

---

## 三 跨切口主题（本批项目的「行业共识」）

1. **自我改进闭环成为标配** — Theseus RSI（L1–L5）、TeamAI（三层）、QoderWake（5 维经验）、Karpathy ratchet 全部指向「智能体系统必须能自我改进」。→ 我们的 flywheel 应向 **RSI 五级 + TeamAI 三层**对齐，作为 v2.1 之后飞轮演进的主线。
2. **本地优先 + 执行安全** — OpenMausBot、AgriTrust、bash-CLI（OverlayFS/guard）、CocoLoop（VM 隔离）、SoL-Pi（opt-in）共同强调本地数据 + 受控执行。→ 强化 AgriTrust 叙事与设备端执行权限模型（A7 + B4）。
3. **技能分发 + 安全检查 + MCP 生态** — CocoLoop、TeamAI、OpenAI Agents API、OpenMausBot 都走 MCP/skills 生态。→ 我们的 9 MCP 工具 + aishield Glama 上架打法对齐，补 CLS 安全分级（A5）。
4. **上下文压缩 / 降本** — SoL-Pi、OpenAI Agents API compaction。→ orchestrator 接 Online Context Compact（A4），直接降本地推理成本。

---

## 四 优先级排序（落地建议）

| 优先级 | 项 | 理由 |
|---|---|---|
| P0（近期） | A1 RSI 框架、A2 TeamAI 自改进闭环、A6 ponytail YAGNI | 战略框架 + 零成本纪律，直接重塑飞轮表述与技能生成约束 |
| P1（中近） | A3 QoderWake Verifier+幂等、A4 SoL-Pi 压缩、A5 CocoLoop CLS 分级 | 强化流水线稳健性、降本、补技能安全分发 |
| P2（中后） | A7 OpenMausBot 团队范式+审批、B1/B2/B3/B4/B5 | 架构借鉴，按需排期，不阻塞主线 |
| 不排期 | C1/C2/C3 | 反向借鉴 / 不迁移，仅作差异化佐证 |

---

## 五 风险备注

- **多数项目是 coding/research/desktop 智能体（非农业）**：价值在架构 / UX / 分发模式，**不是代码合并**。技术栈冲突（TS/Node/Electron/Swift/macOS）与本项目 Python/Web 零依赖栈不兼容。
- **托管 API lock-in**：OpenAI Agents API 为托管服务，与 AgriTrust 本地优先冲突，**不接入**。
- **本地无 NVIDIA**：autoresearch / SoL-Pi 原假设 GPU；我们走 CPU/本地 Ollama，仅借与硬件无关的逻辑（ratchet 方法论、上下文压缩）。
- **HeyClicky 已闭源**：2026-04-27 后新功能转闭源 snapshot，仅借架构（见 `heyclicky_complementary.md`）。
- **一手事实局限**：openmausbot 许可源站表述不一（GitHub 标 MIT、镜站标 Apache-2.0）；TeamAI 有商业 SaaS 与开源 CLI 两款，本文仅取开源 CLI；bash-CLI 为通用模式，本文列 5 个代表性实现。三项均在本次补齐（前次搜索空白/敏感拦截已解决）。

---

## 六 与其他文档关系

- `docs/heyclicky_complementary.md`：HeyClicky 单项目借鉴（A1/A2/A3/B1–B4/C1–C2），本文 C3 与 A7 与之交叉引用。
- `docs/opensource_scan_complementary.md`：农业垂直开源基准（mcp-kasvanta、homeassistant-aerogarden、WOFOST、@pondlog、AgroEvals、PlantVillage 等），本文聚焦**通用 Agent 生态**，互补不重叠。
- 落地后须同步更新：`README.md`、`docs/project_evaluation.md`、`docs/intel_log.md`、`mcp/README.md`、`outputs/项目地图.md` 的能力计数（防静默漂移，见 working memory 报数基线）。

---

## 七 本轮实施落地状态（2026-09-15 完成）

本节记录用户授权「按你计划全部实施」后实际落地的代码，与上文 A/B/C 档逐项对应。**全部零第三方依赖（stdlib only）**，新增单测 59 项（`scripts/test_engine_v2.py`），与既有 42 项合计 **101/101 通过**。

| 档 | 项 | 落地代码 | 验证 |
|---|---|---|---|
| **A1** | Theseus RSI 五级 + HCI | 新增 `engine/rsi.py`（B0→L5 分级 + 五门禁 + HCI 度量）；`engine/eval.py` 接入 `eval_rsi_hci` 北极星 | 现有基线 → L1 执行级，HCI=0.167（诚实：execution_log 与 calibrated 数据尚未回流，L2+ 门禁未闭合） |
| **A2** | TeamAI Git-native harness + 三层自改进 | 新增 `scripts/harness_sync.py`（init/check/dry-run/push 四子命令）+ `harness/manifest.json`；**声明区 vs 观测区分离**防自指漂移 | `init`→`check` 无假漂移；`check` 篡改即报红；`push` 拒绝提交并指向 `gh_push.py` |
| **A3** | QoderWake Executor/Verifier + Session 幂等 | 改造 `agent/orchestrator.py`：新增 `Verifier` 类（结构化校验替代「有字段」弱断言）+ `Session` 缓存（同 session_id 幂等返回）+ Anti-Rot 治理信号 | 42/42 回归通过；捕获并修复一处真实 bug（Verifier 详情文本含 `PLACEHOLDER` 哨兵触发反占位守卫） |
| **A4** | SoL-Pi Online Context Compact | 新增 `engine/context_compact.py`：Evidence-Preserving Reducer + Action Fusion（相邻同类动作合并，数值求和，`__digests` 保留原始证据指针可反查） | 修复一处死代码（`__original is False` 永不成立）；空列表契约稳定 |
| **A5** | CocoLoop CLS 安全分级 | `engine/skill_factory.py` 新增 `cls_grade()`：机读规则判定 S/A/B/C/D（是否联网/读凭据/写文件/可逆），生成技能自带 `cls` 字段 | 修复「覆盖」中文词误报为「覆盖写入」的假阳性；生成技能自动写入 CLS |
| **A6** | ponytail YAGNI | `engine/skill_factory.py` 新增 `yagni_trim()`：删除未被调用路径引用的 inputs/outputs/dependencies，输出精简率指标 | 生成技能自带 `yagni` 元数据 |
| **A7** | OpenMausBot 安全按需执行 | 新增 `scripts/agri_cli.py`：白名单式命令（allow/deny + 默认拒绝 + `--dry-run` + `--write` 显式写盘），无 `subprocess`/`os.system`/`shell=True` | 单测覆盖白名单拦截与只读降级 |
| — | 门禁接入 | `scripts/verify_all.py` 新增「harness 声明区无漂移」检查；`skills/registry/schema.json` 新增 `cls`/`yagni` 可选字段 | `verify_all.py` 全绿 |

**基线现状（诚实报告）**：`rsi.report()` 当前 **B0 / HCI=0.0（0/6 门禁闭合）**。六个门禁全未闭合——`execution_log`（0 条执行记录）、`feedback_inflow`（0 条真实回流）、`calibration`（0 校准）、`generalization`（0/3 泛化）、`skill_generation`（1 个自动生成技能但 0 个被编排层引用）、`meta_improvement`（gate_version 未 bump）。**框架已就位，指标未谎报**——这正是 RSI 的价值：不靠代码完成度刷指标，而靠真实数据回流闭合门禁。L5 元改进门禁经两轮加固后拒绝「反复重测」自我满足（要求 `gate_version` 真 bump + HCI 曾真变化，历史 11 条快照中 HCI 曾变化但 gate_version 仍为初始值 1.0，故仍不闭合）。

**B 档未落地项**（架构借鉴，按需排期）：B1 OpenAI Agents API（不接托管）、B2 Karpathy ratchet、B3 HyperResearch 溯源、B4 bash-CLI 沙箱、B5 OpenMausBot 信任侧叙事。C 档不迁移。

**未做的事**（诚实标注）：
- 未改 `orchestrator.list_skills()` / MCP 工具数（仍为 9）——CLS/YAGNI/Verifier/Session 是**内部引擎能力**，非新增工具，故报数基线不变。
- 未推送 GitHub（`scripts/gh_push.py` 依赖用户 PAT，本机无 token）——本轮改动全部本地可复现，等用户授权后一次性提交。
- 未接 OpenAI 托管 API（与 AgriTrust 冲突，明确拒绝）。
