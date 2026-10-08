# 智慧农业生态 · MCP Server（Agent-native 分发层）

零依赖的 Model Context Protocol Server，把本项目的农业知识引擎（气候分区 / 作物推荐 / 种植计划 / 病虫害诊断 / 养分管理 / Env Recipe 配方 / 物候播期 / 土壤剖面 / BP 投资初筛 / 多源气候调和 / 数据血缘 / 生态清单）以工具形式暴露给任意 MCP 客户端（Claude Desktop、Cursor、Codex、自研 Agent 等）。

- **零第三方依赖**：纯标准库 JSON-RPC 2.0 over stdio，协议版本 `2026-07-28`（无状态），兼容 `2025-06-18` / `2024-11-05`。
- **复用现有能力**：直接调用 `agent` 包，不重复实现业务逻辑。
- **战略定位**：评审将 MCP 定为「最强差异化赌注」且成本极低——这是与 SwarmLabs / aishield 同构的 Agent-native 分发路线，也是 P0-F「主动投递给外部 Agent 项目真实调用」的载体。

## 协议合规（MCP 2026-07-28 无状态规格）

| SEP | 要点 | 本 server 的实现 |
|---|---|---|
| SEP-2575 | 移除 `initialize` 握手 | `initialize` 仍响应（兼容旧客户端），但**非必需**：未握手直接 `tools/list` / `tools/call` 完整可用 |
| SEP-2567 | 移除 `Mcp-Session-Id` | 设计上无会话状态；`initialize` 显式返回 `"stateless": true` |
| SEP-2243 | 强制 `Mcp-Method` / `Mcp-Name` 头 | stdio 无 header，等价信息取自 JSON-RPC `method` / `params.name`；HTTP 形态下由 `_http_headers_ok()` 强制校验 |
| SEP-2549 | 缓存提示 `ttlMs` / `cacheScope` | `tools/list` 返回 `ttlMs=2592000000`（30 天，配方为季度级数据）、`cacheScope=public`；`tools/call` 返回 `ttlMs=60000`（含在线取数，不做长缓存） |
| SEP-414 | W3C Trace Context | 接受请求 `_meta.traceparent`，校验形态后透传进审计日志并**原样回写**响应 `_meta`，支持跨 Agent 串链 |

## 启动（stdio）

```bash
python mcp/server.py
```

MCP 客户端以 stdio 子进程方式拉起本文件即可。

## 注册到 Claude Desktop（示例）

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "agri-eco": {
      "command": "python",
      "args": ["/绝对路径/智慧农业生态/mcp/server.py"]
    }
  }
}
```

也可直接用 Agent Plugins 清单（`plugin/mcp.json`），支持 Agent Plugins 1.0.0 的客户端会自动读取。

## 暴露的工具（14 个）

| 工具 | 说明 |
|---|---|
| `agri_list_cities` | 预设城市（经纬度 + 气候带） |
| `agri_match_zone` | 经纬度 → 气候分区匹配 |
| `agri_recommend_crops` | 分区 + 偏好 → 作物推荐 |
| `agri_growth_plan` | 作物 + 场景 + 分区 → 种植计划 |
| `agri_diagnose_pest` | 症状/图像 → 病虫害与营养缺乏诊断 |
| `agri_nutrition_plan` | 作物 + 阶段 → 养分管理方案 |
| `agri_env_recipe` | 作物 + 阶段 + 设备类 → Env Recipe v1 合规配方（P0-G 落地） |
| `agri_season_advisory` | 作物 + 分区 + 气候输入 → 积温物候 + 霜冻锚定播期窗口 |
| `agri_soil_profile` | 分区 → 土壤剖面（在线 SoilGrids 优先，失败降级离线分区均值） |
| `agri_bp_screen` | BP/审计/流水文本 → 农业项目投资初筛（六分类 + 五闸 + 六评分卡 + 一票否决） |
| `agri_reconcile_climate` | 经纬度 → NASA POWER + Open-Meteo 多源调和 + 逐月一致度与分歧告警 |
| `agri_resolve_recipe` | 城市名/经纬度 → 分区 → 该分区 Env Recipe 清单（完全离线） |
| `agri_query_lineage` | 按作物/分区查数据溯源（外部 API 参与 + 本地 SHA256 指纹 + 校准实证） |
| `agri_list_ecosystem` | 对接的开源/商业生态清单与对接状态 |

## 自测

```bash
python scripts/test_mcp_server.py
```

会以子进程方式对 server 发送 `initialize` / `tools/list` / `tools/call` 并断言响应，退出码 0 表示通过。

## 分发入口（三协议并存）

同一份能力通过三条开放通道暴露，各自有独立清单文件，互相不漂移（CI 门禁）：

| 协议 | 清单文件 | 校验命令 |
|---|---|---|
| MCP 2026-07-28 | `mcp/server.py` | `python scripts/test_mcp_server.py` |
| A2A v1.0 | `.well-known/agent.json` | `python scripts/check_agent_card.py` |
| Agent Plugins 1.0.0 | `plugin/plugin.json` + `plugin/mcp.json` + `plugin/skills/*/SKILL.md` | `python scripts/build_agent_plugin.py --check` |

## P0-F 外部投递模板（主动找真实调用方）

> 目标：MCP server 上线后，主动投递给 5-10 个农业 / 开发者 Agent 项目真实调用，验证「Agent-native 分发」这个核心赌注是否真有人接。对标 aishield 上架 Glama / npm 的打法。

```
主题：开源农业 MCP server · 求真实调用 / 反馈

Hi <项目维护者>,

我们在做「智慧农业生态」——一个把全球农业知识（气候分区/作物适配/病虫害/Env Recipe 配方）
做成 Agent 可调用工具的项目。已发布零依赖 MCP server（协议 2024-11-05）：

  - 14 个工具：分区匹配 / 作物推荐 / 种植计划 / 病虫害诊断 / 养分管理 / Env Recipe 配方 / 物候播期 / 土壤剖面 / BP 投资初筛 / 多源气候调和（带偏差校正）/ 地理编码→配方 / 数据血缘查询 / 预设城市清单 / 生态对接清单
  - 覆盖 8 个气候分区（新增 hot_arid 高温沙漠 / highland 高原）与 116 份可执行 Env Recipe
  - 纯标准库，stdio 拉起，可直接接 Claude Desktop / Cursor / 自研 Agent
  - 仓库：https://github.com/lm203688/smart-agri-eco  （mcp/ 目录）

如果你在做农业 / IoT / 种植类 Agent，欢迎直接 `python mcp/server.py` 试调，
或把你的使用场景告诉我，我们按需补工具。也在找 AeroGarden 等「孤儿设备」社区的配方自救合作。

谢谢！
```

**决策门**：投递后 3 个月内若 **零外部调用方** → 说明 Agent-native 分发当前市场未熟，降级为个人知识库项目，停止对外投入（评审 §3.5）。
