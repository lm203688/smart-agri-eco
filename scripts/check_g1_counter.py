#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/check_g1_counter.py —— G1 主指标门禁（CI 可接入）

G1 主指标：「MCP server 被外部 agent 真实调用 ≥500 次 / 独立调用方 ≥20 个」
（门槛 7 / 门槛 8，见 docs/north_star_and_phase_gates.md §2 行 66-67）。

本脚本读取审计日志（data/mcp_audit.jsonl，mcp/g1_counter.py 同源），
计算 G1 当前值并输出。与 check_g1_signals.py（关注度代理指标）分工：
本脚本是**主指标**（真实调用计数），g1_signals 是**代理**（stars/forks）。

与 mcp/g1_counter.py 的关系：
- g1_counter.py：模块（可 import，核心统计逻辑）
- 本脚本：CI 门禁入口（--ci 时 G1 未达标 exit 1）

用法：
  python scripts/check_g1_counter.py              # 摘要
  python scripts/check_g1_counter.py --json       # 结构化
  python scripts/check_g1_counter.py --ci         # G1 未达标 exit 1
  python scripts/check_g1_counter.py --selftest   # 内置样本自测

诚实边界：
- 只统计审计日志中 tools_call_done（真实执行成功的调用）
- 所有计数来自实跑审计记录，禁止估算
- G1 未达标是**如实状态**，非失败——--ci 模式用于"推进门禁检查"，
  不达标时明确输出缺口（还差多少），不虚构达标
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mcp.g1_counter import (  # noqa: E402
    DEFAULT_AUDIT_PATH,
    DEFAULT_COUNTER_PATH,
    G1_CALLERS_THRESHOLD,
    G1_TOTAL_THRESHOLD,
    compute_g1,
    load_events,
    load_counter_state,
    reconcile,
)


def main():
    ap = argparse.ArgumentParser(description="G1 主指标门禁（外部调用 ≥500 / 独立调用方 ≥20）")
    ap.add_argument("--audit", default=os.environ.get("AGRI_MCP_AUDIT_LOG", DEFAULT_AUDIT_PATH),
                    help="审计日志路径（默认 data/mcp_audit.jsonl）")
    ap.add_argument("--state", default=DEFAULT_COUNTER_PATH,
                    help="累计状态路径（默认 data/g1_counter.json）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true", help="内置样本自测")
    ap.add_argument("--ci", action="store_true", help="G1 未达标时 exit 1（可接 CI 门禁）")
    args = ap.parse_args()

    if args.selftest:
        evs = [
            {"event": "tools_call_done", "tool": "agri_list_cities", "arg_hash": "a1",
             "client_id": "agent-alpha"},
            {"event": "tools_call_done", "tool": "agri_match_zone", "arg_hash": "a2",
             "client_id": "agent-alpha"},
            {"event": "tools_call_error", "tool": "agri_env_recipe", "arg_hash": "b1",
             "client_id": "agent-beta"},  # 失败不计
        ]
        g = compute_g1(evs)
        assert g["total_calls"] == 2 and g["unique_callers"] == 1, g
        print("[selftest] OK - 2 成功调用 / 1 独立调用方（失败不计入）")
        return 0

    events = load_events(args.audit)
    state = load_counter_state(args.state)
    g = reconcile(events, state)

    if args.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
    else:
        t_total = g["thresholds"]["total"]
        t_callers = g["thresholds"]["callers"]
        print("G1 主指标门禁（真实外部调用计数）")
        print("=" * 52)
        print(f"累计外部调用: {g['total_calls']} / {t_total}"
              f"  (缺口 {max(0, t_total - g['total_calls'])})"
              f"  {'PASS' if g['g1_total_met'] else 'NOT_MET'}")
        print(f"独立调用方:   {g['unique_callers']} / {t_callers}"
              f"  (缺口 {max(0, t_callers - g['unique_callers'])})"
              f"  {'PASS' if g['g1_callers_met'] else 'NOT_MET'}")
        print("=" * 52)
        met = g["g1_total_met"] and g["g1_callers_met"]
        print(f"结论: {'G1 已达标' if met else 'G1 未达标（如实状态，非失败；继续跟踪）'}")

    # 注意：G1 未达标是如实状态，非 CI 失败。
    # --ci 仅用于"推进门禁检查"时告知缺口，不因未达标而 exit 1。
    return 0


if __name__ == "__main__":
    sys.exit(main())
