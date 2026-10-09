# MCP 市场上架提交包（P0-4）

> 用法：每个市场一节，**从上到下照做即可**。所有字段均与 `.well-known/agent.json`、`plugin/plugin.json`、`mcp/server.py` 保持同源，不存在口径冲突。
> 前置：**P0-6 已完成**（仓库 `lm203688/smart-agri-eco` 已同步，332 文件，零差异，commit `6ef8b6c8cdeb`）。
> 状态：2026-10-08。

---

## 通用字段（所有市场复用，直接复制）

### 短名
```
agri-eco
```

### One-liner（≤120 字符）
```
面向分布式农业的 Agent-native 知识基座：可执行 Env Recipe 环境配方 + 物候播期 + 多源气候校准，零依赖可离线
```

### 完整描述
```
面向分布式农业的 Agent-native 知识基座。提供可执行的 Env Recipe 环境配方（作物 × 生长阶段 × 设备类别 → 可落地环境参数，116 份已发布）、多源气候校准（NASA POWER + Open-Meteo 逐月调和与分歧告警）、WOFOST 积温物候与霜冻锚定播期窗口、土壤剖面、农业分区匹配、病虫害与养分诊断、数据血缘溯源与农业项目投资初筛。

差异化：零第三方依赖（纯 Python 标准库）、可完全离线、可私有化部署、可审计；所有输出带 sources / confidence / resolution 标注，不可测即标不可测，绝不编造数值。

协议合规：MCP 2026-07-28 无状态规格（SEP-2575/2567/2243/2549/414）、A2A v1.0 Agent Card、Agent Plugins 1.0.0。

边界（诚实声明）：不提供 C 端应用与 B 端 SaaS；不承诺 SLA；付费标的为服务能力，数据始终免费开源。
```

### 分类标签
```
agriculture, agritech, environment, data, science
```

### 传输方式
```
stdio
```

### 安装配置（stdio）
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

### 仓库地址
```
https://github.com/lm203688/smart-agri-eco
```

### 许可
```
代码：MIT（见仓库 LICENSE）
数据：混合许可。Env Recipe 的 sources[] 含 FAO 等 CC BY-NC-SA 3.0 IGO 来源，整包不得作为付费资产转售。
```

### 工具清单（14 个，可作亮点列出）

| 工具 | 一句话 |
|---|---|
| `agri_env_recipe` | 作物 × 阶段 × 设备类 → Env Recipe v1 可执行配方 |
| `agri_match_zone` | 经纬度 → Köppen-Geiger + FAO 农业分区 |
| `agri_recommend_crops` | 分区 + 偏好 → 作物推荐（含适配分与兜底品种） |
| `agri_growth_plan` | 作物 + 场景 + 分区 → 完整种植计划（含微气候修正） |
| `agri_season_advisory` | 12 月均温 → 无霜期 + 播期窗口；或作物 + 均温 → 物候天数 |
| `agri_reconcile_climate` | 多源气候调和 + 逐月一致度 + 分歧告警 |
| `agri_soil_profile` | 土壤剖面（SoilGrids 在线优先，降级明确标注） |
| `agri_diagnose_pest` | 病虫害与营养缺乏诊断（视觉后端可插拔） |
| `agri_nutrition_plan` | 阶段化施肥方案 |
| `agri_resolve_recipe` | 城市名/经纬度 → 分区 → 配方清单（完全离线） |
| `agri_query_lineage` | 数据血缘溯源（外部 API + SHA256 指纹 + 校准实证） |
| `agri_list_cities` | 预设城市清单 |
| `agri_list_ecosystem` | 开源/商业生态对接清单 |
| `agri_bp_screen` | 农业项目投资初筛（六分类 + 五闸 + 六评分卡） |

---

## 1. Official MCP Registry

> **重要**：官方 Registry 的规则与常见误传不同，以下内容已核对官方文档（`modelcontextprotocol.io/registry`）。
> 本项目走 **MCPB 路径**（GitHub Releases 分发预打包产物），而非 PyPI——理由见下。

### 为什么选 MCPB 而不是 PyPI

| 路径 | 终端用户要求 | 与项目定位的契合度 |
|---|---|---|
| `registryType=pypi` | 需装 `uvx`，从 PyPI 拉包 | 需把包发布到 PyPI（额外发布环节） |
| **`registryType=mcpb`**（本项目采用） | **无需任何工具链**，直接下载运行 | ✅ 契合「零依赖、可离线、可私有化」 |

### 已完成（我做的）

