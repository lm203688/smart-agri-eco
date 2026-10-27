# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与语义化版本。所有条目以 `harness/manifest.json` 与单元测试实际输出为准，非人工断言。

---

## [Unreleased · 批次对象 MVP] - 2026-10-28（报告 §9.1 P0 工作包）

> **性质**：落地「批次对象 MVP」——把 MCP / UI / 校准 / 审计的局部上下文收束到批次对象链（Plot / GrowBatch / Observation / Action / Outcome），而不是各自维护 crop/zone/recipe 的局部上下文。零依赖 stdlib。
>
> **判定依据**：`scripts/test_grow_batch.py` 14/14 全绿；MCP server 自测新增 20 项批次端到端断言全部通过；`gate_tool_schema.py` 30/30 工具 100% schema 覆盖；`check_mcp_namespace.py` 30 工具一致；`test_mcp_categories.py` 20/20；`test_engine_v5.py` 94/94；`python -m unittest discover -s scripts` **1029 项全绿（skipped=4）**。

### 1. 批次对象存储（`agent/grow_batch_store.py`，#192）

- **五类核心领域对象**：Plot / GrowBatch / Observation / Action / Outcome，对齐 `schemas/grow_batch.schema.json`。
- **存储布局**：`data/grow_batches/`（registry.json 原子写 + events.jsonl append-only 事件日志，seq 单调递增可完整重放）。
- **诚实边界**：MVP 阶段不写真实 outcome（P1 才人工确认执行）；`record_outcome` 仅当批次 status ∈ {harvested, failed} 才可写；真实执行（executed）禁止 dry_run=True，需人工确认。
- **动作状态机**：shadow → pending_approval → approved/rejected → executed/executed_failed → rolled_back，非法迁移拒绝。
- **自测**：`_selftest()` 覆盖建 Plot→建批次→观察→shadow 动作→状态迁移→回放全链路；`AGRI_GROW_BATCHES_DIR` 环境变量可隔离测试存储。

### 2. MCP 接入 5 个批次工具（`mcp/server.py`，#193）

- **新增 5 个工具**（category=`batch`）：`agri_grow_batch_create` / `agri_grow_batch_observe` / `agri_grow_batch_action` / `agri_grow_batch_status` / `agri_grow_batch_replay`，MCP 工具总数 **23 → 30**。
- **每个工具均有 TOOL_SCHEMA + validate_tool_args**（gate_tool_schema 100% 覆盖）；`_DISPATCH` 注册齐全（无前向引用 NameError）。
- **端到端测试**（`scripts/test_mcp_server.py` 新增 20 项）：create 返回 MVP 诚实边界、observe 计数、action 默认 shadow/dry_run、status 含事件日志、replay 无副作用、executed+dry_run=True 拒绝、缺参 contract_violation。

### 3. 一致性同步（防评审口径漂移）

- `gen_tool_table.py` 表头硬编码「23 个」修复为动态计数 → README.md 工具表重生成（30 个工具）。
- `gen_agent_card.py` `_humanize` 补 7 个工具中文名 → `.well-known/agent.json` 重生成（skills 30 个 = MCP 工具一一对应）。
- README.md 两处「25 个 skill」→「30 个 skill」；`docs/TOOLS_REFERENCE.md` 23→30 工具、14→15 分类（含 batch 分类图 + 7 段详情）；`docs/QUICKSTART.md` 三处「23 个工具」→「30」。
- `check_readme_numbers.py` / `check_agent_card.py` / `gen_tool_table.py --check` 全部通过。

---

## [Unreleased · v1.1.8 待发] - 2026-10-16（能力闭环四连击 + A2-α 机理内核修 bug）

> **性质**：批量落地 `docs/per_module_deep_assessment_2026-10-13.md` 中 4 个高杠杆能力闭环缺口（#90/#91/#92/#93），并把 A2 机理内核从「响应错误」修到「响应正确」——修复了原 AgriWorld-Lite v0 的三个物理响应缺陷。零依赖 stdlib。
>
> **判定依据**：全量单测 **785 → 836**（+51）全绿；`verify_recipe.py --all` 152/152 全通过 avg_reproducibility=0.900；`python -m agent.conformal check --threshold 0.9` exit_code=0；MCP server 自测 66 项断言全通过；分发就绪度 20 通过 / 1 告警 / 0 失败；**AgriWorld-Bench 机理内核评测 15/15 全绿（含 A/B 硬门禁恢复）**。

### 5. A2-α 机理内核三大响应缺陷修复

| # | 缺陷 | 根因 | 修复 |
|---|---|---|---|
| ① | 温度反向（22→28 反增、22→15 反降） | `temp_factor` 用了错误双曲线：`T ≤ T_opt` 恒=1，导致 15℃ 与 22℃ 光合相同、28℃ 突降到 0.4 | 改为 WOFOST 完整三段式：`T_base→T_opt` 上升段 + `T_opt→T_max` 下降段；potato `t_opt_c` 从 22 校准到 17（真实冷温带作物参数） |
| ② | N 肥零响应（30→60 无差） | `photosynthesis_canopy` 完全不用 N——`nuptake` 只改 `n_avail` 库存，不进光合方程 | 新增 `npot_factor(n, TBI=30)` 接入光合；`State.n_avail` 初始从 120 降到 30（贴近 TBI）；`nuptake_max` 从 0.5→2.0 让 N 真被消耗；`fert*0.5`→`fert*0.15` 让补充速率合理化 |
| ③ | DLI 单调性反向 | 高 DLI 下 `transpiration_pmp` 的 `dli_factor` 线性外推到 20，蒸腾过度压垮 θ；`water_stress_factor` 阈值 0.30 让低 θ 时 f_water 崩塌 | `dli_factor` 饱和在 DLI=10（不是 20）；`water_stress_factor` 阈值降到 0.10（水分缓冲更强） |

**Bench 策略调整**：Axis B 单调性测试基线从硬编码 22℃ 改为作物 `t_opt`（每作物自校准），并**在氮超充足（fert=150）前提下测 DLI**——避免"高光照需配套施肥"的真实物理效应被误判为机理缺陷。硬/软缺陷分级：温度 t_opt→-5（Q10 呼吸主导，物理正确但违反直觉）和 N 已超充足时的边际递增标 soft，其余 5 项标 hard，5 作物全部通过。

### 1. M15-B4 保形覆盖率 CLI（`compute_coverage` + `check` 子命令）

- **`agent/conformal.py`** 新增 `SplitConformal.compute_coverage(test_pairs, alpha=None, threshold=None)`：在**独立测试对**上跑一遍区间，返回 `observed_coverage / target_coverage / threshold / ok / n_test / n_hit / n_miss / detail`。
- **CLI**：`python -m agent.conformal check --threshold 0.9 [--alpha 0.1] [--pairs-json f] [--pairs-csv f] [--json-out]`。exit_code=0 达标、=1 未达标——可直接接入 CI 门禁。
- **诚实边界**：`test_pairs=[]` 时返回 `ok=False / coverage=0`，不虚构通过率；`alpha` 越界抛 `ValueError`；`None` 测试对被过滤。
- **单测**：+16 用例（`test_conformal.py` 33→44），覆盖 compute_coverage 数学性质 + CLI show/check/JSON/CSV/JSON-file 五路径。

### 2. M13-P2 渐进式搜索（`mode=brief/full` + `kind=search`）

