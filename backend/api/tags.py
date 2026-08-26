"""Tags API (v1.1.0 PR#4):独立于 Database 的自由标签。

Endpoints:
  GET    /api/knowledge/databases/{db_id}/tags
  POST   /api/knowledge/databases/{db_id}/tags
  PATCH  /api/knowledge/tags/{tag_id}
  DELETE /api/knowledge/tags/{tag_id}
  POST   /api/knowledge/doc-tags
  DELETE /api/knowledge/doc-tags/{source}/{tag_id}
  GET    /api/knowledge/databases/{db_id}/documents?tag_ids=1,2,3
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, conlist

from backend.core.sqlite.tags_repo import (
    assign_tags_to_doc,
    create_tag,
    delete_tag,
    get_tag,
    list_documents_by_tags,
    list_tags,
    list_tags_for_doc,
    unassign_tag_from_doc,
    update_tag,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateTagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    color: str = Field(default="#FF540E", pattern=r"^#[0-9A-Fa-f]{6}$")


class UpdateTagRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class AssignTagsRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=512)
    tag_ids: conlist(int, min_length=1, max_length=50)


@router.get("/knowledge/databases/{db_id}/tags")
def list_tags_endpoint(db_id: str) -> List[Dict[str, Any]]:
    return list_tags(db_id)


@router.post("/knowledge/databases/{db_id}/tags")
def create_tag_endpoint(db_id: str, body: CreateTagRequest) -> Dict[str, Any]:
    try:
        tag_id = create_tag(db_id, body.name, body.color)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return get_tag(tag_id) or {}


@router.patch("/knowledge/tags/{tag_id}")
def update_tag_endpoint(tag_id: int, body: UpdateTagRequest) -> Dict[str, Any]:
    if not get_tag(tag_id):
        raise HTTPException(status_code=404, detail=f"tag {tag_id} 不存在")
    try:
        update_tag(tag_id, name=body.name, color=body.color)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    return get_tag(tag_id) or {}


@router.delete("/knowledge/tags/{tag_id}")
def delete_tag_endpoint(tag_id: int) -> Dict[str, Any]:
    if not get_tag(tag_id):
        raise HTTPException(status_code=404, detail=f"tag {tag_id} 不存在")
    delete_tag(tag_id)
    return {"deleted": True, "tag_id": tag_id}


@router.post("/knowledge/doc-tags")
def assign_tags_endpoint(body: AssignTagsRequest) -> Dict[str, Any]:
    inserted = assign_tags_to_doc(body.source, body.tag_ids)
    return {
        "source": body.source,
        "assigned_count": inserted,
        "tag_ids": body.tag_ids,
        "tags": list_tags_for_doc(body.source),
    }


@router.delete("/knowledge/doc-tags/{source}/{tag_id}")
def unassign_tag_endpoint(source: str, tag_id: int) -> Dict[str, Any]:
    deleted = unassign_tag_from_doc(source, tag_id)
    return {"deleted": deleted, "source": source, "tag_id": tag_id}


@router.get("/knowledge/databases/{db_id}/documents")
def list_documents_by_tags_endpoint(
    db_id: str,
    tag_ids: str = Query(..., description="逗号分隔 tag id 列表,如 1,2,3"),
) -> List[Dict[str, Any]]:
    ids = [int(x) for x in tag_ids.split(",") if x.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="tag_ids 不能为空")
    return list_documents_by_tags(db_id, ids)
