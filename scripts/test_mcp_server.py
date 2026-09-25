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
import tempfile

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
    # AGRI_BP_DB 指向临时库：agri_bp_screen 会写 cases 表，不隔离就会污染
    # bp_screen/data/cases.db 的真实种子库（该文件不受 git 跟踪，污染完全静默）。
    env = dict(os.environ)
    env["AGRI_BP_DB"] = os.path.join(tempfile.mkdtemp(prefix="agri_bp_test_"), "cases.db")
    proc = subprocess.Popen(
        [PY, SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
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
        check(len(tools) == 10, f"tools/list 返回 10 个工具（实际 {len(tools)}）")
        names = {t["name"] for t in tools}
        check("agri_env_recipe" in names, "包含 agri_env_recipe 工具")
        check("agri_season_advisory" in names, "包含 agri_season_advisory 工具")
        check("agri_soil_profile" in names, "包含 agri_soil_profile 工具")
        check("agri_bp_screen" in names, "包含 agri_bp_screen 工具（第 10 个，BP 投资初筛）")

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

        # 5d) tools/call: bp_screen（BP 投资初筛，第 10 个工具）
        # 用真实形态的 BP 文本喂进去。此文本分类置信度低于 70（触发 need_classify），
        # 故显式传 category="seeds" 走人工确认路径——这也顺带验证了 text 模式
        # 的 category 覆盖能力（旧版 text 模式静默丢弃 category，形成死路）。
        resp = _rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                     "params": {"name": "agri_bp_screen",
                                "arguments": {"text": (
                                    "种业公司BP：主营杂交水稻种子。\n"
                                    "已审定品种：6个（金玉188、金玉198、金玉208、"
                                    "金玉218、金玉228、金玉238）。\n"
                                    "生产应用安全证书 2个，农药登记证 3个。\n"
                                    "2023年营业收入1.8亿元，销售净利率10%，毛利率41%。\n"
                                    "研发投入占营业收入8%。政府补贴占营业收入15%。\n"
                                    "现金及现金等价物期末余额3.2亿元，月均净支出800万元。\n"
                                    "单位经济模型为正，ue_margin 32%。客户集中度35%。"
                                ), "company": "测试种业", "category": "seeds"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            bp = json.loads(text)
            check("error" not in bp, "bp_screen 无 error 键")
            check(bp.get("status") == "done",
                  f"bp_screen 人工确认分类后完成评分（status={bp.get('status')}）")
            check(bp.get("verdict_name") in ("通过", "需深挖", "淘汰"),
                  f"bp_screen 给出三档结论（verdict_name={bp.get('verdict_name')}）")
            check(isinstance(bp.get("score"), (int, float)),
                  f"bp_screen 给出分数（score={bp.get('score')}）")
            rng = bp.get("score_range") or []
            check(len(rng) == 2 and bp.get("score") is not None
                  and rng[0] <= bp["score"] <= rng[1],
                  f"bp_screen 分数落在区间内（range={rng}，score={bp.get('score')}）")
            check("不构成投资决策建议" in json.dumps(bp.get("boundary"), ensure_ascii=False),
                  "bp_screen 返回边界声明（不构成投资决策建议）")
        except Exception as e:
            check(False, f"bp_screen 返回可解析 JSON（{type(e).__name__}）")

        # 5e) 非法 category 必须报错而不是静默忽略
        resp = _rpc({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                     "params": {"name": "agri_bp_screen",
                                "arguments": {"text": "营收8000万元。",
                                              "category": "not_a_real_category"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            bad = json.loads(text)
            check(bad.get("status") == "invalid_category",
                  f"非法 category 返回 invalid_category（status={bad.get('status')}）")
        except Exception:
            check(False, "非法 category 返回可解析 JSON")

        # 6) 未知工具报错
        resp = _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "no_such_tool", "arguments": {}}})
        check(resp and "error" in resp, "未知工具返回 error")

        # 7) 安全护栏：超长请求必须被拒绝（防内存耗尽型 DoS）
        big = "X" * 2000000  # ~2 MiB，超过 MAX_LINE_BYTES(1 MiB)
        resp = _rpc({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                     "params": {"name": "agri_match_zone",
                                "arguments": {"lat": 30.2741, "lon": 120.1551,
                                              "pad": big}}})
        check(resp is not None and resp.get("error", {}).get("code") == -32700,
              "超长请求被安全护栏拒绝（error code -32700）")
        # 护栏拒绝后连接仍可用：再发一条正常请求应恢复响应
        resp2 = _rpc({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                      "params": {"name": "agri_match_zone",
                                 "arguments": {"lat": 30.2741, "lon": 120.1551}}})
        check(resp2 and resp2.get("result") is not None and "error" not in resp2,
              "护栏拒绝后连接仍可用（正常请求恢复响应）")
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