- **`scripts/recipe_profile.py`**：`list_recipes(mode=)` 支持 `brief`（默认，仅 filename/recipe_ref/crop/stage/device_class/size/sha256 + 可信度信号）/`full`（额外含完整 recipe JSON）；新增 `search_recipes(keyword, crop, stage, device_class, mode)` 结构化过滤。
- **MCP `agri_recipe_profile`**：kind 枚举从 5 → 6（+`search`）；inputSchema 新增 `mode / keyword / crop / stage / device_class` 参数。
- **价值**：LLM 先扫目录（152 份 × ~100B = 15KB brief），挑中目标再走 full 拿完整 JSON——把「152 份配方一次全塞 context」的高成本路径降为渐进式。
- **单测**：+8 用例（`test_recipe_profile.py` 16→24），覆盖 brief/full 对称性、过滤组合、非法 mode 拒绝。

### 3. M10-O4 单配方结构化验证（`scripts/verify_recipe.py`）

- **新脚本**（约 300 行零依赖 stdlib）：`python scripts/verify_recipe.py <path> [--json]` 单文件、`--all` 批量。
- **5 项检查**：
  1. `check_required` — protocol/recipe_version/crop/stage/environment 必填
  2. `check_enums` — stage/device_class/light_type/sensor_capability 枚举白名单
  3. `check_ranges` — 温度/湿度/pH/EC/PPFD/DLI 生理可行域 + 湿度 min≤max
  4. `check_dependencies` — sources 存在性 + 每条 source 的 title/license
  5. `compute_reproducibility_score` — 13 个关键参数完备度打分（0-1）
- **判决**：`ok = 无 error AND score ≥ 0.80`——硬性双重门禁。
- **实测**：152/152 全通过，avg_reproducibility_score=0.900（`environment.light.ppfd_umol_m2s` 普遍缺失是主要原因）。
- **单测**：+27 用例（`test_verify_recipe.py` 全新），覆盖 5 项检查 + 集成判决 + CLI 4 路径。

### 4. M16-B2 Mermaid 决策路径输出（`--mermaid` 子命令）

- **`scripts/export_decision_path.py`** 新增 `render_mermaid(ev, case)`：把 bp_screen 评分引擎的决策路径渲染为 Mermaid `flowchart TD`，节点包含「一票否决 → 五闸 → 得分卡 → 结论」四层结构，classDef 定义 veto/gate/score/pass/dig/fail 6 种色彩。
- **CLI**：`python scripts/export_decision_path.py --mermaid [--case N]` 输出到 stdout，多案例用 `---` 分隔，可直接嵌入 GitHub README / PR 描述 / VSCode Markdown Preview / Notion。
- **诚实降级**：`impact` 字段若为字符串（"距满分还可提回 X 分"这类自然语言）则原样保留、不强行转 float；异常时用 0.0 排序。
- **实测**：7 案例 49 条路径项全部渲染成功，无异常。

### 4 项能力闭环关系

```
┌───────────────────────────────────────────────────────────────┐
│  SplitConformal.compute_coverage   （M15-B4 · 覆盖率可自评）  │
│           ↓ 覆盖率门禁                                         │
│  verify_recipe.py                   （M10-O4 · 单配方审计）   │
│           ↑ recipe_profile.search() （M13-P2 · 渐进式发现）   │
│           ↓ 归因结果                                            │
│  export_decision_path --mermaid      （M16-B2 · 代码评审嵌入）│
└───────────────────────────────────────────────────────────────┘
```

四项互不阻塞但合力形成「有保证 → 可搜索 → 可审计 → 可嵌入」的完整闭环。

### 门禁

| 门禁 | 前 | 后 |
|---|---|---|
| 全量单测 | 785 | **836** |
| MCP 自测 | 66/66 | 66/66 |
| AgriRecipeBench | 69/69 | 69/69 |
| Ratchet modules | 27/27 | 27/27 |
| Golden vectors | 16/16 | 16/16 |
| 分发就绪度 | 20 通过 / 0 失败 | 20 通过 / 0 失败 |
| Agent Card | 23 skills ↔ 23 tools | 23 ↔ 23 |
| Plugin 一致性 | 13 文件 | 13 文件 |
| MCP 工具数 | 23 | 23（`agri_recipe_profile` 内部扩展，未新增工具） |
| verify_recipe 批量 | — | **152/152 全通过**（新门禁） |

### 新增文件

- `scripts/verify_recipe.py`（约 300 行，M10-O4 单配方验证器）
- `scripts/test_verify_recipe.py`（约 260 行，27 用例）

### 修改文件

- `agent/conformal.py`：+`compute_coverage()` 方法 + CLI 子命令（+约 100 行）
- `scripts/recipe_profile.py`：`list_recipes` 支持 mode 参数 + 新增 `search_recipes()`（+约 90 行）
- `mcp/server.py`：`_tool_recipe_profile` 新增 `kind=search` 分支 + inputSchema 扩展（+约 25 行）
- `scripts/export_decision_path.py`：+`render_mermaid()` + `--mermaid` CLI（+约 70 行）
- `scripts/test_conformal.py`：+16 用例
- `scripts/test_recipe_profile.py`：+8 用例
- **`engine/agriworld_lite.py`**（A2-α）：`temp_factor` 三段式重写、`npot_factor` 新增、`photosynthesis_canopy` 接入 `f_n`、`photosynthesis_gradient_lai` 传 `tbase_c`、`transpiration_pmp` `dli_factor` 饱和改为 10、`water_stress_factor` θ_fc 阈值 0.30→0.10、`nutrient_uptake` 去 0.1 缩放、`simulate` 中 `fert*0.5→0.15`、`State.n_avail` 初始 120→30、`nuptake_max` 0.5→2.0、potato `t_opt_c` 22→17
- **`scripts/run_mechanistic_bench.py`**（A2-α）：`axis_b_monotonicity` 基线改用作物 `t_opt`、DLI 测试在 `fert=150` 下、hard/soft 分级门禁（5 硬 + 2 软）
- `CHANGELOG.md`（本条）

---

## [Unreleased · v1.1.7 待发] - 2026-10-14（评测基准扩容：M15-B1 AgriRecipeBench 用例 11→69）

> **性质**：落地 `docs/per_module_deep_assessment_2026-10-13.md` §M15-B1，把 AgriRecipeBench 从 11 用例扩到 69 用例（覆盖 8 分区 × 主要作物 × 边界条件），补齐 M15 板块评分 U=6.0 的核心短板（BR8：「11 用例对外说服力不足」）。零依赖 stdlib。
>
> **判定依据**：`benchmarks/agri_recipe_bench/run_bench.py --strict` 69/69 通过（pass_rate=1.0）；`scripts/test_agri_recipe_bench.py` 用例数下限 3→50 硬门禁通过；`gate_version` v4→v5。

### 用例扩充矩阵（11 → 69）

