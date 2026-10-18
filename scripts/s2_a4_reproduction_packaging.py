#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2-A4：可复现性证据打包 —— 零依赖复现包 + 逐轴统计摘要 + 复现指纹。

路线要求（docs/SCI_ROADMAP_2026-10-18.md §S2-A4）：
  - 把 `results_history.json` 的历史运行按 §S1.3 做统计分析，
    生成 `benchmarks/results/stat_summary.json`（论文 Table 1 数据源）
  - 生成"复现包"：`python -m venv`（无需装任何包）+ 直接运行 →
    输出与 CI 历史一致
  - 验收：`stat_summary.json` 中每个轴有 mean/std/n

**产出**：
  1. `benchmarks/results/stat_summary.json`（已存在，由 stat_report.py 生成；
     本脚本负责校验其完备性：每个轴必须 mean/std/n 三件套齐备）
  2. `benchmarks/results/reproduction_manifest.json`（本脚本产出）——
     含 Python 环境、文件指纹（SHA256）、依赖审计、复现命令序列、期望输出。

**零依赖验证策略**：
用 ast 静态扫描全项目源码（.py），检查所有 import 是否落在标准库
（`sys.stdlib_module_names`）或项目内部包（`core/`, `agent/`, `engine/`,
`benchmarks/`, `scripts/`, `mcp/`, `schemas/`）中；出现第三方包即视为失败。

用法：
    python scripts/s2_a4_reproduction_packaging.py
    python scripts/s2_a4_reproduction_packaging.py --json
    python scripts/s2_a4_reproduction_packaging.py --strict
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAT_SUMMARY_PATH = ROOT / "benchmarks" / "results" / "stat_summary.json"
MANIFEST_PATH = ROOT / "benchmarks" / "results" / "reproduction_manifest.json"
HISTORY_PATH = ROOT / "benchmarks" / "agri_recipe_bench" / "results_history.json"

# 项目内部包根（顶层包，用于解析 `from xxx import yyy` 的 xxx）
INTERNAL_ROOTS: Set[str] = {
    "core", "agent", "engine", "benchmarks", "scripts", "mcp", "schemas", "data",
    "app",          # demo server 前端 + 后端入口（app/demo_server.py）
    "bp_screen",    # 农业投资初筛子项目，有自己的零依赖分层策略
}

# 排除目录（不参与零依赖审计）
EXCLUDE_PARTS: Set[str] = {
    ".venv", "venv", "__pycache__", ".git", "node_modules",
    "_archive",           # 归档代码，不参与门禁
    ".workbuddy",         # 本地元数据
}

# 排除路径片段（不参与零依赖审计）
EXCLUDE_SEGMENTS: List[str] = [
    ".ref",              # 模板参考目录（非活跃代码）
]

