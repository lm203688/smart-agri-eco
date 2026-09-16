# AI Agent 生态第二批项目借鉴研发清单（2026-09-16）

> 配套文档：`docs/agent_ecosystem_complementary_2026-09-15.md`（第一批 14 项目，含实施落地状态）、`docs/heyclicky_complementary.md`（HeyClicky 单项目）、`docs/opensource_scan_complementary.md`（农业垂直开源基准）。
> 目标：对第二批「记忆/知识图谱/自进化/安全验证/多智能体组织」方向开源项目，判定其对「智慧农业生态」的借鉴价值，落到 A/B/C 档可研发清单。
> 方法：只借**架构 / 范式 / 工程模式**，**不合并代码**（多数项目 TS/TypeScript 栈，与本项目 Python 零依赖栈冲突；且多为 coding/research/security 智能体，非农业领域）。

---

## 〇 本批项目一手事实速查表

| # | 项目 | 性质 / 许可 | 定位 | 关键技术点 |
|---|------|------------|------|-----------|
| 1 | EverOS（EverMind-AI/EverOS） | 开源，~12.8k★ | 智能体长期记忆操作系统 | EverCore 长期记忆 OS；HyperMem 超图记忆；EverMemBench + EvoAgentBench 评测；需 Docker+API key |
| 2 | Hypit（hypit-ai/hypit） | 开源 MIT，~386–1.3k★ | AI 智能体视频制作语言+运行时 | 词级锚定（非时间轴秒）；一条命令 100 变体；TS monorepo；代码渲染零成本 |
| 3 | WeKnora（Tencent/WeKnora） | 开源 MIT，v0.1.3 | 企业级模块化 RAG 文档理解 | 「无文档只有实体+关系」知识图谱范式；多模态 OCR；Ollama 集成；Docker+Web UI |
| 4 | zvec-grep（zvec-ai/zvec-grep） | 开源 Apache-2.0，~1.3k★ | 本地优先工作区检索 | ripgrep+BM25+向量 三层统一 CLI；MCP Server；面向人与 Agent；Node.js 22+ |
| 5 | OpenOPC（HKUDS/OpenOPC） | 开源，~581★ | 「把 Agent 编排成一家公司」AI 原生公司框架 | Self-Built/Self-Run/Self-Grown；Work Item 状态机；5 模式（execute/delegate/review/integrate/rework）；DAG 编排；私有经验+共享 Playbook |
| 6 | Shannon（KeygraphHQ/shannon） | 开源 AGPL-3.0，~10.6–44k★ | 全自动 AI 渗透测试工具 | 多智能体四阶段（侦察→漏洞分析→利用→报告）；「打不通就不报」零误报策略；Docker 隔离；需 Anthropic key |
| 7 | ECC（affaan-m/everything-claude-code） | 开源，~234k★ | Agent Harness 性能优化系统 | 6 层组件树（Agents 48/Skills 182/Commands 68/Rules 89/Hooks/MCP）；Agent-First；TDD+Security-First；跨平台（Claude Code/Cursor/Codex/OpenCode） |
| 8 | AIMe/MS2KOSMOS（Cornell，bioRxiv 2608.05） | 论文+预发布工具 | 质谱神经符号多智能体 | 三智能体（DeepMS2Reasoner 预测+解释 / Generator 建库 8 亿谱图 / Mapper 映射）；1 亿+ 分子索引；**明确面向农业与生态** |
| 9 | PenguinHarness（Prism-Shadow/penguin-harness） | 开源 Apache-2.0，~1.1k★ | 自进化 Agent Harness | 仅 6 工具（shell 为通用接口）；Agent=可编辑文件（非代码）；OmniMessage 三位一体协议；benchmark→评估→找失分→编辑→**仅改进才接受**+快照回滚；LlamaFactory 作者出品 |

---

## 一 互补基线（我们的现状 vs 这批项目的共性能力）

