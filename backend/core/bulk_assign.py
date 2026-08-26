"""Qdrant payload 批量重写 — 用于跨 database 文档迁移。

设计原则:
- 与 keyword_index 同步,但失败降级(不阻断主流程)
- 走 Qdrant REST scroll + set_payload 批量 API
- 上限 100 条/批,避免单批过大超时
- 通过 degradation_events(component='Vector') 记录失败

仅供 backend/core/sqlite.py:bulk_assign_documents_to_database 调用,
不在 API 路由层暴露。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.rag import qdrant_store as rag_qdrant

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def _scroll_points_by_source(
    collection: str, source: str, *, url: Optional[str] = None
) -> List[Dict[str, Any]]:
    """拉取 collection 内 payload.source = source 的所有 points。

    单次 scroll 上限 BATCH_SIZE;若超过该值,后续 v2.x 应加分页循环。
    本次实现聚焦跨 db 单文档迁移(< 100 chunks/source),不实现分页。
    """
    body = {
        "filter": {"must": [{"key": "source", "match": {"value": source}}]},
        "limit": BATCH_SIZE,
        "with_payload": True,
        "with_vector": False,
    }
    resp = rag_qdrant._request(  # noqa: SLF001 — 内部 helper,测试可 mock
        "POST",
        f"{rag_qdrant._base_url(url)}/collections/{collection}/points/scroll",  # noqa: SLF001
        data=body,
        timeout=30,
    )
    return resp.get("result", {}).get("points", [])


def _qdrant_set_payload_batch(
    collection: str,
    points: List[Dict[str, Any]],
    *,
    url: Optional[str] = None,
) -> None:
    """批量更新 points 的 payload(Qdrant REST PUT /points/payload)。

    points: List[{id, payload}] — Qdrant 标准 set_payload 批量格式。
    """
    if not points:
        return
    body = {"points": points}
    rag_qdrant._request(  # noqa: SLF001 — 内部 helper,测试可 mock
        "PUT",
        f"{rag_qdrant._base_url(url)}/collections/{collection}/points/payload",  # noqa: SLF001
        data=body,
        timeout=60,
    )


def _rewrite_qdrant_payloads(
    old_source: str,
    new_source: str,
    *,
    collection: str,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """把 collection 内所有 payload.source = old_source 的 points 改为 new_source。

    Returns:
        {"rewritten": int, "warnings": List[str]}
        - rewritten:成功写入 Qdrant 的 points 数(可能小于应写总数)。
        - warnings:per-batch set_payload 失败描述,空列表表示全量成功。

    Raises:
        仅 scroll 失败时向上抛原异常(未包装),调用方 sqlite.py 负责
        try/except 降级为 degradation_events(component='Vector')。
        per-batch set_payload 失败不抛,仅写入 warnings(部分写入语义)。
    """
    points = _scroll_points_by_source(collection, old_source, url=url)
    if not points:
        return {"rewritten": 0, "warnings": []}

    updates = [
        {"id": p["id"], "payload": {**p.get("payload", {}), "source": new_source}}
        for p in points
    ]

    written = 0
    warnings: List[str] = []
    for batch_start in range(0, len(updates), BATCH_SIZE):
        batch = updates[batch_start : batch_start + BATCH_SIZE]
        try:
            _qdrant_set_payload_batch(collection, batch, url=url)
            written += len(batch)
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"batch {batch_start}-{batch_start + len(batch)} failed: {exc}"
            )
            logger.warning("Qdrant payload rewrite partial failure: %s", exc)

    return {"rewritten": written, "warnings": warnings}
