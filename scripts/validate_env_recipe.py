#!/usr/bin/env python3
"""
scripts/validate_env_recipe.py —— Env Recipe v1 零依赖校验器

不依赖 jsonschema：内置一个覆盖本项目 Schema 用到的约束子集的迷你校验器
（type / enum / const / required / additionalProperties / pattern / minimum / maximum / items）。

用法：
    python scripts/validate_env_recipe.py data/examples/sample_env_recipe.json
    python scripts/validate_env_recipe.py path/to/recipe.json   # 退出码 0=通过 1=失败
    python scripts/validate_env_recipe.py data/env_recipes       # 目录：全量校验
    python scripts/validate_env_recipe.py data/env_recipes --derived
        额外报告 VPD / 露点派生量体检（engine/derived.py，纯算术零依赖）
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schemas", "env_recipe.schema.json")
sys.path.insert(0, ROOT)


def _type_ok(node: object, typ: str) -> bool:
    if typ == "object":
        return isinstance(node, dict)
    if typ == "array":
        return isinstance(node, list)
    if typ == "string":
        return isinstance(node, str)
    if typ == "number":
        return isinstance(node, (int, float)) and not isinstance(node, bool)
    if typ == "integer":
        return isinstance(node, int) and not isinstance(node, bool)
    if typ == "boolean":
        return isinstance(node, bool)
    return False


def _validate(node, schema, path, errors):
    # const
    if "const" in schema and node != schema["const"]:
        errors.append(f"{path}: 期望 const={schema['const']!r}，实际 {node!r}")
        return
    # enum
    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: 值 {node!r} 不在允许枚举 {schema['enum']}")
    # type
    typ = schema.get("type")
    if typ and not _type_ok(node, typ):
        errors.append(f"{path}: 期望类型 {typ}，实际 {type(node).__name__}")
        return
    # pattern
    pat = schema.get("pattern")
    if pat and isinstance(node, str) and not re.match(pat, node):
        errors.append(f"{path}: 字符串 {node!r} 不匹配模式 {pat}")
    # numeric bounds
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if "minimum" in schema and node < schema["minimum"]:
            errors.append(f"{path}: {node} < 下限 {schema['minimum']}")
        if "maximum" in schema and node > schema["maximum"]:
            errors.append(f"{path}: {node} > 上限 {schema['maximum']}")
    # object constraints
    if isinstance(node, dict):
        for req in schema.get("required", []):
            if req not in node:
                errors.append(f"{path}: 缺必填字段 {req!r}")
        props = schema.get("properties", {})
        for k, v in node.items():
            if k in props:
                _validate(v, props[k], f"{path}.{k}", errors)
            else:
                if schema.get("additionalProperties") is False:
                    errors.append(f"{path}: 不允许的额外字段 {k!r}")
    # array items
    if isinstance(node, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, it in enumerate(node):
                _validate(it, item_schema, f"{path}[{i}]", errors)


def validate_recipe(recipe: dict, schema: dict) -> list:
    errors: list = []
    _validate(recipe, schema, "$", errors)
    return errors


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want_derived = "--derived" in sys.argv[1:]
    targets = args or [os.path.join(ROOT, "data", "examples", "sample_env_recipe.json")]
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        print(f"[失败] 读取 Schema 失败: {e}")
        return 1

    all_ok = True
    loaded: list = []  # (path, recipe) 用于 --derived 体检
    # 目录参数展开为其下所有 .json（用于全量配方校验）
    expanded: list = []
    for t in targets:
        if os.path.isdir(t):
            expanded.extend(sorted(
                os.path.join(t, n) for n in os.listdir(t) if n.endswith(".json")))
        else:
            expanded.append(t)
    for path in expanded:
        try:
            with open(path, "r", encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            print(f"[失败] {path}: 读取失败 {e}")
            all_ok = False
            continue
        errs = validate_recipe(recipe, schema)
        if errs:
            all_ok = False
            print(f"[失败] {path} ({len(errs)} 处问题)")
            for e in errs[:20]:
                print(f"   - {e}")
        else:
            print(f"[通过] {path}")
            loaded.append((path, recipe))

    if want_derived and loaded:
        from engine import derived as dv
        report = dv.audit_recipes([r for _, r in loaded])
        print()
        print("=== VPD / 露点派生量体检（engine/derived.py，纯算术） ===")
        print(f"  可计算 {report['available']}/{report['total']}，"
              f"硬告警 {report['with_flags']} 份，"
              f"软提示 {report['with_observations']} 份")
        if report["flag_kinds"]:
            print("  硬告警种类（可执行层面的问题）：")
            for k, n in report["flag_kinds"].items():
                print(f"    {n:>4d} 份  {k}")
        else:
            print("  无硬告警")
        if report["observation_kinds"]:
            print("  软提示种类（数据粒度线索，不门禁）：")
            for k, n in report["observation_kinds"].items():
                print(f"    {n:>4d} 份  {k}")
        # 逐份展示硬告警明细（只列有 flags 的，控制输出量）
        shown = 0
        for row, (path, _) in zip(report["rows"], loaded):
            if not row["flags"] or shown >= 8:
                continue
            rel = os.path.relpath(path, ROOT)
            v = row["vkd"] or {}
            env_ = v.get("envelope") or {}
            print(f"  [{rel}] 标称 VPD {v.get('nominal_kpa')} kPa"
                  f"（{v.get('nominal_label')}）"
                  f"，包络 {env_.get('min_kpa')}–{env_.get('max_kpa')} kPa")
            for fl in row["flags"]:
                print(f"      ! {fl}")
            shown += 1
        if report["with_flags"] > shown:
            print(f"  … 另有 {report['with_flags'] - shown} 份带硬告警，略")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
