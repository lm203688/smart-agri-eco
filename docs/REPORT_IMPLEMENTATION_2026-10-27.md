# 项目全面提升报告 · 执行落地报告

**执行日期：2026-10-27**
**对标文档：`项目全面提升报告_2026-10-26.md`**
**约束口径：`docs/CORE_OBJECTIVE.md` §八（G1 前 P1 及以下不开工）+ §10.1（不可进化区）**

---

## 一、执行范围声明（诚实边界）

原报告覆盖 **P0（0-30 天）+ P1（31-90 天）+ P2（3-6 月）+ P3（6-12 月）** 全部工作包。按 CORE_OBJECTIVE 判据 + AI 能力边界，本次仅执行 **P0 中 AI 能自主完成的技术整改**：

| 判定维度 | 执行 | 不执行 |
|---|---|---|
| 时间窗口 | P0（0-30 天）内 | P1/P2/P3 全部延后 |
| 资源依赖 | 纯代码/文档/数据改动 | 需真实设备/用户/专家/法务/外部团队 |
| 判据 | CORE_OBJECTIVE §八 P0 优先 | §10.1 不可进化区不动 |

**结论**：原报告 12 个月路线图里，AI 一次会话能自主完成的比例约 **10-15%**——剩余需要外部资源或时间投入。本文档**不谎报覆盖**。

---

## 二、本次已执行的 4 项（P0 30 天内）

| # | 对应报告章节 | 交付物 | 状态 |
|---|---|---|---|
| **T1** | §四 P0-7（测试修复） | `agent/orchestration_audit.py` `finish()` 方法：`ended_at` 取 wall-clock 与最后 step 结束时间的较大值 | ✅ 完成 |
| **T2** | §四 P0-8（Demo 公网安全整改） | `app/demo_server.py`：CORS 白名单（`AGRI_ALLOWED_ORIGINS`）+ 路径规范化（`_safe_recipe_id`）+ 上传大小限制（1 MiB body / 5 MiB 单文件 / 20 MiB 总）+ 上传扩展名白名单 + CORS preflight | ✅ 完成 |
| **T3** | §四 P0-3（播种深度语义降级） | `scripts/apply_recipe_semantic_deprecation.py` + `data/.semantic_deprecation_audit.json`；152/152 配方已加 `estimated_unsafe_for_execution=true` + `safety_note` + `deprecation_marker_version=1.0` | ✅ 完成 |
| **T4** | §九 P0 工作包（批次对象 MVP） | `schemas/grow_batch.schema.json`：定义 Plot / GrowBatch / Observation / Action / Outcome 五类对象（JSON Schema draft 2020-12） | ✅ 完成 |

### 2.1 T1 详情：TraceRecord.finish() 修复

- **问题**：`outputs/test_current_2026-10-26.log` 报 `test_add_step_and_finish` 失败——`total_ms() == 0.0`
- **根因**：测试用 `time.time()` 生成 `t0`，与 `TraceRecord.started_at = CLOCK.time()` 几乎同时；add_step 之后立即 finish()，Windows wall-clock 精度可能 < 1 ms，`round((end-started)*1000, 3)` 被截断为 0
- **修法**：改 `finish()` 让 `ended_at = max(CLOCK.time(), steps[-1].ended_at)`——**数学语义**：finish 之后 total_ms 至少覆盖所有已完成 step 的时段
- **不改测试**：实现侧修复比测试侧加 sleep 更本质
- **§10.1 检查**：`agent/orchestration_audit.py` 不在不可进化区清单

### 2.2 T2 详情：Demo 安全整改

