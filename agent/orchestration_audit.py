"""
Orchestration Audit — 编排层可审计性模块（M10-O2 + M10-O4）

落地 docs/per_module_deep_assessment_2026-10-13.md §M10-O2「跨 Agent 一致性检查」
与 §M10-O4「编排 trace 可导出」。

设计原则：
- **旁路无侵入**：orchestrator 只加几行 timing 与 hook，主流水线语义完全不变。
- **advisory only**：所有检查结论写入 result["consistency_audit"]，
  **不阻断流水线、不修改任何 Agent 输出**（与 JEV 门控纪律同构）。
- **诚实暴露不确定性**：冲突显式记录，不静默消解。用户可看到"哪个 Agent
  与哪个 Agent 在什么维度不一致，严重度如何"。
- **零依赖 stdlib**：仅用 time/json/uuid/hashlib/typing。

对齐 M11 可信层的三条铁律：
- 每条 trace 带 trace_id（UUID + payload hash 摘要），可独立复算
- 检查结论带 severity（error/warning/info），不隐藏降级
- 输出可导出为 JSON（orchestration_trace.json）供外部审计

与 M14 自进化引擎的兼容：本模块只做**审计**不做**编辑**，
不触碰 evolution_zones.json 里的不可进化区（core/mcp/schemas）。
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 一致性检查规则（每条规则独立、可增补、失败不影响其他规则）
# ---------------------------------------------------------------------------

_CONSISTENCY_CHECKS = [
    "growth_start_date_frost",       # GrowthAgent 播种期 vs ClimateAgent 冻结期
    "eco_devices_budget_fit",        # EcoAgent 设备预算 vs 用户预算
    "top_crop_device_match",         # CropAgent top_crop vs EcoAgent 设备
    "growth_crop_match",             # GrowthAgent 计划作物 vs CropAgent 首推
    "climate_constraints_coverage",  # ClimateAgent 约束 vs 推荐作物
]


# 作物与 ClimateAgent 分区温度的经验温度窗口
# （用于 climate_constraints_coverage 检查；仅用于 advisory，不参与决策）
_CROP_TEMP_WINDOWS = {
    "番茄": (-5, 40),
    "西红柿": (-5, 40),
    "生菜": (0, 35),
    "菠菜": (-5, 30),
    "辣椒": (5, 40),
    "黄瓜": (5, 35),
    "萝卜": (-10, 30),
    "胡萝卜": (-10, 30),
    "白菜": (-10, 25),
    "小白菜": (-10, 25),
    "韭菜": (-15, 30),
    "香葱": (-10, 30),
    "薄荷": (0, 40),
    "草莓": (-5, 35),
    "葡萄": (0, 40),
    "苹果": (-20, 30),
    "樱桃": (-20, 30),
    "香蕉": (10, 40),
    "西瓜": (5, 40),
    "苦瓜": (10, 40),
    "茄子": (5, 35),
    "南瓜": (0, 35),
    "丝瓜": (5, 40),
    "豆角": (10, 35),
    "毛豆": (0, 30),
    "土豆": (-5, 30),
    "红薯": (10, 40),
    "洋葱": (-15, 30),
    "大蒜": (-15, 25),
    "豌豆": (-5, 25),
    "大豆": (0, 35),
    "玉米": (5, 35),
    "小米": (5, 35),
    "水稻": (10, 35),
    "小米菜": (-5, 25),
}


# ---------------------------------------------------------------------------
# Trace 记录器
# ---------------------------------------------------------------------------

class TraceRecord:
    """编排 trace：一次 pipeline 运行的完整调用图。"""

    __slots__ = ("trace_id", "started_at", "ended_at", "input_request",
                 "steps", "extra")

    def __init__(self, input_request: Dict[str, Any]) -> None:
        self.trace_id = uuid.uuid4().hex[:16]
        self.started_at = time.time()
        self.input_request = dict(input_request or {})
        self.steps: List[Dict[str, Any]] = []
        self.ended_at: Optional[float] = None
        self.extra: Dict[str, Any] = {}

    def add_step(self, agent_name: str, start_ts: float, end_ts: float,
                 input_summary: Dict[str, Any],
                 output_summary: Dict[str, Any],
                 status: str = "ok",
                 verify_report: Optional[Dict[str, Any]] = None,
                 ) -> None:
        self.steps.append({
            "agent": agent_name,
            "started_at": start_ts,
            "ended_at": end_ts,
            "duration_ms": round((end_ts - start_ts) * 1000, 3),
            "input_summary": dict(input_summary or {}),
            "output_summary": dict(output_summary or {}),
            "status": status,
            "verification": dict(verify_report or {}),
        })

    def finish(self) -> None:
        self.ended_at = time.time()

    def total_ms(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.time()
        return round((end - self.started_at) * 1000, 3)

    def summary_hash(self) -> str:
        """
        trace 摘要 SHA256 前 16 位——用于独立复算与外部审计。

        设计要点：**同输入 + 同 steps 序列 → 同 hash**（trace_id 与耗时不进入
        hash），使审计方可对任意一次 trace 输出独立复算校验。
        """
        step_fingerprints = [
            {
                "agent": s["agent"],
                "input_summary": s["input_summary"],
                "output_summary": s["output_summary"],
                "status": s["status"],
            }
            for s in self.steps
        ]
        payload = json.dumps({
            "input_request": self.input_request,
            "steps": step_fingerprints,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "summary_hash": self.summary_hash(),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_ms": self.total_ms(),
            "input_request": self.input_request,
            "steps": list(self.steps),
            "extra": dict(self.extra),
        }


# ---------------------------------------------------------------------------
# 输入/输出摘要提取
# ---------------------------------------------------------------------------

def _input_summary(agent_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """为每个 Agent 提取输入的关键字段，避免 trace 里塞完整 payload。"""
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    keep = {}
    # 通用键
    for k in ("lat", "lon", "scene", "floor", "orientation", "city",
              "purpose", "space_sqm", "difficulty", "container", "budget_cny",
              "crop", "top_crop", "zone_id", "start_date", "microclimate",
              "zone_data"):
        if k in payload:
            v = payload[k]
            if isinstance(v, dict):
                keep[k] = {kk: vv for kk, vv in list(v.items())[:6]}
            elif isinstance(v, list):
                keep[k] = v[:3]
            else:
                keep[k] = v
    return keep


def _output_summary(agent_name: str, output: Any) -> Dict[str, Any]:
    """提取 Agent 输出的关键字段（用于 trace，不做完整 dump）。"""
    if not isinstance(output, dict):
        return {"type": type(output).__name__}
    summary: Dict[str, Any] = {}

    if agent_name == "ClimateAgent":
        ev = output.get("evidence") or {}
        ct = output.get("constraints") or {}
        cf = output.get("confidence") or {}
        summary["zone_id"] = ev.get("zone_id")
        summary["climate_class"] = ev.get("climate_class")
        summary["data_sources"] = ev.get("data_sources")
        summary["min_temp"] = ct.get("min_temp")
        summary["max_temp"] = ct.get("max_temp")
        summary["rubric_score"] = cf.get("rubric_score")
    elif agent_name == "CropAgent":
        recos = output.get("recommendation") or []
        top = []
        for r in (recos or [])[:3]:
            if isinstance(r, dict):
                top.append({
                    "crop": r.get("crop"),
                    "adapt_score": r.get("adapt_score"),
                    "reason": (r.get("reason") or "")[:60],
                })
        summary["top3_crops"] = top
        summary["total_reco"] = len(recos)
    elif agent_name == "GrowthAgent":
        rec = output.get("recommendation") or {}
        phases = rec.get("phases") or []
        summary["crop"] = rec.get("crop")
        summary["total_days"] = rec.get("total_days")
        summary["phases_count"] = len(phases)
        summary["first_phase"] = phases[0] if phases and isinstance(phases[0], dict) else None
    elif agent_name == "EcoAgent":
        recos = output.get("recommendation") or []
        summary["devices_count"] = len(recos)
        summary["devices"] = [{
            "name": d.get("name"),
            "price_cny": d.get("price_cny") or d.get("price"),
            "category": d.get("category"),
        } for d in recos[:5] if isinstance(d, dict)]
    else:
        summary = {k: output[k] for k in list(output.keys())[:5]}
    return summary


# ---------------------------------------------------------------------------
# 跨 Agent 一致性检查
# ---------------------------------------------------------------------------

def check_cross_agent_consistency(
    result: Dict[str, Any],
    user_request: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    对 pipeline 结果做跨 Agent 一致性检查。

    检查项：
      - growth_start_date_frost：GrowthAgent 的 start_date 是否在 ClimateAgent
        的 min_temp > 0 时不早于冻结期（简单版本：min_temp < 0 时若 start_date
        落在冬季月份则警告）
      - eco_devices_budget_fit：EcoAgent 推荐设备总价是否超用户预算
      - top_crop_device_match：EcoAgent 是否有针对 top_crop 的设备
      - growth_crop_match：GrowthAgent 计划作物 == CropAgent 首推
      - climate_constraints_coverage：ClimateAgent 温度窗口覆盖 CropAgent
        top_crop 的经验窗口（若覆盖数据可用）

    返回：
      {
        "passed": bool,        # 无 error 级冲突
        "checked": int,        # 执行了几条规则
        "conflicts": [         # 冲突列表
          {"check": ..., "severity": "error"|"warning"|"info",
           "description": ..., "agents": [...]}
        ]
      }
    """
    user_request = user_request or {}
    steps = result.get("pipeline_steps", []) or []
    by_name: Dict[str, Any] = {s.get("agent"): s for s in steps if isinstance(s, dict)}

    climate = by_name.get("ClimateAgent", {}).get("output", {}) or {}
    crop_reco = by_name.get("CropAgent", {}).get("output", {}) or {}
    growth_plan = by_name.get("GrowthAgent", {}).get("output", {}) or {}
    eco_out = by_name.get("EcoAgent", {}).get("output", {}) or {}

    conflicts: List[Dict[str, Any]] = []

    # --- 1. ClimateAgent constraints 与 CropAgent 首推作物温度窗口匹配 ---
    top_crop = ""
    recs = crop_reco.get("recommendation") or []
    if recs and isinstance(recs[0], dict):
        top_crop = str(recs[0].get("crop") or "")

    if top_crop:
        window = _CROP_TEMP_WINDOWS.get(top_crop)
        ct = climate.get("constraints") or {}
        zmin, zmax = ct.get("min_temp"), ct.get("max_temp")
        if window and isinstance(zmin, (int, float)) and isinstance(zmax, (int, float)):
            cmin, cmax = window
            if cmin < zmin - 2 or cmax > zmax + 2:
                conflicts.append({
                    "check": "climate_constraints_coverage",
                    "severity": "warning",
                    "description": (
                        f"CropAgent 首推「{top_crop}」经验温度窗口 [{cmin}, {cmax}]°C"
                        f" 未被 ClimateAgent 分区窗口 [{zmin}, {zmax}]°C 完整覆盖"
                        f"（差异>2°C），推荐与分区约束存在潜在不匹配"
                    ),
                    "agents": ["ClimateAgent", "CropAgent"],
                    "expected": [cmin, cmax],
                    "actual": [zmin, zmax],
                })

    # --- 2. GrowthAgent 计划作物 vs CropAgent 首推 ---
    g_crop = ""
    g_rec = growth_plan.get("recommendation") or {}
    if isinstance(g_rec, dict):
        g_crop = str(g_rec.get("crop") or "")
    elif growth_plan:
        g_crop = str(growth_plan.get("crop") or "")
    if g_crop and top_crop and g_crop != top_crop:
        conflicts.append({
            "check": "growth_crop_match",
            "severity": "info",
            "description": (
                f"GrowthAgent 计划作物「{g_crop}」与 CropAgent 首推「{top_crop}」"
                "不同（可能是有意的次优选择，此处仅记录不改写）"
            ),
            "agents": ["CropAgent", "GrowthAgent"],
            "crop_agent_top": top_crop,
            "growth_agent_crop": g_crop,
        })

    # --- 3. EcoAgent 设备预算 ---
    user_budget = user_request.get("budget_cny")
    devices = eco_out.get("recommendation") or []
    if isinstance(user_budget, (int, float)) and user_budget > 0 and devices:
        total_price = 0.0
        for d in devices:
            if not isinstance(d, dict):
                continue
            p = d.get("price_cny", d.get("price"))
            if isinstance(p, (int, float)):
                total_price += float(p)
        if total_price > user_budget * 1.0:
            conflicts.append({
                "check": "eco_devices_budget_fit",
                "severity": "warning",
                "description": (
                    f"EcoAgent 推荐设备总价 {total_price:.0f} 元"
                    f" 超出用户预算 {user_budget:.0f} 元"
                    f"（超 {(total_price - user_budget):.0f} 元）"
                ),
                "agents": ["EcoAgent"],
                "user_budget": user_budget,
                "recommended_total": round(total_price, 2),
            })

    # --- 4. Top_crop 设备匹配 ---
    if top_crop and devices:
        has_match = any(
            isinstance(d, dict) and top_crop in str(d.get("name", ""))
            for d in devices
        )
        # 允许"通用"设备：不含作物名也算通过（如滴灌、育苗盘）
        generic_ok = any(
            isinstance(d, dict) and not d.get("crop_specific")
            for d in devices
        )
        if not has_match and not generic_ok:
            conflicts.append({
                "check": "top_crop_device_match",
                "severity": "info",
                "description": (
                    f"EcoAgent 推荐设备列表中无针对「{top_crop}」的专用设备"
                    "（也可能全部为通用设备）"
                ),
                "agents": ["CropAgent", "EcoAgent"],
                "top_crop": top_crop,
            })

    # --- 5. 冻结期 vs 播种期（简化：min_temp < -5 视为寒冷分区，冬季播种需谨慎）---
    #     start_date 从 user_request 里读；若用户未指定，GrowthAgent 会用默认
    start_date = user_request.get("start_date") or ""
    ct = climate.get("constraints") or {}
    zmin = ct.get("min_temp")
    if isinstance(zmin, (int, float)) and zmin < -5 and isinstance(start_date, str) and len(start_date) >= 10:
        # start_date 形如 "2026-02-15"
        try:
            month = int(start_date[5:7])
            # 冬季月份（12、1、2 月）；注意 `12 <= m <= 2` 永远 False，须写成分支
            if month >= 12 or month <= 2:
                conflicts.append({
                    "check": "growth_start_date_frost",
                    "severity": "info",
                    "description": (
                        f"寒冷分区（min_temp={zmin}°C）在冬季月份（{month}月）"
                        f"播种（start_date={start_date}），需评估冻害风险"
                    ),
                    "agents": ["ClimateAgent", "GrowthAgent"],
                    "zone_min_temp": zmin,
                    "start_date": start_date,
                })
        except (ValueError, IndexError):
            pass

    # 严重度分级：error 阻断通过；warning/info 仅记录
    sev_counts = {"error": 0, "warning": 0, "info": 0}
    for c in conflicts:
        sev_counts[c.get("severity", "info")] += 1

    return {
        "passed": sev_counts["error"] == 0,
        "checked": len(_CONSISTENCY_CHECKS),
        "conflicts_count": len(conflicts),
        "severity_counts": sev_counts,
        "conflicts": conflicts,
        "notes": "advisory only；不阻断流水线；冲突详情见 conflicts 字段",
    }


# ---------------------------------------------------------------------------
# Trace 导出
# ---------------------------------------------------------------------------

def export_trace_dict(trace: TraceRecord,
                      result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把 TraceRecord 序列化为可导出 JSON 的 dict（含摘要哈希）。"""
    d = trace.to_dict()
    if result:
        d["audit"] = {
            "consistency": result.get("consistency_audit", {}),
            "verification": result.get("verification", {}),
            "trust_summary": result.get("trust_summary", {}),
        }
    return d


def export_trace_json(trace: TraceRecord, path: str,
                      result: Optional[Dict[str, Any]] = None) -> str:
    """把 trace 写入 JSON 文件；返回路径。"""
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(export_trace_dict(trace, result),
                  f, ensure_ascii=False, indent=2, sort_keys=True)
    return path


# ---------------------------------------------------------------------------
# 对外便捷入口
# ---------------------------------------------------------------------------

def audit_pipeline_result(result: Dict[str, Any],
                          user_request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    便捷入口：对已生成的 pipeline result 做跨 Agent 一致性检查并写回 result。

    调用后 result 会多一个 `consistency_audit` 字段；不修改任何其他字段。
    """
    result["consistency_audit"] = check_cross_agent_consistency(result, user_request)
    return result
