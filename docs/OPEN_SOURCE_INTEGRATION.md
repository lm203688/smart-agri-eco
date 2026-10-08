# 开源生态对接指南（OPEN_SOURCE_INTEGRATION）

> 目标：对照 `docs/planning/项目战略指引.md` 的**七层农业 AI 生态架构**，通过「开源市场扫描 + 自研」补齐各层生态位。
> 本文件是**操作手册**——自研部分已落地（见 §2），**需要你配合的三项操作在 §3（带链接分步）**。

---

## 1. 七层架构 × 生态位补全映射

| 层级 | 生态位缺口 | 补全来源 | 类型 | 状态 |
|------|-----------|---------|------|------|
| L0 | 数据底座（8 分区已闭环） | 自研 + NASA POWER / Open-Meteo / SoilGrids / GBIF | 自研 | ✅ 已闭环 |
| L1 | 感知：叶片病害视觉诊断 | **PlantVillage 视觉权重**（HuggingFace，离线 ONNX） | 开源对接 | 🟡 需你配置后端（§3.2） |
| L2 | 模型 AI：伴生/轮作/虫害情报 | **`@cropgraph/mcp`**（18 工具，离线 stdio） | 开源对接 | 🟡 需你启用连接器（§3.1） |
| L2 | 模型 AI：采收期/产量/风险预测 | **ForecastAgent**（GDD-lite 启发式，诚实标注） | 自研 | ✅ 已落地 |
| L3 | 执行控制：生长计划→硬件指令 | **ControlAgent**（actuator intents + 执行补偿） | 自研 | ✅ 已落地 |
| L4 | 业务支撑：链路数据/鲜度中枢 | **`data/linkage_protocol.schema.json`**（开源链路协议） | 自研 | ✅ 已落地 |
| L5 | 消费服务：认证溯源 | 依赖 L4 链路数据；消费端待对接 | 规划 | ⚪ 规划中 |
| L6 | 运营生态：社区/数据市场 | 反馈闭环 flywheel + MCP 分发 | 自研 | 🟡 进行中 |

**扫描中确认可用的开源资产（真实存在，已核验 2026-10-08）**：

| 资产 | 形态 | 链接 | 用途 |
|------|------|------|------|
| `@cropgraph/mcp` v3.2.0 | npm / MCP stdio | https://www.npmjs.com/package/@cropgraph/mcp · https://cropgraph.com | L2 伴生/轮作/虫害/GDD 情报（18 工具，离线，MIT） |
| PlantVillage 38-class ONNX | HuggingFace 权重 | https://huggingface.co/BiernyVR/crop-disease-classifier | L1 叶片病害分类（EfficientNetV2-S，ONNX 边缘部署，99.89% val） |
| PlantVillage 15-class MobileNetV3 | HuggingFace 权重 | https://huggingface.co/innocent11105/plantvillage-mobilenetv3 | L1 轻量分类（1.53M 参数，TorchScript/ONNX） |
| PlantVillage 数据集 | HuggingFace 数据集 | https://huggingface.co/datasets/GVJahnavi/PlantVillage_dataset | 自训练/微调底座 |

> 可选扩展（**非阻塞**，不在本轮强制项）：`CropProphEU`（产量/市场预测）、`TomorrowNow Decision Tree MCP`（气候决策树）、`WOFOST/AquaCrop/DSSAT`（PCSE 机制模型，已部分用 WOFOST 物候）。

---

## 2. 自研已落地（本轮，零第三方依赖）

- **`agent/forecast_agent.py`**（L2）：采收期（GDD-lite 积温累算）/ 产量（基准×气候×适配×光照）/ 风险（霜冻/高温/计划）预测；`confidence.model="heuristic"` 诚实标注，未知作物安全回退。技能 `harvest_forecast`。
- **`agent/control_agent.py`**（L3）：生长计划→硬件无关 actuator intents（灌溉/施肥/补光/气候/CO₂/风机）+ `needs_gateway` 网关标记 + 车载颠簸/开放环境/设备故障执行补偿。技能 `control_commands`。
- **`data/linkage_protocol.schema.json`**（L4）：开源标准链路数据（batch→product→7 环节三元组 + 鲜度/损耗/货架期模型），支撑 L5 认证溯源。
- 接线 `agent/orchestrator.py`：两 Agent 注入 + `ONDEMAND_SKILLS` 加 `control_commands`/`harvest_forecast` + Verifier 加两分支守卫。
- 能力数字守卫未漂移：**MCP 14 工具 / 8 分区 / 116 作物·EnvRecipe / 12 闸** 全部锁定。

