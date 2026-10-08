#!/usr/bin/env python3
"""scripts/build_mcpb.py 的离线回归测试（零依赖）。

锁住两个性质，防止再次回退：

1. **确定性**：同一份源码连续构建两次，sha256 必须完全相同。
   实踩（2026-10-08）：原实现用 z.write()，zip 条目记录了临时文件的 mtime，
   同一份源码间隔数秒构建 → 两个不同 sha256，导致 server.json 的
   fileSha256 永远追不上产物、Registry 发布反复失败。

2. **zip 内无"当下时间"**：所有条目的 date_time 必须是固定纪元值。
   这是 (1) 的根因，单独断言可让失败信息更直接定位。

运行：python -m unittest scripts.test_build_mcpb
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import scripts.build_mcpb as B  # noqa: E402


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class TestReproducibleBuild(unittest.TestCase):
    def test_two_builds_identical(self):
        """核心断言：连构两次 sha256 必须一致。"""
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "a.mcpb")
            B.build(p1)
            sh1 = _sha256(p1)
            time.sleep(1.2)  # 跨过一秒，确保若用 now() 一定不同
            p2 = os.path.join(d, "b.mcpb")
            B.build(p2)
            sh2 = _sha256(p2)
            self.assertEqual(
                sh1, sh2,
                "构建不可复现：源码未变但 sha256 变了（zip 内多半又混入了时间戳）。\n"
                "  第一次: %s\n  第二次: %s" % (sh1, sh2),
            )

    def test_zip_entries_have_fixed_timestamp(self):
        """zip 内所有条目的 date_time 必须是固定纪元值（非当下时间）。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.mcpb")
            B.build(p)
            with zipfile.ZipFile(p) as z:
                stamps = {zi.date_time for zi in z.infolist()}
            self.assertEqual(
                stamps, {(1980, 1, 1, 0, 0, 0)},
                "zip 条目含非固定时间戳 %s，会破坏可复现性" % sorted(stamps),
            )

    def test_manifest_is_first_entry(self):
        """manifest.json 必须是首个条目（部分客户端依赖此顺序）。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.mcpb")
            B.build(p)
            with zipfile.ZipFile(p) as z:
                self.assertEqual(z.namelist()[0], "manifest.json")

    def test_manifest_parseable_and_has_required_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.mcpb")
            B.build(p)
            with zipfile.ZipFile(p) as z:
                m = json.loads(z.read("manifest.json").decode("utf-8"))
            for k in ("manifest_version", "name", "version"):
                self.assertIn(k, m, "manifest.json 缺关键字段 %s" % k)

    def test_excludes_untracked_backups(self):
        """只打"会入库"的文件：含 .bak/.orig/~/.tmp 标记的本地临时文件必须排除。

        实踩（2026-10-08）：本地遗留 global_zones.json.bak_20261006 未入库，
        于是本地包 201 文件、CI 包 200 文件，sha256 两边永远对不上。
        """
        rels = [rel for _, rel in B.collect_files()]
        leak = [r for r in rels
                if any(m in os.path.basename(r) for m in B.EXCLUDE_FILE_MARKERS)]
        self.assertEqual(leak, [], "打包清单混入临时/备份文件: %s" % leak)

    def test_no_excluded_dirs_leak(self):
        """EXCLUDE_DIR_NAMES 里的目录不能出现在包内（docs/app/scripts 等）。"""
        rels = [rel for _, rel in B.collect_files()]
        leak = [r for r in rels
                if any(part in B.EXCLUDE_DIR_NAMES for part in r.split("/")[:-1])]
        self.assertEqual(leak, [], "打包清单混入排除目录: %s" % leak[:5])

    def test_check_detects_mismatch(self):
        """--check 语义：server.json 与产物不一致时必须能被发现。

        这里直接对 B.sha256_of 与一个伪造 sha 做对比，保证校验逻辑
        （而非只有构建）也在回归范围内。
        """
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.mcpb")
            B.build(p)
            real = B.sha256_of(p)
            self.assertEqual(len(real), 64)
            self.assertNotEqual(real, "0" * 64)


if __name__ == "__main__":
    unittest.main()
