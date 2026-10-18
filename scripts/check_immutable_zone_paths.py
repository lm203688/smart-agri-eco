#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_immutable_zone_paths.py —— 不可进化区路径存在性门禁

解决 GAP_AUDIT §A4：CORE_OBJECTIVE §10.1 不可进化区清单中的路径
必须真实存在，否则 evolution.py 的保护逻辑可能静默跳过。

检查项：
  1. CORE_OBJECTIVE §10.1 表格中列出的每个路径必须 exists()
  2. .well-known/evolution_zones.json 的 immutable 列表必须与 CORE_OBJECTIVE 一致

用法：
    python scripts/check_immutable_zone_paths.py
    python scripts/check_immutable_zone_paths.py --check  # CI 用

退出码：0 = 通过；1 = 不通过。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_OBJ = ROOT / "docs" / "CORE_OBJECTIVE.md"
EVO_ZONES = ROOT / ".well-known" / "evolution_zones.json"


def extract_core_objective_immutable_paths() -> list[str]:
    """从 CORE_OBJECTIVE §10.1 表格提取不可进化区路径。"""
    if not CORE_OBJ.exists():
        print(f"❌ 找不到 {CORE_OBJ}")
        return []

    text = CORE_OBJ.read_text(encoding="utf-8")

    # 找 §10.1 区间里「不可进化区」那张表：从 §10.1 到「可进化区」标记为止
    m = re.search(r"###\s*10\.1.*?(?=\n\*\*可进化区|\n###\s*10\.2)", text, re.DOTALL)
    if not m:
        print("❌ 找不到 CORE_OBJECTIVE §10.1 区间")
        return []

    section = m.group(0)
    paths: list[str] = []
    for line in section.split("\n"):
        # 匹配表格数据行：| `path` | description |
        pm = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if not pm:
            continue
        token = pm.group(1).strip()
        # 跳过表头（资产 / 路径）与分隔行
        if token in ("资产", "路径", "Asset", "Path"):
            continue
        if set(token) <= set("-"):  # 分隔行 |---|---|
            continue
        # 只保留像路径的 token（含斜杠，或已知扩展名），过滤掉表头误匹配
        if "/" in token or token.endswith((".py", ".json", ".md", ".yml", ".yaml")):
            paths.append(token)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def check_evolution_zones_consistency(core_paths: list[str]) -> list[str]:
    """检查 evolution_zones.json 与 CORE_OBJECTIVE 的一致性。"""
    errs = []
    if not EVO_ZONES.exists():
        errs.append(f"❌ 找不到 {EVO_ZONES}")
        return errs

    try:
        zones = json.loads(EVO_ZONES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errs.append(f"❌ evolution_zones.json 解析失败: {e}")
        return errs

    # 读取 immutable_core.assets[].path（evolution_zones.json 的真实 schema）
    immutable_core = zones.get("immutable_core")
    if not isinstance(immutable_core, dict):
        errs.append("❌ evolution_zones.json 缺少 immutable_core 对象")
        return errs
    assets = immutable_core.get("assets")
    if not isinstance(assets, list):
        errs.append("❌ evolution_zones.json immutable_core.assets 不是数组")
        return errs

    evo_immutable = {a["path"] for a in assets if isinstance(a, dict) and "path" in a}
    core_immutable = set(core_paths)

    # 只检查文件路径（目录以 / 结尾的不做精确匹配）
    core_files = {p for p in core_immutable if not p.endswith("/")}
    evo_files = {p for p in evo_immutable if not p.endswith("/")}

    missing_in_evo = core_files - evo_files
    if missing_in_evo:
        errs.append(
            f"❌ CORE_OBJECTIVE §10.1 有但 evolution_zones.json immutable 没有: "
            f"{sorted(missing_in_evo)}"
        )

    extra_in_evo = evo_files - core_files
    if extra_in_evo:
        errs.append(
            f"⚠  evolution_zones.json immutable 有但 CORE_OBJECTIVE §10.1 没有: "
            f"{sorted(extra_in_evo)}"
        )

    return errs


def main() -> int:
    errs: list[str] = []

    # 1. 提取 CORE_OBJECTIVE 不可进化区路径
    core_paths = extract_core_objective_immutable_paths()
    if not core_paths:
        errs.append("❌ 未能从 CORE_OBJECTIVE §10.1 提取到任何路径")
    else:
        print(f"✅ CORE_OBJECTIVE §10.1 提取到 {len(core_paths)} 个路径")

    # 2. 检查每个路径是否存在
    missing = []
    for p in core_paths:
        full = ROOT / p
        if p.endswith("/"):
            # 目录检查
            if not full.is_dir():
                missing.append(p)
        else:
            # 文件检查
            if not full.exists():
                missing.append(p)

    if missing:
        errs.append(f"❌ 不可进化区清单中的路径不存在: {missing}")
    else:
        print("✅ 所有不可进化区路径均存在")

    # 3. 检查 evolution_zones.json 一致性
    if core_paths:
        evo_errs = check_evolution_zones_consistency(core_paths)
        errs.extend(evo_errs)
        if not evo_errs:
            print("✅ evolution_zones.json 与 CORE_OBJECTIVE §10.1 一致")

    # 输出结果
    if errs:
        print("\n❌ 不可进化区路径校验失败：")
        for e in errs:
            print(f"   {e}")
        return 1

    print("\n✅ 不可进化区路径校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
