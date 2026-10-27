#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
validate_grow_batch.py · grow_batch.schema.json 迷你校验器

背景（§九 P0 工作包 · 批次对象 MVP，2026-10-27）：
    schemas/grow_batch.schema.json 定义 Plot / GrowBatch / Observation /
    Action / Outcome 五类对象（oneOf 分派 + $defs 引用 + EvidenceGrade
    E0-E4）。本校验器复用 validate_env_recipe.py 的迷你 JSON Schema
    校验模式（纯 stdlib，零依赖），并增加 $ref / oneOf 支持。

功能：
    1. 校验 schema 自身语法合法（oneOf 5 类 + $defs 齐全）
    2. 校验 5 类样本 required 字段齐全（合法样本应 0 错误）
    3. 反例测试：缺 required 字段应被捕获（证明校验器有效）
    4. 按 discriminator（plot_id/batch_id/observation_id/action_id/outcome_id）
       分派到对应 $defs 校验

CLI：
    python scripts/validate_grow_batch.py            # 自测（样本 + 反例）
    python scripts/validate_grow_batch.py --json     # JSON 输出

退出码：
    0 = PASS（schema 合法 + 样本通过 + 反例被捕获）
    1 = FAIL
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "grow_batch.schema.json"

# 五类对象判别：按特异度优先。注意 plot_id / batch_id 也是外键
# （GrowBatch 引用 plot_id；Observation/Action/Outcome 引用 batch_id），
# 所以不能按"字段存在"唯一判别——必须按最特异的 id 字段优先。
def _classify(obj: dict) -> str | None:
    if "observation_id" in obj:
        return "Observation"
    if "action_id" in obj:
        return "Action"
    if "outcome_id" in obj:
        return "Outcome"
    if "batch_id" in obj:
        return "GrowBatch"
    if "plot_id" in obj:
        return "Plot"
    return None


def _resolve(ref: str, defs: dict) -> dict:
    """解析 '#/$defs/X' 引用。"""
    if not ref.startswith("#/$defs/"):
        raise ValueError(f"不支持的 $ref: {ref}")
    name = ref.split("/")[-1]
    if name not in defs:
        raise ValueError(f"$defs 缺 {name!r}")
    return defs[name]


def _type_ok(node, typ: str) -> bool:
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
    if typ == "null":
        return node is None
    return True


