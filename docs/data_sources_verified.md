# 全球数据源核实清单（P0-B）

> 核实日期：2026-09-05｜方法：①本机 curl 实测可达性（`--ssl-no-revoke --tlsv1.3`，一手数据）②FAO/官方页面与检索核实现状与许可
> 作用：v2.0「待核实」项关闭——确认哪些数据源真实可用、许可是什么、本机网络能不能拿到
> **2026-09-10 修订**：更正 SoilGrids 条目（原记录的主机名 `api.isric.org` 不存在，正确端点为 `rest.isric.org`，详见 §二.2）

## 一、可达性实测（本机一手数据，2026-09-05）

| 数据源 | URL | HTTP | 结论 |
|---|---|---|---|
| GAEZ v4 门户 | `https://gaez.fao.org/` | 200 (1.9s) | ✅ 可达（JS 门户） |
| GAEZ 数据门户 | `https://data.apps.fao.org/gaez/` | 200 (1.1s) | ✅ 可达 |
| Ecocrop 旧域名 | `https://ecocrop.fao.org/` | **503** (8.1s) | ❌ 旧服务已死（详见下文） |
| SoilGrids 网页 | `https://soilgrids.org/` | 200 (1.4s) | ✅ 可达 |
| SoilGrids API（**正确主机**） | `https://rest.isric.org/soilgrids/v2.0/properties/query?lon=10&lat=50&property=phh2o&depth=0-5cm&value=mean` | 200（间歇，0.2–15s）／偶发 60s+ 超时 | ⚠️ **可达但不可靠**（2026-09-10 更正，见下文 §2） |
| SoilGrids API（**此前探错的 URL**） | `https://api.isric.org/...` | **000, exit 6（DNS 解析失败）** | ❌ **该主机不存在**——不是网络问题，是 URL 写错 |
| WorldClim | `https://www.worldclim.org/` | 200 (1.0s) | ✅ 可达 |
| PlantVillage 站点 | `https://plantvillage.psu.edu/` | 200 (2.0s) | ✅ 可达 |
| PlantVillage 数据集仓库 | `https://github.com/spMohanty/PlantVillage-Dataset` | 200 (1.0s) | ✅ 可达（`--ssl-no-revoke` 下 github.com 网页实测可达） |
| EPPO Global Database | `https://gd.eppo.int/` | 200 (1.2s) | ✅ 可达 |
| FAO CropInfo 旧 URL | `.../land-water/databases-and-software/crop-information/en/` | **404** | ❌ 页面已迁移/下线 |

> 附注：github.com 网页与 raw.githubusercontent 经 curl 均实测可达（200）；被封的是 `git push` 的 git 协议通道，推送仍走 Git Data API（api.github.com）。

## 二、关键发现（改变原方案假设）

### 1. Ecocrop 已停服，并入 GAEZ（官方确认）
FAO 官方页明确：**"The ECOCROP database was discontinued around 2015"**，因需求仍在，已**并入 GAEZ 平台**提供。
- 现用入口：`https://ecocrop.apps.fao.org/ecocrop/srv/en/home`（FAO AgroInformatics catalog，2025-04 更新）
- 说明页：`https://www.fao.org/geospatial/data-and-tools/data-portals/ecocrop/en`
- **对本项目的意义**：①`crop_adapt_db.json` 的 `data_sources` 不应再单独引用 Ecocrop 旧站；②「适宜性引擎对标 Ecocrop」的说法应改为「对标 GAEZ（内含 Ecocrop 作物约束参数）」；③2568 种作物的环境约束参数（温度/降水/pH/光照/Köppen 带等）仍可经 GAEZ 获取，冷启动路线不变。

### 2. SoilGrids API：**URL 写错导致连续误判**（2026-09-10 更正）

**此前结论有误。** 09-05 记录为「`api.isric.org` 返回 502，API 经本机代理被拦」；09-08~09-10 的每日巡检又连续报「退出码 6/7，本机不可达」。2026-09-10 核实发现根因是**主机名写错**：

| 主机 | 实测 | 判定 |
|---|---|---|
| `api.isric.org` | `curl` → HTTP 000，**exit 6（Could not resolve host）** | **该主机不存在**，与网络/代理无关 |
| `rest.isric.org` | `curl` → **HTTP 200**，返回真实 SoilGrids v2.0 JSON（欧洲坐标 `lon=10,lat=50` → `phh2o mean=68`，即 pH 6.8） | **官方正确端点，公网存活** |

