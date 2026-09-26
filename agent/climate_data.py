"""climate_data — 零依赖月度气候获取（NASA POWER 主用 / Open-Meteo 兜底）。

这是 P0~P3 数据接地路线的共同地基：
  - P0：season_agent 在缺 monthly_mean_c 但给 lat/lon 时自动拉取，干掉用户手填 12 月均温
  - P1：固化 6 分区代表点气候基线（离线可读）
  - P2：GBIF 校验拉丁名（本模块不直接用，但复用同一 provenance 习惯）
  - P3：生态位包络反推（对每个 GBIF 分布点调本模块取气候）

设计约束（来自 docs/data_acquisition_decision.md）：
  - 仅用**许可干净**的源：NASA POWER（公有领域）、Open-Meteo（CC BY 4.0）。
    不抓 GAEZ/EPPO 门户（无 API / 条款读不全），不接 FAOSTAT（本网超时）。
  - 每次取数都带 provenance：source / url / license / accessed_at / note。
  - 本地缓存（data/_demo_runtime/climate_cache），避免重复打 API、支持离线兜底。
  - 纯标准库（urllib），无任何第三方依赖。

调用示例：
    from agent.climate_data import fetch_monthly_climate
    cl = fetch_monthly_climate(30.2741, 120.1551)
    print(cl["monthly_mean_c"], cl["provenance"])
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CACHE_DIR = os.path.join(ROOT, "data", "_demo_runtime", "climate_cache")
ZONE_META_PATH = os.path.join(ROOT, "data", "zone_meta", "global_zones.json")

# 月度 point 接口仅支持这些参数（ALLSKY_SRF 是日值，月度会 422）；
# 响应里降水键被 POWER 改名为 PRECTOTCORR。
POWER_PARAMS = "T2M,PRECTOT,RH2M"
POWER_LICENSE = "NASA POWER (public domain, https://power.larc.nasa.gov/docs/services/api/)"
OM_LICENSE = "Open-Meteo (CC BY 4.0, https://open-meteo.com/en/terms)"

# 单位口径（2026-09-23 核实并固化，防止后续被「修正」而静默改写校准分）：
# `monthly_precip_mm` 虽是月度序列，但每个元素是**该月日均降水（mm/day）**，
# 不是月累计量（mm/month）。两个源都是这个口径：
#   - NASA POWER 月度 point 接口的 PRECTOTCORR 聚合结果是日均值
#     （实测杭州 30.27N/120.15E = [2,2,2,...]，12 个月合计 24；真实月累计约 120mm）；
#   - Open-Meteo 走日值 precipitation_sum 再按月取均值，同样是 mm/day。
# 之所以两个源一致很重要：niche_envelope_calibrate.score_zone 的降水通道（权重 0.4）
# 是拿作物包络与分区基线做**同口径区间命中**比较。只要不擅自把某一侧乘 30
# 改成月累计，比较就仍然自洽；一旦改成月累计，107 个已固化 adapt_score 会整体改写，
# 且 harness 数据基线/410 项测试基线同时失效。因此**不得**为本字段乘天数。
PRECIP_UNITS = "mm/day"

_HTTP_TIMEOUT = 25
_UA = {"User-Agent": "agri-eco-demo/1.0 (contact: demo)"}


def _http_get_json(url: str, timeout: int = _HTTP_TIMEOUT) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _round_coord(v: float) -> float:
    return round(float(v), 2)


def _cache_path(lat: float, lon: float, cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{_round_coord(lat)}_{_round_coord(lon)}.json")


def _read_cache(lat: float, lon: float, cache_dir: str,
                max_age_days: int = 30) -> Optional[Dict[str, Any]]:
    p = _cache_path(lat, lon, cache_dir)
    if not os.path.exists(p):
        return None
    try:
        age_days = (time.time() - os.path.getmtime(p)) / 86400.0
        if age_days > max_age_days:
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(lat: float, lon: float, cache_dir: str, data: Dict[str, Any]) -> None:
    try:
        with open(_cache_path(lat, lon, cache_dir), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# 源 1：NASA POWER（公有领域，月度 point 接口）
# ---------------------------------------------------------------------------
def _fetch_power(lat: float, lon: float, start_year: int, end_year: int) -> Optional[Dict[str, Any]]:
    url = (
        "https://power.larc.nasa.gov/api/temporal/monthly/point"
        f"?parameters={POWER_PARAMS}&community=RE"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_year}&end={end_year}&format=JSON"
    )
    try:
        data = _http_get_json(url)
    except Exception:
        return None
    params = (data.get("properties") or {}).get("parameter") or {}
    t2m = params.get("T2M")
    if not t2m:
        return None
    monthly_temp = _aggregate_power_monthly(t2m)
    # 降水键在响应中被 POWER 改名为 PRECTOTCORR
    precip = _aggregate_power_monthly(params.get("PRECTOTCORR") or params.get("PRECTOT") or {})
    rh = _aggregate_power_monthly(params.get("RH2M") or {})
    if any(m is None for m in monthly_temp):
        return None
    return {
        "monthly_mean_c": monthly_temp,
        "monthly_precip_mm": precip,
        "monthly_precip_mm_units": PRECIP_UNITS,  # 每个元素是 mm/日，不是月累计
        "monthly_rh_pct": rh,
        "monthly_srad_kwh_m2_day": None,  # 月度接口无太阳辐射，按需走日值/模型
        "source": "NASA POWER",
        "license": POWER_LICENSE,
        "url": url,
    }


def _aggregate_power_monthly(param_dict: Dict[str, Any]) -> List[Optional[float]]:
    by_month: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    for k, v in param_dict.items():
        if v is None:
            continue
        try:
            mm = int(str(k)[-2:])
            if 1 <= mm <= 12:
                by_month[mm].append(float(v))
        except (TypeError, ValueError):
            continue
    out: List[Optional[float]] = []
    for m in range(1, 13):
        vs = by_month[m]
        out.append(round(sum(vs) / len(vs), 2) if vs else None)
    return out


# ---------------------------------------------------------------------------
# 源 2：Open-Meteo（CC BY 4.0，archive 日值 → 月均聚合）
# ---------------------------------------------------------------------------
def _fetch_open_meteo(lat: float, lon: float, start_year: int, end_year: int) -> Optional[Dict[str, Any]]:
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={start_year}-01-01&end_date={end_year}-12-31"
        "&daily=temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean"
        "&timezone=UTC"
    )
    try:
        data = _http_get_json(url)
    except Exception:
        return None
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    temps = daily.get("temperature_2m_mean") or []
    precs = daily.get("precipitation_sum") or []
    rhs = daily.get("relative_humidity_2m_mean") or []
    if not (times and temps) or len(temps) != len(times):
        return None
    by_month: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    by_month_p: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    by_month_r: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    for i, t in enumerate(times):
        try:
            mm = int(t[5:7])
        except Exception:
            continue
        if 1 <= mm <= 12 and temps[i] is not None:
            by_month[mm].append(float(temps[i]))
        if 1 <= mm <= 12 and i < len(precs) and precs[i] is not None:
            by_month_p[mm].append(float(precs[i]))
        if 1 <= mm <= 12 and i < len(rhs) and rhs[i] is not None:
            by_month_r[mm].append(float(rhs[i]))
    monthly_temp = [round(sum(vs) / len(vs), 2) if vs else None for vs in by_month.values()]
    if any(m is None for m in monthly_temp):
        return None
    return {
        "monthly_mean_c": monthly_temp,
        "monthly_precip_mm": [round(sum(vs) / len(vs), 1) if vs else None for vs in by_month_p.values()],
        "monthly_precip_mm_units": PRECIP_UNITS,  # 日值按月取均值 = mm/日，与 POWER 口径一致
        "monthly_rh_pct": [round(sum(vs) / len(vs), 1) if vs else None for vs in by_month_r.values()],
        "source": "Open-Meteo",
        "license": OM_LICENSE,
        "url": url,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def fetch_monthly_climate(lat: float, lon: float, years: int = 5,
                          cache_dir: Optional[str] = None,
                          force_refresh: bool = False,
                          prefer: str = "power") -> Dict[str, Any]:
    """按经纬度获取 12 个月均温（含降水/湿度/太阳辐射可选）。

    返回结构：
        {
          "monthly_mean_c": [12],
          "monthly_precip_mm": [12] | None,         # 元素单位见 monthly_precip_mm_units
          "monthly_precip_mm_units": "mm/day",      # 日平均降水，**不是月累计**（勿乘天数）
          "monthly_rh_pct": [12] | None,
          "monthly_srad_kwh_m2_day": [12] | None,   # 仅 POWER 提供
          "source": "NASA POWER" | "Open-Meteo",
          "license": "...",
          "url": "...",                                # 实际请求 URL（provenance）
          "accessed_at": "2026-09-22T...Z",
          "lat": 30.27, "lon": 120.16,
          "years_used": [2020, 2024],
          "provenance": {source, url, license, accessed_at, note},
          "cached": bool
        }
    失败（两源都挂）时返回 {"error": "...", "monthly_mean_c": None}。
    """
    try:
        lat = float(lat); lon = float(lon)
    except (TypeError, ValueError):
        return {"error": "lat/lon 必须是数字", "monthly_mean_c": None}
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {"error": "lat/lon 超出合法范围", "monthly_mean_c": None}

    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    end_year = 2024
    start_year = max(2000, end_year - max(1, int(years)) + 1)

    if not force_refresh:
        cached = _read_cache(lat, lon, cache_dir)
        if cached and cached.get("monthly_mean_c"):
            cached = dict(cached)
            cached["cached"] = True
            # 老缓存写于单位标注之前，补齐口径字段保证新旧缓存同构。
            cached.setdefault("monthly_precip_mm_units", PRECIP_UNITS)
            return cached

    result: Optional[Dict[str, Any]] = None
    order = ["power", "open_meteo"] if prefer == "power" else ["open_meteo", "power"]
    for src in order:
        if src == "power":
            result = _fetch_power(lat, lon, start_year, end_year)
        else:
            result = _fetch_open_meteo(lat, lon, start_year, end_year)
        if result and result.get("monthly_mean_c") and all(m is not None for m in result["monthly_mean_c"]):
            break
        result = None

    if not result:
        return {"error": "NASA POWER 与 Open-Meteo 均未能返回有效气候（网络不可达或坐标无效）",
                "monthly_mean_c": None}

    result["accessed_at"] = _now_iso()
    result["lat"] = _round_coord(lat)
    result["lon"] = _round_coord(lon)
    result["years_used"] = [start_year, end_year]
    result["cached"] = False
    result["provenance"] = {
        "source": result["source"],
        "url": result["url"],
        "license": result["license"],
        "accessed_at": result["accessed_at"],
        "note": "由 NASA POWER / Open-Meteo 实时获取的真实气候常态，非手编近似；"
                "已写入本地缓存（data/_demo_runtime/climate_cache）用于离线兜底。"
                f"注意 monthly_precip_mm 的元素单位是 {PRECIP_UNITS}（月内日平均降水），"
                "不是月累计量，不得乘天数换算。",
    }
    _write_cache(lat, lon, cache_dir, result)
    return result


# ---------------------------------------------------------------------------
# P1：离线读取已固化的分区气候基线（无需联网）
# ---------------------------------------------------------------------------
def get_zone_climate_baseline(zone_id: str, zone_meta_path: str = ZONE_META_PATH) -> Optional[Dict[str, Any]]:
    """读取 global_zones.json 中某分区已固化的 climate_baseline（P1 产物）。

    返回 dict 含 monthly_mean_c / monthly_precip_mm（元素单位 mm/day）/
    monthly_precip_mm_units / source / license / accessed_at 等，
    或 None（分区不存在 / 尚未固化）。纯离线，不触发网络。
    """
    try:
        with open(zone_meta_path, encoding="utf-8") as f:
            data = json.load(f)
        for z in data.get("zones", []):
            if z.get("zone_id") == zone_id:
                base = z.get("climate_baseline")
                if base:
                    base = dict(base)
                    # 固化文件写于单位标注之前，补齐口径字段保证与实时数据同构。
                    base.setdefault("monthly_precip_mm_units", PRECIP_UNITS)
                return base
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# 自测（零依赖；python agent/climate_data.py）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 1) 离线 cache 命中（不联网）
    r0 = fetch_monthly_climate(30.2741, 120.1551, force_refresh=False)
    print("cached hit:", r0.get("cached"), "temp12:", len(r0.get("monthly_mean_c") or []))

    # 2) 强制联网刷新
    r1 = fetch_monthly_climate(30.2741, 120.1551, force_refresh=True)
    assert r1.get("monthly_mean_c") and len(r1["monthly_mean_c"]) == 12, r1
    print("live source:", r1["source"], "license:", r1["license"])
    print("monthly_mean_c:", r1["monthly_mean_c"])
    print("provenance:", json.dumps(r1["provenance"], ensure_ascii=False))
