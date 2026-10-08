#!/usr/bin/env python3
"""
智慧农业生态 · Demo 站点端到端冒烟自检（零依赖）

用途：
    在部署到公网 ECS 之前，先把「部署后会不会有哑端点」这个未知风险在本地消除。
    在空闲端口以子进程拉起 app/demo_server.py，逐个打全部 HTTP 端点，校验
    状态码 + 响应体形状，最后打印 PASS/FAIL 汇总并以退出码反映结果。

为什么单独成脚本：
    - 人工 curl 容易漏端点，且换端口/换环境要重来
    - CI 需要一条命令把关，防止新增端点后静默变哑
    - 部署自检需要可复跑、可留痕

用法：
    python scripts/check_demo_endpoints.py            # 全量冒烟
    python scripts/check_demo_endpoints.py --quick    # 跳过 POST pipeline（省时）
    python scripts/check_demo_endpoints.py --keep     # 保留服务进程，不自动关闭

退出码：
    0 = 全部通过；1 = 存在失败项
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "app", "demo_server.py")
PY = sys.executable

# ---------------------------------------------------------------------------
# 关键：绕开 HTTP 代理直连回环地址。
#
# 实踩（2026-10-08）：沙箱/IDE 环境常设 HTTP_PROXY=http://127.0.0.1:<port>，
# 而 urllib 默认尊重这些环境变量 —— 于是对 127.0.0.1:<本地端口> 的请求也被
# 塞进代理，代理不认识这个端口，直接回 502 Bad Gateway。表现极具误导性：
# 服务其实正常监听、日志里一条请求都没有，但所有端点"全挂"，看起来像服务崩了。
#
# 正确做法不是删环境变量（那会影响真正的出网请求，比如 NASA POWER），
# 而是给回环地址装一个空 ProxyHandler，只让本地请求直连。
# ---------------------------------------------------------------------------
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_OPENER)


# ---------------------------------------------------------------------------
# 端口与进程
# ---------------------------------------------------------------------------
def free_port() -> int:
    """向系统要一个空闲端口，避免与手工起的 8123 冲突。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_ready(base: str, timeout: float = 90.0) -> bool:
    """轮询 /api/stats 直到服务起来。

    首次启动要加载作物库/配方/检索索引，实测可到 ~20s；沙箱下更慢，
    故窗口给到 90s。每次探测单独设短超时，避免一次卡死吃掉整个窗口。
    """
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/stats", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, e)
            time.sleep(0.5)
    if last_err:
        print("[提示] 最后一次探测错误: %s" % last_err)
    return False


def http(base: str, path: str, payload: dict | None = None, timeout: float = 60.0):
    """发一次请求，返回 (status, bytes, parsed_json_or_None, elapsed)。

    不抛异常：把 HTTPError 也当结果返回，便于断言错误码本身。
    """
    url = base + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    except Exception as e:  # 连接层失败也算失败项
        return 0, str(e).encode("utf-8"), None, time.time() - t0

    parsed = None
    ctype = ""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    return status, raw, parsed, time.time() - t0


# ---------------------------------------------------------------------------
# 用例定义
# ---------------------------------------------------------------------------
# GET 端点：(路径, 期望最小字节数)
# 最小字节数是「哑响应」探针——空数组/空对象返回 200 但体积很小，
# 设下限可捕捉「端点活着但没数据」这种情况。
GET_CASES = [
    ("/api/cities", 300),
    ("/api/skills", 1500),
    ("/api/recipes", 2000),
    ("/api/crops", 30000),
    ("/api/zones", 3000),
    ("/api/pests", 3000),
    ("/api/stats", 500),
    ("/api/bp_list", 300),
]

# POST 端点：(路径, 请求体, 期望存在于响应中的顶层键)
POST_CASES = [
    (
        "/api/recommend",
        {
            "lat": 30.2741, "lon": 120.1551, "scene": "balcony",
            "floor": 6, "orientation": "south", "purpose": "vegetable",
            "space_sqm": 6, "difficulty": "beginner", "budget_cny": 300,
        },
        ["pipeline_steps", "final_recommendation"],
    ),
    (
        "/api/agent",
        {"skill": "nutrition_plan",
         "payload": {"crop": "番茄", "scene": "balcony", "growth_stage": "seedling",
                     "growth_days": 20, "container_volume_l": 10}},
        ["recommendation"],
    ),
    (
        "/api/search",
        {"query": "番茄 叶片发黄", "k": 3},
        ["query", "hits", "stats"],
    ),
    (
        "/api/memory_recall",
        {"query": "番茄 阳台", "k": 3},
        ["query", "hits"],
    ),
    (
        "/api/work_item",
        {"title": "冒烟自检工作项", "actor": "check_demo_endpoints"},
        ["item_id", "state", "transition_table"],
    ),
    (
        "/api/schedule",
        {"crop": "番茄", "zone": "subtropical_wet"},
        ["recipe", "anchors", "actions"],
    ),
]