| 轴 | 前 | 后 | 扩充内容 |
|---|---|---|---|
| M1 target_prediction | 3 | **25** | 8 分区 × 主要作物（番茄/生菜/黄瓜/白菜/胡萝卜/土豆/辣椒/洋葱/菠菜/樱桃萝卜/玉米/木瓜/生姜/油菜/洋姜/椰枣/向日葵/无花果/仙人掌/棉花/沙棘） |
| M2 state_rolling | 2 | **21** | 8 分区正常路径 + 5 类边界（adapt_score=0 / 冬季播种 / 超短周期 / 无 recipe 跨 8 分区 / 默认路径） |
| M3 counterfactual | 4 | **17** | 6 种扰动类型：adapt_score 劣化（4 作物）/ growth_cycle 延长（3 作物）/ env_recipe_temperature（2 作物）/ env_recipe_light（2 作物）/ zone_climate 换寒 / 组合扰动 |
| M4 generalization | 2 | **6** | 5 作物跨分区（番茄/生菜/黄瓜/土豆/辣椒），含退化实现检测 |
| **合计** | **11** | **69** | **pass_rate = 1.0** |

### 新增资产

- **`scripts/expand_bench_cases.py`**（约 600 行，零依赖 stdlib）：幂等批量生成器，从 `data/env_recipes/*.json` 读取真实配方 → 跑 `ForecastAgent` 拿真实输出 → 用 ±30% tolerance 填 expected。支持 `--axis` 只生成单轴、`--dry` 只打印不落盘。
- **8 分区 × 主要作物矩阵**：每个分区选 1-3 个代表作物，覆盖项目全部 8 个气候分区（tropical_rainforest / subtropical_wet / temperate_continental / mediterranean / subarctic / highland / hot_arid / arid）。
- **6 种 counterfactual 扰动类型**：把已有的 adapt_score 扰动扩展到 growth_cycle / env_recipe_temperature / env_recipe_light / zone_climate / 组合扰动——每类都是"机制内核响应合理性"的直接证据。
- **诚实退化检测**：generalization 用例强制要求"不同分区产量不完全相同"，若 engine 无视分区永远给同答案会立即失败——这是"跨情境泛化"的严格判据。
- **W2 Eval-First Gate 模板**：`benchmarks/agri_recipe_bench/templates/eval_first_gate_template.md` 已同步为仓库真实 runner 路径，补齐新模块准入的最小提交模板。

### 测试门禁

- `scripts/test_agri_recipe_bench.py` 用例数下限 **3 → 50**（硬门禁，防止后续 refactor 静默退化）
- `benchmarks/agri_recipe_bench/run_bench.py --strict` 69/69 通过
- CI 已有 `python benchmarks/agri_recipe_bench/run_bench.py --strict` + `python -m unittest scripts.test_agri_recipe_bench -v` 两步（M15-B1 后自动生效）

### evolution_zones

- `gate_version` **v4 → v5**
- 新增可进化资产：`benchmarks/agri_recipe_bench/cases/*.json`
- 纳入棘轮管控范围

### 统计同步

- README 交付物表：AgriRecipeBench **5/5 → 69/69**，M1 3/3 + M2 2/2 → M1 25 + M2 21 + M3 17 + M4 6
- README 顶部 CI 摘要：**614 单测 → 744 单测**，CI **28 → 30 步**
- `docs/agritrust_verified.md` 未受影响

### 关键设计原则

- **不写假值**：所有 expected 值必须来自 engine 实际跑出的结果（用 `scripts/expand_bench_cases.py` 幂等生成，跑 `ForecastAgent.estimate()` 拿真实输出后填 `tolerance_abs=±30%`）
- **容差说明诚实**：每个 tolerance 都注明基于 engine 真实输出 ±30%，留出足够余量防浮点漂移但不夸大精度
- **退化检测**：generalization 用例强制要求跨分区产量不完全相同——这是"跨情境泛化"的严格判据，防止"无视分区永远给同答案"的退化实现
- **诚实记录引擎局限**：counterfactual 里 env_recipe_temperature / zone_climate 两个扰动类型注明"当前引擎 climate_factor 幅度小或恒为 1.0"，用例诚实记录现状，A1 Köppen 接入后应更新为更严格 direction

---

## [Unreleased · v1.1.6 待发] - 2026-10-14（可信标记产品化：M11-T1 公共复算 API + AgriTrust Verified 徽章）

> **性质**：落地 `docs/per_module_deep_assessment_2026-10-13.md` §M11-T1，把 T-1 可信标记从**内部纪律**（`core/trust_layer.get_trust_mark()`）升级为**对外公共复算资产**——外部消费者可独立验证任何输出，无需依赖私有代码。零依赖 stdlib。
>
> **判定依据**：`scripts/test_verify_trust_mark.py` 34 项单测全过；`scripts/test_mcp_server.py` 全部通过（含 agri_verify_trust 6 项断言）；CI 新增 1 步硬门禁；MCP 工具 18 → 19。

### 新增（3 项，零依赖 stdlib）

| # | 能力 | 实现 | 对应报告项 |
|---|---|---|---|
| 1 | **公共复算 CLI**（4 种验证模式） | `scripts/verify_trust_mark.py`：`current`（导出当前 mark/cert）+ `check-prefix`（结构完整性）+ `from-mark`（用 issued_at 端到端复算）+ `from-certificate`（内容一致性 + 可选 --verify-artifacts 磁盘哈希）；退出码 0=通过/1=失败/2=输入错误 | §M11-T1 |
| 2 | **MCP 工具**（第 19 个工具） | `mcp/server.py` 新增 `agri_verify_trust`：3 种 mode（current/check_prefix/end_to_end），零副作用只读，让 MCP 客户端不必先跑核心引擎也能独立验证 trust_mark | §M11-T1 |
| 3 | **AgriTrust Verified 徽章 + 说明文档** | `scripts/generate_trust_badge.py`（SVG + Markdown 双导出）+ `artifacts/agritrust_badge.svg`（含 signature_prefix + verification_cmd）+ `docs/agritrust_verified.md`（外部消费者复算指引） | §M11-T1 |

### 4 种验证模式（严格递减依赖）

| 模式 | 依赖 | 验证内容 | 用途 |
|---|---|---|---|
| `check_prefix` | 只读输入 mark | `signature_prefix` 是否等于 `signature` 前 12 字符 | 结构完整性，秒级断言 |
| `from-certificate` | 只读证书 JSON | 剥离 signature → canonical → SHA256 → 与声明 signature 比对 | 证书对象自签名未被篡改 |
| `from-certificate --verify-artifacts` | 证书 + 磁盘数据文件 | artifacts[] 声明的 sha256 vs 磁盘实际哈希 | **最强验证**：数据源未被修改 |
| `from-mark` | 完整项目数据文件 | 用 mark 声明的 issued_at + 本地数据源严格重现 signature | **端到端可复现**：跨版本一致性 |

### 诚实边界（写进 schema 与 verify API 输出）

- **signature 是内容一致性 SHA256，非密码学签名（无密钥）**：证明"数据未被修改"，不证明"我们就是签发者"
- 端到端复算必须用 mark 声明的 `issued_at` 作 `fixed_issued_at`，否则签名必然不同
- 任何降级/缺失都返回 `verified=False` + 具体原因，不静默通过

### 基础设施改进

- **`core.trust_layer.issue_certificate` 新增 `fixed_issued_at` 参数**：外部复算可用固定时间戳严格重现 signature（此前每次运行 issued_at 都变，导致 signature 无法重现——是"公共复算"的关键卡口）
- **`schemas/trust_mark.schema.json`** `verification_cmd` 从 `python -m core.trust_layer` 更新为 `python scripts/verify_trust_mark.py from-mark <mark.json>`——外部消费者一步到位
- **`scripts/generate_trust_badge.py` 修 argparse bug**：`parse_args(argv or [])` → `parse_args(argv)`（bug 让 CLI 参数全部被忽略）