# 复现命令序列（论文 §Reproducibility 会引用）
REPRO_COMMANDS: List[str] = [
    "python -m unittest discover -s scripts -p 'test_*.py' -v",
    "python benchmarks/agri_recipe_bench/run_bench.py --strict",
    "python benchmarks/agri_recipe_bench/run_bench.py --axis negative --summary --strict",
    "python -m benchmarks.ratchet_modules --strict",
    "python scripts/run_golden_vectors.py --strict",
    "python scripts/verify_all.py",
    "python scripts/data_quality_gate.py",
    "python scripts/check_demo_endpoints.py",
    "python scripts/check_distribution_readiness.py",
    "python scripts/build_agent_plugin.py --check",
    "python scripts/test_mcp_server.py",
    "python scripts/validate_references.py --fast",
    "python benchmarks/baseline_external/run_baseline.py --strict",
    "python scripts/s2_a1_phenology_consistency.py --strict",
    "python scripts/s2_a2_koppen_consistency.py --strict",
    "python scripts/s2_a3_envelope_robustness.py --strict",
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def module_is_internal(module_name: str, filename: str, root: Path) -> bool:
    """判断一个 import 模块是否为项目内部模块（含相对 import 与同目录 sibling）。

    三种情况视为内部：
      1. top-level 在 INTERNAL_ROOTS（如 `from core.numeric_domain import ...`）
      2. 相对导入（`from .foo import ...` 或 `from ..bar import ...`）
      3. sibling 导入：当前文件所在目录下存在同名 .py 或同名子目录
         （如 agent/season_agent.py 里 `from phenology import ...` → agent/phenology.py）
    """
    if not module_name:
        return False
    top = module_name.split(".")[0]
    if filename and top.startswith("."):
        return True
    if top in INTERNAL_ROOTS:
        return True
    # sibling 导入检测
    if filename:
        try:
            cur_dir = Path(filename).resolve().parent
        except (OSError, ValueError):
            cur_dir = None
        if cur_dir is not None:
            sibling_py = cur_dir / f"{top}.py"
            sibling_pkg = cur_dir / top / "__init__.py"
            if sibling_py.exists() or sibling_pkg.exists():
                return True
        # 跨目录检测：模块文件位于 ROOT/<internal_root>/<top>.py
        # （如 scripts/assess_completeness.py 里 sys.path.insert 后 import demo_server，
        #  实际文件在 app/demo_server.py）
        for root_name in INTERNAL_ROOTS:
            candidate_dir = root / root_name
            if (candidate_dir / f"{top}.py").is_file() or (candidate_dir / top / "__init__.py").is_file():
                return True
    return False


def module_is_stdlib(module_name: str) -> bool:
    std = getattr(sys, "stdlib_module_names", None)
    if std is None:
        # Python 3.9 fallback：白名单
        legacy = {"__future__", "argparse", "ast", "collections", "contextlib",
                  "copy", "csv", "dataclasses", "datetime", "decimal", "functools",
                  "hashlib", "importlib", "inspect", "itertools", "json", "logging",
                  "math", "multiprocessing", "os", "pathlib", "pickle", "platform",
                  "re", "shutil", "signal", "socket", "sqlit3", "sqlite3", "statistics",
                  "string", "subprocess", "sys", "tempfile", "textwrap", "time",
                  "traceback", "types", "typing", "unittest", "urllib", "uuid", "warnings"}
        return module_name.split(".")[0] in legacy
    return module_name.split(".")[0] in std


# ---------------------------------------------------------------------------
# Part 1: 依赖审计
# ---------------------------------------------------------------------------
def audit_dependencies() -> Dict[str, Any]:
    """扫描所有 .py 的 import，分类为：
      - module_level_violations：模块顶层第三方 import（真违反，判失败）
      - lazy_violations：函数体内的第三方 import（可选依赖，不判失败但须报告）
    项目零依赖硬约束针对**模块顶层**；bp_screen/parser.py 的 openpyxl、
    bp_screen/web.py 的 fastapi 属可选功能，采用函数内 lazy import 设计。
    """
    module_level: List[Dict[str, Any]] = []
    lazy: List[Dict[str, Any]] = []
    total_files = 0

    for p in sorted(ROOT.rglob("*.py")):
        parts = p.parts
        # 排除目录（元素级）
        if any(x in parts for x in EXCLUDE_PARTS):
            continue
        # 排除路径片段（substring 级）
        if any(any(seg in part for seg in EXCLUDE_SEGMENTS) for part in parts):
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(p))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        total_files += 1

        # 建立 node → parent 映射，用于判断 import 是否在函数体内
        parent_map: Dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent_map[id(child)] = node

        def _in_function(node: ast.AST) -> bool:
            cur = parent_map.get(id(node))
            depth = 0
            while cur is not None and depth < 50:
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    return True
                cur = parent_map.get(id(cur))
                depth += 1
            return False

        def _in_try_import(node: ast.AST) -> bool:
            """检测是否在 try/except ImportError 保护块内（可选依赖惯用模式）。"""
            cur = parent_map.get(id(node))
            depth = 0
            while cur is not None and depth < 50:
                if isinstance(cur, ast.Try):
                    # 检查 except handler 是否捕获 ImportError
                    for h in cur.handlers:
                        if h.type is None:
                            continue  # bare except
                        name = None
                        if isinstance(h.type, ast.Name):
                            name = h.type.id
                        elif isinstance(h.type, ast.Tuple):
                            names = [e.id for e in h.type.elts if isinstance(e, ast.Name)]
                            if "ImportError" in names or "ModuleNotFoundError" in names:
                                return True
                        elif isinstance(h.type, ast.Attribute):
                            name = h.type.attr
                        if name in ("ImportError", "ModuleNotFoundError"):
                            return True
                cur = parent_map.get(id(cur))
                depth += 1
            return False

        def _check(name: str, node: ast.AST, kind: str) -> None:
            if not name:
                return
            if module_is_stdlib(name) or module_is_internal(name, str(p), ROOT):
                return
            entry = {
                "file": str(p.relative_to(ROOT)),
                "line": node.lineno,
                "kind": kind,
                "module": name,
            }
            # 三种分类：
            #   1. 函数体内 lazy import → 可选
            #   2. try/except ImportError 保护 → 可选（模块顶层但受保护）
            #   3. 其他 → 硬违反
            if _in_function(node) or _in_try_import(node):
                lazy.append(entry)
            else:
                module_level.append(entry)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check(alias.name, node, "import")
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                if not node.module:
                    continue
                _check(node.module, node, "from-import")

    return {
        "total_files_scanned": total_files,
        "module_level_violations": module_level,
        "n_module_level_violations": len(module_level),
        "lazy_optional_imports": lazy,
        "n_lazy_optional_imports": len(lazy),
        "stdlib_only_pass": len(module_level) == 0,
        "excluded_parts": sorted(EXCLUDE_PARTS),
        "excluded_segments": EXCLUDE_SEGMENTS,
    }


