#!/usr/bin/env python3
"""
audit_foundation.py — 项目地基六方向硬伤定量审计
直接扫描全量 Python 源码，输出可复核的数字。
"""
from pathlib import Path
import re, os, sys

ROOT = Path(__file__).resolve().parent.parent
files = list(ROOT.rglob("*.py"))
src = []
for f in files:
    if "__pycache__" in str(f):
        continue
    try:
        s = f.read_text(encoding="utf-8", errors="ignore")
    except (PermissionError, OSError):
        continue
    src.append((f, s))

print("=" * 60)
print("智慧农业生态 · 地基硬伤审计（六方向定量证据）")
print("=" * 60)
print(f"扫描范围: {len(files)} 个 .py 文件 (排除 __pycache__ 后 {len(src)} 个)")

# --- 方向1: 异常吞失败 ---
print("\n[方向1] 异常吞失败 (except:pass / except:return None / except:return {})")
bare_pass_hits = 0
files_with_bare = []
pattern1 = re.compile(r"except\s*:\s*(pass|return\s+None|return\s*\{\})\b")
for f, s in src:
    hits = pattern1.findall(s)
    if hits:
        files_with_bare.append(str(f.relative_to(ROOT)))
        bare_pass_hits += len(hits)
print(f"  命中: {bare_pass_hits} 处, 涉及文件: {len(files_with_bare)} 个")
for f in files_with_bare[:10]:
    print(f"    - {f}")

# --- 方向2: 原子写 ---
print("\n[方向2] 持久化原子性 (open(...,'w') 直写 vs os.replace)")
direct_writes = 0
os_replace_hits = 0
files_direct = 0
files_replace = 0
for f, s in src:
    dw = len(re.findall(r"open\([^)]*['\"]w", s))
    orh = s.count("os.replace(")
    if dw:
        files_direct += 1
        direct_writes += dw
    if orh:
        files_replace += 1
        os_replace_hits += orh
total = direct_writes + os_replace_hits
print(f"  open(...,'w') 直写: {direct_writes} 处 (涉及 {files_direct} 文件)")
print(f"  os.replace(...) 原子写: {os_replace_hits} 处 (涉及 {files_replace} 文件)")
if total:
    print(f"  原子写占比: {os_replace_hits/total:.1%}")

# --- 方向3: 不可复现 ---
print("\n[方向3] 不可复现 (datetime.now()/time.time()/random.sample 直接调用)")
non_det = {"datetime.now()": 0, "time.time()": 0, "random.sample": 0}
files_time = []
for f, s in src:
    n1 = s.count("datetime.now()")
    n2 = s.count("time.time()")
    n3 = s.count("random.sample")
    non_det["datetime.now()"] += n1
    non_det["time.time()"] += n2
    non_det["random.sample"] += n3
    if n1 or n2 or n3:
        files_time.append(str(f.relative_to(ROOT)))
print(f"  datetime.now(): {non_det['datetime.now()']} 处")
print(f"  time.time():    {non_det['time.time()']} 处")
print(f"  random.sample:  {non_det['random.sample']} 处")
print(f"  合计: {sum(non_det.values())} 处, 涉及文件: {len(files_time)} 个")

# --- 方向4: 数值边界 ---
# H3 加固：识别 @bounded/@known_enum/@positive/@non_negative/@finite/@not_none/@not_empty_string/@monotone_constraints 装饰器
# 只扫生产代码目录（engine/, agent/, core/, mcp/, bp_screen/），scripts/ 里的辅助/参考实现不参与统计
print("\n[方向4] 核心数值函数边界校验 (VPD / temp_factor / theoretical_yield / water_stress / npot_factor)")
targets = ["def vpd", "def temp_factor", "def theoretical_yield", "def water_stress", "def npot_factor"]
PROD_DIRS = ("engine", "agent", "core", "mcp", "bp_screen")
DECORATOR_PATTERNS = (
    "@bounded", "@bounded_each", "@known_enum", "@positive",
    "@non_negative", "@finite", "@not_none", "@not_empty_string",
    "@monotone_constraints",
)
boundary_ok = 0
boundary_all = 0
detail = []
for f, s in src:
    rel = str(f.relative_to(ROOT))
    # 只统计生产目录，忽略 scripts/ 中的参考/探针实现
    if not rel.split(os.sep)[0] in PROD_DIRS:
        continue
    for fn in targets:
        if fn not in s:
            continue
        boundary_all += 1
        idx = s.find(fn)
        # 装饰器写在 def 之前，向上扫 400 字符
        head = s[max(0, idx - 400):idx]
        has_decorator = any(p in head for p in DECORATOR_PATTERNS)
        body = s[idx:idx + 800]
        has_raise = ("raise " in body) or ("ValueError" in body)
        has_check = has_decorator or has_raise
        if has_check:
            boundary_ok += 1
        detail.append((fn, rel, has_check))
