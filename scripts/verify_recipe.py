#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M10-O4: verify_recipe.py — 单配方结构化验证脚本（零依赖）

读取一份 Env Recipe JSON，做 5 项检查并输出结构化报告（JSON / 文本）：

  1. **schema 完整性**：必填字段（protocol/recipe_version/crop/stage/environment）
  2. **枚举合法性**：stage / device_class / light_type / sensor_capability 是否在 schema 白名单
  3. **数值范围**：温度 / 湿度 / pH / EC / DLI 是否落在生理可行域
  4. **依赖完整**：sources 非空 & 每条 source 带 title + license
  5. **reproducibility_score**：关键参数完备度（0-1）

用法：
  python scripts/verify_recipe.py data/env_recipes/arid__仙人掌.json
  python scripts/verify_recipe.py <path> --json          # JSON 输出
  python scripts/verify_recipe.py <path> --all           # 批量验证整个 data/env_recipes/

零外部依赖，纯标准库。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")

# 与 schemas/env_recipe.schema.json v1.2 对齐
REQUIRED_TOP = ["protocol", "recipe_version", "crop", "stage", "environment"]
STAGE_ENUM = {"seed", "seedling", "vegetative", "flowering", "fruiting",
              "harvest", "full_cycle"}
DEVICE_ENUM = {"balcony", "windowsill", "indoor_cabinet", "aerogarden_orphan",
               "greenhouse", "open_field", "other"}
LIGHT_ENUM = {"full_spectrum_led", "red_blue_led", "sunlight", "unknown"}
SENSOR_ENUM = {"temp", "humidity", "ppfd", "co2", "ec", "ph", "camera"}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# 生理可行域（保守边界，非致命——超界记 warn 不记 error）
RANGES = {
    ("environment", "temperature", "day_c"): (-5.0, 50.0),
    ("environment", "temperature", "night_c"): (-10.0, 45.0),
    ("environment", "humidity", "min_pct"): (0.0, 100.0),
    ("environment", "humidity", "max_pct"): (0.0, 100.0),
    ("environment", "water_nutrient", "ph"): (3.5, 9.5),
    ("environment", "water_nutrient", "ec_mscm"): (0.0, 6.0),
    ("environment", "light", "ppfd_umol_m2s"): (0.0, 2000.0),
    ("environment", "light", "dli_umol_m2_day"): (0.0, 20000.0),
}

# reproducibility_score 打分维度：key → (path, weight)
# 满分 1.0 = 所有关键参数齐备
SCORE_KEYS = [
    (("crop", "species"), 0.10),
    (("crop", "latin"), 0.05),
    (("stage",), 0.05),
    (("device_profile", "device_class"), 0.05),
    (("environment", "temperature", "day_c"), 0.10),
    (("environment", "temperature", "night_c"), 0.10),
    (("environment", "humidity", "min_pct"), 0.10),
    (("environment", "humidity", "max_pct"), 0.10),
    (("environment", "water_nutrient", "ph"), 0.10),
    (("environment", "water_nutrient", "water_ml_day"), 0.05),
    (("environment", "light", "ppfd_umol_m2s"), 0.10),
    (("sources",), 0.05),
    (("license",), 0.05),
]


def _dig(obj: Any, path: Tuple[str, ...]) -> Any:
    """按 path 逐层取值，任一环节缺失即返回 None。"""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def check_required(recipe: Dict[str, Any]) -> List[str]:
    """必填字段缺失清单。"""
    return [k for k in REQUIRED_TOP if k not in recipe]