# ---------------------------------------------------------------------------
# Part 2: 关键文件指纹
# ---------------------------------------------------------------------------
def fingerprint_files() -> Dict[str, Any]:
    targets: List[Path] = [
        ROOT / "pyproject.toml",
        ROOT / "README.md",
        ROOT / "docs" / "CORE_OBJECTIVE.md",
        ROOT / "data" / "wofost_phenology_reference.json",
        ROOT / "data" / "zone_meta" / "koppen_grid.json",
        ROOT / "data" / "zone_meta" / "global_zones.json",
    ]
    # 关键脚本 + agent + engine 目录
    for rel in (
        "agent/phenology.py", "agent/phenology_extended.py",
        "agent/forecast_agent.py", "engine/agriworld_lite.py",
        "core/numeric_domain.py", "core/honest_policy.py",
        "benchmarks/agri_recipe_bench/run_bench.py",
        "benchmarks/agri_recipe_bench/negative_runner.py",
        "benchmarks/agri_recipe_bench/stat_report.py",
        "benchmarks/baseline_external/run_baseline.py",
        "scripts/s2_a1_phenology_consistency.py",
        "scripts/s2_a2_koppen_consistency.py",
        "scripts/s2_a3_envelope_robustness.py",
        "scripts/s2_a4_reproduction_packaging.py",
    ):
        targets.append(ROOT / rel)

    files: List[Dict[str, Any]] = []
    for p in targets:
        if not p.exists():
            files.append({"path": str(p.relative_to(ROOT)), "status": "missing"})
            continue
        files.append({
            "path": str(p.relative_to(ROOT)),
            "sha256": sha256_file(p),
            "bytes": p.stat().st_size,
        })
    return {"files": files, "total": len(files)}


# ---------------------------------------------------------------------------
# Part 3: 统计摘要完备性
# ---------------------------------------------------------------------------
def verify_stat_summary() -> Dict[str, Any]:
    if not STAT_SUMMARY_PATH.exists():
        return {"exists": False, "verdict": "FAIL",
                "reason": f"{STAT_SUMMARY_PATH} 不存在；请运行 stat_report.py"}

    doc = json.loads(STAT_SUMMARY_PATH.read_text(encoding="utf-8"))
    # 期望：history.pass_rate / conformal_coverage 三件套齐备
    issues: List[str] = []

    hist = doc.get("history", {})
    for metric in ("pass_rate", "conformal_coverage"):
        blk = hist.get(metric, {})
        for k in ("mean", "std", "n"):
            if blk.get(k) is None:
                issues.append(f"history.{metric}.{k} 缺失或为 None")

    # 多种子重复块
    multi = doc.get("multi_seed", {})
    if multi:
        for metric in ("pass_rate", "conformal_coverage", "mean_abs_dev", "n_cases"):
            blk = multi.get(metric, {})
            for k in ("mean", "std", "n"):
                if blk.get(k) is None:
                    issues.append(f"multi_seed.{metric}.{k} 缺失或为 None")

    return {
        "exists": True,
        "n_history_entries": hist.get("entries"),
        "issues": issues,
        "verdict": "PASS" if not issues else "FAIL",
    }