for fn, fp, ok in detail:
    mark = "OK " if ok else "MISS"
    print(f"  [{mark}] {fn:<28s} @ {fp}")
print(f"  覆盖率: {boundary_ok}/{boundary_all}")

# --- 方向5: 占位 ---
# 排除测试函数名（test_*、*Test）与 scripts/ 内的审计脚本自身；只统计生产代码目录
print("\n[方向5] 占位/存根函数混入机理内核")
placeholder_hits = []
for f, s in src:
    rel = str(f.relative_to(ROOT))
    # 只统计生产目录（engine/agent/core/mcp/bp_screen）
    if not rel.split(os.sep)[0] in PROD_DIRS:
        continue
    for m in re.finditer(r"def\s+(\w*(?:placeholder|stub|TODO|FIXME)\w*)", s, re.I):
        fname = m.group(1)
        # 排除测试函数名（test_no_placeholder 等）
        if fname.startswith("test_") or fname.endswith("Test"):
            continue
        placeholder_hits.append((fname, rel, s.count("\n", 0, m.start())+1))
for name, fp, line in placeholder_hits:
    print(f"  - {name} @ {fp}:{line}")
print(f"  合计: {len(placeholder_hits)} 个（生产代码目录，排除 test_ 前缀）")

# --- 方向6: MCP 参数校验 ---
# H5 加固：用 AST 提取 _tool_* handler，与 TOOL_SCHEMA_xxx 定义 / validate_tool_args 调用对照
print("\n[方向6] MCP 工具参数校验覆盖率")
mcp_path = ROOT / "mcp" / "server.py"
if mcp_path.exists():
    try:
        import ast as _ast
        tree = _ast.parse(mcp_path.read_text(encoding="utf-8", errors="ignore"),
                           filename=str(mcp_path))
        tool_fns = [n.name for n in tree.body
                    if isinstance(n, _ast.FunctionDef) and n.name.startswith("_tool_")]
        schema_defs = set()
        for n in tree.body:
            if isinstance(n, _ast.Assign):
                for t in n.targets:
                    if isinstance(t, _ast.Name) and t.id.startswith("TOOL_SCHEMA_"):
                        schema_defs.add(t.id)
        # 检查每个 tool 是否有 schema 定义 + validate_tool_args 调用
        covered = 0
        for fn in tool_fns:
            # 找对应函数
            node = next((n for n in tree.body
                         if isinstance(n, _ast.FunctionDef) and n.name == fn), None)
            if node is None:
                continue
            # 白名单：_tool_server_card 纯元数据查询，无用户参数
            if fn == "_tool_server_card":
                covered += 1
                continue
            schema_key = "TOOL_SCHEMA_" + fn.replace("_tool_", "")
            has_schema = schema_key in schema_defs
            has_validate = any(
                isinstance(x, _ast.Call) and isinstance(x.func, _ast.Name)
                and x.func.id == "validate_tool_args"
                for x in _ast.walk(node)
            )
            if has_schema and has_validate:
                covered += 1
        total = len(tool_fns)
        print(f"  _tool_* handler 数: {total}")
        print(f"  有 TOOL_SCHEMA + validate_tool_args: {covered}")
        print(f"  覆盖率: {covered/total:.1%}" if total else "  无 handler")
    except Exception as e:
        print(f"  AST 解析失败: {e}；退回字符串匹配")
        m = mcp_path.read_text(encoding="utf-8", errors="ignore")
        print(f"  _tool_* handler 数: {len(re.findall(r'^def\\s+_tool_\\w+', m, re.M))}")
else:
    print("  mcp/server.py 不存在")

print("\n" + "=" * 60)
print("审计完成")
print("=" * 60)
