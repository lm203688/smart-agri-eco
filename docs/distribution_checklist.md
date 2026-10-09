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
| P0-4a | MCPB 分发包构建 | ✅ **已完成** | `dist/agri-eco-mcp-1.1.0.mcpb`（200 文件 / 0.44 MB），**确定性可复现** |
| P0-5a | Demo 端到端冒烟自检 | ✅ **已完成** | `python scripts/check_demo_endpoints.py`，14/14 通过，已入 CI |
| P0-4c | 官方 MCP Registry 上架 | ✅ **已完成** | `io.github.lm203688/agri-eco` v1.1.0，2026-10-08 上架，CI 一键可重发 |
| P0-4d | Smithery 自动发现 | ✅ **已完成** | `smithery.yaml` 已入仓库，Smithery 从 GitHub 自动抓取，**免表单提交**；搜索入口 `https://smithery.ai/search?q=agri-eco` |
| P0-4e | 分发就绪度一键自检 | ✅ **已完成** | `scripts/check_distribution_readiness.py`，一次性验证 10 类分发入口，20/20 全绿 |
| P0-4b | 上架其余 2 个市场 | ⏸ **需你操作** | Glama / LobeHub，材料全备：`docs/market_listing_pack.md` §2/§3 |
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
| **Official MCP Registry** | GitHub Actions OIDC → Registry API | ✅ 已完成（CI 自动发布） |
| **Smithery** | 仓库根目录 `smithery.yaml` 自动抓取 | ✅ 已完成（2026-10-08，`smithery.yaml` 已入库，无需填表单） |
| **Glama** | 站内表单 / 从 GitHub 拉取 | ⏸ 需你操作（表单材料见 `docs/market_listing_pack.md` §2） |
| **LobeHub MCP** | 站内表单 / PR 到其仓库 | ⏸ 需你操作（材料见 `docs/market_listing_pack.md` §3） |

### 3.2 ✅ 官方 MCP Registry 已上架（2026-10-08）

**验收结果**（Registry API 实时可查）：

```
name        : io.github.lm203688/agri-eco
version     : 1.1.0
registryType: mcpb
identifier  : https://github.com/lm203688/smart-agri-eco/releases/download/v1.1.0/agri-eco-mcp-1.1.0.mcpb
sha256      : 390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24
publishedAt : 2026-10-08T05:33:32Z
```

复核命令：

```bash
curl -s "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.lm203688/agri-eco"
```

**为什么能自动化**：`mcp-publisher login github` 是交互式 device-code 流程（要人工
去 github.com/login/device 输一次性码），无人值守环境做不了；而
`login github-oidc` **只在 GitHub Actions 内可用**。所以发布做成了
`.github/workflows/publish-mcp-registry.yml`，手动 dispatch 或打 `v*` tag 即触发。

**过程中的三个真坑（都已修，别回退）**：

1. **`description` 必须 ≤100 字符**。Registry 返回 422 才暴露，本地 `validate`
   不报错。现已缩到 84 字符。
2. **`fileSha256` 必须与 Release 上的 asset 逐字节一致**。最初设计成"本地构建 →
   回填 server.json → 手工上传 asset"，每改一次代码就得重走一遍，漏一步就
   `❌ sha256 不一致`。现已改为 **CI 内部一条龙**：构建 → `gh release upload --clobber`
   → 用同一文件回填 → 回读校验 → 发布。三处 sha 来源唯一，结构上不可能不一致。
3. **zip 曾混入 mtime**，导致同一份源码两次构建 sha 不同（`a7593649` vs
   `af4b7333`），排查方向被误导到"资产没上传"。修法：显式构造 `ZipInfo`，
   固定 `date_time=(1980,1,1,0,0,0)`、`create_system=3`、权限 `0644`。
   另有本地未入库的 `.bak` 文件混入打包清单（本地 201 / CI 200），已加
   `EXCLUDE_FILE_MARKERS`。现在**本地 = CI = `390e9779`**。
   回归测试锁死：`python -m unittest scripts.test_build_mcpb`。

**幂等行为**：Registry 不允许同版本重复发布（400 `cannot publish duplicate
version`）。workflow 已区分处理——重复视为成功；但若**内容变了而版本没升**，
会先被「版本漂移检测」拦下并显式报错，避免新代码静默发不出去。

### 3.3 提交材料（其余 3 家）

**完整材料已移入独立文件：[`docs/market_listing_pack.md`](market_listing_pack.md)**

该文件包含：
- 所有市场复用的通用字段（短名 / One-liner / 完整描述 / 分类 / 安装配置 / 许可）
- 14 个工具的逐条说明表（可作亮点列举）
- **Glama / LobeHub / Smithery** 各自的表单字段映射与需要新增的文件
- 提交后的验收清单

### 3.4 提交后的验收标准

- [x] 官方 MCP Registry 搜索 `agri-eco` 可见（✅ 已达成）
- [x] Smithery `smithery.yaml` 已入库，Smithery 从 GitHub 自动抓取（✅ 已就绪，等待站内同步显示）
- [ ] Glama / LobeHub 搜索 `agri-eco` 可见（⏸ 待提交表单）
- [ ] 从任一市场按指引安装后，`tools/list` 返回 **14** 个工具
- [ ] 出现第 1 次**非本人**的外部调用（P0 出口指标）

### 3.5 分发就绪度自检（推荐每次评审/发布前跑）

```bash
python scripts/check_distribution_readiness.py
```

一次性验证 10 类分发入口（MCP server / A2A Card / Agent Plugin / Smithery / 官方 Registry /
MCPB 包 / CI workflow / Demo 部署 / 市场材料 / GitHub 同步），非零退出即视为分发链路不可上线。
当前基线：**20 通过 / 0 告警 / 0 失败 / 1 跳过**（跳过项：公网部署待你执行）。

---

## 4. 一页速查：你现在要做的两件事

**前提已就绪**：仓库同步完成（340 文件 / 差异 0）、MCPB 分发包已构建且确定性可复现、
**官方 MCP Registry + Smithery 自动发现已就绪**、CI 与 Publish 两条 workflow 全绿、
分发就绪度自检 20/20 全绿、Glama / LobeHub 提交材料已备齐。

1. **跑部署**（§2）→ 先 `ssh-copy-id root@150.158.119.19`，再 `bash deploy/deploy_local.sh`，拿到公网 Demo 链接
2. **提交 2 家市场**（`docs/market_listing_pack.md` §2/§3）→ Glama + LobeHub 各需独立账号
   （Smithery 已自动就绪，无需填表单，站内搜索 `agri-eco` 即可）

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
