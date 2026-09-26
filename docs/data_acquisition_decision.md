# 数据获取路线决策：抓取门户 vs 对接 API

> 日期：2026-09-21｜依据：`docs/data_sources_verified.md` 第五节（本机一手实测）
> 起因：项目 110 作物 / 110 配方 / 23 病虫害 全部为 AI 编撰的冷启动种子（`calibrated=true` **0/110**，`feedback_log` **0 条**），
> 用户提问「建立闭环任务直接抓取数据，还是对接某个数据库，哪种更好」。

## 一、先把问题框架纠对

「抓取数据」与「对接数据库」并不是二选一——实测后真实的可用选项是**三类**：

| 方案 | 含义 | 实测可行性 |
|---|---|---|
| A. 抓取门户页面 | 用爬虫解析 GAEZ / EPPO 等 JS 门户的 HTML | ❌ **不可行**：GAEZ 是 Terria JS 应用，EPPO `/api/taxon/*` 返 404，无稳定结构可抓 |
| B. 对接传统数据库 | 直连 Postgres/MySQL 型数据仓库 | ❌ **本项目不存在这种源**：目标源都是 API 或文件下载，无人提供 DB 连接 |
| C. **对接免费 API + 一次性批量下载** | REST JSON（NASA POWER / Open-Meteo / GBIF）+ GeoTIFF 批量下载（WorldClim） | ✅ **唯一可行**，5 个源实测全部可用 |

## 二、实测清单（关键）

**✅ 可程序化取数（5 个）**
1. **NASA POWER** — `power.larc.nasa.gov/api/temporal/{climatology,daily}/point`，无密钥，1.2s，
   返 12 月 T2M / 降水 / 湿度 / **太阳辐射**（可直接支撑 PPFD 估算）。公有领域。
2. **Open-Meteo** — `archive-api.open-meteo.com/v1/archive`（历史，daily 可用）+
   `api.open-meteo.com/v1/forecast`（含土壤温湿）。无密钥，1–6.5s。CC BY 4.0。
   ⚠️ **`monthly` 参数实测返回空体**，必须取 `daily` 自行聚合。
3. **WorldClim 2.1** — `geodata.ucdavis.edu` 直接 ZIP 下载 GeoTIFF（`wc2.1_10m_tavg.zip` 含 12 个月均温栅格）。CC BY 4.0。
4. **GBIF** — `api.gbif.org/v1/species/match`，1.0s，返 accepted scientific name + taxonKey。
5. **SoilGrids REST** — `rest.isric.org`，**17.9s**，太慢 → 仅作补充，不作实时主源。

**❌ 不可程序化取数（4 个）**
- GAEZ v4（JS 门户，无 API）｜ EPPO GD（无公开 API，需注册）｜ FAOSTAT（25s 超时，本网不通）｜ ISRIC WoSIS（TLS 握手失败）

## 三、推荐方案：C + 两种闭环分开建

### 决策：不建「抓门户」的爬虫闭环，建「锚定权威 API + 离线快照」的数据闭环

三条理由：
1. **可持续性** — 门户是 JS 渲染，抓取要长期对抗结构变更与反爬；本项目**零第三方依赖**（纯 stdlib），
   维护爬虫会让复杂度失控。API 是契约，稳定。
2. **许可干净度** — GAEZ / EPPO 的条款页自身都读不全，抓取后再分发有法律灰区；
   而 NASA POWER（公有领域）、Open-Meteo / WorldClim / GBIF（CC BY 4.0）许可明确可商用+可署名。
3. **真瓶颈不在取数** — 项目 0 用户、0 反馈，数据取进来也没消费者；先取数不解决"空架子"。

### 必须区分两种「闭环」，别混为一谈

