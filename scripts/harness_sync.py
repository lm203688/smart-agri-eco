#!/usr/bin/env python3
"""
scripts/harness_sync.py —— Git-native harness 清单同步（防漂移门禁）

借鉴：TeamAI 的 Git-native harness 思路——把「harness 要素」（MCP 工具、Agent
技能、协议版本、数据基线、评测基线、环境变量）抽成**单一声明文件**，随仓库
版本化、可审阅、可门禁；而不是散落在各模块里事后对账。

本项目的 harness 声明落在 `harness/manifest.json`，由本脚本**从运行时代码与
真实数据反算生成**（不是手写），因此它永远是「代码真实状态」的镜像。

子命令：
    init      从代码/数据现状生成（或覆盖）harness/manifest.json
    check     重算并比对，有漂移则退出码 1（可挂 CI 门禁）
    dry-run   等价 check，但以「将变更清单」形式输出，不判定失败
    push      **不执行提交**。仅打印待提交变更 + 提醒走 scripts/gh_push.py

约束：零第三方依赖；只读代码、只写 harness/manifest.json；绝不 git commit/push。

用法：
    python scripts/harness_sync.py init
    python scripts/harness_sync.py check
    python scripts/harness_sync.py dry-run
    python scripts/harness_sync.py push
"""

from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MANIFEST_DIR = os.path.join(ROOT, "harness")
MANIFEST_PATH = os.path.join(MANIFEST_DIR, "manifest.json")

# 构成 harness 的关键数据文件（指纹漂移 = 数据基线漂移）
TRACKED_PATHS = [
    "data/crop_adapt_db.json",
    "data/zone_meta/global_zones.json",
    "data/wofost_phenology_reference.json",
    "data/feedback_log.json",
    # 预设城市清单（2026-09-23 收敛为单一数据源）：改它等于改前端与 MCP 的城市集，
    # 必须纳入防漂移追踪，否则静默改动无法被巡检发现。
    "data/preset_cities.json",
]

# 协议版本声明（与各 docs/env_recipe_protocol_v1.md 保持同步，人工维护）
PROTOCOL_VERSIONS = {
    "env_recipe": "v1",
    "mcp_protocol": "2024-11-05",
}

# harness 清单自身版本（bump 时表示 harness 契约已被修订）
MANIFEST_VERSION = "2.2.0"
# RSI 门禁定义版本（bump 时表示门禁口径已被修订）
RSI_GATE_VERSION = "1.0"

# 声明区：由人/代码**约定**的契约，允许漂移但必须门禁（改了就要重新 init）
DECLARED_SECTIONS = ("schema", "version", "project", "protocols", "mcp",
                     "agents", "skills", "harness_tree",
                     "data_baselines", "eval_baseline",
                     "env_vars", "push_policy")
# 观测区：**度量**出来的状态。RSI 本身读 harness 清单，是自指字段——
# 若把它纳入漂移门禁，`init` 之后立刻必然漂移（固定点不存在），
# 因此只作为信息快照打印，不参与通过/失败判定。
# knowledge_graph / org_memory 同理：图是派生索引、记忆随执行增长，都是观测值。
OBSERVED_SECTIONS = ("rsi", "knowledge_graph", "org_memory",
                     "long_term_memory", "local_search", "recipe_scheduler")
_VOLATILE_KEYS = ("generated_at", "updated_at")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _mcp_tools() -> List[str]:
    """从 mcp/server.py 反算真实工具名（不手写，避免文档漂移）。"""
    server_path = os.path.join(ROOT, "mcp", "server.py")
    src = open(server_path, "r", encoding="utf-8").read()
    tools: List[str] = []
    for line in src.splitlines():
        line = line.strip()
        if line.startswith('"agri_') and '":' in line:
            name = line.split('"')[1]
            if name not in tools:
                tools.append(name)
    return sorted(tools)


def _skills() -> Dict[str, Any]:
    reg = os.path.join(ROOT, "skills", "registry")
    out = {"ids": [], "auto_generated": [], "implemented": 0}
    if not os.path.isdir(reg):
        return out
    for fn in sorted(os.listdir(reg)):
        if not fn.endswith(".json") or fn == "schema.json":
            continue
        meta = _load_json(os.path.join(reg, fn)) or {}
        sid = meta.get("id") or fn[:-5]
        out["ids"].append(sid)
        if meta.get("auto_generated"):
            out["auto_generated"].append(sid)
        if meta.get("implemented"):
            out["implemented"] += 1
    return {"ids": out["ids"], "count": len(out["ids"]),
            "auto_generated": out["auto_generated"],
            "implemented": out["implemented"]}


