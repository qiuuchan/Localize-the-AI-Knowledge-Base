"""Pure Python helpers for document and chunk metadata."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date, datetime, timezone

FRONTMATTER_KEYS = {"date", "created", "updated", "certainty"}
CERTAINTY_VALUES = {"fact", "opinion", "draft", "neutral"}

_DRAFT_PATTERN = re.compile(
    r"TODO|FIXME|待确认|待补充|待完善|待核实|待讨论|草案|初稿|草稿|占位|预留|暂缺|暂无|未确定",
    re.IGNORECASE,
)
_FACT_PATTERN = re.compile(
    r"\d|元|万元|亿元|%|百分之|营收|收入|利润|成本|客单价|同比|环比|增长|下降|新增会员|转化率"
)
_OPINION_PATTERN = re.compile(
    r"我认为|我觉得|建议|推荐|可能|也许|大概|或许|应该|应当|最好|优先|需要|必须|更适合|更有效"
)
_DIGIT_PATTERN = re.compile(r"\d")
# 4-digit 20xx year, bounded so that "编号 12026" / "phone 20261234567" don't
# match. Must stay byte-identical to query_profile._YEAR_RE so the chunk-side
# extraction agrees with the query-side year filtering.
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def extract_year_mentions(text: str) -> tuple[int, ...]:
    """Return unique, sorted 20xx years mentioned in ``text``.

    Empty / ``None`` input returns an empty tuple. The regex boundary matches
    query_profile.extract_explicit_years so the chunk-side and query-side
    year extraction agree.
    """
    if not text:
        return ()
    return tuple(sorted({int(value) for value in _YEAR_RE.findall(text)}))


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10])
    except (AttributeError, TypeError, ValueError):
        return None


def extract_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    """Extract supported scalar frontmatter fields and return the document body."""
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, markdown

    closing = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if closing is None:
        return {}, markdown

    values: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        normalized_key = key.strip()
        if separator and normalized_key in FRONTMATTER_KEYS:
            values[normalized_key] = value.strip().strip("'\"")

    body = "\n".join(lines[closing + 1 :])
    return values, body


def resolve_document_date(
    frontmatter: Mapping[str, str],
    file_mtime: float | None = None,
    today: date | None = None,
) -> str:
    """Resolve a document date from frontmatter, then UTC file modification time."""
    for key in ("updated", "date", "created"):
        parsed = _parse_date(frontmatter.get(key, ""))
        if parsed is not None:
            return parsed.isoformat()

    if file_mtime is not None:
        return datetime.fromtimestamp(file_mtime, tz=timezone.utc).date().isoformat()
    return ""


def calculate_days_old(date_text: str, today: date | None = None) -> int | None:
    """Return non-negative whole days between a date and the reference date."""
    parsed = _parse_date(date_text)
    if parsed is None:
        return None

    reference = today or date.today()
    return max(0, (reference - parsed).days)


def calculate_temporal_weight(
    days_old: int | None, half_life_days: float = 365.0
) -> float:
    """Calculate bounded exponential recency weight for a chunk."""
    if days_old is None or days_old <= 0 or half_life_days <= 0:
        return 1.0
    return max(0.1, round(math.exp(-days_old / half_life_days), 6))


def classify_certainty(text: str) -> str:
    """Classify text using the existing fact/opinion/draft/neutral rules."""
    value = (text or "").strip()
    if len(value) < 30 or _DRAFT_PATTERN.search(value):
        return "draft"

    has_fact = bool(_FACT_PATTERN.search(value))
    has_opinion = bool(_OPINION_PATTERN.search(value))
    if has_fact and not has_opinion:
        return "fact"
    if has_opinion and not has_fact:
        return "opinion"
    if has_fact and len(_DIGIT_PATTERN.findall(value)) >= 2:
        return "fact"
    if has_opinion:
        return "opinion"
    return "neutral"


def build_chunk_metadata(
    text: str,
    *,
    document_date: str = "",
    document_mtime: float | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Build date, temporal weighting, and certainty metadata for one chunk."""
    resolved_date = document_date
    if not resolved_date and document_mtime is not None:
        resolved_date = datetime.fromtimestamp(
            document_mtime, tz=timezone.utc
        ).date().isoformat()

    days_old = calculate_days_old(resolved_date, today=today)
    return {
        "date": resolved_date,
        "days_old": days_old,
        "temporal_weight": calculate_temporal_weight(days_old),
        "certainty": classify_certainty(text),
    }