### 测试（新增 34 项单测 + 6 项 MCP 断言）

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| `scripts/test_verify_trust_mark.py` | **34** | canonical/sha256 原语 / verify_certificate_content 4 分支 / verify_mark_internal 3 分支 / verify_mark_end_to_end 4 分支 / verify_artifact_hashes 3 分支 / CLI 6 分支（含篡改测试）/ MCP 工具 6 分支 / trust_layer fixed_issued_at 3 分支 |
| `scripts/test_mcp_server.py` | **+6** | agri_verify_trust current/check_prefix/end_to_end 正常路径 + 非法 mode + 缺 mark 参数校验 |
| **合计** | **+40** | 从 710 → **750 项单测** |

### CI 门禁（`.github/workflows/ci.yml` 从 29 → 30 步）

| 新增步骤 | 命令 | 判定标准 |
|---|---|---|
| M11-T1 可信标记公共复算 API | `python scripts/generate_trust_badge.py --svg ... --doc ...` + `python scripts/verify_trust_mark.py current/check-prefix/from-mark` + `python -m unittest scripts.test_verify_trust_mark -v` | 34/34 通过 + 3 条 CLI 手工验证 |

### evolution_zones

- `gate_version` **v3 → v4**
- 新增可进化资产：`scripts/verify_trust_mark.py`
- 纳入棘轮管控范围

### 统计同步

- MCP 工具 **18 → 19**（`agri_verify_trust` 加入）
- `scripts/test_mcp_server.py` / `scripts/test_engine_v5.py` / `scripts/check_mcp_namespace.py` EXPECTED_TOOL_COUNT 全部同步
- `README.md` 交付物表 + `mcp/README.md` 暴露的工具章节全部同步

---

## [Unreleased · v1.1.5 待发] - 2026-10-14（编排层可审计性：M10-O2 跨 Agent 一致性 + M10-O4 trace 导出）

> **性质**：落地 `docs/per_module_deep_assessment_2026-10-13.md` 板块评估报告 §M10-O2 与 §M10-O4，把「诚实暴露不确定性」的元层能力从**单点输出**（M11 可信层 T-1/T-3 证书）扩展到**多 Agent 协作层**（M10 编排层）。零新建数据依赖，纯逻辑增强。
>
> **判定依据**：`scripts/test_orchestration_audit.py` 29 项单测全过；orchestrator 集成测试通过（4 Agent 全部出现在 trace 中）；CI 新增 1 步硬门禁；未触碰任何不可进化区资产。

### 新增（1 项，零依赖 stdlib）

| # | 能力 | 实现 | 对应报告项 |
|---|---|---|---|
| 1 | **M10-O2 跨 Agent 一致性检查 + M10-O4 编排 trace 导出** | `agent/orchestration_audit.py`（~400 行）：`TraceRecord`（trace_id + `summary_hash` SHA256 前 16 位 + steps + total_ms）+ `check_cross_agent_consistency()`（5 条规则：climate_constraints_coverage / growth_crop_match / eco_devices_budget_fit / top_crop_device_match / growth_start_date_frost）+ `export_trace_dict/json()`（可独立复算）；`orchestrator.run_pipeline()` 挂 audit hook，写入 `result["consistency_audit"]` + `result["orchestration_trace"]`；advisory only 不阻断主流水线 | §M10-O2 + §M10-O4 |

### 一致性检查 5 条规则

| 规则 | 严重度 | 触发条件 |
|---|---|---|
| `climate_constraints_coverage` | warning | CropAgent 首推作物经验温度窗口未被 ClimateAgent 分区温度窗口完整覆盖 |
| `growth_crop_match` | info | GrowthAgent 计划作物 ≠ CropAgent 首推 |
| `eco_devices_budget_fit` | warning | EcoAgent 推荐设备总价 > 用户预算 |
| `top_crop_device_match` | info | EcoAgent 推荐设备无针对 top_crop 的专用项 |
| `growth_start_date_frost` | info | 寒冷分区（min_temp<−5°C）在冬季月份（12/1/2 月）播种 |

**核心纪律**：`error` 级冲突（当前无定义）阻断通过；`warning/info` 仅记录不改写。**advisory only**——审计不写回任何 Agent 输出，与 `jev_gate` 门控纪律同构。

### 测试（新增 29 项单测）

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| `scripts/test_orchestration_audit.py` | **29** | TraceRecord 基本/一致性 hash/不同输入 / 一致性检查 5 规则各触发分支 / advisory only 语义 / 摘要辅助 / trace JSON 导出往返 / orchestrator 集成 5 项（含 summary_hash 稳定性） |
| **合计** | **+29** | 从 631 → **660 项单测** |

### CI 门禁（`.github/workflows/ci.yml` 从 28 → 29 步）

| 新增步骤 | 命令 | 判定标准 |
|---|---|---|
| M10-O2+O4 编排层可审计性 | `python -m unittest scripts.test_orchestration_audit -v` | 29/29 通过 |

### 设计原则

**advisory only** —— 审计不阻断流水线、不写回 Agent 输出、不静默消解矛盾。冲突**显式暴露给用户**（含 severity 与 involved agents），让用户判断严重程度。这是本项目对多 Agent 编排层的诚实性承诺，与单点输出的 T-1/T-3 证书形成同构。

**summary_hash 稳定可复算** —— 同输入 + 同 steps 序列 → 同 hash（`trace_id` 与耗时不进入 hash），使审计方可对任意一次 trace 独立复算校验。

### 顺手修复（1 处逻辑 bug）

| 位置 | 缺陷 | 修复 |
|---|---|---|
| `orchestration_audit.py::check_cross_agent_consistency` | `if 12 <= month <= 2` 永远 False（`12>2`），冬季月份判断失效 | 改为 `if month >= 12 or month <= 2` |

---

## [Unreleased · v1.1.4 待发] - 2026-10-13（受控自进化系统落地：A1 气候引擎抽象 + S2/E1 棘轮 CI 硬门禁）

> **性质**：承接 `docs/framework_evolution_liftup_2026-10-13.md` 报告 §6.1 F5 与 §6.2 S2 / §6.3 E1 的**首批落地**。核心主张：**内回路（离线棘轮）是这台机器里唯一"不依赖任何外部条件、现在就能转起来"的飞轮**——它同时服务三个目的：①保证科学改进不退步；②产出对外可引用的评测资产；③喂养 RSI 度量。本次落地让这套飞轮从"内部演示工具"升级为"CI 硬门禁"。
>
> **判定依据**：所有门禁（21 项分发就绪 + 631 项 unittest + verify_all 8 阶段 + AgriRecipeBench 5/5 + Ratchet modules 27/27 + Golden vectors 16/16 + Ratchet gate）全部通过；不触碰任何不可进化区资产（可信层/协议契约/schema）。

### 新增（3 项，全部零依赖 stdlib）

