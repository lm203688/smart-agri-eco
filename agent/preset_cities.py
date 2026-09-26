"""预设城市清单 · 单一数据源访问器。

背景（2026-09-23）
------------------
城市清单曾在 `app/demo_server.py`（PRESET_CITIES）与 `mcp/server.py`
（_PRESET_CITIES）各硬编码一份完全相同的副本。两份副本 = 必然漂移：改一处
忘另一处，前端与 MCP 工具就会给出不同的城市集，而两侧都不报错。

现在唯一数据源是 `data/preset_cities.json`，本模块是唯一读取入口。

失败语义：数据文件缺失/损坏时回退到内置最小副本（保证 demo 与 MCP 不因此
起不来），但回退副本与主文件保持一致的字段结构（含 `modeled`），使
`coverage_gap` 语义不随降级消失。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITIES_PATH = os.path.join(_PROJECT_ROOT, "data", "preset_cities.json")

# Fallback: identical values to data/preset_cities.json. Deliberately kept in
# sync manually — it only exists so the server can boot when the data file is
# missing (e.g. a stripped deploy bundle). Tests assert the two agree.
_FALLBACK_CITIES: List[Dict[str, Any]] = [
    {"name": "杭州", "lat": 30.2741, "lon": 120.1551, "zone": "亚热带湿润带", "modeled": True},
    {"name": "北京", "lat": 39.9042, "lon": 116.4074, "zone": "温带大陆性", "modeled": True},
    {"name": "深圳", "lat": 22.5431, "lon": 114.0579, "zone": "亚热带湿润带", "modeled": True},
    {"name": "广州", "lat": 23.1291, "lon": 113.2644, "zone": "亚热带湿润带", "modeled": True},
    {"name": "成都", "lat": 30.5728, "lon": 104.0668, "zone": "亚热带湿润带", "modeled": True},
    {"name": "武汉", "lat": 30.5928, "lon": 114.3055, "zone": "亚热带湿润带", "modeled": True},
    {"name": "乌鲁木齐", "lat": 43.8256, "lon": 87.6168, "zone": "干旱带", "modeled": True},
    {"name": "拉萨", "lat": 29.6520, "lon": 91.1721, "zone": "高原（未建模）", "modeled": False},
    {"name": "洛杉矶", "lat": 34.0522, "lon": -118.2437, "zone": "地中海带", "modeled": True},
    {"name": "新加坡", "lat": 1.3521, "lon": 103.8198, "zone": "热带雨林", "modeled": True},
    {"name": "迪拜", "lat": 25.2048, "lon": 55.2708, "zone": "热漠（未建模）", "modeled": False},
    {"name": "莫斯科", "lat": 55.7558, "lon": 37.6173, "zone": "亚寒带", "modeled": True},
]


def load_preset_cities(path: str = CITIES_PATH) -> List[Dict[str, Any]]:
    """Return the preset city list from the single data source.

    Fail-soft: a missing or malformed file falls back to `_FALLBACK_CITIES`
    instead of raising, so the demo/MCP server never fails to boot because of
    a data-file problem.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return list(_FALLBACK_CITIES)
    cities = data.get("cities")
    if isinstance(cities, list) and cities:
        return cities
    return list(_FALLBACK_CITIES)


def cities_from_file_only(path: str = CITIES_PATH) -> List[Dict[str, Any]]:
    """Strict variant: returns [] on any problem (used by tests / tooling that
    must detect a broken data file rather than silently fall back)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []
    cities = data.get("cities")
    return cities if isinstance(cities, list) else []
