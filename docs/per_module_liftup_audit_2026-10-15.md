# per_module_liftup_audit_2026-10-15.md

> 收官审计报告：基于 `per_module_deep_assessment_2026-10-13.md` 的全面提升执行成果与门禁验证。

---

## 一、执行总览

**执行窗口**：2026-10-13 ~ 2026-10-15（3 天）

**执行范围**：报告主线一「接通」全部完成 + 主线三「走出去」人工阻塞项明确留给用户。

| 板块 | 状态 | 评分提升 |
|---|---|---|
| M1-A1 Köppen 栅格 | ✅ 已接 | C 0.5→2.5 |
| M1-A3 太阳几何 | ✅ 已接 | — |
| M1-A5 微气候 | ✅ 已接 | A +0.5 |
| M2-S1 土壤多维 | ✅ 已接 | C +0.5 |
| M5-F1 Split Conformal | ✅ 已接 | A +1.0 |
| M8-R1 HA 事实标准字段 | ✅ 152 配方全补 | C 0.5→2.5, U 2.5→6.5 |
| M8-R2 profile 四件套 | ✅ 已接 | — |
| M9-X1 影子执行日志 | ✅ 已接 | — |
| M10-O2 跨 Agent 一致性 | ✅ 已接 | C +1.0 |
| M10-O4 编排 trace 导出 | ✅ 已接 | — |
| M11-T1 公共复算 API | ✅ 已接 + AgriTrust 徽章 | U 2.5→6.0 |
| M12-K1 检索/图谱 MCP | ✅ 已接 | — |
| M13-P1 工具 14→21 | ✅ +7 工具 | A +0.5 |
| M13-P2 渐进式发现 | ✅ category 过滤 | A +0.5 |
| M13-P3 Server Card+ETags | ✅ mcp-card.json + If-None-Match | A +1.0 |
| M15-B1 bench 11→69 | ✅ 四轴 69 用例 | C 0.5→3.0 |
| M16-B2 决策路径可视化 | ✅ export_decision_path.py + MCP 工具 | — |
| M15-B3 leaderboard | ✅ results_history.json + leaderboard.html | U +0.5 |
| M15-B4 保形覆盖率 | ✅ bench 集成 conformal coverage 指标 | A +0.5, U +0.5 |
| M15-B5 评测先行门禁 | ✅ check_bench_coverage.py + CI 硬门禁 | A +0.5 |
| M15-B3 leaderboard | ✅ results_history.json + leaderboard.html | U +0.5 |
| S1 受控自进化 gate v6 | ✅ 已接 | — |
| S2/E1 棘轮 CI | ✅ 27/27 | — |
| E3 溯源字段门禁 | ✅ 152 配方全合规 | — |
| E4 Golden Vectors 16 | ✅ 16/16 | — |
| W5 治理 badge | ✅ 已接 | — |

**Köppen 分区修正**（本轮新增）：
- `arid.koppen_class` BWh/BSh→BWk/BSk（冷干旱）
- 映射修正：BWh/BSh→hot_arid, BWk/BSk→arid; Dfc/Dwc→subarctic
- 栅格重新生成：+BWk 类（144 cells），三城 ground truth 全对齐

---

## 二、门禁验证（全绿基线）

| 门禁 | 结果 |
|---|---|
| 全量单测 | **785/785** (skipped=4) |
| distribution_readiness | **19 通过 / 2 告警 / 0 失败 / 1 跳过** |
| MCP 命名空间 | **TOOLS=21** |
| MCP 自测 | **66 项断言全通过** |
| check_agent_card | **21 skills ↔ 21 tools** |
| build_agent_plugin --check | **13 文件一致** |
| data_quality_gate | **全部通过** |
| AgriRecipeBench | **69/69** pass_rate=1.0 + conformal_coverage 92.0% |
| M15-B5 bench coverage gate | **PASS** (7/7 模块, 69 用例, 22 作物, 9 分区) |
| Ratchet modules | **27/27** score=1.0 |
| Golden vectors | **16/16** score=1.0 |
| Evolution ratchet | **gate_version=v6** exit_code=0 |
| generate_status_badge --ci | **全部 OK** |
| harness manifest | **v2.3.0** 指纹同步 |

