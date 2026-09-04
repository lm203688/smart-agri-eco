#!/usr/bin/env python3
"""
本地工作区 vs GitHub 远端 main 的内容一致性检查（只读，秒级）。

背景：本机 github.com:443 被封，推送走 GitHub API（Git Data API），本地目录因此
并不是 git 仓库，无法用 `git status` 判断「哪些改动还没推」。本脚本用
Git blob sha1 逐文件比对，给出精确差异清单。

用法：
    python scripts/sync_check.py                     # 匿名读取（要求仓库公开）
    python scripts/sync_check.py --token-file F      # 带 token（私有仓库可用）

退出码：0 = 完全一致；1 = 存在差异；2 = 请求失败。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

REPO = os.environ.get("AGRI_GH_REPO", "lm203688/smart-agri-eco")
BRANCH = os.environ.get("AGRI_GH_BRANCH", "main")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_DIRS = {".git", ".workbuddy", "__pycache__", ".venv", "node_modules", "outputs"}
EXCLUDE_FILES = {".env"}  # gitignored secret，不比对


def git_blob_sha(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def local_files() -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            if fn in EXCLUDE_FILES:
                continue
            out[rel] = git_blob_sha(full)
    return dict(sorted(out.items()))


def fetch(url: str, token: str, method: str = "GET", body=None):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode("utf-8")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def remote_files(token: str) -> tuple:
    tree = fetch(
        "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, BRANCH),
        token,
    )
    blobs = {i["path"]: i["sha"] for i in tree["tree"] if i["type"] == "blob"}
    return tree, blobs


def main() -> int:
    token = ""
    if "--token-file" in sys.argv:
        idx = sys.argv.index("--token-file")
        token = open(sys.argv[idx + 1], encoding="utf-8").read().strip()
    if not token:
        print("（匿名读取，仓库需为公开）")

    print("仓库: %s  分支: %s" % (REPO, BRANCH))
    try:
        tree, remote = remote_files(token)
    except urllib.error.HTTPError as e:
        print("请求失败: HTTP %d %s" % (e.code, e.read().decode("utf-8")[:200]))
        return 2
    except Exception as e:  # noqa: BLE001
        print("请求失败: %s" % e)
        return 2

    print("远端 HEAD tree: %s  文件数: %d  truncated=%s"
          % (tree["sha"][:10], len(remote), tree.get("truncated")))

    local = local_files()
    print("本地文件数: %d" % len(local))

    missing = [p for p in local if p not in remote]
    differ = [p for p in local if p in remote and local[p] != remote[p]]
    extra = [p for p in remote if p not in local]

    print("\n=== 远端缺失（新文件，需推送）: %d ===" % len(missing))
    for p in missing:
        print("  + %s" % p)
    print("=== 内容不一致（已变更，需推送）: %d ===" % len(differ))
    for p in differ:
        print("  ~ %s" % p)
    print("=== 远端独有（本地缺失，需确认）: %d ===" % len(extra))
    for p in extra:
        print("  ? %s" % p)

    if not (missing or differ or extra):
        print("\n✅ 本地与远端完全一致")
        return 0
    print("\n⚠️ 共 %d 处差异待处理" % (len(missing) + len(differ) + len(extra)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
