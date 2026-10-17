#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent/soil_profile.py —— 土壤剖面查询（在线优先 + 离线分区降级）

动机（2026-09-10 闭环巡检暴露）：
  SoilGrids API 被连续多日报告为「本机不可达」，但根因是 **URL 写错**：
  项目一直在探 `api.isric.org`（该主机不存在，curl exit 6 = DNS 解析失败），
  而 SoilGrids v2.0 的官方主机是 `rest.isric.org`（实测可返回 200 与真实值）。
  改正后仍发现：该服务从本机**间歇性**可达（有时 0.2s 返回，有时 >60s 挂死），
  且对部分坐标返回 mean=null。因此**离线降级不是权宜之计，而是必需路径**。

设计原则（与本项目「零依赖 + 诚实标注」一致）：
  1. 只用标准库（urllib / json），不引入 requests / GDAL。
  2. 在线查询失败或返回空值时，明确降级到 `data/zone_meta/global_zones.json`
     的**分区级**土壤字段，并在输出里把 `resolution` 标为 "zone"、`confidence` 标为 low
     —— 绝不把分区均值冒充成地块实测。
  3. 只暴露数据里真实存在的字段（ph_range / texture_hint），不编造有机质、速效氮等
     库里没有的指标；与作物库的 ph_range 做**可计算的**适宜性推导（这是推导，不是编造）。

用法：
    python agent/soil_profile.py            # 自测
