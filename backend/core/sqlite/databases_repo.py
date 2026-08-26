"""Databases + processing_state CRUD (v1.3.0 refactor — ADR-0001 Q3).

Functions extracted verbatim from the former sqlite.py. The two cross-table
writes now use connection.transaction() for atomicity:
  - delete_database(cascade=True): databases row + keyword_index rows.
  - recover_orphans(): processing_state UPDATE + degradation_events INSERT.

bulk_assign_documents_to_database keeps its original structure verbatim: the
keyword_index rewrite is committed first, then Qdrant payloads are synced
best-effort (Qdrant failure must NOT roll back the committed SQLite write).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.bulk_assign import _rewrite_qdrant_payloads
from backend.core.rag import keyword_index
from backend.core.sqlite.connection import get_connection, transaction
from backend.core.sqlite.degradation_repo import save_degradation_event

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# v0.8.11(P1.1) Databases
# ---------------------------------------------------------------------------
# 主分类的载体。default 行的 collection 是 'kb_ai_chunks',保持向后兼容;
# 新建数据库使用 'kb_chunks_<db_id>' 命名(Qdrant collection 隔离)。

DEFAULT_DATABASE_ID = "default"
LEGACY_DEFAULT_COLLECTION = "kb_ai_chunks"


def _collection_for_database(db_id: str) -> str:
    """Compute Qdrant collection name for a given database id.

    'default' → 'kb_ai_chunks'(向后兼容,已有数据不丢);
    其他 → 'kb_chunks_<db_id>'。
    """
    if db_id == DEFAULT_DATABASE_ID:
        return LEGACY_DEFAULT_COLLECTION
    return f"kb_chunks_{db_id}"


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create databases + processing_state tables. Mirrors sqlite.py verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            -- v0.8.11(P1.1):Database 抽象 — 主分类的载体
            -- 默认行 'default' 指向现有 kb_ai_chunks collection,确保向后兼容;
            -- 新建 db 自动使用 kb_chunks_<db_id> 命名空间。
            CREATE TABLE IF NOT EXISTS databases (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                description   TEXT,
                collection    TEXT NOT NULL,        -- 指向 Qdrant collection
                embed_model   TEXT NOT NULL DEFAULT 'text-embedding-v3',
                chunk_size    INTEGER NOT NULL DEFAULT 500,
                chunk_overlap INTEGER NOT NULL DEFAULT 80,
                created_at    TEXT NOT NULL
            );

            -- v0.8.11(P1.2):持久化上传/重嵌入任务状态,支持启动自检
            -- 取代 in-memory _TASKS dict,治 FMEA F07(进程崩状态丢)
            CREATE TABLE IF NOT EXISTS processing_state (
                task_id        TEXT PRIMARY KEY,
                operation      TEXT NOT NULL,        -- 'upload' | 'reembed'
                source         TEXT NOT NULL,
                database_id    TEXT NOT NULL DEFAULT 'default',
                stage          TEXT NOT NULL,
                status         TEXT NOT NULL,        -- 'processing' | 'done' | 'failed'
                started_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                finished_at    TEXT,
                error          TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_state(status, updated_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """No current ALTERs on databases/processing_state. Future go here."""
    pass


def list_databases() -> List[dict[str, Any]]:
    """列出所有 database,默认行 + 用户自建行,各带 document_count。

    v1.0.2 修订:去掉 v0.8.11 的冗余 `total_documents` 相关子查询(在原作者注释里
    就已经承认"太啰嗦且不正确"),改为单次 GROUP BY 后 Python 端按 source 前缀分桶。
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, name, description, collection,
                   embed_model, chunk_size, chunk_overlap, created_at
            FROM databases
            ORDER BY (id = ?) DESC, created_at ASC
            """,
            (DEFAULT_DATABASE_ID,),
        ).fetchall()
        # 一次 GROUP BY 统计 keyword_index 全部 source 的 chunk 数,Python 端按
        # source 前缀(默认 'default';有 '::' 取 '::' 前)分桶到 db
        counts = conn.execute(
            """
            SELECT source, COUNT(DISTINCT point_id) AS chunk_count
            FROM keyword_index
            GROUP BY source
            """
        ).fetchall()
        per_db: dict[str, int] = {}
        for c in counts:
            src = c["source"]
            if "::" in src:
                db, _ = src.split("::", 1)
            else:
                db = DEFAULT_DATABASE_ID
            per_db[db] = per_db.get(db, 0) + 1
        out: List[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["document_count"] = per_db.get(d["id"], 0)
            out.append(d)
        return out
    finally:
        conn.close()


def get_database(db_id: str) -> Optional[dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM databases WHERE id = ?", (db_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_database(
    db_id: str,
    name: str,
    description: str = "",
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    embed_model: str = "text-embedding-v3",
) -> str:
    """Create a new database. Returns the db_id.

    Raises ValueError if db_id exists or invalid.
    """
    if not db_id or not name:
        raise ValueError("db_id and name are required")
    if not db_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("db_id 只能包含字母、数字、下划线、连字符")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM databases WHERE id = ?", (db_id,)
        ).fetchone()
        if existing:
            raise ValueError(f"database '{db_id}' 已存在")
        collection = _collection_for_database(db_id)
        conn.execute(
            """
            INSERT INTO databases
                (id, name, description, collection, embed_model,
                 chunk_size, chunk_overlap, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                name,
                description,
                collection,
                embed_model,
                chunk_size,
                chunk_overlap,
                _now_iso(),
            ),
        )
        conn.commit()
        return db_id
    finally:
        conn.close()


