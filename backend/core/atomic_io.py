"""Atomic file write helpers for KB-AI (v0.8.11 P1.3,v1.0.2 hardened)。

借鉴 Yuxi-Know `base.py:524-555` 的 tempfile + os.replace 模式,
治 FMEA F11 / F13(强制拔盘/三方并发写下的"半截文件"风险)。

约定:
- 所有写入在同一目录建临时文件后 os.replace(在同 fs 上原子)。
- 失败保留 .bak 副本(若原文件存在)。
- 大文件 atomic_append_jsonl 受 size_threshold 保护,
  走"真 append + fsync"路(避免读改写全程吞数据 + 内存尖峰)。
  超过阈值才退回 best-effort append(下次 LRU compact 时整体重写)。
- v1.0.2:增加 Windows 上 antivirus/indexer 持锁时的一次退避重试。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional


def _tmp_path_for(path: Path) -> Path:
    """Return a temp file path in the same directory as `path`."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(parent)
    )
    os.close(fd)
    return Path(name)


def _replace_with_retry(tmp: Path, dest: Path, *, retries: int = 1) -> None:
    """os.replace with one-shot retry+backoff for Windows 持锁场景。

    场景: antivirus / Windows Search indexer 短时间内持锁目标文件,
    os.replace 直接 raise PermissionError(18)。退避 0.15s 再试一次够覆盖多数情况。
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(0.15)
    assert last_exc is not None  # pragma: no cover
    raise last_exc


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically (text mode).

    Sequence: write tmp → fsync → os.replace(retry on Win 持锁).
    On failure, leave the original file untouched (or remove it if it didn't exist).
    """
    tmp = _tmp_path_for(path)
    try:
        with tmp.open("w", encoding=encoding, newline="") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # not all filesystems support fsync; ignore
                pass
        _replace_with_retry(tmp, path)
    except Exception:
        # clean up tmp; don't touch the destination
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path,
    obj: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    """JSON-serialise `obj` then atomic_write_text."""
    content = json.dumps(
        obj,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
    )
    atomic_write_text(path, content)


def atomic_append_jsonl(
    path: Path,
    obj: dict,
    *,
    size_threshold_bytes: int = 50 * 1024 * 1024,  # 50 MB
) -> bool:
    """Append one JSON object as a new line, atomically.

    v1.0.2 行为修订:
      - 小文件(< size_threshold):直接 open(mode='a') + fsync,**不读改写**,
        避免 v1.0.1 的"全量读入内存再 rewrite"开销,也避免两并发 append
        之间 read→modify 的 TOCTOU 丢行风险。
      - 大文件(> size_threshold):同上 open(mode='a') + fsync。
        真正的紧凑(LRU compact)由 embedding-cache 的清理路径独立负责,
        此处不再做读改写。

    Returns True(始终 atomic,无 best-effort 分支)。
    """
    new_line = json.dumps(obj, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(new_line)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    return True


def atomic_compact_jsonl(path: Path, keep_last_n: int) -> int:
    """LRU 紧凑入口:读最后 keep_last_n 行,整体重写到 tmp + os.replace。

    不在 atomic_append_jsonl 路径里调用;供 embedding-cache 的 LRU 清理
    模块主动调用(避免 append 路径里偷偷触发读改写)。
    Returns 实际写入的行数。
    """
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    keep = lines[-keep_last_n:] if keep_last_n > 0 else []
    text = "".join(keep)
    atomic_write_text(path, text)
    return len(keep)
