"""条件锚定执行器（借鉴 Hypit 的「词级锚定」替代固定时间轴）。

为什么需要它
------------
Hypit 做视频生成的关键洞察是：**不要锚定时间轴的第几秒，要锚定画面上
出现的那个词**。秒是固定刻度，词是内容条件——条件满足了才播下一步。

本项目的 Env Recipe 同理：它天然是**参数集**（温度/湿度/pH/灌溉量阈值 +
异常处理条件），却没有执行器把参数集翻译成「现在该做什么」。此前只有两条
路：按固定时间排程（每天浇一次，不管今天湿度 92% 还是 30%），或者全靠人
看到症状再手动查。

这里做的是**把参数集转成可判定的条件锚点**：
    阈值锚点  来自 recipe.environment（湿度上限、温度昼夜值、pH、日灌溉量）
    异常锚点  来自 recipe.exception_handling（condition 文本 → 关键词匹配）
然后给出 `next_actions()`：**ready**（条件已满足、该执行）与 **waiting**
（条件未满足、附当前值与缺口），以及时间锚定 vs 条件锚定的对照解释。

硬约束
------
- 零第三方依赖，纯 stdlib。
- **只读 recipe**：不修改配方文件，不写入 execution_log（那是回流层的事）。
- 缺失/NaN/bool 观测值一律视为「未满足」——与 PestAgent 证据门控同一约定。
  （bool 是 int 子类，必须显式排除，否则 True 会被当成 1 参与比较。）
- 锚点判定全部可机读：field/op/value 三元组，可离线复核。

用法
----
    from engine.recipe_scheduler import anchors_from_recipe, next_actions

    recipe = json.load(open("data/env_recipes/<某作物>.json"))
    anchors = anchors_from_recipe(recipe)
    out = next_actions(recipe, {"temp_c": 38, "humidity_pct": 92, "ph": 8.0})
    # -> ready: [遮阴, 通风降湿, 调 pH]   waiting: [日灌溉补水 ...]

    python -m engine.recipe_scheduler        # 跑一次演示
"""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPE_GLOB = os.path.join(ROOT, "data", "env_recipes", "*.json")

OPS = (">=", ">", "<=", "<", "==", "!=")

#: 观测字段别名：recipe 里的环境量名 → 观测输入里可用的键
FIELD_ALIASES = {
    "temp_c": ("temp_c", "temp", "temperature", "day_temp"),
    "humidity_pct": ("humidity_pct", "humidity", "rh"),
    "ph": ("ph",),
    "water_ml": ("water_ml", "water_ml_given", "water_ml_day_actual", "irrigation_ml"),
    "ppfd": ("ppfd", "light", "lux"),
    "ec": ("ec", "conductivity"),
}


# ---------------------------------------------------------------------------
# 判定原语
# ---------------------------------------------------------------------------
def _num(v: Any) -> Optional[float]:
    """取有效数值：排除 None / NaN / bool（bool 是 int 子类，必须先排）。"""
    if isinstance(v, bool):
        return None
    if not isinstance(v, (int, float)):
        return None
    f = float(v)
    if f != f:  # NaN
        return None
    return f


