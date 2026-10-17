"""verify_service.py — Verify-as-a-Service：成为农业 Agent 的验证者。

愿景：docs/next_stage_vision_2026-10-15.md §支柱五 · Verify-as-a-Service。

**定位**：从"被调用的工具"变成"被调用的裁判"。
任何一个第三方（另一个 Agent、一个大模型、一份 BP、一个农艺师）给出的农业主张，
经过本服务后得到：
  - verdict: "supported" | "contradicted" | "unverifiable"
  - our_estimate: {p10, p50, p90}
  - claimed_value: 用户声称值
  - deviation: 偏差
  - contradictions: 与物理/农艺约束的冲突
  - evidence: 可复算的证据链
  - trust_mark: SHA256

**三类可验证的冲突**（真正的专业深度）：
  1. 物理约束冲突：能量/物质守恒、光热上限、蒸腾-水分平衡
  2. 物候冲突：积温-发育期一致性
  3. 环境-品种冲突：生态位适宜度 + 概率化分区

零依赖：纯 math + dataclasses。
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.agriworld_lite import (
    DailyInput,
    get_params,
    simulate,
    theoretical_yield_cap,
    check_physical_feasibility,
    CropMechanisticParams,
)
from agent.conformal import SplitConformal, build_calibrator_from_pairs
from agent.phenology_extended import estimate_stage_days, resolve_key


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _compute_trust_mark(payload: Dict[str, Any]) -> str:
    """SHA256 trust_mark（对可复算部分）。"""
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 冲突检测器（三类）
# ---------------------------------------------------------------------------

@dataclass
class ClaimContext:
    """被验证主张的上下文。"""
    crop: str
    dli_mj_m2_d: Optional[float] = None        # 日累积辐射 MJ/m²/d
    days: Optional[int] = None                 # 种植天数
    temp_mean_c: Optional[float] = None
    rh: Optional[float] = None
    co2_ppm: Optional[float] = 420.0
    zone: Optional[str] = None                 # 气候分区
    latitude: Optional[float] = None
    scene: Optional[str] = None                # "balcony"/"greenhouse"/"field"


def check_physical_conflict(crop: str,
                            claimed_yield_g_m2: float,
                            ctx: ClaimContext) -> Optional[Dict[str, Any]]:
    """物理约束冲突检测：光能转化效率不可能超理论上限。"""
    if ctx.dli_mj_m2_d is None or ctx.days is None:
        return {"type": "physical", "status": "insufficient_context",
                "detail": "需要 dli_mj_m2_d 与 days"}
    result = check_physical_feasibility(crop, ctx.dli_mj_m2_d, ctx.days,
                                        claimed_yield_g_m2)
    return {
        "type": "physical",
        "check": "theoretical_energy_ceiling",
        "verdict": result["verdict"],
        "detail": result,
    }


def check_phenology_conflict(crop: str,
                            claimed_duration_days: int,
                            ctx: ClaimContext) -> Optional[Dict[str, Any]]:
    """物候冲突检测：积温-发育期一致性。

    给定声称的生长天数，检查在该温度下是否能完成一个完整生长周期。
    """
    if ctx.temp_mean_c is None:
        return {"type": "phenology", "status": "insufficient_context",
                "detail": "需要 temp_mean_c"}
    result = estimate_stage_days(crop, ctx.temp_mean_c)
    if not result.get("available"):
        return {"type": "phenology", "status": "crop_unavailable",
                "detail": "作物未移植"}
    if result.get("maturity_days_from_sow") is None:
        return {"type": "phenology", "status": "insufficient_thermal_time",
                "detail": f"日均温 {ctx.temp_mean_c}℃ 下发育停滞（TBASE={result.get('tbase_c')}）",
                "tbase_c": result.get("tbase_c")}
    theoretical_days = result["maturity_days_from_sow"]
    ratio = claimed_duration_days / max(theoretical_days, 1e-6)
    if ratio < 0.7:
        return {
            "type": "phenology",
            "check": "tsm_adequacy",
            "verdict": "contradicted",
            "claimed_days": claimed_duration_days,
            "theoretical_min_days": theoretical_days,
            "ratio": round(ratio, 3),
            "detail": (
                f"声称 {claimed_duration_days} 天成熟，但 TBASE={result['tbase_c']}℃ 下 "
                f"日均 {ctx.temp_mean_c}℃ 需要至少 {theoretical_days} 天"
            ),
        }
    return {
        "type": "phenology",
        "check": "tsm_adequacy",
        "verdict": "supported",
        "claimed_days": claimed_duration_days,
        "theoretical_min_days": theoretical_days,
        "ratio": round(ratio, 3),
    }


def check_zone_conflict(crop: str, ctx: ClaimContext) -> Optional[Dict[str, Any]]:
    """环境-品种冲突检测：生态位适宜度。

    用 lat + zone 做粗粒度检查（不依赖 Köppen 栅格，零依赖）。
    """
    if ctx.latitude is None and ctx.zone is None:
        return {"type": "zone", "status": "insufficient_context",
                "detail": "需要 latitude 或 zone"}
    # 热带作物：tbase >= 12
    p = get_params(resolve_key(crop) or crop.lower())
    tbase = getattr(p, "tbase_c", 15.0)
    if ctx.latitude is not None:
        lat = abs(ctx.latitude)
    # 热带作物（TBASE≥12）在寒冷带 → contradicted
    if tbase >= 12 and lat > 45:
        return {
            "type": "zone",
            "check": "tropical_crop_in_cold_zone",
            "verdict": "contradicted",
            "detail": (
                f"{crop}（TBASE={tbase}℃）为热带作物，"
                f"但当前纬度 {ctx.latitude}° 积温严重不足"
            ),
        }
    # 亚热带/暖温带作物（TBASE 8-12）在冷温带 → caution
    if 8 <= tbase < 12 and lat > 50:
        return {
            "type": "zone",
            "check": "subtropical_crop_in_cold_zone",
            "verdict": "caution",
            "detail": (
                f"{crop}（TBASE={tbase}℃）为亚热带/暖温带作物，"
                f"纬度 {ctx.latitude}° 户外种植可能困难，建议温室"
            ),
        }
        # 冷凉作物（TBASE ≤ 5）在高纬度 → 适合
        if tbase <= 5 and lat > 45:
            return {
                "type": "zone",
                "check": "cool_crop_in_cold_zone_ok",
                "verdict": "supported",
                "detail": f"{crop}（TBASE={tbase}℃）为冷凉作物，高纬度 {ctx.latitude}° 适合",
            }
    return {
        "type": "zone",
        "check": "niche_compatibility",
        "verdict": "supported",
        "detail": f"纬度 {ctx.latitude} 与 {crop} 的 TBASE={tbase}℃ 相符",
    }


# ---------------------------------------------------------------------------
# 验证器主入口
# ---------------------------------------------------------------------------

def verify_recommendation(
    claim: Dict[str, Any],
    context: Dict[str, Any],
    heuristic_engine_est: Optional[float] = None,
    use_conformal: bool = True,
) -> Dict[str, Any]:
    """验证一条农业建议。

    参数：
      claim : 被验证的主张，至少包含 crop 与至少一个可验证维度
              支持的维度：yield_g_m2, duration_days
      context : 上下文，见 ClaimContext
      heuristic_engine_est : 启发式引擎点估计（用于双轨参考）
      use_conformal : 是否输出保形区间

    返回：
      {
        verdict: "supported" | "contradicted" | "unverifiable",
        contradictions: [...],
        our_estimate: {p10, p50, p90} or None,
        claimed_value: {...},
        evidence: [...],
        trust_mark: "sha256:..."
      }
    """
    ctx = ClaimContext(**{k: v for k, v in context.items()
                          if k in ClaimContext.__dataclass_fields__})
    crop = claim.get("crop") or ctx.crop
    if not crop:
        return {"verdict": "unverifiable",
                "note": "缺少 crop 字段", "contradictions": []}

    contradictions = []
    evidence = []

    # 1. 物理约束
    if "yield_g_m2" in claim:
        phys = check_physical_conflict(crop, claim["yield_g_m2"], ctx)
        if phys:
            contradictions.append(phys)
            evidence.append({"check": "physical", "detail": phys})

    # 2. 物候
    if "duration_days" in claim:
        phen = check_phenology_conflict(crop, claim["duration_days"], ctx)
        if phen:
            contradictions.append(phen)
            evidence.append({"check": "phenology", "detail": phen})

    # 3. 环境-品种
    zone = check_zone_conflict(crop, ctx)
    if zone:
        contradictions.append(zone)
        evidence.append({"check": "zone", "detail": zone})

    # 4. 计算 our_estimate（用机理内核 + conformal）
    our_estimate = None
    if use_conformal and ctx.dli_mj_m2_d is not None and ctx.days is not None:
        # 用机理仿真
        base_action = DailyInput(
            dli=ctx.dli_mj_m2_d,
            temp_mean_c=ctx.temp_mean_c or 22.0,
            rh=ctx.rh or 0.60,
            co2_ppm=ctx.co2_ppm or 420.0,
        )
        sim = simulate(resolve_key(crop) or crop.lower(), [base_action] * ctx.days)
        p50 = sim["final_biomass"]["total"]
        # 保形区间：从默认校准器取
        try:
            from agent.conformal import get_default_calibrator
            cal = get_default_calibrator()
            p10, p50_cf, p90 = cal.predict_interval(p50)
            our_estimate = {"p10": round(p10, 2), "p50": round(p50_cf, 2),
                            "p90": round(p90, 2),
                            "method": "split_conformal",
                            "coverage_guarantee": cal.coverage_guarantee(),
                            "n_calibration": cal.n,
                            "note": "conformal 校准器基于 3 例 bench 快照，"
                                    "接入真实 feedback 后区间会更紧"}
        except Exception:
            our_estimate = {"p50": round(p50, 2), "note": "无 conformal 校准"}

    # 5. 与启发式引擎对比
    dual_track = None
    if heuristic_engine_est is not None and our_estimate:
        mech_est = our_estimate.get("p50")
        if mech_est is not None:
            from agent.dual_track import compare_tracks
            dual_track = compare_tracks(mech_est, heuristic_engine_est,
                                        dimension="yield_g_m2", unit="g/m²")
            evidence.append({"check": "dual_track", "detail": dual_track})

    # 6. 判定
    hard_contradictions = [c for c in contradictions
                           if isinstance(c, dict) and c.get("verdict") == "contradicted"]
    if hard_contradictions:
        verdict = "contradicted"
    elif contradictions and all(
        isinstance(c, dict) and c.get("verdict") == "supported"
        for c in contradictions
    ) and any(isinstance(c, dict) and "check" in c for c in contradictions):
        verdict = "supported"
    elif not contradictions:
        verdict = "unverifiable"
    else:
        verdict = "supported" if not any(
            isinstance(c, dict) and c.get("verdict") in ("contradicted", "caution")
            for c in contradictions
        ) else "caution"

    # 7. trust_mark（对可复算部分）
    evidence_payload = {
        "claim": claim,
        "context": context,
        "contradictions": contradictions,
        "our_estimate": our_estimate,
    }
    trust_mark = _compute_trust_mark(evidence_payload)

    return {
        "verdict": verdict,
        "crop": crop,
        "claimed_value": claim,
        "our_estimate": our_estimate,
        "contradictions": contradictions,
        "evidence": evidence,
        "dual_track": dual_track,
        "trust_mark": trust_mark,
        "verification_timestamp": _now_iso(),
        "schema": "verify_service/v1.0",
    }


def batch_verify(claims: Sequence[Tuple[Dict, Dict]]) -> Dict[str, Any]:
    """批量验证。claims = [(claim, context), ...]"""
    results = []
    counts = {"supported": 0, "contradicted": 0, "unverifiable": 0, "caution": 0}
    for claim, ctx in claims:
        r = verify_recommendation(claim, ctx)
        v = r.get("verdict", "unverifiable")
        if v in counts:
            counts[v] += 1
        results.append({"claim": claim, "result": r})
    return {
        "n_claims": len(results),
        "counts": counts,
        "results": results,
        "verification_summary": (
            f"{counts['supported']} 支持 / {counts['contradicted']} 反驳 / "
            f"{counts['unverifiable']} 不可验证 / {counts['caution']} 警示"
        ),
    }


if __name__ == "__main__":
    import json as _json
    print("=== Verify-as-a-Service 自测 ===")

    # 场景 1：物理上不可行的主张
    claim1 = {"crop": "potato", "yield_g_m2": 500.0}  # 声称 500 g/m²
    ctx1 = {"crop": "potato", "dli_mj_m2_d": 10.0, "days": 45}
    r1 = verify_recommendation(claim1, ctx1)
    print(f"\n场景 1（产量超理论上限）:")
    print(f"  声称={claim1}, 上下文={ctx1}")
    print(f"  判定: {r1['verdict']}")
    print(f"  冲突: {json.dumps(r1['contradictions'], ensure_ascii=False)[:200]}")
    print(f"  our_estimate: {r1['our_estimate']}")

    # 场景 2：物候不足（30 天收获番茄）
    claim2 = {"crop": "番茄", "duration_days": 30}
    ctx2 = {"crop": "番茄", "temp_mean_c": 18.0, "dli_mj_m2_d": 12.0,
            "days": 30, "latitude": 30.0}
    r2 = verify_recommendation(claim2, ctx2)
    print(f"\n场景 2（30 天收番茄，TBASE 不足）:")
    print(f"  判定: {r2['verdict']}")
    for c in r2["contradictions"]:
        print(f"    {c.get('type')}: {c.get('verdict')} - {c.get('detail', '')[:120]}")

    # 场景 3：可信主张（生菜 45 天，短周期叶菜）
    claim3 = {"crop": "生菜", "yield_g_m2": 60.0, "duration_days": 45}
    ctx3 = {"crop": "生菜", "dli_mj_m2_d": 10.0, "days": 45,
            "temp_mean_c": 22.0, "latitude": 30.0}
    r3 = verify_recommendation(claim3, ctx3)
    print(f"\n场景 3（合理主张：生菜 45 天 60 g/m²）:")
    print(f"  判定: {r3['verdict']}")
    print(f"  our_estimate: {r3['our_estimate']}")
    print(f"  冲突数: {len(r3['contradictions'])}")
    for c in r3["contradictions"]:
        if isinstance(c, dict) and "check" in c:
            print(f"    {c.get('type')}/{c.get('check')}: {c.get('verdict')}")

    # 场景 4：热带作物种在温带（辣椒在 60°N）
    claim4 = {"crop": "辣椒", "yield_g_m2": 200.0}
    ctx4 = {"crop": "辣椒", "latitude": 60.0, "dli_mj_m2_d": 8.0, "days": 90,
            "temp_mean_c": 8.0}
    r4 = verify_recommendation(claim4, ctx4)
    print(f"\n场景 4（辣椒种在 60°N）:")
    print(f"  判定: {r4['verdict']}")
    for c in r4["contradictions"]:
        print(f"    {c.get('type')}: {c.get('verdict')}")

    # 场景 5：批量
    print("\n批量验证：")
    batch = batch_verify([
        (claim1, ctx1), (claim2, ctx2), (claim3, ctx3), (claim4, ctx4),
    ])
    print(f"  汇总: {batch['verification_summary']}")

    # 校验断言
    assert r1["verdict"] == "contradicted", f"场景 1 应为 contradicted, got {r1['verdict']}"
    assert r2["verdict"] == "contradicted", f"场景 2 应为 contradicted, got {r2['verdict']}"
    assert r3["verdict"] == "supported", f"场景 3 应为 supported, got {r3['verdict']}"
    assert r4["verdict"] in ("caution", "contradicted"), (
        f"场景 4 应为 caution/contradicted, got {r4['verdict']}")
    print("\n✅ Verify-as-a-Service 自测通过")
