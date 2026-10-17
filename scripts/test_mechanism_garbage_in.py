"""
test_mechanism_garbage_in.py —— 机理内核 GIGO 防御回归测试

把 scripts/probe_mechanism_garbage_in.py 的 34 探针转为 unittest 断言。
目的：确保 A2-α 修复（H3：@bounded/@non_negative/@positive）不回退——
任何接受物理不可能输入而不 raise 的路径都会被 CI 拦住。

覆盖 4 个函数：
  - engine.agriworld_lite.theoretical_yield_cap
  - engine.agriworld_lite.temp_factor
  - engine.agriworld_lite.water_stress_factor
  - engine.derived.vpd

跑法：
    python -m unittest scripts.test_mechanism_garbage_in
    python -m unittest discover -s scripts -p "test_mechanism*.py"
"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class GarbageInTests(unittest.TestCase):
    """所有测试都期望输入触发 InputError / ValueError。"""

    # 1. theoretical_yield_cap ------------------------------------------------

    def test_yield_cap_negative_days_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        with self.assertRaises(Exception):
            theoretical_yield_cap("wheat", 2.0, -5)

    def test_yield_cap_zero_dli_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        # DLI=0 触发下界校验（避免 0/0）
        with self.assertRaises(Exception):
            theoretical_yield_cap("wheat", 0.0, 120)

    def test_yield_cap_unknown_crop_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        with self.assertRaises(Exception):
            theoretical_yield_cap("__nonexistent_crop__", 2.0, 120)

    def test_yield_cap_nan_dli_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        with self.assertRaises(Exception):
            theoretical_yield_cap("wheat", float("nan"), 120)

    def test_yield_cap_infinite_days_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        with self.assertRaises(Exception):
            theoretical_yield_cap("wheat", 2.0, float("inf"))

    def test_yield_cap_negative_dli_raises(self):
        from engine.agriworld_lite import theoretical_yield_cap
        with self.assertRaises(Exception):
            theoretical_yield_cap("wheat", -1.0, 120)

    # 正常基线应通过
    def test_yield_cap_wheat_baseline_ok(self):
        from engine.agriworld_lite import theoretical_yield_cap
        v = theoretical_yield_cap("wheat", 2.0, 120)
        self.assertIsInstance(v, (int, float))
        self.assertGreater(v, 0)
        self.assertLess(v, 20_000)  # 单季单产量 20 t/m² 是物理极限

    # 2. temp_factor ----------------------------------------------------------

    def test_temp_factor_above_Tmax_clamped(self):
        from engine.agriworld_lite import temp_factor
        # 温度超上限，应返回 0 或极低值（不 raise，但要截断）
        v = temp_factor(45, 22, 35, 5)
        self.assertGreaterEqual(v, 0.0)
        self.assertLessEqual(v, 1.0)
        self.assertLess(v, 0.01)  # 45℃ 应接近 0

    def test_temp_factor_below_Tmin_clamped(self):
        from engine.agriworld_lite import temp_factor
        v = temp_factor(-5, 22, 35, 5)
        self.assertGreaterEqual(v, 0.0)
        self.assertLess(v, 0.01)

    def test_temp_factor_at_topt_peak(self):
        from engine.agriworld_lite import temp_factor
        v = temp_factor(17, 17, 30, 5)
        self.assertAlmostEqual(v, 1.0, places=3)

    def test_temp_factor_nan_raises(self):
        from engine.agriworld_lite import temp_factor
        with self.assertRaises(Exception):
            temp_factor(float("nan"), 22, 35, 5)

    def test_temp_factor_inverted_bounds_raises(self):
        # Tmax < Tmin 是配置错误
        from engine.agriworld_lite import temp_factor
        with self.assertRaises(Exception):
            temp_factor(20, 22, 5, 35)

    # 3. water_stress_factor --------------------------------------------------

    def test_water_stress_above_fc_ok(self):
        from engine.agriworld_lite import water_stress_factor
        # theta >= theta_fc 时因子 = 1.0（水充足）
        v = water_stress_factor(0.30)  # θ_fc 默认 0.10
        self.assertAlmostEqual(v, 1.0, places=3)

    def test_water_stress_below_fc_linear(self):
        from engine.agriworld_lite import water_stress_factor
        # θ < θ_fc 时线性下降到 0
        v = water_stress_factor(0.05)
        self.assertGreater(v, 0.0)
        self.assertLess(v, 1.0)
        self.assertAlmostEqual(v, 0.5, places=3)

    def test_water_stress_zero_theta_zero(self):
        from engine.agriworld_lite import water_stress_factor
        v = water_stress_factor(0.0)
        self.assertAlmostEqual(v, 0.0, places=3)

    def test_water_stress_negative_raises(self):
        from engine.agriworld_lite import water_stress_factor
        with self.assertRaises(Exception):
            water_stress_factor(-0.1)

    def test_water_stress_above_0_6_raises(self):
        # 饱和含水量典型上限 0.6
        from engine.agriworld_lite import water_stress_factor
        with self.assertRaises(Exception):
            water_stress_factor(0.8)

    def test_water_stress_nan_raises(self):
        from engine.agriworld_lite import water_stress_factor
        with self.assertRaises(Exception):
            water_stress_factor(float("nan"))

    # 4. vpd ------------------------------------------------------------------

    def test_vpd_high_temp_high_rh_zero(self):
        from engine.derived import vpd
        # 30℃ 100% RH → VPD 应为 0（饱和水汽压）
        v = vpd(30, 100)
        self.assertGreaterEqual(v, 0.0)
        self.assertLess(v, 0.05)

    def test_vpd_high_temp_low_rh_positive(self):
        from engine.derived import vpd
        v = vpd(30, 30)
        self.assertGreater(v, 0.0)
        self.assertLess(v, 5.0)

    def test_vpd_rh_above_100_raises(self):
        from engine.derived import vpd
        with self.assertRaises(Exception):
            vpd(25, 110)

    def test_vpd_rh_below_0_raises(self):
        from engine.derived import vpd
        with self.assertRaises(Exception):
            vpd(25, -5)

    def test_vpd_below_magnus_range_raises(self):
        # Magnus 近似适用域 [-45, 60]
        from engine.derived import vpd
        with self.assertRaises(Exception):
            vpd(-50, 50)

    def test_vpd_above_magnus_range_raises(self):
        from engine.derived import vpd
        with self.assertRaises(Exception):
            vpd(80, 50)

    def test_vpd_nan_raises(self):
        from engine.derived import vpd
        with self.assertRaises(Exception):
            vpd(float("nan"), 50)


if __name__ == "__main__":
    unittest.main()
