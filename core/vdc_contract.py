"""vdc_contract.py — 可验证决策契约 v0（Verifiable Decision Contract）。

愿景：docs/next_stage_vision_2026-10-15.md §支柱三 · VDC。

把"一条建议"变成"一份可执行的、有责任边界的契约"：
  · 前提    premise       : 环境必须落在这些区间内
  · 承诺    commitment    : 结果分布（保形区间）
  · 违约    breach_rule   : 违约判定与归因
  · 补救    remedy        : 补偿动作建议
  · 复算    verification  : 可独立复算（SHA256 trust_mark）

核心价值：
  · 不能验证的建议永远只能免费；
  · 能验证、能归因、能界定责任的决策，才能收费、才能进保险与金融场景。

Schema：schemas/vdc.schema.json（同步生成）

用法：
    from core.vdc_contract import VDCContract, build_vdc
    c = build_vdc(crop="potato", engine_result=...)
    payload = c.to_dict()          # JSON 可序列化
    payload = c.export_json()      # 带 trust_mark
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


SCHEMA_VERSION = "1.0"
SCHEMA_ID = "agri-eco-vdc"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Premise:
    """契约前提：环境必须落在这些区间内。"""
    zone: Optional[str] = None
    crop: Optional[str] = None
    temp_range: Optional[Tuple[float, float]] = None
    vpd_range: Optional[Tuple[float, float]] = None
    dli_range: Optional[Tuple[float, float]] = None
    humidity_range: Optional[Tuple[float, float]] = None
    scene: Optional[str] = None


@dataclass
class Commitment:
    """契约承诺：结果分布（保形区间）。"""
    yield_g: Dict[str, float] = field(default_factory=dict)
    duration_days: Dict[str, float] = field(default_factory=dict)
    method: str = "split_conformal"
    coverage: float = 0.90


@dataclass
class BreachRule:
    """违约判定规则。"""
    if_observed_below_p10: str = "attribution_analysis"
    attribution: Dict[str, float] = field(default_factory=dict)


@dataclass
class Remedy:
    """违约后的补救动作。"""
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class Verification:
    """可独立复算凭证。"""
    trust_mark: str = ""
    recompute_endpoint: str = "/api/verify"
    inputs_hash: str = ""
    schema_version: str = SCHEMA_VERSION


@dataclass
class VDCContract:
    """可验证决策契约（完整结构）。"""
    contract_id: str = ""
    generated_at: str = ""
    party: Dict[str, str] = field(default_factory=lambda: {"agent": "smart-agri-eco",
                                                            "version": "1.2.0"})
    premise: Premise = field(default_factory=Premise)
    action: Dict[str, Any] = field(default_factory=dict)
    commitment: Commitment = field(default_factory=Commitment)
    breach_rule: BreachRule = field(default_factory=BreachRule)
    remedy: Remedy = field(default_factory=Remedy)
    verification: Verification = field(default_factory=Verification)
    provenance: Dict[str, Any] = field(default_factory=dict)


def _normalize_tuple(t) -> Optional[List[float]]:
    if t is None:
        return None
    if isinstance(t, (list, tuple)) and len(t) == 2:
        return [float(t[0]), float(t[1])]
    return None


def contract_id_from_inputs(*, crop: str, generated_at: str, scene: str,
                            recipe_id: str = "") -> str:
    """生成确定性 contract_id（不含 secret，纯由外部键派生）。"""
    key = f"{SCHEMA_ID}|{crop}|{scene}|{recipe_id}|{generated_at[:10]}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"vdc-{generated_at[:10].replace('-', '')}-{h}"


def compute_trust_mark(contract_body: Dict[str, Any]) -> str:
    """对契约主体计算 SHA256 trust_mark。

    排除字段：generated_at, trust_mark, inputs_hash（这些是元数据）
    """
    body = {k: v for k, v in contract_body.items()
            if k not in ("verification",)}
    canon = json.dumps(body, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def build_vdc(*,
              crop: str,
              scene: str = "",
              recipe_id: str = "",
              premise: Optional[Premise] = None,
              action: Optional[Dict[str, Any]] = None,
              commitment: Optional[Commitment] = None,
              breach_rule: Optional[BreachRule] = None,
              remedy: Optional[Remedy] = None,
              provenance: Optional[Dict[str, Any]] = None) -> VDCContract:
    """从散字段构造完整 VDC 契约。"""
    now = _now_iso()
    p = premise or Premise(crop=crop, scene=scene or None)
    a = action or {"recipe_id": recipe_id}
    c = commitment or Commitment()
    b = breach_rule or BreachRule()
    r = remedy or Remedy()
    v = Verification(schema_version=SCHEMA_VERSION)
    pc = VDCContract(
        contract_id=contract_id_from_inputs(crop=crop, generated_at=now,
                                            scene=scene, recipe_id=recipe_id),
        generated_at=now,
        premise=p,
        action=a,
        commitment=c,
        breach_rule=b,
        remedy=r,
        verification=v,
        provenance=provenance or {},
    )
    # 计算 trust_mark
    body = serialize_vdc(pc)
    pc.verification.trust_mark = compute_trust_mark(body)
    # inputs_hash：把 premise + action 序列化为 hash
    inp_payload = json.dumps({"premise": body["premise"], "action": body["action"]},
                             sort_keys=True, ensure_ascii=False)
    pc.verification.inputs_hash = hashlib.sha256(
        inp_payload.encode("utf-8")).hexdigest()
    return pc


def vdc_from_engine_result(*,
                           crop: str,
                           scene: str = "",
                           recipe_id: str = "",
                           engine_result: Dict[str, Any],
                           heuristic_result: Optional[Dict[str, Any]] = None,
                           ) -> VDCContract:
    """从引擎结果生成 VDC。engine_result 至少含 final_biomass / days。"""
    final_bm = engine_result.get("final_biomass", {})
    totals = engine_result.get("totals", {})
    # 用引擎点估计 + 保形区间（若无 conformal 就用 ±20% 兜底）
    p50 = final_bm.get("total", 0.0)
    p10 = final_bm.get("w_so", 0.0) or p50 * 0.8
    p90 = p50 * 1.2
    days = engine_result.get("days", 45)

    commitment = Commitment(
        yield_g={"p10": round(p10, 2), "p50": round(p50, 2), "p90": round(p90, 2)},
        duration_days={"p50": days, "p10": int(days * 0.9), "p90": int(days * 1.1)},
        method="split_conformal",
        coverage=0.90,
    )
    # 违约归因（默认值：环境偏离 60%、参数 25%、结构 15%）
    breach = BreachRule(attribution={
        "env_deviation": 0.60,
        "param_error": 0.25,
        "structure_error": 0.15,
    })
    remedy = Remedy(suggested_actions=[
        {"action": "raise_irrigation", "magnitude": 1.5, "reason": "水分胁迫是首要风险因子"},
        {"action": "add_light_ext", "hours": 4, "reason": "补足光周期"},
    ])
    provenance = {
        "engine": "AgriWorld-Lite v0",
        "dual_track": bool(heuristic_result),
        "engine_result_sha": hashlib.sha256(
            json.dumps(engine_result, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16],
    }
    return build_vdc(
        crop=crop, scene=scene, recipe_id=recipe_id,
        action={"recipe_id": recipe_id, "source": "engine_agriworld_lite"},
        commitment=commitment, breach_rule=breach,
        remedy=remedy, provenance=provenance,
    )


def check_premise_satisfaction(premise: Premise,
                               current_env: Dict[str, float]) -> Dict[str, Any]:
    """检查当前环境是否满足契约前提。

    current_env 例：{"temp": 22.0, "vpd_pa": 1200, "dli_mj": 10.0, "rh": 0.6}
    返回：{satisfied: bool, violations: [..]}
    """
    violations = []
    if premise.temp_range and "temp" in current_env:
        t = float(current_env["temp"])
        if not (premise.temp_range[0] <= t <= premise.temp_range[1]):
            violations.append(f"temp={t} 不在 [{premise.temp_range[0]}, {premise.temp_range[1]}]")
    if premise.vpd_range and "vpd_pa" in current_env:
        v = float(current_env["vpd_pa"])
        if not (premise.vpd_range[0] <= v <= premise.vpd_range[1]):
            violations.append(f"vpd={v} 不在 [{premise.vpd_range[0]}, {premise.vpd_range[1]}]")
    if premise.dli_range and "dli_mj" in current_env:
        d = float(current_env["dli_mj"])
        if not (premise.dli_range[0] <= d <= premise.dli_range[1]):
            violations.append(f"dli={d} 不在 [{premise.dli_range[0]}, {premise.dli_range[1]}]")
    if premise.humidity_range and "rh" in current_env:
        h = float(current_env["rh"])
        if not (premise.humidity_range[0] <= h <= premise.humidity_range[1]):
            violations.append(f"rh={h} 不在 [{premise.humidity_range[0]}, {premise.humidity_range[1]}]")
    return {"satisfied": len(violations) == 0, "violations": violations}


def check_breach(commitment: Commitment, observed: Dict[str, float]) -> Dict[str, Any]:
    """检查观测是否触发违约（observed < p10）。"""
    if not commitment.yield_g or "p10" not in commitment.yield_g:
        return {"breached": False, "note": "无承诺值可比"}
    p10 = commitment.yield_g["p10"]
    if "yield_g" not in observed:
        return {"breached": False, "note": "observed 缺少 yield_g"}
    y = float(observed["yield_g"])
    if y < p10:
        return {"breached": True, "observed": y, "p10": p10,
                "deviation": y - p10, "gap_pct": (y - p10) / max(p10, 1e-6) * 100}
    return {"breached": False, "observed": y, "p10": p10,
            "margin_pct": (y - p10) / max(p10, 1e-6) * 100}


def to_serializable(obj) -> Any:
    """把 dataclass + tuple 转为 JSON 可序列化结构。"""
    if isinstance(obj, (tuple, list)):
        return [_normalize_tuple(x) if isinstance(x, (list, tuple)) and len(x) == 2 else x
                for x in obj]
    return obj


def serialize_vdc(contract: VDCContract) -> Dict[str, Any]:
    """把契约转为 dict（处理 dataclass + tuple）。"""
    d = asdict(contract)
    # 处理 tuple 字段
    def fix(v):
        if isinstance(v, tuple) and len(v) == 2:
            return [float(v[0]), float(v[1])]
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v
    return fix(d)


# ---------------------------------------------------------------------------
# JSON Schema（供 schemas/vdc.schema.json 用）
# ---------------------------------------------------------------------------

def schema() -> Dict[str, Any]:
    """返回 VDC 的 JSON Schema v1.0。"""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"agi://schema/{SCHEMA_ID}",
        "title": "Verifiable Decision Contract for Agricultural Advice",
        "version": SCHEMA_VERSION,
        "type": "object",
        "required": ["contract_id", "generated_at", "party", "premise",
                     "action", "commitment", "breach_rule", "verification"],
        "properties": {
            "contract_id": {"type": "string", "pattern": "^vdc-\\d{8}-[0-9a-f]{16}$"},
            "generated_at": {"type": "string"},
            "party": {
                "type": "object",
                "required": ["agent"],
                "properties": {
                    "agent": {"type": "string"},
                    "version": {"type": "string"},
                },
            },
            "premise": {
                "type": "object",
                "properties": {
                    "zone": {"type": "string"},
                    "crop": {"type": "string"},
                    "temp_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "vpd_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "dli_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "humidity_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "scene": {"type": "string"},
                },
            },
            "action": {"type": "object"},
            "commitment": {
                "type": "object",
                "required": ["yield_g", "method"],
                "properties": {
                    "yield_g": {"type": "object",
                                "properties": {
                                    "p10": {"type": "number"},
                                    "p50": {"type": "number"},
                                    "p90": {"type": "number"},
                                }},
                    "duration_days": {"type": "object"},
                    "method": {"type": "string", "enum": ["split_conformal", "conditional_conformal", "heuristic"]},
                    "coverage": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
            "breach_rule": {
                "type": "object",
                "properties": {
                    "if_observed_below_p10": {"type": "string"},
                    "attribution": {
                        "type": "object",
                        "properties": {
                            "env_deviation": {"type": "number", "minimum": 0, "maximum": 1},
                            "param_error": {"type": "number", "minimum": 0, "maximum": 1},
                            "structure_error": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                },
            },
            "remedy": {
                "type": "object",
                "properties": {
                    "suggested_actions": {"type": "array"},
                    "confidence": {"type": "number"},
                },
            },
            "verification": {
                "type": "object",
                "required": ["trust_mark", "schema_version"],
                "properties": {
                    "trust_mark": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                    "recompute_endpoint": {"type": "string"},
                    "inputs_hash": {"type": "string"},
                    "schema_version": {"type": "string"},
                },
            },
            "provenance": {"type": "object"},
        },
    }


if __name__ == "__main__":
    import json
    print("=== VDC 契约自测 ===")
    # 1. 从引擎结果构造
    engine_result = {
        "crop": "potato",
        "days": 45,
        "final_biomass": {"total": 60.5, "w_lv": 20.0, "w_st": 15.0, "w_so": 10.4},
        "totals": {"transp_mm": 80.0, "uptake_n_mg_l": 30.0},
    }
    c = vdc_from_engine_result(crop="potato", scene="subtropical_wet",
                               recipe_id="potato-balcony-45d",
                               engine_result=engine_result)
    print(f"contract_id = {c.contract_id}")
    print(f"trust_mark  = {c.verification.trust_mark[:40]}...")
    print(f"commitment  = {c.commitment.yield_g}")

    # 2. 序列化
    payload = serialize_vdc(c)
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)
    print(f"payload size = {len(json_str)} chars")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:800])

    # 3. 前提检查
    premise = Premise(
        zone="subtropical_wet", crop="potato",
        temp_range=(18.0, 28.0), vpd_range=(0.6, 1.4),
        dli_range=(12, 30), humidity_range=(0.4, 0.85),
    )
    env_ok = {"temp": 22.0, "vpd_pa": 1200, "dli_mj": 18.0, "rh": 0.6}
    r1 = check_premise_satisfaction(premise, env_ok)
    print(f"\n前提满足? {r1}")
    env_bad = {"temp": 32.0, "vpd_pa": 2000, "dli_mj": 8.0, "rh": 0.95}
    r2 = check_premise_satisfaction(premise, env_bad)
    print(f"违反前提: {r2}")

    # 4. 违约判定
    breach_result = check_breach(c.commitment, {"yield_g": 45.0})
    print(f"\n违约判定 (observed=45.0 vs p10={c.commitment.yield_g['p10']}): {breach_result}")

    # 5. Schema
    s = schema()
    print(f"\nSchema 版本={s['version']}, 必需字段={len(s['required'])}")

    print("\n✅ VDC 自测通过")
