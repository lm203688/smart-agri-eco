# 项目科学性评估与 SCI 论文可写性报告 · 2026-10-18

> **问题**：这个项目的科学性如何？有可能写 SCI 论文吗？
> **立场**：不吹不黑。按 SCI 审稿人的六维打分标准逐项量化，然后给出**三条论**文路径的诚实差距分析。
> **数据来源**：代码实测 + 数据实测 + Bench 648 次运行记录 + 文献引用计量。全部可复现。

---

## 0. 直接回答

**能写，但不是所有方向都能写。**

这个项目在工程可复现性上达到了**罕见的高标准**（零依赖 + golden vectors + 648 次 CI 全绿），这决定了它**可以发软件/系统类 SCI**（SoftwareX 档次，IF 3-4，中科院二区）。

但如果想发"方法类"农业期刊（Agricultural Systems / Field Crops Research，IF 4-6），**以当前状态投出去会被拒**——原因是硬的：**0 条真实田间数据**、**0 次外部模型对比**。这两项不是写作问题，是必须先做实验的问题。（原列的第三项「0 个负例用例」已于 **S1.2 交付**：20 个负例全绿接入 CI，见下方「负例用例」行。）

| 论文类型 | 当前可行性 | 门槛 | 判断 |
|---|---|---|---|
| **软件/系统类**（SoftwareX, Env. Model. Softw.） | 🟡 **够格但需补 4-6 周** | 负例 + 文献 + 1 个 baseline | ✅ 现在可启动 |
| **方法类**（Agric. Systems, Field Crops Res.） | 🔴 **当前会被拒** | 真实数据 + 多数据集统计验证 | ⏸ 需 6-12 个月 |
| **数据类**（Scientific Data, Data in Brief） | 🟡 **够格但需清洗** | 元数据规范化 + license 清理 | ✅ 2-3 个月 |

---

## 1. 六维审稿人打分（每项附实测证据）

### 1.1 Novelty 新颖性 — **7/10** ✅

**得分点**：
- "Agent-native 的农业知识基座"（MCP 工具 + A2A Card + Env Recipe 协议）在农业信息学领域**没有先例**。现有农业软件（DSSAT、MONICA、AquaCrop）全部是"人操作 GUI/CLI"，本项目是"AI Agent 直接调用 `agri_growth_plan`"。
- "可审计数据血缘"（`core/data_lineage.py` + Trust 证书）作为**第一公民**设计，而非事后补丁——这是对 FAIR 原则中 Reproducible 的具体工程化。
- 保形预测（conformal prediction）应用到分布式小规模种植推荐场景，有明确的方法适配空间。

**扣分点**：
- 核心科学问题（GDD 物候、VPD 胁迫、产量上限）本身不是新问题——都是用 WOFOST/UNESCO 几十年前的公式。**新的是封装形式，不是科学内核。**
- "Env Recipe"作为概念很好，但审稿人会问：它和 FAO 的 Agro-Ecological Zones (AEZ)、CGIAR 的 Digital Agriculture Profile 在科学上有什么本质区别？目前的答案主要是**工程差异**（可被 Agent 调用），不是**科学差异**。

**结论**：新颖性够发 SoftwareX / Computers and Electronics in Agriculture，不够发顶刊的方法创新要求。

---

### 1.2 Rigor 方法严谨性 — **4/10** 🔴

这是**最大短板**。实测证据：

