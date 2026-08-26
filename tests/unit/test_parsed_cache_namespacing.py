"""Unit tests for v0.8.11(P2.2) parsed-cache namespacing by db_id."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from backend.core.rag import mineru as rag_mineru


@pytest.fixture()
def tmp_cache():
    d = Path(tempfile.mkdtemp(prefix="kbtest-cache-"))
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def test_cache_layered_by_db_id(tmp_cache):
    """Same doc_id in different db_id → separate cache paths."""
    src = tmp_cache / "doc.txt"
    src.write_text("hello world\n", encoding="utf-8")

    # First call: db_id=finance
    r1 = rag_mineru.parse_to_markdown(
        src,
        use_cache=True,
        cache_dir=tmp_cache,
        doc_id="abc",
        db_id="finance",
    )
    assert r1["method"] != "cache"
    assert r1["cache_hit"] is False

    # Verify layered path was written
    expected = tmp_cache / "finance" / "abc" / "raw.md"
    assert expected.exists()
    assert (tmp_cache / "finance" / "abc" / "meta.json").exists()

    # Second call: same doc_id, db_id=ops → should NOT hit cache (different layer)
    r2 = rag_mineru.parse_to_markdown(
        src,
        use_cache=True,
        cache_dir=tmp_cache,
        doc_id="abc",
        db_id="ops",
    )
    assert r2["cache_hit"] is False
    assert (tmp_cache / "ops" / "abc" / "raw.md").exists()


def test_cache_hit_when_layer_matches(tmp_cache):
    src = tmp_cache / "doc.txt"
    src.write_text("hello world\n", encoding="utf-8")

    r1 = rag_mineru.parse_to_markdown(
        src, use_cache=True, cache_dir=tmp_cache, doc_id="x", db_id="finance"
    )
    assert r1["cache_hit"] is False

    # Second call with same params → cache hit
    r2 = rag_mineru.parse_to_markdown(
        src, use_cache=True, cache_dir=tmp_cache, doc_id="x", db_id="finance"
    )
    assert r2["cache_hit"] is True
    assert r2["method"] == "cache"


def test_legacy_flat_path_still_readable(tmp_cache):
    """Existing flat <cache_dir>/<doc_id>/raw.md is read on first db_id call."""
    import os

    doc_id = "legacy_doc"
    legacy_dir = tmp_cache / doc_id
    legacy_dir.mkdir(parents=True)
    legacy_md = "legacy content\n"
    (legacy_dir / "raw.md").write_text(legacy_md, encoding="utf-8")
    src_mtime = 1700000000.0
    # Write the source first; Windows 下 write_text 会把 \n 转 \r\n,actual_size
    # 用 stat 拿真实字节数,避免 OS 差异。
    src = tmp_cache / "source.txt"
    src.write_text(legacy_md, encoding="utf-8")
    actual_size = src.stat().st_size
    os.utime(src, (src_mtime, src_mtime))

    (legacy_dir / "meta.json").write_text(
        json.dumps({"mtime": src_mtime, "size": actual_size}), encoding="utf-8"
    )

    r = rag_mineru.parse_to_markdown(
        src,
        use_cache=True,
        cache_dir=tmp_cache,
        doc_id=doc_id,
        db_id="finance",  # new layered request
    )
    # Falls back to legacy path
    assert r["cache_hit"] is True, r
    assert r["method"] == "cache"
    assert "legacy" in r["markdown"]


def test_no_db_id_uses_flat_path(tmp_cache):
    """When db_id is None, falls back to flat layout (legacy behaviour)."""
    src = tmp_cache / "doc.txt"
    src.write_text("hi\n", encoding="utf-8")

    rag_mineru.parse_to_markdown(
        src, use_cache=True, cache_dir=tmp_cache, doc_id="x"
    )
    assert (tmp_cache / "x" / "raw.md").exists()
    # No nested directory
    assert not (tmp_cache / "default" / "x" / "raw.md").exists()
