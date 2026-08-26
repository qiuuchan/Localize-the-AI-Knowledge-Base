"""Cross-Encoder reranker for Hybrid Search results.

Mirrors the "粗排 + 精排" suggestion from the RAG pain-point analysis:
- Rough ranking is already done by vector/keyword recall + RRF.
- This module provides a light re-ranking step using a local cross-encoder.

Default model: BAAI/bge-reranker-base (CPU-friendly, ~400 MB download).
If the model cannot be loaded, reranking is skipped and the original order
is returned so the pipeline never breaks because of a missing/invalid model.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from backend.core.config import get_env_or_env_var

# v0.8.7 性能优化(A):默认离线模式加载模型 — 模型已缓存时避免每次进程启动
# 向 huggingface.co 发 HEAD 校验(国内直连会 10s×5 重试,挂起 ~70s)。
# 未缓存时加载快速失败 → 优雅降级跳过重排,而非请求挂起。
# 显式设 HF_HUB_OFFLINE=0 或 HF_ENDPOINT 可恢复在线行为(如首次下载模型)。
os.environ.setdefault("HF_HUB_OFFLINE", "1")

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"

_reranker: Any = None
_load_error: Optional[str] = None


def _load_reranker(model_name: Optional[str] = None) -> Any:
    """Lazy-load the cross-encoder model."""
    global _reranker, _load_error
    if _reranker is not None:
        return _reranker
    if _load_error is not None:
        # Already failed once; do not retry within the same process.
        return None

    model_name = model_name or get_env_or_env_var("RERANK_MODEL") or DEFAULT_RERANK_MODEL
    try:
        from sentence_transformers import CrossEncoder
    except Exception as exc:  # pragma: no cover - dependency missing
        _load_error = f"sentence-transformers not installed: {exc}"
        logger.warning(_load_error)
        return None

    try:
        logger.info("Loading reranker model: %s", model_name)
        _reranker = CrossEncoder(model_name)
        logger.info("Reranker model loaded")
        return _reranker
    except Exception as exc:
        _load_error = f"Failed to load reranker {model_name}: {exc}"
        logger.warning(_load_error)
        return None


def rerank(
    query: str,
    candidates: Sequence[Dict[str, Any]],
    *,
    top_k: Optional[int] = None,
    model_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Re-rank candidates by cross-encoder scores.

    Args:
        query: The user query.
        candidates: Already-normalized chunk dicts from retrieval. Each must
            contain a "text" field.
        top_k: If given, return only the top_k reranked items. If None,
            return all candidates in reranked order.
        model_name: Optional override for the cross-encoder model.

    Returns:
        A new list of candidates sorted by reranker score (descending).
        If the model cannot be loaded, the original order is returned.
    """
    if not candidates:
        return []

    model = _load_reranker(model_name)
    if model is None:
        # Graceful degradation: keep original order.
        result = list(candidates)
        if top_k is not None:
            result = result[:top_k]
        return result

    # v0.8.7 性能优化(E):截断到 500 字 — bge-reranker-base 上限 512 token,
    # 超长部分模型本来也看不到;截断减少 CPU 推理的 padding 浪费(~25%)
    texts = [(c.get("text") or "")[:500] for c in candidates]
    pairs = [(query, text) for text in texts]
    try:
        scores = model.predict(pairs, show_progress_bar=False)
    except Exception as exc:
        logger.warning("Reranker scoring failed: %s", exc)
        result = list(candidates)
        if top_k is not None:
            result = result[:top_k]
        return result

    # Attach rerank score and sort descending.
    scored = []
    for item, score in zip(candidates, scores):
        item = dict(item)
        item["rerank_score"] = float(score)
        item["score"] = float(score)
        scored.append(item)
    scored.sort(key=lambda x: x["rerank_score"], reverse=True)

    if top_k is not None:
        scored = scored[:top_k]
    return scored


def is_available() -> bool:
    """Return True if a reranker model can be loaded."""
    return _load_reranker() is not None
