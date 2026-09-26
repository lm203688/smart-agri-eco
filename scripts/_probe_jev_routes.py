#!/usr/bin/env python3
"""Jev 路由探测：试所有候选端点，输出哪些可达、哪些被封。"""

import sys
import os
import json
import urllib.request
import urllib.error
import ssl
import time

KEY = os.environ.get("TYPESAFE_API_KEY", "")
if not KEY:
    print("无 TYPESAFE_API_KEY，跳过鉴权测试")
    sys.exit(0)

# 候选路由列表（按优先级排序）
ROUTES = [
    # (name, url, timeout_sec)
    ("直连 api.typesafe.ai", "https://api.typesafe.ai/v1/systemone", 10),
    ("Vercel gateway", "https://typesafe-ai-jev.vercel.app/api/v1/systemone", 12),
    ("Vercel 根路径", "https://typesafe-ai-jev.vercel.app", 8),
    ("GitHub raw 示例", "https://raw.githubusercontent.com/lm203688/smart-agri-eco/main/README.md", 8),
]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def probe(name, url, timeout):
    try:
        body = json.dumps({
            "state": "test",
            "model": "jev-latest",
            "questions": {"q1": {"type": "noul", "instructions": "ping"}}
        }).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {KEY}",
                "Content-Type": "application/json"
            }
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body_out = r.read().decode(errors="replace")
        dt = time.time() - t0
        status = "OK" if r.status == 200 else f"HTTP_{r.status}"
        hint = body_out[:120].replace("\n", " ")
        return name, status, dt, hint
    except urllib.error.HTTPError as e:
        dt = time.time() - t0
        body_out = e.read().decode(errors="replace")[:120]
        # 检查 Cloudflare 1010
        if "1010" in body_out or "error code" in body_out.lower():
            extra = " [CF 1010 封禁]"
        elif "401" in str(e.code):
            extra = " [401 密钥错/未授权]"
        elif "403" in str(e.code):
            extra = " [403 禁止]"
        else:
            extra = ""
        return name, f"HTTP_{e.code}{extra}", dt, body_out.strip()
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "timed out" in reason.lower():
            extra = " [超时]"
        elif "name or service not known" in reason.lower() or "DNS" in reason.upper():
            extra = " [DNS 失败]"
        elif "Connection refused" in reason or "errno 111" in reason:
            extra = " [连接被拒]"
        else:
            extra = f" [{reason[:50]}]"
        return name, f"ERR{extra}", time.time() - t0, reason[:80]
    except Exception as e:
        return name, f"EXC_{type(e).__name__}", time.time() - t0, str(e)[:80]

print("=" * 70)
print("Jev 路由探测（TYPESAFE_API_KEY 已设置）")
print("=" * 70)
results = []
for name, url, timeout in ROUTES:
    r = probe(name, url, timeout)
    results.append(r)
    tag = "✓" if "OK" in r[1] else ("⚠" if "HTTP_200" not in r[1] else "✓")
    print(f"{tag} {r[0]}")
    print(f"   {r[1]}  ({r[2]:.2f}s)")
    if r[3]:
        print(f"   hint: {r[3][:100]}")
    print()

print("=" * 70)
print("结论：")
ok_routes = [r for r in results if "OK" in r[1] or "HTTP_200" in r[1]]
cf_blocked = [r for r in results if "1010" in r[1]]
if ok_routes:
    print(f"  ✓ 可达路由：{', '.join(r[0] for r in ok_routes)}")
else:
    print("  ✗ 所有路由均不可达")
if cf_blocked:
    print(f"  ⚠ Cloudflare 1010 封禁：{', '.join(r[0] for r in cf_blocked)}")
print("=" * 70)
