# AOCI 开发指南（工程化）

> 适用版本：v0.9-beta。本文件描述如何在本地以「工程级别」方式开发、验证与发布 AOCI（智慧农业生态）。

## 1. 关键约束

- **零第三方运行时依赖**：全部代码仅用 Python 标准库（`agent/`、`engine/`、`core/`、`scripts/`、`mcp/`、`bp_screen/`、`skills/`）。不要引入 pip 包作为运行时依赖；纯算法请用标准库实现。
- **stdout 是协议通道**：MCP server 走 stdio，任何 `print` 到 stdout 都会破坏 JSON-RPC。日志一律走 `stderr` / `logging`。
- **数据真实性红线**：`calibrated=true` 必须带 `measured_calibration` 实证；`feedback_log` 不得含 demo/单测/冒烟合成样本（见 `engine/rsi.py::_is_synthetic`）。
- **能力数字防漂移**：README / `mcp/README` / `app/index.html` 的 MCP 工具数(14)/分区数(8)/配方数(152)/闸数(12) 由 `scripts/test_engine_v5.py::TestDocCapabilityNumbersInSync` 锁死，扩张后必须同步这三处。

## 2. 目录布局

| 目录 | 职责 |
|---|---|
| `agent/` | 多 Agent 编排（climate/crop/growth/eco + pest/nutrition/season） |
| `engine/` | 核心引擎（RSI / flywheel / local_search / trust_layer） |
| `core/` | 共享原语（geo_recipe / trust 等） |
| `mcp/` | MCP server（14 工具）+ skill 注册 |
| `bp_screen/` | 商业可行性门禁（规则库 v2.2.0，12 gate） |
| `data/` | 知识底座（crop_adapt_db / env_recipes / knowledge_graph / zone_meta） |
| `scripts/` | 可复跑脚本 + 13 套单测（共 505 项，3 skip） |
| `docs/` | 设计/评估/发行文档（规划类在 `docs/planning/`） |
| `deploy/` | 部署物料（含 `deploy/releases/` 历史部署包） |
| `config/` | 运行时配置（ecosystem.json 等） |
| `harness/` | manifest 指纹基线（声明区门禁） |
| `schemas/` | Env Recipe / 数据协议 schema |
| `skills/` | 9 个 Agent skill |

## 3. 本地常用命令

```bash
make test      # 全量单测回归
make verify    # 端到端主门禁 verify_all.py
make quality   # 数据质量门禁 data_quality_gate.py
make gate      # 三件套
make ci        # 复现 CI 关键步骤
```

或直接用托管 Python（本项目验证用）：

```bash
C:/Users/xing/.workbuddy/binaries/python/versions/3.13.12/python.exe -m unittest discover scripts/
C:/Users/xing/.workbuddy/binaries/python/versions/3.13.12/python.exe scripts/verify_all.py
```

## 4. 数据/基线管理

- 改动 `data/*.json`、`global_zones.json`、`crop_adapt_db.json` 后必须重跑 `python scripts/harness_sync.py init` 刷新指纹基线，否则 `verify_all` 会报声明区漂移。
- `validate_env_recipe.py` 必须带 `data/env_recipes` 目录参数，否则只校验 1 份 sample。

## 5. 推送与发布

- 本仓 **不走 git 直推**（github.com:443 被封）。统一走 `scripts/gh_push.py <token_file> <msg> <files...>`（Contents API，需 `curl --ssl-no-revoke --tlsv1.3`）。
- 发版：打 annotated tag `v0.9-beta` + GitHub Release（物料见 `docs/release_notes_v0.9-beta.md`）。
- 编辑 `.github/workflows/ci.yml` 需 PAT 含 `Workflows:write`。

## 6. 定时治理

- `AOCI 每日治理校验` 自动化（每日 03:00，只读）：跑 `verify_all` + `data_quality_gate` + 全量单测并汇报，不改文件、不推送。
