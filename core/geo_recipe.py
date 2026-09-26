"""Geo → Zone → Recipe resolver — 地理编码到配方（核心分发价值）。

输入：城市名（中文/英文）或经纬度。
流程：
  1. 解析坐标：city 名 → preset_cities 查表 / 直接 lat+lon / "lat,lon" 字符串
  2. 分区匹配：agent.climate_agent._match_zone_by_coords（纯函数，无文件依赖）
  3. 配方检索：glob data/env_recipes/<zone>__*.json（命名与 mcp/server.py 一致）

返回：zone_id / zone_name / 坐标 / 匹配配方清单（作物名 + 路径 + 摘要）。

零依赖（stdlib only）。完全离线可测——不触发任何网络。
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RECIPE_DIR = os.path.join(DATA, "env_recipes")
ZONE_META = os.path.join(DATA, "zone_meta", "global_zones.json")

# 当前分区库未建模的气候类（与 climate_agent.UNMODELED_ZONE_CLASSES 对齐）
_UNMODELED = ("hot_arid", "highland")


def _resolve_coords(query: Optional[str], lat: Any, lon: Any) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """返回 (lat, lon, error_or_None)。"""
    # 1) 显式经纬度
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), None
        except (TypeError, ValueError):
            return None, None, "lat/lon 非数值"
    # 2) "lat,lon" 字符串
    if query and "," in query:
        parts = query.split(",")
        if len(parts) == 2:
            try:
                return float(parts[0].strip()), float(parts[1].strip()), None
            except ValueError:
                pass
    # 3) 城市名查表
    if query:
        try:
            from agent.preset_cities import load_preset_cities
            for c in load_preset_cities():
                if c.get("name") == query or c.get("name_en") == query:
                    return float(c["lat"]), float(c["lon"]), None
        except Exception:
            pass
        return None, None, "无法将「%s」解析为已知城市或坐标" % query
    return None, None, "缺少 query(城市名/坐标) 或 lat/lon"


def _zone_name(zone_id: str) -> Optional[str]:
    try:
        with open(ZONE_META, encoding="utf-8") as f:
            data = json.load(f)
        for z in data.get("zones", []):
            if z.get("zone_id") == zone_id:
                return z.get("zone_name")
    except Exception:
        pass
    return None


def _lookup_recipes(zone_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(RECIPE_DIR):
        return out
    pat = os.path.join(RECIPE_DIR, "%s__*.json" % zone_id)
    for path in sorted(glob.glob(pat)):
        name = os.path.basename(path)
        crop = name[len(zone_id) + 2:-5]  # 去掉 "<zone>__" 前缀与 ".json" 后缀
        summary = {
            "zone_id": zone_id,
            "crop": crop,
            "path": os.path.relpath(path, ROOT),
        }
        try:
            with open(path, encoding="utf-8") as f:
                r = json.load(f)
            summary["stage"] = r.get("stage")
            summary["device_class"] = (r.get("device_profile") or {}).get("device_class")
            summary["species"] = (r.get("crop") or {}).get("species", crop)
        except Exception:
            pass
        out.append(summary)
    return out


def resolve(query: Optional[str] = None, lat: Optional[float] = None,
            lon: Optional[float] = None) -> Dict[str, Any]:
    """地理编码 → 分区 → 配方。"""
    la, lo, err = _resolve_coords(query, lat, lon)
    if la is None:
        return {"resolved": False, "error": err, "query": query}

    try:
        from agent.climate_agent import _match_zone_by_coords
        zone_id = _match_zone_by_coords(la, lo)
    except Exception as e:
        return {"resolved": False, "error": "分区匹配失败: %s" % e,
                "lat": la, "lon": lo}

    zname = _zone_name(zone_id)
    recipes = _lookup_recipes(zone_id)
    unmodeled = zone_id in _UNMODELED
    return {
        "resolved": True,
        "query": query,
        "lat": la, "lon": lo,
        "zone_id": zone_id,
        "zone_name": zname,
        "zone_modeled": not unmodeled,
        "recipe_count": len(recipes),
        "recipes": recipes,
        "note": ("该气候类（%s）当前分区库未建模，无现成配方；"
                 "可走箱体环境控制路线" % zone_id) if unmodeled else None,
    }


def render_text(rep: Dict[str, Any]) -> str:
    if not rep.get("resolved"):
        return "# 解析失败\n%s" % rep.get("error", "")
    lines = ["# 地理编码 → 配方", "",
             "查询: %s" % (rep.get("query") or "%s, %s" % (rep.get("lat"), rep.get("lon"))),
             "坐标: (%.4f, %.4f)" % (rep["lat"], rep["lon"]),
             "分区: %s (%s)" % (rep["zone_id"], rep.get("zone_name") or "未命名"),
             "分区已建模: %s" % rep.get("zone_modeled"),
             "匹配配方数: %s" % rep.get("recipe_count"), ""]
    for r in rep.get("recipes", []):
        lines.append("  - %s [%s/%s]: %s" % (
            r.get("crop"), r.get("stage"), r.get("device_class"), r.get("path")))
    if rep.get("note"):
        lines.append("")
        lines.append("⚠️ %s" % rep["note"])
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "杭州"
    lat = float(sys.argv[2]) if len(sys.argv) > 2 else None
    lon = float(sys.argv[3]) if len(sys.argv) > 3 else None
    print(render_text(resolve(q, lat, lon)))