def update_database(
    db_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> None:
    """Update mutable fields. Raises ValueError if db_id missing."""
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM databases WHERE id = ?", (db_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"database '{db_id}' 不存在")
        fields = []
        params: list[Any] = []
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if chunk_size is not None:
            fields.append("chunk_size = ?")
            params.append(chunk_size)
        if chunk_overlap is not None:
            fields.append("chunk_overlap = ?")
            params.append(chunk_overlap)
        if fields:
            params.append(db_id)
            conn.execute(
                f"UPDATE databases SET {', '.join(fields)} WHERE id = ?",
                params,
            )
            conn.commit()
    finally:
        conn.close()


def delete_database(db_id: str, cascade: bool = False) -> int:
    """Delete a database record.

    cascade=False(默认):仅删 metadata 记录,**不动** Qdrant collection / keyword_index,
    数据保留供后续 assign 到其他 db。
    cascade=True:原子删 databases 行 + keyword_index 中以该 db_id 前缀的 source 行
    (v1.3.0 ADR-0001:走 transaction() 共享 conn,修 v1.1.0 PR#1 已知非原子 bug —
    旧实现两次 commit,中途崩溃留脏状态)。

    Returns affected metadata row count(0 或 1)。
    """
    if db_id == DEFAULT_DATABASE_ID:
        raise ValueError("'default' 数据库不可删除")

    if not cascade:
        conn = get_connection()
        try:
            cur = conn.execute("DELETE FROM databases WHERE id = ?", (db_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    # cascade 路径:跨 repo 原子写(databases + keyword_index)
    with transaction() as conn:
        deleted = conn.execute(
            "DELETE FROM databases WHERE id = ?", (db_id,)
        ).rowcount
        if deleted > 0:
            keyword_index.delete_by_db_prefix(db_id, conn=conn)
        return deleted


def ensure_default_database(db_path: Optional[Path] = None) -> None:
    """v0.8.11(P1.1):init_db 末尾调用,确保 'default' 行存在。

    保证向后兼容:旧 db.sqlite 升级后,所有存量 keyword_index.source 仍归 'default'。

    v1.3.0(ADR-0001 §5):加可选 db_path,让 init_db(db_path) 三步全部作用于同一
    db(db_path=None 时行为与旧版完全一致,走全局 get_db_path)。
    """
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT 1 FROM databases WHERE id = ?", (DEFAULT_DATABASE_ID,)
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT OR IGNORE INTO databases
                    (id, name, description, collection, embed_model,
                     chunk_size, chunk_overlap, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_DATABASE_ID,
                    "默认分类",
                    "v0.8.10 升级前的存量文档(无显式归属)",
                    LEGACY_DEFAULT_COLLECTION,
                    "text-embedding-v3",
                    500,
                    80,
                    _now_iso(),
                ),
            )
            conn.commit()
    finally:
        conn.close()


def count_documents_by_database(db_id: str) -> int:
    """Count distinct sources belonging to a database.

    Convention: source 字符串 '<db_id>::<filename>' → 该 db;
    没有 '::' 前缀 → 'default'。
    """
    if db_id == DEFAULT_DATABASE_ID:
        sql = "SELECT COUNT(DISTINCT source) FROM keyword_index WHERE source NOT LIKE '%::%'"
    else:
        sql = "SELECT COUNT(DISTINCT source) FROM keyword_index WHERE source LIKE ?"
    conn = get_connection()
    try:
        if db_id == DEFAULT_DATABASE_ID:
            row = conn.execute(sql).fetchone()
        else:
            row = conn.execute(sql, (f"{db_id}::%",)).fetchone()
        # fetchone returns dict due to row_factory; tolerate tuple too
        if row is None:
            return 0
        if isinstance(row, dict):
            for v in row.values():
                return int(v or 0)
            return 0
        return int(row[0] or 0)
    finally:
        conn.close()


def bulk_assign_documents_to_database(
    db_id: str, sources: List[str]
) -> int:
    """Rewrite keyword_index.source + Qdrant payload.source from old to new db prefix.

    输入 sources 兼容两种格式(向后兼容):
      - raw filename (e.g., 'cookbook.pdf') → 旧 db = DEFAULT_DATABASE_ID('default')
      - pre-prefixed (e.g., 'default::cookbook.pdf') → 旧 db 从前缀解析

    Idempotent:旧 db == 新 db → skip(source 已在目标库)。

    Returns number of source strings actually rewritten(按 keyword_index 影响行计,
    每个 distinct source 最多 +1)。Qdrant payload rewrite 失败不阻断主流程,
    仅写 degradation_events(component='Vector')。
    """
    if not sources:
        return 0
    db = get_database(db_id)
    if not db:
        raise ValueError(f"database '{db_id}' 不存在")
    collection = db.get("collection")

    affected = 0
    # 记录成功重写的 (old_qdrant_source, new_qdrant_source, original_input),
    # 事务提交后再走 Qdrant 同步(Qdrant 失败不应回滚 SQLite 已提交的事)
    qdrant_jobs: List[tuple[str, str, str]] = []
    conn = get_connection()
    try:
        for src in sources:
            if "::" in src:
                old_db_id, _, filename = src.partition("::")
            else:
                old_db_id, filename = DEFAULT_DATABASE_ID, src
            if old_db_id == db_id:
                # 已在目标库 — idempotent skip
                continue
            new_src = f"{db_id}::{filename}"
            # keyword_index.source / Qdrant payload.source 里的实际值取决于
            # 入参格式:pre-prefixed 输入 → 直接当 FROM 值;raw 输入 → 当 legacy
            # raw filename FROM(假设旧 parser 直接写 raw,无 default:: 前缀)
            old_src_full = src
            cur = conn.execute(
                "UPDATE keyword_index SET source = ? WHERE source = ?",
                (new_src, old_src_full),
            )
            if cur.rowcount > 0:
                affected += 1
                qdrant_jobs.append((old_src_full, new_src, src))
        conn.commit()
    finally:
        conn.close()

    # v1.1.0 PR#1:同步重写 Qdrant payload.source,关闭 known-limitations §2 #11
    # Qdrant 不可达 → degradation_events(component='Vector'),不阻断主流程
    if collection and qdrant_jobs:
        for old_src_full, new_src, original_input in qdrant_jobs:
            try:
                result = _rewrite_qdrant_payloads(
                    old_source=old_src_full,
                    new_source=new_src,
                    collection=collection,
                )
                if result["warnings"]:
                    save_degradation_event(
                        session_id=None,
                        query=None,
                        source=original_input,
                        reason=(
                            f"Qdrant payload rewrite partial: {result['warnings']}"
                        ),
                        model=None,
                        component="Vector",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Qdrant payload rewrite failed db_id=%s source=%s: %s",
                    db_id,
                    original_input,
                    exc,
                )
                save_degradation_event(
                    session_id=None,
                    query=None,
                    source=original_input,
                    reason=f"Qdrant payload rewrite failed: {exc}",
                    model=None,
                    component="Vector",
                )

    return affected


# ---------------------------------------------------------------------------
# v0.8.11(P1.2) Processing state (取代 _TASKS dict,治 FMEA F07)
# ---------------------------------------------------------------------------


def upsert_processing(
    task_id: str,
    operation: str,
    source: str,
    database_id: str,
    stage: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """插入或更新一个处理任务状态行。

    status ∈ {'processing', 'done', 'failed'}。
    """
    conn = get_connection()
    try:
        now = _now_iso()
        existing = conn.execute(
            "SELECT started_at FROM processing_state WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE processing_state
                SET stage = ?, status = ?, error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (stage, status, error, now, task_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO processing_state
                    (task_id, operation, source, database_id, stage, status,
                     started_at, updated_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, operation, source, database_id, stage, status,
                 now, now, error),
            )
        conn.commit()
    finally:
        conn.close()


def finish_processing(
    task_id: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """Mark a task done/failed; set finished_at."""
    if status not in ("done", "failed"):
        raise ValueError("finish_processing requires status='done' or 'failed'")
    conn = get_connection()
    try:
        now = _now_iso()
        conn.execute(
            """
            UPDATE processing_state
            SET status = ?, error = ?, finished_at = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (status, error, now, now, task_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_orphan_processing(max_age_seconds: int = 600) -> List[dict[str, Any]]:
    """Return processing rows whose updated_at is older than max_age_seconds ago.

    Used at startup to detect tasks that died mid-flight.
    """
    conn = get_connection()
    try:
        # SQLite doesn't have INTERVAL — use strftime delta.
        cur = conn.execute(
            """
            SELECT * FROM processing_state
            WHERE status = 'processing'
              AND updated_at < datetime('now', ?)
            ORDER BY updated_at ASC
            """,
            (f"-{max_age_seconds} seconds",),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def recover_orphans(max_age_seconds: int = 600) -> int:
    """Mark orphaned processing rows as failed + write a degradation_event.

    v1.3.0 ADR-0001:UPDATE processing_state + INSERT degradation_events 现在包在
    connection.transaction() 里原子提交(标记 failed 必伴随 degradation 记录)。

    Returns number of rows recovered. Called from backend/api/boot.py at startup.
    """
    orphans = list_orphan_processing(max_age_seconds)
    if not orphans:
        return 0
    now = _now_iso()
    with transaction() as conn:
        for o in orphans:
            conn.execute(
                """
                UPDATE processing_state
                SET status = 'failed',
                    error = COALESCE(error, '') ||
                            ' [auto-recovered: process not found in queue]',
                    finished_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (now, now, o["task_id"]),
            )
            conn.execute(
                """
                INSERT INTO degradation_events
                    (session_id, query, source, reason, model, component, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    None,
                    "processing_recovery",
                    f"orphan task {o['task_id']} auto-recovered "
                    f"(operation={o['operation']}, source={o['source']})",
                    None,
                    "Processing",
                    now,
                ),
            )
    return len(orphans)
