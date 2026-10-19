# 项目 SCI 论文达标度核查报告（2026-10-19）

> 核查方式：**直接读代码 + 跑静态扫描 + 读 Bench/数据资产**，所有结论附可复核证据。
> 对比基线：`docs/SCI_WRITABILITY_2026-10-18.md`（加权 4.9/10）。
> 配套方案：`docs/SCI_ROADMAP_2026-10-18.md`（S1/S2-A/S2-B/S3）。

---

## 0. 一句话结论

**尚未达到 SCI 论文要求，但距离「SoftwareX / Data in Brief 类软件-数据论文」投稿门槛已从 4.9/10 推进到约 6.8/10，且剩余缺口全部可由 agent 自主补齐（无需外部帮助）。距离「方法类/农学论文（Agric. Systems）」仍远，因其硬门槛是真实田间数据，必须由你本人完成（S2-B）。**

两个**必须解决**的硬伤（否则任何投稿都会被 desk reject）：
1. **`results_history.json` 668 次运行的 `pass_rate` 恒为 1.0、`std=0.0`**（S1.3 统计纪律未做）——确定性测试集下这本身合理，但论文里不能把它当「精度指标」呈现，必须改为「多随机划分的 mean±std」或明确标注为确定性回归测试。
2. **S2-A1 物候交叉验证未产出**（`stat_summary.json` 中 `rmse/mae/ccc/wofost` 命中次数为 0）——即「用 WOFOST 权威参数表做外部验证」尚未跑出结果文件。

---

## 1. 六维审稿人评分卡（更新版）

| 维度 | 基线(10-18) | **当前(10-19)** | 变化 | 关键证据 |
|---|---|---|---|---|
| Reproducibility 可复现 | 8.5 | **8.5** | → | 零依赖、golden vectors 已挂引用、668 次 CI 全绿 |
| Novelty 新颖性 | 7.0 | **7.0** | → | Agent-native 农业配置无先例，内核为 WOFOST 老公式 |
| Data 数据 | 5.5 | **6.0** | ↑ | 152 配方 / 120 species；`license=unknown` 已部分清理 |
| Rigor 严谨性 | 4.0 | **6.0** | ↑↑ | 20 负例骨架 + `negative_runner.py`(388行,真执行器) + 4 机理函数全 `@bounded` |
| References 文献 | 2.0 | **8.0** | ↑↑↑ | 3 个 golden vector 文件 schema v2,7 条引用,5/7 DOI 已填；REFERENCES.md 已建 |
| Validation 验证 | 2.0 | **2.5** | ↑(微) | execution_log 88 条**仍全 shadow**；feedback_log 0 条；S2-A1 未产出 |
| **加权总分** | **4.9** | **≈6.8** | **+1.9** | 见 §2 加权法 |

> 加权法（同基线）：`0.25*Repro + 0.20*Novelty + 0.15*Data + 0.15*Rigor + 0.15*Ref + 0.10*Valid`
> = 0.25*8.5 + 0.20*7 + 0.15*6 + 0.15*6 + 0.15*8 + 0.10*2.5 = 2.125+1.4+0.9+0.9+1.2+0.25 = **6.775**

---

## 2. 自上次评估以来「已完成」的实证（可复核）

| # | 已完成项 | 证据 | 对应路线图任务 |
|---|---|---|---|
| 1 | **Golden Vectors 引用挂载** | 3 文件全部 `schema=v2`；references：forecast 2 / nutrition 2 / phenology 3 = **7 条**；cases 100% 带 `reference_keys` | S1.1 部分 |
| 2 | **DOI 已填 5/7** | forecast 2/2、nutrition 1/2、phenology 2/3；剩 2 个待 doi.org 核对 | S1.1 |
| 3 | **REFERENCES.md 已建立** | 全仓 `rg` 命中 REFERENCES.md；docs 中 `doi.org`×6、`DOI`×20、`et al.`×43 | S1.1 |
| 4 | **20 个负例骨架 + 真执行器** | `benchmarks/agri_recipe_bench/cases/neg/` 20 个；`negative_runner.py` **388 行**，映射到 `numeric_domain`/`honest_policy`/`simulate+counterfactual`/`recipe_signing+data_lineage` 真实代码路径（非桩函数） | S1.2 |
| 5 | **4 个机理函数全部 `@bounded`** | `agriworld_lite.py` 的 `theoretical_yield_cap`/`temp_factor`/`water_stress_factor` + `derived.py` 的 `vpd` 均套装饰器；`test_mechanism_domain.py`/`test_mechanism_garbage_in.py` 存在 | S1.4 |
| 6 | **Baseline / 统计报告脚本就位** | `scripts/fetch_zone_baselines.py`、`benchmarks/.../stat_report.py`、`stat_summary.json` 已生成 | S1.5 / S2-A4 部分 |

