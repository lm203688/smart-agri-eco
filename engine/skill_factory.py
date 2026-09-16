#!/usr/bin/env python3
"""
engine/skill_factory.py —— Skill 自动生成管线

闭环触发（逻辑闭环的关键一环）：
    - 情报闭环（automation）发现新的农业能力点 / 新作物 / 新场景
    - 数据飞轮（flywheel）发现 crop_adapt_db 未覆盖的作物或场景
    → 由本模块自动产出一份「符合 skills/registry/schema.json」的 Skill 定义，
      写入 skills/registry/<id>.json，使 CropAgent 等立即获得可复用能力。

设计原则：
    - 生成的 Skill 严格满足 schema 的 required 字段（id/name/description/domain/
      inputs/outputs/data_sources），domain 必须是 enum 之一。
    - 默认不覆盖已有 Skill（overwrite=False），避免误删人工打磨的能力。
    - 所有自动生成的 Skill 标注 auto_generated=true，便于审计与溯源。
    - CLS 安全分级（借 CocoLoop S/A/B/C/D）：由 classify_skill_risk() 从字段文本
      **机读判定**（联网/读凭据/写文件/安全边界），随 skill 落盘，分发前可审查。
    - YAGNI 精简（借 ponytail）：yagni_trim() 删除零引用字段与空可选字段，
      但不裁剪 required 字段；未显式传白名单时不裁剪 inputs/outputs，避免误删。
    - Anti-Rot 治理（借 QoderWake）：lint_skill()/audit() 标记零调用路径引用的技能。

用法：
    python -m engine.skill_factory            # 跑一次演示（冰菜→新 Skill）
    python -m engine.skill_factory --list     # 列出当前所有 Skill
    python -m engine.skill_factory --audit    # CLS + YAGNI + Anti-Rot 全量审计（只读）
"""

from __future__ import annotations

import os
import re
import json
import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "skills", "registry")
SCHEMA_PATH = os.path.join(REGISTRY, "schema.json")

_DOMAIN_ENUM = ["climate", "crop", "growth", "pest", "eco", "logistics", "soil"]

# CLS 安全分级：S 最安全 → D 风险最高（借 CocoLoop 的 S/A/B/C/D 分级思想）
CLS_LEVELS = {
    "S": "纯本地只读，无外部依赖，安全边界明确",
    "A": "纯本地只读，可逆",
    "B": "写本地文件（可逆）或调用受限外部只读接口",
    "C": "调用外部网络接口",
    "D": "联网且写文件/不可逆，或接触凭据",
}

# 分级信号关键词（机读，可从 skill 文本自动判定，不靠人工标注）
_NET_HINTS = ("http://", "https://", "api.", "在线", "online", "cloud", "rest.")
# 凭据关键词用短词，但 `_key` 这类后缀极易假阳（foreign_key / primary_key），
# 故改用正则精确匹配「环境变量式密钥」与 api_key 写法。
_CRED_KEYWORDS = ("token", "凭据", "secret", "password", "密钥", "api key")
_CRED_PATTERNS = (r"agri_[a-z0-9_]*key", r"api[_-]?key")
# 注意：这里**刻意不用**裸「覆盖」——skill 描述里「扩大覆盖」会被误判成「覆盖写入」。
# 教训：中文关键词分级必须用长匹配词，短词极易假阳。
_WRITE_HINTS = ("写入", "落盘", "写盘", "写文件", "覆盖写入", "覆盖已有",
                "overwrite", "upload")
_LOCAL_HINTS = ("本地", "local", "data/", "离线", "offline")


