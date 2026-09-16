#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/diff_daily_loop.py —— 每日巡检报告跨日对比

动机：每日报告独立生成，变化靠人工对比两份 markdown——实际没人会做，
于是「某天某数据源从 200 变 404」这类渐变信号会被漏掉。

策略（兼顾可靠与成本）：
  - 数据源 HTTP 码：从上一份报告解析（**不重新探测**，避免每日多轮长耗时）
  - 快照数字：**重新采集**当前真实值（纯本地读文件，毫秒级），与上份报告解析值对比
    —— 这样即使上份报告写错，也能发现漂移

解析策略：优先读报告内嵌的 ```json 摘要块（稳定契约，见自动化 prompt 要求）；
缺失时回退到 markdown 表格正则（兼容 09-08 ~ 09-10 的历史报告）。

用法：
    python scripts/diff_daily_loop.py
退出码：0 = 无显著变化；1 = 有变化需关注
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "outputs")


# ---------------- 解析历史报告 ----------------
def _parse_json_block(text: str):
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


_HOST_RE = re.compile(r"(?:https?://)?([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)(?:/[^\s|]*)?")


def _norm_host(cell: str):
    """从单元格里抽出主机名并归一化；非主机（文件名/命令）返回 None。"""
    c = cell.strip().strip("`*").strip()
    if not c or c.startswith(("./", "/", "scripts/", "data/")):
        return None
    m = _HOST_RE.search(c)
    if not m:
        return None
    host = m.group(1).lower()
    # 排除被当成主机的文件名：.py/.json/.md 结尾，或含下划线（域名不允许下划线）
    if host.endswith((".py", ".json", ".md")) or "_" in host:
        return None
    # 归一化 www. 前缀，避免 worldclim.org 与 www.worldclim.org 被当成两个源
    if host.startswith("www."):
        host = host[4:]
    return host


def _parse_md_sources(text: str) -> dict:
    """只解析「外部数据源」章节内的表格；按主机名归一化作为键。

    兼容两种历史格式：
      09-09：URL 列为裸域名（gaez.fao.org），HTTP 码可能带 ** 加粗
      09-10：URL 列为完整 URL（https://gaez.fao.org/），并含退出码列（也是数字，需区分）
    判定一行是数据源行需同时满足：存在 3 位 HTTP 码单元格 + 存在主机名单元格。
    """
    sources: dict = {}
    lines = text.splitlines()
    in_src = False
    for line in lines:
        if line.lstrip().startswith("#") and "数据源" in line:
            in_src = True
            continue
        if in_src and line.lstrip().startswith("#"):
            break
        if not in_src or "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        code = None
        host = None
        for c in cells:
            c2 = c.strip().strip("`*").strip()
            if code is None and re.fullmatch(r"\d{3}", c2):
                code = c2
            if host is None:
                h = _norm_host(c)
                if h:
                    host = h
        if code and host:
            sources[host] = code
    return sources


def _parse_md_fallback(text: str) -> dict:
    snap = {}
    for line in text.splitlines():
        low = line.lower()
        if "feedback" in low and "|" in line:
            nums = re.findall(r"\b(\d+)\b", line)
            nums = [n for n in nums if n not in ("0",) or "feedback" in low]
            if nums:
                snap["feedback"] = nums[0]
        if ("env_recipes" in low or "配方" in line) and "|" in line:
            nums = re.findall(r"\b(\d{2,4})\b", line)
            if nums:
                snap["recipes"] = nums[0]
        if ("wofost" in low or "作物数" in line) and "|" in line:
            nums = re.findall(r"\b(\d+)\b", line)
            if nums:
                snap["wofost_crops"] = nums[0]
    return {"sources": _parse_md_sources(text), "snapshot": snap}


