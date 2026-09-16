# 土壤剖面查询（在线优先 + 离线分区降级）

> 模块：`agent/soil_profile.py`｜MCP 工具：`agri_soil_profile`｜落地日期：2026-09-10
> 起因：闭环巡检连续多日报「SoilGrids API 本机不可达」，核实后发现是**主机名写错**（见下）

## 一、为什么需要它

SoilGrids 的在线点查询在本机**不能作为可靠主源**：

| 主机 | 实测结果 |
|---|---|
| `api.isric.org`（项目此前探的） | HTTP 000 / `exit 6` = **DNS 解析失败，该主机不存在** |
| `rest.isric.org`（官方正确端点） | **HTTP 200**，返回真实 JSON（欧洲点 `phh2o mean=68` → pH 6.8）；但**间歇**——有时 60s+ 挂死，且中国多点返回 `mean: null` |

所以结论不是"API 死了"，而是"**URL 写错了 + 该服务从本机不稳**"。修复 URL 之外，仍需一条**离线兜底**，否则土壤数据在无网/超时时完全缺失。

## 二、设计原则

1. **零依赖**：只用标准库 `urllib` / `json` / `ssl`，不引入 requests、GDAL。
2. **在线优先、离线兜底**：先试 SoilGrids 点查询；失败或空值 → 降级到 `data/zone_meta/global_zones.json` 的分区级土壤。
3. **诚实标注，不夸大**：降级时输出强制带
   - `resolution: "zone"`（而非 `"point"`）
   - `confidence: "low"`
   - `limitations` 中明确写「分区级均值，不可作为地块级施肥依据」
4. **不编造字段**：离线库只有 `ph_range` 与 `texture_hint`，就只输出这两项；**不虚构有机质、速效氮等库里没有的指标**。
5. **pH 适宜性是"推导"不是"编造"**：用分区土壤 pH 区间与作物库 `ph_range` 做区间重叠计算，属可验证的推导。

## 三、接口

```python
from agent.soil_profile import get_soil_profile, probe_soilgrids, ph_fit

get_soil_profile(lat=None, lon=None, zone_id=None, crop=None,
                 online=True, timeout=12) -> dict
```

返回关键字段：

| 字段 | 说明 |
|---|---|
| `resolution` | `"point"`（在线点数据）／`"zone"`（离线分区均值）／`"unavailable"` |
| `confidence` | point→`medium`；zone→`low` |
| `source` | 数据出处（在线为 SoilGrids REST；离线为 `global_zones.json`） |
| `soil` | 在线上为 `properties`（phh2o/clay/sand/silt/soc，SoilGrids 原始单位）；离线为 `ph_range` / `ph_mean` / `texture_hint` |
| `online_attempt` | 在线尝试的 URL 与失败原因（便于排查，不隐藏失败） |
| `crop_ph_fit` | 传入 `crop` 时给出 pH 拟合：`coverage_of_crop_range` 与 `level`（suitable/marginal/narrow/unsuitable） |
| `limitations` | 本次结论的局限清单（下游 Agent 引用时应一并转述） |

MCP 工具 `agri_soil_profile` 参数：`lat` / `lon` / `zone_id` / `crop` / `online`（默认 true）/`timeout_s`（默认 10）。

> 提示：已知服务不稳时，Agent 可传 `online: false` 直接走离线分区数据，**毫秒级返回且确定性高**。

## 四、示例（离线路径，实测输出）

杭州（lat 30.2741, lon 120.1551）+ 作物「小白菜」，`online=false`：

```
resolution: zone
source:     data/zone_meta/global_zones.json（Köppen/FAO 分区均值）
soil:       ph_range [5.5, 7.0]  |  texture_hint 红壤/黄壤为主
confidence: low
crop_ph_fit: 基本适宜（需调酸/调碱）   # 与小白菜 [6.0,7.0] 重叠 1.0 pH 单位
limitations: 分区级均值，同一分区内不同地块差异很大，不可作为地块级施肥依据
```

## 五、局限（明确写出来，避免被过度解读）

- 离线数据是**分区级**（Köppen/FAO 大区均值），**不是地块实测**；同区内差异可达 1 个 pH 单位以上。
- 离线库**无**有机质、速效养分、盐分、CEC 等指标——需要这些时必须走在线或批量下载 SoilGrids 栅格。
- 在线路径深度固定取 **0-5cm** 表层；其余深度需扩展 `_DEPTH`。
- 在线值本身是 **250m 栅格预测均值 + 模型推断**，带不确定性，不是采样实测。
- `AGRI_SOIL_INSECURE=1` 可跳过 TLS 校验（针对本机拦截代理），**仅在本地调试使用**，不得用于生产。

## 六、回归自测

```bash
python agent/soil_profile.py            # 模块自测（5 组断言）
python scripts/test_agents.py           # 含 TestSoilProfile 7 项
python scripts/test_mcp_server.py       # 含 agri_soil_profile 4 项断言
```
