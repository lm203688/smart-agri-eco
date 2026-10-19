#!/usr/bin/env python3
"""M11-T1 公共复算 API：外部可独立验证 Trust Mark / Certificate。

对齐报告 per_module_deep_assessment_2026-10-13.md §M11-T1「可信标记产品化」——
把 T-1 可信标记从内部纪律（core/trust_layer.get_trust_mark）升级为**对外公共
复算 API**：任何外部消费者可以用本脚本独立复算 signature，无需依赖私有代码。

支持的三种验证模式：
  1. verify_certificate_content —— 检查证书内部 signature 与其规范化内容一致
     （离线可做，只需 JSON + SHA256；不依赖任何项目文件）
  2. verify_mark_internal —— 检查 trust_mark.signature_prefix 是 signature 前 12 字符
     （结构完整性检查，秒级，用于日志/CI）
  3. verify_mark_end_to_end —— 用本地数据重新生成 trust_mark 并对比 signature
     （需要项目数据文件；等价于 python -m core.trust_layer 的手动封装）

设计原则：
  - 零依赖 stdlib（hashlib + json + argparse）
  - 诚实边界：**signature 是内容一致性哈希，不是密码学签名（无密钥）**
    —— 它能证明"数据未被修改"，不能证明"我们就是签发者"
  - 不静默通过：任何降级/缺失都返回 verified=False + 具体原因
  - 退出码语义：0=全通过，1=验证失败，2=输入错误

用法示例：
  # 打印当前 trust_mark 供外部下载
  python scripts/verify_trust_mark.py --current

  # 验证一份证书文件（离线，仅内容一致性）
  python scripts/verify_trust_mark.py --from-certificate cert.json

  # 验证一份外部提供的 trust_mark 是否与本地上次生成的 signature 匹配
  python scripts/verify_trust_mark.py --from-mark external.json

  # 只验证 trust_mark 内部一致性（signature_prefix vs signature）
  python scripts/verify_trust_mark.py --check-prefix external.json

  # JSON 输出（供 CI / 自动化）
  python scripts/verify_trust_mark.py --from-certificate cert.json --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---- 核心原语（stdlib only）----

def canonical(obj: Any) -> str:
    """规范化 JSON 序列化：sort_keys + 紧凑分隔符，与 core/trust_layer._canonical 一致。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- 三种验证模式 ----

def verify_certificate_content(cert: Dict[str, Any]) -> Dict[str, Any]:
    """验证证书内部 signature 与内容规范化后 SHA256 一致。

    离线可做，仅依赖 JSON + SHA256。等价于：
      1. 剥掉 signature 字段
      2. canonical(cert_without_signature)
      3. SHA256
      4. 与 cert['signature'] 比对
    """
    if not isinstance(cert, dict):
        return {"verified": False, "mode": "certificate_content", "error": "输入不是 JSON 对象"}

    provided_sig = cert.get("signature")
    if not provided_sig or not isinstance(provided_sig, str):
        return {
            "verified": False,
            "mode": "certificate_content",
            "error": "证书缺少 signature 字段",
        }

    content = {k: v for k, v in cert.items() if k != "signature"}
    recomputed = sha256_hex(canonical(content))

    return {
        "verified": provided_sig == recomputed,
        "mode": "certificate_content",
        "provided_signature": provided_sig,
        "recomputed_signature": recomputed,
        "matched": provided_sig == recomputed,
        "note": (
            "signature 是内容规范化后 SHA256。匹配 = 证书对象自签名未被篡改；"
            "不匹配 = 字段被修改或删除（例如修改 data_coverage 或 rubric 数值）。"
            "本验证不验证数据源文件的实际哈希——那需要 --verify-artifacts 模式。"
        ),
    }


def verify_mark_internal(mark: Dict[str, Any]) -> Dict[str, Any]:
    """检查 trust_mark 内部结构一致性：signature_prefix 是 signature 前 12 字符。

    这是**结构性检查**，不验证数据源。用于：
      - CI 里对刚生成的 trust_mark 做快速断言
      - 日志/调试时秒级判断 trust_mark 是否自洽
    """
    if not isinstance(mark, dict):
        return {"verified": False, "mode": "mark_internal", "error": "输入不是 JSON 对象"}

    sig = mark.get("signature")
    prefix = mark.get("signature_prefix")
    if not sig or not prefix:
        return {
            "verified": False,
            "mode": "mark_internal",
            "error": "trust_mark 缺少 signature 或 signature_prefix 字段",
        }

    expected_prefix = sig[:12]
    return {
        "verified": prefix == expected_prefix,
        "mode": "mark_internal",
        "provided_prefix": prefix,
        "expected_prefix": expected_prefix,
        "matched": prefix == expected_prefix,
        "note": (
            "signature_prefix 应为 signature 前 12 字符。仅结构完整性检查——"
            "不验证 signature 是否基于当前数据源，需 --from-mark 模式端到端复算。"
        ),
    }