def classify_skill_risk(skill: Dict[str, Any]) -> Dict[str, Any]:
    """机读 CLS 安全分级：从 skill 的字段文本自动判定，不依赖人工标注。

    判定口径（可复算）：
        联网 = data_sources/description/dependencies 出现网络端点关键词
        读凭据 = 出现 token/key/凭据 等关键词
        写文件 = 出现写入/落盘/覆盖 等关键词
    分级：
        S —— 本地只读 + 有 safety_boundary 声明 + 无外部数据源
        A —— 本地只读 + 可逆（无写入、无凭据、无联网）
        B —— 写本地文件（可逆），或联网但仅只读
        C —— 调用外部网络接口
        D —— 联网且写文件/不可逆，或接触凭据
    返回 {"cls","grade_name","signals","rationale"}
    """
    text_parts = [
        str(skill.get("description", "")),
        str(skill.get("safety_boundary", "")),
        " ".join(str(x) for x in skill.get("data_sources", []) or []),
        " ".join(str(x) for x in skill.get("dependencies", []) or []),
    ]
    text = " ".join(text_parts).lower()

    external_net = any(h in text for h in _NET_HINTS)
    reads_creds = any(h in text for h in _CRED_KEYWORDS) or any(
        re.search(p, text) for p in _CRED_PATTERNS)
    writes_files = any(h in text for h in _WRITE_HINTS)
    mentions_local = any(h in text for h in _LOCAL_HINTS)
    has_safety_boundary = bool(str(skill.get("safety_boundary", "")).strip())

    signals = {
        "external_network": external_net,
        "reads_credentials": reads_creds,
        "writes_files": writes_files,
        "mentions_local_only": mentions_local,
        "has_safety_boundary": has_safety_boundary,
    }

    if reads_creds or (external_net and writes_files):
        cls = "D"
    elif external_net:
        cls = "C"
    elif writes_files:
        cls = "B"
    elif external_net or not mentions_local:
        cls = "B"
    else:
        cls = "S" if has_safety_boundary else "A"

    return {
        "cls": cls,
        "grade_name": CLS_LEVELS[cls],
        "signals": signals,
        "rationale": "由 classify_skill_risk() 从 skill 文本机读判定："
                     f"联网={external_net} 读凭据={reads_creds} "
                     f"写文件={writes_files} 安全边界声明={has_safety_boundary}",
    }


_OPTIONAL_TEXT_FIELDS = ("version", "agent", "confidence_method",
                         "safety_boundary", "reuse_value")


def yagni_trim(
    skill: Dict[str, Any],
    used_inputs: Optional[List[str]] = None,
    used_outputs: Optional[List[str]] = None,
    drop_empty: bool = True,
) -> Dict[str, Any]:
    """YAGNI 精简：删除零引用字段，返回精简率（借 ponytail 的「少即是多」原则）。

    参数：
        skill: 原始 skill 定义
        used_inputs: 若提供，仅保留在此列表中的 inputs（未提供则不裁剪，避免误删）
        used_outputs: 同上，用于 outputs
        drop_empty: 删除值为空的可选字段（默认 True）
    返回 {"skill", "yagni": {...}}，yagni 含 before/after/reduction_ratio/dropped

    约束：不裁剪 required 字段（id/name/description/domain/inputs/outputs/
    data_sources）——它们为空时本就应报错，由 generate_skill 负责校验。
    """
    trimmed = dict(skill)
    dropped: Dict[str, List[str]] = {"inputs": [], "outputs": [], "fields": []}
    before_chars = len(json.dumps(skill, ensure_ascii=False, sort_keys=True))

    if used_inputs is not None:
        kept = [x for x in trimmed.get("inputs", []) or [] if x in used_inputs]
        dropped["inputs"] = [x for x in trimmed.get("inputs", []) or []
                             if x not in used_inputs]
        trimmed["inputs"] = kept
    if used_outputs is not None:
        kept = [x for x in trimmed.get("outputs", []) or [] if x in used_outputs]
        dropped["outputs"] = [x for x in trimmed.get("outputs", []) or []
                              if x not in used_outputs]
        trimmed["outputs"] = kept

    if drop_empty:
        for f in _OPTIONAL_TEXT_FIELDS:
            if f in trimmed and str(trimmed[f]).strip() == "":
                trimmed.pop(f)
                dropped["fields"].append(f)
        deps = trimmed.get("dependencies")
        if deps is not None and not deps:
            trimmed.pop("dependencies")
            dropped["fields"].append("dependencies")

    after_chars = len(json.dumps(trimmed, ensure_ascii=False, sort_keys=True))
    n_dropped = sum(len(v) for v in dropped.values())
    return {
        "skill": trimmed,
        "yagni": {
            "before_chars": before_chars,
            "after_chars": after_chars,
            "reduction_ratio": round(1 - after_chars / before_chars, 3)
                               if before_chars else 0.0,
            "dropped": dropped,
            "dropped_count": n_dropped,
            "note": "YAGNI：只删零引用字段。required 字段永不裁剪；"
                    "未提供 used_inputs/used_outputs 时不裁剪列表，避免误删真实能力。",
        },
    }