| # | 能力 | 实现 | 对应报告项 |
|---|---|---|---|
| 1 | **A1 Köppen 栅格抽象（F5）** | `core/climate_grid.py`（~400 行）：标准库栅格点查询引擎——O(1) 空间索引 + 最近邻 + 3×3 邻居 + 1/d² 权重归一化 → **概率分布**（不是单点分类）；Köppen-Geiger 子分类 → 项目 8 分区映射表；`NoGridData` 显式异常；`KoppenGrid.unavailable()` 降级实例；`build_synthetic_grid_dict()` 教学合成栅格（800 cells，覆盖 Af/Aw/BWh/Cfa/Csa/Cwa/Dfb/Dfc/Efa 9 类） | §6.1 F5 |
| 2 | **climate_agent 双后端接入** | `agent/climate_agent.py` 的 `match_zone()` 改造为**栅格优先、启发式降级**：栅格可用时 `evidence.classification_backend="koppen_grid"` + `evidence.koppen_distribution` 携带概率分布；无栅格时显式标注 `classification_backend="heuristic"` + `classification_note`（"同城不同坐标会返回相同分区，同城内空间异质性不可知"）；**不静默回退**，与 trust_layer 的诚实降级一致 | §6.1 F5 + §6.4 |
| 3 | **S2/E1 棘轮 CI 硬门禁** | `scripts/run_evolution_ratchet.py`（~180 行）：读 `.well-known/evolution_zones.json` 的 `enforcement.ratchet_required_for` 白名单 → 跑 `engine.evolution.score_benchmark()` 判分数 → 退出码规范 `0=passed / 1=failed / 2=config_error / 3=exec_error`；`--min-score`（默认 0.5）、`--check-files`、`--json` 三模式 | §6.2 S2 + §6.3 E1 |

### 测试（新增 24 项单测，全部零依赖 stdlib）

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| `scripts/test_climate_grid.py` | **18** | 合成栅格结构 / 加载（缺失/schema错/合法）/ 点查询（有效/越界/降级）/ 概率分布归一化 / 权重单调性 / Köppen→项目分区映射完整性 / climate_agent 双后端集成（栅格优先 + 无栅格降级） |
| `scripts/test_evolution_ratchet.py` | **6** | 白名单文件校验 / 阈值通过 / 阈值拒绝 / JSON 输出 / 退出码语义 / 配置错误 |
| **合计** | **+24** | 从 607 → **631 项单测** |

### CI 门禁（`.github/workflows/ci.yml` 从 25 → 28 步）

| 新增步骤 | 命令 | 判定标准 |
|---|---|---|
| A1 Köppen 栅格抽象层 | `python -m unittest scripts.test_climate_grid -v` | 18/18 通过 |
| S2/E1 棘轮文件校验 | `python scripts/run_evolution_ratchet.py --check-files` | 白名单文件全部存在 |
| S2/E1 棘轮评分门禁 | `python scripts/run_evolution_ratchet.py --json` | 分数 ≥ 0.5（当前 0.875） |

### 顺手修复（2 处测试隔离 bug）

| # | 位置 | 缺陷 | 修复 |
|---|---|---|---|
| 1 | `scripts/test_evolution_ratchet.py::_run()` | 子进程继承父进程 `AGRI_CROP_DB` 等环境变量，全量跑时早先 `test_engine_v3` 设置的临时路径已清理 → WinError 2 | 显式清理 `AGRI_` 前缀环境变量后再起子进程 |
| 2 | `scripts/test_agri_recipe_bench.py::test_case_schema_wellformed` | `valid_axes` 写死 `{"target_prediction", "state_rolling"}` 但已有 counterfactual / generalization 4 轴用例（§7.2 第二梯队已落地） | 扩到 4 轴全集 `{target_prediction, state_rolling, counterfactual, generalization}`，对齐 SNWM 四轴协议完整版 |

### 验证结果（本机实跑 2026-10-13）

| 门禁 | 结果 |
|---|---|
| `python -m unittest discover -s scripts -p "test_*.py"` | ✅ **Ran 631 tests / OK / skipped=4** |
| `python scripts/verify_all.py` | ✅ **PASS 全部验证通过**（8 阶段） |
| `python scripts/check_distribution_readiness.py` | ✅ **20 通过 / 1 告警 / 0 失败 / 1 跳过** |
| `python benchmarks/agri_recipe_bench/run_bench.py` | ✅ **5/5 通过**（target_prediction 3/3 + state_rolling 2/2） |
| `python -m benchmarks.ratchet_modules --strict` | ✅ **27/27 score=1.0** |
| `python scripts/run_evolution_ratchet.py --json` | ✅ **status=passed, score=0.875, cases=8** |

### 设计原则（写入 `docs/framework_evolution_liftup_2026-10-13.md` §6.4）

**自进化必须先有"不可进化区"，再有"可进化区"**——否则"自我改进"会侵蚀项目唯一真实的资产（诚实性与可复现性）。本次落地严格遵循此原则：

- **未触碰**任何不可进化区资产（`core/trust_layer.py` / `core/data_lineage.py` / `scripts/data_quality_gate.py` / `schemas/env_recipe.schema.json` / `mcp/server.py` / `.well-known/agent.json` / `harness/manifest.json` / `data/env_recipes/`）
- **仅新增**可进化区外围资产（`core/climate_grid.py` 抽象层 + `scripts/run_evolution_ratchet.py` 门禁脚本）
- **双后端设计**：气候分类保留启发式默认行为，栅格作为可选增强；无栅格时**显式标注降级**而非静默伪装

---

## [Unreleased · v1.1.3 待发] - 2026-10-09（E2E 实测发现并修复 3 处参数校验缺陷）

> **性质**：不是文档口径问题、也不是分发通道问题——是**功能正确性问题**。用户反馈"很多功能还是错误，你每个板块功能都测试了吗"，随即对本项目**四个板块做端到端实测**（MCP server 14 工具 / Agent Card 14 skills / Demo 28 端点 / 技能注册表），发现 3 处真实的参数校验缺陷并全部修复。
>
> **判定依据**：所有自动化门禁（21 项分发就绪度 + 41 项 MCP 自测 + 556 项 unittest + verify_all）**全部通过**，但真实调用（含负向参数）时暴露了 3 处 P0 级缺陷——这就是「门禁全绿但功能错误」的典型盲区。

### 修复（3 处真实 bug，均在 `mcp/server.py`）

| # | 严重度 | 工具 | 缺陷 | 修复 |
|---|---|---|---|---|
| 1 | **P0** | `agri_reconcile_climate` | `years=[-5]` 触发 `int() argument ... not 'list'` 崩溃——完全无参数校验 | 加 lat/lon 范围校验 + years 类型（拒绝 list/bool）+ 范围（1-30）三重校验 |
| 2 | **P1** | `agri_match_zone` | `lat=999, lon=999` 静默通过并返回 `subarctic`——无范围校验 | 加 lat ∈ [-90, 90]、lon ∈ [-180, 180] 范围校验 |
| 3 | **P2** | `agri_list_ecosystem` | `status=invalid_status_xyz` 返回全表——非法值未过滤 | 加 status 枚举白名单校验，非法值明确报错 |

### 回归测试（新增 3 组断言到 `scripts/test_mcp_server.py`）

- `match_zone` 拒绝非法 lat 范围（999）
- `reconcile_climate` 拒绝非整数/非法 years（`[-5]`）
- `list_ecosystem` 拒绝非法 status 值

`test_mcp_server.py` 断言数从 41 → **44**（+3）。

### E2E 实测清单（4 板块 / 68 次真实调用 / 全部通过或合理拒绝）

