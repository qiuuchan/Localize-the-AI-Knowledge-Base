"""Unit tests for v1.1.0 PR#1 — DELETE database with 409 guard + cascade Qdrant fallback.

覆盖 FMEA 二级保护:
  - 有子文档时 DELETE 必须返回 409 + child_documents 计数,避免误删向量
  - 无子文档时 DELETE 直接成功(向后兼容旧行为)
  - cascade=true 时 Qdrant 不可达 → 200 + warning + degradation_events(component='Vector'),
    不阻断主流程(数据可在下次 stop.bat 后手动清理)

实现注:endpoint 用 `count_documents_by_database as _count_docs_impl` 导入别名,
本测试 patch 模块局部名 `backend.api.databases._count_docs_impl` 才能真正影响
endpoint 调用。pydantic/Query 层 + DELETE 路由仍走真实 FastAPI app,确保契约层
与运行时一致。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api import databases as db_api
from backend.main import app


_FAKE_DB = {
    "id": "my_db",
    "name": "测试库",
    "description": "",
    "collection": "kb_chunks_my_db",
    "embed_model": "text-embedding-v3",
    "chunk_size": 500,
    "chunk_overlap": 80,
    "created_at": "2026-01-01T00:00:00+00:00",
}


@pytest.fixture()
def patch_db_layer(monkeypatch):
    """默认把 get_database / _count_docs_impl / _delete_db_impl 都 mock 成 safe stubs。

    各测试可覆盖 monkeypatch.setattr 调用以调整行为。返回 fake_db 字典方便复用。
    """
    fake_db = dict(_FAKE_DB)
    monkeypatch.setattr(db_api, "get_database", lambda db_id: fake_db)
    monkeypatch.setattr(db_api, "_count_docs_impl", lambda db_id: 0)
    monkeypatch.setattr(db_api, "_delete_db_impl", lambda db_id, cascade: True)
    return fake_db


def test_delete_database_with_children_returns_409(monkeypatch, patch_db_layer):
    """db 仍有子文档 → 默认 cascade=false 时返回 409,不删。"""
    monkeypatch.setattr(db_api, "_count_docs_impl", lambda db_id: 5)
    client = TestClient(app)
    resp = client.delete("/api/knowledge/databases/my_db")
    assert resp.status_code == 409
    body = resp.json()
    # FastAPI 把 HTTPException(detail=dict) 序列化在 body["detail"] 里
    detail = body["detail"]
    assert detail["child_documents"] == 5
    assert detail["requires_cascade"] is True


def test_delete_database_no_children_succeeds(monkeypatch, patch_db_layer):
    """db 无子文档 → cascade=false 也能直接删(向后兼容)。"""
    # 默认 _count_docs_impl → 0,_delete_db_impl → True
    client = TestClient(app)
    resp = client.delete("/api/knowledge/databases/empty_db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["database_id"] == "empty_db"
    assert body["cascade"] is False
    assert body["warnings"] == []


def test_delete_database_cascade_qdrant_down_returns_warning(monkeypatch, patch_db_layer):
    """cascade=true 但 Qdrant 不可达 → 返回 200 + warning + degradation_events。"""
    monkeypatch.setattr(db_api, "_delete_db_impl", lambda db_id, cascade: True)
    # qdrant_store.delete_collection 是模块属性,patch 源模块即可
    monkeypatch.setattr(
        "backend.core.rag.qdrant_store.delete_collection",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Qdrant offline")),
    )
    captured = []
    # save_degradation_event 是 endpoint 在 except 块内 import 的函数,
    # 每次调用 re-import 当前模块属性 → patch 源模块即可
    monkeypatch.setattr(
        "backend.core.sqlite.degradation_repo.save_degradation_event",
        lambda **kw: captured.append(kw),
    )
    client = TestClient(app)
    resp = client.delete("/api/knowledge/databases/some_db?cascade=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["warnings"]
    assert any("Qdrant" in w or "offline" in w for w in body["warnings"])
    assert any(c.get("component") == "Vector" for c in captured)