| 我们的缺口 / 现状 | 这批项目提供的对应能力 | 结论 |
|---|---|---|
| 飞轮已有 RSI L1–L5 框架（A1 已落地），但**缺具体自进化闭环**（仅度量无改进循环） | PenguinHarness（benchmark→评估→编辑→仅改进才接受+快照回滚）、OpenOPC Self-Grown（执行轨迹→私有经验→共享 Playbook） | **A：补自进化闭环** |
| 数据底座为扁平 JSON（crop_adapt_db / zone_meta），**缺实体关系建模** | WeKnora（「无文档只有实体+关系」）、EverOS HyperMem（超图记忆） | **A：知识图谱重构底座** |
| 9 个 MCP 工具 + skill_factory 生成技能，**缺完整 harness 组件树**（无 Commands/Hooks/Rules 层） | ECC（6 层组件树）、PenguinHarness（Agent=可编辑文件） | **A：补组件树** |
| PestAgent 诊断**可能产生假阳性**（无证据也报） | Shannon（「打不通就不报」零误报） | **A：采纳零误报策略** |
| 数据底座为 JSON 文件，**Agent 无法自服务检索** | zvec-grep（本地优先三层检索+MCP）、WeKnora（模块化 RAG） | B：本地检索层 |
| 跨会话无记忆（每日 automation 定时而非记忆驱动） | EverOS（长期记忆 OS）、EverMemBench（记忆质量评测） | B：跨会话记忆 |
| Env Recipe 执行按固定时间排程，**缺环境条件自适应** | Hypit（词级锚定替代时间轴）、AIMe（预测+解释+映射 三阶段） | B：条件锚定执行 |
| 多 Agent 流水线同构为「团队」但**缺组织记忆** | OpenOPC（私有经验+共享 Playbook+组织记忆） | B：组织记忆 |

---

## 二 借鉴研发主表（A/B/C 档）

### A 档（直接采纳 / 最高优先，建议近期排期）

| 编号 | 来源项目 | 借鉴点 | 对应我们缺口 | 落地动作 | 风险 / 注意 |
|---|---|---|---|---|---|
| **A1** | PenguinHarness | 自进化闭环：benchmark→评估→找失分→编辑 Agent 文件→**仅分数严格提升才接受**+每轮快照回滚 | 飞轮 RSI 框架仅度量无改进循环；HCI 从 B0 起步 | 在 `engine/flywheel.py` 加自进化循环：①固定评测集（配方→执行→结果三元组）②每轮回流仅保留正向 diff（ratchet）③HCI 未升不合并 ④快照到 `data/snapshots/` 可回滚 | TypeScript/Node 栈，仅借范式；我们的 Python 零依赖栈可直接实现该循环 |
| **A2** | OpenOPC | 执行轨迹→私有经验→共享 Playbook 组织记忆 | 飞轮 L4「经验获取」门禁未闭合；skill_factory 生成技能但不蒸馏经验 | 在 orchestrator 执行轨迹上叠加经验蒸馏：每次 recipe→execution→outcome 回流后，将高频模式提炼为共享 Playbook（与 skill_factory 生成的技能互补） | HKU 学术项目，实现细节有限，借范式不抄代码 |
| **A3** | WeKnora | 「无文档只有实体+关系」知识图谱范式 | 数据底座为扁平 JSON，无法跨维度查询 | 将 crop_adpt_db / zone_meta / pest_db 重构为实体-关系图（实体：作物/分区/病虫害/土壤/气候；关系：生长于/易感/需要/抑制）；保留 JSON 兼容层，新增图索引 | 腾讯项目，Python 栈兼容；重构需迁移现有数据，建议增量（先建图索引层，不删 JSON） |
| **A4** | Shannon | 「打不通就不报」零误报策略 | PestAgent 诊断可能假阳性 | 在 PestAgent 诊断输出中加证据门控：仅当 ①图像匹配+环境条件同时满足 才输出诊断结论；无证据则标注「未确认」而非报告 | AGPL-3.0 与本项目许可不兼容，仅借策略不改代码；策略本身零成本 |
| **A5** | ECC | 完整 harness 组件树（Agents/Skills/Commands/Hooks/Rules/MCP 六层） | 仅 skill_factory 生成技能层，缺 Commands/Hooks/Rules | 在 `skills/registry/` 下扩展三类：Commands（一键触发流水线）、Hooks（事件驱动如温湿度越限自动诊断）、Rules（always-follow 约束如「禁止在无数据源时输出诊断」） | ECC 234k★ 疑为营销虚高；Claude Code 生态，借组件树概念不迁移代码 |