def evaluate(anchor: Dict[str, Any], observations: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """判定单个锚点是否满足。返回 satisfied/current/gap + 可读说明。"""
    obs = observations or {}
    field = anchor.get("field", "")
    op = anchor.get("op", "")
    want = _num(anchor.get("value"))

    cur = None
    for alias in FIELD_ALIASES.get(field, (field,)):
        if alias in obs:
            cur = _num(obs[alias])
            break

    if want is None:
        return {"satisfied": False, "current": None, "gap": None,
                "reason": "锚点缺省值非法：%r" % anchor.get("value")}
    if cur is None:
        return {"satisfied": False, "current": None, "gap": None,
                "reason": "缺观测字段 %s（别名 %s）" % (field, FIELD_ALIASES.get(field, (field,)))}
    if op not in OPS:
        return {"satisfied": False, "current": cur, "gap": None,
                "reason": "未知比较符 %r" % op}

    ok = {
        ">=": cur >= want, ">": cur > want,
        "<=": cur <= want, "<": cur < want,
        "==": abs(cur - want) < 1e-9, "!=": abs(cur - want) >= 1e-9,
    }[op]

    return {
        "satisfied": bool(ok),
        "current": round(cur, 3),
        "target": round(want, 3),
        "op": op,
        "gap": round(abs(cur - want), 3),
        "reason": "%s %s %.3f → %s" % (field, op, want, "满足" if ok else "未满足"),
    }


# ---------------------------------------------------------------------------
# 锚点抽取
# ---------------------------------------------------------------------------
def _a(aid: str, name: str, field: str, op: str, value: Any,
       action: str, severity: str, source: str) -> Dict[str, Any]:
    return {"id": aid, "name": name, "kind": "threshold", "field": field,
            "op": op, "value": value, "action": action,
            "severity": severity, "source": source}


def anchors_from_recipe(recipe: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 Env Recipe 抽取全部条件锚点。

    两类来源：
      1. environment 阈值 —— 温度昼夜、湿度上下限、pH、日灌溉量
      2. exception_handling —— condition 文本转关键词锚点
    """
    out: List[Dict[str, Any]] = []
    env = (recipe or {}).get("environment") or {}

    temp = env.get("temperature") or {}
    if temp.get("day_c") is not None:
        out.append(_a("temp_day_high", "白天温度过高", "temp_c", ">=",
                      temp["day_c"],
                      "遮阴或降功率（拉遮阳网/移入室内），避免叶片灼伤",
                      "warn", "environment.temperature.day_c"))
    if temp.get("night_c") is not None:
        out.append(_a("temp_night_low", "夜间温度过低", "temp_c", "<=",
                      temp["night_c"],
                      "保温（加盖薄膜/靠近热源），夜间低温会停滞生长",
                      "warn", "environment.temperature.night_c"))

    hum = env.get("humidity") or {}
    if hum.get("max_pct") is not None:
        out.append(_a("humidity_high", "湿度超过上限", "humidity_pct", ">=",
                      hum["max_pct"],
                      "加强通风并减少地表水膜，高湿是真菌病害的主要诱因",
                      "warn", "environment.humidity.max_pct"))
    if hum.get("min_pct") is not None:
        out.append(_a("humidity_low", "湿度低于下限", "humidity_pct", "<=",
                      hum["min_pct"],
                      "增湿（喷雾/加湿），过干会加剧蒸腾与气孔关闭",
                      "info", "environment.humidity.min_pct"))

    wn = env.get("water_nutrient") or {}
    ph = wn.get("ph")
    if ph is not None:
        out.append(_a("ph_high", "pH 偏高", "ph", ">", ph,
                      "按配方下调 pH（酸性调节剂），pH 越界会导致营养锁肥",
                      "warn", "environment.water_nutrient.ph"))
        out.append(_a("ph_low", "pH 偏低", "ph", "<", ph,
                      "按配方上调 pH（碱性调节剂），过酸同样锁肥",
                      "warn", "environment.water_nutrient.ph"))
    if wn.get("water_ml_day") is not None:
        out.append(_a("water_shortfall", "日灌溉量不足", "water_ml", "<=",
                      wn["water_ml_day"],
                      "按配方补灌至日额度（分次少量优于一次大水）",
                      "info", "environment.water_nutrient.water_ml_day"))

    # 异常处理条款 → 关键词锚点（无 field/op/value，走文本匹配）
    for i, e in enumerate((recipe or {}).get("exception_handling") or []):
        cond = str(e.get("condition") or "").strip()
        if not cond:
            continue
        out.append({
            "id": "exception_%02d" % i,
            "name": "异常条款：" + cond[:24],
            "kind": "keyword",
            "field": None,
            "op": None,
            "value": None,
            "keywords": _keywords_of(cond),
            "action": str(e.get("action") or ""),
            "severity": str(e.get("severity") or "warn"),
            "source": "exception_handling[%d]" % i,
        })
    return out


def _keywords_of(cond: str) -> List[str]:
    """从异常条款文本抽关键词：「出现「冻害」相关症状」→ ['冻害']。"""
    quoted = re.findall(r"[「『\"][^」』\"]+[」』\"]", cond)
    kws = [q.strip("「」『』\"") for q in quoted if q.strip("「」『』\"")]
    if not kws:
        # 无引号时按「病/虫/害/旱/涝/冻/灼」等风险词切
        kws = [w for w in re.split(r"[^\u4e00-\u9fff]+", cond)
               if len(w) >= 2 and w not in ("出现", "相关", "症状", "异常", "情况")]
    return kws[:6]


def keyword_hit(anchor: Dict[str, Any], text: str) -> bool:
    """关键词锚点是否在给定文本（症状描述/日志）中出现。"""
    kws = anchor.get("keywords") or []
    t = text or ""
    return any(k in t for k in kws)


# ---------------------------------------------------------------------------
# 决策
# ---------------------------------------------------------------------------
def next_actions(recipe: Dict[str, Any],
                 observations: Optional[Dict[str, Any]] = None,
                 symptom_text: str = "",
                 fired: Optional[Sequence[str]] = None,
                 cooldown_fields: Optional[Sequence[str]] = None,
                 anchors: Optional[List[Dict[str, Any]]] = None,
                 ) -> Dict[str, Any]:
    """决定「现在该做什么」。

    fired           本周期已执行过的锚点 id（用于去重，避免重复触发同一动作）
    cooldown_fields 本周期已触发过的字段（同字段本周期只报一次）

    返回 ready（该执行）/ waiting（未满足，附缺口）/ summary。
    """
    obs = observations or {}
    skip = set(fired or [])
    cool = set(cooldown_fields or [])
    src = anchors if anchors is not None else anchors_from_recipe(recipe)

    ready: List[Dict[str, Any]] = []
    waiting: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for a in src:
        if a["id"] in skip:
            skipped.append(a["id"])
            continue
        if a.get("kind") == "keyword":
            if symptom_text and keyword_hit(a, symptom_text):
                ready.append({"anchor_id": a["id"], "name": a["name"],
                              "severity": a["severity"], "action": a["action"],
                              "matched": "症状文本命中「%s」"
                                         % "、".join(a.get("keywords") or [])})
            else:
                waiting.append({"anchor_id": a["id"], "name": a["name"],
                                "severity": a["severity"], "action": a["action"],
                                "gap": "需出现关键词：" + "、".join(a.get("keywords") or [])})
            continue

        ev = evaluate(a, obs)
        if not ev["satisfied"]:
            waiting.append({"anchor_id": a["id"], "name": a["name"],
                            "severity": a["severity"], "action": a["action"],
                            "current": ev.get("current"),
                            "target": ev.get("target"),
                            "op": ev.get("op"), "gap": ev.get("gap"),
                            "reason": ev["reason"]})
            continue
        if a["field"] in cool:
            skipped.append(a["id"])
            continue
        ready.append({"anchor_id": a["id"], "name": a["name"],
                      "severity": a["severity"], "action": a["action"],
                      "current": ev["current"], "target": ev["target"],
                      "gap": ev["gap"], "reason": ev["reason"]})

    sev_rank = {"critical": 0, "error": 1, "warn": 2, "info": 3, "": 4}
    ready.sort(key=lambda r: sev_rank.get(str(r.get("severity")), 4))
    waiting.sort(key=lambda w: sev_rank.get(str(w.get("severity")), 4))

    return {
        "ready": ready,
        "waiting": waiting,
        "skipped": skipped,
        "summary": {
            "anchors_total": len(src),
            "ready_count": len(ready),
            "waiting_count": len(waiting),
            "observations_used": sorted(obs.keys()),
            "policy": "条件满足才触发；缺观测一律视为未满足，不猜测",
        },
    }


# ---------------------------------------------------------------------------
# 时间锚定 vs 条件锚定 对照（可解释性）
# ---------------------------------------------------------------------------
def compare_modes(recipe: Dict[str, Any],
                  observations: Optional[Dict[str, Any]] = None,
                  schedule: Optional[List[Dict[str, Any]]] = None,
                  symptom_text: str = "") -> Dict[str, Any]:
    """同一 recipe、同一观测下，两种排程模式的差异。

    schedule 默认给一个「每日例行」时间锚定计划（灌溉 + 巡查），用于对照。
    输出三类差异：
      time_only     时间模式会做、条件模式认为不必做（浪费/白做）
      condition_only 条件模式会做、时间模式漏做（风险）
      both          两模式都会做
    """
    obs = observations or {}
    cond = next_actions(recipe, obs, symptom_text=symptom_text)
    sched = schedule or [
        {"id": "daily_irrigation", "name": "每日灌溉", "field": "water_ml"},
        {"id": "daily_patrol", "name": "每日巡查", "field": None},
    ]

    time_ids = {s["id"] for s in sched}
    cond_ready = {r["anchor_id"] for r in cond["ready"]}

    time_only = [s for s in sched if s["id"] not in cond_ready]
    condition_only = [r for r in cond["ready"] if r["anchor_id"] not in time_ids]
    both = [r for r in cond["ready"] if r["anchor_id"] in time_ids]

    return {
        "mode_a": "固定时间排程（daily schedule）",
        "mode_b": "条件锚定（condition-triggered）",
        "time_only": time_only,
        "condition_only": condition_only,
        "both": both,
        "waiting_under_condition": cond["waiting"],
        "interpretation": {
            "time_only": "按时间会执行、按条件不必执行——时间模式下的白做动作",
            "condition_only": "按条件需要执行、时间模式漏掉的动作（风险项）",
            "both": "两种模式都会执行的动作",
        },
    }


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------
def load_recipe(path: str = "", crop: str = "", zone: str = "") -> Dict[str, Any]:
    """按路径 / 作物名 / 分区名加载一份 Env Recipe。"""
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    want_crop = crop.strip() if crop else ""
    want_zone = zone.strip() if zone else ""
    for p in sorted(glob.glob(RECIPE_GLOB)):
        try:
            with open(p, "r", encoding="utf-8") as f:
                r = json.load(f)
        except Exception:
            continue
        sp = str((r.get("crop") or {}).get("species") or "")
        base = os.path.basename(p)
        if want_crop and sp == want_crop:
            if not want_zone or want_zone in base:
                return r
    raise FileNotFoundError("未找到配方：crop=%r zone=%r" % (crop, zone))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _demo() -> None:
    try:
        recipe = load_recipe(crop="番茄")
    except FileNotFoundError:
        recipe = load_recipe(crop="生菜")
    print("配方作物:", (recipe.get("crop") or {}).get("species"))

    anchors = anchors_from_recipe(recipe)
    print("\n[锚点] 共 %d 个（阈值 %d / 关键词 %d）"
          % (len(anchors),
             sum(1 for a in anchors if a["kind"] == "threshold"),
             sum(1 for a in anchors if a["kind"] == "keyword")))
    for a in anchors:
        if a["kind"] == "threshold":
            print("  %-16s %-14s %s %s %s" % (a["id"], a["name"],
                                              a["field"], a["op"], a["value"]))
        else:
            print("  %-16s %s 关键词=%s" % (a["id"], a["name"], a["keywords"]))

    obs = {"temp_c": 39, "humidity_pct": 93, "ph": 8.2, "water_ml": 20}
    print("\n[观测] %s" % obs)
    print("[症状] 「叶片发白有粉状物，疑似蚜虫或白粉病」")
    out = next_actions(recipe, obs, symptom_text="叶片发白有粉状物，疑似蚜虫")
    print("ready %d 条:" % len(out["ready"]))
    for r in out["ready"]:
        print("  - [%s] %s（%s）→ %s" % (r["severity"], r["name"], r.get("reason", ""),
                                         r["action"][:34]))
    print("waiting %d 条:" % len(out["waiting"]))
    for w in out["waiting"][:5]:
        print("  - %s | %s | 缺口 %s" % (w["name"], w.get("reason", ""), w.get("gap")))

    cmp_ = compare_modes(recipe, obs, symptom_text="蚜虫")
    print("\n[时间锚定 vs 条件锚定]")
    print("  time_only（时间模式白做）:", [s["name"] for s in cmp_["time_only"]])
    print("  condition_only（时间模式漏做）:", [r["name"] for r in cmp_["condition_only"]])
    print("  两种模式都会做:", [r["name"] for r in cmp_["both"]])


if __name__ == "__main__":
    _demo()
