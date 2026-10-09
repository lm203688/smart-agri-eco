#!/usr/bin/env python3
"""scripts/drive_push.py —— 按批次驱动 gh_push.py 推送本地待推文件（零凭据落库）。

用途：bash 命令长度受限（~8000 字符），一次传 139 个路径会溢出。
本脚本把待推清单分 3 批，每批独立调用 gh_push.py 创建 commit。
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(ROOT, ".workbuddy-ai", "tmp", "pat_push.txt")
DIFF_FILE = os.path.join(ROOT, ".workbuddy-ai", "tmp", "remain_new.txt")
BATCH = 50
MSG = ("feat(dist): P1-1 Env Recipe v1.2 派生量(DLI/播种深度) + P1-9 MCP 自测纳入unittest "
       "+ P1-2 sources三字段 + 修复分发就绪度判定bug")

BATCH = 50


def main() -> int:
    with open(DIFF_FILE, encoding="utf-8") as f:
        files = [l.strip() for l in f if l.strip()]
    print("待推文件总数:", len(files))
    for i in range(0, len(files), BATCH):
        batch = files[i:i + BATCH]
        cmd = [sys.executable, "-S", "-P",
               os.path.join(ROOT, "scripts", "gh_push.py"),
               TOKEN_FILE, "%s (batch %d/%d)" % (MSG, i // BATCH + 1, (len(files) + BATCH - 1) // BATCH)]
        cmd += batch
        print("=" * 50)
        print("batch %d/%d  (%d files)" % (i // BATCH + 1, (len(files) + BATCH - 1) // BATCH, len(batch)))
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        print((r.stdout or "") + (r.stderr or ""))
        if r.returncode != 0:
            print("!!! batch 失败 rc=%d" % r.returncode)
            return r.returncode
    print("=" * 50)
    print("全部批次推送完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())