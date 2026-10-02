# Env Recipe ↔ AgGateway ADAPT 字段映射（2026-09-30）

> 目的：声明我们的 Env Recipe 数据模型与 AgGateway ADAPT 标准的对应关系，为**跨平台互操作**铺路。
>
> 状态：**planned_mapping**（映射已声明，实际互操作待 AgGateway 会员/许可评估）。
>
> 铁律：真实数据、不编造——本文件声明的是字段对应关系，不代表我们已获得 AgGateway 认证。

---

## 1. 为什么做这个映射

**市场需求**：AgGateway 是 AgGateway Consortium 主导的**开放农业数据交换标准**（Aggregation Exchange Standard），ADAPT 是其数据模式子集，被 John Deere、CNH Industrial、Trimble、Albaugh 等一线农机巨头采纳。任何想跨平台流通的农业数据都绕不开它。

**我们的定位**：智慧农业生态的差异化在于**知识配方（Env Recipe）**，而非数据管道。Env Recipe 描述的是"某作物 × 某阶段 × 某箱体设备"下的环境设定，与 ADAPT 的 `Crop`、`Field`、`Weather`、`Equipment` 等领域有部分重叠，但粒度不同。

**互操作价值**：
- **数据出口**：未来如对接 John Deere / CNH 数据，Env Recipe 可映射到 ADAPT 结构，降低集成成本。
- **数据入口**：接收 ADAPT 格式的农场数据，可反查对应 Env Recipe 做校准。
- **生态声明**：向 AgGateway 会员、投资人和下游集成商声明我们的数据模型可互操作。

**边界**：我们不是 AgGateway 会员，本映射是**工程声明**（让集成方知道怎么对接），不是**认证声明**（不代表 AgGateway 认可）。

---

## 2. Env Recipe 字段清单

Env Recipe 结构（`data/env_recipes/*.json`）：

| 层级 | 字段 | 含义 |
|---|---|---|
| 顶层 | `protocol` | 协议标识（`env-recipe`） |
| 顶层 | `recipe_version` | 版本（如 `1.0.0`） |
| 顶层 | `crop` | 作物信息（species/latin/family） |
| 顶层 | `stage` | 生长阶段（seedling/vegetative/full_cycle/...） |
| 顶层 | `device_profile` | 设备档案（device_class/sensor_capability） |
| 顶层 | `environment` | 环境设定（temperature/humidity/water_nutrient/airflow） |
| 顶层 | `exception_handling` | 异常处理规则列表 |
| 顶层 | `execution_log` | 执行日志（空数组=未执行） |
| 顶层 | `outcome` | 结果反馈（空对象=未反馈） |
| 顶层 | `image_consent` | 图像同意状态 |
| 顶层 | `sources` | 数据来源清单（title/url/accessed_at/license） |
| 顶层 | `license` | 分发条款 |
| 顶层 | `license_scope` | 授权范围说明 |

---

## 3. 映射到 ADAPT 领域

