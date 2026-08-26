"""Unit tests for the upload-time Qdrant payload helper and main pipeline.

Covers Task 3 invariants:
  - `_build_point` keeps the legacy payload fields (text, source, source_file,
    section, header_path) untouched.
  - It also writes the new metadata fields (header_level, date, days_old,
    temporal_weight, certainty, chunk_type) sourced from the Chunk dataclass
    populated by Task 2.
  - Old-style Chunk instances without metadata still build a valid payload
    using the defaults exposed by the dataclass.
  - `_build_point` defensively strips any directory prefix from ``source_file``
    so an absolute Windows / POSIX path never leaks into the Qdrant payload.
  - `_process_upload` strips YAML frontmatter before calling
    ``split_into_chunks``, threads ``document_date`` / ``document_mtime``
    derived from the saved file, hands safe filenames (not absolute paths)
    to Qdrant, and writes the original 4-tuple shape into keyword_index —
    with MinerU, Qdrant, embedder, keyword_index and SQLite fully mocked, so
    nothing reads or writes ``E:/data/parsed`` or any other real path.

Run from project root:
    backend/.venv/Scripts/python -m pytest tests/unit/test_knowledge_metadata.py -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.api import knowledge as knowledge_api
from backend.api.knowledge import _build_point
from backend.core.rag.chunker import Chunk


# ---------------------------------------------------------------------------
# Payload helper: every field is asserted explicitly
# ---------------------------------------------------------------------------


def _full_chunk() -> Chunk:
    return Chunk(
        id="00000000-0000-0000-0000-000000000001",
        text="2026年营收增长12%",
        source="report.md",
        section=2,
        header_path="经营 > 数据",
        header_level=2,
        tokens=["营收"],
        date="2026-07-01",
        days_old=19,
        temporal_weight=0.94935,
        certainty="fact",
        chunk_type="text",
    )


def test_build_point_keeps_legacy_fields_and_adds_metadata():
    chunk = _full_chunk()
    point = _build_point(chunk, "report.md", [0.1, 0.2])

    # Top-level shape
    assert point["id"] == chunk.id
    assert point["vector"] == [0.1, 0.2]

    # Legacy fields (verbatim from old inline code).
    assert point["payload"]["text"] == "2026年营收增长12%"
    assert point["payload"]["source"] == "report.md"
    assert point["payload"]["source_file"] == "report.md"
    assert point["payload"]["section"] == 2
    assert point["payload"]["header_path"] == "经营 > 数据"

    # New Task 3 metadata fields — every one explicitly asserted.
    assert point["payload"]["header_level"] == 2
    assert point["payload"]["date"] == "2026-07-01"
    assert point["payload"]["days_old"] == 19
    assert point["payload"]["temporal_weight"] == 0.94935
    assert point["payload"]["certainty"] == "fact"
    assert point["payload"]["chunk_type"] == "text"

    # No surprise keys — exactly the 11 documented fields plus id/vector.
    assert set(point) == {"id", "vector", "payload"}
    assert set(point["payload"]) == {
        "text",
        "source",
        "source_file",
        "section",
        "header_path",
        "header_level",
        "date",
        "days_old",
        "temporal_weight",
        "certainty",
        "chunk_type",
        "year_mentions",
        "sheet_name",
        "row_start",
        "row_end",
        "columns",
    }


def test_build_point_defaults_legacy_chunk_metadata():
    chunk = Chunk(
        id="00000000-0000-0000-0000-000000000002",
        text="旧格式",
        source="old.md",
        section=1,
        header_path="",
        header_level=0,
    )
    payload = _build_point(chunk, "old.md", [0.0])["payload"]

    # Legacy fields still come through with the values the caller supplied.
    assert payload["text"] == "旧格式"
    assert payload["source"] == "old.md"
    assert payload["source_file"] == "old.md"
    assert payload["section"] == 1
    assert payload["header_path"] == ""

    # New metadata fields fall back to the dataclass defaults — no exception.
    assert payload["header_level"] == 0
    assert payload["date"] == ""
    assert payload["days_old"] is None
    assert payload["temporal_weight"] == 1.0
    assert payload["certainty"] == "neutral"
    assert payload["chunk_type"] == "text"


@pytest.mark.parametrize(
    "raw,expected",
    [
        # POSIX absolute path
        ("/var/data/uploads/report.md", "report.md"),
        # Windows-style absolute path (backslash)
        ("E:\\uploads\\report.md", "report.md"),
        # Mixed separators
        ("E:/uploads\\report.md", "report.md"),
        # Trailing slash on a directory-like input
        ("/var/data/uploads/", "uploads"),
        # Already-safe bare filename is left alone
        ("report.md", "report.md"),
    ],
)
def test_build_point_strips_absolute_path_to_basename(raw, expected):
    chunk = _full_chunk()
    payload = _build_point(chunk, raw, [0.1])["payload"]
    assert payload["source_file"] == expected
    # And the rest of the payload is unaffected by the sanitization.
    assert payload["source"] == "report.md"


def test_build_point_includes_structured_xlsx_metadata():
    chunk = Chunk(
        id="00000000-0000-0000-0000-000000000003",
        text="# 工作表：门店\n\n第 2 行：年份=2026",
        source="progress.xlsx",
        section=1,
        header_path="工作表：门店",
        header_level=1,
        tokens=["年份"],
        chunk_type="xlsx_row_group",
        year_mentions=[2026],
        sheet_name="门店",
        row_start=2,
        row_end=2,
        columns=["年份"],
    )

    payload = _build_point(chunk, "progress.xlsx", [0.0])["payload"]

    assert payload["chunk_type"] == "xlsx_row_group"
    assert payload["year_mentions"] == [2026]
    assert payload["sheet_name"] == "门店"
    assert payload["row_start"] == 2
    assert payload["row_end"] == 2
    assert payload["columns"] == ["年份"]


# ---------------------------------------------------------------------------
# _process_upload main-chain integration test (no real Qdrant / no real API /
# no project data dir). Verifies the wiring described in the Task 3 brief.
# ---------------------------------------------------------------------------


class _Recorder:
    """Tiny stand-in that records how it was called."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return None


