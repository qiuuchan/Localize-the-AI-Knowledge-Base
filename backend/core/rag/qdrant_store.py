"""Qdrant 1.7.x store for KB-AI.

Mirrors scripts/embed-and-ingest.ps1 + scripts/chat.ps1 search path.

Operations:
  - ensure_collection(name): PUT /collections/{name} with Cosine + 1024 dim
  - upsert_points(name, points): PUT /collections/{name}/points (Qdrant 1.7
    accepts PUT here; POST would be interpreted as retrieve-by-ids)
  - search(name, vector, limit, with_payload=True): POST /collections/{name}/points/search
  - delete_by_source(name, source): POST /collections/{name}/points/delete with payload filter
  - scroll_by_source(name, source, limit, offset): POST /collections/{name}/points/scroll
  - health(): GET / (v0.7.2 fix: /health returns 404, root returns 200 + version)

Point schema:
  {
    "id": "<uuid>",
    "vector": [float; 1024],
    "payload": {"text": str, "source": str, "source_file": str, "section": int}
  }
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

from backend.core.config import get_env_or_env_var

DEFAULT_URL = "http://localhost:6333"
DEFAULT_COLLECTION = "kb_ai_chunks"
EMBEDDING_DIM = 1024


def _base_url(url: Optional[str]) -> str:
    return (url or get_env_or_env_var("QDRANT_URL") or DEFAULT_URL).rstrip("/")


def _request(
    method: str,
    url: str,
    *,
    data: Optional[dict] = None,
    timeout: int = 30,
    allow_404: bool = False,
) -> Dict[str, Any]:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if allow_404 and e.code == 404:
            return {"_status": 404, "_body": body}
        raise RuntimeError(f"Qdrant {method} {url} HTTP {e.code}: {body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Qdrant unreachable {url}: {e}")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def health(url: Optional[str] = None) -> bool:
    """Check if Qdrant is reachable."""
    try:
        resp = _request("GET", f"{_base_url(url)}/", timeout=5)
        return isinstance(resp, dict) and ("version" in resp or "title" in resp)
    except Exception:
        return False


def ensure_collection(
    name: str = DEFAULT_COLLECTION,
    *,
    dim: int = EMBEDDING_DIM,
    distance: str = "Cosine",
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Create collection if not exists; idempotent.

    Qdrant 1.7 returns 404 for GET on a missing collection; we treat that as
    'not yet created' rather than an error.
    """
    info = _request("GET", f"{_base_url(url)}/collections/{name}", timeout=10, allow_404=True)
    if info.get("_status") != 404 and info.get("result"):
        return info

    body = {
        "name": name,
        "vectors": {"size": dim, "distance": distance},
    }
    return _request("PUT", f"{_base_url(url)}/collections/{name}", data=body, timeout=30)


def get_collection_info(
    name: str,
    *,
    url: Optional[str] = None,
    allow_404: bool = True,
) -> Optional[Dict[str, Any]]:
    """v1.0.2 公开包装:返回 collection 元信息 `{points_count, vector_size, ...}`。

    原 v0.8.11 dashboard.py 直接调 `_request` + `_base_url`,借道私有 API,
    耦合易碎。此处暴露稳定 contract:
      - 200 + 存在 → 返回 dict(含 `points_count`),已清掉 status 字段
      - 404(allow_404=True)→ 返回 None(语义:该 collection 不存在)
      - 不允许 404 或 Qdrant 不可达 → 抛 RuntimeError(透传底层)
    """
    resp = _request(
        "GET",
        f"{_base_url(url)}/collections/{name}",
        timeout=10,
        allow_404=allow_404,
    )
    if resp.get("_status") == 404:
        return None
    result = resp.get("result") or {}
    result.pop("_status", None)
    return result


def upsert_points(
    points: List[Dict[str, Any]],
    name: str = DEFAULT_COLLECTION,
    *,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Upsert points (PUT). Each point: {id, vector, payload}."""
    if not points:
        return {"result": {"status": "empty"}, "noop": True}
    body = {"points": points}
    return _request("PUT", f"{_base_url(url)}/collections/{name}/points", data=body, timeout=60)


def search(
    vector: List[float],
    *,
    name: str = DEFAULT_COLLECTION,
    limit: int = 5,
    with_payload: bool = True,
    url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Vector search. Returns list of {id, score, payload}."""
    body = {
        "vector": vector,
        "limit": limit,
        "with_payload": with_payload,
    }
    resp = _request(
        "POST", f"{_base_url(url)}/collections/{name}/points/search", data=body, timeout=30
    )
    return resp.get("result") or []


def delete_by_source(
    source: str,
    *,
    name: str = DEFAULT_COLLECTION,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete all points with payload.source == source."""
    body = {
        "filter": {
            "must": [{"key": "source", "match": {"value": source}}]
        }
    }
    return _request(
        "POST",
        f"{_base_url(url)}/collections/{name}/points/delete",
        data=body,
        timeout=60,
    )


def delete_by_ids(
    ids: "Sequence[str]",
    *,
    name: str = DEFAULT_COLLECTION,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete specific points by their IDs."""
    if not ids:
        return {"result": {"status": "empty"}, "noop": True}
    return _request(
        "POST",
        f"{_base_url(url)}/collections/{name}/points/delete",
        data={"points": [str(value) for value in ids]},
        timeout=60,
    )


def scroll_by_source(
    source: str,
    *,
    name: str = DEFAULT_COLLECTION,
    limit: int = 50,
    offset: Optional[str] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Scroll all chunks belonging to a source. Returns {points, next_page_offset}."""
    body: Dict[str, Any] = {
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
        "filter": {
            "must": [{"key": "source", "match": {"value": source}}]
        },
    }
    if offset:
        body["offset"] = offset
    return _request(
        "POST", f"{_base_url(url)}/collections/{name}/points/scroll", data=body, timeout=30
    )


def list_sources(
    *,
    name: str = DEFAULT_COLLECTION,
    url: Optional[str] = None,
) -> List[str]:
    """List distinct sources by scrolling collection. Best-effort, capped at 10k."""
    body = {
        "limit": 1000,
        "with_payload": ["source"],
        "with_vector": False,
    }
    seen: List[str] = []
    seen_set = set()
    offset = None
    for _ in range(20):  # safety cap
        if offset:
            body["offset"] = offset
        elif "offset" in body:
            del body["offset"]
        resp = _request(
            "POST",
            f"{_base_url(url)}/collections/{name}/points/scroll",
            data=body,
            timeout=30,
        )
        result = resp.get("result") or {}
        for p in result.get("points") or []:
            src = ((p.get("payload") or {}).get("source")) or ""
            if src and src not in seen_set:
                seen.append(src)
                seen_set.add(src)
        offset = result.get("next_page_offset")
        if not offset:
            break
    return seen


# ---------------------------------------------------------------------------
# v0.8.11(P1.1):collection 生命周期 — 删 / 列表
# ---------------------------------------------------------------------------


def delete_collection(
    name: str,
    *,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """Drop a Qdrant collection entirely. Idempotent on 404.

    Used by /api/knowledge/databases/{id}?cascade=true to clean up a db's vectors.
    """
    return _request(
        "DELETE",
        f"{_base_url(url)}/collections/{name}",
        timeout=30,
        allow_404=True,
    )


def list_collections(
    *,
    url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all Qdrant collections. Returns [{name, ...}, ...]."""
    resp = _request("GET", f"{_base_url(url)}/collections", timeout=10)
    result = resp.get("result") or {}
    return result.get("collections") or []