---

## 3. 仍未解决的关键缺口（决定「能否投稿」）

| 缺口 | 严重度 | 证据 | 是否需外部 |
|---|---|---|---|
| **G1 · `pass_rate` 恒 1.0 / `std=0`** | 🔴 致命(可信度) | `results_history.json` 668 运行，`pass_rate` 集合=`{1.0}`，`conformal_coverage` 恒 `0.92` | ❌ 纯计算，agent 可做 |
| **G2 · S2-A1 交叉验证未产出** | 🔴 致命(验证维度) | `stat_summary.json` 中 `rmse/mae/ccc/wofost` 命中=0；无 WOFOST 对比报告 | ❌ 纯计算，agent 可做 |
| **G3 · 负例未并入主 Bench 集** | 🟡 高 | `cases/` 主集仍 69 例、负例 0；20 负例在 `neg/` 待并入 CI | ❌ agent 可做 |
| **G4 · 真实验证缺失** | 🟡 中(仅方法类致命) | execution_log 88 条全 `shadow`；feedback_log 0 条 | ✅ **需你种菜/采购** |
| **G5 · 2 个 DOI 未填** | 🟢 低 | nutrition 1 / phenology 1 | ❌ 需联网核对(agent) |

---

## 4. 分层达标判定

### 路径 A · SoftwareX（软件论文，IF≈3.4）—— **可投状态：≈75%**
- ✅ 已具备：可复现底座、引用体系、负例执行器、机理契约、基线脚本
- ❌ 还差 3 件（全部 agent 自主）：
  1. 修 G1（统计纪律：多划分 mean±std，或明确标注为确定性回归）
  2. 跑 G2（S2-A1 物候交叉验证 → 填 `stat_summary.json`，给出 RMSE/CCC）
  3. 并入 G3（负例进 CI）→ 写稿 S3
- **结论：解决 G1+G2+G3 后（预计 2-3 周）即达 SoftwareX 投稿线。不需要你种菜。**

### 路径 B · Data in Brief（数据论文）—— **可投状态：≈70%**
- 数据资产已齐（152 配方、Köppen 11,946 cells、WOFOST 参数表），主要补数据描述文档 + 许可清理。
- **结论：与 A 同期可达。**

### 路径 C · Agric. Systems / Field Crops Res.（方法类，IF≈5.6-5.8）—— **可投状态：≈20%**
- ❌ 硬门槛：真实田间数据（≥20 条 `source=real`）。当前 0 条。
- 必须由你执行 S2-B（采购 ESP32-C3+SHT30 等、种植、目视、采收），agent 仅写固件/落盘/分析。
- **结论：在 G4 解决前不可投。这是唯一需要外部人力的部分。**

---

## 5. 立即执行清单（达到 SoftwareX 投稿线）

| 优先级 | 动作 | 交付物 | 验收 |
|---|---|---|---|
| P0 | 修 G1 统计纪律 | `benchmarks/.../stat_report.py` 改输出多划分 mean±std | `std(pass_rate)>0` 或报告明确标注「确定性回归测试，非精度估计」 |
| P0 | 跑 G2 交叉验证 | `scripts/run_wofost_crossval.py` 新脚本 | `stat_summary.json` 含 `rmse/mae/ccc` 与 WOFOST 对比 35 组 |
| P1 | 并入 G3 | `run_bench.py` 扫描 `cases/neg/` | 主 Bench 负例数 >0，CI 全绿 |
| P1 | 填 G5 剩余 2 DOI | 更新 `attach_golden_references.py` 登记表后重跑 | 7/7 DOI 非空 |
| P2 | 写 S3 论文稿 | `docs/paper_draft.md` + 图表脚本 | Related Work 覆盖 32 篇；Limitations 写 3 条 |

---

## 6. 诚实声明（论文 Limitations 必须包含）

1. `koppen_grid.json` 为启发式投影（非 Beck et al. 1km 真实栅格）—— provenance 已自述。
2. WOFOST 参数表仅覆盖 152 份配方中的 7 作物——已在 `uncovered_crop` 负例体现。
3. `execution_log` 当前 88 条全部为 `shadow`（仿真闭环），无真实硬件执行记录。

> 这三条主动披露是**增信项**，不是污点——审稿人更信任如实写清边界的工作。

---

*本报告与 `SCI_WRITABILITY_2026-10-18.md`（评估「差什么」）、`SCI_ROADMAP_2026-10-18.md`（规划「怎么补」）构成完整闭环。本次核查确认：项目已从 4.9 推进到 ≈6.8，且 SoftwareX 路径的剩余缺口（G1/G2/G3）全部可由 agent 自主在 2-3 周内补齐。*
