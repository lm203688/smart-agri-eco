"""
CropAgent - 作物-分区适配推荐

职责：
  1. 接收 ClimateAgent 输出的分区元数据
  2. 根据环境约束 + 种植者偏好（食用/观赏/空间/难度）推荐作物
  3. 输出适配度评分 + 推荐排序 + 种植周期
  4. 标记"易失败风险"和"推荐兜底品种"

对标 SwarmLabs：相当于 physics_predict Skill 的作物子域

输出契约：
  {
    "evidence": {"crop_db_version": "1.0", "zone_id": "...", "recommendation_count": 3},
    "confidence": {"rubric_score": 0.8, "coverage_pct": 0.6},
    "constraints": {"min_area_sqm": 0.5, "max_area_sqm": 2.0},
    "recommendation": [{"crop": "生菜", "adapt_score": 0.92, "growth_days": 45, ...}, ...]
  }
"""

from __future__ import annotations

import json
import os
from typing import Dict, Any, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")

# 观赏类作物关键词（用于 purpose 过滤）
ORNAMENTAL_KEYWORDS = ["观", "花", "兰", "菊", "玫瑰", "月季", "杜鹃", "多肉", "仙人掌", "沙漠玫瑰"]
# 香料类作物关键词
HERB_KEYWORDS = ["香草", "薄荷", "罗勒", "迷迭香", "百里香", "香菜", "紫苏", "牛至", "鼠尾草",
                 "柠檬草", "莳萝", "花椒", "胡椒"]
# beginner 友好作物（生长周期短、适配度高）
BEGINNER_FRIENDLY = [
    "生菜", "小白菜", "萝卜", "樱桃萝卜", "菠菜", "韭菜", "葱", "薄荷",
    "空心菜", "红薯叶", "香菜", "豌豆苗", "豆芽", "微绿菜", "紫苏",
    "秋葵", "辣椒", "豆角", "黄瓜",
]


def _load_crop_db(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"meta": {}, "zones": {}}


def _is_ornamental(crop_name: str) -> bool:
    return any(k in crop_name for k in ORNAMENTAL_KEYWORDS)


def _is_herb(crop_name: str) -> bool:
    return any(k in crop_name for k in HERB_KEYWORDS)


def _is_container_suitable(crop: Dict[str, Any]) -> bool:
    scenes = crop.get("suitable_scenes", [])
    return any(s in scenes for s in ["balcony", "container", "office",
                                       "container_large", "container_deep",
                                       "tree_container", "water_container",
                                       "hanging_container", "water_grow"])


