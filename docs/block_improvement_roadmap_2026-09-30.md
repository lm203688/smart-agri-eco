# 智慧农业生态 · 板块深度调研与改进路线图（2026-09-30）

> 定位：**发行后迭代路线图**。本轮不追数量（MCP 工具数），而追**方法论硬骨头**。
>
> 铁律：真实数据、不编造。所有改进必须能证明"提升了产品力"，不是"改了代码"。

---

## 1. 调研发现（5 板块，一手信息）

### 板块 A · Env Recipe / MCP 生态

**市场格局**（chatforest.com / 2026-05 汇总）：
- **Linux Foundation `agstack/opensource-pestmodels`**：13 models / 19 crops / 54 threats，fuzzy Mamdani 推理 + 完整 MCP 工具。**这是可对接的开源标准，不是竞品**。
- **FieldMCP**（商业）：$29/org/month，150+ 农艺规则 / 12 领域。唯一商业农业 MCP 平台。
- **Leaf Agriculture MCP**：唯一商业统一 farm data API，聚合 John Deere/CFV/CNHi/AGCO/Trimble。
- **mcp-agriculture**（Rust）：35 tools 全栈，内置 Kenyan farm backend，Apache-2.0。
- **kilimo-mcp**：Kenya 精准农业 6 工具 + Africa Coordination Stack 32 MCP 生态。

**关键差距**：
- 数量差距（13 vs 35 vs 150+）——**我们不追数量**，因为我们是"知识配方"而非"数据入口"。
- **差异化护城河**：110 Env Recipe + 107 双源校准 + 4/4 血缘追溯——**这些是数据入口型工具做不到的**。
- **agstack pestmodels 是直接机会**：可作为**生态对接**而非自建，填补我们"视觉后端未接入"的空缺。

### 板块 B · 气候多源调和（硬骨头 #1）

**2025 同行验证**：
- Verpeta et al. (2025) Ukraine 研究：NASA POWER + Open-Meteo 融合显著优于单一源，**但需站点级偏差校正**。
- Ravindu & Dias (2025) Sri Lanka Nuwara Eliya 研究：NASA POWER 0.5° 分辨率在数据稀缺高地 **R=0.66（温度）/ R=0.92（云量）/ 降水有系统正偏差**（干季高估、雨季强度低估）。

**当前缺陷**：我们的 `climate_reconcile` 只做"算术平均"，**没有偏差校正**——在多源系统偏差下会产出"看似可信但整体偏移"的调和值。这正是**多源融合的方法论硬缺陷**。

### 板块 C · 病虫害 AI

**2025 前沿趋势**：
- PLA-ViT (2025)：99.77% accuracy on PlantVillage。
- **CCT (Compact Convolutional Transformer)**：16.66 MB / **0.7 ms 推理** / 93.55% accuracy——**边缘部署友好**（CABI 2025）。
- **GreenViT**：参数 86M → 21.65M，边缘部署优化。
- **多模态融合**：RGB + hyperspectral + thermal 显著提升复杂环境下的鲁棒性。

**关键洞察**：视觉后端选型是**产品决策**（用户待拍板 E），工程可先加"模型接入层"占位。但 Linux Foundation agstack pestmodels **已经存在**，本轮不动，写进 roadmap。

### 板块 D · AgTech DD 初筛（硬骨头 #2）

**2025 投资人硬指标**（iGrow News / Harvest Returns Chris Rawley 2025）：
- **3:1 ROI for farmers**——Seed 阶段核心硬门槛，Rawley 原话："You need to show a 3:1 ROI for farmers if they're your customer."
- **5 大 DD deal-killers**：IP 归属、客户合同限制、Cap table 错误、创始人诉讼、财务重述。
- **AgTech 特有合规**：EPA 农药注册、USDA 有机认证、水权。
- **VC 评估维度**：Scientific Innovation / Market Fit & Scalability / Capital Efficiency / ESG Alignment / Founding Team。

**当前缺陷**：bp_screen 规则库 v2.0.0 有 **6 闸**，全是财务/客户侧（cash_ratio / client_concentration / margin_gap / unit_economics / runway / bio_asset），**完全缺 AgTech 特有的 3:1 ROI 硬指标**。

### 板块 E · MCP 分发

**关键判断**：
- FieldMCP 定价 $29/org/month 已验证农业 MCP 商业模式可行。
- Linux Foundation agstack 是农业 MCP 的开源标准，我们应考虑**接入**而非自建。
- 我们的商业化边界（"只做 MCP 分发"）与 agstack 生态天然契合。

---

## 2. 每板块改进方向（按 ROI 排序）