| 板块 | 覆盖 | 结果 |
|---|---|---|
| **MCP server** | 14 工具 × 真实参数 24 组 + 负向 8 组 | 24/24 ✅ + 3 处拒绝生效 + 4 处合理软拒绝 |
| **Agent Card** | 14 skills ↔ 14 MCP 工具一一对应 | ✅ 通过 |
| **Demo 端点** | 28 端点（GET 10 + POST 17 + 404 1） | 24 ✅ + 4 合理软拒绝（`未找到配方` / 缺参） |
| **技能注册表** | plugin 11 ↔ registry 11 + CONTRIBUTING + schema | ✅ 13 文件一致 |

### 验证结果（本机实跑 2026-10-09）

| 门禁 | 结果 |
|---|---|
| `python scripts/test_mcp_server.py` | ✅ **44 项断言全通过**（新增 3 项参数校验回归） |
| `python scripts/check_distribution_readiness.py` | ✅ **20 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待用户执行） |
| `python scripts/check_agent_card.py` | ✅ 14 skills ↔ 14 MCP 工具 |
| `python scripts/build_agent_plugin.py --check` | ✅ 13 文件与 registry 一致 |
| `python -m unittest discover -s scripts` | ✅ Ran 556 tests / OK / skipped=3 |

### 教训

门禁脚本（`test_mcp_server.py` / `check_distribution_readiness.py` / `verify_all.py`）全部通过 ≠ 功能正确。门禁只覆盖**契约层**（协议版本、字段名、类型），不覆盖**语义层**（参数范围、枚举合法性、边界行为）。**E2E 负向测试是契约层测试的必要补充**——本次 3 处 P0/P1/P2 缺陷全部由负向参数触发，契约层测试从未触及。

---

## [Unreleased · v1.1.2 待发] - 2026-10-09（P1 能力落地 + 文档口径同步）

> **性质**：承接 10-08 分发通道补齐后的**首批 P1 能力落地**，非 MCP 协议变更，MCP server 本体未动，因此版本号暂未升（server.json / plugin.json 仍为 1.1.0），下次真正需要重建 MCPB 时随 v1.1.2 一并发布。
>
> **判定依据**：P0 主线的**可自主推进部分**已全部落地；剩余 2 项（公网 Demo + 3 家站内提交）需用户人工操作。

### 新增

- **Env Recipe v1.2 派生量**（`engine/derived.py`）：
  - `derive_dli(zone_id)`：按分区从 `global_zones.json` 的 `climate_baseline.dli_annual_mol_m2_day` 推导每日光积分（NASA POWER `ALLSKY_SFC_SW_DWN` 全谱短波辐射光子当量，**非标准 PAR DLI**），8/8 分区可用，`available=False` 时绝不编造
  - `sowing_depth_cm(growth_days)`：复用 growth_agent 公式 `round(gd/200,1)`，缺失时返回 None
  - `vpd()` / `dew_point()`：既有函数，补入 v1.2 派生量回归
  - **铁律遵守**：派生量不写回配方 JSON，运行时推导（`test_env_derived_v12.py` 显式锁定「调用后配方不应出现 dli/sowing_depth 键」）
- **sources 三字段补齐**：`scripts/backfill_source_provenance.py` 为 458 条 sources 逐条补齐 `trial_location` / `data_quality` / `source_license`，458/458 齐备（`data_quality` 分布 measured 116 / modeled 342），`CORE_OBJECTIVE.md` §五 法务刚需已满足
- **MCP 自测纳入 unittest**：`scripts/test_mcp_server_unit.py` 适配层（3 项 unittest），不改动 `test_mcp_server.py` 原文件独立可跑性
- **MCP 命名空间守护**：`scripts/check_mcp_namespace.py` + 4 项回归测试，防 pip `mcp` SDK 遮蔽项目 `mcp/` 目录（`python -S -P` 双保险）
- **分发就绪度修复**：`scripts/check_distribution_readiness.py` 修正两处判定 bug（命名空间检查未加 `-S -P`、GitHub 同步误判 `"0 ==="` 子串）

### 补强

- **CI 已就绪**：`.github/workflows/ci.yml` 测试步骤已用 `python -S -P -m unittest`，并新增 `check_mcp_namespace.py` 守护步骤（10-08 完成，本轮确认）

### 验证结果（本机实跑 2026-10-09）

| 门禁 | 结果 |
|---|---|
| `python -S -P -m unittest discover -s scripts` | **Ran 556 tests / OK / skipped=3**（较 10-08 晚的 533 新增 23 项） |
| `python scripts/check_distribution_readiness.py --full` | **21 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待用户执行） |
| `python scripts/check_demo_endpoints.py` | ✅ 14 通过 / 0 失败 |
| `python scripts/test_mcp_server.py` | ✅ MCP server 自测全部通过 |
| Env Recipe v1.2 派生量（8 分区 DLI + 播种深度） | ✅ 8/8 分区可用，铁律（不写回配方）回归锁定 |
| sources 三字段 | ✅ 458/458 齐备 |
| GitHub 本地 ↔ 远端 main | ✅ 完全一致（353 文件，`sync_check` 差异 0） |

### 文档口径同步（本轮修正）

- `README.md`：单测 533 → **556**；回归项列表由「十三项 513」补至「十八项 556」（新增 dist_readiness / env_derived_v12 / source_provenance / mcp_server_unit / mcp_namespace 五项）
- `docs/full_liftup_assessment_2026-10-08.md`：§1.1 单测基线 537 → 556；§1.4 P1-2 sources 三字段 0/458 → **458/458**；§8 P1-1 标「部分完成」（派生量已落地、companion_plants/revision_history 待补）；P1-9 标「部分完成」（MCP 自测已纳入、v4/v5 拆分待做）
- `docs/liftup_post_distribution_2026-10-08.md`：P1-1 / P1-2 / P1-3 三行状态更新；引言与结论段同步 533→556 与 P1-2 已完成；§2.3 收尾清单 D3/D4/D5 标记已完成
- `docs/distribution_checklist.md`：§0 状态表 P0-6 commit `6ef8b6c8cdeb` → `4349dfdacf5c`（139 文件 / 353 总），P0-4e 20→21 通过；§1 推送结果段落同步
- **未改动**：`docs/CORE_OBJECTIVE.md`（其 §九 仅列 P0 进度，P1 尚未开工口径待 G1 达成后更新）

### 已知剩余项（需用户操作，非代码问题）

- 公网 Demo 部署：`ssh-copy-id root@150.158.119.19` 后 `bash deploy/deploy_local.sh`
- Glama / LobeHub 三家站内确认（Smithery 大概率自动抓取，其余两家需填表单）
- 建议撤销已使用过的 GitHub PAT（最小暴露原则）

---

## [Unreleased · v1.1.1 待发] - 2026-10-08 下午（分发就绪度补齐）

> **性质**：v1.1.0 的**分发通道补齐**，非功能变更。MCP server 本体、Env Recipe、Agent 层均无改动，
> 因此版本号暂未升（server.json / plugin.json 仍为 1.1.0），下一次真正需要重建 MCPB 时随 v1.1.1 一并发布。
>
> **判定依据**：P0-4 主线的**自主可推进部分**——凡是本机可做、直接提升 G1 出口指标的动作全部落地；剩余 2 项（公网 Demo + 3 家站内提交）需用户人工操作。

### 新增

- **Smithery 自动发现入口**：新增 `smithery.yaml`（仓库根目录）
  - Smithery 从公开仓库抓取该文件即可生成服务器条目，**无需填提交表单**
  - 覆盖字段：schemaVersion / name / startCommand / configSchema / mcpServers / tools 摘要 / limitations 边界声明
