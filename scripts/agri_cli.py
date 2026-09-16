#!/usr/bin/env python3
"""
智慧农业生态 · 按需 CLI（安全门禁版）

用途：把项目的能力以「按需调用」方式暴露给脚本 / CI / Agent，
      而不是每次都要写一个临时 Python 脚本。

安全模型（默认拒绝，借 just-bash / 白名单式 shell 沙箱思路）：
  1. **子命令白名单**：只允许 --COMMANDS 里列出的动作，其余一律拒绝。
  2. **零 shell 拼接**：所有动作都是 Python 函数分派，
     不把任何用户字符串拼进 shell / subprocess，因此不存在命令注入面。
  3. **路径逃逸防护**：--input-file 必须是仓库内的真实文件，
     解析 realpath 后校验前缀，../ 与绝对路径越界一律拒绝。
  4. **只读默认**：任何会写盘的动作必须显式 --write，且只写仓库内。

用法：
  python scripts/agri_cli.py --help
  python scripts/agri_cli.py pipeline --lat 30.2741 --lon 120.1551 --scene balcony
  python scripts/agri_cli.py skill pest_diagnose --crop 番茄 --symptom 叶片白色粉状物
  python scripts/agri_cli.py hci
  python scripts/agri_cli.py audit
  python scripts/agri_cli.py verify
  python scripts/agri_cli.py feedback-log --json
  python scripts/agri_cli.py recipe-init            # 需 --write 才真正落盘
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# 安全门禁
# ---------------------------------------------------------------------------
DENY_MESSAGE = "⛔ 已拒绝：该动作不在白名单内（默认拒绝原则）"

# 写盘类动作：必须显式 --write，且只允许写仓库内
WRITE_ACTIONS = {"recipe-init"}


def resolve_inside_root(path: str) -> str:
    """把输入路径解析为仓库内的真实路径；越界则抛 ValueError。

    防护点：
      - 相对路径统一按 ROOT 解析
      - 用 realpath 消除符号链接与 .. 逃逸
      - 校验前缀，防 ../../etc/passwd 这类越界
    """
    if not path:
        raise ValueError("路径不能为空")
    candidate = path if os.path.isabs(path) else os.path.join(ROOT, path)
    real = os.path.realpath(candidate)
    root_real = os.path.realpath(ROOT)
    if os.path.commonpath([real, root_real]) != root_real:
        raise ValueError(f"路径越出仓库范围，已拒绝: {path!r}")
    return real


def sha_of(path: str, length: int = 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:length]


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 动作实现（纯 Python 分派，无 shell 拼接）
# ---------------------------------------------------------------------------
def cmd_pipeline(args: argparse.Namespace) -> int:
    from agent.orchestrator import AgriOrchestrator
    req = {
        "lat": args.lat, "lon": args.lon, "scene": args.scene,
        "purpose": args.purpose, "space_sqm": args.space_sqm,
        "difficulty": args.difficulty, "budget_cny": args.budget_cny,
    }
    if args.input_file:
        with open(resolve_inside_root(args.input_file), "r",
                  encoding="utf-8") as f:
            req.update(_load_json_input(f))
    r = AgriOrchestrator().run_pipeline(req, verify=True)
    return _emit({
        "zone": r["final_recommendation"].get("zone_id",
                    r["pipeline_steps"][0]["output"]["evidence"]["zone_id"]),
        "top_crops": [c.get("crop") for c in
                      r["final_recommendation"].get("recommended_crops", [])],
        "rubric": r["trust_summary"].get("overall_rubric_score"),
        "verification_passed": r["verification"].get("passed"),
    }, args.json)


def _load_json_input(f) -> Dict[str, Any]:
    data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("输入文件必须是 JSON 对象")
    return data


def cmd_skill(args: argparse.Namespace) -> int:
    """按技能名按需调用（走 orchestrator 统一入口，不绕过编排层）。"""
    from agent.orchestrator import ONDEMAND_SKILLS, AgriOrchestrator
    if args.name not in ONDEMAND_SKILLS:
        print(f"⛔ 已拒绝：{args.name!r} 不是可按需调用的技能")
        print(f"   可用: {sorted(ONDEMAND_SKILLS)}")
        return 2
    payload: Dict[str, Any] = {}
    for attr, key in (("crop", "crop"), ("symptom", "symptom"),
                      ("lat", "lat"), ("lon", "lon"), ("zone_id", "zone_id"),
                      ("container_l", "container_l")):
        v = getattr(args, attr, None)
        if v is not None:
            payload[key] = v
    if args.input_file:
        with open(resolve_inside_root(args.input_file), "r",
                  encoding="utf-8") as f:
            payload.update(_load_json_input(f))
    r = AgriOrchestrator().call_skill(args.name, payload)
    return _emit(r, args.json)


def cmd_hci(args: argparse.Namespace) -> int:
    from engine.eval import eval_hci
    r = eval_hci()
    return _emit(r, args.json)


def cmd_audit(args: argparse.Namespace) -> int:
    import engine.skill_factory as sf
    r = sf.audit()
    return _emit(r, args.json)


def cmd_verify(args: argparse.Namespace) -> int:
    """跑全部单测（四套）+ 端到端验证，返回 0/1。"""
    import unittest
    import importlib
    failed = 0
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    for name in ("test_agents", "test_engine_v2", "test_engine_v3", "test_engine_v4"):
        mod = importlib.import_module(name)
        suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
        res = unittest.TextTestRunner(verbosity=0).run(suite)
        bad = len(res.failures) + len(res.errors)
        failed += bad
        print(f"  {name}: {res.testsRun} 例，{bad} 失败")
    return 1 if failed else 0


def cmd_search(args: argparse.Namespace) -> int:
    """本地三层检索（精确/关键词/向量），只读。"""
    import engine.local_search as ls
    return _emit(ls.search(args.query, corpus=args.corpus, k=args.k,
                           mode=args.mode), args.json)


def cmd_schedule(args: argparse.Namespace) -> int:
    """条件锚定：给定观测值，判断该执行哪些动作（只读）。"""
    import engine.recipe_scheduler as rs
    recipe = rs.load_recipe(crop=args.crop, zone=args.zone)
    obs = json.loads(args.observations) if args.observations else {}
    return _emit(rs.next_actions(recipe, obs, symptom_text=args.symptom or ""),
                 args.json)


def cmd_recall(args: argparse.Namespace) -> int:
    """跨会话长期记忆召回（只读）。"""
    import engine.long_term_memory as ltm
    hits = ltm.recall(query=args.query or "", crop=args.crop or "",
                      zone=args.zone or "", skill=args.skill or "",
                      tags=args.tags.split(",") if args.tags else None,
                      k=args.k, expand=not args.no_expand)
    slim = [{"id": h["id"], "ts": h["ts"], "score": h["score"],
             "outcome": (h["memory"] or {}).get("outcome", ""),
             "summary": (h["memory"] or {}).get("summary", "")}
            for h in hits]
    return _emit({"hits": slim, "total": len(slim),
                  "store_stats": ltm.stats()}, args.json)


def cmd_state_machine(args: argparse.Namespace) -> int:
    """工作项状态机契约快照（转移表 + 当前注册表，只读）。"""
    import engine.work_item as wim
    return _emit({"transitions": wim.transition_table(),
                  "states": list(wim.STATES), "modes": list(wim.MODES),
                  "registry": wim.registry_stats()}, args.json)


def cmd_feedback_log(args: argparse.Namespace) -> int:
    """只读查看反馈回流状态（真实条目 vs 合成样本）。"""
    import engine.rsi as rsi_mod
    state = rsi_mod.project_state()
    return _emit({k: state[k] for k in
                  ("real_feedback_entries", "synthetic_feedback_excluded",
                   "calibrated_crops", "total_skills", "harness_manifest_version")},
                 args.json)


def cmd_recipe_init(args: argparse.Namespace) -> int:
    """初始化空执行日志（唯一写盘动作，需 --write）。"""
    target = os.path.join(ROOT, "data", "execution_log.json")
    real = os.path.realpath(target)
    if os.path.commonpath([real, os.path.realpath(ROOT)]) != os.path.realpath(ROOT):
        print("⛔ 已拒绝：目标路径越出仓库范围")
        return 2
    if not args.write:
        print(f"🔒 只读模式：{target} 将写入 1 条空日志占位。"
              "加 --write 才会真正写盘。")
        print("   当前状态：",
              "已存在" if os.path.exists(target) else "不存在")
        return 0
    if not os.path.exists(target):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False)
        print(f"✅ 已创建空执行日志：{os.path.relpath(target, ROOT)}")
    else:
        print(f"ℹ️  已存在，未覆盖：{os.path.relpath(target, ROOT)}")
    return 0


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def _emit(obj: Any, as_json: bool) -> int:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            print(f"  {k}: {v}")
        return 0
    print(obj)
    return 0


COMMANDS: Dict[str, Dict[str, Any]] = {
    "pipeline": {"func": cmd_pipeline, "write": False,
                 "help": "跑四 Agent 流水线并做结构化校验"},
    "skill": {"func": cmd_skill, "write": False,
              "help": "按需调用单一技能（走 orchestrator 统一入口）"},
    "hci": {"func": cmd_hci, "write": False,
            "help": "打印自主权级别与 HCI 门禁闭合率"},
    "audit": {"func": cmd_audit, "write": False,
              "help": "Skill 审计：CLS 分级 + YAGNI + Anti-Rot"},
    "verify": {"func": cmd_verify, "write": False,
               "help": "跑全部单测（agents + engine_v2 + v3 + v4）"},
    "search": {"func": cmd_search, "write": False,
               "help": "本地三层检索（精确/关键词/向量，只读）"},
    "schedule": {"func": cmd_schedule, "write": False,
                 "help": "条件锚定：按观测值判定该执行哪些动作（只读）"},
    "recall": {"func": cmd_recall, "write": False,
               "help": "跨会话长期记忆召回（只读）"},
    "state-machine": {"func": cmd_state_machine, "write": False,
                      "help": "工作项状态机契约快照（只读）"},
    "feedback-log": {"func": cmd_feedback_log, "write": False,
                     "help": "查看反馈回流与校准状态（只读）"},
    "recipe-init": {"func": cmd_recipe_init, "write": True,
                    "help": "初始化空执行日志（写盘，需 --write）"},
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agri_cli",
        description="智慧农业生态按需 CLI（白名单 + 只读默认 + 零 shell 拼接）",
    )
    p.add_argument("--write", action="store_true",
                   help="允许写盘动作（默认只读）")
    sub = p.add_subparsers(dest="command")
    sub.required = True

    pp = sub.add_parser("pipeline", help=COMMANDS["pipeline"]["help"])
    pp.add_argument("--lat", type=float, required=True)
    pp.add_argument("--lon", type=float, required=True)
    pp.add_argument("--scene", default="balcony")
    pp.add_argument("--purpose", default="食用")
    pp.add_argument("--space_sqm", type=float, default=1.5)
    pp.add_argument("--difficulty", default="beginner")
    pp.add_argument("--budget_cny", type=float, default=500)
    pp.add_argument("--input-file", dest="input_file", default=None)
    pp.add_argument("--json", action="store_true")

    ps = sub.add_parser("skill", help=COMMANDS["skill"]["help"])
    ps.add_argument("name")
    ps.add_argument("--crop", default=None)
    ps.add_argument("--symptom", default=None)
    ps.add_argument("--lat", type=float, default=None)
    ps.add_argument("--lon", type=float, default=None)
    ps.add_argument("--zone_id", default=None)
    ps.add_argument("--container_l", type=float, default=None)
    ps.add_argument("--input-file", dest="input_file", default=None)
    ps.add_argument("--json", action="store_true")

    for name in ("hci", "audit", "verify", "feedback-log", "recipe-init"):
        s = sub.add_parser(name, help=COMMANDS[name]["help"])
        s.add_argument("--json", action="store_true")

    psr = sub.add_parser("search", help=COMMANDS["search"]["help"])
    psr.add_argument("query")
    psr.add_argument("--corpus", default="all",
                     help="crops / zones / pests / recipes / all")
    psr.add_argument("--k", type=int, default=8)
    psr.add_argument("--mode", default="hybrid",
                     choices=("hybrid", "exact", "keyword", "vector"))
    psr.add_argument("--json", action="store_true")

    psc = sub.add_parser("schedule", help=COMMANDS["schedule"]["help"])
    psc.add_argument("--crop", required=True)
    psc.add_argument("--zone", default=None)
    psc.add_argument("--observations", default=None,
                     help='JSON 观测值，如 {"humidity_pct": 92, "temp_c": 34}')
    psc.add_argument("--symptom", default=None,
                     help="症状文本，用于关键词锚点匹配")
    psc.add_argument("--json", action="store_true")

    pcr = sub.add_parser("recall", help=COMMANDS["recall"]["help"])
    pcr.add_argument("--query", default=None)
    pcr.add_argument("--crop", default=None)
    pcr.add_argument("--zone", default=None)
    pcr.add_argument("--skill", default=None)
    pcr.add_argument("--tags", default=None, help="逗号分隔")
    pcr.add_argument("--k", type=int, default=5)
    pcr.add_argument("--no-expand", action="store_true",
                     help="不做超边二阶扩展")
    pcr.add_argument("--json", action="store_true")

    psm = sub.add_parser("state-machine", help=COMMANDS["state-machine"]["help"])
    psm.add_argument("--json", action="store_true")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cmd = args.command

    if cmd not in COMMANDS:
        print(f"{DENY_MESSAGE}: {cmd!r}")
        return 2
    spec = COMMANDS[cmd]
    # 写盘动作不在这里硬拒绝：由各动作自行降级为只读提示（更友好，
    # 且不牺牲安全性——真正写盘仍必须显式 --write）。

    if getattr(args, "input_file", None):
        try:
            resolve_inside_root(args.input_file)
        except ValueError as e:
            print(f"⛔ 已拒绝：{e}")
            return 2

    try:
        return spec["func"](args)
    except FileNotFoundError as e:
        print(f"⛔ 文件不存在或不可读: {e}")
        return 2
    except ValueError as e:
        print(f"⛔ 已拒绝：{e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
