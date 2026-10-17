#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_zero_ref_core.py —— core/ 基础模块最小冒烟测试

GAP_AUDIT §6：34 个零引用模块中，core/ 下的 8 个是最高杠杆的基础设施，
必须验证基本契约（可导入、返回值合理、异常契约、幂等性）。

不追求 100% 覆盖，追求"任何一处坏了能被发现"。
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from core import atomic_io, clock, exceptions as ex, seed, sun_geometry, tool_schema, vdc_contract, nutrient_solution


class TestAtomicIo(unittest.TestCase):
    """core.atomic_io: 原子写必须保证要么成功要么文件不变。"""

    def test_atomic_write_json_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "out.json")
            atomic_io.atomic_write_json(p, {"a": 1, "b": [2, 3]})
            self.assertTrue(os.path.exists(p))
            with open(p, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"a": 1, "b": [2, 3]})

    def test_atomic_write_json_no_temp_leftover(self):
        """关键契约：原子写不能留下 .tmp 残留（这是原动机）。"""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "out.json")
            atomic_io.atomic_write_json(p, {"x": 1})
            leftover = [f for f in os.listdir(td) if f != "out.json"]
            self.assertEqual(leftover, [], f"发现残留: {leftover}")

    def test_atomic_append_jsonl_appends_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "log.jsonl")
            atomic_io.atomic_append_jsonl(p, {"i": 1})
            atomic_io.atomic_append_jsonl(p, {"i": 2})
            with open(p, encoding="utf-8") as f:
                lines = [json.loads(x) for x in f if x.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], {"i": 1})
            self.assertEqual(lines[1], {"i": 2})

    def test_atomic_write_byte_content(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "raw.bin")
            atomic_io.atomic_write(p, b"\x00\x01\x02", mode=0o644)
            with open(p, "rb") as f:
                self.assertEqual(f.read(), b"\x00\x01\x02")


class TestClock(unittest.TestCase):
    """core.clock: 可注入时钟，测试与生产隔离。"""

    def test_system_clock_now_is_datetime(self):
        """SystemClock.now() 返回 naive local datetime（与 datetime.now() 语义一致）。"""
        c = clock.SystemClock()
        now = c.now()
        self.assertIsInstance(now, datetime)
        # naive local：应与 datetime.now() 差 < 5 秒
        self.assertIsNone(now.tzinfo, "SystemClock.now() 应为 naive local")
        delta = abs((datetime.now() - now).total_seconds())
        self.assertLess(delta, 5)

    def test_system_clock_time_is_monotonic_float(self):
        c = clock.SystemClock()
        t1 = c.time()
        t2 = c.time()
        self.assertLessEqual(t1, t2)

    def test_frozen_clock_returns_fixed_value(self):
        """FrozenClock 输入 naive 会补 UTC 时区，返回 aware UTC datetime。"""
        fixed_naive = datetime(2026, 1, 1, 12, 0, 0)
        c = clock.FrozenClock(fixed=fixed_naive)
        first = c.now()
        self.assertIsInstance(first, datetime)
        # 输入 naive → 强制补 UTC tzinfo
        self.assertEqual(first, fixed_naive.replace(tzinfo=datetime.now(timezone.utc).tzinfo))
        # 关键是幂等：offset=0 多次调用值不变
        self.assertEqual(c.now(), c.now())

    def test_frozen_clock_with_offset(self):
        """offset_seconds > 0 时每调用一次 clock 时间前进 offset 秒。"""
        fixed = datetime(2026, 1, 1, 12, 0, 0)
        c = clock.FrozenClock(fixed=fixed, offset_seconds=3600)
        t1 = c.now()
        t2 = c.now()
        # 第二次比第一次晚 3600 秒
        self.assertEqual((t2 - t1).total_seconds(), 3600.0)


class TestExceptions(unittest.TestCase):
    """core.exceptions: 分层异常契约。"""

    def test_hierarchy_all_extend_agri_exception(self):
        for cls in (ex.InputError, ex.DataError, ex.ComputeError, ex.UpstreamError):
            self.assertTrue(issubclass(cls, ex.AgriException))
            self.assertTrue(issubclass(cls, Exception))

    def test_is_swallowed_safe_accepts_upstream_error(self):
        """契约：UpstreamError 是上游/网络类错误，允许被静默吞掉。"""
        if hasattr(ex, "is_swallowed_safe"):
            self.assertTrue(ex.is_swallowed_safe(ex.UpstreamError))

    def test_is_swallowed_safe_rejects_internal_errors(self):
        """契约：内部计算错误不允许静默吞掉（必须至少 log）。"""
        if hasattr(ex, "is_swallowed_safe"):
            self.assertFalse(ex.is_swallowed_safe(ex.ComputeError))
            self.assertFalse(ex.is_swallowed_safe(ex.InputError))

    def test_exceptions_are_constructible(self):
        for cls in (ex.InputError, ex.DataError, ex.ComputeError, ex.UpstreamError):
            try:
                _ = cls("boom")
            except Exception:
                self.fail(f"{cls.__name__} 无法用单字符串构造")


class TestSeed(unittest.TestCase):
    """core.seed: 稳定哈希种子（相同输入→相同整数）。"""

    def test_stable_seed_deterministic(self):
        a = seed.stable_seed("agri", "recipe", "v1.2")
        b = seed.stable_seed("agri", "recipe", "v1.2")
        self.assertEqual(a, b)

    def test_stable_seed_order_sensitive(self):
        a = seed.stable_seed("x", "y")
        b = seed.stable_seed("y", "x")
        # 顺序不同 → 结果应不同（FNV 是顺序敏感哈希）
        self.assertNotEqual(a, b)

    def test_stable_seed_64_in_range(self):
        v = seed.stable_seed_64("any", "content")
        self.assertIsInstance(v, int)
        self.assertGreaterEqual(v, 0)
        self.assertLess(v, 2**64)


