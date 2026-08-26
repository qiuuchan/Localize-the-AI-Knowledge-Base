from backend.core.rag.query_profile import (
    build_query_profile,
    compress_for_rerank,
    extract_explicit_years,
)


def test_profile_counts_non_whitespace_and_effective_tokens():
    profile = build_query_profile("  2026 年 门店进度  ")

    assert profile.char_count == len("2026年门店进度")
    assert profile.meaningful_token_count >= 2
    assert profile.explicit_years == (2026,)
    assert profile.is_short is False
    assert profile.is_long is False


def test_profile_short_boundary_uses_or_rule():
    assert build_query_profile("进度").is_short is True
    assert build_query_profile("一二三四").is_short is True
    assert build_query_profile("一二三四五").is_short is False


def test_profile_long_boundary_is_over_two_hundred_non_whitespace_chars():
    assert build_query_profile("甲" * 200).is_long is False
    assert build_query_profile("甲" * 201).is_long is True


def test_extract_years_is_unique_sorted_and_rejects_longer_numbers():
    assert extract_explicit_years("预算 2026 和 2025") == (2025, 2026)
    assert extract_explicit_years("编号 12026 不算年份") == ()
    assert extract_explicit_years("没有年份") == ()


def test_compress_for_rerank_preserves_edges_and_explicit_year():
    query = "2026 年" + "前半段" * 120 + "结尾要求"
    compressed = compress_for_rerank(query, max_chars=80)

    assert len(compressed) <= 80
    assert "2026" in compressed
    assert compressed.startswith("年份:")
    assert "结尾要求" in compressed
