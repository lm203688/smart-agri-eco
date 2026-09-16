#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/check_doc_links.py —— 文档外链全量死链扫描

动机：每日巡检只探测 7 个固定数据源，但项目文档（docs/*.md、根目录 *.md）里
实际引用了更多外部 URL，这些**无人监控**。本项目已连续三次踩到死数据源
（Ecocrop 2015 停服、OpenFarm 2025-04 归档、@pondlog 数据不在仓库），
覆盖面漏洞就是事故源头。

设计要点（避免每天报假警）：
  1. 三态判定：ALIVE / DEAD / UNPROBEABLE
     - UNPROBEABLE：省略占位符（含 ".."）、非 http(s) 等，不可探测，不算故障
  2. 已知死链白名单 KNOWN_DEAD：文档里**有意保留**的死亡证据（如 Ecocrop 停服记录），
     死了不算故障，但**若复活反而要提示更新文档**（双向检查）
  3. 只用 subprocess 调 curl，判定看 HTTP 码与退出码，**不用 || 兜底**

用法：
    python scripts/check_doc_links.py            # 扫描并打印报告
    python scripts/check_doc_links.py --json      # 机器可读输出
退出码：0 = 无可关注项；1 = 有新增死链或文档需更新
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 扫描范围：docs/ 下所有 md + 根目录 md
DOC_DIRS = [os.path.join(ROOT, "docs"), ROOT]
DOC_GLOB_SUFFIX = ".md"

# 本地/内网地址：不探测
LOCAL_HOST_MARKERS = ("127.0.0.1", "localhost", "host.docker.internal",
                      "0.0.0.0", "192.168.", "10.")

# 已知死链白名单：文档有意保留的「已死」证据。死了正常，复活才需处理。
# 格式：URL 前缀 -> 死亡理由（写进文档的依据）
KNOWN_DEAD = {
    "https://ecocrop.fao.org/":
        "ECOCROP 于 2015 年前后停服并并入 GAEZ，FAO 官方页已确认；"
        "docs/data_sources_verified.md 有意保留为死亡证据",
}

# 已知「本机不可达」白名单：源站可能活着，但本机网络层连不上（代理/DNS 拦截）。
# 与 KNOWN_DEAD 的区别：这类不等于源站死亡，只是本环境拿不到，
# 误报成"数据源死了"会误导决策（实测踩过：github.com 根域 200，但某个长路径稳定 exit=7）。
KNOWN_UNREACHABLE = {
    "https://api.isric.org/":
        "**该主机不存在**（curl exit 6 = DNS 解析失败），与网络/代理无关。"
        "2026-09-10 核实：SoilGrids v2.0 的官方主机是 rest.isric.org（实测可达）。"
        "本条保留仅为让文档中'错误 URL'的历史记录探测时不报错，**不要据此认为源站不可达**。",
}
# 注：github.com 各仓库链接曾出现 exit=7（约 10s 失败），但重试后多为 200（耗时可达 10s+），
# 属本机代理层抖动而非源站死亡，**故不列入白名单**，交由 probe_with_retry 的重试覆盖。
# 教训：不要因为一次探测失败就把可达源写进不可达白名单——白名单会掩盖真实状态。

URL_RE = re.compile(r"https?://[a-zA-Z0-9._~:/?#@!$&'()*+,;=%\-]+")

TIMEOUT_SEC = 20


def _iter_doc_files():
    for d in DOC_DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(DOC_GLOB_SUFFIX):
                yield os.path.join(d, name)


def extract_urls() -> tuple:
    """返回 ({url: [出现它的文件相对路径, ...]}, 实际扫描的文件数)。"""
    found: dict = {}
    scanned = 0
    for path in _iter_doc_files():
        rel = os.path.relpath(path, ROOT)
        scanned += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
        for raw in URL_RE.findall(text):
            url = raw.rstrip(").,;")
            if not url:
                continue
            found.setdefault(url, [])
            if rel not in found[url]:
                found[url].append(rel)
    return found, scanned


def _is_local(url: str) -> bool:
    return any(m in url for m in LOCAL_HOST_MARKERS)


def _is_unprobeable(url: str) -> str:
    """返回不可探测的原因，可探测则返回空串。"""
    if ".." in url:
        return "省略占位符（含 ..），非真实可请求地址"
    if "<" in url or ">" in url:
        return "含模板占位符"
    # 以 ? 或 # 结尾 = 查询/片段为空，是「路径 + ?...」这类省略写法被 rstrip 剥掉后的残留，
    # 不是真实可请求地址（实测：曾把 .../query?... 当成真链接去探，得到 4xx 假死链）。
    if url.rstrip().endswith(("?", "#")):
        return "空查询/片段（疑似省略写法残留），非真实可请求地址"
    return ""


def probe(url: str) -> dict:
    """用 curl 探测单个 URL。注意：Git Bash 下 -o /dev/null 会返回退出码 23 导致误判，
    必须用 NUL。"""
    cmd = [
        "curl", "-s", "-o", "NUL",
        "-w", "%{http_code} %{time_total}",
        "--ssl-no-revoke", "--tlsv1.3",
        "--max-time", str(TIMEOUT_SEC),
        "-L", url,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SEC + 10)
        out = (p.stdout or "").strip()
        parts = out.split()
        code = parts[0] if parts else "000"
        elapsed = parts[1] if len(parts) > 1 else "-"
        return {"http_code": code, "elapsed_s": elapsed, "exit": p.returncode}
    except subprocess.TimeoutExpired:
        return {"http_code": "000", "elapsed_s": "-", "exit": 28}
    except Exception as e:  # noqa: BLE001
        return {"http_code": "000", "elapsed_s": "-", "exit": -1, "error": str(e)}


def classify(res: dict) -> str:
    """四态判定——区分「源站明确死亡」与「本机连不上」，后者不等于源站死亡。

    - ALIVE         : HTTP 2xx/3xx
    - DEAD_CONFIRMED: 服务器明确返回 4xx/5xx（源站层面的问题，可判定死亡）
    - UNREACHABLE   : curl 退出码非 0（DNS/TCP/TLS 层失败）——可能只是本机网络问题，
                      必须重试确认，且**不得**据此断言源站死亡
    """
    code = str(res.get("http_code", "000"))
    if code.startswith("2") or code.startswith("3"):
        return "ALIVE"
    if res.get("exit", 0) == 0 and code[0] in ("4", "5"):
        return "DEAD_CONFIRMED"
    return "UNREACHABLE"


def probe_with_retry(url: str, retries: int = 2, delay_s: float = 3.0) -> dict:
    """UNREACHABLE 常为本机网络抖动（实测：同一 URL 首次 exit=7、复测 200），
    故需重试确认，避免每日巡检报假警消耗报告信用。"""
    import time
    res = probe(url)
    state = classify(res)
    tries = 1
    while state == "UNREACHABLE" and tries <= retries:
        time.sleep(delay_s)
        res = probe(url)
        state = classify(res)
        tries += 1
    res["state"] = state
    res["tries"] = tries
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描文档外链，发现死链与需更新的死链证据")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    urls, scanned_count = extract_urls()

    to_probe, unprobeable, skipped_local = [], {}, []
    for u, files in sorted(urls.items()):
        if _is_local(u):
            skipped_local.append(u)
            continue
        why = _is_unprobeable(u)
        if why:
            unprobeable[u] = {"files": files, "reason": why}
            continue
        to_probe.append((u, files))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(probe_with_retry, u): (u, files) for u, files in to_probe}
        for fut in concurrent.futures.as_completed(futures):
            u, files = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = {"http_code": "000", "elapsed_s": "-", "exit": -1,
                       "state": "UNREACHABLE", "tries": 0, "error": str(e)}
            results[u] = {"files": files, "probe": res, "state": res.get("state", "UNREACHABLE")}

    # --- 判定需关注项 ---
    new_dead = []        # 源站明确 4xx/5xx 且不在白名单 → 真死，需处理
    new_unreachable = [] # 本机连不上且不在白名单 → 需人工判断（不等于源站死亡）
    revived = []         # 白名单里却活了 → 文档需更新
    alive = []
    for u, info in sorted(results.items()):
        state = info["state"]
        known_dead = next((k for k in KNOWN_DEAD if u.startswith(k)), None)
        known_unreach = next((k for k in KNOWN_UNREACHABLE if u.startswith(k)), None)
        info["known_reason"] = KNOWN_DEAD.get(known_dead) or KNOWN_UNREACHABLE.get(known_unreach) or ""
        known = known_dead or known_unreach
        if state == "ALIVE":
            alive.append(u)
            if known:
                revived.append({"url": u, "note": "白名单标记为不可达/已死，但探测为 ALIVE，文档需更新"})
        elif state == "DEAD_CONFIRMED":
            if not known:
                new_dead.append(u)
        else:  # UNREACHABLE
            if not known:
                new_unreachable.append(u)

    payload = {
        "scanned_file_count": scanned_count,
        "files_with_links": sorted({f for v in results.values() for f in v["files"]}),
        "total_urls": len(urls),
        "probed": len(results),
        "alive": len(alive),
        "new_dead": new_dead,
        "new_unreachable": new_unreachable,
        "revived": revived,
        "unprobeable": unprobeable,
        "skipped_local": skipped_local,
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("文档外链死链扫描")
        print("=" * 60)
        print(f"扫描 md 文件 {scanned_count} 个（其中 {len(payload['files_with_links'])} 个含外链），"
              f"抽取 URL {len(urls)} 个，实际探测 {len(results)} 个"
              f"（跳过本地 {len(skipped_local)}、不可探测 {len(unprobeable)}）\n")
        for u, info in sorted(results.items()):
            p = info["probe"]
            st = info["state"]
            mark = {"ALIVE": "✅", "DEAD_CONFIRMED": "❌", "UNREACHABLE": "⚠️"}.get(st, "?")
            tail = ""
            if info["known_reason"]:
                tail = "  [白名单·预期]"
            if p.get("tries", 1) > 1:
                tail += f"  (重试{p['tries']}次)"
            print(f"{mark} {st:14s} HTTP {p['http_code']:>3s} "
                  f"{p['elapsed_s']:>7s}s  exit={p['exit']}{tail}  {u}")
        if unprobeable:
            print("\n--- 不可探测（非故障）---")
            for u, v in sorted(unprobeable.items()):
                print(f"  ⚪ {u}  ({v['reason']})")
        print()
        if new_dead:
            print(f"🔴 确认死链 {len(new_dead)} 个（源站返回 4xx/5xx，需处理）：")
            for u in new_dead:
                print(f"   - {u}  （出现在：{', '.join(results[u]['files'])}）")
        else:
            print("✅ 无确认死链")
        if new_unreachable:
            print(f"\n⚠️  本机不可达 {len(new_unreachable)} 个"
                  f"（网络层失败，**不等于源站死亡**，需人工判断或换环境复测）：")
            for u in new_unreachable:
                print(f"   - {u}  （出现在：{', '.join(results[u]['files'])}）")
        if revived:
            print(f"\n🟡 白名单项复活 {len(revived)} 个（文档标注不可达/已死但实际可达，需更新文档）：")
            for r in revived:
                print(f"   - {r['url']}")
        print()

    return 1 if (new_dead or revived) else 0


if __name__ == "__main__":
    sys.exit(main())
