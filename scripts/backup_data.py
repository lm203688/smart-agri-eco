#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup_data.py —— 数据资产自动备份 + 清理旧备份

GAP_AUDIT §F2：4 个 `.bak_*` 文件手动 cp 出来，说明"没有备份策略"。本脚本：
  1) 在写操作前，把受保护数据文件备份到 `data/.backups/YYYY-MM-DD/`
  2) 保留最近 N 天的备份，超出自动清理
  3) 提供 list/clean/restore 三个子命令

不覆盖核心 atomic_write_json（那是写入原语）；本脚本是"人工触发的快照备份"，
供大规模变更前手工调用。

用法：
    python scripts/backup_data.py                     # 备份一次，按今天日期
    python scripts/backup_data.py --list              # 列出所有备份快照
    python scripts/backup_data.py --clean --keep 7    # 只保留最近 7 天
    python scripts/backup_data.py --restore <snap>    # 从某个快照恢复
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = ROOT / "data" / ".backups"

# 受保护的数据文件（相对 ROOT）
PROTECTED_FILES = [
    "data/crop_adapt_db.json",
    "data/knowledge_graph.json",
    "data/zone_meta/global_zones.json",
    "data/feedback_log.json",
    "data/execution_log.json",
    "data/preset_cities.json",
    "data/wofost_phenology_reference.json",
    "data/env_recipes/",  # 目录，整包备份
]


def _today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def _snap_dir(tag: str) -> Path:
    return BACKUP_ROOT / tag


def list_snapshots() -> list[Path]:
    if not BACKUP_ROOT.exists():
        return []
    return sorted([p for p in BACKUP_ROOT.iterdir() if p.is_dir()], reverse=True)


def do_backup() -> Path:
    today = _today()
    snap = _snap_dir(today)
    snap.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for rel in PROTECTED_FILES:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = snap / Path(rel).name if not rel.endswith("/") else snap / Path(rel).stem
        if src.is_dir():
            dst.mkdir(exist_ok=True)
            for child in src.iterdir():
                shutil.copy2(child, dst / child.name)
            copied.append(rel)
        else:
            shutil.copy2(src, dst)
            copied.append(rel)
    # 写一个 meta 文件，记录备份内容与源 sha256
    import hashlib
    meta = {"tag": today, "created_at": dt.datetime.now().isoformat(timespec="seconds"), "files": []}
    for rel in copied:
        src = ROOT / rel
        if not rel.endswith("/") and src.is_file():
            h = hashlib.sha256(src.read_bytes()).hexdigest()[:16]
            meta["files"].append({"path": rel, "sha256_16": h})
    (snap / "meta.json").write_text(
        __import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snap


def do_clean(keep_days: int) -> int:
    removed = 0
    snaps = list_snapshots()
    for snap in snaps[keep_days:]:
        shutil.rmtree(snap, ignore_errors=True)
        removed += 1
    return removed


def do_restore(snap_name: str) -> list[str]:
    snap = BACKUP_ROOT / snap_name
    if not snap.is_dir():
        print(f"❌ 快照不存在: {snap_name}")
        return []
    restored: list[str] = []
    for entry in snap.iterdir():
        if entry.name == "meta.json":
            continue
        # 从 meta 找原始路径
        try:
            import json
            meta = json.loads((snap / "meta.json").read_text(encoding="utf-8"))
            for f in meta["files"]:
                if f["path"].endswith(entry.name) and not f["path"].endswith("/"):
                    dst = ROOT / f["path"]
                    shutil.copy2(entry, dst)
                    restored.append(f["path"])
                    break
        except Exception as e:
            print(f"  ⚠  {entry.name}: meta 解析失败 {e}", file=sys.stderr)
    return restored


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--keep", type=int, default=7)
    p.add_argument("--restore", type=str, default=None)
    args = p.parse_args()

    if args.list:
        snaps = list_snapshots()
        if not snaps:
            print("（无备份）")
        else:
            for s in snaps:
                print(f"  {s.name}")
        return 0

    if args.clean:
        removed = do_clean(args.keep)
        print(f"✅ 清理 {removed} 个旧备份（保留最近 {args.keep} 天）")
        return 0

    if args.restore:
        restored = do_restore(args.restore)
        print(f"✅ 从 {args.restore} 恢复 {len(restored)} 个文件")
        for r in restored:
            print(f"   - {r}")
        return 0

    # 默认：备份
    snap = do_backup()
    print(f"✅ 已备份到 {snap.relative_to(ROOT)}（{len(list(snap.iterdir()))} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
