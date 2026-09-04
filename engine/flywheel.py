"""
engine/flywheel.py —— 反馈闭环 / 主动学习

设计目标（对标 SwarmLabs engine/flywheel.py 的「数据飞轮」）：
    用户种植结果回流  →  校准 crop_adapt_db 的 adapt_score  →  下次推荐自动采用校准分

闭环如何生效（不破坏 seed 数据）：
    - 原始适配分保留为 ``seed_adapt_score``
    - 新增 ``measured_calibration`` 字段记录实测校准
    - ``adapt_score`` 被更新为「seed 与实测的 blended 分」，CropAgent 透明受益
    - 作物标注 ``calibrated: true/false``，诚实区分「文献聚合」与「实测校准」

反馈记录累积在 data/feedback_log.json，可独立复算。

用法：
    python -m engine.flywheel            # 跑一次示例反馈闭环并打印迭代报告
    python -m engine.flywheel --demo     # 同上
"""

from __future__ import annotations

import json
import os
import datetime
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULT_CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
_DEFAULT_FEEDBACK_LOG = os.path.join(ROOT, "data", "feedback_log.json")


def crop_db_path() -> str:
    """作物库路径。可用环境变量 AGRI_CROP_DB 覆盖（测试 / 隔离运行用）。

    覆盖路径必须真实存在，否则 fail fast：静默降级会导致所有查询返回空、
    校准全部「未找到」，输出全为 None 却没有任何报错（实测踩过）。
    """
    override = os.environ.get("AGRI_CROP_DB")
    if not override:
        return _DEFAULT_CROP_DB
    if not os.path.exists(override):
        raise ValueError(
            "AGRI_CROP_DB 指向的文件不存在: %r\n"
            "提示：Windows 上 Git Bash 的 /tmp 映射到 %%LOCALAPPDATA%%\\Temp，"
            "而 Python 按 C:\\tmp 解析——请用 Windows 风格绝对路径。" % override
        )
    return override


def feedback_log_path() -> str:
    """反馈日志路径。可用环境变量 AGRI_FEEDBACK_LOG 覆盖（测试 / 隔离运行用）。

    设计动机：record_feedback 会真的写盘。若路径固定，单测与 CI 每次运行都会
    向 data/feedback_log.json 追加测试样本，造成 git 噪音、文件无限膨胀，
    并在部署时把伪造数据带进生产。改为按调用时读取，测试即可整体重定向到临时文件。
    """
    return os.environ.get("AGRI_FEEDBACK_LOG") or _DEFAULT_FEEDBACK_LOG


# 向后兼容的模块级常量（调用时以函数为准，环境变量始终优先生效）
CROP_DB_PATH = _DEFAULT_CROP_DB
FEEDBACK_LOG_PATH = _DEFAULT_FEEDBACK_LOG

SEED_WEIGHT = 0.35      # 首条反馈：文献分权重
OBS_WEIGHT = 0.65       # 首条反馈：实测分权重
EMA_ALPHA = 0.5         # 多条反馈：指数移动平均系数（实测占比）


def _load(path: str) -> Any:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {} if path.endswith(".json") else []


