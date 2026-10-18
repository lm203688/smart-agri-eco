#!/usr/bin/env python3
"""
core/crop_registry.py —— 作物命名的单一来源（S1.4）

背景（为什么需要它）
--------------------
项目里"作物"有三套互不相识的命名，三处各说各话：

  1. engine/agriworld_lite.py 的 @known_enum 里**硬编码** 7 个英文机理作物名
  2. data/env_recipes/ 的 120 个 species 中文名
  3. data/env_recipes/ 的 112 个 latin 学名

后果：校验口径漂移，"我们覆盖多少种作物"在论文里说不清；往配方库加一个新作物
也不会自动进入机理层枚举。本模块把三者统一为一个可复算的注册表。

结构
----
  ENGINE_CROPS      7    机理内核真正建模的作物（白名单，人工维护）
  ENGINE_TO_SPECIES 6    机理作物 ↔ 配方中文名对照（白名单，人工维护）
  RECIPE_SPECIES   120   程序化扫描 data/env_recipes/ 得到
  RECIPE_LATIN     112   程序化扫描 data/env_recipes/ 得到
  ALL_CROPS        union 给 @known_enum 使用的全量集合

诚实边界（如实暴露，不做美化）
------------------------------
  * **水稻缺口**：`rice` 在 152 份配方里**没有任何**对应条目，因此
    ENGINE_CROPS 有 7 个、但只有 6 个能查到中文名对照。这是配方库的真实覆盖
    缺口，不是 bug。用 `uncovered_engine_crops()` 随时可见。
  * `data/env_recipes/` 缺失时 RECIPE_* 退化为空集、ALL_CROPS 退化为
    ENGINE_CROPS，**不抛异常**（零依赖、可离线运行）。
  * 学名匹配只取**属名**（首个 token），因此同一属的不同种会归到同一个机理
    作物上（如 洋姜 Helianthus tuberosus 与 向日葵 Helianthus annuus 都归
    sunflower）。这是保守近似，已在 `notes()` 里声明。

用法
----
    python -m core.crop_registry
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 白名单（人工维护）
# ---------------------------------------------------------------------------

#: 机理内核实际建模的 7 个作物。与 engine.agriworld_lite.CROP_PARAMS 的键集合
#: 必须一致 —— 由 scripts/test_crop_registry.py 的漂移守卫持续校验。
ENGINE_CROPS: FrozenSet[str] = frozenset({
    "potato", "wheat", "soybean", "sunflower", "rice",
    "sweetpotato", "mungbean",
})

#: 机理作物 → 配方库中文名（按学名属名匹配，见下）
ENGINE_TO_SPECIES: Dict[str, str] = {
    "wheat":       "小麦",
    "potato":      "土豆",
    "soybean":     "大豆",
    "sunflower":   "向日葵",
    "sweetpotato": "红薯",
    "mungbean":    "绿豆",
    # rice：配方库中无对应条目，故意不写（见 uncovered_engine_crops）
}

#: 属名前缀 → 机理作物。用于把配方库的学名归约到机理作物。
GENUS_TO_ENGINE_CROP: Dict[str, str] = {
    "Triticum":          "wheat",
    "Solanum tuberosum": "potato",
    "Glycine max":       "soybean",
    "Helianthus":        "sunflower",
    "Ipomoea batatas":   "sweetpotato",
    "Vigna":             "mungbean",
    # rice（Oryza）故意不列：配方库无此作物
}


# ---------------------------------------------------------------------------
# 程序化扫描
# ---------------------------------------------------------------------------
def _recipes_dir() -> Path:
    return ROOT / "data" / "env_recipes"


def scan_recipes() -> Tuple[FrozenSet[str], FrozenSet[str], int]:
    """扫描 data/env_recipes/*.json，返回 (species 集合, latin 集合, 文件数)。

    目录缺失 / 单文件损坏时静默跳过，不抛异常。
    """
    species: set = set()
    latin: set = set()
    n_files = 0
    d = _recipes_dir()
    if not d.is_dir():
        return frozenset(), frozenset(), 0

    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        n_files += 1
        crop = doc.get("crop") or {}
        if not isinstance(crop, dict):
            continue
        s = crop.get("species")
        l = crop.get("latin")
        if isinstance(s, str) and s.strip():
            species.add(s.strip())
        if isinstance(l, str) and l.strip():
            latin.add(l.strip())
    return frozenset(species), frozenset(latin), n_files


RECIPE_SPECIES, RECIPE_LATIN, RECIPE_FILE_COUNT = scan_recipes()

#: 反向对照：配方中文名 → 机理作物（由 ENGINE_TO_SPECIES 生成，避免两处维护）
SPECIES_TO_ENGINE_CROP: Dict[str, str] = {
    v: k for k, v in ENGINE_TO_SPECIES.items()
}

#: 给 @known_enum 使用的全量作物集合（机理 + 配方中文名 + 学名）
ALL_CROPS: FrozenSet[str] = ENGINE_CROPS | RECIPE_SPECIES | RECIPE_LATIN


# ---------------------------------------------------------------------------
# 查询接口
# ---------------------------------------------------------------------------
def _normalize(name: object) -> str:
    return str(name).strip() if name is not None else ""


def is_known_crop(name: object) -> bool:
    """是否为注册表内已知名（三种命名任一命中即可）。"""
    n = _normalize(name)
    return bool(n) and n in ALL_CROPS


def normalize_crop(name: object) -> str:
    """归一到小写去空白形式；空值返回空串（不做静默默认）。"""
    n = _normalize(name)
    return n.lower() if n else ""


def species_to_engine_crop(species: object) -> str | None:
    """配方中文名 → 机理作物名；无对照返回 None（不编造映射）。"""
    return SPECIES_TO_ENGINE_CROP.get(_normalize(species))


def genus_to_engine_crop(latin: object) -> str | None:
    """学名 → 机理作物名（按属名匹配，见模块 docstring 的保守近似说明）。"""
    l = _normalize(latin)
    if not l:
        return None
    for genus, crop in GENUS_TO_ENGINE_CROP.items():
        if l.startswith(genus):
            return crop
    return None


def recipe_name_for_engine_crop(crop: str) -> str | None:
    """机理作物 → 配方中文名；无对照返回 None。"""
    return ENGINE_TO_SPECIES.get(crop.strip().lower())


def uncovered_engine_crops() -> List[str]:
    """ENGINE_CROPS 中在配方库里查不到中文名对照的作物（如实暴露覆盖缺口）。"""
    return sorted(c for c in ENGINE_CROPS if c not in ENGINE_TO_SPECIES)


def engine_crops_with_recipe_coverage() -> List[str]:
    """能在配方库里找到中文名对照的机理作物。"""
    return sorted(c for c in ENGINE_CROPS if c in ENGINE_TO_SPECIES)


def provenance() -> Dict[str, object]:
    """注册表的来源说明，供论文 Materials 章节直接引用。"""
    return {
        "engine_crops": {
            "n": len(ENGINE_CROPS),
            "names": sorted(ENGINE_CROPS),
            "source": "engine/agriworld_lite.py CROP_PARAMS（人工白名单同步）",
        },
        "recipe_species": {
            "n": len(RECIPE_SPECIES),
            "source": "data/env_recipes/*.json -> crop.species",
            "files_scanned": RECIPE_FILE_COUNT,
        },
        "recipe_latin": {
            "n": len(RECIPE_LATIN),
            "source": "data/env_recipes/*.json -> crop.latin",
        },
        "all_crops": {"n": len(ALL_CROPS)},
        "uncovered_engine_crops": uncovered_engine_crops(),
    }


def notes() -> List[str]:
    """诚实边界声明：论文与审稿回复时应逐条引用，不得省略。"""
    out = [
        "learned_from_genus: 学名归约按属名匹配，同属不同种会合并（洋姜与向日葵"
        "都归 sunflower）。",
        "uncovered: rice 在 152 份配方中无对应条目，机理层建模了 7 种作物但配方"
        "库只覆盖 6 种的中文命名。",
        "offline_safe: data/env_recipes/ 缺失时 RECIPE_* 为空集，ALL_CROPS 退化为"
        " ENGINE_CROPS，不抛异常。",
        "drift_guard: ENGINE_CROPS 与 CROP_PARAMS 的一致性由"
        " scripts/test_crop_registry.py 持续校验，防止两处漂移。",
    ]
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: List[str] | None = None) -> int:
    p = provenance()
    print("=== 作物命名单一来源（core/crop_registry.py） ===")
    print(f"机理作物 ENGINE_CROPS    : {p['engine_crops']['n']}  {p['engine_crops']['names']}")
    print(f"配方中文名 RECIPE_SPECIES: {p['recipe_species']['n']}  "
          f"(扫描 {p['recipe_species']['files_scanned']} 份配方)")
    print(f"配方学名 RECIPE_LATIN    : {p['recipe_latin']['n']}")
    print(f"合并 ALL_CROPS           : {p['all_crops']['n']}")
    print()
    print("机理作物 ↔ 配方中文名对照：")
    for crop in sorted(ENGINE_CROPS):
        sp = recipe_name_for_engine_crop(crop)
        print(f"  {crop:12s} -> {sp if sp else '⚠️ 配方库无对应条目'}")
    unc = uncovered_engine_crops()
    if unc:
        print(f"\n⚠️  覆盖缺口：{unc} 在配方库中查不到中文名对照")
    print()
    print("诚实边界：")
    for n in notes():
        print(f"  · {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
