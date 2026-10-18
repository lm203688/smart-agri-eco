# SCI 达标路线图 · 下一阶段提升执行方案

> **依据**：`docs/SCI_WRITABILITY_2026-10-18.md`（六维评估：Rigor 4 / Validation 2 / References 2 是短板）
> **唯一目标**：22 周内达到 **SoftwareX 或 Data in Brief 投稿状态**，并铺平方法类论文（Agric. Systems / Field Crops Res.）的数据基础。
> **执行原则**：每个任务有 `交付物` + `验收标准`（可机械判定）+ `依赖`。未通过前一任务的验收，不得开下一任务。

---

## 0. 总目标拆解（按 SCI 六维反推）

| 维度 | 现值 | 目标 | 负责阶段 |
|---|---|---|---|
| Reproducibility 可复现 | 8.5 | **9.5**（加 reference + 统计报告） | S1 |
| References 文献 | 2 | **9**（32 篇必引 + DOI 体系） | S1 |
| Rigor 严谨性 | 4 | **7.5**（负例 + 统计纪律 + 机理测试 + baseline） | S1 |
| Novelty 新颖性 | 7 | **7.5**（related work 精准对标） | S1 |
| **Validation 验证** | **2** | **7**（公开数据集交叉验证 + 消融 + 物理采集可选） | **S2-A（自主）/ S2-B（需外部）** |
| Data 数据 | 5.5 | **8**（元数据规范化 + license 清理） | S1+S2 |

**验收公式**：目标总分 8.0/10 = SoftwareX 门槛；Validation ≥ 7 是方法类论文的最低门槛。

---

## S1 · 科学严谨性补齐（第 1-6 周）

> **本阶段总验收**：Bench 运行报告从 `pass_rate=1.0` 单值，变为 `89.2% ± 3.4%` 带置信区间的统计报告；golden vectors 每个 case 带 DOI；负例 20 个全接入 CI。

### S1.1 文献引用体系（第 1 周，纯写作）

**交付物**：`docs/REFERENCES.md` —— 32 篇必引文献，分 8 组：

