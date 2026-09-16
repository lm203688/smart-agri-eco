"""
engine/rsi.py —— RSI 五级自主权分级 + Headroom Closed Index（北极星）

借鉴：Theseus Labs《Recursive Self-Improvement》五级框架（L1 执行 → L2 策略 →
L3 部署 → L4 经验获取 → L5 元改进）与其「Headroom Closed Index」度量思想。

本模块把「自主权」从口号变成**可机读、可审计、可跨日比较**的数字：
    - 每一级自主权都必须有**真实产物证据**（文件/记录），否则不达标
    - 绝不因「规划里写了」就计为已达成（防自我感觉良好）
    - HCI 是当前已闭合门禁 / 全部门禁，范围 0-1，越高越接近无人工干预的闭环

分级与本项目证据锚点：
    L1 执行 Execution   —— 有 execution_log 记录 + 至少 1 条真实反馈回流
    L2 策略 Strategy    —— 至少 1 个作物被实测校准（measured_calibration）
    L3 部署 Deployment  —— 校准泛化到 >= 3 个作物（跨作物/跨区域复用）
    L4 经验获取 Experience —— 自动生成技能 >= 1 个且已被编排层引用
    L5 元改进 Meta      —— 门禁口径被 bump 过 且 历史 HCI 出现过变化（反复重测不算改进）

用法：
    python -m engine.rsi                    # 打印当前项目的自主权分级报告
    from engine.rsi import project_state, classify_autonomy, headroom_closed_index
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
_FEEDBACK_LOG = os.path.join(ROOT, "data", "feedback_log.json")
_EXECUTION_LOG = os.path.join(ROOT, "data", "execution_log.json")
_SKILLS_DIR = os.path.join(ROOT, "skills", "registry")
_HARNESS_MANIFEST = os.path.join(ROOT, "harness", "manifest.json")

# 六条「自主权门禁」：每条对应一个真实产物，闭合即贡献 HCI
GATE_EXECUTION = "execution_log"
GATE_FEEDBACK = "feedback_inflow"
GATE_CALIBRATION = "calibration"
GATE_GENERALIZATION = "generalization"
GATE_SKILL = "skill_generation"
GATE_META = "meta_improvement"

ALL_GATES = [
    GATE_EXECUTION, GATE_FEEDBACK, GATE_CALIBRATION,
    GATE_GENERALIZATION, GATE_SKILL, GATE_META,
]

# 五级定义（机读）：level → (名称, 语义, 达标所需门禁)
LEVELS: Dict[str, Dict[str, Any]] = {
    "L1": {
        "name": "执行 Execution",
        "meaning": "系统按既定规则执行配方/建议，无人工改写即可落地",
        "requires": [GATE_EXECUTION, GATE_FEEDBACK],
    },
    "L2": {
        "name": "策略 Strategy",
        "meaning": "执行结果回流并反过来调整系统策略（校准生效）",
        "requires": [GATE_EXECUTION, GATE_FEEDBACK, GATE_CALIBRATION],
    },
    "L3": {
        "name": "部署 Deployment",
        "meaning": "校准后的策略可跨作物/跨区域泛化复用",
        "requires": [GATE_EXECUTION, GATE_FEEDBACK, GATE_CALIBRATION,
                     GATE_GENERALIZATION],
    },
    "L4": {
        "name": "经验获取 Experience",
        "meaning": "从积累的经验自动产生新能力（生成新技能并被调用）",
        "requires": [GATE_EXECUTION, GATE_FEEDBACK, GATE_CALIBRATION,
                     GATE_GENERALIZATION, GATE_SKILL],
    },
    "L5": {
        "name": "元改进 Meta",
        "meaning": "系统改进自身的评测基线与门禁定义（递归自我改进）",
        "requires": ALL_GATES,
    },
}

# 分级达到 L2 视为「有策略回流」；HCI 的分母恒为全部门禁数
LEVEL_ORDER = ["B0", "L1", "L2", "L3", "L4", "L5"]

# 门禁口径的初始版本。L5 要求它被 bump 过（修订过门禁定义才算「元改进」）；
# 与 scripts/harness_sync.py 的 RSI_GATE_VERSION 保持同步。
INITIAL_GATE_VERSION = "1.0"


def _load_json(path: str) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None
    return None


def _feedback_log_path() -> str:
    """与 flywheel 一致：允许 AGRI_FEEDBACK_LOG 覆盖（测试隔离用）。"""
    return os.environ.get("AGRI_FEEDBACK_LOG") or _FEEDBACK_LOG


def _crop_db_path() -> str:
    return os.environ.get("AGRI_CROP_DB") or _CROP_DB


def _is_synthetic(entry: Dict[str, Any]) -> bool:
    """合成样本（单测/demo/冒烟）不得计为真实回流证据。"""
    text = " ".join(
        [str(entry.get("note", ""))] + [str(i) for i in entry.get("issues", [])]
    ).lower()
    return any(k in text for k in ("unittest", "smoke", "[demo]"))


def project_state() -> Dict[str, Any]:
    """从真实产物提取自主权证据（只读，不改任何文件）。"""
    crop_db = _load_json(_crop_db_path()) or {}
    feedback = _load_json(_feedback_log_path())
    execution = _load_json(_EXECUTION_LOG)

    real_feedback = [e for e in (feedback or [])
                     if isinstance(e, dict) and not _is_synthetic(e)]
    exec_entries = execution if isinstance(execution, list) else (
        [] if not execution else list(execution.values())
    )

    calibrated = 0
    calibrated_keys: List[str] = []
    for zid, zm in (crop_db.get("zones", {}) or {}).items():
        for c in (zm.get("crops", []) or []):
            if c.get("calibrated") and c.get("measured_calibration"):
                calibrated += 1
                calibrated_keys.append(f"{zid}/{c.get('crop', '')}")

    auto_skills: List[Dict[str, Any]] = []
    all_skills: List[Dict[str, Any]] = []
    if os.path.isdir(_SKILLS_DIR):
        for path in sorted(glob.glob(os.path.join(_SKILLS_DIR, "*.json"))):
            if os.path.basename(path) == "schema.json":
                continue
            meta = _load_json(path)
            if not isinstance(meta, dict):
                continue
            meta["_path"] = os.path.relpath(path, ROOT).replace("\\", "/")
            all_skills.append(meta)
            if meta.get("auto_generated"):
                auto_skills.append(meta)

    referenced_ids: List[str] = []
    try:
        from agent.orchestrator import ONDEMAND_SKILLS
        referenced_ids = sorted(ONDEMAND_SKILLS.keys())
    except Exception:
        pass
    auto_referenced = [s for s in auto_skills if s.get("id") in referenced_ids]

    manifest = _load_json(_HARNESS_MANIFEST) or {}
    manifest_rsi = manifest.get("rsi", {}) if isinstance(manifest, dict) else {}
    manifest_version = str(manifest.get("version", ""))
    eval_baseline = manifest.get("eval_baseline", {}) if isinstance(manifest, dict) else {}
    history = manifest_rsi.get("history", []) if isinstance(manifest_rsi, dict) else []

    # L5 证据需要区分「重新测量」与「真的改进」：
    #   - gate_version 被 bump（门禁口径本身修订过）
    #   - 历史快照中 hci 出现过不同取值（系统真的移动过，不是原地重测）
    gate_version = str(manifest_rsi.get("gate_version", ""))
    gate_bumped = bool(gate_version) and gate_version != INITIAL_GATE_VERSION
    hci_values = [h.get("hci") for h in history
                  if isinstance(h, dict) and h.get("hci") is not None]
    hci_changed = len(set(hci_values)) >= 2

    return {
        "execution_log_entries": len(exec_entries),
        "real_feedback_entries": len(real_feedback),
        "synthetic_feedback_excluded": len(feedback or []) - len(real_feedback),
        "calibrated_crops": calibrated,
        "calibrated_keys": calibrated_keys,
        "auto_generated_skills": len(auto_skills),
        "auto_generated_skill_ids": [s.get("id") for s in auto_skills],
        "auto_skills_referenced": len(auto_referenced),
        "referenced_skill_ids": referenced_ids,
        "total_skills": len(all_skills),
        "harness_manifest_version": manifest_version,
        "rsi_gate_version": gate_version,
        "rsi_gate_version_bumped": gate_bumped,
        "rsi_history_entries": len(history),
        "rsi_history_hci_changed": hci_changed,
        "eval_baseline_implemented": len(eval_baseline.get("implemented", []) or []),
        "eval_baseline_pending": len(eval_baseline.get("pending", []) or []),
    }


def evaluate_gates(state: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """逐门禁判定闭合与否，并给出**真实证据**（不闭合就说明缺什么）。"""
    s = state or project_state()
    gates: Dict[str, Dict[str, Any]] = {}

    gates[GATE_EXECUTION] = {
        "closed": s["execution_log_entries"] > 0,
        "evidence": f"execution_log.json 含 {s['execution_log_entries']} 条执行记录",
        "gap": "Env Recipe 尚无真实执行设备回填 execution_log"
               if not s["execution_log_entries"] else "",
    }

    gates[GATE_FEEDBACK] = {
        "closed": s["real_feedback_entries"] > 0,
        "evidence": f"真实反馈 {s['real_feedback_entries']} 条"
                    f"（已排除 {s['synthetic_feedback_excluded']} 条合成样本）",
        "gap": "feedback_log.json 无真实用户回流（0 条）"
               if not s["real_feedback_entries"] else "",
    }

    gates[GATE_CALIBRATION] = {
        "closed": s["calibrated_crops"] >= 1,
        "evidence": f"{s['calibrated_crops']} 个作物已实测校准",
        "gap": "无任何实测校准条目" if not s["calibrated_crops"] else "",
    }

    gates[GATE_GENERALIZATION] = {
        "closed": s["calibrated_crops"] >= 3,
        "evidence": f"{s['calibrated_crops']} 个作物已校准（>=3 视为可泛化）",
        "gap": f"已校准 {s['calibrated_crops']}/3，尚未跨作物/区域泛化"
               if s["calibrated_crops"] < 3 else "",
    }

    gates[GATE_SKILL] = {
        "closed": s["auto_generated_skills"] > 0 and s["auto_skills_referenced"] > 0,
        "evidence": f"自动生成技能 {s['auto_generated_skills']} 个，"
                    f"其中 {s['auto_skills_referenced']} 个已被编排层引用",
        "gap": ("无自动生成技能" if not s["auto_generated_skills"]
                else "有自动生成技能但零调用路径引用（YAGNI 应复核）")
               if (not s["auto_generated_skills"] or not s["auto_skills_referenced"]) else "",
    }

    # L5 元改进门禁：harness 契约已声明，且「真的改进过」。
    # 两条改进证据缺一不可：
    #   ① gate_version 被 bump —— 门禁口径本身修订过（不是沿用初始定义）
    #   ② 历史 hci 出现过不同取值 —— 系统真的移动过（不是原地反复重测）
    # 另外：判定读的是**已提交**的 harness 清单，所以运行 harness_sync init
    # 不会立刻闭合自己这一条（避免「写清单即 L5」的自我满足陷阱）。
    meta_ok = (bool(s["harness_manifest_version"])
               and s["rsi_gate_version_bumped"]
               and s["rsi_history_hci_changed"])
    gates[GATE_META] = {
        "closed": meta_ok,
        "evidence": f"harness 清单版本 {s['harness_manifest_version'] or '未声明'}；"
                    f"门禁口径 {s['rsi_gate_version'] or '未声明'}"
                    f"（bump={s['rsi_gate_version_bumped']}）；"
                    f"自观测快照 {s['rsi_history_entries']} 条，"
                    f"hci 曾变化={s['rsi_history_hci_changed']}；"
                    f"评测基线已实现 {s['eval_baseline_implemented']} 项",
        "gap": "门禁口径从未修订（gate_version 仍为初始值）或历史 hci 从未变化"
               "（反复重测 ≠ 自我改进）" if not meta_ok else "",
    }

    return gates


def classify_autonomy(gates: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """按门禁闭合情况给出当前自主权级别（取可达到的最高级）。"""
    g = gates or evaluate_gates()
    achieved = "B0"
    per_level: Dict[str, Any] = {}
    for level in LEVEL_ORDER[1:]:  # B0 是基线，直接跳过
        spec = LEVELS[level]
        ok = all(g[k]["closed"] for k in spec["requires"])
        per_level[level] = {
            "name": spec["name"],
            "meaning": spec["meaning"],
            "achieved": ok,
            "open_gates": [k for k in spec["requires"] if not g[k]["closed"]],
        }
        if ok:
            achieved = level
    return {
        "level": achieved,
        "name": LEVELS.get(achieved, {}).get("name", "无自主（人工全程）"),
        "per_level": per_level,
        "gates": g,
    }


def headroom_closed_index(gates: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Headroom Closed Index：已闭合门禁 / 全部门禁（0-1，越高越接近 L5）。"""
    g = gates or evaluate_gates()
    closed = [k for k in ALL_GATES if g[k]["closed"]]
    open_ = [k for k in ALL_GATES if not g[k]["closed"]]
    return {
        "hci": round(len(closed) / len(ALL_GATES), 3) if ALL_GATES else 0.0,
        "closed": len(closed),
        "total": len(ALL_GATES),
        "closed_gates": closed,
        "open_gates": open_,
        "interpretation": (
            "HCI 度量「自主权门禁闭合率」。它不度量能力高低，只度量"
            "「闭环是否真的闭合」。0 表示所有产物证据都缺失，1 表示 L5 全闭合。"
        ),
    }


