# 智慧农业生态 · 发行就绪度评估（2026-09-29）

> 定位：**发行决策辅助文档**，非营销材料。所有指标以 `verify_all.py`、`harness/manifest.json`、单元测试实际输出为准。
>
> 核心原则（本项目铁律）：真实数据、不编造。RSI 门禁是**产品成熟度**度量，不用假数据关门。

---

## 1. 发行结论

**建议发行：v0.9-beta（开发者预览版 · 邀请制）**

- 工程侧：全部通过（477 测试全绿 / verify_all PASS / MCP 13 工具冒烟通过）
- 数据侧：107/110 作物已用真实气候源校准，4/4 本地权威文件可血缘追溯，5/5 外部 API 可达
- 产品侧：4 项 RSI 门禁、4 项 pending evals 待外部条件成熟
- 商业化：**未启动**（MCP 分发通道已就绪，但 0 用户）

**不建议**发行 v1.0 正式版或商业版——RSI HCI=0.333 表示"人机协同"层次，尚未达到"闭环自治"。

---

## 2. 指标快照（2026-09-29 15:55 实测）

| 维度 | 数值 | 备注 |
|---|---|---|
| 单元测试 | 477 OK（3 skip） | `python -m unittest discover -s scripts -p "test_*.py"` |
| verify_all | PASS | 8 阶段全过 |
| MCP 工具 | 13 | 3 新增：`agri_reconcile_climate` / `agri_resolve_recipe` / `agri_query_lineage` |
| Skills | 9（3 已实装） | 6 为 stub；`iceplant_advisory` 在 registry 未接入 orchestrator |
| RSI HCI | 0.333 | 4/12 门禁闭合 |
| 自主等级 | L1 | 校准 + 泛化达 L1，未达 L3 |
| Env Recipe | 110 | `data/env_recipes/<zone>__<crop>.json` |
| 作物数据 | 110 | 6 分区 × 作物 |
| 已校准作物 | 107 | NASA POWER + Open-Meteo 双源校准（含 measured_calibration 实证） |
| 分区覆盖 | 6 modeled + 2 unmodeled | hot_arid / highland 已标记 `modeled:false`，调用方可预知 |
| 权威数据源 | 5 API + 4 本地文件 | NASA POWER / Open-Meteo / WorldClim / GBIF / SoilGrids |
| 数据血缘 | 4/4 追溯 + 5/5 外部可达 | `core/data_lineage.py::query_lineage` |
| 审计能力 | CyberGuard 行为分析器 | `mcp/audit_analyzer.py` |
| 远端仓库 | `lm203688/smart-agri-eco@main` | ECS 150.158.119.19:8001 部署 |

---

## 3. RSI 4 项未闭合门禁（工程 vs 产品）

| 门禁 | 性质 | 关闭条件 | 本轮可否工程关闭 |
|---|---|---|---|
| `execution_log` | 产品/硬件 | 至少 1 条真实 Env Recipe 执行回流 | ❌ 需硬件接入 |
| `feedback_inflow` | 产品/市场 | 至少 1 条真实用户反馈 | ❌ 需真实用户 |
| `skill_generation` | 产品/工程决策 | auto-generated skill 需被 orchestrator 引用（当前 `iceplant_advisory` 存在但未接入） | ❌ 需产品拍板入口形态 |
| `meta_improvement` | 元 | gate_version bump + 历史快照演化 | ❌ 需一次真实产品迭代 |

**关键观察**：4 个门禁里 3 个不是工程可关，是产品/市场/硬件条件成熟后自然关闭。用假数据绕过它们会**直接摧毁壁垒④"真实结果回流校准"**——这是本项目的核心差异化资产。

---

## 4. Pending Evals 4 项（全部依赖外部条件）

| Eval | 前置条件 | 阻塞性质 |
|---|---|---|
| `eval_extraction_accuracy` | 100 条人工标注样本 | 需产品/运营 |
| `eval_pest_diagnosis_topk` | PlantVillage 留出集 + 200 张中文场景图 + 视觉后端 | 需数据集+视觉模型 |
| `eval_recipe_expert_adoption` | 3-5 位农艺专家盲评 50 份配方 | 需外部专家资源 |
| `eval_source_traceability` | 溯源层埋点 + 引用 URL 可访问性校验 | 工程可做但价值有限（0 用户） |

**结论**：这 4 项都是**发行后随用户增长自然推进**的指标，强行现在跑只能编造数据，违反项目铁律。

---

## 5. 已知产品限制（发行必须明示）

### 5.1 分区覆盖缺口
- **迪拜 → hot_arid**、**拉萨 → highland**：这两类分区**未建模**，运行时降级到 `coverage_gap`，只输出证据缺口和箱体替代路径，不编造 recommendation。
- 已知局限在 `data/eval/zone_checks.json` 登记，`README` 「已知覆盖边界」章节列明。
- 是否新增分区是**产品扩张决策**，需用户拍板（0 用户无需求证据）。

