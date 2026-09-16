#!/usr/bin/env python3
"""
engine/harness_tree.py —— Harness 完整组件树：Agents / Skills / Commands / Hooks / Rules / MCP

借鉴 ECC（everything-claude-code）的六层组件树思想。本项目已有两层
（Agents、Skills/MCP），本模块补齐另外三层：

    Commands  一键触发流水线——人/CI 显式调用，参数与副作用写死可审计
    Hooks     事件驱动——环境越限等信号自动触发下游 agent
    Rules     常驻约束——agent 输出前必须满足的声明式规则（always-follow）

为什么把规则写成一等公民：
    过去这些约束散落在各 agent 的代码里（如「不要输出 PLACEHOLDER」「证据不足
    不下结论」），改一处容易漏另一处。抽成 Rules 后：①可被 CI 统一 lint；
    ②可被 harness 清单统计；③新增约束只需加一条声明，不必改动 agent 主体。

单一权威：组件定义在本文件（源码即真相），`--export` 导出 JSON 供 agent / CI
消费，与 harness_sync 生成 manifest 的模式一致。

用法：
    python -m engine.harness_tree              # 打印组件树统计
    python -m engine.harness_tree --export     # 导出 skills/harness/*.json
    python -m engine.harness_tree --lint       # 校验（重复 id / 缺字段 / 规则冲突）
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(ROOT, "skills", "harness")

# ---------------------------------------------------------------------------
# Commands：一键触发（人/CI 显式调用；skill 是能力契约，command 是编排意图）
# ---------------------------------------------------------------------------
COMMANDS: List[Dict[str, Any]] = [
    {
        "id": "full_advisory",
        "name": "全链路种植建议",
        "entry": "agent.orchestrator.AgriOrchestrator.run_pipeline",
        "inputs": {"lat": "float", "lon": "float", "scene": "str"},
        "outputs": ["pipeline_steps", "confidence_summary"],
        "writes": [],
        "side_effect": "none",
        "description": "分区匹配 → 作物推荐 → 生长计划 → 生态闭环，一次跑完",
    },
    {
        "id": "pest_check",
        "name": "病虫害检查（含证据门控）",
        "entry": "agent.orchestrator.AgriOrchestrator.call_skill",
        "inputs": {"skill": "pest_diagnose", "crop": "str",
                   "symptom_description": "str", "environment": "dict?"},
        "outputs": ["diagnosis", "confirmation_status", "evidence_gate"],
        "writes": [],
        "side_effect": "none",
        "description": "无双重证据时返回 confirmation_status=unconfirmed，只报监测项",
    },
    {
        "id": "season_check",
        "name": "物候与播期检查",
        "entry": "agent.orchestrator.AgriOrchestrator.call_skill",
        "inputs": {"skill": "season_advisory", "mode": "str",
                   "monthly_mean_c": "list[float]", "crops": "list[str]"},
        "outputs": ["available", "planting_window"],
        "writes": [],
        "side_effect": "none",
        "description": "霜冻锚定播期窗口，纯本地推导不依赖第三方日历",
    },
    {
        "id": "nutrition_check",
        "name": "容器营养方案",
        "entry": "agent.orchestrator.AgriOrchestrator.call_skill",
        "inputs": {"skill": "nutrition_plan", "crop": "str",
                   "container_volume_l": "float"},
        "outputs": ["recommendation"],
        "writes": [],
        "side_effect": "none",
        "description": "四阶段营养配比方案",
    },
]

# ---------------------------------------------------------------------------
# Hooks：事件驱动（信号 → 下游动作；触发条件必须是可机读表达式）
# ---------------------------------------------------------------------------
HOOKS: List[Dict[str, Any]] = [
    {
        "id": "humidity_over_limit",
        "name": "湿度越限 → 病害风险检查",
        "trigger": {"field": "environment.humidity_pct", "op": ">=", "value": 90},
        "action": {"command": "pest_check",
                   "inject": {"environment": "event.environment",
                              "symptom_hint": "高湿环境，重点排查霜霉病/白粉病"}},
        "priority": "high",
        "cooldown_hours": 6,
        "rationale": "持续高湿是霜霉病/白粉病的主要非生物诱因",
    },
    {
        "id": "temp_extreme",
        "name": "极端温度 → 环境胁迫告警",
        "trigger": {"field": "environment.temp_c", "op": "not_in", "value": [5, 35]},
        "action": {"command": "season_check",
                   "inject": {"mode": "risk", "crops": "event.crops"}},
        "priority": "high",
        "cooldown_hours": 12,
        "rationale": "越出 [5,35]°C 多数喜温作物进入胁迫区，需复核播期与遮阴",
    },
    {
        "id": "feedback_arrived",
        "name": "用户反馈到达 → 触发飞轮校准",
        "trigger": {"field": "event.type", "op": "==", "value": "feedback"},
        "action": {"command": "flywheel_record",
                   "inject": {"zone_id": "event.zone_id", "crop": "event.crop"}},
        "priority": "normal",
        "cooldown_hours": 0,
        "rationale": "反馈是飞轮的输入端；不触发校准则闭环永远空转",
    },
]

# ---------------------------------------------------------------------------
# Rules：常驻约束（always-follow；每条都必须可机读校验）
# ---------------------------------------------------------------------------
RULES: List[Dict[str, Any]] = [
    {
        "id": "no_unconfirmed_diagnosis",
        "name": "无双重证据不下确定性诊断",
        "applies_to": ["pest_diagnose"],
        "check": "confirmation_status == 'unconfirmed' → diagnosis 必须带（未确认）前缀",
        "severity": "blocker",
        "source": "agent/pest_agent._evidence_gate（借鉴 Shannon 零误报）",
    },
    {
        "id": "no_placeholder_output",
        "name": "禁止占位符输出",
        "applies_to": ["*"],
        "check": "输出 JSON 中不得出现 PLACEHOLDER 字面量",
        "severity": "blocker",
        "source": "agent/orchestrator Verifier 既有约束",
    },
    {
        "id": "data_provenance_required",
        "name": "每条建议必须标注数据来源",
        "applies_to": ["*"],
        "check": "evidence 字段非空且含 source 或 crop_known_risks 等证据指针",
        "severity": "major",
        "source": "docs/agent_output_contract.md",
    },
    {
        "id": "safe_rollback_on_regression",
        "name": "评测分数下降必须回滚",
        "applies_to": ["*"],
        "check": "engine.evolution.ratchet 判定 Δ<=0 时自动 restore 快照",
        "severity": "blocker",
        "source": "engine/evolution.py（借鉴 PenguinHarness 棘轮）",
    },
    {
        "id": "local_first_no_silent_telemetry",
        "name": "本地优先，无静默遥测",
        "applies_to": ["*"],
        "check": "任何外发请求必须可被环境变量关闭；视觉后端未配置时安全降级",
        "severity": "major",
        "source": "AgriTrust 信任层原则",
    },
]


def tree() -> Dict[str, Any]:
    """返回完整组件树（含统计），供 harness 清单与 CI 引用。"""
    return {
        "schema": "agri-harness-tree/v1",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "layers": {
            "agents": {
                "count": 4,
                "pipeline": ["ClimateAgent", "CropAgent", "GrowthAgent", "EcoAgent"],
                "ondemand": ["PestAgent", "NutritionAgent", "SeasonAgent"],
                "note": "Agent 定义见 agent/ 目录，此处只登记层级计数",
            },
            "skills": {"count": None, "source": "skills/registry/*.json"},
            "commands": {"count": len(COMMANDS), "items": copy.deepcopy(COMMANDS)},
            "hooks": {"count": len(HOOKS), "items": copy.deepcopy(HOOKS)},
            "rules": {"count": len(RULES), "items": copy.deepcopy(RULES)},
            "mcp_tools": {"count": None, "source": "mcp/server.py"},
        },
        "six_layer_note": "Agents / Skills / Commands / Hooks / Rules / MCP 六层齐备；"
                          "Commands/Hooks/Rules 由本模块定义并导出。",
    }


def lint(tree_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """组件树校验：重复 id、缺必填字段、规则严重度合法性、触发条件可机读。"""
    t = tree_obj or tree()
    issues: List[Dict[str, Any]] = []

    for layer in ("commands", "hooks", "rules"):
        items = t["layers"][layer]["items"]
        required = {"id", "name", "description"} if layer == "commands" else \
                   {"id", "name"}
        seen: Dict[str, int] = {}
        for i, item in enumerate(items):
            rid = item.get("id")
            if not rid:
                issues.append({"layer": layer, "idx": i,
                               "issue": "缺 id"})
                continue
            seen[rid] = seen.get(rid, 0) + 1
            for field in required:
                if not item.get(field):
                    issues.append({"layer": layer, "id": rid,
                                   "issue": "缺必填字段 %s" % field})
        for rid, n in seen.items():
            if n > 1:
                issues.append({"layer": layer, "id": rid,
                               "issue": "id 重复 %d 次" % n})

    # Hook 触发条件必须是可机读的三元组；Rule 严重度必须合法。
    # 全部从传入的 tree 取数（不直接遍历模块常量），保证 lint 的输入唯一。
    hooks = t["layers"]["hooks"]["items"]
    rules = t["layers"]["rules"]["items"]
    commands = t["layers"]["commands"]["items"]
    _OPS = {"=", "==", "!=", ">", ">=", "<", "<=", "in", "not_in"}
    for h in hooks:
        trig = h.get("trigger") or {}
        if not trig.get("field") or trig.get("op") not in _OPS or "value" not in trig:
            issues.append({"layer": "hooks", "id": h.get("id"),
                           "issue": "trigger 不可机读（需 field/op/value，op∈%s）" % sorted(_OPS)})

    _SEV = {"blocker", "major", "minor"}
    for r in rules:
        if r.get("severity") not in _SEV:
            issues.append({"layer": "rules", "id": r.get("id"),
                           "issue": "severity 非法: %r" % r.get("severity")})
        if not (r.get("applies_to") or []):
            issues.append({"layer": "rules", "id": r.get("id"),
                           "issue": "applies_to 为空，规则不生效"})

    # 交叉一致性：hook 引用的 command 必须存在
    cmd_ids = {c["id"] for c in commands}
    for h in hooks:
        ref = (h.get("action") or {}).get("command")
        if ref and ref not in cmd_ids and ref != "flywheel_record":
            issues.append({"layer": "hooks", "id": h.get("id"),
                           "issue": "引用的 command 不存在: %r" % ref})

    return {"ok": not issues, "issue_count": len(issues), "issues": issues,
            "layers_checked": ["commands", "hooks", "rules"]}


def export(tree_obj: Optional[Dict[str, Any]] = None,
           skills_count: Optional[int] = None,
           mcp_count: Optional[int] = None) -> Dict[str, Any]:
    """导出组件树到 skills/harness/{commands,hooks,rules}.json。

    skills/mcp 计数从 harness_sync 注入（避免重复扫描）。
    """
    t = tree_obj or tree()
    if skills_count is not None:
        t["layers"]["skills"]["count"] = skills_count
    if mcp_count is not None:
        t["layers"]["mcp_tools"]["count"] = mcp_count

    os.makedirs(HARNESS_DIR, exist_ok=True)
    written: Dict[str, str] = {}
    mapping = {k: ("%s.json" % k, t["layers"][k]["items"])
               for k in ("commands", "hooks", "rules")}
    for key, (fname, items) in mapping.items():
        path = os.path.join(HARNESS_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"schema": "agri-harness-%s/v1" % key,
                       "generated_at": t["generated_at"],
                       "count": len(items), "items": items},
                      f, ensure_ascii=False, indent=2)
        written[key] = os.path.relpath(path, ROOT)

    idx_path = os.path.join(HARNESS_DIR, "index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)
    written["index"] = os.path.relpath(idx_path, ROOT)
    return written


def stats() -> Dict[str, Any]:
    """组件树摘要（供 harness 清单声明区计数）。"""
    t = tree()
    return {
        "commands": len(COMMANDS),
        "hooks": len(HOOKS),
        "rules": len(RULES),
        "blocker_rules": sum(1 for r in RULES if r.get("severity") == "blocker"),
        "lint_ok": lint(t)["ok"],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--export", action="store_true")
    p.add_argument("--lint", action="store_true")
    args = p.parse_args()

    t = tree()
    if args.export:
        w = export(t)
        for k, v in w.items():
            print("  导出 %s -> %s" % (k, v))
        return
    if args.lint:
        r = lint(t)
        print("lint ok=%s, issues=%d" % (r["ok"], r["issue_count"]))
        for i in r["issues"]:
            print("  -", i)
        return

    s = stats()
    print("=" * 60)
    print("Harness 组件树（六层）")
    print("=" * 60)
    print("Commands %d | Hooks %d | Rules %d（blocker %d）| lint ok=%s"
          % (s["commands"], s["hooks"], s["rules"], s["blocker_rules"], s["lint_ok"]))
    print("Agents: %s + 按需 %s" % (t["layers"]["agents"]["pipeline"],
                                     t["layers"]["agents"]["ondemand"]))
    print("=" * 60)


if __name__ == "__main__":
    main()
