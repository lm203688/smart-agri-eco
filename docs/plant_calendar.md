# 种植日历 / 播期窗口（B2）落地说明

> 对应 `docs/opensource_scan_complementary.md` 的 **B2** 项。
> 状态：**已实现并可用**（走本地推导通路）；外部日历通路**待数据到位**。

---

## 1. 结论先行

`@pondlog` 的 150 作物种植日历**当前不可获取**，所以**没有**照搬它的日历数据。
改为实现一条**不依赖任何第三方日历**的通路：调用方给 12 个月均温 → 用已移植的
WOFOST 积温参数反推无霜期与各作物安全播期。这条通路今天就能用。

| 通路 | 状态 | 说明 |
|---|---|---|
| 本地推导（默认） | ✅ 可用 | `frost_anchored_windows(monthly_mean_c, ...)`，见 §3 |
| 外部日历查表 | ⏸ 待数据 | `what_to_plant(zone, date)`，需 drop `data/plant_calendar.json` |

---

## 2. @pondlog 不可达的实测证据（不靠记忆，逐条验过）

| 尝试 | 命令/URL | 结果 |
|---|---|---|
| npm 元数据 | `registry.npmjs.org/@pondlog/core` | 200，`latest=1.0.0` |
| npm tarball | `.../core-1.0.0.tgz` | 下载成功，解压后**仅含 `package.json`**，无数据文件 |
| GitHub raw | `raw.githubusercontent.com/.../main/packages/core/src/data/crop-calendar.json` | **404** |
| GitHub raw（schema） | 同目录 `crop-calendar.schema.json` | **404** |
| GitHub Contents API | `/contents/packages/core/src/data/` | **404**（目录不存在） |
| GitHub tree API | `/git/trees/main?recursive=1` | 200，但**无任何 `crop-calendar` / `companions` / `usda-zones` 条目** |
| 默认分支确认 | `api.github.com/repos/andrewschristison/pondlog` | `default_branch = main`，排除分支名错误 |

README 指向一个**兄弟 CropGraph HTTP API** 作为真实数据源，但该 API 未公开文档化，
本环境未取得可用端点。→ **结论：该数据源暂不可依赖，不做为交付基础。**

> 教训（可复用）：npm 发布包 ≠ 包含源文件；README 描述的数据文件可能根本不在仓库里。
> 引入任何第三方数据前，必须先按「tarball / raw / Contents API / tree API」四路探测确认可达。

---

## 3. 已实现的本地推导通路

### 3.1 输入

```json
{
  "mode": "planting_window",
  "monthly_mean_c": [-4,-1,5,14,20,25,27,26,21,14,5,-2],
  "crops": ["马铃薯"],
  "frost_threshold_c": 0.0,
  "safety_margin_days": 7
}
```

- `monthly_mean_c`：12 个月均温（℃），1 月起。来源可为 WorldClim 2.1 / Open-Meteo / 本地气象站。
  **本模块不内置气候数据**——气候输入由调用方负责，避免编造。
- `frost_threshold_c`：霜冻阈值，默认 0℃。
- `safety_margin_days`：成熟预留安全边际，默认 7 天。

### 3.2 算法

1. 12 个月均温 → 360 天逐日序列（月内线性插值到相邻月中点；每月按 30 天简化）。
2. 在**环形**日序列上找**最长连续无霜段** → 无霜期起止与长度、期内均温（南半球跨年已处理）。
3. 对每种已移植作物：用 `agent/phenology.py` 的积温模型算 `maturity_days`
   （`TSUM / (日均温 − 基温)`），再反推：
   - `earliest_sow` = 无霜期起始
   - `latest_sow` = 无霜期结束 − 成熟天数 − 安全边际
   - `feasible` = 成熟天数 + 安全边际 ≤ 无霜期长度

### 3.3 输出示例（北京型气候）

```json
{
  "frost_free": {"start": "02-21", "end": "11-30", "length_days": 280, "mean_temp_c": 16.86},
  "windows": [
    {"crop": "potato", "feasible": true, "maturity_days": 126,
     "earliest_sow": "02-21", "latest_sow": "07-17", "sow_window_days": 146}
  ]
}
```

---

## 4. 已知限制（逐条写明，不掩饰）

1. **作物覆盖仅 7 种**：potato / wheat / soybean / sunflower / rice / sweetpotato / mungbean
   （WOFOST `wofost81` 分支里与我们配方库有交集的部分）。其余作物返回 `available=false` 并列出可查作物，**不编造**。
2. **不含春化（vernalization）与光周期机制**。需春化品种（如冬小麦）的窗口**只对春播型成立**；
   输出中 `requires_vernalization=true` 时会附显式警告。
3. **月份按每月 30 天简化**（年 360 天）。物候推演误差远大于此简化误差，可接受；但输出的
   `MM-DD` 是 360 天制近似，勿当日历精确日期用。
4. **参数是主产区代表品种值**，品种间差异可能很大（如马铃薯 TSUM2 跨 1550–2100）。
5. **未本地校准**：置信度固定 `medium`（rubric 0.6），测试中有断言防止其被拔高成 high。

---

## 5. 外部日历通路的数据契约

若日后取得合规日历数据（含 license 与来源），按以下契约 drop 到 `data/plant_calendar.json` 即可生效，
无需改代码：

```json
{
  "meta": {"source": "...", "license": "...", "accessed_at": "YYYY-MM-DD"},
  "crops": [
    {
      "slug": "tomato",
      "common_name": "番茄",
      "category": "vegetable",
      "zones": {"min": 3, "max": 11},
      "windows": [
        {"action": "start_indoors", "start_doy": 45, "end_doy": 75},
        {"action": "transplant",    "start_doy": 105, "end_doy": 135}
      ],
      "days_to_harvest": {"min": 60, "max": 90}
    }
  ]
}
```

`action` 取值：`start_indoors` / `direct_sow` / `transplant` / `plant`。
`start_doy`/`end_doy` 用 **1-365/366 真实 day-of-year**（与本地推导的 360 天制区分）。

---

## 6. 调用方式

```python
from agent import AgriOrchestrator
AgriOrchestrator().call_skill("season_advisory", {...})
```

MCP：`agri_season_advisory`（8 个 agri 工具之一）。
自测：`python agent/plant_calendar.py`、`python agent/season_agent.py`。
回归：`python scripts/test_agents.py`（35 项，含 9 项 SeasonAgent）。
