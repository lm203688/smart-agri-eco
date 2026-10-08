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
| P0-6 | GitHub 推送 | ✅ **已完成** | commit `6ef8b6c8cdeb`，332 文件，`sync_check` 差异 **0** |
| P0-4a | MCPB 分发包构建 | ✅ **已完成** | `dist/agri-eco-mcp-1.1.0.mcpb`（201 文件 / 0.44 MB），实测解压可跑 |
| P0-5a | Demo 端到端冒烟自检 | ✅ **已完成** | `python scripts/check_demo_endpoints.py`，14/14 通过，已入 CI |
| P0-4b | 上架 4 个市场 | ⏸ **需你操作** | 材料全备：`docs/market_listing_pack.md` |
| P0-5 | 公网 Demo 部署 | ⏸ **需你执行** | 脚本 + 自检全就绪，只差 SSH 免密；见 §2 |

**已完成的安全处置**：推送过程中 GitHub 密钥扫描拦截了一次误传（临时 PAT 文件进入 blobs），
随后修正 `.gitignore` 与 `sync_check.py` 的忽略规则，**凭据文件已永久排除在比对与推送范围外**。
推送完成后所有临时凭据已删除，并做了全盘残留审计（结果：无残留，远端亦无）。

---

## 1. P0-6 · GitHub 推送 ✅ 已完成

**结果**：commit `6ef8b6c8cdeb`，写入 73 文件 / 删除 29 文件，`sync_check` 差异归零。

推送前 HEAD 为 `a9f331b7dc`（如需回滚，用此 sha reset）。

### 过程中的一个安全事件（值得记录）

首次推送被 GitHub 的 **secret scanning** 拦截（HTTP 422，`Secret detected in content`）。
原因：我把 PAT 存到了 `.workbuddy-ai/tmp/pat4.txt`，而该目录当时未被忽略，
`sync_check.py` 把它当成待推送文件收集了进去。

**处置**：
1. 立即在 `.gitignore` 与 `sync_check.py` 中加入凭据排除规则（`.workbuddy-ai/tmp/`、`*_pat*.txt` 等）
2. 加"凭据二次检查"断言，推送前若发现含 `pat` 的路径则中止
3. 推送成功后删除全部临时凭据，并做全盘 + 远端双向残留审计

> 教训：**凭据文件绝不应放在会被版本控制的目录里**。GitHub 的扫描这次起了作用，
> 但不能依赖外部防护——本地忽略规则才是根本。

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
| `deploy/deploy_config.sh` | ✅ 已创建（端口 8001；已加入 `.gitignore`，不随仓库分发） |
| 本机部署链路自检 | ✅ **14/14 端点通过**（`python scripts/check_demo_endpoints.py`） |
| SSH 免密登录 | ❌ **未配置**（`Permission denied (publickey,password)`） |

### 部署前已消除的未知风险

因为 SSH 未通，无从在真实 ECS 上试跑，我改为在**本机把整条部署链路完整跑一遍**，
把「部署后才发现哑端点」这个风险提前消掉。结果：

```
$ python scripts/check_demo_endpoints.py
汇总: 14 通过 / 0 失败 / 共 14 项
```

- 8 个 GET 端点全部 200，且体积高于哑响应下限
  （`/api/cities` 1659B、`/api/skills` 4941B、`/api/recipes` 9280B、
  `/api/crops` 165410B、`/api/zones` 17281B、`/api/pests` 9826B、
  `/api/stats` 1828B、`/api/bp_list` 1256B）
- 6 个 POST 端点全部 200 且响应契约键齐备，其中 `/api/recommend`
  真实跑通整条 pipeline（返回 `pipeline_steps` / `final_recommendation`）
- 该脚本已并入 CI（见 `.github/workflows/ci.yml`「Demo 站点端到端冒烟」步骤），
  以后新增端点若静默变哑，CI 会直接拦下

> **踩坑记录（重要，部署到 ECS 时同样适用）**：环境里若有
> `HTTP_PROXY=http://127.0.0.1:<port>`，`urllib` 会把发往
> `127.0.0.1:<本地端口>` 的请求也塞进代理，代理不认这个端口就回
> **502 Bad Gateway**。表现极具误导性——服务日志里一条请求都没有，
> 所有端点"全挂"，看着像服务崩了，其实是代理拦的。
> `check_demo_endpoints.py` 内已用空 `ProxyHandler` 只对回环地址装直连，
> 不动环境变量（否则会误伤 NASA POWER 等真实出网请求）。

### 你需要做

```bash
# 1. 配置模板已创建（deploy/deploy_config.sh，端口 8001，ECS 150.158.119.19）

# 2. 只需配一次 SSH 免密登录
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

### 3.2 提交材料

**完整材料已移入独立文件：[`docs/market_listing_pack.md`](market_listing_pack.md)**

该文件包含：
- 所有市场复用的通用字段（短名 / One-liner / 完整描述 / 分类 / 安装配置 / 许可）
- 14 个工具的逐条说明表（可作亮点列举）
- **Official MCP Registry** 的完整 3 步操作（含 `server.json` 与 MCPB 产物说明）
- **Glama / LobeHub / Smithery** 各自的表单字段映射与需要新增的文件
- 提交后的验收清单

### 3.3 提交后的验收标准

- [ ] 4 个市场搜索 `agri-eco` / `agriculture mcp` 均可见
- [ ] 从任一市场按指引安装后，`tools/list` 返回 **14** 个工具
- [ ] 出现第 1 次**非本人**的外部调用（P0 出口指标）

---

## 4. 一页速查：你现在要做的两件事

**前提已就绪**：仓库同步完成（332 文件 / 差异 0）、MCPB 分发包已构建并通过运行验证、四个市场的提交材料已备齐。

1. **跑部署**（§2）→ 三条命令，拿到公网 Demo 链接
2. **提交市场**（`docs/market_listing_pack.md`）→ 先建 GitHub Release 上传 `.mcpb`，再逐家提交

两步做完，`docs/CORE_OBJECTIVE.md` 的 G1 目标（≥500 次调用 / ≥20 独立调用方，窗口约至 2026-12 中旬）才真正开始计时。

---

## 5. 若需要我代劳的部分

以下操作我可以做，**只需要你临时提供一次凭据**，用完即删：

| 操作 | 需要什么 | 我做的时长 |
|---|---|---|
| 更新仓库元数据（描述 / topics / 主页） | GitHub PAT（repo 权限） | 1 分钟 |
| 创建 GitHub Release 并上传 `.mcpb` | GitHub PAT（Contents + Releases 写权限） | 2 分钟 |
| 创建 `smithery.yaml` 并推送 | GitHub PAT（Contents 写权限） | 2 分钟 |

> 凭据请**不要在对话中长期保留**。用完我会立即删除，并做残留审计（如 §1 所做）。