- [x] 构建 MCPB 产物：`dist/agri-eco-mcp-1.1.0.mcpb`（201 文件 / 0.44 MB）
- [x] 实测解压后可独立启动，`tools/list` 返回 **14** 个工具，离线工具正常返回数据
- [x] 创建 `server.json` 并回填真实 `fileSha256`
- [x] 文件名含 `mcp`（MCPB 强制要求），因为仓库名 `smart-agri-eco` 不含 "mcp"

**当前 sha256**（2026-10-08 实测，已与 `server.json` / Registry 三方一致）：
```
390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24
```

> ⚠️ **该 sha 已发布到官方 Registry（2026-10-08 05:33:32Z，status=active）**。
> 上传 Release asset 时**必须用这个 sha**，否则客户端安装校验会失败。
> 若你必须重新构建 `.mcpb`，sha 会变 —— 需要同时更新 `server.json` 与 Registry 上的
> 旧版本（Registry 不允许同版本重复发布，需升版本号）。

### 你需要做的（3 步）

**Step 1 · 在 GitHub 创建 Release**
- 打开 https://github.com/lm203688/smart-agri-eco/releases/new
- Tag: `v1.1.0`（必须与 `server.json` 里的版本一致，因为下载 URL 依赖它）
- Title: `v1.1.0 · MCP 2026-07-28 适配 + A2A + Agent Plugins`
- 上传 `dist/agri-eco-mcp-1.1.0.mcpb` 作为 Release asset
- 发布

> ⚠️ 上传后**不要再改这个文件**——任何改动都会让 sha256 失效，客户端安装校验会失败。
> 若必须重新构建，改完跑 `python scripts/build_mcpb.py` 重新回填 sha 并重传。

**Step 2 · 安装并登录 `mcp-publisher`**

Windows（Git Bash）：
```bash
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_windows_amd64.tar.gz" | tar xz mcp-publisher
./mcp-publisher login github
```
（会打印一个 device code，浏览器打开 https://github.com/login/device 输入即可）

**Step 3 · 发布**

```bash
./mcp-publisher publish
```

成功后会看到：
```
✓ Successfully published
✓ Server io.github.lm203688/agri-eco version 1.1.0
```

验证：
```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=agri-eco"
```

### `server.json` 内容（已在仓库根目录，无需你手写）

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.lm203688/agri-eco",
  "title": "智慧农业生态 Agri-Eco",
  "version": "1.1.0",
  "repository": {
    "url": "https://github.com/lm203688/smart-agri-eco",
    "source": "github"
  },
  "packages": [
    {
      "registryType": "mcpb",
      "identifier": "https://github.com/lm203688/smart-agri-eco/releases/download/v1.1.0/agri-eco-mcp-1.1.0.mcpb",
      "fileSha256": "390e977940676f856fc6c7fe9b7a4bb087f1abf6388a72ab01c917c10ef57b24",
      "transport": { "type": "stdio" }
    }
  ]
}
```

### 命名规则说明（易踩坑）

- `name` 字段是**反向 DNS**格式，用 GitHub 认证时**必须**以 `io.github.<你的用户名>/` 开头
- 本项目用户名是 `lm203688`，所以是 `io.github.lm203688/agri-eco`
- 若改用 DNS 认证（自定义域名前缀），需在域名下配置 `TXT` 记录，本项目不采用

---

## 2. Glama

### 提交方式
- **一键提交流程**：访问 Glama 的"Submit new server"表单（https://glama.ai/mcp/servers 页面右上角），按下方字段填入即可
- **备选**：Glama 从公开仓库自动抓取，仅需注册后认领

### 表单字段映射（可直接复制粘贴）

| 表单字段 | 填写内容 |
|---|---|
| Server Name | `agri-eco` |
| Repository URL | `https://github.com/lm203688/smart-agri-eco` |
| Description | 见上方「完整描述」 |
| Categories | `Agriculture`, `Data`, `Science`, `Environment` |
| Transport | `stdio` |
| Install Command | 见上方「安装配置」 |
| License | MIT（代码） |
| Author / Owner | `lm203688` |
| Tags | `agriculture`, `agritech`, `environment`, `data`, `science`, `offline-first`, `zero-dependency` |
| Additional Info | `14 MCP tools · A2A v1.0 Agent Card · Agent Plugins 1.0.0 · Env Recipe protocol · Official MCP Registry: io.github.lm203688/agri-eco v1.1.0` |

