"""Tags + doc_tags CRUD (v1.1.0 PR#4; v1.3.0 refactor — ADR-0001).

自由标签:tags + doc_tags 表 + CASCADE FK。Functions extracted verbatim from
the former sqlite.py (incl db_path params and create_tag IntegrityError→ValueError).
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
    """Create tags + doc_tags tables. Mirrors sqlite.py init_db verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            -- v1.1.0 PR#4:自由标签 — 独立于 Database 的多对多标签
            CREATE TABLE IF NOT EXISTS tags (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                database_id TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                color       TEXT    NOT NULL DEFAULT '#FF540E',
                created_at  TEXT    NOT NULL,
                UNIQUE(database_id, name)
            );

            CREATE TABLE IF NOT EXISTS doc_tags (
                source      TEXT    NOT NULL,
                tag_id      INTEGER NOT NULL,
                created_at  TEXT    NOT NULL,
                PRIMARY KEY (source, tag_id),
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_doc_tags_tag ON doc_tags(tag_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """No current ALTERs. Future go here."""
    pass


# ---------------------------------------------------------------------------
# Tag CRUD
# ---------------------------------------------------------------------------


def create_tag(
    database_id: str,
    name: str,
    color: str = "#FF540E",
    db_path: Optional[Path] = None,
) -> int:
    """Create a tag. Returns tag id. Raises ValueError on duplicate name within db."""
    if not database_id or not name:
        raise ValueError("database_id and name required")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO tags (database_id, name, color, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (database_id, name, color, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise ValueError(
            f"tag '{name}' already exists in database '{database_id}'"
        ) from exc
    finally:
        conn.close()


def list_tags(database_id: str, db_path: Optional[Path] = None) -> List[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM tags WHERE database_id = ? ORDER BY name",
            (database_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_tag(tag_id: int, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,))
        return cur.fetchone()
    finally:
        conn.close()


def update_tag(
    tag_id: int,
    name: Optional[str] = None,
    color: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    conn = get_connection(db_path)
    try:
        fields = []
        params: List[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if color is not None:
            fields.append("color = ?")
            params.append(color)
        if fields:
            params.append(tag_id)
            conn.execute(
                f"UPDATE tags SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
    finally:
        conn.close()


def delete_tag(tag_id: int, db_path: Optional[Path] = None) -> None:
    """Delete tag (CASCADE removes doc_tags rows)."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# doc_tags CRUD
# ---------------------------------------------------------------------------


def assign_tags_to_doc(
    source: str, tag_ids: List[int], db_path: Optional[Path] = None
) -> int:
    """批量打标。Returns number of rows inserted (skips existing)."""
    if not tag_ids:
        return 0
    conn = get_connection(db_path)
    try:
        rows = [(source, tid, _now_iso()) for tid in tag_ids]
        cur = conn.executemany(
            """
            INSERT OR IGNORE INTO doc_tags (source, tag_id, created_at)
            VALUES (?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def unassign_tag_from_doc(
    source: str, tag_id: int, db_path: Optional[Path] = None
) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM doc_tags WHERE source = ? AND tag_id = ?",
            (source, tag_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_tags_for_doc(source: str, db_path: Optional[Path] = None) -> List[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT t.* FROM tags t
            JOIN doc_tags dt ON dt.tag_id = t.id
            WHERE dt.source = ?
            ORDER BY t.name
            """,
            (source,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def list_documents_by_tags(
    database_id: str,
    tag_ids: List[int],
    db_path: Optional[Path] = None,
) -> List[dict[str, Any]]:
    """列出指定 db 下同时拥有所有 tag_ids 的文档 sources。

    Returns:
        [{"source": str, "tag_count": int}, ...]
    """
    if not tag_ids:
        return []
    conn = get_connection(db_path)
    try:
        # 通过 source 前缀推断 db
        placeholder = ",".join("?" * len(tag_ids))
        cur = conn.execute(
            f"""
            SELECT dt.source, COUNT(DISTINCT dt.tag_id) AS tag_count
            FROM doc_tags dt
            WHERE dt.tag_id IN ({placeholder})
              AND dt.source LIKE ?
            GROUP BY dt.source
            HAVING tag_count = ?
            ORDER BY dt.source
            """,
            (*tag_ids, f"{database_id}::%", len(tag_ids)),
        )
        return cur.fetchall()
    finally:
        conn.close()
