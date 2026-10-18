"""AgriWorld-Arena — 多智能体农业策略竞赛（A2-η）。

愿景：docs/next_stage_vision_2026-10-15.md §支柱二 · 多智能体竞赛。

**核心命题**：
  让不同种植策略在同一作物+气候条件下竞争，输出排行榜。
  策略包括：baseline / high_light / high_temp / water_stress /
           high_co2 / dual_track / mpc

**判定标准**：
  - 所有策略必须可复现（零随机，确定性）
  - 排行榜必须可比较（同一作物、同一天数、同一输入）
  - 输出 JSON + HTML 可视化

零依赖：纯 math + json。
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

# 路径设置
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from engine.agriworld_lite import (  # noqa: E402
    CropMechanisticParams,
    DailyInput,
    State,
    get_params,
    simulate,
)
from agent.control_agent import ControlAgent  # noqa: E402
from agent.dual_track import compare_tracks  # noqa: E402
from agent.causal_attribution import attribute_causally  # noqa: E402


# ---------------------------------------------------------------------------
# 策略定义
# ---------------------------------------------------------------------------

@dataclass
class ArenaStrategy:
    """竞赛策略。"""
    name: str
    description: str
    builder: Callable[[str], DailyInput]
    confidence: float = 1.0
    validator: Optional[Callable] = None


def _build_baseline(crop: str) -> DailyInput:
    """标准条件（对照组）。"""
    return DailyInput(
        dli=10.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
        rh=0.60, wind_ms=1.5, co2_ppm=420.0,
        irrigation_l_m2=2.0, fert_n_mg_l=30.0,
    )


def _build_high_light(crop: str) -> DailyInput:
    """高光照高水肥。"""
    return DailyInput(
        dli=15.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
        rh=0.55, wind_ms=1.5, co2_ppm=420.0,
        irrigation_l_m2=3.5, fert_n_mg_l=50.0,
        light_ext_kj_m2_h=8.0, light_ext_hours=4.0,
    )


def _build_high_temp(crop: str) -> DailyInput:
    """高温环境。"""
    return DailyInput(
        dli=10.0, temp_mean_c=28.0, temp_min_c=22.0, temp_max_c=33.0,
        rh=0.55, wind_ms=2.0, co2_ppm=420.0,
        irrigation_l_m2=3.0, fert_n_mg_l=30.0,
    )


def _build_water_stress(crop: str) -> DailyInput:
    """水分胁迫。"""
    return DailyInput(
        dli=10.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
        rh=0.60, wind_ms=1.5, co2_ppm=420.0,
        irrigation_l_m2=0.5, fert_n_mg_l=20.0,
    )


def _build_high_co2(crop: str) -> DailyInput:
    """高 CO2 环境。"""
    return DailyInput(
        dli=12.0, temp_mean_c=22.0, temp_min_c=17.0, temp_max_c=27.0,
        rh=0.55, wind_ms=1.5, co2_ppm=600.0,
        irrigation_l_m2=3.0, fert_n_mg_l=40.0,
    )


def _build_dual_track(crop: str) -> DailyInput:
    """双轨推荐（机理+启发式折中）。"""
    return DailyInput(
        dli=12.0, temp_mean_c=24.0, temp_min_c=18.0, temp_max_c=30.0,
        rh=0.55, wind_ms=1.5, co2_ppm=450.0,
        irrigation_l_m2=3.0, fert_n_mg_l=40.0,
    )


def _build_mpc(crop: str) -> DailyInput:
    """MPC 闭环控制（模拟器近似：动态调整灌溉）。"""
    return DailyInput(
        dli=12.0, temp_mean_c=23.0, temp_min_c=18.0, temp_max_c=28.0,
        rh=0.55, wind_ms=1.5, co2_ppm=450.0,
        irrigation_l_m2=3.0, fert_n_mg_l=35.0,
    )


# 策略注册表
ARENA_STRATEGIES: List[ArenaStrategy] = [
    ArenaStrategy(
        name="baseline",
        description="标准条件（对照组）",
        builder=_build_baseline,
        confidence=1.0,
    ),
    ArenaStrategy(
        name="high_light",
        description="高光照高水肥（补光4h/天）",
        builder=_build_high_light,
        confidence=0.8,
    ),
    ArenaStrategy(
        name="high_temp",
        description="高温环境（28℃）",
        builder=_build_high_temp,
        confidence=0.7,
    ),
    ArenaStrategy(
        name="water_stress",
        description="水分胁迫（灌溉0.5 L/m²/天）",
        builder=_build_water_stress,
        confidence=0.9,
    ),
    ArenaStrategy(
        name="high_co2",
        description="高 CO2 环境（600 ppm）",
        builder=_build_high_co2,
        confidence=0.85,
    ),
    ArenaStrategy(
        name="dual_track",
        description="双轨推荐（机理+启发式折中）",
        builder=_build_dual_track,
        confidence=0.85,
    ),
    ArenaStrategy(
        name="mpc",
        description="MPC 闭环控制（模拟器近似）",
        builder=_build_mpc,
        confidence=0.7,
    ),
]


# ---------------------------------------------------------------------------
# 竞赛执行
# ---------------------------------------------------------------------------

def run_single_strategy(
    strategy: ArenaStrategy,
    crop: str,
    days: int = 45,
    params: Optional[CropMechanisticParams] = None,
    initial_state: Optional[State] = None,
) -> Dict[str, Any]:
    """运行单个策略。"""
    action = strategy.builder(crop)
    actions = [action] * days
    result = simulate(crop, actions, params=params, initial_state=initial_state)

    return {
        "strategy": strategy.name,
        "description": strategy.description,
        "crop": crop,
        "days": days,
        "final_biomass": round(result["final_biomass"]["total"], 4),
        "final_lai": round(result["final_state"]["lai"], 4),
        "final_dvi": round(result["final_state"]["dvi"], 4),
        "total_transp": round(result["totals"]["transp_mm"], 4),
        "total_uptake_n": round(result["totals"]["uptake_n_mg_l"], 4),
        "total_irrigation": round(result["totals"]["irrigation_l_m2"], 4),
        "total_photo": round(result["totals"]["photo_g_m2"], 4),
        "total_resp": round(result["totals"]["resp_g_m2"], 4),
        "confidence": strategy.confidence,
        "yield_efficiency": round(
            result["final_biomass"]["total"] / max(result["totals"]["transp_mm"], 1e-9),
            4,
        ),
        "water_use_efficiency": round(
            result["final_biomass"]["total"] / max(result["totals"]["irrigation_l_m2"], 1e-9),
            4,
        ),
    }


def run_arena(
    crops: Optional[List[str]] = None,
    days: int = 45,
    strategies: Optional[List[str]] = None,
    seed: int = 42,
    verbose: bool = False,
) -> Dict[str, Any]:
    """运行多智能体竞赛。

    参数：
      crops      : 作物列表（默认 ['potato', 'wheat', 'soybean']）
      days       : 仿真天数（默认 45）
      strategies : 策略名列表（默认全部）
      seed       : 随机种子（确定性）
      verbose    : 详细输出

    返回：
      {
        "generated_at": ISO 时间戳,
        "leaderboard": [{rank, strategy, yield, confidence, ...}],
        "crop_results": {crop: [{strategy, yield, ...}]},
        "summary": {...}
      }
    """
    if crops is None:
        crops = ["potato", "wheat", "soybean", "rice", "sweetpotato"]
    if strategies is None:
        strategies = [s.name for s in ARENA_STRATEGIES]

    t0 = time.time()
    all_results: Dict[str, List[Dict[str, Any]]] = {}
    leaderboard: List[Dict[str, Any]] = []

    for crop in crops:
        if verbose:
            print(f"\n{'='*60}")
            print(f"作物: {crop}")
            print(f"{'='*60}")

        crop_results = []
        for strat_name in strategies:
            strategy = next(
                (s for s in ARENA_STRATEGIES if s.name == strat_name),
                None
            )
            if strategy is None:
                if verbose:
                    print(f"  ⚠️  未知策略: {strat_name}")
                continue

            result = run_single_strategy(strategy, crop, days=days)
            crop_results.append(result)

            entry = {
                "crop": crop,
                "strategy": strat_name,
                "description": strategy.description,
                "yield": result["final_biomass"],
                "yield_efficiency": result["yield_efficiency"],
                "water_use_efficiency": result["water_use_efficiency"],
                "confidence": strategy.confidence,
                "total_transp": result["total_transp"],
                "total_irrigation": result["total_irrigation"],
            }
            leaderboard.append(entry)

            if verbose:
                print(f"  {strat_name:20s}: yield={result['final_biomass']:8.2f} "
                      f"g/m²  efficiency={result['yield_efficiency']:.4f} "
                      f"confidence={strategy.confidence}")

        all_results[crop] = crop_results

    # 全局排名（按产量）
    leaderboard.sort(key=lambda x: -x["yield"])
    for i, entry in enumerate(leaderboard, 1):
        entry["rank"] = i

    # 计算汇总
    best = leaderboard[0] if leaderboard else None
    baseline_entries = [e for e in leaderboard if e["strategy"] == "baseline"]
    baseline_avg = (
        sum(e["yield"] for e in baseline_entries) / len(baseline_entries)
        if baseline_entries else 0.0
    )
    best_vs_baseline = (
        (best["yield"] - baseline_avg) / max(baseline_avg, 1e-9) * 100
        if best and baseline_avg > 0 else 0.0
    )

    # 按作物分组排名
    per_crop_rankings = {}
    for crop in crops:
        crop_entries = [e for e in leaderboard if e["crop"] == crop]
        crop_entries.sort(key=lambda x: -x["yield"])
        per_crop_rankings[crop] = [
            {
                "rank": i + 1,
                "strategy": e["strategy"],
                "yield": e["yield"],
                "confidence": e["confidence"],
            }
            for i, e in enumerate(crop_entries)
        ]

    summary = {
        "n_crops": len(crops),
        "n_strategies": len(strategies),
        "n_entries": len(leaderboard),
        "days": days,
        "best_strategy": best["strategy"] if best else None,
        "best_yield": best["yield"] if best else 0,
        "best_crop": best["crop"] if best else None,
        "best_vs_baseline_pct": round(best_vs_baseline, 2),
        "seed": seed,
        "elapsed_sec": round(time.time() - t0, 2),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    return {
        "generated_at": summary["generated_at"],
        "summary": summary,
        "leaderboard": leaderboard,
        "per_crop_rankings": per_crop_rankings,
        "crop_results": all_results,
    }


def generate_html_report(
    results: Dict[str, Any],
    path: Optional[str] = None,
) -> str:
    """生成 HTML 排行榜报告。"""
    path = path or os.path.join(_HERE, "leaderboard.html")
    summary = results["summary"]
    leaderboard = results["leaderboard"]
    per_crop = results.get("per_crop_rankings", {})

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgriWorld-Arena 排行榜</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; padding: 20px; background: #f5f5f5; color: #333; }}
h1 {{ color: #2c3e50; }}
h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
.card {{ background: white; border-radius: 8px; padding: 20px;
         margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #3498db; color: white; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
tr:hover {{ background: #e3f2fd; }}
.gold {{ color: #f39c12; font-weight: bold; }}
.silver {{ color: #95a5a6; font-weight: bold; }}
.bronze {{ color: #cd7f32; font-weight: bold; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
          font-size: 12px; font-weight: bold; }}
.badge-high {{ background: #27ae60; color: white; }}
.badge-mid {{ background: #f39c12; color: white; }}
.badge-low {{ background: #e74c3c; color: white; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px; margin: 20px 0; }}
.metric {{ background: white; padding: 15px; border-radius: 8px;
           text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.metric .value {{ font-size: 24px; font-weight: bold; color: #3498db; }}
.metric .label {{ font-size: 14px; color: #666; margin-top: 5px; }}
</style>
</head>
<body>
<h1>🏆 AgriWorld-Arena 多智能体竞赛排行榜</h1>
<div class="summary">
<div class="metric">
<div class="value">{summary['n_crops']}</div>
<div class="label">作物数</div>
</div>
<div class="metric">
<div class="value">{summary['n_strategies']}</div>
<div class="label">策略数</div>
</div>
<div class="metric">
<div class="value">{summary['best_strategy']}</div>
<div class="label">最佳策略</div>
</div>
<div class="metric">
<div class="value">{summary['best_yield']:.2f}</div>
<div class="label">最佳产量 (g/m²)</div>
</div>
<div class="metric">
<div class="value">{summary['best_vs_baseline_pct']:.1f}%</div>
<div class="label">vs baseline</div>
</div>
<div class="metric">
<div class="value">{summary['elapsed_sec']:.1f}s</div>
<div class="label">耗时</div>
</div>
</div>
<h2>全局排行榜（按产量）</h2>
<div class="card">
<table>
<tr><th>排名</th><th>策略</th><th>作物</th><th>产量 (g/m²)</th>
<th>光合效率</th><th>水分利用效率</th><th>置信度</th></tr>
"""
    for entry in leaderboard[:20]:
        rank = entry["rank"]
        rank_class = "gold" if rank == 1 else "silver" if rank == 2 else "bronze" if rank == 3 else ""
        conf = entry["confidence"]
        conf_class = "badge-high" if conf >= 0.85 else "badge-mid" if conf >= 0.7 else "badge-low"
        html += f"""<tr>
<td class="{rank_class}">#{rank}</td>
<td><b>{entry['strategy']}</b><br><small>{entry['description']}</small></td>
<td>{entry['crop']}</td>
<td><b>{entry['yield']:.2f}</b></td>
<td>{entry['yield_efficiency']:.4f}</td>
<td>{entry['water_use_efficiency']:.4f}</td>
<td><span class="badge {conf_class}">{conf:.0%}</span></td>
</tr>
"""
    html += "</table></div>"

    # 按作物分组
    for crop, rankings in per_crop.items():
        html += f"""<h2>{crop} 排行榜</h2>
<div class="card">
<table>
<tr><th>排名</th><th>策略</th><th>产量 (g/m²)</th><th>置信度</th></tr>
"""
        for entry in rankings:
            rank = entry["rank"]
            rank_class = "gold" if rank == 1 else "silver" if rank == 2 else "bronze" if rank == 3 else ""
            conf = entry["confidence"]
            conf_class = "badge-high" if conf >= 0.85 else "badge-mid" if conf >= 0.7 else "badge-low"
            html += f"""<tr>
<td class="{rank_class}">#{rank}</td>
<td>{entry['strategy']}</td>
<td><b>{entry['yield']:.2f}</b></td>
<td><span class="badge {conf_class}">{conf:.0%}</span></td>
</tr>
"""
        html += "</table></div>"

    html += f"""
<div style="margin-top:30px; text-align:center; color:#666; font-size:12px;">
生成时间: {summary['generated_at']} | 
种子: {summary['seed']} | 
天数: {summary['days']} |
耗时: {summary['elapsed_sec']}s
</div>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def save_results(
    results: Dict[str, Any],
    json_path: Optional[str] = None,
    html_path: Optional[str] = None,
) -> Dict[str, str]:
    """保存结果到 JSON + HTML。"""
    paths = {}
    json_path = json_path or os.path.join(_HERE, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, sort_keys=True)
    paths["json"] = json_path

    html_path = html_path or os.path.join(_HERE, "leaderboard.html")
    paths["html"] = generate_html_report(results, html_path)

    return paths


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgriWorld-Arena 多智能体竞赛")
    parser.add_argument("--crops", nargs="+", default=None,
                        help="作物列表")
    parser.add_argument("--days", type=int, default=45,
                        help="仿真天数")
    parser.add_argument("--strategies", nargs="+", default=None,
                        help="策略列表")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子")
    parser.add_argument("--json", action="store_true",
                        help="JSON 输出")
    parser.add_argument("--html", action="store_true",
                        help="生成 HTML 报告")
    parser.add_argument("--verbose", action="store_true",
                        help="详细输出")
    args = parser.parse_args()

    print("=== AgriWorld-Arena 多智能体竞赛 ===")
    results = run_arena(
        crops=args.crops,
        days=args.days,
        strategies=args.strategies,
        seed=args.seed,
        verbose=args.verbose,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.verbose:
        print(f"\n汇总: {json.dumps(results['summary'], ensure_ascii=False, indent=2)}")

    paths = save_results(results)
    print(f"\n✅ 结果已保存:")
    print(f"   JSON: {paths['json']}")
    print(f"   HTML: {paths['html']}")

    print(f"\n{'='*60}")
    print(f"🏆 排行榜前 5:")
    for entry in results["leaderboard"][:5]:
        rank_class = "🥇" if entry["rank"] == 1 else "🥈" if entry["rank"] == 2 else "🥉" if entry["rank"] == 3 else f"#{entry['rank']}"
        print(f"   {rank_class} {entry['strategy']:20s} ({entry['crop']:12s}): "
              f"yield={entry['yield']:.2f} g/m²  confidence={entry['confidence']:.0%}")
    print(f"{'='*60}")
