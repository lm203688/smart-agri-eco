#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2-A2：Köppen 分区一致性 —— `koppen_grid.json` (11946 cells × 12 classes)
与 `global_zones.json` (8 分区 × 声明 koppen_class) 的内部一致性检验。

路线要求（docs/SCI_ROADMAP_2026-10-18.md §S2-A2）：
  - 用 `koppen_grid.json` 11946 cells + `global_zones.json` 8 分区做内部一致性检验
  - 必须诚实声明：`koppen_grid.json` provenance 已自述"启发式分区投影，非
    Beck et al. 1km 真实栅格"——论文里这句话**原样保留**，作为 Limitations 明确写出
  - 可选升级：下载 Beck et al. 2018 的 1km 数据（公开 CC BY 4.0），替换后接口不变
  - 验收：一致性报告 + provenance 引用链完整（3 篇文献 key 入 REFERENCES）

**诚实标注**（必须与论文一致）：
本脚本做**内部一致性**，不是外部真值。分区→Köppen 类映射是启发式，
栅格是 2° 粗分辨率投影，都受 `provenance.note` 声明的局限约束。
审稿人若问"与真实 1km 栅格差多少"，本脚本给不出答案——
须走 Beck et al. (2018) 1km 数据升级路径，届时接口不变、只换数据文件。

用法：
    python scripts/s2_a2_koppen_consistency.py
    python scripts/s2_a2_koppen_consistency.py --json
    python scripts/s2_a2_koppen_consistency.py --strict
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
GRID_PATH = ROOT / "data" / "zone_meta" / "koppen_grid.json"
ZONES_PATH = ROOT / "data" / "zone_meta" / "global_zones.json"
REFS_PATH = ROOT / "docs" / "REFERENCES.md"
OUT_DIR = ROOT / "benchmarks" / "results"
OUT_PATH = OUT_DIR / "koppen_consistency.json"

# 路线点名的 3 篇关键文献 key（须已在 REFERENCES.md 中登记）
REQUIRED_REF_KEYS = ["peel2007", "kottek2006", "beck2018"]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def declared_letters(koppen_class: str) -> List[str]:
    """声明的 koppen_class 可能为复合形式如 'Cfa/Cwa'，取全部子型字母。"""
    return [p.strip() for p in str(koppen_class or "").split("/") if p.strip()]


