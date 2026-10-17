#!/usr/bin/env python3
"""
map_direct_writes.py — 98 处 open(..., 'w') 直写点定位

按目录聚合，输出：每个文件有多少处、写的是什么类型数据（JSON/文本/二进制）。
目的：让"H1 持久化非原子"从抽象数字变成一张具体清单，
      决策层可以按目录优先级排修复顺序。
"""
from pathlib import Path
import re
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
files = list(ROOT.rglob("*.py"))

# 每个文件的所有 open(..., 'w') 或 open(..., 'wb') 命中，附带行号
hits_by_dir = defaultdict(list)
hits_by_file = defaultdict(list)
total = 0

for f in files:
    if "__pycache__" in str(f):
        continue
    try:
        lines = f.read_text(encoding="utf-8", errors="ignore").split("\n")
    except (PermissionError, OSError):
        continue
    rel = f.relative_to(ROOT)
    top_dir = str(rel.parts[0]) if len(rel.parts) > 1 else "."
    for i, line in enumerate(lines, 1):
        # open(..., 'w') / open(..., 'wb') / open(..., "w") 等
        if re.search(r"open\([^)]*['\"](w|wb|w\+|a)['\"]", line):
            # 判断上下文是否可能是数据文件
            line_stripped = line.strip()
            hits_by_dir[top_dir].append((str(rel), i, line_stripped[:120]))
            hits_by_file[str(rel)].append(i)
            total += 1

print("=" * 72)
print(f"H1 直写点分布 — 共 {total} 处 open(..., 'w') / open(..., 'a')")
print("=" * 72)

# 按目录汇总
print("\n按目录聚合（修复优先级：数据文件 > 日志 > 临时文件）：")
dir_counts = {d: len(v) for d, v in hits_by_dir.items()}
for d, c in sorted(dir_counts.items(), key=lambda x: -x[1]):
    marker = "🚨" if d in ("data", "engine", "agent", "core", "mcp") else ("🟡" if d in ("scripts",) else "  ")
    print(f"  {marker} {d:<20s} {c:>3} 处")

# 高危文件 top 20（涉及 data/ engine/ agent/ core/ mcp/）
print("\n高危文件 Top 20（按直写点数量排序，全部位于数据/机理/Agent 核心目录）：")
priority_files = [
    (fp, ln) for fp, ln in hits_by_file.items()
    if any(d in fp for d in ("data", "engine", "agent", "core", "mcp", "bp_screen"))
]
priority_files.sort(key=lambda x: -len(x[1]))
for fp, lines in priority_files[:20]:
    print(f"  🚨 {fp:<50s}  {len(lines):>2} 处  (行号: {lines[:6]}{'...' if len(lines)>6 else ''})")

# 全部清单：写操作上下文，帮用户分类
print("\n具体写操作上下文（前 30 处，用于判断是否写入持久化数据）：")
for d in sorted(hits_by_dir.keys()):
    for fp, ln, txt in hits_by_dir[d][:6]:
        # 分类
        if '.json' in txt or 'json.dump' in txt or '.json"' in txt:
            kind = "JSON 数据"
        elif 'open(' in txt and '.log' in txt:
            kind = "日志"
        elif '.tmp' in txt or 'temp' in txt:
            kind = "临时"
        elif '.txt' in txt:
            kind = "文本"
        else:
            kind = "?"
        print(f"  [{kind:<10s}] {fp}:{ln}  |  {txt[:80]}")
    if len(hits_by_dir[d]) > 6:
        print(f"  ... {d} 还有 {len(hits_by_dir[d])-6} 处")
        break  # 只展开第一个目录，其余用聚合数

print("\n" + "=" * 72)
print(f"总计: {total} 处直写点，涉及 {len(hits_by_file)} 个文件")
print("=" * 72)