def check_enums(recipe: Dict[str, Any]) -> List[str]:
    """枚举字段越界清单。"""
    issues = []
    stage = recipe.get("stage")
    if stage is not None and stage not in STAGE_ENUM:
        issues.append(f"stage='{stage}' 不在枚举 {sorted(STAGE_ENUM)}")
    dc = _dig(recipe, ("device_profile", "device_class"))
    if dc is not None and dc not in DEVICE_ENUM:
        issues.append(f"device_class='{dc}' 不在枚举 {sorted(DEVICE_ENUM)}")
    lt = _dig(recipe, ("device_profile", "light_type"))
    if lt is not None and lt not in LIGHT_ENUM:
        issues.append(f"light_type='{lt}' 不在枚举 {sorted(LIGHT_ENUM)}")
    sensors = _dig(recipe, ("device_profile", "sensor_capability")) or []
    for s in sensors:
        if s not in SENSOR_ENUM:
            issues.append(f"sensor_capability 含未知值 '{s}'")
    return issues


def check_ranges(recipe: Dict[str, Any]) -> List[str]:
    """数值范围越界清单（超界记 warn 不记 error）。"""
    warnings = []
    for path, (lo, hi) in RANGES.items():
        v = _dig(recipe, path)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            warnings.append(f"{'.'.join(path)}='{v}' 非数值")
            continue
        if not (lo <= f <= hi):
            warnings.append(f"{'.'.join(path)}={f} 越界 [{lo}, {hi}]")
    # 湿度 min ≤ max
    hmin = _dig(recipe, ("environment", "humidity", "min_pct"))
    hmax = _dig(recipe, ("environment", "humidity", "max_pct"))
    if hmin is not None and hmax is not None:
        try:
            if float(hmin) > float(hmax):
                warnings.append(f"humidity.min_pct={hmin} > max_pct={hmax}")
        except (TypeError, ValueError):
            pass
    return warnings


def check_dependencies(recipe: Dict[str, Any]) -> List[str]:
    """sources / license 存在性 + 每条 source 结构。"""
    issues = []
    sources = recipe.get("sources")
    if not sources:
        issues.append("sources 缺失或为空（违反法务溯源要求）")
    else:
        for i, s in enumerate(sources):
            if not isinstance(s, dict):
                issues.append(f"sources[{i}] 非 object")
                continue
            if not s.get("title"):
                issues.append(f"sources[{i}] 缺 title")
            # license 可选但强烈建议
            if not s.get("source_license") and not s.get("license"):
                issues.append(f"sources[{i}] 缺 source_license/license")
    if not recipe.get("license"):
        issues.append("顶层 license 缺失")
    return issues


def compute_reproducibility_score(recipe: Dict[str, Any]) -> Tuple[float, List[str], List[str]]:
    """基于关键参数完备度算 reproducibility_score。

    返回 (score, present_paths, missing_paths)，路径以 '.' 连接。
    满分 1.0；缺失项按权重递减；sources 存在且有 ≥1 条有效 source 才计分。
    """
    score = 0.0
    present: List[str] = []
    missing: List[str] = []
    for path, weight in SCORE_KEYS:
        v = _dig(recipe, path)
        if v is None:
            missing.append(".".join(path))
            continue
        # sources 特殊：需要非空 list
        if path == ("sources",) and not v:
            missing.append(".".join(path))
            continue
        score += weight
        present.append(".".join(path))
    return round(score, 4), present, missing