def primary_letter(k: str) -> str:
    return k[0] if k else ""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_report() -> Dict[str, Any]:
    grid_doc = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    zones_doc = json.loads(ZONES_PATH.read_text(encoding="utf-8"))

    grid_classes = list(grid_doc.get("classes") or [])
    cells = grid_doc.get("cells") or []
    zone_entries = zones_doc.get("zones") or []

    # ---- Part 1: 类集合一致性（声明 vs 存在） ----
    # 从 8 分区聚合声明类
    declared_union: Set[str] = set()
    per_zone_declared: Dict[str, List[str]] = {}
    for z in zone_entries:
        zid = z.get("zone_id", "")
        decl = declared_letters(z.get("koppen_class", ""))
        per_zone_declared[zid] = decl
        declared_union.update(decl)

    grid_set = set(grid_classes)
    # 声明类在栅格中的覆盖
    declared_covered = sorted(declared_union & grid_set)
    declared_missing = sorted(declared_union - grid_set)   # 声明了但栅格无
    grid_unused = sorted(grid_set - declared_union)         # 栅格有但分区未声明

    # 逐分区覆盖
    per_zone_coverage: List[Dict[str, Any]] = []
    for z in zone_entries:
        zid = z.get("zone_id", "")
        decl = per_zone_declared[zid]
        covered = sorted(set(decl) & grid_set)
        missing = sorted(set(decl) - grid_set)
        per_zone_coverage.append({
            "zone_id": zid,
            "declared": decl,
            "covered_by_grid": covered,
            "missing_from_grid": missing,
            "fully_covered": len(missing) == 0,
        })

    # ---- Part 2: 栅格类分布 + 分区归属推断 ----
    class_counts = Counter(c["class"] for c in cells if c.get("class"))
    total_cells = sum(class_counts.values())

    # 按声明类统计栅格占比
    per_class_share: List[Dict[str, Any]] = []
    for cls, n in sorted(class_counts.items()):
        # 是否被任一分区声明
        owners = [zid for zid, decl in per_zone_declared.items() if cls in decl]
        per_class_share.append({
            "class": cls,
            "cells": n,
            "share": round(n / total_cells, 4) if total_cells else 0.0,
            "declared_by_zones": owners,
            "orphan_class": len(owners) == 0,
        })

    orphan_classes = sorted({s["class"] for s in per_class_share if s["orphan_class"]})
    orphan_cells = sum(class_counts[c] for c in orphan_classes)

    # ---- Part 3: 分区归属统计（每个分区声明的类在栅格中的合计占比）----
    per_zone_share: List[Dict[str, Any]] = []
    for z in zone_entries:
        zid = z.get("zone_id", "")
        decl = per_zone_declared[zid]
        n_declared = sum(class_counts.get(c, 0) for c in decl)
        per_zone_share.append({
            "zone_id": zid,
            "declared": decl,
            "cells_in_grid": n_declared,
            "share": round(n_declared / total_cells, 4) if total_cells else 0.0,
        })

    # ---- Part 4: 关键分区覆盖率校验（防 152 份配方指向的空分区）----
    # 从 env_recipes 统计每个 zone_id 的配方数
    recipes_dir = ROOT / "data" / "env_recipes"
    recipe_by_zone: Counter = Counter()
    if recipes_dir.is_dir():
        for p in recipes_dir.glob("*.json"):
            zid = p.name.split("__")[0]
            recipe_by_zone[zid] += 1

    # 分区声明类在栅格中的占比 0 表示该分区在栅格上无覆盖（真缺口）
    zero_coverage_zones = [r["zone_id"] for r in per_zone_share if r["cells_in_grid"] == 0]
    zero_coverage_with_recipes = [zid for zid in zero_coverage_zones if recipe_by_zone.get(zid, 0) > 0]

    # ---- Part 5: 溯源引用链完整性（3 篇文献必须入 REFERENCES.md）----
    ref_doc = REFS_PATH.read_text(encoding="utf-8") if REFS_PATH.exists() else ""
    ref_check: List[Dict[str, Any]] = []
    for key in REQUIRED_REF_KEYS:
        # 宽松匹配：REFERENCES.md 的 JSON 片段含 "key":"peel2007"
        present = f'"key":"{key}"' in ref_doc or f'"key": "{key}"' in ref_doc or f'"{key}"' in ref_doc
        ref_check.append({"key": key, "present": present})

    grid_prov = grid_doc.get("provenance") or {}
    prov_note = grid_prov.get("note", "")
    prov_has_honest_disclosure = "启发式" in prov_note and "非" in prov_note and "真实栅格" in prov_note
    prov_reference_count = len(grid_prov.get("reference") or [])

    # ---- Part 6: 验收 ----
    acceptance = {
        "grid_total_cells": total_cells,
        "grid_total_classes": len(grid_classes),
        "declared_covered_count": len(declared_covered),
        "declared_missing_count": len(declared_missing),
        "grid_unused_count": len(grid_unused),
        "all_zones_fully_covered": all(x["fully_covered"] for x in per_zone_coverage),
        "zero_coverage_zones_with_recipes": zero_coverage_with_recipes,
        "orphan_classes": orphan_classes,
        "orphan_cells": orphan_cells,
        "all_refs_present": all(r["present"] for r in ref_check),
        "prov_honest_disclosure_present": prov_has_honest_disclosure,
        "prov_reference_count_ge_3": prov_reference_count >= 3,
    }
    # 关键验收：3 篇文献齐备 + provenance 诚实披露 + 引用链 ≥3
    acceptance["all_pass"] = (
        acceptance["all_refs_present"]
        and acceptance["prov_honest_disclosure_present"]
        and acceptance["prov_reference_count_ge_3"]
        and len(zero_coverage_with_recipes) == 0  # 有配方的分区在栅格里必须有覆盖
    )

    return {
        "generated_by": "scripts/s2_a2_koppen_consistency.py",
        "roadmap_task": "S2-A2",
        "scope": f"{total_cells} grid cells × {len(grid_classes)} classes ↔ "
                 f"{len(zone_entries)} zones × {len(declared_union)} declared classes",
        "honesty_notes": [
            "本脚本做**内部一致性**，不是外部真值。栅格 provenance 已自述"
            "'启发式分区投影，非 Beck et al. 1km 真实栅格'（脚本会校验此声明在位）。"
            "审稿人若问'与真实 1km 栅格差多少'，本脚本给不出答案——须走 "
            "Beck et al. (2018) 1km 数据升级路径，届时接口不变、只换数据文件。",
            "本脚本报告'声明 vs 存在'差异是**发现**，不是失败：分区声明的复合类（如 Cfa/Cwa）"
            "与栅格 12 类的实际覆盖之间存在预期缺口，论文须逐条列出并解释成因。",
            "orphan_classes（栅格有但分区未声明，如 Aw）表示数据冗余，可能来自 "
            "generate_koppen_grid.py 的启发式分支，不代表错误，但论文须提及。",
        ],
        "class_set_reconciliation": {
            "declared_by_zones_union": sorted(declared_union),
            "grid_classes": sorted(grid_set),
            "declared_and_covered": declared_covered,
            "declared_but_missing_from_grid": declared_missing,
            "grid_but_no_zone_declares": grid_unused,
            "per_zone_coverage": per_zone_coverage,
        },
        "grid_distribution": {
            "total_cells": total_cells,
            "classes": per_class_share,
            "orphan_classes": orphan_classes,
            "orphan_cells": orphan_cells,
        },
        "zone_share_in_grid": per_zone_share,
        "recipe_zone_coverage": {
            "recipes_by_zone": dict(recipe_by_zone),
            "zero_coverage_zones_with_recipes": zero_coverage_with_recipes,
        },
        "provenance": {
            "reference_chain_check": ref_check,
            "prov_note_excerpt": prov_note[:400] + ("..." if len(prov_note) > 400 else ""),
            "prov_honest_disclosure_present": prov_has_honest_disclosure,
            "prov_reference_count": prov_reference_count,
        },
        "acceptance": acceptance,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="S2-A2 Köppen 分区一致性")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    report = build_report()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    acc = report["acceptance"]
    reconc = report["class_set_reconciliation"]
    dist = report["grid_distribution"]
    prov = report["provenance"]
    print("=== S2-A2 Köppen 分区一致性 ===")
    print(f"范围: {report['scope']}")
    print()
    print(f"声明↔栅格 类集合对账：")
    print(f"  声明并栅格覆盖 : {len(reconc['declared_and_covered'])} 类")
    print(f"  声明但栅格缺失 : {len(reconc['declared_but_missing_from_grid'])} 类"
          f"  {reconc['declared_but_missing_from_grid'] or '（无）'}")
    print(f"  栅格有但无声明 : {len(reconc['grid_but_no_zone_declares'])} 类"
          f"  {reconc['grid_but_no_zone_declares'] or '（无）'}")
    print()
    print("分区覆盖情况：")
    for r in reconc["per_zone_coverage"]:
        mark = "✅" if r["fully_covered"] else "⚠️"
        print(f"  {mark} {r['zone_id']:22s} 声明={r['declared']}"
              f"  覆盖={r['covered_by_grid']}"
              f"  缺失={r['missing_from_grid'] or '（无）'}")
    print()
    print(f"栅格类分布（top 5）:")
    for row in sorted(dist["classes"], key=lambda x: -x["cells"])[:5]:
        tag = "" if not row["orphan_class"] else "  [orphan]"
        print(f"  {row['class']:4s} {row['cells']:5d} cells ({row['share']*100:.1f}%){tag}")
    print(f"  ... 共 {len(dist['classes'])} 类")
    print()
    print("溯源引用链：")
    for r in prov["reference_chain_check"]:
        mark = "✅" if r["present"] else "❌"
        print(f"  {mark} {r['key']}: {'present' if r['present'] else 'MISSING'}")
    print(f"  prov.honest_disclosure: {prov['prov_honest_disclosure_present']}")
    print(f"  prov.reference_count: {prov['prov_reference_count']}")
    print()
    print("验收：")
    for k, v in acc.items():
        if isinstance(v, bool):
            mark = "✅" if v else "❌"
            print(f"  {mark} {k}: {v}")
        else:
            print(f"     {k}: {v}")
    print()
    print(f"已写入 {os.path.relpath(OUT_PATH, ROOT)}")

    if args.strict and not acc["all_pass"]:
        print("\n❌ --strict 未通过")
        return 1
    if args.json:
        print("\n" + json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if acc["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