| 闭环 | 内容 | 当前能否跑 |
|---|---|---|
| **① 数据锚定闭环** | `fetch(API) → schema 校验 → 落库带 provenance（源/URL/许可/取数时间/置信度） → 引擎优先用真值 → 离线快照兜底` | ✅ **立即可做**。把 AI 编的 `monthly_mean_c`/气候基线换成 NASA/WorldClim 实测值 |
| **② 结果校准闭环** | 真实种植结果回流 → 修正 `adapt_score` | ❌ **跑不起来**（需真实用户，当前 0） |

### ② 的无用户替代路径（真正把「编的」变成「实证的」）
**生态位包络反推**：用 **GBIF 真实分布点** + **WorldClim 生物气候层**（bio1/bio12 等）反推每个作物的
气候适宜区间，替换 `crop_adapt_db.json` 里手写的 `adapt_score`。
这是**在 0 用户条件下唯一能实证校准适配分的办法**，且完全依赖上面已验证可用的源。

## 四、落地排序（按性价比）

| 优先级 | 动作 | 成本 | 产出 |
|---|---|---|---|
| **P0** | 接 NASA POWER + Open-Meteo 进 `climate_agent` / `season_agent` | 低（stdlib urllib） | 干掉"用户手填 12 月均温"，气候基线变实测 |
| **P1** | WorldClim ZIP 一次性下载 → 6 分区气候基线**离线固化** | 低（一次性下载） | 不受网络波动影响，兜底可信 |
| **P2** | GBIF 校验 110 作物的拉丁名（现为 AI 手写，0 条核验） | 低 | 学名可信化 |
| **P3** | 生态位包络反推替换 `adapt_score` | 中 | **无用户条件下唯一实证校准路径** |
| P4 | GAEZ 走人工许可确认后 bulk 下载一次（一次性，非闭环抓取） | 中（需人工） | 适宜性对标基准 |
| **不做** | 抓 GAEZ/EPPO 门户、建爬虫、接 FAOSTAT（本网不通） | — | — |

## 五、若走 P0 必须遵守的工程约束

1. **必须落 provenance 字段**（`source` / `url` / `license` / `fetched_at` / `confidence`），
   否则又是"来路不明的数字"——这正是上一轮"空架子"的根因。
2. **必须有离线快照兜底**：网络失败时降级到上一次快照，并标注 `stale=true`，绝不静默返回空/0。
3. **必须遵守既有隔离纪律**：新增写盘能力要清点全部调用点（生产入口 + 测试 + 验证脚本），
   合成数据留痕标记，防污染真实种子库。
4. **字段单位必须显式声明且跨源一致**（2026-09-23 补，起因是 `monthly_precip_mm` 的口径歧义）：
   - `monthly_precip_mm` 虽是月度序列，但**每个元素是月内日均降水（mm/day），不是月累计量**。
     两个源同口径：NASA POWER 月度 point 接口的 `PRECTOTCORR` 聚合结果是日均值
     （实测杭州 30.27N/120.15E = `[2,2,...]`、12 个月合计 24，真实月累计约 120mm）；
     Open-Meteo 走日值 `precipitation_sum` 再按月取均值，同样是 mm/day。
   - 代码侧以 `climate_data.PRECIP_UNITS = "mm/day"` 为唯一口径声明，所有产出该字段的
     路径都透传 `monthly_precip_mm_units`；老缓存与已固化分区基线在读回时 `setdefault` 补齐
     （见 `get_zone_climate_baseline` 与缓存命中分支），保证新旧数据同构。
   - **禁止**对该字段乘天数换算成月累计：`niche_envelope_calibrate.score_zone` 的降水通道
     （权重 0.4）依赖「作物包络与分区基线同口径区间命中」，单侧换算会让比较失去意义，
     并连带改写 107 个已固化 `adapt_score`（harness 数据基线 + 测试基线同时失效）。
   - 该约束由 `scripts/test_climate_data.py` 的 `TestPrecipUnitsContract` 锁定，
     其中一项直接断言校准脚本源码内不出现 `* 30` / `* 31`。
