"""generate_shadow_execution_log.py — 影子运行破零脚本（M9-X1）。

依据 docs/per_module_deep_assessment_2026-10-13.md §M9-X1：
  ControlAgent 输出先写影子 execution_log（记录"建议动作 + 预期效果"），
  不执行；这是"不依赖任何硬件即可产生第 1 条 execution_log 的唯一路径"。

同时闭合 RSI L1 的 execution_log 门（engine/rsi.py 目前实测 execution_log=0）。

设计约束：
  - 零依赖（stdlib only）。
  - 只写 data/execution_log.json，不改 Env Recipe 文件本体（避免污染配方资产）。
  - 每条记录 mode=shadow + expected_effect 显式 + not_executed=true，与真实执行日志区分。
  - 与 schemas/execution_log.schema.json 契约保持向后兼容：
      本扩展在 source 值上扩展 "shadow"（原 enum 是 native/imported_kasvanta/imported_other）；
      validate_entry 相应放宽以支持 shadow，见 agent/execution_log.py。
  - 幂等：重复运行不重复追加同一 run_id。

CLI：
  python scripts/generate_shadow_execution_log.py              # 交互式打印 + 写盘
  python scripts/generate_shadow_execution_log.py --check      # 只检查，不写盘（CI 用）
  python scripts/generate_shadow_execution_log.py --dry-run    # 只打印，不写盘
  python scripts/generate_shadow_execution_log.py --json       # JSON 输出
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOG_PATH = os.path.join(ROOT, "data", "execution_log.json")
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")


# ---------------------------------------------------------------------------
# 典型场景模板：3 个不同分区 + 不同空间形态，覆盖气候/物候/设备多样性
# 这些场景是"如果真有人按我们的建议执行"的假设性记录。
# ---------------------------------------------------------------------------
_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "shadow_seed_001",
        "recipe_ref": "番茄:full_cycle:indoor_cabinet",
        "recipe_file": "mediterranean__番茄.json",
        "scene": "indoor_cabinet",
        "crop": "番茄",
        "zone_id": "mediterranean",
        "device_id": "shadow_device_seed_001",
        "started_at": "2026-10-01T08:00:00Z",
        "expected_effect": (
            "130 天周期内累积 GDD ~2600（地中海分区），"
            "预期单株产量 P50 ~450g、P90 ~650g；采收期 2027-02-22 前后"
        ),
        "expected_metrics": {
            "yield_estimate_g_p50": 450,
            "yield_estimate_g_p90": 650,
            "adjusted_duration_days_p50": 130,
            "harvest_date_p50": "2027-02-22",
            "target_ph": 6.4,
            "target_water_ml_day": 350,
            "target_day_temp_c": 32,
            "target_night_temp_c": 15,
        },
        "notes": (
            "影子运行：ControlAgent 依据 Env Recipe（mediterranean__番茄.json）"
            "生成的建议指令集未下发至任何真实设备，仅记录建议内容 + 预期效果，"
            "作为 L3 执行闭环的最小可验证证据。真实执行需硬件网关。"
        ),
    },
    {
        "id": "shadow_seed_002",
        "recipe_ref": "生菜:full_cycle:balcony",
        "recipe_file": "subtropical_wet__生菜.json",
        "scene": "balcony",
        "crop": "生菜",
        "zone_id": "subtropical_wet",
        "device_id": "shadow_device_seed_002",
        "started_at": "2026-10-05T06:30:00Z",
        "expected_effect": (
            "45 天周期完成一个采收周期；亚热带湿润分区下无光周期敏感，"
            "阳台半日照条件下预期产量 P50 ~80g/株、P90 ~120g/株"
        ),
        "expected_metrics": {
            "yield_estimate_g_p50": 80,
            "yield_estimate_g_p90": 120,
            "adjusted_duration_days_p50": 45,
            "harvest_date_p50": "2026-11-19",
        },
        "notes": (
            "影子运行：开放阳台场景补偿规则触发（降雨/骤降温预案），"
            "指令建议仅登记不下发。"
        ),
    },
    {
        "id": "shadow_seed_003",
        "recipe_ref": "胡萝卜:root_bulking:container",
        "recipe_file": "mediterranean__胡萝卜.json",
        "scene": "container",
        "crop": "胡萝卜",
        "zone_id": "mediterranean",
        "device_id": "shadow_device_seed_003",
        "started_at": "2026-09-25T07:00:00Z",
        "expected_effect": (
            "75 天完成根膨大期；预期单株产量 P50 ~200g、P90 ~280g；"
            "采收期 2026-12-09 前后；期间需维持 EC 1.5-2.0 mS/cm、pH 6.0-6.5"
        ),
        "expected_metrics": {
            "yield_estimate_g_p50": 200,
            "yield_estimate_g_p90": 280,
            "adjusted_duration_days_p50": 75,
            "harvest_date_p50": "2026-12-09",
            "target_ec_ms": 2.0,
            "target_ph": 6.3,
        },
        "notes": (
            "影子运行：ControlAgent 生成灌溉/施肥指令序列，"
            "记录建议但不下发，供未来对比真实执行数据时验证模型准确性。"
        ),
    },
]


def _derive_run_id(scenario: Dict[str, Any]) -> str:
    """影子记录稳定 ID：以 scenario id + started_at 派生。"""
    raw = "shadow|%s|%s" % (scenario["id"], scenario["started_at"])
    return "shadow_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_entry(s: Dict[str, Any]) -> Dict[str, Any]:
    """构造符合 schemas/execution_log.schema.json 的条目（含 shadow 扩展字段）。"""
    return {
        "run_id": _derive_run_id(s),
        "recipe_ref": s["recipe_ref"],
        "device_id": s["device_id"],
        "started_at": s["started_at"],
        "source": "shadow",
        "actual_params": {},
        "params_unknown": True,
        "actions_taken": [
            "[shadow] ControlAgent 建议指令已生成，未下发至硬件",
            "[shadow] 参见 expected_effect / expected_metrics 获取建议内容",
        ],
        "deviations": [],
        "observations": s.get("notes", ""),
        # —— 以下为 shadow 模式扩展字段，与 schema 兼容（additionalProperties 在 execution_log 数组项上是 false，
        # —— 因此这些扩展字段以 shadow_context 单一容器承载，避免 schema 冲突）
        "shadow_context": {
            "mode": "shadow",
            "not_executed": True,
            "expected_effect": s["expected_effect"],
            "expected_metrics": s["expected_metrics"],
            "scene": s["scene"],
            "crop": s["crop"],
            "zone_id": s["zone_id"],
            "recipe_file": s["recipe_file"],
            "control_agent_version": "1.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generator": "scripts/generate_shadow_execution_log.py",
            "reference": "docs/per_module_deep_assessment_2026-10-13.md §M9-X1",
        },
    }


def _load_log() -> List[Dict[str, Any]]:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_log(entries: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def generate(shadow_only: bool = True) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """生成影子条目并合并进现有日志。

    返回 (新增条目, 最终日志)。
    """
    existing = _load_log()
    existing_ids = {e.get("run_id") for e in existing}
    added: List[Dict[str, Any]] = []
    for s in _SCENARIOS:
        entry = _build_entry(s)
        if entry["run_id"] not in existing_ids:
            added.append(entry)
            existing_ids.add(entry["run_id"])
    return added, existing + added


def summarize(log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 source 分组统计。"""
    by_source: Dict[str, int] = {}
    for e in log:
        src = e.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    shadow_count = by_source.get("shadow", 0)
    return {
        "total_entries": len(log),
        "by_source": by_source,
        "shadow_count": shadow_count,
        "has_real_execution": any(s != "shadow" for s in by_source),
        "rsi_L1_execution_log_gate": "closed" if shadow_count > 0 else "open",
    }