### B 档（架构 / 方法论借鉴，排期中后段）

| 编号 | 来源项目 | 借鉴点 | 对应我们缺口 | 落地动作 | 风险 / 注意 |
|---|---|---|---|---|---|
| **B1** | EverOS | 长期记忆 OS + HyperMem 超图记忆 | 跨会话无记忆（每日 automation 定时非记忆驱动） | 给 agent 加跨会话记忆层：配方执行结果存入长期记忆，后续会话可检索历史诊断 | 需 Docker+API key，与 AgriTrust 本地优先冲突；仅借架构模式 |
| **B2** | zvec-grep | 本地优先三层检索（ripgrep+BM25+向量）统一入口 | 数据底座为 JSON 文件，Agent 无法自服务检索 | 给数据底座加本地检索层：Agent 可自行检索作物/分区/病虫害数据，无需硬编码路径 | Node.js 22+ 依赖，仅借范式；Python 可用 sqlite FTS5+向量替代 |
| **B3** | AIMe | 预测+解释+映射 三阶段多智能体范式 | PestAgent 诊断缺「解释性」——仅给结论不给推理链 | PestAgent 输出增加推理链：预测（哪种病害）→解释（为什么：症状+环境条件）→映射（匹配到哪个已知模式） | 论文预发布工具，代码未开源；仅借范式 |
| **B4** | Hypit | 词级锚定替代时间轴秒 | Env Recipe 按固定时间排程，缺环境条件自适应 | Env Recipe 执行步骤锚定到环境条件（温/湿/光照阈值）而非固定时间，条件满足才触发下一步 | 视频制作领域，仅借锚定范式 |
| **B5** | OpenOPC（组织侧） | Work Item 状态机 + 5 模式（execute/delegate/review/integrate/rework） | 多 Agent 流水线缺显式状态机与角色分工 | 给 orchestrator 加显式状态机：每个 agent 输出有状态（execute→review→integrate），失败可 rework | 同 A2，借范式 |

### C 档（反向借鉴 / 弱相关 / 不迁移）

| 编号 | 来源项目 | 判定 | 原因 |
|---|---|---|---|
| **C1** | Shannon | 不迁移 | AGPL-3.0 与本项目许可不兼容；安全渗透测试领域无关；仅借「打不通就不报」策略（已列 A4） |
| **C2** | ECC | 弱相关 | Claude Code 编码智能体增强，非农业；234k★ 疑为营销虚高；仅借组件树概念（已列 A5） |
| **C3** | Hypit | 弱相关 | 视频制作领域，仅借词级锚定范式（已列 B4）；TS 栈不迁移 |
| **C4** | EverOS | 不迁移 | 需 Docker+API key，与 AgriTrust 本地优先冲突；仅借架构模式（已列 B1） |

---

## 三 跨切口主题（本批项目的「行业共识」）

