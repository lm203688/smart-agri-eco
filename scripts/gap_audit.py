#!/usr/bin/env python3
"""
gap_audit.py —— 项目查漏补缺 14 项机械核对

对应 docs/GAP_AUDIT_2026-10-17.md §1 的核对清单。
运行本脚本可复核报告中的每一个数字。

用法：
    python scripts/gap_audit.py
"""
from __future__ import annotations

import json
import re
import datetime as dt
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = "OK  "
FAIL = "MISS"
WARN = "WARN"


def hr(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# 1. A2A Card skill 数 vs MCP 工具数 vs registry
# ---------------------------------------------------------------------------
hr("[1] A2A Card / MCP / registry 三方数字一致性")
card = _load(ROOT / ".well-known/agent.json", {}) or {}
# A2A Card 中 skills[] 的每一项 id 就是 MCP 工具名（"agri_xxx"），
# 因此 Card.skills 与 MCP 工具数对齐；skills/registry 与 manifest.skills.count 才是"人读技能目录"。
# 两套语义必须分别对齐，不得混在一起判定。
n_card = len(card.get("skills", []))
n_card_tools = len(card.get("tools", []))

m = (ROOT / "mcp/server.py").read_text(encoding="utf-8", errors="ignore")
n_fn = len(re.findall(r"^def _tool_(\w+)\s*\(", m, re.M))
n_reg = len(re.findall(r'"name"\s*:\s*"agri_\w+"', m))

registry = [f for f in (ROOT / "skills/registry").glob("*.json") if f.name != "schema.json"]
n_skill = len(registry)

manifest = _load(ROOT / "harness/manifest.json", {}) or {}
n_manifest_skill = manifest.get("skills", {}).get("count", "?")
n_manifest_tool = manifest.get("mcp", {}).get("tool_count", "?")

print(f"  A2A Card skills        : {n_card}  (语义=MCP 工具映射)")
print(f"  A2A Card tools         : {n_card_tools}  (独立声明，可为 0)")
print(f"  MCP _tool_* 函数       : {n_fn}")
print(f"  MCP TOOLS 注册表       : {n_reg}")
print(f"  skills/registry 文件数 : {n_skill}  (语义=人读技能目录)")
print(f"  manifest.skills.count  : {n_manifest_skill}")
print(f"  manifest.mcp.tool_count: {n_manifest_tool}")

# 工具口径：Card.skills（工具映射）应与 MCP 函数数、TOOLS 注册表、manifest.mcp.tool_count 四者一致
consistent = len({n_card, n_fn, n_reg, n_manifest_tool}) == 1
# 技能口径：registry 文件数与 manifest.skills.count 应一致
skill_consistent = (n_skill == n_manifest_skill)
print(f"  → 工具数一致: {PASS if consistent else FAIL}  "
      f"(Card.skills {n_card} vs MCP fn {n_fn} vs TOOLS {n_reg} vs manifest {n_manifest_tool})")
print(f"  → 技能数一致: {PASS if skill_consistent else FAIL}  "
      f"(registry {n_skill} vs manifest {n_manifest_skill})")

# ---------------------------------------------------------------------------
# 2. 法务三字段 + license=unknown
# ---------------------------------------------------------------------------
hr("[2] 法务三字段补齐率 + license=unknown")
files = sorted((ROOT / "data/env_recipes").glob("*.json"))
tot = lic = qual = trial = 0
lic_vals = Counter()
complete = 0
for f in files:
    d = _load(f, {}) or {}
    srcs = d.get("sources") or []
    ok = bool(srcs)
    for s in srcs:
        tot += 1
        if s.get("source_license"): lic += 1
        else: ok = False
        if s.get("data_quality"): qual += 1
        else: ok = False
        if s.get("trial_location"): trial += 1
        else: ok = False
        lic_vals[s.get("license", "(missing)")] += 1
    if ok: complete += 1
print(f"  配方文件: {len(files)}   sources 条目: {tot}")
print(f"  source_license: {lic}/{tot} ({lic/max(tot,1):.1%})")
print(f"  data_quality  : {qual}/{tot} ({qual/max(tot,1):.1%})")
print(f"  trial_location: {trial}/{tot} ({trial/max(tot,1):.1%})")
print(f"  三字段齐全文件: {complete}/{len(files)}")
unknown = lic_vals.get("unknown", 0)
print(f"  license=unknown: {unknown} 条  {FAIL if unknown else PASS}")
print(f"  license 取值: {dict(lic_vals)}")

# ---------------------------------------------------------------------------
# 3. 不可进化区路径存在性
# ---------------------------------------------------------------------------
hr("[3] CORE_OBJECTIVE §10.1 不可进化区路径")
immutable = [
    "core/trust_layer.py",
    "core/data_lineage.py",
    "scripts/data_quality_gate.py",
    "schemas/env_recipe.schema.json",  # 实际文件名（原写成 env_recipe_schema.json 会 MISS）
    "mcp/server.py",
    ".well-known/agent.json",
    "harness/manifest.json",
    "data/env_recipes/",
]
bad = 0
for p in immutable:
    exists = (ROOT / p).exists()
    if not exists: bad += 1
    print(f"  {PASS if exists else FAIL}  {p}")
if bad:
    print(f"  → {bad} 条路径不存在。文档写 env_recipe_schema.json，"
          f"实际是 env_recipe.schema.json")

# ---------------------------------------------------------------------------
# 4. harness/manifest.json 关键数字
# ---------------------------------------------------------------------------
hr("[4] harness/manifest.json 关键指标")
def flat(o, pre=""):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[pre + k] = v
            elif isinstance(v, dict):
                out.update(flat(v, pre + k + "."))
    return out

mf = flat(manifest)
for k in sorted(mf):
    print(f"  {k} = {mf[k]}")
empty = [k for k, v in mf.items() if v == 0]
if empty:
    print(f"  → 零值字段 ({len(empty)}): {empty}")

# ---------------------------------------------------------------------------
# 5. README 数字口径
# ---------------------------------------------------------------------------
hr("[5] README 数字口径")
readme = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore")
# 口径统计：严格匹配"N 个工具/skill"这种计数语义。
# 用 (?<![\d第]) 排除"第 N 个"里的数字（序数）和"NN 个"里被截断的低位数字（如"23"里的"3"）。
tool_nums = sorted(set(re.findall(
    r"(?<![\d第])(\d+)\s*个\s*(?:MCP\s*)?(?:agri\s*)?工具", readme)))
skill_nums = sorted(set(re.findall(
    r"(?<![\d第])(\d+)\s*个\s*(?:skill|技能)", readme, re.I)))
print(f"  README 工具数出现: {tool_nums}   (实际 {n_fn})")
print(f"  README skill 数出现: {skill_nums}  (实际 registry={n_skill}, Card.skills={n_card})")
# 允许两个合法值：
#   - n_skill（11）= skills/registry 人读技能目录语义
#   - n_card（23）= A2A Card.skills（工具映射语义，因为 Card.skills.id == MCP tool name）
# 其他任何值都是漂移。
bad_skill = {s for s in skill_nums if s not in (str(n_skill), str(n_card), n_skill, n_card)}
bad_tool = {t for t in tool_nums if t not in (str(n_fn), n_fn)}
if bad_tool or bad_skill:
    print(f"  → {FAIL} 数字漂移: tool={bad_tool or 'OK'} skill={bad_skill or 'OK'}")
elif len(set(tool_nums) - {str(n_fn), n_fn}) > 1:
    print(f"  → {FAIL} 同一文档内工具数不一致")
elif len(set(skill_nums) - {str(n_skill), str(n_card), n_skill, n_card}) > 1:
    print(f"  → {FAIL} 同一文档内技能数不一致")
else:
    print(f"  → {PASS} 数字口径一致")

# ---------------------------------------------------------------------------
# 6. 测试覆盖
# ---------------------------------------------------------------------------
hr("[6] 测试覆盖缺口")
test_text = "\n".join(
    f.read_text(encoding="utf-8", errors="ignore")
    for f in (ROOT / "scripts").glob("test_*.py")
)
mods = []
for d in ["agent", "core", "engine", "mcp", "bp_screen", "app"]:
    p = ROOT / d
    if p.exists():
        for f in p.glob("*.py"):
            if not f.name.startswith("_"):
                mods.append((d, f.stem))
uncovered = []
for d, mod in mods:
    hit = (f"from {d}.{mod}" in test_text or f"import {mod}" in test_text
           or f"{d}.{mod}" in test_text or f"{d}/{mod}" in test_text)
    if not hit:
        uncovered.append(f"{d}/{mod}.py")
print(f"  模块总数: {len(mods)}   有测试引用: {len(mods)-len(uncovered)}   "
      f"覆盖率: {(len(mods)-len(uncovered))/max(len(mods),1):.1%}")
print(f"  零引用模块 ({len(uncovered)} 个):")
for u in uncovered:
    print(f"    - {u}")

# ---------------------------------------------------------------------------
# 7. CI 步骤数
# ---------------------------------------------------------------------------
hr("[7] CI 步骤数")
ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8", errors="ignore")
steps = re.findall(r"^\s*- name:\s*(.+)$", ci, re.M)
print(f"  CI 步骤: {len(steps)}")
# CI 步数不硬编码：从 manifest.ci.step_count 读（A3 已统一到 manifest 单一真源）
ci_expected = manifest.get("ci", {}).get("step_count")
if ci_expected is not None:
    print(f"  manifest.ci.step_count: {ci_expected}  → "
          f"{PASS if len(steps) == ci_expected else FAIL}")
else:
    print(f"  manifest.ci.step_count: 未声明  → WARN（请在 manifest.ci 加 step_count 锁定步数）")

# ---------------------------------------------------------------------------
# 8. G2 数据飞轮
# ---------------------------------------------------------------------------
hr("[8] G2 数据飞轮状态")
for name, rel, target in [
    ("feedback_log", "data/feedback_log.json", 30),
    ("execution_log", "data/execution_log.json", 20),
]:
    p = ROOT / rel
    if not p.exists():
        print(f"  {FAIL} {rel}")
        continue
    d = _load(p, [])
    entries = d if isinstance(d, list) else next(
        (d[k] for k in ("entries", "records", "logs", "items") if isinstance(d.get(k), list)), []
    )
    print(f"  {name}: {len(entries)} 条 (目标 {target})")
    if name == "execution_log" and entries:
        srcs = Counter(e.get("source", "?") for e in entries)
        modes = Counter(e.get("mode", "?") for e in entries)
        print(f"    source: {dict(srcs)}")
        print(f"    mode:   {dict(modes)}")
        real = sum(1 for e in entries if e.get("source") == "real")
        print(f"    真实执行: {real} 条  {FAIL if real == 0 else PASS}")

# ---------------------------------------------------------------------------
# 9. data 资产
# ---------------------------------------------------------------------------
hr("[9] data 资产盘点")
for sub in sorted((ROOT / "data").iterdir()):
    if sub.is_dir():
        n = len([x for x in sub.rglob("*") if x.is_file()])
        flag = WARN if sub.name.startswith("_") or n == 0 else ""
        print(f"  {sub.name}/: {n} 文件  {flag}")

# ---------------------------------------------------------------------------
# 10. 文档新鲜度
# ---------------------------------------------------------------------------
hr("[10] 文档新鲜度（>20 天未更新）")
now = dt.datetime.now()
docs = sorted((ROOT / "docs").rglob("*.md"))
old = []
for f in docs:
    age = (now - dt.datetime.fromtimestamp(f.stat().st_mtime)).days
    if age > 20:
        old.append((age, f.name))
old.sort(reverse=True)
print(f"  文档总数: {len(docs)}   超 20 天: {len(old)}")
for age, name in old[:15]:
    print(f"    {age:3d} 天  {name}")

# ---------------------------------------------------------------------------
# 11. Schema vs 实际字段
# ---------------------------------------------------------------------------
hr("[11] env_recipe schema vs 实际数据字段")
schema = _load(ROOT / "schemas/env_recipe.schema.json", {}) or {}
props = set(schema.get("properties", {}))
actual = Counter()
for f in files:
    d = _load(f, {}) or {}
    for k in d: actual[k] += 1
print(f"  schema 字段: {len(props)}   实际字段: {len(actual)}")
print(f"  schema 有但数据无: {sorted(props - set(actual))}")
print(f"  数据有但 schema 无: {sorted(set(actual) - props)}")

# ---------------------------------------------------------------------------
# 12. 工具文档覆盖
# ---------------------------------------------------------------------------
hr("[12] MCP 工具文档覆盖")
tools = re.findall(r'"name"\s*:\s*"agri_(\w+)"', m)
all_docs = "\n".join(f.read_text(encoding="utf-8", errors="ignore") for f in docs)
no_readme = [t for t in tools if f"agri_{t}" not in readme]
no_docs = [t for t in tools if f"agri_{t}" not in all_docs]
print(f"  工具总数: {len(tools)}")
print(f"  README 未点名: {len(no_readme)} → {no_readme}")
print(f"  docs 未提及:   {len(no_docs)} → {no_docs}")

# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------
hr("汇总：报告中的关键数字")
print(f"  A2A Card skills        = {n_card}")
print(f"  MCP 工具数             = {n_fn}")
print(f"  skills/registry 文件   = {n_skill}")
print(f"  manifest.skills.count  = {n_manifest_skill}")
print(f"  CI 步骤                = {len(steps)}")
print(f"  测试覆盖率             = {(len(mods)-len(uncovered))/max(len(mods),1):.1%} "
      f"({len(uncovered)} 个模块零引用)")
print(f"  license=unknown        = {unknown} 条")
print(f"  三字段齐全配方         = {complete}/{len(files)}")
print(f"  超 20 天未更新文档     = {len(old)}/{len(docs)}")
print(f"  README 工具数出现值    = {tool_nums}")
print(f"  README skill 数出现值  = {skill_nums}")
