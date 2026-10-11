#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2A Card JWS 签名校验脚本（供外部消费者使用）。

用途：
  任何调用方可用此脚本验证 .well-known/agent.json 是否被篡改。
  签名密钥通过 AGRI_A2A_SIGNING_KEY 环境变量提供。

用法：
  AGRI_A2A_SIGNING_KEY="..." python scripts/verify_agent_card.py
  AGRI_A2A_SIGNING_KEY="..." python scripts/verify_agent_card.py --jws "<jws-string>"

退出码：
  0 = 签名有效
  2 = 缺密钥
  3 = 找不到签名
  4 = 签名不匹配（可能被篡改）
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.sign_agent_card import (  # noqa: E402
    CARD_PATH, KEY_ENV, _load_card, extract_signature_from_card, verify,
)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="A2A Card JWS 签名校验")
    p.add_argument("--jws", help="直接传入 JWS 字符串，跳过文件读取")
    args = p.parse_args(argv)

    key_str = os.environ.get(KEY_ENV, "")
    if not key_str:
        print(f"❌ 缺环境变量 {KEY_ENV}", file=sys.stderr)
        return 2

    key = key_str.encode("utf-8")

    if args.jws:
        jws = args.jws.strip()
    else:
        card = _load_card()
        jws = extract_signature_from_card(card)
        if not jws:
            print("❌ 未找到签名", file=sys.stderr)
            return 3

    ok, msg = verify(jws, key)
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
