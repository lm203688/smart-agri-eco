#!/usr/bin/env python3
"""scripts/gate_no_direct_time.py —— H2 防回退门禁：禁止生产代码新增时间/随机直调

FOUNDATION_AUDIT H2 要求：生产代码（engine/agent/core/mcp/bp_screen）不得直接调用
datetime.now() / datetime.datetime.now() / time.time() / random.random() 等，
必须走 core.clock.CLOCK 或 core.seed.Random(stable_seed(...)) 以保证可复现。

用法：
    python scripts/gate_no_direct_time.py                  # 扫描并报错
    python scripts/gate_no_direct_time.py --json           # JSON 输出（供 CI）

判定：
- 命中即 FAIL，exit 1
- SKIP 白名单：core/clock.py（自身是 CLOCK 实现）、core/seed.py（自身是 Random 实现）
- 白名单文件里允许这些调用作为底层实现；其他地方一律禁止
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROD_DIRS = ["engine", "agent", "core", "mcp", "bp_screen"]
# 白名单：core/clock.py 和 core/seed.py 是底层实现，本身需要调用真实 API。
# bp_screen/db.py 是数据库审计模块——审计日志的 created/finished 时间戳必须是真实
# 墙钟时间（用户查 DB 时要看真实时间），且该文件受 test_core_modules_use_only_stdlib
# 约束不能 import core 包，故豁免。
SKIP_FILES = {"core/clock.py", "core/seed.py", "bp_screen/db.py"}

# 违规模式：模块限定调用（避免误伤 time.time_ns、datetime.timezone 等）
BAD_PATTERNS = {
    "datetime.now": re.compile(r"\bdatetime\.now\("),
    "datetime.datetime.now": re.compile(r"\bdatetime\.datetime\.now\("),
    "datetime.utcnow": re.compile(r"\bdatetime\.utcnow\("),
    "datetime.datetime.utcnow": re.compile(r"\bdatetime\.datetime\.utcnow\("),
    "time.time": re.compile(r"\btime\.time\("),
    "random.random": re.compile(r"\brandom\.random\("),
    "random.sample": re.compile(r"\brandom\.sample\("),
    "random.choice": re.compile(r"\brandom\.choice\("),
    "random.randint": re.compile(r"\brandom\.randint\("),
    "random.seed": re.compile(r"\brandom\.seed\("),
}


def scan_file(path: Path) -> list:
    """扫描单个 .py 文件，返回违规列表。"""
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    if rel in SKIP_FILES:
        return []
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    violations = []
    for name, pat in BAD_PATTERNS.items():
        for m in pat.finditer(src):
            line_no = src.count("\n", 0, m.start()) + 1
            violations.append({
                "file": rel,
                "line": line_no,
                "pattern": name,
                "match": m.group(0),
            })
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="H2 防回退门禁：禁止生产代码直调时间/随机 API")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    all_violations = []
    scanned = 0
    for d in PROD_DIRS:
        dp = ROOT / d
        if not dp.exists():
            continue
        for py in dp.rglob("*.py"):
            scanned += 1
            vs = scan_file(py)
            all_violations.extend(vs)

    if args.json:
        print(json.dumps({
            "gate": "no_direct_time",
            "scanned_files": scanned,
            "violations": len(all_violations),
            "details": all_violations,
            "status": "PASS" if not all_violations else "FAIL",
        }, ensure_ascii=False, indent=2))
    else:
        if not all_violations:
            print(f"✅ gate_no_direct_time PASS: 扫描 {scanned} 个文件，0 处直调")
            print(f"   SKIP 白名单: {sorted(SKIP_FILES)}")
            return 0
        print(f"❌ gate_no_direct_time FAIL: 扫描 {scanned} 个文件，{len(all_violations)} 处直调")
        for v in all_violations:
            print(f"   {v['file']}:{v['line']}: {v['pattern']} ({v['match']})")
        print("\n修复方案：")
        print("  - datetime.datetime.now()  →  CLOCK.now()")
        print("  - datetime.now()            →  CLOCK.now()")
        print("  - time.time()               →  CLOCK.time()")
        print("  - random.random/sample/...  →  Random(stable_seed(...)).random()/sample()/...")
        print("  详见 core/clock.py 与 core/seed.py 模块文档。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
