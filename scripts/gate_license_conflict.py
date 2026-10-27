#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_license_conflict.py —— 门禁：Env Recipe 许可一致性（P0-5 许可冲突）

依据：项目全面提升报告_2026-10-26 §四 P0-5 与 docs/CORE_OBJECTIVE.md §五：
  - 152 份配方顶层均标 CC-BY-4.0，同时 license_scope 又声明含 NC 来源不得转售。
    这类"顶层宽松 + scope 收紧"的组合本身是**有意的治理声明**，但必须一致性成立：
      ① 有 NC 来源 → license_scope 必须声明非商用限制（否则顶层 CC-BY 掩盖字段级限制）
      ② license_scope 声明了非商用 → 必须确实存在 NC 来源（否则声明虚假/冗余）
  - 空 URL 来源条目必须有处置状态（url_unverified + reason），不允许静默留空。
  - 归因完整性：sources 非空、每条 title 非空、顶层 license 非 unknown。

本门禁不判断"法律结论是否正确"（需法务意见），只保证**声明之间不自相矛盾**，
即报告 P0-5 的"152 空 URL 与许可冲突均有处置状态"中"许可冲突"部分。

用法：
    python scripts/gate_license_conflict.py              # 通过=0，失败=1
    python scripts/gate_license_conflict.py --strict     # 同上（保留参数兼容）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "data" / "env_recipes"

# license_scope 中声明非商用的关键词（对齐报告 P0-5 与 CORE_OBJECTIVE §五）
_NC_SCOPE_KEYWORDS = ("NC", "非商用", "不得转售", "不得作为付费", "非商业")
# sources[].license 中的 NC 标记（CC BY-NC-* 系列）
_NC_LICENSE_MARKERS = ("NC", "非商用", "非商业")


def _is_nc_license(license_text: str) -> bool:
    t = (license_text or "").upper()
    return any(m.upper() in t for m in _NC_LICENSE_MARKERS)


def _scope_declares_nc(scope_text: str) -> bool:
    t = scope_text or ""
    return any(k in t for k in _NC_SCOPE_KEYWORDS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="兼容参数（等价默认）")
    ap.parse_args()

    files = sorted(RECIPES.glob("*.json"))
    if not files:
        print(f"❌ 未找到 {RECIPES}/*.json")
        return 1

    issues: list[str] = []
    stats = {"recipes": 0, "sources": 0, "nc_sources": 0,
             "empty_url": 0, "empty_url_handled": 0}

    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(f"{f.name}: JSON 解析失败 {e}")
            continue
        stats["recipes"] += 1

        top_license = (obj.get("license") or "").strip()
        scope = obj.get("license_scope") or ""
        sources = obj.get("sources") or []

        # ---- 归因完整性 ----
        if not sources:
            issues.append(f"{f.name}: sources 为空，无法溯源")
        if not top_license or top_license.lower() == "unknown":
            issues.append(f"{f.name}: 顶层 license 缺失或 unknown")
        if not scope:
            issues.append(f"{f.name}: license_scope 缺失（NC 治理声明必须显式）")

        # ---- 逐条来源检查 ----
        has_nc = False
        for i, s in enumerate(sources):
            stats["sources"] += 1
            title = (s.get("title") or "").strip()
            if not title:
                issues.append(f"{f.name}: sources[{i}] title 缺失")
            lic = (s.get("license") or "").strip()
            if lic.lower() == "unknown":
                issues.append(f"{f.name}: sources[{i}] license 仍为 unknown（应保守占位）")
            if _is_nc_license(lic):
                has_nc = True
                stats["nc_sources"] += 1

            # ---- 空 URL 处置状态 ----
            url = (s.get("url") or "").strip()
            if not url:
                stats["empty_url"] += 1
                if s.get("url_unverified") is not True or not s.get("url_unverified_reason"):
                    issues.append(
                        f"{f.name}: sources[{i}] 空 URL 缺处置状态 "
                        f"(需 url_unverified=true + url_unverified_reason)")
                else:
                    stats["empty_url_handled"] += 1

        # ---- NC 一致性（双向）----
        if has_nc and not _scope_declares_nc(scope):
            issues.append(f"{f.name}: 含 NC 来源但 license_scope 未声明非商用限制")
        if _scope_declares_nc(scope) and not has_nc:
            issues.append(f"{f.name}: license_scope 声明非商用但无 NC 来源（声明冗余）")

    if issues:
        print(f"❌ 许可一致性门禁失败（{len(issues)} 项）：")
        for msg in issues[:15]:
            print(f"   - {msg}")
        if len(issues) > 15:
            print(f"   ... 共 {len(issues)} 项")
        print(f"\n统计：recipes={stats['recipes']} sources={stats['sources']} "
              f"nc_sources={stats['nc_sources']} empty_url={stats['empty_url']} "
              f"empty_url_handled={stats['empty_url_handled']}")
        return 1

    print(f"✅ 许可一致性门禁通过：{stats['recipes']} 份配方 / {stats['sources']} 条 sources")
    print(f"   NC 来源={stats['nc_sources']}，空 URL={stats['empty_url']}"
          f"（全部有处置状态={stats['empty_url_handled']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