def report() -> Dict[str, Any]:
    """完整分级报告：状态 → 门禁 → 级别 → HCI。"""
    state = project_state()
    gates = evaluate_gates(state)
    level = classify_autonomy(gates)
    hci = headroom_closed_index(gates)
    return {
        "evidence_state": state,
        "gates": gates,
        "autonomy": level,
        "hci": hci,
        "definition": "RSI 五级自主权分级（B0→L5）+ Headroom Closed Index；"
                      "每级达标必须有真实产物证据，未闭合即列出缺口。",
    }


def main() -> None:
    r = report()
    a = r["autonomy"]
    h = r["hci"]
    s = r["evidence_state"]
    print("=" * 60)
    print("RSI 自主权分级报告")
    print("=" * 60)
    print(f"当前级别：{a['level']} · {a['name']}")
    print(f"HCI（门禁闭合率）：{h['hci']}  ({h['closed']}/{h['total']})")
    print()
    print("证据状态：")
    for k, v in s.items():
        print(f"  {k}: {v}")
    print()
    print("门禁明细：")
    for k, g in r["gates"].items():
        mark = "✅" if g["closed"] else "❌"
        print(f"  {mark} {k:<18} {g['evidence']}")
        if not g["closed"]:
            print(f"     └ 缺口：{g['gap']}")
    print()
    print("分级达成情况：")
    for level, info in a["per_level"].items():
        mark = "✅" if info["achieved"] else "➖"
        print(f"  {mark} {level} {info['name']}"
              + ("" if info["achieved"] else f"（待闭合：{info['open_gates']}）"))
    print("=" * 60)


if __name__ == "__main__":
    main()
