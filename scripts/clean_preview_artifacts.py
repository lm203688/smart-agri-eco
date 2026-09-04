#!/usr/bin/env python3
"""
清理 HTML 里被预览工具注入的 data-page-node-id 属性。

背景（真实事故）：本地 HTML 文件被在线预览后，预览系统会在几乎每个标签上写入
data-page-node-id="xxxx" 属性用于节点定位。这些属性会污染源码（本仓库 app/index.html
曾一次性被注入 115 处，体积 20419 → 25364 字节），一旦提交会污染仓库与部署产物。

用法：
    python scripts/clean_preview_artifacts.py                 # 默认清理 app/index.html
    python scripts/clean_preview_artifacts.py app/x.html      # 指定文件
    python scripts/clean_preview_artifacts.py --dry-run       # 只看差异，不改文件
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TARGET = os.path.join(ROOT, "app", "index.html")

# 形如 ` data-page-node-id="AbCd1234"` —— 前导空格 + 属性名 + 字符串值
NODE_ID_ATTR = re.compile(r'\s+data-page-node-id="[^"]*"')


def clean(text: str) -> tuple[str, int]:
    cleaned, n = NODE_ID_ATTR.subn("", text)
    return cleaned, n


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    targets = args or [DEFAULT_TARGET]

    total = 0
    for t in targets:
        path = t if os.path.isabs(t) else os.path.join(ROOT, t)
        if not os.path.exists(path):
            print(f"跳过（不存在）: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            original = f.read()
        before = len(original)
        cleaned, n = clean(original)
        total += n
        if n == 0:
            print(f"✅ {os.path.relpath(path, ROOT)}: 无注入残留")
            continue
        print(
            f"🧹 {os.path.relpath(path, ROOT)}: 清理 {n} 处注入属性，"
            f"{before} → {len(cleaned)} 字节"
        )
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                f.write(cleaned)
    print(f"\n合计清理 {total} 处" + ("（dry-run，未写盘）" if dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
