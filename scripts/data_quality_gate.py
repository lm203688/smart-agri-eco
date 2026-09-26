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


# --- 数据标准规范校验（DataFlow「数据标准规范制定」→ 壁垒③ 可执行配置）---
# 定义核心数据文件的最小 schema 契约，使 MCP 分发后消费方可确定性解析。
# 仅校验「结构合法性」，不臆造字段值；发现不合规即暴露真实数据缺口。

def _check_global_zones_schema(obj):
    issues = []
    if not isinstance(obj, dict) or "zones" not in obj:
        issues.append("global_zones 缺少顶层 zones")
        return issues
    zones = obj["zones"]
    if not isinstance(zones, list):
        issues.append("zones 非列表")
        return issues
    for i, z in enumerate(zones):
        if not isinstance(z, dict):
            issues.append(f"zones[{i}] 非对象")
            continue
        for req in ("zone_id", "zone_name", "temperature_range", "frost_risk"):
            if req not in z:
                issues.append(f"zones[{i}] 缺必需字段 {req}")
        tr = z.get("temperature_range")
        if tr is not None and not (
            isinstance(tr, dict)
            and isinstance(tr.get("min_c"), (int, float))
            and isinstance(tr.get("max_c"), (int, float))
        ):
            issues.append(f"zones[{i}] temperature_range 结构非法（须含 min_c/max_c 数值）")
        if "frost_risk" in z and not isinstance(z["frost_risk"], bool):
            issues.append(f"zones[{i}] frost_risk 须为布尔")
    return issues


def _check_preset_cities_schema(obj):
    issues = _check_preset_cities(obj)
    cities = obj if isinstance(obj, list) else (obj.get("cities") if isinstance(obj, dict) else None)
    if not isinstance(cities, list):
        return issues
    for i, c in enumerate(cities):
        if not isinstance(c, dict):
            issues.append(f"cities[{i}] 非对象")
            continue
        for req in ("name", "lat", "lon", "modeled"):
            if req not in c:
                issues.append(f"cities[{i}] 缺 {req} 字段")
        lat, lon = c.get("lat"), c.get("lon")
        if not (isinstance(lat, (int, float)) and -90 <= lat <= 90):
            issues.append(f"cities[{i}] lat 越界/非法: {lat!r}")
        if not (isinstance(lon, (int, float)) and -180 <= lon <= 180):
            issues.append(f"cities[{i}] lon 越界/非法: {lon!r}")
        if "modeled" in c and not isinstance(c["modeled"], bool):
            issues.append(f"cities[{i}] modeled 须为布尔")
    return issues


def _check_zone_checks_schema(obj):
    issues = []
    if not isinstance(obj, list):
        issues.append("zone_checks 非列表结构")
        return issues
    for i, e in enumerate(obj):
        if not isinstance(e, dict):
            issues.append(f"[{i}] 非对象")
            continue
        for req in ("lat", "lon", "expected_zone"):
            if req not in e:
                issues.append(f"[{i}] 缺 {req} 字段")
        if "modeled" in e and not isinstance(e["modeled"], bool):
            issues.append(f"[{i}] modeled 须为布尔")
    return issues


def _check_crop_db_schema(obj):
    issues = _check_crop_db(obj)
    zones = obj.get("zones", {}) if isinstance(obj, dict) else {}
    if not isinstance(zones, dict):
        issues.append("crop_adapt_db.zones 非字典（zone_id 须为键）")
        return issues
    for zid, zdata in zones.items():
        crops = (zdata or {}).get("crops", []) if isinstance(zdata, dict) else []
        for j, c in enumerate(crops):
            if not isinstance(c, dict):
                issues.append(f"zone {zid} crop[{j}] 非对象")
                continue
            if "crop" not in c:
                issues.append(f"zone {zid} crop[{j}] 缺 crop 字段")
            if "calibrated" not in c:
                issues.append(f"zone {zid} crop[{j}] 缺 calibrated 字段")
            elif not isinstance(c["calibrated"], bool):
                issues.append(f"zone {zid} crop[{j}] calibrated 须为布尔")
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
            issues += _check_crop_db_schema(obj)
        elif rel.endswith("preset_cities.json"):
            issues += _check_preset_cities_schema(obj)
        elif rel.endswith("global_zones.json"):
            issues += _check_global_zones_schema(obj)
        elif rel.endswith("zone_checks.json"):
            issues += _check_zone_checks_schema(obj)
        if obj in (None, {}, []) and rel not in _ALLOW_EMPTY:
            issues.append("文件为空结构")
        if issues:
            results.append((rel, "FAIL", issues))
        else:
            results.append((rel, "PASS", []))

    # 额外已知核心文件（eval 真值表）：不污染 harness_sync 声明区，
    # 仅做 schema 结构校验，守护「真值本身合法」这一数据质量底线。
    checked = {r[0] for r in results}
    for rel in ("data/eval/zone_checks.json",):
        if rel in checked:
            continue
        if not rel.endswith(_DATA_EXT):
            continue
        obj, err = _load(rel)
        if err:
            results.append((rel, "FAIL", [err]))
            continue
        issues = _check_zone_checks_schema(obj)
        results.append((rel, "PASS" if not issues else "FAIL", issues))

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