class CropAgent:
    """作物-分区适配推荐 Agent"""

    NAME = "CropAgent"
    VERSION = "1.1"

    def __init__(self, crop_db_path: str = DEFAULT_CROP_DB):
        self.crop_db_path = crop_db_path
        self._db = _load_crop_db(self.crop_db_path)
        self._db_version = self._db.get("meta", {}).get("version", "1.0")
        self._db_sources = self._db.get("meta", {}).get("data_sources", [])
        self._total_entries = self._db.get("meta", {}).get("total_entries", 0)

    def recommend(
        self,
        zone_data: Dict[str, Any],
        preferences: Dict[str, Any],
    ) -> Dict[str, Any]:
        """根据分区数据和用户偏好推荐作物。"""
        zone_id = zone_data.get("evidence", {}).get("zone_id", "")
        zone_meta = self._db.get("zones", {}).get(zone_id)

        if not zone_meta:
            # 数据缺失
            return {
                "evidence": {
                    "crop_db_version": self._db_version,
                    "data_sources": self._db_sources,
                    "zone_id": zone_id,
                    "recommendation_count": 0,
                    "total_crops_in_zone": 0,
                },
                "confidence": {"rubric_score": 0.0, "coverage_pct": 0.0,
                               "confidence_note": f"分区 {zone_id} 无作物数据"},
                "constraints": {},
                "recommendation": [],
            }

        all_crops = zone_meta.get("crops", [])
        total_in_zone = len(all_crops)

        # ---- 过滤 ----
        purpose = preferences.get("purpose", "食用")
        difficulty = preferences.get("difficulty", "beginner")
        space_sqm = preferences.get("space_sqm", 1.5)
        container = preferences.get("container", False)
        harvest_max = preferences.get("harvest_time_days", 9999)

        candidates = []
        for c in all_crops:
            name = c.get("crop", "")

            # purpose 过滤
            if purpose == "食用":
                if _is_ornamental(name) or _is_herb(name):
                    continue
            elif purpose == "香料":
                if not _is_herb(name) and not _is_ornamental(name):
                    continue
            elif purpose == "观赏":
                if not _is_ornamental(name) and not _is_herb(name):
                    continue

            # 采收周期过滤
            if c.get("growth_days", 9999) > harvest_max:
                continue

            # 容器适配
            if container and not _is_container_suitable(c):
                continue

            # 空间估算（简化的启发式：大型作物需更大空间）
            large_keywords = ["玉米", "芒果", "橄榄", "葡萄", "香蕉", "木瓜",
                              "百香果", "花生", "沙棘", "鹰嘴豆"]
            needs_large_space = any(k in name for k in large_keywords)
            if needs_large_space and space_sqm < 3.0:
                continue

            # 加分项
            score_boost = c.get("adapt_score", 0)
            if difficulty == "beginner" and name in BEGINNER_FRIENDLY:
                score_boost += 0.05
            if difficulty == "advanced":
                score_boost -= 0.02 if name in BEGINNER_FRIENDLY else 0

            candidates.append((score_boost, c))

        # ---- 排序取 Top N ----
        candidates.sort(key=lambda x: x[0], reverse=True)
        top_n = 5
        top = candidates[:top_n]

        recommendations = []
        for _, c in top:
            name = c.get("crop", "")
            # 生成推荐理由
            reason_parts = []
            if c.get("growth_days", 999) <= 30:
                reason_parts.append(f"速生（D{c['growth_days']}）")
            elif c.get("growth_days", 999) <= 60:
                reason_parts.append(f"周期短（D{c['growth_days']}）")
            if c.get("adapt_score", 0) >= 0.95:
                reason_parts.append("广适")
            if name in BEGINNER_FRIENDLY and difficulty == "beginner":
                reason_parts.append("新手友好")
            reason = "、".join(reason_parts) if reason_parts else "适配度较高"

            rec = {
                "crop": name,
                "latin": c.get("latin"),
                "family": c.get("family"),
                "adapt_score": c.get("adapt_score"),
                "growth_days": c.get("growth_days"),
                "temp_range_c": c.get("temp_range_c"),
                "ph_range": c.get("ph_range"),
                "water_ml_day": c.get("water_ml_day"),
                "suitable_scenes": c.get("suitable_scenes"),
                "reason": reason,
                "risk_flags": c.get("key_risks", []),
                "fallback_variety": c.get("fallback_variety"),
            }
            recommendations.append(rec)

        # 置信度：数据覆盖度 + 候选密度
        score_coverage = sum(1 for c in all_crops if c.get("adapt_score") is not None) / max(total_in_zone, 1)
        # 候选占该区所有作物的比例
        candidate_density = len(candidates) / max(total_in_zone, 1)
        rubric_score = round(0.6 + score_coverage * 0.25 + candidate_density * 0.15, 2)

        return {
            "evidence": {
                "crop_db_version": self._db_version,
                "data_sources": self._db_sources,
                "zone_id": zone_id,
                "total_crops_in_zone": total_in_zone,
                "candidates_after_filter": len(candidates),
                "recommendation_count": len(recommendations),
                "filter_applied": {
                    "purpose": purpose,
                    "difficulty": difficulty,
                    "space_sqm": space_sqm,
                    "container": container,
                    "harvest_max_days": harvest_max,
                },
            },
            "confidence": {
                "rubric_score": min(rubric_score, 0.98),
                "coverage_pct": round(score_coverage, 2),
                "confidence_note": (
                    f"该区 {total_in_zone} 种作物中 {len(candidates)} 种匹配条件，"
                    f"推荐 Top {len(recommendations)}"
                ),
            },
            "constraints": {
                "total_crops_available_in_zone": total_in_zone,
                "filter_criteria": preferences,
                "note": "推荐基于公开农艺文献聚合，尚未叠加本地实测校准",
            },
            "recommendation": recommendations,
        }