- **CORS 白名单**：默认仅允许本机回环（127.0.0.1 / localhost / [::1]）；生产必须显式 `AGRI_ALLOWED_ORIGINS`；离线调试可用 `AGRI_DEMO_CORS_WILDCARD=1` 恢复旧行为
- **CORS preflight**：新增 `do_OPTIONS` 处理；未匹配白名单返回 403
- **请求体限制**：`MAX_BODY_BYTES` 默认 1 MiB，超限返回 413
- **上传限制**：单文件 5 MiB / 总 20 MiB；扩展名白名单（PDF/DOCX/XLSX/CSV/TXT/MD/DOC/XLS/PNG/JPG/JPEG/WEBP/BMP）
- **路径规范化**：`_safe_recipe_id` 拒绝 `/` `\` `..` NUL 与非白名单字符；应用于 `_charts_vpd` 与 `_recipe_detail`
- **§10.1 检查**：`app/demo_server.py` 不在不可进化区清单
- **冒烟验证**：`scripts/check_demo_endpoints.py` **14/14 端点全绿**

### 2.3 T3 详情：152 配方语义降级

- **动作**：给 `data/env_recipes/*.json` 的 `sowing_depth_cm` 追加 4 个字段（不删不改原字段）：
  - `estimated_unsafe_for_execution: true`
  - `safety_note`：说明 `growth_days/200` 非农艺依据，需 E1 农艺专家审核才能进入控制层
  - `deprecation_marker_version: "1.0"`
  - `deprecation_marker_at`：ISO 时间戳
- **幂等**：脚本检测 `deprecation_marker_version == "1.0"` 即跳过；验证第二次跑 `skipped=152`
- **审计**：写入 `data/.semantic_deprecation_audit.json`（**不在 env_recipes/ 下**，避免被配方校验器误扫）
- **schema 兼容**：`sowing_depth_cm` 的 schema 允许 additionalProperties，152 份配方重新校验 **152/152 通过**

### 2.4 T4 详情：批次对象 Schema MVP

- **文件**：`schemas/grow_batch.schema.json`（JSON Schema draft 2020-12）
- **5 类对象**（顶层 `oneOf` 组合）：
  - `Plot`：位置（plot_id, location_type 必填）
  - `GrowBatch`：批次主对象（batch_id, crop, plot_id, recipe_version, started_at 必填）
  - `Observation`：观察记录（observation_id, batch_id, ts, metric, source 必填）
  - `Action`：动作执行（action_id, batch_id, ts, recommendation, status 必填；`status` enum 含 `shadow/pending_approval/approved/rejected/executed/executed_failed/rolled_back`）
  - `Outcome`：采收复盘（outcome_id, batch_id, ts 必填；其他字段全 optional，允许批次未结束）
- **证据等级**：`EvidenceGrade` enum `E0/E1/E2/E3/E4`（对齐 §8.2 定义）
- **默认安全**：`Action.dry_run` 默认 `true`；`status=shadow` 表示仅推演不执行

---

## 三、本次**未执行**的 P0 项（含原因分类）

| 报告项 | 原因 | 谁能完成 |
|---|---|---|
| **P0-1 独立评测重建** | 需独立农艺真值数据集（文献/专家标注），AI 无法自造 | 农艺专家 + 数据工程 |
| **P0-1 独立评测重建 · 分层落地** | ⚠️ **仅做框架**（本报告 §四）；真值数据缺失 | 同上 |
| **P0-2 保形区间语义纠正** | 需重命名 `P10/P50/P90` → `coverage_lower/upper`，但会破坏外部工具契约 | 需先与调用方沟通 |
| **P0-4 DLI 字段拆分** | 涉及 schema v1.2 → v1.3 版本 bump + 152 配方修改；§10.1 说 schema 在不可进化区（版本 bump 除外） | 需版本管理决策 |
| **P0-5 字段级血缘 `source_spans`** | 需真实来源映射（哪个来源支持哪个字段），AI 无法凭空造 | 数据治理 |
| **P0-5 许可冲突 CI 门禁** | 同上，需字段级来源数据 | 数据治理 |
| **P0-6 真实批次执行** | 需真实设备 + 真实用户 | 用户本人 + 设备合作方 |
| **P0-7 Windows UTF-8 编码 CI** | 需修改 CI workflow + 加跨环境测试 | 可下轮做 |
| **P0-7 ResourceWarning 清理** | 需系统扫全部 `open()` 缺 `with` 的地方 | 可下轮做 |
| **P0-8 鉴权** | Demo 是本地工具；公网部署需真实域名/反代 | 用户配置真实环境时 |
| **P0-8 速率限制** | 同上，公网部署前 | 用户配置真实环境时 |
| **P0-9 联邦/隐私威胁建模** | 需安全专家评审 | 安全工程师 |

**判定**：12 项未执行 P0 中，**7 项完全超出 AI 自主范围**（需外部资源），**5 项可下轮继续自主推进**（编码/CI/门禁，但受 CORE_OBJECTIVE §八 G1 判据约束——G1 外部调用为 0，理论上不该做 P1 及以下）。

---

## 四、P0-1 独立评测三层分类（本次仅做框架）

原报告 §四 P0-1 指出：`expand_bench_cases.py` 用 ForecastAgent 自身输出 ±30% 填 `expected`，89 用例本质是**自回归基准**，不是独立真值。

建议拆分为三层，**分开报告、禁止合并宣传**：

| 层级 | 数据源 | 允许用途 | 当前项目状态 |
|---|---|---|---|
| **L0 engineering_regression** | 被测模型固定快照（±30% 容差） | 验证"不变"，防回归 | ✅ 已有 89 用例 |
| **L1 agronomic_reference** | 独立文献 / 专家标注 / 机理模型（WOFOST/PCSE） | 证明接近真实农艺 | ⏸ **0 用例**（需外部数据） |
| **L2 field_holdout** | 按批次/站点/时间隔离 | 最终评估泛化能力 | ⏸ **0 用例**（需真实批次） |

**当前 89 用例**只能声明为"L0 工程回归通过"，**不得**进入"产量准确率"宣传。

落地建议：
1. 新建 `benchmarks/engineering_regression/` 目录（迁当前 89 用例）
2. 新建 `benchmarks/agronomic_reference/` 目录（先空，标注 TODO）
3. 新建 `benchmarks/field_holdout/` 目录（先空，等 P1 真实批次）
4. 报告层区分四层结果（原报告 §10.1 四层评测金字塔）

**本次未做迁移**——因为迁移会触及 `benchmarks/agri_recipe_bench/` 目录结构与 CI 门禁，超出本次会话范围。仅作**框架建议**，落地需下轮独立会话执行。

---

## 五、P1-P3 全部延后（明确说明）

| 阶段 | 时间 | 主要工作 | 延后原因 |
|---|---|---|---|
| **P1** | 31-90 天 | 一个真实批次 MVP（1 作物 × 1 设备 × 1 场景） | 需真实设备 + 真实用户 + 30-90 天数据积累 |
| **P1** | 31-90 天 | MCP Tasks/Apps 交付外部任务 | 需先有外部合作方 |
| **P2** | 3-6 月 | 3 站点 3 作物跨域验证 | 需站点资源 + 时间 |
| **P2** | 3-6 月 | 视觉 OOD/人工升级、混合模型基线 | 需图像数据集 |
| **P2** | 3-6 月 | A2A 生产端点 + 设备适配器 | 需 HTTPS 部署 + 硬件 |
| **P3** | 6-12 月 | 第三方独立复现（E4） | 需外部团队 |
| **P3** | 6-12 月 | 联邦/DP 生产化 | 需威胁建模 + 独立审计 |
| **P3** | 6-12 月 | Recipe v2 商业化 | 需法务 + 用户基础 |

**这些不是"AI 不努力"，是物理上需要外部资源和时间投入。**

---

## 六、证据等级 × 项目行为绑定（对齐 §8.2）

原报告 §8.2 定义 E0-E4 五档证据等级，并要求"证据等级必须控制产品行为"。本次在 `schemas/grow_batch.schema.json` 引入 `evidence_grade` 字段（enum E0-E4），后续可执行：

| 证据等级 | 允许用途 | 不允许用途 |
|---|---|---|
| E0 文献/规则推导 | 探索、解释、低风险参考 | 宣称精准、自动控制 |
| E1 专家审核 | 人工确认建议、试点 | 跨域自动泛化 |
| E2 单点实测 | 同站点同设备推荐、有限闭环 | 宣称普遍有效 |
| E3 多点复现 | 规模化推荐、条件自动控制 | 超出适用域执行 |
| E4 外部独立验证 | 生态认证、商业高可信声明 | 免于持续监控 |

**当前项目所有资产证据等级 = E0**（152 配方为规则推导、ForecastAgent 为启发式、Bench 89 用例为自回归）。

**红线**：任何字段 `evidence_grade < E1` 时，进入 `Action.executed`（真实执行）应被阻断。本次仅在 schema 层声明此约束，未做运行时强制（属 P1 工程实现）。

---

## 七、后续自主可做清单（AI 下轮可继续）

按 CORE_OBJECTIVE §八 P0 判据 + §10.1 不可进化区约束，**若 G1 外部调用仍为 0**，则不应开启 P1 工作。当前自主可做仅限于：

| 项 | 判据 |
|---|---|
| 补齐 T3 剩余的编码规范（ResourceWarning、Windows UTF-8） | §四 P0-7 补充 |
| Bench 三层目录迁移（engineering_regression / agronomic_reference / field_holdout） | §四 P0-1 框架落地 |
| 补 `schemas/grow_batch.schema.json` 的迷你校验器（复用 env_recipe 模式） | §九 P0 工作包 MVP 校验 |
| 完善 `check_external_reachability.py` / `check_g1_signals.py` 定期巡检记录 | §八 P0 观察层 |

---

## 八、必须用户/团队介入的清单（AI 无法替代）

| 项 | 需谁做 | 阻塞什么 |
|---|---|---|
| **G1 决策门** | 用户本人（P0-4b Glama/LobeHub 上架；P0-5 公网 Demo SSH） | 外部调用 ≥ 500 / 独立调用方 ≥ 20 |
| **P0-3 农艺专家审核** | 农艺专家（E1 签署） | 播种深度从 E0 升到 E1 |
| **P0-5 法务咨询** | 法务顾问 | NC 来源与顶层 CC BY 的商用边界 |
| **P0-6 真实批次** | 用户 + 设备合作方 | 首个 E2 候选 RecipeVersion |
| **P1-P3 全部** | 团队（产品/农艺/ML/设备/安全/数据治理） | 全部后续阶段 |

---

## 九、诚实声明

- **本次执行覆盖率**：报告 12 个月路线图 ~10-15%（4 项 P0 自主整改 / 全部工作包）
- **未执行不是漏做，是物理不可能**：需要外部资源/时间
- **不谎报证据等级**：所有资产仍为 E0，Bench 89 用例仍是自回归
- **不夸大安全整改**：CORS/上传/路径规范化只做基础防护，不构成"公网安全"认证；公网部署前仍需威胁建模
- **不宣称 schema 完美**：`grow_batch.schema.json` 是 MVP，字段可能不完整；`evidence_grade` 声明但未在运行时强制

**北极星不变**：项目从"功能丰富的农业 Agent 仓库"到"有真实证据的微场景决策产品"的跨越，靠**真实批次 + 农艺签署 + 外部采用**，不是更多代码。

---

*本文件是执行落地报告，与 `项目全面提升报告_2026-10-26.md`（诊断）配对。执行日志见 `.workbuddy/memory/2026-10-27.md`。*
