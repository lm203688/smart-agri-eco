"""
EcoAgent - 多层级生态撮合

职责：
  1. 设备/工具推荐（基于 data/device_catalog.json，按场景×品类×预算）
  2. 供需撮合（采摘即食 / 社区交换 / 本地交易，结构化模板）
  3. 社区内容推荐（相似环境用户的经验匹配）
  4. 数据贡献激励（脱敏数据回报）

对标 SwarmLabs：无直接对应物，是农业生态项目的特有层（"生态卡位"核心）
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEVICE_DB = os.path.join(ROOT, "data", "device_catalog.json")

# 采摘即食场景：车载/阳台/办公室可直接消费，匹配"即时性"优先级
PICK_AND_EAT_SCENES = {"car_herbs", "car_greens", "balcony", "office", "roof"}


def _load_device_db(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"meta": {}, "categories": {}, "devices": []}


class EcoAgent:
    """多层级生态撮合 Agent"""

    NAME = "EcoAgent"
    VERSION = "1.1"

    def __init__(self, device_db_path: str = DEFAULT_DEVICE_DB):
        self.device_db_path = device_db_path
        self._db = _load_device_db(self.device_db_path)
        self._categories = self._db.get("categories", {})
        self._devices = self._db.get("devices", [])
        self._db_version = self._db.get("meta", {}).get("version", "1.0")
        self._db_sources = self._db.get("meta", {}).get("data_sources", [])

    def recommend_device(
        self,
        scene: str,
        crop: str = "",
        zone_data: Dict[str, Any] = {},
        budget: float = 0.0,
    ) -> Dict[str, Any]:
        """基于场景 + 作物 + 预算推荐设备。"""
        if not self._devices:
            return {
                "evidence": {"scene": scene, "crop": crop},
                "confidence": {"match_quality": 0.0},
                "constraints": {"budget": budget},
                "recommendation": [],
            }

        # 场景归一化：car_herbs/car_greens 归到车载类
        scene_keys = {scene}
        if scene in ("car_herbs", "car_greens"):
            scene_keys.add("car_herbs")
        if scene == "balcony_rail":
            scene_keys.add("balcony")

        candidate = []
        for d in self._devices:
            scenes = set(d.get("scenes", []))
            if not (scene_keys & scenes):
                continue
            # 品类匹配加分
            good = d.get("good_for", ["通用"])
            crop_match = ("通用" in good) or (crop and any(
                g in crop or crop in g for g in good))
            candidate.append((d.get("priority", 9), 0 if crop_match else 1, d))

        # 按优先级 + 品类匹配排序
        candidate.sort(key=lambda x: (x[0], x[1]))

        # 累计预算贪心：budget>0 时按优先级累加，超预算即停
        picked = []
        running = 0.0
        for _, _, d in candidate:
            price = d.get("price_cny", 0)
            if budget and budget > 0 and running + price > budget:
                continue
            picked.append(d)
            running += price

        recs = []
        for d in picked:
            recs.append({
                "device": d.get("name"),
                "device_id": d.get("id"),
                "category": self._categories.get(d.get("category"), d.get("category")),
                "price_cny": d.get("price_cny"),
                "reason": d.get("reason"),
                "good_for": d.get("good_for", ["通用"]),
            })

        total_price = sum(d.get("price_cny", 0) for d in picked)
        rubric = 0.7 + min(0.25, len(recs) * 0.03)

        return {
            "evidence": {
                "scene": scene,
                "crop": crop,
                "device_db_version": self._db_version,
                "data_sources": self._db_sources,
                "matched_count": len(recs),
            },
            "confidence": {
                "match_quality": round(min(rubric, 0.95), 2),
                "coverage_pct": round(len(recs) / max(len(self._devices), 1), 2),
            },
            "constraints": {"budget": budget, "total_estimated_price_cny": total_price},
            "recommendation": recs,
        }

    def match_supply_demand(
        self,
        user_location: Dict[str, Any],
        produce_type: str,
        quantity_kg: float,
        freshness_requirement: str = "当日",
    ) -> Dict[str, Any]:
        """供需撮合结构化模板（采摘即食 / 社区交换 / 本地交易）。"""
        is_pick_eat = user_location.get("scene") in PICK_AND_EAT_SCENES
        radius = 1.0 if is_pick_eat else 3.0
        return {
            "evidence": {
                "scene": user_location.get("scene"),
                "produce_type": produce_type,
                "freshness_requirement": freshness_requirement,
            },
            "confidence": {
                "match_quality": 0.75 if is_pick_eat else 0.6,
                "coverage_pct": 0.4,
                "confidence_note": "撮合网络为结构化模板，需接入真实供给方数据后生效",
            },
            "constraints": {
                "search_radius_km": radius,
                "min_quantity_kg": 0.5,
                "delivery_window": freshness_requirement,
            },
            "recommendation": [
                {
                    "channel": "社区种植者直供",
                    "distance_km": round(radius * 0.4, 1),
                    "freshness_score": 0.95,
                    "note": "同小区/同楼宇阳台种植者，采摘即食最短链路",
                },
                {
                    "channel": "本地社区团购/市集",
                    "distance_km": radius,
                    "freshness_score": 0.85,
                    "note": "社区团购团长聚合周边供给", },
                {
                    "channel": "城市农场/屋顶菜园", "distance_km": round(radius * 1.5, 1),
                    "freshness_score": 0.8,
                    "note": "城市农业产能入口，适合稳定复购",
                },
            ],
        }

    def suggest_community_content(
        self,
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """社区内容推荐（相似环境用户经验匹配）。"""
        zone = user_profile.get("zone_id", "")
        scene = user_profile.get("scene", "")
        return {
            "evidence": {"zone_id": zone, "scene": scene},
            "confidence": {"match_quality": 0.5, "coverage_pct": 0.3},
            "constraints": {},
            "recommendation": [
                f"关注同属「{zone}」气候带的阳台种植者经验帖",
                f"订阅「{scene}」场景的种植日历与病虫害预警",
                "参与数据贡献计划：上传生长记录换取 Premium 诊断额度",
            ],
        }
