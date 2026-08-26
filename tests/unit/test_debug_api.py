"""Unit tests for the /api/debug/retrieval endpoint."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi.testclient import TestClient

from backend.main import app


def test_debug_retrieval_endpoint(monkeypatch):
    """Debug endpoint should expose every retrieval stage."""
    expected = {
        "original_query": "老王怎么说",
        "rewritten_query": "王工怎么说",
        "used_entities": {"老王": "王工"},
        "vector_hits": [{"id": "v1", "text": "vector result"}],
        "keyword_hits": [{"id": "k1", "text": "keyword result"}],
        "rrf_hits": [{"id": "r1", "text": "rrf result"}],
        "reranked_hits": [{"id": "rr1", "text": "reranked result"}],
        "fallback_triggered": False,
    }

    import backend.api.debug as debug_module

    monkeypatch.setattr(debug_module, "retrieve_debug", lambda *args, **kwargs: expected)

    with TestClient(app) as client:
        r = client.get("/api/debug/retrieval", params={"question": "老王怎么说"})

    assert r.status_code == 200
    data = r.json()
    assert data["original_query"] == "老王怎么说"
    assert data["rewritten_query"] == "王工怎么说"
    assert "vector_hits" in data
    assert "keyword_hits" in data
    assert "rrf_hits" in data
    assert "reranked_hits" in data
    assert "fallback_triggered" in data


def test_debug_retrieval_validation():
    with TestClient(app) as client:
        r = client.get("/api/debug/retrieval")
    assert r.status_code == 422
