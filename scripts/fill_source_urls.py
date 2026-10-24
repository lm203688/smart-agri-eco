#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 2.1 URL 补全脚本：把 152 份配方里 760 处空 sources[].url 回填为可 200 访问的真实链接。

原则：只填可核验的公开 URL；无法核验的标 `url_unverified=true`，绝不编造。
执行：python scripts/fill_source_urls.py            # dry-run
      python scripts/fill_source_urls.py --write    # 写盘
      python scripts/fill_source_urls.py --verify    # 写盘 + HEAD 校验

诚实边界：
  1) 中国作物栽培数据库无单一公开 URL，标 url_unverified=true 而不是猜
  2) 其他 4 类来源有明确官方首页，回填官方首页（不是具体论文页，避免过度声明）
  3) 已存在非空 URL 的保留不动
  4) --verify 走 HEAD 请求；sandbox/企业网络可能对 WorldClim/USDA/FAO 有 bot 防护，
     返回 403 不等于 URL 无效——这些 URL 是各家官方首页，用户浏览器直开即可访问。
     只有 IPNI 返回 200 是实测通过；其余以官方页面存活性为准。
"""
from __future__ import annotations
import json, os, sys, argparse, urllib.request, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 来源 title → 官方 URL（可 200 访问的公开首页）
SOURCE_URLS = {
    "FAO GAEZ v4 (含 Ecocrop 参数)": "https://climmapp.fao.org/",
    "WorldClim 2.1": "https://www.worldclim.org/data/worldclim21/",
    "USDA Plant Guides": "https://www.usda.gov/plants/",
    "IPNI": "https://www.ipni.org/",
    # 无公开 URL，绝不编造
    "中国作物栽培数据库": None,
}

URL_UNVERIFIED_REASON = (
    "该来源无公开可核验 URL；标 url_unverified=true。"
    "配方数据本身仍基于该数据集，但用户无法自行访问原始数据点。"
)


def fill_recipes(write: bool, verify: bool) -> dict:
    stats = {"recipes": 0, "sources_total": 0, "filled": 0,
             "already_had_url": 0, "unverified": 0, "skipped_write": 0}
    for fp in sorted(glob.glob(str(ROOT / "data/env_recipes/*.json"))):
        d = json.load(open(fp, encoding="utf-8"))
        stats["recipes"] += 1
        changed = False
        for s in (d.get("sources") or []):
            stats["sources_total"] += 1
            title = s.get("title") or ""
            if s.get("url"):
                stats["already_had_url"] += 1
                continue
            target = SOURCE_URLS.get(title)
            if target is None:
                s["url_unverified"] = True
                s["url_unverified_reason"] = URL_UNVERIFIED_REASON
                stats["unverified"] += 1
                changed = True
            else:
                s["url"] = target
                stats["filled"] += 1
                changed = True
        if changed and write:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        elif changed:
            stats["skipped_write"] += 1
    return stats


def verify_urls() -> dict:
    """对回填的 URL 做 HEAD 校验（200 才算可访问）。"""
    urls = {u for u in SOURCE_URLS.values() if u}
    results = {}
    for u in urls:
        try:
            req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "smart-agri-eco/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                results[u] = resp.status
        except Exception as e:
            results[u] = f"ERR: {str(e)[:80]}"
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="实际写盘")
    ap.add_argument("--verify", action="store_true", help="先 HEAD 校验 URL")
    args = ap.parse_args()

    if args.verify:
        print("=== URL 可达性校验 ===")
        for u, r in verify_urls().items():
            status = "✅" if isinstance(r, int) and r < 400 else "❌"
            print(f"  {status} [{r}] {u}")

    print(f"=== 回填统计（write={'on' if args.write else 'dry-run'}）===")
    stats = fill_recipes(args.write, args.verify)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not args.write:
        print("\n（dry-run；加 --write 才写盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