def verify_mark_end_to_end(provided_mark: Dict[str, Any]) -> Dict[str, Any]:
    """用本地数据 + 外部 mark 的 issued_at 重新生成 trust_mark，严格对比 signature。

    核心逻辑：core.trust_layer.issue_certificate 的 signature 是内容 sha256，
    其中包括 issued_at 时间戳。要让外部复算得到**完全一致**的 signature，
    必须用外部 mark 声明的 issued_at 作为 fixed_issued_at 重新生成。

    如果 signature 一致 → 外部 mark 基于同一份数据源、同一时刻生成；
    如果不一致 → 数据源已修改（或 issued_at 不同步，需要外部消费者重算）。
    """
    if not isinstance(provided_mark, dict):
        return {
            "verified": False,
            "mode": "mark_end_to_end",
            "error": "输入不是 JSON 对象",
        }

    provided_sig = provided_mark.get("signature")
    provided_issued_at = provided_mark.get("issued_at")

    # 用外部 mark 的 issued_at 严格重现
    from core.trust_layer import get_trust_mark, issue_certificate
    cert = issue_certificate(
        run_id="trust-mark",
        inputs={"scope": "agri_ecosystem", "scene": "distribution"},
        fixed_issued_at=provided_issued_at,
    )
    recomputed_sig = cert["signature"]

    # 同时给出当前时刻的 signature（供参考：本地数据此刻若重算会得到什么）
    local_now = get_trust_mark()
    local_now_sig = local_now.get("signature")

    return {
        "verified": provided_sig is not None and provided_sig == recomputed_sig,
        "mode": "mark_end_to_end",
        "provided_signature": provided_sig,
        "recomputed_signature_at_issued_at": recomputed_sig,
        "recomputed_issued_at": provided_issued_at,
        "current_local_signature": local_now_sig,
        "provided_prefix": provided_mark.get("signature_prefix"),
        "current_local_prefix": local_now.get("signature_prefix"),
        "local_status": local_now.get("status"),
        "local_rubric": local_now.get("rubric_passed"),
        "matched": provided_sig is not None and provided_sig == recomputed_sig,
        "note": (
            "端到端复算：用外部 mark 的 issued_at + 本地数据源严格重现 signature。"
            "匹配 = 外部 mark 基于同一份数据源 + 同一时刻生成（可复现）；"
            "不匹配 = 数据源已修改或 mark 声明的 issued_at 与实际不符。"
            "另附 current_local_signature 供参考本地此刻若重算会得到什么。"
        ),
    }


def verify_artifact_hashes(cert: Dict[str, Any], project_root: Optional[str] = None) -> Dict[str, Any]:
    """验证证书 artifacts[] 声明的每个 sha256 与磁盘实际文件哈希一致。

    这是**最强的验证**：不仅验证证书对象本身，还验证其引用的数据文件确实未被修改。
    需要项目文件存在。
    """
    if not isinstance(cert, dict):
        return {"verified": False, "mode": "artifact_hashes", "error": "输入不是 JSON 对象"}

    root = project_root or ROOT
    artifacts = cert.get("artifacts") or []
    if not artifacts:
        return {
            "verified": False,
            "mode": "artifact_hashes",
            "error": "证书缺少 artifacts[]",
        }

    results = []
    all_ok = True
    for art in artifacts:
        rel_path = art.get("path", "")
        declared_sha = art.get("sha256", "")
        abs_path = os.path.join(root, rel_path)
        exists = os.path.exists(abs_path)
        actual_sha = None
        matched = False
        if exists:
            h = hashlib.sha256()
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            actual_sha = h.hexdigest()
            matched = actual_sha == declared_sha
        else:
            matched = False
        all_ok = all_ok and matched
        results.append({
            "path": rel_path,
            "declared_sha256": declared_sha,
            "actual_sha256": actual_sha,
            "exists": exists,
            "matched": matched,
        })

    return {
        "verified": all_ok,
        "mode": "artifact_hashes",
        "artifacts_checked": len(results),
        "artifacts": results,
        "note": (
            "每个 artifact 的 sha256 与磁盘文件实际哈希比对。这是最强的验证——"
            "不仅证书对象一致，其引用的数据文件也未被修改。"
        ),
    }


