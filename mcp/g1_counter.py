#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp/g1_counter.py —— G1 关注度计数机制（零依赖，纯 stdlib）

G1 主指标：「MCP server 被外部 agent 真实调用 ≥500 次 / 独立调用方 ≥20 个」
（门槛 7 / 门槛 8，见 docs/north_star_and_phase_gates.md §2 行 66-67）。

本模块把「外部调用」从**不可测量**变成**可测量**：
  1. 调用方指纹提取：从审计事件中提取稳定的调用方标识（去重键）。
  2. G1 统计：累计外部调用次数（门槛7）+ 独立调用方数（门槛8，去重）。
  3. 持久化：默认落盘 ``data/g1_counter.json``（累计状态，跨进程/跨重启保留）。

调用方指纹（去重键）设计 —— 优先级从高到低：
  A. ``client_id``：客户端在 ``_meta.client_id`` 主动声明（最可靠，不同 agent
     应自报身份；同一 agent 多次调用共享同一 client_id）。
  B. ``traceparent`` 的 trace-id：W3C 链路标识（SEP-414）。同一调用方在同一次
     任务内多次调用通常共享 trace-id（trace-id 是"一次任务"的标识）。
  C. 回退：``tool + arg_hash``（弱标识，同一工具+相同参数 = 可能同一调用方，
     保守计数——宁可低估也不虚增独立调用方）。

诚实边界：
  - 只统计审计日志中 **tools_call_done**（执行成功的调用）事件。
  - 统计的是"记录到的调用"，不是"推断的外部调用"。审计日志默认落盘后，
    每个真实外部调用都会留痕，据此计数。
  - 指标不可编造：所有计数来自实跑审计记录，禁止估算。
  - 与 check_g1_signals.py（关注度代理指标）分工：本模块是**主指标计数**，
    g1_signals 是**间接代理**（stars/forks）。二者互补不重复。

用法：
  python mcp/g1_counter.py --audit data/mcp_audit.jsonl     # 统计
  python mcp/g1_counter.py --audit data/mcp_audit.jsonl --json
  python mcp/g1_counter.py --selftest                       # 内置样本自测

数据文件：
  data/mcp_audit.jsonl   —— 审计日志（原始证据，由 mcp/server.py _audit 写）
  data/g1_counter.json   —— G1 累计状态（本模块维护）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

# 项目根
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# G1 门槛（与 north_star_and_phase_gates.md §2 一致，提案值待用户确认）
G1_TOTAL_THRESHOLD = 500    # 门槛7：累计外部调用 ≥500 次
G1_CALLERS_THRESHOLD = 20   # 门槛8：累计独立调用方 ≥20 个

DEFAULT_AUDIT_PATH = os.path.join(ROOT, "data", "mcp_audit.jsonl")
DEFAULT_COUNTER_PATH = os.path.join(ROOT, "data", "g1_counter.json")


def caller_fingerprint(event: dict) -> str:
    """从单条审计事件提取调用方指纹（去重键）。

    优先级：client_id > traceparent trace-id > tool+arg_hash。
    返回稳定短哈希（12 hex），空串表示"无法确定调用方"（不计入独立调用方）。
    """
    # A. client_id（客户端主动声明）
    cid = event.get("client_id")
    if isinstance(cid, str) and cid.strip():
        return "cid:" + hashlib.sha256(cid.strip().encode("utf-8")).hexdigest()[:12]
    # B. traceparent trace-id（W3C：00-<32hex trace-id>-<16hex parent>-<2hex flags>）
    tp = event.get("traceparent")
    if isinstance(tp, str) and tp:
        parts = tp.split("-")
        if len(parts) == 4 and len(parts[1]) == 32 and parts[1] != "0" * 32:
            return "tp:" + parts[1][:12]
    # C. 回退：tool + arg_hash（弱标识）
    tool = event.get("tool")
    ah = event.get("arg_hash")
    if isinstance(tool, str) and tool and isinstance(ah, str) and ah:
        return "weak:" + hashlib.sha256(
            (tool + "|" + ah).encode("utf-8")).hexdigest()[:12]
    return ""


def load_events(path: str) -> list[dict]:
    """逐行解析审计日志（兼容 [mcp_audit] 前缀）。失败行跳过。"""
    evs = []
    try:
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
    except FileNotFoundError:
        pass  # 无审计日志 = 0 调用（诚实：尚无记录）
    return evs


