"""SQLite connection management for KB-AI (v1.3.0 refactor — ADR-0001).

Splits the connection/transaction primitives out of the former 1064-line
``backend/core/sqlite.py`` god module. Behavior of ``get_connection`` mirrors
the prior ``sqlite.py`` implementation verbatim (same PRAGMAs, same
``_row_to_dict`` row factory) — no behavior change.

New primitives:
  - transaction():   cross-repo atomic writes (fixes delete_database cascade +
                     recover_orphans non-atomic bugs).
  - optional_conn(): "self-managed vs injected" conn mode for repo functions.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from backend.core.config import get_db_path


def _row_to_dict(cursor, row) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = _row_to_dict
    # v0.8.6(FMEA F11):dify 容器与宿主机后端共享同一 db.sqlite,并发写时
    # 默认立即抛 SQLITE_BUSY;设置 busy_timeout(ms)让 SQLite 等待锁释放。
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection wrapped in commit-on-success / rollback-on-exception.

    Used for cross-repo atomic writes (e.g. delete_database cascade +
    keyword_index cleanup). Single-repo single-table writes keep using
    get_connection() directly to minimize blast radius.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def optional_conn(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> Tuple[sqlite3.Connection, bool]:
    """Return (conn, owns_conn). owns_conn=True means caller should close.

      - Direct call (no conn arg)  → open new connection, owns it.
      - Injected call (caller passes conn)  → reuse it, do NOT close.
    """
    if conn is not None:
        return conn, False
    return get_connection(db_path), True


def commit_and_close_if_owned(conn: sqlite3.Connection, owns: bool) -> None:
    """Commit and close the connection only if we opened it."""
    try:
        conn.commit()
    finally:
        if owns:
            conn.close()
