# QUICKSTART · 15 分钟上手

> **目标**：从空机器到本地成功调用 `agri_match_zone`，15 分钟内完成。
> **前提**：Python ≥ 3.10，**零第三方依赖**（只吃标准库）。
> **范围**：只覆盖 MCP stdio 直连路径；如需 Claude Desktop / Cursor 集成，看 §5。

---

## 1. 克隆与校验（1 分钟）

```bash
git clone https://github.com/lm203688/smart-agri-eco.git
cd smart-agri-eco
python --version            # 需要 3.10 / 3.11 / 3.12
```

本项目**零第三方依赖**，无需 `pip install`，无需 venv。若你在 Windows 且 `python` 指向商店的 Python，改用 `py -3.12`。

---

## 2. 30 秒验证内核（1 分钟）

```bash
# 一条命令跑完整 MCP 自测：initialize + tools/list + tools/call
python scripts/test_mcp_server.py
```

看到 `OK` / exit code 0 即代表 server 可拉起、23 个工具全部可解析。

---

## 3. 直接以 stdio 方式调用（3 分钟）

MCP 是 JSON-RPC 2.0 over stdio。手动调用一条：

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python mcp/server.py
```

会返回 23 个工具的 JSON 列表。要**调一个工具**（以 `agri_match_zone` 为例，杭州）：

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"agri_match_zone","arguments":{"lat":30.27,"lon":120.15}}}' \
  | python mcp/server.py
```

响应关键字段：
- `zone_id` — 分区标识（如 `subtropical_wet`）
- `zone_name` — 中文名
- `adapt_score` — 与主粮作物的适配度 0-1
- `_trust_mark` — SHA256 内容指纹，可独立复算

---

## 4. 用 examples/ 跑通 5 个真实场景（10 分钟）

```bash
python examples/01_match_zone.py        # 经纬度 → 分区
python examples/02_recommend.py         # 城市 → 推荐作物
python examples/03_diagnose.py          # 症状 → 病虫害诊断
python examples/04_recipe.py            # 配方检索 + 加载 + 对比
python examples/05_counterfactual.py    # 反事实轨迹（机理内核仿真）
```

每个脚本都用 `mcp.server.TOOLS` + 内部 `_tool_*` 函数**直调**，无需起子进程；这也是你未来在自己代码里接入本项目最快的方式。

---

## 5. 集成到 Claude Desktop / Cursor（可选，5 分钟）

编辑 `claude_desktop_config.json`（或 Cursor 的 MCP 配置）：

```json
{
  "mcpServers": {
    "agri-eco": {
      "command": "python",
      "args": ["C:/绝对路径/smart-agri-eco/mcp/server.py"]
    }
  }
}
```

macOS / Linux 把路径改成 `/home/user/.../mcp/server.py`。重启客户端，就能在对话中让 LLM 自主调用这 23 个工具。

---

## 6. 常见错误

| 症状 | 原因 | 修法 |
|---|---|---|
| `ModuleNotFoundError: agent` | 在 `mcp/` 目录下运行，找不到项目根 | 从项目根运行；或在脚本开头 `sys.path.insert(0, ...)` |
| `agri_*: 参数错误 crop='xxx'` | 作物名不在 239 作物注册表内 | 用中文名或先跑 `examples/01_match_zone.py` 拿分区再选 |
| `_trust_mark.signature` 复算失败 | 数据被本地修改过 | 用 `git checkout -- .` 恢复；或跑 `python -m core.trust_layer verify` |
| MCP 客户端连不上 stdio | 路径含中文/空格 | 用引号包住 `"args": ["C:/path with space/智慧农业生态/mcp/server.py"]` |
| Windows 下 `python` 指向商店版 | Windows App Execution Alias | 用 `py -3.12` 代替 `python` |

---

## 7. 下一步

- 想看**每个工具的详细契约**（何时用 / 输入 / 返回示例）→ [`docs/TOOLS_REFERENCE.md`](TOOLS_REFERENCE.md)
- 想跑**评测基准**验证内核 → `python benchmarks/agri_recipe_bench/run_bench.py`
- 想加**新工具** → 参考 `mcp/server.py` 的 `TOOLS` 注册表与 `_tool_*` 命名约定
- 想接入**外部 Agent** → `.well-known/agent.json`（A2A v1.0 Card）+ `.well-known/mcp-card.json`（MCP Server Card）

---

*文档版本：2026-10-23 · 依赖范围：Python 3.10+ 标准库 · CI 门禁见 `.github/workflows/ci.yml`*
