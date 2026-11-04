# -*- coding: utf-8 -*-
"""任务3 · 工具 description agent 优化版

替换 mcp/server.py 中「【农业决策】xxx / 输入：根据工具参数，详见 inputSchema。
返回：{"success": true, "data": "工具执行结果"}」这类不可自解释的占位描述，
改为真正自解释、可让外部 agent 直接理解与使用的描述（工具级 + 属性级）。

零依赖，幂等（已替换则跳过）。用法：
    python scripts/fix_placeholder_descriptions.py
"""
import io
import sys

PATH = "mcp/server.py"

# (旧文本精确串, 新文本, 期望替换次数或 None=不限)
REPLACEMENTS = [
    # ---- match_zone ----
    (
        '"""【选址规划】纬度\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"纬度（度，北纬为正）；与 lon 必填"',
        1,
    ),
    # ---- season_advisory 工具级 ----
    (
        '"""【农业决策】（B1+B2）物候与播期：mode=planting_window 时给 12 个月均温'
        '返回无霜期与各作物最早/最晚安全播种日；mode=stage_days 时给作物+日均温'
        '返回出苗/开花/成熟天数；mode=calendar 时按 USDA 区+日期查外部日历（需数据到位）。\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"""（B1+B2）物候与播期查询。\n'
        '三种模式：planting_window=给 12 个月均温返回无霜期与各作物最早/最晚安全播种日；\n'
        'stage_days=给作物+日均温返回出苗/开花/成熟天数；calendar=按 USDA 区+日期查外部日历（需数据到位）。\n'
        'mode=planting_window 必填 monthly_mean_c；stage_days 必填 crop+mean_temp_c；calendar 必填 zone+date。\n'
        '返回：{"mode": "...", "result": {...}}"""',
        1,
    ),
    # ---- season_advisory.mode ----
    (
        '"""【农业决策】默认 planting_window\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"查询模式；默认 planting_window"',
        1,
    ),
    # ---- soil_profile 工具级 ----
    (
        '"""【土壤查询】（土壤降级路径）经纬度或分区 → 土壤剖面。优先查 ISRIC SoilGrids v2.0'
        '（在线点数据），不可用时降级为离线分区均值并明确标注 resolution=zone、confidence=low。'
        '可选传入 crop 做 pH 适宜性拟合。\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"ph": 6.5, "organic_matter": "2.1%", "drainage": "良好"}"""',
        '"""（土壤降级路径）经纬度或分区 → 土壤剖面。\n'
        '优先查 ISRIC SoilGrids v2.0 在线点数据；不可用时降级为离线分区均值，'
        '明确标注 resolution=zone、confidence=low。可选传入 crop 做 pH 适宜性拟合。\n'
        'lat+lon 或 zone_id 二选一必填；online=false 直接走离线分区数据（更快）。\n'
        '返回：{"ph": 6.5, "organic_matter": "2.1%", "drainage": "良好", "resolution": "point|zone", "confidence": 0.8}"""',
        1,
    ),
    # ---- soil_profile.lat ----
    (
        '"""【土壤查询】纬度（与 lon 同用；可与 zone_id 二选一）\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"ph": 6.5, "organic_matter": "2.1%", "drainage": "良好"}"""',
        '"纬度（度）；与 lon 必填，或传 zone_id"',
        1,
    ),
    # ---- soil_profile.lon ----
    (
        '"""【土壤查询】经度\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"ph": 6.5, "organic_matter": "2.1%", "drainage": "良好"}"""',
        '"经度（度）；与 lat 必填，或传 zone_id"',
        1,
    ),
    # ---- reconcile_climate.lat ----
    (
        '"""【农业决策】纬度\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"纬度（度，北纬为正）；必填"',
        1,
    ),
    # ---- query_lineage.crop ----
    (
        '"""【农业决策】作物名（中文）；与 zone_id 可组合\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"作物名（中文，如 番茄）；可与 zone_id 组合"',
        1,
    ),
    # ---- knowledge_query.kind ----
    (
        '"""【农业决策】查询类型\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"查询类型：summary/crops_by_zone/crops_by_risk/neighbors/traverse"',
        1,
    ),
    # ---- forecast.crop ----
    (
        '"""【农业决策】作物中文名（必填）\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"作物中文名（如 番茄）；必填"',
        1,
    ),
    # ---- server_card.if_none_match ----
    (
        '"""【服务卡片】客户端缓存的 ETag；命中时返回 not_modified 短路\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"客户端缓存的 ETag（来自上次 agri_server_card 的 etag）；命中时返回 not_modified 短路"',
        1,
    ),
    # ---- postharvest.crop ----
    (
        '"""【采后处理】作物中文名\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"作物中文名（如 番茄/生菜）；必填"',
        1,
    ),
    # ---- grow_batch_observe.observation ----
    (
        '"""【农业决策】Observation 对象（grow_batch.schema.json）\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"Observation 对象（grow_batch.schema.json）：含 batch_id、ts、metric（如 leaf_area/ph）、source（sensor/manual）"',
        1,
    ),
    # ---- grow_batch_action.action ----
    (
        '"""【农业决策】Action 对象（grow_batch.schema.json）\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"Action 对象（grow_batch.schema.json）：含 action_id、batch_id、ts、recommendation；真实执行需 dry_run=false"',
        1,
    ),
    # ---- grow_batch_status.batch_id / replay.batch_id（两处相同文本，全替换）----
    (
        '"""【农业决策】批次唯一 ID\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"批次唯一 ID（如 b_01）；必填"',
        None,
    ),
    # ---- grow_batch_status.include_events ----
    (
        '"""【农业决策】是否附带事件日志，默认 false\n'
        '输入：根据工具参数，详见 inputSchema。\n'
        '返回：{"success": true, "data": "工具执行结果"}"""',
        '"是否附带 append-only 事件日志，默认 false"',
        1,
    ),
]


def main() -> int:
    src = io.open(PATH, encoding="utf-8").read()
    total = 0
    for old, new, expect in REPLACEMENTS:
        n = src.count(old)
        if expect is not None and n != expect:
            print(f"[FAIL] 期望替换 {expect} 处，实际 {n} 处：{old[:40]!r}...")
            return 1
        if n == 0:
            print(f"[SKIP] 未找到（可能已替换）：{old[:40]!r}...")
            continue
        src = src.replace(old, new)
        total += n
        print(f"[OK] 替换 {n} 处：{old.splitlines()[0][:40]!r}...")
    io.open(PATH, "w", encoding="utf-8", newline="\n").write(src)
    print(f"\n共替换 {total} 处占位描述 → 自解释版。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