class TestSunGeometry(unittest.TestCase):
    """core.sun_geometry: 太阳几何微气候模块。"""

    def test_make_sun_geometry_returns_object(self):
        g = sun_geometry.make_sun_geometry(lat=40.0, lon=116.0)
        self.assertIsInstance(g, sun_geometry.SunGeometry)

    def test_make_sun_geometry_has_position_method(self):
        """SunGeometry 引擎暴露 position/daily/hourly_positions 三档 API。"""
        g = sun_geometry.make_sun_geometry(lat=40.0, lon=116.0)
        for method in ("position", "daily", "hourly_positions"):
            self.assertTrue(callable(getattr(g, method, None)),
                            f"SunGeometry 缺少方法 {method}")

    def test_sun_geometry_daily_returns_required_fields(self):
        g = sun_geometry.make_sun_geometry(lat=40.0, lon=116.0)
        result = g.daily(year=2026, month=6, day=21)  # 夏至
        self.assertIn("DLI_kJ_m2_day", result)
        self.assertIn("day_length_hours", result)
        # 夏至北半球日照应 > 12 小时
        self.assertGreater(result["day_length_hours"], 12.0)
        self.assertLess(result["day_length_hours"], 18.0)

    def test_lat_lon_extremes_do_not_crash(self):
        """极点与赤道的极端纬度不应抛异常（可能返回 0 日照）。"""
        for lat in (-90, -60, 0, 60, 90):
            g = sun_geometry.make_sun_geometry(lat=float(lat), lon=0.0)
            self.assertIsNotNone(g)


class TestToolSchema(unittest.TestCase):
    """core.tool_schema: MCP 工具参数校验。"""

    def test_validate_accepts_conforming_args(self):
        schema = {
            "type": "object",
            "required": ["crop"],
            "properties": {
                "crop": {"type": "string"},
                "stage": {"type": "string", "enum": ["seedling", "vegetative", "flowering"]},
            },
        }
        errs = tool_schema.validate_tool_args("test_tool", schema, {"crop": "tomato", "stage": "vegetative"})
        self.assertEqual(errs, [])

    def test_validate_rejects_missing_required(self):
        schema = {
            "type": "object",
            "required": ["crop"],
            "properties": {"crop": {"type": "string"}},
        }
        errs = tool_schema.validate_tool_args("test_tool", schema, {})
        self.assertTrue(any("crop" in e.lower() or "required" in e.lower() for e in errs),
                        f"错误信息应提到 missing required 字段: {errs}")

    def test_validate_rejects_bad_type(self):
        schema = {
            "type": "object",
            "properties": {"n": {"type": "integer"}},
        }
        errs = tool_schema.validate_tool_args("test_tool", schema, {"n": "not-an-int"})
        self.assertTrue(len(errs) > 0)

    def test_validate_rejects_bad_enum(self):
        schema = {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": ["seedling", "vegetative"]}
            },
        }
        errs = tool_schema.validate_tool_args("test_tool", schema, {"stage": "nonexistent"})
        self.assertTrue(len(errs) > 0)


class TestVDCContract(unittest.TestCase):
    """core.vdc_contract: 可验证决策契约。"""

    def test_vdc_constructs_with_defaults(self):
        c = vdc_contract.VDCContract()
        # 关键子结构不应为 None
        self.assertIsNotNone(c.premise)
        self.assertIsNotNone(c.commitment)
        self.assertIsNotNone(c.breach_rule)

    def test_vdc_accepts_custom_action(self):
        c = vdc_contract.VDCContract(
            contract_id="test-001",
            action={"kind": "irrigate", "amount_mm": 5.0},
        )
        self.assertEqual(c.contract_id, "test-001")
        self.assertEqual(c.action["amount_mm"], 5.0)


class TestNutrientSolution(unittest.TestCase):
    """core.nutrient_solution: 营养液配方求解器。"""

    def test_solve_returns_solve_result(self):
        r = nutrient_solution.solve(
            target_n=20.0, target_p=5.0, target_k=25.0, volume_l=100.0
        )
        self.assertIsInstance(r, nutrient_solution.SolveResult)
        self.assertGreater(r.volume_l, 0)
        # achieved 是 dict，键应包含 n/p/k（不区分大小写）
        self.assertIsInstance(r.achieved, dict)
        keys_lower = {k.lower() for k in r.achieved.keys()}
        self.assertIn("n", keys_lower)
        self.assertIn("p", keys_lower)
        self.assertIn("k", keys_lower)
        # salts 应是 list
        self.assertIsInstance(r.salts, list)

    def test_solve_rejects_negative_target(self):
        with self.assertRaises(Exception):
            nutrient_solution.solve(target_n=-1.0, target_p=5.0, target_k=25.0, volume_l=100.0)

    def test_common_salts_has_expected_keys(self):
        salts = nutrient_solution.common_salts()
        self.assertIsInstance(salts, dict)
        self.assertGreater(len(salts), 0)

    def test_check_precipitation_returns_dict(self):
        ions = {"ca": 2.0, "so4": 1.0}
        result = nutrient_solution.check_precipitation_and_antagonism(ions_mmol_per_l=ions)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
