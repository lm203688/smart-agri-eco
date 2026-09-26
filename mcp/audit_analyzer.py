#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp/audit_analyzer.py —— MCP 安全审计日志异常行为分析器（零依赖）

对齐 GOAI CyberGuard 提升点「行为监控机制」。
离线分析 AGRI_MCP_AUDIT_LOG（或 --log 指定）中的审计记录，检测异常行为
并输出 WARN/INFO 报告。**不修改 server、不扩张 MCP 接口、不触网**。

检测维度：
  1. 超长请求拒绝占比（DoS 试探信号）
  2. 未知工具调用次数（探测/错误客户端信号）
  3. 工具调用错误率（实现缺陷或异常输入信号）
  4. 审计完整性（tools_call_request 缺 arg_hash）
  5. 高频工具 Top3（可观测性，INFO）

用法：
  python mcp/audit_analyzer.py --log /path/to/audit.log
  AGRI_MCP_AUDIT_LOG=/path python mcp/audit_analyzer.py
  python mcp/audit_analyzer.py --selftest        # 内置样本自测
"""
from __future__ import annotations
import json
import os
import sys
import argparse
from collections import Counter

# 异常检测阈值（可按运营经验调参）
THRESH = {
    "oversize_ratio": 0.2,    # 超长拒绝占总请求比例上限
    "unknown_tool_max": 5,    # 未知工具拒绝次数上限
    "error_ratio": 0.3,       # 工具调用错误率上限
}


def load_events(path: str):
    """逐行解析审计日志，兼容 `[mcp_audit]` 前缀（stderr 混排场景）。"""
    evs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                evs.append(json.loads(line))
            except Exception:
                if line.startswith("[mcp_audit]"):
                    try:
                        evs.append(json.loads(line[len("[mcp_audit]"):].strip()))
                    except Exception:
                        pass
    return evs


def analyze(evs: list):
    issues = []
    total_req = sum(
        1 for e in evs
        if e.get("event") in ("tools_call_request", "request_rejected")
    )
    oversize = [e for e in evs
                if e.get("event") == "request_rejected" and e.get("reason") == "oversize"]
    unknown = [e for e in evs
               if e.get("event") == "tools_call_rejected" and e.get("tool") == "unknown"]
    done = [e for e in evs if e.get("event") == "tools_call_done"]
    errs = [e for e in evs if e.get("event") == "tools_call_error"]
    no_arg_hash = [e for e in evs
                   if e.get("event") == "tools_call_request" and not e.get("arg_hash")]

    # 1. 超长请求拒绝占比
    if total_req and oversize:
        r = len(oversize) / total_req
        if r > THRESH["oversize_ratio"]:
            issues.append(("WARN",
                f"超长请求拒绝占比 {r:.0%} > {THRESH['oversize_ratio']:.0%}"
                f"（{len(oversize)}/{total_req}）——疑似 DoS 试探"))
    # 2. 未知工具探测
    if len(unknown) > THRESH["unknown_tool_max"]:
        issues.append(("WARN",
            f"未知工具调用 {len(unknown)} 次 > 阈值 {THRESH['unknown_tool_max']}"
            f"——疑似探测/错误客户端"))
    # 3. 工具调用错误率
    if done or errs:
        er = len(errs) / (len(done) + len(errs))
        if er > THRESH["error_ratio"]:
            issues.append(("WARN",
                f"工具调用错误率 {er:.0%} > {THRESH['error_ratio']:.0%}——实现缺陷或异常输入"))
    # 4. 审计完整性
    if no_arg_hash:
        issues.append(("WARN",
            f"{len(no_arg_hash)} 条 tools_call_request 缺 arg_hash——审计不完整"))
    # 5. 高频工具 Top3（可观测性，仅 INFO）
    tool_counter = Counter(
        e.get("tool") for e in evs if e.get("event") == "tools_call_done")
    top = tool_counter.most_common(3)
    info = [("INFO", "高频工具 Top3: " +
             ", ".join(f"{t}({c})" for t, c in top))] if top else []

    stats = {
        "total": total_req, "oversize": len(oversize),
        "unknown": len(unknown), "done": len(done), "errs": len(errs),
    }
    return issues, info, stats


def main():
    ap = argparse.ArgumentParser(description="MCP 审计日志异常行为分析器")
    ap.add_argument("--log", default=os.environ.get("AGRI_MCP_AUDIT_LOG"),
                    help="审计日志路径（默认读 AGRI_MCP_AUDIT_LOG）")
    ap.add_argument("--strict", action="store_true",
                    help="出现 WARN 时 exit 1（可接入 CI 门禁）")
    ap.add_argument("--selftest", action="store_true",
                    help="用内置样本日志自测")
    args = ap.parse_args()

    if args.selftest:
        evs = [
            {"event": "tools_call_request", "tool": "get_zone", "arg_hash": "ab12"},
            {"event": "tools_call_done", "tool": "get_zone"},
            {"event": "request_rejected", "reason": "oversize"},
            {"event": "tools_call_rejected", "tool": "unknown"},
        ]
    elif args.log:
        if not os.path.isfile(args.log):
            print(f"审计日志不存在: {args.log}")
            return 2
        evs = load_events(args.log)
    else:
        print("需指定 --log PATH 或设置 AGRI_MCP_AUDIT_LOG，或 --selftest")
        return 2

    issues, info, stats = analyze(evs)
    print("=" * 50)
    print("MCP 审计异常行为分析报告 (audit_analyzer)")
    print("=" * 50)
    print(f"统计: 总请求 {stats['total']} / 超长拒绝 {stats['oversize']} / "
          f"未知工具 {stats['unknown']} / 成功 {stats['done']} / 错误 {stats['errs']}")
    for lv, msg in info:
        print(f"[{lv}] {msg}")
    for lv, msg in issues:
        print(f"[{lv}] {msg}")
    print("=" * 50)
    if issues:
        print(f"结论: 发现 {len(issues)} 项告警 ⚠️")
        return 1 if args.strict else 0
    print("结论: 未见异常行为 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
