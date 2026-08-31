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

用法：
    python -m engine.skill_factory            # 跑一次演示（冰菜→新 Skill）
    python -m engine.skill_factory --list     # 列出当前所有 Skill
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
    overwrite: bool = False,
) -> Dict[str, Any]:
    """生成并落盘一个符合 schema 的 Skill。

    返回：{"skill": ..., "path": ..., "validated": True}
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
    return {"skill": skill, "path": fpath, "validated": True}


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
    args = p.parse_args()
    if args.list:
        for s in list_skills():
            print(f"  {s.get('id')}  [{s.get('domain')}]  {s.get('name')}")
        return
    r = demo()
    print(f"已生成 Skill 文件: {r['path']}")


if __name__ == "__main__":
    main()
