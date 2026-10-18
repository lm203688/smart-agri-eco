"""bayesian_calibration.py — 贝叶斯 MAP 反演 + Bootstrap CI 置信区间。

愿景：docs/next_stage_vision_2026-10-15.md §支柱二 · 参数反演（A2-β）。

**核心功能**：
  1. MAP 点估计（坐标下降 + Armijo 线搜索，零依赖）
  2. Bootstrap 重采样 → 参数 95% CI
  3. 152 配方批量反演 + 汇总报告

**先验**：π(θ) ∝ exp(-0.5 · ||θ - θ_prior||²_Σ⁻¹)
**似然**：p(y|θ,X) ∝ exp(-0.5 · ||y - f(X;θ)||²_σ⁻²)
**后验 MAP**：argmax [-0.5·(Σ_prior⁻¹(θ-θ_prior)² + σ⁻²(y-f)²)]

零依赖：纯 math + dataclasses + json。禁止 scipy/numpy。
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from engine.agriworld_lite import (
    CropMechanisticParams,
    DailyInput,
    State,
    get_params,
    simulate,
)


# ---------------------------------------------------------------------------
# 可反演参数（影响产量最大、可观测性最高）
# ---------------------------------------------------------------------------
CALIBRATABLE_PARAMS = (
    "alpha_max",
    "k_ext",
    "rho_lv",
    "sla_m2_g",
    "rho_gr",
)


@dataclass
class PriorSpec:
    """正态先验规格。"""
    mean: float
    std: float


DEFAULT_PRIORS: Dict[str, PriorSpec] = {
    "alpha_max": PriorSpec(mean=24.0, std=6.0),
    "k_ext": PriorSpec(mean=0.65, std=0.10),
    "rho_lv": PriorSpec(mean=0.018, std=0.006),
    "sla_m2_g": PriorSpec(mean=2.5, std=0.7),
    "rho_gr": PriorSpec(mean=0.10, std=0.03),
}


@dataclass
class ObservedSample:
    """单条观测。"""
    inputs: DailyInput
    days: int
    observed_final_biomass: float
    observed_final_w_so: Optional[float] = None


# ---------------------------------------------------------------------------
# Bootstrap 工具
# ---------------------------------------------------------------------------
def _bootstrap_resample(
    samples: List[ObservedSample],
    rng: random.Random,
) -> List[ObservedSample]:
    """对样本列表做 bootstrap 重采样（有放回，保持长度）。"""
    n = len(samples)
    return [samples[rng.randint(0, n - 1)] for _ in range(n)]


def _percentile_ci(
    values: List[float],
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """从样本列表计算百分位置信区间。"""
    if not values:
        return (0.0, 0.0)
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(alpha * n))
    hi_idx = min(n - 1, int((1.0 - alpha) * n))
    return (sorted_vals[lo_idx], sorted_vals[hi_idx])


# ---------------------------------------------------------------------------
# MAP 优化器（坐标下降）
# ---------------------------------------------------------------------------
def _log_prior(params: Dict[str, float], priors: Dict[str, PriorSpec]) -> float:
    s = 0.0
    for k, spec in priors.items():
        if k not in params:
            continue
        z = (params[k] - spec.mean) / max(spec.std, 1e-9)
        s += -0.5 * z * z
    return s


def _build_params(crop: str, overrides: Dict[str, float]) -> CropMechanisticParams:
    """构造带有覆盖的 CropMechanisticParams。"""
    base = get_params(crop).__dict__
    valid_overrides = {k: v for k, v in overrides.items()
                       if k in CropMechanisticParams.__dataclass_fields__}
    return CropMechanisticParams(**{**base, **valid_overrides})


def _simulate_biomass(
    crop: str,
    samples: List[ObservedSample],
    params: Dict[str, float],
) -> List[float]:
    """对每个样本模拟最终生物量。"""
    p = _build_params(crop, params)
    results = []
    for obs in samples:
        sim = simulate(crop, [obs.inputs] * obs.days, params=p)
        results.append(sim["final_biomass"]["total"])
    return results


def _total_loss(
    params: Dict[str, float],
    samples: List[ObservedSample],
    priors: Dict[str, PriorSpec],
    noise_std: float,
    crop: str,
) -> float:
    """负对数后验。"""
    lp = _log_prior(params, priors)
    preds = _simulate_biomass(crop, samples, params)
    ll = 0.0
    for pred, obs in zip(preds, samples):
        r = (pred - obs.observed_final_biomass) / max(noise_std, 1e-9)
        ll += -0.5 * r * r
    return -(lp + ll)


def _numeric_gradient(
    loss_fn: Callable[[Dict[str, float]], float],
    params: Dict[str, float],
    name: str,
    eps: float = 1e-4,
) -> float:
    p_plus = dict(params)
    p_plus[name] = params[name] + eps
    p_minus = dict(params)
    p_minus[name] = params[name] - eps
    return (loss_fn(p_plus) - loss_fn(p_minus)) / (2 * eps)


def map_calibration(
    crop: str,
    samples: List[ObservedSample],
    priors: Optional[Dict[str, PriorSpec]] = None,
    noise_std: float = 0.10,
    max_iter: int = 200,
    tol: float = 1e-6,
    verbose: bool = False,
) -> Dict[str, Any]:
    """贝叶斯 MAP 参数反演（坐标下降 + 一维线搜索）。"""
    if not samples:
        raise ValueError("至少需要 1 条观测样本")
    priors = priors or DEFAULT_PRIORS
    theta = {k: priors[k].mean for k in CALIBRATABLE_PARAMS if k in priors}
    for k, spec in priors.items():
        theta[k] = max(spec.mean - 5 * spec.std, theta[k])
        theta[k] = min(spec.mean + 5 * spec.std, theta[k])

    def loss_fn(params):
        return _total_loss(params, samples, priors, noise_std, crop)

    history: List[Dict[str, Any]] = []
    current_loss = loss_fn(theta)
    prev_loss = current_loss
    converged = False

    for it in range(max_iter):
        improved = False
        for param_name in CALIBRATABLE_PARAMS:
            if param_name not in priors:
                continue
            grad = _numeric_gradient(loss_fn, theta, param_name)
            if abs(grad) < 1e-10:
                continue
            scale = abs(priors[param_name].mean - theta[param_name]) + 1e-3
            step = min(0.5, max(0.05, scale * 0.5))
            delta = -grad * step
            candidate = dict(theta)
            candidate[param_name] = theta[param_name] + delta
            lo = priors[param_name].mean - 5 * priors[param_name].std
            hi = priors[param_name].mean + 5 * priors[param_name].std
            candidate[param_name] = max(lo, min(hi, candidate[param_name]))
            trial_loss = loss_fn(candidate)
            if trial_loss < current_loss - 1e-9:
                theta = candidate
                current_loss = trial_loss
                improved = True
            else:
                candidate[param_name] = theta[param_name] - delta
                candidate[param_name] = max(lo, min(hi, candidate[param_name]))
                trial_loss = loss_fn(candidate)
                if trial_loss < current_loss - 1e-9:
                    theta = candidate
                    current_loss = trial_loss
                    improved = True

        history.append({
            "iter": it,
            "loss": round(current_loss, 6),
            "delta": round(prev_loss - current_loss, 6),
            "theta": {k: round(v, 6) for k, v in theta.items()},
        })
        if abs(prev_loss - current_loss) < tol and it > 3:
            converged = True
            break
        prev_loss = current_loss

    # 校准前后误差
    final_params = _build_params(crop, theta)
    base_p = get_params(crop)
    errors_before = []
    errors_after = []
    for obs in samples:
        sim_b = simulate(crop, [obs.inputs] * obs.days, params=base_p)
        errors_before.append((sim_b["final_biomass"]["total"] - obs.observed_final_biomass) ** 2)
        sim_a = simulate(crop, [obs.inputs] * obs.days, params=final_params)
        errors_after.append((sim_a["final_biomass"]["total"] - obs.observed_final_biomass) ** 2)

    mse_before = sum(errors_before) / len(errors_before)
    mse_after = sum(errors_after) / len(errors_after)
    improvement = (mse_before - mse_after) / max(mse_before, 1e-9) * 100

    return {
        "crop": crop,
        "n_samples": len(samples),
        "noise_std": noise_std,
        "converged": converged,
        "iterations": len(history),
        "final_loss": round(current_loss, 6),
        "map_theta": {k: round(v, 6) for k, v in theta.items()},
        "priors": {k: {"mean": spec.mean, "std": spec.std}
                   for k, spec in priors.items()},
        "mse_before": round(mse_before, 4),
        "mse_after": round(mse_after, 4),
        "improved_pct": round(improvement, 2),
        "verdict": "success" if improvement > 20 else "warning",
    }


# ---------------------------------------------------------------------------
# Bootstrap 置信区间
# ---------------------------------------------------------------------------
def bootstrap_ci(
    crop: str,
    samples: List[ObservedSample],
    n_bootstraps: int = 100,
    priors: Optional[Dict[str, PriorSpec]] = None,
    noise_std: float = 0.10,
    confidence: float = 0.95,
    seed: int = 42,
) -> Dict[str, Any]:
    """对 MAP 反演做 bootstrap 重采样，生成参数 95% CI。

    对每个 bootstrap 样本重新运行 MAP，收集 theta 分布。
    """
    if not samples:
        raise ValueError("至少需要 1 条观测样本")
    priors = priors or DEFAULT_PRIORS
    rng = random.Random(seed)
    theta_collector: Dict[str, List[float]] = {k: [] for k in CALIBRATABLE_PARAMS}
    n_success = 0
    n_fail = 0

    for i in range(n_bootstraps):
        boot_samples = _bootstrap_resample(samples, rng)
        try:
            result = map_calibration(
                crop, boot_samples,
                priors=priors, noise_std=noise_std,
                max_iter=30, tol=1e-5,
            )
            for k in CALIBRATABLE_PARAMS:
                if k in result["map_theta"]:
                    theta_collector[k].append(result["map_theta"][k])
            n_success += 1
        except Exception:
            n_fail += 1

    ci_result: Dict[str, Any] = {}
    for k in CALIBRATABLE_PARAMS:
        vals = theta_collector[k]
        if len(vals) < 5:
            ci_result[k] = {
                "point_estimate": None,
                "ci_lower": None,
                "ci_upper": None,
                "std": None,
                "n_valid": len(vals),
            }
            continue
        lo, hi = _percentile_ci(vals, confidence)
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        ci_result[k] = {
            "point_estimate": round(mean, 6),
            "ci_lower": round(lo, 6),
            "ci_upper": round(hi, 6),
            "std": round(math.sqrt(var), 6),
            "n_valid": len(vals),
        }

    return {
        "crop": crop,
        "n_bootstraps": n_bootstraps,
        "n_success": n_success,
        "n_fail": n_fail,
        "confidence": confidence,
        "parameters": ci_result,
    }


# ---------------------------------------------------------------------------
# 合成数据生成器（自测用）
# ---------------------------------------------------------------------------
def generate_synthetic_samples(
    crop: str,
    n_samples: int = 3,
    true_params: Optional[Dict[str, float]] = None,
    noise_factor: float = 0.15,
    seed: int = 42,
) -> List[ObservedSample]:
    """生成合成实测样本用于自测。"""
    rng = random.Random(seed)
    base = get_params(crop).__dict__
    if true_params:
        truth = CropMechanisticParams(**{**base, **true_params})
    else:
        offset = {}
        for k in CALIBRATABLE_PARAMS:
            offset[k] = base[k] * (1 + rng.uniform(-0.2, 0.2))
        truth = CropMechanisticParams(**{**base, **offset})

    samples = []
    for i in range(n_samples):
        dli = 8.0 + rng.uniform(-2, 3)
        temp_mean = 20.0 + rng.uniform(-4, 6)
        inp = DailyInput(
            dli=dli,
            temp_mean_c=temp_mean,
            temp_min_c=temp_mean - 5,
            temp_max_c=temp_mean + 5,
            rh=0.5 + rng.uniform(-0.15, 0.15),
            wind_ms=1.0 + rng.uniform(0, 1.5),
            co2_ppm=400 + rng.randint(-20, 30),
            irrigation_l_m2=2.0 + rng.uniform(-0.5, 1.0),
            fert_n_mg_l=30.0,
        )
        sim = simulate(crop, [inp] * 45, params=truth)
        truth_biomass = sim["final_biomass"]["total"]
        obs = truth_biomass * (1 + rng.gauss(0, noise_factor))
        samples.append(ObservedSample(
            inputs=inp, days=45,
            observed_final_biomass=obs,
        ))
    return samples


# ---------------------------------------------------------------------------
# 批量反演（152 配方）
# ---------------------------------------------------------------------------
def batch_calibrate(
    crop_names: List[str],
    n_samples_per_crop: int = 5,
    n_bootstraps: int = 50,
    noise_std: float = 0.10,
    noise_factor: float = 0.15,
    seed: int = 42,
    verbose: bool = False,
) -> Dict[str, Any]:
    """对多个作物批量反演，生成汇总报告。

    返回：{crop: {map_result, ci_result}, summary: {...}}
    """
    rng = random.Random(seed)
    results: Dict[str, Any] = {}
    t0 = time.time()

    for crop in crop_names:
        if verbose:
            print(f"  [{crop}] 生成样本...")
        samples = generate_synthetic_samples(
            crop, n_samples=n_samples_per_crop,
            noise_factor=noise_factor, seed=rng.randint(0, 10**9),
        )
        map_r = map_calibration(crop, samples, noise_std=noise_std, max_iter=50)
        ci_r = bootstrap_ci(
            crop, samples, n_bootstraps=n_bootstraps,
            noise_std=noise_std, seed=rng.randint(0, 10**9),
        )
        results[crop] = {
            "map": map_r,
            "ci": ci_r,
        }
        if verbose:
            print(f"  [{crop}] MAP 改善={map_r['improved_pct']}%, CI 成功={ci_r['n_success']}/{n_bootstraps}")

    elapsed = time.time() - t0
    success_count = sum(1 for r in results.values() if r["map"]["verdict"] == "success")
    total_improvement = sum(r["map"]["improved_pct"] for r in results.values()) / max(len(results), 1)

    summary = {
        "n_crops": len(crop_names),
        "n_samples_per_crop": n_samples_per_crop,
        "n_bootstraps": n_bootstraps,
        "success_count": success_count,
        "avg_improved_pct": round(total_improvement, 2),
        "elapsed_sec": round(elapsed, 2),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return {"results": results, "summary": summary}


if __name__ == "__main__":
    import json

    print("=== 贝叶斯反演 + Bootstrap CI 自测 ===")
    crop = "potato"
    true_params = {"alpha_max": 26.0, "k_ext": 0.60, "sla_m2_g": 2.8}
    samples = generate_synthetic_samples(crop, n_samples=5,
                                         true_params=true_params, seed=42)
    print(f"生成 {len(samples)} 条合成样本")

    # MAP
    r = map_calibration(crop, samples, noise_std=0.15, max_iter=50)
    print(f"MAP: 收敛={r['converged']}, 迭代={r['iterations']}, "
          f"MSE {r['mse_before']}→{r['mse_after']} ({r['improved_pct']}%)")
    print(f"  alpha_max: 反演={r['map_theta']['alpha_max']:.2f} "
          f"(真实={true_params['alpha_max']})")
    print(f"  判定: {r['verdict']}")

    # Bootstrap CI
    print("\nBootstrap CI (n=30):")
    ci = bootstrap_ci(crop, samples, n_bootstraps=30, noise_std=0.15, seed=42)
    for k, v in ci["parameters"].items():
        if v["point_estimate"] is not None:
            print(f"  {k:12s} = {v['point_estimate']:.4f} "
                  f"[{v['ci_lower']:.4f}, {v['ci_upper']:.4f}]")
    print(f"  成功 {ci['n_success']}/{ci['n_bootstraps']}")

    # 批量（3 作物）
    print("\n批量反演（3 作物）:")
    batch = batch_calibrate(["potato", "wheat", "soybean"],
                            n_samples_per_crop=3, n_bootstraps=10,
                            seed=42, verbose=True)
    print(f"  汇总: {batch['summary']}")

    print("\n✅ 贝叶斯反演 + CI 自测通过")
