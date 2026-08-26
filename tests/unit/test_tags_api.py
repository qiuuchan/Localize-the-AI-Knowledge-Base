"""Unit tests for v1.1.0 PR#4 — tags + doc_tags tables + CRUD functions."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.core.sqlite import init_db
from backend.core.sqlite.databases_repo import DEFAULT_DATABASE_ID
from backend.core.sqlite.tags_repo import (
    assign_tags_to_doc,
    create_tag,
    list_documents_by_tags,
    list_tags,
    list_tags_for_doc,
)
from backend.main import app


def test_init_db_creates_tags_table(tmp_path):
    """init_db 应建 tags 表。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tags'"
    )
    assert cur.fetchone() is not None
    # doc_tags 表 + idx_doc_tags_tag 索引也应一并建立
    cur2 = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_tags'"
    )
    assert cur2.fetchone() is not None
    cur3 = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND name='idx_doc_tags_tag'"
    )
    assert cur3.fetchone() is not None
    conn.close()


def test_create_and_list_tags(tmp_path):
    """create_tag → list_tags 应返回该 tag。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    tid = create_tag(DEFAULT_DATABASE_ID, "财务", db_path=db_path)
    tags = list_tags(DEFAULT_DATABASE_ID, db_path=db_path)
    assert len(tags) == 1
    assert tags[0]["name"] == "财务"
    assert tags[0]["color"] == "#FF540E"
    assert tags[0]["id"] == tid
    assert tags[0]["database_id"] == DEFAULT_DATABASE_ID


def test_create_duplicate_tag_raises(tmp_path):
    """同 db 同名 → ValueError。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    create_tag(DEFAULT_DATABASE_ID, "财务", db_path=db_path)
    with pytest.raises(ValueError):
        create_tag(DEFAULT_DATABASE_ID, "财务", db_path=db_path)


def test_assign_and_list_doc_tags(tmp_path):
    """assign_tags_to_doc → list_tags_for_doc 应返回关联 tag。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    t1 = create_tag(DEFAULT_DATABASE_ID, "财务", db_path=db_path)
    t2 = create_tag(DEFAULT_DATABASE_ID, "Q3", db_path=db_path)
    assign_tags_to_doc("default::budget.pdf", [t1, t2], db_path=db_path)
    tags = list_tags_for_doc("default::budget.pdf", db_path=db_path)
    assert {t["name"] for t in tags} == {"财务", "Q3"}


def test_list_documents_by_tags_intersect(tmp_path):
    """list_documents_by_tags 应只返回同时拥有所有 tag 的文档。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    t1 = create_tag(DEFAULT_DATABASE_ID, "财务", db_path=db_path)
    t2 = create_tag(DEFAULT_DATABASE_ID, "Q3", db_path=db_path)
    assign_tags_to_doc("default::budget_q3.pdf", [t1, t2], db_path=db_path)
    assign_tags_to_doc("default::budget_q4.pdf", [t1], db_path=db_path)
    docs = list_documents_by_tags(DEFAULT_DATABASE_ID, [t1, t2], db_path=db_path)
    assert len(docs) == 1
    assert docs[0]["source"] == "default::budget_q3.pdf"


def _all_route_paths(app_obj) -> set[str]:
    """Walk app.routes + included router routes → set of templated paths.

    Accumulates prefix from include_router(..., prefix=...) so the returned
    paths mirror the actual request paths.
    """
    paths: set[str] = set()

    def _walk(routes, prefix: str = "") -> None:
        for r in routes:
            original = getattr(r, "original_router", None)
            if original is not None and hasattr(original, "routes"):
                ic = getattr(r, "include_context", None)
                sub_prefix = (getattr(ic, "prefix", "") or "") if ic is not None else ""
                _walk(original.routes, prefix + sub_prefix)
                continue
            path = getattr(r, "path", None)
            if path:
                paths.add(prefix + path)

    _walk(app_obj.routes)
    return paths


def test_tags_endpoints_registered():
    """tags 路由应注册到 app。"""
    paths = _all_route_paths(app)
    assert "/api/knowledge/databases/{db_id}/tags" in paths
    assert "/api/knowledge/tags/{tag_id}" in paths


# ---------------------------------------------------------------------------
# E2E(走 FastAPI TestClient + 真实 HTTP 路由)
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_db(monkeypatch, tmp_path):
    """Redirect SQLite to a tempfile and rebuild schema(mirrors test_database_crud)。"""
    from backend.core import sqlite as sqlite_mod
    db_file = tmp_path / "e2e.db"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file


def test_create_tag_via_api(fresh_db):
    """走 FastAPI TestClient 完整端到端:create + 409 + delete。"""
    client = TestClient(app)
    resp = client.post(
        "/api/knowledge/databases/default/tags",
        json={"name": "财务", "color": "#FF540E"},
    )
    assert resp.status_code == 200
    tag_id = resp.json()["id"]
    # 重名
    resp2 = client.post(
        "/api/knowledge/databases/default/tags",
        json={"name": "财务"},
    )
    assert resp2.status_code == 409
    # 删除
    resp3 = client.delete(f"/api/knowledge/tags/{tag_id}")
    assert resp3.status_code == 200
    assert resp3.json()["deleted"] is True


def test_assign_doc_tags_via_api(fresh_db):
    """POST /api/knowledge/doc-tags 端到端 + 按 tag 过滤文档。"""
    client = TestClient(app)
    t1 = client.post(
        "/api/knowledge/databases/default/tags",
        json={"name": "财务"},
    ).json()
    t2 = client.post(
        "/api/knowledge/databases/default/tags",
        json={"name": "Q3"},
    ).json()
    resp = client.post(
        "/api/knowledge/doc-tags",
        json={"source": "default::budget.pdf", "tag_ids": [t1["id"], t2["id"]]},
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_count"] == 2
    # 按 tag 过滤
    resp2 = client.get(
        f"/api/knowledge/databases/default/documents?tag_ids={t1['id']},{t2['id']}",
    )
    assert resp2.status_code == 200
    docs = resp2.json()
    assert any(d["source"] == "default::budget.pdf" for d in docs)


def test_cascade_delete_tag_removes_doc_tags(fresh_db):
    """删 tag → doc_tags 关联 CASCADE 删。"""
    client = TestClient(app)
    tag = client.post(
        "/api/knowledge/databases/default/tags",
        json={"name": "临时"},
    ).json()
    client.post(
        "/api/knowledge/doc-tags",
        json={"source": "default::x.pdf", "tag_ids": [tag["id"]]},
    )
    client.delete(f"/api/knowledge/tags/{tag['id']}")
    # 查 doc_tags 应空
    docs = client.get(
        f"/api/knowledge/databases/default/documents?tag_ids={tag['id']}",
    )
    assert docs.json() == []


def test_cross_db_isolation(fresh_db):
    """同 tag 名跨 db 互不影响。"""
    from backend.core.sqlite import databases_repo as bs
    bs.create_database("db_a", "A")
    bs.create_database("db_b", "B")

    client = TestClient(app)
    r1 = client.post(
        "/api/knowledge/databases/db_a/tags",
        json={"name": "财务"},
    )
    r2 = client.post(
        "/api/knowledge/databases/db_b/tags",
        json={"name": "财务"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
