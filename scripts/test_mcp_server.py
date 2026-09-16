#!/usr/bin/env python3
"""
scripts/test_mcp_server.py —— MCP server 零依赖冒烟测试

以子进程方式启动 mcp/server.py，通过 stdin/stdout 发送 JSON-RPC 消息，
断言 initialize / tools/list / tools/call 三类响应。退出码 0 = 通过。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")
PY = sys.executable


def _rpc(msg: dict) -> dict | None:
    """向子进程发送一条并读取下一条响应（请求）。"""
    line = json.dumps(msg, ensure_ascii=False) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    raw = proc.stdout.readline()
    if not raw:
        return None
    return json.loads(raw.strip())


def _notify(msg: dict) -> None:
    """发送通知（无 id，服务端不回响应，调用方不可读）。"""
    line = json.dumps(msg, ensure_ascii=False) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


def main() -> int:
    global proc
    proc = subprocess.Popen(
        [PY, SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    failures = []

    def check(cond: bool, label: str):
        if cond:
            print(f"[通过] {label}")
        else:
            print(f"[失败] {label}")
            failures.append(label)

    try:
        # 1) initialize
        resp = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "smoke", "version": "0"}}})
        check(resp and resp.get("result", {}).get("protocolVersion") == "2024-11-05",
              "initialize 返回协议版本")
        check(resp and resp.get("result", {}).get("capabilities", {}).get("tools") == {},
              "initialize 声明 tools 能力")

        # 2) notifications/initialized（无响应，仅发送不读）
        _notify({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3) tools/list
        resp = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = (resp or {}).get("result", {}).get("tools", [])
        check(len(tools) == 9, f"tools/list 返回 9 个工具（实际 {len(tools)}）")
        names = {t["name"] for t in tools}
        check("agri_env_recipe" in names, "包含 agri_env_recipe 工具")
        check("agri_season_advisory" in names, "包含 agri_season_advisory 工具")
        check("agri_soil_profile" in names, "包含 agri_soil_profile 工具")

        # 4) tools/call: match_zone
        resp = _rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "agri_match_zone", "arguments": {"lat": 30.2741, "lon": 120.1551}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            zone = json.loads(text)
            check("error" not in zone and bool(zone.get("evidence", {}).get("zone_id")),
                  f"match_zone 返回真实分区（{zone.get('evidence', {}).get('zone_id') or zone.get('error')}）")
        except Exception:
            check(False, "match_zone 返回可解析 JSON")

        # 5) tools/call: env_recipe
        resp = _rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "agri_env_recipe",
                                "arguments": {"crop": "番茄", "stage": "fruiting", "device_class": "indoor_cabinet"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            recipe = json.loads(text)
            check(recipe.get("protocol") == "env-recipe", "env_recipe 返回合规协议标识")
        except Exception:
            check(False, "env_recipe 返回可解析 JSON")

        # 5b) tools/call: season_advisory（播期窗口 + 物候天数）
        resp = _rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                     "params": {"name": "agri_season_advisory",
                                "arguments": {"mode": "planting_window",
                                              "monthly_mean_c": [-4, -1, 5, 14, 20, 25, 27, 26, 21, 14, 5, -2],
                                              "crops": ["马铃薯"]}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            season = json.loads(text)
            w = (season.get("windows") or [{}])[0]
            check(season.get("available") and w.get("feasible")
                  and w.get("latest_sow"),
                  "season_advisory 返回可用播期窗口")
        except Exception:
            check(False, "season_advisory 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                     "params": {"name": "agri_season_advisory",
                                "arguments": {"mode": "stage_days", "crop": "马铃薯",
                                              "mean_temp_c": 18}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            st = json.loads(text)
            check(st.get("available") and st.get("maturity_days_from_sow"),
                  "season_advisory 返回物候天数")
        except Exception:
            check(False, "season_advisory stage_days 返回可解析 JSON")

        # 5c) tools/call: soil_profile（离线降级路径，online=false 保证快且确定）
        resp = _rpc({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                     "params": {"name": "agri_soil_profile",
                                "arguments": {"lat": 30.2741, "lon": 120.1551,
                                              "crop": "小白菜", "online": False}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            soil = json.loads(text)
            # 不能只断言"有字段"——必须断言真实降级语义，否则 error 对象也会通过
            check(soil.get("resolution") == "zone" and "error" not in soil,
                  f"soil_profile 降级为分区级（resolution={soil.get('resolution') or soil.get('error')}）")
            check(bool(soil.get("soil", {}).get("ph_range")) and soil.get("confidence") == "low",
                  "soil_profile 给出 pH 区间且置信度标为 low（不夸大）")
            check("global_zones" in (soil.get("source") or ""),
                  "soil_profile 标明离线来源")
            check(bool(soil.get("crop_ph_fit", {}).get("level")),
                  f"soil_profile 给出作物 pH 拟合（{soil.get('crop_ph_fit', {}).get('verdict')}）")
        except Exception:
            check(False, "soil_profile 返回可解析 JSON")

        # 6) 未知工具报错
        resp = _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "no_such_tool", "arguments": {}}})
        check(resp and "error" in resp, "未知工具返回 error")
    finally:
        proc.terminate()

    print("-" * 40)
    if failures:
        print(f"失败 {len(failures)} 项：{failures}")
        return 1
    print("MCP server 自测全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
