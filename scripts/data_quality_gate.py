#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/data_quality_gate.py —— 数据质量门禁（零依赖）

对齐项目战略《项目战略指引》§九.2「数据质量风险 → 数据清洗管线 + 标准操作引导」
与 §七.3「数据标准：配套数据质量与标注规范」。

职责：
  1. 核验核心数据文件可解析、非空、结构合理；
  2. 守卫「真实性红线」：crop_adapt_db 中 calibrated=true 必须带 measured_calibration 实证，
     禁止「假校准标记」（与 clean_demo_data.py / CI 数据完整性门禁同源）；
  3. 数值合理性：降水单位口径与既有约定一致（monthly_precip_mm 为月内日均 mm/day，
     不得出现 >200 的疑似月累计误标）；温度区间须落在合理农业范围；
  4. 预设城市单一数据源约定：每城须显式声明 modeled 字段；
  5. 输出 PASS/FAIL 报告，全部通过 exit 0，否则 exit 1（可接入 CI 门禁）。

用法：
  python scripts/data_quality_gate.py
"""
from __future__ import annotations
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 复用 harness_sync 的受追踪路径（若有），否则回退到核心数据文件清单
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    import harness_sync  # type: ignore
    TRACKED = list(getattr(harness_sync, "TRACKED_PATHS", []))
except Exception:
    TRACKED = [
        "data/crop_adapt_db.json",
        "data/zone_meta/global_zones.json",
        "data/preset_cities.json",
        "data/eval/zone_checks.json",
    ]

_DATA_EXT = (".json",)

# 这些文件允许为空（日志/回流类，真实数据到位前本就为空结构，属已知数据量缺口而非质量缺陷）
_ALLOW_EMPTY = {"data/feedback_log.json"}


def _load(path):
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        return None, f"文件不存在: {path}"
    try:
        with open(full, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # noqa: BLE001
        return None, f"JSON 解析失败: {e}"


def _check_crop_db(obj):
    issues = []
    zones = obj.get("zones", {}) if isinstance(obj, dict) else {}
    if not isinstance(zones, dict):
        issues.append("crop_adapt_db.zones 非字典")
        return issues
    fake_calib = 0
    temp_bad = 0
    for _zid, zdata in zones.items():
        crops = (zdata or {}).get("crops", []) if isinstance(zdata, dict) else []
        for c in crops:
            if not isinstance(c, dict):
                continue
            # 真实性红线：calibrated=true 必须有 measured_calibration 实证
            if c.get("calibrated") is True and not c.get("measured_calibration"):
                fake_calib += 1
            tr = c.get("temp_range_c")
            if isinstance(tr, list) and len(tr) == 2:
                lo, hi = tr
                if not (-60 <= lo <= hi <= 60):
                    temp_bad += 1
    if fake_calib:
        issues.append(f"发现 {fake_calib} 条 calibrated=true 但缺 measured_calibration（假校准标记）")
    if temp_bad:
        issues.append(f"发现 {temp_bad} 条温度区间越界（应为 -60~60℃）")
    return issues


def _check_precip_units(obj):
    """monthly_precip_mm 应为月内日均 mm/day，不得出现 >200 的疑似月累计误标。"""
    issues = []
    zones = obj.get("zones", {}) if isinstance(obj, dict) else {}
    bad = 0
    for _zid, zdata in (zones or {}).items():
        mp = (zdata or {}).get("monthly_precip_mm")
        if isinstance(mp, list):
            for v in mp:
                if isinstance(v, (int, float)) and v > 200:
                    bad += 1
    if bad:
        issues.append(f"发现 {bad} 个降水值 >200mm/day，疑似月累计误标（应为月内日均 mm/day）")
    return issues


def _check_preset_cities(obj):
    issues = []
    cities = obj if isinstance(obj, list) else (obj.get("cities") if isinstance(obj, dict) else None)
    if not isinstance(cities, list):
        issues.append("preset_cities 非列表结构")
        return issues
    missing_modeled = 0
    for c in cities:
        if isinstance(c, dict) and "modeled" not in c:
            missing_modeled += 1
    if missing_modeled:
        issues.append(f"{missing_modeled} 个城市缺 modeled 字段（单一数据源约定要求显式声明）")
    return issues


def run():
    results = []
    for rel in TRACKED:
        if not rel.endswith(_DATA_EXT):
            continue
        obj, err = _load(rel)
        if err:
            results.append((rel, "FAIL", [err]))
            continue
        issues = []
        if rel.endswith("crop_adapt_db.json"):
            issues += _check_crop_db(obj)
            issues += _check_precip_units(obj)
        elif rel.endswith("preset_cities.json"):
            issues += _check_preset_cities(obj)
        if obj in (None, {}, []) and rel not in _ALLOW_EMPTY:
            issues.append("文件为空结构")
        if issues:
            results.append((rel, "FAIL", issues))
        else:
            results.append((rel, "PASS", []))

    width = max([len(r[0]) for r in results] + [10])
    print("=" * (width + 12))
    print("数据质量门禁报告 (data_quality_gate)")
    print("=" * (width + 12))
    all_pass = True
    for rel, status, issues in results:
        print(f"[{status}] {rel.ljust(width)}")
        for i in issues:
            print(f"       - {i}")
            all_pass = False
    print("=" * (width + 12))
    print("结论: " + ("全部通过 ✅" if all_pass else "存在失败项 ❌"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run())
