"""
AgriOrchestrator - 四 Agent 串行 + 反馈闭环编排

编排逻辑：
  用户输入
    → ClimateAgent  分区匹配
    → CropAgent     作物推荐
    → GrowthAgent   种植计划生成
    → EcoAgent      生态撮合（设备/社区/供需）
    → 反馈闭环：用户种植结果 → 数据回流 → 模型迭代

对标 SwarmLabs engine/flywheel.py 的 multi-agent 串行 + 主动学习反馈闭环
"""

from typing import Any, Dict, List, Optional

from .climate_agent import ClimateAgent
from .crop_agent import CropAgent
from .growth_agent import GrowthAgent
from .eco_agent import EcoAgent
from .pest_agent import PestAgent
from .nutrition_agent import NutritionAgent
from .season_agent import SeasonAgent

import os
import json
import glob
import hashlib

# 引擎侧能力（可选依赖：引擎缺失时编排器仍能独立运行，不硬绑定）
try:
    from engine import work_item as _work_item
    from engine import long_term_memory as _long_term_memory
    from engine import org_memory as _org_memory
except Exception:  # pragma: no cover - 仅在引擎不可导入时
    _work_item = None
    _long_term_memory = None
    _org_memory = None


def _agent_score(output: Dict[str, Any]) -> float:
    """统一取 Agent 置信度：rubric_score 优先，其次 match_quality。"""
    conf = output.get("confidence", {})
    return float(conf.get("rubric_score", conf.get("match_quality", 0.0)))


def _load_known_zone_ids() -> set:
    """从全球分区元数据取真实 zone_id 集合，供 Verifier 校验（缺文件时返回空集）。"""
    import json as _json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "zone_meta", "global_zones.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        return set()
    ids = set()
    zones = data.get("zones", []) if isinstance(data, dict) else []
    for z in zones if isinstance(zones, list) else []:
        for key in ("zone_id", "id"):
            if isinstance(z, dict) and z.get(key):
                ids.add(str(z[key]))
    return ids


