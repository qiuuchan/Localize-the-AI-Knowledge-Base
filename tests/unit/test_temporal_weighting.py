"""Unit tests for temporal weighting and certainty metadata in retrieval."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import math

from backend.core.rag import llm as rag_llm
from backend.core.rag.retriever import _apply_temporal_weight, _temporal_weight


def test_temporal_weight_new_chunk():
    assert _temporal_weight(0) == 1.0
    assert _temporal_weight(1) < 1.0


def test_temporal_weight_decay():
    half_life = 365.0
    w = _temporal_weight(half_life)
    assert abs(w - math.exp(-1)) < 0.01
    w2 = _temporal_weight(2 * half_life)
    assert abs(w2 - math.exp(-2)) < 0.01


def test_temporal_weight_floor():
    # Very old chunks are bounded below at 0.1
    assert _temporal_weight(10000) == 0.1


def test_apply_temporal_weight_reorders():
    candidates = [
        {"id": "old", "score": 1.0, "temporal_weight": 0.2},
        {"id": "new", "score": 0.5, "temporal_weight": 1.0},
    ]
    result = _apply_temporal_weight(candidates)
    assert result[0]["id"] == "new"
    assert result[0]["score"] == 0.5


def test_build_messages_includes_certainty_and_date():
    chunks = [
        {
            "source": "test.md",
            "text": "会员数 1000 人",
            "date": "2024-11-01",
            "certainty": "fact",
        }
    ]
    messages = rag_llm.build_messages(
        question="会员数多少？",
        context_chunks=chunks,
    )
    user_content = messages[-1]["content"]
    assert "certainty: fact" in user_content
    assert "date: 2024-11-01" in user_content
    assert "会员数 1000 人" in user_content