| 缺失项 | 实测 | SCI 要求 |
|---|---|---|
| 机理内核测试 | ✅ **已交付（S1.4）**：`engine/agriworld_lite.py` 从 0 测试 → `scripts/test_mechanism_domain.py` **34 项契约单测**（4 个核心函数逐条锁死），另加 `scripts/test_crop_registry.py` 23 项 | 每个核心函数必须有单元测试 |
| 数值边界校验 | ✅ **已修复（A2-α + S1.4）**：34 探针 **23 FAIL-GIGO（67.6%）→ 0 FAIL（0%）**，非法输入全部被拒绝；实测 28 抛异常 / 6 返回合法边界值 | 非法输入必须被拒绝或降级且不污染输出 |
| 负例用例 | ✅ **已补齐（S1.2）**：Bench 69 → 89 用例，新增 `cases/neg/` 20 个负例（A 输入合法性 8 · B 诚实降级 6 · C 反事实不变式 4 · D 血缘/信任断裂 2），全部映射到**真实代码路径**（`core/numeric_domain` / `core/honest_policy` / `engine.agriworld_lite.simulate` / `core/recipe_signing` + `data_lineage.verify_lineage_intact`），`run_bench.py --summary` 输出 `negative: 20/20 passed`，CI 门禁 #40 | 原缺口「必须有 negative control，证明"拒识能力"」已闭合 |
| 消融实验 | 无任何 ablation（去掉保形预测、去掉双源校准、去掉血缘各掉多少分） | 方法类论文必须有 |
| 统计检验 | ✅ **已交付（S1.3）**：`stat_report.py` 对 652 条历史记录 + 5 次多种子实验统计。结论：`pass_rate` 恒 1.0 是**事实**（回归套件全绿），非缺陷；真正有方差的是 `conformal_coverage`（0.92±0.022）与 `mean_abs_dev`（0.004±0.004）。数据源 `benchmarks/results/stat_summary.json` | 至少 5 个随机种子的 mean ± std |

**最刺眼的一条**：648 次 bench 运行，**pass_rate 从 1.0 到 1.0，一个值**。审稿人看到这个会立刻明白——**测试集是固定的、确定性的、没有统计波动**，因此"通过率"这个指标没有统计意义。正确的做法是：多种子 + 多数据划分 + 报告 mean ± std。

**保形预测的特殊问题**：`conformal_coverage` 498 次运行**全部 = 0.92**，而同批 `pass_rate` 恒为 1.0。这说明 0.92 是在**同一个固定合成数据集**上算出的确定性结果，不是在多个真实数据集上的自适应校准。Vovk (2012) 和 Lei & Wasserman (2018) 的保证是"边际覆盖"，需要在**新样本上验证**——目前一个外部样本都没有。

**结论**：这一项不补，任何"方法类"投稿都是 desk reject。

---

### 1.3 Reproducibility 可复现性 — **8.5/10** ✅✅（最强项）

这是项目**真正超越同类工作**的地方：

| 要素 | 实测 |
|---|---|
| 零第三方依赖 | `agent/ core/ engine/ mcp/` 的 import 只有标准库 → 无 supply chain 风险、无版本地狱 |
| Golden vectors | 19 个向量（phenology 7 / forecast 7 / nutrition 6），每个带 **`rationale` 手写推理链** + **`tolerance.reasoning`** |
| 历史运行记录 | `results_history.json` **648 条**，含 `timestamp` + `commit` hash + `by_axis` 分解 |
| 原子写入 | `core/atomic_io.py`（fsync + os.replace） |
| CI | 39 步 × 3 Python 版本 |
| Bench 时间跨度 | 2026-10-15 07:09 → 2026-10-18 08:33（3 天连续） |

**Golden vector 的设计尤其专业**。看 phenology 的第一个用例：

```json
{
  "id": "potato_18c",
  "rationale": "马铃薯 @ 18°C（TBASE=2，效温 16）：出苗 170/16=10.6d，
                 开花 (170+150)/16=20.0d，成熟 (170+150+1550)/16=116.9d",
  "payload": {"crop": "马铃薯", "mean_temp_c": 18.0},
  "expected": {"emergence_days": 10.6, "anthesis_days_from_sow": 20.0, ...}
}
```

`rationale` 字段把"为什么这个值是 10.6 天"写成了人可读的推导链——**这是绝大多数农业软件论文做不到的**（它们只给数字，不给推导）。审稿人可以逐条手算验证，这对接受率是实打实的加分。