1. **自进化从度量走向闭环** — PenguinHarness（严格改进才接受+快照回滚）、OpenOPC Self-Grown（轨迹→经验→Playbook）、PenguinHarness Skills 可被 Agent 改写。→ 我们的 RSI 框架已有度量，下一步是补**具体改进循环**（A1）。
2. **知识图谱化** — WeKnora（无文档只有实体+关系）、EverOS HyperMem（超图）、AIMe MS2KOSMOS（8 亿谱图结构化）。→ 数据底座从扁平 JSON 走向实体关系图（A3）。
3. **本地优先检索** — zvec-grep（本地三层统一）、PenguinHarness（Agent=可编辑文件，shell 为通用接口）。→ 数据底座加本地检索层（B2）。
4. **零误报 / 证据门控** — Shannon（打不通就不报）、PenguinHarness（仅改进才接受）。→ PestAgent 加证据门控（A4）。
5. **Agent 即数据** — PenguinHarness（Agent=可编辑文件而非代码）、ECC（Agent-First 委派）、OpenOPC（Agent=公司员工）。→ skill_factory 已生成技能文件，下一步让 Agent 可编辑自己的技能（A1+A2）。

---

## 四 优先级排序（落地建议）

| 优先级 | 项 | 理由 |
|---|---|---|
| P0（近期） | A1 自进化闭环、A4 零误报、A3 知识图谱 | 自进化闭环让 RSI 从度量走向改进；零误报强化 AgriTrust 可信度；知识图谱是数据底座的关键升级 |
| P1（中近） | A2 组织记忆、A5 组件树 | 经验蒸馏与组件树完善技能体系 |
| P2（中后） | B1–B5 | 架构借鉴，按需排期 |
| 不排期 | C1–C4 | 反向借鉴 / 不迁移 |

---

## 五 风险备注

- **多数项目是 coding/research/security 智能体（非农业）**：价值在架构/范式/工程模式，**不是代码合并**。
- **技术栈冲突**：TS/TypeScript/Node.js 与本项目 Python 零依赖栈不兼容；仅借范式。
- **许可兼容**：Shannon AGPL-3.0 不兼容，仅借策略；ECC 许可需确认。
- **ECC 234k★ 疑为营销虚高**：DeepWiki 显示实际组件为 48 agents/182 skills，与「20 万星」不成比例。
- **EverOS 需 Docker+API key**：与 AgriTrust 本地优先冲突，仅借架构模式。
- **AIMe 论文预发布**：代码未开源，仅借范式。
- **WeKnora v0.1.3**：早期版本，实现细节有限。

---

## 六 与其他文档关系

- `docs/agent_ecosystem_complementary_2026-09-15.md`：第一批 14 项目评估+实施落地状态（A1–A7 已实现，101/101 单测通过）。本文第二批 9 项目，**A1 自进化闭环是第一批 A1（RSI 五级框架）的下一步**。
- `docs/heyclicky_complementary.md`：HeyClicky 单项目借鉴。
- `docs/opensource_scan_complementary.md`：农业垂直开源基准。
- 落地后须同步更新：`README.md`、`docs/project_evaluation.md`、`docs/intel_log.md`、`mcp/README.md`、`outputs/项目地图.md` 的能力计数。

---

## 七 实施状态（2026-09-16 已落地，A 档 + B 档全量）

