"""engine/derived.py —— 温湿派生量（VPD / 露点）零依赖计算。

为什么需要它
------------
Env Recipe v1 的 environment 块只存「设定值」（temperature / humidity 的上下限），
没有行业事实标准的派生量。竞品对照（见 docs/competitive_scan_2026-09-17.md）：
Home Assistant 生态的 Horticulture-Assistant 与已归档的 OpenFarm 都把 **VPD**
（Vapor Pressure Deficit，水汽压亏缺）和**露点**当成温室/箱体调控的核心指标——
因为它们直接决定蒸腾速率与病害风险，比单看温度或湿度更接近「植物实际感受到的
干湿」。两者都只是温湿的纯算术变换，不需要任何第三方包，符合本项目零依赖约束。

单位与公式
----------
- VPD：kPa。`es(T) = 0.6108 * exp(17.27*T/(T+237.3))`（Magnus 近似），
  `VPD = es(T) * (1 - RH/100)`。
- 露点：°C。`Td = 237.3*γ/(17.27-γ)`，其中
  `γ = ln(RH/100) + 17.27*T/(T+237.3)`。

经验区间（叶菜类通用参考，非某作物的唯一正确答案）
--------------------------------------------------
- VPD < 0.5 kPa：过湿，真菌性病害（白粉病/霜霉病）风险升高，蒸腾不足。
- VPD 0.5–1.0 kPa：多数叶菜/果菜的舒适区。
- VPD 1.0–1.5 kPa：可接受但蒸腾压力上升，需加强通风与补水。
- VPD > 1.5 kPa：蒸腾胁迫，叶片易萎蔫。
- 露点 >= 日温下限 且 VPD 已偏低 → 结露风险（叶片表面持续湿润 = 病害温床）。

注意
----
    这些是**派生量**，不应写回配方 JSON（否则就成了两份可漂移的数据源）。
    正确用法是读取配方后即时计算并展示，参见 scripts/validate_env_recipe.py 的
    ``--derived`` 报告模式。

    flags 与 observations 的区分（重要）
    -----------------------------------
    ``flags`` 只放**可执行层面有问题**的判定：标称点（区间中点）已处蒸腾胁迫/过湿、
    夜间结露风险。``observations`` 放**数据粒度线索**：包络跨度偏宽。
    包络跨度不作硬告警，因为露天/干旱区配方（``arid__*``）的昼夜温差是气候描述
    而非设定错误，把它们当告警会在 110 份配方上报出 63 份噪声，淹没唯一的真问题。
    """
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

# VPD 经验区间（叶菜类通用参考）
VPD_OPTIMAL: Tuple[float, float] = (0.5, 1.0)
VPD_STRESS: float = 1.5
# 包络跨度阈值：超过此值仅提示「区间偏宽」，不计为告警（见下方 flags/observations 区分）
ENVELOPE_SPAN_WARN: float = 1.5


def saturation_vapor_pressure(temp_c: float) -> float:
    """饱和水汽压 es(T)，单位 kPa。Magnus 近似式，适用 -45..60°C。"""
    t = float(temp_c)
    return 0.6108 * math.exp(17.27 * t / (t + 237.3))


def vpd(temp_c: float, humidity_pct: float) -> float:
    """水汽压亏缺 VPD，单位 kPa。"""
    return saturation_vapor_pressure(temp_c) * (1.0 - max(0.0, min(100.0, float(humidity_pct))) / 100.0)


def dew_point(temp_c: float, humidity_pct: float) -> float:
    """露点温度，单位 °C。湿度取 0.1% 下限避免 ln(0)。"""
    t = float(temp_c)
    rh = max(0.1, min(100.0, float(humidity_pct)))
    gamma = math.log(rh / 100.0) + 17.27 * t / (t + 237.3)
    return 237.3 * gamma / (17.27 - gamma)


def vpd_band_label(v: float) -> str:
    """把 VPD 数值翻译成可读的风险带。"""
    if v < VPD_OPTIMAL[0]:
        return "过湿（<%.1f kPa，真菌病害风险升高）" % VPD_OPTIMAL[0]
    if v <= VPD_OPTIMAL[1]:
        return "舒适区（%.1f–%.1f kPa）" % VPD_OPTIMAL
    if v <= VPD_STRESS:
        return "偏干（%.1f–%.1f kPa，蒸腾压力上升）" % (VPD_OPTIMAL[1], VPD_STRESS)
    return "胁迫（>%.1f kPa，易萎蔫）" % VPD_STRESS


