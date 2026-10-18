#!/usr/bin/env python3
"""
validate_references.py —— SCI S1.1 文献 DOI / URL 机械校验器

唯一事实源：docs/REFERENCES.md 文末的 ```references-json 代码块。

校验规则（学术诚信：禁止猜测 DOI）：
  - kind=paper        : 必须有 doi；向 https://doi.org/<doi> 发请求（不跟随跳转），
                        接受 2xx/3xx（doi.org 返回 302 即视为已注册/可解析）；
                        拒绝 404/410（未注册）。并对能拿到标题的出版社做标题子串匹配。
  - kind=report / specification : 必须有 url；校验 HTTP 可达（2xx/3xx）。
  - kind=dataset      : 必须有 origin（本地文件）；校验文件存在。

交叉校验：benchmarks/golden_vectors/*.json 中每个 case 的 reference_keys
          必须全部存在于登记表，且其 DOI/URL/本地文件可解析（即被上面规则覆盖）。

退出码：全部通过为 0；任一失败为 1。供 CI 调用。

用法：
    python scripts/validate_references.py
    python scripts/validate_references.py --strict     # 标题不匹配也报错（默认仅警告）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_MD = ROOT / "docs" / "REFERENCES.md"
GV_DIR = ROOT / "benchmarks" / "golden_vectors"

VALID_HTTP = {200, 201, 202, 203, 204, 301, 302, 303, 307, 308}
BAD_HTTP = {404, 410}


def extract_references_json(md_text: str) -> dict:
    m = re.search(r"```references-json\s*\n(.*?)\n```", md_text, re.DOTALL)
    if not m:
        raise SystemExit("ERROR: docs/REFERENCES.md 未找到 ```references-json 代码块")
    return json.loads(m.group(1))


def http_status(url: str, timeout: int = 25) -> int | None:
    """返回 url 的 HTTP 状态码（不跟随跳转）；失败返回 None。"""
    try:
        out = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-m", str(timeout),
             "-w", "%{http_code}", url],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        code = out.stdout.strip()
        return int(code) if code.isdigit() else None
    except Exception:
        return None


def fetch_title_via_doi(doi: str, timeout: int = 25) -> str | None:
    """尽力通过 doi.org 内容协商拿到标题；拿不到返回 None。"""
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "-m", str(timeout),
             "-H", "Accept: application/vnd.citationstyles.csl+json",
             f"https://doi.org/{doi}"],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if out.returncode != 0:
            return None
        data = json.loads(out.stdout)
        t = data.get("title")
        if isinstance(t, list):
            t = t[0]
        return t
    except Exception:
        return None


def fetch_title_via_crossref(doi: str, timeout: int = 25) -> str | None:
    """出版社（Wiley/Elsevier/ACM）常屏蔽内容协商，退回 Crossref 元数据拿标题。"""
    try:
        out = subprocess.run(
            ["curl", "-sS", "-m", str(timeout),
             f"https://api.crossref.org/works/{doi}"],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if out.returncode != 0:
            return None
        d = json.loads(out.stdout)["message"]
        t = d.get("title")
        if isinstance(t, list):
            t = t[0]
        return t
    except Exception:
        return None


def _toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", (s or "").lower()))


def title_close(en: str, got: str) -> bool:
    """标题是否足够接近：token Jaccard >= 0.5 视为匹配（容忍标点/大小写/介词差异）。"""
    te, tg = _toks(en), _toks(got)
    if not te or not tg:
        return False
    return len(te & tg) / len(te | tg) >= 0.5


def verify_one(ref: dict, strict: bool, fast: bool) -> list[str]:
    """返回该条目的问题列表（空=通过）。"""
    issues: list[str] = []
    kind = ref.get("kind")
    key = ref.get("key", "?")
    if kind == "paper":
        doi = ref.get("doi")
        if not doi:
            issues.append(f"[{key}] paper 类缺少 doi")
            return issues
        st = http_status(f"https://doi.org/{doi}")
        if st is None:
            issues.append(f"[{key}] doi.org 请求失败（网络/超时）: {doi}")
        elif st in BAD_HTTP:
            issues.append(f"[{key}] DOI 不可解析 ({st}): {doi}")
        elif st not in VALID_HTTP:
            issues.append(f"[{key}] DOI 返回异常码 {st}: {doi}")
        else:
            # DOI 已注册（2xx/3xx）。标题匹配（--fast 跳过，仅做注册校验），用于 CI。
            if not fast:
                t_nego = fetch_title_via_doi(doi)
                t_cr = fetch_title_via_crossref(doi)
                expected = ref.get("title", "")
                matched = (t_nego and title_close(expected, t_nego)) or \
                          (t_cr and title_close(expected, t_cr))
                if (t_nego or t_cr) and not matched:
                    got = t_nego or t_cr
                    msg = (f"[{key}] 标题疑似不匹配 (expected≈{expected[:42]!r} "
                           f"got≈{got[:42]!r})")
                    issues.append(msg) if strict else print("  ⚠ " + msg)
    elif kind in ("report", "specification"):
        url = ref.get("url")
        if not url:
            issues.append(f"[{key}] {kind} 类缺少 url")
            return issues
        st = http_status(url)
        if st is None:
            issues.append(f"[{key}] URL 请求失败（网络/超时）: {url}")
        elif st in BAD_HTTP:
            issues.append(f"[{key}] URL 不可达 ({st}): {url}")
        elif st not in VALID_HTTP:
            issues.append(f"[{key}] URL 返回异常码 {st}: {url}")
    elif kind == "dataset":
        origin = ref.get("origin")
        if not origin:
            issues.append(f"[{key}] dataset 类缺少 origin")
            return issues
        if not (ROOT / origin).exists():
            issues.append(f"[{key}] 本地数据集不存在: {origin}")
    else:
        issues.append(f"[{key}] 未知 kind: {kind}")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="标题不匹配也视为失败（默认仅警告）")
    ap.add_argument("--fast", action="store_true",
                    help="快速模式：仅校验 DOI 注册/URL 可达/本地文件存在，"
                         "跳过逐条标题内容协商（供 CI 使用，更快更稳）")
    args = ap.parse_args()

    if not REF_MD.exists():
        print("ERROR: docs/REFERENCES.md 不存在")
        raise SystemExit(1)

    registry = extract_references_json(REF_MD.read_text(encoding="utf-8"))
    refs = registry.get("references", [])
    print(f"登记文献总数: {len(refs)}")

    all_issues: list[str] = []
    by_kind: dict[str, int] = {}
    for ref in refs:
        by_kind[ref.get("kind", "?")] = by_kind.get(ref.get("kind", "?"), 0) + 1
        iss = verify_one(ref, args.strict, args.fast)
        all_issues += iss
        status = "OK " if not iss else "FAIL"
        ident = ref.get("doi") or ref.get("url") or ref.get("origin") or "?"
        print(f"  [{status}] {ref.get('key'):<18} {ref.get('kind'):<13} {ident}")

    print(f"\n按类型统计: {by_kind}")

    # ---- 交叉校验 golden vectors ----
    if GV_DIR.exists():
        import glob
        used_keys: set[str] = set()
        case_total = 0
        case_with_keys = 0
        for f in sorted(glob.glob(str(GV_DIR / "*.json"))):
            d = json.loads(Path(f).read_text(encoding="utf-8"))
            for c in d.get("cases", []):
                case_total += 1
                rk = c.get("reference_keys") or []
                if rk:
                    case_with_keys += 1
                for k in rk:
                    used_keys.add(k)
                    if k not in {r["key"] for r in refs}:
                        all_issues.append(f"golden_vector 引用了未登记的 key: {k} (file={Path(f).name})")
        print(f"\ngolden vectors: cases={case_total}, 带 reference_keys={case_with_keys}")
        print(f"golden vectors 用到的 reference keys ({len(used_keys)}): {sorted(used_keys)}")
        # 用到的 paper/dataset 的 DOI/文件已在上面逐条校验；此处仅确认无悬空 key
    else:
        print("\n(跳过 golden vectors 校验：目录不存在)")

    print("\n" + "=" * 60)
    if all_issues:
        print(f"结果: FAIL —— {len(all_issues)} 个问题")
        for i in all_issues:
            print("  - " + i)
        raise SystemExit(1)
    else:
        print("结果: PASS —— 所有 DOI/URL/本地数据集均可解析，golden vectors 引用一致。")


if __name__ == "__main__":
    main()
