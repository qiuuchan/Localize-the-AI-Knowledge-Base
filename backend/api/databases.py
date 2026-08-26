"""Knowledge database CRUD endpoints (v0.8.11 P1.1).

Implements PRD REQ-2 主分类管理:
  GET    /api/knowledge/databases             list databases (+ document_count)
  POST   /api/knowledge/databases             create database
  GET    /api/knowledge/databases/{id}        fetch one
  PATCH  /api/knowledge/databases/{id}        update name/desc/chunk params
  DELETE /api/knowledge/databases/{id}        drop metadata (?cascade=true to drop collection)
  POST   /api/knowledge/databases/{id}/assign bulk-assign existing sources to this db
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.rag import qdrant_store as rag_qdrant
from backend.core.sqlite.databases_repo import (
    DEFAULT_DATABASE_ID,
    bulk_assign_documents_to_database as _bulk_assign_impl,
    count_documents_by_database as _count_docs_impl,
    create_database as _create_db,
    delete_database as _delete_db_impl,
    ensure_default_database,
    get_database,
    list_databases,
    update_database as _update_db_impl,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateDatabaseRequest(BaseModel):
    # v1.0.2:db_id 字符集在 Pydantic 层先卡一遍,422 直接拒,避免走到 sqlite 层再
    # raise ValueError。后续 Qdrant collection 名 + parse cache 路径都依赖这个约束。
    id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="字母/数字/下划线/连字符,1-64 字符",
    )
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=80, ge=0, le=500)
    embed_model: str = Field(default="text-embedding-v3", max_length=64)


class UpdateDatabaseRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    chunk_size: Optional[int] = Field(default=None, ge=100, le=2000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=500)


class AssignRequest(BaseModel):
    sources: List[str] = Field(..., min_length=1)


def _serialize(db: Dict[str, Any]) -> Dict[str, Any]:
    """Trim to public-facing shape and ensure document_count is filled."""
    out = dict(db)
    out.setdefault("document_count", 0)
    return out


@router.get("/knowledge/databases")
def list_all_databases() -> List[Dict[str, Any]]:
    ensure_default_database()
    return [_serialize(d) for d in list_databases()]


@router.post("/knowledge/databases")
def create_database_endpoint(body: CreateDatabaseRequest) -> Dict[str, Any]:
    try:
        _create_db(
            db_id=body.id,
            name=body.name,
            description=body.description,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
            embed_model=body.embed_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(get_database(body.id) or {})


@router.get("/knowledge/databases/{db_id}")
def get_database_endpoint(db_id: str) -> Dict[str, Any]:
    db = get_database(db_id)
    if not db:
        raise HTTPException(status_code=404, detail=f"database '{db_id}' 不存在")
    db["document_count"] = _count_docs_impl(db_id)
    return _serialize(db)


@router.patch("/knowledge/databases/{db_id}")
def update_database_endpoint(db_id: str, body: UpdateDatabaseRequest) -> Dict[str, Any]:
    try:
        _update_db_impl(
            db_id=db_id,
            name=body.name,
            description=body.description,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize(get_database(db_id) or {})


@router.delete("/knowledge/databases/{db_id}")
def delete_database_endpoint(
    db_id: str,
    cascade: bool = Query(default=False, description="true 时同时删 Qdrant collection + keyword 行 + tag 关联"),
) -> Dict[str, Any]:
    if db_id == DEFAULT_DATABASE_ID:
        raise HTTPException(
            status_code=400,
            detail="'default' 数据库不可删除(承载存量数据,改用 assign 迁移)",
        )
    db = get_database(db_id)
    if not db:
        raise HTTPException(status_code=404, detail=f"database '{db_id}' 不存在")

    # v1.1.0 PR#1:FMEA 二级保护 — 有子文档时拒绝删,要求显式 cascade=true
    child_count = _count_docs_impl(db_id)
    if child_count > 0 and not cascade:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"database '{db_id}' 仍有 {child_count} 个文档,需 cascade=true 显式确认",
                "child_documents": child_count,
                "requires_cascade": True,
            },
        )

    # 先删 metadata,再按需 cascade
    deleted = _delete_db_impl(db_id, cascade=cascade)
    warnings: List[str] = []
    if cascade:
        try:
            rag_qdrant.delete_collection(db["collection"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Qdrant collection 清理失败 db_id=%s collection=%s", db_id, db["collection"])
            # 不阻断 200;降级路径写 degradation_events
            from backend.core.sqlite.degradation_repo import save_degradation_event
            save_degradation_event(
                session_id=None,
                query=None,
                source=db_id,
                reason=f"cascade delete: Qdrant cleanup failed: {exc}",
                model=None,
                component="Vector",
            )
            warnings.append(f"Qdrant collection 清理失败: {exc}")

    return {
        "deleted": deleted,
        "database_id": db_id,
        "cascade": cascade,
        "warnings": warnings,
    }


@router.post("/knowledge/databases/{db_id}/assign")
def assign_documents_endpoint(db_id: str, body: AssignRequest) -> Dict[str, Any]:
    """把旧 source 批量划归到指定 db。同步重写 keyword_index.source 列。

    不动 Qdrant 中的向量;后续检索时根据 db_id 决定 collection,
    新上传会自动用新前缀,但存量 source 需手动重索引(若要使用新 db 的 collection)。
    """
    db = get_database(db_id)
    if not db:
        raise HTTPException(status_code=404, detail=f"database '{db_id}' 不存在")
    try:
        affected = _bulk_assign_impl(db_id, body.sources)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"database_id": db_id, "affected": affected, "sources": body.sources}
