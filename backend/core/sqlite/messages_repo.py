"""Messages CRUD (v1.3.0 refactor — ADR-0001 Q2 B).

Hot path: one row written per chat turn; SSE soft_warning reads via
count_messages equivalents in the API layer. Functions extracted verbatim
from the former sqlite.py.

The messages table DDL lives in sessions_repo.init_schema (combined with the
sessions FK), so init_schema/migrate here are no-ops kept for repo symmetry.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import get_connection
from backend.core.sqlite.sessions_repo import touch_session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """No-op: messages DDL lives in sessions_repo.init_schema (FK to sessions)."""
    pass


def migrate(db_path: Optional[Path] = None) -> None:
    """No-op for now. Future ALTERs on messages columns go here."""
    pass


# ---------------------------------------------------------------------------
# Messages CRUD
# ---------------------------------------------------------------------------


def get_messages(
    session_id: str, limit: int = 50, offset: int = 0
) -> List[dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            SELECT id, session_id, role, content, citations_json, timestamp
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (session_id, limit, offset),
        )
        rows = cur.fetchall()
        for r in rows:
            r["citations"] = (
                json.loads(r["citations_json"]) if r.get("citations_json") else []
            )
            del r["citations_json"]
        return rows
    finally:
        conn.close()


def save_message(
    session_id: str,
    role: str,
    content: str,
    citations: Optional[List[Any]] = None,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO messages (session_id, role, content, citations_json, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(citations, ensure_ascii=False) if citations else None,
                _now_iso(),
            ),
        )
        conn.commit()
        touch_session(session_id)
        return cur.lastrowid
    finally:
        conn.close()