| 项 | 代码 | 落地要点 | 可验证信号 |
|---|---|---|---|
| **A1 自进化闭环** | `engine/evolution.py`（新增） | benchmark 从真实作物库派生（`seed_benchmark`，good/bad 反馈×方向期望，评分方向正确=1/无变化=0.5/反向=0）；棘轮门禁 `ratchet`（Δ>0 才接受，持平即回滚）；`snapshot`/`restore` 快照回滚，支持绝对路径别名存放，保留最近 10 份 | `python -m engine.evolution` 打印基线分数与快照数 |
| **A2 组织记忆** | `engine/org_memory.py`（新增） | 轨迹 append-only → `classify_issue` 六类归类 → `distill_playbook` 按 `(skill, issue_category)` 支持度≥N 蒸馏为共享 Playbook（含 support/outcome_breakdown/countermeasures/confidence）；`recall` 供诊断前预取 | `python -m engine.org_memory` 打印轨迹与 Playbook 统计 |
| **A3 知识图谱层** | `engine/knowledge_graph.py`（新增） | 派生索引（**不删任何源 JSON**）：实体 Zone/Crop/PestDisease，边 grows_in(带权重)/sensitive_to/koppen_of/constrains；`neighbors`/`traverse` 支持 `reverse=True` 沿入边反查 | 198 实体 / 320 边；「叶斑病→受影响作物→分区暴露度」反向查询可用 |
| **A4 零误报证据门控** | `agent/pest_agent.py` | `_evidence_gate`：`symptom_hit`（top_score≥0.45 且命中 KB 条目）∧（`visual_confirm` ∨ `environment_observed`≥2 项有效值）才 `confirmed`；否则诊断加「（未确认）」前缀、只报监测项。NaN/bool 不算有效观测 | 输出含 `confirmation_status` + `evidence_gate`（三要素+missing+policy） |
| **A5 六层组件树** | `engine/harness_tree.py`（新增） | 补齐 Commands（4）/Hooks（3，触发条件须 field/op/value 三元组可机读）/Rules（5，**3 条 blocker**：`no_unconfirmed_diagnosis`、`no_placeholder_output`、`safe_rollback_on_regression`；2 条 major）；`lint` 校验重复 id/不可机读触发/非法 severity/空 applies_to/hook 悬空引用；`--export` 导出 `skills/harness/*.json` | `python -m engine.harness_tree --lint` → `ok=True, issues=0` |
| **harness 清单同步** | `scripts/harness_sync.py` | `MANIFEST_VERSION` 2.0.0→**2.1.0**；`harness_tree` 入**声明区**（计数+id+lint 结果，完整定义只在导出 JSON，避免双份维护必然漂移）；`knowledge_graph`/`org_memory` 入**观测区**（信息快照，不参与门禁） | `harness_sync.py check` → 声明区无漂移 |
| **单测** | `scripts/test_engine_v3.py`（新增，42 项） | 覆盖 A1–A5 + manifest 集成；全部写盘操作重定向临时目录 | 三套合计 **143/143 通过**（v3 42 + v2 59 + agents 42），`verify_all.py` PASS |
| **B1 跨会话长期记忆** | `engine/long_term_memory.py`（新增） | 本地 JSON append-only（**零 Docker / 零 API key**，这是与 EverOS 的关键区别：只借架构不引运行时）。6 层加权打分：主体精确 3.0 / skill 1.5 / tag 1.0 / 查询词 0.5 / 时间近因（半衰期 30 天）0.6 / 哈希向量余弦 0.8，超边扩展 0.4。相似度用「字符 2-gram 哈希→256 维向量→余弦」零依赖实现。HyperMem 借鉴：`link()` 建超边（可挂任意条记忆），`recall(expand=True)` 做一次二阶扩展把同超边兄弟带回 | `python -m engine.long_term_memory`；流水线跑两次后第二次能召回到第一次的结论 |
| **B2 本地三层检索** | `engine/local_search.py`（新增） | sqlite3 **FTS5**（stdlib）+ 二元分词关键词层 + 零依赖哈希向量层，混合排序 `1.0·exact + 0.5·keyword + 0.4·vector`。索引是**派生缓存**（`data/search_index/`，可随时 `rebuild()`，不删任何源 JSON）。语料 4 类：crops 110 / zones 6 / pests 23 / recipes 110 = **249 条**。FTS5 不可用时降级为全量扫描 | `python -m engine.local_search`；`agri_cli.py search "蚜虫 症状" --corpus pests` |
| **B3 三阶段解释链** | `agent/pest_agent.py` | 输出新增 `reasoning_chain` = `{prediction, explanation, mapping, narrative}`。prediction（首选/类别/分数/备选/严重度）→ explanation（**症状词逐条命中明细** name_hit/name_fragment/symptom_keywords/signal_score + 环境观测阈值 + 视觉补充）→ mapping（映射到 KB 条目还是类别通用模板 + 候选集 + 门控状态）。**全部派生自 diagnose() 已算出的真实结果，不引入新判定口径**——门控仍是唯一裁决者 | 白粉病例 narrative：「因为 症状文本直接点名「白粉病」；命中知识库症状词：白粉、粉状；…所以 证据充分，按零误报策略下确定结论」 |
| **B4 条件锚定执行器** | `engine/recipe_scheduler.py`（新增） | 把 Env Recipe 的**参数集**翻译成可判定的条件锚点：阈值锚点（来自 `environment`：温度昼夜/湿度上下限/pH/日灌溉量）+ 异常锚点（来自 `exception_handling` 文本抽关键词）。`next_actions(recipe, observations)` 返回 `ready`（该执行）/`waiting`（未满足，附 current/target/gap/reason）；`compare_modes()` 给出**时间锚定 vs 条件锚定**三类差异（time_only 白做 / condition_only 漏做 / both）。NaN/bool 一律视为「未满足」，与 A4 证据门控同一约定 | 110 份配方共 **957 个锚点**（阈值 770 / 关键词 187）；`agri_cli.py schedule --crop 番茄 --observations '{"humidity_pct":92,"temp_c":34}'` |
| **B5 工作项状态机** | `engine/work_item.py`（新增） | 显式状态机 `created→executing→pending_review→integrating→done`，分支 `rework`/`blocked`；5 模式 execute/delegate/review/integrate/rework，**转移表是声明式常量，非法转移直接拒绝且不改动状态**；审计日志 append-only，每条含 from/mode/to/actor/payload_key（**只存 16 位摘要，不存全量产物**，避免日志膨胀与泄漏）；`done` 是正常终态，仅 `rework` 可回炉。已接入 `orchestrator.run_pipeline()`：复核通过走 review→integrate→done，不通过走 rework | `python -m engine.work_item`；`agri_cli.py state-machine` 打印转移表与注册表 |
| **CLI 扩展** | `scripts/agri_cli.py` | 新增 4 个只读命令：`search` / `schedule` / `recall` / `state-machine`；`verify` 从两套单测扩到四套。白名单与只读默认守卫不变 | `agri_cli.py verify` → 四套 241 例 0 失败 |
| **单测（B 档）** | `scripts/test_engine_v4.py`（新增，**98 项**） | 覆盖 B1–B5 + 编排器集成 + manifest 新观测区；所有写盘重定向临时目录，路径经 `AGRI_LONG_TERM_MEMORY` / `AGRI_SEARCH_INDEX` 隔离，tearDown 恢复原值 | 四套合计 **241/241 通过**（v4 98 + v3 42 + v2 59 + agents 42，1 skip 为条件跳过的失败路径用例） |

