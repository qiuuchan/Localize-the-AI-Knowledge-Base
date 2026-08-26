"""Debug endpoints for KB-AI retrieval pipeline.

Exposes the internal retrieval stages so developers can inspect why a
particular query returned the chunks it did.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.core.rag.retriever import retrieve_debug

router = APIRouter()


@router.get("/debug/retrieval")
def debug_retrieval(
    question: str = Query(..., min_length=1, max_length=1000),
    top_k: int = Query(default=5, ge=1, le=20),
    disable_hybrid: bool = Query(default=False),
    use_query_rewrite: Optional[bool] = Query(default=None),
    rerank_top_n: Optional[int] = Query(default=None, ge=0, le=100),
) -> Dict[str, Any]:
    """Return the full retrieval pipeline for a query.

    Response fields:
      - original_query: the input question
      - rewritten_query: after entity linking / LLM rewrite
      - used_entities: {alias: canonical} map
      - vector_hits: Qdrant vector recall results
      - keyword_hits: SQLite keyword_index results
      - rrf_hits: after Reciprocal Rank Fusion
      - reranked_hits: after cross-encoder rerank
      - fallback_triggered: whether the low-confidence fallback fired

    Set rerank_top_n=0 to skip the cross-encoder rerank step.
    """
    try:
        result = retrieve_debug(
            question,
            top_k=top_k,
            disable_hybrid=disable_hybrid,
            use_query_rewrite=use_query_rewrite,
            rerank_top_n=rerank_top_n,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retrieval debug failed: {exc}")
    return result
