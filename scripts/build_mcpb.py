#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 MCPB 分发包并回填 server.json 的 fileSha256（零依赖，纯标准库）。

为什么走 MCPB 而不是 PyPI：
    MCP Registry 支持的两条 Python 相关路径：
      - registryType=pypi：需把包发布到 PyPI，用户经 `uvx` 运行。
      - registryType=mcpb：产物托管在 GitHub Releases，用户无需任何工具链。
    本项目定位是「零依赖、可离线、可私有化」，仓库直发 + 免 CI 安装更契合，
    因此主路径选 mcpb。（pypi 路径保留为备选，见 --pypi 说明。）

MCPB 的硬性要求（来自官方 package-types 文档）：
    1. identifier URL **必须含字符串 "mcp"**（文件名或仓库名均可）。
       本项目仓库名 `smart-agri-eco` 不含 "mcp"，故产物命名为 `agri-eco-mcp.mcpb`。
    2. server.json 必须带 `fileSha256`（客户端安装前会校验）。
    3. `.mcpb` 本质是 zip，含 manifest.json + 服务端代码。

用法：
    python scripts/build_mcpb.py                  # 构建 + 回填 sha256
    python scripts/build_mcpb.py --check          # 只校验已构建产物与 server.json 是否一致
    python scripts/build_mcpb.py --out dist/x.mcpb

退出码：0 = 成功；1 = 失败。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_JSON = os.path.join(ROOT, "server.json")
VERSION = "1.1.0"
# 文件名必须含 "mcp"（MCPB 校验规则）
DEFAULT_OUT = os.path.join(ROOT, "dist", "agri-eco-mcp-%s.mcpb" % VERSION)

# 打进去的内容：MCP server 及其依赖的最小闭包（零第三方依赖，故只需本项目代码 + 数据）
INCLUDE_DIRS = ["agent", "core", "engine", "mcp", "bp_screen", "skills", "schemas", "config"]
INCLUDE_FILES = ["LICENSE", "README.md", "pyproject.toml"]

# 排除项：与本包运行无关或体积大且敏感
EXCLUDE_DIR_NAMES = {"__pycache__", ".git", ".workbuddy", ".workbuddy-ai", ".venv",
                     "node_modules", "outputs", "_archive", "dist", "plugin",
                     ".github", "deploy", "docs", "app", "scripts", "harness"}
EXCLUDE_FILE_SUFFIX = (".pyc", ".pyo", ".log")
EXCLUDE_FILE_NAMES = {".env"}

# 本地临时备份（如 global_zones.json.bak_20261006）——未入库，故本地打进包、
# CI 打不进，两边文件数不同 -> sha256 必然不同。
# 实踩（2026-10-08）：本地 201 文件 vs CI 200 文件，差的就是一个 .bak 文件，
# 导致仓库里的 server.json 与 CI 发布的永远对不上。
EXCLUDE_FILE_MARKERS = (".bak", ".orig", "~", ".tmp")

# data/ 下要打包的内容（运行必需）：env_recipes + 核心 JSON 库
DATA_INCLUDE = [
    "data/env_recipes",
    "data/crop_adapt_db.json",
    "data/preset_cities.json",
    "data/zone_meta",
    "data/wofost_phenology_reference.json",
    "data/linkage_protocol.schema.json",
]


def build_manifest() -> dict:
    return {
        "manifest_version": "0.3",
        "name": "agri-eco",
        "display_name": "智慧农业生态 Agri-Eco",
        "version": VERSION,
        "description": (
            "面向分布式农业的 Agent-native 知识基座。14 个 MCP 工具："
            "Env Recipe 环境配方 / 气候分区匹配 / 作物推荐 / 种植计划 / "
            "物候播期 / 多源气候校准 / 土壤剖面 / 病虫害诊断 / 养分管理 / "
            "地理编码到配方 / 数据血缘 / 生态清单 / 预设城市 / 投资初筛。"
            "零第三方依赖，可完全离线运行。"
        ),
        "author": {"name": "lm203688", "url": "https://github.com/lm203688"},
        "homepage": "https://github.com/lm203688/smart-agri-eco",
        "repository": {
            "type": "git",
            "url": "https://github.com/lm203688/smart-agri-eco",
        },
        "license": "MIT",
        "keywords": ["agriculture", "agritech", "mcp", "env-recipe",
                     "phenology", "climate", "soil", "offline-first"],
        "server": {
            "type": "python",
            "entry_point": "mcp/server.py",
            "mcp_config": {
                "command": "python",
                "args": ["${__dirname}/mcp/server.py"],
                "env": {},
            },
        },
        "compatibility": {
            "platforms": ["darwin", "win32", "linux"],
            "runtimes": {"python": ">=3.10"},
        },
    }


def _should_include_dir(dirname: str) -> bool:
    return dirname not in EXCLUDE_DIR_NAMES