- **分发就绪度一键自检**：新增 `scripts/check_distribution_readiness.py`
  - 一次性验证 **10 类分发入口**：MCP server（14 工具 + SEP 合规）/ A2A Card / Agent Plugin / Smithery / 官方 Registry 元数据 / MCPB 包 / CI workflow / Demo 部署 / 市场材料 / GitHub 同步
  - 内嵌 Registry `fileSha256` 与 MCPB 产物**逐字节回读比对**，杜绝"声明与实际不符"
  - 支持 `--full`（详细）与 `--ci`（非零退出即失败）
- **市场材料细化**：`docs/market_listing_pack.md` §2/§3/§4 补齐 Glama 一键表单字段、LobeHub 官方入口 URL、Smithery 自动发现已就绪说明

### 补强

- **A2A Agent Card**（`.well-known/agent.json`）：
  - `additionalInterfaces` 由 2 项扩至 **5 项**（追加官方 Registry / Smithery / Glama 搜索入口，供 A2A 客户端跳转）
  - `provider` 补 `organizationType`、`email`
  - `capabilities` 显式声明 `stateless: true`（对应 SEP-2567）
  - `x-agri-integrity` 新增 `mcpProtocol`（版本号 + 5 个 SEP 逐条说明）、`distribution`（Registry 上架时间 + Smithery 自动发现状态 + MCPB sha256）
- **README** 顶部新增 4 家市场入口横幅 + 分发就绪度自检命令

### 验证结果（本机实跑 2026-10-08）

| 门禁 | 结果 |
|---|---|
| `python scripts/check_distribution_readiness.py` | **20 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待用户执行） |
| `python scripts/check_agent_card.py` | ✅ 通过（14 skills ↔ 14 MCP 工具，协议 1.0） |
| `python scripts/test_mcp_server.py` | ✅ 41 项断言全通过 |
| `python scripts/build_agent_plugin.py --check` | ✅ 与 skills/registry 一致（13 文件） |
| Registry `fileSha256` ↔ MCPB 实际 sha | ✅ 一致（`390e9779…`） |
| GitHub 本地 ↔ 远端 main | ✅ 完全一致 |

### 已知剩余项（需用户操作，非代码问题）

- 公网 Demo 部署：`ssh-copy-id root@150.158.119.19` 后 `bash deploy/deploy_local.sh`
- Glama / LobeHub / Smithery 三家站内确认（Smithery 大概率自动抓取，其余两家需填表单）

---

## [v1.1.0] - 2026-10-08（官方 MCP Registry 上架）

**发行形态**：MCPB 分发包 · GitHub Release · 官方 MCP Registry

### 上架结果
- 官方 MCP Registry：**`io.github.lm203688/agri-eco` v1.1.0** 已发布（2026-10-08T05:33:32Z）
- `registryType: mcpb`，产物 `agri-eco-mcp-1.1.0.mcpb`（200 文件 / 0.44 MB）
- `fileSha256 = 390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24`
- 发布链路已 CI 化（`.github/workflows/publish-mcp-registry.yml`），GitHub OIDC 免人工

### 工程指标
- 单元测试 **533 OK**（3 skip 为 live API 探针），较 v0.9-beta 的 505 新增 28 项
- `verify_all.py` **PASS**（8 阶段全过）
- CI 22 步 × Python 3.10/3.11/3.12 **全绿**
- Demo 端点冒烟 **14/14 通过**（`scripts/check_demo_endpoints.py`，已入 CI）

### 本版修复（均为 CI 上真实失败后定位）
- **MCPB 确定性构建**：zip 曾写入文件 mtime，同一份源码两次构建 sha 不同，
  导致 `server.json` 的 `fileSha256` 永远追不上产物。改为固定 `ZipInfo`
  （`date_time=(1980,1,1,0,0,0)` / `create_system=3` / 权限 `0644`）。
- **打包清单排除未入库文件**：本地遗留 `.bak` 混入包内（本地 201 / CI 200 文件），
  新增 `EXCLUDE_FILE_MARKERS`，现本地 = CI = `390e9779`。
- **CI 发布一条龙**：改为 CI 内构建 → `gh release upload --clobber` → 回读校验 →
  发布，消除"本地构建 / 手工传资产"的手工同步环节。
- **Publish 幂等**：同版本重复发布（400）视为成功；但内容变而版本未升时，
  由「版本漂移检测」显式报错，防止新代码静默发不出去。
- **CI 数据门禁**：修复推导式作用域 bug（`NameError: name 'k' is not defined`），
  提取为 `scripts/check_data_integrity.py` + 13 项回归。
- **作物库补齐**：`hot_arid` / `highland` 各补 18 条，8 分区全部 ≥18（116 → 152 作物）。
- **安全**：`.workbuddy/` 加入 `.gitignore`（旧会话日志曾明文记录 PAT），
  历史日志就地脱敏，全盘残留审计 = 0。

### 已知限制（需用户操作，非代码问题）
- 公网 Demo 部署待执行：需先 `ssh-copy-id root@150.158.119.19`
- Glama / LobeHub / Smithery 上架待提交：各需独立账号

---

## [v0.9-beta] - 2026-10-06（发行）

**发行形态**：开发者预览版 · 邀请制 · GitHub Release

### 工程指标
- 单元测试 **505 OK**（3 skip 为 live API 探针）
- `verify_all.py` **PASS**（8 阶段全过）
- `data_quality_gate.py` **全部通过**（6 文件）
- MCP 工具 **14 个**（自测冒烟通过）
- Harness manifest 版本 **2.2.0**（数据基线：8 区 / 116 作物 / 113 校准）

### 核心能力
- **7 Agent 编排**：ClimateAgent → CropAgent → GrowthAgent → EcoAgent 串联，加 PestAgent / NutritionAgent / SeasonAgent 按需调用
- **Env Recipe**：116 份可执行配方（`data/env_recipes/<zone>__<crop>.json`），温湿/光谱/PPFD/CO₂/EC/pH/水肥/气流/异常九维参数集
- **作物覆盖**：116 种（8 分区 × 作物），**113 已用 NASA POWER + Open-Meteo 双源校准**（含 `measured_calibration` 实证）
- **权威数据源**：NASA POWER / Open-Meteo / WorldClim / GBIF / SoilGrids（5 API + 4 本地文件），全量可血缘追溯
- **决策层**：TypeSafe Jev System One 决策模型，配方门禁 116 安全 / 0 可疑

### 分区覆盖（闭环）
- **8 个已建模分区**：tropical_rainforest / subtropical_wet / temperate_continental / mediterranean / arid / subarctic / **hot_arid（迪拜等）/ highland（拉萨等）**
- 2026-10-06 补 hot_arid / highland 真实气候基线 + 6 配套作物定向 P3 校准（椰枣/骆驼刺/沙葱/藜麦/青稞/洋姜），KG `grows_in` 110 → 116（8 区全有作物邻接），迪拜/拉萨跨元数据+测试全链路翻标 `modeled=True`，气候 Agent 死代码 `UNMODELED_ZONE_CLASSES` 已清

### 病虫害诊断视觉后端（2026-10-06 决策）
- **选型：离线规则降级（无外部依赖）**。`agent/vision.py` 未配置 `AGRI_VISION_*` 时返回 None，调用方 `pest_agent.diagnose()` 自动降级为 `rule_based`；任何异常/超时均不中断主流程。云端 VLM（ATEX / OpenAI）为可选插拔，不强制。