def compute_g1(events: list[dict]) -> dict:
    """从审计事件计算 G1 指标。

    只计 tools_call_done（执行成功的调用）。累计次数 = 所有 done 事件数；
    独立调用方 = done 事件的调用方指纹去重数（空指纹不计入）。
    """
    done = [e for e in events if e.get("event") == "tools_call_done"]
    total_calls = len(done)
    callers = set()
    for e in done:
        fp = caller_fingerprint(e)
        if fp:
            callers.add(fp)
    return {
        "total_calls": total_calls,
        "unique_callers": len(callers),
        "g1_total_met": total_calls >= G1_TOTAL_THRESHOLD,
        "g1_callers_met": len(callers) >= G1_CALLERS_THRESHOLD,
        "thresholds": {
            "total": G1_TOTAL_THRESHOLD,
            "callers": G1_CALLERS_THRESHOLD,
        },
        "caller_top": Counter(caller_fingerprint(e) for e in done
                              if caller_fingerprint(e)).most_common(10),
    }


def load_counter_state(path: str) -> dict:
    """读取 G1 累计状态。不存在返回空。"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_counter_state(path: str, state: dict) -> None:
    """原子写 G1 累计状态。"""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def reconcile(events: list[dict], state: dict | None = None) -> dict:
    """从审计事件重算 G1，并与累计状态合并（保留历史峰值，防回退）。

    设计：审计日志是追加型原始证据（只增不减），但可能被清理/轮转。
    为防"日志被清理导致 G1 回退"，保留累计状态里的历史最高值：
      - total_calls = max(日志统计, 历史累计)
      - unique_callers = max(日志统计, 历史累计)
    当前审计日志完整时二者一致；日志部分丢失时用历史峰值（诚实不低估）。
    """
    g = compute_g1(events)
    if state and isinstance(state, dict):
        hist_total = int(state.get("total_calls", 0) or 0)
        hist_callers = int(state.get("unique_callers", 0) or 0)
        g["total_calls"] = max(g["total_calls"], hist_total)
        g["unique_callers"] = max(g["unique_callers"], hist_callers)
        g["g1_total_met"] = g["total_calls"] >= G1_TOTAL_THRESHOLD
        g["g1_callers_met"] = g["unique_callers"] >= G1_CALLERS_THRESHOLD
    return g


def main():
    ap = argparse.ArgumentParser(description="G1 关注度计数（外部调用 ≥500 / 独立调用方 ≥20）")
    ap.add_argument("--audit", default=os.environ.get("AGRI_MCP_AUDIT_LOG", DEFAULT_AUDIT_PATH),
                    help="审计日志路径（默认 data/mcp_audit.jsonl）")
    ap.add_argument("--state", default=DEFAULT_COUNTER_PATH,
                    help="累计状态路径（默认 data/g1_counter.json）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true", help="内置样本自测")
    ap.add_argument("--ci", action="store_true", help="G1 未达标时 exit 1（可接 CI 门禁）")
    args = ap.parse_args()

    if args.selftest:
        # 内置样本：3 个调用方，5 次成功调用，1 次失败（不计）
        evs = [
            {"event": "tools_call_done", "tool": "agri_list_cities", "arg_hash": "a1",
             "client_id": "agent-alpha"},
            {"event": "tools_call_done", "tool": "agri_match_zone", "arg_hash": "a2",
             "client_id": "agent-alpha"},
            {"event": "tools_call_done", "tool": "agri_recommend_crops", "arg_hash": "b1",
             "client_id": "agent-beta"},
            {"event": "tools_call_done", "tool": "agri_env_recipe", "arg_hash": "c1",
             "client_id": "agent-gamma"},
            {"event": "tools_call_done", "tool": "agri_soil_profile", "arg_hash": "c2",
             "client_id": "agent-gamma"},
            {"event": "tools_call_error", "tool": "agri_growth_plan", "arg_hash": "d1",
             "client_id": "agent-delta"},  # 失败不计
        ]
        g = compute_g1(evs)
        assert g["total_calls"] == 5, g
        assert g["unique_callers"] == 3, g
        print(f"[selftest] OK — 5 次成功调用 / 3 个独立调用方（失败不计入）")
        return 0

    events = load_events(args.audit)
    state = load_counter_state(args.state)
    g = reconcile(events, state)
    # 更新累计状态（保留历史峰值）
    save_counter_state(args.state, g)

    if args.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
    else:
        print("=" * 56)
        print("G1 关注度计数（主指标）")
        print("=" * 56)
        print(f"累计外部调用:     {g['total_calls']} 次  (门槛7 ≥ {g['thresholds']['total']})"
              f"  {'✅' if g['g1_total_met'] else '❌'}")
        print(f"独立调用方:       {g['unique_callers']} 个  (门槛8 ≥ {g['thresholds']['callers']})"
              f"  {'✅' if g['g1_callers_met'] else '❌'}")
        if g["caller_top"]:
            print("调用方 Top10: " + ", ".join(f"{fp}({n})" for fp, n in g["caller_top"]))
        print("=" * 56)
        met = g["g1_total_met"] and g["g1_callers_met"]
        print(f"结论: {'G1 已达标 🎯' if met else 'G1 未达标（继续跟踪）'}")

    if args.ci and not (g["g1_total_met"] and g["g1_callers_met"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
