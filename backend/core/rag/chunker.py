"""Markdown header-aware sliding-window chunker with protected units.

Mirrors scripts/lib/Tokenizer.ps1's chunking behavior:
  - Split by markdown headers (`#` `##` `###` ...) into sections.
  - Within each section, split on blank lines into paragraphs.
  - If a paragraph is too long, sliding-window with overlap.
  - Short paragraphs are accumulated until they exceed max length,
    then flushed; the tail (overlap chars) is kept for the next chunk.
  - Each chunk keeps the header path (e.g. "# Title > ## Section > ### Subsection")
    so the Qdrant payload can be searched by section.

Task 2 (v0.8.11) adds protected units that bypass header parsing and the
sliding window:
  - Code fences: ```` ``` ```` open and close; everything in between is one
    chunk, regardless of length, and inner ``#`` lines do not change the
    header_stack.
  - Tables: lines starting with ``|`` followed by a separator row ``| --- |``.
    Data rows are grouped so that every emitted chunk starts with the header
    + separator and never slices a single row.
  - Blockquotes: consecutive lines starting with ``>`` are one protected unit.

Chunk also gains optional ``date``, ``days_old``, ``temporal_weight``,
``certainty``, and ``chunk_type`` fields. These are populated via
``build_chunk_metadata`` from Task 1; the chunk ID hash keeps using only
``(source, text)`` so existing IDs are stable.

Task 5 (v1.2 PR2) adds structured-document metadata for chunks produced from
xlsx inputs:
  - ``year_mentions`` is filled for every chunk via extract_year_mentions
    so year filtering and temporal weighting see the same set of years that
    the query profile does.
  - When ``document_type == "xlsx"`` is passed, ``split_into_chunks`` runs
    a lightweight regex pass over each emitted chunk to recover the sheet
    name, header columns, and row range, and re-labels the chunk as
    ``xlsx_row_group`` so downstream payload writers and retriever
    diagnostics can group rows by sheet.
  - Plain markdown / text / docx / pdf / pptx chunks keep their previous
    ``text / code / quote / table`` types; the new fields stay at their
    default values so legacy callers see no change.

Defaults come from parse-doc.ps1:
  - max_len = 800
  - overlap = 150
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .metadata import build_chunk_metadata, extract_year_mentions
from .tokenizer import get_tokens

MAX_LEN_DEFAULT = 800
OVERLAP_DEFAULT = 150

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
# Table separator row: starts and ends with |, contains at least one ---.
# Accepts alignment cells like "| --- | :---: | ---: |".
_TABLE_SEP_DASHES = re.compile(r"-{3,}")
# Structured xlsx output (see format_xlsx_sheet in mineru.py):
#   # 工作表：<title>
#   表头：<col1> | <col2> | ...
#   第 <n> 行：<col1>=<val1>；<col2>=<val2>
#   ...
# We only consume these to enrich Chunk metadata; chunker never re-parses
# the workbook itself.
_XLSX_SHEET_RE = re.compile(r"^#\s*工作表[：:]\s*(.+?)\s*$", re.MULTILINE)
_XLSX_HEADER_RE = re.compile(r"^表头[：:]\s*(.+?)\s*$", re.MULTILINE)
_XLSX_ROW_RE = re.compile(r"^第\s*(\d+)\s*行[：:]", re.MULTILINE)


def _is_table_sep_line(s: str) -> bool:
    return (
        s.startswith("|")
        and s.endswith("|")
        and _TABLE_SEP_DASHES.search(s) is not None
    )


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    section: int
    header_path: str
    header_level: int
    tokens: List[str] = field(default_factory=list)
    # Task 2 metadata (populated via build_chunk_metadata).
    date: str = ""
    days_old: Optional[int] = None
    temporal_weight: float = 1.0
    certainty: str = "neutral"
    chunk_type: str = "text"
    # Task 5 structured-document metadata. Defaults are empty / None so
    # existing callers that build Chunk directly see no behaviour change.
    year_mentions: List[int] = field(default_factory=list)
    sheet_name: str = ""
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    columns: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "meta": {
                "section": self.section,
                "header_path": self.header_path,
                "header_level": self.header_level,
            },
        }


@dataclass
class _Unit:
    """Internal logical unit emitted by ``_parse_units``."""

    text: str
    kind: str = "text"  # one of: text, code, quote, table


def _strip_text(s: str) -> str:
    return s.strip()


def _format_header_path(stack: List[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in stack)


def _make_chunk_id(source: str, text: str) -> str:
    """Match Format-AsUuid(Get-Sha256Short source|text) from PowerShell.

    Metadata fields deliberately do not participate in the hash so existing
    Qdrant IDs stay stable when date/certainty metadata is added later.
    """
    h = hashlib.sha256(f"{source}|{text}".encode("utf-8")).hexdigest()[:32]
    # 8-4-4-4-12 UUID formatting
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _split_long_paragraph(text: str, max_len: int, overlap: int) -> List[str]:
    """Sliding window split when a single paragraph exceeds max_len."""
    if len(text) <= max_len:
        return [text]
    step = max(1, max_len - overlap)
    parts: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_len, n)
        parts.append(text[start:end])
        if end >= n:
            break
        start += step
    return parts


def _accumulate_paragraphs(
    paragraphs: List[str], max_len: int, overlap: int
) -> List[str]:
    """Pack short paragraphs into chunks of <= max_len, carrying overlap tail."""
    chunks: List[str] = []
    if not paragraphs:
        return chunks
    buf = ""
    for p in paragraphs:
        if len(p) > max_len:
            # Flush current buffer first
            if buf:
                chunks.append(buf.strip())
                # Keep tail as overlap for next chunk
                buf = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            # Split long paragraph and add each piece
            for piece in _split_long_paragraph(p, max_len, overlap):
                if buf:
                    piece = (buf + " " + piece).strip() if buf else piece
                if len(piece) > max_len:
                    # Re-slice if still too long after buffer merge
                    sub = _split_long_paragraph(piece, max_len, overlap)
                    for s in sub[:-1]:
                        chunks.append(s.strip())
                    buf = sub[-1] if sub else ""
                else:
                    chunks.append(piece.strip())
                    buf = piece[-overlap:] if overlap > 0 and len(piece) > overlap else ""
            continue

        candidate = (buf + "\n\n" + p).strip() if buf else p.strip()
        if len(candidate) > max_len and buf:
            chunks.append(buf.strip())
            buf = p.strip()
        else:
            buf = candidate
    if buf:
        chunks.append(buf.strip())
    return [c for c in chunks if c]


def _parse_units(lines: List[str]) -> List[_Unit]:
    """Walk raw markdown lines and group them into protected / text units.

    Protected units (``code``, ``quote``, ``table``) are emitted as a single
    ``_Unit`` regardless of internal blank lines; their internal ``#`` and
    ``>`` and ``|`` characters must not reach the header parser.
    """

    def _is_blank(idx: int) -> bool:
        return idx < len(lines) and lines[idx].strip() == ""

    def _is_code_fence(idx: int) -> bool:
        return idx < len(lines) and lines[idx].lstrip().startswith("```")

    def _is_quote_start(idx: int) -> bool:
        return idx < len(lines) and lines[idx].lstrip().startswith(">")

    def _is_table_start(idx: int) -> bool:
        if idx >= len(lines):
            return False
        cur = lines[idx].strip()
        if not (cur.startswith("|") and cur.endswith("|")):
            return False
        nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
        return bool(nxt) and _is_table_sep_line(nxt)

    units: List[_Unit] = []
    i = 0
    while i < len(lines):
        # Code fence: consume from opening ``` to next matching ```.
        if _is_code_fence(i):
            start = i
            i += 1
            while i < len(lines) and not _is_code_fence(i):
                i += 1
            end = i + 1 if _is_code_fence(i) else i
            units.append(_Unit(text="\n".join(lines[start:end]), kind="code"))
            i = end
            continue

        # Blockquote: consecutive '>'-prefixed lines.
        if _is_quote_start(i):
            start = i
            while i < len(lines) and _is_quote_start(i):
                i += 1
            units.append(_Unit(text="\n".join(lines[start:i]), kind="quote"))
            continue

        # Table: header | separator | data rows.
        if _is_table_start(i):
            start = i
            i += 2  # consume header + separator
            while i < len(lines) and lines[i].strip().startswith("|"):
                i += 1
            units.append(_Unit(text="\n".join(lines[start:i]), kind="table"))
            continue

        # Plain text: group consecutive non-blank, non-protected lines as a
        # single text unit (blank lines act as paragraph separators).
        if not _is_blank(i):
            start = i
            while i < len(lines):
                if _is_blank(i):
                    break
                # Stop if a protected unit is about to start at this line.
                if (
                    _is_code_fence(i)
                    or _is_quote_start(i)
                    or _is_table_start(i)
                ):
                    break
                i += 1
            units.append(_Unit(text="\n".join(lines[start:i]), kind="text"))
            continue

        # Blank line: skip and continue.
        i += 1

    return units


def _table_chunk_texts(
    header_row: str,
    sep_row: str,
    data_rows: List[str],
    max_len: int,
) -> List[str]:
    """Group table data rows into chunks of <= max_len while preserving order.

    Every returned chunk text begins with ``header_row + sep_row`` so that
    the header is always available downstream, and no row is sliced across
    groups.
    """
    prefix = f"{header_row}\n{sep_row}\n"
    prefix_len = len(prefix)
    if not data_rows:
        return [prefix.rstrip("\n")]

    groups: List[List[str]] = []
    current: List[str] = []
    current_len = prefix_len  # newline already included in the prefix above
    for row in data_rows:
        row_len = len(row) + 1  # row + newline
        if current and current_len + row_len > max_len:
            groups.append(current)
            current = [row]
            current_len = prefix_len + row_len
        else:
            current.append(row)
            current_len += row_len
    if current:
        groups.append(current)

    return [prefix + "\n".join(g) for g in groups]


def _make_chunk(
    text: str,
    source: str,
    section: int,
    header_path: str,
    header_level: int,
    chunk_type: str,
    document_date: str,
    document_mtime: Optional[float],
) -> Chunk:
    """Build a Chunk populated with Task 2 metadata via build_chunk_metadata."""
    metadata = build_chunk_metadata(
        text,
        document_date=document_date,
        document_mtime=document_mtime,
    )
    return Chunk(
        id=_make_chunk_id(source, text),
        text=text,
        source=source,
        section=section,
        header_path=header_path,
        header_level=header_level,
        tokens=get_tokens(text),
        date=str(metadata["date"]),
        days_old=metadata["days_old"],
        temporal_weight=float(metadata["temporal_weight"]),
        certainty=str(metadata["certainty"]),
        chunk_type=chunk_type,
        year_mentions=list(extract_year_mentions(text)),
    )


def _enrich_xlsx_chunk(chunk: Chunk) -> None:
    """Mutate ``chunk`` in place with sheet / columns / row metadata.

    The xlsx parser (format_xlsx_sheet in mineru.py) emits a structured
    markdown layout that we can recover cheaply with three regexes; the
    chunker never re-parses the workbook itself. If a chunk crosses sheet
    boundaries we keep the first sheet header (best effort) and union all
    row numbers — splitting the chunk further would require knowing where
    the next sheet begins, which the regex pass cannot do reliably.
    """
    text = chunk.text or ""
    sheet_match = _XLSX_SHEET_RE.search(text)
    if sheet_match is not None:
        chunk.sheet_name = sheet_match.group(1).strip()
    header_match = _XLSX_HEADER_RE.search(text)
    if header_match is not None:
        chunk.columns = [
            col.strip() for col in header_match.group(1).split("|") if col.strip()
        ]
    row_numbers = [int(value) for value in _XLSX_ROW_RE.findall(text)]
    if row_numbers:
        chunk.row_start = min(row_numbers)
        chunk.row_end = max(row_numbers)
    # Even when only the sheet header or a single row line is present we
    # still want the chunk to be queryable as a structured xlsx unit; the
    # brief mandates ``xlsx_row_group`` for every xlsx chunk that survives
    # the regular chunking pipeline.
    chunk.chunk_type = "xlsx_row_group"


def _ensure_unique_id(chunk: Chunk, source: str, seen: set) -> Chunk:
    """Return the chunk with a unique id, regenerating if necessary."""
    if chunk.id in seen:
        chunk.id = _make_chunk_id(source, chunk.text + f"#{len(seen)}")
    seen.add(chunk.id)
    return chunk


def split_into_chunks(
    markdown: str,
    source: str,
    max_len: int = MAX_LEN_DEFAULT,
    overlap: int = OVERLAP_DEFAULT,
    header_aware: bool = True,
    document_date: str = "",
    document_mtime: Optional[float] = None,
    document_type: str = "",
) -> List[Chunk]:
    """Split a markdown document into chunks.

    Args:
      markdown: Full markdown text.
      source:   Document source label (becomes Chunk.source).
      max_len:  Maximum chunk length in characters.
      overlap:  Overlap between consecutive sliding-window chunks.
      header_aware: When True, keep header path in payload; otherwise flatten.
      document_date: Optional ISO date string for temporal weighting.
      document_mtime: Optional file mtime (UTC seconds) used when
        ``document_date`` is empty.
      document_type: Optional lowercased file extension (no leading dot).
        When ``"xlsx"`` the chunker runs a lightweight regex pass over each
        emitted chunk to recover the sheet name, header columns, and row
        range, and re-labels the chunk as ``xlsx_row_group``. Any other
        value is ignored so the legacy code path is unchanged.
    """
    if not markdown:
        return []

    lines = markdown.splitlines()
    seen_ids: set = set()
    chunks: List[Chunk] = []
    section_counter = 0

    if not header_aware:
        # Flat path: still recognize protected units, but no header context.
        units = _parse_units(lines)
        for unit in units:
            if unit.kind == "code":
                section_counter += 1
                ch = _make_chunk(
                    _strip_text(unit.text), source, section_counter, "", 0,
                    "code", document_date, document_mtime,
                )
                chunks.append(_ensure_unique_id(ch, source, seen_ids))
            elif unit.kind == "quote":
                section_counter += 1
                ch = _make_chunk(
                    _strip_text(unit.text), source, section_counter, "", 0,
                    "quote", document_date, document_mtime,
                )
                chunks.append(_ensure_unique_id(ch, source, seen_ids))
            elif unit.kind == "table":
                rows = unit.text.splitlines()
                if len(rows) < 2:
                    section_counter += 1
                    ch = _make_chunk(
                        _strip_text(unit.text), source, section_counter, "",
                        0, "table", document_date, document_mtime,
                    )
                    chunks.append(_ensure_unique_id(ch, source, seen_ids))
                    continue
                header_row, sep_row = rows[0], rows[1]
                data_rows = [r for r in rows[2:] if r.strip()]
                for chunk_text in _table_chunk_texts(
                    header_row, sep_row, data_rows, max_len,
                ):
                    section_counter += 1
                    ch = _make_chunk(
                        _strip_text(chunk_text), source, section_counter, "",
                        0, "table", document_date, document_mtime,
                    )
                    chunks.append(_ensure_unique_id(ch, source, seen_ids))
            else:
                # Text unit: split on blank lines, accumulate via existing logic.
                paragraphs = [
                    p.strip()
                    for p in _PARAGRAPH_RE.split(unit.text)
                    if p.strip()
                ]
                for piece in _accumulate_paragraphs(
                    paragraphs, max_len, overlap
                ):
                    section_counter += 1
                    ch = _make_chunk(
                        _strip_text(piece), source, section_counter, "", 0,
                        "text", document_date, document_mtime,
                    )
                    chunks.append(_ensure_unique_id(ch, source, seen_ids))
        if document_type == "xlsx":
            for ch in chunks:
                _enrich_xlsx_chunk(ch)
        return chunks

    header_stack: List[tuple[int, str]] = []  # (level, title)
    buffer_paragraphs: List[str] = []

    def flush_text_buffer():
        nonlocal section_counter, buffer_paragraphs
        if not buffer_paragraphs:
            return
        section_counter += 1
        header_path = _format_header_path(header_stack)
        header_level = header_stack[-1][0] if header_stack else 0
        for piece in _accumulate_paragraphs(
            buffer_paragraphs, max_len, overlap
        ):
            text = _strip_text(piece)
            ch = _make_chunk(
                text, source, section_counter, header_path, header_level,
                "text", document_date, document_mtime,
            )
            chunks.append(_ensure_unique_id(ch, source, seen_ids))
        buffer_paragraphs = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        m = _HEADER_RE.match(line)

        if m:
            # Header: flush pending text, push onto the stack.
            flush_text_buffer()
            level = len(m.group(1))
            title = m.group(2).strip()
            while header_stack and header_stack[-1][0] >= level:
                header_stack.pop()
            header_stack.append((level, title))
            i += 1
            continue

        # Code fence: protected unit, single chunk regardless of length.
        if stripped.startswith("```"):
            flush_text_buffer()
            start = i
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                i += 1
            end = i + 1 if i < len(lines) and lines[i].lstrip().startswith(
                "```"
            ) else i
            text = "\n".join(lines[start:end])
            section_counter += 1
            header_path = _format_header_path(header_stack)
            header_level = header_stack[-1][0] if header_stack else 0
            ch = _make_chunk(
                _strip_text(text), source, section_counter, header_path,
                header_level, "code", document_date, document_mtime,
            )
            chunks.append(_ensure_unique_id(ch, source, seen_ids))
            i = end
            continue

        # Blockquote: protected unit, single chunk regardless of length.
        if stripped.startswith(">"):
            flush_text_buffer()
            start = i
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            text = "\n".join(lines[start:i])
            section_counter += 1
            header_path = _format_header_path(header_stack)
            header_level = header_stack[-1][0] if header_stack else 0
            ch = _make_chunk(
                _strip_text(text), source, section_counter, header_path,
                header_level, "quote", document_date, document_mtime,
            )
            chunks.append(_ensure_unique_id(ch, source, seen_ids))
            continue

        # Table: protected unit grouped row-by-row.
        if stripped.startswith("|") and i + 1 < len(lines) and _is_table_sep_line(
            lines[i + 1].strip()
        ):
            flush_text_buffer()
            start = i
            i += 2  # skip header + separator
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                i += 1
            rows = lines[start:i]
            header_path = _format_header_path(header_stack)
            header_level = header_stack[-1][0] if header_stack else 0
            if len(rows) < 2:
                section_counter += 1
                ch = _make_chunk(
                    _strip_text("\n".join(rows)), source, section_counter,
                    header_path, header_level, "table", document_date,
                    document_mtime,
                )
                chunks.append(_ensure_unique_id(ch, source, seen_ids))
                continue
            header_row, sep_row = rows[0], rows[1]
            data_rows = [r for r in rows[2:] if r.strip()]
            for chunk_text in _table_chunk_texts(
                header_row, sep_row, data_rows, max_len,
            ):
                section_counter += 1
                ch = _make_chunk(
                    _strip_text(chunk_text), source, section_counter,
                    header_path, header_level, "table", document_date,
                    document_mtime,
                )
                chunks.append(_ensure_unique_id(ch, source, seen_ids))
            continue

        # Plain text line: accumulate into the current section's buffer.
        if stripped:
            buffer_paragraphs.append(stripped)
        i += 1

    flush_text_buffer()
    if document_type == "xlsx":
        for ch in chunks:
            _enrich_xlsx_chunk(ch)
    return chunks
