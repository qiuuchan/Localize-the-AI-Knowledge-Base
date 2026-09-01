"""Sessions CRUD (v1.3.0 refactor — ADR-0001 Q2 B).

Cold path: only touched on PATCH/GET session. Messages hot path lives in
messages_repo. Functions extracted verbatim from the former sqlite.py.

sessions_repo owns the sessions + messages DDL (combined because messages has
an FK to sessions); messages_repo.init_schema is a no-op for symmetry.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create sessions + messages tables. Mirrors sqlite.py init_db verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                title        TEXT,
                created_at   TEXT NOT NULL,
                last_active  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                citations_json  TEXT,
                timestamp       TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """v1.1.0 PR#2: sessions 加 history_limit(REQ-6 50 轮软上限)。

    SQLite ALTER TABLE ADD COLUMN 非幂等,需包 try/except 捕 duplicate column。

    T10(v2.2):sessions 加 summary(TEXT,nullable) — 上下文工程滚动摘要落库,
    参与后续轮次上下文(ADR-0003)。
    """
    conn = get_connection(db_path)
    try:
        try:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN history_limit INTEGER NOT NULL DEFAULT 50"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        try:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN summary TEXT"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sessions CRUD
# ---------------------------------------------------------------------------


def list_sessions(limit: int = 50, offset: int = 0) -> List[dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_session(
    session_id: str, db_path: Optional[Path] = None
) -> Optional[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        return cur.fetchone()
    finally:
        conn.close()


def create_session(
    title: Optional[str] = None,
    session_id: Optional[str] = None,
    history_limit: int = 50,
    db_path: Optional[Path] = None,
) -> str:
    if session_id is None:
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    now = _now_iso()
    # Fallback title
    if not title:
        title = "新会话"
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_id, title, created_at, last_active, history_limit)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, title, now, now, history_limit),
        )
        conn.commit()
    finally:
        conn.close()
    return session_id


def touch_session(session_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (_now_iso(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T10(v2.2):滚动摘要落库(ADR-0003)
# ---------------------------------------------------------------------------


def get_session_summary(
    session_id: str, db_path: Optional[Path] = None
) -> Optional[str]:
    """读会话摘要;会话不存在 / 未生成过摘要返回 None。"""
    s = get_session(session_id, db_path=db_path)
    if s is None:
        return None
    return s.get("summary") or None


def set_session_summary(
    session_id: str, summary: str, db_path: Optional[Path] = None
) -> None:
    """写会话摘要(空串也写,幂等;失败由调用方 try/except 兜底)。"""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET summary = ? WHERE session_id = ?",
            (summary, session_id),
        )
        conn.commit()
    finally:
        conn.close()