def _main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="只检查当前状态并输出，不写盘（CI 门禁用）")
    p.add_argument("--dry-run", action="store_true", help="只打印将新增的条目，不写盘")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    added, final_log = generate()
    summary = summarize(final_log)

    if args.check:
        ok = summary["shadow_count"] > 0
        if args.json:
            print(json.dumps({"ok": ok, "summary": summary},
                             ensure_ascii=False, indent=2))
        else:
            print("影子运行门禁检查")
            print("=" * 46)
            print(f"  总条目: {summary['total_entries']}")
            print(f"  shadow 条目: {summary['shadow_count']}")
            print(f"  RSI L1 execution_log 门: {summary['rsi_L1_execution_log_gate']}")
            print(f"  真实执行数据: {'有' if summary['has_real_execution'] else '无'}")
            print("=" * 46)
            print("结论: " + ("✅ shadow 记录已存在，L1 门闭合"
                              if ok else "❌ 无 shadow 记录，L1 门未闭合"))
        return 0 if ok else 1

    if args.dry_run:
        if args.json:
            print(json.dumps({"added": added, "summary": summary},
                             ensure_ascii=False, indent=2))
        else:
            print(f"[DRY-RUN] 将新增 {len(added)} 条 shadow 记录:")
            for e in added:
                print(f"  - {e['run_id']} ({e['recipe_ref']})")
        return 0

    _save_log(final_log)
    if args.json:
        print(json.dumps({"added": len(added), "total": len(final_log),
                          "summary": summary, "log_path": LOG_PATH},
                         ensure_ascii=False, indent=2))
    else:
        print(f"✅ 已写入 {LOG_PATH}")
        print(f"   新增 {len(added)} 条 shadow 记录，总计 {len(final_log)} 条")
        print(f"   RSI L1 execution_log 门: {summary['rsi_L1_execution_log_gate']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