def _on_demand_skills() -> List[str]:
    try:
        from agent.orchestrator import ONDEMAND_SKILLS
        return sorted(ONDEMAND_SKILLS.keys())
    except Exception:
        return []


def _env_vars() -> List[str]:
    """从源码反算 AGRI_* 环境变量名（不手写，避免文档漂移）。

    只认实际被 os.environ 读取/清除的名字，注释与文档里的提及不计。
    """
    import re
    found: List[str] = []
    pat = re.compile(r'os\.environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']')
    pat2 = re.compile(r'os\.environ\.pop\(\s*["\']([A-Z][A-Z0-9_]*)["\']')
    # bp_screen 是独立包（零依赖 BP 初筛引擎），2026-09-20 并入。
    # 漏扫后果：它的 6 个环境变量（AGRI_BP_DB / _LLM_URL / _LLM_KEY /
    # _LLM_MODEL / _WEB_PORT / _WEB_HOST）对防漂移清单完全不可见——
    # 曾只有 AGRI_BP_LLM_URL/_KEY 因测试文件恰好引用而混入，属假阳性。
    for rel in ("engine", "agent", "core", "mcp", "app", "scripts", "bp_screen"):
        d = os.path.join(ROOT, rel)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".py"):
                continue
            try:
                with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                    src = f.read()
            except Exception:
                continue
            for m in list(pat.finditer(src)) + list(pat2.finditer(src)):
                name = m.group(1)
                if name.startswith("AGRI_") and name not in found:
                    found.append(name)
    return sorted(found)


def _data_baselines() -> List[Dict[str, Any]]:
    out = []
    for rel in TRACKED_PATHS:
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            obj = _load_json(path)
            entry: Dict[str, Any] = {"path": rel, "sha256_16": _sha(path)}
            if rel.endswith("crop_adapt_db.json") and isinstance(obj, dict):
                zones = obj.get("zones", {})
                crops = sum(len(z.get("crops", [])) for z in zones.values())
                calib = sum(
                    1 for z in zones.values()
                    for c in z.get("crops", [])
                    if c.get("calibrated") and c.get("measured_calibration")
                )
                entry.update({"zones": len(zones), "crops": crops,
                              "calibrated": calib})
            if rel.endswith("feedback_log.json") and isinstance(obj, list):
                entry["entries"] = len(obj)
            out.append(entry)
        else:
            out.append({"path": rel, "missing": True})
    return out


def _eval_baseline() -> Dict[str, Any]:
    """评测基线：逐个调用 engine.eval 的评测函数，据其真实返回值判定状态。

    engine.eval 的约定是：已实现的返回 {total, rate, ...}；未实现的返回
    {"status": "NOT_IMPLEMENTED", ...}。此处按该约定如实分类，不做主观判断。
    """
    import importlib
    ev = importlib.import_module("engine.eval")
    checks = _load_json(os.path.join(ROOT, "data", "eval", "zone_checks.json"))
    crop_db = _load_json(os.path.join(ROOT, "data", "crop_adapt_db.json"))

    # 分区一致率与覆盖评测需要一个 ClimateAgent 实例（构造无副作用、无网络）
    climate = None
    try:
        from agent.climate_agent import ClimateAgent
        climate = ClimateAgent()
    except Exception:
        climate = None

    candidates = {
        "eval_zone_consistency": lambda: ev.eval_zone_consistency(checks or [], climate),
        "eval_crop_db_coverage": lambda: ev.eval_crop_db_coverage(
            [{"crop": "番茄", "lat": 30.2741, "lon": 120.1551}],
            climate, crop_db or {}),
        "eval_extraction_accuracy": ev.eval_extraction_accuracy,
        "eval_pest_diagnosis_topk": ev.eval_pest_diagnosis_topk,
        "eval_recipe_expert_adoption": ev.eval_recipe_expert_adoption,
        "eval_source_traceability": ev.eval_source_traceability,
    }
    implemented, pending = [], []
    for name, fn in candidates.items():
        try:
            res = fn()
        except Exception:
            res = None
        if isinstance(res, dict) and res.get("status") == "NOT_IMPLEMENTED":
            pending.append(name)
        elif isinstance(res, dict):
            implemented.append(name)
        else:
            pending.append(name)
    return {
        "implemented": sorted(implemented),
        "pending": sorted(pending),
        "pending_reasons": _pending_reasons(ev, pending),
        "updated_at": _now(),
    }


