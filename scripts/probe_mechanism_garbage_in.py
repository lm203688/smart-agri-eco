#!/usr/bin/env python3
"""
probe_mechanism_garbage_in.py — 机理内核"垃圾进垃圾出"实证探针

针对 engine/agriworld_lite.py 和 engine/derived.py 里的 4 个核心数值函数，
逐个喂入物理上不可能的输入，观察返回值。

用途：为地基审计 H3 提供**实测证据**——不依赖推断，
      每一个"返回异常值而不报错"就是可复现的失效样本。

运行：
    python scripts/probe_mechanism_garbage_in.py
"""
from pathlib import Path
import sys, math, traceback

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

results = []

def probe(name, fn, arg_desc, arg_value, expected_ok=False):
    """arg_desc: 参数说明; arg_value: 传入的异常值; expected_ok: 期望是否应正常返回"""
    try:
        v = fn(*arg_value) if isinstance(arg_value, tuple) else fn(arg_value)
        status = "RETURNED"
        detail = f"return={v!r}"
    except Exception as e:
        status = f"RAISED {type(e).__name__}"
        detail = f"msg={str(e)[:60]}"
    verdict = "OK" if (status.startswith("RAISED") or (status == "RETURNED" and expected_ok)) else "FAIL-GIGO"
    results.append((name, arg_desc, arg_value, status, detail, verdict))

# --- 1. theoretical_yield_cap(crop, dli, days) ---
print("=" * 72)
print("H3 机理内核反例实证 — 垃圾进垃圾出")
print("=" * 72)

try:
    from engine.agriworld_lite import theoretical_yield_cap as tyc
    print("\n[1] theoretical_yield_cap(crop, dli, days)")
    print("-" * 60)
    # 正常基线
    probe("tyc", tyc, "正常基线 (wheat, 2MJ/m²/day, 120d)",
          ("wheat", 2.0, 120), expected_ok=True)
    # 负天数
    probe("tyc", tyc, "负天数 days=-5 (物理不可能)",
          ("wheat", 2.0, -5))
    # 超大天数
    probe("tyc", tyc, "超大天数 days=99999 (超过作物全生长期)",
          ("wheat", 2.0, 99999))
    # 零光照（合法边界：无光合=零产量，返回 0 是正确行为）
    probe("tyc", tyc, "零光照 dli=0 (合法边界)",
          ("wheat", 0.0, 120), expected_ok=True)
    # 负光照
    probe("tyc", tyc, "负光照 dli=-1 (物理不可能)",
          ("wheat", -1.0, 120))
    # NaN 光照
    probe("tyc", tyc, "NaN 光照 dli=nan",
          ("wheat", float("nan"), 120))
    # inf 光照
    probe("tyc", tyc, "inf 光照 dli=inf",
          ("wheat", float("inf"), 120))
    # 未知作物
    probe("tyc", tyc, "未知作物 crop='quantum_plant'",
          ("quantum_plant", 2.0, 120))
    # 空作物
    probe("tyc", tyc, "空字符串作物 crop=''",
          ("", 2.0, 120))
    # 字符串作物
    probe("tyc", tyc, "作物为 None",
          (None, 2.0, 120))
except Exception as e:
    print(f"  [import failed] {e}")

# --- 2. temp_factor(T, Topt, Tmax, Tmin) ---
try:
    from engine.agriworld_lite import temp_factor as tf
    print("\n[2] temp_factor(T, Topt, Tmax, Tmin)")
    print("-" * 60)
    probe("temp_factor", tf, "正常基线 T=25, Topt=25, Tmax=35, Tmin=15",
          (25.0, 25.0, 35.0, 15.0), expected_ok=True)
    # 超低温
    probe("temp_factor", tf, "超低温 T=-100°C (地球外)",
          (-100.0, 25.0, 35.0, 15.0))
    # 超高温
    probe("temp_factor", tf, "超高温 T=100°C (沸水)",
          (100.0, 25.0, 35.0, 15.0))
    # Tmin > Tmax
    probe("temp_factor", tf, "边界错乱 Tmin(30) > Tmax(10)",
          (25.0, 25.0, 10.0, 30.0))
    # Topt 超出 [Tmin, Tmax]
    probe("temp_factor", tf, "Topt 超出边界 (Topt=50, Tmax=35)",
          (25.0, 50.0, 35.0, 15.0))
    # NaN
    probe("temp_factor", tf, "NaN 输入",
          (float("nan"), 25.0, 35.0, 15.0))
    # 字符串
    probe("temp_factor", tf, "字符串输入 T='hot'",
          ("hot", 25.0, 35.0, 15.0))
