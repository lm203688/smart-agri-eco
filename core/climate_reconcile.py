"""Climate source reconciliation — 多源气候数据调和（壁垒④ 真实结果回流校准）。

给定 (lat, lon)，并行拉取多个程序化气候源，逐月比对，产出：
  - reconciled          逐月调和值（多源算术平均，含可用源数）
  - agreement           逐月一致度（多源总体标准差，越小越一致）
  - disagreement_months  任一月两源标准差超阈值的月份（供下游/人工告警）
  - sources             各源原始值 + provenance（source/url/license）
  - provenance_complete  至少 2 源可用才算"可交叉验证"

当前接入：**NASA POWER** + **Open-Meteo**（两源均已程序化、可离线缓存复现）。
**WorldClim 2.1** 列为扩展点——它需要栅格瓦片下载做逐点取数，本项目尚未接入；
明确标注为扩展点，绝不编造其值。

零依赖（stdlib only）。网络调用委托 ``agent.climate_data`` 的
``_fetch_power`` / ``_fetch_open_meteo``，与项目"真实数据、不编造"红线一致。

失败语义：任一源不可用 → ``available:false`` + 原因；全部不可用 → ``reconciled:null``
+ ``error``。**绝不返回"看似合理但实为编造"的调和值。**

用法：
    from core import climate_reconcile as cr
    rep = cr.reconcile_climate(30.27, 120.15)
    print(cr.render_text(rep))
"""
from __future__ import annotations

import statistics
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

DEFAULT_SOURCES = ("power", "open_meteo")
# 逐月两源标准差超过此值（℃）即标记分歧，提示下游/人工复核
_DISAGREEMENT_THRESHOLD_C = 3.0


def _fetch_one(source_id: str, lat: float, lon: float, years: int) -> Dict[str, Any]:
    """调用单个源的取数函数，统一返回 {available, monthly_mean_c, error, provenance}。"""
    try:
        from agent import climate_data as cd
    except Exception as e:  # 模块级故障（极少见）
        return {"available": False, "monthly_mean_c": None,
                "error": "climate_data 模块不可用: %s" % e, "provenance": None}
    try:
        end_year = 2024
        start_year = max(2000, end_year - max(1, int(years)) + 1)
        if source_id == "power":
            raw = cd._fetch_power(lat, lon, start_year, end_year)
        elif source_id == "open_meteo":
            raw = cd._fetch_open_meteo(lat, lon, start_year, end_year)
        elif source_id == "worldclim":
            # 扩展点：明确标注未接入，不编造
            return {
                "available": False, "monthly_mean_c": None,
                "error": "WorldClim 2.1 暂未接入逐点取数（需栅格瓦片下载），列为扩展点",
                "provenance": {"source": "WorldClim 2.1",
                               "note": "扩展点：30s 生物气候变量，离线快照"},
            }
        else:
            return {"available": False, "monthly_mean_c": None,
                    "error": "未知源: %s" % source_id, "provenance": None}
    except Exception as e:
        return {"available": False, "monthly_mean_c": None,
                "error": "取数异常: %s" % e, "provenance": None}

    if not raw:
        return {"available": False, "monthly_mean_c": None,
                "error": "源返回空", "provenance": None}
    series = raw.get("monthly_mean_c")
    if not series or len(series) != 12 or any(m is None for m in series):
        return {"available": False, "monthly_mean_c": None,
                "error": "返回序列无效（非 12 月或含 None）",
                "provenance": raw.get("provenance")}
    return {
        "available": True,
        "monthly_mean_c": [float(x) for x in series],
        "error": None,
        "provenance": raw.get("provenance") or {
            "source": raw.get("source"),
            "url": raw.get("url"),
            "license": raw.get("license"),
            "accessed_at": raw.get("accessed_at"),
        },
    }


