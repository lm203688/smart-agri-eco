# 智慧农业生态 · 全球分区农业 AI 助手

> 以数据平台分析为基座，孵化多层级农业 AI 关键节点生态

---

## 项目定位

**一句话**：做分布式农业的 AI 操作系统与数据网络——回答「在哪里种什么、怎么种得好、怎么送到消费者」。

**核心架构（对标 SwarmLabs 科研 Agent Infra 的工程路径）**：

```
输入（地块信息 / 种植者需求 / 环境参数）
  │
  ▼
┌──────────────────────────────────────────────────────────┐
│  L0  数据底座层   全球分区气候/土壤/水文元数据               │
│    └─ data/zone_meta/ (Köppen 气候带 + FAO 农业分区)      │
├──────────────────────────────────────────────────────────┤
│  L1  多 Agent 协同层                                      │
│    ├─ ClimateAgent  气候/水文/土壤分区匹配                  │
│    ├─ CropAgent     作物-分区适配推荐                       │
│    ├─ GrowthAgent   生长周期管理 + 病虫害诊断               │
│    └─ EcoAgent      多层级生态撮合（供需/社区/设备）        │
├──────────────────────────────────────────────────────────┤
│  L2  Skill 注册表   可复用能力模块                         │
│    └─ skills/registry/ (climate_match / crop_adapt / ...) │
├──────────────────────────────────────────────────────────┤
│  L3  可信输出层  evidence + confidence + constraints        │
│    └─ docs/agent_output_contract.md                       │
└──────────────────────────────────────────────────────────┘
```

---

## 七层生态架构（来自项目战略指引）

| 层级 | 名称 | 关键节点 | 本项目状态 |
|------|------|---------|-----------|
| L6 | 运营生态 | 社区/城市合伙人/数据市场 | 规划中 |
| L5 | 消费服务 | 采摘即食/本地撮合/认证溯源 | 规划中 |
| L4 | 业务支撑 | 链路数据/鲜度中枢/损耗预测 | 规划中 |
| L3 | 执行控制 | 水肥一体化/环境调控/执行补偿 | 进行中（水肥一体化已落地 NutritionAgent） |
| L2 | 模型 AI | 生长模型/病虫害/决策引擎/世界模型 | ★ 当前重点 |
| L1 | 感知层 | 传感器/摄像头/边缘AI | 规划中 |
| L0 | 数据底座 | 气候/土壤/水文/光照 | ★ 当前重点 |

---

## 核心模块

| 模块 | 路径 | 用途 |
|------|------|------|
| 多 Agent 协同框架 | `agent/` | 气候/作物/生长/生态四 Agent + 病虫害(PestAgent) + 养分(NutritionAgent) 按需调用 |
| 统一编排器 | `agent/orchestrator.py` | 四 Agent 流水线（run_pipeline）+ call_skill 按需技能路由 + 技能目录（list_skills） |
| 农业分区数据 | `data/zone_meta/` | 全球农业分区元数据 |
| Skill 注册表 | `skills/registry/` | 可复用农业 AI 能力 |
| 可信输出契约 | `docs/agent_output_contract.md` | 每条建议的证据/置信度/适用条件 |
| 项目评估 | `docs/project_evaluation.md` | 评审维度逐项自评 |
| 战略指引 | `项目战略指引.md` | 七层架构与商业设计 |
| 执行方案 | `项目执行方案.md` | 分阶段路线图 |
| 反馈闭环引擎 | `engine/flywheel.py` | 种植结果回流 → 适配评分校准（主动学习） |
| 交互式 Demo | `app/` | 零依赖 http.server 站点：坐标 → 四 Agent 方案 + AgriTrust 证书 |
| 数据扩展脚本 | `scripts/enrich_crop_data.py` | 每气候带补充适生作物至 ≥18 种 |
| 端到端验证 | `scripts/verify_all.py` | 多城市 pipeline + Trust 证书 PASS/FAIL |
| Skill 自动生成 | `engine/skill_factory.py` | 新作物/能力点 → 自动生成符合 Schema 的 Skill |
| 单元测试 | `scripts/test_agents.py` | 26 项 unittest（零依赖），覆盖四 Agent + PestAgent + NutritionAgent + Orchestrator 统一路由 + 视觉后端降级 + Trust + flywheel + **作物库数据完整性守卫** |
| 预览残留清理 | `scripts/clean_preview_artifacts.py` | 清除预览工具注入 HTML 的 `data-page-node-id` 属性（曾一次性注入 115 处） |
| 演示数据重置 | `scripts/clean_demo_data.py` | 清空 demo/单测污染的 feedback_log + 剥离作物库假校准标记 |
| 同步状态检查 | `scripts/sync_check.py` | 本地工作区 vs GitHub main 逐文件 blob sha 比对（本仓非 git clone，无法用 git status） |
| 反馈回流 CLI | `scripts/submit_feedback.py` | 内测用户提交种植结果 → 校准 adapt_score |
| 生产部署 | `deploy/` | 一键部署（`deploy_local.sh` 上传 + `setup_ecs.sh` 远端构建启动）+ nginx 反代 + DEPLOY.md |
| CI | `.github/workflows/ci.yml` | push 自动跑单测/verify/trust/flywheel/数据自检，Python 3.10-3.12 矩阵 |

