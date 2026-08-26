"""Hybrid Search: vector + keyword recall with RRF fusion + rerank + fallback.

Mirrors scripts/chat.ps1:438-573 and adds:
  - Optional query rewriting + entity linking (query_rewriter)
  - Cross-encoder reranking (reranker)
  - Automatic fallback when the first retrieval is empty or low-confidence

Pipeline:
  1. Optionally rewrite the query (entity linking + LLM expansion).
  2. Embed the rewritten query via embedder.embed_query.
  3. Vector recall from Qdrant (top HybridVectorCandidates).
  4. Keyword recall from SQLite keyword_index (top HybridKeywordCandidates).
  5. RRF fusion with constant K = HybridRRFK (default 60).
  6. Optional cross-encoder rerank over the top RERANK_TOP_N candidates.
  7. Fallback: if results are empty or all rerank scores are below the
     fallback threshold, retry with larger candidate pools.

Each result is normalized to {id, source, text, score, header_path, section}
so downstream prompt building can format it uniformly.
"""
from __future__ import annotations

import logging
import math
import re
from time import perf_counter
from typing import Any, Dict, List, Optional, Sequence

from backend.core.config import get_env_or_env_var

from .embedder import embed_query
from .keyword_index import search_by_tokens
from .qdrant_store import search
from .query_profile import build_query_profile, compress_for_rerank
from .query_rewriter import rewrite_query
from .reranker import rerank
from .tokenizer import get_top_tokens

DEFAULT_COLLECTION = "kb_ai_chunks"
DEFAULT_RERANK_TOP_N = 10  # v0.8.7 性能优化(B):20→10,实测 rerank 7.8s→4.3s,top-10 RRF 候选质量足够
DEFAULT_LONG_QUERY_RERANK_TOP_N = 5
DEFAULT_FALLBACK_THRESHOLD = 0.3
DEFAULT_TEMPORAL_HALF_LIFE_DAYS = 365.0
FALLBACK_VECTOR_CANDIDATES = 50
FALLBACK_KEYWORD_CANDIDATES = 50

logger = logging.getLogger(__name__)


def _safe_error(exc: BaseException) -> str:
    """Return a short diagnostic without secrets, paths, or upstream bodies."""
    text = " ".join(str(exc).split()) or exc.__class__.__name__
    text = re.sub(
        r"(?i)authorization\s*[:=]\s*(?:\S+\s+)?\S+",
        "[credential redacted]",
        text,
    )
    text = re.sub(
        r"(?i)(api[_ -]?key|access[_ -]?token|token|secret|password)\s*[:=]\s*\S+",
        "[credential redacted]",
        text,
    )
    text = re.sub(r"(?i)\b(?:bearer|basic)\s+\S+", "[credential redacted]", text)
    text = re.sub(r"(?i)\b(?:sk|tvly)-[a-z0-9_-]+", "[redacted]", text)
    text = re.sub(r"https?://[^\s,;]+", "[upstream]", text)
    text = re.sub(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s,;]+", "[path]", text)
    text = re.sub(r"(?<!\w)/(?:[^\s,;]+/)+[^\s,;]*", "[path]", text)
    text = re.sub(r"(?i)(http\s+\d{3}\s*:|response|body)\s*[:=]?\s*.*$", r"\1 [upstream response redacted]", text)
    return text[:200]


def _clamp01(value: Any) -> Optional[float]:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _sigmoid(value: Any) -> Optional[float]:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score >= 0:
        z = math.exp(-score)
        return 1.0 / (1.0 + z)
    z = math.exp(score)
    return z / (1.0 + z)


def _elapsed_ms(started: float) -> float:
    """Return non-negative milliseconds since ``started`` rounded to two decimals."""
    elapsed = (perf_counter() - started) * 1000.0
    if elapsed < 0:
        elapsed = 0.0
    return round(elapsed, 2)


