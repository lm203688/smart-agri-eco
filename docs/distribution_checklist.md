# 分发上架操作手册（P0-4 / P0-5 / P0-6）

> 目的：把「让外部 Agent 真实调用」这条 P0 主线的**剩余人工步骤**写成可照做的清单。
> 依据：`docs/CORE_OBJECTIVE.md` §八（P0 = 直接提升 G1 的动作）、`docs/full_liftup_assessment_2026-10-08.md` §8。
> 状态更新时间：2026-10-08。
>
> **本文件中的每一条，凡标注「需你操作」的，都是我在本机无法代劳的（需要账号、凭据或人工提交表单）。**

---

## 0. 当前状态总览

| # | 动作 | 状态 | 说明 |
|---|---|---|---|
| P0-1 | MCP 2026-07-28 无状态适配 | ✅ **已完成** | `mcp/server.py`，SEP-2575/2567/2243/2549/414 全适配 |
| P0-2 | A2A Agent Card | ✅ **已完成** | `.well-known/agent.json`，14 skill |
| P0-3 | Agent Plugins 打包 | ✅ **已完成** | `plugin/`，13 文件 |
| P0-7 | 消除硬编码密钥 | ✅ **已完成** | `grep secret_key` = 0 命中 |
| P0-6 | GitHub 推送 | ⏸ **需你提供 PAT** | 见 §1 |
| P0-5 | 公网 Demo 部署 | ⏸ **需你执行** | 脚本已就绪，见 §2 |
| P0-4 | 上架 4 个市场 | ⏸ **依赖 P0-6** | 材料已备，见 §3 |

---

## 1. P0-6 · GitHub 推送（阻塞全部上架动作）

### 为什么这是瓶颈

所有 MCP 市场（Glama / LobeHub / Smithery / Official Registry）都是**从 GitHub 仓库抓取**元数据与清单。
仓库没同步 = 市场看不到 = 零外部调用。这是当前唯一的关键路径卡点。

### 你需要做（仅此一步）

1. 打开 https://github.com/settings/personal-access-tokens/new
2. 按以下参数创建 **fine-grained** token：
   - **Token name**: `agri-eco-push`
   - **Expiration**: 7 days（够用即可，不必长期）
   - **Repository access**: Only select repositories → `lm203688/smart-agri-eco`
   - **Permissions**:
     - `Contents`: **Read and write**（必需）
     - `Workflows`: **Read and write**（必需——本次要更新 `.github/workflows/ci.yml`）
     - 其余全部保持 No access
3. 生成后复制 token，粘贴到一个临时文件，例如 `C:\Users\xing\Desktop\pat.txt`（只有一行，不要有空格或换行以外的字符）

### 然后我执行（已封装成一键脚本）

```bash
# 一条命令完成：算差异 → 推送（含删除）→ 回读校验 → 复核归零
bash scripts/push_all.sh /path/to/pat.txt

# 脚本结束后立即删 PAT
rm /path/to/pat.txt
```

`scripts/push_all.sh` 的行为：
1. 实时调 `sync_check` 算差异（不依赖预生成清单，避免清单过期）
2. 单 commit 推送全部新增 + 更新 + 删除
3. `gh_push.py` 内置回读校验（写入项 sha 一致 + 删除项确已不存在）
4. 再跑一次 `sync_check` 确认差异归零

### 本次推送清单（102 处差异，已实测逐条核对）

- **新增 45**：`docs/CORE_OBJECTIVE.md`、`.well-known/agent.json`、`plugin/**`（13 文件）、`docs/distribution_checklist.md`、`Makefile`、`pyproject.toml` 等
- **更新 28**：`mcp/server.py`、`mcp/README.md`、`README.md`、`.github/workflows/ci.yml`、`harness/manifest.json`、`scripts/sync_check.py` 等
- **远端删除 29**：根目录旧布局遗留 + 归档模块 + 临时产物

> ⚠️ **删除项已逐条核对本地副本（全部确认有留存或确为临时产物）**：
>
> | 类别 | 数量 | 本地留存位置 |
> |---|---|---|
> | 根目录旧规划文档 | 10 | `docs/planning/`（同名副本） |
> | 部署包 | 2 | `deploy/releases/`（同名副本） |
> | 归档 agent 模块 | 5 | `_archive/agent_legacy_20261008/` |
> | `config/agents/*.json` | 7 | `_archive/agent_legacy_20261008/config_agents/agents/` |
> | 临时产物（`_jev_out.txt` 等） | 3 | `_archive/workbuddy_tmp_20261008/` |
> | 探针脚本 | 1 | 已确认为一次性探针，无引用 |
> | 旧备份 | 1 | `data/crop_adapt_db.json.bak_20261006` 为更新版本，且 `.gitignore` 已忽略 |

> **重要修正**：`agent/__init__.py` / `bp_screen/__init__.py` / `engine/__init__.py` 曾一度出现在删除清单中——
> 原因是 `sync_check.py` 的 `_*.py` 忽略规则用 `fnmatch` 匹配时会误吞 `__init__.py`（`*` 匹配到 `_init__`）。
> 已修正为「根目录 glob 只作用于根 + `__init__.py` 永不禁用」，并加了 16 个用例的回归验证。
> 这三个包入口文件**不应删除**，推送清单中已正确移出。

