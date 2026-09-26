#!/usr/bin/env python3
"""
scripts/env_recipe_diff.py —— Env Recipe 生命周期工具（零依赖）

补齐 Env Recipe 的「生命周期」能力，对标 Horticulture-Assistant 的 profile
生命周期设计（export / import / diff / versioning，见 docs/competitive_scan_2026-09-17.md）。
此前 Env Recipe 只有「写」和「校验」，缺「变更可追溯」——批量改 110 份配方后
无法回答「谁改了什么」，也无法回滚。

三个动作（互不依赖，可单独用）：
    python scripts/env_recipe_diff.py snapshot <recipes_dir> <snapshot_out.json>
        导出当前配方库指纹（每份配方一个全文指纹 + 语义字段逐个指纹）
    python scripts/env_recipe_diff.py diff <recipes_dir> <snapshot.json>
        与快照对比：列出 新增 / 删除 / 修改，以及修改的字段级变更
    python scripts/env_recipe_diff.py verify <snapshot.json>
        校验快照自身完整性（条目数、字段齐全）

设计约束：
  - 纯标准库（json / hashlib / os / sys），符合本项目零第三方依赖
  - 快照只存指纹与摘要，不存配方全文——快照文件不会变成第二份配方数据源
  - 字段级可比性靠「每个语义字段单独存指纹」实现，不需要快照持有全文
  - 快照写入 data/ 下时由调用方决定是否提交 git（建议提交，才有跨日可比性）
  - 退出码：0=无变化或校验通过，1=有变化/校验失败，2=用法或输入错误

注意：不修改任何配方文件，纯只读对比 + 显式写入指定快照路径。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_SCHEMA = "agri-recipe-snapshot/v1"

# 参与「语义变更」判定的字段：配方可执行语义的主要载体。
# execution_log / outcome 故意不纳入语义字段——它们是独占回流数据，
# 一旦用户开始回流，diff 会因回流数据天天变红，淹没「配置变更」信号。
SEMANTIC_KEYS = ("protocol", "recipe_version", "crop", "stage", "device_profile",
                 "environment", "exception_handling", "sources", "license", "license_scope")


def _sha256(obj: Any) -> str:
    """稳定序列化后取 sha256，键排序保证与写入顺序无关。"""
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _digest(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """一份配方的全文指纹 + 语义字段逐个指纹。"""
    return {
        "full_sha256": _sha256(recipe),
        "semantic_sha256": _sha256({k: recipe.get(k) for k in SEMANTIC_KEYS}),
        "field_sha256": {k: _sha256(recipe.get(k)) for k in SEMANTIC_KEYS},
        "recipe_version": recipe.get("recipe_version"),
        "protocol": recipe.get("protocol"),
    }


def load_recipes(dir_path: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """读一个目录下所有 .json 配方，返回 {文件名: 配方} 与读取错误列表。

    约定：以 `_` 开头的 .json 视为内部文件并跳过。原因——若快照被写进配方目录
    （如 `data/env_recipes/_snapshot.json`），它本身是合法 JSON 且以 .json 结尾，
    会被当成配方读进来，导致 diff 永远报出「新增 1 份：_snapshot.json」的假变更。
    该约定与项目既有的 `_demo_runtime/` 内部目录约定一致。
    """
    out: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    if not os.path.isdir(dir_path):
        return out, ["目录不存在: %s" % dir_path]
    for name in sorted(os.listdir(dir_path)):
        if not name.endswith(".json"):
            continue
        if name.startswith("_"):
            continue
        try:
            with open(os.path.join(dir_path, name), "r", encoding="utf-8") as f:
                out[name] = json.load(f)
        except Exception as exc:  # noqa: BLE001 - 报告而非崩溃
            errors.append("%s: %s" % (name, exc))
    return out, errors


def build_snapshot(dir_path: str) -> Dict[str, Any]:
    """构建快照对象（不落盘）。"""
    recipes, errors = load_recipes(dir_path)
    return {
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "source_dir": os.path.abspath(dir_path),
        "recipe_count": len(recipes),
        "errors": errors,
        "recipes": {name: _digest(rec) for name, rec in sorted(recipes.items())},
    }


def export_snapshot(dir_path: str, out_path: str) -> Dict[str, Any]:
    snap = build_snapshot(dir_path)
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)
    return snap


def _load_snapshot(path: str) -> Tuple[Dict[str, Any], List[str]]:
    if not os.path.isfile(path):
        return {}, ["快照文件不存在: %s" % path]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), []


def verify_snapshot(path: str) -> Tuple[bool, List[str]]:
    """校验快照自身完整性。"""
    snap, errs = _load_snapshot(path)
    problems: List[str] = list(errs)
    if not snap:
        return False, problems or ["快照为空"]
    if snap.get("snapshot_schema") != SNAPSHOT_SCHEMA:
        problems.append("snapshot_schema 不匹配: %r" % snap.get("snapshot_schema"))
    recipes = snap.get("recipes")
    if not isinstance(recipes, dict):
        return False, problems + ["缺 recipes 映射"]
    if snap.get("recipe_count") != len(recipes):
        problems.append("recipe_count=%r 与实际条目数 %d 不一致"
                        % (snap.get("recipe_count"), len(recipes)))
    for name, digest in recipes.items():
        for field in ("full_sha256", "semantic_sha256", "field_sha256"):
            if field not in digest:
                problems.append("%s 缺字段 %r" % (name, field))
    return (not problems), problems


def diff_against(dir_path: str, snap_path: str) -> Dict[str, Any]:
    """当前配方库 vs 快照，返回结构化差异（含字段级变更）。"""
    snap, errs = _load_snapshot(snap_path)
    current, cur_errors = load_recipes(dir_path)
    baseline = snap.get("recipes") or {}

    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    modified: List[Dict[str, Any]] = []

    for name in sorted(set(current) & set(baseline)):
        dig = _digest(current[name])
        old = baseline[name]
        if dig["full_sha256"] == old.get("full_sha256"):
            continue
        entry: Dict[str, Any] = {"recipe": name, "full_changed": True}
        if dig["semantic_sha256"] == old.get("semantic_sha256"):
            # 全文变了但语义字段没变 → 只动了回流数据/元数据，不触发配置变更告警
            entry["semantic_changed"] = False
            entry["note"] = "仅回流数据或元数据变更"
        else:
            entry["semantic_changed"] = True
            entry["changed_keys"] = sorted(
                k for k in SEMANTIC_KEYS
                if dig["field_sha256"][k] != (old.get("field_sha256") or {}).get(k)
            )
        modified.append(entry)

    errors = errs + cur_errors
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "summary": {
            "baseline_count": len(baseline),
            "current_count": len(current),
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
        },
        "errors": errors,
    }


def fmt_report(report: Dict[str, Any], limit: int = 20) -> str:
    """把 diff 报告格式化为可读文本。"""
    s = report["summary"]
    lines = ["== Env Recipe 差异报告 ==",
             "基线 %d 份 → 当前 %d 份" % (s["baseline_count"], s["current_count"]),
             "新增 %d / 删除 %d / 修改 %d" % (s["added"], s["removed"], s["modified"])]
    if report["added"]:
        lines.append("新增:")
        lines.extend("  + %s" % n for n in report["added"][:limit])
    if report["removed"]:
        lines.append("删除:")
        lines.extend("  - %s" % n for n in report["removed"][:limit])
    if report["modified"]:
        lines.append("修改:")
        for m in report["modified"][:limit]:
            if m.get("semantic_changed"):
                lines.append("  ~ %s（语义变更：%s）" % (m["recipe"], ", ".join(m.get("changed_keys", []))))
            else:
                lines.append("  ~ %s（%s）" % (m["recipe"], m.get("note", "仅非语义字段变更")))
    if report["errors"]:
        lines.append("读取错误:")
        lines.extend("  ! %s" % e for e in report["errors"])
    for group in ("added", "removed", "modified"):
        if len(report[group]) > limit:
            lines.append("  … %s 另有 %d 项略" % (group, len(report[group]) - limit))
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip())
        return 2
    action, target, second = argv[1], argv[2], (argv[3] if len(argv) > 3 else None)

    if action == "snapshot":
        if second is None:
            print("用法: snapshot <recipes_dir> <snapshot_out.json>")
            return 2
        snap = export_snapshot(target, second)
        print("快照已写入 %s（%d 份配方）" % (second, snap["recipe_count"]))
        if snap["errors"]:
            print("读取错误 %d 处" % len(snap["errors"]))
        return 0

    if action == "diff":
        if second is None:
            print("用法: diff <recipes_dir> <snapshot.json>")
            return 2
        report = diff_against(target, second)
        print(fmt_report(report))
        return 1 if (report["summary"]["added"] or report["summary"]["removed"]
                     or report["summary"]["modified"] or report["errors"]) else 0

    if action == "verify":
        ok, problems = verify_snapshot(target)
        if ok:
            print("快照校验通过")
            return 0
        print("快照校验失败:")
        for p in problems:
            print("  ! %s" % p)
        return 1

    print("未知动作: %r（支持 snapshot / diff / verify）" % action)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
