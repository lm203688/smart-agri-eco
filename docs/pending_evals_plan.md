# 4 Pending Evals · 验收标准与实施计划

`engine/eval.py` 中 4 项 pending evals 全部**需外部条件**（人工标注 / 专家盲评 / 视觉数据集 / 溯源埋点），非工程可关。本文档明确每项的量化验收标准，供内测阶段按图索骥。

---

## E1 · extraction_accuracy（BP 抽取准确率）

**位置**：`engine/eval.py::eval_extraction_accuracy()`
**当前状态**：0%（未标注任何样本）

### 验收标准
| 指标 | 门槛 | 说明 |
|---|---|---|
| 已标注样本数 | ≥ 50 | 覆盖 15 case 类型的样本 |
| 字段级准确率 | ≥ 85% | `bp_screen/extractor.py::FIELD_PATTERNS` 匹配正确 |
| BOOL 字段召回 | ≥ 90% | 9 个 bool 字段（pesticide_registration 等）应能被正确抽取 |
| 数值字段 MAE | ≤ 20% | farmer_roi / cash_to_revenue / gross_margin 等 |

### 实施路径
1. 从 `data/bp_screen_cases.db` 导出 100 份匿名化 case（脱敏创始人/公司名）
2. 邀请 3 位 BP 分析师（可内部或合作机构）用 Excel 标注
3. 跑 `python -m engine.eval`，读取准确率
4. 未达门槛则迭代 `FIELD_PATTERNS` 正则

---

## E2 · pest_diagnosis_topk（病虫害视觉诊断 TopK）

**位置**：`engine/eval.py::eval_pest_diagnosis_topk()`
**当前状态**：0%（未接入视觉数据集）

### 验收标准
| 指标 | 门槛 | 说明 |
|---|---|---|
| 测试图像数 | ≥ 200 | 覆盖 5+ 常见病害（番茄晚疫病 / 葡萄霜霉病 / 玉米锈病 / 苹果锈病 / 水稻稻瘟病） |
| Top-3 准确率 | ≥ 75% | 诊断结果落在前 3 候选内 |
| 严重度混淆矩阵 | 混淆率 ≤ 20% | 轻/中/重 三档 |
| 视觉后端可用性 | 100% | `AGRI_VISION_URL/KEY/MODEL` 配置后可稳定返回 |

### 实施路径
1. 数据源选择：**PlantDoc**（CC-BY-NC-SA 4.0，175k 图像，8.4k 类别）或 **PlantVillage**（MIT）——**PlantDoc 已在项目 memory 中登记为推荐替代**
2. 抽样 200 张（每种病害 40 张）本地固化到 `data/eval/pest_images/`
3. 标注 ground truth（`data/eval/pest_ground_truth.csv`）
4. 跑 `scripts/eval_vision.py`（待新增，本轮不落地——需先完成视觉后端选型 C）
5. 未达门槛则调 prompt 或换模型

---

## E3 · recipe_expert_adoption（配方专家采纳率）

**位置**：`engine/eval.py::eval_recipe_expert_adoption()`
**当前状态**：0%（未邀请专家）

### 验收标准
| 指标 | 门槛 | 说明 |
|---|---|---|
| 参与专家数 | ≥ 3 | 覆盖种植 / 植保 / 水肥 3 类角色 |
| 采样配方数 | ≥ 30 | 从 116 份 Env Recipe 分层抽样（每分区 ≥ 2 份） |
| 完全采纳率 | ≥ 60% | 无需修改直接采纳 |
| 修改后采纳率 | ≥ 85% | 修改后愿意采纳 |
| 拒绝原因分布 | 记录完整 | 至少分类到 5 类（数据源 / 参数 / 边界 / 场景 / 其他） |

### 实施路径
1. 邀请渠道：合作高校（中国农大 / 南京农大）、地方农技站、合作社种植大户
2. 发放问卷：`data/eval/recipe_survey_template.md`（待新增）
3. 收集后按 `formula_id → expert_id → decision → comment` 存 `data/eval/recipe_adoption.csv`
4. 汇总输出到 `engine/eval.py::eval_recipe_expert_adoption()`

---

## E4 · source_traceability（数据溯源完整度）

**位置**：`engine/eval.py::eval_source_traceability()`
**当前状态**：0%（溯源埋点数据量不足）

### 验收标准
| 指标 | 门槛 | 说明 |
|---|---|---|
| MCP 调用带溯源的比例 | ≥ 90% | `agri_get_recipe` / `agri_bp_screen` 等 API 每次调用附 `query_lineage` |
| 溯源字段完整率 | 100% | `source` / `url` / `license` / `accessed_at` / `provenance_complete` |
| 30 天内溯源样本 | ≥ 100 | 至少跑 2 周真实调用积累 |
| 溯源可复现率 | ≥ 95% | 用溯源记录反查数据源，值一致 |

### 实施路径
1. **当前已在跑**：`AGRI_MCP_AUDIT_LOG=data/mcp_audit.log` 已启用 MCP 调用日志
2. `data_lineage.query_lineage()` 已实现溯源查询（Round 2 已交付）
3. 内测阶段真实流量积累 2 周后自动满足门槛
4. `eval_source_traceability()` 读 audit log + lineage store 计算比例

---

## 汇总：4 pending evals 关闭路线图

| Eval | 依赖项 | 预计完成时间 | 阻塞方 |
|---|---|---|---|
| E1 extraction_accuracy | 人工标注 | 内测阶段第 2 周 | 邀请 BP 分析师 |
| E2 pest_diagnosis_topk | 视觉后端选型 C + 数据集 | 内测阶段第 4 周 | 视觉后端决策 |
| E3 recipe_expert_adoption | 专家邀请 | 内测阶段第 2 周 | 合作机构 |
| E4 source_traceability | 真实调用 2 周 | 内测阶段第 3 周 | 内测启动 |

**结论**：4 项 evals 全部在内测阶段可关闭，不阻塞 v0.9-beta 内测启动，但阻塞 v1.0 正式版。

---

**文档最后更新**：2026-10-02
