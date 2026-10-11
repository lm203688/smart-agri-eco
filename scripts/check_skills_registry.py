"""Validate skills/registry/*.json against plugin/skills/*/SKILL.md for consistency."""
import json, re, sys
from pathlib import Path

ROOT = Path(r"C:/Users/xing/Desktop/智慧农业生态")
REG = ROOT / "skills/registry"
PLG = ROOT / "plugin/skills"

def parse_skill_md(path):
    """Extract YAML frontmatter from SKILL.md."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    out = {}
    for line in fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            out[key] = val
    return out

def main():
    registry = {}
    for jf in REG.glob("*.json"):
        if jf.name == "schema.json" or jf.name == "CONTRIBUTING.md":
            continue
        registry[jf.stem] = json.loads(jf.read_text(encoding="utf-8"))

    skills = {}
    for sk_dir in PLG.glob("*/"):
        if not sk_dir.is_dir():
            continue
        md = sk_dir / "SKILL.md"
        if md.exists():
            skills[sk_dir.name] = parse_skill_md(md)

    print(f"registry entries: {len(registry)}")
    print(f"SKILL.md entries: {len(skills)}")
    print()

    # Check coverage
    r_ids = set(registry.keys())
    s_ids = set(skills.keys())
    only_r = r_ids - s_ids
    only_s = s_ids - r_ids
    if only_r: print(f"[!] only in registry: {only_r}")
    if only_s: print(f"[!] only in SKILL.md: {only_s}")
    both = r_ids & s_ids
    print(f"matched: {len(both)}")

    # For each matched pair, check id/name/version consistency
    print("\n=== Consistency check ===")
    errors = 0
    for name in sorted(both):
        r = registry[name]
        s = skills[name]
        diffs = []
        if r.get("id") != name:
            diffs.append(f"registry.id={r.get('id')!r} != {name}")
        if s.get("name") and r.get("name") and s.get("name") != r.get("name"):
            diffs.append(f"name differs: skill={s.get('name')!r} registry={r.get('name')!r}")
        if s.get("version") and r.get("version") and s.get("version") != r.get("version"):
            diffs.append(f"version differs: skill={s.get('version')!r} registry={r.get('version')!r}")
        # Description consistency (fuzzy: first 40 chars should match)
        if s.get("description") and r.get("description"):
            sd = s["description"][:60]
            rd = r["description"][:60]
            if sd != rd:
                diffs.append(f"description diff: skill='{sd}' vs registry='{rd}'")
        # Domain check
        if r.get("domain") and "领域:" in (s.get("description") or ""):
            pass
        if diffs:
            errors += 1
            print(f"[DIFF] {name}:")
            for d in diffs:
                print(f"    - {d}")
        else:
            print(f"[OK]   {name} v{r.get('version')}")

    print(f"\n=== summary: {len(both)} checked, {errors} with diffs ===")
    return 1 if errors > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