---

## 工程路径（对标 SwarmLabs）

| SwarmLabs 做法 | 农业项目映射 |
|----------------|------------|
| `traceability.py`（可追溯层） | 每条种植建议的溯源链（数据来源+分区依据+作物研究） |
| `trust_layer.py`（可复现证书） | 农业建议的可信度评分（rubric + 数据覆盖度） |
| `skills/registry/`（机读注册表） | 农业 Skill 的 JSON Schema 注册表 |
| `docs/agent_output_contract.md` | 农业可信输出契约 |
| `engine/flywheel.py`（飞轮主循环） | ✅ 已落地：record_feedback() 校准 adapt_score，闭环生效 |

---

## 快速验证

```bash
# 查看农业分区数据
python -c "import json; d=json.load(open('data/zone_meta/global_zones.json')); print(len(d))"

# 查看 Skill 注册表
for f in skills/registry/*.json; do python -c "import json; s=json.load(open('$f')); print(s['id'])"; done
```

---

## 数据卫生（重要）

`engine/flywheel.py` 的 `record_feedback()` **真的会写盘**——这是为了让反馈闭环真实生效。
代价是：demo 与单测如果不隔离，就会把合成样本混进真实数据。本项目已踩过的两类事故及防护：

| 事故 | 现象 | 防护 |
|---|---|---|
| 单测污染反馈日志 | `data/feedback_log.json` 累积 12 条 `unittest`/`smoke` 样本，制造「已有真实数据回流」的假象 | 单测把 `AGRI_FEEDBACK_LOG` 重定向到临时文件 |
| 作物库假校准标记 | 34 个作物只有 `calibrated: true` 却**零校准证据**，被可信层当成实测数据透出 | `scripts/clean_demo_data.py` 清洗 + CI/单测双门禁 |

规则：

1. **`data/feedback_log.json` 只允许真实用户反馈**。demo 记录带 `[demo]` 前缀，门禁会拦截未标注的合成数据。
2. **`python -m engine.flywheel` 跑过之后**，提交前必须执行：
   ```bash
   python scripts/clean_demo_data.py --dry-run   # 先看会清多少
   python scripts/clean_demo_data.py             # 实际清理
   ```
3. **隔离运行**（不碰仓库数据）：
   ```bash
   AGRI_CROP_DB=<绝对路径>/crop.json AGRI_FEEDBACK_LOG=<绝对路径>/fb.json python -m engine.flywheel
   ```
   ⚠️ Windows 注意：Git Bash 的 `/tmp` 映射到 `%LOCALAPPDATA%\Temp`，Python 按 `C:\tmp` 解析，
   **必须用 Windows 风格绝对路径**，否则 `AGRI_CROP_DB` 找不到文件会直接报错（故意 fail fast，避免静默输出全 None）。
4. CI 中的 flywheel 步骤已改为写入 `$RUNNER_TEMP` 隔离目录，并加了数据完整性门禁。

---

## 快速启动

### 1. 交互式 Demo 站点（零依赖，仅标准库）
```bash
python app/demo_server.py
# 浏览器打开 http://127.0.0.1:8000
# 选择城市 / 场景 / 预算 → 四 Agent 协同方案 + 可点击 AgriTrust 证书
```

### 2. 端到端验证
```bash
python scripts/verify_all.py          # 五城市 pipeline + Trust 证书，输出 PASS/FAIL
python -m engine.flywheel              # 跑一次反馈闭环示例，校准「生菜」adapt_score
python scripts/enrich_crop_data.py     # 扩展作物数据密度至每带 ≥18 种
```

### 3. Docker 部署
```bash
docker compose up --build                                  # 本地 verify 模式（跑端到端验证即退出）
docker compose -f deploy/docker-compose.prod.yml up -d --build   # 生产 serving 模式（宿主机 :8001 → 容器 :8000）
```