def _pending_reasons(ev: Any, pending: List[str]) -> Dict[str, str]:
    """把未实现评测的官方理由写进清单，避免「待办清单」被当作已完成。"""
    out: Dict[str, str] = {}
    for name in pending:
        fn = getattr(ev, name, None)
        if fn is None:
            continue
        try:
            res = fn()
            if isinstance(res, dict):
                out[name] = str(res.get("reason", ""))
        except Exception:
            pass
    return out


def build_manifest() -> Dict[str, Any]:
    """从运行时状态构建 harness 清单（唯一真相来源 = 代码与数据本身）。"""
    mcp_tools = _mcp_tools()
    skills = _skills()
    data = _data_baselines()
    eval_baseline = _eval_baseline()

    rsi_section: Dict[str, Any] = {"gate_version": RSI_GATE_VERSION, "history": []}
    try:
        import importlib
        rsi = importlib.import_module("engine.rsi")
        r = rsi.report()
        rsi_section.update({
            "autonomy_level": r["autonomy"]["level"],
            "hci": r["hci"]["hci"],
            "open_gates": r["hci"]["open_gates"],
        })
    except Exception as e:  # pragma: no cover - 仅在 rsi 模块不可用时
        rsi_section["error"] = str(e)

    # L5「元改进」证据：harness 自身被观测的快照历史（不含首次运行即自证）
    rsi_section["history"] = _rsi_history(rsi_section)

    return {
        "schema": "agri-harness-manifest/v1",
        "version": MANIFEST_VERSION,
        "generated_at": _now(),
        "project": "智慧农业生态 (smart-agri-eco)",
        "protocols": dict(PROTOCOL_VERSIONS),
        "mcp": {"tool_count": len(mcp_tools), "tools": mcp_tools},
        "agents": {
            "pipeline": ["ClimateAgent", "CropAgent", "GrowthAgent", "EcoAgent"],
            "ondemand_skills": _on_demand_skills(),
        },
        "skills": skills,
        "harness_tree": _harness_tree(),
        "data_baselines": data,
        "eval_baseline": eval_baseline,
        "knowledge_graph": _knowledge_graph_obs(),
        "org_memory": _org_memory_obs(),
        "long_term_memory": _long_term_memory_obs(),
        "local_search": _local_search_obs(),
        "recipe_scheduler": _recipe_scheduler_obs(),
        "rsi": rsi_section,
        "env_vars": _env_vars(),
        "push_policy": "本脚本绝不执行 git commit/push；提交走 scripts/gh_push.py",
    }


def _harness_tree() -> Dict[str, Any]:
    """组件树声明区：计数 + id 清单 + lint 结果（完整定义在 skills/harness/*.json）。

    刻意只登记计数与 id——manifest 是漂移门禁的锚点，塞入完整组件正文会让
    manifest 与导出 JSON 双份维护，必然漂移。
    """
    try:
        import importlib
        ht = importlib.import_module("engine.harness_tree")
        s = ht.stats()
        t = ht.tree()
        return {
            "commands": {"count": s["commands"],
                         "ids": [c["id"] for c in ht.COMMANDS]},
            "hooks": {"count": s["hooks"],
                      "ids": [h["id"] for h in ht.HOOKS]},
            "rules": {"count": s["rules"],
                      "ids": [r["id"] for r in ht.RULES],
                      "blocker": s["blocker_rules"]},
            # 显式列出 blocker 规则 id——避免巡检脚本每次都要回读 engine/harness_tree.py 才能
            # 知道哪 3 条是硬门禁。blocker 决定「回归即拒发布」，缺失会让门禁失效。
            "blockers": [r["id"] for r in ht.RULES if r.get("severity") == "blocker"],
            "lint_ok": s["lint_ok"],
            "exported_to": "skills/harness/",
            "six_layers": ["agents", "skills", "commands", "hooks", "rules", "mcp_tools"],
            "source": "engine/harness_tree.py",
        }
    except Exception as e:  # pragma: no cover - 模块不可用时降级
        return {"error": str(e)}