def load_report(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    data = _parse_json_block(text)
    if data and ("sources" in data or "snapshot" in data):
        data["_parse"] = "json"
    else:
        data = _parse_md_fallback(text)
        data["_parse"] = "md"
    data["_file"] = os.path.basename(path)
    return data


# ---------------- 采集当前真实快照 ----------------
def collect_snapshot() -> dict:
    snap = {}
    fb = os.path.join(ROOT, "data", "feedback_log.json")
    try:
        with open(fb, "r", encoding="utf-8") as f:
            snap["feedback"] = str(len(json.load(f) or []))
    except Exception:
        snap["feedback"] = "N/A"
    try:
        snap["recipes"] = str(len(glob.glob(os.path.join(ROOT, "data", "env_recipes", "*.json"))))
    except Exception:
        snap["recipes"] = "N/A"
    try:
        with open(os.path.join(ROOT, "data", "wofost_phenology_reference.json"),
                  "r", encoding="utf-8") as f:
            snap["wofost_crops"] = str(len(json.load(f).get("crops", {})))
    except Exception:
        snap["wofost_crops"] = "N/A"
    return snap


def main() -> int:
    files = sorted(glob.glob(os.path.join(OUT_DIR, "daily_loop_*.md")))
    if len(files) < 2:
        print("报告不足 2 份，无法对比（需至少两份 daily_loop_*.md）")
        return 0

    prev_path = files[-2]
    curr_path = files[-1]
    prev = load_report(prev_path)
    curr = load_report(curr_path)

    print("=" * 60)
    print("每日巡检报告跨日对比")
    print("=" * 60)
    print(f"上一份：{prev['_file']}（解析方式 {prev['_parse']}）")
    print(f"当前份：{curr['_file']}（解析方式 {curr['_parse']}）\n")

    changes = []

    # 1) 数据源 HTTP 码变化
    ps = prev.get("sources", {}) or {}
    cs = curr.get("sources", {}) or {}
    if ps or cs:
        print("--- 数据源 HTTP 码 ---")
        keys = sorted(set(ps) | set(cs))
        for k in keys:
            a, b = ps.get(k, "缺失"), cs.get(k, "缺失")
            if a == b:
                print(f"  = {a:>4s}  {k}")
            else:
                sev = "🔴" if (a != "缺失" and b != "缺失") else "🟡"
                print(f"  {sev} {a:>4s} → {b:<4s}  {k}")
                changes.append({"type": "source", "url": k, "from": a, "to": b})
        if not keys:
            print("  （两份报告均未解析出数据源条目）")
        print()

    # 2) 快照数字（当前真实值 vs 上一份报告解析值）
    now = collect_snapshot()
    prev_snap = prev.get("snapshot", {}) or {}
    print("--- 快照数字（当前真实采集 vs 上一份报告）---")
    for key, label in (("feedback", "feedback_log 回流条数"),
                       ("recipes", "env_recipes 配方数"),
                       ("wofost_crops", "WOFOST 作物数")):
        a = prev_snap.get(key, "缺失")
        b = now.get(key, "N/A")
        if a == b:
            print(f"  = {a:>6s}  {label}")
        else:
            print(f"  🟡 {a:>6s} → {b:<6s}  {label}")
            changes.append({"type": "snapshot", "key": key, "from": a, "to": b})
    print()

    print("-" * 60)
    if changes:
        print(f"⚠️  发现 {len(changes)} 处变化：")
        for c in changes:
            if c["type"] == "source":
                print(f"   - 数据源 {c['url']}: {c['from']} → {c['to']}")
            else:
                print(f"   - 快照 {c['key']}: {c['from']} → {c['to']}")
        return 1
    print("✅ 无变化——数据源状态码与快照数字均与上一份一致")
    return 0


def _selftest() -> int:
    """解析器回归自测：两种历史格式都要解析出正确的源集合。

    这是报告格式契约的守门人——格式漂移会让 diff 大面积误报，
    必须能在无真实报告时独立验证。
    """
    fmt_a = """
## 二、外部数据源存活探测
| 数据源 | URL | HTTP | 耗时(s) | 退出码 | 基线 | 判定 |
|---|---|---|---|---|---|---|
| GAEZ v4 门户 | gaez.fao.org | 200 | 1.72 | 0 | 200 | ✅ 正常 |
| WorldClim | worldclim.org | 200 | 1.10 | 0 | 200 | ✅ 正常 |
| SoilGrids API | api.isric.org/soilgrids/v2.0/... | **000** | 0.31 | **6** | 不可达 | ⚠️ 仍不可达 |
---
## 三、状态快照
"""
    fmt_b = """
## 2. 外部数据源存活探测
| # | 数据源 | HTTP | 耗时(s) | 退出码 | 相对基线 |
|---|---|---|---|---|---|
| 1 | https://gaez.fao.org/ | 200 | 1.629 | 0 | 正常 |
| 3 | https://www.worldclim.org/ | 200 | 1.131 | 0 | 正常 |
| 7 | api.isric.org SoilGrids v2.0 query | 000 | 0.712 | 6 | 无变化 |
---
## 3. 状态快照
"""
    fails = []
    a = _parse_md_sources(fmt_a)
    b = _parse_md_sources(fmt_b)
    exp = {"gaez.fao.org": "200", "worldclim.org": "200", "api.isric.org": "000"}
    if a != exp:
        fails.append(f"格式A 解析结果不符：{a} != {exp}")
    if b != exp:
        fails.append(f"格式B 解析结果不符：{b} != {exp}")
    # 快照不应把回归表/命令行误认成数据源
    if "scripts" in str(a) or "test_agents" in str(a):
        fails.append("误把回归表命令当作数据源")
    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK：两种历史格式均解析正确（3 源 / 含 000 与 **000** 加粗 / www. 归一化）")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
