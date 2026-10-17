#!/usr/bin/env python3
"""查漏补缺扫描 · C：Env Recipe sources[] 法务三字段完整性

CORE_OBJECTIVE §五 明确：sources[] 每条必须补齐
  source_license + data_quality + trial_location
  混合许可（含 FAO CC BY-NC-SA）下这是法务刚需，不是优化项。
"""
import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
recipe_dir = ROOT / "data" / "env_recipes"
if not recipe_dir.exists():
    print(f"未找到 {recipe_dir}")
    raise SystemExit(0)

files = sorted(recipe_dir.glob("*.json"))
print(f"=== Env Recipe sources[] 法务字段完整性 ===")
print(f"配方文件数: {len(files)}")

missing_license = 0
missing_quality = 0
missing_trial = 0
total_sources = 0
recipes_with_nc = 0
field_counter = Counter()
recipes_missing_all_three = []

for f in files:
    try:
        data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        print(f"  [JSON损坏] {f.name}: {e}")
        continue
    sources = data.get("sources") or data.get("source") or []
    if not isinstance(sources, list):
        # 单 source 字符串
        sources = [sources] if sources else []
    has_nc = False
    for s in sources:
        total_sources += 1
        if isinstance(s, dict):
            lic = s.get("source_license")
            q = s.get("data_quality")
            t = s.get("trial_location")
            if lic is None:
                missing_license += 1
                field_counter["missing_source_license"] += 1
            if q is None:
                missing_quality += 1
                field_counter["missing_data_quality"] += 1
            if t is None:
                missing_trial += 1
                field_counter["missing_trial_location"] += 1
            if isinstance(lic, str) and ("NC" in lic.upper() or "NON-COMMERC" in lic.upper()):
                has_nc = True
        elif isinstance(s, str):
            # 字符串形式的 source，完全没有结构化字段
            missing_license += 1
            missing_quality += 1
            missing_trial += 1
            field_counter["scalar_source_no_fields"] += 1
            if "FAO" in s.upper() or "NC" in s.upper():
                has_nc = True
    if has_nc:
        recipes_with_nc += 1
    if missing_license and missing_quality and missing_trial and total_sources:
        recipes_missing_all_three.append(f.name)

print(f"\nsources[] 总条数: {total_sources}")
print(f"含 NC(非商用) 来源的配方数: {recipes_with_nc}")
print(f"\n缺失 source_license: {missing_license} 条 ({missing_license/max(total_sources,1):.1%})")
print(f"缺失 data_quality:   {missing_quality} 条 ({missing_quality/max(total_sources,1):.1%})")
print(f"缺失 trial_location: {missing_trial} 条 ({missing_trial/max(total_sources,1):.1%})")
print(f"\n字段缺失分布: {dict(field_counter)}")
print(f"\nCORE_OBJECTIVE §五判定：这是'法务刚需，不是优化项'")
print(f"  -> 三字段缺失比例直接决定法务合规缺口大小")
print(f"  -> 152 份配方若多数缺这三字段，则 N4 边界(数据不得转售)仍处于裸奔状态")
