"""
core/climate_grid.py —— Köppen-Geiger 栅格气候分类抽象（A1/F5）

设计动机（承接 docs/framework_evolution_liftup_2026-10-13.md §6.1 F5）：
  气候分类是全链正确性的第一环（`climate_agent._match_zone_by_coords` 现在是
  盒式启发式，注释自承"精确匹配需栅格数据"）。未来接入 Beck et al. 2018/2023
  Köppen-Geiger 1km 栅格（CC BY 4.0）是必然动作，但栅格是数百 MB 二进制资产——
  本模块**先建抽象、再接数据**，避免第一环再次欠技术债。

接口设计原则：
  1. 零第三方依赖（stdlib only：json / struct / math / array）
  2. 点查询返回**分区概率分布**（不是单点分类）——这是 SNWM"高精度≠可决策"
     的直接落地：调用方能获得"这个坐标落在几个格点的边界上、每类占多少"
  3. 显式降级：无栅格数据时**不静默回退盒式启发式**——返回 status="no_grid"，
     调用方明确知道自己走的是哪个后端（与 trust_layer 的诚实降级一致）
  4. 数据格式中立：接口只认 (lat, lon, klass)，具体是 1km 栅格还是 10m × 10m
     抽样表，实现层决定

栅格数据格式（本模块约定）：
  {
    "schema": "agri-koppen-grid/v1",
    "resolution_deg": 0.25,          # 每格代表的经纬度
    "bbox": [lat_min, lat_max, lon_min, lon_max],
    "classes": ["Af", "Aw", "As", "BWh", ...],   # Köppen-Geiger 子分类列表
    "cells": [                         # 一行行展平，row-major
      {"lat": 10.0, "lon": 20.0, "class": "Aw"},
      {"lat": 10.0, "lon": 20.25, "class": "BWh"},
      ...
    ]
  }
  真实数据到位时替换 data/zone_meta/koppen_grid.json 即可。

用法：
    from core.climate_grid import KoppenGrid
    grid = KoppenGrid.load("data/zone_meta/koppen_grid.json")
    if grid.available:
        result = grid.query(30.0, 120.0)   # → {"Cfa": 0.7, "Cfa/2m": 0.3, ...}
    else:
        # 调用方应显式标注 status="no_grid" 并降级到盒式启发式
        ...
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GRID_PATH = os.path.join(ROOT, "data", "zone_meta", "koppen_grid.json")

SCHEMA = "agri-koppen-grid/v1"

# Köppen-Geiger 子分类 → 本项目 8 分区映射表。
# 依据：项目 data/zone_meta/global_zones.json 里每个分区已经声明了 koppen_class
# 字段（Af / Cfa·Cwa / Dfa·Dfb / Csa·Csb / BWh·BSh / Dfc·Dwc / BWh / H）。
# 这里做的是"Köppen 精确分类 → 项目粗分区"的下采样。
# 诚实边界：这是一次信息损失——同一细分类可能跨多项目分区（如 Cfa 覆盖温带
# 与亚热带湿润），映射时取"典型语义"，边界情况调用方看概率分布自行判断。
KOPPEN_TO_PROJECT_ZONE = {
    # 热带
    "Af": "tropical_rainforest",
    "Am": "tropical_rainforest",
    "Aw": "subtropical_wet",
    "As": "subtropical_wet",
    # 干旱
    "BWh": "hot_arid",
    "BWk": "arid",
    "BSh": "hot_arid",
    "BSk": "arid",
    # 地中海
    "Csa": "mediterranean",
    "Csb": "mediterranean",
    "Csc": "mediterranean",
    # 温带湿润
    "Cfa": "temperate_subhumid",
    "Cfb": "temperate_subhumid",
    "Cfc": "temperate_subhumid",
    "Cwa": "temperate_subhumid",
    "Cwb": "temperate_subhumid",
    # 温带大陆性（暖夏季）
    "Dfa": "temperate_continental",
    "Dfb": "temperate_continental",
    "Dsa": "temperate_continental",
    "Dsb": "temperate_continental",
    "Dsc": "temperate_continental",
    # 亚寒带（冷夏季）—— 对应 subarctic 分区声明的 Dfc/Dwc
    "Dfc": "subarctic",
    "Dfd": "subarctic",
    "Dwc": "subarctic",
    "Dwd": "subarctic",
    # 高纬
    "Efa": "subarctic",
    "Efb": "subarctic",
    "ET": "subarctic",
    "EF": "subarctic",
}

# 高海拔分区（Köppen 单独 H 类；本项目也有 highland 分区）
HIGH_ELEVATION_MARKER = "H"


class NoGridData(Exception):
    """栅格数据不可用（文件缺失或解析失败）。调用方应显式降级。"""


class KoppenGrid:
    """Köppen-Geiger 栅格点查询引擎。

    使用示例：
        grid = KoppenGrid.load(path)
        if not grid.available:
            return {"status": "no_grid", "degraded_reason": grid.status_reason}
        result = grid.query(lat, lon)
        # → {"top_klassen": [("Cfa", 0.6), ("Cfb", 0.4)],
        #    "project_zone": "temperate_subhumid",
        #    "distance_km": 32.1,
        #    "available": True}
    """

    def __init__(self, cells: List[Dict[str, Any]],
                 resolution_deg: float, bbox: List[float],
                 classes: List[str]) -> None:
        self.cells = cells
        self.resolution_deg = resolution_deg
        self.bbox = bbox  # [lat_min, lat_max, lon_min, lon_max]
        self.classes = classes
        # 从数据推导真实步长（真实栅格 lat_step == lon_step，但合成测试可能不同）
        self._derive_steps()
        self._build_spatial_index()

    def _derive_steps(self) -> None:
        """从 cells 里唯一 lat/lon 推导真实步长，避免合成栅格 lat_step != lon_step 时索引错乱。"""
        if not self.cells:
            self._lat_step = self.resolution_deg
            self._lon_step = self.resolution_deg
            return
        lats = sorted({round(float(c["lat"]), 6) for c in self.cells})
        lons = sorted({round(float(c["lon"]), 6) for c in self.cells})
        if len(lats) >= 2:
            self._lat_step = (lats[-1] - lats[0]) / (len(lats) - 1)
        else:
            self._lat_step = self.resolution_deg
        if len(lons) >= 2:
            self._lon_step = (lons[-1] - lons[0]) / (len(lons) - 1)
        else:
            self._lon_step = self.resolution_deg

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[str] = None) -> "KoppenGrid":
        """从 JSON 加载栅格数据；文件不存在或解析失败时抛 NoGridData。"""
        grid_path = path or DEFAULT_GRID_PATH
        if not os.path.exists(grid_path):
            raise NoGridData(f"栅格文件不存在: {grid_path}")
        try:
            with open(grid_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("schema") != SCHEMA:
                raise NoGridData(
                    f"schema 不匹配: 期望 {SCHEMA}，实际 {d.get('schema')}")
            return cls(
                cells=d["cells"],
                resolution_deg=float(d["resolution_deg"]),
                bbox=[float(x) for x in d["bbox"]],
                classes=d.get("classes", []),
            )
        except NoGridData:
            raise
        except Exception as e:  # noqa: BLE001
            raise NoGridData(f"栅格加载失败 {grid_path}: {e}") from e

    @classmethod
    def unavailable(cls, reason: str = "no_grid_data") -> "KoppenGrid":
        """构造一个显式降级实例（不建索引，不占内存）。"""
        obj = cls.__new__(cls)
        obj.cells = []
        obj.resolution_deg = 0.0
        obj.bbox = []
        obj.classes = []
        obj.status_reason = reason
        obj._lat_step = 0.0
        obj._lon_step = 0.0
        obj._index: Dict[Tuple[int, int], Dict[str, Any]] = {}
        return obj

    @property
    def available(self) -> bool:
        return bool(self.cells)

    def __repr__(self) -> str:
        return (f"<KoppenGrid available={self.available} "
                f"cells={len(self.cells)} lat_step={self._lat_step:.3f}° "
                f"lon_step={self._lon_step:.3f}° bbox={self.bbox}>")

    # ------------------------------------------------------------------
    # 空间索引
    # ------------------------------------------------------------------

    def _build_spatial_index(self) -> None:
        """按 (row, col) 网格化。行按纬度、列按经度；row 从北向南。"""
        if not self.cells or not self.bbox or self._lat_step <= 0 or self._lon_step <= 0:
            self._index = {}
            return
        lat_min, lat_max, lon_min, _ = self.bbox
        self._index = {}
        for c in self.cells:
            lat, lon = float(c["lat"]), float(c["lon"])
            row = int(round((lat_max - lat) / self._lat_step))
            col = int(round((lon - lon_min) / self._lon_step))
            self._index[(row, col)] = c

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def _cell_at(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """最近邻格点查询。超出 bbox 返回 None。"""
        if not self.available:
            return None
        lat_min, lat_max, lon_min, lon_max = self.bbox
        if not (lat_min - 1e-9 <= lat <= lat_max + 1e-9 and
                lon_min - 1e-9 <= lon <= lon_max + 1e-9):
            return None
        row = int(round((lat_max - lat) / self._lat_step))
        col = int(round((lon - lon_min) / self._lon_step))
        return self._index.get((row, col))

    def _distance_km(self, lat1: float, lon1: float,
                     lat2: float, lon2: float) -> float:
        """haversine 距离，标准库实现。"""
        r = 6371.0  # km
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))

    def query(self, lat: float, lon: float) -> Dict[str, Any]:
        """点查询：返回坐标所在区域的分类分布 + 项目分区映射。

        返回结构：
          {
            "available": bool,
            "status": "ok" | "no_grid" | "out_of_bounds",
            "nearest": {"klass": "Cfa", "lat": ..., "lon": ..., "distance_km": ...},
            "neighbors": [{"klass": ..., "distance_km": ..., "weight": ...}, ...],  # 最多 4 邻居
            "top_klassen": [("Cfa", 0.6), ("Cfb", 0.4)],   # 按权重降序
            "project_zone": "temperate_subhumid" | None,    # 主 class 映射
            "highland": bool                                # Köppen H 类
          }
        实现原理：最近邻 + 距离衰减权重（1/d²）。权重之和归一化。
        """
        if not self.available:
            return {"available": False, "status": "no_grid",
                    "nearest": None, "neighbors": [], "top_klassen": [],
                    "project_zone": None, "highland": False}

        nearest = self._cell_at(lat, lon)
        if nearest is None:
            return {"available": True, "status": "out_of_bounds",
                    "nearest": None, "neighbors": [], "top_klassen": [],
                    "project_zone": None, "highland": False}

        # 收集邻居（含自身）
        candidates = []
        seen = set()
        for cand in self._gather_neighbors(lat, lon, nearest):
            key = (round(cand["lat"], 6), round(cand["lon"], 6))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(cand)

        # 距离权重：1/(d+ε)²
        eps = 1e-3
        raw = []
        for c in candidates:
            d = self._distance_km(lat, lon, float(c["lat"]), float(c["lon"]))
            w = 1.0 / ((d + eps) ** 2)
            raw.append((c, d, w))

        # 归一化
        wsum = sum(r[2] for r in raw)
        if wsum <= 0:
            wsum = 1.0
        weighted = []
        klass_weight: Dict[str, float] = {}
        for c, d, w in raw:
            wn = w / wsum
            weighted.append({
                "klass": c.get("class"),
                "lat": c.get("lat"),
                "lon": c.get("lon"),
                "distance_km": round(d, 3),
                "weight": round(wn, 4),
            })
            k = c.get("class", "?")
            klass_weight[k] = klass_weight.get(k, 0.0) + wn

        top_klassen = sorted(klass_weight.items(), key=lambda x: -x[1])

        # 主分类 → 项目分区
        top_klass = top_klassen[0][0] if top_klassen else None
        project_zone = KOPPEN_TO_PROJECT_ZONE.get(top_klass) if top_klass else None
        highland = (top_klass == HIGH_ELEVATION_MARKER) or (
            isinstance(top_klass, str) and "H" in top_klass
        )

        # 最近邻
        nearest_cell = min(raw, key=lambda x: x[1])
        nearest_out = {
            "klass": nearest_cell[0].get("class"),
            "lat": nearest_cell[0].get("lat"),
            "lon": nearest_cell[0].get("lon"),
            "distance_km": round(nearest_cell[1], 3),
        }

        return {
            "available": True,
            "status": "ok",
            "nearest": nearest_out,
            "neighbors": weighted[:4],  # 最多 4 个邻居
            "top_klassen": [(k, round(w, 4)) for k, w in top_klassen],
            "project_zone": project_zone,
            "highland": highland,
        }

    def _gather_neighbors(self, lat: float, lon: float,
                          center: Dict[str, Any]) -> List[Dict[str, Any]]:
        """取 center 所在格点及 8 邻居（3×3 窗口）。"""
        _, lat_max, lon_min, _ = self.bbox
        row = int(round((lat_max - float(center["lat"])) / self._lat_step))
        col = int(round((float(center["lon"]) - lon_min) / self._lon_step))
        out = [center]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                c = self._index.get((row + dr, col + dc))
                if c is not None:
                    out.append(c)
        return out


# ----------------------------------------------------------------------
# 便捷 API：给调用方（climate_agent）用
# ----------------------------------------------------------------------

def query_with_fallback(lat: float, lon: float,
                        grid: Optional[KoppenGrid] = None) -> Dict[str, Any]:
    """栅格优先，无栅格时显式返回 no_grid（不静默回退）。

    调用方（如 climate_agent）拿到 status="no_grid" 后应显式调用
    盒式启发式 _match_zone_by_coords，并在输出里标注 backend="heuristic"。
    """
    if grid is None:
        try:
            grid = KoppenGrid.load()
        except NoGridData:
            grid = KoppenGrid.unavailable("grid_file_missing")
    return grid.query(lat, lon)


def make_synthetic_test_grid(resolution_deg: float = 0.25,
                             n_rows: int = 20,
                             n_cols: int = 40) -> List[Dict[str, Any]]:
    """生成一份小尺寸的合成栅格，用于测试与文档示例。

    合成规则（用于验证 point query 与概率分布算法，非真实数据）：
      - 5N 以下：Aw / Af（热带）
      - 15N-25N：Cwa / Cfa（亚热带）
      - 25N-35N：Csa / BWh（地中海/干旱过渡）
      - 35N-50N：Cfa / Dfb（温带）
      - 50N-60N：Dfc（寒温带）
      - 60N+：Efa（寒带）
    这是**教学合成**，不是 Köppen-Geiger 真实栅格；用于单元测试与集成测试。
    """
    cells = []
    lat_step = 140.0 / max(1, n_rows - 1)   # 从 70N 到 70S
    lon_step = 360.0 / max(1, n_cols)        # 从 -180 到 +180
    for r in range(n_rows):
        for c in range(n_cols):
            lat = 70.0 - r * lat_step
            lon = -180.0 + c * lon_step
            if lat >= 60:
                k = "Efa"
            elif lat >= 50:
                k = "Dfc"
            elif lat >= 35:
                k = "Cfa" if (c % 2 == 0) else "Dfb"
            elif lat >= 25:
                k = "Csa" if lon < 0 else "BWh"
            elif lat >= 15:
                k = "Cwa" if lon < 0 else "Cfa"
            else:
                k = "Aw" if lat >= 0 else "Af"
            cells.append({"lat": round(lat, 4), "lon": round(lon, 4), "class": k})
    return cells


def build_synthetic_grid_dict(resolution_deg: float = 0.25,
                              n_rows: int = 20, n_cols: int = 40) -> Dict[str, Any]:
    """合成栅格的完整 JSON 结构（含 schema / bbox / classes）。"""
    cells = make_synthetic_test_grid(resolution_deg, n_rows, n_cols)
    lats = [c["lat"] for c in cells]
    lons = [c["lon"] for c in cells]
    classes = sorted({c["class"] for c in cells})
    # bbox 用合成数据的真实范围（不是 resolution_deg 推导的）
    return {
        "schema": SCHEMA,
        "resolution_deg": round((max(lats) - min(lats)) / max(1, n_rows - 1), 4),
        "bbox": [min(lats), max(lats), min(lons), max(lons)],
        "classes": classes,
        "cells": cells,
        "generated_at": "synthetic_test",
        "provenance": {
            "note": ("合成栅格用于测试 point query 与概率分布算法；"
                     "不是 Köppen-Geiger 真实数据。真实数据请替换本文件为 "
                     "Beck et al. 2018/2023 版本（CC BY 4.0）。"),
            "reference": "https://climexp.knmi.nl/dataaccess/",
        },
    }