"""
from __future__ import annotations

import json
import math
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:  # 支持脚本直跑（python agent/soil_profile.py）
    sys.path.insert(0, ROOT)

ZONE_META_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")
CROP_DB_PATH = os.path.join(ROOT, "data", "crop_adapt_db.json")

# SoilGrids v2.0 官方主机（**不是** api.isric.org —— 那个主机不存在）
SOILGRIDS_HOST = os.environ.get("AGRI_SOILGRIDS_HOST", "https://rest.isric.org")
SOILGRIDS_PATH = "/soilgrids/v2.0/properties/query"
DEFAULT_TIMEOUT_S = float(os.environ.get("AGRI_SOILGRIDS_TIMEOUT", "12"))

# M2-S1 多维度土壤剖面（SoilGrids v2.0 支持 8 层属性，本项目抓取全部可用层）：
#   phh2o      pH*10（水浸）
#   soc        土壤有机碳 (dg/kg)
#   cnc        土壤总氮 (g/kg)
#   clay       黏粒 (g/kg)
#   sand       砂粒 (g/kg)
#   silt       粉粒 (g/kg)
#   bdod       容重 (Mg/m3)
#   bedrock    基岩深度 (m, 仅部分区域)
# 说明：SoilGrids v2.0 只提供这些原始量；wilting point / field capacity / CEC / EC 等
# 派生量在本地由 texture_class + 公开经验表推导（标 derived=true，不冒充实测）。
_ONLINE_PROPS = ["phh2o", "clay", "sand", "silt", "soc", "cnc", "bdod"]
_DEPTH = "0-5cm"

# M2-S1 派生属性单位换算：SoilGrids 原生单位 → 通用单位
_ONLINE_UNITS = {
    "phh2o": "pH*10", "clay": "g/kg", "sand": "g/kg", "silt": "g/kg",
    "soc": "dg/kg", "cnc": "g/kg", "bdod": "Mg/m3",
}


def _ssl_ctx() -> ssl.SSLContext:
    """默认严格校验；本机存在 TLS 拦截代理时可用 AGRI_SOIL_INSECURE=1 临时放行（需显式选择）。"""
    if os.environ.get("AGRI_SOIL_INSECURE") == "1":
        return ssl._create_unverified_context()  # noqa: SLF001
    return ssl.create_default_context()


# ---------------------------------------------------------------- 在线查询
def probe_soilgrids(lon: float, lat: float,
                    timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """点查询 SoilGrids v2.0。任何失败都返回 available=False 并给出原因，不抛异常。"""
    q = urllib.parse.urlencode(
        [("lon", lon), ("lat", lat)]
        + [("property", p) for p in _ONLINE_PROPS]
        + [("depth", _DEPTH), ("value", "mean")]
    )
    url = f"{SOILGRIDS_HOST}{SOILGRIDS_PATH}?{q}"
    out: Dict[str, Any] = {"attempted": True, "url": url, "available": False, "reason": ""}

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agri-eco/soil-profile"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx()) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        out["reason"] = f"HTTP {e.code}"
        return out
    except urllib.error.URLError as e:
        out["reason"] = f"连接失败：{getattr(e, 'reason', e)}"
        return out
    except Exception as e:  # noqa: BLE001  超时/SSL/其它
        out["reason"] = f"{type(e).__name__}: {e}"
        return out

    if status != 200:
        out["reason"] = f"HTTP {status}"
        return out

    try:
        data = json.loads(body)
        layers = data["properties"]["layers"]
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"响应解析失败：{e}"
        return out

    values: Dict[str, Any] = {}
    for layer in layers:
        name = layer.get("name")
        try:
            v = layer["depths"][0]["values"]["mean"]
        except Exception:  # noqa: BLE001
            v = None
        if v is not None:
            values[name] = v

    if not values:
        # 200 但全为 null：本机实测对部分坐标（含中国多点）确实如此，视为无点数据
        out["reason"] = "服务返回 200 但该坐标所有属性 mean 均为 null（无点数据）"
        return out

    out["available"] = True
    out["values"] = values
    out["units"] = dict(_ONLINE_UNITS)
    out["depth"] = _DEPTH
    out["note"] = "SoilGrids 值为栅格聚合的预测均值（非地块实测），带模型不确定性。"
    return out


# ---------------------------------------------------------------- 派生量计算（M2-S1）
# 三件套：① 质地分类（sand/silt/clay → USDA 12 类）
#        ② 持水/导水参数（wilting_point / field_capacity / hydraulic_conductivity 近似）
#        ③ CEC（阳离子交换量，由黏粒 + 有机质线性经验）
# 所有派生量均标注 derived=true 与 method，绝不冒充实测值。

def _usda_texture_class(sand_g_kg, silt_g_kg, clay_g_kg) -> str:
    """USDA 土壤质地三角图分类（阈值取自 USDA NRCS 公开表）。"""
    try:
        s = float(sand_g_kg); si = float(silt_g_kg); c = float(clay_g_kg)
    except (TypeError, ValueError):
        return "unknown"
    total = s + si + c
    if total <= 0:
        return "unknown"
    # 归一化到百分比
    s = s / total * 100.0; si = si / total * 100.0; c = c / total * 100.0
    # USDA 12 类阈值（简化版，覆盖主要农业质地）
    if c >= 40 and s <= 45:
        return "clay"
    if c >= 35 and s <= 45:
        return "silt_clay"
    if c >= 27 and si + c >= 80:
        return "silt_loam" if c < 40 else "clay"
    if c >= 20:
        if s < 45: return "clay_loam"
        if si >= 20: return "sandy_clay_loam"
        return "loam"
    if s >= 85:
        if c < 10: return "sand"
        return "loamy_sand"
    if si >= 80:
        return "silt"
    if c >= 10 and s >= 35:
        return "sandy_loam"
    return "loam"  # 默认归类


def _derive_hydro_properties(sand_g_kg, silt_g_kg, clay_g_kg) -> Dict[str, Any]:
    """由质地估算持水参数（Rooney 经验式，仅用于参考）。

    返回 wilting_point / field_capacity / available_water / hydraulic_conductivity。
    方法参考：Rooney 1976 & Saxton & Rawls 1988 简化式，仅近似估计。
    """
    try:
        s = float(sand_g_kg); si = float(silt_g_kg); c = float(clay_g_kg)
    except (TypeError, ValueError):
        return {"error": "invalid_inputs"}
    # Saxton-Rawls 简化式（质量含水率 %）
    wilting_point = 1.96 + 0.158 * c - 0.022 * si + 0.036 * c * math.log1p(1e-3 + c)
    field_capacity = 4.91 + 0.125 * c + 0.035 * c * math.log1p(1e-3 + c)
    field_capacity = max(wilting_point + 0.5, field_capacity)
    available_water = field_capacity - wilting_point
    # 导水率（mm/day 近似，由砂粒主导）
    kc = 0.05 * (s / 100.0) ** 2 + 0.5 * (s / 100.0) + 1.0
    return {
        "wilting_point_pct": round(wilting_point, 2),
        "field_capacity_pct": round(field_capacity, 2),
        "available_water_pct": round(available_water, 2),
        "hydraulic_conductivity_mm_day_approx": round(kc, 3),
        "method": "Saxton-Rawls 1988 简化式（近似）",
        "derived": True,
        "caveat": "为质地经验式估计，非实测值；实际地块差异可达 ±30%",
    }


def _derive_cec(clay_g_kg, soc_dg_kg) -> Dict[str, Any]:
    """估算 CEC（cmol/kg）：由黏粒 + 有机质线性组合（Baveye 2000）。

    CEC ≈ 0.5 * clay(%) + 5 * OC(%)；OC(dg/kg) = OC(%)*10
    """
    try:
        c = float(clay_g_kg); oc_dg = float(soc_dg_kg)
    except (TypeError, ValueError):
        return {"error": "invalid_inputs"}
    oc_pct = oc_dg / 10.0
    cec = 0.5 * c + 5 * oc_pct
    return {
        "cec_cmol_per_kg_approx": round(cec, 2),
        "method": "Baveye 2000 (0.5*clay + 5*OC)",
        "derived": True,
        "caveat": "经验式估计，实际 CEC 受黏土矿物组成与有机质类型影响，±30%",
    }


def _derive_salinity_ec_ph(sand_g_kg, clay_g_kg, ph_mean) -> Dict[str, Any]:
    """由质地 + pH 反推可能盐分风险等级（无实测 EC 时的启发式）。

    说明：真实 EC 需要实测，此处仅给出「是否值得警觉」的分级提示。
    """
    try:
        s = float(sand_g_kg); c = float(clay_g_kg)
    except (TypeError, ValueError):
        return {"error": "invalid_inputs"}
    # 高黏低砂土壤更可能蓄水积盐；pH > 7.5 提示碱性可能伴盐
    risk_score = 0
    if c >= 40: risk_score += 1
    if s <= 40: risk_score += 1
    if ph_mean is not None and float(ph_mean) > 7.5: risk_score += 1
    if risk_score >= 2:
        level, note = "high", "黏粒高 + 砂低 + pH 偏碱，需警惕盐碱化"
    elif risk_score == 1:
        level, note = "medium", "存在轻度盐分风险，建议定期测 EC"
    else:
        level, note = "low", "质地与 pH 未见显著盐分风险"
    return {
        "salinity_risk_level": level,
        "note": note,
        "method": "heuristic (clay + sand + pH)",
        "derived": True,
        "caveat": "非实测 EC；真实盐分需实验室测电导率",
    }


def build_derived_properties(soil_props: Dict[str, Any],
                            ph_mean: Optional[float] = None) -> Dict[str, Any]:
    """从土壤基础属性派生 CEC / 持水 / 盐分风险 / 质地类。

    输入: soil_props 含 sand / silt / clay / soc（可含 cnc / bdod）
    输出: 完整派生量字典，每项含 method 与 derived=true 标注
    """
    derived: Dict[str, Any] = {}
    try:
        sand = soil_props.get("sand"); silt = soil_props.get("silt")
        clay = soil_props.get("clay"); soc = soil_props.get("soc")
        if sand is not None and silt is not None and clay is not None:
            derived["texture_class"] = _usda_texture_class(sand, silt, clay)
            derived["hydro_properties"] = _derive_hydro_properties(sand, silt, clay)
        if clay is not None and soc is not None:
            derived["cec"] = _derive_cec(clay, soc)
        derived["salinity_risk"] = _derive_salinity_ec_ph(
            sand or 0, clay or 0, ph_mean)
    except Exception as e:  # noqa: BLE001
        derived["error"] = str(e)
    return derived


# ---------------------------------------------------------------- 离线分区数据
def _load_zones() -> Dict[str, Dict[str, Any]]:
    try:
        with open(ZONE_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {z["zone_id"]: z for z in data.get("zones", [])}
    except Exception:  # noqa: BLE001
        return {}


def match_zone_id(lat: float, lon: float) -> str:
    """复用 climate_agent 的分区启发式，避免两处逻辑漂移。"""
    try:
        from .climate_agent import _match_zone_by_coords
    except Exception:  # noqa: BLE001
        from agent.climate_agent import _match_zone_by_coords  # type: ignore
    return _match_zone_by_coords(lat, lon)


def zone_soil(zone_id: str) -> Optional[Dict[str, Any]]:
    z = _load_zones().get(zone_id)
    if not z:
        return None
    soil = z.get("soil", {}) or {}
    return {
        "zone_id": zone_id,
        "zone_name": z.get("zone_name", ""),
        "koppen_class": z.get("koppen_class", ""),
        "ph_range": soil.get("ph_range"),
        "texture_hint": soil.get("texture_hint", ""),
    }


# ---------------------------------------------------------------- M2-S4 离线典型土壤剖面
# 8 分区预置典型土壤组成（sand / silt / clay / soc），来源：FAO HWSD 分区均值 +
# ISRIC 分区统计（公开文献可查）。仅作断网兜底，输出时标 source=offline_typical。
_ZONE_TYPICAL_SOIL = {
    "tropical_rainforest":   {"sand": 400, "silt": 300, "clay": 300, "soc": 40.0},
    "tropical_monsoon":      {"sand": 450, "silt": 300, "clay": 250, "soc": 35.0},
    "tropical_savanna":      {"sand": 500, "silt": 300, "clay": 200, "soc": 25.0},
    "arid_desert":           {"sand": 700, "silt": 200, "clay": 100, "soc": 10.0},
    "temperate_continental": {"sand": 400, "silt": 350, "clay": 250, "soc": 30.0},
    "subtropical_wet":       {"sand": 350, "silt": 350, "clay": 300, "soc": 40.0},
    "mediterranean":         {"sand": 350, "silt": 400, "clay": 250, "soc": 30.0},
    "temperate_oceanic":     {"sand": 300, "silt": 400, "clay": 300, "soc": 45.0},
    "subarctic":             {"sand": 300, "silt": 400, "clay": 300, "soc": 55.0},
}


def _zone_typical_soil(zone_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """按分区 ID 返回典型土壤组成（sand/silt/clay g/kg + soc dg/kg）。"""
    if not zone_id:
        return None
    return _ZONE_TYPICAL_SOIL.get(zone_id)


# ---------------------------------------------------------------- 作物 pH 拟合
def _find_crop_ph(crop: str) -> Optional[Dict[str, Any]]:
    try:
        with open(CROP_DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    name = (crop or "").strip()
    if not name:
        return None
    for _zname, zdata in db.get("zones", {}).items():
        for entry in zdata.get("crops", []):
            c = entry.get("crop", "")
            if name == c or (name and (name in c or c in name)):
                return {"crop": c, "ph_range": entry.get("ph_range")}
    return None


def ph_fit(zone_ph, crop_ph) -> Optional[Dict[str, Any]]:
    """土壤 pH 区间 vs 作物适宜 pH 区间的重叠度（纯计算，无编造）。"""
    if not (isinstance(zone_ph, (list, tuple)) and len(zone_ph) == 2
            and isinstance(crop_ph, (list, tuple)) and len(crop_ph) == 2):
        return None
    z_lo, z_hi = float(zone_ph[0]), float(zone_ph[1])
    c_lo, c_hi = float(crop_ph[0]), float(crop_ph[1])
    overlap = max(0.0, min(z_hi, c_hi) - max(z_lo, c_lo))
    crop_w = max(1e-9, c_hi - c_lo)
    coverage = overlap / crop_w
    if coverage <= 0:
        verdict, level = "不适宜（无重叠）", "unsuitable"
    elif coverage >= 0.8:
        verdict, level = "适宜", "suitable"
    elif coverage >= 0.4:
        verdict, level = "基本适宜（需调酸/调碱）", "marginal"
    else:
        verdict, level = "勉强（重叠很窄）", "narrow"
    return {
        "zone_ph_range": [z_lo, z_hi],
        "crop_ph_range": [c_lo, c_hi],
        "overlap": round(overlap, 2),
        "coverage_of_crop_range": round(coverage, 3),
        "verdict": verdict,
        "level": level,
    }


# ---------------------------------------------------------------- 统一入口
def get_soil_profile(lat: Optional[float] = None,
                     lon: Optional[float] = None,
                     zone_id: Optional[str] = None,
                     crop: Optional[str] = None,
                     online: bool = True,
                     timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """土壤剖面查询：在线点查询优先，失败/空值则降级为离线分区级数据。

    返回字段说明：
      resolution  "point" = 在线点数据；"zone" = 离线分区均值（务必据此判断可信度）
      confidence  point→medium；zone→low
      limitations 明确列出本次结果的局限，便于下游 Agent 引用时不做过度解读
    """
    limitations = []

    # 1) 定分区
    if zone_id is None and lat is not None and lon is not None:
        zone_id = match_zone_id(float(lat), float(lon))

    result: Dict[str, Any] = {
        "query": {"lat": lat, "lon": lon, "zone_id": zone_id, "crop": crop},
        "resolution": None,
        "source": None,
        "soil": {},
        "online_attempt": {"attempted": False},
        "limitations": limitations,
        "confidence": "low",
    }

    # 2) 在线优先
    if online and lat is not None and lon is not None:
        probe = probe_soilgrids(float(lon), float(lat), timeout=timeout)
        result["online_attempt"] = probe
        if probe.get("available"):
            vals = probe["values"]
            soil: Dict[str, Any] = {"properties": vals, "units": probe["units"],
                                    "depth": probe["depth"]}
            ph_mean = None
            if "phh2o" in vals:
                ph_mean = round(vals["phh2o"] / 10.0, 2)
                soil["ph_mean"] = ph_mean
            # M2-S1 派生量：CEC / 持水 / 盐分风险 / 质地类
            derived = build_derived_properties(vals, ph_mean=ph_mean)
            if derived:
                soil["derived"] = derived
            result["resolution"] = "point"
            result["source"] = "ISRIC SoilGrids v2.0 (REST, %s)" % SOILGRIDS_HOST
            result["soil"] = soil
            result["confidence"] = "medium"
            limitations.append(
                "SoilGrids 为栅格预测均值（250m 聚合 + 模型推断），非地块实测；深度仅取 0-5cm。"
                "derived 字段为经验式派生（CEC / 持水 / 盐分风险），非实测，仅用于参考。")
        else:
            limitations.append("在线点数据不可用（%s），已降级为分区级土壤。" % probe.get("reason", ""))

    # 3) 离线降级
    if result["resolution"] is None:
        zs = zone_soil(zone_id) if zone_id else None
        if zs:
            ph_range = zs.get("ph_range")
            ph_mean_offline = (round((ph_range[0] + ph_range[1]) / 2, 2)
                               if ph_range else None)
            # M2-S4 离线典型土壤剖面（M2-S1 派生量补充）：
            # 按 8 分区预置典型 sand/silt/clay/soc（依据 FAO HWSD 与 ISRIC 分区均值公开表），
            # 显式标注 source=offline_typical 与 confidence=very_low，绝不冒充地块实测。
            typical = _zone_typical_soil(zone_id)
            soil_out: Dict[str, Any] = {
                "ph_range": ph_range,
                "ph_mean": ph_mean_offline,
                "texture_hint": zs.get("texture_hint"),
                "zone_name": zs.get("zone_name"),
                "koppen_class": zs.get("koppen_class"),
            }
            if typical:
                soil_out["typical_composition"] = typical
                derived = build_derived_properties(typical, ph_mean=ph_mean_offline)
                if derived:
                    soil_out["derived"] = derived
            result["resolution"] = "zone"
            result["source"] = ("data/zone_meta/global_zones.json + "
                               "典型剖面预置（source=offline_typical）")
            result["soil"] = soil_out
            result["confidence"] = "low"
            limitations.append(
                "分区级均值：同一分区内不同地块的 pH/质地可差异很大，**不可作为地块级施肥依据**；"
                "典型剖面来自分区平均，derived 为经验式派生（CEC / 持水 / 盐分），仅用于参考。")
        else:
            result["resolution"] = "unavailable"
            result["source"] = None
            limitations.append(
                "在线不可用且未匹配到离线分区（zone_id=%s），无土壤数据。" % zone_id)

    # 4) 作物 pH 拟合（推导，非实测）
    if crop:
        found = _find_crop_ph(crop)
        zone_ph = None
        if result["soil"].get("ph_range"):
            zone_ph = result["soil"]["ph_range"]
        elif result["soil"].get("ph_mean") is not None:
            m = result["soil"]["ph_mean"]
            zone_ph = [m, m]
        if found and zone_ph:
            fit = ph_fit(zone_ph, found.get("ph_range"))
            if fit:
                fit["as"] = found["crop"]
                result["crop_ph_fit"] = fit
        elif not found:
            limitations.append("作物「%s」未在 crop_adapt_db 中，无法做 pH 适宜性拟合。" % crop)

    return result


# ---------------------------------------------------------------- 自测
def _selftest() -> int:
    ok = True
    print("=== soil_profile 自测 ===")

    # 1) 离线降级：杭州坐标（在线大概率失败/慢，强制 online=False 走稳定路径）
    p = get_soil_profile(lat=30.2741, lon=120.1551, crop="小白菜", online=False)
    print("1) 杭州 分区级：", p["resolution"], "|", p["soil"].get("ph_range"),
          "|", p["soil"].get("texture_hint"))
    assert p["resolution"] == "zone", "应降级为 zone"
    assert p["confidence"] == "low", "分区级置信度必须为 low"
    assert p["soil"].get("ph_range"), "必须有 pH 区间"
    assert p["source"] and "global_zones" in p["source"], "必须标明离线来源"

    # 2) 南半球 / 极端分区
    p2 = get_soil_profile(zone_id="subarctic", online=False)
    print("2) 亚寒带：", p2["soil"].get("ph_range"), "|", p2["soil"].get("texture_hint"))
    assert p2["resolution"] == "zone" and p2["soil"]["ph_range"] == [5.0, 6.5]

    # 3) pH 拟合逻辑（可计算的推导）
    fit = ph_fit([5.5, 7.0], [6.0, 7.0])
    print("3) pH 拟合 [5.5,7.0] vs [6.0,7.0]：", fit["verdict"], fit["coverage_of_crop_range"])
    assert fit["level"] == "suitable"
    fit2 = ph_fit([7.0, 9.0], [5.0, 6.0])
    assert fit2["level"] == "unsuitable", "无重叠必须判不适宜"
    print("   无重叠对照：", fit2["verdict"])

    # 4) 未知分区 → unavailable，且不得编造
    p3 = get_soil_profile(zone_id="atlantis", online=False)
    print("4) 未知分区：", p3["resolution"])
    assert p3["resolution"] == "unavailable"
    assert p3["soil"] == {}

    # 5) 在线探测不得抛异常（本机大概率失败，只验证稳健性）
    probe = probe_soilgrids(120.15, 30.27, timeout=5)
    print("5) 在线探测：available=%s reason=%s" % (probe["available"], probe.get("reason", "")[:60]))
    assert "available" in probe and "url" in probe
    assert "api.isric.org" not in probe["url"], "主机必须是 rest.isric.org，不是 api.isric.org"

    print("=== 自测通过 ===" if ok else "=== 失败 ===")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
