"""Degradation events CRUD (v1.3.0 refactor — ADR-0001).

Functions extracted verbatim from the former sqlite.py. Owns the
degradation_events table incl the v0.8.11 P1.4 component column ALTER.
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
    """Create degradation_events table. Mirrors sqlite.py init_db verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            CREATE TABLE IF NOT EXISTS degradation_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT,
                query       TEXT,
                source      TEXT,
                reason      TEXT,
                model       TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_degradation_session ON degradation_events(session_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """v0.8.11(P1.4):degradation_events 加 component 列。

    SQLite ALTER TABLE ADD COLUMN 非幂等,需包 try/except 捕 duplicate column。
    """
    conn = get_connection(db_path)
    try:
        try:
            conn.execute(
                "ALTER TABLE degradation_events ADD COLUMN component TEXT"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_degradation_component "
                "ON degradation_events(component, created_at)"
            )
        except sqlite3.OperationalError as exc:
            # duplicate column name → 已迁移过,跳过
            if "duplicate column" not in str(exc).lower():
                raise
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Degradation events CRUD
# ---------------------------------------------------------------------------


def save_degradation_event(
    session_id: Optional[str],
    query: Optional[str],
    source: str,
    reason: str,
    model: Optional[str] = None,
    component: Optional[str] = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO degradation_events
                (session_id, query, source, reason, model, component, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, query, source, reason, model, component, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_degradation_events(
    session_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    since_iso: Optional[str] = None,
    component: Optional[str] = None,
) -> List[dict[str, Any]]:
    """List degradation events with optional filtering.

    v0.8.11(P1.4):加 since_iso / component 过滤,供 Dashboard 聚合 24h 事件。
    """
    conn = get_connection()
    try:
        clauses = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if since_iso:
            clauses.append("created_at >= ?")
            params.append(since_iso)
        if component:
            clauses.append("component = ?")
            params.append(component)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        cur = conn.execute(
            f"""
            SELECT * FROM degradation_events
            {where}
            ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            params,
        )
        return cur.fetchall()
    finally:
        conn.close()


def degradation_summary_by_component(since_iso: str) -> List[dict[str, Any]]:
    """Aggregate degradation event counts per component since `since_iso`.

    Used by Dashboard P1.6. Returns [{component, count}].
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT COALESCE(component, 'Unknown') AS component, COUNT(*) AS count
            FROM degradation_events
            WHERE created_at >= ?
            GROUP BY component
            ORDER BY count DESC
            """,
            (since_iso,),
        )
        return cur.fetchall()
    finally:
        conn.close()