# 顶层键断言现已全部按实测契约硬校验：键名来自各端点的真实响应
# （2026-10-08 实测），一旦某端点改契约或静默降级返回空对象，此处即报错。


def _dump_child(proc: subprocess.Popen, lines: int = 40) -> None:
    """启动失败时把子进程日志打出来。

    注意：因为 stdout 是 PIPE，子进程写满管道缓冲会阻塞。这里先 terminate
    再读，避免"服务看起来卡住"其实是日志写不进去。
    """
    if proc.poll() is None:
        proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=5)
    out = (out or "").strip()
    if out:
        print("       ---- 子进程输出 ----")
        for ln in out.splitlines()[-lines:]:
            print("       | %s" % ln)
        print("       --------------------")


def _terminate(proc: subprocess.Popen) -> None:
    """收尾：关掉服务进程，同时把管道读空防止僵尸。"""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="跳过 POST pipeline 用例")
    ap.add_argument("--keep", action="store_true", help="保留服务进程不关闭")
    ap.add_argument("--port", type=int, default=0, help="指定端口，默认自动选空闲端口")
    args = ap.parse_args()

    if not os.path.exists(SERVER):
        print("[FAIL] 找不到 %s" % SERVER)
        return 1

    port = args.port or free_port()
    base = "http://127.0.0.1:%d" % port

    env = dict(os.environ)
    env["AGRI_DEMO_HOST"] = "127.0.0.1"
    env["AGRI_DEMO_PORT"] = str(port)
    # 不缓冲，便于父进程在出错时把子进程日志打出来
    env["PYTHONUNBUFFERED"] = "1"
    # 强制 UTF-8：服务启动横幅含 emoji，若落到 GBK/ascii 控制台会
    # UnicodeEncodeError 并在 serve_forever() 之前崩掉（端口已 bind，
    # 表现却像"启动超时"）。此处与 app/demo_server.py 的 _safe_print 双保险。
    env["PYTHONIOENCODING"] = "utf-8"
    # 清掉代理变量：Demo 只监听回环，子进程不必也不应经代理出网；
    # 留着反而会让内部自请求（若有）绕到代理上。
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    # 写盘隔离：与 demo_server 的默认隔离策略保持一致，防止冒烟污染真实数据
    env.setdefault("AGRI_FEEDBACK_DRY_RUN", "1")

    print("=" * 68)
    print("Demo 端点端到端冒烟自检")
    print("=" * 68)
    print("服务脚本 : %s" % os.path.relpath(SERVER, ROOT))
    print("监听地址 : %s" % base)
    print()

    proc = subprocess.Popen(
        [PY, "-u", SERVER],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    results: list[tuple[str, bool, str]] = []
    try:
        if not wait_ready(base):
            print("[FAIL] 服务在 90s 内未就绪（进程 exit=%s）" % proc.poll())
            print("       请手动运行排查：AGRI_DEMO_PORT=%d python app/demo_server.py" % port)
            _dump_child(proc)
            return 1
        print("[ OK ] 服务已就绪\n")

        print("--- GET 端点 ---")
        for path, min_bytes in GET_CASES:
            status, raw, parsed, dt = http(base, path)
            n = len(raw)
            ok = status == 200 and n >= min_bytes
            note = "HTTP %s  %7d B  %.3fs" % (status, n, dt)
            if status == 200 and n < min_bytes:
                note += "  (低于下限 %d B，疑似哑响应)" % min_bytes
            if parsed is None and status == 200:
                note += "  (响应非 JSON)"
                ok = False
            results.append((path, ok, note))
            print("  %s  %-18s %s" % ("[ OK ]" if ok else "[FAIL]", path, note))

        print()
        print("--- POST 端点 ---")
        cases = [] if args.quick else POST_CASES
        if args.quick:
            print("  (--quick 已跳过)")
        for path, body, expect_keys in cases:
            status, raw, parsed, dt = http(base, path, body)
            ok = status == 200 and isinstance(parsed, dict)
            note = "HTTP %s  %7d B  %.3fs" % (status, len(raw), dt)

            if ok and expect_keys:
                missing = [k for k in expect_keys if k not in parsed]
                if missing:
                    ok = False
                    note += "  缺失键: %s" % ",".join(missing)
            results.append((path, ok, note))
            print("  %s  %-18s %s" % ("[ OK ]" if ok else "[FAIL]", path, note))

        print()
        print("=" * 68)
        failed = [r for r in results if not r[1]]
        print("汇总: %d 通过 / %d 失败 / 共 %d 项"
              % (len(results) - len(failed), len(failed), len(results)))
        if failed:
            print("\n失败明细:")
            for path, _, note in failed:
                print("  - %-18s %s" % (path, note))
        print("=" * 68)
        return 1 if failed else 0

    finally:
        if args.keep:
            print("\n[--keep] 服务进程保留，PID=%d，地址 %s" % (proc.pid, base))
        else:
            _terminate(proc)
            print("\n服务进程已关闭")


if __name__ == "__main__":
    sys.exit(main())
