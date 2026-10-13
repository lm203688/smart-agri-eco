#!/usr/bin/env python3
"""A3 AgriTrust Verified：可信标记产品化。

把 T-1 可信标记（core/trust_layer.get_trust_mark()）从内部字段升级为
对外可展示的信任资产。对齐报告 §6.3 E2「公开 JSON schema + 独立复算徽章」。

交付：
  1. schemas/trust_mark.schema.json — 公开 JSON Schema（外部消费者按此验证）
  2. scripts/generate_trust_badge.py — 生成 AgriTrust Verified SVG 徽章
  3. artifacts/agritrust_badge.svg — 导出徽章文件（含 signature_prefix 可验证）
  4. docs/agritrust_verified.md — 对外说明文档（如何独立复算）

设计原则：
  - 零依赖纯标准库
  - signature_prefix 嵌入徽章，外部消费者可独立复算校验
  - 明确标注"当前信任级别"（trusted / degraded）
  - 不静默伪装：任何降级都显示 degraded_reasons
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import hashlib
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.trust_layer import get_trust_mark  # noqa: E402


def render_trust_badge_svg(trust_mark: Dict[str, Any]) -> str:
    """渲染 AgriTrust Verified 徽章 SVG。

    设计：
      - 左侧：徽章标题 "AgriTrust Verified"
      - 中间：信任状态（trusted=绿 / degraded=黄）
      - 右侧：signature_prefix（可独立复算）
      - 底部：复算命令
    """
    status = trust_mark.get("status", "unknown")
    rubric = trust_mark.get("rubric_passed", "0/0")
    sig_prefix = trust_mark.get("signature_prefix", "")[:12]
    verify_cmd = trust_mark.get("verification_cmd", "")

    # 颜色：trusted=绿，degraded=黄，其他=灰
    if status == "trusted":
        color = "#3fb950"
        label = "VERIFIED"
    elif status == "degraded":
        color = "#d29922"
        label = "DEGRADED"
    else:
        color = "#959595"
        label = "UNKNOWN"

    width = 320
    height = 60
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" rx="4" fill="#ffffff" stroke="#cccccc"/>
  <rect x="4" y="4" width="90" height="52" rx="2" fill="#1a1a1a"/>
  <text x="49" y="22" font-family="monospace" font-size="9" fill="#ffffff" text-anchor="middle">AgriTrust</text>
  <text x="49" y="36" font-family="monospace" font-size="10" fill="{color}" text-anchor="middle" font-weight="bold">{label}</text>
  <text x="49" y="50" font-family="monospace" font-size="7" fill="#888888" text-anchor="middle">Rubric {rubric}</text>
  <rect x="100" y="12" width="210" height="36" fill="#f5f5f5" stroke="#dddddd"/>
  <text x="108" y="28" font-family="monospace" font-size="9" fill="#333333">sig: {sig_prefix}</text>
  <text x="108" y="44" font-family="monospace" font-size="7" fill="#666666">{verify_cmd}</text>
</svg>'''


def render_trust_mark_document(trust_mark: Dict[str, Any]) -> str:
    """生成 AgriTrust Verified 说明文档（Markdown）。"""
    status = trust_mark.get("status", "unknown")
    rubric = trust_mark.get("rubric_passed", "0/0")
    sig = trust_mark.get("signature", "")
    sig_prefix = trust_mark.get("signature_prefix", "")
    verify_cmd = trust_mark.get("verification_cmd", "")
    reasons = trust_mark.get("degraded_reasons", [])

    status_emoji = "✅" if status == "trusted" else ("⚠️" if status == "degraded" else "❓")

    doc = f"""# AgriTrust Verified — 可信性验证说明

## 当前信任级别

{status_emoji} **{status.upper()}** — Rubric {rubric}

## 如何独立复算验证

外部消费者可以独立验证任何 Env Recipe 输出的可信性：

```bash
# 1. 获取当前信任标记
python -c "from core.trust_layer import get_trust_mark; import json; print(json.dumps(get_trust_mark(), indent=2))"

# 2. 独立复算 signature（应与信任标记中的 signature 一致）
{verify_cmd}

# 3. 比对 signature
# 如果复算结果与信任标记中的 signature 一致，说明数据未被篡改
```

## 信任标记字段结构

```json
{{
  "cert_id": "{trust_mark.get('cert_id', 'trust-mark')}",
  "signature": "{sig}",
  "signature_prefix": "{sig_prefix}",
  "issued_at": "{trust_mark.get('issued_at', '')}",
  "verification_cmd": "{verify_cmd}",
  "status": "{status}",
  "rubric_passed": "{rubric}",
  "degraded_reasons": {json.dumps(reasons, ensure_ascii=False)}
}}
```

## 信任等级定义

| 状态 | 含义 | Rubric 阈值 |
|------|------|-------------|
| `trusted` | 数据一致，可复算验证通过 | 5/5 |
| `degraded` | 部分数据不可验证（降级运行） | < 5/5 |
| `unknown` | 信任层未初始化 | - |

## 数据血缘追溯

每条 Env Recipe 输出的 `_trust_mark` 字段包含：
- **cert_id**: 证书标识符
- **signature**: SHA-256 数据一致性签名
- **signature_prefix**: 前 12 字符（可嵌入徽章供人眼验证）
- **verification_cmd**: 独立复算命令

## 当前状态

- 签名: `{sig}`
- 签发时间: `{trust_mark.get('issued_at', '')}`
- 复算命令: `{verify_cmd}`
"""
    return doc


def main(argv: List[str] = None) -> int:
    p = argparse.ArgumentParser(description="AgriTrust Verified badge 生成")
    p.add_argument("--svg", help="导出 SVG 徽章到指定路径")
    p.add_argument("--doc", help="导出说明文档到指定路径")
    p.add_argument("--json", action="store_true", help="JSON 输出信任标记")
    p.add_argument("--quiet", action="store_true", help="静默模式")
    args = p.parse_args(argv or [])

    trust_mark = get_trust_mark()

    if args.json:
        print(json.dumps(trust_mark, ensure_ascii=False, indent=2))

    if args.svg:
        svg = render_trust_badge_svg(trust_mark)
        with open(args.svg, "w", encoding="utf-8") as f:
            f.write(svg)
        if not args.quiet:
            print(f"SVG 已导出: {args.svg}", file=sys.stderr)

    if args.doc:
        doc = render_trust_mark_document(trust_mark)
        with open(args.doc, "w", encoding="utf-8") as f:
            f.write(doc)
        if not args.quiet:
            print(f"文档已导出: {args.doc}", file=sys.stderr)

    if not args.quiet and not (args.svg or args.doc or args.json):
        print(f"Trust status: {trust_mark.get('status')} ({trust_mark.get('rubric_passed')})")
        print(f"Signature prefix: {trust_mark.get('signature_prefix')}")
        print(f"Verification: {trust_mark.get('verification_cmd')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
