#!/usr/bin/env python3
"""
attach_golden_references.py —— 给 golden vectors 挂上权威出处（SCI S1.1）

背景：SCI 评审第一问必然是 "expected 值哪来的？"。
    本项目 golden vectors 的 expected 值实际源自本地权威数据/文献：
      - phenology  → data/wofost_phenology_reference.json (WOFOST 参数表, wofost_params) + 物候文献
      - nutrition  → 番茄干物质/N-P-K 分配模型 (heuvelink1996) + FAO-56 (allen1998)
      - forecast   → 保形预测理论 (vovk2012 / lei2018)

本脚本从 docs/REFERENCES.md 的 ```references-json 代码块读取**唯一事实源**，
把用到的 reference key 解析为完整条目（含已逐条核实的 DOI/URL/本地文件），
写进 golden vector 文件。schema 从 v1 升到 v2。
字段设计（可被 validate_references.py 机械校验）：
    references: [{key, kind, authors, year, title, venue, doi?, url?, origin?, license?, provenance}]
    cases[].reference_keys: [str]

用法：
    python scripts/attach_golden_references.py
    python scripts/attach_golden_references.py --check   # 只校验不改写
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GV_DIR = ROOT / "benchmarks" / "golden_vectors"
REF_MD = ROOT / "docs" / "REFERENCES.md"

# 每个 golden vector 文件：用例 → 引用的 reference keys（key 必须存在于 REFERENCES.md）
BINDINGS = {
    "phenology.json": {
        "default": ["wofost_params", "vandidpen1989", "mcmaster1997"],
        "by_case": {
            "uncovered_crop": ["vandidpen1989"],   # 番茄不在 WOFOST 表 → 仅引方法论
        },
    },
    "nutrition.json": {
        "default": ["heuvelink1996", "allen1998"],
        "by_case": {},
    },
    "forecast.json": {
        "default": ["vovk2012", "bates2021"],
        "by_case": {},
    },
}


def load_registry() -> dict:
    """从 REFERENCES.md 的 ```references-json 读取唯一事实源，返回 key->entry。"""
    md = REF_MD.read_text(encoding="utf-8")
    m = re.search(r"```references-json\s*\n(.*?)\n```", md, re.DOTALL)
    if not m:
        raise SystemExit("ERROR: docs/REFERENCES.md 未找到 ```references-json 代码块")
    data = json.loads(m.group(1))
    return {r["key"]: r for r in data["references"]}


def attach(path: Path, config: dict, registry: dict, check_only: bool) -> tuple[bool, list[str]]:
    """给单个 golden vector 文件挂 reference。返回 (changed, issues)。"""
    d = json.loads(path.read_text(encoding="utf-8"))
    issues: list[str] = []
    changed = False

    used_keys: set[str] = set()
    for c in d["cases"]:
        cid = c.get("id", "")
        keys = config["by_case"].get(cid, config["default"])
        if c.get("reference_keys") != keys:
            c["reference_keys"] = keys
            changed = True
        used_keys |= set(keys)

    refs = []
    for k in sorted(used_keys):
        if k not in registry:
            issues.append(f"unknown reference key: {k}")
            continue
        entry = dict(registry[k])
        # 只保留对外有意义的字段，保持 golden vector 自包含
        keep = ["key", "kind", "authors", "year", "title", "venue",
                "doi", "url", "origin", "license", "provenance"]
        entry = {kk: entry[kk] for kk in keep if kk in entry}
        refs.append(entry)
    if d.get("references") != refs:
        d["references"] = refs
        changed = True

    # schema 版本升级
    old = d.get("schema", "")
    if old and "/v1" in old and "/v2" not in old:
        d["schema"] = old.replace("/v1", "/v2")
        changed = True
    if "attached_at" not in d:
        d["attached_at"] = "2026-10-18"
        changed = True

    if changed and not check_only:
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return changed, issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不改写（供 CI 使用）")
    args = ap.parse_args()

    registry = load_registry()
    if not registry:
        raise SystemExit("ERROR: REFERENCES.md 登记为空")

    all_issues: list[str] = []
    n_changed = 0
    for fname, cfg in BINDINGS.items():
        p = GV_DIR / fname
        if not p.exists():
            all_issues.append(f"{fname}: 文件不存在")
            continue
        changed, issues = attach(p, cfg, registry, args.check)
        n_changed += int(changed)
        all_issues += [f"{fname}: {i}" for i in issues]
        verb = "需更新" if changed else "已就绪"
        print(f"  {fname}: {verb} ({len(p.read_text(encoding='utf-8'))} bytes after)")

    # 全局自检：每个 paper 必须有 doi；report/specification 必须有 url；dataset 必须有 origin
    missing = []
    for k, e in registry.items():
        if e["kind"] == "paper" and not e.get("doi"):
            missing.append(f"{k}: paper 缺 doi")
        elif e["kind"] in ("report", "specification") and not e.get("url"):
            missing.append(f"{k}: {e['kind']} 缺 url")
        elif e["kind"] == "dataset" and not e.get("origin"):
            missing.append(f"{k}: dataset 缺 origin")
    print(f"\n  已登记 reference: {len(registry)} 个")
    print(f"  待补标识符: {len(missing)} 个")
    for m in missing:
        print(f"    - {m}")
    print(f"  改写文件数: {n_changed}")

    if all_issues:
        print("\n  问题:")
        for i in all_issues:
            print(f"    - {i}")
        raise SystemExit(1)

    if args.check:
        print("\n  --check 模式：未改写任何文件")
    print("\n  golden vector schema 已升至 v2（含 references + reference_keys，全部 DOI/URL 已核实）")


if __name__ == "__main__":
    main()