def verify_recipe(recipe: Dict[str, Any],
                  filename: str = "") -> Dict[str, Any]:
    """完整验证：返回结构化报告。

    字段：
      ok                  总判决（True=可发布 / False=需修复）
      filename            配方文件名（可空）
      missing_required    必填字段缺失
      enum_violations     枚举越界
      range_warnings      数值越界（warn 级）
      dependency_issues   依赖完整性问题
      reproducibility_score  0-1 关键参数完备度
      present_paths       已具备的关键路径
      missing_paths       缺失的关键路径
      sha256_prefix       文件指纹前 16 位（有 path 时）
      note                简短解读
    """
    missing = check_required(recipe)
    enums = check_enums(recipe)
    ranges = check_ranges(recipe)
    deps = check_dependencies(recipe)
    score, present, miss_paths = compute_reproducibility_score(recipe)
    # 硬性 error：必填缺 + 枚举错 + 依赖缺
    errors = missing + enums + deps
    ok = len(errors) == 0 and score >= 0.80
    note_parts = []
    if missing:
        note_parts.append(f"必填缺失 {len(missing)}")
    if enums:
        note_parts.append(f"枚举越界 {len(enums)}")
    if deps:
        note_parts.append(f"依赖问题 {len(deps)}")
    if ranges:
        note_parts.append(f"数值越界 warn {len(ranges)}")
    if score < 0.80:
        note_parts.append(f"完备度 {score:.2f}<0.80")
    return {
        "ok": ok,
        "filename": filename,
        "missing_required": missing,
        "enum_violations": enums,
        "range_warnings": ranges,
        "dependency_issues": deps,
        "reproducibility_score": score,
        "present_paths": present,
        "missing_paths": miss_paths,
        "note": "; ".join(note_parts) if note_parts else "全部通过",
    }


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _sha256_prefix(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _main() -> int:
    parser = argparse.ArgumentParser(description="M10-O4 单配方结构化验证")
    parser.add_argument("path", nargs="?", help="配方 JSON 路径")
    parser.add_argument("--recipes-dir", default=DEFAULT_RECIPES_DIR,
                        help="批量模式下的配方库根目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--all", action="store_true",
                        help="批量验证整个 recipes-dir（无需 path）")
    args = parser.parse_args()

    if args.all:
        if not os.path.isdir(args.recipes_dir):
            print(f"配方目录不存在: {args.recipes_dir}", file=sys.stderr)
            return 1
        files = sorted(f for f in os.listdir(args.recipes_dir)
                       if f.endswith(".json"))
        if not files:
            print(f"配方目录为空: {args.recipes_dir}", file=sys.stderr)
            return 1
        reports = []
        for name in files:
            p = os.path.join(args.recipes_dir, name)
            try:
                r = _load_json(p)
                rep = verify_recipe(r, filename=name)
                rep["sha256_prefix"] = _sha256_prefix(p)
                reports.append(rep)
            except Exception as e:  # noqa: BLE001
                reports.append({"filename": name, "ok": False,
                                "note": f"加载失败: {e}"})
        ok_count = sum(1 for r in reports if r.get("ok"))
        summary = {
            "mode": "batch",
            "recipes_dir": args.recipes_dir,
            "total": len(reports),
            "ok": ok_count,
            "failed": len(reports) - ok_count,
            "avg_reproducibility_score": round(
                sum(r.get("reproducibility_score", 0) for r in reports) / max(len(reports), 1), 4),
            "reports": reports,
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"批量验证 {summary['total']} 份配方：ok={summary['ok']} "
                  f"failed={summary['failed']} "
                  f"avg_reproducibility={summary['avg_reproducibility_score']:.3f}")
            for rep in reports:
                if not rep.get("ok"):
                    print(f"  ✗ {rep['filename']}: {rep.get('note')}")
        return 0 if ok_count == len(reports) else 1

    if not args.path:
        parser.print_help()
        return 2

    if not os.path.isfile(args.path):
        print(f"文件不存在: {args.path}", file=sys.stderr)
        return 1
    try:
        recipe = _load_json(args.path)
    except Exception as e:  # noqa: BLE001
        print(f"加载失败: {e}", file=sys.stderr)
        return 1

    report = verify_recipe(recipe, filename=os.path.basename(args.path))
    report["sha256_prefix"] = _sha256_prefix(args.path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        icon = "✓" if report["ok"] else "✗"
        print(f"{icon} {report['filename']}  ok={report['ok']}")
        print(f"  reproducibility_score = {report['reproducibility_score']:.3f}")
        print(f"  note = {report['note']}")
        if report["missing_required"]:
            print(f"  必填缺失: {report['missing_required']}")
        if report["enum_violations"]:
            print(f"  枚举越界: {report['enum_violations']}")
        if report["range_warnings"]:
            print(f"  数值越界(warn): {report['range_warnings']}")
        if report["dependency_issues"]:
            print(f"  依赖问题: {report['dependency_issues']}")
        if report["missing_paths"]:
            print(f"  缺失关键路径: {report['missing_paths']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())