**真正的问题不是"不可达"，而是"不可靠"**：改正 URL 后实测表现为**间歇性**——
- 有时 200 且 0.2–15s 返回真实值；
- 有时 >60s 挂死（curl exit 28）；
- 对中国多点（北京 116.4/39.9、广州 113.3/23.1、杭州 120.2/30.3）返回 `mean: null`，欧洲点则有值。

**影响与处置**：
1. 每日巡检的探测 URL 已改为 `rest.isric.org`（**绝不可改回 `api.isric.org`**），判定标准改为「出现过 200 即记为*可达但不可靠*」，不得改判为"源已死亡"（公网侧该 API 是活的）。
2. 因该服务在本机不可作为实时主源，已落地**离线降级路径** `agent/soil_profile.py`（MCP 工具 `agri_soil_profile`）：在线优先，失败/空值自动降级到 `data/zone_meta/global_zones.json` 的**分区级**土壤字段，输出强制标注 `resolution=zone` / `confidence=low` / 局限说明，绝不把分区均值冒充地块实测。
3. **教训（已写入项目长期记忆）**：探测不可达时，先排除"URL 本身是否存在"（DNS 解析失败 exit 6 ≠ 网络拦截），再下"源不可达"的结论。这一次把 URL 错误误判成了网络问题，连续多日无人发现。

### 3. FAO CropInfo 页面 404
旧 URL 已失效。作物基本信息以 GAEZ 平台（含 Ecocrop 参数）为主入口，`crop_adapt_db.json` 后续版本应更新 `data_sources`。

## 三、许可与使用条款（已核实部分）

| 数据源 | 许可/条款 | 核实程度 |
|---|---|---|
| GAEZ v4 | FAO & IIASA 联合出品；按 FAO 开放数据政策为 **CC BY 4.0**（需署名）。⚠️ 条款页为 JS 门户无法程序化抓取，**正式商用前人工确认一次** | ⚠️ 高置信未逐字核验 |
| Ecocrop（经 GAEZ） | 随 GAEZ 平台条款 | 同上 |
| SoilGrids | ISRIC 数据政策，惯例 **CC BY 4.0**（端点 `rest.isric.org` 实测可达但间歇超时；许可未逐字核验） | ⚠️ 同上 |
| WorldClim | **CC BY 4.0**（官方明示，需引用 Fick & Hijmans 2017） | ✅ |
| PlantVillage 数据集 | 54,306 图 / **14 作物 / 26 病害**（README 2026-02 更新）；官方推荐经 HuggingFace `mohanty/PlantVillage`（含 80/20 防泄露划分）。**⚠️ README 无明确 license，仅要求引用 Mohanty et al. 2016**——商用/再分发前需联系作者确认 | ✅ 规模已核验；license 缺失是风险点 |
| EPPO GD | 注册免费；98,700+ 物种基础信息、1,900+ 有害生物详表、16,000+ 图片；批量查询工具需注册；**新申请 EPPO Code 收费**；商业再分发条款未在首页明示，投递前读完整条款 | ✅ 部分核验 |

## 四、结论与后续动作

1. **冷启动数据路线成立**：GAEZ（含 Ecocrop 参数）+ WorldClim 均可达且 CC BY 4.0，覆盖「气候→适宜性」建模需求。
2. **病虫害视觉冷启动路线成立但有一个法律风险点**：PlantVillage 规模足够（5.4 万图），但 license 未明示——P2 视觉上线前发邮件向 EPFL 作者确认（或仅做训练不做再分发，规避风险）。
3. **SoilGrids 端点已更正为 `rest.isric.org`**（原 `api.isric.org` 不存在）；该服务本机「可达但不可靠」，已用离线分区降级兜住（`agent/soil_profile.py`）。ECS 侧仍可复测一次，若服务器网络下稳定，可把在线土壤查询放到服务端执行。
4. `crop_adapt_db.json` 的 `data_sources` 字段下个版本更新为：GAEZ v4（含 Ecocrop）/ WorldClim 2.1 / USDA Plant Guides / 中国作物栽培通识（去掉已死的 Ecocrop 旧站与 404 的 CropInfo 直链）。
