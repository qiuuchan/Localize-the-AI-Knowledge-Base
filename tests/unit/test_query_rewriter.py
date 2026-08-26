"""Unit tests for backend.core.rag.query_rewriter.

These tests do not call external APIs; the LLM path is mocked.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


from backend.core.rag import query_rewriter


def test_load_entities_flat():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"老王": "王工", "K2.7": "项目 K2.7"}, f)
        path = f.name
    try:
        entities = query_rewriter.load_entities(Path(path))
        assert entities["老王"] == "王工"
        assert entities["K2.7"] == "项目 K2.7"
    finally:
        Path(path).unlink()


def test_load_entities_nested():
    data = {
        "aliases": {"老王": "王工"},
        "people": {"李总": "李总-负责人"},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        path = f.name
    try:
        entities = query_rewriter.load_entities(Path(path))
        assert entities["老王"] == "王工"
        assert entities["李总"] == "李总-负责人"
    finally:
        Path(path).unlink()


def test_load_entities_missing_file():
    assert query_rewriter.load_entities(Path("/nonexistent/entities.json")) == {}


def test_link_entities():
    entities = {"老王": "王工", "K2.7": "项目 K2.7"}
    query = "老王的K2.7方案怎么样"
    linked, used = query_rewriter._link_entities(query, entities)
    assert "王工" in linked
    assert "项目 K2.7" in linked
    assert used == {"老王": "王工", "K2.7": "项目 K2.7"}


def test_link_entities_word_boundary():
    entities = {"redis": "Redis"}
    query = "myredis is down"
    linked, used = query_rewriter._link_entities(query, entities)
    # 'myredis' should not be replaced because it lacks a word boundary.
    assert "myredis" in linked
    assert used == {}


def test_rewrite_query_no_llm():
    entities = {"老王": "王工"}
    query = "老王怎么说"
    rewritten, used = query_rewriter.rewrite_query(query, entities=entities, use_llm=False)
    assert "王工" in rewritten
    assert "老王" not in rewritten
    assert used == {"老王": "王工"}


def test_rewrite_query_with_llm(monkeypatch):
    def fake_llm(linked_query, entities, *, api_key=None, model=None):
        return f"具体化：{linked_query}"

    monkeypatch.setattr(query_rewriter, "_call_rewrite_llm", fake_llm)

    entities = {"老王": "王工"}
    query = "老王上次说的方案"
    rewritten, used = query_rewriter.rewrite_query(query, entities=entities, use_llm=True)
    assert rewritten.startswith("具体化：")
    assert "王工" in rewritten
    assert used == {"老王": "王工"}


def test_rewrite_query_llm_fallback(monkeypatch):
    def failing_llm(*args, **kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(query_rewriter, "_call_rewrite_llm", failing_llm)

    entities = {"老王": "王工"}
    query = "老王上次说的方案"
    rewritten, used = query_rewriter.rewrite_query(query, entities=entities, use_llm=True)
    # Should fall back to entity-linked query.
    assert "王工" in rewritten
    assert used == {"老王": "王工"}


def test_rewrite_query_empty():
    rewritten, used = query_rewriter.rewrite_query("", entities={"a": "b"})
    assert rewritten == ""
    assert used == {}
