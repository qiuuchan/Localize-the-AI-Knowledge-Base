from __future__ import annotations

import re
from dataclasses import dataclass

from .tokenizer import get_top_tokens

_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


@dataclass(frozen=True)
class QueryProfile:
    char_count: int
    meaningful_token_count: int
    explicit_years: tuple[int, ...]
    is_short: bool
    is_long: bool


def extract_explicit_years(text: str) -> tuple[int, ...]:
    years = {int(value) for value in _YEAR_RE.findall(text or "")}
    return tuple(sorted(years))


def build_query_profile(query: str) -> QueryProfile:
    value = query or ""
    compact = re.sub(r"\s+", "", value)
    token_count = len(get_top_tokens(value, max_n=20))
    return QueryProfile(
        char_count=len(compact),
        meaningful_token_count=token_count,
        explicit_years=extract_explicit_years(value),
        is_short=len(compact) <= 4 or token_count <= 2,
        is_long=len(compact) > 200,
    )


def compress_for_rerank(query: str, *, max_chars: int = 512) -> str:
    value = query or ""
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value

    years = extract_explicit_years(value)
    marker = f"年份:{','.join(str(year) for year in years)}\n" if years else ""
    body_budget = max_chars - len(marker)
    if body_budget <= 0:
        return marker[:max_chars]
    head_len = body_budget // 2
    tail_len = body_budget - head_len
    return marker + value[:head_len] + value[-tail_len:]
