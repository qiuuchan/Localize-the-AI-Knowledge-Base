"""Tokenizer mirroring scripts/lib/Tokenizer.ps1.

Rules (PowerShell version, v0.7.2):
  1. Lowercase the input.
  2. Split English / numbers by r'[^a-z0-9]+'.
  3. Split Chinese (CJK) character-by-character across the standard ranges.
  4. Filter stopwords (built-in list of ~80 high-frequency terms).
  5. Filter 1 <= len <= 32.
  6. Return deduplicated list, original order preserved.
"""
from __future__ import annotations

import re
from typing import List, Set

# CJK Unicode ranges from PowerShell version
_CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_EN_MIN_LEN = 1
_EN_MAX_LEN = 32
_CJK_MAX_LEN = 32

# Stopwords copied from scripts/lib/Tokenizer.ps1 (v0.7.2)
STOPWORDS: Set[str] = {
    # Chinese single-char
    "的", "了", "是", "在", "和", "与", "及", "或", "也", "都", "就",
    "不", "没", "把", "被", "给", "对", "从", "到", "为", "以", "于",
    "而", "但", "却", "可", "能", "会", "要", "应", "这", "那", "哪",
    "何", "一", "个", "些", "上", "下", "中", "内", "外", "里", "前",
    "后", "时", "间", "年", "月", "日", "把", "向", "比", "更", "最",
    "很", "太", "非", "没", "未", "再", "又", "已", "将", "才", "只",
    # English / ASCII
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "at", "by", "for", "with", "as", "and",
    "or", "but", "if", "then", "this", "that", "it", "its",
}


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def get_tokens(text: str, min_length: int = 1, max_length: int = 32) -> List[str]:
    """Split text into tokens.

    Returns deduplicated tokens in the order they first appeared.
    Mirrors Get-Tokens -MinLength $min_length -MaxLength $max_length.
    """
    if not text:
        return []

    lower = text.lower()
    out: List[str] = []
    seen: Set[str] = set()

    # 1) English / digits: split on non-alnum
    for piece in _NON_ALNUM.split(lower):
        if not piece:
            continue
        if len(piece) < min_length or len(piece) > max_length:
            continue
        if piece in STOPWORDS:
            continue
        if piece in seen:
            continue
        seen.add(piece)
        out.append(piece)

    # 2) Chinese: character-by-character
    for ch in lower:
        if not _is_cjk(ch):
            continue
        if ch in STOPWORDS:
            continue
        # CJK tokens are single characters; min_length filter only removes them if > max
        if len(ch) > max_length:
            continue
        if ch in seen:
            continue
        seen.add(ch)
        out.append(ch)

    return out


def get_top_tokens(text: str, max_n: int = 20) -> List[str]:
    """Truncate token list to first N entries (mirrors Get-TopTokens -MaxN)."""
    return get_tokens(text)[:max_n]
