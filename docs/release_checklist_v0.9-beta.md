# v0.9-beta 发行就绪清单

**当前建议版本**：v0.9-beta（邀请制）
**建议日期**：不早于 RSI HCI ≥ 0.6 时
**当前 RSI HCI**：0.333（**不建议发 v1.0**，理由见 `docs/release_readiness_2026-09-29.md`）

---

## 一、当前状态快照（2026-10-02）

| 指标 | 数值 | 门禁 |
|---|---|---|
| 单测总数 | 497 tests / 3 skip / 0 fail | ✅ |
| verify_all | PASS | ✅ |
| harness manifest | v2.2.0 | ✅ |
| MCP 工具数 | 14 | ✅ |
| Env Recipe | 116（8 分区） | ✅ |
| bp_screen 规则库 | v2.2.0 / 12 gates | ✅ |
| 校准作物数 | 107 或 110（视 DB 版本） | ✅ |
| 远端 HEAD | `c9ed33d17bcd` | ✅ |

---

## 二、阻塞项（4 项，需用户拍板）

| ID | 项目 | 阻塞原因 | 建议 |
|---|---|---|---|
| **A** | 发 v0.9-beta tag | RSI HCI=0.333，非工程可关 | 建议延后到 RSI ≥ 0.6 时发正式版；beta 版可先内测 |
| **B** | PAT 轮换 | `ghp_rrBYNTGP...` 已多次明文暴露 | **强烈建议**在 https://github.com/settings/tokens 生成新 fine-grained PAT（Contents: read/write only） |
| **C** | 视觉后端选型 | 工程层已就绪（`agent/vision.py`），缺模型决策 | 3 选项：(1) OpenAI gpt-4o-mini（$0.02/1K） (2) ATEX 网关 (150.158.119.19:8420) (3) 本地 Ollama + vision-capable model |
| **D** | WorldClim 2.1 栅格管道 | 需 GeoTIFF/NetCDF 解析依赖（与零依赖 stdlib 策略冲突） | 独立轮次；如需接入建议引入 `numpy` + `rasterio` 或走第三方 WCS 服务 |

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

1. **完成阻塞项**：PAT 轮换 → 视觉后端选型 → WorldClim 决策（可延后）
2. **RSI 提升**：至少完成 skill_generation 架构调整 + 引入内测用户（feedback_inflow）
3. **补 4 pending evals**：至少完成 2 项（建议 E3 recipe_expert_adoption + E1 extraction_accuracy）
4. **准备 release tag**：
   - 更新 `CHANGELOG.md` 到 v0.9-beta 段落
   - 生成 `docs/release_notes_v0.9-beta.md`
   - 打 tag：`git tag -a v0.9-beta -m "..." && git push --tags`
5. **发布 MCP 工具清单**：通过 Glama / Official MCP Registry 上架 `smart-agri-eco`

---

## 六、发行后 2 周里程碑

- 邀请 3-5 家农业投资机构内测（bp_screen + Env Recipe）
- 邀请 2-3 家种植合作社试用（Env Recipe + pest_agent 视觉诊断）
- 收集 feedback_log 真实数据 → 推动 RSI HCI 从 0.333 向 0.6 迈进
- 每周 Jev 决策层异常归因报告（自动化已在跑）

---

**文档最后更新**：2026-10-02
**维护者**：Lexing（工作邮箱 QQ 1786240725175）
**相关文档**：`CHANGELOG.md` / `docs/release_readiness_2026-09-29.md` / `docs/block_improvement_roadmap_2026-09-30.md` / `docs/pricing_strategy_2026-09-30.md`
