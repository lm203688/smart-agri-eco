"""Daily-loop anomaly attribution node — OPTIONAL Jev judgment layer.

This is the "副驾 / 判断层" integration of Jev (TypeSafe System One) into the
每日单口闭环. It does NOT touch calibrated real data; it only *explains* why a
data-source probe failed, so the daily report can say "源已死 / 区域慢 / 代理抖"
instead of a bare HTTP code.

Design rules (consistent with agent/jev_gate.py):
- Self-contained: probes the 7 sources itself with stdlib urllib. The SSL context
  uses CERT_NONE + no hostname check, which is equivalent to the daily loop's
  `curl --ssl-no-revoke --tlsv1.3` (this sandbox sits behind a TLS-intercepting
  proxy). If `--probe-json` is given, those pre-computed results are used instead
  of re-probing (lets the automation reuse its own curl probes verbatim).
- If TYPESAFE_API_KEY is absent, every attribution is skipped and a *deterministic*
  fallback text is emitted (map exit code 6->host-missing, 28->timeout/slow,
  other->needs-human). Never crash the loop, never claim a Jev verdict it didn't make.
- Jev answers live inside the schema; "valid label" != semantically correct. A
  confidence threshold escalates low-confidence calls to "无法判断 / 需人工".

Zero third-party deps.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import ssl
import sys
import urllib.error

# Ensure the project root is importable regardless of CWD, so `from agent.jev_gate`
# works when the script is run directly as `python scripts/jev_attribution.py`.
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Same 7 sources as the daily-loop probe (Step 2), with known baselines.
SOURCES: List[Dict[str, str]] = [
    {"name": "gaez.fao.org", "url": "https://gaez.fao.org/"},
    {"name": "data.apps.fao.org", "url": "https://data.apps.fao.org/gaez/"},
    {"name": "worldclim.org", "url": "https://www.worldclim.org/"},
    {"name": "plantvillage.psu.edu", "url": "https://plantvillage.psu.edu/"},
    {"name": "gd.eppo.int", "url": "https://gd.eppo.int/"},
    {"name": "soilgrids.org", "url": "https://soilgrids.org/"},
    {"name": "rest.isric.org",
     "url": "https://rest.isric.org/soilgrids/v2.0/properties/query"
            "?lon=120.15&lat=30.27&property=phh2o&depth=0-5cm&value=mean"},
]

_PROBE_TIMEOUT = 25
_ATTR_OPTIONS = ["源已死亡（永久停用）", "区域网络慢或临时超时", "代理/TLS 拦截抖动", "无法判断"]
# Confidence at/above which we trust Jev's non-"无法判断" pick; below -> escalate.


def _norevoke_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _has_key() -> bool:
    """Whether a Jev key is resolvable (env var OR ~/.config/typesafe/credentials.json).

    Mirrors agent.jev_gate.jev_available() without forcing a module import at the
    top level, keeping the Jev dependency optional for this script.
    """
    from agent.jev_gate import jev_available  # noqa: PLC0415
    return jev_available()


def probe_source(url: str, timeout: int = _PROBE_TIMEOUT) -> Dict[str, Any]:
    """Return {url, http_code(str 3-digit|'000'), time(float), exit_code(int)}.

    exit_code mirrors curl semantics the daily loop already uses:
      0 = ok, 6 = DNS fail (host missing), 7 = conn fail, 28 = timeout, else 1.
    """
    t0 = datetime.datetime.now()
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "agri-jev-probe/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=_norevoke_ctx()) as r:
            code = r.status
            exit_code = 0
    except urllib.error.HTTPError as e:
        code = e.code
        exit_code = 0
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        # urllib wraps DNS/conn/timeout in URLError; distinguish by message.
        if "getaddrinfo" in reason or "Name or service not known" in reason:
            exit_code = 6
        elif "timed out" in reason or "Timeout" in reason:
            exit_code = 28
        elif "Connection" in reason or "refused" in reason:
            exit_code = 7
        else:
            exit_code = 1
        code = "000"
    except Exception:  # noqa: BLE001
        code = "000"
        exit_code = 1
    dt = (datetime.datetime.now() - t0).total_seconds()
    return {"url": url, "http_code": str(code), "time": round(dt, 2),
            "exit_code": exit_code}


def _load_probe_json(path: str) -> Optional[List[Dict[str, Any]]]:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        srcs = d.get("sources") if isinstance(d, dict) else None
        if isinstance(srcs, list) and srcs:
            return srcs
    except Exception:  # noqa: BLE001
        pass
    return None


def attribute_source(s: Dict[str, Any], key_present: bool
                     ) -> Tuple[str, Optional[float], bool]:
    """Return (attribution_label, confidence, skipped).

    attribution_label is one of _ATTR_OPTIONS or the deterministic fallback text.
    """
    if s.get("http_code") == "200":
        return "正常（200）", None, False

    if not key_present:
        # Deterministic fallback — no Jev verdict claimed.
        ec = s.get("exit_code", 1)
        if ec == 6:
            label = "缺 key · 确定性规则：exit 6 = 主机不存在（DNS 解析失败），非网络抖动"
        elif ec == 28:
            label = "缺 key · 确定性规则：exit 28 = 超时 → 区域慢/代理抖，不得判死源"
        elif ec == 7:
            label = "缺 key · 确定性规则：exit 7 = 连接失败，需人工核验"
        else:
            label = "缺 key · 确定性规则：HTTP≠200 且非超时，需人工核验"
        return label, None, True

    # Jev Choice attribution.
    from agent.jev_gate import jev_choice  # local import keeps jev optional
    state = {
        "source": s.get("url"),
        "http_code": s.get("http_code"),
        "time_total_s": s.get("time"),
        "exit_code": s.get("exit_code"),
        "baseline": "该源此前在公网存活；本项目已知 rest.isric.org 为间歇可达（有时 200、有时 >60s 挂死），"
                    "不得因一次超时即判源死。",
    }
    instructions = ("根据上面的探测结果，判断该数据源本次不可达的最可能原因。"
                    "若证据不足以判断，必须选「无法判断」。")
    choice, _probs, conf, skipped, note = jev_choice(
        state, instructions, _ATTR_OPTIONS, qid="attrib")
    if skipped or choice is None:
        return f"Jev 无法判断（{note or 'low confidence'}）→ 升级人工", conf, True
    return choice, conf, False


def run(probe_json: Optional[str], date_str: str) -> str:
    # Use jev_available() rather than probing os.environ directly: since
    # 2026-09-23 a key may also come from ~/.config/typesafe/credentials.json
    # (see agent.jev_gate._api_key), which scheduled runs rely on.
    key_present = _has_key()
    probes = _load_probe_json(probe_json) if probe_json else None
    if probes is None:
        probes = [probe_source(s["url"]) for s in SOURCES]
        # attach human-readable name
        by_url = {s["url"]: s["name"] for s in SOURCES}
        for p in probes:
            p["name"] = by_url.get(p["url"], p["url"])

    rows: List[str] = []
    any_attributed = False
    for p in probes:
        label, conf, skipped = attribute_source(p, key_present)
        if p.get("http_code") != "200":
            any_attributed = True
        cstr = f" (conf={conf:.2f})" if conf is not None else ""
        rows.append(
            f"| {p.get('name', p.get('url'))} | {p.get('http_code')} | "
            f"{p.get('exit_code')} | {p.get('time')}s | {label}{cstr} |")

    jev_status = "启用（TYPESAFE_API_KEY 已设）" if key_present else "未启用（无 key，走确定性 fallback）"
    head = [
        f"## Jev 数据源异常归因（{date_str}）",
        "",
        f"- Jev 状态：{jev_status}",
        f"- 说明：本节点只用 Jev 做**归因解释**，绝不回写任何校准数据；低置信结论一律升级人工。",
        "",
        "| 源 | HTTP | exit | 耗时 | 归因 |",
        "|---|---|---|---|---|",
    ]
    if not any_attributed:
        head.append("| — | — | — | — | 本轮 7 源全部 200，无需归因 |")
    body = head + rows + [""]
    return "\n".join(body)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Jev daily-loop source anomaly attribution")
    ap.add_argument("--probe-json", default=None,
                    help="Optional pre-computed probe results JSON (reuses curl probes).")
    ap.add_argument("--date", default=None, help="Report date YYYY-MM-DD (default: today local).")
    ap.add_argument("--out", default=None, help="Output markdown path (default: outputs/jev_attribution_<date>.md).")
    args = ap.parse_args(argv)

    date_str = args.date or datetime.date.today().strftime("%Y-%m-%d")
    out_path = args.out or os.path.join("outputs", f"jev_attribution_{date_str}.md")

    md = run(args.probe_json, date_str)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md + "\n")

    # stdout echo so the automation can append it to the daily report inline.
    print(md)
    print(f"\n[written] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