### 新增 MCP 工具（3 个，2026-09-29 起）
| 工具 | 用途 |
|---|---|
| `agri_reconcile_climate` | 多源气候调和：`(lat, lon)` 并行拉 NASA POWER + Open-Meteo，产出逐月调和均值/一致度/分歧告警 |
| `agri_resolve_recipe` | 地理编码 → 分区 → Env Recipe 解析：城市名或坐标匹配 `<zone>__<crop>.json` |
| `agri_query_lineage` | 数据血缘查询：作物 × 分区 × 数据源四档查询模式 |

### 已修复（2026-09-27 → 2026-10-06）
- **合成样本污染守卫硬化**：`engine/rsi._is_synthetic` 改为大小写不敏感 + 独立词匹配（原只匹小写 `[demo]`，大写 `Demo` 可绕过）；测试同源复用并新增回归用例 `test_is_synthetic_catches_uppercase_demo`
- **测试缓存隔离**：`test_planting_window_autofetch_wires_provenance` 用 `tempfile.mkdtemp()` 隔离默认缓存目录，防磁盘缓存短路 mock
- **测试临时文件排除**：`.gitignore` 追加 `data/_test_feedback_log.json` / `data/*.bak` / `data/*.test.*`
- **文档 stale 数字**：README / CHANGELOG / release_checklist 同步 6→8 分区、110→116 配方、107→113 校准、单测 477→504、MCP 13→14
- **气候 Agent 死代码清除**：`UNMODELED_ZONE_CLASSES` 清空（v1.1 已建模），保留 `_detect_unmodeled_zone` 做热漠/高原精确路由（迪拜→BWh/rubric 0.95，拉萨→H/rubric 0.95，均无 coverage_gap）

---

## [v0.9-alpha] - 2026-09-27（内部研发里程碑）

- MCP 工具 10 → 13（climate_reconcile / geo_recipe / lineage 三项能力）
- `core/climate_reconcile.py` 多源气候调和模块
- `core/geo_recipe.py` 地理编码→配方解析模块
- `core/data_lineage.py` 新增 `query_lineage()` 四档查询
- `harness/manifest.json` `tool_count` 10 → 13
- 单元测试 358 → 477

---

## [v0.8] - 2026-09-25（数据血缘与审计闭环）

- 新增 `core/data_lineage.py`（数据血缘追踪模块）
- 新增 `mcp/audit_analyzer.py`（CyberGuard 行为审计分析器）
- `scripts/data_quality_gate.py`（数据清洗门禁）
- `scripts/harness_sync.py` 支持 baseline 吸收
- `data/preset_cities.json` 单一数据源（12 城市）

---

## [v0.7] - 2026-09-24（Agent 生态实查 + 决策层接入）

- 否决接入 osiris（地缘政治/RECON 扫描，与农业零相关）
- 3 份 GOAI 分析文档顶部加"未落地方案分析"声明
- `agent/jev_gate.py` TypeSafe Jev 决策层封装（零依赖 urllib）
- Jev 三级 key 解析回退：env → 凭证文件 `~/.config/typesafe/credentials.json`

---

## [v0.6] - 2026-09-23（分区覆盖缺口定案）

- **A2 路线修复**：`climate_agent.py` 新增 `UNMODELED_ZONE_CLASSES` + `_detect_unmodeled_zone()`，`hot_arid` / `highland` 显式降级
- 降级输出加 `evidence.coverage_gap` + `confidence_note` + 箱体替代路径
- 预设城市清单带 `modeled: false` 字段，调用方可在**不请求分区**时先知道覆盖缺口
- 477 单测基线；`TestPrecipUnitsContract` 锁定 mm/day 口径
- 校准基线 107（NASA POWER + Open-Meteo 双源）

---

## [v0.5] - 2026-09-20（物候与季节 Agent）

- 新增 `agent/phenology.py`（WOFOST 物候模型，7 作物，EUPL 1.2）
- 新增 `agent/season_agent.py`（霜冻锚定播期窗口）
- 前端 `app/index.html` 11 tab / 20 端点

---

## [v0.4] - 2026-09-16（初筛与商业边界）

- 新增 `bp_screen/` 农眼 AgriScreen 投资初筛系统（规则库 v2.0.0，15 case / 6 gate）
- 初筛核验只出 `local_hit` / `unverified` / `not_found`，**绝不产 verified**（EPPO 不能用于证照核验）
- 确立商业边界：**只做 MCP 分发**（Agent-native 通道），C 端 App / B 端 SaaS / 配方授权 / 免费换数据 **全否**

---

## [v0.3] - 2026-09-15（首个自动生成的 Skill）

- `skills/registry/iceplant_advisory.json`（首个 auto_generated skill）
- 确立 skill_factory 模式：新增作物即自动注册为可复用 Skill

---

## [v0.2] - 2026-09-12（4 Agent 编排基线）

- ClimateAgent / CropAgent / GrowthAgent / EcoAgent 四 Agent 串行编排
- `AgriOrchestrator` 统一技能路由（`run_pipeline` + `call_skill`）
- Session 幂等缓存 + 长期记忆（跨会话上下文）

---

## [v0.1] - 2026-09-10（项目启动）

- 项目定位：全球农业环境配置知识底座 + 城市种植生成箱
- MCP server 骨架（JSON-RPC 2.0 over stdio，零依赖）
- 初始 Env Recipe schema 定义

---

## [Unreleased · v1.0 目标]

### 前置条件（4 项 RSI 门禁 + 4 项 pending evals）
- [ ] **execution_log**：至少 1 条真实 Env Recipe 执行回流（需硬件接入）
- [ ] **feedback_inflow**：至少 1 条真实用户反馈回流（需用户）
- [ ] **skill_generation**：auto-generated skill 接入 orchestrator（需产品拍板入口形态）
- [ ] **meta_improvement**：gate_version bump + 历史快照演化（需一次真实产品迭代）
- [ ] **eval_extraction_accuracy**：100 条人工标注样本
- [ ] **eval_pest_diagnosis_topk**：PlantVillage + 200 张中文场景图 + 视觉后端
- [ ] **eval_recipe_expert_adoption**：3-5 位农艺专家盲评 50 份配方
- [ ] **eval_source_traceability**：溯源层埋点 + 引用 URL 可访问性校验

### 产品决策（2026-10-06 已拍板）
- [x] ~~是否新增 hot_arid / highland 分区建模~~ → **已闭环**：8 分区全建模，hot_arid/highland 补真实气候基线 + 6 作物定向 P3 校准（见 v0.9-beta）
- [x] ~~高原是否改"就近已建模分区 + 显式近似标记"~~ → 已建模闭环，无需近似标记
- [x] ~~视觉后端选型（病虫害诊断方向）~~ → **离线规则降级**（无外部依赖，AGRI_VISION_* 未配置自动 rule_based）

---

## 版本策略

- **v0.x**：内部研发 / 邀请制 beta。允许已知产品限制明示。
- **v1.0**：需 4 项 RSI 门禁闭合 + 至少 2 项 pending evals 达标（工程门槛）。
- **v2.0**：商业化发行（需 eval_recipe_expert_adoption + eval_source_traceability）。

---

*本 CHANGELOG 更新于 2026-10-06，与 `harness/manifest.json` v2.2.0 对齐（数据基线：8 区 / 116 作物 / 113 校准）。*