def _patch_upload_dependencies(monkeypatch, tmp_path: Path, captured: dict):
    """Replace every external dependency `_process_upload` reaches.

    All fakes live in ``tmp_path`` / in-memory; nothing touches the real
    Qdrant / SQLite / project data / Aliyun API / MinerU. In particular
    ``rag_mineru.parse_to_markdown`` is monkeypatched so the production
    cache directory (``E:/data/parsed``) is never written to — without this
    stub the parser would create ``<cache_dir>/<doc_id>/raw.md`` and
    ``meta.json`` on disk during the test.
    """
    # 1. Stand-in saved file inside tmp_path so saved_path.stat().st_mtime
    #    works without touching the real USB / project data dir.
    fake_saved = tmp_path / "1717000000_demo.md"
    fixture_markdown = (
        "---\ndate: 2026-07-01\ncertainty: fact\n---\n# 标题\n正文段落。\n"
    )
    fake_saved.write_text(fixture_markdown, encoding="utf-8")

    # 2. Temporary SQLite for keyword_index — overrides get_data_dir() so the
    #    code path that calls _db_path() inside _process_upload also uses it.
    db_file = tmp_path / "db.sqlite"
    monkeypatch.setattr(
        knowledge_api, "_db_path", lambda: db_file
    )

    # 2a. Stub MinerU parser so `_process_upload` step 1 never reaches the
    #     real cache directory or the real Aliyun API. Returns the same
    #     fixture markdown that was just written to the fake saved file.
    captured["parse_to_markdown_calls"] = []

    def fake_parse_to_markdown(saved_path, **kwargs):
        captured["parse_to_markdown_calls"].append(
            {
                "saved_path": str(saved_path),
                "kwargs": kwargs,
            }
        )
        return {
            "markdown": fixture_markdown,
            "method": "fixture-stub",
            "cache_hit": True,
        }

    monkeypatch.setattr(
        knowledge_api.rag_mineru,
        "parse_to_markdown",
        fake_parse_to_markdown,
    )

    # 3. Capture metadata.frontmatter / body / document_date passed downstream.
    captured["extract_frontmatter_calls"] = []
    real_extract = knowledge_api.rag_metadata.extract_frontmatter
    real_resolve = knowledge_api.rag_metadata.resolve_document_date

    def fake_extract(markdown):
        frontmatter, body = real_extract(markdown)
        captured["extract_frontmatter_calls"].append(
            {"frontmatter_keys": sorted(frontmatter.keys()), "body_starts_with": body[:40]}
        )
        return frontmatter, body

    def fake_resolve(frontmatter, file_mtime=None):
        result = real_resolve(frontmatter, file_mtime=file_mtime)
        captured["resolve_document_date"] = {
            "frontmatter": dict(frontmatter),
            "file_mtime": file_mtime,
            "resolved": result,
        }
        return result

    monkeypatch.setattr(knowledge_api.rag_metadata, "extract_frontmatter", fake_extract)
    monkeypatch.setattr(knowledge_api.rag_metadata, "resolve_document_date", fake_resolve)

    # 4. Capture chunker.split_into_chunks invocation.
    captured["split_calls"] = []

    def fake_split(markdown, **kwargs):
        captured["split_calls"].append(
            {"body_starts_with": markdown[:40], "kwargs": kwargs}
        )
        # Return two stable, metadata-rich chunks so downstream stages run.
        return [
            Chunk(
                id="11111111-0000-0000-0000-000000000001",
                text="正文段落一。",
                source=kwargs["source"],
                section=1,
                header_path="标题",
                header_level=1,
                tokens=["正文"],
                date=kwargs.get("document_date", ""),
                days_old=19 if kwargs.get("document_date") else None,
                temporal_weight=0.95,
                certainty="fact",
                chunk_type="text",
            ),
            Chunk(
                id="22222222-0000-0000-0000-000000000002",
                text="正文段落二。",
                source=kwargs["source"],
                section=2,
                header_path="标题 > 子节",
                header_level=2,
                tokens=["段落"],
                date=kwargs.get("document_date", ""),
                days_old=19 if kwargs.get("document_date") else None,
                temporal_weight=0.95,
                certainty="fact",
                chunk_type="text",
            ),
        ]

    monkeypatch.setattr(knowledge_api.rag_chunker, "split_into_chunks", fake_split)

    # 5. Fake embedder (no network).
    monkeypatch.setattr(
        knowledge_api.rag_embedder,
        "embed_texts",
        lambda texts: ([[0.1, 0.2, 0.3] for _ in texts], {"dim": 3, "mock": True}),
    )

    # 6. Fake qdrant collection + upsert — capture the points handed over.
    monkeypatch.setattr(
        knowledge_api.rag_qdrant, "ensure_collection", _Recorder()
    )
    captured["upsert_points_calls"] = []

    def fake_upsert(points, collection):
        captured["upsert_points_calls"].append(
            {"points": points, "collection": collection}
        )
        return {"result": "ok"}

    monkeypatch.setattr(knowledge_api.rag_qdrant, "upsert_points", fake_upsert)

    # 7. Fake keyword_index write_rows — capture exact 4-tuple shape.
    captured["write_rows_calls"] = []

    def fake_write_rows(rows, db_path=None):
        captured["write_rows_calls"].append({"rows": rows, "db_path": str(db_path) if db_path else None})
        return len(rows)

    monkeypatch.setattr(knowledge_api.rag_keyword, "write_rows", fake_write_rows)

    # 8. Stub the verification SQL probe so it doesn't touch the real db.
    monkeypatch.setattr(
        sqlite3, "connect", lambda p: _SqlLiteProbe(p)
    )

    return fake_saved