def reconcile_climate(lat: float, lon: float, years: int = 5,
                      sources: Optional[tuple] = None,
                      cache_dir: Optional[str] = None,
                      force_refresh: bool = False) -> Dict[str, Any]:
    """多源气候调和。

    参数:
        lat, lon     坐标
        years        取数年数（默认 5，仅影响活取；缓存命中时由缓存决定）
        sources      源 id 元组，默认 ("power", "open_meteo")
        cache_dir    预留（当前取数函数自带缓存；保留以对齐后续可配置缓存目录）
        force_refresh 预留（透传给取数层；当前取数函数忽略，保留接口稳定性）

    返回结构:
        lat/lon, sources([{id,available,monthly_mean_c,error,provenance}]),
        n_sources, reconciled(12|null), agreement(12|null),
        disagreement_months([{month,std_c,values}]),
        provenance_complete(bool), method, error(可选)
    """
    srcs = list(sources) if sources else list(DEFAULT_SOURCES)
    fetched = []
    for s in srcs:
        f = _fetch_one(s, lat, lon, years)
        f["id"] = s
        fetched.append(f)

    valid = [f["monthly_mean_c"] for f in fetched if f.get("available")]
    n = len(valid)

    reconciled = None
    agreement = None
    disagreement_months: List[Dict[str, Any]] = []
    if n >= 1:
        reconciled = [sum(col) / n for col in zip(*valid)]
    if n >= 2:
        agreement = []
        for i in range(12):
            col = [v[i] for v in valid]
            sd = statistics.pstdev(col) if len(col) >= 2 else 0.0
            agreement.append(round(sd, 3))
            if sd > _DISAGREEMENT_THRESHOLD_C:
                disagreement_months.append({
                    "month": i + 1,
                    "std_c": round(sd, 3),
                    "values": {srcs[k]: round(valid[k][i], 2) for k in range(n)},
                })

    result: Dict[str, Any] = {
        "lat": lat, "lon": lon,
        "sources": fetched,
        "n_sources": n,
        "reconciled": [round(x, 2) for x in reconciled] if reconciled else None,
        "agreement": agreement,
        "disagreement_months": disagreement_months,
        "disagreement_threshold_c": _DISAGREEMENT_THRESHOLD_C,
        "provenance_complete": n >= 2,
        "method": "逐月算术平均；一致度=多源总体标准差；分歧=标准差>阈值",
    }
    if n == 0:
        result["error"] = ("所有气候源均不可达（网络不可达或坐标无效）；"
                           "未产生调和基线")
    elif n == 1:
        result["note"] = ("仅 1 源可用，无法做交叉验证；reconciled 为该源原值，"
                          "provenance_complete=false")
    return result


def render_text(rep: Dict[str, Any]) -> str:
    lines = ["# 气候多源调和报告", "",
             "坐标: (%.4f, %.4f)" % (rep.get("lat", 0), rep.get("lon", 0)),
             "可用源数: %s" % rep.get("n_sources"),
             "可交叉验证(≥2源): %s" % rep.get("provenance_complete"), ""]
    for s in rep.get("sources", []):
        st = "✅" if s.get("available") else "❌ %s" % (s.get("error") or "")
        lines.append("  - %s: %s" % (s.get("id"), st))
    rec = rep.get("reconciled")
    if rec:
        lines.append("")
        lines.append("调和月均温(℃): " + ", ".join("%.1f" % x for x in rec))
    dm = rep.get("disagreement_months") or []
    if dm:
        lines.append("")
        lines.append("⚠️ 分歧月份(标准差>阈值): " + ", ".join(
            "M%s(σ=%.2f)" % (d["month"], d["std_c"]) for d in dm))
    else:
        lines.append("逐月两源一致度良好（无超阈分歧）")
    if rep.get("error"):
        lines.append("")
        lines.append("❌ %s" % rep["error"])
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        la, lo = float(sys.argv[1]), float(sys.argv[2])
        print(render_text(reconcile_climate(la, lo)))
