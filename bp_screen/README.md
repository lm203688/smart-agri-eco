# bp_screen · 农业项目投资初筛引擎

AgriScreen V1 的零依赖移植版。把「BP / 审计 / 流水 / 证书文本 → 六分类 → 五闸 → 六评分卡 → 一票否决 → 三档初筛结论」这条九层管线，从 FastAPI handler 里剥出来做成纯数据流包，使评分内核可在无 Web 层、无第三方依赖的环境下运行。

## 来源与许可

- 上游：`V1 农眼AgriScreen-农业投资初筛系统.zip`（作者自有，已确认无版权问题）
- 许可：随本项目 LICENSE（见仓库根目录）
- 规则版本：`v2.0.0`（2026-09-20）

## 依赖分层（零第三方依赖，关键）

| 子模块 | 依赖 |
|---|---|
| `rules` `scorer` `classifier` `verifier` `gap` `archiver` `report` `sanity` `pipeline` | 仅标准库 |
| `extractor` | 仅标准库（`re` + `parser` + `llm`） |
| `parser` | 仅标准库；pdfplumber / pandas / openpyxl 为**函数内 lazy import**（indent≥4），仅解析 PDF/CSV/Excel 时触发 |
| `llm` | 仅标准库 `urllib.request`；通道 B 无 key 时静默降级为纯正则 |
| `db` | 仅标准库 `sqlite3` |
| `web` | **可选**，依赖 fastapi / uvicorn；不装也能用 MCP 或直接调函数 |

导入 `bp_screen` 不会触发任何第三方 import。未装依赖时解析 PDF/Excel 会返回 error 状态，其余格式照常。

## 用法

```python
import bp_screen

# 路径一：直接给文本（MCP / 单测推荐）
r = bp_screen.screen_text(open("BP.txt", encoding="utf-8").read(), company="金玉种业")
print(r["verdict"], r["score"], r["score_range"])   # 需深挖 71.8 [60.0, 83.8]
print(r["evaluation"]["decision_path"])              # 归因：决策路径

# 路径二：给已抽取字段（跳过 L0-L3）
r = bp_screen.screen_fields(
    {"revenue": 1.8e8, "approved_varieties": 6, "ue_margin": 32.0,
     "runway_months": 36.7, "top5_client_pct": 38.0},
    category="seeds")

# 路径三：给文件路径（Web 层）
r = bp_screen.run_pipeline([("/tmp/a.pdf", "a.pdf"), ("/tmp/b.txt", "b.txt")], company="X")

bp_screen.meta()   # 规则版本 / 门禁 / 分类 / 案例数
```

## 九层管线

| 层 | 模块 | 说明 |
|---|---|---|
| L0 归档 | `archiver` | 文件角色判定（BP/审计/流水/合同/证书）+ 冲突检测 |
| L1 解析 | `parser` | txt/md/docx 零依赖；pdf/xlsx 依赖缺失时降级跳过 |
| L2 提取 | `extractor` | 正则通道 A；LLM 通道 B 可用时交叉验证，分歧>5% 标记复核 |
| L3 归一化 | `extractor.normalize` | 单位统一（万/亿→元）+ 派生指标（净利率、现金收入比、跑道） |
| **L2.5 合理性** | **`sanity`** | **移植时新增**：拦越界值，置空后进入区间化，防假精确 |
| L5 分类 | `classifier` | 六分类 + 置信度；<70 要求人工确认，不自动评分 |
| L6 核验 | `verifier` | 证照核验；本地库命中只标 `local_hit`，不冒充官方 |
| L4 缺口 | `gap` | 三级缺口（fatal/critical/normal）+ 补数提示 |
| L7 评分 | `scorer` | 五闸 → 六评分卡 → 一票否决 → 三档（≥75 通过 / 60-75 需深挖 / <60 淘汰） |
| L8 报告 | `report` | 统一 11 区块：结论/归因/评分卡/门禁/核验/缺口/对标/尽调清单/提取溯源/文件角色/元信息 |

## 移植时修的 8 个缺陷

上游 V1 包实测跑通，但审计发现 8 处问题，已在移植中修掉：