**说明**：以下映射是**语义对应关系**，不是逐字逐字段一一对应。ADAPT 各领域详见 [AgGateway ADAPT Data Model](https://github.com/agcore/AgGatewayDataModels)。

### 3.1 `crop` → ADAPT `Crop` + `Seed`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `crop.species` | `Crop.crops.crops[].name` | 直接对应（中文作物名，需转英文） |
| `crop.latin` | `Crop.crops.crops[].variety` | 拉丁学名近似于品种名 |
| `crop.family` | — | ADAPT 无直接字段；可写入 `Crop.notes` |
| `stage` | `Crop.growthStages.growthStages[].name` | 需建立映射表：`seedling` → `Planting`，`vegetative` → `Pre-Mid Growth`，`full_cycle` → `Pre-Mid Growth + Mid-Post Growth` 组合 |

### 3.2 `environment.temperature` → ADAPT `Weather`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `temperature.day_c` | `Weather.weather[].data.data[].high` | 单位需换算（℃ → ℉ 或 K） |
| `temperature.night_c` | `Weather.weather[].data.data[].low` | 同上 |

**注意**：ADAPT Weather 是**观测数据**（观测时间、观测点），Env Recipe 是**设定值**（推荐目标温度）。映射时应明确语义：Env Recipe 的 day_c/night_c 对应 ADAPT 中的 **set point**，而非观测值。

### 3.3 `environment.humidity` → ADAPT `Weather`

| Env Recipe 字段 | ADAPT 对应 |
|---|---|
| `humidity.min_pct` | `Weather.weather[].data.data[].minHumidity` |
| `humidity.max_pct` | `Weather.weather[].data.data[].maxHumidity` |

### 3.4 `environment.water_nutrient` → ADAPT `Equipment` + `Tillage`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `water_nutrient.ph` | `Tillage.tillages.tillages[].notes` | ADAPT 无 pH 字段；写入 notes |
| `water_nutrient.water_ml_day` | `Equipment.equipment[].notes` | ADAPT 无灌溉量字段；写入 notes |

**Gap**：ADAPT 对灌溉/施肥粒度的建模弱于 Env Recipe，未来可能需要扩展自定义字段（AgGateway 允许 `notes` 扩展）。

### 3.5 `environment.airflow` → ADAPT `Equipment`

| Env Recipe 字段 | ADAPT 对应 |
|---|---|
| `airflow.level` | `Equipment.equipment[].notes`（"Airflow: medium"） |

### 3.6 `device_profile` → ADAPT `Equipment`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `device_class` | `Equipment.equipment[].equipmentType` | 需建立映射表：`balcony` → `Greenhouse`，`car` → `Mobile Grower`，`rooftop` → `Greenhouse` |
| `sensor_capability` | `Equipment.equipment[].sensors`（自定义） | ADAPT 无原生传感器清单，写入自定义字段 |

### 3.7 `exception_handling` → ADAPT `OperationsLog`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `condition` | `OperationsLog.operations.operations[].details` | 异常条件写入操作描述 |
| `action` | `OperationsLog.operations.operations[].details` | 处理建议写入操作描述 |
| `severity` | `OperationsLog.operations.operations[].details` | 严重度写入操作描述 |

**Gap**：Env Recipe 的 exception_handling 是**规则**（条件→动作），ADAPT 的 OperationsLog 是**日志**（已发生的操作）。映射时应区分：Env Recipe 的规则在触发时才生成 ADAPT 日志条目。

### 3.8 `execution_log` → ADAPT `OperationsLog`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `execution_log[]` | `OperationsLog.operations.operations[]` | 1:1 对应（结构相似：时间戳、操作、结果） |

### 3.9 `outcome` → ADAPT `OperationsLog` + `Analytics`

| Env Recipe 字段 | ADAPT 对应 | 映射说明 |
|---|---|---|
| `outcome` | `Analytics.analytics[].analytics[].result` | 结果指标（产量、成本、品质）写入 Analytics |

### 3.10 `sources` / `license` → ADAPT 无对应

**Gap**：ADAPT 无 `sources` 和 `license` 顶层字段。这些是智慧农业生态的**差异化数据血缘能力**（壁垒 ④），映射到 ADAPT 时应写入 `notes` 或自定义字段。

---

## 4. 映射 Gap 汇总

| Gap 类别 | 具体 Gap | 影响 | 缓解方案 |
|---|---|---|---|
| **语义 Gap** | ADAPT Weather 是观测数据，Env Recipe 是设定值 | 中等 | 明确区分 set point vs observation |
| **粒度 Gap** | ADAPT 无 pH / 灌溉量 / 气流字段 | 中等 | 写入 `notes` 或自定义字段（AgGateway 允许扩展） |
| **结构 Gap** | Env Recipe exception_handling 是规则，ADAPT OperationsLog 是日志 | 低 | 规则触发时生成日志条目 |
| **缺失 Gap** | ADAPT 无 sources / license 字段 | 高（丢失血缘能力） | 写入 `notes`；这是我们的差异化能力，不能丢 |

---

## 5. 映射实现路线

### 阶段 1（本轮）：**映射文档化**（已完成）

- 本文件声明字段对应关系
- `config/ecosystem.json` 声明 `aggateway-adapt` 生态对接状态为 `planned_mapping`

### 阶段 2（未来）：**转换脚本原型**

- 在 `core/` 下新增 `aggateway_export.py`：Env Recipe → ADAPT XML/JSON
- 覆盖 crop / environment / device_profile 三块核心字段
- 测试：验证转换后 ADAPT JSON schema 校验通过

### 阶段 3（长期）：**双向同步**

- 接收 ADAPT 格式农场数据，反查 Env Recipe 做校准
- 需要 AgGateway 会员评估 + ADAPT schema 版本适配

---

## 6. 商业化边界

**我们不做的事**：
- ❌ 不申请 AgGateway 认证（除非会员价值明确）
- ❌ 不做 ADAPT 数据管道产品（定位是知识配方，不是数据入口）
- ❌ 不承诺跨平台互操作 SLA（本映射是**参考实现**，非产品承诺）

**我们做的事**：
- ✅ 声明字段映射关系（让集成方知道怎么对接）
- ✅ 提供转换脚本原型（降低集成成本）
- ✅ 保留 Env Recipe 的差异化字段（sources / license / exception_handling）

---

## 7. 相关文档

- `config/ecosystem.json`：生态对接清单
- `docs/block_improvement_roadmap_2026-09-30.md`：板块深度改进路线图
- `docs/release_readiness_2026-09-29.md`：发行就绪度评估

---

*本文件生成于 2026-09-30，与 `harness/manifest.json` 版本 2.2.0 对齐。映射状态：planned_mapping（未获 AgGateway 认证）。*
