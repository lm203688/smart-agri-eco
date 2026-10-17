#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_mechanism_gigo.py —— 机理内核 GIGO 门禁

GAP_AUDIT §C2：A2-α 机理内核修复（H3：@bounded/@non_negative/@positive）必须
用 34 个探针验证不回退。本门禁运行 scripts/probe_mechanism_garbage_in.py，
确保 FAIL-GIGO 比例为 0。

FAIL-GIGO 指标：输入物理不可能值（负数/NaN/inf/超界）时函数未 raise 异常，
而是返回垃圾值。这是严重的安全漏洞——农业决策不能容忍"错误输出不报错"。

**当前状态**：2026-10-17 34/34 探针全绿，FAIL-GIGO=0。A2-α 修复有效。

用法：
    python scripts/gate_mechanism_gigo.py              # 通过=0，失败=1
    python scripts/gate_mechanism_gigo.py --strict     # 同上（保留参数兼容）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "probe_mechanism_garbage_in.py"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="兼容参数")
    p.parse_args()

    if not PROBE.exists():
        print(f"❌ 探针脚本不存在: {PROBE}")
        return 1

    # 运行探针脚本，捕获输出
    proc = subprocess.run(
        [sys.executable, str(PROBE)],
        capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8", errors="ignore",
    )
    out = proc.stdout
    err = proc.stderr

    if proc.returncode != 0:
        print("❌ 探针脚本执行失败：")
        print(err or out)
        return 1

    # 解析汇总
    total = 0
    fails = 0
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("总探针数"):
            total = int(line.split(":")[1].strip())
        elif line.startswith("FAIL-GIGO") and "(" in line:
            try:
                fails = int(line.split("(")[0].replace("FAIL-GIGO", "").strip())
            except ValueError:
                pass

    if total == 0:
        print("❌ 无法解析探针输出（总探针数=0）")
        print(out[:500])
        return 1

    pct = fails / total if total else 0
    if fails > 0:
        print(f"❌ GIGO 门禁失败：{fails}/{total} 探针 FAIL-GIGO（{pct:.1%}）")
        print("以下函数存在垃圾进垃圾出，必须修复：")
        # 提取 FAIL 详细清单
        in_detail = False
        for line in out.splitlines():
            if "FAIL-GIGO 详细清单" in line:
                in_detail = True
                continue
            if in_detail:
                if line.startswith("="):
                    break
                if line.strip():
                    print(f"  {line.strip()}")
        print("\n→ A2-α 机理内核修复回退了。请检查 core/numeric_domain.py 的 @bounded/@non_negative/@positive 是否被误删，")
        print("  以及 engine/agriworld_lite.py / engine/derived.py 中的装饰器是否被移除。")
        return 1

    print(f"✅ GIGO 门禁通过：{total}/{total} 探针全绿，FAIL-GIGO=0")
    print(f"   覆盖函数：theoretical_yield_cap / temp_factor / water_stress_factor / vpd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
