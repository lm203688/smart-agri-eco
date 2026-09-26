# -*- coding: utf-8 -*-
"""L4 缺口检测：三级分类 + 人话版补数清单"""
from .rules import GAP_LEVELS, SUPPLEMENT_HINTS


def detect(normalized: dict, category: str) -> dict:
    """
    返回 {level: {field: hint}}, 汇总 critical/normal 命中情况
    level: fatal（阻断结论）/ critical（拉宽区间）/ normal（报告标注）
    """
    result = {"fatal": {}, "critical": {}, "normal": {}}
    for level in ["fatal", "critical", "normal"]:
        for f in GAP_LEVELS.get(level, {"fields": []})["fields"]:
            if normalized.get(f) is None:
                hint = SUPPLEMENT_HINTS.get(f, f"请补充提供「{f}」相关资料")
                # 分类适配：非养殖/种业类不要求出栏量等
                result[level][f] = hint
    return result


def supplement_list(gaps: dict) -> list:
    """生成给用户的待补清单（按优先级排序，人话版）"""
    items = []
    for level, fields in [("fatal", gaps.get("fatal", {})), ("critical", gaps.get("critical", {})), ("normal", gaps.get("normal", {}))]:
        for f, hint in fields.items():
            items.append({"field": f, "level": level, "hint": hint,
                          "level_name": {"fatal": "致命缺（无法给出结论）", "critical": "重要缺（影响评分精度）", "normal": "一般缺（报告将标注）"}[level]})
    return items


def missing_fields(normalized: dict, category: str) -> list:
    g = detect(normalized, category)
    return list(g["fatal"].keys()) + list(g["critical"].keys()) + list(g["normal"].keys())