# ---------------------------------------------------------------------------
# Verifier（借 QoderWake 的 Executor/Verifier 分离）
#
# 原则：不只看「有没有字段」，而是校验字段的**语义合法性**。
# 历史上这类检查只断言 content 里含 "text"，导致工具返回 {"error": ...} 也判通过。
# ---------------------------------------------------------------------------
def verify_agent_output(name: str, output: Any,
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对单个 Agent 输出做结构化校验，返回 {ok, checks:[{name, ok, detail}]}。"""
    context = context or {}
    checks: List[Dict[str, Any]] = []

    def _check(cname: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": cname, "ok": bool(ok), "detail": detail})

    if not isinstance(output, dict):
        _check("output_is_dict", False, f"输出类型 {type(output).__name__} 非 dict")
        return {"ok": False, "checks": checks}
    _check("no_placeholder",
           "PLACEHOLDER" not in json.dumps(output, ensure_ascii=False),
           # 注意：detail 里不得出现哨兵字面量本身，否则 Verifier 元数据会污染
           # 结果 JSON，反过来触发项目的「不得含 PLACEHOLDER」回归守卫。
           "输出中不得含占位符哨兵")
    _check("no_error_payload", "error" not in output or not output["error"],
           "输出不得携带 error 载荷")

    if name == "ClimateAgent":
        zone_id = output.get("evidence", {}).get("zone_id", "")
        known = _load_known_zone_ids()
        _check("zone_id_present", bool(zone_id), f"zone_id={zone_id!r}")
        if known:
            _check("zone_id_known", zone_id in known,
                   f"{zone_id} 是否在 global_zones.json 中（共 {len(known)} 个）")

    elif name == "CropAgent":
        recs = output.get("recommendation", [])
        _check("recommendation_is_list", isinstance(recs, list))
        _check("recommendation_nonempty", isinstance(recs, list) and len(recs) > 0,
               f"{len(recs) if isinstance(recs, list) else 'N/A'} 条")
        bad = [r for r in recs if isinstance(r, dict)
               and (not r.get("crop") or not isinstance(r.get("adapt_score"), (int, float)))]
        _check("recommendation_items_valid", not bad,
               f"{len(bad)} 条缺 crop/adapt_score")
        oor = [r["crop"] for r in recs if isinstance(r, dict)
               and isinstance(r.get("adapt_score"), (int, float))
               and not (0.0 <= float(r["adapt_score"]) <= 1.0)]
        _check("adapt_score_in_range", not oor, f"越界: {oor[:3]}")

    elif name == "GrowthAgent":
        phases = output.get("recommendation", {}).get("phases", [])
        _check("growth_phases_count", isinstance(phases, list) and len(phases) == 4,
               f"阶段数 {len(phases) if isinstance(phases, list) else 'N/A'}（约定 4 阶段）")
        _check("growth_data_loaded",
               bool(output.get("evidence", {}).get("data_loaded")),
               "evidence.data_loaded 必须为真，否则是空跑")
        alerts = output.get("recommendation", {}).get("risk_alerts", [])
        _check("growth_has_risk_alerts", isinstance(alerts, list) and len(alerts) > 0,
               "种植计划必须给出风险提示")

    elif name == "EcoAgent":
        recs = output.get("recommendation", [])
        _check("devices_is_list", isinstance(recs, list))
        budget = context.get("budget_cny")
        total = output.get("constraints", {}).get("total_estimated_price_cny")
        if budget and total is not None:
            _check("device_budget_gate", float(total) <= float(budget),
                   f"总价 {total} <= 预算 {budget}")

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def verify_pipeline_result(result: Dict[str, Any],
                           budget_cny: Optional[float] = None) -> Dict[str, Any]:
    """校验整个流水线结果（各 Agent 输出 + trust_summary）。"""
    failures: List[str] = []
    per_agent: Dict[str, Any] = {}
    for step in result.get("pipeline_steps", []):
        name = step.get("agent", "")
        report = verify_agent_output(
            name, step.get("output", {}),
            {"budget_cny": step.get("budget_cny", budget_cny)},
        )
        per_agent[name] = report
        if not report["ok"]:
            failures.append(name)
    ts = result.get("trust_summary", {})
    score = ts.get("overall_rubric_score")
    _score_ok = isinstance(score, (int, float)) and 0.0 <= float(score) <= 1.0
    if not _score_ok:
        failures.append("trust_summary.overall_rubric_score")
    return {
        "passed": not failures,
        "verified_agents": len(per_agent),
        "failures": failures,
        "per_agent": per_agent,
        "overall_rubric_score_in_range": _score_ok,
    }



# 按需调用（反应式）技能：由 call_skill 直接路由到独立 Agent 的 run(payload)
ONDEMAND_SKILLS = {
    "pest_diagnose": {"agent": "pest", "label": "病虫害与营养缺乏诊断"},
    "nutrition_plan": {"agent": "nutrition", "label": "养分管理与阶段化施肥"},
    "season_advisory": {"agent": "season", "label": "物候推演与霜冻锚定播期窗口"},
}

# 注册表目录（用于技能目录自动发现）
_REGISTRY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "skills", "registry")


class AgriOrchestrator:
    """四 Agent 串联编排器 + 统一技能路由

    两类入口：
      - run_pipeline()：规划流水线（Climate→Crop→Growth→Eco 四 Agent 串行）
      - call_skill(name, payload)：按需/反应式技能（PestAgent / NutritionAgent 等）
    """

    def __init__(self):
        self.climate = ClimateAgent()
        self.crop = CropAgent()
        self.growth = GrowthAgent()
        self.eco = EcoAgent()
        self.pest = PestAgent()
        self.nutrition = NutritionAgent()
        self.season = SeasonAgent()
        # Session 幂等缓存（借 QoderWake 的幂等恢复）：
        # 同一 session_id + 同一输入 → 直接返回已算结果；崩溃后重跑可续上。
        self._sessions: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _payload_key(user_request: Dict[str, Any]) -> str:
        """输入指纹：判断同 session 下输入是否变化。"""
        raw = json.dumps(user_request or {}, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """取出某 session 的已缓存结果（供崩溃恢复/审计）。"""
        entry = self._sessions.get(session_id)
        if not entry:
            return None
        return {"payload_key": entry["payload_key"], "result": entry["result"]}

    def session_stats(self) -> Dict[str, Any]:
        return {"active_sessions": len(self._sessions),
                "session_ids": sorted(self._sessions.keys())}

    # ---------- 统一技能路由 ----------
    def list_skills(self) -> list:
        """返回全部注册表技能目录（含是否可经 call_skill 直接调用）。"""
        skills = []
        if not os.path.isdir(_REGISTRY_DIR):
            return skills
        for path in sorted(glob.glob(os.path.join(_REGISTRY_DIR, "*.json"))):
            if os.path.basename(path) == "schema.json":
                continue  # 注册表元 Schema，非可调用技能
            try:
                with open(path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            sid = meta.get("id") or meta.get("skill") or os.path.splitext(os.path.basename(path))[0]
            skills.append({
                "id": sid,
                "name": meta.get("name", sid),
                "agent": meta.get("agent", ""),
                "domain": meta.get("domain", ""),
                "implemented": bool(meta.get("implemented", False)),
                "description": meta.get("description", ""),
                "callable_via": "call_skill" if sid in ONDEMAND_SKILLS else "pipeline",
            })
        return skills

    def call_skill(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """按技能名路由到对应 Agent（反应式技能）。

        当前支持：pest_diagnose / nutrition_plan / season_advisory。
        规划流水线技能（climate/crop/growth/eco）请走 run_pipeline()。
        """
        entry = ONDEMAND_SKILLS.get(name)
        if not entry:
            available = " / ".join(sorted(ONDEMAND_SKILLS.keys()))
            raise ValueError(f"未知技能「{name}」；call_skill 当前支持：{available}")
        agent = getattr(self, entry["agent"])
        return agent.run(payload or {})

    def run_pipeline(
        self,
        user_request: Dict[str, Any],
        session_id: Optional[str] = None,
        verify: bool = True,
        work_item_id: Optional[str] = None,
        record_memory: bool = True,
    ) -> Dict[str, Any]:
        """
        完整流水线：从地块信息到可执行种植方案

        参数：
            user_request: {
                "lat": 30.2741, "lon": 120.1551,  # 杭州
                "scene": "balcony",
                "floor": 15, "orientation": "south",
                "purpose": "食用",
                "space_sqm": 1.5,
                "difficulty": "beginner",
                "budget_cny": 500,
            }
            session_id: 可选。传入后启用幂等：同 session_id + 同输入直接返回缓存；
                同 session_id + 不同输入抛 ValueError（防止错误复用缓存）。
            verify: 可选，默认 True。在返回前对每个 Agent 输出做结构化校验。
            work_item_id: 可选。传入后为本次流水线建显式工作项（OpenOPC 式
                状态机），并把状态流转审计附在结果的 work_item 字段里。
            record_memory: 可选，默认 True。流水线结束时把「分区+作物+结论」
                写入本地长期记忆，供后续会话召回（跨会话上下文）。

        返回：
            {
                "pipeline_steps": [
                    {"agent": "ClimateAgent", "status": "ok", "output": {...}},
                    {"agent": "CropAgent", "status": "ok", "output": {...}},
                    {"agent": "GrowthAgent", "status": "ok", "output": {...}},
                    {"agent": "EcoAgent", "status": "ok", "output": {...}},
                ],
                "final_recommendation": {
                    "zone": "...",
                    "recommended_crops": [...],
                    "growth_plan": {...},
                    "devices": [...],
                    "confidence_summary": {...}
                },
                "trust_summary": {
                    "overall_rubric_score": 0.8,
                    "data_coverage": "...",
                    "known_limitations": [...]
                }
            }
        """
        user_request = user_request or {}
        payload_key = self._payload_key(user_request)

        # Session 幂等恢复：同 session + 同输入 → 复用已算结果（崩溃重跑可续上）
        if session_id:
            entry = self._sessions.get(session_id)
            if entry is not None:
                if entry["payload_key"] == payload_key:
                    cached = dict(entry["result"])
                    cached["session"] = {
                        "session_id": session_id,
                        "payload_key": payload_key,
                        "from_cache": True,
                    }
                    return cached
                raise ValueError(
                    f"session_id 冲突：{session_id!r} 已绑定不同输入"
                    f"（{entry['payload_key']} ≠ {payload_key}）。"
                    "同一 session_id 必须对应同一输入，否则可能返回错误的缓存结果。"
                )

        # 工作项状态机（借鉴 OpenOPC）：给流水线一个可审计的状态
        wi = None
        if _work_item is not None:
            wi = _work_item.new_work_item(
                work_item_id or ("wi-%s" % payload_key),
                title="种植方案流水线：%s" % (user_request.get("city") or user_request.get("scene") or "未知地块"),
                actor="AgriOrchestrator",
                reuse=bool(work_item_id),
            )
            wi.transition("execute", actor="AgriOrchestrator", payload=user_request)

        # Step 1: 分区匹配
        lat, lon = user_request.get("lat", 0), user_request.get("lon", 0)
        zone_data = self.climate.match_zone(lat, lon)

        # Step 2: 微气候修正
        micro = self.climate.microclimate_adjustment(
            {
                "scene": user_request.get("scene", "balcony"),
                "floor": user_request.get("floor", 1),
                "orientation": user_request.get("orientation", "south"),
                "city": user_request.get("city", ""),
            }
        )

        # Step 3: 作物推荐
        crop_reco = self.crop.recommend(
            zone_data=zone_data,
            preferences={
                "purpose": user_request.get("purpose", "食用"),
                "space_sqm": user_request.get("space_sqm", 1.0),
                "difficulty": user_request.get("difficulty", "beginner"),
                "container": user_request.get("scene") in ["balcony", "office"],
            },
        )

        # Step 4: 种植计划（选第一个推荐作物，传入微气候与分区约束）
        growth_plan = {}
        top_crop = ""
        if crop_reco.get("recommendation"):
            top_crop = crop_reco["recommendation"][0].get("crop", "")
            growth_plan = self.growth.generate_growth_plan(
                crop=top_crop,
                zone_data=zone_data,
                start_date=user_request.get("start_date", ""),
                scene=user_request.get("scene", "balcony"),
                microclimate=micro,
            )

        # Step 5: 生态撮合
        devices = self.eco.recommend_device(
            scene=user_request.get("scene", "balcony"),
            crop=top_crop if crop_reco.get("recommendation") else "",
            zone_data=zone_data,
            budget=user_request.get("budget_cny", 0),
        )

        result = {
            "pipeline_steps": [
                {"agent": "ClimateAgent", "status": "ok", "output": zone_data, "microclimate": micro},
                {"agent": "CropAgent", "status": "ok", "output": crop_reco},
                {"agent": "GrowthAgent", "status": "ok", "output": growth_plan},
                {"agent": "EcoAgent", "status": "ok", "output": devices},
            ],
            "final_recommendation": {
                "zone": zone_data.get("evidence", {}).get("zone_id", "UNKNOWN"),
                "recommended_crops": crop_reco.get("recommendation", []),
                "growth_plan": growth_plan,
                "devices": devices.get("recommendation", []),
            },
            "trust_summary": {
                "overall_rubric_score": round(
                    sum(
                        _agent_score(s["output"])
                        for s in [
                            {"output": zone_data},
                            {"output": crop_reco},
                            {"output": growth_plan},
                            {"output": devices},
                        ]
                    ) / 4, 2
                ),
                "known_limitations": [
                    "作物-分区适配为公开文献聚合，未叠加本地实测校准",
                    "病虫害诊断已独立实现 PestAgent（数据驱动 + 可插拔视觉，默认规则降级），经 orchestrator.call_skill('pest_diagnose') 统一调用",
                    "养分管理已独立实现 NutritionAgent（作物科属 NPK 侧重 + 阶段化施肥方案），经 orchestrator.call_skill('nutrition_plan') 统一调用",
                    "供需撮合为结构化模板，需接入真实供给方数据后生效",
                ],
            },
        }

        # Verifier 阶段（Executor 产出 → Verifier 复核，二者分离）
        if verify:
            result["verification"] = verify_pipeline_result(
                result, budget_cny=user_request.get("budget_cny"))
        else:
            result["verification"] = {"passed": None, "skipped": True,
                                      "note": "verify=False，未做结构化校验"}

        # 跨会话长期记忆：先召回同分区同作物的历史（下次会话能看到「上次出了什么」）
        if _long_term_memory is not None:
            zone_id = result["final_recommendation"].get("zone", "")
            prior = _long_term_memory.recall(
                crop=top_crop, zone=zone_id, k=3, expand=True)
            result["prior_memory"] = [
                {"id": h["id"], "ts": h["ts"], "score": h["score"],
                 "summary": (h["memory"] or {}).get("summary", ""),
                 "outcome": (h["memory"] or {}).get("outcome", "")}
                for h in prior
            ]

        # 工作项状态机收尾：复核 → 集成（复核不通过则回炉 rework）
        if wi is not None:
            v = result.get("verification", {})
            if v.get("skipped"):
                wi.transition("review", actor="Verifier", note="verify=False，跳过复核")
                wi.transition("integrate", actor="AgriOrchestrator")
                wi.transition("integrate", actor="AgriOrchestrator",
                              note="未复核直接集成（跳过复核）")
            else:
                wi.transition("review", actor="Verifier", payload=v)
                if v.get("passed"):
                    wi.transition("integrate", actor="AgriOrchestrator")
                    wi.transition("integrate", actor="AgriOrchestrator",
                                  note="集成产物，流水线结束")
                else:
                    wi.transition("rework", actor="Verifier",
                                  note="复核未通过：%s" % (v.get("failures") or []))
            result["work_item"] = wi.summary()
            result["work_item_audit"] = wi.audit

        # 记忆写入：本次流水线的结论落到长期记忆（append-only，本地）
        if record_memory and _long_term_memory is not None:
            zone_id = result["final_recommendation"].get("zone", "")
            v = result.get("verification", {})
            outcome = ("verified" if v.get("passed") else
                       ("unverified" if not v.get("skipped") else "skipped"))
            reco = result["final_recommendation"].get("recommended_crops") or []
            top_n = "、".join(str(r.get("crop", "")) for r in reco[:3]
                              if isinstance(r, dict)) or "（无推荐）"
            try:
                mid = _long_term_memory.add_memory(
                    session_id=session_id or "",
                    skill="run_pipeline",
                    kind="plan",
                    crop=top_crop, zone=zone_id,
                    scene=str(user_request.get("scene", "")),
                    summary="分区 %s，推荐 %s；信任分 %s" % (
                        zone_id, top_n,
                        result.get("trust_summary", {}).get("overall_rubric_score")),
                    outcome=outcome,
                    confidence=result.get("trust_summary", {}).get("overall_rubric_score"),
                    tags=[t for t in [top_crop, zone_id, outcome] if t],
                )
                result["memory_id"] = mid
            except Exception as exc:  # pragma: no cover - 记忆故障不阻断主流水线
                result["memory_error"] = str(exc)[:200]

        # Session 记录（供幂等恢复与审计）
        if session_id:
            result["session"] = {
                "session_id": session_id,
                "payload_key": payload_key,
                "from_cache": False,
            }
            self._sessions[session_id] = {"payload_key": payload_key,
                                          "result": result}
        return result