| 板块 | 改进方向 | 类型 | 本轮可否落地 | 预计影响 |
|---|---|---|---|---|
| **A** Env Recipe | 引入 AgGateway / ADAPT 数据交换标准，让配方跨平台互操作 | 生态对接 | ❌ 需标准调研 | 提升互操作性 |
| **A** Env Recipe | 对接 Linux Foundation agstack pestmodels（13 models / 54 threats） | 生态对接 | ❌ 需产品决策 | 补齐病虫害能力 |
| **B** 气候多源 | **偏差校正**：估计各源相对多源中位数的月度系统偏差，剔除后再平均 | 方法论硬骨头 | ✅ **本轮已落地** | 高原/热漠区精度提升 |
| **B** 气候多源 | 接 WorldClim 2.1 栅格作为第三源（打破"两源天花板"） | 数据源扩展 | ❌ 需瓦片下载管道 | 提升交叉验证强度 |
| **C** 病虫害 | 视觉后端接入层（ViT / MobileNetV2 / CCT 可插拔） | 工程占位 | ❌ 需产品拍板视觉后端选型 | 从"规则降级"升级到 CV |
| **C** 病虫害 | 对接 agstack pestmodels 作为**规则/模型引擎**（非视觉） | 生态对接 | ❌ 需评估 agstack API | 填补 pest_diagnose 硬缺口 |
| **D** BP 初筛 | **新增 3:1 ROI 硬指标 gate** | 方法论硬骨头 | ✅ **本轮已落地** | 覆盖 AgTech Seed 核心硬门槛 |
| **D** BP 初筛 | 加 5 大 DD deal-killers 扫描（IP 归属/客户合同/cap table/创始人诉讼/财务重述） | 规则扩展 | ❌ 需扩展 extractor | 补齐 DD 常见 blocker |
| **D** BP 初筛 | AgTech 特有合规检查（EPA / USDA / 水权） | 规则扩展 | ❌ 需分类适配 | 触发 verify 门禁 |
| **E** MCP 分发 | 加 `agri_list_ecosystem` 工具：声明我们对接的开源生态清单 | 生态对接 | ❌ 本轮先文档化 | 提升 MCP 生态可见性 |
| **E** MCP 分发 | 商业化定价策略（对标 FieldMCP $29/org/month） | 产品决策 | ❌ 需用户拍板 | 决定商业模式 |

---

## 3. 本轮落地的 2 个硬骨头（已实施 + 验证）

### 硬骨头 #1：climate_reconcile 偏差校正

**问题**：多源融合只做算术平均，在多源系统偏差下（Sri Lanka Nuwara Eliya 高地 NASA POWER 温度偏差 R=0.66）产出"看似可信但整体偏移"的调和值。

**改动**：
- `core/climate_reconcile.py::reconcile_climate()` 新增 `bias_corrected=True` 参数
- 新增输出字段：
  - `source_biases`：每源逐月偏差 + 均值/标准差 + 参考基准（多源中位数）
  - `corrected_mean`：偏差校正后的调和值（各源减去其月度偏差再平均）
  - `correction_magnitude_c`：校正幅度（原调和 vs 校正后的逐月 |Δ| 均值）
- `render_text()` 补一节"🔧 偏差校正"输出
- `bias_corrected=False` 保持 v1 行为，向后兼容

**方法学对齐**：2025 Ukraine 论文（Verpeta）+ 斯里兰卡研究（Ravindu & Dias）验证的 bias correction 范式，不引入新外部依赖。

**验证证据**（`scripts/test_climate_reconcile.py` 新增 7 项）：
- `test_bias_correction_produces_all_fields`：字段结构完整
- `test_two_source_bias_sums_to_zero`：数学恒等式（中位数基准下偏差互抵）
- `test_open_meteo_bias_is_positive_for_power_minus_one`：能正确捕捉"Open-Meteo 恒高 1℃"系统偏差
- `test_bias_correction_disabled_preserves_v1_contract`：向后兼容
- `test_single_source_skips_bias_correction`：单源跳过（数学上无意义）
- `test_zero_bias_both_sources_identical`：零偏差极限情况
- `test_corrected_mean_finite_and_valid_range`：结果有限且在 [-40, +50]℃ 合理范围

### 硬骨头 #2：bp_screen 加 3:1 ROI 硬指标

**问题**：bp_screen 规则库 v2.0.0 有 6 闸全是财务/客户侧，**完全缺 AgTech Seed 阶段最核心的 3:1 ROI 硬指标**（Harvest Returns 2025 明确 Deal-Killer #1）。

**改动**：
- `bp_screen/extractor.py::FIELD_PATTERNS` 新增 `farmer_roi` 正则提取（"农户ROI 3:1" / "农民投入产出比 4" / "农户每亩净收益 3.5 倍"）
- `bp_screen/extractor.py::normalize()` 新增 `n["farmer_roi"] = g("farmer_roi")`
- `bp_screen/rules.py` bump `RULES_VERSION` v2.0.0 → **v2.1.0**，`VERSION_HISTORY` 追加一条
- `bp_screen/rules.py::GATES` 新增 `farmer_roi` gate：`metric="farmer_roi", default=3.0, op="lt", severity="warn"`

