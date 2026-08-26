"""Unit tests for backend.core.rag.reranker.

These tests mock the underlying cross-encoder model so they do not require
internet access or the ~400 MB model download.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

# Make the backend package importable when running pytest from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import importlib

import pytest

from backend.core.rag import reranker


class _FakeCrossEncoder:
    """Deterministic cross-encoder for unit tests."""

    def predict(self, pairs: List[Any], *, show_progress_bar: bool = False) -> List[float]:
        scores = []
        for _query, text in pairs:
            lower = text.lower()
            score = 0.1
            if "relevant" in lower:
                score += 0.5
            if "most" in lower:
                score += 0.3
            scores.append(score)
        return scores


def _make_fake_loader(returns: Any):
    """Return a fake _load_reranker that returns `returns` and resets state."""
    def _fake_loader(model_name: Any = None) -> Any:
        reranker._reranker = returns  # type: ignore[misc]
        reranker._load_error = None  # type: ignore[misc]
        return returns
    return _fake_loader


@pytest.fixture(autouse=True)
def _reload_module():
    """Reload the reranker module before each test to clear cached state."""
    importlib.reload(reranker)
    yield


def test_rerank_reorders_candidates(monkeypatch):
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(reranker, "_load_reranker", _make_fake_loader(fake))

    candidates = [
        {"id": "1", "text": "some text"},
        {"id": "2", "text": "most relevant text"},
        {"id": "3", "text": "another relevant snippet"},
    ]
    result = reranker.rerank("query", candidates, top_k=2)

    assert len(result) == 2
    # "most relevant text" should score highest.
    assert result[0]["id"] == "2"
    assert result[0]["rerank_score"] > result[1]["rerank_score"]
    # Original dicts should not be mutated.
    assert "rerank_score" not in candidates[0]


def test_rerank_without_top_k_returns_all(monkeypatch):
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(reranker, "_load_reranker", _make_fake_loader(fake))

    candidates = [
        {"id": "1", "text": "some text"},
        {"id": "2", "text": "most relevant text"},
    ]
    result = reranker.rerank("query", candidates)

    assert len(result) == 2
    assert result[0]["id"] == "2"


def test_rerank_falls_back_when_model_load_fails(monkeypatch):
    monkeypatch.setattr(reranker, "_load_reranker", _make_fake_loader(None))

    candidates = [
        {"id": "first", "text": "original first"},
        {"id": "second", "text": "original second"},
    ]
    result = reranker.rerank("query", candidates, top_k=2)

    # Should preserve original order and not raise.
    assert [r["id"] for r in result] == ["first", "second"]
    assert "rerank_score" not in result[0]


def test_rerank_empty_candidates():
    assert reranker.rerank("query", []) == []


def test_is_available_true(monkeypatch):
    fake = _FakeCrossEncoder()
    monkeypatch.setattr(reranker, "_load_reranker", _make_fake_loader(fake))
    assert reranker.is_available() is True


def test_is_available_false(monkeypatch):
    monkeypatch.setattr(reranker, "_load_reranker", _make_fake_loader(None))
    assert reranker.is_available() is False