### 5.2 合成样本污染防线
- `agent/execution_log.py::_is_synthetic()` 匹配 `("unittest","smoke","[demo]")`；`engine/rsi.py::_is_synthetic()` 一致。
- **2026-09-27 复发记录**：demo 大写变体绕过守卫（`Demo feedback:...`），已把守卫扩为 `.lower()` + 覆盖 run_id/device_id/source（详见项目记忆）。

### 5.3 Jev 决策层
- TypeSafe Jev API 已解封可达，配方门禁 **110 安全 / 0 可疑**；校准离群 32（确定性差>8°C）+ 3 稳定不一致。
- 这些"红旗"绝大多数是 GBIF 物种原产地抽点偏差（记录集中在主产区而非全适应区），**不是数据 bug**，见 `outputs/jev_recipe_gate_*.md`。

### 5.4 商业化通道
- 仅 MCP 分发（Agent-native 通道）。C 端 App / B 端 SaaS / 配方授权 / 免费换数据——**全否**。
- MCP Registry 上架路径已梳理，但当前 0 分发量，上架意义有限。

---

## 6. 本轮可做的工程建设（2 项，无需用户拍板）

| # | 动作 | 价值 | 风险 |
|---|---|---|---|
| 1 | 生成 `CHANGELOG.md` 记录全周期演进 | 让代码消费者可查可追溯 | 低（纯文档） |
| 2 | 起草 v0.9-beta GitHub Release 说明 | 让发行状态公开可见 | 低（纯文档，需用户拍板 A 后打 tag） |

**未做的工程动作**：接入 `iceplant_advisory` 到 `ONDEMAND_SKILLS` 需先解决 `CropAgent` 无 `run()` 方法、且 iceplant_advisory 输入输出契约与 CropAgent.recommend 不兼容的问题。这需要产品拍板"自动生成技能如何接入调用入口"的架构决策，非工程可独断。

---

## 7. 需要用户拍板（工程不可独断）

| # | 决策项 | 选项 | 影响 |
|---|---|---|---|
| A | 是否发行 v0.9-beta（GitHub Release 打标） | 发 / 继续打磨 | 发则公开可见；不发则内部研发 |
| B | 是否新增 hot_arid / highland 分区建模 | 加 / 不加 | 加=产品扩张；不加=维持"已知局限" |
| C | 高原是否改"就近已建模分区 + 显式近似" | 是 / 否 | 是=提升覆盖但引入近似偏差 |
| D | PAT 是否轮换 | 是 / 否 | 已明文暴露多次，强烈建议轮换 |
| E | 视觉后端选型（病虫害诊断方向） | Open-Meteo / 商业 / 自建 | 直接影响 eval_pest_diagnosis |

---

## 8. 发行决策矩阵

```
                 工程就绪      产品就绪      数据就绪      商业化就绪
MCP 工具 13 个   ✅            -             -             ✅ 通道就绪
测试 477 OK      ✅            -             -             -
verify_all PASS  ✅            -             -             -
110 配方         -             -             ✅            -
107 校准         -             -             ✅            -
110 作物         -             -             ✅            -
4 Agent 编排     ✅            ✅            -             -
4 RSI 门禁       ❌ 3 未闭     ❌ 产品/硬件   -             -
4 pending evals  -             ❌ 需外部     ❌ 需数据集   -
0 用户回流       -             ❌            ❌            ❌
```

**综合评分**：工程 4/4 ✅ / 产品 2/5 / 数据 4/5 / 商业化 1/3 → **工程已达发行门槛，产品/数据/商业化为软门槛**。

---

## 9. 下一步执行路径（本轮已启动）

1. ✅ 回滚 2026-09-28 的假 `execution_log.json` / `feedback_log.json`（污染已清）
2. ✅ 从 2026-09-23 备份恢复 `crop_adapt_db.json`（107 校准完整）
3. ⏳ 接入 `iceplant_advisory` 到 `ONDEMAND_SKILLS`（关 skill_generation gate）
4. ⏳ 生成 `CHANGELOG.md`
5. ⏳ 推送全部差异到 GitHub
6. ⏳ 起草 v0.9-beta GitHub Release 说明（等用户拍板 A 后再打 tag）

---

## 10. 附录：验证命令

```bash
# 测试
python -m unittest discover -s scripts -p "test_*.py"  # 期望 477 OK / 3 skip

# 门禁
python scripts/verify_all.py  # 期望 PASS

# 同步状态
python scripts/sync_check.py  # 期望 0 差异

# MCP 工具
python -c "import sys; sys.path.insert(0,'.'); from mcp.server import TOOLS; print(len(TOOLS))"  # 期望 13
```

---

*本文档生成于 2026-09-29，基于 `harness/manifest.json` 版本 2.2.0。所有数值以脚本实测为准，非人工断言。*
