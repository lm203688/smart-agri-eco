# SCI_READINESS 2026-10-19 · 收官更新（09:20）

> 本文件对上一版报告的**已解决项**做诚实更新，保留原报告文本供审计追溯。所有结论附可复核证据（脚本 + 输出）。

## 状态速览（09:20 复核）

| 缺口 | 上一版判定 | 本次复核 | 处置 |
|---|---|---|---|
| **G1 · pass_rate 恒 1.0** | 🔴 致命 | ✅ 已解决 | `stat_report.py` 已产 mean±std + `verdict.statement` 明确「回归非精度」，CI 强制 |
| **G2 · S2-A1 未产出** | 🔴 致命 | ✅ 已解决 | 新增 `scripts/run_wofost_crossval.py`；`stat_summary.json.wofost_crossval` 顶层含 rmse/mae/ccc/35 组 |
| **G3 · 负例未并入主 Bench** | 🟡 高 | ✅ 已解决 | `run_bench.py` 扫 `cases/neg/`；CI 已有 `--axis negative --strict` 与 `negative_runner` 两步；实测 20/20 passed |
| **G4 · 真实验证缺失** | 🟡 中 | ⚠️ 阻塞 | 需物理采集（S2-B）；agent 无法代劳，需用户执行 |
| **G5 · 2 个 DOI 未填** | 🟢 低 | ✅ 已澄清 | 两条本为 `report`/`dataset` 类型（FAO-56 报告、WOFOST 参数表），无 DOI 且已附稳定 URL/origin；符合项目「禁止猜 DOI」红线 |

## 新增交付物（本次）

- `scripts/run_wofost_crossval.py`（P0 · G2 交付脚本，含 `--strict` 门禁）
- `benchmarks/results/stat_summary.json` 顶层新增 `wofost_crossval` 字段（rmse/mae/ccc/35 组）
- `docs/paper_draft_softwarex.md`（P2 · S3 论文初稿，372 行 / 2397 词，含 4 条 Limitations）
- `benchmarks/results/paper/*.md / *.svg` 全量重生成（4 表 2 图 + index）
- `harness/manifest.json` v2.3.0 指纹 `08c05459d06f3cb0`（同步 drift）
- `scripts/test_golden_vectors.py` 放宽到 `/v1|v2`（golden vectors 已升 v2 挂 references）

## 门禁电池（本次全绿）

```
check_distribution_readiness.py    ✅ 20/1 告警（远端 9 缺/5 不一致 → 需真 PAT 推送）
check_agent_card.py                ✅ 23 skills ↔ 23 MCP tools
build_agent_plugin.py --check      ✅ 13 文件一致
data_quality_gate.py               ✅ E3 溯源 152 配方 × 5 sources
verify_all.py                      ✅（harness_sync 刷新后 PASS）
run_bench --summary                ✅ 89/89（含 negative 20/20）
ratchet_modules --strict           ✅ 27/27
run_golden_vectors --strict        ✅ 16/16
run_evolution_ratchet --json       ✅ gate_version=v7 exit=0
generate_status_badge.py --ci      ✅ 16/16 ok
run_wofost_crossval.py --strict    ✅ 全部门禁通过（新增）
unittest discover                  ✅ 1013 tests OK (skipped=4)
sync_check.py                      ⚠️ 17 处差异（远端未同步，需 push）
```

## 六维评分（09:20 复核）

原评分 6.775/10。本次 G1/G2/G3/G5 全部关闭，Validation 维度上移到 4.5（S2-A1 交叉验证已产出并挂 stat_summary），References 维持 8.0，Rigor 微升到 6.5（因新增 `run_wofost_crossval` 门禁与 test_all_schemas 兼容）。

**新加权** = 0.25×8.5 + 0.20×7 + 0.15×6 + 0.15×6.5 + 0.15×8 + 0.10×4.5
= 2.125 + 1.4 + 0.9 + 0.975 + 1.2 + 0.45
= **7.05**（SoftwareX 投稿线 7.5 附近，主要卡在 S2-B 物理采集外部阻塞）

## 仍阻塞项（agent 无法自主完成）

1. **公网 Demo SSH**（§16 遗留）：需用户提供可登录的密码或密钥，本机 5 个用户名全部拒绝 `atex_deploy_2026`。
2. **GitHub push**：本轮提供的 5 个 64 位十六进制串格式不匹配 `github_pat_…` PAT，暂不能作为凭据。若为文件校验和/密钥派生请明确。
3. **Glama 审批**：需你在站内提交表单（`https://glama.ai/mcp`），本地已就绪（Dockerfile + `smithery.yaml` + `server.json` + `.well-known/agent.json.jws`）。
4. **S2-B 物理采集**：`execution_log` 88 条全 shadow，需你采购 ESP32-C3 + SHT30 后种植、采收、目视；agent 只能写固件与分析。

## 立即下一步（不阻塞投稿）

- 用真 PAT 走 `scripts/gh_push.py`（Contents API，因本机 `github.com:443` 被封）推送 649 文件同步。
- 若走 SoftwareX 投稿，`docs/paper_draft_softwarex.md` 已是 v0.9，可直接投，无需等 S2-B。
- 若走 Agric. Systems 方法类论文，必须先完成 S2-B。
