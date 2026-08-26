"""SQLite refactor tests (v1.3.0 — ADR-0001 Q7 B: 5 精准测).

覆盖本次拆分引入的新行为(旧 252/270 测覆盖的是搬迁前的既有行为):
  - transaction() commit 路径
  - transaction() rollback 路径
  - delete_database(cascade=True) 跨 repo 原子性(keyword_index 失败 → databases 回滚)
  - rag.keyword_index.delete_by_db_prefix 新公开函数(独立 conn 模式)
  - init_db 3 步独立可调 + 幂等

隔离方式:同时把 connection 层与 keyword_index 层的 get_db_path 都重定向到
临时库(两者各有独立 get_db_path,见 ADR-0001 Q1 B),保证测试不污染真实 db。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.rag import keyword_index
from backend.core.sqlite import (
    databases_repo,
    init_db,
    init_db_core,
    init_db_migrate,
    init_db_post,
)
from backend.core.sqlite.connection import get_connection, transaction


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    """Per-test tmp db。connection + keyword_index 两层 get_db_path 都重定向。"""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    monkeypatch.setattr("backend.core.rag.keyword_index.get_db_path", lambda: db_file)
    init_db()
    return db_file


def test_transaction_commit_on_success(tmp_db):
    """transaction() 正常退出 → commit,写入可见。"""
    with transaction() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, title, created_at, last_active) "
            "VALUES ('sid-commit', 'T', '2026-01-01', '2026-01-01')"
        )

    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM sessions WHERE session_id = 'sid-commit'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_transaction_rollback_on_exception(tmp_db):
    """transaction() 抛异常 → rollback,写入被撤销。"""
    with pytest.raises(RuntimeError, match="boom"):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, created_at, last_active) "
                "VALUES ('sid-rollback', 'T', '2026-01-01', '2026-01-01')"
            )
            raise RuntimeError("boom")

    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM sessions WHERE session_id = 'sid-rollback'"
    ).fetchone()
    conn.close()
    assert row is None, "rollback failed — row leaked"


def test_delete_database_cascade_atomicity(tmp_db, monkeypatch):
    """delete_database(cascade=True) 内 keyword_index 清理抛异常
    → databases 行**仍在**(transaction 回滚)。

    修 v1.1.0 PR#1 已知非原子 bug:旧实现两次 commit,中途崩溃留脏状态。
    """
    conn = get_connection()
    conn.execute(
        "INSERT INTO databases (id, name, collection, created_at) "
        "VALUES ('cascade-db', 'C', 'kb_chunks_cascade-db', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO keyword_index (word, point_id, source) "
        "VALUES ('w', 'p', 'cascade-db::f.md')"
    )
    conn.commit()
    conn.close()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated keyword_index failure")

    monkeypatch.setattr(keyword_index, "delete_by_db_prefix", boom)

    with pytest.raises(RuntimeError, match="simulated keyword_index failure"):
        databases_repo.delete_database("cascade-db", cascade=True)

    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM databases WHERE id = 'cascade-db'"
    ).fetchone()
    conn.close()
    assert row is not None, "transaction() did not rollback — databases row lost"


def test_keyword_index_delete_by_db_prefix(tmp_db):
    """新公开函数 delete_by_db_prefix(独立 conn 模式)按 '<db>::' 前缀删行。"""
    conn = get_connection()
    conn.executescript(
        """
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w1', 'p1', 'test-db::foo.md');
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w2', 'p2', 'test-db::bar.md');
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w3', 'p3', 'other::baz.md');
        """
    )
    conn.commit()
    conn.close()

    deleted = keyword_index.delete_by_db_prefix("test-db")
    assert deleted == 2

    conn = get_connection()
    remaining = conn.execute(
        "SELECT source FROM keyword_index ORDER BY source"
    ).fetchall()
    conn.close()
    assert len(remaining) == 1
    assert remaining[0]["source"] == "other::baz.md"


def test_init_db_three_steps_idempotent(tmp_db):
    """init_db_core / init_db_migrate / init_db_post 可独立、可重复调用不报错,
    且 ensure_default_database 不重复插 'default' 行。"""
    for _ in range(2):
        init_db_core()
        init_db_migrate()
        init_db_post()

    conn = get_connection()
    rows = conn.execute("SELECT id FROM databases").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] == "default"
