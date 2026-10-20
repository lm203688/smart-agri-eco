#!/usr/bin/env python3
"""
JOSS 提交前自检（2026-10 scope 版）。

用途：把 `paper.md` + `paper.bib` 推上 GitHub 前跑一次，验证 JOSS 2026 强制
要求的格式合规。不依赖第三方包，仅用 stdlib。

用法：
    python scripts/check_joss_submission.py                     # 默认读 ./paper.md + ./paper.bib
    python scripts/check_joss_submission.py --paper X --bib Y
    python scripts/check_joss_submission.py --strict            # 任一失败即 exit 1

退出码：0 = 全部通过；1 = 有硬性失败（strict 模式或默认都返回）；2 = 有 warning。

检查项（对齐 JOSS 2026 review criteria）：
  S1 · Summary（非专业读者摘要）
  S2 · Statement of need
  S3 · State of the field（2026 新增，含 build-vs-contribute）
  S4 · Software design（架构权衡 + 设计理由）
  S5 · Research impact statement（realized 或 credible near-term）
  S6 · AI usage disclosure（2026 新增，允许使用但要求透明）
  S7 · Acknowledgements
  S8 · References（含相关软件引用）
  S9 · YAML frontmatter（title/tags/authors/affiliations/date）
  S10 · 字数 750-1750
  S11 · License（MIT/OSI-approved）
  S12 · Bibliography file（paper.bib 存在，非空）
  S13 · 公开历史 >= 6 个月（JOSS 2026 scope 明确门槛；本项目 49 天，需诚实披露）
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REQUIRED_SECTIONS = [
    "Summary",
    "Statement of need",
    "State of the field",
    "Software design",
    "Research impact statement",
    "AI usage disclosure",
    "Acknowledgements",
    "References",
]

REQUIRED_YAML_KEYS = ["title", "tags", "authors", "affiliations", "date", "bibliography"]

MIN_WORDS = 750
MAX_WORDS = 1750

MIN_PUBLIC_HISTORY_DAYS = 182  # JOSS 2026: at least 6 months


def _strip_yaml(md: str) -> tuple[str, str]:
    """返回 (frontmatter, body)。没有 frontmatter 时 frontmatter 为空串。"""
    if not md.startswith("---"):
        return "", md
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", md, re.DOTALL)
    if not m:
        return "", md
    return m.group(1), m.group(2)


def _count_words(body: str) -> int:
    """粗略 word count，忽略代码块和表格竖线。"""
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    body = re.sub(r"^\s*\|.*\|\s*$", "", body, flags=re.MULTILINE)
    tokens = re.findall(r"[A-Za-z0-9]+(?:[-'\u2019.][A-Za-z0-9]+)*", body)
    return len(tokens)


def check_paper(path: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    if not path.exists():
        return [("file_exists", False, f"paper.md not found at {path}")]
    text = path.read_text(encoding="utf-8")
    results.append(("file_exists", True, str(path)))

    frontmatter, body = _strip_yaml(text)

    # YAML
    yaml_ok = bool(frontmatter)
    results.append(("yaml_frontmatter", yaml_ok, "found" if yaml_ok else "MISSING"))

    yaml_keys_present = [k for k in REQUIRED_YAML_KEYS if re.search(rf"^{k}:", frontmatter, re.MULTILINE)]
    missing_yaml = set(REQUIRED_YAML_KEYS) - set(yaml_keys_present)
    results.append((
        "yaml_required_keys",
        not missing_yaml,
        f"present={yaml_keys_present}" + (f"; missing={sorted(missing_yaml)}" if missing_yaml else ""),
    ))

    # Sections
    found_sections = re.findall(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    found_lower = [s.lower().strip() for s in found_sections]
    for sec in REQUIRED_SECTIONS:
        present = sec.lower() in found_lower
        results.append((f"section::{sec}", present, "found" if present else "MISSING"))

    # Word count
    wc = _count_words(body)
    in_range = MIN_WORDS <= wc <= MAX_WORDS
    results.append((
        "word_count_range",
        in_range,
        f"{wc} words (target {MIN_WORDS}-{MAX_WORDS})",
    ))

    # AI usage disclosure: 必须包含具体动词，不只是"no AI"或"some AI"
    ai_section_body = ""
    m = re.search(r"^#\s+AI usage disclosure\s*$(.*?)(?=^#\s|\Z)", body, re.MULTILINE | re.DOTALL)
    if m:
        ai_section_body = m.group(1)
    has_transparency = any(kw in ai_section_body.lower() for kw in ["ai", "generated", "assist", "verify"])
    results.append((
        "ai_disclosure_substantive",
        bool(ai_section_body) and has_transparency,
        f"{len(ai_section_body)} chars",
    ))

    # build-vs-contribute (JOSS 2026 State of the field 强制短语)
    soc_body = ""
    m = re.search(r"^#\s+State of the field\s*$(.*?)(?=^#\s|\Z)", body, re.MULTILINE | re.DOTALL)
    if m:
        soc_body = m.group(1)
    has_build_vs_contribute = "build vs" in soc_body.lower() or "contribute" in soc_body.lower()
    results.append((
        "state_of_the_field_build_vs_contribute",
        has_build_vs_contribute,
        f"body={len(soc_body)} chars",
    ))

    return results


def check_bib(path: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    if not path.exists():
        return [("bib_exists", False, f"{path} not found")]
    text = path.read_text(encoding="utf-8")
    results.append(("bib_exists", True, str(path)))

    entries = re.findall(r"@\w+\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    has_entries = len(entries) >= 5
    results.append(("bib_entry_count", has_entries, f"{len(entries)} entries"))

    # 至少一个 @misc/@software 类型（软件引用）
    has_software = bool(re.search(r"@misc\s*\{", text, re.IGNORECASE))
    results.append(("bib_has_software_ref", has_software, "found" if has_software else "MISSING"))

    return results


def check_license(repo_root: Path) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    lic = repo_root / "LICENSE"
    if not lic.exists():
        return [("license_present", False, "LICENSE not found")]
    text = lic.read_text(encoding="utf-8", errors="ignore").lower()
    is_osi = any(k in text for k in ["mit license", "apache license", "gnu", "mozilla public", "bsd"])
    results.append(("license_present", True, str(lic)))
    results.append(("license_osi_approved", is_osi, "MIT/Apache/GPL/MPL/BSD detected" if is_osi else "unknown"))
    return results


def check_public_history(repo_root: Path) -> list[tuple[str, bool, str]]:
    """JOSS 2026: private-development projects need >= 6 months of public history."""
    today = date.today()
    # 本仓已知公开起始日（GitHub created_at）
    public_since = date(2026, 8, 31)
    days = (today - public_since).days
    ok = days >= MIN_PUBLIC_HISTORY_DAYS
    return [("public_history_days", ok,
             f"{days} days since 2026-08-31 (JOSS 2026 minimum {MIN_PUBLIC_HISTORY_DAYS})")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default="paper.md")
    ap.add_argument("--bib", default="paper.bib")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--strict", action="store_true", help="任一失败即 exit 1（默认行为；此 flag 保持向后兼容）")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    paper_path = (repo_root / args.paper).resolve() if not Path(args.paper).is_absolute() else Path(args.paper)
    bib_path = (repo_root / args.bib).resolve() if not Path(args.bib).is_absolute() else Path(args.bib)

    results = []
    results.extend(check_paper(paper_path))
    results.extend(check_bib(bib_path))
    results.extend(check_license(repo_root))
    results.extend(check_public_history(repo_root))

    fails = [(k, m) for k, ok, m in results if not ok]
    print(f"\nJOSS submission pre-check ({date.today()})")
    print("=" * 60)
    for k, ok, m in results:
        icon = "✓" if ok else "✗"
        print(f"  {icon} {k:<45} {m}")
    print("=" * 60)

    if fails:
        print(f"\n❌ {len(fails)} hard fail(s):")
        for k, m in fails:
            print(f"   - {k}: {m}")
        return 1

    print("\n✅ All JOSS 2026 checks pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
