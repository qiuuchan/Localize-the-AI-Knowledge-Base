"""Unit tests for v0.8.11(P1.4) degradation_events.component dimension."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.core import sqlite as sqlite_mod
from backend.core.sqlite import degradation_repo


@pytest.fixture()
def fresh_db(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-deg-"))
    db_file = tmp / "test.sqlite"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file
    try:
        db_file.unlink()
        os.rmdir(tmp)
    except OSError:
        pass


def test_save_degradation_event_with_component(fresh_db):
    degradation_repo.save_degradation_event(
        session_id="s1",
        query="q",
        source="x",
        reason="r",
        model=None,
        component="LLM",
    )
    rows = degradation_repo.list_degradation_events(component="LLM")
    assert len(rows) == 1
    assert rows[0]["component"] == "LLM"


def test_save_degradation_event_without_component(fresh_db):
    degradation_repo.save_degradation_event(None, None, "x", "r")
    rows = degradation_repo.list_degradation_events()
    # component may be NULL → list returns dicts where component is None
    assert rows[0]["component"] is None


def test_summary_groups_by_component(fresh_db):
    degradation_repo.save_degradation_event(None, None, "x", "r1", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r2", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r3", component="Embedding")
    degradation_repo.save_degradation_event(None, None, "x", "r4", component="Qdrant")
    degradation_repo.save_degradation_event(None, None, "x", "r5")  # no component
    rows = degradation_repo.degradation_summary_by_component("1900-01-01T00:00:00")
    by = {r["component"]: r["count"] for r in rows}
    assert by["LLM"] == 2
    assert by["Embedding"] == 1
    assert by["Qdrant"] == 1
    assert by["Unknown"] == 1


def test_list_with_since_filter(fresh_db):
    # 写 1 条老事件(直接改表)
    import sqlite3 as sq

    degradation_repo.save_degradation_event(None, None, "x", "recent", component="LLM")
    with sq.connect(str(fresh_db)) as c:
        # 插一条 2 小时前的
        c.execute(
            "INSERT INTO degradation_events(session_id, query, source, reason, "
            "model, component, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-2 hours'))",
            (None, None, "x", "old", None, "LLM"),
        )
        c.commit()

    rows = degradation_repo.list_degradation_events(since_iso="2000-01-01T00:00:00")
    assert len(rows) == 2  # both old + recent
    reasons = sorted(r["reason"] for r in rows)
    assert reasons == ["old", "recent"]

    # 1 小时前为下限 → 只剩 recent
    rows = degradation_repo.list_degradation_events(since_iso="1970-01-01T00:00:00")
    assert any(r["reason"] == "recent" for r in rows)


def test_init_db_idempotent_component_column(fresh_db):
    """Re-run init_db on already-migrated db → no error."""
    sqlite_mod.init_db()  # should be no-op
    sqlite_mod.init_db()
    rows = degradation_repo.list_degradation_events(component="LLM")
    assert rows == []  # column exists, table empty