def collect_files() -> list:
    """返回 (绝对路径, 包内相对路径) 列表。"""
    out = []
    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if _should_include_dir(x)]
            for fn in filenames:
                if fn.endswith(EXCLUDE_FILE_SUFFIX) or fn in EXCLUDE_FILE_NAMES:
                    continue
                if any(m in fn for m in EXCLUDE_FILE_MARKERS):
                    continue
                full = os.path.join(dirpath, fn)
                out.append((full, os.path.relpath(full, ROOT).replace(os.sep, "/")))
    for f in INCLUDE_FILES:
        full = os.path.join(ROOT, f)
        if os.path.isfile(full):
            out.append((full, f))
    for d in DATA_INCLUDE:
        p = os.path.join(ROOT, d)
        if os.path.isfile(p):
            out.append((p, d))
        elif os.path.isdir(p):
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = [x for x in dirnames if _should_include_dir(x)]
                for fn in filenames:
                    if fn.endswith(EXCLUDE_FILE_SUFFIX):
                        continue
                    if any(m in fn for m in EXCLUDE_FILE_MARKERS):
                        continue
                    full = os.path.join(dirpath, fn)
                    out.append((full, os.path.relpath(full, ROOT).replace(os.sep, "/")))
    return sorted(out, key=lambda t: t[1])


def build(out_path: str) -> str:
    """打包 MCPB（zip），**确定性可复现**：同一份源码 => 同一个 sha256。

    实踩（2026-10-08）：原实现用 ``z.write(full, rel)``，而 zip 条目会记录
    文件的 mtime —— 于是同一份源码间隔几十秒构建两次，sha256 就不同
    （a7593649… / af4b7333…）。后果是 ``server.json`` 里的 ``fileSha256``
    永远追不上产物，Registry 的"声明哈希 == 实际下载哈希"校验反复失败，
    排查方向被误导到"资产没上传"上，实际根因在此。

    修法：不落盘任何"当下时间"，显式构造 ZipInfo（固定 date_time、
    固定权限位），条目顺序也已由 collect_files 的 sorted 保证。
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    files = collect_files()
    manifest = build_manifest()

    # 固定为 1980-01-01 00:00:00（zip 纪元下限）。
    # 不能用 datetime.now()，否则破坏可复现性。
    FIXED_DT = (1980, 1, 1, 0, 0, 0)
    FIXED_MODE = 0o644

    def _info(name: str) -> zipfile.ZipInfo:
        zi = zipfile.ZipInfo(filename=name, date_time=FIXED_DT)
        zi.compress_type = zipfile.ZIP_DEFLATED
        # 只保留权限位，去掉文件类型/可变位，避免平台差异
        zi.external_attr = (FIXED_MODE & 0xFFFF) << 16
        zi.create_system = 3  # 固定为 Unix，避免 Windows/Linux 产物不同
        return zi

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        blob = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        z.writestr(_info("manifest.json"), blob)
        for full, rel in files:
            with open(full, "rb") as f:
                payload = f.read()
            z.writestr(_info(rel), payload)
    return out_path


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def update_server_json(sha: str, filename: str) -> None:
    with open(SERVER_JSON, "r", encoding="utf-8") as f:
        doc = json.load(f)
    url = ("https://github.com/lm203688/smart-agri-eco/releases/download/"
           "v%s/%s" % (VERSION, filename))
    doc["version"] = VERSION
    doc["packages"][0]["identifier"] = url
    doc["packages"][0]["fileSha256"] = sha
    with open(SERVER_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    check = "--check" in sys.argv
    out = DEFAULT_OUT
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]

    if check:
        if not os.path.exists(out):
            print("❌ 未找到产物 %s（先跑 python scripts/build_mcpb.py）" % out)
            return 1
        sha = sha256_of(out)
        with open(SERVER_JSON, "r", encoding="utf-8") as f:
            doc = json.load(f)
        want = doc["packages"][0].get("fileSha256", "")
        if sha != want:
            print("❌ server.json 的 fileSha256 与产物不一致")
            print("   产物: %s" % sha)
            print("   清单: %s" % want)
            print("   修复: python scripts/build_mcpb.py")
            return 1
        if "mcp" not in doc["packages"][0]["identifier"]:
            print("❌ identifier URL 不含 'mcp'（MCPB 校验会失败）")
            return 1
        print("✅ MCPB 产物与 server.json 一致")
        print("   sha256: %s" % sha)
        return 0

    path = build(out)
    sha = sha256_of(path)
    fname = os.path.basename(path)
    update_server_json(sha, fname)

    size = os.path.getsize(path)
    n = len(collect_files())
    print("✅ 已构建 %s" % os.path.relpath(path, ROOT))
    print("   文件数: %d   体积: %.2f MB" % (n, size / 1048576))
    print("   sha256: %s" % sha)
    print("   已回填 server.json")
    print()
    print("下一步：")
    print("   1. 在 GitHub 创建 Release，tag = v%s" % VERSION)
    print("   2. 上传 %s 作为 Release asset" % fname)
    print("   3. 运行 mcp-publisher login github && mcp-publisher publish")
    return 0


if __name__ == "__main__":
    sys.exit(main())