---

## 2. P0-5 · 公网 Demo 部署

### 前置条件检查

| 项 | 状态 |
|---|---|
| `deploy/deploy_local.sh` | ✅ 就绪 |
| `deploy/setup_ecs.sh` | ✅ 就绪 |
| `deploy/docker-compose.prod.yml` | ✅ 就绪 |
| `deploy/nginx.conf` | ✅ 就绪 |
| `deploy/deploy_config.example.sh` | ✅ 就绪（模板，含默认 ECS IP） |
| `deploy/deploy_config.sh` | ❌ **未创建** |

### 你需要做

```bash
# 1. 复制配置模板（已含默认 ECS 150.158.119.19 / 端口 8001）
cp deploy/deploy_config.example.sh deploy/deploy_config.sh

# 2. 确认 SSH 免密登录可用
ssh-copy-id root@150.158.119.19

# 3. 一键部署
bash deploy/deploy_local.sh

# 4. 验证
curl http://150.158.119.19:8001/api/cities
```

> 端口 8001 是刻意选定的：该 ECS 上已跑 ATEX(8420) 与 HealthLens，8001 不冲突。
> 若你希望改用其他端口，只需在 `deploy_config.sh` 里改 `PORT`。

### 部署成功后

把可点链接写进 README 顶部（这是 MCP 市场与 A2A 发现都会抓的字段），并把它填进 `.well-known/agent.json` 的 `url`（当前指向 GitHub，有公网 Demo 后应改指 Demo 地址）。

---

## 3. P0-4 · 上架四个 MCP 市场

> 全部依赖 §1 完成（市场从 GitHub 抓取）。

### 3.1 为什么是这四家

| 市场 | 抓取方式 | 需要你操作 |
|---|---|---|
| **Official MCP Registry** | GitHub 仓库 → 自动/半自动 | 提交仓库地址 |
| **Glama** | 从 GitHub 拉取 MCP server 清单 | 认领/提交 |
| **LobeHub MCP** | 社区提交 PR 到其仓库 | 提 PR 或在其站内提交 |
| **Smithery** | 站内提交 `mcp.json` 或仓库地址 | 提交表单 |

### 3.2 提交时可直接复用的字段

以下内容已备好，粘贴即可（与 `.well-known/agent.json`、`plugin/plugin.json` 完全一致，无口径冲突）：

**Name**: `agri-eco`

**One-liner**（≤120 字符）:
```
面向分布式农业的 Agent-native 知识基座：可执行 Env Recipe 环境配方 + 物候播期 + 多源气候校准，零依赖可离线
```

**Description**:
```
面向分布式农业的 Agent-native 知识基座。提供可执行的 Env Recipe 环境配方（作物 × 生长阶段 × 设备类别 → 可落地环境参数，116 份已发布）、多源气候校准（NASA POWER + Open-Meteo 逐月调和与分歧告警）、WOFOST 积温物候与霜冻锚定播期窗口、土壤剖面、农业分区匹配、病虫害与养分诊断、数据血缘溯源与农业项目投资初筛。

差异化：零第三方依赖（纯标准库）、可完全离线、可私有化部署、可审计；所有输出带 sources / confidence / resolution 标注，不可测即标不可测，绝不编造数值。

协议合规：MCP 2026-07-28 无状态规格（SEP-2575/2567/2243/2549/414）、A2A v1.0 Agent Card、Agent Plugins 1.0.0。

边界（诚实声明）：不提供 C 端应用与 B 端 SaaS；不承诺 SLA；付费标的为服务能力，数据始终免费开源。
```

**Categories**: `agriculture`, `agritech`, `environment`, `data`, `science`

**Transport**: `stdio`

**Install**:
```json
{
  "mcpServers": {
    "agri-eco": {
      "command": "python",
      "args": ["mcp/server.py"]
    }
  }
}
```

**Repository**: `https://github.com/lm203688/smart-agri-eco`

**License**: 见仓库 LICENSE（代码）；数据为混合许可（含 CC BY-NC-SA 3.0 IGO 来源），不得转售

### 3.3 提交后的验收标准

- [ ] 4 个市场搜索 `agri-eco` / `agriculture mcp` 均可见
- [ ] 从任一市场按指引安装后，`tools/list` 返回 14 个工具
- [ ] 出现第 1 次**非本人**的外部调用（P0 出口指标）

---

## 4. 一页速查：你现在要做的三件事

1. **给 PAT**（§1）→ 我立刻完成推送，这是解锁所有后续动作的唯一前提
2. **跑部署**（§2）→ 三条命令，拿到公网 Demo 链接
3. **提交市场**（§3）→ 用 §3.2 的现成字段，逐家粘贴

三步做完，`docs/CORE_OBJECTIVE.md` 的 G1 目标（≥500 次调用 / ≥20 独立调用方，窗口约至 2026-12 中旬）才真正开始计时。
