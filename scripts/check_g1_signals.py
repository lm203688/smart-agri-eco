#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G1 关注度信号追踪（外部关注度的代理指标）

G1 主指标是"MCP 外部调用 ≥500 / 独立调用方 ≥20"，但直接调用次数项目本身
无法从内部感知（无 API 网关/日志层）。本脚本追踪 GitHub 关注度指标
（stars/forks/watchers/open_issues/contributors/releases）作为**间接代理
指标**：关注度上升通常伴随调用尝试增加，是决策门倒计时期间的早期信号。

与 check_external_reachability.py 的分工：
- external_reachability：验证"入口活着"（HTTP 200）
- g1_signals：追踪"关注度变化"（数字趋势，跨时间）

用法：
    python scripts/check_g1_signals.py               # 摘要 + 与上次对比
    python scripts/check_g1_signals.py --json        # 结构化输出
    python scripts/check_g1_signals.py --ci          # FAIL 时退出 1
    python scripts/check_g1_signals.py --no-history  # 只打印，不追加历史

数据存储：.workbuddy/github_signals_history.json
（追加模式；每次一条记录，含 ISO 时间戳 + 所有指标）
历史文件不入版本控制（.workbuddy/ 已在 .gitignore）。

注意：
- GitHub API 无 token 每小时 60 次配额；本脚本单次调用消耗 1 次配额
- 403 响应被明确标注为 rate_limit，区分"限流"与"真失败"
- 首次运行无历史对比，只记录基线
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

REPO = "lm203688/smart-agri-eco"
API_URL = f"https://api.github.com/repos/{REPO}"
HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".workbuddy",
    "github_signals_history.json",
)

TIMEOUT = 15
USER_AGENT = "agri-eco-g1-signal-check/1.0 (+lm203688/smart-agri-eco)"

# 直连 + 默认 SSL context（同 check_external_reachability.py 的代理规避处理）
_SSL_CTX = ssl.create_default_context()
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPSHandler(context=_SSL_CTX),
)

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def fetch_repo(token: str | None = None) -> tuple[int, dict | None, str]:
    """GET 仓库元数据。返回 (status, parsed_json, error_detail)。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API_URL, method="GET", headers=headers)
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as r:
            body = r.read()
            try:
                return r.status, json.loads(body.decode("utf-8")), ""
            except Exception as e:
                return r.status, None, f"json_parse_error: {e}"
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            err_body = ""
        return e.code, None, f"HTTP {e.code}: {err_body}"
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"


def extract_signals(j: dict) -> dict:
    """从 GitHub repo 元数据提取关注的指标。缺失字段填 -1 表示未知。"""
    return {
        "stars": int(j.get("stargazers_count", -1)),
        "forks": int(j.get("forks_count", -1)),
        "watchers": int(j.get("subscribers_count", -1)),
        "open_issues": int(j.get("open_issues_count", -1)),
        "issues_enabled": bool(j.get("has_issues", True)),
        "is_fork": bool(j.get("fork", False)),
        "default_branch": j.get("default_branch", ""),
        "created_at": j.get("created_at", ""),
        "pushed_at": j.get("pushed_at", ""),
        "archived": bool(j.get("archived", False)),
    }


def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def append_history(record: dict) -> None:
    hist = load_history()
    hist.append(record)
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


def compare_with_previous(cur: dict, prev: dict | None) -> dict:
    """计算本次与上次记录的差值。prev=None 表示首次基线。"""
    if prev is None:
        return {"first_baseline": True, "deltas": {}}
    deltas = {}
    for k in ("stars", "forks", "watchers", "open_issues"):
        a = cur.get(k, 0)
        b = prev.get(k, 0)
        if a < 0 or b < 0:
            deltas[k] = None
        else:
            deltas[k] = a - b
    return {"first_baseline": False, "deltas": deltas}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--ci", action="store_true", help="FAIL 时退出 1")
    ap.add_argument("--no-history", action="store_true", help="不追加到历史文件")
    ap.add_argument("--token-file", help="含 GitHub PAT 的临时文件（可选，提升配额）")
    args = ap.parse_args()

    token = None
    if args.token_file and os.path.exists(args.token_file):
        try:
            with open(args.token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except Exception:
            pass

    status, body, err = fetch_repo(token)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    if body is None:
        # 403 特殊标签：GitHub API 无 token 每小时 60 次配额
        if status == 403:
            detail = f"rate_limit_403 (unauthenticated, 60/h) — {err}"
        else:
            detail = err or f"HTTP {status}"
        result = {
            "ts": now_iso,
            "repo": REPO,
            "status": FAIL,
            "detail": detail,
            "signals": None,
            "delta": None,
        }
        print_result(result, args)
        return 1 if args.ci else 0

    signals = extract_signals(body)
    hist = load_history()
    prev = hist[-1] if hist else None
    delta = compare_with_previous(signals, prev)

    record = {
        "ts": now_iso,
        "repo": REPO,
        "status": PASS,
        "signals": signals,
        "delta": delta,
    }
    if not args.no_history:
        append_history(record)

    print_result(record, args)
    return 0


def print_result(record: dict, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return

    ts = record["ts"]
    sig = record["signals"]
    delta = record.get("delta") or {}

    if record["status"] != PASS or sig is None:
        print(f"❌ G1 关注度信号获取失败 · {ts}")
        print(f"   repo: {record['repo']}")
        print(f"   detail: {record['detail']}")
        return

    print(f"G1 关注度信号 · {ts}")
    print("-" * 60)
    print(f"  ⭐ stars:      {sig['stars']}")
    print(f"  🍴 forks:      {sig['forks']}")
    print(f"  👀 watchers:   {sig['watchers']}")
    print(f"  📋 open_issues:{sig['open_issues']}")
    print(f"  📌 pushed_at:  {sig['pushed_at']}")
    print(f"  📅 created_at: {sig['created_at']}")
    print("-" * 60)
    if delta.get("first_baseline"):
        print("ℹ️  首次基线（无历史对比）")
    else:
        d = delta.get("deltas", {})
        def fmt(k):
            v = d.get(k)
            if v is None:
                return f"{k}: N/A"
            sign = "+" if v > 0 else ""
            return f"{k}: {sign}{v}"
        parts = [fmt(k) for k in ("stars", "forks", "watchers", "open_issues")]
        print("  与上次对比: " + " · ".join(parts))
        # 关注度趋势提示
        delta_stars = d.get("stars") or 0
        delta_forks = d.get("forks") or 0
        if delta_stars > 0 or delta_forks > 0:
            print("  ✅ 外部关注度上升——G1 早期正向信号")
        elif delta_stars == 0 and delta_forks == 0:
            print("  ⏸  关注度无变化——需继续 P0 主动投递")


if __name__ == "__main__":
    sys.exit(main())
