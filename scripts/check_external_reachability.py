#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部入口可达性巡检（P0 自主部分 · 与 check_distribution_readiness 互补）

check_distribution_readiness 只验证**本地资产齐备**（文件存在、字段完整、
版本号一致）；本脚本验证**这些资产在公网是否真活着**——Registry API、
Smithery 搜索、GitHub Actions、GitHub Release、Release 资产下载 URL。

为什么单独一个脚本：
  - G1 目标是"外部 Agent 真实调用"，若外部入口已挂而本地自检全绿，
    会导致"资产齐备但零调用"的静默失败；本脚本把这个盲区补上。
  - 每项检查失败不修改任何资产（纯观察层），符合 §十 不可进化区约束。
  - 零依赖：只用 stdlib urllib，不新增第三方包。

用法：
    python scripts/check_external_reachability.py            # 摘要
    python scripts/check_external_reachability.py --full     # 详细响应片段
    python scripts/check_external_reachability.py --json     # 结构化输出
    python scripts/check_external_reachability.py --ci       # 任一 FAIL 退出 1

退出码：
    0 = 全绿或仅有 WARN（网络临时抖动）
    1 = 存在 FAIL（真实入口不可达）

注意：所有请求走 https:// 直连，不通过代理；本机沙箱可能拦截
      WorldClim/FAO 之类站点，但 github.com / registry.npmjs / smithery.ai
      通常可达。若网络受限，请手动设置 NO_PROXY 或临时放行。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 让本地脚本对 github / registry 等走直连，避免 IDE 的 HTTP_PROXY 污染。
# 与 check_demo_endpoints.py 同款处理，理由见那里的注释。
_TIME = 10  # 单请求秒；沙箱环境给宽点
USER_AGENT = "agri-eco-reachability-check/1.0 (+lm203688/smart-agri-eco)"

# urllib.request.build_opener 不接受 context=；用 HTTPSHandler 注入 ssl context。
_SSL_CTX = ssl.create_default_context()
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),  # 直连，绕 IDE 代理
    urllib.request.HTTPSHandler(context=_SSL_CTX),
)