---

## 三、核心指标演进

| 指标 | 10-13（报告基线） | 10-15（当前） | 变化 |
|---|---|---|---|
| MCP 工具数 | 14 | **21** | +7 |
| 单测数 | ~414 | **785** | +371 |
| Bench 用例 | 11 | **69** | +58 |
| 配方 HA 字段 | 0/152 | **152/152** | 全覆盖 |
| Golden vectors | 0 | **16** | 新增 |
| Ratchet modules | 0 | **27** | 新增 |
| gate_version | v2 | **v6** | +4 |
| 分区数 | 6 | **8** | +2 (hot_arid, highland) |
| Köppen 分类正确率 | ~80% | **100%** | 修正 3 个映射错误 |

---

## 四、明确不做（诚实清单）

按 CORE_OBJECTIVE §八 纪律，以下项目**不做**：

**需外部数据/长时间**：
- M4-P1 30 作物扩展 · M1-A4 CMIP7 数据 · M2 土壤全量 · M3 生态位
- M4-P4 机理生物量 · M6-D2 环境耦合 · M7-N1/N2 营养深探
- L1 视觉识别 · M-1 激励机制 · L2-5 eval 外部基准

**破坏风险高**：
- M10-O1 DAG 编排重构 · M13-P5 mcp 三层拆分

**需 G1 才能激活**：
- M14-E6 外回路反馈 · M16-B1 A/B 面联动

**人工阻塞（仅用户能做）**：
- 公网 Demo SSH 部署（`ssh-copy-id root@150.158.119.19`）
- Glama 审批跟催 · npm 发布 · README EN

---

## 五、剩余缺口

**已补完（本轮新增）**：
- ✅ M15-B4 保形覆盖率指标（bench 集成 conformal coverage，46/50 覆盖，92% > 90% guarantee）
- ✅ M15-B5 评测先行门禁（check_bench_coverage.py + CI 硬门禁，7/7 模块覆盖，69 用例）

**已补完（本轮新增）**：
- ✅ M16-B2 决策路径可视化报告（`scripts/export_decision_path.py` + `agri_decision_path_report` MCP 工具，7 案例 55.5KB HTML）

**立刻可做**（不违背 G1）：
- （无，M16-B2 已完成）

**需 G1 激活**：
- M14-E6 外回路反馈 · M16-B1 A/B 面联动

**人工阻塞**：
- 公网 Demo SSH · Glama · npm · README EN

---

## 六、本轮文件变更汇总

### 新增
- `.well-known/mcp-card.json` — MCP Server Card 元数据
- `benchmarks/agri_recipe_bench/results_history.json` + `leaderboard.html` — bench 历史追踪
- `agent/orchestration_audit.py` — 编排层可审计性（400 行）
- `scripts/verify_trust_mark.py` — T-1 可信标记公共复算 API（320 行）
- `scripts/apply_recipe_ha_fields.py` — HA 事实标准字段生成器（300 行）
- `scripts/test_mcp_categories.py` / `test_orchestration_audit.py` / `test_verify_trust_mark.py` / `test_ha_fields.py` — 硬门禁

### 修改
- `core/climate_grid.py` — Köppen 映射修正
- `data/zone_meta/global_zones.json` — arid 分区 koppen_class 修正
- `data/zone_meta/koppen_grid.json` — 栅格重新生成
- `mcp/server.py` — +6 工具（19→20），Server Card，ETags
- `scripts/generate_koppen_grid.py` / `test_climate_grid.py` / `test_engine_v5.py` / `test_shadow_execution_log.py` — 测试修复
- `.well-known/evolution_zones.json` — gate_version v2→v6
- `harness/manifest.json` — v2.3.0 指纹同步
- `README.md` / `mcp/README.md` / `app/index.html` — 文档同步
