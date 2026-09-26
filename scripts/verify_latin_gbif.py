#!/usr/bin/env python3
"""
P2 · GBIF 校验 110 作物拉丁名（零依赖）

作物库里的 latin 字段是 AI 依据农艺通识手写的（calibrated:false，0 校验）。
本脚本对每个唯一拉丁名调用 GBIF species/match API（CC BY 4.0，已实测 1.0s），
回填校验结果：
  - latin_verified: bool（GBIF 是否匹配到）
  - gbif_accepted_name: GBIF 接受名（可能与手写 latin 不同 → 纠错信号）
  - gbif_key: GBIF usageKey
  - gbif_status: ACCEPTED / SYNONYM / ...
  - gbif_match_note: 备注（含网络失败原因）

按 latin 去重查询（110 条目 / 84 唯一种名），结果应用到所有同名条目。
运行：
  python scripts/verify_latin_gbif.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
GBIF_MATCH = "https://api.gbif.org/v1/species/match"
_UA = {"User-Agent": "agri-eco-demo/1.0 (demo)"}
_DELAY = 0.12


def gbif_match(latin: str) -> Dict[str, Any]:
    url = GBIF_MATCH + "?name=" + urllib.parse.quote(latin)
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d
    except Exception as e:
        return {"_error": str(e)}


def main() -> None:
    with open(CROP_DB, encoding="utf-8") as f:
        cdb = json.load(f)
    zones = cdb.get("zones", {})
    crops = [c for z in zones.values() for c in z.get("crops", [])]

    # 去重：latin -> 条目列表
    by_latin: Dict[str, List[dict]] = {}
    for c in crops:
        lat = (c.get("latin") or "").strip()
        if not lat:
            c["latin_verified"] = False
            c["gbif_match_note"] = "作物无 latin 字段"
            continue
        by_latin.setdefault(lat, []).append(c)

    cache: Dict[str, Dict[str, Any]] = {}
    ok = 0
    syn = 0
    fail = 0
    for lat in sorted(by_latin):
        d = gbif_match(lat)
        cache[lat] = d
        if d.get("_error"):
            fail += 1
        elif d.get("usageKey") is not None and d.get("match") is not False:
            ok += 1
            if d.get("status") == "SYNONYM":
                syn += 1
        else:
            fail += 1
        time.sleep(_DELAY)

    # 应用结果
    # 注意：GBIF species/match 在匹配成功时 match 字段常为 None（非 True），
    # 可靠信号是 usageKey 存在且 match 不为显式 False。
    for lat, entries in by_latin.items():
        d = cache[lat]
        if d.get("_error"):
            for c in entries:
                c["latin_verified"] = False
                c["gbif_match_note"] = "GBIF 查询失败：" + d["_error"]
            continue
        matched = d.get("usageKey") is not None and d.get("match") is not False
        if matched:
            for c in entries:
                c["latin_verified"] = True
                c["gbif_accepted_name"] = d.get("scientificName")
                c["gbif_key"] = d.get("usageKey")
                c["gbif_status"] = d.get("status")
                c["gbif_rank"] = d.get("rank")
                c["gbif_match_note"] = (
                    "GBIF 接受名与手写一致" if d.get("scientificName", "").lower().startswith(lat.lower())
                    else "GBIF 接受名：「" + str(d.get("scientificName")) + "」"
                )
        else:
            for c in entries:
                c["latin_verified"] = False
                c["gbif_match_note"] = "GBIF 未匹配（可能拼写/分类变动）"

    with open(CROP_DB, "w", encoding="utf-8") as f:
        json.dump(cdb, f, ensure_ascii=False, indent=2)

    verified = sum(1 for c in crops if c.get("latin_verified"))
    print(f"唯一拉丁名 {len(by_latin)} | GBIF 匹配 {ok}（其中 SYNONYM {syn}）| 未匹配/失败 {fail}")
    print(f"110 作物条目：latin_verified=True {verified} / False {len(crops) - verified}")
    print("已写回", CROP_DB)


if __name__ == "__main__":
    main()