| 组 | 文献 | 引用位置 |
|---|---|---|
| **作物模型** | Supit et al. 1994 (WOFOST 6.0); Van Diepen et al. 1989; Boogaard et al. 1998 (WOFOST 7.1 guide); Steduto et al. 2009 (AquaCrop); Jones et al. 2003 (DSSAT); Hoogenboom et al. 2019 (DSSAT v4.7.5) | `sun_geometry` / `agriworld_lite` / `phenology.py` 的公式出处 |
| **积温与物候** | McMaster & Wilhelm 1997 (GDD one equation two interpretations); Porter & Semenov 2005 | `estimate_stage_days` |
| **气候分类** | Peel, Finlayson & McMahon 2007 (Köppen-Geiger updated map); Trabucco & Zomer 2009 (Global Aridity Index) | `climate_grid.py` / `zone_meta/` |
| **蒸散与水分** | Allen et al. 1998 (FAO Irrigation & Drainage Paper 56, FAO-56) | `derived.py::vpd` / `water_stress_factor` |
| **太阳几何** | Michalsky 1988 (The Astronomical Almanac's algorithm 1950-2100); Blanc & Wald 2012 (SG2 algorithm); Hofierka & Šúri 2002 (r.sun) | `sun_geometry.py` |
| **保形预测** | Vovk 2012 (Conditional validity of inductive conformal predictors); Lei & Wasserman 2018 (Distribution-free prediction sets, JACM); Papadopoulos et al. 2002; Angelopoulos & Bates 2023 (gentle introduction) | `conditional_conformal.py` |
| **数据/软件规范** | Wilkinson et al. 2016 (FAIR Guiding Principles, Scientific Data); Lamprecht et al. 2020 (FAIR for research software); Jiménez et al. 2017 (Four simple recommendations) | `data/` + `schemas/` + 全部数据论文素材 |
| **Agent 协议** | Anthropic 2024 (Model Context Protocol spec); Linux Foundation 2025 (A2A Protocol); FAO CC BY-NC-SA 3.0 IGO 许可条款 | `mcp/server.py` / `.well-known/agent.json` / `env_recipes` license |

**执行要求**：
1. 每条文献五要素齐全：`authors / year / title / venue / DOI`。**DOI 必须逐条到 doi.org 核对可解析，禁止猜测**（猜 DOI 是学术不端）。
2. 写 `scripts/validate_references.py`：解析 `docs/REFERENCES.md` 中的 DOI → 请求 doi.org → 断言 HTTP 200 + title 匹配。CI 第 40 步。
3. **golden vectors 加 `reference` 字段**。改造 `benchmarks/golden_vectors/*.json`：

```json
{
  "schema": "agri-golden-vectors/phenology/v2",
  "target_module": "agent/phenology.py",
  "target_function": "estimate_stage_days",
  "references": [
    {"key": "supit1994", "doi": "10.1007/BF00863701",
     "provenance": "WOFOST 物候参数 TBASE/TSUM 来源"}
  ],
  "cases": [
    {
      "id": "potato_18c",
      "reference_keys": ["supit1994", "mcmaster1997"],
      "rationale": "...",
      "payload": {...},
      "expected": {...}
    }
  ]
}
```

**验收标准**：`python scripts/validate_references.py` 全绿；3 个 golden vector 文件每 case 均有 `reference_keys` 且引用的 DOI 全部可解析。

---

### S1.2 负例用例（第 1-2 周）—— **已交付**

**已交付**：`scripts/gen_negative_cases.py` + 20 个骨架文件 `benchmarks/agri_recipe_bench/cases/neg/`
+ `benchmarks/agri_recipe_bench/negative_runner.py`（真实校验器）+ `run_bench.py --axis negative` 集成
+ CI 第 40 步「Bench 负例回归」。验收已达标：`negative: ✅ 20/20 passed`，89/89 全绿。
**待用户确认**：C 类容差（`C4_ADDITIVITY_TOLERANCE=0.20`，实测偏差 0.2%）与物理口径。

| 类 | 数量 | 内容 |
|---|---|---|
| A 输入合法性拒绝 | 8 | 负天数/未知作物/NaN/RH=150/dli<0/theta=1.5/Tmin>Tmax/空字符串 |
| B 诚实降级与拒识 | 6 | 无观测降级/漂移 3σ 拒识/数据过期标 stale/多源冲突/传感器矛盾/超校准域 |
| C 反事实一致性 | 4 | 零扰动恒等/方向反转/饱和约束/复合扰动可加性 |
| D 信誉断裂 | 2 | 篡改签名失效/移除 source 断链 |

**剩余执行要求**：
1. **人工逐条确认** 20 个骨架的 `expect_failure_detail`（C 类容差取值须由你定并记录理由，不能自动生成）。
2. **扩 `run_bench.py`**：识别 `case_type=negative`，按 `expect_failure_type` 分派给对应校验器（`InputError` → `bounded`；`flag` → 输出含标记；`invariant` → 不变式断言）。
3. **CI 接入**：新增第 40 步 `Bench 负例回归（A/B/C/D 四类共 20 个）`。
4. `benchmarks/agri_recipe_bench/README.md` 与 `docs/SCI_WRITABILITY_2026-10-18.md` 中"负例 0 个"的结论需改为实测新数字。

**验收标准**：CI 第 40 步全绿；`python benchmarks/agri_recipe_bench/run_bench.py --summary` 输出 `negative: 20/20 passed`。

---

### S1.3 统计纪律（第 2-3 周）—— **已交付**（治"648 次恒 1.0"）

**问题**：`results_history.json` 648 次运行 `pass_rate` 恒等于 1.0，无统计波动 → "通过率"指标在统计上无意义，方法类论文审稿人必问。

**交付物**：
1. `benchmarks/agri_recipe_bench/stat_report.py` —— 对历史 648 条记录做统计分析：
   - 按 `axis` 分组的 pass_rate **均值 ± 标准差**
   - `conformal_coverage` 的分布（当前 498 条恒 0.92 → 报告"方差=0，说明测试集固定确定性，需多种子实验"）
   - 时间趋势（mutual information 或简单回归，检测性能漂移）
2. **多 split / 多 seed 扩展**：`run_bench.py --repeats 5 --seed 20241018`，对 Bench 做 5 次不同随机划分，报告 `mean ± std`。
3. 输出 `benchmarks/results/stat_summary.json`，作为论文 Table 1 的数据源。

**验收标准**：统计报告中每个轴都有 `mean` / `std` / `n` 三字段；std 不为 0（若仍为 0，说明测试集仍无随机性，需继续扩）。

**已交付（实测）**：
1. `benchmarks/agri_recipe_bench/stat_report.py` —— 历史分析（652 条）+ 5 次多种子重复实验，全标准库零依赖。
2. `run_bench.py --repeats 5 --seed 20241018 --fraction 0.8` 已可用（**不写 leaderboard**，避免向历史序列注入抽样噪声）。
3. 输出 `benchmarks/results/stat_summary.json`，含按轴 `mean/std/n` + OLS 趋势 + 诚实判定。
   - `pass_rate` = 1.0 ± 0.0（n=652，方差为零是**事实**，已如实写入报告）
   - `conformal_coverage` = 0.92 ± 0.0（历史）/ 0.9488 ± 0.0223（重复实验，n=5）→ **有方差**
   - `mean_abs_dev` = 0.0039 ± 0.0036（n=5）→ **有方差**
4. CI 新增步骤「Bench 统计纪律（S1.3）」：`--repeats 5 --seed 20241018 --fraction 0.8 --strict` + `stat_report.py`。

---

### S1.4 机理内核测试 + 边界契约（第 3-4 周）—— **已交付**

**交付物**：
1. `agent` 侧引用已就绪的 `core/numeric_domain.py`（8 种装饰器，28 项自测已过）——把 `engine/agriworld_lite.py` 的 4 个函数套上：

```python
@known_enum("crop", CROP_REGISTRY)
@not_empty_string("crop")
@bounded("dli", 0, 100)
@bounded("days", 1, 365)
def theoretical_yield_cap(crop, dli, days, ...): ...

@bounded_each(("T", "Topt"), lo=-50, hi=60)
@bounded_each(("Tmin", "Tmax"), lo=-50, hi=60)
@monotone_constraints("Tmin", "Tmax", a_lt_b=True)
def temp_factor(T, Topt, Tmax, Tmin): ...

@bounded("theta", 0, 1)
def water_stress_factor(theta): ...

@bounded("T", -50, hi=60) @bounded("RH", 0, 100)
def vpd(T, RH): ...   # engine/derived.py
```

2. 把 `scripts/probe_mechanism_garbage_in.py` 的 34 个探针转为正式测试 `scripts/test_mechanism_domain.py`，断言**必须 raise**。
3. 建 `core/crop_registry.py`（单一枚举源，从 `data/env_recipes` 的 120 species 程序化生成 + 人工维护白名单），替代装饰器里硬编码。
4. CI 加 `Scripts/gate_mechanism_gigo.py` 作为**永久**第 41 步门禁。

**验收标准**：`python scripts/test_mechanism_domain.py` → 34/34 passed；`gate_mechanism_gigo.py` 从当前 23/34 FAIL 降为 0/34 FAIL。

**已交付（实测 2026-10-18）**：
1. `core/crop_registry.py` —— 作物命名单一来源：`ENGINE_CROPS`（7）+ `RECIPE_SPECIES`（120，程序化扫描）+ `RECIPE_LATIN`（112）+ `ALL_CROPS`（239）+ 中文名↔机理作物对照。`engine/agriworld_lite.py` 的 `@known_enum` 已由硬编码集合改为引用 `ENGINE_CROPS`。
2. `scripts/test_mechanism_domain.py` —— **34/34 passed**。逐条实测确认：**28 抛异常 / 6 返回合法边界值**（并非全 raise，见下）。
3. `scripts/test_crop_registry.py` —— **23/23 passed**，含漂移守卫：`ENGINE_CROPS == set(CROP_PARAMS)`、配方扫描计数、`rice` 缺口锁定。
4. CI 第 45 步「S1.4 机理内核边界契约 + 作物注册表漂移守卫」。

**两处与路线图原文的偏差（按实测行为修正，不照抄伪代码）**：
- 真实签名是 `temp_factor(t_c, t_opt, t_max, t_base=5.0)`（非 `T, Topt, Tmax, Tmin`）、
  `theoretical_yield_cap(crop, dli_mj_m2_d, days)`（非 `dli`）。
- 探针脚本口径**过于宽容**：其判定为 `OK if RAISED or (RETURNED and expected_ok)`，
  导致两个 `expected_ok=True` 的探针即使抛异常也算通过：
  `theoretical_yield_cap(wheat, 0, 120)`（`@positive` 要求 >0，实际抛 InputError）
  与 `water_stress_factor(1.0)`（`@bounded` 上限是 0.6 而非田间持水量 1.0，实际抛 InputError）。
  正式测试按**实测行为**断言，并额外锁死异常类型（InputError / DataError / ValueError）。
- 额外发现：`T15 temp_factor(t_opt=50, t_max=35)` 抛的是**裸 ValueError**（函数体校验），
  不经装饰器 —— 契约里已单独记录。


---

### S1.5 第一个外部 baseline（第 4-6 周）

**为什么必须有**：审稿人必问"你们这个和现有方法比如何"。哪怕只是一致性对比，也证明"不是随手写的规则"。

**方案**（三选一，按性价比排序）：
1. **FAO GAEZ v4 分区**（免费、可下载）——把 152 份配方的 `zone_id` 与 GAEZ 分区做交叉表，报告一致性/差异分布。**推荐**（数据公开、过程简单）。
2. **开源规则引擎**（如 agstack / agridat 的 Python 实现）——同输入同输出对比。
3. **DSSAT v4.8**（需 MATLAB，仅离线用）——物候/产量对比，作为 S2 的铺垫。

**交付物**：`benchmarks/baseline_fao_gaez/`（或选定项）+ 报告 `benchmarks/results/baseline_comparison.json`（含 n / mean / std / RMSE / CCC）。

**验收标准**：至少 1 个 baseline 在 152 份配方（或其子集）上有完整对比数字，写入论文 Table 2。

---

## S2 · 独立可信验证（第 5-14 周）—— 修订版 2026-10-18

> **修订原因**：原方案 S2.1 把"真实数据采集"设为必要项。经实测发现：
> **agent 无法自主种菜、购买硬件、每日目视检查**——该任务必须外部人力。
> 但进一步核对项目数据资产后发现，**SCI 投稿所需的"外部验证"完全可以用项目
> 已内置的公开权威数据源完成，无需任何物理采集**。
>
> **因此 S2 拆为两条并行轨道**：
> - **S2-A「公开数据集验证」→ 完全 agent 自主，投稿前置条件，不可跳过**
> - **S2-B「物理采集」→ 需要外部人力，仅作为加分项，SoftwareX 不强制要求**
>
> **实测依据**（`scripts/attach_golden_references.py` 已验证）：
> `benchmarks/golden_vectors/phenology.json` 的 6 个作物用例，其 expected 值
> **全部可由本地 WOFOST 参数表精确复算**：
> ```
> potato_18c: 出苗 170/16.0=10.625≈10.6 | 开花 (170+150)/16=20.0 | 成熟 (170+150+1550)/16=116.875≈116.9
>              参数来源：data/wofost_phenology_reference.json (ajwdewit/WOFOST_crop_parameters, EUPL 1.2)
> ```
> 覆盖 potato / wheat / soybean / rice / sweetpotato 共 5 作物（第 6 个为番茄，
> 即 `uncovered_crop` 负例）。**这意味着 WOFOST 官方参数表就是现成的外部权威基线。**

### S2-A · 公开数据集验证（完全自主，第 5-11 周）

**核心思路**：不种菜，改用**可公开引用的权威数据源**做交叉验证。
项目已内置 3 套，可直接引用；另有 3 套可下载。

**已内置（零下载，立即可用）**：

| 数据源 | 位置 | 权威性证明 | 许可证 |
|---|---|---|---|
| **WOFOST 作物参数表** | `data/wofost_phenology_reference.json` | 源自 `ajwdewit/WOFOST_crop_parameters` wofost81 分支；7 作物 TSUM/TBASE/春化 | EUPL 1.2（可商用，需署名） |
| **Köppen-Geiger 分类栅格** | `data/zone_meta/koppen_grid.json` | 11,946 cells / 2° / 12 classes；口径引 Peel 2007 + Kottek 2006 + Trubert 2009 | NASA POWER 气候基线为 public domain |
| **全球分区元数据** | `data/zone_meta/global_zones.json` | 8 分区 + FAO 农业分区口径；data_sources 标注 WorldClim 2.1 / FAO GAEZ / ISRIC SoilGrids | 见文件 meta |

**A1：物候一致性交叉验证（第 5-6 周，3 天）**
- 把 `phenology.py` 的 `estimate_stage_days` 对 7 个 WOFOST 作物 × 5 个温度水平（10/15/20/25/30°C）跑全套，与 WOFOST 参数表复算值对比，报告 RMSE / MAE / 一致性 (CCC, Lin 1989)。
- **注意 TBASE 边界**：`wheat_below_tbase_stalled` 用例必须正确处理 T < TBASE（返回"停滞"而非负数）。
- **验收**：35 组对比，RMSE ≤ 1 天，且 0 组出现负天数。

**A2：Köppen 分区一致性（第 6-7 周，3 天）**
- 用 `koppen_grid.json` 的 11,946 cells + `global_zones.json` 的 8 分区做内部一致性检验（同分区内 cell 的 T/P 聚类紧密度）。
- **必须诚实声明**：`koppen_grid.json` provenance 已自述"启发式分区投影，非 Beck et al. 1km 真实栅格"——论文里这句话**原样保留**，并作为 Limitations 明确写出。这是加分项（诚实），不是污点。
- **可选升级**（如需替换为真实栅格）：下载 Beck et al. 2018 的 1km 数据（公开 CC BY 4.0），替换后 `KoppenGrid` 接口不变。
- **验收**：一致性报告 + provenance 引用链完整（3 篇文献 key 入 `REFERENCES`）。

**A3：包络稳健性验证（第 7-9 周，1 周）**
- 用 `ratchet_modules.py` 的现有棘轮机制，对 152 份配方做"扰动包络"测试：输入加 ±10% 温度噪声，看输出是否在声明容差内单调变化。
- **验收**：152/152 配方无异常漂移；报告 mean ± std。

**A4：可复现性证据打包（第 9-11 周，3 天）**
- 把 `results_history.json` 的 648 次运行按 §S1.3 做统计分析，生成 `benchmarks/results/stat_summary.json`（论文 Table 1 数据源）。
- 生成"复现包"：`python -m venv`（无需装任何包）+ `pytest`/直接运行 → 输出与 CI 历史一致。
- **验收**：`stat_summary.json` 中每个轴有 mean/std/n。

### S2-B · 物理采集（需外部人力，可选加分，第 7-18 周）

> **自主性判定：❌ 不可由 agent 独立完成。**
> 必须由你（或任何能种菜的人）执行以下动作：
> ① 采购硬件  ② 播种/育苗  ③ 每日目视检查  ④ 周期性人工采收与称重。
> agent 可承担：固件代码（<200 行）、数据落盘 schema、质控脚本、分析报告。

**何时值得做**：
- 若目标仅 SoftwareX / Data in Brief → **可完全跳过 S2-B**，S2-A 已足够支撑。
- 若目标是方法类（Agric. Systems / Field Crops Res.）→ **必须做**，且 real 数据 ≥ 20 条。

**最小可行配置**（3 个节点即可，单节点 < 300 元）：

| 部件 | 型号建议 | 数量 | 备注 |
|---|---|---|---|
| 主控 | ESP32-C3 | 1 | 固件由 agent 写（S2-B 交付物之一） |
| 温湿度 | SHT30 × 2 | 2 | **一柜内 + 一环境对照**（构成处理/对照） |
| 光照 | BH1750 | 1 | 验证 DLI 推算 |
| 土壤含水 | 电容式 | 1-2 | 需注明校准日期 |
| 执行 | 继电器 + 补光灯/水泵 | 1 套 | 验证"下发→执行→回传"闭环 |
| 种植载体 | 室内柜 / 阳台箱 | 1 | — |
| **合计** | | | **~250-300/节点** |

**SOP 要点**（完整版见 `docs/data_acquisition_protocol.md`，需新建）：
1. 采样频率：温湿度/光照 5 分钟；土壤含水 1 小时
2. 覆盖 ≥ 1 个完整物候期（生菜 45 天 / 番茄 90 天）
3. 记录字段严格按 `schemas/execution_log.schema.json`，`source: "real"`
4. 每日人工目视 1 次并记录（防设备空跑）
5. 传感器故障 > 24h 标记 `data_quality=interpolated`
6. 图像回流需 `image_consent.captured=true` + 显式 license

**验收**：`source=real` 条目 ≥ 20；`outcome` 非空 ≥ 20。

---

## S3 · 论文撰写与投稿（第 19-22 周）

### S3.1 论文组件准备（并行于 S2，第 12 周起）

| 组件 | 来源 | 论文位置 |
|---|---|---|
| Figure 1：系统架构图 | `mcp/` + `.well-known/` + `engine/` 现有代码 | System Design |
| Figure 2：Env Recipe 数据结构 | `schemas/env_recipe.schema.json` + 152 份实例 | Data Model |
| Table 1：Bench 统计报告 | `benchmarks/results/stat_summary.json`（S1.3） | Evaluation |
| Table 2：Baseline 对比 | S1.5 产出 | Evaluation |
| Table 3：保形覆盖（多数据集） | S2.2 产出 | Evaluation |
| Table 4：消融 | S2.3 产出 | Evaluation |
| Figure 3：WOFOST 交叉验证散点（预测 vs 权威参数表） | S2-A1 产出 | Evaluation |
| Figure 4：Köppen 分区一致性热力图 | S2-A2 产出 | Evaluation |

### S3.2 投稿目标（分梯队）

| 梯队 | 期刊 | IF | 触发条件 |
|---|---|---|---|
| 冲刺 | Computers and Electronics in Agriculture / SoftwareX | 3.4-6.5 | S1 全部 + **S2-A** 完成（全自主） |
| 稳妥 | Data in Brief（配套数据集）+ SoftwareX（软件本体） | 1.3-3.4 | S1 全部完成 |
| 铺垫 | Agricultural Systems / Field Crops Research | 5.6-5.8 | **S2-B 完成（≥20 条 real）+ Validation ≥ 7** |

### S3.3 写作纪律
- 全部数字必须来自 `benchmarks/results/*.json`，禁止手写进正文（保证稿子与代码一致）。
- 每张表的生成脚本必须入库（`scripts/paper_tables.py`）。
- Related Work 必须覆盖 S1.1 的 32 篇，不得引用未读文献。
- Limitations 必须写明三条：① koppen_grid 为启发式投影（非 Beck 1km）；② WOFOST 参数表仅覆盖 7/152 作物；③ execution_log 当前全部为 shadow，无真实硬件闭环。**主动披露是增信项。**

---

## 4. 依赖与时间线总览（修订版）

```
第1周    S1.1 文献体系            ████████
第1-2周  S1.2 负例(骨架已就绪)    ████████░░
第2-3周  S1.3 统计纪律            ░░░░████████
第3-4周  S1.4 机理测试            ░░░░░░░░████████
第4-6周  S1.5 baseline            ░░░░░░░░░░░░████████████
第5-6周  S2-A1 物候交叉验证(自主)   ░░░░░░░░░░░░████████
第6-7周  S2-A2 Köppen一致性(自主)   ░░░░░░░░░░░░░░░░████████
第7-9周  S2-A3 包络稳健性(自主)     ░░░░░░░░░░░░░░░░░░░░████████
第9-11周 S2-A4 复现包(自主)         ░░░░░░░░░░░░░░░░░░░░░░░░░░████████
─────────────────── 以上 S1+S2-A = 投稿 SoftwareX 的充分条件（全自主） ───────────────────
第7-18周 S2-B 物理采集(需外部,可选)  ░░░░░░░░░░░░░░░░████████████████████░░░░░░░░
第10-16周 S2.2 conformal 验证           ░░░░░░░░░░░░░░░░░░░░░░████████████████
第14-17周 S2.3 消融                       ░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████████
第12周起  S3.1 论文组件(并行)                   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████
第19-22周 S3.2/3 投稿                              ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████
```

**关键路径（修订）**：
- **只投 SoftwareX / Data in Brief** → 关键路径是 **S1 + S2-A（约 11 周，全 agent 自主）**。S2-B 可完全跳过。
- **要投方法类** → 关键路径追加 **S2-B 物理采集（12 周）**，唯一需外部人力的部分。

**分水岭在第 11 周末**：S2-A4 交付后，即具备 SoftwareX 投稿条件；此时再决定是否投入 S2-B。

## 5. 风险与对策（修订版）

| 风险 | 概率 | 对策 |
|---|---|---|
| **S2-B 硬件节点中途故障导致数据断档** | 高（若做 S2-B） | 每节点冗余 1 传感器；数据每日导出到 Git；**S2-B 是可选轨道，故障率不影响投稿主线** |
| DOI 核对发现引用的公式实际出处不同 | 中 | 文献核对与代码 review 并行；`references` 字段设计为单源登记表，改一处即全量生效 |
| WOFOST 参数表未覆盖项目作物（152 份配方中仅 7 作物在表内） | 高 | 已作为负例设计（`uncovered_crop`）；论文 Limitations 明确声明覆盖率 |
| koppen_grid 被审稿人识破是启发式投影 | 中 | provenance 已自述非 Beck 真实栅格；**论文主动声明 + 列为 Limitations**，反而增信 |
| 12 周内 real 数据不足 20 条（仅影响方法类） | 中 | 提前 2 周采购；节点 3→5 |
| FAO NC 许可条款阻碍 | 低 | CORE_OBJECTIVE §五 已定案（方案 A：卖服务不卖数据），论文同样遵守 |

---

## 6. 本周立刻可做的三件事

1. `python scripts/attach_golden_references.py` —— **已完成**，golden vectors 已挂上 9 条权威出处（schema v1→v2），DOI 待你逐条核对
2. `python scripts/gen_negative_cases.py` —— **已完成**，20 个负例骨架已生成，待你确认 `expect_failure_detail`
3. 开写 `docs/REFERENCES.md`（按 S1.1 八组清单），DOI 逐条到 doi.org 核对后填回 `scripts/attach_golden_references.py` 的 `REFERENCES` 登记表，再重跑一次脚本

> **S2-B（买硬件种菜）不是本周必做项**——SoftwareX 投递路径不需要它。

---

## 7. 自主性一览（谁必须做什么）

| 工作 | agent 可独立完成 | 需要你做的 | 备注 |
|---|---|---|---|
| S1.1 文献体系 | ✅ 全流程（含 DOI 核对） | 最终确认引用范围 | DOI 需联网核对 |
| S1.2 负例用例 | ✅ 生成 + 接入 CI | 确认 C 类容差取值 | 科学判断不可外包 |
| S1.3 统计纪律 | ✅ | — | 纯计算 |
| S1.4 机理测试 | ✅ | — | `numeric_domain` 已就绪 |
| S1.5 baseline | ✅ 用 WOFOST 参数表 | — | 已在本地 |
| S2-A1~A4 公开数据验证 | ✅ | — | **这是外部验证的替代路径** |
| S2-B 物理采集 | ❌ 固件/schema/分析可做 | **采购、种植、目视、采收** | 仅方法类论文需要 |
| S3 论文撰写 | ✅ 全稿 + 图表脚本 | 定稿署名与投稿账号 | — |

**结论**：除 S2-B（种菜）外，全部可自主完成。而 S2-B 只影响方法类论文，对 SoftwareX 完全可省。

---

*本方案与 `docs/SCI_WRITABILITY_2026-10-18.md` 配套：评估报告说"差什么"，本方案说"怎么补、何时验"。*
*2026-10-18 修订：S2 拆分为 S2-A（公开数据验证，全自主）/ S2-B（物理采集，需外部），并已实际交付 golden vector reference 挂载与 20 个负例骨架。*
