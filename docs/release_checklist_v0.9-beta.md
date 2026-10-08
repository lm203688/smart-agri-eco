# v0.9-beta 发行就绪清单

**当前版本**：v0.9-beta（邀请制）— 2026-10-06 已拍板发行
**RSI HCI 现状**：0.333（v1.0 门禁 ≥ 0.6，未达，故先发 beta 邀请制；理由见 `docs/release_readiness_2026-09-29.md`）
**beta 可发条件**：工程指标全绿 + 分区闭环 + 离线视觉降级已就绪（本清单第一节）

---

## 一、当前状态快照（2026-10-06，已复核）

| 指标 | 数值 | 门禁 |
|---|---|---|
| 单测总数 | 505 tests / 3 skip / 0 fail | ✅ |
| verify_all | PASS（8 阶段全过） | ✅ |
| data_quality_gate | 全部通过（6 文件） | ✅ |
| validate_env_recipe | 116/116 通过 | ✅ |
| harness manifest | v2.2.0（数据基线 8 区 / 116 作物 / 113 校准） | ✅ |
| MCP 工具数 | 14 | ✅ |
| Env Recipe | 116（8 分区，含 hot_arid/highland） | ✅ |
| bp_screen 规则库 | v2.2.0 / 12 gates | ✅ |
| 校准作物数 | 113（8 分区全校准） | ✅ |
| KG grows_in | 116（8 分区全有作物邻接） | ✅ |

---

## 二、决策项（4 项，2026-10-06 已拍板）

| ID | 项目 | 决策 | 状态 |
|---|---|---|---|
| **A** | 发 v0.9-beta tag | 发 v0.9-beta（邀请制），配套更新 `CHANGELOG.md` / `docs/release_notes_v0.9-beta.md`；实际 tag+push 待 PAT 到位 | 🟡 物料就绪，待 PAT |
| **B** | PAT 轮换 | 用户提供新 fine-grained PAT（带 Workflows:write），到位后由 AI 接手推送闭环 + 打 tag | 🟡 待用户提供 |
| **C** | 视觉后端选型 | **离线规则降级**（无外部依赖）：`AGRI_VISION_*` 未配置自动 `rule_based`，云端 VLM 为可选插拔 | ✅ 已闭环（含回归守卫） |
| **D** | WorldClim 2.1 栅格管道 | **暂不做**，维持现有 5 程序化源（NASA POWER/Open-Meteo/WorldClim/GBIF/SoilGrids），避免与零依赖约束冲突 | ✅ 已决议延后 |

---

## 三、4 Pending Evals（需外部条件）

详见 `docs/pending_evals_plan.md`。

| ID | 名称 | 依赖 | 何时可关 |
|---|---|---|---|
| E1 | extraction_accuracy | 人工标注 BP 抽取样本 ≥ 50 | 邀请 3 位 BP 分析师标注一批样本后 |
| E2 | pest_diagnosis_topk | 真实病虫害图像 ≥ 200 | 接入视觉数据集后（PlantDoc / PlantVillage） |
| E3 | recipe_expert_adoption | 3+ 位种植专家盲评 | 邀请制内测阶段 |
| E4 | source_traceability | 溯源埋点数据积累 | 至少跑 2 周真实调用后 |

---

## 四、RSI HCI 门禁（当前 0.333，门禁 ≥ 0.6）

| 维度 | 当前 | 目标 | 差距 |
|---|---|---|---|
| execution_log | 0 | 1 | 需硬件接入 |
| feedback_inflow | 0 | 1 | 需真实用户回流 |
| meta_improvement | 0 | 1 | 需真实迭代记录 |
| skill_generation | 0 | 1 | 架构决策（`CropAgent` 无 `run()`，与 `recommend()` 契约不兼容） |

**4 项中 3 项非工程可关**（需真实数据/迭代）；`skill_generation` 需先重构 `CropAgent` 接口。

---

## 五、发行步骤（建议顺序）

1. **完成决策项**：PAT 轮换（用户提供）→ 视觉后端选型（离线降级，已定）→ WorldClim 决策（已延后）
2. **RSI 提升**：至少完成 skill_generation 架构调整 + 引入内测用户（feedback_inflow）
3. **补 4 pending evals**：至少完成 2 项（建议 E3 recipe_expert_adoption + E1 extraction_accuracy）
4. **准备 release tag（物料已完成）**：
   - ✅ `CHANGELOG.md` 已更新至 v0.9-beta 段落（2026-10-06）
   - ✅ `docs/release_notes_v0.9-beta.md` 已生成
   - 🟡 打 tag + push：待 PAT 到位后 `git tag -a v0.9-beta -m "..." && git push --tags`（经 `scripts/gh_push.py`）
5. **发布 MCP 工具清单**：通过 Glama / Official MCP Registry 上架 `smart-agri-eco`

---

## 六、发行后 2 周里程碑

- 邀请 3-5 家农业投资机构内测（bp_screen + Env Recipe）
- 邀请 2-3 家种植合作社试用（Env Recipe + pest_agent 视觉诊断）
- 收集 feedback_log 真实数据 → 推动 RSI HCI 从 0.333 向 0.6 迈进
- 每周 Jev 决策层异常归因报告（自动化已在跑）

---

**文档最后更新**：2026-10-06
**维护者**：Lexing（工作邮箱 QQ 1786240725175）
**相关文档**：`CHANGELOG.md` / `docs/release_readiness_2026-09-29.md` / `docs/block_improvement_roadmap_2026-09-30.md` / `docs/pricing_strategy_2026-09-30.md` / `docs/release_notes_v0.9-beta.md`
