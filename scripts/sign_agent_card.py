#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2A Card JWS 签名（HMAC-SHA256，零依赖）。

背景：
  MCP 2026-08 路线图第 3 项「智能体身份与企业级安全」指出 A2A Card
  身份不可验证是生产化障碍。本脚本给 .well-known/agent.json 加 JWS
  compact serialization（header.payload.signature 三段），签名密钥从
  AGRI_A2A_SIGNING_KEY 环境变量读取。

零依赖实现：
  - hmac + hashlib + base64（标准库）
  - 无 JOSE / PyJWT / PyCrypto 依赖
  - 与 RFC 7515 JWS Compact Serialization 兼容（alg=HS256）

用法：
    AGRI_A2A_SIGNING_KEY="your-key" python scripts/sign_agent_card.py
    python scripts/sign_agent_card.py --print          # 打印签名结果，不落盘
    python scripts/sign_agent_card.py --verify         # 校验现有签名
    python scripts/sign_agent_card.py --verify-only    # 只校验不落盘

密钥管理：
  - 密钥不入库（不入 git），仅通过环境变量传递
  - 未配置时脚本会给出明确错误并退出码 2
  - 密钥缺失时不静默降级（诚实边界）：调用方必须明确知道签名不可用
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from typing import Any, Dict, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CARD_PATH = os.path.join(ROOT, ".well-known", "agent.json")
SIGNATURE_PATH = os.path.join(ROOT, ".well-known", "agent.json.jws")
KEY_ENV = "AGRI_A2A_SIGNING_KEY"


def _b64url(data: bytes) -> str:
    """RFC 7515 无 padding 的 base64url。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """RFC 7515 反向解码，容忍无 padding。"""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def _load_card() -> Dict[str, Any]:
    with open(CARD_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _payload_bytes(card: Dict[str, Any]) -> bytes:
    """规范化 JSON（sort_keys + 无额外空白）后编码，保证签名稳定可复算。"""
    return json.dumps(card, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _header_bytes(card: Dict[str, Any], alg: str = "HS256") -> bytes:
    """JWS header：声明 alg / typ + A2A 元数据（协议版本 / name / version）。"""
    header = {
        "alg": alg,
        "typ": "JWS",
        "kid": card.get("name", "unknown") + "@" + str(card.get("version", "?")),
    }
    return json.dumps(header, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign(card: Dict[str, Any], key: bytes, alg: str = "HS256") -> str:
    """生成 JWS compact serialization：header.payload.signature。"""
    h = _b64url(_header_bytes(card, alg))
    p = _b64url(_payload_bytes(card))
    signing_input = f"{h}.{p}".encode("ascii")
    if alg == "HS256":
        mac = hmac.new(key, signing_input, hashlib.sha256).digest()
    else:
        raise ValueError(f"不支持的 alg: {alg}")
    s = _b64url(mac)
    return f"{h}.{p}.{s}"


def verify(jws: str, key: bytes) -> Tuple[bool, str]:
    """校验 JWS：返回 (是否通过, 说明)。"""
    parts = jws.split(".")
    if len(parts) != 3:
        return False, f"JWS 段数 {len(parts)} != 3"
    h, p, s = parts
    try:
        header = json.loads(_b64url_decode(h))
        payload = _b64url_decode(p)
        got_sig = _b64url_decode(s)
    except Exception as e:  # noqa: BLE001
        return False, f"解码失败: {e}"
    alg = header.get("alg")
    if alg != "HS256":
        return False, f"不支持的 alg: {alg}"
    signing_input = f"{h}.{p}".encode("ascii")
    expected = hmac.new(key, signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, got_sig):
        return False, "签名不匹配"
    return True, f"校验通过 (alg={alg}, kid={header.get('kid')})"


def extract_signature_from_card(card: Dict[str, Any]) -> str | None:
    """从 agent.json 的签名字段读取。

    支持两种存法：
      1. 独立文件 .well-known/agent.json.jws（默认）
      2. 内嵌字段 card["signature"]["jws"]
    优先级：内嵌字段 > 独立文件。
    """
    embedded = card.get("signature", {}).get("jws")
    if embedded:
        return embedded
    if os.path.exists(SIGNATURE_PATH):
        with open(SIGNATURE_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="A2A Card JWS 签名")
    p.add_argument("--print", action="store_true", help="仅打印签名结果，不落盘")
    p.add_argument("--verify", action="store_true", help="仅校验现有签名，不生成新签名")
    p.add_argument("--inplace", action="store_true",
                   help="把签名写入 agent.json 的 signature.jws 字段（默认写独立文件）")
    args = p.parse_args(argv)

    key_str = os.environ.get(KEY_ENV, "")
    if not key_str:
        print(f"❌ 缺环境变量 {KEY_ENV}", file=sys.stderr)
        print(f"   示例：{KEY_ENV}=\"your-secret\" python {os.path.basename(__file__)}",
              file=sys.stderr)
        return 2

    key = key_str.encode("utf-8")
    card = _load_card()

    if args.verify:
        jws = extract_signature_from_card(card)
        if not jws:
            print("❌ 未找到签名（既不内嵌也无独立文件）", file=sys.stderr)
            return 3
        ok, msg = verify(jws, key)
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 4

    jws = sign(card, key)
    if args.print:
        print(jws)
        return 0

    if args.inplace:
        card.setdefault("signature", {})["jws"] = jws
        card["signature"]["algorithm"] = "HS256"
        card["signature"]["verification_command"] = (
            f'{KEY_ENV}="***" python scripts/sign_agent_card.py --verify'
        )
        with open(CARD_PATH, "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"✅ 签名写入 {CARD_PATH}（signature.jws）")
    else:
        with open(SIGNATURE_PATH, "w", encoding="utf-8") as f:
            f.write(jws + "\n")
        print(f"✅ 签名写入 {SIGNATURE_PATH}")

    # 复算校验一次，避免密钥错配
    ok, msg = verify(jws, key)
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
