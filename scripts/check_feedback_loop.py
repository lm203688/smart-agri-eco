#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/check_feedback_loop.py —— 数据回流通路可用性自检

动机：data/feedback_log.json 长期 0 条，意味着 submit_feedback → flywheel.record_feedback
→ crop_adapt_db 校准 这条链路**从未被真实调用验证过**。一旦它坏了（路径变更、schema 漂移、
字段改名），要等到有真实用户使用时才会暴露——与已修复的 MCP 单例 bug 同属「静默失败」。

本脚本在**完全隔离**的环境里跑通一次完整回流，验证链路仍然可用。

隔离方式（关键）：
  - 通过 flywheel 已支持的环境变量 AGRI_CROP_DB / AGRI_FEEDBACK_LOG
    重定向到 .workbuddy/tmp/ 下的副本
  - 真实 data/crop_adapt_db.json 与 data/feedback_log.json **只读**，全程不写
  - 自检前后比对真实 feedback_log.json 的字节内容，确保零污染
    （项目有测试 test_feedback_log_has_no_synthetic_entries 专门守卫，
     本脚本若污染会被该测试捕获）

用法：
    python scripts/check_feedback_loop.py
退出码：0 = 回流通路可用；1 = 链路损坏（需修）
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REAL_CROP_DB = os.path.join(ROOT, "data", "crop_adapt_db.json")
REAL_FEEDBACK_LOG = os.path.join(ROOT, "data", "feedback_log.json")

# 临时目录放项目内：Windows 上 Git Bash 的 /tmp 与 Python 解析不一致（flywheel 已注明此坑）
TMP_DIR = os.path.join(ROOT, ".workbuddy", "tmp")


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> int:
    checks = []

    def check(ok: bool, label: str, detail: str = ""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})
        print(f"{'✅' if ok else '❌'} {label}" + (f"  — {detail}" if detail else ""))

    # ---- 0. 前置：真实文件存在性 + 记录校验和（防污染）----
    if not os.path.exists(REAL_CROP_DB):
        check(False, "真实作物库存在", REAL_CROP_DB)
        return 1
    if not os.path.exists(REAL_FEEDBACK_LOG):
        check(False, "真实反馈日志存在", REAL_FEEDBACK_LOG)
        return 1
    db_sha_before = _sha(REAL_CROP_DB)
    fb_sha_before = _sha(REAL_FEEDBACK_LOG)
    fb_size_before = os.path.getsize(REAL_FEEDBACK_LOG)
    check(True, "真实文件已锁定校验和",
          f"feedback_log {fb_size_before} 字节")

    os.makedirs(TMP_DIR, exist_ok=True)
    tmp_db = os.path.join(TMP_DIR, "crop_db_isolated.json")
    tmp_fb = os.path.join(TMP_DIR, "feedback_log_isolated.json")
    shutil.copyfile(REAL_CROP_DB, tmp_db)
    shutil.copyfile(REAL_FEEDBACK_LOG, tmp_fb)

    os.environ["AGRI_CROP_DB"] = tmp_db
    os.environ["AGRI_FEEDBACK_LOG"] = tmp_fb

    try:
        import engine.flywheel as fw  # 必须在设置环境变量后导入/重载
        import importlib
        importlib.reload(fw)

        # ---- 1. 回流通路：写入一条隔离的反馈 ----
        # 用真实存在的 zone/crop，确保能命中校准目标
        with open(tmp_db, "r", encoding="utf-8") as f:
            db = json.load(f)
        zone_id = next(iter(db.get("zones", {})), None)
        crop_name = db["zones"][zone_id]["crops"][0]["crop"] if zone_id else ""
        if not zone_id or not crop_name:
            check(False, "定位测试目标作物", "作物库无可用 zone/crop")
            return 1
        check(True, "定位测试目标", f"{zone_id} / {crop_name}")

        before_score = db["zones"][zone_id]["crops"][0].get("adapt_score")

        res = fw.record_feedback(
            zone_id=zone_id,
            crop=crop_name,
            survival_rate=0.85,
            yield_rating=4.0,
            user_rating=4.0,
            issues=["自检用隔离数据，不写入生产"],
            note="check_feedback_loop 自检（隔离副本）",
        )
        check(bool(res.get("changed")), "record_feedback 命中并校准作物",
              f"before={res.get('before')} after={res.get('after')}")

        # ---- 2. 反馈日志确实落盘 ----
        with open(tmp_fb, "r", encoding="utf-8") as f:
            log = json.load(f)
        check(isinstance(log, list) and len(log) == 1,
              "隔离反馈日志写入 1 条", f"实际 {len(log) if isinstance(log, list) else type(log)} 条")
        if log:
            e = log[0]
            check(all(k in e for k in ("ts", "zone_id", "crop", "survival_rate")),
                  "反馈条目字段完整", ",".join(sorted(e.keys())))

        # ---- 3. 校准结果写回作物库 ----
        with open(tmp_db, "r", encoding="utf-8") as f:
            db2 = json.load(f)
        tgt = db2["zones"][zone_id]["crops"][0]
        check(tgt.get("calibrated") is True, "作物库 calibrated 标记已置位")
        check(bool(tgt.get("measured_calibration")), "measured_calibration 已生成",
              json.dumps(tgt.get("measured_calibration", {}), ensure_ascii=False)[:120])
        check(tgt.get("seed_adapt_score") is not None,
              "保留 seed_adapt_score（可回溯文献原始分）",
              f"seed={tgt.get('seed_adapt_score')}")
        check(tgt.get("adapt_score") != before_score,
              "adapt_score 已被实测校准", f"{before_score} → {tgt.get('adapt_score')}")

        # ---- 4. 报告可生成 ----
        rep = fw.generate_report()
        check(isinstance(rep, dict), "generate_report 可生成",
              f"keys={list(rep.keys())[:5] if isinstance(rep, dict) else type(rep)}")

        # ---- 5. CLI 入口可导入 ----
        try:
            import subprocess
            p = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "submit_feedback.py"), "--help"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "AGRI_CROP_DB": tmp_db, "AGRI_FEEDBACK_LOG": tmp_fb},
            )
            check(p.returncode == 0 and "--zone" in (p.stdout or ""),
                  "submit_feedback.py CLI 可用", f"exit={p.returncode}")
        except Exception as e:  # noqa: BLE001
            check(False, "submit_feedback.py CLI 可用", str(e))

    except Exception as e:  # noqa: BLE001
        check(False, "回流通路执行未抛异常", f"{type(e).__name__}: {e}")
    finally:
        # ---- 6. 真实文件零污染校验（最重要）----
        db_sha_after = _sha(REAL_CROP_DB)
        fb_sha_after = _sha(REAL_FEEDBACK_LOG)
        ok_db = db_sha_before == db_sha_after
        ok_fb = fb_sha_before == fb_sha_after
        check(ok_db, "真实 crop_adapt_db.json 未被修改")
        check(ok_fb, "真实 feedback_log.json 未被污染")
        # 清理临时副本
        for p in (tmp_db, tmp_fb):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    failed = [c for c in checks if not c["ok"]]
    print("-" * 56)
    if failed:
        print(f"❌ 回流通路自检失败 {len(failed)}/{len(checks)} 项：")
        for c in failed:
            print(f"   - {c['label']} {c['detail']}")
        return 1
    print(f"✅ 回流通路自检全部通过（{len(checks)} 项）")
    print("   注：真实反馈仍为 0 条——通路可用，但尚无真实用户回流数据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
