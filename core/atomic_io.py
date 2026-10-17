"""
core/atomic_io.py —— 零依赖原子写入底座

解决 H1 硬伤：项目 102 处 open(..., 'w') 直写 vs 3 处 os.replace，原子写占比 2.9%。
一次进程崩溃 / OOM / 断电就可能让 engine/long_term_memory.py、agent/execution_log.py 等
生产运行时点的数据损坏。

设计原则：
1. 纯标准库，零依赖（与项目一贯理念一致）
2. POSIX + Windows 双兼容（os.replace 在两者下都是原子的）
3. 提供 fsync（防断电丢失）
4. 提供 JSON 专用封装（自动 UTF-8 + sort_keys + indent=2）
5. 失败时清理 tmp 文件，不留垃圾
6. 支持文件内容哈希校验（可选，加固 F：防篡改）

用法：
    from core.atomic_io import atomic_write, atomic_write_json, atomic_append_jsonl

    # 替换: with open(path, "w", encoding="utf-8") as f: f.write(json.dumps(data))
    # 为：
    atomic_write_json(path, data)

    # 追加 JSONL（用于 execution_log）
    atomic_append_jsonl(log_path, {"event": ..., "ts": ...})
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class AtomicWriteError(OSError):
    """原子写入失败。父类 OSError，可被现有 except OSError 捕获。"""


def _same_filesystem(a: Path, b: Path) -> bool:
    """同一文件系统才能 os.replace 原子；跨盘会退化为 copy+unlink（非原子）。
    这里通过 stat 的 st_dev 判断。若任一路径不存在，视为同一 FS（写入方会创建）。"""
    try:
        return a.stat().st_dev == b.stat().st_dev
    except (FileNotFoundError, OSError):
        return True


def atomic_write(
    path: str | Path,
    data: bytes | str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
    mode: int = 0o644,
    checksum: bool = False,
) -> str | None:
    """
    原子写入文件：先写 .tmp，flush + fsync，然后 os.replace。
    任何一步失败都不会污染目标文件。

    参数：
        path     目标路径；父目录不存在会自动创建
        data     bytes 或 str（str 时用 encoding 编码）
        encoding str 类型输入时的编码，默认 utf-8
        fsync    是否 fsync（默认 True，防断电丢失；写入极频繁可关闭换取性能）
        mode     权限位（POSIX），默认 0644
        checksum 若 True，返回 SHA-256 hex；否则返回 None

    返回：
        SHA-256 hex（若 checksum=True）；否则 None

    异常：
        AtomicWriteError  包装底层的 OSError，便于上层区分
    """
    p = Path(path)
    if not isinstance(data, bytes):
        if not isinstance(data, str):
            raise TypeError(f"atomic_write: data must be bytes or str, got {type(data).__name__}")
        data = data.encode(encoding)

    p.parent.mkdir(parents=True, exist_ok=True)

    # 若目标已存在且在同一 FS 上，tmp 文件也必须与目标同目录（保证 os.replace 原子）
    tmp_dir = p.parent
    fd, tmp_name = tempfile.mkstemp(
        dir=str(tmp_dir), prefix=p.name + ".", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        if hasattr(os, "chmod"):
            try:
                os.chmod(tmp_path, mode)
            except OSError:
                pass  # Windows 下 chmod 权限位无实际意义，静默忽略

        # 原子替换：POSIX rename(2) / Windows MoveFileExW(MOVEFILE_REPLACE_EXISTING)
        try:
            os.replace(tmp_path, p)
        except OSError as e:
            raise AtomicWriteError(f"replace failed: {p} <- {tmp_path}: {e}") from e
    except BaseException:
        # 任何异常都清理 tmp 文件，不留垃圾
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    return hashlib.sha256(data).hexdigest() if checksum else None


def atomic_write_json(
    path: str | Path,
    obj: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
    fsync: bool = True,
    checksum: bool = False,
) -> str | None:
    """原子写入 JSON。默认 UTF-8、按 key 排序、缩进 2 空格、保留中文字符。

    sort_keys=True 保证同数据在不同进程/不同 Python 版本下写出 byte-for-byte 一致，
    是可复现性的基础（配合 H2 加固）。
    """
    try:
        text = json.dumps(
            obj,
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
            default=str,  # 兜底：非 JSON 原生类型（datetime、Path 等）自动 str()
        )
    except (TypeError, ValueError) as e:
        raise ValueError(f"atomic_write_json: obj is not JSON-serializable: {e}") from e
    return atomic_write(path, text, encoding="utf-8", fsync=fsync, checksum=checksum)


def atomic_append_jsonl(path: str | Path, obj: Any) -> None:
    """
    向 JSONL 文件追加一行 JSON。
    追加写无法用 os.replace 保证原子性（会破坏已有内容），
    所以用另一种策略：read-all + append + atomic_write。
    代价是 O(n)，但日志量级 < 10 MB 时可接受；超过则应切换到真正的 append-only log。

    注意：这不是并发安全的。真正并发场景请配合 core.lock 使用。
    """
    p = Path(path)
    existing = ""
    if p.exists():
        try:
            existing = p.read_text(encoding="utf-8")
        except OSError as e:
            raise AtomicWriteError(f"cannot read existing JSONL: {e}") from e
    line = json.dumps(obj, ensure_ascii=False, default=str)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    atomic_write(p, existing + line + "\n", encoding="utf-8")


def load_json_strict(path: str | Path, *, checksum: str | None = None) -> Any:
    """
    严格 JSON 加载：读失败/JSON 语法错/校验和不匹配 一律 raise，
    而不是返回 None 静默吞错（解决 H6 异常吞失败模式）。

    参数：
        path      JSON 文件路径
        checksum  若非 None，验证 SHA-256 是否匹配（防篡改，配合加固 F）

    异常：
        FileNotFoundError, JSONDecodeError, ValueError(checksum mismatch)
    """
    p = Path(path)
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        raise
    try:
        obj = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise ValueError(f"file is not valid UTF-8: {p}: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"file is not valid JSON: {p}: {e}") from e
    if checksum is not None:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != checksum:
            raise ValueError(
                f"checksum mismatch for {p}: expected={checksum[:12]}..., actual={actual[:12]}..."
            )
    return obj


# ---------------------------------------------------------------------------
# 自测：python -m core.atomic_io
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import tempfile as _tf

    tmpdir = _tf.mkdtemp(prefix="atomic_io_test_")
    p = Path(tmpdir) / "test.json"

    # 1. 基础原子写
    atomic_write_json(p, {"b": 2, "a": 1})
    assert load_json_strict(p) == {"a": 1, "b": 2}, "基本写入+读取失败"
    print("✓ 1. 基础 JSON 原子写 + 读回")

    # 2. 带校验和
    ck = atomic_write_json(p, {"x": 42}, checksum=True)
    load_json_strict(p, checksum=ck)
    print(f"✓ 2. SHA-256 校验和 ({ck[:12]}...) 验证通过")

    # 3. 校验和不匹配应抛异常
    try:
        load_json_strict(p, checksum="0" * 64)
        raise AssertionError("应该抛 checksum mismatch 异常")
    except ValueError as e:
        assert "checksum mismatch" in str(e)
        print("✓ 3. 校验和不匹配正确抛异常")

    # 4. 损坏 JSON 应抛异常
    atomic_write(p, "{invalid json", encoding="utf-8")
    try:
        load_json_strict(p)
        raise AssertionError("应该抛 JSON 解析异常")
    except ValueError as e:
        assert "not valid JSON" in str(e)
        print("✓ 4. 损坏 JSON 正确抛异常（不是静默返回 None）")

    # 5. JSONL 追加
    jl = Path(tmpdir) / "log.jsonl"
    atomic_append_jsonl(jl, {"event": "a"})
    atomic_append_jsonl(jl, {"event": "b"})
    atomic_append_jsonl(jl, {"event": "c"})
    lines = jl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3 and '"""event"":"""a"""' in lines[0] or '"event": "a"' in lines[0]
    print("✓ 5. JSONL 追加 3 行成功")

    # 6. 非字符串/bytes 输入应抛 TypeError
    try:
        atomic_write(p, 12345)
        raise AssertionError("应该抛 TypeError")
    except TypeError:
        print("✓ 6. 非法 data 类型正确抛 TypeError")

    # 7. 幂等性：同样输入重复写两次，byte-for-byte 一致
    atomic_write_json(p, {"k": [1, 2, 3]})
    a = p.read_bytes()
    atomic_write_json(p, {"k": [1, 2, 3]})
    b = p.read_bytes()
    assert a == b, "同样输入输出不一致"
    print("✓ 7. 幂等性：同输入 byte-for-byte 一致（H2 可复现前提）")

    # 8. 目录自动创建
    deep = Path(tmpdir) / "a" / "b" / "c" / "d.json"
    atomic_write_json(deep, {"ok": True})
    assert deep.exists()
    print("✓ 8. 父目录自动创建")

    # 9. tmp 文件不留垃圾
    before = set(Path(tmpdir).iterdir())
    atomic_write_json(p, {"final": True})
    after = set(Path(tmpdir).iterdir())
    tmp_left = [x for x in after - before if x.suffix == ".tmp"]
    assert not tmp_left, f"发现残留 tmp: {tmp_left}"
    print("✓ 9. 无 tmp 文件残留")

    print("\n原子写入底座全部 9 项自测通过。")
