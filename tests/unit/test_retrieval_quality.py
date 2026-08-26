from backend.core.rag.query_profile import build_query_profile
from backend.core.rag.retriever import (
    _filter_short_keyword_hits,
    _apply_year_priority,
    _effective_rerank_top_n,
    _finish_retrieval,
)
from backend.core.rag import retriever


def test_short_query_requires_phrase_or_two_token_overlap():
    hits = [
        {"text": "表格完成", "source": "a.md", "score": 1},
        {"text": "门店进度表：一店完成", "source": "b.md", "score": 2},
    ]

    filtered, used_fallback = _filter_short_keyword_hits("进度表", hits)

    assert used_fallback is False
    assert [hit["source"] for hit in filtered] == ["b.md"]
    assert filtered[0]["keyword_overlap"] >= 2


def test_short_query_falls_back_when_strict_gate_would_be_empty():
    hits = [{"text": "单字命中", "source": "a.md", "score": 1}]

    filtered, used_fallback = _filter_short_keyword_hits("表", hits)

    assert used_fallback is True
    assert filtered == hits


def test_long_or_normal_query_does_not_use_short_gate():
    hits = [{"text": "进度", "source": "a.md", "score": 1}]

    filtered, used_fallback = _filter_short_keyword_hits("门店进度如何", hits)

    assert used_fallback is False
    assert filtered == hits


def test_explicit_year_moves_matching_chunks_ahead_of_newer_nonmatching_chunk():
    profile = build_query_profile("2025 预算")
    results = [
        {"id": "new", "score": 0.99, "text": "预算 2026", "year_mentions": [2026]},
        {"id": "old", "score": 0.40, "text": "预算 2025", "year_mentions": [2025]},
    ]

    ordered = _apply_year_priority(results, profile, {})

    assert [item["id"] for item in ordered] == ["old", "new"]
    assert ordered[0]["year_match"] is True
    assert ordered[1]["year_match"] is False


def test_year_priority_keeps_results_when_no_candidate_matches():
    profile = build_query_profile("2025 预算")
    diagnostics = {}
    results = [{"id": "new", "text": "预算 2026", "year_mentions": [2026]}]

    ordered = _apply_year_priority(results, profile, diagnostics)

    assert ordered[0]["id"] == "new"
    assert diagnostics["year_match_miss"] is True


def test_multiple_explicit_years_all_count_as_matches():
    profile = build_query_profile("比较 2025 和 2026")
    results = [
        {"id": "2026", "score": 0.2, "year_mentions": [2026]},
        {"id": "2024", "score": 0.9, "year_mentions": [2024]},
        {"id": "2025", "score": 0.1, "year_mentions": [2025]},
    ]

    ordered = _apply_year_priority(results, profile, {})

    assert {ordered[0]["id"], ordered[1]["id"]} == {"2025", "2026"}


def test_no_explicit_year_returns_unchanged():
    profile = build_query_profile("门店进度")
    results = [{"id": "a", "score": 0.5, "year_mentions": [2026]}]

    ordered = _apply_year_priority(results, profile, {})

    assert ordered[0]["id"] == "a"
    assert "year_match" not in ordered[0]


def test_long_profile_caps_default_rerank_candidates_at_five():
    profile = build_query_profile("甲" * 201)

    assert _effective_rerank_top_n(None, profile) == 5
    assert _effective_rerank_top_n(10, profile) == 5
    assert _effective_rerank_top_n(3, profile) == 3


def test_explicit_disable_rerank_wins_for_long_query():
    profile = build_query_profile("甲" * 201)

    assert _effective_rerank_top_n(0, profile) == 0


def test_normal_profile_keeps_configured_rerank_top_n():
    profile = build_query_profile("门店进度")

    assert _effective_rerank_top_n(None, profile) == 10
    assert _effective_rerank_top_n(7, profile) == 7


def test_finish_retrieval_passes_compressed_query_to_reranker(monkeypatch):
    captured = {}

    def fake_rerank(query, candidates, *, top_k, model_name=None):
        captured["query"] = query
        return list(candidates)

    monkeypatch.setattr(retriever, "rerank", fake_rerank)
    results = _finish_retrieval(
        "2026 年" + "背景" * 180 + "最终要求",
        [{"id": "1", "text": "命中", "score": 0.8}],
        top_k=5,
        rerank_top_n=1,
        rerank_model=None,
        retrieval_mode="hybrid",
        rerank_query="年份:2026\n压缩后的查询",
    )

    assert results
    assert captured["query"] == "年份:2026\n压缩后的查询"
