#!/usr/bin/env python3
"""查漏补缺扫描 · B：真实单测数量 vs README 声称数字"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
test_files = sorted(ROOT.glob("scripts/test_*.py")) + sorted(ROOT.glob("scripts/*_test.py"))
total_cases = 0
total_methods = 0
per_file = []
for f in test_files:
    try:
        src = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    # 统计 def test_ 方法数
    cases = len(re.findall(r"^\s*def\s+test_\w+", src, re.M))
    # 统计 assert 数（粗略）
    asserts = len(re.findall(r"\bassert\b", src))
    # 统计类数
    classes = len(re.findall(r"^\s*class\s+\w+", src, re.M))
    total_cases += cases
    total_methods += classes
    per_file.append((f.name, cases, asserts, classes))

print("=== 真实单测统计 ===")
print(f"测试文件数: {len(test_files)}")
print(f"def test_* 方法总数: {total_cases}")
print(f"assert 语句总数: {sum(x[2] for x in per_file)}")
print()
for name, cases, asserts, classes in sorted(per_file, key=lambda x: -x[1]):
    print(f"  {name:<42s} test={cases:>3}  assert={asserts:>4}  class={classes}")

print("\n=== 与 README 声称数字对比 ===")
print("  README 第42行:  '单测 744 OK'")
print("  README 第241行: '**700+ 项** unittest'")
print("  README 第417行: '556 项用例全过'")
print("  README 第456行: '回归十八项（556 项单测 + MCP 自测）'")
print(f"  实际 def test_* 方法总数: {total_cases}")
print(f"  -> 744 / 700+ / 556 三个数字彼此矛盾，且与实际 {total_cases} 不一致")