---

## 3. 需要你配合的三项操作（带链接分步）

> 这三项都不需要你写代码，但需要你在**自己的账号/环境**里点几下或贴一个临时文件。每一步都给了直达链接。

### 3.1 启用 CropGraph MCP 连接器（补全 L2 伴生/轮作/虫害情报）

让 WorkBuddy 把 `@cropgraph/mcp` 的 18 个农业工具接入本会话，PestAgent / 伴生规划 / 轮作建议即可调用真实策展数据。

**方式 A（推荐，改 WorkBuddy MCP 配置）**

1. 打开 WorkBuddy 的 MCP 配置文件：`C:\Users\xing\.workbuddy\mcp.json`（用记事本/VS Code 打开）。
2. 在 `mcpServers` 下新增一段（不要覆盖已有的 `laya` / 其他条目，只追加）：
   ```json
   "cropgraph": {
     "command": "npx",
     "args": ["-y", "@cropgraph/mcp"]
   }
   ```
3. 保存文件，**重启 WorkBuddy**。
4. 打开左侧「连接器」面板（左下角 `+` → 连接器管理），在自定义连接器里找到 `cropgraph`，点 **「信任」** 启用它。
5. 验证：在本会话输入「列出可用的 MCP 工具」，应能看到 `get_companions` / `get_rotation_advice` / `get_pest_intelligence` 等 18 个 cropgraph 工具。

**方式 B（WorkBuddy 连接器 UI）**

1. 打开连接器官理页（左下角 `+` → 连接器），右上角「自定义连接器」入口。
2. 新建一个 MCP 连接器，类型选 **stdio**，命令填 `npx`，参数填 `-y @cropgraph/mcp`，保存并信任。
3. 重启 WorkBuddy 后工具自动出现。

> 资源：npm https://www.npmjs.com/package/@cropgraph/mcp · 官网 https://cropgraph.com
> ⚠️ 该包走 `npx` 首次运行会下载（需联网一次），之后离线可用、无 API key。

---

### 3.2 配置视觉后端 `AGRI_VISION_*`（升级 L1 感知：从规则降级 → 真实视觉）

`agent/vision.py` 已支持可插拔视觉后端：**配置了就启用真实视觉诊断，没配置则规则降级**（不报错、不静默造假）。后端必须是 **OpenAI 兼容的 `/v1/chat/completions` 多模态端点**（图片进、文本出）。

**路径 A — 本地 Ollama 视觉模型（最简单、契合现有代码）**

1. 安装并启动 Ollama：https://ollama.com （你本机已装 Ollama，监听 `127.0.0.1:11434`）。
2. 拉一个视觉模型（任选其一）：
   ```bash
   ollama pull llava:13b      # 通用多模态
   ollama pull moondream      # 轻量视觉对话
   ```
3. 在项目根目录 `.env` 写（**不要提交**，已被 `.gitignore` 忽略）：
   ```bash
   AGRI_VISION_URL=http://127.0.0.1:11434/v1
   AGRI_VISION_KEY=ollama          # Ollama 不需要真 key，占位即可
   AGRI_VISION_MODEL=llava:13b
   ```

**路径 B — ATEX / OpenAI 兼容网关（README §3b-2 已写）**

1. 用你已有的 ATEX 网关（ECS `:8420/v1`）或 OpenAI `gpt-4o`，在 `.env` 填 `AGRI_VISION_URL` / `AGRI_VISION_KEY` / `AGRI_VISION_MODEL=gpt-4o`。

**路径 C — PlantVillage 离线权重（边缘/无网场景）**

