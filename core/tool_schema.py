"""core/tool_schema.py —— MCP 工具参数 JSON Schema 校验器（FOUNDATION_AUDIT H5）

设计动机
--------
MCP 是对外暴露层，等于 Web API。10 个 `_tool_*` handler 原本裸奔，
用户传 `-30°C`、`days=-5`、`crop='quantum_plant'` 会静默进入机理层，
产出看似合理但完全错误的种植计划。

本模块提供零依赖最小 JSON Schema 校验器（<150 行）：
- 支持 `type` / `required` / `minimum` / `maximum` / `enum` / `items`
- 返回错误列表，空列表 = 通过
- 纯标准库，与项目零依赖理念一致

用法示例
--------
    from core.tool_schema import validate

    schema = {
        "type": "object",
        "required": ["lat", "lon"],
        "properties": {
            "lat": {"type": "number", "minimum": -90, "maximum": 90},
            "lon": {"type": "number", "minimum": -180, "maximum": 180},
        },
    }
    errs = validate(schema, {"lat": 30, "lon": 120})  # [] 通过
    errs = validate(schema, {"lat": 200, "lon": 120})  # ['lat: out of range']
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 类型判定
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


def _type_ok(value: Any, t: str) -> bool:
    """判定 value 是否符合类型 t。"""
    if t == "number":
        # number 包括 int 和 float，但不包括 bool（bool 是 int 子类）
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPE_MAP.get(t, ()))


# ---------------------------------------------------------------------------
# 核心校验
# ---------------------------------------------------------------------------

def validate(schema: dict, value: Any) -> list[str]:
    """
    校验 value 是否符合 schema。返回错误列表（空 = 通过）。

    支持的 schema 字段：
        type       类型检查
        required   必填字段列表（仅 object）
        properties 字段 schema（仅 object）
        minimum    最小值（number）
        maximum    最大值（number）
        enum       枚举列表
        items      数组元素 schema（仅 array）
        minItems   数组最小长度
        maxItems   数组最大长度
        nullable   是否允许 null（true 时跳过类型检查）
    """
    errs = []

    # nullable: null 检查
    if value is None:
        if schema.get("nullable"):
            return errs
        if schema.get("type") not in (None, "null"):
            return [f"expected {schema.get('type')}, got null"]
        return errs

    # 类型检查
    t = schema.get("type")
    if t:
        if not _type_ok(value, t):
            return [f"type mismatch: expected {t}, got {type(value).__name__}"]

    # 数值范围
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"value={value} below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"value={value} above maximum {schema['maximum']}")

    # 枚举
    if "enum" in schema and value not in schema["enum"]:
        sample = schema["enum"][:8]
        more = len(schema["enum"]) - len(sample)
        suffix = f", +{more} more" if more > 0 else ""
        errs.append(f"value={value!r} not in enum {sample}{suffix}")

    # 对象：required + properties
    if isinstance(value, dict):
        # required 字段
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"missing required field: {k}")

        # 字段 schema
        props = schema.get("properties", {})
        for k, sub_schema in props.items():
            if k in value:
                sub_errs = validate(sub_schema, value[k])
                for e in sub_errs:
                    errs.append(f"{k}: {e}")

    # 数组：items + minItems + maxItems
    if isinstance(value, list):
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(value):
                item_errs = validate(items_schema, item)
                for e in item_errs:
                    errs.append(f"[{i}]: {e}")

        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"array length {len(value)} below minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"array length {len(value)} above maxItems {schema['maxItems']}")

    return errs


def validate_tool_args(tool_name: str, schema: dict, args: dict) -> list[str]:
    """
    工具参数校验的便捷封装。

    参数：
        tool_name  工具名（用于错误消息前缀）
        schema     JSON Schema 字典
        args       实际传入的参数

    返回：
        错误列表（空 = 通过）
    """
    errs = validate(schema, args)
    if errs:
        # 给错误加上工具名前缀，便于定位
        return [f"{tool_name}: {e}" for e in errs]
    return []


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 1. 基本类型校验
    assert validate({"type": "string"}, "hello") == []
    assert validate({"type": "number"}, 42) == []
    assert validate({"type": "number"}, 42.5) == []
    assert validate({"type": "integer"}, 42) == []
    assert validate({"type": "boolean"}, True) == []
    assert validate({"type": "array"}, [1, 2, 3]) == []
    assert validate({"type": "object"}, {"a": 1}) == []
    assert validate({"type": "null"}, None) == []

    # 类型不匹配
    assert validate({"type": "string"}, 42) == ["type mismatch: expected string, got int"]
    assert validate({"type": "number"}, "abc") == ["type mismatch: expected number, got str"]
    assert validate({"type": "integer"}, 42.5) == ["type mismatch: expected integer, got float"]
    print("✓ 1. 类型校验")

    # 2. 数值范围
    schema = {"type": "number", "minimum": 0, "maximum": 100}
    assert validate(schema, 50) == []
    assert validate(schema, -1) == ["value=-1 below minimum 0"]
    assert validate(schema, 101) == ["value=101 above maximum 100"]
    print("✓ 2. 数值范围")

    # 3. 枚举
    schema = {"enum": ["a", "b", "c"]}
    assert validate(schema, "a") == []
    assert validate(schema, "d") == ["value='d' not in enum ['a', 'b', 'c']"]
    print("✓ 3. 枚举")

    # 4. 对象 required
    schema = {"type": "object", "required": ["a", "b"]}
    assert validate(schema, {"a": 1, "b": 2}) == []
    assert validate(schema, {"a": 1}) == ["missing required field: b"]
    print("✓ 4. 对象 required")

    # 5. 对象 properties 递归
    schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "minimum": -90, "maximum": 90},
            "lon": {"type": "number", "minimum": -180, "maximum": 180},
        },
    }
    assert validate(schema, {"lat": 30, "lon": 120}) == []
    errs = validate(schema, {"lat": 200, "lon": 120})
    assert "lat: value=200 above maximum 90" in errs
    print("✓ 5. 对象 properties 递归")

    # 6. 数组 items
    schema = {"type": "array", "items": {"type": "integer", "minimum": 1}}
    assert validate(schema, [1, 2, 3]) == []
    errs = validate(schema, [1, -1, 3])
    assert "[1]: value=-1 below minimum 1" in errs
    print("✓ 6. 数组 items")

    # 7. 数组长度
    schema = {"type": "array", "minItems": 2, "maxItems": 4}
    assert validate(schema, [1, 2]) == []
    assert validate(schema, [1]) == ["array length 1 below minItems 2"]
    assert validate(schema, [1, 2, 3, 4, 5]) == ["array length 5 above maxItems 4"]
    print("✓ 7. 数组长度")

    # 8. nullable
    schema = {"type": "number", "nullable": True}
    assert validate(schema, None) == []
    assert validate(schema, 42) == []
    assert validate({"type": "number"}, None) == ["expected number, got null"]
    print("✓ 8. nullable")

    # 9. validate_tool_args 封装
    errs = validate_tool_args("test_tool", {"type": "object", "required": ["x"]}, {})
    assert "test_tool: missing required field: x" in errs
    print("✓ 9. validate_tool_args 封装")

    # 10. bool 不是 integer
    assert validate({"type": "integer"}, True) == ["type mismatch: expected integer, got bool"]
    assert validate({"type": "number"}, True) == ["type mismatch: expected number, got bool"]
    print("✓ 10. bool 排除在 integer/number 外")

    print("\nJSON Schema 校验器全部 10 项自测通过。")