def _profile_dict(profile) -> Dict[str, object]:
    """Project a ``QueryProfile`` to a diagnostics-safe dict (no raw query text)."""
    return {
        "char_count": profile.char_count,
        "meaningful_token_count": profile.meaningful_token_count,
        "explicit_years": list(profile.explicit_years),
        "is_short": profile.is_short,
        "is_long": profile.is_long,
    }


def _safe_vector_leg(
    query: str,
    *,
    collection: str,
    qdrant_url: Optional[str],
    limit: int,
    api_key: Optional[str],
    diagnostics: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Run embedding and Qdrant search as one isolated retrieval leg."""
    embed_started = perf_counter()
    try:
        vector = embed_query(query, api_key=api_key)
        hits = search(vector, name=collection, limit=limit, url=qdrant_url)
        normalized = _normalize_vector_hits(hits)
    except Exception as exc:
        if diagnostics is not None:
            diagnostics["embed_ms"] = _elapsed_ms(embed_started)
        return [], _safe_error(exc)
    if diagnostics is not None:
        diagnostics["embed_ms"] = _elapsed_ms(embed_started)
    return normalized, None


def _safe_keyword_leg(
    query: str,
    *,
    limit: int,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Run tokenization and SQLite keyword search as one isolated leg."""
    try:
        tokens = get_top_tokens(query, max_n=20)
        hits = search_by_tokens(tokens, limit=limit)
        normalized = _normalize_keyword_hits(hits)
        filtered, _used_fallback = _filter_short_keyword_hits(query, normalized)
        return filtered, None
    except Exception as exc:
        return [], _safe_error(exc)


def _mode_for_legs(
    vector_hits: Sequence[Dict[str, Any]],
    keyword_hits: Sequence[Dict[str, Any]],
    *,
    failed: bool = False,
) -> str:
    if vector_hits and keyword_hits:
        return "hybrid"
    if vector_hits:
        return "vector_only"
    if keyword_hits:
        return "keyword_only"
    return "failed" if failed else "hybrid"


def _set_diagnostics(
    diagnostics: Optional[Dict[str, Any]],
    *,
    vector_error: Optional[str],
    keyword_error: Optional[str],
    retrieval_mode: str,
) -> None:
    if diagnostics is None:
        return
    degradations = []
    if vector_error:
        degradations.append("vector_failed")
    if keyword_error:
        degradations.append("keyword_failed")
    diagnostics.update(
        {
            "retrieval_mode": retrieval_mode,
            "degradations": degradations,
            "vector_error": vector_error,
            "keyword_error": keyword_error,
        }
    )


def _annotate_results(
    results: Sequence[Dict[str, Any]],
    *,
    query: str,
    retrieval_mode: str,
    rerank_enabled: bool,
    source_scores: Optional[Dict[str, Any]] = None,
    rerank_candidate_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Attach stable retrieval metadata while preserving the legacy score."""
    source_scores = source_scores or {}
    rerank_candidate_ids = rerank_candidate_ids or set()
    query_token_count = len(get_top_tokens(query, max_n=20))
    annotated: List[Dict[str, Any]] = []
    for result in results:
        item = dict(result)
        item.setdefault("rrf_score", None)
        item.setdefault("rerank_score", None)
        if rerank_enabled and item.get("rerank_score") is None:
            # The real reranker adds rerank_score. A replacement result from a
            # test/custom reranker has no candidate id, so its score is the
            # only available reranker score.
            if str(item.get("id")) not in rerank_candidate_ids:
                item["rerank_score"] = item.get("score")
        if retrieval_mode == "hybrid" and rerank_enabled:
            item["retrieval_confidence"] = _sigmoid(item.get("rerank_score"))
        elif retrieval_mode == "vector_only":
            score = source_scores.get(str(item.get("id")), item.get("score"))
            item["retrieval_confidence"] = _clamp01(score)
        elif retrieval_mode == "keyword_only":
            score = source_scores.get(str(item.get("id")), item.get("score"))
            try:
                matched_count = max(0.0, float(score))
            except (TypeError, ValueError):
                matched_count = None
            if matched_count is None:
                item["retrieval_confidence"] = None
            else:
                item["retrieval_confidence"] = min(
                    1.0, matched_count / max(query_token_count, 1)
                )
        else:
            item["retrieval_confidence"] = None
        item["retrieval_mode"] = retrieval_mode
        annotated.append(item)
    return annotated


def _effective_rerank_top_n(rerank_top_n: Optional[int], profile=None) -> int:
    """Allow env override RERANK_TOP_N; <= 0 disables reranking.

    When profile.is_long, cap at DEFAULT_LONG_QUERY_RERANK_TOP_N to reduce
    reranker latency for very long queries.
    """
    if rerank_top_n is None:
        env_val = get_env_or_env_var("RERANK_TOP_N")
        if env_val:
            try:
                configured = int(env_val)
            except ValueError:
                configured = DEFAULT_RERANK_TOP_N
        else:
            configured = DEFAULT_RERANK_TOP_N
    else:
        configured = rerank_top_n
    if configured <= 0:
        return configured
    if profile is not None and profile.is_long:
        return min(configured, DEFAULT_LONG_QUERY_RERANK_TOP_N)
    return configured


def _fallback_threshold() -> float:
    """Return RETRIEVAL_FALLBACK_THRESHOLD env value or default 0.3."""
    env_val = get_env_or_env_var("RETRIEVAL_FALLBACK_THRESHOLD")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return DEFAULT_FALLBACK_THRESHOLD


def _temporal_half_life_days() -> float:
    """Return TEMPORAL_HALF_LIFE_DAYS env value or default 365."""
    env_val = get_env_or_env_var("TEMPORAL_HALF_LIFE_DAYS")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return DEFAULT_TEMPORAL_HALF_LIFE_DAYS


def _temporal_weight(days_old: Optional[int]) -> float:
    """Exponential decay weight bounded below at 0.1."""
    if days_old is None or days_old <= 0:
        return 1.0
    half_life = _temporal_half_life_days()
    if half_life <= 0:
        return 1.0
    weight = math.exp(-days_old / half_life)
    return max(0.1, round(weight, 6))


def _normalize_vector_hits(hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for h in hits:
        payload = h.get("payload") or {}
        out.append(
            {
                "id": str(h.get("id")),
                "source": payload.get("source") or "",
                "text": payload.get("text") or "",
                "score": h.get("score"),
                "header_path": payload.get("header_path") or "",
                "section": payload.get("section"),
                "days_old": payload.get("days_old"),
                "temporal_weight": payload.get("temporal_weight") or 1.0,
                "certainty": payload.get("certainty") or "neutral",
                "date": payload.get("date") or "",
                "year_mentions": payload.get("year_mentions") or [],
                "rrf_score": None,
                "rerank_score": None,
                "retrieval_confidence": None,
                "retrieval_mode": "vector_only",
            }
        )
    return out


def _normalize_keyword_hits(hits: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for h in hits:
        out.append(
            {
                "id": h.get("point_id"),
                "source": h.get("source") or "",
                "text": h.get("text") or "",
                "score": h.get("score"),
                "header_path": "",
                "section": None,
                "days_old": None,
                "temporal_weight": 1.0,
                "certainty": "neutral",
                "date": "",
                "year_mentions": [],
                "rrf_score": None,
                "rerank_score": None,
                "retrieval_confidence": None,
                "retrieval_mode": "keyword_only",
            }
        )
    return out


def _rrf_merge(
    legs: Sequence[Sequence[Dict[str, Any]]],
    *,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Reciprocal Rank Fusion across multiple ranked legs.

    Mirrors scripts/chat.ps1:510-573 Merge-WithRRF.
    Applies temporal weighting so newer chunks can enter the rerank candidate pool.
    """
    scores: Dict[str, float] = {}
    by_id: Dict[str, Dict[str, Any]] = {}
    for leg in legs:
        for rank, item in enumerate(leg, start=1):
            pid = str(item.get("id"))
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
            # Keep first-seen data; later legs only add score.
            if pid not in by_id:
                by_id[pid] = dict(item)
    merged = []
    for pid, item in by_id.items():
        merged.append({**item, "score": scores[pid], "rrf_score": scores[pid], "retrieval_mode": "hybrid"})
    merged.sort(key=lambda x: x.get("score") or 0.0, reverse=True)
    return merged


def _apply_temporal_weight(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Multiply each result score by its temporal_weight for final ranking."""
    out: List[Dict[str, Any]] = []
    for item in results:
        weighted = dict(item)
        tw = float(weighted.get("temporal_weight") or 1.0)
        weighted["score"] = (weighted.get("score") or 0.0) * tw
        out.append(weighted)
    # Re-sort because temporal weight may have changed ordering.
    out.sort(key=lambda x: x.get("score") or 0.0, reverse=True)
    return out


def _filter_short_keyword_hits(
    query: str, hits: Sequence[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], bool]:
    """Gate noisy keyword hits for ultra-short queries.

    Returns (filtered_hits, used_fallback). For non-short queries, returns
    hits unchanged with used_fallback=False.
    """
    profile = build_query_profile(query)
    if not profile.is_short:
        return [dict(hit) for hit in hits], False

    query_tokens = set(get_top_tokens(query, max_n=20))
    strict = []
    for raw in hits:
        hit = dict(raw)
        text = str(hit.get("text") or "")
        hit_tokens = set(get_top_tokens(text, max_n=20))
        overlap = len(query_tokens & hit_tokens)
        phrase_match = query.strip() in text
        hit["keyword_overlap"] = overlap
        required = 2 if len(query_tokens) >= 2 else 1
        if phrase_match or overlap >= required:
            strict.append(hit)

    if strict:
        return strict, False
    return [dict(hit) for hit in hits], bool(hits)


def _apply_year_priority(
    results: Sequence[Dict[str, Any]],
    profile,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Stable year-match-first ordering when query has explicit years.

    If no candidate matches the wanted years, results are returned unchanged
    (with year_match_miss recorded in diagnostics).
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    if not profile.explicit_years:
        return [dict(item) for item in results]

    wanted = set(profile.explicit_years)
    marked = []
    for item in results:
        current = dict(item)
        mentions = {int(v) for v in current.get("year_mentions") or []}
        current["year_match"] = bool(wanted & mentions)
        marked.append(current)

    if not any(item["year_match"] for item in marked):
        diagnostics["year_match_miss"] = True
        return marked
    return [item for item in marked if item["year_match"]] + [
        item for item in marked if not item["year_match"]
    ]


def _finish_retrieval(
    query: str,
    candidates: List[Dict[str, Any]],
    *,
    top_k: int,
    rerank_top_n: int,
    rerank_model: Optional[str],
    retrieval_mode: str,
    source_scores: Optional[Dict[str, Any]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
    rerank_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Apply optional reranking, annotate results, then apply temporal weight."""
    rerank_enabled = rerank_top_n > 0
    if rerank_enabled:
        rerank_candidates = candidates[:rerank_top_n]
        candidate_ids = {str(item.get("id")) for item in rerank_candidates}
        rerank_started = perf_counter()
        try:
            final = rerank(
                rerank_query or query,
                rerank_candidates,
                top_k=top_k,
                model_name=rerank_model,
            ) or []
        finally:
            if diagnostics is not None:
                diagnostics["rerank_ms"] = _elapsed_ms(rerank_started)
    else:
        candidate_ids = set()
        final = candidates[:top_k]
        if diagnostics is not None:
            diagnostics["rerank_ms"] = 0.0
    annotated = _annotate_results(
        final,
        query=query,
        retrieval_mode=retrieval_mode,
        rerank_enabled=rerank_enabled,
        source_scores=source_scores,
        rerank_candidate_ids=candidate_ids,
    )
    return _apply_temporal_weight(annotated)


def _retrieve_once(
    query: str,
    *,
    top_k: int,
    collection: str,
    qdrant_url: Optional[str],
    hybrid_vector_candidates: int,
    hybrid_keyword_candidates: int,
    hybrid_rrf_k: int,
    disable_hybrid: bool,
    api_key: Optional[str],
    rerank_top_n: int,
    rerank_model: Optional[str],
    diagnostics: Optional[Dict[str, Any]] = None,
    rerank_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run one retrieval attempt with independently isolated recall legs."""
    rerank_enabled = rerank_top_n > 0

    if disable_hybrid:
        limit = rerank_top_n if rerank_enabled else top_k
        vector_hits, vector_error = _safe_vector_leg(
            query,
            collection=collection,
            qdrant_url=qdrant_url,
            limit=limit,
            api_key=api_key,
            diagnostics=diagnostics,
        )
        if vector_error:
            _set_diagnostics(
                diagnostics,
                vector_error=vector_error,
                keyword_error=None,
                retrieval_mode="failed",
            )
            raise RuntimeError("vector retrieval failed") from None
        source_scores = {
            str(item.get("id")): item.get("score") for item in vector_hits
        }
        _set_diagnostics(
            diagnostics,
            vector_error=None,
            keyword_error=None,
            retrieval_mode="vector_only",
        )
        return _finish_retrieval(
            query,
            vector_hits,
            top_k=top_k,
            rerank_top_n=rerank_top_n,
            rerank_model=rerank_model,
            retrieval_mode="vector_only",
            source_scores=source_scores,
            diagnostics=diagnostics,
            rerank_query=rerank_query,
        )

    vector_hits, vector_error = _safe_vector_leg(
        query,
        collection=collection,
        qdrant_url=qdrant_url,
        limit=hybrid_vector_candidates,
        api_key=api_key,
        diagnostics=diagnostics,
    )
    keyword_hits, keyword_error = _safe_keyword_leg(
        query,
        limit=hybrid_keyword_candidates,
    )
    if not vector_hits and not keyword_hits and (vector_error or keyword_error):
        _set_diagnostics(
            diagnostics,
            vector_error=vector_error,
            keyword_error=keyword_error,
            retrieval_mode="failed",
        )
        raise RuntimeError("retrieval legs failed") from None

    retrieval_mode = _mode_for_legs(vector_hits, keyword_hits)
    _set_diagnostics(
        diagnostics,
        vector_error=vector_error,
        keyword_error=keyword_error,
        retrieval_mode=retrieval_mode,
    )
    source_hits = vector_hits if retrieval_mode == "vector_only" else keyword_hits
    source_scores = {
        str(item.get("id")): item.get("score") for item in source_hits
    }
    if retrieval_mode == "hybrid":
        merged = _rrf_merge([vector_hits, keyword_hits], k=hybrid_rrf_k)
    else:
        merged = list(source_hits)
    return _finish_retrieval(
        query,
        merged,
        top_k=top_k,
        rerank_top_n=rerank_top_n,
        rerank_model=rerank_model,
        retrieval_mode=retrieval_mode,
        source_scores=source_scores,
        diagnostics=diagnostics,
        rerank_query=rerank_query,
    )


def _should_fallback(results: List[Dict[str, Any]], *, rerank_enabled: bool) -> bool:
    """Return True only for empty or uniformly low-confidence results."""
    if not results:
        return True
    if not rerank_enabled:
        # RRF scores are not calibrated to a universal threshold.
        return False
    confidences = [result.get("retrieval_confidence") for result in results]
    # Unknown confidence must not be mistaken for a low RRF score.
    if any(confidence is None for confidence in confidences):
        return False
    threshold = _fallback_threshold()
    return all(float(confidence) < threshold for confidence in confidences)


def retrieve(
    query: str,
    *,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    qdrant_url: Optional[str] = None,
    hybrid_vector_candidates: int = 20,
    hybrid_keyword_candidates: int = 20,
    hybrid_rrf_k: int = 60,
    disable_hybrid: bool = False,
    api_key: Optional[str] = None,
    rerank_top_n: Optional[int] = None,
    rerank_model: Optional[str] = None,
    use_query_rewrite: Optional[bool] = None,
    entities_path: Optional[str] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return top-K chunks ranked by Hybrid Search + optional rerank + fallback."""
    profile = build_query_profile(query)
    if diagnostics is not None:
        diagnostics.update(
            {
                "retrieval_mode": "vector_only" if disable_hybrid else "hybrid",
                "degradations": [],
                "vector_error": None,
                "keyword_error": None,
                "query_profile": _profile_dict(profile),
            }
        )
    retrieve_started = perf_counter()
    try:
        if not query:
            return []

        effective_rerank_top_n = _effective_rerank_top_n(rerank_top_n, profile)
        rerank_enabled = effective_rerank_top_n > 0

        rewritten_query, _used_entities = rewrite_query(
            query,
            use_llm=use_query_rewrite,
            api_key=api_key,
        )
        rerank_query = compress_for_rerank(rewritten_query) if profile.is_long else None

        attempt_diagnostics: Dict[str, Any] = {}
        try:
            results = _retrieve_once(
                rewritten_query,
                top_k=top_k,
                collection=collection,
                qdrant_url=qdrant_url,
                hybrid_vector_candidates=hybrid_vector_candidates,
                hybrid_keyword_candidates=hybrid_keyword_candidates,
                hybrid_rrf_k=hybrid_rrf_k,
                disable_hybrid=disable_hybrid,
                api_key=api_key,
                rerank_top_n=effective_rerank_top_n,
                rerank_model=rerank_model,
                diagnostics=attempt_diagnostics,
                rerank_query=rerank_query,
            )
        except Exception:
            if diagnostics is not None:
                diagnostics.update(attempt_diagnostics)
            raise
        if diagnostics is not None:
            diagnostics.update(attempt_diagnostics)

        if _should_fallback(results, rerank_enabled=rerank_enabled):
            logger.warning(
                "Retrieval fallback triggered: results=%d profile=%s",
                len(results),
                _profile_dict(profile),
            )
            wider_diagnostics: Dict[str, Any] = {}
            try:
                wider = _retrieve_once(
                    rewritten_query,
                    top_k=top_k,
                    collection=collection,
                    qdrant_url=qdrant_url,
                    hybrid_vector_candidates=FALLBACK_VECTOR_CANDIDATES,
                    hybrid_keyword_candidates=FALLBACK_KEYWORD_CANDIDATES,
                    hybrid_rrf_k=hybrid_rrf_k,
                    disable_hybrid=disable_hybrid,
                    api_key=api_key,
                    rerank_top_n=effective_rerank_top_n,
                    rerank_model=rerank_model,
                    diagnostics=wider_diagnostics,
                    rerank_query=rerank_query,
                )
            except Exception:
                if diagnostics is not None:
                    diagnostics.update(wider_diagnostics)
                raise
            if wider:
                results = wider
                if diagnostics is not None:
                    diagnostics.update(wider_diagnostics)

        results = _apply_year_priority(results, profile, diagnostics)
        return results
    finally:
        if diagnostics is not None:
            diagnostics["retrieve_ms"] = _elapsed_ms(retrieve_started)


def retrieve_debug(
    query: str,
    *,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    qdrant_url: Optional[str] = None,
    hybrid_vector_candidates: int = 20,
    hybrid_keyword_candidates: int = 20,
    hybrid_rrf_k: int = 60,
    disable_hybrid: bool = False,
    api_key: Optional[str] = None,
    rerank_top_n: Optional[int] = None,
    rerank_model: Optional[str] = None,
    use_query_rewrite: Optional[bool] = None,
    entities_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the full retrieval pipeline for debugging."""
    profile = build_query_profile(query)
    debug_diagnostics: Dict[str, Any] = {
        "query_profile": _profile_dict(profile),
    }
    if not query:
        debug_diagnostics.update(
            {
                "retrieval_mode": "hybrid",
                "degradations": [],
                "vector_error": None,
                "keyword_error": None,
                "embed_ms": 0.0,
                "rerank_ms": 0.0,
                "retrieve_ms": 0.0,
            }
        )
        return {
            "original_query": query,
            "rewritten_query": query,
            "used_entities": {},
            "vector_hits": [],
            "keyword_hits": [],
            "rrf_hits": [],
            "reranked_hits": [],
            "fallback_triggered": False,
            "diagnostics": debug_diagnostics,
        }

    retrieve_started = perf_counter()
    try:
        effective_rerank_top_n = _effective_rerank_top_n(rerank_top_n, profile)
        rerank_enabled = effective_rerank_top_n > 0
        rewritten_query, used_entities = rewrite_query(
            query,
            use_llm=use_query_rewrite,
            api_key=api_key,
        )
        rerank_query = compress_for_rerank(rewritten_query) if profile.is_long else None

        vector_hits, vector_error = _safe_vector_leg(
            rewritten_query,
            collection=collection,
            qdrant_url=qdrant_url,
            limit=(
                effective_rerank_top_n if rerank_enabled else top_k
            )
            if disable_hybrid
            else hybrid_vector_candidates,
            api_key=api_key,
            diagnostics=debug_diagnostics,
        )
        if disable_hybrid:
            keyword_hits, keyword_error = [], None
        else:
            keyword_hits, keyword_error = _safe_keyword_leg(
                rewritten_query,
                limit=hybrid_keyword_candidates,
            )

        retrieval_mode = _mode_for_legs(
            vector_hits,
            keyword_hits,
            failed=not vector_hits and not keyword_hits and bool(vector_error or keyword_error),
        )
        _set_diagnostics(
            debug_diagnostics,
            vector_error=vector_error,
            keyword_error=keyword_error,
            retrieval_mode=retrieval_mode,
        )

        source_hits = vector_hits if retrieval_mode == "vector_only" else keyword_hits
        source_scores = {
            str(item.get("id")): item.get("score") for item in source_hits
        }
        if retrieval_mode == "hybrid":
            merged = _rrf_merge([leg for leg in (vector_hits, keyword_hits) if leg], k=hybrid_rrf_k)
        else:
            merged = list(source_hits)

        rrf_base = merged[:effective_rerank_top_n] if rerank_enabled else merged[:top_k]
        rrf_hits = _annotate_results(
            rrf_base,
            query=rewritten_query,
            retrieval_mode=retrieval_mode,
            rerank_enabled=False,
            source_scores=source_scores,
        )

        if rerank_enabled:
            candidate_ids = {str(item.get("id")) for item in rrf_base}
            rerank_started = perf_counter()
            try:
                reranked_raw = rerank(
                    rerank_query or rewritten_query,
                    rrf_base,
                    top_k=top_k,
                    model_name=rerank_model,
                ) or []
            finally:
                debug_diagnostics["rerank_ms"] = _elapsed_ms(rerank_started)
            reranked_hits = _annotate_results(
                reranked_raw,
                query=rewritten_query,
                retrieval_mode=retrieval_mode,
                rerank_enabled=True,
                source_scores=source_scores,
                rerank_candidate_ids=candidate_ids,
            )
        else:
            reranked_hits = rrf_hits[:top_k]
            debug_diagnostics["rerank_ms"] = 0.0
        reranked_hits = _apply_temporal_weight(reranked_hits)
        reranked_hits = _apply_year_priority(reranked_hits, profile, debug_diagnostics)
        fallback_triggered = _should_fallback(
            reranked_hits,
            rerank_enabled=rerank_enabled,
        )

        def _clip(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out = []
            for item in items:
                clipped = dict(item)
                text = clipped.get("text") or ""
                if len(text) > 300:
                    clipped["text"] = text[:300] + "..."
                out.append(clipped)
            return out

        return {
            "original_query": query,
            "rewritten_query": rewritten_query,
            "used_entities": used_entities,
            "vector_hits": _clip(vector_hits),
            "keyword_hits": _clip(keyword_hits),
            "rrf_hits": _clip(rrf_hits),
            "reranked_hits": _clip(reranked_hits),
            "fallback_triggered": fallback_triggered,
            "diagnostics": debug_diagnostics,
        }
    finally:
        debug_diagnostics["retrieve_ms"] = _elapsed_ms(retrieve_started)