def _wired_agents() -> set:
    """编排层实际装配的 Agent 类名集合（自省，不硬编码）。

    这样新增 Agent 或漏装 Agent 时，腐化检查会自动跟着变化。
    """
    try:
        from agent.orchestrator import AgriOrchestrator
        inst = AgriOrchestrator()
        return {type(v).__name__ for v in vars(inst).values()
                if type(v).__name__.endswith("Agent")}
    except Exception:
        return set()


def _known_agent_ids() -> set:
    """可按需调用的技能 id 集合（ONDEMAND_SKILLS）。"""
    try:
        from agent.orchestrator import ONDEMAND_SKILLS
        return set(ONDEMAND_SKILLS.keys())
    except Exception:
        return set()


def lint_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Anti-Rot 治理检查：一个 skill 是否「腐化」（零引用 / 无证据 / 字段残缺）。

    「被引用」有两类合法路径：
        1. id 在 orchestrator.ONDEMAND_SKILLS 中（反应式技能，call_skill 直调）
        2. agent 字段指向编排层实际装配的 Agent（规划流水线技能，run_pipeline 调用）
    两者都不满足才算零引用。
    """
    issues: List[str] = []
    if not str(skill.get("description", "")).strip():
        issues.append("description 为空")
    if not (skill.get("inputs") or []):
        issues.append(
            "顶层 inputs 缺失（schema required）——"
            + ("本技能用 modes 结构描述参数，建议补顶层聚合 inputs 以满足 schema"
               if skill.get("modes") else "无参数契约，无法被调用")
        )
    if not (skill.get("outputs") or []):
        issues.append(
            "顶层 outputs 缺失（schema required）——"
            + ("本技能用 modes 结构描述产出" if skill.get("modes") else "无产出契约")
        )
    if not (skill.get("data_sources") or []):
        issues.append("data_sources 为空（无溯源依据）")
    if skill.get("auto_generated") and not skill.get("cls"):
        issues.append("自动生成技能缺 CLS 分级（应运行 --audit 补齐）")

    agent_name = str(skill.get("agent", "")).strip()
    referenced = (skill.get("id") in _known_agent_ids()) or (agent_name in _wired_agents())
    if not referenced:
        issues.append(
            "零调用路径引用："
            + (f"agent={agent_name!r} 未在编排层装配" if agent_name
               else "agent 字段缺失且 id 不在 ONDEMAND_SKILLS")
        )

    return {
        "id": skill.get("id"),
        "rot_score": len(issues),
        "rot": len(issues) > 0,
        "issues": issues,
        "referenced_by_orchestrator": referenced,
        "reference_path": ("call_skill" if skill.get("id") in _known_agent_ids()
                           else "run_pipeline" if referenced else "none"),
    }


def audit() -> Dict[str, Any]:
    """全量审计注册表：每个 skill 的 CLS 分级 + YAGNI 机会 + 腐化检查（只读）。"""
    out: List[Dict[str, Any]] = []
    for s in list_skills():
        risk = classify_skill_risk(s)
        yagni = yagni_trim(s)
        rot = lint_skill(s)
        out.append({
            "id": s.get("id"),
            "domain": s.get("domain"),
            "cls": risk["cls"],
            "cls_name": risk["grade_name"],
            "cls_signals": risk["signals"],
            "yagni": yagni["yagni"],
            "rot": rot,
        })
    grades = {k: 0 for k in CLS_LEVELS}
    for row in out:
        grades[row["cls"]] += 1
    return {
        "total": len(out),
        "cls_distribution": grades,
        "rot_count": sum(1 for r in out if r["rot"]["rot"]),
        "skills": out,
    }


def _load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def generate_skill(
    skill_id: str,
    name: str,
    domain: str,
    description: str,
    inputs: List[str],
    outputs: List[str],
    data_sources: List[str],
    version: str = "1.0",
    agent: str = "",
    confidence_method: str = "",
    safety_boundary: str = "",
    reuse_value: str = "",
    dependencies: Optional[List[str]] = None,
    used_inputs: Optional[List[str]] = None,
    used_outputs: Optional[List[str]] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """生成并落盘一个符合 schema 的 Skill。

    参数：
        used_inputs / used_outputs：YAGNI 裁剪白名单。传入时仅保留列表内字段；
            不传（默认）则不裁剪列表，只清理空可选字段，避免误删真实能力。
    返回：{"skill": ..., "path": ..., "validated": True, "yagni": ..., "cls": ...}
    """
    schema = _load_schema()
    required = schema.get("required", [])

    skill: Dict[str, Any] = {
        "id": skill_id,
        "name": name,
        "description": description,
        "domain": domain,
        "inputs": inputs,
        "outputs": outputs,
        "data_sources": data_sources,
    }
    if version:
        skill["version"] = version
    if agent:
        skill["agent"] = agent
    if confidence_method:
        skill["confidence_method"] = confidence_method
    if safety_boundary:
        skill["safety_boundary"] = safety_boundary
    if reuse_value:
        skill["reuse_value"] = reuse_value
    if dependencies is not None:
        skill["dependencies"] = dependencies
    skill["auto_generated"] = True
    skill["created_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    # YAGNI：删除零引用/空可选字段（不裁剪 required 字段）
    yagni_result = yagni_trim(skill, used_inputs=used_inputs,
                              used_outputs=used_outputs)
    skill = yagni_result["skill"]

    # CLS 安全分级：机读判定后落盘，供分发前审查（借 CocoLoop S/A/B/C/D）
    skill["cls"] = classify_skill_risk(skill)["cls"]

    # 校验必填
    missing = [k for k in required if k not in skill]
    if missing:
        raise ValueError(f"缺少必填字段: {missing}")
    # 校验 domain enum
    if domain not in _DOMAIN_ENUM:
        raise ValueError(f"domain 必须是 {_DOMAIN_ENUM} 之一，收到 {domain!r}")
    # 校验 id 格式
    if not re.match(r"^[a-z_]+$", skill_id):
        raise ValueError(f"id 必须全小写下划线（^[a-z_]+$），收到 {skill_id!r}")

    fname = skill_id + ".json"
    fpath = os.path.join(REGISTRY, fname)
    if os.path.exists(fpath) and not overwrite:
        raise FileExistsError(f"Skill 已存在: {fname}（用 overwrite=True 覆盖）")

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(skill, f, ensure_ascii=False, indent=2)
    return {"skill": skill, "path": fpath, "validated": True,
            "yagni": yagni_result["yagni"], "cls": skill["cls"]}


def list_skills() -> List[Dict[str, Any]]:
    out = []
    if not os.path.isdir(REGISTRY):
        return out
    for fn in sorted(os.listdir(REGISTRY)):
        if fn.endswith(".json") and fn != "schema.json":
            with open(os.path.join(REGISTRY, fn), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def demo() -> Dict[str, Any]:
    """演示：数据飞轮发现新作物「冰菜」，自动生成一个 CropAgent 可复用 Skill。"""
    return generate_skill(
        skill_id="iceplant_advisory",
        name="冰菜阳台种植建议",
        domain="crop",
        description="为新增作物冰菜（Mesembryanthemum crystallinum）提供分区适配与阳台种植建议，"
                    "由 skill_factory 自动生成，扩大 CropAgent 覆盖。",
        inputs=["zone_id", "scene", "space_sqm"],
        outputs=["adapt_score", "growth_days", "risk_flags", "fallback_variety"],
        data_sources=["用户反馈", "农艺通识"],
        agent="CropAgent",
        confidence_method="seed 适配分 + flywheel 实测校准",
        safety_boundary="建议结合本地实测，不替代农技人员",
        reuse_value="新增作物即自动注册为可复用 Skill，降低重复工程",
        overwrite=True,
    )


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="列出当前所有 Skill")
    p.add_argument("--audit", action="store_true",
                   help="全量审计：CLS 分级 + YAGNI 精简机会 + Anti-Rot 腐化检查（只读）")
    args = p.parse_args()
    if args.list:
        for s in list_skills():
            print(f"  {s.get('id')}  [{s.get('domain')}]  "
                  f"cls={s.get('cls', '?')}  {s.get('name')}")
        return
    if args.audit:
        r = audit()
        print("=" * 56)
        print(f"Skill 审计：{r['total']} 个 | CLS 分布 {r['cls_distribution']} | "
              f"腐化 {r['rot_count']} 个")
        print("=" * 56)
        for row in r["skills"]:
            mark = "⚠️" if row["rot"]["rot"] else "✅"
            print(f"  {mark} {row['id']:<20} cls={row['cls']} "
                  f"精简率={row['yagni']['reduction_ratio']}")
            for issue in row["rot"]["issues"]:
                print(f"       └ {issue}")
        return
    r = demo()
    print(f"已生成 Skill 文件: {r['path']}")
    print(f"CLS 分级: {r['cls']} | YAGNI 精简率: {r['yagni']['reduction_ratio']} "
          f"(删除 {r['yagni']['dropped_count']} 个零引用字段)")


if __name__ == "__main__":
    main()