**扣分点**（1.5 分）：
- Golden vectors 的 `expected` 值**没有 reference/citation**——审稿人第一问必然是"10.6 天这个数哪来的？" 目前答案是"我们自己按 WOFOST 公式算的"。**必须是：①引 WOFOST 原始文献，②或引一个公开数据集（如 FAO 的 gdearm / AgMIP 的基准）作为外部锚点。** 没有外部锚点的 golden vector 是自证。
- `rationale` 是自然语言，不是结构化证明——无法自动校验"推导是否成立"。

---

### 1.4 Validation 实验验证 — **2/10** 🔴🔴（最致命）

**实测数据**：

| 指标 | 目标（CORE_OBJECTIVE G2） | 实际 |
|---|---|---|
| `feedback_log` 真实回流 | ≥ 30 条 | **0 条** |
| `execution_log` 条目 | ≥ 20 条 | 87 条，但 **`source=shadow` 87/87（100%）** |
| 非影子观察 | — | **0 条** |
| 图像回流 | ≥ 50 张 | **0 张** |
| `measured` 级数据质量 | — | 152/760（20%），其余 60% 是 `modeled` |

**这说明什么**：项目目前的全部"实验"都是在**合成数据/回放数据**上做的自证循环。没有任何一条**真实世界的反馈**进入系统。

对于 SCI 这意味着：

- 想写"我们的推荐比现有方法好" → 无法回答"好在哪个真实场景？"
- 想写"用户采纳率 X%" → 无用户数据
- 想写"田间验证产量预测误差 Y kg/㎡" → 无田间数据
- `verify_service.py`（Verify-as-a-Service）的"可信标记" → 没有任何一条被真实执行验证过的记录

**对比参照**：DSSAT 的论文有 40 年田间试验；AquaCrop 有全球 30+ 站点验证；连 PlantVillage 数据集论文都有 58,000 张真实病害图像。本项目的验证层目前是**空的**。

**结论**：这是"方法类论文"的绝对阻断项，也是唯一无法靠写作/工程绕过的短板。

---

### 1.5 Data 数据质量 — **5.5/10** 🟡

**好的部分**：
- 152 份 Env Recipe，**120 个独立 species**、112 个拉丁名、62 个科属 —— 覆盖度对一篇数据论文是够的
- 760 条 `sources[]` 三字段（`source_license` / `data_quality` / `trial_location`）**100% 补齐**
- 数据血缘（哪些配方引用哪个源、哪个许可证）完整可追
- `data_quality` 分层诚实标注（`modeled` 456 / `interpolated` 152 / `measured` 152）

**问题部分**：
1. **`license=unknown` 152 条** —— 法务隐患，也是 Sci Data 类期刊的**硬拒项**（Data availability 声明不能有 unknown license）
2. **科属名字段中英文混用**：`仙人掌科` vs `Cactaceae`、`豆科` vs `Fabaceae`、`茄科` vs `Solanaceae`、还有一条 `'多样'`（明显是占位符）。数据论文会被要求统一到 GBIF/TPL 分类标准。
3. `recipe_version` 全部 `1.0.0` —— 没有版本演化信息
4. `zone` 字段 152 条全为 `None`（在 environment 子对象里，不是顶层——这是 schema 设计问题）

---

### 1.6 References 文献引用体系 — **2/10** 🔴

**全文实测**：
```
docs/ + benchmarks/ 的 .md 文件中：
  "doi"（小写）     : 2 次
  "DOI"（大写）     : 0 次
  "arXiv"           : 2 次
  "et al"           : 11 次
  "References"      : 0 次
  "参考文献"         : 0 次
```

**这意味着**：项目**没有建立任何文献引用体系**。WOFOST 公式用了，但没引 Supit et al. (1994)；Köppen 分类用了，但没引 Peel et al. (2007)；保形预测用了，但没引 Vovk (2012)。

