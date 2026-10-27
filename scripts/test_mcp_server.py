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
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
    except OSError:
        # Windows 上子进程提前退出会抛 OSError(EINVAL)；此时管道已关闭
        return None
    raw = proc.stdout.readline()
    if not raw:
        return None
    return json.loads(raw.strip())


def _notify(msg: dict) -> None:
    """发送通知（无 id，服务端不回响应，调用方不可读）。"""
    line = json.dumps(msg, ensure_ascii=False) + "\n"
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
    except OSError:
        # Windows 上子进程提前退出会抛 OSError(EINVAL)；通知丢失可接受
        pass


def main() -> int:
    global proc
    # AGRI_BP_DB 指向临时库：agri_bp_screen 会写 cases 表，不隔离就会污染
    # bp_screen/data/cases.db 的真实种子库（该文件不受 git 跟踪，污染完全静默）。
    env = dict(os.environ)
    env["AGRI_BP_DB"] = os.path.join(tempfile.mkdtemp(prefix="agri_bp_test_"), "cases.db")
    # AGRI_GROW_BATCHES_DIR 指向临时目录：5 个批次工具会写 registry/events，
    # 不隔离就会污染真实 data/grow_batches/ 的审计资产（静默且不可逆）。
    env["AGRI_GROW_BATCHES_DIR"] = tempfile.mkdtemp(prefix="agri_grow_batch_test_")
    # 安全审计日志落盘（CyberGuard 提升点3）：经 AGRI_MCP_AUDIT_LOG 写入临时文件，便于断言
    audit_log = os.path.join(tempfile.mkdtemp(prefix="agri_mcp_audit_"), "mcp_audit.log")
    env["AGRI_MCP_AUDIT_LOG"] = audit_log
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
        _caps = (resp or {}).get("result", {}).get("capabilities", {})
        # 断言语义：必须声明 tools 能力（tools 键存在且为 dict）；
        # 内部子键可扩展（如 2026-07-28 的 listChanged），故不做等值比较。
        check(isinstance(_caps.get("tools"), dict),
              "initialize 声明 tools 能力")
        check((resp or {}).get("result", {}).get("stateless") is True,
              "initialize 声明无状态（SEP-2567）")

        # 2) notifications/initialized（无响应，仅发送不读）
        _notify({"jsonrpc": "2.0", "method": "notifications/initialized"})

        # 3) tools/list
        resp = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = (resp or {}).get("result", {}).get("tools", [])
        check(len(tools) == 30, f"tools/list 返回 30 个工具（实际 {len(tools)}）")
        names = {t["name"] for t in tools}
        check("agri_env_recipe" in names, "包含 agri_env_recipe 工具")
        check("agri_season_advisory" in names, "包含 agri_season_advisory 工具")
        # 批次对象 MVP 工具（2026-10-27，报告 §9.1 P0 工作包）
        check("agri_grow_batch_create" in names, "包含 agri_grow_batch_create 工具")
        check("agri_grow_batch_replay" in names, "包含 agri_grow_batch_replay 工具")
        check("agri_soil_profile" in names, "包含 agri_soil_profile 工具")
        check("agri_bp_screen" in names, "包含 agri_bp_screen 工具（BP 投资初筛）")
        check("agri_reconcile_climate" in names, "包含 agri_reconcile_climate 工具（多源气候校准）")
        check("agri_resolve_recipe" in names, "包含 agri_resolve_recipe 工具（地理编码→配方）")
        check("agri_query_lineage" in names, "包含 agri_query_lineage 工具（数据血缘查询）")
        check("agri_list_ecosystem" in names, "包含 agri_list_ecosystem 工具（生态对接清单）")

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

        # 5f) tools/call: resolve_recipe（地理编码→配方，完全离线）
        resp = _rpc({"jsonrpc": "2.0", "id": 12, "method": "tools/call",
                     "params": {"name": "agri_resolve_recipe",
                                "arguments": {"query": "杭州"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            gr = json.loads(text)
            check(gr.get("resolved") and gr.get("zone_id") == "subtropical_wet",
                  f"resolve_recipe 城市名→分区（zone={gr.get('zone_id') or gr.get('error')}）")
        except Exception:
            check(False, "resolve_recipe 返回可解析 JSON")

        # 5g) tools/call: query_lineage（数据血缘查询）
        resp = _rpc({"jsonrpc": "2.0", "id": 13, "method": "tools/call",
                     "params": {"name": "agri_query_lineage",
                                "arguments": {"crop": "番茄"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            ql = json.loads(text)
            # 必须断言真实业务值而非"有字段"：番茄在库中应至少命中一个分区
            ok = ("traces" in ql and ql.get("match_count", 0) >= 1) or ql.get("summary")
            check(ok and "error" not in ql,
                  f"query_lineage 按作物查血缘（match_count={ql.get('match_count')}）")
        except Exception:
            check(False, "query_lineage 返回可解析 JSON")

        # 5h) tools/call: reconcile_climate（多源气候校准；网络相关，断言契约稳定性）
        # 无论在线/离线，都必须返回结构化 JSON：sources 列表 + provenance_complete 布尔 +
        # reconciled 为 12 列表或 null（绝不抛协议错误）
        resp = _rpc({"jsonrpc": "2.0", "id": 14, "method": "tools/call",
                     "params": {"name": "agri_reconcile_climate",
                                "arguments": {"lat": 30.27, "lon": 120.15}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            rc = json.loads(text)
            rec = rc.get("reconciled")
            contract = (isinstance(rc.get("sources"), list)
                        and isinstance(rc.get("provenance_complete"), bool)
                        and (rec is None or (isinstance(rec, list) and len(rec) == 12)))
            check(contract,
                  f"reconcile_climate 返回稳定契约（n_sources={rc.get('n_sources')}）")
        except Exception:
            check(False, "reconcile_climate 返回可解析 JSON")

        # 5i) tools/call: list_ecosystem（生态对接清单；声明生态可见性，含过滤）
        resp = _rpc({"jsonrpc": "2.0", "id": 15, "method": "tools/call",
                     "params": {"name": "agri_list_ecosystem", "arguments": {}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            ec = json.loads(text)
            # 断言真实业务值：至少有 10 项生态；含已知 ID（nasa-power 应为 integrated）
            ok = (ec.get("count", 0) >= 10
                  and isinstance(ec.get("integration_matrix"), dict)
                  and "nasa-power" in ec["integration_matrix"].get("integrated", []))
            check(ok and "error" not in ec,
                  f"list_ecosystem 返回生态清单（count={ec.get('count')}）")
        except Exception:
            check(False, "list_ecosystem 返回可解析 JSON")

        # 5j) tools/call: list_ecosystem 按 status 过滤
        resp = _rpc({"jsonrpc": "2.0", "id": 16, "method": "tools/call",
                     "params": {"name": "agri_list_ecosystem",
                                "arguments": {"status": "integrated"}}})
        content = (resp or {}).get("result", {}).get("content", [{}])
        text = content[0].get("text", "") if content else ""
        try:
            ec = json.loads(text)
            # 过滤后每条目 status 都必须是 integrated
            all_integrated = all(e.get("status") == "integrated" for e in ec.get("ecosystems", []))
            check(ec.get("count", 0) >= 4 and all_integrated,
                  f"list_ecosystem status=integrated 过滤生效（count={ec.get('count')}）")
        except Exception:
            check(False, "list_ecosystem 过滤调用返回可解析 JSON")

        # 6) 未知工具报错
        resp = _rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "no_such_tool", "arguments": {}}})
        check(resp and "error" in resp, "未知工具返回 error")

        # 6b) 参数校验：非法经纬度范围必须被拒绝（P0 回归：999/-999 曾静默通过）
        resp = _rpc({"jsonrpc": "2.0", "id": 20, "method": "tools/call",
                     "params": {"name": "agri_match_zone",
                                "arguments": {"lat": 999, "lon": 999}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _z = json.loads(_txt)
            check("error" in _z and "lat" in _z.get("error", ""),
                  "match_zone 拒绝非法 lat 范围（999）")
        except Exception:
            check(False, "match_zone 非法 lat 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 21, "method": "tools/call",
                     "params": {"name": "agri_reconcile_climate",
                                "arguments": {"lat": 0, "lon": 0, "years": [-5]}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _z = json.loads(_txt)
            check("error" in _z and "years" in _z.get("error", ""),
                  "reconcile_climate 拒绝非整数/非法 years（[-5]）")
        except Exception:
            check(False, "reconcile_climate 非法 years 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 22, "method": "tools/call",
                     "params": {"name": "agri_list_ecosystem",
                                "arguments": {"status": "invalid_status_xyz"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _z = json.loads(_txt)
            check("error" in _z and "status" in _z.get("error", ""),
                  "list_ecosystem 拒绝非法 status 值")
        except Exception:
            check(False, "list_ecosystem 非法 status 返回可解析 JSON")

        # 6c) 新增工具：agri_search / agri_knowledge_query / agri_forecast（M12-K1 / M13-P1）
        resp = _rpc({"jsonrpc": "2.0", "id": 30, "method": "tools/call",
                     "params": {"name": "agri_search",
                                "arguments": {"query": "番茄 地中海"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _s = json.loads(_txt)
            check("error" not in _s and _s.get("count", 0) >= 1
                  and "evidence" in _s and "results" in _s,
                  "agri_search 番茄地中海返回结果含 evidence+results")
        except Exception:
            check(False, "agri_search 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 31, "method": "tools/call",
                     "params": {"name": "agri_search",
                                "arguments": {"query": "番茄", "corpus": "pests"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _s = json.loads(_txt)
            check("error" not in _s and _s.get("corpus") == "pests",
                  "agri_search corpus=pests 过滤生效")
        except Exception:
            check(False, "agri_search corpus 过滤返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 32, "method": "tools/call",
                     "params": {"name": "agri_search",
                                "arguments": {"query": ""}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _s = json.loads(_txt)
            check("error" in _s and "query" in _s["error"],
                  "agri_search 拒绝空 query")
        except Exception:
            check(False, "agri_search 空 query 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 33, "method": "tools/call",
                     "params": {"name": "agri_knowledge_query",
                                "arguments": {"kind": "summary"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _k = json.loads(_txt)
            check("error" not in _k and _k.get("total_entities", 0) >= 200,
                  f"agri_knowledge_query summary 返回图谱统计（entities={_k.get('total_entities')}）")
        except Exception:
            check(False, "agri_knowledge_query summary 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 34, "method": "tools/call",
                     "params": {"name": "agri_knowledge_query",
                                "arguments": {"kind": "crops_by_zone",
                                              "zone_id": "subtropical_wet"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _k = json.loads(_txt)
            check("error" not in _k and isinstance(_k.get("crops"), list)
                  and len(_k["crops"]) >= 1,
                  "agri_knowledge_query crops_by_zone subtropical_wet 返回非空列表")
        except Exception:
            check(False, "agri_knowledge_query crops_by_zone 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 35, "method": "tools/call",
                     "params": {"name": "agri_knowledge_query",
                                "arguments": {"kind": "traverse", "node": "Crop:番茄"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _k = json.loads(_txt)
            check("error" not in _k and "traversal" in _k,
                  "agri_knowledge_query traverse Crop:番茄 返回遍历结果")
        except Exception:
            check(False, "agri_knowledge_query traverse 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 36, "method": "tools/call",
                     "params": {"name": "agri_knowledge_query",
                                "arguments": {"kind": "crops_by_zone"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _k = json.loads(_txt)
            check("error" in _k,
                  "agri_knowledge_query crops_by_zone 缺 zone_id 时拒绝")
        except Exception:
            check(False, "agri_knowledge_query 缺参返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 37, "method": "tools/call",
                     "params": {"name": "agri_forecast",
                                "arguments": {"crop": "番茄",
                                              "zone_id": "mediterranean",
                                              "start_date": "2026-02-15",
                                              "adapt_score": 0.85}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _f = json.loads(_txt)
            check("error" not in _f and "recommendation" in _f
                  and "prediction_interval" in _f["recommendation"],
                  "agri_forecast 番茄地中海返回完整推荐含区间")
            check(_f["recommendation"]["prediction_interval"]["yield_estimate_g"]["p50"] > 0,
                  "agri_forecast 产量 P50 > 0")
        except Exception:
            check(False, "agri_forecast 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 38, "method": "tools/call",
                     "params": {"name": "agri_forecast",
                                "arguments": {"crop": "番茄", "adapt_score": 1.5}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _f = json.loads(_txt)
            check("error" in _f and "0.0" in _f["error"] or "adapt_score" in _f["error"],
                  "agri_forecast 拒绝 adapt_score > 1")
        except Exception:
            check(False, "agri_forecast adapt_score 越界返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 39, "method": "tools/call",
                     "params": {"name": "agri_forecast",
                                "arguments": {"crop": ""}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _f = json.loads(_txt)
            check("error" in _f and "crop" in _f["error"],
                  "agri_forecast 拒绝空 crop")
        except Exception:
            check(False, "agri_forecast 空 crop 返回可解析 JSON")

        # 6d) 新增工具：agri_recipe_profile（M8-R2 配方四件套）
        resp = _rpc({"jsonrpc": "2.0", "id": 40, "method": "tools/call",
                     "params": {"name": "agri_recipe_profile",
                                "arguments": {"kind": "stats"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check("error" not in _rp and _rp.get("kind") == "stats"
                  and _rp.get("total_recipes", 0) >= 150,
                  f"agri_recipe_profile stats 返回资产统计（recipes={_rp.get('total_recipes')}）")
        except Exception:
            check(False, "agri_recipe_profile stats 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 41, "method": "tools/call",
                     "params": {"name": "agri_recipe_profile",
                                "arguments": {"kind": "list"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check("error" not in _rp and isinstance(_rp.get("recipes"), list)
                  and len(_rp["recipes"]) >= 150,
                  "agri_recipe_profile list 返回全部配方清单")
        except Exception:
            check(False, "agri_recipe_profile list 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 42, "method": "tools/call",
                     "params": {"name": "agri_recipe_profile",
                                "arguments": {"kind": "diff",
                                              "a": "data/env_recipes/mediterranean__番茄.json",
                                              "b": "data/env_recipes/subtropical_wet__生菜.json"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check("error" not in _rp and _rp.get("status") == "different",
                  "agri_recipe_profile diff 识别两份不同配方的差异")
        except Exception:
            check(False, "agri_recipe_profile diff 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 43, "method": "tools/call",
                     "params": {"name": "agri_recipe_profile",
                                "arguments": {"kind": "export",
                                              "filename": "mediterranean__番茄.json"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check("error" not in _rp and "content" in _rp.get("meta", {})
                  and "番茄" in _rp["meta"]["content"],
                  "agri_recipe_profile export 返回配方 JSON 字符串")
        except Exception:
            check(False, "agri_recipe_profile export 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 44, "method": "tools/call",
                     "params": {"name": "agri_recipe_profile",
                                "arguments": {"kind": "diff"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check("error" in _rp,
                  "agri_recipe_profile diff 缺参时拒绝")
        except Exception:
            check(False, "agri_recipe_profile diff 缺参返回可解析 JSON")

        # 6.5) M11-T1 agri_verify_trust 公共复算 API：三种 mode
        resp = _rpc({"jsonrpc": "2.0", "id": 46, "method": "tools/call",
                     "params": {"name": "agri_verify_trust",
                                "arguments": {"mode": "current"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        _vt = None
        try:
            _vt = json.loads(_txt)
            check("signature" in _vt and "status" in _vt,
                  "agri_verify_trust current 返回签名 + 状态")
            check(_vt["signature"] == _vt.get("signature_prefix", "") + _vt["signature"][12:],
                  "agri_verify_trust current signature_prefix 是 signature 前缀（内部一致）")
        except Exception:
            check(False, "agri_verify_trust current 返回可解析 JSON")

        # 用刚拿到的 current mark 做 check_prefix + end_to_end
        if _vt is not None:
            resp = _rpc({"jsonrpc": "2.0", "id": 47, "method": "tools/call",
                         "params": {"name": "agri_verify_trust",
                                    "arguments": {"mode": "check_prefix", "mark": _vt}}})
            _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
            try:
                _cp = json.loads(_txt)
                check(_cp.get("verified") is True,
                      "agri_verify_trust check_prefix 自校验通过")
            except Exception:
                check(False, "agri_verify_trust check_prefix 返回可解析 JSON")

            resp = _rpc({"jsonrpc": "2.0", "id": 48, "method": "tools/call",
                         "params": {"name": "agri_verify_trust",
                                    "arguments": {"mode": "end_to_end", "mark": _vt}}})
            _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
            try:
                _e2e = json.loads(_txt)
                check(_e2e.get("verified") is True,
                      "agri_verify_trust end_to_end 用固定 issued_at 严格复算通过")
            except Exception:
                check(False, "agri_verify_trust end_to_end 返回可解析 JSON")

        # 参数校验：非法 mode + 缺 mark
        resp = _rpc({"jsonrpc": "2.0", "id": 49, "method": "tools/call",
                     "params": {"name": "agri_verify_trust",
                                "arguments": {"mode": "bogus"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _err = json.loads(_txt)
            # H5 加固：schema enum 校验给出 "not in enum"，或 fallback 到原 "非法 mode" 文案
            _is_bad_mode = ("非法 mode" in _err.get("error", "")
                            or "not in enum" in _err.get("error", ""))
            check("error" in _err and _is_bad_mode,
                  "agri_verify_trust 非法 mode 被拒绝")
        except Exception:
            check(False, "agri_verify_trust 非法 mode 返回可解析 JSON")

        resp = _rpc({"jsonrpc": "2.0", "id": 50, "method": "tools/call",
                     "params": {"name": "agri_verify_trust",
                                "arguments": {"mode": "check_prefix"}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _err = json.loads(_txt)
            check("error" in _err and "mark" in _err["error"],
                  "agri_verify_trust check_prefix 缺 mark 被拒绝")
        except Exception:
            check(False, "agri_verify_trust 缺 mark 返回可解析 JSON")

        # 6.6) 批次对象 MVP（报告 §9.1 P0 工作包，2026-10-27）：5 工具端到端
        # 存储已经 AGRI_GROW_BATCHES_DIR 隔离到临时目录（见 env 上方）。
        _bid = "e2e_batch_001"
        _pid = "e2e_plot_a"
        # create：Plot + GrowBatch
        resp = _rpc({"jsonrpc": "2.0", "id": 60, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_create",
                                "arguments": {
                                    "plot": {"plot_id": _pid, "location_type": "balcony",
                                             "orientation": "south",
                                             "area_sqm": {"value": 0.5, "unit": "sqm"}},
                                    "batch": {"batch_id": _bid, "crop": "生菜",
                                              "plot_id": _pid, "recipe_version": "v1.2.0",
                                              "recipe_id": "mediterranean__生菜",
                                              "started_at": "2026-10-27T00:00:00Z"}}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _b = json.loads(_txt)
            check(_b.get("ok") and _b.get("batch_id") == _bid and _b.get("status") == "planned",
                  "agri_grow_batch_create 建立 Plot+GrowBatch（status=planned）")
            check("honest_note" in _b and "MVP" in _b["honest_note"],
                  "agri_grow_batch_create 返回 MVP 诚实边界说明")
        except Exception:
            check(False, "agri_grow_batch_create 返回可解析 JSON")

        # observe：追加 Observation
        resp = _rpc({"jsonrpc": "2.0", "id": 61, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_observe",
                                "arguments": {"observation": {
                                    "observation_id": "e2e_obs_001", "batch_id": _bid,
                                    "ts": "2026-10-27T08:00:00Z", "metric": "temperature_c",
                                    "value": {"value": 21.5, "unit": "celsius"},
                                    "source": {"kind": "sensor", "device_id": "dev_t01"}}}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _o = json.loads(_txt)
            check(_o.get("ok") and _o.get("count") == 1,
                  "agri_grow_batch_observe 追加观察（count=1）")
        except Exception:
            check(False, "agri_grow_batch_observe 返回可解析 JSON")

        # action：MVP 默认 shadow/dry_run，不真实执行
        resp = _rpc({"jsonrpc": "2.0", "id": 62, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_action",
                                "arguments": {"action": {
                                    "action_id": "e2e_act_001", "batch_id": _bid,
                                    "ts": "2026-10-27T08:05:00Z",
                                    "recommendation": "浇水 200ml",
                                    "parameters": {"irrigation_ml": 200}}}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _a = json.loads(_txt)
            check(_a.get("ok") and _a.get("status") == "shadow" and _a.get("dry_run") is True,
                  "agri_grow_batch_action 记录动作默认 shadow/dry_run（不真实执行）")
        except Exception:
            check(False, "agri_grow_batch_action 返回可解析 JSON")

        # status：查询批次 + 关联对象
        resp = _rpc({"jsonrpc": "2.0", "id": 63, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_status",
                                "arguments": {"batch_id": _bid, "include_events": True}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _s = json.loads(_txt)
            check(_s.get("ok") and _s.get("batch", {}).get("crop") == "生菜"
                  and _s.get("n_observations") == 1 and _s.get("n_actions") == 1,
                  "agri_grow_batch_status 返回批次+观察+动作计数")
            check(_s.get("events") and any(e["event_type"] == "observation_added"
                                           for e in _s["events"]),
                  "agri_grow_batch_status include_events 返回事件日志")
        except Exception:
            check(False, "agri_grow_batch_status 返回可解析 JSON")

        # replay：按时间线回放（无副作用）
        resp = _rpc({"jsonrpc": "2.0", "id": 64, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_replay",
                                "arguments": {"batch_id": _bid}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _rp = json.loads(_txt)
            check(_rp.get("ok") and _rp.get("n_events") >= 3
                  and any(e["event_type"] == "batch_created" for e in _rp.get("timeline", [])),
                  "agri_grow_batch_replay 按时间线回放（n_events≥3）")
            check("回放仅重建事件序列" in _rp.get("honest_note", ""),
                  "agri_grow_batch_replay 返回无副作用诚实说明")
        except Exception:
            check(False, "agri_grow_batch_replay 返回可解析 JSON")

        # 契约：批次未结束（非 harvested/failed）不允许写真实 outcome —— 走 create 工具
        # 验证 MVP 诚实边界（真实执行需人工确认）。此路径通过 status 查询确认无 outcomes。
        # 非法 action（executed + dry_run=True）必须被拒绝
        resp = _rpc({"jsonrpc": "2.0", "id": 65, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_action",
                                "arguments": {"action": {
                                    "action_id": "e2e_act_bad", "batch_id": _bid,
                                    "ts": "2026-10-27T09:00:00Z",
                                    "recommendation": "真实执行",
                                    "dry_run": True, "status": "executed"}}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _bad = json.loads(_txt)
            check(_bad.get("contract_violation") and "dry_run" in _bad.get("error", ""),
                  "agri_grow_batch_action 拒绝 executed+dry_run=True（需人工确认）")
        except Exception:
            check(False, "agri_grow_batch_action 非法状态返回可解析 JSON")

        # 缺 plot 的 create 必须被拒绝（契约违反）
        resp = _rpc({"jsonrpc": "2.0", "id": 66, "method": "tools/call",
                     "params": {"name": "agri_grow_batch_create",
                                "arguments": {"plot": {}, "batch": {}}}})
        _txt = ((resp or {}).get("result", {}).get("content") or [{}])[0].get("text", "")
        try:
            _bad = json.loads(_txt)
            check(_bad.get("contract_violation") is True,
                  "agri_grow_batch_create 缺参被拒绝（contract_violation）")
        except Exception:
            check(False, "agri_grow_batch_create 缺参返回可解析 JSON")

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

        # 8) 安全审计日志（CyberGuard 提升点3）：所有调用与拒绝均被记录
        try:
            with open(audit_log, "r", encoding="utf-8") as f:
                audit_lines = f.read()
            check("tools_call_request" in audit_lines,
                  "审计日志记录了 tools_call_request")
            check("tools_call_done" in audit_lines,
                  "审计日志记录了对正常工具的调用完成")
            check("tools_call_rejected" in audit_lines,
                  "审计日志记录了对未知工具的拒绝")
            check("request_rejected" in audit_lines,
                  "审计日志记录了对超长请求的拒绝")
        except Exception as e:
            check(False, f"审计日志读取失败: {e}")

        # 9) 审计异常行为分析器（CyberGuard 行为监控）：消费真实审计日志产出报告
        try:
            import subprocess as _sp
            analyzer = os.path.join(ROOT, "mcp", "audit_analyzer.py")
            r = _sp.run([PY, analyzer, "--log", audit_log],
                        capture_output=True, text=True, timeout=30)
            out = (r.stdout or "") + (r.stderr or "")
            check("MCP 审计异常行为分析报告" in out,
                  "审计分析器消费真实日志并产出报告")
            check("统计:" in out, "审计分析器输出统计摘要")
        except Exception as e:
            check(False, f"审计分析器运行失败: {e}")
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