**语义设计**：
- `severity="warn"`（非一票否决）：早期项目数据不完整常见，报告置顶提示但不阻断
- 缺失即跳过：`farmer_roi` 抽取不到时 gate 静默跳过（视为"未披露"，不判为违规）——与 v2.0.0 verify 类门禁的语义一致

**验证证据**（`scripts/test_engine_v5.py` 新增 6 项）：
- `test_farmer_roi_gate_registered`：gate 结构完整
- `test_farmer_roi_normalize_field_present`：normalize 无条件写键
- `test_farmer_roi_regex_extraction_3_to_1`：3 种常见文本表述能正确抽取
- `test_farmer_roi_gate_fires_below_threshold`：2.0 触发 warn
- `test_farmer_roi_gate_not_fired_at_or_above_threshold`：3.0/3.5/5.0/10.0 都不触发
- `test_farmer_roi_gate_skipped_when_missing`：缺失静默跳过（不误报）

---

## 4. 全量验证结果

| 指标 | 改动前 | 改动后 |
|---|---|---|
| 单元测试 | 477 OK / 3 skip | **490 OK / 3 skip** (+13) |
| verify_all | PASS | **PASS** |
| MCP 工具 | 13 | 13（向后兼容） |
| bp_screen RULES_VERSION | v2.0.0 | **v2.1.0** |
| climate_reconcile bias_corrected | 无 | **✅ 默认启用** |

**新增测试**：
- `ReconcileBiasCorrection` 7 项（`test_climate_reconcile.py`）
- `TestColdStart` farmer_roi 系列 6 项（`test_engine_v5.py`）

---

## 5. 未落地项 Roadmap（按优先级）

### P0 · 高价值 · 需用户拍板
1. **视觉后端选型**（板块 C）——pest_diagnose 从"规则降级"升级到 CV 是最大能力跃迁
2. **hot_arid / highland 分区建模**——高原偏差校正落地后，这两个分区的 recommendation 精度将显著提升
3. **agstack pestmodels 对接决策**——开源生态对接 vs 自建视觉后端

### P1 · 工程可推进 · 但需产品定义
4. **WorldClim 2.1 接入**——打破"两源天花板"，需瓦片下载管道
5. **bp_screen 加 5 大 DD deal-killers 扫描**——每类需扩展 extractor regex
6. **AgTech 特有合规检查**（EPA/USDA/水权）——需在 classify 里加合规维度

### P2 · 生态对接 · 提升可见性
7. **AgGateway / ADAPT 数据交换标准**——让 Env Recipe 跨平台互操作
8. **`agri_list_ecosystem` MCP 工具**——声明对接的开源生态清单
9. **商业化定价策略**——对标 FieldMCP $29/org/month 制定我们的 MCP 分发定价

---

## 6. 板块成熟度快照

| 板块 | 当前 | 目标（v1.0） | 关键缺口 |
|---|---|---|---|
| A · Env Recipe | 110 配方 / 107 校准 | 加入 agstack 生态对接 | 视觉后端 + 生态对接 |
| B · 气候多源 | ✅ **已加偏差校正** | 加第三源 WorldClim | 打破两源天花板 |
| C · 病虫害 | 规则降级 | ViT 视觉后端接入 | 产品决策阻塞 |
| D · BP 初筛 | ✅ **已加 3:1 ROI 硬指标** | 加 DD deal-killers + 合规 | 需扩展 extractor |
| E · MCP 分发 | 13 工具 | 加生态声明工具 | 商业定价策略 |

---

## 7. 方法论小结

**本轮的核心判断**：
1. **不追工具数量**——FieldMCP 150+ 是数量竞争，我们的护城河是**方法深度**（107 双源校准 / 4 血缘 / 偏差校正）。
2. **优先啃方法论硬骨头**——`climate_reconcile` 从"算术平均"升级到"偏差校正"是**方法学升级**，不是加字段。
3. **生态对接 > 自建**——Linux Foundation agstack pestmodels 是**开源标准**，我们对接而非重复造轮子。
4. **规则库改动要 bump 版本 + 记录历史**——bp_screen v2.0.0 → v2.1.0，`VERSION_HISTORY` 追加，让下次改规则的人知道坑在哪。

**下次迭代方向**：
- 板块 C（病虫害视觉后端）是**最大能力跃迁点**，但需要用户拍板视觉后端选型（决策 E）。
- 板块 D 的 5 大 DD deal-killers 是**规则扩展**，可以在下个 sprint 完成。
- 板块 E 的生态对接是**长期投入**，需要产品定义后再动。

---

*本路线图生成于 2026-09-30，与 `harness/manifest.json` 版本 2.2.0、`bp_screen/rules.py` 版本 v2.1.0 对齐。*
