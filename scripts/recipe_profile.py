"""recipe_profile.py — Env Recipe profile 四件套（M8-R2，报告 §M8-R2）。

依据 docs/per_module_deep_assessment_2026-10-13.md §M8-R2：
  152 份配方资产厚（8.0 分）但流转弱（4.0 分）；补 profile 四件套
  （export/import/diff/clone），让"资产厚"变为"资产活"。

设计约束：
  - 零依赖（stdlib only），使用 difflib 做结构化 diff。
  - 不改动配方本体；只做读写视图层。
  - 与 schemas/env_recipe.schema.json 契约兼容。
  - JSON 序列化使用 ensure_ascii=False + indent=2（可读）。
  - 所有操作幂等；import 覆盖前会备份旧文件到 .bak.<timestamp>。

CLI：
  python scripts/recipe_profile.py export <zone>__<crop>.json <out.json>
  python scripts/recipe_profile.py import <in.json> <zone>__<crop>.json
  python scripts/recipe_profile.py diff <a.json> <b.json>
  python scripts/recipe_profile.py clone <src.json> <zone>__<crop>.json
  python scripts/recipe_profile.py list              # 列出所有配方
  python scripts/recipe_profile.py stats             # 配方资产统计

Python API：
  from scripts.recipe_profile import export_recipe, import_recipe,
                                    diff_recipes, clone_recipe, list_recipes
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")


def _default_recipes_dir() -> str:
    return RECIPES_DIR


def _recipe_path(name: str, recipes_dir: str = "") -> str:
    """把 'zone__crop' 解析为绝对路径。"""
    base = recipes_dir or RECIPES_DIR
    if not name.endswith(".json"):
        name += ".json"
    return os.path.join(base, name)


def _load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def export_recipe(src_name: str, out_path: str,
                  recipes_dir: str = "",
                  include_sources: bool = True,
                  include_execution_log: bool = False,
                  include_outcome: bool = False) -> Dict[str, Any]:
    """把一份配方导出到任意 JSON 文件（供分享/备份/提交 review）。

    默认剥离 execution_log 与 outcome（这些是私有回流数据，不应随配方外传）；
    sources 保留（含溯源许可，对外交付必需）。

    参数：
      src_name: 配方文件名（如 "mediterranean__番茄.json"）
      out_path: 输出文件绝对/相对路径
      include_sources: 是否包含 sources 溯源（默认 True）
      include_execution_log: 是否包含 execution_log（默认 False，隐私保护）
      include_outcome: 是否包含 outcome（默认 False，隐私保护）

    返回：{exported_path, recipe_ref, size_bytes, keys_included, size_original}
    """
    src = _recipe_path(src_name, recipes_dir)
    if not os.path.exists(src):
        raise FileNotFoundError(f"配方不存在: {src}")
    recipe = _load(src)

    exported = copy.deepcopy(recipe)
    if not include_execution_log:
        exported.pop("execution_log", None)
    if not include_outcome:
        exported.pop("outcome", None)
    if not include_sources:
        exported.pop("sources", None)

    # 加导出元数据（不污染原契约，走 _profile_meta 扩展键）
    exported["_profile_meta"] = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_recipe": src_name,
        "source_sha256": _sha256_of(src),
        "export_options": {
            "include_sources": include_sources,
            "include_execution_log": include_execution_log,
            "include_outcome": include_outcome,
        },
        "generator": "scripts/recipe_profile.py",
        "profile_version": "1.0.0",
    }

    _save(out_path, exported)
    return {
        "exported_path": os.path.abspath(out_path),
        "recipe_ref": _recipe_ref_of(exported),
        "size_bytes": os.path.getsize(out_path),
        "keys_included": sorted(exported.keys()),
        "size_original_bytes": os.path.getsize(src),
    }


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
def import_recipe(in_path: str, dest_name: str = "",
                  recipes_dir: str = "",
                  backup: bool = True) -> Dict[str, Any]:
    """把导出的 JSON 导入为 data/env_recipes/ 下的正式配方。

    参数：
      in_path: 导入源文件路径
      dest_name: 目标文件名（省略则从 _profile_meta.source_recipe 或文件名推导）
      backup: 目标已存在时是否先备份到 .bak.<timestamp>

    返回：{imported_path, recipe_ref, overwrote, backup_path, keys}
    """
    src = _load(in_path)
    # 剥离导出元数据（不进入正式配方契约）
    src.pop("_profile_meta", None)

    if not dest_name:
        meta = src.get("_profile_meta", {}) if isinstance(src.get("_profile_meta"), dict) else {}
        dest_name = meta.get("source_recipe") or os.path.basename(in_path)
    if not dest_name.endswith(".json"):
        dest_name += ".json"

    dest = _recipe_path(dest_name, recipes_dir)
    existed_before = os.path.exists(dest)
    backup_path = None
    if existed_before and backup:
        backup_path = f"{dest}.bak.{int(time.time())}"
        os.rename(dest, backup_path)

    _save(dest, src)
    return {
        "imported_path": os.path.abspath(dest),
        "recipe_ref": _recipe_ref_of(src),
        "overwrote": existed_before,
        "backup_path": backup_path,
        "keys": sorted(src.keys()),
    }


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
_DIFF_IGNORE_KEYS = {"_profile_meta", "execution_log", "outcome"}


def diff_recipes(a_path: str, b_path: str,
                 ignore_keys: Optional[set] = None,
                 unified: bool = True) -> Dict[str, Any]:
    """结构化 diff 两份配方（忽略 execution_log/outcome 私有数据）。

    参数：
      a_path, b_path: 两份配方 JSON 路径
      ignore_keys: 要忽略的顶层键（默认忽略 _profile_meta/execution_log/outcome）
      unified: 返回 unified diff 文本（True）还是结构化变更（False）

    返回：
      {status: "identical"|"different",
       summary: {changed_keys, added_keys, removed_keys, added_entries, removed_entries},
       unified_diff: str (可选),
       details: List[Dict]（structured 模式）}
    """
    ignore = ignore_keys or set(_DIFF_IGNORE_KEYS)
    a = _load(a_path)
    b = _load(b_path)

    a_keys = {k: v for k, v in a.items() if k not in ignore}
    b_keys = {k: v for k, v in b.items() if k not in ignore}

    all_k = sorted(set(a_keys) | set(b_keys))
    changed, added, removed = [], [], []
    details = []

    for k in all_k:
        in_a, in_b = k in a_keys, k in b_keys
        if in_a and not in_b:
            removed.append(k)
            details.append({"kind": "removed", "key": k,
                            "value_a": a_keys[k]})
        elif in_b and not in_a:
            added.append(k)
            details.append({"kind": "added", "key": k,
                            "value_b": b_keys[k]})
        elif a_keys[k] != b_keys[k]:
            changed.append(k)
            details.append({"kind": "changed", "key": k,
                            "value_a": a_keys[k], "value_b": b_keys[k]})

    identical = (not changed and not added and not removed)

    out: Dict[str, Any] = {
        "status": "identical" if identical else "different",
        "a_path": a_path,
        "b_path": b_path,
        "a_ref": _recipe_ref_of(a),
        "b_ref": _recipe_ref_of(b),
        "summary": {
            "changed_keys": len(changed),
            "added_keys": len(added),
            "removed_keys": len(removed),
            "changed": changed,
            "added": added,
            "removed": removed,
        },
        "ignored_keys": sorted(ignore),
        "details": details,
    }
    if unified and not identical:
        # 用 difflib 做统一 diff（基于排序后的 JSON）
        def _dump(d: Dict[str, Any]) -> str:
            keys = {k: v for k, v in d.items() if k not in ignore}
            return json.dumps(keys, ensure_ascii=False, indent=2, sort_keys=True)
        lines = list(difflib.unified_diff(
            _dump(a).splitlines(), _dump(b).splitlines(),
            fromfile=f"a:{_recipe_ref_of(a)}",
            tofile=f"b:{_recipe_ref_of(b)}",
            lineterm="",
        ))
        out["unified_diff"] = "\n".join(lines)
    return out


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------
def clone_recipe(src_name: str, dest_name: str,
                 recipes_dir: str = "") -> Dict[str, Any]:
    """把一个配方 clone 为另一个 zone__crop 命名空间的副本。

    用途：把 mediterranean__番茄 派生为 highland__番茄，
    再针对目标分区修改 climate/environment 字段。
    """
    src = _recipe_path(src_name, recipes_dir)
    if not os.path.exists(src):
        raise FileNotFoundError(f"源配方不存在: {src}")
    dest = _recipe_path(dest_name, recipes_dir)
    if os.path.exists(dest):
        raise FileExistsError(f"目标配方已存在: {dest}")
    recipe = _load(src)
    # 保留原 clone 溯源
    recipe["_clone_from"] = {
        "source_recipe": src_name,
        "cloned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_sha256": _sha256_of(src),
        "generator": "scripts/recipe_profile.py",
    }
    _save(dest, recipe)
    return {
        "cloned_from": src_name,
        "cloned_to": dest_name,
        "path": os.path.abspath(dest),
        "size_bytes": os.path.getsize(dest),
    }


# ---------------------------------------------------------------------------
# list / stats / helper
# ---------------------------------------------------------------------------
def list_recipes(recipes_dir: str = "") -> List[Dict[str, Any]]:
    """列出所有配方的元信息（不加载完整内容）。"""
    base = recipes_dir or RECIPES_DIR
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(base, name)
        try:
            d = _load(path)
            crop = d.get("crop", {}).get("species", "?")
            stage = d.get("stage", "?")
            dc = d.get("device_profile", {}).get("device_class", "?")
            out.append({
                "filename": name,
                "recipe_ref": f"{crop}:{stage}:{dc}",
                "crop": crop,
                "stage": stage,
                "device_class": dc,
                "size_bytes": os.path.getsize(path),
                "sha256": _sha256_of(path)[:16],
            })
        except Exception:  # noqa: BLE001
            out.append({"filename": name, "error": "parse_failed"})
    return out


def recipe_stats(recipes_dir: str = "") -> Dict[str, Any]:
    """配方资产统计。"""
    items = list_recipes(recipes_dir)
    by_stage: Dict[str, int] = {}
    by_device: Dict[str, int] = {}
    for it in items:
        if "error" in it:
            continue
        by_stage[it["stage"]] = by_stage.get(it["stage"], 0) + 1
        by_device[it["device_class"]] = by_device.get(it["device_class"], 0) + 1
    total_size = sum(it.get("size_bytes", 0) for it in items)
    return {
        "total_recipes": len(items),
        "total_bytes": total_size,
        "by_stage": by_stage,
        "by_device_class": by_device,
        "profile_version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _recipe_ref_of(recipe: Dict[str, Any]) -> str:
    crop = (recipe.get("crop") or {}).get("species", "?")
    stage = recipe.get("stage", "?")
    dc = (recipe.get("device_profile") or {}).get("device_class", "?")
    return f"{crop}:{stage}:{dc}"


def _sha256_of(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s_export = sub.add_parser("export", help="导出配方到任意 JSON")
    s_export.add_argument("src_name")
    s_export.add_argument("out_path")
    s_export.add_argument("--include-execution-log", action="store_true")
    s_export.add_argument("--include-outcome", action="store_true")
    s_export.add_argument("--no-sources", action="store_true")

    s_import = sub.add_parser("import", help="从 JSON 导入为正式配方")
    s_import.add_argument("in_path")
    s_import.add_argument("dest_name", nargs="?", default="")
    s_import.add_argument("--no-backup", action="store_true")

    s_diff = sub.add_parser("diff", help="两份配方结构化 diff")
    s_diff.add_argument("a")
    s_diff.add_argument("b")
    s_diff.add_argument("--no-unified", action="store_true")

    s_clone = sub.add_parser("clone", help="克隆配方到另一命名空间")
    s_clone.add_argument("src_name")
    s_clone.add_argument("dest_name")

    sub.add_parser("list", help="列出所有配方")
    sub.add_parser("stats", help="配方资产统计")

    args = p.parse_args()

    if args.cmd == "export":
        r = export_recipe(args.src_name, args.out_path,
                          include_sources=not args.no_sources,
                          include_execution_log=args.include_execution_log,
                          include_outcome=args.include_outcome)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.cmd == "import":
        r = import_recipe(args.in_path, args.dest_name,
                          backup=not args.no_backup)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.cmd == "diff":
        r = diff_recipes(args.a, args.b, unified=not args.no_unified)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.cmd == "clone":
        r = clone_recipe(args.src_name, args.dest_name)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif args.cmd == "list":
        items = list_recipes()
        print(json.dumps({"count": len(items), "recipes": items},
                         ensure_ascii=False, indent=2))
    elif args.cmd == "stats":
        print(json.dumps(recipe_stats(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
