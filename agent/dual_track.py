"""dual_track.py — 双轨分歧告警器（机理轨 vs 启发式轨）。

愿景：docs/next_stage_vision_2026-10-15.md §支柱一 · 双轨 + 分歧告警。

设计：
  - 机理轨：AgriWorld-Lite 微场景数字孪生（可微分、物理约束）
  - 启发式轨：现有规则表（已被 69 个 bench 用例验证）
  - 两轨并行运行，分歧超过阈值时降置信度 + 显式标注

**为什么这重要**：两个独立方法不一致 = 我们真的不确定。
这本身就是"诚实暴露不确定性"的最强表达，比任何单一区间都强。

接口：
  compare_tracks(mechanistic_est, heuristic_est, tol, unit, dimension) → {
    verdict, divergence, confidence_multiplier, notes
  }

判定规则：
  - divergence < tol·0.3  → aligned，confidence=1.0
  - tol·0.3 ≤ divergence < tol  → mild_divergence，confidence=0.85
  - tolerance ≤ divergence < 2·tol  → significant_divergence，confidence=0.5
  - divergence ≥ 2·tol  → critical_divergence，confidence=0.2，标记 untrustworthy
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


DEFAULT_TOLERANCE = 0.25  # 25% 相对分歧阈值


def _relative_divergence(a: float, b: float) -> float:
    """相对分歧 = |a-b| / max(|a|, |b|, ε)"""
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom


def compare_tracks(mechanistic_est: float, heuristic_est: float,
                   tol: float = DEFAULT_TOLERANCE,
                   unit: str = "", dimension: str = "",
                   direction_hint: str = "") -> Dict[str, Any]:
    """比较机理轨与启发式轨的估计，返回分歧诊断。

    参数：
      mechanistic_est : 机理模型（AgriWorld-Lite）输出
      heuristic_est   : 启发式规则表输出
      tol             : 允许的最大相对分歧
      unit            : 单位字符串（仅用于可读性）
      dimension       : 维度名（"yield"/"duration"/"biomass" 等）
      direction_hint  : "higher" / "lower" / ""，机理轨偏高或偏低

    返回：
      {
        "verdict": "aligned" | "mild_divergence" | "significant_divergence" | "critical_divergence",
        "mechanistic_est": ...,
        "heuristic_est": ...,
        "absolute_diff": ...,
        "relative_divergence": ...,
        "tolerance": ...,
        "confidence_multiplier": ...,
        "unit": ..., "dimension": ...,
        "direction": "mechanistic_higher" | "mechanistic_lower" | "aligned" | direction_hint,
        "notes": str,
      }
    """
    mech = float(mechanistic_est)
    heur = float(heuristic_est)
    abs_diff = abs(mech - heur)
    rel = _relative_divergence(mech, heur)

    # 分级（对齐带取 0.5·tol，让 3-8% 的分歧进入 mild 而不是 aligned）
    if rel < 0.5 * tol:
        verdict = "aligned"
        mult = 1.0
        note = "机理轨与启发式轨基本一致"
    elif rel < tol:
        verdict = "mild_divergence"
        mult = 0.85
        note = "轻度分歧，可继续以启发式为主、机理作辅助"
    elif rel < 2 * tol:
        verdict = "significant_divergence"
        mult = 0.5
        note = "显著分歧：两轨给出不同方向的答案，建议人工复核"
    else:
        verdict = "critical_divergence"
        mult = 0.2
        note = "严重分歧：两轨可能一方有系统性偏差，标记为 untrustworthy"

    # 方向判定
    if abs_diff < 1e-9:
        direction = "aligned"
    elif mech > heur:
        direction = "mechanistic_higher"
    else:
        direction = "mechanistic_lower"
    if direction_hint and direction_hint in ("higher", "lower"):
        direction = direction_hint

    return {
        "verdict": verdict,
        "mechanistic_est": round(mech, 6),
        "heuristic_est": round(heur, 6),
        "absolute_diff": round(abs_diff, 6),
        "relative_divergence": round(rel, 6),
        "tolerance": tol,
        "confidence_multiplier": mult,
        "unit": unit,
        "dimension": dimension,
        "direction": direction,
        "notes": note,
    }


def apply_confidence(base_confidence: float, track_comparison: Dict[str, Any]) -> float:
    """将双轨结果乘到基置信度上（不低于 0.05 保证可用）。"""
    mult = track_comparison.get("confidence_multiplier", 1.0)
    return max(0.05, float(base_confidence) * mult)


def summarize_divergences(comparisons: List[Dict[str, Any]]) -> Dict[str, Any]:
    """批量比较的汇总统计。"""
    if not comparisons:
        return {"n": 0, "aligned": 0, "mild": 0, "significant": 0, "critical": 0, "avg_confidence": 1.0}
    counts = {"aligned": 0, "mild_divergence": 0, "significant_divergence": 0, "critical_divergence": 0}
    confs = []
    for c in comparisons:
        v = c.get("verdict")
        if v in counts:
            counts[v] += 1
        confs.append(c.get("confidence_multiplier", 1.0))
    return {
        "n": len(comparisons),
        "aligned": counts["aligned"],
        "mild": counts["mild_divergence"],
        "significant": counts["significant_divergence"],
        "critical": counts["critical_divergence"],
        "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 1.0,
        "untrustworthy_count": counts["critical_divergence"],
    }


if __name__ == "__main__":
    # 自测：以 tol=0.25 为基准（默认），四档明确
    tests = [
        (300, 295, "aligned", 0.25),                # rel=1.7%  < 0.5*tol
        (300, 260, "mild_divergence", 0.25),        # rel=15%   0.5*tol..tol
        (300, 200, "significant_divergence", 0.25), # rel=33%   tol..2*tol
        (300, 100, "critical_divergence", 0.25),    # rel=67%   >2*tol
        (1200, 1200, "aligned", 0.25),              # 完全一致
        (500, 550, "mild_divergence", 0.10),        # 紧阈值：10% → mild
    ]
    print("双轨分歧告警自测：")
    for a, b, expected, tol in tests:
        r = compare_tracks(a, b, tol=tol, dimension="yield", unit="g/m²")
        status = "✅" if r["verdict"] == expected else "❌"
        print(f"  {status} mech={a} heur={b} tol={tol} → {r['verdict']} "
              f"(rel={r['relative_divergence']:.3f}, conf_mult={r['confidence_multiplier']})")
        assert r["verdict"] == expected, f"expected {expected}, got {r['verdict']}"
    # 汇总统计
    comparisons = [
        compare_tracks(300, 295), compare_tracks(300, 260),
        compare_tracks(300, 200), compare_tracks(300, 100),
    ]
    summary = summarize_divergences(comparisons)
    print(f"\n汇总: {summary}")
    assert summary["n"] == 4
    print("全部自测通过")