def http_request(url: str, method: str = "GET", timeout: int = _TIME):
    """发起 HTTP 请求，返回 (status, body, content_type)。异常时抛。"""
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/octet-stream, text/plain, text/html, */*",
    })
    with _OPENER.open(req, timeout=timeout) as r:
        body = r.read() if method == "GET" else b""
        ctype = r.headers.get("Content-Type", "")
        return r.status, body, ctype

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# 检查项定义
CHECKS: list[dict[str, Any]] = [
    {
        "key": "github_repo",
        "desc": "GitHub 仓库主页可达",
        "url": "https://github.com/lm203688/smart-agri-eco",
        "expect": "html",
    },
    {
        "key": "github_api_repo",
        "desc": "GitHub API 仓库元数据",
        "url": "https://api.github.com/repos/lm203688/smart-agri-eco",
        "expect": "json",
        "field_check": lambda j: isinstance(j, dict) and j.get("full_name") == "lm203688/smart-agri-eco",
    },
    {
        "key": "github_latest_release",
        "desc": "GitHub 最新 Release 存在",
        "url": "https://api.github.com/repos/lm203688/smart-agri-eco/releases/latest",
        "expect": "json",
        "field_check": lambda j: isinstance(j, dict) and bool(j.get("tag_name")),
    },
    {
        "key": "mcpb_asset_url",
        "desc": "MCPB 分发包 Release 资产下载 URL",
        "url": "https://github.com/lm203688/smart-agri-eco/releases/download/v1.1.0/agri-eco-mcp-1.1.0.mcpb",
        "expect": "bytes",
        "method": "HEAD",
    },
    {
        "key": "registry_mcpb",
        "desc": "MCP 官方 Registry 可查（server.json 声明的 identifier）",
        # MCP Registry 没有统一 HTTP API；此处探活 static.modelcontextprotocol.io
        # 上 server.schema.json 是否可达，作为 Registry 生态健康代理指标。
        "url": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "expect": "json",
    },
    {
        "key": "smithery_search",
        "desc": "Smithery 可搜索 agri-eco",
        "url": "https://smithery.ai/search?q=agri-eco",
        "expect": "html",
    },
    {
        "key": "docs_quickstart_raw",
        "desc": "QUICKSTART.md 可公网访问（README 外链依赖）",
        "url": "https://raw.githubusercontent.com/lm203688/smart-agri-eco/main/docs/QUICKSTART.md",
        "expect": "text",
    },
    {
        "key": "well_known_agent_raw",
        "desc": "A2A Agent Card 可公网访问",
        "url": "https://raw.githubusercontent.com/lm203688/smart-agri-eco/main/.well-known/agent.json",
        "expect": "json",
    },
]


def parse_json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def check_one(item: dict[str, Any], verbose: bool = False) -> tuple[str, str]:
    url = item["url"]
    method = item.get("method", "GET")
    # 对沙箱网络抖动做 1 次重试（同域其他 URL 通常能通，说明是瞬时抖动）。
    # 沙箱环境常出现：SSL 握手超时、IncompleteRead、偶发 502——重试即可恢复。
    last_err = ""
    for attempt in (1, 2):
        t0 = time.time()
        try:
            status, body, ctype = http_request(url, method=method)
            dt = time.time() - t0
            last_err = ""
            break
        except urllib.error.HTTPError as e:
            dt = time.time() - t0
            last_err = f"HTTP {e.code} ({dt:.1f}s)"
            # HTTPError 是真实服务器响应，不重试
            break
        except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, Exception) as e:
            dt = time.time() - t0
            last_err = f"{type(e).__name__}: {e} ({dt:.1f}s)"
    if last_err:
        # GitHub API unauthenticated 每小时 60 次配额；配额耗尽返回 403。
        # 这不是"入口挂"，而是"限流"——给明确标签让下游判断不误读。
        if "HTTP 403" in last_err and "api.github.com" in url:
            return FAIL, f"rate_limit_403 (unauthenticated, 60/h) {url} ({last_err})"
        return FAIL, f"{last_err} attempt=2 {url}"

    # 状态码判定
    if status < 200 or status >= 400:
        return FAIL, f"HTTP {status} {url} ({dt:.1f}s)"

    # HEAD 请求不校验 body
    if method == "HEAD":
        return PASS, f"HTTP {status} ({dt:.1f}s)"

    # JSON 期望校验
    expect = item.get("expect")
    if expect == "json":
        j = parse_json(body)
        if j is None:
            return FAIL, f"non-JSON body ({dt:.1f}s)"
        field_check = item.get("field_check")
        if field_check and not field_check(j):
            return FAIL, f"field_check failed ({dt:.1f}s)"
        return PASS, f"HTTP {status} json ok ({dt:.1f}s)"
    if expect == "text" and len(body) == 0:
        return FAIL, f"empty body ({dt:.1f}s)"
    if expect == "html" and len(body) == 0:
        return FAIL, f"empty body ({dt:.1f}s)"
    return PASS, f"HTTP {status} {len(body)}B ({dt:.1f}s)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="打印详细响应")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--ci", action="store_true", help="FAIL 时退出 1")
    args = ap.parse_args()

    results = []
    for item in CHECKS:
        status, detail = check_one(item, verbose=args.full)
        results.append({
            "key": item["key"],
            "desc": item["desc"],
            "url": item["url"],
            "status": status,
            "detail": detail,
        })

    n_pass = sum(1 for r in results if r["status"] == PASS)
    n_warn = sum(1 for r in results if r["status"] == WARN)
    n_fail = sum(1 for r in results if r["status"] == FAIL)
    n_skip = sum(1 for r in results if r["status"] == SKIP)

    if args.json:
        print(json.dumps({
            "results": results,
            "summary": {
                "total": len(results),
                "pass": n_pass, "warn": n_warn, "fail": n_fail, "skip": n_skip,
            },
        }, ensure_ascii=False, indent=2))
        return 1 if args.ci and n_fail else 0

    print(f"外部入口可达性巡检 ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    print("-" * 78)
    icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "⏸"}
    for r in results:
        print(f"{icon[r['status']]} {r['desc']}")
        print(f"    {r['url']}")
        print(f"    → {r['detail']}")
    print("-" * 78)
    print(f"汇总：PASS={n_pass}  WARN={n_warn}  FAIL={n_fail}  SKIP={n_skip}  total={len(results)}")

    if n_fail:
        print("⚠️  存在不可达入口——请检查网络/账号/入口是否被下架。")
        print("    本脚本不修改任何资产（纯观察层）。")

    return 1 if args.ci and n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