### 落地过程中修掉的真实缺陷（非风格问题）

1. **`risky_zones` 前缀不一致**：`find_crops_for_risk` 返回已剥前缀的作物名，直接当节点名匹配边 → 分区暴露度永远返回空 `{}`。改为还原 `Crop:` 前缀。
2. **benchmark 用例互相污染**：同一作物 good/bad 两例共享一份隔离副本，前一条反馈改写 `adapt_score` 后，后一条的 `before` 变成被污染值，导致 bad 用例**永远判错**（Δ 恒为 0，棘轮无法验证）。改为逐例独立复制副本，评测集才真正可复算。
3. **快照在隔离评测下是空操作**：`snapshot` 只按相对 `ROOT` 路径备份 `PROTECTED_FILES`，测试用绝对路径的临时 crop_db 不被保护，棘轮回滚实际未生效。改为绝对路径以哈希别名存放 + `file_map` 精确还原。
4. **`tree()` 返回模块级常量的共享引用**：任何消费者都能意外改写 `HOOKS`/`RULES` 定义（实测 lint 被前一用例的断言污染）。改为 `deepcopy`，并让 `lint`/`export` 统一从传入的 tree 取数。

#### B 档落地过程中修掉的真实缺陷

5. **中文检索关键词层恒为 0 分**（最隐蔽）：FTS5 默认 `unicode61` 分词器把整段中文当作**一个 token**，查「生菜」查不到；而查询侧又被拆成单字、文档侧存的是 2-gram，两边切法不一致导致交集**恒为空**。改为：查询侧与文档侧统一走「连续 CJK 按 2-gram 切、ASCII 词整体保留」，且 FTS5 的 `body` 列必须同时存分词结果与原文（只存原文时 MATCH 中文二元组永远命中 0）。
6. **超边扩展被尾部切片截断**：`recall()` 末尾 `[:k]` 在超边扩展**之后**执行，兄弟记忆刚被补进来就被切掉，`expand=True` 形同虚设。改为先取主命中 k 条、扩展命中作为「附加项」不参与截断。
7. **`evaluate()` 早返回路径缺 `target` 键**：缺观测/非法值/未知比较符三条早返回分支不带 `target`，而 `next_actions()` 用 `ev["target"]` 取值 → CLI 一跑就 `KeyError`。改为 `.get()` 容错。
8. **`verify=False` 少一步 integrate**：跳过复核的路径只做了 1 次 `integrate`（`pending_review→integrating`），工作项停在 `integrating` 而非 `done`，流水线「看起来成功」但状态机未收敛。
9. **vector 模式仍报关键词分**：`search(mode="vector")` 的 `keyword` 字段照算照报（实测报 1.0），误导使用者以为关键词层参与了排序。改为三层各自只在 `hybrid` 或本层模式下计入。
10. **`agri_cli.py verify` 子命令从未注册**（既有 bug，非本轮引入）：`COMMANDS` 里有 `verify` 但 `build_parser()` 的循环漏了它，CLI 实际打不出这个命令。补进循环。
11. **测试/验证脚本写穿到真实记忆库**（本轮最严重）：B1 把记忆写入接进 `run_pipeline` 后，早于该能力写成的三个脚本没做写盘隔离——`test_agents` 每次 6 条、`test_engine_v2` 每次 7 条、`verify_all.py` 每次 6 条，一次全量验证就往 `data/long_term_memory.json` 写 **13 条合成记录**，差点被当成真实记忆提交。修复三件套：① 三处均把 `AGRI_LONG_TERM_MEMORY`/`AGRI_SEARCH_INDEX` 重定向到临时目录；② 新增 `AGRI_MEMORY_SYNTHETIC` 机制，测试进程写入的记录自动带 `[unittest]` 标记（留痕而非静默）；③ CI 新增长期记忆完整性门禁按标记拦下（对齐既有 `feedback_log` 门禁）。**教训：给既有函数加副作用，会让所有旧调用点同时变成污染源**——新增写盘能力必须清点全部调用点，只给新写的测试加隔离是不够的。

### 未实施项（按原计划）

- **C1–C4**（Shannon 代码、ECC 代码、Hypit、EverOS）：许可不兼容 / 弱相关 / 需 Docker，不迁移。
- **MCP 工具数仍为 9**：A1–A7 + B1–B5 全部是引擎内部能力，未新增 `agri_*` 工具（避免为计数而加空壳工具）。能力通过 `engine/*` 模块与 `agri_cli.py` 只读命令暴露。
- **CI 之前只跑 1 套单测**：`.github/workflows/ci.yml` 只跑 `test_agents`（42 项），v2/v3/v4（199 项）从未进 CI。已补齐为四套全跑 + 新增长期记忆完整性门禁。
- **RSI 仍为 B0 / HCI=0.0**：6 个门禁全部未闭合（无真实 execution_log / feedback / calibration）。A1/B1 提供的是**机制**（改进循环、跨会话记忆），不产出真实业务数据——指标不谎报。`data/long_term_memory.json` 现保留 0 条的空壳，联调产生的 26 条测试记录已清空。
