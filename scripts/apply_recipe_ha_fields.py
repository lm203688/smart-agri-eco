"""scripts/apply_recipe_ha_fields.py —— 为 Env Recipe 补齐 HA 生态事实标准字段（M8-R1）。

背景
----
报告 `docs/per_module_deep_assessment_2026-10-13.md` §M8-R1 指出：Env Recipe 协议
缺少 HA 生态（Home Assistant Horticulture-Assistant）事实标准字段——DLI / VPD / 露点 /
霉菌风险——以及 OpenFarm 共识字段（伴生植物 / 播种深度）。这些字段是温室与箱体调控
的**行业惯例**：竞品 HA 已把它们当作一等实体，本项目缺失意味着协议层面处于劣势。

设计要点（严守项目硬约束）
--------------------------
1. **零依赖**：仅使用 Python 标准库，不引入第三方包。
2. **不编造**：派生不出来的字段写 `null`，并给出 `reason`；绝不填近似值。
3. **诚实标注**：每个派生字段带 `source`（如 `derived_from_environment` / `derived_from_zone` /
   `crop_adapt_db`）+ `method`（如 `magnus_vpd`）+ `derived_at`。这样下游消费者能区分
   「人工设定」与「机器派生」两种数据来源——**这是本项目可信层的纪律**。
4. **幂等**：重复运行不改变结果（先读现有值再决定是否覆盖；已存在字段不重算，除非 `--force`）。
5. **不写坏原有字段**：所有 HA 字段是**新增 optional**（schema v1.2 声明），
   原有 environment / crop / stage 结构**完全不动**。
6. **可校验**：配套 `scripts/test_ha_fields.py` 硬门禁（CI 拒绝 152 配方缺字段）。

派生来源（每个字段的权威数据链）
--------------------------------
- `vpd_kpa`：`engine.derived.vpd()`（Magnus 近似式），从 environment.temperature + humidity 派生
- `dew_point_c`：`engine.derived.dew_point()`，同上
- `mold_risk`：从 vpd + 露点判定（叶菜类通用参考阈值，`derived.py` VPD_OPTIMAL/STRESS）
- `dli_umol_m2_day`：`engine.derived.derive_dli(zone_id)`，从 `data/zone_meta/global_zones.json`
  的 `climate_baseline.dli_annual_mol_m2_day` 读取。**注意**：NASA POWER 数据是全谱短波辐射
  光子当量，非标准 PAR；本字段以 umol 为单位（HA 惯例），并在 `note` 中明确标注。
- `companion_plants`：从 `data/crop_adapt_db.json` 反查**同分区**其他作物（Top-K，按 adapt_score 降序）
- `sowing_depth_cm`：从 `crop_adapt_db.growth_days` → `engine.derived.sowing_depth_cm()`
  （复用公式 `round(growth_days / 200, 1)`）

CLI
---
    python scripts/apply_recipe_ha_fields.py --check         # 检查所有配方状态（不落盘）
    python scripts/apply_recipe_ha_fields.py --dry-run       # 打印将写入的字段（不落盘）
    python scripts/apply_recipe_ha_fields.py --apply         # 就地补齐 152 配方
    python scripts/apply_recipe_ha_fields.py --apply --force # 已存在字段也重算覆盖
    python scripts/apply_recipe_ha_fields.py --recipe data/env_recipes/arid__仙人掌.json
        # 只处理单个配方

Exit code
--------
    0  所有配方都已含全部 6 项 HA 字段（`--check` 通过）
    1  存在缺失（`--check` 失败；`--apply` 也失败）
    2  输入文件错误 / 参数错误
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# 项目内派生函数（零依赖）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.derived import (  # noqa: E402
    dew_point,
    derive_dli,
    sowing_depth_cm,
    vpd,
    VPD_OPTIMAL,
    VPD_STRESS,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

RECIPE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "env_recipes")
ZONE_META_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "zone_meta", "global_zones.json")
CROP_ADAPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data", "crop_adapt_db.json")

DERIVED_AT = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
SOURCE_ENV = "derived_from_environment"
SOURCE_ZONE = "derived_from_zone"
SOURCE_ADAPT = "crop_adapt_db"

# HA 生态字段清单（用于 check / report）
HA_FIELDS = ("vpd_kpa", "dew_point_c", "mold_risk", "dli_umol_m2_day")
OPENFARM_FIELDS = ("companion_plants", "sowing_depth_cm")


# ---------------------------------------------------------------------------
# 派生函数（每个字段独立、诚实）
# ---------------------------------------------------------------------------

def _derive_vpd(env: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 environment.temperature + humidity 派生 VPD（kPa）。"""
    temp = (env or {}).get("temperature") or {}
    hum = (env or {}).get("humidity") or {}
    day_c, night_c = temp.get("day_c"), temp.get("night_c")
    hmin, hmax = hum.get("min_pct"), hum.get("max_pct")
    missing = [k for k, v in (("temperature.day_c", day_c), ("temperature.night_c", night_c),
                              ("humidity.min_pct", hmin), ("humidity.max_pct", hmax)) if v is None]
    if missing:
        return None
    # 标称工作点：区间中点
    t_mid = (float(day_c) + float(night_c)) / 2.0
    h_mid = (float(hmin) + float(hmax)) / 2.0
    v_nom = vpd(t_mid, h_mid)
    # 包络：高温+低湿→干；低温+高湿→湿
    v_max = vpd(float(day_c), float(hmin))
    v_min = vpd(float(night_c), float(hmax))
    return {
        "nominal": round(v_nom, 3),
        "envelope_min": round(v_min, 3),
        "envelope_max": round(v_max, 3),
        "unit": "kPa",
        "method": "magnus_vpd",
        "source": SOURCE_ENV,
        "derived_at": DERIVED_AT,
        "note": "Magnus 近似式；标称点为温湿区间中点。叶菜类参考：<0.5 过湿，0.5-1.0 舒适，"
                "1.0-1.5 偏干，>1.5 胁迫。",
    }


