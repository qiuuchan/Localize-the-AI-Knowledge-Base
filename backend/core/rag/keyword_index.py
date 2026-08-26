"""SQLite keyword_index for Hybrid Search.

Mirrors scripts/lib/Invoke-SqliteExec.ps1 + scripts/embed-and-ingest.ps1
keyword_index writes + scripts/chat.ps1 keyword search.

Schema:
    CREATE TABLE IF NOT EXISTS keyword_index (
        word      TEXT NOT NULL,
        point_id  TEXT NOT NULL,
        source    TEXT,
        text      TEXT,
        PRIMARY KEY (word, point_id)
    );
    CREATE INDEX IF NOT EXISTS idx_keyword_word ON keyword_index(word);

Operations:
  - init_table: idempotent DDL.
  - write_rows: bulk insert (word, point_id, source, text).
  - delete_by_source: remove all rows for a given source.
  - search_by_tokens: SELECT WHERE word IN (...) GROUP BY point_id ORDER BY COUNT.
  - count_by_source: GROUP BY source aggregate (used by list_documents).
  - list_sources: distinct sources.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.core.config import get_db_path

_TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS keyword_index (
        word      TEXT NOT NULL,
        point_id  TEXT NOT NULL,
        source    TEXT,
        text      TEXT,
        PRIMARY KEY (word, point_id)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_keyword_word ON keyword_index(word);",
]


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.row_factory = sqlite3.Row
    # v0.8.6(FMEA F11):与 sqlite.py 一致,并发写时等待锁而非立即 SQLITE_BUSY
    c.execute("PRAGMA busy_timeout = 5000")
    return c


def init_table(db_path: Optional[Path] = None) -> None:
    conn = _conn(db_path)
    try:
        for stmt in _TABLE_DDL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def write_rows(
    rows: Sequence[tuple],
    db_path: Optional[Path] = None,
) -> int:
    """Bulk insert rows. Each row = (word, point_id, source, text).

    Returns number of rows written (after INSERT OR REPLACE).
    Uses executemany; missing (word, point_id) pairs are replaced.
    """
    if not rows:
        return 0
    conn = _conn(db_path)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO keyword_index (word, point_id, source, text) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def delete_by_source(source: str, db_path: Optional[Path] = None) -> int:
    """Delete all keyword_index rows for a given source. Returns rowcount."""
    conn = _conn(db_path)
    try:
        cur = conn.execute("DELETE FROM keyword_index WHERE source = ?", (source,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def search_by_tokens(
    tokens: Sequence[str],
    *,
    limit: int = 20,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return {point_id, source, text, score} per point, ordered by score DESC.

    Score is the count of distinct tokens from the query that hit the point.
    Mirrors chat.ps1:493-500.
    """
    if not tokens:
        return []
    placeholders = ",".join(["?"] * len(tokens))
    sql = (
        "SELECT point_id, source, text, COUNT(*) AS score "
        "FROM keyword_index "
        f"WHERE word IN ({placeholders}) "
        "GROUP BY point_id "
        "ORDER BY score DESC LIMIT ?"
    )
    conn = _conn(db_path)
    try:
        cur = conn.execute(sql, [*tokens, limit])
        rows = cur.fetchall()
        return [
            {
                "point_id": r["point_id"],
                "source": r["source"],
                "text": r["text"],
                "score": r["score"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def count_by_source(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return list of {source, chunk_count} aggregated by source."""
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT source, COUNT(*) AS chunk_count "
            "FROM keyword_index GROUP BY source ORDER BY source"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_sources(db_path: Optional[Path] = None) -> List[str]:
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "SELECT DISTINCT source FROM keyword_index ORDER BY source"
        )
        return [r["source"] for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# v1.3.0 refactor — ADR-0001 Q1 B: keyword_index schema + cross-repo helpers
# 本模块自管 conn(不依赖 core.sqlite),避免循环依赖。
# ---------------------------------------------------------------------------


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create keyword_index table + index.

    v1.3.0(ADR-0001 Q1 B):keyword_index 的 schema 从 sqlite.init_db 移到本模块,
    与 CRUD 同包。orchestrator(sqlite.init_db_core)显式 import 调用之。
    行为等同旧 init_table(相同 DDL)。
    """
    init_table(db_path)


def delete_by_db_prefix(
    db_id: str, *, conn: Optional[sqlite3.Connection] = None
) -> int:
    """删除某 db 下所有 keyword_index 行(source LIKE '<db_id>::%')。

    由 databases_repo.delete_database(cascade=True) 在 connection.transaction()
    内以共享 conn 调用,保证跨表原子(修 v1.1.0 PR#1 非原子 bug)。
    conn=None 时自开 conn 并 commit(独立调用场景)。注入 conn 时不 commit
    (由外层 transaction() 控制提交/回滚)。
    """
    like = f"{db_id}::%"
    if conn is None:
        own = _conn()
        try:
            cur = own.execute(
                "DELETE FROM keyword_index WHERE source LIKE ?", (like,)
            )
            own.commit()
            return cur.rowcount
        finally:
            own.close()
    cur = conn.execute("DELETE FROM keyword_index WHERE source LIKE ?", (like,))
    return cur.rowcount