except Exception as e:
    print(f"  [import failed] {e}")

# --- 3. water_stress_factor(theta) ---
try:
    from engine.agriworld_lite import water_stress_factor as wsf
    print("\n[3] water_stress_factor(theta)")
    print("-" * 60)
    probe("water_stress", wsf, "正常基线 theta=0.5 (田间持水量一半)",
          0.5, expected_ok=True)
    probe("water_stress", wsf, "干燥极限 theta=0 (合法边界)",
          0.0, expected_ok=True)
    probe("water_stress", wsf, "饱和上限 theta=1.0 (合法边界)",
          1.0, expected_ok=True)
    probe("water_stress", wsf, "负含水率 theta=-0.2 (物理不可能)",
          -0.2)
    probe("water_stress", wsf, "超饱和 theta=1.5 (不可能)",
          1.5)
    probe("water_stress", wsf, "超大 theta=1e9",
          1e9)
    probe("water_stress", wsf, "NaN",
          float("nan"))
    probe("water_stress", wsf, "字符串 'soil'",
          "soil")
except Exception as e:
    print(f"  [import failed] {e}")

# --- 4. vpd(T, RH) ---
try:
    from engine.derived import vpd
    print("\n[4] vpd(T, RH)")
    print("-" * 60)
    probe("vpd", vpd, "正常基线 T=25°C, RH=60%",
          (25.0, 60.0), expected_ok=True)
    probe("vpd", vpd, "RH=100% 饱和 (合法边界)",
          (25.0, 100.0), expected_ok=True)
    probe("vpd", vpd, "RH=150% (物理不可能)",
          (25.0, 150.0))
    probe("vpd", vpd, "RH=-5% (物理不可能)",
          (25.0, -5.0))
    probe("vpd", vpd, "极低温 T=-100°C",
          (-100.0, 50.0))
    probe("vpd", vpd, "极高温 T=150°C",
          (150.0, 50.0))
    probe("vpd", vpd, "NaN 温度",
          (float("nan"), 50.0))
    probe("vpd", vpd, "NaN 湿度",
          (25.0, float("nan")))
    probe("vpd", vpd, "inf 温度",
          (float("inf"), 50.0))
except Exception as e:
    print(f"  [import failed] {e}")

# --- 汇总 ---
print("\n" + "=" * 72)
print("汇总")
print("=" * 72)
total = len(results)
fails = sum(1 for r in results if r[5] == "FAIL-GIGO")
print(f"\n总探针数: {total}")
print(f"FAIL-GIGO (垃圾进垃圾出): {fails} / {total}  ({fails/total:.1%})")
print(f"\n按函数分组:")
from collections import defaultdict
by_fn = defaultdict(lambda: [0, 0])
for r in results:
    by_fn[r[0]][0] += 1
    if r[5] == "FAIL-GIGO":
        by_fn[r[0]][1] += 1
for fn, (t, f) in by_fn.items():
    print(f"  {fn:<22s}  {f}/{t} FAIL")

print("\n" + "=" * 72)
print("FAIL-GIGO 详细清单（每一行都是可复现的失效样本）")
print("=" * 72)
for r in results:
    if r[5] == "FAIL-GIGO":
        print(f"  ✗ {r[0]:<18s} | {r[1]:<40s} | {r[3]:<15s} | {r[4]}")