def _validate(node, schema, defs, path, errors):
    """迷你 JSON Schema 校验（支持 $ref / type / enum / const / required /
    properties / additionalProperties / items / minimum / maximum）。"""
    # $ref 解析
    if "$ref" in schema:
        _validate(node, _resolve(schema["$ref"], defs), defs, path, errors)
        return
    # const
    if "const" in schema and node != schema["const"]:
        errors.append(f"{path}: 期望 const={schema['const']!r}，实际 {node!r}")
        return
    # enum
    if "enum" in schema and node not in schema["enum"]:
        errors.append(f"{path}: 值 {node!r} 不在允许枚举 {schema['enum']}")
    # type
    typ = schema.get("type")
    if typ:
        if isinstance(typ, list):
            if not any(_type_ok(node, t) for t in typ):
                errors.append(f"{path}: 期望类型之一 {typ}，实际 {type(node).__name__}")
                return
        elif not _type_ok(node, typ):
            errors.append(f"{path}: 期望类型 {typ}，实际 {type(node).__name__}")
            return
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
                _validate(v, props[k], defs, f"{path}.{k}", errors)
            else:
                if schema.get("additionalProperties") is False:
                    errors.append(f"{path}: 不允许的额外字段 {k!r}")
    # array items
    if isinstance(node, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, it in enumerate(node):
                _validate(it, item_schema, defs, f"{path}[{i}]", errors)


def validate_instance(instance: dict, defs: dict) -> list:
    """按特异度判别对象类型，校验对应 $defs，返回错误列表。"""
    errors: list = []
    cls = _classify(instance)
    if cls is None:
        return ["$: 无法判别对象类型（需含 observation_id/action_id/"
                "outcome_id/batch_id/plot_id 之一）"]
    _validate(instance, defs[cls], defs, "$", errors)
    return errors


# ---------- 样本与反例 ----------

_SAMPLES = {
    "Plot": {"plot_id": "plot-001", "location_type": "balcony"},
    "GrowBatch": {
        "batch_id": "batch-001", "crop": "生菜", "plot_id": "plot-001",
        "recipe_version": "v1.2.0", "started_at": "2026-10-26T00:00:00Z",
    },
    "Observation": {
        "observation_id": "obs-001", "batch_id": "batch-001",
        "ts": "2026-10-26T12:00:00Z", "metric": "temperature_c",
        "source": {"kind": "sensor"},
    },
    "Action": {
        "action_id": "act-001", "batch_id": "batch-001",
        "ts": "2026-10-26T12:00:00Z", "recommendation": "启动滴灌",
        "status": "shadow",
    },
    "Outcome": {
        "outcome_id": "out-001", "batch_id": "batch-001",
        "ts": "2026-11-05T00:00:00Z",
    },
}

# 反例：各缺一个必填字段
_NEGATIVE = [
    ("Plot 缺 plot_id", {"location_type": "balcony"}),
    ("GrowBatch 缺 crop", {"batch_id": "b1", "plot_id": "p1", "recipe_version": "v1", "started_at": "t"}),
    ("Observation 缺 source", {"observation_id": "o1", "batch_id": "b1", "ts": "t", "metric": "m"}),
    ("Action 缺 status", {"action_id": "a1", "batch_id": "b1", "ts": "t", "recommendation": "r"}),
    ("Outcome 缺 ts", {"outcome_id": "o1", "batch_id": "b1"}),
]


def _check_schema(schema: dict) -> list:
    """校验 schema 自身结构。"""
    errors: list = []
    defs = schema.get("$defs", {})
    if len(schema.get("oneOf", [])) != 5:
        errors.append(f"oneOf 应为 5 类，实际 {len(schema.get('oneOf', []))}")
    for name in ("Plot", "GrowBatch", "Observation", "Action", "Outcome"):
        if name not in defs:
            errors.append(f"$defs 缺 {name}")
    if "EvidenceGrade" not in defs:
        errors.append("$defs 缺 EvidenceGrade")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="grow_batch schema 迷你校验器")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"status": "FAIL", "error": f"schema 读取失败: {e}"}) if args.json
              else f"❌ schema 读取失败: {e}")
        return 1

    defs = schema.get("$defs", {})
    schema_errors = _check_schema(schema)

    # 1) 合法样本校验
    sample_errors: dict = {}
    for cls, sample in _SAMPLES.items():
        errs = validate_instance(sample, defs)
        if errs:
            sample_errors[cls] = errs

    # 2) 反例校验（应捕获缺失）
    neg_caught = 0
    neg_missed = []
    for label, bad in _NEGATIVE:
        errs = validate_instance(bad, defs)
        if errs:
            neg_caught += 1
        else:
            neg_missed.append(label)

    ok = (not schema_errors) and (not sample_errors) and (neg_caught == len(_NEGATIVE))

    result = {
        "status": "PASS" if ok else "FAIL",
        "schema_errors": schema_errors,
        "sample_errors": sample_errors,
        "negative_caught": neg_caught,
        "negative_total": len(_NEGATIVE),
        "negative_missed": neg_missed,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"grow_batch.schema.json 自测：{'✅ PASS' if ok else '❌ FAIL'}")
        print(f"  schema 自身: {'✅' if not schema_errors else '❌ ' + str(schema_errors)}")
        print(f"  5 类样本: {'✅' if not sample_errors else '❌ ' + str(sample_errors)}")
        print(f"  反例捕获: {neg_caught}/{len(_NEGATIVE)}"
              + ("" if not neg_missed else f"  ❌ 漏检 {neg_missed}"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
