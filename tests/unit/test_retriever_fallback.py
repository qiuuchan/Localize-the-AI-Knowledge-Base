"""Unit tests for retrieval fallback behavior in backend.core.rag.retriever."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest

from backend.core.rag import retriever


def _make_vector_hit(point_id: str, text: str, score: float) -> Dict[str, Any]:
    return {
        "id": point_id,
        "source": "test.md",
        "text": text,
        "score": score,
        "header_path": "",
        "section": 1,
    }


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Provide deterministic defaults for every test."""
    monkeypatch.setattr(retriever, "embed_query", lambda text, api_key=None: [0.0] * 1024)
    monkeypatch.setattr(retriever, "rewrite_query", lambda query, **kwargs: (query, {}))


@pytest.fixture
def track_search(monkeypatch):
    """Return a list that records every call to qdrant_store.search."""
    calls: List[Dict[str, Any]] = []

    def fake_search(vector, *, name, limit, url=None, with_payload=True):
        calls.append({"name": name, "limit": limit, "url": url})
        if limit >= 50:
            return [{"id": "fallback-1", "score": 0.5, "payload": {"text": "fallback result"}}]
        return []

    monkeypatch.setattr(retriever, "search", fake_search)
    return calls


@pytest.fixture
def track_keyword(monkeypatch):
    calls: List[int] = []

    def fake_search_by_tokens(tokens, *, limit, db_path=None):
        calls.append(limit)
        return []

    monkeypatch.setattr(retriever, "search_by_tokens", fake_search_by_tokens)
    return calls


@pytest.fixture
def low_score_rerank(monkeypatch):
    def fake_rerank(query, candidates, *, top_k, model_name=None):
        return [_make_vector_hit("low-1", "low confidence", -2.0)]

    monkeypatch.setattr(retriever, "rerank", fake_rerank)


@pytest.fixture
def high_score_rerank(monkeypatch):
    def fake_rerank(query, candidates, *, top_k, model_name=None):
        return [_make_vector_hit("high-1", "high confidence", 0.95)]

    monkeypatch.setattr(retriever, "rerank", fake_rerank)


def test_fallback_triggers_on_empty_results(track_search, track_keyword, monkeypatch):
    """When vector+keyword both return empty, retrieval should retry with 50 candidates."""
    calls = []

    def fake_rerank(query, candidates, *, top_k, model_name=None):
        calls.append(("rerank", len(candidates)))
        if len(candidates) == 0:
            return []
        return [_make_vector_hit("fb-1", "fallback", 0.5)]

    monkeypatch.setattr(retriever, "rerank", fake_rerank)

    result = retriever.retrieve("test query", top_k=5, rerank_top_n=5)

    assert len(result) == 1
    assert result[0]["id"] == "fb-1"
    # The second qdrant search should have used the larger fallback limit.
    assert any(c["limit"] == 50 for c in track_search)


def test_no_fallback_when_confident(
    track_search, track_keyword, high_score_rerank
):
    result = retriever.retrieve("test query", top_k=5, rerank_top_n=5)

    assert len(result) == 1
    assert result[0]["id"] == "high-1"
    # Only one qdrant search call should have been made.
    assert len(track_search) == 1
    assert track_search[0]["limit"] == 20


def test_fallback_when_low_score(
    track_search, track_keyword, low_score_rerank
):
    result = retriever.retrieve("test query", top_k=5, rerank_top_n=5)

    # The negative rerank score produces sigmoid confidence below 0.3,
    # so the first result triggers the wider retrieval attempt.
    assert len(result) == 1
    assert result[0]["retrieval_confidence"] < 0.3
    assert len(track_search) == 2
    assert track_search[1]["limit"] == 50


def test_vector_failure_falls_back_to_keyword(monkeypatch):
    monkeypatch.setattr(retriever, "embed_query", lambda *a, **k: [0.0] * 1024)
    monkeypatch.setattr(
        retriever,
        "search",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("qdrant down")),
    )
    monkeypatch.setattr(
        retriever,
        "search_by_tokens",
        lambda *a, **k: [{"point_id": "k1", "source": "a.md", "text": "关键词命中", "score": 2}],
    )
    diagnostics = {}
    result = retriever.retrieve("关键词查询", top_k=5, rerank_top_n=0, diagnostics=diagnostics)
    assert result[0]["id"] == "k1"
    assert result[0]["retrieval_mode"] == "keyword_only"
    assert diagnostics["degradations"] == ["vector_failed"]


def test_keyword_failure_keeps_vector_results(monkeypatch):
    monkeypatch.setattr(retriever, "embed_query", lambda *a, **k: [0.0] * 1024)
    monkeypatch.setattr(
        retriever,
        "search",
        lambda *a, **k: [{"id": "v1", "score": 0.82, "payload": {"text": "向量命中", "source": "a.md"}}],
    )
    monkeypatch.setattr(
        retriever,
        "search_by_tokens",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sqlite down")),
    )
    diagnostics = {}
    result = retriever.retrieve("向量查询", top_k=5, rerank_top_n=0, diagnostics=diagnostics)
    assert result[0]["id"] == "v1"
    assert result[0]["retrieval_mode"] == "vector_only"
    assert diagnostics["degradations"] == ["keyword_failed"]


def test_both_retrieval_legs_fail(monkeypatch):
    monkeypatch.setattr(
        retriever,
        "embed_query",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("embedding down")),
    )
    monkeypatch.setattr(
        retriever,
        "search_by_tokens",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sqlite down")),
    )
    diagnostics = {}
    with pytest.raises(RuntimeError, match="retrieval legs failed"):
        retriever.retrieve("失败查询", top_k=5, rerank_top_n=0, diagnostics=diagnostics)
    assert diagnostics["retrieval_mode"] == "failed"
    assert set(diagnostics["degradations"]) == {"vector_failed", "keyword_failed"}


def test_confidence_is_separate_from_legacy_score(monkeypatch):
    monkeypatch.setattr(retriever, "embed_query", lambda *a, **k: [0.0] * 1024)
    monkeypatch.setattr(
        retriever,
        "search",
        lambda *a, **k: [{"id": "v1", "score": 0.82, "payload": {"text": "命中", "source": "a.md"}}],
    )
    monkeypatch.setattr(retriever, "search_by_tokens", lambda *a, **k: [])
    result = retriever.retrieve("查询", top_k=5, rerank_top_n=0)
    assert result[0]["score"] == 0.82
    assert 0.0 <= result[0]["retrieval_confidence"] <= 1.0
