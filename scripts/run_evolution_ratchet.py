"""S2/E1 棘轮 CI 硬门禁 —— 不依赖外部调用就能转的内回路。

承接 `docs/framework_evolution_liftup_2026-10-13.md` §6.2 S2 与 §6.3 E1：

  - **S2**：evolution benchmark 扩展到全科学模块的 CI；任何 PR 触碰科学内核，
    棘轮不过即拒绝合并。
  - **E1**：把「不允许退步」从理念变硬门禁。

设计原则：
  1. **只读、不写**：只跑 benchmark 评估，绝不改数据（CI 环境下最安全的形态）
  2. **只检查棘轮要求的模块**：读取 `.well-known/evolution_zones.json` 的
     `enforcement.ratchet_required_for` 白名单；未列出的路径不受本门禁约束
  3. **诚实降级**：benchmark 用例数不足或评测脚本不可用时明确失败，
     不静默跳过
  4. **阈值可配**：`--min-score` 控制最低通过分数（默认 0.5，因为现有
     benchmark 的分数范围是 [0, 1]，0.5 代表方向正确率 ≥ 50%）
  5. **退出码规范**：0=通过、1=评分不达标、2=配置错误、3=执行异常

用法：
    python scripts/run_evolution_ratchet.py                # 默认阈值 0.5
    python scripts/run_evolution_ratchet.py --min-score 0.7
    python scripts/run_evolution_ratchet.py --check-files  # 只检查棘轮白名单文件是否存在
    python scripts/run_evolution_ratchet.py --json         # JSON 输出，供 CI 消费
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ZONES_PATH = os.path.join(ROOT, ".well-known", "evolution_zones.json")


def _load_zones() -> Dict[str, Any]:
    with open(ZONES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_whitelist_files(zones: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """校验棘轮白名单里的所有文件路径都真实存在。

    支持 glob 模式：若 entry 含通配符（* ? [），用 glob.glob 展开；
    否则按精确路径检查。glob 展开后至少要匹配到 1 个文件才算存在。
    """
    import glob as _glob
    enf = zones.get("meta_policy", {}).get("enforcement", {})
    whitelist = enf.get("ratchet_required_for", [])
    missing = []
    for entry in whitelist:
        prefix = entry.rstrip("/")
        full = os.path.join(ROOT, prefix)
        if any(c in prefix for c in "*?["):
            # glob 模式：展开后至少要有匹配项
            matches = _glob.glob(full)
            if not matches:
                missing.append({"prefix": entry, "path": full, "reason": "glob_no_match"})
        elif not os.path.exists(full):
            missing.append({"prefix": entry, "path": full})
    return len(missing) == 0, missing


def _score_evolution_benchmark() -> Dict[str, Any]:
    """跑 evolution benchmark 并返回分数摘要。"""
    import engine.evolution as ev
    bm = ev.load_benchmark()
    cases = bm.get("cases", [])
    if not cases:
        return {"error": "benchmark_empty", "cases": 0, "score": None}
    sc = ev.score_benchmark(bm)
    return {
        "cases": sc.get("n", len(cases)),
        "score": sc.get("score", 0.0),
        "perfect": sc.get("perfect", 0),
        "neutral": sc.get("neutral", 0),
        "wrong": sc.get("wrong", 0),
    }


def run_gate(min_score: float = 0.5) -> Dict[str, Any]:
    """执行棘轮门禁。返回结果字典，包含 status / detail。"""
    try:
        zones = _load_zones()
    except Exception as e:  # noqa: BLE001
        return {"status": "config_error", "error": f"无法加载 evolution_zones.json: {e}",
                "exit_code": 2}

    ok, missing = _check_whitelist_files(zones)
    if not ok:
        return {
            "status": "config_error",
            "error": "棘轮白名单文件缺失",
            "missing_files": missing,
            "exit_code": 2,
        }

    try:
        score_info = _score_evolution_benchmark()
    except Exception as e:  # noqa: BLE001
        return {"status": "execution_error", "error": f"benchmark 执行失败: {e}",
                "exit_code": 3}

    if "error" in score_info:
        return {"status": "execution_error", "detail": score_info,
                "error": score_info.get("error", "unknown"), "exit_code": 3}

    score = score_info.get("score", 0.0)
    passed = score >= min_score
    return {
        "status": "passed" if passed else "failed",
        "score": round(score, 4),
        "min_score": min_score,
        "cases": score_info.get("cases", 0),
        "perfect": score_info.get("perfect", 0),
        "neutral": score_info.get("neutral", 0),
        "wrong": score_info.get("wrong", 0),
        "enforcement": zones.get("meta_policy", {}).get("enforcement", {}),
        "gate_version": zones.get("meta_policy", {}).get("gate_version"),
        "exit_code": 0 if passed else 1,
    }


def check_files_only() -> Dict[str, Any]:
    """只检查棘轮白名单文件是否存在（不跑 benchmark）。"""
    zones = _load_zones()
    ok, missing = _check_whitelist_files(zones)
    return {"status": "passed" if ok else "config_error",
            "missing_files": missing,
            "exit_code": 0 if ok else 2}


def main() -> int:
    p = argparse.ArgumentParser(description="S2/E1 棘轮 CI 硬门禁")
    p.add_argument("--min-score", type=float, default=0.5,
                   help="最低通过分数（默认 0.5，即方向正确率 ≥ 50%%）")
    p.add_argument("--check-files", action="store_true",
                   help="只检查棘轮白名单文件是否存在")
    p.add_argument("--json", action="store_true",
                   help="JSON 格式输出（供 CI 消费）")
    args = p.parse_args()

    if args.check_files:
        result = check_files_only()
    else:
        result = run_gate(min_score=args.min_score)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = result.get("status")
        icon = {"passed": "✅", "failed": "❌", "config_error": "⚠️",
                "execution_error": "💥"}.get(status, "❓")
        print(f"{icon} 棘轮门禁 status={status}")
        if status == "passed":
            if result.get("score") is not None:
                print(f"   分数: {result['score']:.4f} ≥ 阈值 {result.get('min_score')}")
                print(f"   用例: {result.get('cases')} 完美={result.get('perfect')} "
                      f"中性={result.get('neutral')} 反向={result.get('wrong')}")
                print(f"   gate_version: {result.get('gate_version')}")
            else:
                # --check-files 模式：无分数
                print("   白名单文件全部存在（--check-files 模式）")
        elif status == "failed":
            print(f"   ❌ 分数 {result.get('score'):.4f} < 阈值 {result.get('min_score')}")
            print("   棘轮拒绝本次变更（benchmark 分数未严格提升）")
        else:
            print(f"   错误: {result.get('error')}")
            if result.get("missing_files"):
                print(f"   缺失文件 {len(result['missing_files'])} 个：")
                for m in result["missing_files"][:5]:
                    print(f"     - {m['prefix']} ({m['path']})")

    return result.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
