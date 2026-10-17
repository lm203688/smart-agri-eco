#!/usr/bin/env python3
"""查漏补缺扫描 · D：代码卫生（地基审计 H1-H6 之外的漏点）

覆盖：
  D1 循环依赖（import 图 + DFS 环检测）
  D2 print 滥用（应用层应走 logging）
  D3 TODO/FIXME/stub/placeholder/XXX 残留（含注释）
  D4 死代码（defined but never referenced 的 top-level 函数）
  D5 魔法数字（核心数值无常量声明）
"""
import ast, re
from pathlib import Path
from collections import defaultdict, deque

ROOT = Path(__file__).resolve().parent.parent
py_files = [f for f in ROOT.rglob("*.py")
            if "__pycache__" not in str(f) and "_archive" not in str(f)]

# ---------------- D1 循环依赖 ----------------
print("="*70)
print("D1 · 模块间循环依赖")
print("="*70)
import_graph = defaultdict(set)
mod_of = {}
for f in py_files:
    rel = f.relative_to(ROOT)
    mod = ".".join(rel.with_suffix("").parts)
    mod_of[f] = mod
    try:
        tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # 仅追踪项目内模块
            top = node.module.split(".")[0]
            if top in {p.parts[0] for p in py_files}:
                import_graph[mod].add(node.module)
        elif isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split(".")[0]
                if top in {p.parts[0] for p in py_files}:
                    import_graph[mod].add(n.name)

# 仅保留同项目内可达边
project_mods = set(mod_of.values())
edges = {k: {v for v in vs if v in project_mods} for k, vs in import_graph.items()}

# Tarjan / 朴素 DFS 环检测
WHITE, GRAY, BLACK = 0, 1, 2
color = defaultdict(int)
cycles = []
def dfs(u, stack):
    color[u] = GRAY
    stack.append(u)
    for v in edges.get(u, ()):
        if color[v] == GRAY:
            # 发现环
            idx = stack.index(v)
            cycles.append(stack[idx:] + [v])
        elif color[v] == WHITE:
            dfs(v, stack)
    stack.pop()
    color[u] = BLACK
for m in edges:
    if color[m] == WHITE:
        dfs(m, [])
if cycles:
    print(f"发现 {len(cycles)} 个循环依赖环:")
    for c in cycles[:20]:
        print(f"  ⚠ {c}")
else:
    print("  ✓ 未发现循环依赖（import 图无环）")

# ---------------- D2 print 滥用 ----------------
print("\n"+"="*70)
print("D2 · print 语句滥用（应用层应走 logging）")
print("="*70)
print_hits = defaultdict(int)
print_files = 0
for f in py_files:
    try:
        src = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    # 排除 __main__ 演示块里的 print（用 AST 判断是否在 if __name__=='__main__' 内）
    try:
        tree = ast.parse(src)
    except Exception:
        continue
    main_only = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            t = node.test
            if isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__":
                for n in ast.walk(node):
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print":
                        main_only.add(id(n))
    cnt = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            if id(node) not in main_only:
                cnt += 1
    if cnt:
        print_hits[str(f.relative_to(ROOT))] = cnt
        print_files += 1
print(f"print 滥用（非 __main__ 块）涉及 {print_files} 个文件，合计 {sum(print_hits.values())} 处")
for fp, c in sorted(print_hits.items(), key=lambda x: -x[1])[:20]:
    print(f"  {c:>4}  {fp}")

# ---------------- D3 TODO/FIXME/stub/placeholder/XXX ----------------
print("\n"+"="*70)
print("D3 · TODO/FIXME/stub/placeholder/XXX 残留")
print("="*70)
markers = ["TODO", "FIXME", "XXX", "HACK", "stub", "placeholder", "KLUDGE", "BUG"]
marker_count = defaultdict(int)
marker_loc = defaultdict(list)
for f in py_files:
    try:
        src = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for line_no, line in enumerate(src.split("\n"), 1):
        up = line.upper()
        for mk in markers:
            if re.search(rf"\b{mk}\b", up):
                marker_count[mk] += 1
                marker_loc[mk].append(f"{f.relative_to(ROOT)}:{line_no}")
                break
total_markers = sum(marker_count.values())
print(f"合计 {total_markers} 处标记（含注释）:")
for mk, c in sorted(marker_count.items(), key=lambda x: -x[1]):
    print(f"  {mk:<12s} {c:>4} 处")
    for loc in marker_loc[mk][:5]:
        print(f"       {loc}")

# ---------------- D4 死代码（top-level 函数未引用） ----------------
print("\n"+"="*70)
print("D4 · 可能死代码（top-level def 无内部/外部引用，排除测试/__main__）")
print("="*70)
# 收集所有被调用名
called = set()
defs = {}
for f in py_files:
    if f.name.startswith("test_") or "test" in f.name:
        continue
    try:
        src = f.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except Exception:
        continue
    mod = defs.setdefault(str(f.relative_to(ROOT)), [])
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            mod.append(node.name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)
dead = 0
for fp, names in defs.items():
    for n in names:
        if n not in called and not n.startswith("_") and n not in ("main",):
            # 排除明显的入口/dunder
            print(f"  ? {fp}: {n}  (def 但未被任何调用点引用，需人工确认)")
            dead += 1
print(f"候选死代码（需人工复核）: {dead} 处")

# ---------------- D5 魔法数字（核心数值）----------------
print("\n"+"="*70)
print("D5 · 魔法数字密度（核心数值无常量声明）")
print("="*70)
magic_hits = defaultdict(int)
for f in py_files:
    if f.name.startswith("test_"):
        continue
    try:
        src = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    # 找出现在表达式中、绝对值 >= 2 的整数/浮点（粗略）
    for m in re.finditer(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w.])", src):
        num = m.group(1)
        val = float(num)
        if abs(val) >= 2 and "." not in num:
            magic_hits[str(f.relative_to(ROOT))] += 1
print("含魔法数字（>=2 整数）最多的文件 Top 15:")
for fp, c in sorted(magic_hits.items(), key=lambda x: -x[1])[:15]:
    print(f"  {c:>4}  {fp}")
print("\n（注：魔法数字密度高是可读性与可维护性的细节缺口，")
print("  但属 P2 级，不影响正确性；此处仅量化，不要求立即全改）")
