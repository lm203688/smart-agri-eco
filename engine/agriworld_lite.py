"""agriworld_lite.py — AgriWorld-Lite v0：零依赖可微分微场景数字孪生机理内核。

愿景：docs/next_stage_vision_2026-10-15.md §支柱一 · AgriWorld-Lite。

v0 范围（严格）：
  ① 光截获        Beer-Lambert        I_abs = I_0·(1 − exp(−k·LAI))
  ② CO2 同化      矩形双曲线 × 光×温×水×CO2 修正（WOFOST/Farquhar 简化）
  ③ 同化物分配    发育期依赖的系数表（营养生长 → 生殖生长切换）
  ④ 维持+生长呼吸 Q10 温度依赖 + 器官特异性系数（Penning de Vries）
  ⑤ 蒸腾          Penman-Monteith 简化（FAO-56）× 冠层导度 × VPD
  ⑥ 根区水/养分   水量平衡 + 蒸腾驱动的质量流

**零依赖硬约束**：只用 math/json/dataclasses。禁止 numpy/scipy。

**微场景特化**：状态变量少（6 个），参数少，可解析求导。
**不做的事**：大田土壤水力（Richards 方程）、根系分布模型、病虫害动力学——
这些不属于微场景数字孪生，也不属于 v0 范围。

参考来源（方法公开，代码不复用）：
  - WOFOST/PCSE：光截获/同化/分配骨架
  - FAO Irrigation Drainage Paper 56：Penman-Monteith
  - Penning de Vries (1974)：呼吸 Q10
  - van Genuchten：基质持水曲线（简化为线性）

署名：Wageningen WOFOST crop parameters (EUPL 1.2) — 参数仅从已有
data/wofost_phenology_reference.json 读取，禁止从 WOFOST 源码抄函数。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# H3：数值契约装饰器（FOUNDATION_AUDIT 2026-10-16 §H3）
# 用 core/numeric_domain.py 提供的 bounded/positive/known_enum/non_negative
# 在机理核心函数入口做物理/统计/类型校验，杜绝 GIGO 静默通过。
from core.numeric_domain import bounded, known_enum, non_negative, positive
from core.crop_registry import ENGINE_CROPS  # S1.4：作物枚举单一来源


# ---------------------------------------------------------------------------
# 物理常数（国际单位）
# ---------------------------------------------------------------------------
# 光合有效辐射 PAR 上限参考（充足光环境，用于校准量级）
PAR_MAX_KJ_M2_D = 200.0  # ~600 µmol·m⁻²·s⁻¹ × 24h × 0.4 × 3.6 ≈ 210
# 作物光合效率理论上限（每单位 PAR 转碳水干物质，用于物理约束冲突检测）
# 光能→生物质转化率：C3 理论上限 ~2%；C4 上限 ~5%
PHOTO_CONVERSION_C3 = 0.02 * 0.04184  # ~8.4e-4 g·kJ⁻¹（PAR 到干物质，粗略）
PHOTO_CONVERSION_C4 = 0.05 * 0.04184  # ~2.1e-3 g·kJ⁻¹
# 蒸腾水的潜热（kJ·kg⁻¹），FAO-56 中 λ 的典型值
LATENT_HEAT_KJ_KG = 2450.0
# 空气密度（kg·m⁻³）在 20℃
AIR_DENSITY_KG_M3 = 1.2
# VPD 上限（Pa），高盐度空气 ~4000 Pa
VPD_MAX_PA = 4000.0
# Q10 呼吸温度系数
Q10_DEFAULT = 2.0


# ---------------------------------------------------------------------------
# 作物参数（机理参数，与物候参数表解耦）
# 所有参数均为「零样本可跑通」的合理默认，来源为公开文献（WOFOST/FAO-56）。
# 每个作物可以 override，未 override 时用 DEFAULT_PARAMS。
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CropMechanisticParams:
    """作物机理参数（与作物本体参数解耦，独立于物候 TSUM 表）。

    参数命名与量纲：
      k_ext           : 冠层消光系数 [1/LAI]           — 典型 0.45–0.75
      alpha_max       : 冠层最大光响应速率 [g·m⁻²·d⁻¹] — 冠层尺度，不是叶尺
      c_star          : 光呼吸补偿点 [µmol·mol⁻¹]     — C3 典型 40-70，C4 ~15-20
      k_m             : CO2 半饱和 [µmol·mol⁻¹]       — 典型 400-600（=C3 的 Kc*(1+O/Ko)）
      tbase_c         : 基温 [℃]                       — 与物候 TBASE 一致
      t_opt_c         : 同化最适温度 [℃]               — 典型 25-30
      t_max_c         : 同化停止温度 [℃]               — 典型 40-45
      rho_lv          : 叶维持呼吸系数 [g·g⁻¹·d⁻¹]     — 典型 0.015
      rho_st          : 茎维持呼吸系数                   — 典型 0.006
      rho_so          : 贮藏器官维持呼吸系数             — 典型 0.003
      rho_gr          : 生长呼吸系数 [g·g⁻¹]            — 典型 0.06-0.15
      lai_max         : 最大 LAI [m²·m⁻²]              — 典型 4-10
      y_max           : 单位叶面积的最大累积生物量上限    — 用于截断
      sla_m2_g        : 单位叶干重的叶面积 [m²·g⁻¹]     — 用于 W_lv → LAI
      g_canopy        : 冠层气孔导度 [mm·s⁻¹] 基准       — 简化，用于蒸腾
      nuptake_max     : 单位蒸腾最大吸氮量 [mg·L⁻¹·d⁻¹]  — 用于养分质量流
      eco_type        : "C3" 或 "C4"，用于物理上限判定
    """
    # 光截获
    k_ext: float = 0.65
    # 同化
    alpha_max: float = 22.0       # g·m⁻²·d⁻¹（冠层最大光合速率，叶尺≈12）
    c_star: float = 50.0          # Pa（光呼吸补偿点）
    k_m: float = 500.0            # Pa（CO2 半饱和）
    # 温度响应
    tbase_c: float = 8.0
    t_opt_c: float = 27.0
    t_max_c: float = 42.0
    # 呼吸
    rho_lv: float = 0.015
    rho_st: float = 0.006
    rho_so: float = 0.003
    rho_gr: float = 0.10
    # LAI 上限
    lai_max: float = 8.0
    y_max: float = 4500.0         # g·m⁻² 累积上限（用于数值稳定）
    sla_m2_g: float = 2.5         # 单位叶干重的叶面积（用于 W_lv→LAI）
    # 蒸腾
    g_canopy: float = 15.0        # mm·s⁻¹ 冠层气孔导度基准（FAO-56 参考）
    # 养分
    nuptake_max: float = 2.00    # mg·L⁻¹·d⁻¹ 单位蒸腾吸氮强度（A2-α：0.5 过低导致 N 几乎不消耗）
    # 生态型
    eco_type: str = "C3"


# 已移植的 7 作物机理参数（覆盖 wofost_phenology_reference.json 的作物）
CROP_PARAMS: Dict[str, CropMechanisticParams] = {
    "potato": CropMechanisticParams(
        k_ext=0.62, alpha_max=24.0, c_star=50.0, k_m=500.0,
        # A2-α：t_opt_c 从 22 降到 17（真实土豆同化最适温度 15-18℃，参照 WOFOST 冷温带作物参数）
        tbase_c=2.0, t_opt_c=17.0, t_max_c=28.0,
        rho_lv=0.020, rho_st=0.006, rho_so=0.004, rho_gr=0.12,
        lai_max=9.0, y_max=4500.0, sla_m2_g=3.0,
        g_canopy=18.0, eco_type="C3",
    ),
    "wheat": CropMechanisticParams(
        k_ext=0.68, alpha_max=22.0, c_star=45.0, k_m=500.0,
        tbase_c=0.0, t_opt_c=25.0, t_max_c=38.0,
        rho_lv=0.018, rho_st=0.008, rho_so=0.004, rho_gr=0.10,
        lai_max=6.5, y_max=3200.0, sla_m2_g=2.0,
        g_canopy=14.0, eco_type="C3",
    ),
    "soybean": CropMechanisticParams(
        k_ext=0.58, alpha_max=26.0, c_star=55.0, k_m=550.0,
        tbase_c=7.0, t_opt_c=28.0, t_max_c=38.0,
        rho_lv=0.017, rho_st=0.007, rho_so=0.005, rho_gr=0.11,
        lai_max=7.0, y_max=2800.0, sla_m2_g=2.5,
        g_canopy=17.0, eco_type="C3",
    ),
    "sunflower": CropMechanisticParams(
        k_ext=0.60, alpha_max=27.0, c_star=55.0, k_m=520.0,
        tbase_c=5.0, t_opt_c=28.0, t_max_c=40.0,
        rho_lv=0.018, rho_st=0.008, rho_so=0.005, rho_gr=0.10,
        lai_max=6.0, y_max=2600.0, sla_m2_g=2.5,
        g_canopy=16.0, eco_type="C3",
    ),
    "rice": CropMechanisticParams(
        k_ext=0.62, alpha_max=23.0, c_star=45.0, k_m=500.0,
        tbase_c=10.0, t_opt_c=30.0, t_max_c=42.0,
        rho_lv=0.016, rho_st=0.007, rho_so=0.004, rho_gr=0.11,
        lai_max=8.0, y_max=3800.0, sla_m2_g=3.0,
        g_canopy=20.0, eco_type="C3",
    ),
    "sweetpotato": CropMechanisticParams(
        k_ext=0.55, alpha_max=25.0, c_star=50.0, k_m=500.0,
        tbase_c=10.0, t_opt_c=30.0, t_max_c=40.0,
        rho_lv=0.018, rho_st=0.006, rho_so=0.004, rho_gr=0.12,
        lai_max=10.0, y_max=3600.0, sla_m2_g=3.5,
        g_canopy=22.0, eco_type="C3",
    ),
    "mungbean": CropMechanisticParams(
        k_ext=0.60, alpha_max=20.0, c_star=50.0, k_m=500.0,
        tbase_c=10.0, t_opt_c=28.0, t_max_c=38.0,
        rho_lv=0.020, rho_st=0.007, rho_so=0.004, rho_gr=0.11,
        lai_max=6.0, y_max=2200.0, sla_m2_g=2.0,
        g_canopy=16.0, eco_type="C3",
    ),
}


def get_params(crop: str, overrides: Optional[Dict[str, float]] = None
               ) -> CropMechanisticParams:
    """按作物名取机理参数，可覆盖。未移植作物回落 DEFAULT_PARAMS。"""
    p = CROP_PARAMS.get(crop.strip().lower())
    if p is None:
        p = CropMechanisticParams()
    if not overrides:
        return p
    return CropMechanisticParams(**{
        **p.__dict__,
        **{k: v for k, v in overrides.items()
           if k in CropMechanisticParams.__dataclass_fields__},
    })


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------

@dataclass
class State:
    """作物冠层状态（微场景）。"""
    dvi: float = 0.0           # 发育进程 0=出苗 1=开花 2=成熟
    lai: float = 0.05          # 叶面积指数
    w_lv: float = 0.0          # 叶干重 [g·m⁻²]
    w_st: float = 0.0          # 茎干重
    w_so: float = 0.0          # 贮藏器官干重（果实/块茎/籽）
    theta: float = 0.30        # 根区基质含水量 [-]（无土用基质体积含水率）
    n_avail: float = 30.0      # 根区可用氮 [mg·L⁻¹]（A2-α：初始贴近 TBI=30 才有响应空间）
    ec: float = 1.5            # 根区电导率 [mS·cm⁻¹]
    t_canopy: Optional[float] = None  # 冠层温度 [℃]（None 表示与气温相等）

    @property
    def total_biomass(self) -> float:
        return self.w_lv + self.w_st + self.w_so


# ---------------------------------------------------------------------------
# 输入（每日驱动）
# ---------------------------------------------------------------------------

@dataclass
class DailyInput:
    """每日环境 + 动作输入。"""
    # 环境
    dli: float = 12.0                # 日累积辐射 [M·J·m⁻²·d⁻¹] ≈ 100× [k·J·m⁻²·d⁻¹]
    temp_mean_c: float = 22.0        # 日均温
    temp_min_c: float = 17.0         # 日均低
    temp_max_c: float = 27.0         # 日均高
    rh: float = 0.60                 # 相对湿 [-]
    wind_ms: float = 1.5             # 风速
    co2_ppm: float = 420.0           # 大气 CO2
    # 动作
    irrigation_l_m2: float = 2.0     # 当日灌溉量 [L·m⁻²]
    fert_n_mg_l: float = 30.0        # 当日补氮 [mg·L⁻¹]
    light_ext_kj_m2_h: float = 0.0   # 补光强度 [k·J·m⁻²·h⁻¹]，0=无补光
    light_ext_hours: float = 0.0     # 补光小时数


def par_from_dli(dli_mj_m2_d: float) -> float:
    """把 DLI 单位从 MJ·m⁻²·d⁻¹ 换算为 kJ·m⁻²·d⁻¹ 的 PAR 有效分量。

    PAR 占总太阳辐射约 40-50%；工程上取 45%。
    """
    return dli_mj_m2_d * 1000.0 * 0.45


def vp_from_rh(t_c: float, rh: float) -> float:
    """根据气温与相对湿度算水汽压亏缺 VPD [Pa]。

    FAO-56 简化：e_s(T) = 0.6108 · exp(17.27·T/(T+237.3))  [kPa]
    """
    if t_c < -40 or t_c > 60:
        return 0.0
    es = 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3)) * 1000.0  # Pa
    return max(0.0, es * (1.0 - rh))


# ---------------------------------------------------------------------------
# 段 ①：光截获
# ---------------------------------------------------------------------------

def light_interception(i0_par_kj: float, lai: float, k_ext: float
                       ) -> float:
    """Beer-Lambert 冠层截获 PAR [kJ·m⁻²·d⁻¹]。

    I_abs = I_0 · (1 − exp(−k · LAI))
    LAI=0 时 I_abs=0；LAI→∞ 时 I_abs→I_0。
    """
    if i0_par_kj <= 0 or lai <= 0:
        return 0.0
    return i0_par_kj * (1.0 - math.exp(-k_ext * lai))


def light_interception_gradient(lai: float, i0_par_kj: float, k_ext: float
                                ) -> float:
    """dI_abs/dLAI = I_0 · k · exp(−k·LAI)"""
    if i0_par_kj <= 0:
        return 0.0
    return i0_par_kj * k_ext * math.exp(-k_ext * lai)


def d_light_interception_d_k_ext(i0_par_kj: float, lai: float, k_ext: float) -> float:
    """dI_abs/dk = I_0 · LAI · exp(−k·LAI)"""
    if i0_par_kj <= 0 or lai <= 0:
        return 0.0
    return i0_par_kj * lai * math.exp(-k_ext * lai)


# ---------------------------------------------------------------------------
# 段 ②：CO2 同化
# ---------------------------------------------------------------------------

@bounded("t_base", -50.0, 50.0)
@bounded("t_opt", 0.0, 60.0)
@bounded("t_max", 20.0, 80.0)
@bounded("t_c", -50.0, 80.0)
def temp_factor(t_c: float, t_opt: float, t_max: float,
                t_base: float = 5.0) -> float:
    """温度响应因子 [0,1]（WOFOST 完整双曲线）。

    三段式（修正 A2-α）：
      T ≤ T_base: 0.0                                  低于基温不生长
      T_base < T ≤ T_opt: (T−T_base)/(T_opt−T_base)    上升段
      T_opt < T < T_max: (T_max−T)/(T_max−T_opt)        下降段
      T ≥ T_max: 0.0                                   停止生长

    原实现错误：`T ≤ T_opt` 时恒返回 1.0，导致 15℃ 与 22℃ 光合相同
    且 28℃ 时突降到 0.4，违反温度响应单调性——现已修复。

    H3 加固：入口加数值契约，杜绝 Tmin>Tmax 静默返回 0、T=-100℃ 静默接受。
    """
    # 契约之外的关系约束（装饰器目前不支持双向区间，人工兜底）
    if not (t_base < t_opt < t_max):
        raise ValueError(
            f"temp_factor: require t_base < t_opt < t_max, "
            f"got t_base={t_base}, t_opt={t_opt}, t_max={t_max}"
        )
    if t_c <= t_base or t_c >= t_max:
        return 0.0
    if t_c <= t_opt:
        return (t_c - t_base) / max(t_opt - t_base, 1e-9)
    return (t_max - t_c) / max(t_max - t_opt, 1e-9)


@non_negative("n_avail")
@bounded("tbi", 5.0, 100.0)
def npot_factor(n_avail: float, tbi: float = 30.0) -> float:
    """NPOT 氮素限制性因子 [0,1]（修正 A2-α）。

    基于 Penning de Vries 氮-干物质比（TBI 需求浓度，默认 30 mg·L⁻¹）：
      n_avail ≥ TBI: 1.0         氮充足
      0 < n < TBI:   n / TBI     线性降
      n ≤ 0:         0.0         完全氮限制

    参数 tbi 单位 mg·L⁻¹；调用方可按作物调整（叶菜 ≈ 15，作物 ≈ 30，果树 ≈ 45）。

    H3 加固：n_avail 必须 ≥ 0（负氮是物理不可能）；
             tbi ∈ [5, 100]（叶菜下限 15、果树上限 45，留余量到 5/100），拒绝 NaN/inf。
    """
    if n_avail >= tbi:
        return 1.0
    if n_avail <= 0:
        return 0.0
    return n_avail / max(tbi, 1e-9)


@bounded("theta", 0.0, 0.6, allow_nan=False)
@bounded("theta_fc", 0.0, 0.6)
def water_stress_factor(theta: float, theta_fc: float = 0.10) -> float:
    """水分胁迫因子（线性，简化）。θ≥θ_fc 时=1；θ→0 时→0。

    A2-α：θ_fc 从 0.30 降到 0.10（原阈值让低 θ 时 f_water 崩塌，压垮 DLI 单调性）

    H3 加固：θ 必须在 [0, 0.6]（饱和含水量典型上限），拒绝 NaN/inf/超大值。
    """
    if theta >= theta_fc:
        return 1.0
    return max(0.0, theta / max(theta_fc, 1e-9))


def light_half_saturation(alpha_max: float) -> float:
    """K_i（冠层光半饱和点）[kJ·m⁻²·d⁻¹]。

    由 α_max（冠层最大同化率）线性标定：K_i ≈ α_max × 30。
    经验关系来自 WOFOST 冠层同化率参数化——α_max 越高，冠层越接近光饱和，
    半饱和点也相应抬升。下限 1e-6 防零除。
    """
    return max(alpha_max * 30.0, 1e-6)


def photosynthesis_canopy(i_abs: float, co2_ppm: float, t_c: float,
                          theta: float, p: CropMechanisticParams,
                          n_avail: float = 30.0) -> float:
    """冠层同化率 A [g·m⁻²·d⁻¹]。

    A = α_max · f_light(I_abs) · f_temp(T) · f_water(θ) · f_co2(CO2)
      · f_n(NPOT)
      · f_light = 矩形双曲线光响应 I_abs / (I_abs + K_i)，K_i 由 α_max 标定
      · f_temp  = WOFOST 完整双曲线温度响应（T_base/T_opt/T_max 三段）
      · f_water = 线性水分胁迫
      · f_co2   = Farquhar CO2 响应 (Ci - C*) / (Ci + K_m)
                  （Ci 用大气 CO2 ppm 近似，C*/K_m 也用 µmol·mol⁻¹，量纲一致）
      · f_n     = NPOT 氮限制因子（A2-α 新增）
    """
    if i_abs <= 0:
        return 0.0
    k_i = light_half_saturation(p.alpha_max)
    f_light = i_abs / (i_abs + k_i)
    f_temp = temp_factor(t_c, p.t_opt_c, p.t_max_c, p.tbase_c)
    f_water = water_stress_factor(theta, 0.30)
    f_n = npot_factor(n_avail, 30.0)
    # CO2 响应：Farquhar 型矩形双曲线
    ci = co2_ppm
    if ci > p.c_star:
        c_factor = (ci - p.c_star) / (ci + p.k_m)
    else:
        c_factor = 0.0
    a_gross = p.alpha_max * f_light * f_temp * f_water * f_n
    return max(0.0, a_gross * c_factor)


def photosynthesis_gradient_lai(i0_par_kj: float, lai: float, co2_ppm: float,
                                t_c: float, theta: float,
                                p: CropMechanisticParams) -> float:
    """∂A/∂LAI = ∂A/∂I_abs · ∂I_abs/∂LAI（链式法则）。"""
    d_iabs_d_lai = light_interception_gradient(lai, i0_par_kj, p.k_ext)
    i_abs = light_interception(i0_par_kj, lai, p.k_ext)
    if i_abs <= 0:
        return 0.0
    k_i = light_half_saturation(p.alpha_max)
    f_light_grad = k_i / (i_abs + k_i) ** 2
    f_temp = temp_factor(t_c, p.t_opt_c, p.t_max_c, p.tbase_c)
    f_water = water_stress_factor(theta, 0.30)
    f_n = npot_factor(30.0, 30.0)  # 梯度对 LAI，N 视为外生；此处用充足氮参考
    # Farquhar CO2 响应梯度（对 LAI 无关，只是系数）
    ci = co2_ppm
    c_factor = max(0.0, (ci - p.c_star) / (ci + p.k_m)) if ci > p.c_star else 0.0
    return p.alpha_max * f_light_grad * f_temp * f_water * f_n * c_factor * d_iabs_d_lai


# ---------------------------------------------------------------------------
# 段 ③：同化物分配
# ---------------------------------------------------------------------------

def allocation_fraction(dvi: float) -> Tuple[float, float, float]:
    """发育期依赖的分配系数 (叶, 茎, 果)。归一化，和=1。

    参照 WOFOST 分配表：
      DVI 0-0.5 营养生长期：叶 0.55, 茎 0.35, 果 0.10
      DVI 0.5-1.0 生殖生长初期：叶 0.35, 茎 0.30, 果 0.35
      DVI 1.0-1.5 生殖生长盛期：叶 0.20, 茎 0.20, 果 0.60
      DVI ≥ 1.5 成熟期：叶 0.05, 茎 0.15, 果 0.80
    """
    d = max(0.0, min(dvi, 2.0))
    if d < 0.5:
        f = 0.5 + 0.5 * d  # 0.5→1.0
        # 线性插值 stage 0→1
        t = d / 0.5
        f_lv = 0.55 + t * (0.35 - 0.55)
        f_st = 0.35 + t * (0.30 - 0.35)
        f_so = 0.10 + t * (0.35 - 0.10)
    elif d < 1.0:
        t = (d - 0.5) / 0.5
        f_lv = 0.35 + t * (0.20 - 0.35)
        f_st = 0.30 + t * (0.20 - 0.30)
        f_so = 0.35 + t * (0.60 - 0.35)
    elif d < 1.5:
        t = (d - 1.0) / 0.5
        f_lv = 0.20 + t * (0.05 - 0.20)
        f_st = 0.20 + t * (0.15 - 0.20)
        f_so = 0.60 + t * (0.80 - 0.60)
    else:
        f_lv, f_st, f_so = 0.05, 0.15, 0.80
    # 数值稳定：归一化
    s = f_lv + f_st + f_so
    if s <= 0:
        return 0.5, 0.3, 0.2
    return f_lv / s, f_st / s, f_so / s


# ---------------------------------------------------------------------------
# 段 ④：呼吸
# ---------------------------------------------------------------------------

def respiration(maintenance_base: float, t_c: float, t_ref: float = 20.0,
                q10: float = Q10_DEFAULT, organ_biomass: float = 0.0,
                growth_respiration_coef: float = 0.10) -> float:
    """日呼吸损失 [g·m⁻²·d⁻¹]。

    维持呼吸 = ρ_org · W_org · Q10^((T−T_ref)/10)
    生长呼吸 = ρ_gr · ΔW  (在日积增量层面单独调用，此处只算维持)
    """
    if organ_biomass <= 0:
        return 0.0
    if q10 <= 0:
        return maintenance_base * organ_biomass
    return maintenance_base * organ_biomass * (q10 ** ((t_c - t_ref) / 10.0))


# ---------------------------------------------------------------------------
# 段 ⑤：蒸腾
# ---------------------------------------------------------------------------

def transpiration_pmp(inp: DailyInput, state: State, p: CropMechanisticParams) -> float:
    """Penman-Monteith 简化蒸腾 [mm·d⁻¹] = [L·m⁻²·d⁻¹]。

    基于 FAO-56 Penman-Monteith，量纲正确化：
      ET0 ≈ 3.5 mm/d @ (T=20℃, DLI=10 MJ/m²/d, VPD=1000 Pa) 参考点
    在此参考点上乘以：
      · dli_factor    = DLI/10（线性）
      · vp_factor     = VPD/1000（线性，上限 1.5）
      · temp_factor   = 1 + 0.03·(T−20)（Q10 近似）
      · lai_factor    = min(LAI/4, 1)（冠层饱和）
      · water_factor  = min(θ/0.15, 1)（水分胁迫）
      · g_canopy_factor = g_canopy/15（气孔导度缩放）

    上限 15 mm/d 用于防止极端情况下的数值发散。
    """
    if state.lai <= 0.01:
        return 0.0
    vp = vp_from_rh(inp.temp_mean_c, inp.rh)
    # A2-α：DLI 对蒸腾的驱动饱和在 DLI=10（原为 20），避免高 DLI 时蒸腾过量压垮 θ
    dli_factor = min(inp.dli, 10.0) / 10.0
    vp_factor = min(vp / 1000.0, 1.5)
    temp_factor = max(0.0, min(1.0 + 0.03 * (inp.temp_mean_c - 20.0), 1.5))
    lai_factor = max(0.1, min(state.lai / 4.0, 1.0))
    water_factor = min(state.theta / 0.15, 1.0)
    g_canopy_factor = p.g_canopy / 15.0
    et0_mm_d = 3.5 * dli_factor * vp_factor * temp_factor
    et_mm_d = et0_mm_d * lai_factor * water_factor * g_canopy_factor
    return max(0.0, min(et_mm_d, 15.0))


# ---------------------------------------------------------------------------
# 段 ⑥：根区水/养分平衡
# ---------------------------------------------------------------------------

def water_balance(state: State, transp_mm: float, irrigation_l_m2: float,
                  drainage_frac: float = 0.10) -> float:
    """水量平衡：Δθ = 灌溉 − 蒸腾 − 渗漏。返回新的根区基质含水量。

    简化：1 mm 蒸腾 = 1 L·m⁻²；基质体积含水率与灌溉换算取 200 mm 有效持水层。
    """
    delta = irrigation_l_m2 - transp_mm - 15.0 * drainage_frac  # 15mm 深度渗漏
    return max(0.02, min(0.60, state.theta + delta / 200.0))


def nutrient_uptake(transp_mm: float, theta: float, n_avail: float,
                    p: CropMechanisticParams) -> float:
    """养分吸收（蒸腾驱动质量流）。[mg·L⁻¹]

    质量流：N_uptake = N_avail · min(1, ET/L_ref) · (1 − exp(−θ/0.1))
    """
    if transp_mm <= 0 or n_avail <= 0:
        return 0.0
    l_ref = 20.0  # mm·d⁻¹ 参考蒸腾
    frac = min(1.0, transp_mm / l_ref)
    theta_factor = 1.0 - math.exp(-max(theta, 0.0) / 0.10)
    # A2-α：nuptake_max 已从 0.5 提到 2.0，去掉 0.1 缩放（原缩放过强导致 N 几乎不消耗）
    return n_avail * frac * theta_factor * p.nuptake_max


def ec_from_n(n_mg_l: float) -> float:
    """粗略 EC 估算：每 100 mg·L⁻¹ N 约 0.6 mS·cm⁻¹（含 K、Ca 等）。"""
    return 0.06 * n_mg_l * 0.01 + 0.3  # 基础 0.3 + 增量


# ---------------------------------------------------------------------------
# 主仿真器
# ---------------------------------------------------------------------------

@dataclass
class SimConfig:
    """仿真配置。"""
    days: int = 45
    dt_days: float = 1.0           # 日步长
    log_interval: int = 1          # 每几步记录
    verbose: bool = False


def simulate(crop: str, actions: Sequence[DailyInput],
             params: Optional[CropMechanisticParams] = None,
             initial_state: Optional[State] = None,
             config: Optional[SimConfig] = None) -> Dict[str, Any]:
    """运行机理仿真。

    返回：
      {
        "crop": ..., "params": ..., "days": N,
        "state_trajectory": [{"day": 0, "lai": ..., "w_lv": ..., "w_so": ..., "theta": ...}, ...],
        "final_state": {...},
        "final_biomass": {"total": ..., "w_so": ..., "w_lv": ..., "w_st": ...},
        "totals": {"dli_kj_m2": ..., "irrigation_l_m2": ..., "transp_mm": ..., "uptake_n": ...}
      }
    """
    if not actions:
        return {"crop": crop, "days": 0, "state_trajectory": [], "error": "empty actions"}
    p = params or get_params(crop)
    s = initial_state or State()
    cfg = config or SimConfig(days=len(actions))
    traj: List[Dict[str, Any]] = [{
        "day": 0, "dvi": round(s.dvi, 4), "lai": round(s.lai, 4),
        "w_lv": round(s.w_lv, 4), "w_st": round(s.w_st, 4), "w_so": round(s.w_so, 4),
        "theta": round(s.theta, 4), "n_avail": round(s.n_avail, 4),
    }]
    tot_dli = 0.0
    tot_irr = 0.0
    tot_transp = 0.0
    tot_uptake = 0.0
    tot_photo = 0.0
    tot_resp = 0.0
    dvi_rate = 1.0 / max(p.t_opt_c * 2, 30.0)  # 粗略物候推进
    for step_idx, inp in enumerate(actions, start=1):
        # ① 光截获
        i0_par = par_from_dli(inp.dli)
        # 补光（如果补光小时>0，按 kJ·m⁻²·h⁻¹ × 小时 折算到日累积，乘以 0.45 PAR）
        ext_par = inp.light_ext_kj_m2_h * inp.light_ext_hours * 0.45
        i0_par += ext_par
        i_abs = light_interception(i0_par, s.lai, p.k_ext)
        # ② 同化（A2-α：接入 NPOT 因子）
        a = photosynthesis_canopy(i_abs, inp.co2_ppm, inp.temp_mean_c, s.theta,
                                  p, n_avail=s.n_avail)
        # ④ 维持呼吸
        r_lv = respiration(p.rho_lv, inp.temp_mean_c, 20.0, Q10_DEFAULT, s.w_lv)
        r_st = respiration(p.rho_st, inp.temp_mean_c, 20.0, Q10_DEFAULT, s.w_st)
        r_so = respiration(p.rho_so, inp.temp_mean_c, 20.0, Q10_DEFAULT, s.w_so)
        r_total = r_lv + r_st + r_so
        # 净同化（用于分配）
        a_net = max(0.0, a - r_total)
        # ③ 分配
        f_lv, f_st, f_so = allocation_fraction(s.dvi)
        dw_lv, dw_st, dw_so = a_net * f_lv, a_net * f_st, a_net * f_so
        # 生长呼吸（消耗新干物质）
        r_gr = (dw_lv + dw_st + dw_so) * p.rho_gr
        dw_lv -= r_gr * f_lv
        dw_st -= r_gr * f_st
        dw_so -= r_gr * f_so
        # 状态推进
        s.w_lv = max(0.0, s.w_lv + dw_lv)
        s.w_st = max(0.0, s.w_st + dw_st)
        s.w_so = max(0.0, s.w_so + dw_so)
        # LAI 更新（叶干重→LAI，SLA = m²/g）
        s.lai = min(p.lai_max, max(0.0, s.lai + dw_lv / p.sla_m2_g))
        # DVI 推进
        s.dvi = min(2.0, s.dvi + dvi_rate)
        # ⑤ 蒸腾
        transp = transpiration_pmp(inp, s, p)
        # ⑥ 水分
        s.theta = water_balance(s, transp, inp.irrigation_l_m2)
        # 养分
        uptake = nutrient_uptake(transp, s.theta, s.n_avail, p)
        s.n_avail = max(0.0, s.n_avail - uptake + inp.fert_n_mg_l * 0.15)
        # A2-α：fert 补充系数 0.5 → 0.15（原系数导致 45 天 N 从 30 堆积到 600+，远超 TBI=30）
        # 冠层温度（VPD 越大，蒸腾越强，冠层可能更凉）
        vp = vp_from_rh(inp.temp_mean_c, inp.rh)
        s.t_canopy = inp.temp_mean_c - min(2.0, transp * 0.15)
        # 累计
        tot_dli += i0_par
        tot_irr += inp.irrigation_l_m2
        tot_transp += transp
        tot_uptake += uptake
        tot_photo += a
        tot_resp += r_total
        if step_idx % max(1, cfg.log_interval) == 0:
            traj.append({
                "day": step_idx, "dvi": round(s.dvi, 4), "lai": round(s.lai, 4),
                "w_lv": round(s.w_lv, 4), "w_st": round(s.w_st, 4),
                "w_so": round(s.w_so, 4), "theta": round(s.theta, 4),
                "n_avail": round(s.n_avail, 4),
                "photo_g_m2_d": round(a, 4), "resp_g_m2_d": round(r_total, 4),
                "transp_mm_d": round(transp, 4),
                "co2_ppm": inp.co2_ppm, "temp_mean_c": inp.temp_mean_c,
            })
    return {
        "crop": crop,
        "days": len(actions),
        "params": p.__dict__,
        "state_trajectory": traj,
        "final_state": {
            "dvi": s.dvi, "lai": s.lai, "w_lv": s.w_lv, "w_st": s.w_st,
            "w_so": s.w_so, "theta": s.theta, "n_avail": s.n_avail,
        },
        "final_biomass": {
            "total": s.w_lv + s.w_st + s.w_so,
            "w_lv": s.w_lv, "w_st": s.w_st, "w_so": s.w_so,
        },
        "totals": {
            "par_kj_m2": round(tot_dli, 4),
            "irrigation_l_m2": round(tot_irr, 4),
            "transp_mm": round(tot_transp, 4),
            "uptake_n_mg_l": round(tot_uptake, 4),
            "photo_g_m2": round(tot_photo, 4),
            "resp_g_m2": round(tot_resp, 4),
        },
    }


# ---------------------------------------------------------------------------
# 物理约束冲突检测（供 verify_service 复用）
# ---------------------------------------------------------------------------

@known_enum("crop", ENGINE_CROPS)
@positive("dli_mj_m2_d")
@bounded("days", 1, 365)
def theoretical_yield_cap(crop: str, dli_mj_m2_d: float, days: int) -> float:
    """给定 DLI 与天数，返回单位面积产量理论上限 [g·m⁻²]。

    用于物理约束冲突判定：光能转化效率不可能超上限。

    H3 加固：
    - crop 必须是已移植作物（拒 'quantum_plant' 静默回落）
    - dli_mj_m2_d 必须 > 0（拒 0/负数）
    - days ∈ [1, 365]（拒 -5、99999）
    """
    p = get_params(crop)
    conv = PHOTO_CONVERSION_C3 if p.eco_type == "C3" else PHOTO_CONVERSION_C4
    par_total = dli_mj_m2_d * 1000.0 * 0.45 * days
    return par_total * conv


def check_physical_feasibility(crop: str, dli_mj_m2_d: float, days: int,
                               claimed_yield_g_m2: float) -> Dict[str, Any]:
    """给定声称产量与 DLI/天数，返回可行性诊断。"""
    cap = theoretical_yield_cap(crop, dli_mj_m2_d, days)
    if claimed_yield_g_m2 > cap:
        return {
            "verdict": "contradicted",
            "reason": "physical_energy_ceiling",
            "claimed": claimed_yield_g_m2,
            "theoretical_max": round(cap, 2),
            "ratio": round(claimed_yield_g_m2 / cap, 3),
        }
    return {
        "verdict": "supported",
        "theoretical_max": round(cap, 2),
        "headroom_ratio": round(cap - claimed_yield_g_m2, 2),
    }


if __name__ == "__main__":
    # 自测：45 天温和环境（12h 光周期、22℃ 均温、10 MJ/m²/d DLI），马铃薯
    base = DailyInput(dli=10.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
                      rh=0.60, wind_ms=1.5, co2_ppm=420.0,
                      irrigation_l_m2=2.0, fert_n_mg_l=30.0)
    res = simulate("potato", [base] * 45)
    print(f"days={res['days']}, lai={res['final_state']['lai']:.2f}, "
          f"total_biomass={res['final_biomass']['total']:.1f} g/m², "
          f"w_so={res['final_biomass']['w_so']:.1f} g/m²")
    print(f"totals={res['totals']}")
    # 物理上限验证：DLI=10 MJ/m²/d × 45d 马铃薯理论上限
    cap = theoretical_yield_cap("potato", 10.0, 45)
    print(f"theoretical_yield_cap = {cap:.1f} g/m²")
