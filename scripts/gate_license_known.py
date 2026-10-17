#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_license_known.py —— 门禁：env_recipes 里 sources[].license 不得为 "unknown"

GAP_AUDIT §B3：license=unknown 152 条属于法务红线未闭合（"我知道要填但不知道填什么"
比"未声明"更危险）。本门禁确保：
  1) 任何 sources[].license == "unknown" → 直接失败
  2) 任何 sources[].source_license 以 "unknown" 开头 → 直接失败

若必须留占位（因为源方未标注），必须用带 note 的保守占位（如 "CC BY-NC-SA 4.0
(保守占位：...)"），并在同一 source 条目里加 license_note 字段说明占位原因，
不允许静默填 "unknown"。

用法：
    python scripts/gate_license_known.py              # 通过=0，失败=1
    python scripts/gate_license_known.py --strict     # 同上（保留参数兼容）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "data" / "env_recipes"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="兼容参数（等价默认）")
    p.parse_args()

    files = sorted(RECIPES.glob("*.json"))
    if not files:
        print(f"❌ 未找到 {RECIPES}/*.json")
        return 1

    bad_license = []  # (file, source_idx, license)
    bad_source_license = []
    total_sources = 0

    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"❌ {f.name}: JSON 解析失败 {e}")
            return 1
        for i, s in enumerate(obj.get("sources") or []):
            total_sources += 1
            lic = (s.get("license") or "").strip()
            s_lic = (s.get("source_license") or "").strip()
            if lic.lower() == "unknown":
                bad_license.append((f.name, i, lic))
            if s_lic.lower().startswith("unknown"):
                bad_source_license.append((f.name, i, s_lic))

    errs = 0
    if bad_license:
        errs += 1
        print(f"❌ sources[].license == 'unknown' 命中 {len(bad_license)} 条：")
        for name, i, v in bad_license[:10]:
            print(f"   {name} sources[{i}].license = {v!r}")
        if len(bad_license) > 10:
            print(f"   ... 共 {len(bad_license)} 条")
    if bad_source_license:
        errs += 1
        print(f"❌ sources[].source_license 以 'unknown' 开头命中 {len(bad_source_license)} 条：")
        for name, i, v in bad_source_license[:10]:
            print(f"   {name} sources[{i}].source_license = {v!r}")

    if errs:
        print(f"\n→ 门禁失败：license 必须显式声明或带 note 的保守占位，不允许静默 'unknown'")
        return 1

    print(f"✅ license 门禁通过：{len(files)} 份配方 / {total_sources} 条 sources 全部无 'unknown'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
