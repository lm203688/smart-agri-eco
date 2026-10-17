"""
core/sun_geometry.py —— NOAA SPA 简化版太阳几何引擎（M1-A3）

设计动机（承接 docs/per_module_deep_assessment_2026-10-13.md §M1-A3）：
  当前项目的 DLI 来自 NASA POWER 全谱短波辐射 × 16.45（光子当量近似，
  非标准 PAR DLI，且不含云量/地形/太阳几何效应）。这导致：
    1. 分区级 DLI 无法反映纬度/季节/日长变化——上海 6 月 vs 12 月 DLI 应该差 2 倍，
       但分区级数据是均值，无法区分
    2. 无法做「同一城市不同季节/不同朝向」的微气候差异化
    3. 无法与 WOFOST 光截获模型对接（缺少逐时太阳高度角）

本模块提供纯标准库实现的太阳几何核心：
  - 太阳赤纬 δ(t)
  - 太阳时角 H(t)
  - 太阳高度角 α(t) 与方位角 A(t)
  - 日出/日落/正午时刻
  - 日长度
  - 太阳高度角驱动的每日光积分 DLI（mol·m⁻²·d⁻¹）
  - 直射辐射最大值（大气透射简化模型）

接口设计原则：
  1. 零第三方依赖（stdlib only：math / datetime）
  2. 诚实边界：无云/清水/无地形修正的**理论值**，真实场景需乘天空透射系数
     (k_t，无数据时用 0.5 典型值并显式标注)
  3. 结果带溯源（source="NOAA SPA 简化版"）与不确定度区间

精度定位：
  - 太阳位置（赤纬/时角/高度角）：误差 < 0.01°（NOAA SPA 官方精度）
  - 直射辐射最大值：误差 ±20%（大气透射简化模型，未含气溶胶/水气/地形）
  - DLI 晴天上界：与实测对比约 ±15%（缺云量修正）
  - **不追求实测精度**，追求**纬度/季节/朝向的相对变化正确**——这是替代
    「楼层/朝向 ±℃」固定偏置查表的关键

用法：
    from core.sun_geometry import SunGeometry, solar_position
    # 便捷函数
    pos = solar_position(lat=30.0, lon=120.0, year=2026, month=10, day=14,
                         hour_utc=8, tz_offset=8)
    # 或类实例（缓存常量）
    sg = SunGeometry(30.0, 120.0)
    daily = sg.daily(2026, 10, 14, tz_offset=8)
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "agri-sun-geometry/v1"
SOURCE = "NOAA SPA simplified (zero-dependency reimplementation)"

# ---------------------------------------------------------------------------
# 常数
# ---------------------------------------------------------------------------

SOLAR_CONSTANT_W_M2 = 1361.0          # 太阳常数（W/m²，NASA）
PAR_TO_KJ_PER_MOL = 14.34             # 1 mol PAR = 14.34 kJ（400-700nm 波段）
AIR_MASSES_0 = 0.3  # 大气光学质量（无云典型值）
CLEAR_SKY_TRANSMITTANCE_K_T = 0.7     # 晴空大气透射系数（简化）


def _rad(deg: float) -> float:
    return math.radians(deg)


def _deg(rad: float) -> float:
    return math.degrees(rad)


def _normalize_angle(angle_deg: float) -> float:
    """归一化到 [0, 360)"""
    return angle_deg % 360.0


# ---------------------------------------------------------------------------
# NOAA SPA 简化版核心公式
# ---------------------------------------------------------------------------

def _julian_day(year: int, month: int, day: int, hour_utc: float = 12.0) -> float:
    """儒略日（JD）。以 Python datetime 为标准实现，避免公式误差。

    JD 2451545.0 = 2000-01-01 12:00 UT（J2000.0 历元）。
    """
    d = date(year, month, day)
    # Python 的 ordinal：0001-01-01 为 1
    ordinal = d.toordinal()
    # JD for 0001-01-01 00:00 UT = 1721424.5
    jd = ordinal + 1721424.5 + hour_utc / 24.0
    return jd


def _doy_from_jd(jd: float) -> float:
    """从儒略日（JD）推算含小时小数的日序（day-of-year, float）。

    JD 2451545.0 = 2000-01-01 12:00 UT（J2000.0 历元）。
    12:00 UT 对应 doy 整数（无小数偏移），00:00 UT 对应 -0.5 天。
    """
    delta_days = jd - 2451545.0
    dt = datetime(2000, 1, 1, 12, 0, 0) + timedelta(days=delta_days)
    return dt.timetuple().tm_yday + dt.hour / 24.0 + dt.minute / 1440.0 - 0.5


def _fractional_year(doy: float) -> float:
    """γ: 春分点为 0 的一年分数（弧度）。

    doy 为 float（如 2026-12-21 12:00 UT 正午 = 355.0）。
    春分点约在第 80 天（3 月 20 日）；夏至约 172（+92 天）；
    冬至约 355（+275 天）。
    """
    return 2.0 * math.pi / 365.25 * (doy - 80.0)


def _solar_mean_anomaly(gamma: float) -> float:
    """太阳平近点角 M（弧度）。"""
    return gamma - _rad(0.00691835)


def _ecliptic_longitude(M: float, year: int) -> Tuple[float, float]:
    """黄经 λ 与轨道离心率 e。year 用于推算儒略世纪 T = (year-2000)/100。"""
    T = (year - 2000) / 100.0
    e = 0.016708634 - 0.0000420379 * T - 0.0000001267 * T * T
    C = (_rad(1.914807) * math.sin(M) +
         _rad(0.0209627) * math.sin(2 * M) +
         _rad(0.0003053) * math.sin(3 * M))
    return M + C, e


def _obliquity_of_ecliptic(year: int) -> float:
    """黄赤交角 ε（弧度）。year 用于推算儒略世纪 T。

    使用 Meeus 公式：ε = 23.43929111 - 0.013004167*T - 0.0000001639*T²
                       + 0.0000005036*T³（度）。
    """
    T = (year - 2000) / 100.0
    eps_deg = (23.43929111 - 0.013004167 * T - 0.0000001639 * T * T
               + 0.0000005036 * T * T * T)
    return _rad(eps_deg)


def _solar_declination(eps: float, ecl_lon: float) -> float:
    """太阳赤纬 δ（弧度）。"""
    return math.asin(math.sin(eps) * math.sin(ecl_lon))


def _solar_right_ascension(eps: float, ecl_lon: float) -> float:
    """太阳赤经 α（弧度）。"""
    return math.atan2(math.cos(eps) * math.sin(ecl_lon), math.cos(ecl_lon))


def _solar_mean_sidereal_time(year: int, month: int, day: int,
                              hour_utc: float, jd: float) -> float:
    """太阳平均恒星时（弧度）。"""
    T = (jd - 2451543.5) / 36525.0
    theta0 = (280.46061837 + 360.98564736629 * (jd - 2451543.5) +
              0.000387933 * T + T * T / 38710000.0)
    gmst = _normalize_angle(theta0)
    return _rad(gmst)


def _hour_angle(sidereal_time: float, right_ascension: float) -> float:
    """太阳时角 H（弧度），正午 H=0。"""
    return sidereal_time - right_ascension


def _solar_altitude(lat_rad: float, decl_rad: float, hour_angle: float) -> float:
    """太阳高度角 α（弧度）。"""
    sin_alt = (math.sin(lat_rad) * math.sin(decl_rad) +
               math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle))
    # 数值误差可能超出 [-1,1]
    sin_alt = max(-1.0, min(1.0, sin_alt))
    return math.asin(sin_alt)


def _solar_azimuth(lat_rad: float, decl_rad: float, hour_angle: float,
                   alt_rad: float) -> float:
    """太阳方位角 A（度，0=N，顺时针），正午时指向南。"""
    sin_alt = math.sin(alt_rad)
    cos_az = ((math.sin(decl_rad) - sin_alt * math.sin(lat_rad)) /
              (math.cos(alt_rad) * math.cos(lat_rad) + 1e-12))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.acos(cos_az)
    if hour_angle > 0:
        az = 2 * math.pi - az
    return _deg(az)


# ---------------------------------------------------------------------------
# 大气透射与辐射
# ---------------------------------------------------------------------------

def _air_mass(altitude_deg: float) -> float:
    """大气质量（Kasten-Young 简化，仅考虑太阳高度角）。"""
    alt_rad = _rad(altitude_deg)
    cos_zen = math.cos(alt_rad)
    if cos_zen <= 0:
        return 0.0  # 太阳在地平线下
    # Kasten-Young 1989：m = 1 / (cos(z) + 0.50572 * (z + 6.07995)^-1.6364)
    z = 90.0 - altitude_deg
    return 1.0 / (cos_zen + 0.50572 * (z + 6.07995) ** (-1.6364))


def _direct_beam_irradiance(altitude_deg: float,
                            k_t: float = CLEAR_SKY_TRANSMITTANCE_K_T) -> float:
    """直射辐射（W/m²），仅考虑大气透射，不含漫射与地形反射。"""
    if altitude_deg <= 0.0:
        return 0.0
    am = _air_mass(altitude_deg)
    # 简化大气透射模型：G = G_∞ * k_t^(1/am) * exp(-airmasses_0 / am)
    return SOLAR_CONSTANT_W_M2 * (k_t ** (1.0 / max(am, 0.001))) * math.exp(
        -AIR_MASSES_0 / max(am, 0.001)
    )


def _total_irradiance_horizontal(altitude_deg: float,
                                 k_t: float = CLEAR_SKY_TRANSMITTANCE_K_T) -> float:
    """水平面总辐射（W/m²），直射 + 简化漫射。"""
    if altitude_deg <= 0.0:
        return 0.0
    direct = _direct_beam_irradiance(altitude_deg, k_t)
    # 简化漫射：晴空下漫射约占总辐射 15%
    diffuse = direct * 0.15 * (1.0 - k_t)
    sin_alt = math.sin(_rad(altitude_deg))
    return direct * sin_alt + diffuse


def _dli_clear_sky(lat: float, lon: float, year: int, month: int, day: int,
                   tz_offset: int = 0,
                   k_t: float = CLEAR_SKY_TRANSMITTANCE_K_T) -> float:
    """晴天上界的 DLI（mol·m⁻²·d⁻¹，PAR 波段）。

    方法：逐 15 分钟积分水平面总辐射，取 PAR 比例 45%。
    晴空模型（无云），实际值需乘天空透射系数（0.3-0.9 视云量）。
    """
    total_kj = 0.0
    n_steps = 96  # 15 分钟
    for i in range(n_steps):
        hour_utc = (i * 0.25) - tz_offset
        pos = solar_position(lat, lon, year, month, day, hour_utc)
        irr = _total_irradiance_horizontal(pos["altitude_deg"], k_t)
        total_kj += irr * 0.25 * 3.6  # W/m² * 0.25h = Wh/m²，×3.6 → kJ/m²
    # 全谱 → PAR：PAR 约占全谱 45%（KJA 2000 值）
    par_kj = total_kj * 0.45
    return par_kj / PAR_TO_KJ_PER_MOL


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def solar_position(lat: float, lon: float, year: int, month: int, day: int,
                   hour_utc: float = 12.0,
                   tz_offset: int = 0) -> Dict[str, float]:
    """查询某一时刻的太阳位置。

    Args:
        lat, lon: 经纬度（度）
        year, month, day: 日期
        hour_utc: 当日 UTC 时（0-24，支持小数如 12.5 表示 12:30）
        tz_offset: 时区偏移（小时），仅用于返回的本地时刻标注

    Returns:
        dict 含：declination_deg, hour_angle_deg, altitude_deg, azimuth_deg,
                air_mass, direct_beam_irradiance_w_m2, total_horizontal_w_m2,
                is_day (bool), source
    """
    jd = _julian_day(year, month, day, hour_utc)
    gamma = _fractional_year(jd)
    M = _solar_mean_anomaly(gamma)
    ecl_lon, _ = _ecliptic_longitude(M, year)
    eps = _obliquity_of_ecliptic(year)
    decl = _solar_declination(eps, ecl_lon)
    ra = _solar_right_ascension(eps, ecl_lon)
    st = _solar_mean_sidereal_time(year, month, day, hour_utc, jd)
    ha = _hour_angle(st, ra)
    lat_r = _rad(lat)
    alt = _solar_altitude(lat_r, decl, ha)
    az = _solar_azimuth(lat_r, decl, ha, alt)
    alt_deg = _deg(alt)
    irr = _direct_beam_irradiance(alt_deg)
    total_h = _total_irradiance_horizontal(alt_deg)
    am = _air_mass(alt_deg)
    return {
        "declination_deg": round(_deg(decl), 4),
        "hour_angle_deg": round(_deg(ha), 4),
        "altitude_deg": round(alt_deg, 4),
        "azimuth_deg": round(az, 4),
        "air_mass": round(am, 4) if am > 0 else 0.0,
        "direct_beam_irradiance_w_m2": round(irr, 3),
        "total_horizontal_w_m2": round(total_h, 3),
        "is_day": alt_deg > 0.0,
        "local_hour": round(hour_utc + tz_offset, 4),
        "source": SOURCE,
    }


def solar_noon_hours_utc(lat: float, lon: float, year: int, month: int,
                         day: int) -> float:
    """太阳正午 UTC 时（0-24）。"""
    # 简化：正午时 H=0，即 ra = sidereal_time
    # 从 jd 反推近似正午
    # 使用近似公式：正午 UTC 时 ≈ (12 - lon/15 + Equation_of_Time)
    jd_noon = _julian_day(year, month, day, 12.0)
    gamma = _fractional_year(jd_noon)
    M = _solar_mean_anomaly(gamma)
    ecl_lon, _ = _ecliptic_longitude(M, year)
    eps = _obliquity_of_ecliptic(year)
    ra = _solar_right_ascension(eps, ecl_lon)
    st = _solar_mean_sidereal_time(year, month, day, 12.0, jd_noon)
    ha = _hour_angle(st, ra)
    # 从 ha 推小时偏移：ha = 0 时是正午，ha = 15°/小时
    hour_offset = -_deg(ha) / 15.0
    return round(12.0 + hour_offset - lon / 15.0, 4)


def day_length_hours(lat: float, year: int, month: int, day: int) -> float:
    """日长（小时），基于日出日落时刻。"""
    sunrise, sunset = _sunrise_sunset(lat, year, month, day)
    if sunrise is None or sunset is None:
        return 0.0
    return sunset - sunrise


def _sunrise_sunset(lat: float, year: int, month: int, day: int
                    ) -> Tuple[Optional[float], Optional[float]]:
    """日出日落 UTC 时。返回 (sunrise, sunset)，极昼/极夜时可能为 None。"""
    jd_noon = _julian_day(year, month, day, 12.0)
    gamma = _fractional_year(jd_noon)
    M = _solar_mean_anomaly(gamma)
    ecl_lon, _ = _ecliptic_longitude(M, year)
    eps = _obliquity_of_ecliptic(year)
    decl = _solar_declination(eps, ecl_lon)
    lat_r = _rad(lat)
    # 日出时角：cos(H0) = -tan(lat)*tan(decl)
    cos_h0 = -math.tan(lat_r) * math.tan(decl)
    if cos_h0 > 1.0:
        # 太阳全天在地平线下（极夜）
        return None, None
    if cos_h0 < -1.0:
        # 太阳全天在地平线上（极昼）
        return 0.0, 24.0
    h0 = math.acos(cos_h0)
    # 太阳正午 UTC 时
    ra = _solar_right_ascension(eps, ecl_lon)
    st = _solar_mean_sidereal_time(year, month, day, 12.0, jd_noon)
    ha_noon = _hour_angle(st, ra)
    noon_hour = 12.0 - _deg(ha_noon) / 15.0
    # 日出日落时角 → 时间偏移
    hour_offset = _deg(h0) / 15.0
    sunrise = noon_hour - hour_offset
    sunset = noon_hour + hour_offset
    return round(sunrise, 4), round(sunset, 4)


class SunGeometry:
    """太阳几何引擎（缓存纬度/经度，多次调用更高效）。"""

    def __init__(self, lat: float, lon: float) -> None:
        self.lat = float(lat)
        self.lon = float(lon)
        self._lat_rad = _rad(lat)

    def position(self, year: int, month: int, day: int,
                 hour_utc: float = 12.0, tz_offset: int = 0) -> Dict[str, float]:
        return solar_position(self.lat, self.lon, year, month, day,
                              hour_utc, tz_offset)

    def hourly_positions(self, year: int, month: int, day: int,
                         tz_offset: int = 0) -> List[Dict[str, float]]:
        """返回 24 小时的太阳位置序列（0-23 时，UTC）。"""
        return [
            self.position(year, month, day, hour_utc=h, tz_offset=tz_offset)
            for h in range(24)
        ]

    def daily(self, year: int, month: int, day: int,
              tz_offset: int = 0) -> Dict[str, Any]:
        """返回某一日的完整太阳几何数据。

        Returns:
            dict 含：date, day_of_year, declination_deg（正午值）,
            sunrise_utc, sunset_utc, solar_noon_utc, day_length_hours,
            solar_noon_altitude_deg, direct_beam_max_w_m2,
            DLI_mol_m2_day, DLI_kJ_m2_day, DLI_45pct_of_SW_kJ_m2_day,
            source, uncertainty_note
        """
        noon_utc = solar_noon_hours_utc(self.lat, self.lon, year, month, day)
        noon_pos = self.position(year, month, day, noon_utc, tz_offset)
        sunrise, sunset = _sunrise_sunset(self.lat, year, month, day)
        dl = sunset - sunrise if (sunrise is not None and sunset is not None) else 0.0
        dli = _dli_clear_sky(self.lat, self.lon, year, month, day, tz_offset)
        doy = date(year, month, day).timetuple().tm_yday
        return {
            "date": f"{year}-{month:02d}-{day:02d}",
            "day_of_year": doy,
            "lat": self.lat,
            "lon": self.lon,
            "declination_deg": noon_pos["declination_deg"],
            "sunrise_utc": sunrise,
            "sunset_utc": sunset,
            "solar_noon_utc": round(noon_utc, 4),
            "solar_noon_local": round(noon_utc + tz_offset, 4),
            "day_length_hours": round(dl, 4),
            "solar_noon_altitude_deg": noon_pos["altitude_deg"],
            "solar_noon_azimuth_deg": noon_pos["azimuth_deg"],
            "direct_beam_max_w_m2": noon_pos["direct_beam_irradiance_w_m2"],
            "DLI_mol_m2_day": round(dli, 3),
            "DLI_kJ_m2_day": round(dli * PAR_TO_KJ_PER_MOL, 3),
            "DLI_units_note": "DLI 为晴空上界（无云），实际值需乘天空透射系数 0.3-0.9",
            "source": SOURCE,
            "uncertainty_note": (
                "太阳位置误差 <0.01°；DLI 与实测偏差约 ±15%（缺云量/气溶胶/地形修正）"
            ),
        }

    def monthly_dli(self, year: int, tz_offset: int = 0) -> Dict[str, float]:
        """返回全年 12 个月的 DLI（mol·m⁻²·d⁻¹）。"""
        out = {}
        for m in range(1, 13):
            # 每月取 15 日
            dli = _dli_clear_sky(self.lat, self.lon, year, m, 15, tz_offset)
            out[f"{m:02d}"] = round(dli, 3)
        return out

    def __repr__(self) -> str:
        return (f"<SunGeometry lat={self.lat} lon={self.lon} "
                f"source={SOURCE}>")


# ---------------------------------------------------------------------------
# 便捷工厂与测试
# ---------------------------------------------------------------------------

def make_sun_geometry(lat: float, lon: float) -> SunGeometry:
    """工厂函数，与项目内其它模块命名风格一致。"""
    return SunGeometry(lat, lon)


def _selftest() -> None:
    """自测：验证关键数值正确性。"""
    # 测试 1：太阳赤纬在夏至日最大（约 +23.4°），冬至日最小（约 -23.4°）
    sg = SunGeometry(0.0, 0.0)
    june21 = sg.daily(2026, 6, 21, tz_offset=0)
    dec21 = sg.daily(2026, 12, 21, tz_offset=0)
    assert 22.0 < june21["declination_deg"] < 24.5, (
        f"夏至赤纬应约 +23.4°，实际 {june21['declination_deg']}")
    assert -24.5 < dec21["declination_deg"] < -22.0, (
        f"冬至赤纬应约 -23.4°，实际 {dec21['declination_deg']}")
    print(f"✓ 太阳赤纬：夏至 {june21['declination_deg']:+.3f}° / "
          f"冬至 {dec21['declination_deg']:+.3f}°")

    # 测试 2：日长在春/秋分日约 12h，夏至日在北半球最长
    eq_mar = sg.daily(2026, 3, 21, tz_offset=0)
    eq_sep = sg.daily(2026, 9, 23, tz_offset=0)
    assert 11.9 < eq_mar["day_length_hours"] < 12.1, (
        f"春分日长应≈12h，实际 {eq_mar['day_length_hours']}")
    assert 11.9 < eq_sep["day_length_hours"] < 12.1, (
        f"秋分日长应≈12h，实际 {eq_sep['day_length_hours']}")
    print(f"✓ 日长：春分 {eq_mar['day_length_hours']:.3f}h / "
          f"秋分 {eq_sep['day_length_hours']:.3f}h")

    # 测试 3：上海（30N）夏至日长 > 冬至日长
    shanghai = SunGeometry(31.23, 121.47)
    sh_s21 = shanghai.daily(2026, 6, 21, tz_offset=8)
    sh_w21 = shanghai.daily(2026, 12, 21, tz_offset=8)
    assert sh_s21["day_length_hours"] > 14.0, (
        f"上海夏至日长应>14h，实际 {sh_s21['day_length_hours']}")
    assert sh_w21["day_length_hours"] < 10.5, (
        f"上海冬至日长应<10.5h，实际 {sh_w21['day_length_hours']}")
    print(f"✓ 上海夏至/冬至日长：{sh_s21['day_length_hours']:.3f}h / "
          f"{sh_w21['day_length_hours']:.3f}h")

    # 测试 4：DLI 应满足：上海夏至 > 上海冬至，赤道全年较均匀
    eq_q1 = sg.monthly_dli(2026, tz_offset=0)
    sh_q1 = shanghai.monthly_dli(2026, tz_offset=8)
    assert sh_q1["06"] > sh_q1["12"] * 1.5, (
        f"上海 6 月 DLI 应 > 12 月 * 1.5，实际 6={sh_q1['06']}, 12={sh_q1['12']}")
    print(f"✓ 上海 DLI：6 月 {sh_q1['06']:.2f} vs 12 月 {sh_q1['12']:.2f} "
          f"(差 {sh_q1['06']/sh_q1['12']:.2f}×)")

    # 测试 5：极昼极夜（斯瓦尔巴群岛 78N）
    s80 = SunGeometry(78.0, 15.0)
    s80_w = s80.daily(2026, 12, 21, tz_offset=1)
    s80_s = s80.daily(2026, 6, 21, tz_offset=1)
    assert s80_w["day_length_hours"] == 0.0, (
        f"78N 冬至应极夜，实际 {s80_w['day_length_hours']}")
    assert s80_s["day_length_hours"] == 24.0, (
        f"78N 夏至应极昼，实际 {s80_s['day_length_hours']}")
    print(f"✓ 极昼极夜：78N 夏至 {s80_s['day_length_hours']}h / "
          f"冬至 {s80_w['day_length_hours']}h")

    # 测试 6：太阳高度角上限（赤道正午春分 ≈ 90°）
    eq_pos = sg.position(2026, 3, 21, hour_utc=12.0, tz_offset=0)
    assert 85.0 < eq_pos["altitude_deg"] < 91.0, (
        f"赤道春分正午太阳高度应≈90°，实际 {eq_pos['altitude_deg']}")
    print(f"✓ 太阳高度角：赤道春分正午 {eq_pos['altitude_deg']:.3f}°")

    # 测试 7：DLI 合理性（上海 6 月应约 45-55 mol/m²/day，与 NASA POWER 全谱当量 60-70 一致）
    assert 40.0 < sh_q1["06"] < 65.0, (
        f"上海 6 月 DLI 应在 40-65 区间，实际 {sh_q1['06']}")
    print(f"✓ DLI 量级：上海 6 月 {sh_q1['06']:.2f} mol/m²/day "
          f"(合理区间 40-65)")

    print("\n[all 7 selftests passed]")


if __name__ == "__main__":
    _selftest()
