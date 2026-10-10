"""一次性数据修复：VPD 硬告警 + license_scope / sources.license 缺失。

依据：test_engine_v4 报 4 类失败：
- arid__沙棘 night_c=-20 是冬季休眠值误用，VPD=0.36 过湿
- highland__青稞 night_c=4 导致 VPD=0.49 边界过湿
- 152 配方全部缺 license_scope
- 760 sources 条目缺 license（backfill_source_provenance.py 只补了 source_license）

原则：确定性、可复现、不编造、幂等。
"""
from __future__ import annotations
import json, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(ROOT, "data", "env_recipes")

# 1. 温度修正（VPD 硬告警修复）
# 依据：arid/hot_arid__沙棘 同属旱地/沙漠气候，hot_arid 的 night_c=8 已验证舒适；
#       青稞是高原作物，日 20 / 夜 8 是合理生长期范围（原 4°C 导致 VPD 边界过湿）
TEMP_FIXES = {
    "arid__沙棘": {"night_c": 8},
    "highland__青稞": {"night_c": 8},
}

# 2. license_scope 统一说明（对齐 CORE_OBJECTIVE §五 方案 A）
LICENSE_SCOPE = (
    "含 FAO/FAOSTAT（CC BY-NC-SA，非商用）来源时，整包不得作为付费资产转售。"
    " 数据始终免费开源；付费标的为服务能力（接入配额、优先响应、定制分区建模、企业部署支持）。"
    " 详见 docs/CORE_OBJECTIVE.md §五。"
)


def _license_from_title(title: str) -> str:
    """按 sources.title 前缀确定 license（对齐 backfill_source_provenance.py 的映射）。"""
    t = title.lower()
    if "fao" in t or "ecocrop" in t:
        return "CC BY-NC-SA 3.0 IGO"
    if "gaez" in t:
        return "CC BY 4.0"
    if "usa" in t or "usda" in t or "pubs.us" in t or "nass.usda" in t:
        return "Public Domain (US Government)"
    if "ipni" in t or "plants.usda" in t or "botanicus" in t:
        return "CC BY 3.0"
    if "gbif" in t:
        return "CC BY 1.0"
    if "中国作物栽培数据库" in title:
        return "unknown"
    return "unknown"


def apply():
    changed_temp = []
    changed_scope = 0
    changed_license = 0
    for p in sorted(glob.glob(os.path.join(RECIPES_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        mod = False

        # 1. 温度修正
        basename = os.path.basename(p)[:-5]
        if basename in TEMP_FIXES:
            env = d.setdefault("environment", {})
            temp = env.setdefault("temperature", {})
            for k, v in TEMP_FIXES[basename].items():
                if temp.get(k) != v:
                    temp[k] = v
                    mod = True
                    changed_temp.append(f"{basename}: {k}={v}")

        # 2. license_scope
        if not d.get("license_scope"):
            d["license_scope"] = LICENSE_SCOPE
            changed_scope += 1
            mod = True

        # 3. sources[].license
        for s in d.get("sources", []):
            if not s.get("license"):
                s["license"] = _license_from_title(s.get("title", ""))
                changed_license += 1
                mod = True

        if mod:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

    print(f"温度修正: {len(changed_temp)} 处")
    for x in changed_temp:
        print(f"  - {x}")
    print(f"license_scope 补齐: {changed_scope} 份配方")
    print(f"sources.license 补齐: {changed_license} 条")


if __name__ == "__main__":
    apply()