1. 下载权重（选一个）：38-class ONNX https://huggingface.co/BiernyVR/crop-disease-classifier · 15-class https://huggingface.co/innocent11105/plantvillage-mobilenetv3
2. 用一个**OpenAI 兼容包装**把它暴露成 `/v1/chat/completions`（例如 FastAPI 包一层，或 llama.cpp + mmproj 跑视觉 LLM）。把 `AGRI_VISION_URL` 指向这个本地端点即可。
   > 注意：PlantVillage 是「分类器」不是「对话模型」，直接喂 `agent/vision.py` 需要一层 OpenAI 兼容适配；若不想自己包，路径 A 的 Ollama 视觉模型开箱即用。

**验证（任一路径）**：`.env` 配好后重跑 `python scripts/verify_all.py`，PestAgent 视觉分支应走真实后端；没配则仍是规则降级（属预期，非故障）。

---

### 3.3 提供 fine-grained PAT（推送 v0.9-beta + 打 tag）

本目录**不是 git clone**（github.com:443 被封），统一走 `scripts/gh_push.py`（GitHub Contents API）推送。打 `v0.9-beta` tag 需要一次性的 fine-grained PAT。

**步骤（你的 GitHub 账号操作）**

1. 打开 PAT 创建页：https://github.com/settings/personal-access-tokens/new
2. 填：
   - **Token name**：`smart-agri-eco-push`（随意）
   - **Expiration**：选 `7 days`（临时，用完即删）
   - **Repository access**：选 `Only select repositories` → `lm203688/smart-agri-eco`
   - **Permissions → Repository permissions**：
     - `Contents` = **Read and write**
     - `Workflows` = **Read and write**（CI 要能改 workflow）
3. 点 **Generate token**，把那串 `github_pat_xxx` **完整复制**。
4. 把 token 存成本机临时文件（不要贴进聊天、不要进 git）：
   ```bash
   # 例如在项目根目录新建一个临时文件
   notepad C:\Users\xing\Desktop\智慧农业生态\.pat_tmp.txt
   # 把 github_pat_xxx 粘进去，保存，关闭
   ```
5. 告诉我「PAT 已就绪」，我会跑：
   ```bash
   python scripts/gh_push.py .pat_tmp.txt "feat: L2/L3/L4 生态位补全 + 工程化收尾 (v0.9-beta)" <文件清单>
   ```
   推送后**自动回读校验**，确认 success 后你删掉 `.pat_tmp.txt` 即可。

> 仓库：https://github.com/lm203688/smart-agri-eco
> ⚠️ 安全红线：PAT 只过本地临时文件，**绝不**出现在聊天/代码/commit 里；用完即删。当前仓库已有多次明文暴露教训，建议本轮用新 fine-grained PAT（旧 classic `ghp_` 建议轮换）。

---

## 4. 能力数字守卫（不可改，写进测试锁死）

以下数字由 `scripts/test_engine_v5.py::TestDocCapabilityNumbersInSync` 实算并反向守卫，**任何扩张后不改 README / mcp/README / app/index.html 即回归红**：

| 数字 | 含义 |
|------|------|
| **14** | MCP 工具数（零依赖 JSON-RPC stdio） |
| **8** | 农业分区数（含 hot_arid / highland） |
| **116** | 作物数 = Env Recipe 配方数 |
| **12** | bp_screen 投资初筛闸数 |

本轮新增的 ForecastAgent / ControlAgent 是 **Agent 层 call_skill 技能**（不计入 MCP 工具数），harness 技能数 9→11（已 `harness_sync.py init` 重新同步，指纹 `7f38ac4044332826`），上述 4 个锁定数均未变。

---

## 5. 待你拍板（阻塞项外的决策）

- **A. 发 `v0.9-beta` tag** —— 需 §3.3 的 PAT 到位后我执行。
- **E. 视觉后端选型** —— §3.2 三路径你定（推荐路径 A 本地 Ollama，零成本）。
- **F. WorldClim 2.1 栅格管道** —— numpy/rasterio 与零依赖冲突，待定。
- **1db296e6 命名易混淆** —— 「AOCI 每日治理校验」实为 swarmlabs/算力共享平台 校验，是否改名/退役待你定（未擅改）。
