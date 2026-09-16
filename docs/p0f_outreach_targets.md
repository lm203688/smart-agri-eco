# P0-F / P0-G 外部投递目标清单

> 编制日期：2026-09-05｜候选均经联网核实（名称/链接/定位以检索结果为准，未编造）
> 用途：评审 §3.2 P0-F（MCP 真实调用方）与 P0-G（Env Recipe 协议社区触达）的执行清单
> 决策门：投递后 3 个月内零外部调用 / 零社区响应 → 降级为个人知识库项目

## 〇、关键时间窗事实（投递叙事的核心钩子）

- WIRED 证实：**AeroGarden 于 2025-01-01 停止运营，Wi-Fi App 承诺仅维护至 2026 年 3 月**——**该期限已过**。数百万 Wi-Fi 机型的云端"大脑"已死，设备本身（灯/泵定时器）还在转。孤儿设备自救需求处于历史最强窗口。
- GitHub 上 `dalinicus/homeassistant-aerogarden`（HACS 集成）已于 2024-10 因 AeroGarden 停运归档；`jacobdonenfeld/homeassistant-aerogarden` 为接续维护 fork——**它同样依赖已死的 AeroGarden 云 API**。这正是 Env Recipe「离线配方大脑」的切入叙事。

## 一、MCP 分发目录上架（自服，低成本先做）

| 渠道 | 说明 | 动作 |
|---|---|---|
| Glama（glama.ai/mcp/servers） | aishield 已上架，流程熟悉 | 复用 aishield 打法提交 `mcp/server.py` |
| Smithery / PulseMCP | 主流 MCP 目录 | 提交（各需账号） |
| mcpworld.com / mcphub.com / lobehub.com / himcp.cn | 检索中发现的活跃 MCP 目录（同类园艺 server 均在此收录） | 提交收录 |

## 二、直接投递目标（农业/种植 MCP 项目，均真实存在）

| # | 项目 | 定位（已核实） | 与本项目关系 | 切入点 | 优先级 |
|---|---|---|---|---|---|
| 1 | `avlihachev/mcp-garden` | 园艺 MCP：天气预报/霜冻警报/土壤数据/灌溉需求（Open-Meteo + **SoilGrids** + sunrise-sunset），MIT，Node | **高度互补**：它有环境数据、无作物知识与配方 | 提案交叉引用/互补安装：它管环境数据，我们管「种什么+怎么种」（Env Recipe + 诊断）；且我们已核实 SoilGrids API 在中国网络不可达，可提数据源备选建议 | ★★★ |
| 2 | `drewherron/mcp-kasvanta` | 花园管理 MCP：SQLite 持久记录植物/位置/活动历史，MIT，Python | **天然配对**：它记录「你做了什么」，我们生成「该做什么」 | 提案：kasvanta 的活动日志对接 Env Recipe 的 `execution_log`/`outcome` 字段，共同补全配方→执行→结果闭环（独占数据 A） | ★★★ |
| 3 | `jacobdonenfeld/homeassistant-aerogarden` | AeroGarden HA 集成（接续维护，依赖已死云 API） | **P0-G 核心目标**：孤儿设备的软件层 | GitHub issue/PR：提案集成 Env Recipe 离线配方大脑（`device_class: aerogarden_orphan`），云死之后设备仍有决策层；附协议规范链接 | ★★★ |
| 4 | `eagleisbatman/gap-agriculture-mcp` | TomorrowNow GAP 天气情报 MCP（东非），StreamableHTTP，对接 OpenAI Agent Builder | 互补：天气智能 vs 农艺知识 | 提案工具互补/互引；学习其 StreamableHTTP 传输实现（我们当前 stdio） | ★★ |
| 5 | `omardaaboul/microfarm-mcp` | 地块微型农场可行性评估 MCP（气候/水/洪泛/土地），Python stdio，证据驱动叙事与我们同调 | 互补：选址评估 vs 种植执行 | 互引；其 "evidence-backed, never invented" 原则与我们 AgriTrust 一致，适合联合叙事 | ★★ |
| 6 | `day-in-the-country-llc/garden-mcp-server` | 园艺 MCP：天气/Plant.id 识别/床位规划，GPL-3.0，fastMCP | 互补；**注意 GPL-3.0 传染性**，只互引不合并代码 | 互引 + Plant.id 识别能力交流（我们走 PlantVillage 冷启动 + 中文图像） | ★ |
| 7 | kizniche/MyCodo（备选） | 老牌开源环境控制系统（树莓派），Star 数与现状**未单独核验** | 互补：硬件控制器 vs 配方大脑 | 核验后再投递 | ★ |

## 三、AeroGarden 孤儿设备社区（P0-G 触达）

| 社区 | 事实 | 动作 | 谁来做 |
|---|---|---|---|
| r/AeroGarden（subreddit，1万+ 订户） | AeroGarden 品牌设备主社区，氛围互助、反带货（需 mod 审批推广位） | 发 Env Recipe 自救帖（配 WIRED 时间线 + 协议链接）；严禁 affiliate 链接（社区明令禁止） | **用户**（Reddit 中国网络不可直连且需账号） |
| homeassistant-aerogarden（GitHub） | 见上表 #3 | issue/PR | **AI**（待 PAT 提供 GitHub 登录后可直接发 issue，文稿已备） |
| Click & Grow / Gardyn 等在位者社区 | WIRED 提及的替代品牌，同样配方层薄弱 | 二批触达 | 用户 |

## 四、投递文案

MCP 项目投递文案：见 `mcp/README.md`「P0-F 外部投递模板」。
AeroGarden HA 集成 issue 草稿（发 issue 时直接粘贴）：

> **标题**：Proposal: offline "recipe brain" for orphaned AeroGarden Wi-Fi units (Env Recipe protocol)
>
> Hi — thanks for maintaining this integration after the shutdowns upstream.
>
> AeroGarden ceased operations 2025-01-01 and the Wi-Fi app was only promised until March 2026, so the cloud brain of these units is now gone. We maintain an open protocol, **Env Recipe v1**, that gives any planter an offline, machine-readable decision layer: crop × stage × device → temperature/humidity/PPFD/EC/pH/watering params as JSON (schema + 110 pre-generated recipes included, CC-BY-4.0).
>
> Repo: https://github.com/lm203688/smart-agri-eco (see `docs/env_recipe_protocol_v1.md`, `schemas/env_recipe.schema.json`, `mcp/server.py` for MCP tooling).
>
> Would you be interested in an integration path where HA serves Env Recipes to AeroGarden units locally, replacing the dead cloud logic? Happy to open a PR sketch. The schema also reserves `execution_log`/`outcome` fields so every run can feed a shared open dataset — something the orphan-device community could own together.

## 五、执行顺序建议

1. （AI，零成本）MCP 目录上架材料整理 → 等用户在 Glama/Smithery 建号或提供 PAT 后提交。
2. （AI，待 PAT）向 #1/#2/#3 发 GitHub issue（文稿已备）。
3. （用户）r/AeroGarden 帖子发布。
4. 记录每次投递时间与响应，进 `docs/intel_log.md`；3 个月决策门倒计时自首次投递起算。
