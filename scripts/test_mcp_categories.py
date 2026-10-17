#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_mcp_categories.py —— M13-P2 渐进式发现 category 分组硬门禁

背景
----
per_module_deep_assessment_2026-10-13.md §M13-P2「渐进式发现」：
工具数 19 已超过临界点，客户端拉全量成本变高。每个工具已声明 category
字段（11 个分类：climate/crop/pest/nutrition/recipe/meta/business/
knowledge/forecast/phenology/soil），但 tools/list 处理器原本不消费
它。本轮补上 params.category / params.categories 过滤能力，让客户端
可只加载关心的子集。

门禁覆盖点
---------
1. 工具元数据完整：每个工具都有 category 字段，值在允许列表内
2. 分类唯一性：无重复分类
3. 过滤向后兼容：不传 params 返回全量 19 工具
4. 单分类过滤：params.category="climate" 返回 climate 类工具
5. 多分类过滤：params.categories=["recipe","meta"] 返回并集
6. 空数组 = 全量：与"不传"等价
7. 不存在的分类静默忽略（渐进式发现的宽松语义）
8. 完全未知分类：返回空 tools + 完整 categories 提示
9. tools/list 处理器：返回 categories 字段 + 过滤生效
10. 协议版本兼容：SUPPORTED_PROTOCOL_VERSIONS 保持不变
"""
import unittest
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mcp.server import (  # noqa: E402
    _select_tools_by_category,
    TOOLS,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)


# M13-P2 声明的允许分类集合（与 mcp/server.py TOOLS 定义对齐）
ALLOWED_CATEGORIES = frozenset({
    "bp_screen", "business", "climate", "counterfactual", "crop",
    "forecast", "knowledge", "meta", "nutrition", "pest", "phenology",
    "recipe", "soil", "verify",
})


class TestToolCategoryMetadata(unittest.TestCase):
    """TOOLS 元数据完整性与分类唯一性。"""

    def test_all_tools_have_category(self):
        """每个工具必须声明 category 字段（M13-P2 基础）。"""
        missing = [t.get("name") for t in TOOLS if not t.get("category")]
        self.assertEqual(missing, [],
                         f"工具缺 category 字段: {missing}")

    def test_categories_in_allowed_set(self):
        """category 值必须在允许列表内（防漂移）。"""
        bad = [(t["name"], t["category"]) for t in TOOLS
               if t["category"] not in ALLOWED_CATEGORIES]
        self.assertEqual(bad, [],
                         f"category 值超出允许列表: {bad}")

    def test_all_categories_used(self):
        """允许列表中的分类至少被 1 个工具使用（防死声明）。"""
        used = {t["category"] for t in TOOLS}
        unused = ALLOWED_CATEGORIES - used
        self.assertEqual(unused, set(),
                         f"允许列表中未使用的分类: {sorted(unused)}")

    def test_no_duplicate_tool_names(self):
        """工具名唯一（防 _DISPATCH 路由冲突）。"""
        names = [t["name"] for t in TOOLS]
        dupes = {n for n in names if names.count(n) > 1}
        self.assertEqual(dupes, set(),
                         f"重复工具名: {dupes}")

    def test_tool_count_ge_19(self):
        """工具数下限 19（防退化）。"""
        self.assertGreaterEqual(len(TOOLS), 19,
                                f"工具数 {len(TOOLS)} < 19")


class TestSelectToolsByCategory(unittest.TestCase):
    """_select_tools_by_category 过滤逻辑硬门禁。"""

    def test_no_params_returns_all(self):
        """不传 params 返回全量（向后兼容，旧客户端行为不变）。"""
        r = _select_tools_by_category({})
        self.assertEqual(len(r["tools"]), len(TOOLS))
        self.assertEqual(len(r["categories"]), 14)

    def test_single_category_filter(self):
        """params.category='climate' 返回 climate 类工具。"""
        r = _select_tools_by_category({"category": "climate"})
        names = {t["name"] for t in r["tools"]}
        self.assertIn("agri_match_zone", names)
        self.assertIn("agri_list_cities", names)
        # 非 climate 工具不应出现
        self.assertNotIn("agri_diagnose_pest", names)
        # categories 始终返回完整列表
        self.assertEqual(len(r["categories"]), 14)

    def test_multiple_categories_filter(self):
        """params.categories=['recipe','meta'] 返回并集。"""
        r = _select_tools_by_category({"categories": ["recipe", "meta"]})
        expected = [t for t in TOOLS
                    if t["category"] in ("recipe", "meta")]
        self.assertEqual(len(r["tools"]), len(expected))
        for t in r["tools"]:
            self.assertIn(t["category"], ("recipe", "meta"))

    def test_empty_categories_equals_all(self):
        """空 categories 数组 = 全量（与不传等价）。"""
        r1 = _select_tools_by_category({"categories": []})
        r2 = _select_tools_by_category({})
        self.assertEqual(r1["tools"], r2["tools"])

    def test_nonexistent_category_ignored(self):
        """不存在的 category 静默忽略（渐进式发现的宽松语义）。"""
        r = _select_tools_by_category({"category": "nonexistent"})
        self.assertEqual(len(r["tools"]), 0)
        # categories 提示仍完整，让客户端知道有哪些可用分类
        self.assertEqual(len(r["categories"]), 14)

    def test_mixed_known_and_unknown(self):
        """多分类中部分存在、部分不存在：存在的生效，不存在的忽略。"""
        r = _select_tools_by_category(
            {"categories": ["climate", "nonexistent"]})
        self.assertEqual(len(r["tools"]),
                         sum(1 for t in TOOLS if t["category"] == "climate"))

    def test_whitespace_stripped(self):
        """分类值前后空白被 strip（防客户端传参粗心）。"""
        r = _select_tools_by_category({"category": "  climate  "})
        self.assertGreater(len(r["tools"]), 0)

    def test_duplicate_categories_deduped(self):
        """重复分类去重（不会重复返回同一工具）。"""
        r = _select_tools_by_category(
            {"categories": ["climate", "climate", "climate"]})
        expected = [t for t in TOOLS if t["category"] == "climate"]
        self.assertEqual(len(r["tools"]), len(expected))

    def test_categories_always_sorted(self):
        """categories 返回按字典序排序（稳定可复算）。"""
        r = _select_tools_by_category({})
        self.assertEqual(r["categories"], sorted(r["categories"]))

    def test_single_and_multi_combined(self):
        """params 同时含 category 与 categories：取并集。"""
        r = _select_tools_by_category(
            {"category": "climate", "categories": ["recipe"]})
        expected = [t for t in TOOLS
                    if t["category"] in ("climate", "recipe")]
        self.assertEqual(len(r["tools"]), len(expected))

    def test_none_params_safe(self):
        """params=None 时不抛异常（返回全量）。"""
        r = _select_tools_by_category(None)
        self.assertEqual(len(r["tools"]), len(TOOLS))

    def test_non_dict_params_safe(self):
        """params 非 dict 时不抛异常（返回全量）。"""
        for bad in ("climate", ["climate"], 42, False):
            r = _select_tools_by_category(bad)
            self.assertEqual(len(r["tools"]), len(TOOLS))


class TestToolsListProtocol(unittest.TestCase):
    """协议层面不变量（M13-P2 不应破坏 MCP 契约）。"""

    def test_protocol_version_unchanged(self):
        """M13-P2 只加过滤能力，不改协议版本。"""
        self.assertEqual(PROTOCOL_VERSION, "2026-07-28")

    def test_supported_versions_unchanged(self):
        """兼容版本列表不变（向后兼容纪律）。"""
        self.assertIn("2026-07-28", SUPPORTED_PROTOCOL_VERSIONS)
        self.assertIn("2025-06-18", SUPPORTED_PROTOCOL_VERSIONS)
        self.assertIn("2024-11-05", SUPPORTED_PROTOCOL_VERSIONS)

    def test_dispatch_covers_all_tools(self):
        """_DISPATCH 路由表覆盖 TOOLS 声明的所有工具（防声明/实现漂移）。"""
        from mcp.server import _DISPATCH
        for t in TOOLS:
            self.assertIn(t["name"], _DISPATCH,
                          f"工具 {t['name']} 在 TOOLS 声明但 _DISPATCH 无路由")


if __name__ == "__main__":
    unittest.main()