这不是"还没写论文所以不用引"的问题——**golden vectors 的 expected 值必须能追溯到文献**（见 1.3），没有引用链，全部分配方在科学上都不可追溯。

**这是最容易补的一项**（纯写作，1-2 周），但**优先级最高**，因为其他所有分数都依赖它。

---

## 2. 三条论文路径的诚实差距分析

### 路径 A：软件/系统类论文 ✅ 现在可启动

**目标期刊**（按投稿难度排序）：

| 期刊 | IF | 分区 | 为什么合适 |
|---|---|---|---|
| **SoftwareX** (Elsevier) | ~3.4 | 中科院三区 | 专发"有科学价值的软件"，零依赖+648次CI+golden vectors 是完美卖点 |
| **Environmental Modelling & Software** | ~4.9 | 二区 | 偏建模软件，需要更强的模型验证（慎选） |
| **Computers and Electronics in Agriculture** | ~6.5 | 一区 | 收农业软件系统，但审稿人会要农业验证（难） |
| **Data in Brief** | ~1.3 | 四区 | 配套数据集描述，最易中 |

**论文骨架**：
> *"AgriEco: A Zero-Dependency, Agent-Native Platform for Reproducible Distributed-Horticulture Knowledge Delivery"*
> - 卖点 1：Agent-native（第一个把农业配置做成 MCP 协议的）
> - 卖点 2：可复现工程（零依赖 + golden vectors + 648 次连续 CI + 原子写入）
> - 卖点 3：可审计血缘（Trust 证书 + JWS 签名）

**4-6 周补齐清单**：

| # | 工作 | 工作量 | 为什么审稿人要 |
|---|---|---|---|
| 1 | **补 20+ 个负例用例**（拒绝/降级场景） | 3 天 | 证明系统会"说不"，不只是"会说好" |
| 2 | **Golden vectors 加 `reference` 字段**（DOI + 具体公式出处） | 1 周 | 这是 desk review 第一关 |
| 3 | **1 个 baseline 对比**：与 FAO AEZ 或一个开源规则引擎在 152 份配方上做一致性/差异统计 | 2 周 | 证明"我们这个不是随手写的规则" |
| 4 | **文献引用体系**（30-50 篇，含 WOFOST / conformal / MCP 协议 / FAO 许可） | 1 周 | 上面已述 |
| 5 | 补 `engine/agriworld_lite.py` 单元测试 + 套 `numeric_domain` 装饰器 | 1 周 | 答"你怎么保证内部一致性" |

**成功率估计**：SoftwareX 70%（补齐后）/ Data in Brief 85%。

---

### 路径 B：方法类论文 ⏸ 当前会被拒

**目标期刊**：Agricultural Systems (IF 5.6) / Field Crops Research (IF 5.8) / Computers and Electronics in Agriculture (IF 6.5)

**想讲的故事**：
> "Split Conformal Prediction 在分布式园艺推荐中的可靠性：Agent-native 架构下的校准与反事实推理"

**当前阻断项（按严重度）**：

| 阻断项 | 现状 | 需要 |
|---|---|---|
| **真实数据** | 0 条 | ≥ 20 个真实种植周期（哪怕只有温室/阳台/室内柜） |
| **多数据集验证** | 单一合成集 | ≥ 3 个独立数据集报告 92% 覆盖率的 mean ± std |
| **外部模型对比** | 0 次 | DSSAT 或 AquaCrop 在同参数下的物候/产量对比 |
| **消融实验** | 无 | 去 conformal / 去双源 / 去血缘 三组的指标差 |
| **负例** | ✅ 20 个（S1.2，超 15 个门槛；C4 容差为待作者确认项，实测相对偏差 0.2%） | 至少 15 个 negative control |

