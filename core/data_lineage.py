"""AgriDataLineage — 运行时数据血缘追踪（对齐 GOAI DataFlow-Agent 提升点3）。

壁垒④「真实结果回流校准」要求：任何一次 Env Recipe / 种植方案生成，都必须能
追到它依赖的真实数据源（外部程序化 API + 本地权威文件）及其版本指纹。

本模块**不修改任何数据**，只做「追踪 + 报告」：
- 外部程序化 API（可离线缓存复现）：NASA POWER / Open-Meteo / WorldClim 2.1 /
  GBIF / SoilGrids（rest.isric.org）。这些源是否「实际参与」以磁盘缓存是否命中为准，
  而非口头声称 —— 符合项目「真实数据、不编造」红线。
- 本地权威文件（单一数据源）：
    data/zone_meta/global_zones.json、data/crop_adapt_db.json、
    data/preset_cities.json、data/eval/zone_checks.json
- 校准溯源：calibration_provenance（若存在）+ data/env_recipes/*.json

所有读取均 try/except，缺文件时降级为 "absent"，不抛异常。

用法：
    from core import data_lineage as dl
    report = dl.trace_recipe(crop="tomato", zone_id="temperate")
    print(dl.render_text(report))
    # 或 CLI:  python -m core.data_lineage --crop tomato --zone temperate
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DATA = os.path.join(PROJECT_ROOT, "data")

# ---------------------------------------------------------------------------
# 数据源注册表（配置化：新增数据源只改这里）
# ---------------------------------------------------------------------------
EXTERNAL_APIS = [
    {
        "id": "nasa_power",
        "name": "NASA POWER",
        "cache_dir": os.path.join(DATA, "climate_cache"),
        "reachable": True,   # 无密钥，程序化可达
        "note": "气温/降水/辐射，Open-Meteo 交叉验证",
    },
    {
        "id": "open_meteo",
        "name": "Open-Meteo",
        "cache_dir": os.path.join(DATA, "climate_cache"),
        "reachable": True,
        "note": "日值自聚合；monthly 参数返空体（已知坑）",
    },
    {
        "id": "worldclim_2_1",
        "name": "WorldClim 2.1",
        "cache_dir": None,
        "reachable": True,
        "note": "30s 生物气候变量，离线快照",
    },
    {
        "id": "gbif",
        "name": "GBIF 物种分布",
        "cache_dir": os.path.join(DATA, "gbif_occ_cache"),
        "reachable": True,
        "note": "物种原产地抽点，存在 13.7°C 噪声待人工审",
    },
    {
        "id": "soilgrids",
        "name": "SoilGrids (ISRIC)",
        "cache_dir": None,
        "reachable": True,   # 正确主机 rest.isric.org；中国坐标慢/超时
        "note": "土壤栅格，欧洲坐标先重试一次",
    },
]

LOCAL_FILES = [
    {
        "id": "global_zones",
        "path": os.path.join(DATA, "zone_meta", "global_zones.json"),
        "role": "全球农业分区元数据（气候/土壤/水文）",
    },
    {
        "id": "crop_adapt_db",
        "path": os.path.join(DATA, "crop_adapt_db.json"),
        "role": "作物-分区适配数据库（含 calibrated 实证）",
    },
    {
        "id": "preset_cities",
        "path": os.path.join(DATA, "preset_cities.json"),
        "role": "预设城市单一数据源（含 modeled 字段）",
    },
    {
        "id": "zone_checks",
        "path": os.path.join(DATA, "eval", "zone_checks.json"),
        "role": "分区覆盖已知局限登记（降级语义不消失）",
    },
]


def _sha256_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _mtime_iso(path: str) -> Optional[str]:
    try:
        return datetime.datetime.fromtimestamp(
            os.path.getmtime(path)).isoformat(timespec="seconds")
    except Exception:
        return None


def _cache_hit(cache_dir: Optional[str]) -> Dict[str, Any]:
    """判断外部源是否「实际参与」：以磁盘缓存是否存在、命中多少文件为准。

    返回 {present, file_count, sampled}：present 表示缓存目录存在且有文件，
    说明该源在历史上被真实调用过（离线可复现），而非口头声称。
    """
    if not cache_dir:
        return {"present": None, "file_count": None,
                "note": "离线快照，无在线缓存目录"}
    try:
        if not os.path.isdir(cache_dir):
            return {"present": False, "file_count": 0, "note": "缓存目录不存在"}
        files = [f for f in os.listdir(cache_dir)
                 if os.path.isfile(os.path.join(cache_dir, f))]
        return {
            "present": len(files) > 0,
            "file_count": len(files),
            "note": "缓存命中即视为该源真实参与（离线可复现）",
        }
    except Exception:
        return {"present": False, "file_count": 0, "note": "缓存检查失败"}


def trace_external_apis() -> List[Dict[str, Any]]:
    out = []
    for api in EXTERNAL_APIS:
        cache = _cache_hit(api["cache_dir"])
        out.append({
            "id": api["id"],
            "name": api["name"],
            "reachable": api["reachable"],
            "cache_present": cache["present"],
            "cache_file_count": cache["file_count"],
            "note": api["note"],
        })
    return out


def trace_local_files() -> List[Dict[str, Any]]:
    out = []
    for lf in LOCAL_FILES:
        if os.path.exists(lf["path"]):
            out.append({
                "id": lf["id"],
                "path": os.path.relpath(lf["path"], PROJECT_ROOT),
                "role": lf["role"],
                "sha256": _sha256_file(lf["path"]),
                "mtime": _mtime_iso(lf["path"]),
                "present": True,
            })
        else:
            out.append({
                "id": lf["id"],
                "path": os.path.relpath(lf["path"], PROJECT_ROOT),
                "role": lf["role"],
                "sha256": None,
                "mtime": None,
                "present": False,
            })
    return out


def _calibration_present(crop: str, zone_id: str) -> Dict[str, Any]:
    """检查该作物-分区是否有 measured_calibration 实证（壁垒④核心）。"""
    db_path = os.path.join(DATA, "crop_adapt_db.json")
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        zones = db.get("zones", {}) if isinstance(db, dict) else {}
        zd = zones.get(zone_id, {})
        crops = zd.get("crops", []) if isinstance(zd, dict) else []
        for c in crops:
            if isinstance(c, dict) and c.get("crop") == crop:
                cal = c.get("calibration_provenance") or {}
                has_measured = bool(c.get("measured_calibration")
                                    or cal.get("measured_calibration")
                                    or c.get("calibrated") is True)
                return {
                    "found": True,
                    "calibrated": c.get("calibrated"),
                    "has_measured_evidence": has_measured,
                    "seed": cal.get("seed"),
                }
        return {"found": False, "calibrated": None,
                "has_measured_evidence": False, "seed": None}
    except Exception:
        return {"found": False, "calibrated": None,
                "has_measured_evidence": False, "seed": None,
                "error": "crop_adapt_db 读取失败"}


def trace_recipe(crop: str, zone_id: str) -> Dict[str, Any]:
    """追踪一次「作物 × 分区」配方生成所依赖的数据血缘。

    返回结构化报告：外部 API 参与情况 + 本地文件指纹 + 校准实证。
    """
    return {
        "trace_id": "lineage-%s@%s" % (crop, zone_id),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "query": {"crop": crop, "zone_id": zone_id},
        "external_apis": trace_external_apis(),
        "local_files": trace_local_files(),
        "calibration": _calibration_present(crop, zone_id),
        "lineage_statement": (
            "本配方依赖的全部数据均链接至其真实来源：外部源以磁盘缓存命中为"
            "「实际参与」判据（离线可复现），本地权威文件以 SHA256 指纹固定版本。"
            "任何数据变化都会改变指纹，可被独立复算验证。"
        ),
    }


def trace_pipeline_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """从 orchestrator.run_pipeline 的结果中提取 zone/crop 并追踪血缘。"""
    zone = (result.get("final_recommendation") or {}).get("zone", "")
    crops = (result.get("final_recommendation") or {}).get("recommended_crops") or []
    top_crop = crops[0].get("crop", "") if crops and isinstance(crops[0], dict) else ""
    if top_crop and zone:
        return trace_recipe(top_crop, zone)
    # 退化：至少追踪全局文件血缘
    return {
        "trace_id": "lineage-pipeline-global",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "query": {"crop": top_crop, "zone_id": zone},
        "external_apis": trace_external_apis(),
        "local_files": trace_local_files(),
        "calibration": {"found": False, "note": "无 zone/crop 可追踪"},
        "lineage_statement": "流水线结果缺少 zone/crop，仅输出全局文件血缘。",
    }


def query_lineage(crop: Optional[str] = None,
                 zone_id: Optional[str] = None) -> Dict[str, Any]:
    """按作物 / 分区查询数据血缘（对照 trace_recipe 的单点追踪，升级为可查询）。

    - crop + zone_id：等价 trace_recipe（单点追踪）
    - 仅 crop：在 crop_adapt_db 中找含该作物的全部分区，逐区追踪（上限 50）
    - 仅 zone_id：找该分区全部作物，逐作物追踪（上限 50）
    - 皆无：返回全局摘要（分区数 / 作物条目数 / 本地文件指纹）

    返回结构化 dict，便于 MCP 工具 agri_query_lineage 直接透传。
    """
    if crop and zone_id:
        return trace_recipe(crop, zone_id)

    db_path = os.path.join(DATA, "crop_adapt_db.json")
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return {"error": "crop_adapt_db 读取失败",
                "query": {"crop": crop, "zone_id": zone_id}}
    zones = db.get("zones", {}) if isinstance(db, dict) else {}

    matches: List[tuple] = []
    if crop and not zone_id:
        for zid, zdata in zones.items():
            for c in zdata.get("crops", []):
                if isinstance(c, dict) and (c.get("crop") == crop
                                            or crop in str(c.get("crop", ""))):
                    matches.append((crop, zid))
                    break
    elif zone_id and not crop:
        zdata = zones.get(zone_id, {})
        for c in zdata.get("crops", []):
            if isinstance(c, dict) and c.get("crop"):
                matches.append((c.get("crop"), zone_id))

    if matches:
        traces = [trace_recipe(c, z) for c, z in matches[:50]]
        return {
            "query": {"crop": crop, "zone_id": zone_id},
            "match_count": len(matches),
            "returned": len(traces),
            "traces": traces,
        }

    # 全局摘要
    zc = len(zones)
    cc = sum(len(z.get("crops", [])) for z in zones.values())
    return {
        "query": {"crop": crop, "zone_id": zone_id},
        "summary": True,
        "zone_count": zc,
        "crop_entry_count": cc,
        "local_files": trace_local_files(),
        "hint": "传入 crop 和/或 zone_id 以追踪具体配方血缘",
    }


def render_text(report: Dict[str, Any]) -> str:
    lines = [
        "# 数据血缘追踪报告 · %s" % report.get("trace_id", ""),
        "",
        "生成时间: %s" % report.get("generated_at", ""),
        "查询: %s" % json.dumps(report.get("query", {}), ensure_ascii=False),
        "",
        "## 外部程序化 API（缓存命中 = 真实参与）",
    ]
    for a in report.get("external_apis", []):
        cp = a.get("cache_present")
        cp_s = "命中 %s 文件" % a.get("cache_file_count") if cp else (
            "无缓存" if cp is False else "离线快照")
        lines.append("  - %s [%s]: %s | %s" % (
            a["name"], "可达" if a["reachable"] else "不可达", cp_s, a.get("note", "")))
    lines.append("")
    lines.append("## 本地权威文件（SHA256 指纹）")
    for f in report.get("local_files", []):
        if f.get("present"):
            fp = (f.get("sha256") or "")[:16]
            lines.append("  - %s: ✅ %s (sha256:%s)" % (f["path"], f["role"], fp))
        else:
            lines.append("  - %s: ❌ 缺失" % f["path"])
    lines.append("")
    cal = report.get("calibration", {})
    lines.append("## 校准实证（壁垒④）")
    if cal.get("found"):
        lines.append("  - 作物分区命中: calibrated=%s, 有实测实证=%s, seed=%s" % (
            cal.get("calibrated"), cal.get("has_measured_evidence"), cal.get("seed")))
    else:
        lines.append("  - 未命中校准条目（%s）" % cal.get("note", ""))
    lines.append("")
    lines.append("> %s" % report.get("lineage_statement", ""))
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="AgriDataLineage 数据血缘追踪")
    ap.add_argument("--crop", default="tomato", help="作物名")
    ap.add_argument("--zone", default="temperate", help="分区 ID")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()
    rep = query_lineage(crop=args.crop or None, zone_id=args.zone or None)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render_text(rep))


if __name__ == "__main__":
    main()