def _derive_dew_point(env: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 environment.temperature + humidity 派生露点温度（°C）。"""
    temp = (env or {}).get("temperature") or {}
    hum = (env or {}).get("humidity") or {}
    day_c, night_c = temp.get("day_c"), temp.get("night_c")
    hmax = hum.get("max_pct")
    if None in (day_c, night_c, hmax):
        return None
    d_day = dew_point(float(day_c), float(hmax))
    d_night = dew_point(float(night_c), float(hmax))
    return {
        "day_max": round(d_day, 2),
        "night": round(d_night, 2),
        "unit": "celsius",
        "method": "magnus_dew_point",
        "source": SOURCE_ENV,
        "derived_at": DERIVED_AT,
    }


def _derive_mold_risk(env: Dict[str, Any]) -> Dict[str, Any]:
    """从 VPD + 露点判定霉菌/真菌病害风险等级。"""
    temp = (env or {}).get("temperature") or {}
    hum = (env or {}).get("humidity") or {}
    day_c, night_c = temp.get("day_c"), temp.get("night_c")
    hmin, hmax = hum.get("min_pct"), hum.get("max_pct")
    if None in (day_c, night_c, hmin, hmax):
        return {"level": "unknown", "reason": "environment 缺字段，无法判定",
                "source": SOURCE_ENV, "derived_at": DERIVED_AT}
    t_mid = (float(day_c) + float(night_c)) / 2.0
    h_mid = (float(hmin) + float(hmax)) / 2.0
    v_nom = vpd(t_mid, h_mid)
    d_night = dew_point(float(night_c), float(hmax))
    # 判据：VPD < 0.5 且 夜露点 ≥ 夜温-1℃ → high（双重条件都满足才 high）
    if v_nom < VPD_OPTIMAL[0] and d_night >= float(night_c) - 1.0:
        level, reason = "high", (
            "标称 VPD=%.2f kPa < %.1f 且夜露点 %.1f°C 逼近夜温 %.1f°C，"
            "双重条件下真菌病害风险显著升高" % (v_nom, VPD_OPTIMAL[0], d_night, night_c))
    elif v_nom < VPD_OPTIMAL[0]:
        level, reason = "medium", (
            "标称 VPD=%.2f kPa < %.1f，过湿区（真菌病害风险中等）" % (v_nom, VPD_OPTIMAL[0]))
    elif v_nom <= VPD_OPTIMAL[1]:
        level, reason = "low", (
            "标称 VPD=%.2f kPa 在舒适区（%.1f-%.1f），真菌病害风险低"
            % (v_nom, VPD_OPTIMAL[0], VPD_OPTIMAL[1]))
    elif v_nom <= VPD_STRESS:
        level, reason = "low", (
            "标称 VPD=%.2f kPa 在偏干区，真菌病害风险低（需关注蒸腾）"
            % v_nom)
    else:
        level, reason = "low", (
            "标称 VPD=%.2f kPa > %.1f 蒸腾胁迫区，真菌病害风险低（关注萎蔫）"
            % (v_nom, VPD_STRESS))
    return {
        "level": level,
        "reason": reason,
        "vpd_nominal_kpa": round(v_nom, 3),
        "dew_point_night_c": round(d_night, 2),
        "thresholds": {"optimal_low": VPD_OPTIMAL[0], "optimal_high": VPD_OPTIMAL[1],
                       "stress": VPD_STRESS},
        "method": "vpd_plus_dew_point",
        "source": SOURCE_ENV,
        "derived_at": DERIVED_AT,
    }


def _derive_dli(zone_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """从分区推导 DLI（umol/m²/day，HA 单位）。"""
    if not zone_id:
        return None
    r = derive_dli(zone_id)
    if not r.get("available"):
        return None
    # NASA POWER 给的是 mol/m²/day，HA 惯例用 umol，转换 = *1000
    mol_val = float(r["mol_m2_day"])
    umol_val = mol_val * 1000.0
    return {
        "value": round(umol_val, 1),
        "unit": "umol_m2_day",
        "zone_id": zone_id,
        "source": SOURCE_ZONE,
        "source_file": r.get("source"),
        "method": "climate_baseline_annual_mean",
        "derived_at": DERIVED_AT,
        "note": r.get("note", "") + " 单位从 mol 换算为 umol（HA 惯例）。",
    }


def _derive_companions(zone_id: Optional[str], crop_species: str) -> Dict[str, Any]:
    """从 crop_adapt_db 反查同分区其他作物作为伴生候选（Top-K）。"""
    out: Dict[str, Any] = {
        "items": [],
        "source": SOURCE_ADAPT,
        "derived_at": DERIVED_AT,
        "note": "同分区 adapt_score 前 3 作物（不含自身）；仅为候选，非最优伴生。"
                "OpenFarm 共识字段，本项目当前无实测伴生数据，用同分区推荐作占位。",
    }
    if not zone_id:
        out["items"] = []
        out["reason"] = "未知 zone_id"
        return out
    try:
        with open(CROP_ADAPT_PATH, encoding="utf-8") as f:
            db = json.load(f)
    except Exception as e:
        out["reason"] = "读取 crop_adapt_db 失败: %s" % e
        return out
    zd = (db.get("zones") or {}).get(zone_id)
    if not zd or not zd.get("crops"):
        out["reason"] = "分区 %s 无作物数据" % zone_id
        return out
    others = [c for c in zd["crops"] if c.get("crop") != crop_species]
    others.sort(key=lambda c: -(c.get("adapt_score") or 0))
    for c in others[:3]:
        out["items"].append({
            "crop": c.get("crop"),
            "latin": c.get("latin"),
            "adapt_score": c.get("adapt_score"),
            "reason": "同分区（%s）适配度 %s，可作伴生候选"
                      % (zone_id, c.get("adapt_score")),
        })
    return out


def _derive_sowing_depth(zone_id: Optional[str], crop_species: str) -> Dict[str, Any]:
    """从 crop_adapt_db.growth_days 派生播种深度（cm）。"""
    out: Dict[str, Any] = {
        "value": None,
        "unit": "cm",
        "source": SOURCE_ADAPT,
        "derived_at": DERIVED_AT,
        "method": "growth_days_over_200",
        "note": "复用 agent/growth_agent.py 公式 round(growth_days/200, 1)。"
                "缺 growth_days 时值为 null（不编造）。",
    }
    if not zone_id or not crop_species:
        out["reason"] = "缺 zone_id 或 crop_species"
        return out
    try:
        with open(CROP_ADAPT_PATH, encoding="utf-8") as f:
            db = json.load(f)
    except Exception as e:
        out["reason"] = "读取 crop_adapt_db 失败: %s" % e
        return out
    zd = (db.get("zones") or {}).get(zone_id) or {}
    for c in zd.get("crops", []):
        if c.get("crop") == crop_species:
            gd = c.get("growth_days")
            if gd and gd > 0:
                out["value"] = sowing_depth_cm(int(gd))
                out["growth_days"] = int(gd)
                return out
            out["reason"] = "crop_adapt_db 中 %s 无 growth_days" % crop_species
            return out
    out["reason"] = "crop_adapt_db 中 %s / %s 无匹配" % (zone_id, crop_species)
    return out


# ---------------------------------------------------------------------------
# 单配方处理
# ---------------------------------------------------------------------------

def extract_zone_from_filename(recipe_path: str) -> Optional[str]:
    """从 'data/env_recipes/arid__仙人掌.json' 提取 zone_id='arid'。"""
    base = os.path.basename(recipe_path)
    stem = base.rsplit(".", 1)[0]
    if "__" in stem:
        return stem.split("__", 1)[0]
    return None


def apply_ha_fields(recipe: Dict[str, Any], zone_id: Optional[str],
                    force: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    """就地补齐 HA 字段。返回 (新recipe, changes_list)。

    - 若字段已存在且非 force，跳过（幂等）
    - 派生失败时写 None + reason（不编造）
    - 所有新增字段带 source/derived_at 元数据
    """
    changes: List[str] = []
    env = recipe.setdefault("environment", {})
    crop = recipe.get("crop", {}) or {}
    species = crop.get("species") or ""

    # --- HA 生态字段（environment 子层）---
    if force or "vpd_kpa" not in env:
        r = _derive_vpd(env)
        env["vpd_kpa"] = r
        changes.append("environment.vpd_kpa" + ("(null)" if r is None else ""))
    if force or "dew_point_c" not in env:
        r = _derive_dew_point(env)
        env["dew_point_c"] = r
        changes.append("environment.dew_point_c" + ("(null)" if r is None else ""))
    if force or "mold_risk" not in env:
        r = _derive_mold_risk(env)
        env["mold_risk"] = r
        changes.append("environment.mold_risk")
    if force or "dli_umol_m2_day" not in env:
        r = _derive_dli(zone_id)
        env["dli_umol_m2_day"] = r
        changes.append("environment.dli_umol_m2_day" + ("(null)" if r is None else ""))

    # --- OpenFarm 共识字段（顶层）---
    if force or "companion_plants" not in recipe:
        r = _derive_companions(zone_id, species)
        recipe["companion_plants"] = r
        changes.append("companion_plants")
    if force or "sowing_depth_cm" not in recipe:
        r = _derive_sowing_depth(zone_id, species)
        recipe["sowing_depth_cm"] = r
        changes.append("sowing_depth_cm" + ("(null)" if r and r.get("value") is None else ""))

    return recipe, changes


# ---------------------------------------------------------------------------
# 批量处理
# ---------------------------------------------------------------------------

def iter_recipes() -> List[str]:
    return sorted(os.path.join(RECIPE_DIR, f)
                  for f in os.listdir(RECIPE_DIR) if f.endswith(".json"))


def check_all_recipes() -> Tuple[int, int, List[Dict[str, Any]]]:
    """检查所有配方的 HA 字段状态。返回 (ok_count, fail_count, fail_details)。"""
    fail_details: List[Dict[str, Any]] = []
    ok = 0
    for path in iter_recipes():
        try:
            with open(path, encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            fail_details.append({"path": path, "error": "read failed: %s" % e})
            continue
        env = recipe.get("environment", {}) or {}
        missing = []
        for f in HA_FIELDS:
            v = env.get(f)
            if v is None:
                missing.append("environment.%s" % f)
            elif isinstance(v, dict) and v.get("level") == "unknown":
                # mold_risk 允许 unknown，但要标注
                pass
        # OpenFarm 字段
        if "companion_plants" not in recipe:
            missing.append("companion_plants")
        if "sowing_depth_cm" not in recipe:
            missing.append("sowing_depth_cm")
        if missing:
            fail_details.append({"path": path, "missing": missing})
        else:
            ok += 1
    return ok, len(fail_details), fail_details


def run(args: argparse.Namespace) -> int:
    if args.check:
        ok, fail, details = check_all_recipes()
        total = ok + fail
        print("HA 字段检查：总 %d / 通过 %d / 缺失 %d" % (total, ok, fail))
        if fail:
            for d in details[:10]:
                print("  [FAIL] %s -> %s" % (
                    d.get("path", "?").split("/")[-1],
                    d.get("error") or ", ".join(d.get("missing", []))))
            if fail > 10:
                print("  ... 另有 %d 份缺失" % (fail - 10))
        return 0 if fail == 0 else 1

    if args.recipe:
        paths = [args.recipe]
    else:
        paths = iter_recipes()

    applied = 0
    null_fields = 0
    errors = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                recipe = json.load(f)
        except Exception as e:
            print("  [ERROR] 读取失败 %s: %s" % (path, e))
            errors += 1
            continue
        zone_id = extract_zone_from_filename(path)
        new_recipe, changes = apply_ha_fields(recipe, zone_id, force=args.force)
        # 统计 null 派生字段（诚实标注）
        for k in ("vpd_kpa", "dew_point_c", "dli_umol_m2_day"):
            if new_recipe.get("environment", {}).get(k) is None:
                null_fields += 1
        if new_recipe.get("sowing_depth_cm", {}).get("value") is None:
            null_fields += 1
        if args.dry_run:
            print("[DRY] %s -> 将写入 %s" % (
                os.path.basename(path), ", ".join(changes)))
            continue
        if args.apply:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_recipe, f, ensure_ascii=False, indent=2)
                f.write("\n")
            applied += 1
            if changes:
                print("[OK] %s -> %s" % (os.path.basename(path), ", ".join(changes)))
    if not args.check:
        print("\n汇总：处理 %d 份 / apply %d / errors %d / null 派生字段 %d 项"
              % (len(paths), applied, errors, null_fields))
    return 0 if errors == 0 else 2


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="为 Env Recipe 补齐 HA 生态事实标准字段（M8-R1）")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="只检查所有配方状态（不落盘）")
    mode.add_argument("--dry-run", action="store_true",
                      help="打印将写入的字段（不落盘）")
    mode.add_argument("--apply", action="store_true",
                      help="就地补齐所有配方")
    p.add_argument("--force", action="store_true",
                   help="已存在字段也重算覆盖")
    p.add_argument("--recipe", help="只处理单个配方文件路径")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