# ---- I/O 辅助 ----

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def current_mark_json() -> Dict[str, Any]:
    """获取当前信任标记 JSON（等价于 core.trust_layer.get_trust_mark()）。"""
    from core.trust_layer import get_trust_mark
    return get_trust_mark()


def current_certificate() -> Dict[str, Any]:
    """获取当前完整证书（等价于 core.trust_layer.issue_certificate()）。"""
    from core.trust_layer import issue_certificate
    return issue_certificate(run_id="verify-api-current")


# ---- CLI ----

def cmd_current(args: argparse.Namespace) -> int:
    """打印当前信任标记或证书，供外部下载后独立复算。"""
    payload = current_mark_json() if not args.certificate else current_certificate()
    print(json.dumps(payload, ensure_ascii=False, indent=2 if not args.compact else None))
    return 0


def cmd_from_certificate(args: argparse.Namespace) -> int:
    """从文件读取证书并验证内部一致性。"""
    cert = load_json(args.file)
    if args.verify_artifacts:
        result = verify_artifact_hashes(cert, args.root)
    else:
        result = verify_certificate_content(cert)
    return _emit(result, args)


def cmd_from_mark(args: argparse.Namespace) -> int:
    """从文件读取外部 trust_mark，与本地重新生成的对比。"""
    mark = load_json(args.file)
    result = verify_mark_end_to_end(mark)
    return _emit(result, args)


def cmd_check_prefix(args: argparse.Namespace) -> int:
    """检查 trust_mark 内部一致性（signature_prefix 是否等于 signature 前 12 字符）。"""
    mark = load_json(args.file)
    result = verify_mark_internal(mark)
    return _emit(result, args)


def _emit(result: Dict[str, Any], args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2 if not args.compact else None))
    else:
        status = "✅ VERIFIED" if result.get("verified") else "❌ FAILED"
        print(f"{status} [{result.get('mode')}]")
        for k in ("error", "matched", "provided_signature", "recomputed_signature",
                  "local_signature", "provided_prefix", "expected_prefix",
                  "local_status", "local_rubric", "artifacts_checked"):
            if k in result:
                print(f"  {k}: {result[k]}")
        print(f"  note: {result.get('note', '')}")
    return 0 if result.get("verified") else 1


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="M11-T1 公共复算 API：外部独立验证 Trust Mark / Certificate")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --current: 打印当前标记/证书
    cur = sub.add_parser("current", help="打印当前信任标记 JSON（等价 core.trust_layer.get_trust_mark）")
    cur.add_argument("--certificate", action="store_true", help="输出完整证书而非紧凑标记")
    cur.add_argument("--compact", action="store_true", help="单行 JSON")
    # --json 是 no-op（current 默认即 JSON 输出），仅接受以保持与其他子命令一致的调用面
    cur.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    cur.set_defaults(func=cmd_current)

    # --from-certificate <file>
    fc = sub.add_parser("from-certificate", help="验证证书内部 signature 一致性")
    fc.add_argument("file", help="证书 JSON 文件路径")
    fc.add_argument("--verify-artifacts", action="store_true",
                    help="同时验证 artifacts[] 声明的 sha256 与磁盘文件一致")
    fc.add_argument("--root", default=None, help="项目根目录（默认当前脚本所在项目的父目录）")
    fc.add_argument("--json", action="store_true", help="JSON 输出")
    fc.add_argument("--compact", action="store_true")
    fc.set_defaults(func=cmd_from_certificate)

    # --from-mark <file>
    fm = sub.add_parser("from-mark", help="用本地数据端到端复算，对比外部 trust_mark")
    fm.add_argument("file", help="trust_mark JSON 文件路径")
    fm.add_argument("--json", action="store_true")
    fm.add_argument("--compact", action="store_true")
    fm.set_defaults(func=cmd_from_mark)

    # --check-prefix <file>
    cp = sub.add_parser("check-prefix", help="检查 trust_mark 内部一致性（signature_prefix vs signature）")
    cp.add_argument("file", help="trust_mark JSON 文件路径")
    cp.add_argument("--json", action="store_true")
    cp.add_argument("--compact", action="store_true")
    cp.set_defaults(func=cmd_check_prefix)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"❌ 文件不存在: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"❌ 未预期错误: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
