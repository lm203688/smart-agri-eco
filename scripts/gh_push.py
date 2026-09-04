#!/usr/bin/env python3
"""
把本地文件推送到 GitHub 远端（单 commit，走 Git Data API）。

为什么需要：本机 github.com:443 被封，`git push` 无法使用；本项目本地目录也不是
git clone，因此不能用 `git status` 判断待推改动。本项目所有提交都通过本脚本完成。

用法：
    python scripts/gh_push.py <token_file> <commit_message> <file1> [file2 ...]

参数说明：
    token_file    仅含一行 PAT 的临时文件（请勿用命令行参数直接传 token）
    commit_message 提交信息，支持多行
    files         相对仓库根的路径，可混合新文件与已存在文件

行为：
    - 单 commit、线性更新（force=false），远端其余文件保持不变
    - 推送后回读远端 tree 校验每个文件的 blob sha 是否一致
    - 退出码 0 = 成功；非 0 = 失败（含 HTTP 错误详情）

配套：推送前先跑 `python scripts/sync_check.py` 查看完整差异清单。

凭据提示：
    - 用 fine-grained PAT（需要 repository 的 Contents: read/write 权限）
    - 用完即删 token 文件：del 路径 或 rm 路径
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/repos/%s"


def blob_sha(path: str) -> str:
    """按 git 规则计算文件 blob sha，用于与远端比对。"""
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def call(token: str, repo: str, method: str, subpath: str, body=None) -> dict:
    url = (API % repo) + "/" + subpath
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s %s %s -> %s"
                         % (e.code, method, subpath, e.read().decode("utf-8")[:400]))


def main() -> int:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    token = open(sys.argv[1], encoding="utf-8").read().strip()
    message = sys.argv[2]
    rels = sys.argv[3:]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo = os.environ.get("AGRI_GH_REPO", "lm203688/smart-agri-eco")
    branch = os.environ.get("AGRI_GH_BRANCH", "main")

    ref = call(token, repo, "GET", "git/ref/heads/%s" % branch)
    head_sha = ref["object"]["sha"]
    parent = call(token, repo, "GET", "git/commits/%s" % head_sha)
    base_tree = parent["tree"]["sha"]
    print("远端 HEAD: %s  base_tree: %s" % (head_sha[:10], base_tree[:10]))
    print("待推送 %d 个文件" % len(rels))

    tree = call(token, repo, "GET", "git/trees/%s?recursive=1" % base_tree)
    remote = {i["path"]: i["sha"] for i in tree["tree"] if i["type"] == "blob"}

    entries = []
    for rel in rels:
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            raise SystemExit("本地文件不存在: %s" % full)
        with open(full, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        blob = call(token, repo, "POST", "git/blobs",
                    {"content": b64, "encoding": "base64"})
        local_sha = blob_sha(full)
        if blob["sha"] != local_sha:
            raise SystemExit("blob sha 不一致: %s" % rel)
        if rel not in remote:
            state = "新建"
        elif remote[rel] != local_sha:
            state = "更新"
        else:
            state = "无变化"
        print("  [%s] %s -> %s" % (state, rel, local_sha[:10]))
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": local_sha})

    new_tree = call(token, repo, "POST", "git/trees",
                    {"base_tree": base_tree, "tree": entries})
    if new_tree.get("truncated"):
        raise SystemExit("tree 被截断")

    commit = call(token, repo, "POST", "git/commits",
                  {"message": message, "tree": new_tree["sha"], "parents": [head_sha]})
    call(token, repo, "PATCH", "git/refs/heads/%s" % branch,
         {"sha": commit["sha"], "force": False})
    print("\ncommit: %s" % commit["sha"][:12])
    print("已更新 ref heads/%s" % branch)

    chk = call(token, repo, "GET", "git/trees/%s?recursive=1" % commit["tree"]["sha"])
    got = {i["path"]: i["sha"] for i in chk["tree"] if i["type"] == "blob"}
    missing = [e["path"] for e in entries if got.get(e["path"]) != e["sha"]]
    if missing:
        raise SystemExit("回读校验失败，远端缺: %s" % missing)
    print("回读校验通过：%d/%d" % (len(entries), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
