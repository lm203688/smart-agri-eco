"""phenology.py — 基于 WOFOST 物候温度总和的轻量发育期推演（零依赖，stdlib-only）。

来源：data/wofost_phenology_reference.json（从 ajwdewit/WOFOST_crop_parameters 的 wofost81 分支移植，EUPL 1.2，需署名）。
用途（B1，见 docs/opensource_scan_complementary.md）：给 growth_agent 增加『积温 → 物候期天数』的微观推演，
弥补当前 growth_plan 只给计划、不给发育期推演的缺口；不依赖 WOFOST/PCSE 引擎，保持项目零依赖。

模型（thermal-time）：某阶段天数 ≈ TSUM / max(0, 日均温 - 基温TBASE)。
仅覆盖已移植的 7 种作物（potato/wheat/soybean/sunflower/rice/sweetpotato/mungbean）。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REF_PATH = os.path.join(ROOT, "data", "wofost_phenology_reference.json")


def _load_ref() -> Dict[str, Any]:
    with open(_REF_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_key(crop: str, crops: Dict[str, Any]) -> Optional[str]:
    """按英文 key 或中文名（species_cn）解析作物键。"""
    c = crop.strip()
    if c in crops:
        return c
    for k, v in crops.items():
        if v.get("species_cn") == c:
            return k
    return None


def estimate_stage_days(crop_cn: str, mean_temp_c: float) -> Dict[str, Any]:
    """估算某作物在给定日均温下的发育期天数。

    返回：
        {available, crop, tbase_c, mean_temp_c,
         emergence_days, anthesis_days_from_sow, maturity_days_from_sow,
         requires_vernalization, note}
    emergence_days: 播种→出苗；anthesis_days_from_sow: 播种→开花；
    maturity_days_from_sow: 播种→成熟（累计）。单位：天。
    当日均温 ≤ TBASE 时发育停滞，对应天数置 None 并在 note 说明。
    """
    ref = _load_ref()
    crops = ref.get("crops", {})
    key = _resolve_key(crop_cn, crops)
    if key is None:
        return {
            "available": False,
            "crop": crop_cn,
            "covered_crops": list(crops.keys()),
            "note": "该作物尚未移植 WOFOST 物候参数；可增补 data/wofost_phenology_reference.json。",
        }
    c = crops[key]
    tbase = float(c["tbase_c"])
    eff = mean_temp_c - tbase
    out: Dict[str, Any] = {
        "available": True,
        "crop": key,
        "tbase_c": tbase,
        "mean_temp_c": mean_temp_c,
        "requires_vernalization": bool(c.get("vernalization", {}).get("idls", 0)),
    }
    if eff <= 0:
        out.update({
            "emergence_days": None,
            "anthesis_days_from_sow": None,
            "maturity_days_from_sow": None,
            "note": "日均温 %.1f℃ ≤ 基温 %.1f℃，发育停滞，无法按积温推进。" % (mean_temp_c, tbase),
        })
        return out
    te = c["tsum_em"]; t1 = c["tsum1"]; t2 = c["tsum2"]
    out.update({
        "emergence_days": round(te / eff, 1),
        "anthesis_days_from_sow": round((te + t1) / eff, 1),
        "maturity_days_from_sow": round((te + t1 + t2) / eff, 1),
        "note": c.get("note", ""),
    })
    return out


def covered_crops() -> list:
    return list(_load_ref().get("crops", {}).keys())


# ---------------------------------------------------------------------------
# 自测（零依赖；python agent/phenology.py）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 马铃薯 @ 18℃：出苗≈10.6d，开花≈20d，成熟≈116.9d
    r = estimate_stage_days("马铃薯", 18.0)
    assert r["available"] and r["emergence_days"] is not None
    # 小麦 @ 5℃ 但 TBASE=0，应正常推演
    r2 = estimate_stage_days("小麦", 5.0)
    assert r2["available"]
    # 未覆盖作物
    r3 = estimate_stage_days("番茄", 20.0)
    assert not r3["available"]
    print(json.dumps({
        "potato_18C": estimate_stage_days("马铃薯", 18.0),
        "wheat_5C": estimate_stage_days("小麦", 5.0),
        "covered": covered_crops(),
    }, ensure_ascii=False, indent=2))
