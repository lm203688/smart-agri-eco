"""phenology_extended.py — 扩展版物候查询（WOFOST 7 + 扩展 23 = 30+ 作物）。

愿景：docs/next_stage_vision_2026-10-15.md §Phase N+1 动作 #7：物候作物 7→30+。

设计：
  - 优先使用 wofost_phenology_reference.json（EUPL 1.2，7 种 WOFOST 移植）
  - 兜底使用 crop_phenology_extended.json（23 种微场景常见作物）
  - 保持与 agent/phenology.py 完全相同的函数签名，可直接替换

接口：
  estimate_stage_days(crop_cn, mean_temp_c)   # 与 phenology.py 完全兼容
  covered_crops()                            # 返回所有已覆盖作物（英文 key）
  covered_crops_cn()                         # 返回所有已覆盖作物（中文名）
  resolve_key(crop, verbose=False)           # 中文名→英文 key
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WOFOST_PATH = os.path.join(ROOT, "data", "wofost_phenology_reference.json")
_EXTENDED_PATH = os.path.join(ROOT, "data", "crop_phenology_extended.json")

_cache: Optional[Dict[str, Any]] = None


def _load_all() -> Dict[str, Any]:
    """加载合并后的作物参数（WOFOST 7 优先，扩展表补齐）。"""
    global _cache
    if _cache is not None:
        return _cache
    merged: Dict[str, Any] = {}
    # 1. 扩展表（先加载）
    if os.path.exists(_EXTENDED_PATH):
        with open(_EXTENDED_PATH, "r", encoding="utf-8") as f:
            ext = json.load(f)
        for k, v in ext.get("crops", {}).items():
            merged[k] = v
    # 2. WOFOST（后加载，覆盖同 key）
    if os.path.exists(_WOFOST_PATH):
        with open(_WOFOST_PATH, "r", encoding="utf-8") as f:
            wof = json.load(f)
        for k, v in wof.get("crops", {}).items():
            merged[k] = v
    _cache = {"crops": merged, "n": len(merged)}
    return _cache


def reload() -> Dict[str, Any]:
    """强制重载（文件变更后）。"""
    global _cache
    _cache = None
    return _load_all()


def resolve_key(crop: str) -> Optional[str]:
    """按英文 key 或中文名解析作物键。"""
    c = crop.strip()
    d = _load_all()["crops"]
    if c in d:
        return c
    for k, v in d.items():
        if v.get("species_cn") == c:
            return k
    return None


def estimate_stage_days(crop_cn: str, mean_temp_c: float) -> Dict[str, Any]:
    """估算某作物在给定日均温下的发育期天数。

    返回：
        {available, crop, tbase_c, mean_temp_c,
         emergence_days, anthesis_days_from_sow, maturity_days_from_sow,
         requires_vernalization, source, note}
    """
    d = _load_all()["crops"]
    key = resolve_key(crop_cn)
    if key is None:
        return {
            "available": False,
            "crop": crop_cn,
            "covered_crops": list(d.keys()),
            "note": "该作物尚未移植；可增补 data/crop_phenology_extended.json。",
        }
    c = d[key]
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
            "note": "日均温 %.1f℃ ≤ 基温 %.1f℃，发育停滞。" % (mean_temp_c, tbase),
        })
        return out
    te = c["tsum_em"]; t1 = c["tsum1"]; t2 = c["tsum2"]
    out.update({
        "emergence_days": round(te / eff, 1),
        "anthesis_days_from_sow": round((te + t1) / eff, 1),
        "maturity_days_from_sow": round((te + t1 + t2) / eff, 1),
        "note": c.get("note", ""),
    })
    # 来源标注
    with open(_WOFOST_PATH, "r", encoding="utf-8") as f:
        wof_crops = json.load(f).get("crops", {})
    out["source"] = "wofost" if key in wof_crops else "extended"
    return out


def covered_crops() -> list:
    """返回所有已覆盖作物（英文 key）。"""
    return list(_load_all()["crops"].keys())


def covered_crops_cn() -> list:
    """返回所有已覆盖作物（中文名）。"""
    return [v["species_cn"] for v in _load_all()["crops"].values()]


def coverage_stats() -> Dict[str, Any]:
    """覆盖统计：WOFOST 7 + 扩展 N = 总 M。"""
    d = _load_all()["crops"]
    with open(_WOFOST_PATH, "r", encoding="utf-8") as f:
        wof_crops = json.load(f).get("crops", {})
    return {
        "total": len(d),
        "wofost": len(wof_crops),
        "extended": len(d) - len(wof_crops),
        "wofost_crops": sorted(wof_crops.keys()),
        "extended_crops": sorted(k for k in d if k not in wof_crops),
    }


if __name__ == "__main__":
    import json as _json
    print("=== 扩展物候自测 ===")
    stats = coverage_stats()
    print(f"总作物={stats['total']}, WOFOST={stats['wofost']}, 扩展={stats['extended']}")
    print(f"扩展作物: {stats['extended_crops']}")

    # 每个作物都能正常推演
    print("\n推演测试（20℃ 均温）：")
    ok_count = 0
    for cn in covered_crops_cn():
        r = estimate_stage_days(cn, 20.0)
        if r["available"]:
            ok_count += 1
        print(f"  {cn:6s} → available={r['available']}, "
              f"tbase={r.get('tbase_c')}, maturity={r.get('maturity_days_from_sow')}, "
              f"source={r.get('source')}")
    print(f"\n可用作物: {ok_count}/{len(covered_crops_cn())}")
    assert ok_count >= 30, f"覆盖数不足 30，实际 {ok_count}"
    print("✅ 物候扩展自测通过（30+ 作物）")