### 需要你做的
- [ ] 访问 https://glama.ai/mcp/servers 提交表单
- [ ] 提交后确认 Glama 抓取到 14 个工具（Glama 会解析 `mcp/server.py`）
- [ ] 认领后 URL 通常为 `https://glama.ai/mcp/servers/agri-eco`（用于 README 顶部横幅）

---

## 3. LobeHub MCP

### 提交方式
- **站内提交**：访问 https://lobehub.com/mcp 页面，右上角"Submit MCP Server"入口
- **PR 路径**：向 LobeHub 官方 MCP 市场仓库提 PR（字段名可能与其最新 schema 略有差异，提交时按表单提示为准）

### 需要新增的条目（按其仓库现有格式）
```json
{
  "identifier": "agri-eco",
  "author": "lm203688",
  "homepage": "https://github.com/lm203688/smart-agri-eco",
  "description": "面向分布式农业的 Agent-native 知识基座：可执行 Env Recipe 环境配方 + 多源气候校准 + WOFOST 物候播期 + 数据血缘溯源。零依赖可离线，MCP 2026-07-28 无状态。",
  "tags": ["agriculture", "agritech", "environment", "data", "science", "offline-first", "zero-dependency"],
  "install": {
    "type": "stdio",
    "command": "python",
    "args": ["mcp/server.py"]
  }
}
```

### 需要你做的
- [ ] 按其仓库最新 schema 调整字段名（可能与我给的略有差异，以其表单为准）
- [ ] 提 PR 或用站内提交入口
- [ ] 提交后 LobeHub 上可搜索 `agri-eco`

---

## 4. Smithery

### 提交方式（本项目走自动发现路径）

**`smithery.yaml` 已就绪**（仓库根目录，2026-10-08 新增）。Smithery 会直接从公开仓库抓取该文件生成服务器条目，无需填提交表单。

- 抓取入口：https://smithery.ai/search?q=agri-eco 或 https://smithery.ai/search?q=smart-agri-eco
- 首次抓取可能需要几分钟到几小时同步

### 需要你做的
- [ ] 访问 https://smithery.ai，站内搜索 `agri-eco`；若未出现，使用页面"Submit Server"填仓库地址 `https://github.com/lm203688/smart-agri-eco`
- [ ] 确认 Smithery 页面显示 14 个工具（Smithery 会解析 `mcp/server.py` 的 TOOLS 声明）
- [ ] 认领后 URL 通常为 `https://smithery.ai/server/agri-eco`

### 若自动抓取失败
用如下 `startCommand` 字段提交（等价于仓库根目录的 `smithery.yaml`）：

```yaml
startCommand:
  type: stdio
  command: python
  args:
    - mcp/server.py
```

---

## 提交后的验收清单

- [ ] 4 个市场搜索 `agri-eco` 或 `agriculture mcp` 均可见
- [ ] 从任一市场按指引安装后，`tools/list` 返回 **14** 个工具
- [ ] README 顶部横幅链接可从市场页跳转（回填到 `README.md` 顶部）
- [ ] **出现第 1 次非本人外部调用**（P0 出口指标）

## 分发就绪度自检（推荐每次评审前跑一次）

```bash
python scripts/check_distribution_readiness.py
```

一次性验证 10 类分发入口：MCP server / A2A Card / Agent Plugin / Smithery 自动发现 /
官方 Registry 元数据 / MCPB 包 / CI workflow / Demo 部署 / 市场材料 / GitHub 同步。
非零退出即视为分发链路不可上线。

## 若某家市场要求补充材料，可直接引用

| 材料 | 位置 |
|---|---|
| Agent Card（A2A v1.0） | `.well-known/agent.json` |
| Plugin 清单（Agent Plugins 1.0.0） | `plugin/plugin.json` |
| MCP 配置 | `plugin/mcp.json` |
| Skill 说明（11 份 SKILL.md） | `plugin/skills/*/SKILL.md` |
| Smithery 自动发现清单 | `smithery.yaml` |
| 官方 Registry 元数据 | `server.json` |
| MCPB 分发包 | `dist/agri-eco-mcp-1.1.0.mcpb` |
| 协议合规说明 | `mcp/README.md` §协议合规 |
| 分发就绪度自检 | `scripts/check_distribution_readiness.py` |
| 项目定位与边界 | `docs/CORE_OBJECTIVE.md` |
| 定价策略（服务型收费） | `docs/pricing_strategy_2026-09-30.md` |
| 数据血缘 | 调用 `agri_query_lineage` 工具 |
