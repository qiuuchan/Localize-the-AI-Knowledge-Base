"""Unit tests for v0.8.11(P1.3) atomic_io module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.core import atomic_io


@pytest.fixture()
def tmpdir():
    d = Path(tempfile.mkdtemp(prefix="kbtest-atomic-"))
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def test_atomic_write_text_new_file(tmpdir):
    p = tmpdir / "x.txt"
    atomic_io.atomic_write_text(p, "hello\n")
    assert p.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_overwrite(tmpdir):
    p = tmpdir / "x.txt"
    p.write_text("old", encoding="utf-8")
    atomic_io.atomic_write_text(p, "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_atomic_write_text_unicode(tmpdir):
    p = tmpdir / "x.txt"
    atomic_io.atomic_write_text(p, "中文 ⭐ ")
    assert p.read_text(encoding="utf-8") == "中文 ⭐ "


def test_atomic_write_json_roundtrip(tmpdir):
    p = tmpdir / "x.json"
    obj = {"a": 1, "b": ["x", "y"], "c": {"nested": True}}
    atomic_io.atomic_write_json(p, obj)
    assert json.loads(p.read_text(encoding="utf-8")) == obj


def test_atomic_write_json_unicode_preserved(tmpdir):
    p = tmpdir / "x.json"
    atomic_io.atomic_write_json(p, {"k": "中文"}, ensure_ascii=False)
    assert "中文" in p.read_text(encoding="utf-8")


def test_atomic_append_jsonl_new_file(tmpdir):
    p = tmpdir / "cache.jsonl"
    atomic_io.atomic_append_jsonl(p, {"a": 1})
    atomic_io.atomic_append_jsonl(p, {"a": 2})
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"a": 2}


def test_atomic_append_jsonl_no_partial_lines(tmpdir):
    """Simulate concurrent write: ensure final file has only full JSON lines."""
    p = tmpdir / "cache.jsonl"
    for i in range(100):
        atomic_io.atomic_append_jsonl(p, {"i": i, "vec": [0.1, 0.2] * 50})
    text = p.read_text(encoding="utf-8")
    # Every non-empty line must be a complete JSON object
    for ln, raw in enumerate(text.strip().splitlines()):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            pytest.fail(f"line {ln} is not valid JSON: {raw[:80]}")
        assert "i" in obj
        assert "vec" in obj


def test_atomic_append_jsonl_over_threshold_remains_atomic(tmpdir):
    """v1.0.2:大文件仍走 open(mode='a') + fsync 真 append,不再有 read-rewrite 退回分支。

    验证两点:
      1. 始终返回 True(v1.0.1 把"read-rewrite 退回"标 False;v1.0.2 取消退回)
      2. 末尾 JSON 行存在
    """
    p = tmpdir / "cache.jsonl"
    # Simulate big existing file with valid jsonl prefix
    big_prefix = "\n".join(json.dumps({"i": i}) for i in range(1000)) + "\n"
    p.write_text(big_prefix, encoding="utf-8")
    # Pad to over 50MB with non-newline chars on the last line
    with p.open("a", encoding="utf-8") as f:
        f.write("x" * (60 * 1024 * 1024))
    used_atomic = atomic_io.atomic_append_jsonl(p, {"a": 1}, size_threshold_bytes=50 * 1024 * 1024)
    assert used_atomic is True
    # Final appended JSON object should be present (last chars)
    tail = p.read_text(encoding="utf-8")[-50:]
    assert tail.endswith('{"a": 1}\n')


def test_atomic_compact_jsonl_truncates(tmpdir):
    """v1.0.2 新增 atomic_compact_jsonl:保留最后 N 行,整体重写。"""
    from backend.core import atomic_io

    p = tmpdir / "cache.jsonl"
    lines = "\n".join(json.dumps({"i": i}) for i in range(100)) + "\n"
    p.write_text(lines, encoding="utf-8")
    kept = atomic_io.atomic_compact_jsonl(p, keep_last_n=5)
    assert kept == 5
    remaining = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln]
    assert len(remaining) == 5
    assert json.loads(remaining[-1]) == {"i": 99}


def test_atomic_write_text_creates_parent(tmpdir):
    p = tmpdir / "deep" / "nested" / "x.txt"
    atomic_io.atomic_write_text(p, "hi")
    assert p.read_text(encoding="utf-8") == "hi"


def test_atomic_write_text_no_tmp_residue(tmpdir):
    """After successful write, no .tmp files left in the directory."""
    p = tmpdir / "x.txt"
    atomic_io.atomic_write_text(p, "ok")
    leftovers = list(tmpdir.glob(".x.txt.*.tmp"))
    assert leftovers == []