def _knowledge_graph_obs() -> Dict[str, Any]:
    """知识图谱观测区：图是派生索引，节点/边数随源数据变化，仅作信息快照。"""
    try:
        import importlib
        kg = importlib.import_module("engine.knowledge_graph")
        r = kg.report()
        return {
            "schema": r.get("schema"),
            "nodes": r.get("nodes"),
            "edges": r.get("edges"),
            "edges_by_rel": r.get("edges_by_rel"),
            "reverse_queries_supported": bool(
                r.get("reverse_query_examples", {}).get("exposure_by_zone")),
        }
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _org_memory_obs() -> Dict[str, Any]:
    """组织记忆观测区：轨迹与 Playbook 随真实执行增长。"""
    try:
        import importlib
        om = importlib.import_module("engine.org_memory")
        return om.stats()
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _pin_default_env(name: str) -> str:
    """观测区必须读**真实默认路径**，不能跟随 AGRI_* 覆盖。

    背景：观测区被 verify_all / 各测试套件调用时，进程内的 AGRI_LONG_TERM_MEMORY /
    AGRI_SEARCH_INDEX 可能已被某个用例指向 tempfile（那是隔离用的临时文件）。
    若观测区照单全收，快照就会报告「memories 0→6」「built True→False」这类
    假漂移——数字来自临时文件，不代表真实基线（2026-09-17 实测踩到）。
    这里临时摘除覆盖，测完原样还原。
    """
    old = os.environ.get(name)
    os.environ.pop(name, None)
    return old if old is not None else ""


def _restore_env(name: str, old: str):
    if old:
        os.environ[name] = old
    else:
        os.environ.pop(name, None)


