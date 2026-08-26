"""Unit tests for retrieval diagnostics: query profile + stage timings.

These tests verify that ``retrieve_debug`` (and the supporting helpers used
inside ``retrieve``) now expose the QueryProfile snapshot plus non-negative
millisecond timings for embedding, reranking and the full retrieval flow.

Diagnostics MUST NOT contain the raw user query (privacy / log safety).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from backend.core.rag import retriever


def test_retrieve_debug_reports_profile_and_non_negative_timings(monkeypatch):
    monkeypatch.setattr(retriever, "rewrite_query", lambda query, **kwargs: (query, {}))
    monkeypatch.setattr(
        retriever,
        "embed_query",
        lambda query, api_key=None: [0.0] * 1024,
    )
    monkeypatch.setattr(
        retriever,
        "search",
        lambda vector, *, name, limit, url=None, with_payload=True: [
            {"id": "v1", "score": 0.8, "payload": {"source": "a.md", "text": "2026 进度"}}
        ],
    )
    monkeypatch.setattr(retriever, "search_by_tokens", lambda tokens, *, limit, db_path=None: [])

    result = retriever.retrieve_debug("2026 进度", rerank_top_n=0)
    diagnostics = result["diagnostics"]

    assert diagnostics["query_profile"]["explicit_years"] == [2026]
    assert diagnostics["embed_ms"] >= 0
    assert diagnostics["rerank_ms"] >= 0
    assert diagnostics["retrieve_ms"] >= 0
    assert "query" not in diagnostics