**最短补齐路径（6-12 个月）**：
1. 用 20-50 元的成本搭建 3-5 个真实种植节点（室内种植柜 + ESP32 + 温湿度传感器），连续跑 2-3 个种植周期 → 拿到真实 `measured` 数据
2. 或者：找公开数据集做迁移验证（如 AgMIP 的 benchmark、或 FAO 的 GAEZ 站点数据）
3. 做 DSSAT 对比：同作物同气候，跑 DSSAT v4.8（需 MATLAB，本项目零依赖原则下可只在离线分析用），报告 RMSE / MAE / 一致性相关系数 (CCC, Lin 1989)

**成功率估计**：当前 5%（desk reject 级）。补齐后 40-50%。

---

### 路径 C：数据论文 ✅ 2-3 个月

**目标**：Scientific Data (IF ~9,  natura 旗下) / Data in Brief

**故事**：发布 Env Recipe 数据集——152 份可执行配置、120 species、760 条来源 + 许可血缘。

**这可能是性价比最高的一条**，因为：
- 数据已经有了（152 份）
- 血缘已经有了（760 条 sources 三字段齐）
- 可复现性已经有了（schemas + 零依赖加载器）

**补齐清单**：

| # | 工作 | 工作量 |
|---|---|---|
| 1 | 清理 152 条 `license=unknown`（逐个查源或移除） | 2 周 |
| 2 | 统一科属名到 GBIF backbone（`仙人掌科`→`Cactaceae`，消除中英混用和 `'多样'`） | 1 周 |
| 3 | 补 `zone` 顶层字段（152 条全 None 必须修） | 2 天 |
| 4 | 写 Data Descriptor 模板（Scientific Data 有固定结构）+ 20 篇引用 | 2 周 |
| 5 | 数据可用性声明（Zenodo/figshare DOI + 许可证选择：建议 CC BY-NC-SA 保持与 FAO 源一致） | 3 天 |

**成功率估计**：Data in Brief 80% / Scientific Data 35%（Scientific Data 要求更强的科学叙事，不是纯数据集罗列）。

---

## 3. 如果只做三件事，做哪三件

按"对论文贡献最大 / 耗时最短"排序：

1. **建文献引用体系**（1 周）—— 把 WOFOST / Köppen / conformal / MCP / FAO 许可的核心文献找齐，给 golden vectors 的每个 expected 值加 DOI。**这是所有路径的前置条件，ROI 最高。**
2. **补 20 个负例用例**（3 天）—— 把 bench 从"正向回归"升级为"正负对抗"，直接支撑 Rigor 分数从 4 → 6。
3. **启动真实数据采集**（3-5 个节点，一次性投入 < 500 元，持续 2-3 个月）—— 这是从"软件论文"跨到"方法论文"的唯一门票，也是 G2 的核心指标。**它的价值不只是论文，是项目从"文献推导"变成"实测校准"的分水岭。**

---

## 4. 总结：一张表说清

| 维度 | 分数 | 能写什么 |
|---|---|---|
| Novelty | 7/10 | ✅ 软件论文的核心卖点 |
| Rigor | 4/10 | 🔴 方法论文的阻断项 |
| Reproducibility | 8.5/10 | ✅✅ **最强项，论文的脊梁** |
| Validation | 2/10 | 🔴🔴 最致命，无法绕过 |
| Data | 5.5/10 | 🟡 数据论文需清洗 |
| References | 2/10 | 🔴 最容易补，优先做 |

**加权总分：4.9/10** —— 对应"一篇合格的 SoftwareX 期刊论文需要 2-4 周补齐；一篇方法类 SCI 需要 6-12 个月真实数据积累"。

**最后一句诚实的话**：这个项目**当前不是一个"等待写论文的科学项目"，而是一个"写论文的好苗子"**。它的工程纪律（零依赖、golden vectors、648 次 CI）已经超过 90% 的农业软件论文；但它缺的恰恰是科学论文最硬的那块——**真实世界的验证**。那块补上，SCI 是水到渠成；补不上，就安心发 SoftwareX 和 Data in Brief，也是实打实的产出。

---

*本报告生成于 2026-10-18，基于代码扫描、数据实测与 648 次 bench 运行记录分析。*