| # | 缺陷 | 影响 | 修法 |
|---|---|---|---|
| 1 | `rules.py` 门禁 `cash_ratio` 的 metric 写成 `cash_to_revenue`，而 `normalize` 产出的是 `cash_ratio` | **该闸永不触发**（静默死代码） | metric 改为 `cash_ratio` |
| 2 | 门禁 `bio_asset` 的 metric 写成 `bio_asset_pct`，`GAP_LEVELS` 用的是 `bio_inventory_pct` | **该闸永不触发** | metric 改为 `bio_inventory_pct` |
| 3 | `extractor.py` 净利率正则 `净利率?` 的 `率?` 使「率」可选 | 「净利润1800万」被当净利率提出，实测 `net_margin=1800.0`（真值 10.0） | 强制要求「率」且必须带 `%`；并允许由 净利润/营业收入 派生 |
| 4 | 研发占比正则整组可选 | 「月均运营支出（工资+研发+管理）600万」命中，实测 `rd_pct=600.0`（真值 12.0） | 强制要求占比/率指示词且必须带 `%` |
| 5 | 在审登记数正则三段可选 + 两段非数字窗口合计 14 字符 | 跨段落匹配，把品种名「金玉188」当计数，实测 `pipeline_certs=188.0` | 强制要求「在(申请\|申报)」且要求量词，窗口收窄 |
| 6 | `verifier.py` 对 `["审定","品种审定"]` 两条 kw 各扫一遍 | 同一条证照重复出现（金玉188/郑单958 各两次） | 按 `(type, value)` 去重 |
| 7 | `eia_passed` 正则无捕获组 | `groups[0]` 抛 IndexError 被 except 吞掉 → **该字段永不提取**，养殖类环评一票否决失效 | 加捕获组 + `BOOL_FIELDS` 显式声明，命中即 True |
| 8 | 区间化 `band=min(4*len(missing),12)` 只覆盖「没抽到」 | 抽错了（如 1800.0）不进缺失路径，输出「71.8（区间 71.8–71.8）」**假精确** | 新增 `sanity.py`：越界值置空 → 自然进入缺失路径 |

另有一处**文案诚实性**修正：种子案例里 7 条合成案例的 `outcome` 原写「真实结局=…」，虚构公司不可能有真实尽调结局，已改为「预设结局=」，并按 `is_benchmark` 打 `source=benchmark / synthetic` 标。

## 核验状态三档（不要误读）

| 状态 | 含义 |
|---|---|
| `local_hit` | 与**本地示例库**字符串一致，仅可作格式校验参考。**不是官方核验** |
| `unverified` | 文本声称有资质但无可核验编号，需人工向企业索取后在官方系统复核 |
| `not_found` | 文本中未发现相关资质表述 |

`LOCAL_REGISTRY` 里 7 个审定品种 / 4 个登记证号 / 2 个安全证书编号**全是演示数据**。本模块绝不产出 `verified` 状态。每条结果带 `official_source`，告诉你真正该查哪个官方系统：

- 审定品种 → 农业农村部种业管理司 / 全国农业技术推广服务中心品种信息查询
- 农药肥料登记证 → 农业农村部农药检定所 / 中国农药信息网 chinapesticide.org.cn
- 安全证书 → 农业农村部农业转基因生物安全委员会公告
- 环评批复 → 生态环境部门建设项目环评公示系统

注：EPPO（eppo.int）是植物保护组织的有害生物数据库，**不是**品种审定或农药登记数据源，不能用它做证照核验。

## Web 层（可选）

```bash
pip install fastapi uvicorn
python -m bp_screen.web        # 起在 8010
```

**端口 8010，不是 8001**：8001 已被本项目 ECS 公网服务占用（宿主 8001 → 容器 8000，8000 被陌生 FastAPI 占用故主服务改 8001）。上游 V1 包的 README/deploy.sh 用 8001，移植时已改，避免同机撞车。

## 环境变量

| 变量 | 作用 |
|---|---|
| `AGRI_VISION_URL` / `AGRI_VISION_KEY` / `AGRI_VISION_MODEL` | 首选 LLM 网关（项目既有，指向 ATEX `:8420`） |
| `AGRI_BP_LLM_URL` / `AGRI_BP_LLM_KEY` / `AGRI_BP_LLM_MODEL` | 可选覆盖，仅给初筛器单独指定 |
| `AGRI_BP_DB` | 覆盖 SQLite 路径（默认 `bp_screen/data/cases.db`，测试用临时库时用） |
| `AGRI_BP_WEB_PORT` / `AGRI_BP_WEB_HOST` | Web 层监听（默认 `8010` / `0.0.0.0`） |

未配任何 LLM key 时走正则单通道，功能完整（提取覆盖略降），不报错。

## 边界声明

- 输出为**初筛参考**（通过 / 需深挖 / 淘汰），不构成投资决策建议
- 评分规则基于 2023–2025 公开案例归纳，建议 6–12 个月更新基准数据
- 所有提取值可溯源（文件名 + 页码），无来源的值不计分
- 数据不足时输出分数区间并标注缺口，**禁止用估算值冒充实际值**
- 核验层本地库为演示数据，正式结论须在官方系统按编号复核

## 与本项目「投资评估板块」判定的关系

本项目此前判定 `agri_project_roi`（用种植数据算 ROI）**不做**：110 份配方的 `outcome` / `yield` / 经济字段全为 0，输入不存在，硬做只能编数字。

本包**是另一回事**，不冲突：

| | `agri_project_roi`（不做） | `bp_screen`（本包） |
|---|---|---|
| 输入 | 种植数据（outcome/yield/价格） | BP / 审计 / 流水 / 证书**文本** |
| 输出 | ROI 数字 | 完备性 + 风险初筛三档 |
| 依赖本项目数据 | 强依赖 | **不依赖** |
| 防编造 | 无 | 三重防线：无来源不计分 / 缺失区间化 / 合理性校验 |

本包还补上本项目两个已知短板：① outcome 回流通路（`cases` / `assessments` 表）；② 投资决策规则的第二个领域实例。

评估与方案记录：`docs/agriscreen_integration_assessment.md`
