"""Unit tests for protected-unit chunking and Chunk metadata extension.

Covers Task 2 invariants:
  - Code fences are protected units: chunk_type == "code", single chunk,
    inner ``#`` does not change header_stack, sliding window never cuts inside.
  - Markdown tables are protected units: chunk_type == "table", every data
    group repeats the header row, no single row gets sliced.
  - Blockquotes are protected units: chunk_type == "quote", stays as one chunk
    even when over max_len, and the leading ``>`` is preserved.
  - Backward compatibility: header_path / 36-char chunk id / certainty /
    chunk_type defaults are unchanged for plain text.

Covers Task 5 invariants:
  - extract_year_mentions returns unique, sorted, bounded 20xx years.
"""
from __future__ import annotations

import re

from backend.core.rag.chunker import split_into_chunks
from backend.core.rag.metadata import extract_year_mentions


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def test_code_fence_is_not_treated_as_header_and_is_not_split():
    text = (
        "# 外层\n\n"
        "```python\n"
        "# 代码里的标题\n"
        + ("x = 1\n" * 80)
        + "```\n"
    )
    chunks = split_into_chunks(text, source="code.md", max_len=80, overlap=20)

    code_chunks = [c for c in chunks if c.chunk_type == "code"]
    # Sliding window must never cut inside the protected code fence.
    assert len(code_chunks) == 1
    assert "# 代码里的标题" in code_chunks[0].text
    # The inner "# 代码里的标题" must not have pushed a new header onto the stack;
    # the code chunk still inherits "外层" from the outer # section.
    assert code_chunks[0].header_path == "外层"


def test_code_fence_inside_header_section_carries_header_path():
    chunks = split_into_chunks(
        "# A\n\nparagraph\n\n# B\n\n```py\n# inside\nbody\n```\n",
        source="code.md",
    )
    code = [c for c in chunks if c.chunk_type == "code"]
    assert len(code) == 1
    assert code[0].header_path == "B"
    assert "# inside" in code[0].text


def test_table_chunks_keep_header_and_type():
    text = (
        "# 菜单\n\n"
        "| 菜名 | 价格 |\n"
        "| --- | --- |\n"
        "| 红烧肉 | 58 |\n"
        "| 清蒸鱼 | 68 |\n"
    )
    chunks = split_into_chunks(text, source="menu.md", max_len=45, overlap=10)

    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert table_chunks, "expected at least one table chunk"
    # Every data group must repeat the header line; the table is protected
    # by row, so no row should be sliced across groups.
    for c in table_chunks:
        assert "| 菜名 | 价格 |" in c.text
        assert "| --- | --- |" in c.text
    # Both data rows must be represented across the chunks.
    combined = "\n".join(c.text for c in table_chunks)
    assert "红烧肉" in combined
    assert "清蒸鱼" in combined


def test_table_row_is_never_split_across_groups():
    # 8 data rows; small max_len forces multiple groups but no row should be cut.
    rows = [f"| row{i} | val{i} |\n" for i in range(8)]
    text = (
        "# T\n\n"
        "| k | v |\n| --- | --- |\n"
        + "".join(rows)
    )
    chunks = split_into_chunks(text, source="t.md", max_len=60, overlap=10)
    table_chunks = [c for c in chunks if c.chunk_type == "table"]
    assert table_chunks
    for c in table_chunks:
        # Each group starts with the header + separator and then full rows.
        body = c.text.splitlines()
        assert body[0] == "| k | v |"
        assert body[1] == "| --- | --- |"
        # No row is sliced, so every body row must start with "| " and end with " |".
        for line in body[2:]:
            assert line.startswith("| ") and line.endswith(" |"), line
    # All 8 rows preserved across groups in order.
    flat = "".join(c.text for c in table_chunks)
    for i in range(8):
        assert f"row{i}" in flat and f"val{i}" in flat


def test_blockquote_remains_a_protected_unit():
    text = "> 这是第一条建议\n> 这是第二条建议\n\n普通段落"
    chunks = split_into_chunks(text, source="quote.md", max_len=20, overlap=5)

    quote_chunks = [c for c in chunks if c.chunk_type == "quote"]
    # A blockquote is one protected unit regardless of max_len.
    assert len(quote_chunks) == 1
    assert quote_chunks[0].text.startswith(">")
    # Both quote lines must still be in the single protected chunk.
    assert "第一条建议" in quote_chunks[0].text
    assert "第二条建议" in quote_chunks[0].text
    # And the trailing paragraph is not folded into the quote.
    assert "普通段落" in [c.text for c in chunks if c.chunk_type == "text"][0]


def test_existing_headers_and_ids_remain_compatible():
    chunks = split_into_chunks("# A\n\n正文", source="a.md")
    assert chunks[0].header_path == "A"
    assert UUID_RE.match(chunks[0].id), chunks[0].id
    assert chunks[0].certainty in {"fact", "opinion", "draft", "neutral"}
    assert chunks[0].chunk_type == "text"


def test_chunk_metadata_defaults_are_exposed():
    chunks = split_into_chunks("# A\n\n正文", source="a.md")
    c = chunks[0]
    # New fields exposed and defaulted.
    assert hasattr(c, "date")
    assert hasattr(c, "days_old")
    assert hasattr(c, "temporal_weight")
    assert hasattr(c, "certainty")
    assert hasattr(c, "chunk_type")
    # Without document_date/mtime, date defaults to "" and days_old stays None,
    # temporal_weight stays at the neutral 1.0, certainty is whatever
    # classify_certainty decides for "正文" (a 2-char short string → "draft").
    assert c.date == ""
    assert c.days_old is None
    assert c.temporal_weight == 1.0


def test_document_date_and_mtime_thread_through_to_chunks(monkeypatch):
    from datetime import datetime, timezone
    import backend.core.rag.chunker as chunker_mod

    # Pin 'today' so the calculation is deterministic across environments.
    fixed_today = datetime(2026, 7, 20).date()

    def fake_build_chunk_metadata(text, *, document_date="", document_mtime=None, today=None):
        resolved = document_date
        if not resolved and document_mtime is not None:
            resolved = datetime.fromtimestamp(
                document_mtime, tz=timezone.utc
            ).date().isoformat()
        from backend.core.rag.metadata import (
            calculate_days_old,
            calculate_temporal_weight,
            classify_certainty,
        )
        days_old = calculate_days_old(resolved, today=today or fixed_today)
        return {
            "date": resolved,
            "days_old": days_old,
            "temporal_weight": calculate_temporal_weight(days_old),
            "certainty": classify_certainty(text),
        }

    monkeypatch.setattr(chunker_mod, "build_chunk_metadata", fake_build_chunk_metadata)

    chunks = split_into_chunks(
        "# A\n\n正文段落",
        source="a.md",
        document_date="2026-07-18",
    )
    assert chunks[0].date == "2026-07-18"
    assert chunks[0].days_old == 2
    # 2 days old → exp(-2/365) ≈ 0.994536, well above the 0.1 floor.
    assert 0.99 < chunks[0].temporal_weight <= 1.0


def test_old_call_signature_without_metadata_kwargs_still_works():
    # Pure positional/known kwargs must remain compatible with prior callers.
    chunks = split_into_chunks("# A\n\nB", source="a.md", max_len=400, overlap=50)
    assert chunks
    assert chunks[0].header_path == "A"


def test_year_mentions_are_unique_sorted_and_bounded():
    assert extract_year_mentions("2026 预算、2025 预算、2026") == (2025, 2026)
    assert extract_year_mentions("编号 12026") == ()