def derive_from_recipe(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """从一份 Env Recipe 里提取温湿设定，算出 VPD / 露点区间。

    返回结构：
        {
          "available": bool,
          "inputs": {"temp_day_c", "temp_night_c", "humidity_min_pct", "humidity_max_pct"},
          "vkd": {...}, "dew_point": {...},
          "flags": [str, ...],        # 硬告警：标称点胁迫/过湿、结露风险（可执行层面有问题）
          "observations": [str, ...], # 软提示：区间偏宽等数据粒度线索（信息保留，不计为告警）
          "notes": [str, ...]
        }
    配方缺温或湿字段时 available=False 并给出原因，绝不编造数值。
    """
    out: Dict[str, Any] = {
        "available": False, "inputs": {}, "vkd": None, "dew_point": None,
        "flags": [], "observations": [], "notes": [],
    }
    env = (recipe or {}).get("environment") or {}
    temp = env.get("temperature") or {}
    hum = env.get("humidity") or {}

    day_c = temp.get("day_c")
    night_c = temp.get("night_c")
    hmin = hum.get("min_pct")
    hmax = hum.get("max_pct")
    missing = [k for k, v in (
        ("temperature.day_c", day_c), ("temperature.night_c", night_c),
        ("humidity.min_pct", hmin), ("humidity.max_pct", hmax)) if v is None]
    if missing:
        out["notes"].append("缺字段 %s，无法计算派生量" % "/".join(missing))
        return out

    out["available"] = True
    out["inputs"] = {
        "temp_day_c": day_c, "temp_night_c": night_c,
        "humidity_min_pct": hmin, "humidity_max_pct": hmax,
    }

    # 标称工作点：温湿区间中点。这是「按配方设定时实际运行在哪」的答案，
    # 比包络极值更接近可执行配置（区间越宽，包络越必然告警，噪声大）。
    t_mid = (float(day_c) + float(night_c)) / 2.0
    h_mid = (float(hmin) + float(hmax)) / 2.0
    v_nom = vpd(t_mid, h_mid)
    out["vkd"] = {
        "nominal_kpa": round(v_nom, 3),
        "nominal_label": vpd_band_label(v_nom),
        "nominal_inputs": {"temp_c": round(t_mid, 2), "humidity_pct": round(h_mid, 2)},
    }

    # VPD 包络：温度高+湿度低 → 干；温度低+湿度高 → 湿
    v_max = vpd(day_c, hmin)
    v_min = vpd(night_c, hmax)
    out["vkd"]["envelope"] = {
        "min_kpa": round(v_min, 3), "max_kpa": round(v_max, 3),
        "min_label": vpd_band_label(v_min), "max_label": vpd_band_label(v_max),
        "span_kpa": round(v_max - v_min, 3),
    }

    d_day = dew_point(day_c, hmax)   # 白天高温 + 高湿 → 露点最高
    d_night = dew_point(night_c, hmax)
    out["dew_point"] = {
        "day_max_c": round(d_day, 2), "night_c": round(d_night, 2),
    }

    # 告警：优先看标称点（可执行），包络只作「区间过宽」提示
    if v_nom > VPD_STRESS:
        out["flags"].append(
            "标称 VPD=%.2f kPa > %.1f，按区间中点运行即处蒸腾胁迫" % (v_nom, VPD_STRESS))
    elif v_nom < VPD_OPTIMAL[0]:
        out["flags"].append(
            "标称 VPD=%.2f kPa < %.1f，按区间中点运行即处过湿（真菌病害风险）"
            % (v_nom, VPD_OPTIMAL[0]))
    # 区间宽度提示：跨度大意味着「只设范围不给设定点」时条件会在极端间漂移。
    # 降级为 observation 而非 flag 的理由：
    #   1) 可执行的判定依据是标称点（区间中点），已由上面两条覆盖；
    #   2) 露天/干旱区配方（arid__*）的昼夜温差不受箱体约束，天然大，是气候描述而非设定错误；
    #   3) 若把区间宽度当硬告警，110 份配方会报出 63 份噪声，反而淹没那 1 份真问题。
    if (v_max - v_min) > ENVELOPE_SPAN_WARN:
        out["observations"].append(
            "VPD 包络跨度 %.2f kPa（%.2f–%.2f）> %.1f，温湿区间偏宽；"
            "露天/干旱区为正常气候描述，箱体场景建议收窄或给出设定点"
            % (v_max - v_min, v_min, v_max, ENVELOPE_SPAN_WARN))
    # 结露判据：露点逼近最低温 → 基质/叶片表面易凝水
    if d_night >= float(night_c) - 1.0:
        out["flags"].append(
            "夜露点 %.2f°C 逼近夜温 %.1f°C，结露风险高（叶片持续湿润=病害温床）"
            % (d_night, float(night_c)))

    out["notes"].append(
        "VPD/露点由 Magnus 近似式从温湿设定即时派生，未写回配方 JSON；"
        "区间为叶菜类通用参考，非该作物的唯一正确答案。")
    return out


def audit_recipes(recipes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量体检：统计有多少配方带派生量告警，返回聚合结论。

    flags（硬告警）与 observations（软提示）分开统计——前者是可执行层面的问题
    （标称点胁迫/过湿、结露），后者是数据粒度线索（区间偏宽），不应混为一谈。
    """
    rows: List[Dict[str, Any]] = []
    flags: Dict[str, int] = {}
    observations: Dict[str, int] = {}
    for r in recipes:
        d = derive_from_recipe(r)
        for f in d.get("flags", []):
            key = f.split("，")[0]
            flags[key] = flags.get(key, 0) + 1
        for o in d.get("observations", []):
            key = o.split("，")[0]
            observations[key] = observations.get(key, 0) + 1
        rows.append({
            "recipe": r.get("crop", {}).get("name") or r.get("crop"),
            "zone": r.get("stage", {}).get("zone") if isinstance(r.get("stage"), dict) else None,
            "available": d.get("available"),
            "vkd": d.get("vkd"),
            "flags": d.get("flags"),
            "observations": d.get("observations"),
        })
    return {
        "total": len(recipes),
        "available": sum(1 for x in rows if x["available"]),
        "with_flags": sum(1 for x in rows if x["flags"]),
        "with_observations": sum(1 for x in rows if x["observations"]),
        "flag_kinds": dict(sorted(flags.items(), key=lambda kv: -kv[1])),
        "observation_kinds": dict(sorted(observations.items(), key=lambda kv: -kv[1])),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# 派生量扩展（P1-1）：DLI 与播种深度
# 遵循同一铁律：派生量不写回配方 JSON，运行时从分区级输入数据即时推导。
# ---------------------------------------------------------------------------

_ZONE_META_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "zone_meta", "global_zones.json")


def derive_dli(zone_id: str) -> Dict[str, Any]:
    """按分区推导 DLI（每日光积分）。

    数据来源：global_zones.json 的 climate_baseline.dli_annual_mol_m2_day
    （NASA POWER ALLSKY_SFC_SW_DWN，全谱短波辐射的光子当量，非 PAR）。

    返回：
        {
          "available": bool,
          "mol_m2_day": float | None,
          "source": {...} | None,
          "note": str
        }
    分区无坐标或数据未回填时 available=False，绝不编造数值。
    """
    out: Dict[str, Any] = {
        "available": False, "mol_m2_day": None, "source": None,
        "note": "",
    }
    try:
        with open(_ZONE_META_PATH, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        out["note"] = "读取 global_zones.json 失败"
        return out
    for zd in meta.get("zones", []):
        if zd.get("zone_id") != zone_id:
            continue
        cb = zd.get("climate_baseline", {}) or {}
        val = cb.get("dli_annual_mol_m2_day")
        src = cb.get("dli_source")
        if isinstance(val, (int, float)):
            out["available"] = True
            out["mol_m2_day"] = float(val)
            out["source"] = src
            out["note"] = (
                "全谱短波辐射光子当量，非标准 PAR DLI；PAR 占全谱约 45%-50%"
                "（项目内无实测），专业应用请自行乘 PAR 比例。"
            )
        else:
            out["note"] = "该分区 climate_baseline 无 DLI 数据（未回填）"
        return out
    out["note"] = "未知分区 %r" % zone_id
    return out


def sowing_depth_cm(growth_days: Optional[int]) -> Optional[float]:
    """播种深度估计（cm）。复用 agent/growth_agent.py 的公式 round(gd/200, 1)。

    growth_days 缺失或非正时返回 None（不编造）。
    """
    if not growth_days or growth_days <= 0:
        return None
    return max(0.1, round(growth_days / 200.0, 1))
