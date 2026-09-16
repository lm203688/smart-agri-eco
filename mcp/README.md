# 智慧农业生态 · MCP Server（Agent-native 分发层）

零依赖的 Model Context Protocol Server，把本项目的农业知识引擎（气候分区 / 作物推荐 / 种植计划 / 病虫害诊断 / 养分管理 / Env Recipe 配方 / 物候播期 / 土壤剖面）以工具形式暴露给任意 MCP 客户端（Claude Desktop、Cursor、Codex、自研 Agent 等）。

- **零第三方依赖**：纯标准库 JSON-RPC 2.0 over stdio，协议版本 `2024-11-05`。
- **复用现有能力**：直接调用 `agent` 包，不重复实现业务逻辑。
- **战略定位**：评审将 MCP 定为「最强差异化赌注」且成本极低——这是与 SwarmLabs / aishield 同构的 Agent-native 分发路线，也是 P0-F「主动投递给外部 Agent 项目真实调用」的载体。

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

## 暴露的工具

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

## 自测

```bash
python scripts/test_mcp_server.py
```

会以子进程方式对 server 发送 `initialize` / `tools/list` / `tools/call` 并断言响应，退出码 0 表示通过。

## P0-F 外部投递模板（主动找真实调用方）

> 目标：MCP server 上线后，主动投递给 5-10 个农业 / 开发者 Agent 项目真实调用，验证「Agent-native 分发」这个核心赌注是否真有人接。对标 aishield 上架 Glama / npm 的打法。

```
主题：开源农业 MCP server · 求真实调用 / 反馈

Hi <项目维护者>,

我们在做「智慧农业生态」——一个把全球农业知识（气候分区/作物适配/病虫害/Env Recipe 配方）
做成 Agent 可调用工具的项目。已发布零依赖 MCP server（协议 2024-11-05）：

  - 9 个工具：分区匹配 / 作物推荐 / 种植计划 / 病虫害诊断 / 养分管理 / Env Recipe 配方 / 物候播期 / 土壤剖面
  - 纯标准库，stdio 拉起，可直接接 Claude Desktop / Cursor / 自研 Agent
  - 仓库：https://github.com/lm203688/smart-agri-eco  （mcp/ 目录）

如果你在做农业 / IoT / 种植类 Agent，欢迎直接 `python mcp/server.py` 试调，
或把你的使用场景告诉我，我们按需补工具。也在找 AeroGarden 等「孤儿设备」社区的配方自救合作。

谢谢！
```

**决策门**：投递后 3 个月内若 **零外部调用方** → 说明 Agent-native 分发当前市场未熟，降级为个人知识库项目，停止对外投入（评审 §3.5）。