# ---------------------------------------------------------------------------
# Part 4: 复现命令期望（不实际执行，仅列指纹）
# ---------------------------------------------------------------------------
def describe_reproduction_commands() -> List[Dict[str, str]]:
    return [
        {"cmd": c, "expected": "exit 0"} for c in REPRO_COMMANDS
    ]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_manifest() -> Dict[str, Any]:
    dep_audit = audit_dependencies()
    fingerprint = fingerprint_files()
    stat_verify = verify_stat_summary()

    # 环境
    env = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "requires_python": ">=3.10",
        "third_party_dependencies": "none (stdlib only)",
    }

    acceptance = {
        "stdlib_only_pass": dep_audit["stdlib_only_pass"],
        "stat_summary_completeness_pass": stat_verify.get("verdict") == "PASS",
        "n_repro_commands": len(REPRO_COMMANDS),
    }
    acceptance["all_pass"] = (
        acceptance["stdlib_only_pass"]
        and acceptance["stat_summary_completeness_pass"]
        and acceptance["n_repro_commands"] >= 15
    )

    return {
        "generated_by": "scripts/s2_a4_reproduction_packaging.py",
        "roadmap_task": "S2-A4",
        "environment": env,
        "dependency_audit": dep_audit,
        "file_fingerprints": fingerprint,
        "stat_summary_verification": stat_verify,
        "reproduction_commands": describe_reproduction_commands(),
        "reproduction_steps": [
            "python -m venv .venv",
            "source .venv/bin/activate  # 或 .venv\\Scripts\\activate (Windows)",
            "（无需 pip install 任何包）",
            "python scripts/s2_a4_reproduction_packaging.py --strict  # 验证环境",
            "依次运行 reproduction_commands 中的每条命令",
        ],
        "honesty_notes": [
            "本项目的零依赖约束是硬约束（见 CORE_OBJECTIVE.md）：核心代码只允许使用"
            "Python 标准库。本脚本用 ast 静态扫描所有 .py 文件的 import，"
            "**模块顶层**出现第三方包即判失败——这是防漂移门禁。",
            f"扫描到 {dep_audit['total_files_scanned']} 个 .py 文件，"
            f"模块顶层第三方依赖违反 {dep_audit['n_module_level_violations']} 处，"
            f"函数体内 lazy import（可选依赖）{dep_audit['n_lazy_optional_imports']} 处。",
            "函数体内 lazy import 不违反零依赖约束：bp_screen/parser.py 的 openpyxl/pdfplumber、"
            "bp_screen/web.py 的 fastapi 均为可选功能，未装依赖时对应功能静默降级、核心逻辑照常。"
            "论文 §Reproducibility 应如实区分'核心零依赖'与'可选功能依赖'。",
            "本脚本不实际执行 reproduction_commands；论文复现步骤须逐条执行并"
            "与 CI 结果比对。命令序列已列入 manifest，供论文 §Reproducibility 引用。",
            "stat_summary.json 完备性只查 mean/std/n 三件套齐备，不验证数值与"
            "CI 历史一致——那是 CI 本身的职责（每次运行 bench 都会重算）。",
        ],
        "acceptance": acceptance,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="S2-A4 可复现性证据打包")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()

    manifest = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

    acc = manifest["acceptance"]
    dep = manifest["dependency_audit"]
    stat = manifest["stat_summary_verification"]
    print("=== S2-A4 可复现性证据打包 ===")
    print(f"环境: Python {manifest['environment']['python_version']} "
          f"on {manifest['environment']['platform']}")
    print()
    print("零依赖审计：")
    print(f"  扫描 .py 文件数: {dep['total_files_scanned']}")
    print(f"  模块顶层第三方违反: {dep['n_module_level_violations']}  ← 判失败阈值")
    print(f"  函数体 lazy import (可选): {dep['n_lazy_optional_imports']}")
    if dep["module_level_violations"]:
        for v in dep["module_level_violations"][:5]:
            print(f"    ❌ {v['file']}:{v['line']}  {v['kind']} {v['module']}")
        if len(dep["module_level_violations"]) > 5:
            print(f"    ... 共 {dep['n_module_level_violations']} 处")
    if dep["lazy_optional_imports"]:
        # 汇总 lazy imports
        from collections import Counter
        by_mod = Counter(v["module"] for v in dep["lazy_optional_imports"])
        for mod, n in by_mod.most_common():
            print(f"    🟡 lazy: {mod} ×{n}")
    print()
    print(f"文件指纹: {manifest['file_fingerprints']['total']} 个关键文件已哈希")
    print()
    print(f"stat_summary.json 完备性: {stat.get('verdict')} "
          f"(n={stat.get('n_history_entries')})")
    if stat.get("issues"):
        for i in stat["issues"][:5]:
            print(f"    ⚠️ {i}")
    print()
    print(f"复现命令: {len(manifest['reproduction_commands'])} 条")
    print()
    print("验收：")
    for k, v in acc.items():
        mark = "✅" if v else "❌"
        print(f"  {mark} {k}: {v}")
    print()
    print(f"已写入 {os.path.relpath(MANIFEST_PATH, ROOT)}")

    if args.strict and not acc["all_pass"]:
        print("\n❌ --strict 未通过")
        return 1
    if args.json:
        print("\n" + json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    return 0 if acc["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
