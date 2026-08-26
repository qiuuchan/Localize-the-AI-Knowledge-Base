"""Unit tests for v0.8.11(P1.1) database CRUD + helper functions."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.core import sqlite as sqlite_mod
from backend.core.sqlite import databases_repo, degradation_repo


@pytest.fixture()
def fresh_db(monkeypatch):
    """Redirect SQLite to a tempfile and rebuild schema."""
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-"))
    db_file = tmp / "test.sqlite"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file
    # cleanup
    try:
        db_file.unlink()
        os.rmdir(tmp)
    except OSError:
        pass


def test_init_db_creates_default(fresh_db):
    db = databases_repo.get_database("default")
    assert db is not None
    assert db["name"] == "默认分类"
    assert db["collection"] == "kb_ai_chunks"


def test_create_and_get(fresh_db):
    databases_repo.create_database("finance", "财务部", description="2025 SOP")
    db = databases_repo.get_database("finance")
    assert db is not None
    assert db["name"] == "财务部"
    assert db["description"] == "2025 SOP"
    assert db["collection"] == "kb_chunks_finance"
    assert db["chunk_size"] == 500
    assert db["chunk_overlap"] == 80


def test_create_duplicate_rejected(fresh_db):
    databases_repo.create_database("ops", "运营部")
    with pytest.raises(ValueError, match="已存在"):
        databases_repo.create_database("ops", "运营部2")


def test_create_invalid_id_rejected(fresh_db):
    with pytest.raises(ValueError, match="字母、数字"):
        databases_repo.create_database("invalid id with spaces", "X")


def test_update_database(fresh_db):
    databases_repo.create_database("kitchen", "厨房")
    databases_repo.update_database(
        "kitchen",
        name="厨房部",
        description="中央厨房 SOP",
        chunk_size=600,
    )
    db = databases_repo.get_database("kitchen")
    assert db["name"] == "厨房部"
    assert db["chunk_size"] == 600


def test_update_missing_raises(fresh_db):
    with pytest.raises(ValueError, match="不存在"):
        databases_repo.update_database("ghost", name="X")


def test_delete_default_rejected(fresh_db):
    with pytest.raises(ValueError, match="default"):
        databases_repo.delete_database("default")


def test_delete_nonexistent_returns_zero(fresh_db):
    assert databases_repo.delete_database("ghost") == 0


def test_delete_cascade_only(fresh_db):
    databases_repo.create_database("train", "培训")
    databases_repo.delete_database("train", cascade=False)
    assert databases_repo.get_database("train") is None


def test_list_databases_orders_default_first(fresh_db):
    databases_repo.create_database("a", "A")
    databases_repo.create_database("b", "B")
    rows = databases_repo.list_databases()
    assert rows[0]["id"] == "default"
    assert {r["id"] for r in rows} == {"default", "a", "b"}


def test_source_namespacing(fresh_db):
    """Sources without '::' belong to default; with prefix belong to that db."""
    import sqlite3 as sq

    # simulate 3 sources: 2 in default, 1 in 'finance'
    with sq.connect(str(fresh_db)) as c:
        c.executescript(
            """
            INSERT INTO keyword_index(word, point_id, source, text) VALUES
              ('红烧肉', 'p1', 'cookbook.pdf', '红烧肉做法'),
              ('解腻', 'p2', 'cookbook.pdf', '解腻菜'),
              ('报销', 'p3', 'finance::policy.pdf', '差旅报销流程');
            """
        )
        c.commit()

    assert databases_repo.count_documents_by_database("default") == 1
    assert databases_repo.count_documents_by_database("finance") == 1


def test_bulk_assign(fresh_db):
    import sqlite3 as sq

    with sq.connect(str(fresh_db)) as c:
        c.executescript(
            "INSERT INTO keyword_index(word, point_id, source, text) "
            "VALUES ('a', 'p1', 'menu.docx', 'x'), ('b', 'p2', 'menu.docx', 'y');"
        )
        c.commit()

    databases_repo.create_database("ops", "运营")
    affected = databases_repo.bulk_assign_documents_to_database("ops", ["menu.docx"])
    assert affected == 1
    assert databases_repo.count_documents_by_database("ops") == 1


def test_bulk_assign_idempotent(fresh_db):
    import sqlite3 as sq

    with sq.connect(str(fresh_db)) as c:
        c.executescript(
            "INSERT INTO keyword_index(word, point_id, source, text) "
            "VALUES ('a', 'p1', 'ops::menu.docx', 'x');"
        )
        c.commit()
    databases_repo.create_database("ops", "运营")
    # Already namespaced → affected should be 0
    affected = databases_repo.bulk_assign_documents_to_database("ops", ["menu.docx"])
    assert affected == 0


def test_processing_state_lifecycle(fresh_db):
    """upsert → upsert(更新阶段) → finish → recover_orphans 找空集。"""
    databases_repo.upsert_processing(
        task_id="t1", operation="upload", source="a.pdf",
        database_id="default", stage="解析中", status="processing",
    )
    # 更新阶段
    databases_repo.upsert_processing(
        task_id="t1", operation="upload", source="a.pdf",
        database_id="default", stage="嵌入中", status="processing",
    )
    databases_repo.finish_processing("t1", "done")

    # 这次不应被当成孤儿
    assert databases_repo.recover_orphans(max_age_seconds=600) == 0


def test_processing_recovery(fresh_db):
    """手动插一条 1 小时前的 processing,recover_orphans 应捡到并写 degradation_event。"""
    databases_repo.upsert_processing(
        task_id="t1", operation="upload", source="orphan.pdf",
        database_id="default", stage="解析中", status="processing",
    )
    # 把 updated_at 改成 1 小时前
    import sqlite3 as sq
    with sq.connect(str(fresh_db)) as c:
        c.execute(
            "UPDATE processing_state SET updated_at = datetime('now', '-1 hour') "
            "WHERE task_id = 't1'"
        )
        c.commit()

    n = databases_repo.recover_orphans(max_age_seconds=600)
    assert n == 1
    # degradation event 应已记
    events = degradation_repo.list_degradation_events(component="Processing")
    assert any("auto-recovered" in (e.get("reason") or "") for e in events)


def test_degradation_summary_by_component(fresh_db):
    degradation_repo.save_degradation_event(None, None, "x", "r1", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r2", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r3", component="Embedding")
    rows = degradation_repo.degradation_summary_by_component("1900-01-01T00:00:00")
    by_comp = {r["component"]: r["count"] for r in rows}
    assert by_comp.get("LLM") == 2
    assert by_comp.get("Embedding") == 1

# --- v1.0.2:CreateDatabaseRequest 字符集校验放在 Pydantic 层 ---


def test_create_database_request_rejects_invalid_chars():
    """v1.0.2:db_id 含非 [A-Za-z0-9_-] 字符时 Pydantic 直接 422,不再走到 sqlite 层。"""
    from pydantic import ValidationError

    from backend.api.databases import CreateDatabaseRequest

    # 合法的几种
    CreateDatabaseRequest(id="a", name="A")
    CreateDatabaseRequest(id="my_db-1", name="My DB")

    # 非法的几种:空格 / 斜杠 / 中文 / 点
    for bad in ["a b", "a/b", "中文", "a.b", "a:b", "../etc"]:
        with pytest.raises(ValidationError):
            CreateDatabaseRequest(id=bad, name="n")


def test_create_database_request_via_endpoint_returns_422():
    """HTTP 层:FastAPI 把 ValidationError 翻译成 422。"""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    r = client.post("/api/knowledge/databases", json={"id": "bad id", "name": "n"})
    assert r.status_code == 422
    # 错误体应包含字符集提示
    body = r.json()
    assert "id" in str(body)