def _long_term_memory_obs() -> Dict[str, Any]:
    """长期记忆观测区：记忆与超边随真实执行增长。"""
    try:
        import importlib
        ltm = importlib.import_module("engine.long_term_memory")
        saved = _pin_default_env(ltm.ENV_PATH)
        try:
            s = ltm.stats()
        finally:
            _restore_env(ltm.ENV_PATH, saved)
        # 去掉绝对路径：路径会随 AGRI_LONG_TERM_MEMORY 变化，属噪声
        s.pop("path", None)
        return s
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _local_search_obs() -> Dict[str, Any]:
    """本地检索观测区：索引是派生缓存，行数随数据源增长。"""
    try:
        import importlib
        ls = importlib.import_module("engine.local_search")
        env_name = getattr(ls, "ENV_INDEX", getattr(ls, "ENV_PATH", "AGRI_SEARCH_INDEX"))
        saved = _pin_default_env(env_name)
        try:
            s = ls.stats()
        finally:
            _restore_env(env_name, saved)
        s.pop("path", None)
        return s
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _recipe_scheduler_obs() -> Dict[str, Any]:
    """条件锚定观测区：全部配方的锚点总量（配方一变锚点数就变）。"""
    try:
        import importlib
        rs = importlib.import_module("engine.recipe_scheduler")
        total = 0
        by_kind: Dict[str, int] = {"threshold": 0, "keyword": 0}
        n = 0
        for path in sorted(glob.glob(rs.RECIPE_GLOB)):
            try:
                r = _load_json(path)
            except Exception:
                continue
            for a in rs.anchors_from_recipe(r):
                total += 1
                by_kind[a.get("kind", "?")] = by_kind.get(a.get("kind", "?"), 0) + 1
            n += 1
        return {
            "recipes_scanned": n,
            "anchors_total": total,
            "anchors_by_kind": by_kind,
            "operators_supported": list(rs.OPS),
            "field_aliases": {k: list(v) for k, v in rs.FIELD_ALIASES.items()},
        }
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def _rsi_history(current: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把上一次的 RSI 快照追加进历史（上限 50 条），供 L5 门禁判定。

    语义：L5 要求「系统观测过自身多次」，首次运行没有历史 → 门禁不闭合。
    """
    old = _load_json(MANIFEST_PATH) or {}
    hist: List[Dict[str, Any]] = list(old.get("rsi", {}).get("history", []) or [])
    old_rsi = old.get("rsi", {}) or {}
    if old_rsi.get("autonomy_level") or old_rsi.get("hci") is not None:
        snap = {
            "ts": old.get("generated_at", ""),
            "level": old_rsi.get("autonomy_level"),
            "hci": old_rsi.get("hci"),
        }
        if not hist or hist[-1] != snap:
            hist.append(snap)
    hist.append({
        "ts": _now(),
        "level": current.get("autonomy_level"),
        "hci": current.get("hci"),
    })
    return hist[-50:]


def _digest(manifest: Dict[str, Any]) -> str:
    """清单指纹：忽略生成时间戳，只比较实质内容。"""
    m = {k: v for k, v in manifest.items() if k not in ("generated_at",)}
    raw = json.dumps(m, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _project(manifest: Dict[str, Any], sections) -> Dict[str, Any]:
    """按区域投影清单，只保留指定 section。"""
    return {k: v for k, v in manifest.items() if k in sections}


def _strip_volatile(changes: List[str]) -> List[str]:
    """剔除时间戳类噪声字段。"""
    return [c for c in changes if not any(v in c for v in _VOLATILE_KEYS)]


def _diff(old: Dict[str, Any], new: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """拆成（声明区漂移, 观测区漂移），分别对待。"""
    return (_strip_volatile(_diff_declared(
                                _project(old, DECLARED_SECTIONS),
                                _project(new, DECLARED_SECTIONS))),
            _strip_volatile(_diff_declared(
                                _project(old, OBSERVED_SECTIONS),
                                _project(new, OBSERVED_SECTIONS))))


def _diff_declared(old: Dict[str, Any], new: Dict[str, Any],
                   path: str = "") -> List[str]:
    """结构 diff：返回漂移条目的人类可读清单。"""
    out: List[str] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for k in sorted(set(old) | set(new)):
            p = f"{path}.{k}" if path else k
            if k not in old:
                out.append(f"+ {p}: <new> = {new[k]!r}"[:200])
            elif k not in new:
                out.append(f"- {p}: <removed>")
            else:
                out.extend(_diff_declared(old[k], new[k], p))
    elif isinstance(old, list) and isinstance(new, list):
        if old != new:
            out.append(f"~ {path or 'root'}: list 变更 {len(old)}→{len(new)} 项")
    else:
        if old != new:
            out.append(f"~ {path}: {old!r} → {new!r}"[:200])
    return out


def cmd_init() -> int:
    manifest = build_manifest()
    # 目录从 MANIFEST_PATH 反推（而非硬编码 MANIFEST_DIR），
    # 这样测试重定向清单路径时不会误写仓库里的真实清单。
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"✅ 已生成 harness 清单：{os.path.relpath(MANIFEST_PATH, ROOT)}")
    print(f"   版本 {manifest['version']} | MCP 工具 {manifest['mcp']['tool_count']} 个 "
          f"| 技能 {manifest['skills']['count']} 个 | 指纹 {_digest(manifest)}")
    print("   说明：`check` 只门禁「声明区」；rsi/长期记忆/检索索引/锚点等"
          "为自指或派生观测区，仅信息展示。")
    return 0


def _report_check(fail_on_drift: bool) -> int:
    if not os.path.exists(MANIFEST_PATH):
        print("⚠️  harness/manifest.json 不存在——请先运行 `harness_sync.py init`")
        return 1
    committed = _load_json(MANIFEST_PATH) or {}
    live = build_manifest()
    changes = _diff(committed, live)
    declared_drift, observed_drift = changes

    if not declared_drift:
        print("✅ harness 声明区无漂移（清单与代码/数据现状一致）")
    else:
        print(f"❌ 声明区发现 {len(declared_drift)} 处漂移：")
        for c in declared_drift:
            print(f"   {c}")
        print("\n修复：运行 `python scripts/harness_sync.py init` 更新清单，"
              "随后走 scripts/gh_push.py 提交。")

    if observed_drift:
        print(f"ℹ️  观测区（自指/派生字段）变化 {len(observed_drift)} 处，仅供参考：")
        for c in observed_drift:
            print(f"   {c}")
    return (1 if declared_drift else 0) if fail_on_drift else 0


def cmd_check() -> int:
    return _report_check(fail_on_drift=True)


def cmd_dry_run() -> int:
    return _report_check(fail_on_drift=False)


def cmd_push() -> int:
    print("⛔ 拒绝提交。本脚本永不执行 git commit/push。")
    print("   请按项目既有链路操作：")
    print("     1) python scripts/harness_sync.py init      # 更新清单")
    print("     2) python scripts/harness_sync.py check      # 确认无漂移")
    print("     3) python scripts/gh_push.py                 # 走 Contents API 推送")
    print("   （本机直连 github.com:443 被封，仅 api.github.com 可达）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Git-native harness 清单同步")
    p.add_argument("command", choices=["init", "check", "dry-run", "push"])
    args = p.parse_args()
    return {
        "init": cmd_init,
        "check": cmd_check,
        "dry-run": cmd_dry_run,
        "push": cmd_push,
    }[args.command]()


if __name__ == "__main__":
    sys.exit(main())