### 3b. 公网部署（一条命令）
```bash
cp deploy/deploy_config.example.sh deploy/deploy_config.sh   # 一次性：按需改 IP/端口
bash deploy/deploy_local.sh                                   # 同步代码 + 远端构建 + 启动 + 验证
# 站点：http://<ECS_IP>:8001   详细流程见 deploy/DEPLOY.md
```

### 3b-2. 视觉诊断后端（可选，接 ATEX 多模态网关）
PestAgent 的视觉诊断走可插拔后端：配置以下环境变量（读 `agent/vision.py`）即启用，未配置则规则降级。
密钥放仓库外的 `.env`（已被 `.gitignore` 忽略，部署时由 `deploy_local.sh` 同步到 ECS，不进 GitHub）：

```bash
# .env（项目根目录，不要提交）
AGRI_VISION_URL=http://host.docker.internal:8420/v1   # ATEX 网关，容器内用 host 网桥访问
AGRI_VISION_KEY=<你的 ATEX 网关 Key>
AGRI_VISION_MODEL=gpt-4o                              # 须为多模态模型
```
`deploy/docker-compose.prod.yml` 已默认读取这三个变量；若 ATEX 仅监听 `127.0.0.1`，可把 `AGRI_VISION_URL` 改为宿主内网 IP。

### 3c. CI（push 自动验证）
```
.github/workflows/ci.yml
```
push 到 main 后自动跑：单测 → verify_all → trust_layer → flywheel（隔离到 $RUNNER_TEMP）→ **数据完整性门禁**（禁假校准标记、禁合成反馈样本）→ Skill 注册表合法性 → 数据自检（每带 ≥18 种作物），Python 3.10/3.11/3.12 矩阵。
状态：GitHub Actions 已验证可用（fine-grained PAT 含 `Workflows:write`，push 后 CI 自动跑通，最近一次 run 结论 success）。

### 3d. 本地 → GitHub 同步（无 git push 环境）

本机 github.com:443 不可达，且本地目录不是 git clone，**不能用 `git push` / `git status`**。
统一走这两个脚本：

```bash
# 1) 查看待推差异（只读，公开仓库可匿名）
python scripts/sync_check.py

# 2) 推送（单 commit，推送后自动回读校验）
python scripts/gh_push.py <token临时文件> "<提交信息>" file1 file2 ...
```

- 需要 fine-grained PAT（Contents: read/write），建议含 `Workflows:write` 以便改 CI
- token 放临时文件、用完即删，不要留在命令行历史里
- 推送后 CI 会自动跑；确认 success 再关掉本地改动

### 4. 单元测试（零依赖）
```bash
python -m unittest scripts.test_agents -v     # 26 项用例全过
```

### 5. Skill 自动生成（闭环触发）
```bash
python -m engine.skill_factory            # 演示：新作物冰菜 → 自动 Skill
python -m engine.skill_factory --list     # 列出当前所有 Skill
```

### 6. 提交种植反馈（内测回流 → flywheel 校准）
```bash
python scripts/submit_feedback.py --zone subtropical_wet --crop 生菜 \
  --survival 0.92 --yield 4.5 --rating 5 --issues "梅雨季霜霉病" --note "杭州阳台春播"
# 或直接调用 Demo 站点 POST /api/feedback
```

---

## 自动化定时闭环（情报 → 数据 → 评估）

项目已建立三个互相衔接的**定时自动化任务**（WorkBuddy Automation），持续收集情报、修复迭代、度量提升，形成逻辑闭环：

| 闭环 | 频率 | 产出文件 | 作用 |
|------|------|---------|------|
| 情报收集 | 每周一 09:00 | `docs/intel_log.md` | WebSearch 农业 AI 最新进展 → 差距分析 → 改进点 / 自动 Skill |
| 数据飞轮 | 每周日 22:00 | `data/WEEKLY_REPORT.md` | verify_all + flywheel + enrich 自检 → 周报 |
| 评审自评 | 每两周周三 10:00 | `docs/project_evaluation.md` | 评审维度重评 → 暴露短板 → 度量提升 |

**闭环逻辑**：情报（发现差距）→ 数据（执行校准/扩充）→ 评审（度量提升并暴露新短板）→ 情报（再发现）。三个任务均已 ACTIVE，按上方频率自动运行。

---

## 开源协议

待确定。核心数据标准与协议倾向开源（抢生态话语权），应用层与决策引擎闭源（保利润）。