def _save(path: str, obj: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _observed_score(survival_rate: float, yield_rating: float, user_rating: float) -> float:
    """实测综合分（0-1）：成活率 0.5 + 产量 0.3 + 用户评分 0.2。"""
    sr = max(0.0, min(1.0, float(survival_rate)))
    yr = max(0.0, min(1.0, float(yield_rating) / 5.0))
    ur = max(0.0, min(1.0, float(user_rating) / 5.0))
    return round(sr * 0.5 + yr * 0.3 + ur * 0.2, 3)


def _find_crop(db: Dict[str, Any], zone_id: str, crop_name: str) -> Optional[Dict[str, Any]]:
    """先在本分区精确查找，找不到再全局兜底（避免跨带误匹配）。"""
    zd = db.get("zones", {}).get(zone_id)
    if zd:
        for c in zd.get("crops", []):
            if c.get("crop") == crop_name:
                return c
    for zid, zm in db.get("zones", {}).items():
        if zid == zone_id:
            continue
        for c in zm.get("crops", []):
            if c.get("crop") == crop_name:
                return c
    return None


def record_feedback(
    zone_id: str,
    crop: str,
    survival_rate: float = 1.0,
    yield_rating: float = 5.0,
    user_rating: float = 5.0,
    issues: Optional[List[str]] = None,
    note: str = "",
) -> Dict[str, Any]:
    """记录一条用户种植反馈并校准 adapt_score。

    返回：{changed, before, after, calibrated, n_feedback}
    """
    issues = issues or []
    crop_db = crop_db_path()
    feedback_log = feedback_log_path()
    db = _load(crop_db)
    log = _load(feedback_log)
    if not isinstance(log, list):
        log = []

    ts = datetime.datetime.now().isoformat(timespec="seconds")
    entry = {
        "ts": ts, "zone_id": zone_id, "crop": crop,
        "survival_rate": survival_rate, "yield_rating": yield_rating,
        "user_rating": user_rating, "issues": issues, "note": note,
    }
    log.append(entry)

    target = _find_crop(db, zone_id, crop)
    if not target:
        _save(feedback_log, log)
        return {"changed": False, "reason": f"未找到 {zone_id}/{crop}", "before": None, "after": None}

    seed = float(target.get("seed_adapt_score", target.get("adapt_score", 0.0)))
    if "seed_adapt_score" not in target:
        target["seed_adapt_score"] = seed

    observed = _observed_score(survival_rate, yield_rating, user_rating)
    calib = target.get("measured_calibration")
    if not calib:
        new_score = round(SEED_WEIGHT * seed + OBS_WEIGHT * observed, 3)
        n = 1
    else:
        old = float(calib.get("calibrated_score", seed))
        new_score = round((1 - EMA_ALPHA) * old + EMA_ALPHA * observed, 3)
        n = int(calib.get("n_feedback", 0)) + 1

    before = target.get("adapt_score")
    target["adapt_score"] = new_score
    target["measured_calibration"] = {
        "n_feedback": n,
        "calibrated_score": new_score,
        "last_survival_rate": survival_rate,
        "last_yield_rating": yield_rating,
        "last_user_rating": user_rating,
        "last_issues": issues,
        "last_updated": ts,
    }
    target["calibrated"] = True

    _save(crop_db, db)
    _save(feedback_log, log)
    return {
        "changed": True, "before": before, "after": new_score,
        "calibrated": True, "n_feedback": n,
        "seed_adapt_score": seed, "observed_score": observed,
    }


def get_calibration(zone_id: str, crop: str) -> Optional[Dict[str, Any]]:
    db = _load(crop_db_path())
    t = _find_crop(db, zone_id, crop)
    return t.get("measured_calibration") if t else None


def generate_report() -> Dict[str, Any]:
    log = _load(feedback_log_path())
    if not isinstance(log, list):
        log = []
    by_crop: Dict[str, int] = {}
    for e in log:
        key = f"{e.get('zone_id')}/{e.get('crop')}"
        by_crop[key] = by_crop.get(key, 0) + 1
    return {
        "total_feedback": len(log),
        "calibrated_entries": len(by_crop),
        "per_crop": by_crop,
        "recent": log[-5:] if log else [],
    }


def run_demo() -> Dict[str, Any]:
    """跑一次示例反馈闭环（杭州·生菜 实测表现好），展示校准前后。

    注意：这里的记录是 **demo 合成数据**，note 带 `[demo]` 前缀以便与真实用户反馈区分。
    不要把它当成真实回流数据；提交前请运行 `python scripts/clean_demo_data.py` 清理。
    """
    print("=" * 56)
    print("🌿 flywheel 反馈闭环示例（demo 合成数据，非真实用户反馈）")
    print("=" * 56)
    # 先看校准前
    before = get_calibration("subtropical_wet", "生菜")
    print(f"校准前 生菜 measured_calibration: {before}")

    res = record_feedback(
        zone_id="subtropical_wet",
        crop="生菜",
        survival_rate=0.92,
        yield_rating=4.5,
        user_rating=5.0,
        issues=["梅雨季轻微霜霉病，已控湿处理"],
        note="[demo] 杭州 15 楼南向阳台，春播实测",
    )
    print(f"反馈记录：成活率 0.92 / 产量 4.5 / 评分 5.0")
    print(f"校准结果：{res.get('seed_adapt_score')} (seed) "
          f"→ {res.get('before')} → {res.get('after')} (n={res.get('n_feedback')})")

    # 第二条反馈（夏季抽苔问题，评分下降）→ 看 EMA 收敛
    res2 = record_feedback(
        zone_id="subtropical_wet",
        crop="生菜",
        survival_rate=0.70,
        yield_rating=3.0,
        user_rating=3.5,
        issues=["夏季高温抽苔，提前采收"],
        note="[demo] 杭州夏季阳台，未遮阳",
    )
    print(f"第二条反馈（夏季）：0.70 / 3.0 / 3.5 → 校准分 {res2.get('after')} (n={res2.get('n_feedback')})")

    report = generate_report()
    print(f"\n累计反馈 {report['total_feedback']} 条，已校准 {report['calibrated_entries']} 个作物")
    print("=" * 56)
    return {"first": res, "second": res2, "report": report}


def main():
    run_demo()


if __name__ == "__main__":
    main()
