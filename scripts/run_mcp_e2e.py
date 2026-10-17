#!/usr/bin/env python3
"""
MCP E2E 测试：20 个工具全部冒烟测试

对应报告主线一「接通」M13-P1 + M12-K1 的完成校验：
- 14 个原有工具
- 5 个新增工具（M13-P1 新增）：
  * agri_search (M12 检索接入)
  * agri_knowledge_query (M12 图谱)
  * agri_forecast (M5 独立暴露)
  * agri_recipe_profile (M8-R2 配方四件套)
  * agri_verify_trust (M11-T1 可信标记产品化)
- 1 个新增工具（M13-P3 新增）：
  * agri_server_card (Server Card + ETags)

使用：python scripts/run_mcp_e2e.py
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# 每个工具的调用参数。返回值 dict 表示成功，异常/失败表示 FAIL。
TOOL_CALLS = [
    # ---- 原 14 个 ----
    ("agri_list_cities", {}),
    ("agri_match_zone", {"lat": 39.9, "lon": 116.4}),
    ("agri_recommend_crops", {"zone_id": "temperate", "area_m2": 10}),
    ("agri_growth_plan", {"crop": "番茄", "zone_id": "temperate"}),
    ("agri_diagnose_pest", {"crop": "番茄", "symptoms": "叶片卷曲黄化"}),
    ("agri_nutrition_plan", {"crop": "番茄", "stage": "vegetative", "target_yield_g": 500}),
    ("agri_env_recipe", {"crop": "番茄", "zone_id": "temperate", "scene": "indoor_cabinet"}),
    ("agri_season_advisory", {"zone_id": "temperate", "month": 3}),
    ("agri_soil_profile", {"zone_id": "temperate"}),
    ("agri_bp_screen", {"project": "阳台种菜创业", "stage": "天使轮", "ask_amount": 2000000}),
    ("agri_reconcile_climate", {"lat": 39.9, "lon": 116.4, "month": 3}),
    ("agri_resolve_recipe", {"crop": "番茄", "zone_id": "temperate"}),
    ("agri_query_lineage", {"target": "data/env_recipes/"}),
    ("agri_list_ecosystem", {}),

    # ---- M13-P1 新增 5 个（M12/M5/M8/M11 接通）----
    ("agri_search", {"query": "番茄 病虫害", "top_k": 5}),
    ("agri_knowledge_query", {"entity_id": "番茄"}),
    ("agri_forecast", {"crop": "番茄", "zone_id": "temperate", "plant_date": "2026-03-01"}),
    ("agri_recipe_profile", {"op": "list"}),
    ("agri_verify_trust", {"target": "data/env_recipes/"}),

    # ---- M13-P3 新增 1 个（Server Card + ETags）----
    ("agri_server_card", {}),
]


def main() -> int:
    print(f"{'=' * 60}")
    print("MCP E2E 冒烟测试 · 20 个工具")
    print(f"{'=' * 60}")

    from mcp.server import _DISPATCH

    passed = []
    failed = []
    for name, args in TOOL_CALLS:
        try:
            handler = _DISPATCH.get(name)
            if not handler:
                raise RuntimeError(f"tool not registered: {name}")
            result = handler(args)
            # call_tool 返回值可能是 dict，也可能带 status
            if isinstance(result, dict):
                ok = result.get("ok", result.get("status") == "ok" or "data" in result or result.get("content"))
                if ok is False:
                    raise RuntimeError(f"tool returned ok=false: {str(result)[:120]}")
            passed.append(name)
            print(f"  [PASS] {name}({json.dumps(args, ensure_ascii=False)[:80]})")
        except Exception as e:
            failed.append((name, str(e)))
            print(f"  [FAIL] {name}: {str(e)[:120]}")

    print(f"\n{'=' * 60}")
    print(f"PASS: {len(passed)} / {len(TOOL_CALLS)}")
    print(f"FAIL: {len(failed)}")
    print(f"{'=' * 60}")
    if failed:
        for name, err in failed:
            print(f"  FAILED: {name} - {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