# Capture the *real* sqlite3.connect at module import so the probe can
# always reach the C extension, even if sibling tests monkeypatch
# ``sqlite3.connect`` to a no-kwarg lambda. This avoids infinite recursion
# in v0.8.11(P1.2)+ tests where _process_upload also touches SQLite.
_REAL_SQLITE3_CONNECT = sqlite3.connect


class _SqlLiteProbe:
    """Minimal sqlite3.Connection look-alike used only by the verification
    step in `_process_upload`. Forwards writes through to a real temp DB so
    the COUNT(DISTINCT point_id) probe succeeds."""

    def __init__(self, path):
        self._path = path
        # Always reach the real (C-level) sqlite3.connect — bypasses any
        # monkeypatching installed by sibling tests so we don't recurse.
        try:
            self._conn = _REAL_SQLITE3_CONNECT(str(path), check_same_thread=False)
        except TypeError:
            # Some monkeypatched shims don't accept kwargs.
            self._conn = _REAL_SQLITE3_CONNECT(str(path))
        # keyword_index table is what `_process_upload` counts against; create
        # it here so the SELECT below returns 0 rather than raising.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS keyword_index ("
            "  token TEXT, point_id TEXT, source TEXT, text TEXT"
            ")"
        )
        self._conn.commit()

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_process_upload_main_chain_uses_frontmatter_and_safe_source_file(
    monkeypatch, tmp_path
):
    captured = {}
    fake_saved = _patch_upload_dependencies(monkeypatch, tmp_path, captured)

    # Seed an empty _TASKS entry the way upload_document does.
    task_id = "test-task-001"
    knowledge_api._TASKS[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "stage": "等待处理",
        "created_at": 0,
    }

    # Drive the background pipeline with the fake saved path.
    knowledge_api._process_upload(task_id, fake_saved, source="demo.md")

    task = knowledge_api._TASKS[task_id]
    assert task["status"] == "done", task
    assert task["chunk_count"] == 2

    # (pre-a) parse_to_markdown was called with the saved path and the
    #     expected kwargs; the stub returns the fixture markdown instead
    #     of writing to the real E:/data/parsed cache.
    assert captured["parse_to_markdown_calls"], "parse_to_markdown not called"
    pmk = captured["parse_to_markdown_calls"][0]
    assert pmk["saved_path"] == str(fake_saved)
    assert pmk["kwargs"].get("use_cache") is True
    assert pmk["kwargs"].get("doc_id") == knowledge_api._make_doc_id("demo.md")
    # The cache_dir argument is whatever _PARSED_DIR points at — the stub
    # receives it but never opens or writes anything there.
    assert "cache_dir" in pmk["kwargs"]

    # (a) extract_frontmatter was called and the body passed downstream no
    #     longer starts with the "---\ndate: ..." frontmatter.
    assert captured["extract_frontmatter_calls"], "extract_frontmatter not called"
    body = captured["extract_frontmatter_calls"][0]["body_starts_with"]
    assert body.startswith("# 标题"), f"frontmatter not stripped; body starts with: {body!r}"

    # (b) split_into_chunks received markdown_body (frontmatter stripped)
    #     and the right keyword args.
    split = captured["split_calls"][0]
    assert split["body_starts_with"].startswith("# 标题")
    assert split["kwargs"]["source"] == "demo.md"
    assert split["kwargs"]["document_date"] == "2026-07-01"
    # mtime comes from saved_path.stat().st_mtime; assert it's a positive float.
    assert isinstance(split["kwargs"]["document_mtime"], float)
    assert split["kwargs"]["document_mtime"] > 0

    # (c) resolve_document_date was invoked with the parsed frontmatter + mtime.
    rdd = captured["resolve_document_date"]
    assert rdd["frontmatter"].get("date") == "2026-07-01"
    assert rdd["file_mtime"] == split["kwargs"]["document_mtime"]
    assert rdd["resolved"] == "2026-07-01"

    # (d) Qdrant upsert received a list of points; every point's source_file
    #     is the safe filename (no path components), id matches chunk.id, and
    #     payload carries all 11 documented fields.
    upsert = captured["upsert_points_calls"][0]
    assert upsert["collection"] == knowledge_api.DEFAULT_COLLECTION
    assert len(upsert["points"]) == 2
    for p, expected_id in zip(
        upsert["points"],
        [
            "11111111-0000-0000-0000-000000000001",
            "22222222-0000-0000-0000-000000000002",
        ],
    ):
        assert p["id"] == expected_id
        assert p["vector"] == [0.1, 0.2, 0.3]
        payload = p["payload"]
        assert payload["source"] == "demo.md"
        assert payload["source_file"] == fake_saved.name
        # No path separator in source_file — defensive basename held up.
        assert "/" not in payload["source_file"]
        assert "\\" not in payload["source_file"]
        assert set(payload) == {
            "text",
            "source",
            "source_file",
            "section",
            "header_path",
            "header_level",
            "date",
            "days_old",
            "temporal_weight",
            "certainty",
            "chunk_type",
            "year_mentions",
            "sheet_name",
            "row_start",
            "row_end",
            "columns",
        }

    # (e) keyword_index.write_rows was called with the original 4-tuple shape
    #     (token, point_id, source, text) — one row per (chunk, token).
    wr = captured["write_rows_calls"][0]
    assert wr["rows"], "write_rows never called"
    for row in wr["rows"]:
        assert len(row) == 4
        token, point_id, src, text = row
        assert isinstance(token, str) and token
        assert isinstance(point_id, str) and point_id
        assert src == "demo.md"
        assert isinstance(text, str) and text

    # (f) Qdrant ensure_collection was invoked exactly once.
    ensure_calls = knowledge_api.rag_qdrant.ensure_collection.calls
    assert len(ensure_calls) == 1
    assert ensure_calls[0][0] == (knowledge_api.DEFAULT_COLLECTION,)


# Note: an earlier `test_process_upload_handles_absolute_path_safely_via_
# basename_normalization` was deleted in the §9 review pass. Its scenario
# (passing `saved_path.name` to `_build_point`) only re-verified behaviour
# already covered by `test_build_point_strips_absolute_path_to_basename`
# parametrize above. The defensive basename normalization lives inside
# `_build_point`; the main chain intentionally only ever passes the safe
# `saved_path.name`, so a separate main-chain test added no signal.
