"""core/recipe_signing.py —— 配方签名 / 验签（S1.2 负例 D1）

真实、确定性、可复算：对配方正文的规范化 JSON 求 sha256 作为 trust_mark.signature。
任何字段改动都会改变签名，验签即失败 —— 这是"配方不可被静默篡改"的可验证承诺。

与 core/trust_layer.py 的证书签名同构（规范化 + sha256），但作用于**单个配方对象**
而非全局证书；因此可作为 D1 负例的真实校验器。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def canonical(obj: Any) -> str:
    """规范化 JSON：键排序、去空白、保留 unicode。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_recipe(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """对配方正文（剔除 trust_mark 自身）求 sha256 签名。"""
    body = {k: v for k, v in recipe.items() if k != "trust_mark"}
    sig = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()
    return {"signature": sig, "signature_prefix": sig[:12]}


def verify_recipe(recipe: Dict[str, Any]) -> Dict[str, Any]:
    """验签：重算签名并与 trust_mark.signature 比对。

    返回 {"verified": bool, "expected": ..., "actual": ...}。
    缺失 trust_mark 一律 verified=False（不得静默通过）。
    """
    if "trust_mark" not in recipe:
        return {"verified": False, "reason": "missing-trust-mark"}
    expected = sign_recipe(recipe)["signature"]
    actual = (recipe.get("trust_mark") or {}).get("signature")
    return {"verified": expected == actual, "expected": expected, "actual": actual}


def tamper(recipe: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """深拷贝配方并按点路径修改一个字段（如 "environment.temperature.day_c"）。

    path 不存在时抛 KeyError（负例必须显式失败，不静默降级）。
    """
    out = json.loads(json.dumps(recipe))
    cur = out
    parts = path.split(".")
    for p in parts[:-1]:
        cur = cur[p]
    cur[parts[-1]] = value
    return out
