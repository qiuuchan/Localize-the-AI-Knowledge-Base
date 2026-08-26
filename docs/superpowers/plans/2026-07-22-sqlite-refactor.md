# PR #1+#2 · sqlite-refactor · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**配套决策**:`docs/adr/0001-sqlite-repo-split.md`(8 轮 grilling 决策)
**配套 spec**:`docs/superpowers/specs/2026-07-21-v1.3-ops-hardening-design.md`(v1.3.0 运维加固)
**驱动版本**:KB-AI **v1.3.0**

---

## Goal

把 `backend/core/sqlite.py`(1064 行 god 模块)拆为 `backend/core/sqlite/` 包(5 个独立 repo + connection helper + 3 步 orchestrator);`keyword_index` 表 schema 归 `core/rag/keyword_index.py`;跨表操作用 `transaction()` 共享 conn 修原子性 bug;加 5 个精准测覆盖新行为;最后清掉 re-export shim 把 12 个调用方迁到直接 repo import。

**双 PR 边界**:
- **PR #1**:结构 + transaction + 3 步 + 新测 + 临时 re-export shim(行为不变)
- **PR #2**:调用方迁移到 `from backend.core.sqlite.X_repo import X` + 删 shim

---

## Architecture(改后)

```
backend/core/
├── rag/
│   └── keyword_index.py    # +init_schema(db_path) +delete_by_db_prefix(db_id, *, conn=None) +rewrite_source_prefix(old_db, new_db, sources, *, conn=None)
└── sqlite/                  # 新包
    ├── __init__.py          # orchestrator: init_db + init_db_core/migrate/post + 临时 re-export (PR #1 末)
    ├── connection.py        # get_connection + transaction() + optional_conn() + commit_and_close_if_owned()
    ├── sessions_repo.py     # 4 个函数:list/get/create/touch
    ├── messages_repo.py     # 3 个函数:get/count/save
    ├── degradation_repo.py  # 3 个函数:save/list/summary
    ├── databases_repo.py    # 11 个函数(含 processing_state + recover_orphans 用 transaction())
    └── tags_repo.py         # 10 个函数(CRUD + 多对多)

backend/api/                 # PR #2 改 12 个调用点
└── chat.py / sessions.py / databases.py / tags.py / knowledge.py / boot.py / dashboard.py

tests/unit/
├── test_limit_guard.py      # PR #2 改 1 个 import
├── test_tags_api.py         # PR #2 改 1 个 import
└── test_sqlite_refactor.py  # 新建,~80 行,5 个测
```

---

## Tech Stack

Python 3.12 · FastAPI · SQLite (stdlib `sqlite3`) · pytest

## Global Constraints

- **不修改**:`.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- **version bump**:`version` 文件不动(内部重构);v1.3.0 spec §1.2 的 version 1.2.0 → 1.3.0 由 release commit 处理
- **依赖**:不引入新第三方包;`sqlite3` stdlib + `contextlib.contextmanager` 已有
- **行为不变**:PR #1 跑完,既有 252 pytest + run-checks.ps1 4/4 必须全绿;零 SQL 行为变化
- **测试基线**:PR #1 末 pytest 252 → **257**(+5 新测);PR #2 末保持 257
- **commit 格式**:沿用 `<type>(<scope>): <subject>`,type ∈ {feat, refactor, chore, test}

---

## File Structure

### PR #1(结构 + transaction + 新测)

| 文件 | 类型 | 责任 |
|---|---|---|
| `backend/core/sqlite/connection.py` | 新建 | `get_connection` + `transaction()` context manager + `optional_conn()` + `commit_and_close_if_owned()` |
| `backend/core/sqlite/sessions_repo.py` | 新建 | 4 个函数(`list_sessions` / `get_session` / `create_session` / `touch_session`) + `init_schema` + `migrate` |
| `backend/core/sqlite/messages_repo.py` | 新建 | 3 个函数 + `init_schema` + `migrate` |
| `backend/core/sqlite/degradation_repo.py` | 新建 | 3 个函数 + `init_schema` + `migrate`(现有 ALTER 在这里) |
| `backend/core/sqlite/databases_repo.py` | 新建 | databases + processing_state 表组的所有函数 + `init_schema` + `migrate`;`delete_database(cascade=True)` 用 `transaction()`;`recover_orphans` 用 `transaction()` |
| `backend/core/sqlite/tags_repo.py` | 新建 | tags + doc_tags 表组的所有函数 + `init_schema` + `migrate` |
| `backend/core/sqlite/__init__.py` | 新建 | orchestrator(`init_db` 3 步)+ 临时 re-export 全部 5 个 repo 的公开函数(保持 12 调用方零改) |
| `backend/core/sqlite.py` | 删除 | 内容已搬到 5 个 repo + connection.py + __init__.py |
| `backend/core/rag/keyword_index.py` | 修改 | + `init_schema(db_path)` 迁移 CREATE TABLE;+ `delete_by_db_prefix(db_id, *, conn=None)` 新公开函数;+ `rewrite_source_prefix(old_db, new_db, sources, *, conn=None)` 新公开函数(给 `bulk_assign_documents_to_database` 用) |
| `tests/unit/test_sqlite_refactor.py` | 新建 | 5 个新测(见 Task 1.8) |

### PR #2(调用方迁移 + 删 shim)

| 文件 | 类型 | 责任 |
|---|---|---|
| `backend/api/chat.py` | 修改 | `from backend.core.sqlite import (count_messages, get_messages, save_degradation_event, save_message, touch_session)` → 拆成 4 个 repo 的具体 import |
| `backend/api/sessions.py` | 修改 | 同样拆分 |
| `backend/api/databases.py` | 修改 | 同样拆分 |
| `backend/api/tags.py` | 修改 | 同样拆分 |
| `backend/api/knowledge.py` | 修改 | 同样拆分 |
| `backend/api/boot.py` | 修改 | `init_db` 仍从 `backend.core.sqlite` import(re-export 删除后改为从 `backend.core.sqlite.__init__` import,或保持 `from backend.core.sqlite import init_db`) |
| `backend/api/dashboard.py` | 修改 | 同样拆分 |
| `tests/unit/test_limit_guard.py` | 修改 | 1 个 import site |
| `tests/unit/test_tags_api.py` | 修改 | 1 个 import site |
| `backend/core/sqlite/__init__.py` | 修改 | 删 re-export 块(保留 orchestrator) |
| `CHANGELOG.md` | 修改 | v1.3.0 段加 PR #1 + PR #2 子段 |

---

## PR #1 Tasks

### Task 1.1: 抽出 `connection.py` — `transaction()` + `optional_conn()` helpers

**Files:**
- 新建: `backend/core/sqlite/connection.py`

- [ ] **Step 1: 创建包目录 + connection.py 雏形**

```bash
mkdir -p E:/backend/core/sqlite
```

新建文件 `E:/backend/core/sqlite/connection.py`:

```python
"""SQLite connection management for KB-AI (v1.3.0 refactor — ADR-0001)。

对比 v0.8.11 P1.3 借鉴 Yuxi-Know atomic_io.py 的 idempotent 写模式,
本模块是 DB 层的对偶:
  - get_connection:     复用 sqlite.py:25 的 PRAGMA 设置 + busy_timeout
  - transaction():      跨 repo 原子写(修 delete_database cascade 非原子 bug)
  - optional_conn():    单 repo 函数"自管 vs 注入"的统一模式
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, Tuple

from backend.core.config import get_db_path


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a SQLite connection with the KB-AI canonical PRAGMAs.

    Mirrors the prior sqlite.py:25-35 implementation verbatim (no behavior
    change). Callers are responsible for commit()/close().
    """
    if db_path is None:
        db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = _row_to_dict
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_dict(cursor, row) -> dict:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Yield a connection wrapped in BEGIN/COMMIT (ROLLBACK on exception).

    Used for cross-repo atomic writes (e.g. delete_database cascade +
    keyword_index cleanup). Single-repo writes keep using get_connection()
    directly to minimize blast radius.
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


def optional_conn(conn: Optional[sqlite3.Connection]) -> Tuple[sqlite3.Connection, bool]:
    """Return (conn, owns_conn). owns_conn=True means caller should close.

    Used by repo functions to support two call modes:
      - Direct call (no conn arg)  → open new connection, owns it
      - Injected call (caller passes conn)  → reuse it, do NOT close
    """
    if conn is not None:
        return conn, False
    return get_connection(), True


def commit_and_close_if_owned(conn: sqlite3.Connection, owns: bool) -> None:
    """Commit the transaction and close the connection if we own it.

    Repo functions call this in their finally block:
        try:
            conn.execute(...)
        finally:
            commit_and_close_if_owned(conn, owns)
    """
    try:
        conn.commit()
    finally:
        if owns:
            conn.close()
```

- [ ] **Step 2: 不跑测试(这一步纯新建,不影响 pytest)**

这是结构拆分的第一个文件,所有 5 个 repo 都依赖它。但 pytest 还没动到 sqlite.py,所以不需要跑测试验证。

- [ ] **Step 3: Commit**

```bash
git add backend/core/sqlite/connection.py
git commit -m "refactor(sqlite): extract connection.py with transaction() helper (ADR-0001)"
```

---

### Task 1.2: 抽出 `sessions_repo.py` + `messages_repo.py`

**Files:**
- 新建: `backend/core/sqlite/sessions_repo.py`
- 新建: `backend/core/sqlite/messages_repo.py`

- [ ] **Step 1: 创建 sessions_repo.py**

新建 `E:/backend/core/sqlite/sessions_repo.py`:

```python
"""Sessions CRUD (v1.3.0 refactor — ADR-0001 Q2 B)。

冷路径:只在 PATCH/GET session 时碰。messages 热路径独立。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import (
    commit_and_close_if_owned,
    get_connection,
    optional_conn,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create sessions + messages tables. Mirrors sqlite.py:44-71 verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
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
        """)
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """Apply ALTER TABLE migrations (sessions.history_limit from v1.1.0 PR#2)."""
    conn = get_connection(db_path)
    try:
        try:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN history_limit INTEGER NOT NULL DEFAULT 50"
            )
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        conn.commit()
    finally:
        conn.close()


# ----- CRUD -----

def list_sessions(limit: int = 50, offset: int = 0) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def get_session(
    session_id: str, db_path: Optional[Path] = None
) -> Optional[dict[str, Any]]:
    conn, owns = optional_conn(None) if db_path is None else (get_connection(db_path), True)
    try:
        cur = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        return cur.fetchone()
    finally:
        commit_and_close_if_owned(conn, owns)


def create_session(
    title: Optional[str] = None,
    session_id: Optional[str] = None,
    history_limit: int = 50,
    db_path: Optional[Path] = None,
) -> str:
    if session_id is None:
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    now = _now_iso()
    if not title:
        title = "新会话"
    conn, owns = optional_conn(None) if db_path is None else (get_connection(db_path), True)
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
        commit_and_close_if_owned(conn, owns)
    return session_id


def touch_session(session_id: str) -> None:
    conn, owns = optional_conn(None)
    try:
        conn.execute(
            "UPDATE sessions SET last_active = ? WHERE session_id = ?",
            (_now_iso(), session_id),
        )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)
```

- [ ] **Step 2: 创建 messages_repo.py**

新建 `E:/backend/core/sqlite/messages_repo.py`:

```python
"""Messages CRUD (v1.3.0 refactor — ADR-0001 Q2 B)。

热路径:每条 chat 写一条;SSE soft_warning 读 count_messages。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import (
    commit_and_close_if_owned,
    get_connection,
    optional_conn,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """No-op: messages schema lives in sessions_repo.init_schema (combined DDL).

    Kept for symmetry with other repos; future ALTERs on messages table
    go here.
    """
    pass


def migrate(db_path: Optional[Path] = None) -> None:
    """No-op for now. Future ALTERs on messages columns go here."""
    pass


# ----- CRUD -----

def get_messages(
    session_id: str,
    limit: int = 20,
    db_path: Optional[Path] = None,
) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None) if db_path is None else (get_connection(db_path), True)
    try:
        cur = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cur.fetchall()
        rows.reverse()  # caller expects chronological order
        return rows
    finally:
        commit_and_close_if_owned(conn, owns)


def count_messages(session_id: str) -> int:
    """SSE soft_warning hot path. Uses direct conn (no db_path override)."""
    conn, owns = optional_conn(None)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["n"]) if row else 0
    finally:
        commit_and_close_if_owned(conn, owns)


def save_message(
    session_id: str,
    role: str,
    content: str,
    citations: Optional[List[Any]] = None,
    db_path: Optional[Path] = None,
) -> int:
    citations_json = json.dumps(citations, ensure_ascii=False) if citations else None
    conn, owns = optional_conn(None) if db_path is None else (get_connection(db_path), True)
    try:
        cur = conn.execute(
            """
            INSERT INTO messages (session_id, role, content, citations_json, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, citations_json, _now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        commit_and_close_if_owned(conn, owns)
```

- [ ] **Step 3: 跑现有 tests 验证不回归**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/test_limit_guard.py -v`

Expected: 全过(test_limit_guard.py 当前用 `from backend.core.sqlite import (...)`,re-export shim 还没建,但这两个 repo 文件不影响旧 sqlite.py 的工作)

实际上现在还不需要验证 —— sqlite.py 还在,新文件还没被 import。要等到 Task 1.7 才会切换。

- [ ] **Step 4: Commit**

```bash
git add backend/core/sqlite/sessions_repo.py backend/core/sqlite/messages_repo.py
git commit -m "refactor(sqlite): extract sessions_repo + messages_repo (ADR-0001)"
```

---

### Task 1.3: 抽出 `degradation_repo.py`

**Files:**
- 新建: `backend/core/sqlite/degradation_repo.py`

- [ ] **Step 1: 创建 degradation_repo.py**

新建 `E:/backend/core/sqlite/degradation_repo.py`:

```python
"""Degradation events CRUD (v1.3.0 refactor — ADR-0001)。

含 ALTER TABLE 加 component 列(v0.8.11 P1.4)。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import (
    commit_and_close_if_owned,
    get_connection,
    optional_conn,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create degradation_events table. Mirrors sqlite.py:62-71 verbatim."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
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
        """)
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """ALTER TABLE degradation_events ADD COLUMN component (v0.8.11 P1.4)."""
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
            if "duplicate column" not in str(exc).lower():
                raise
        conn.commit()
    finally:
        conn.close()


# ----- CRUD -----

def save_degradation_event(
    session_id: Optional[str],
    query: Optional[str],
    *,
    source: str,
    reason: str,
    model: Optional[str] = None,
    component: Optional[str] = None,
) -> None:
    """Used by chat.py / sessions.py / boot.py / etc. Persistence failure
    is non-fatal at caller level; this function does not raise.
    """
    try:
        conn, owns = optional_conn(None)
        try:
            conn.execute(
                """
                INSERT INTO degradation_events
                    (session_id, query, source, reason, model, component, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, query, source, reason, model, component, _now_iso()),
            )
            conn.commit()
        finally:
            commit_and_close_if_owned(conn, owns)
    except Exception:
        # Persistence failure is non-fatal; chat flow continues.
        pass


def list_degradation_events(
    limit: int = 100, session_id: Optional[str] = None
) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        if session_id is not None:
            cur = conn.execute(
                "SELECT * FROM degradation_events WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM degradation_events ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def degradation_summary_by_component(
    since_iso: str,
) -> List[dict[str, Any]]:
    """Dashboard 24h 聚合 (v0.8.11 P1.6)."""
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            """
            SELECT COALESCE(component, 'Unknown') AS component,
                   COUNT(*) AS count,
                   MAX(created_at) AS last_seen
            FROM degradation_events
            WHERE created_at >= ?
            GROUP BY COALESCE(component, 'Unknown')
            ORDER BY count DESC
            """,
            (since_iso,),
        )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)
```

- [ ] **Step 2: Commit**

```bash
git add backend/core/sqlite/degradation_repo.py
git commit -m "refactor(sqlite): extract degradation_repo (ADR-0001)"
```

---

### Task 1.4: 抽出 `databases_repo.py`(含 processing_state + recover_orphans)

**Files:**
- 新建: `backend/core/sqlite/databases_repo.py`

- [ ] **Step 1: 创建 databases_repo.py**

新建 `E:/backend/core/sqlite/databases_repo.py`(本文件最大,~340 行):

```python
"""Databases + processing_state CRUD (v1.3.0 refactor — ADR-0001 Q3)。

含 cascade 原子性修复(recover_orphans / delete_database cascade 走
transaction() 共享 conn)。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.bulk_assign import _rewrite_qdrant_payloads
from backend.core.sqlite.connection import (
    commit_and_close_if_owned,
    get_connection,
    optional_conn,
    transaction,
)


DEFAULT_DATABASE_ID = "default"
DEFAULT_COLLECTION = "kb_ai_chunks"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create databases + processing_state tables."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS databases (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                description   TEXT,
                collection    TEXT NOT NULL,
                embed_model   TEXT NOT NULL DEFAULT 'text-embedding-v3',
                chunk_size    INTEGER NOT NULL DEFAULT 500,
                chunk_overlap INTEGER NOT NULL DEFAULT 80,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processing_state (
                task_id        TEXT PRIMARY KEY,
                operation      TEXT NOT NULL,
                source         TEXT NOT NULL,
                database_id    TEXT NOT NULL DEFAULT 'default',
                stage          TEXT NOT NULL,
                status         TEXT NOT NULL,
                started_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL,
                finished_at    TEXT,
                error          TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_processing_status ON processing_state(status, updated_at);
        """)
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """No current ALTERs on databases/processing_state. Future go here."""
    pass


# ----- databases CRUD -----

def list_databases() -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute("SELECT * FROM databases ORDER BY created_at ASC")
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def get_database(db_id: str) -> Optional[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute("SELECT * FROM databases WHERE id = ?", (db_id,))
        return cur.fetchone()
    finally:
        commit_and_close_if_owned(conn, owns)


def create_database(
    db_id: str,
    name: str,
    description: Optional[str] = None,
    collection: Optional[str] = None,
    embed_model: str = "text-embedding-v3",
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> None:
    conn, owns = optional_conn(None)
    try:
        conn.execute(
            """
            INSERT INTO databases
                (id, name, description, collection, embed_model, chunk_size, chunk_overlap, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                name,
                description,
                collection or f"kb_chunks_{db_id}",
                embed_model,
                chunk_size,
                chunk_overlap,
                _now_iso(),
            ),
        )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def update_database(
    db_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> None:
    conn, owns = optional_conn(None)
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
        commit_and_close_if_owned(conn, owns)


def delete_database(db_id: str, cascade: bool = False) -> int:
    """Delete a database record.

    cascade=True 时原子删除 databases 行 + keyword_index 行(通过
    transaction() 共享 conn)。修复 v1.1.0 PR#1 已知非原子 bug:
    旧实现两次 commit,中途崩溃留脏状态。
    """
    if db_id == DEFAULT_DATABASE_ID:
        raise ValueError("'default' 数据库不可删除")

    if not cascade:
        # 简单路径:保持现状(单 repo 单表写)
        conn, owns = optional_conn(None)
        try:
            cur = conn.execute("DELETE FROM databases WHERE id = ?", (db_id,))
            conn.commit()
            return cur.rowcount
        finally:
            commit_and_close_if_owned(conn, owns)

    # cascade 路径:跨 repo 原子写
    from backend.core.rag import keyword_index as rag_keyword  # 避免循环依赖
    with transaction() as conn:
        deleted = conn.execute(
            "DELETE FROM databases WHERE id = ?", (db_id,)
        ).rowcount
        if deleted > 0:
            prefix = f"{db_id}::"
            # 调 rag 层公开函数(共享 conn)
            rag_keyword.delete_by_db_prefix(db_id, conn=conn)
        return deleted


def ensure_default_database() -> None:
    """init_db 末尾调用,确保 'default' 行存在。"""
    conn, owns = optional_conn(None)
    try:
        existing = conn.execute(
            "SELECT 1 FROM databases WHERE id = ?", (DEFAULT_DATABASE_ID,)
        ).fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT INTO databases (id, name, collection, created_at)
            VALUES (?, '默认', ?, ?)
            """,
            (DEFAULT_DATABASE_ID, DEFAULT_COLLECTION, _now_iso()),
        )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def count_documents_by_database(db_id: str) -> int:
    conn, owns = optional_conn(None)
    try:
        if db_id == DEFAULT_DATABASE_ID:
            sql = "SELECT COUNT(DISTINCT source) FROM keyword_index WHERE source NOT LIKE '%::%'"
        else:
            sql = (
                "SELECT COUNT(DISTINCT source) FROM keyword_index "
                "WHERE source LIKE ?"
            )
            row = conn.execute(sql, (f"{db_id}::%",)).fetchone()
            return int(row[0]) if row else 0
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0
    finally:
        commit_and_close_if_owned(conn, owns)


def bulk_assign_documents_to_database(
    old_db_id: str, new_db_id: str, sources: List[str]
) -> int:
    """Rewrite keyword_index.source + Qdrant payload.source via transaction()."""
    from backend.core.rag import keyword_index as rag_keyword
    with transaction() as conn:
        # 1. 改 keyword_index(共享 conn,原子)
        rewritten = rag_keyword.rewrite_source_prefix(
            old_db_id, new_db_id, sources, conn=conn
        )
        # 2. 改 Qdrant payload(外部 IO,失败降级)
        try:
            _rewrite_qdrant_payloads(old_db_id, new_db_id, sources)
        except Exception:
            pass  # 已有 degradation 事件记录
        return rewritten


# ----- processing_state CRUD -----

def upsert_processing(
    task_id: str,
    operation: str,
    source: str,
    database_id: str,
    stage: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    conn, owns = optional_conn(None)
    try:
        now = _now_iso()
        existing = conn.execute(
            "SELECT task_id FROM processing_state WHERE task_id = ?", (task_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE processing_state
                SET stage = ?, status = ?, updated_at = ?, error = ?
                WHERE task_id = ?
                """,
                (stage, status, now, error, task_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO processing_state
                    (task_id, operation, source, database_id, stage, status,
                     started_at, updated_at, finished_at, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (task_id, operation, source, database_id, stage, status, now, now, error),
            )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def finish_processing(
    task_id: str,
    stage: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    conn, owns = optional_conn(None)
    try:
        conn.execute(
            """
            UPDATE processing_state
            SET stage = ?, status = ?, updated_at = ?, finished_at = ?, error = ?
            WHERE task_id = ?
            """,
            (stage, status, _now_iso(), _now_iso(), error, task_id),
        )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def list_orphan_processing(max_age_seconds: int = 600) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            """
            SELECT * FROM processing_state
            WHERE status = 'processing'
              AND updated_at < datetime('now', ?)
            """,
            (f"-{max_age_seconds} seconds",),
        )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def recover_orphans(max_age_seconds: int = 600) -> int:
    """Mark stale processing_state rows as failed + write degradation_events.

    跨 processing_state + degradation_events 两表写,用 transaction() 共享
    conn 保证原子(原子 = 标记 failed 必伴随 degradation 记录)。
    """
    from backend.core.sqlite.degradation_repo import save_degradation_event
    recovered = 0
    with transaction() as conn:
        cur = conn.execute(
            """
            UPDATE processing_state
            SET status = 'failed',
                error = COALESCE(error, 'recovered_orphan'),
                updated_at = ?
            WHERE status = 'processing'
              AND updated_at < datetime('now', ?)
            """,
            (_now_iso(), f"-{max_age_seconds} seconds"),
        )
        recovered = cur.rowcount
        # degradation 事件写入必须紧跟(共享 conn,共享 transaction)
        if recovered > 0:
            conn.execute(
                """
                INSERT INTO degradation_events
                    (session_id, query, source, reason, model, component, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None, None, "processing",
                    "orphan_recovered", None, "Processing", _now_iso(),
                ),
            )
    return recovered
```

> **注意**:`save_degradation_event` 自带 try/except 吞异常(原 sqlite.py:344-345),但 `recover_orphans` 现在在 `transaction()` 里,不能调那个 self-swallowing 版本 —— 必须直接 `INSERT`。如果异常,transaction() 会回滚,UPDATE 也撤销 → 正确行为(不写事件就不标记 failed)。

- [ ] **Step 2: Commit**

```bash
git add backend/core/sqlite/databases_repo.py
git commit -m "refactor(sqlite): extract databases_repo + recover_orphans atomicity (ADR-0001)"
```

---

### Task 1.5: 抽出 `tags_repo.py`

**Files:**
- 新建: `backend/core/sqlite/tags_repo.py`

- [ ] **Step 1: 创建 tags_repo.py**

新建 `E:/backend/core/sqlite/tags_repo.py`:

```python
"""Tags + doc_tags CRUD (v1.3.0 refactor — ADR-0001)。

v1.1.0 PR#4 自由标签:tags + doc_tags 表 + CASCADE FK。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from backend.core.sqlite.connection import (
    commit_and_close_if_owned,
    get_connection,
    optional_conn,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    """Create tags + doc_tags tables."""
    conn = get_connection(db_path)
    try:
        conn.executescript("""
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
        """)
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """No current ALTERs. Future go here."""
    pass


# ----- tag CRUD -----

def create_tag(database_id: str, name: str, color: str = "#FF540E") -> int:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            """
            INSERT INTO tags (database_id, name, color, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (database_id, name, color, _now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        commit_and_close_if_owned(conn, owns)


def list_tags(database_id: str) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            "SELECT * FROM tags WHERE database_id = ? ORDER BY name",
            (database_id,),
        )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def get_tag(tag_id: int) -> Optional[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute("SELECT * FROM tags WHERE id = ?", (tag_id,))
        return cur.fetchone()
    finally:
        commit_and_close_if_owned(conn, owns)


def update_tag(tag_id: int, name: Optional[str] = None, color: Optional[str] = None) -> None:
    conn, owns = optional_conn(None)
    try:
        fields = []
        params: list[Any] = []
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
        commit_and_close_if_owned(conn, owns)


def delete_tag(tag_id: int) -> None:
    conn, owns = optional_conn(None)
    try:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


# ----- doc_tags CRUD -----

def assign_tags_to_doc(source: str, tag_ids: List[int]) -> None:
    if not tag_ids:
        return
    conn, owns = optional_conn(None)
    try:
        for tid in tag_ids:
            conn.execute(
                "INSERT OR IGNORE INTO doc_tags (source, tag_id, created_at) VALUES (?, ?, ?)",
                (source, tid, _now_iso()),
            )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def unassign_tag_from_doc(source: str, tag_id: int) -> None:
    conn, owns = optional_conn(None)
    try:
        conn.execute(
            "DELETE FROM doc_tags WHERE source = ? AND tag_id = ?",
            (source, tag_id),
        )
        conn.commit()
    finally:
        commit_and_close_if_owned(conn, owns)


def list_tags_for_doc(source: str) -> List[dict[str, Any]]:
    conn, owns = optional_conn(None)
    try:
        cur = conn.execute(
            """
            SELECT t.* FROM tags t
            JOIN doc_tags d ON d.tag_id = t.id
            WHERE d.source = ?
            ORDER BY t.name
            """,
            (source,),
        )
        return cur.fetchall()
    finally:
        commit_and_close_if_owned(conn, owns)


def list_documents_by_tags(database_id: str, tag_ids: List[int]) -> List[dict[str, Any]]:
    if not tag_ids:
        return []
    conn, owns = optional_conn(None)
    try:
        placeholders = ",".join("?" * len(tag_ids))
        cur = conn.execute(
            f"""
            SELECT DISTINCT d.source FROM doc_tags d
            JOIN tags t ON t.id = d.tag_id
            WHERE t.database_id = ? AND t.id IN ({placeholders})
            GROUP BY d.source
            HAVING COUNT(DISTINCT t.id) = ?
            """,
            (database_id, *tag_ids, len(tag_ids)),
        )
        return [{"source": row["source"]} for row in cur.fetchall()]
    finally:
        commit_and_close_if_owned(conn, owns)
```

- [ ] **Step 2: Commit**

```bash
git add backend/core/sqlite/tags_repo.py
git commit -m "refactor(sqlite): extract tags_repo (ADR-0001)"
```

---

### Task 1.6: `rag/keyword_index.py` 加 init_schema + delete_by_db_prefix + rewrite_source_prefix

**Files:**
- 修改: `backend/core/rag/keyword_index.py`

- [ ] **Step 1: 读现有 keyword_index.py 末尾**

Run: `tail -20 E:/backend/core/rag/keyword_index.py`

确认 `search_by_tokens` 等函数的位置,我们要在文件末尾追加新函数。

- [ ] **Step 2: 加 `init_schema(db_path)` 函数**

在 `keyword_index.py` 末尾追加:

```python
def init_schema(db_path: Optional[Path] = None) -> None:
    """Create keyword_index table + index (v1.3.0 refactor — ADR-0001 Q1 B)。

    Schema 跟随 CRUD 同模块(本文件)。init_db_core() 显式 import 调用之。
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS keyword_index (
                word      TEXT NOT NULL,
                point_id  TEXT NOT NULL,
                source    TEXT,
                text      TEXT,
                PRIMARY KEY (word, point_id)
            );
            CREATE INDEX IF NOT EXISTS idx_keyword_word ON keyword_index(word);
        """)
        conn.commit()
    finally:
        conn.close()
```

实际 `keyword_index.py` 用的是 `import sqlite3` 直接管理 conn(不是从 `core.sqlite` import)。检查现有 import 后,**用同样的本地模式**写一个新 helper:

```python
from backend.core.config import get_db_path

def _own_connection(db_path=None):
    if db_path is None:
        db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(db_path=None):
    conn = _own_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS keyword_index (
                word      TEXT NOT NULL,
                point_id  TEXT NOT NULL,
                source    TEXT,
                text      TEXT,
                PRIMARY KEY (word, point_id)
            );
            CREATE INDEX IF NOT EXISTS idx_keyword_word ON keyword_index(word);
        """)
        conn.commit()
    finally:
        conn.close()
```

> **不引用 core.sqlite.connection**:避免循环依赖(coresqlite → rag.keyword_index → 任何东西 → coresqlite)。本模块用本地 helper。

- [ ] **Step 3: 加 `delete_by_db_prefix(db_id, *, conn=None)` 函数**

```python
def delete_by_db_prefix(db_id, *, conn=None):
    """删除某 db 下所有 keyword_index 行(共享 conn for 跨 repo 原子)。

    由 databases_repo.delete_database(cascade=True) 在 transaction() 内调用。
    conn=None 时自己开 conn(独立调用场景)。
    """
    prefix = f"{db_id}::"
    if conn is None:
        own_conn = _own_connection()
        try:
            cur = own_conn.execute(
                "DELETE FROM keyword_index WHERE source LIKE ?",
                (prefix + "%",),
            )
            own_conn.commit()
            return cur.rowcount
        finally:
            own_conn.close()
    # Injected conn 模式:不 commit(由 transaction() 控制)
    cur = conn.execute(
        "DELETE FROM keyword_index WHERE source LIKE ?",
        (prefix + "%",),
    )
    return cur.rowcount
```

- [ ] **Step 4: 加 `rewrite_source_prefix(old_db_id, new_db_id, sources, *, conn=None)` 函数**

```python
def rewrite_source_prefix(old_db_id, new_db_id, sources, *, conn=None):
    """改写 keyword_index.source 从 <old_db>::<file> 到 <new_db>::<file>。

    由 databases_repo.bulk_assign_documents_to_database() 在 transaction()
    内调用。sources 是要改的 source 列表(允许 caller 限定 scope)。
    """
    old_prefix = f"{old_db_id}::"
    new_prefix = f"{new_db_id}::"
    rewritten = 0
    if conn is None:
        own_conn = _own_connection()
        try:
            for src in sources:
                if not src.startswith(old_prefix):
                    continue
                new_src = new_prefix + src[len(old_prefix):]
                cur = own_conn.execute(
                    "UPDATE keyword_index SET source = ? WHERE source = ?",
                    (new_src, src),
                )
                rewritten += cur.rowcount
            own_conn.commit()
            return rewritten
        finally:
            own_conn.close()
    for src in sources:
        if not src.startswith(old_prefix):
            continue
        new_src = new_prefix + src[len(old_prefix):]
        cur = conn.execute(
            "UPDATE keyword_index SET source = ? WHERE source = ?",
            (new_src, src),
        )
        rewritten += cur.rowcount
    return rewritten
```

- [ ] **Step 5: Commit**

```bash
git add backend/core/rag/keyword_index.py
git commit -m "refactor(rag): keyword_index owns schema + add delete/rewrite helpers (ADR-0001)"
```

---

### Task 1.7: `sqlite/__init__.py` orchestrator + 临时 re-export shim

**Files:**
- 新建: `backend/core/sqlite/__init__.py`

- [ ] **Step 1: 创建 __init__.py**

新建 `E:/backend/core/sqlite/__init__.py`:

```python
"""SQLite orchestrator (v1.3.0 refactor — ADR-0001)。

init_db 是 3 步 orchestrator:
  init_db_core    → 每 repo.init_schema() + rag.keyword_index.init_schema()
  init_db_migrate → 每 repo.migrate() + 未来 rag.keyword_index ALTER
  init_db_post    → databases_repo.ensure_default_database()

本模块同时 re-export 5 个 repo 的公开函数(PR #1 临时 shim);PR #2
会删除 re-export,要求调用方改为 `from backend.core.sqlite.X_repo import ...`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.rag import keyword_index as rag_keyword_index

from . import (
    connection,
    databases_repo,
    degradation_repo,
    messages_repo,
    sessions_repo,
    tags_repo,
)

__all__ = [
    # Orchestrator
    "init_db",
    "init_db_core",
    "init_db_migrate",
    "init_db_post",
    # Connection helpers
    "get_connection",
    "transaction",
    # Re-exports (PR #1 shim; deleted in PR #2)
    # sessions_repo
    "list_sessions",
    "get_session",
    "create_session",
    "touch_session",
    # messages_repo
    "get_messages",
    "count_messages",
    "save_message",
    # degradation_repo
    "save_degradation_event",
    "list_degradation_events",
    "degradation_summary_by_component",
    # databases_repo (含 processing_state)
    "list_databases",
    "get_database",
    "create_database",
    "update_database",
    "delete_database",
    "ensure_default_database",
    "count_documents_by_database",
    "bulk_assign_documents_to_database",
    "upsert_processing",
    "finish_processing",
    "list_orphan_processing",
    "recover_orphans",
    # tags_repo
    "create_tag",
    "list_tags",
    "get_tag",
    "update_tag",
    "delete_tag",
    "assign_tags_to_doc",
    "unassign_tag_from_doc",
    "list_tags_for_doc",
    "list_documents_by_tags",
]

_REPOS = [
    sessions_repo,
    messages_repo,
    degradation_repo,
    databases_repo,
    tags_repo,
]


def init_db(db_path: Optional[Path] = None) -> None:
    """Orchestrator:core DDL → per-repo migrate → default row."""
    init_db_core(db_path)
    init_db_migrate(db_path)
    init_db_post(db_path)


def init_db_core(db_path: Optional[Path] = None) -> None:
    """所有 repo 的 CREATE TABLE。"""
    for repo in _REPOS:
        repo.init_schema(db_path)
    rag_keyword_index.init_schema(db_path)  # ADR-0001 Q1 B


def init_db_migrate(db_path: Optional[Path] = None) -> None:
    """所有 repo 的 ALTER TABLE(幂等)。"""
    for repo in _REPOS:
        repo.migrate(db_path)
    # rag.keyword_index 当前无 ALTER;未来有 ALTER 时也在这里调


def init_db_post(db_path: Optional[Path] = None) -> None:
    """post-schema 后置钩子(目前只 ensure_default_database)。"""
    databases_repo.ensure_default_database()


# ----- 临时 re-export shim (PR #1) -----
get_connection = connection.get_connection
transaction = connection.transaction

list_sessions = sessions_repo.list_sessions
get_session = sessions_repo.get_session
create_session = sessions_repo.create_session
touch_session = sessions_repo.touch_session

get_messages = messages_repo.get_messages
count_messages = messages_repo.count_messages
save_message = messages_repo.save_message

save_degradation_event = degradation_repo.save_degradation_event
list_degradation_events = degradation_repo.list_degradation_events
degradation_summary_by_component = degradation_repo.degradation_summary_by_component

list_databases = databases_repo.list_databases
get_database = databases_repo.get_database
create_database = databases_repo.create_database
update_database = databases_repo.update_database
delete_database = databases_repo.delete_database
ensure_default_database = databases_repo.ensure_default_database
count_documents_by_database = databases_repo.count_documents_by_database
bulk_assign_documents_to_database = databases_repo.bulk_assign_documents_to_database
upsert_processing = databases_repo.upsert_processing
finish_processing = databases_repo.finish_processing
list_orphan_processing = databases_repo.list_orphan_processing
recover_orphans = databases_repo.recover_orphans

create_tag = tags_repo.create_tag
list_tags = tags_repo.list_tags
get_tag = tags_repo.get_tag
update_tag = tags_repo.update_tag
delete_tag = tags_repo.delete_tag
assign_tags_to_doc = tags_repo.assign_tags_to_doc
unassign_tag_from_doc = tags_repo.unassign_tag_from_doc
list_tags_for_doc = tags_repo.list_tags_for_doc
list_documents_by_tags = tags_repo.list_documents_by_tags
```

- [ ] **Step 2: 删除 `backend/core/sqlite.py`**

```bash
rm E:/backend/core/sqlite.py
```

> **风险提示**:`backend/core/sqlite.py` 是单文件模块,删除后 Python 缓存(`__pycache__/sqlite.cpython-312.pyc`)可能残留。
> 检查并清掉:`rm -f E:/backend/core/__pycache__/sqlite.cpython-312-pytest-9.1.1.pyc`(或类似文件名)

- [ ] **Step 3: 跑全套测试验证行为不变**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **252 passed**(基线,与重构前一致)

如果失败,可能原因:
- shim 没把某个函数导出 → 看 `__all__` 加缺失项
- bulk_assign 循环 import → 检查 `from backend.core.rag import keyword_index as rag_keyword` 是不是放在函数内 lazy import(避免循环)

- [ ] **Step 4: 跑 run-checks.ps1 全套**

Run: `cd /e && pwsh -File scripts/run-checks.ps1 -SkipFrontendBuild`

Expected: 4/4 全绿(ruff + pytest + eslint 跳过 frontend build 因为前端没改)

- [ ] **Step 5: Commit**

```bash
git add backend/core/sqlite/ backend/core/sqlite.py
git commit -m "refactor(sqlite): sqlite.py → sqlite/ package with re-export shim (ADR-0001)"
```

> **commit 用 `-m` 多个 message**,因为这次包含删除 sqlite.py + 新建包,实质是一个逻辑单元。

---

### Task 1.8: `test_sqlite_refactor.py` 5 个新测

**Files:**
- 新建: `tests/unit/test_sqlite_refactor.py`

- [ ] **Step 1: 写测试文件**

新建 `E:/tests/unit/test_sqlite_refactor.py`:

```python
"""SQLite refactor tests (v1.3.0 — ADR-0001 Q7 B: 5 精准测)。

覆盖新行为:
  - transaction() commit 路径
  - transaction() rollback 路径
  - delete_database cascade 跨 repo 原子性
  - rag.keyword_index.delete_by_db_prefix 新公开函数
  - init_db 3 步独立可调 + idempotent
"""
import sqlite3
from pathlib import Path

import pytest

from backend.core.sqlite import (
    databases_repo,
    init_db,
    init_db_core,
    init_db_migrate,
    init_db_post,
)
from backend.core.sqlite.connection import get_connection, transaction


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Per-test tmp db.sqlite. init_db 跑过一遍。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


def test_transaction_commit_on_success(tmp_db_path):
    """transaction() 上下文正常退出 → conn.commit() 被调。"""
    conn = get_connection(tmp_db_path)
    pre_row_count = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions"
    ).fetchone()["n"]
    conn.close()

    with transaction(tmp_db_path) as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, title, created_at, last_active) "
            "VALUES ('test-sid', 'T', '2026-01-01', '2026-01-01')"
        )

    conn = get_connection(tmp_db_path)
    post_row_count = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions"
    ).fetchone()["n"]
    conn.close()
    assert post_row_count == pre_row_count + 1


def test_transaction_rollback_on_exception(tmp_db_path):
    """transaction() 上下文抛异常 → 写入回滚,db 不变。"""
    pre_row_count = get_connection(tmp_db_path).execute(
        "SELECT COUNT(*) AS n FROM sessions"
    ).fetchone()["n"]

    with pytest.raises(RuntimeError):
        with transaction(tmp_db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, title, created_at, last_active) "
                "VALUES ('rolled-back', 'T', '2026-01-01', '2026-01-01')"
            )
            raise RuntimeError("simulated failure")

    post_row_count = get_connection(tmp_db_path).execute(
        "SELECT COUNT(*) AS n FROM sessions"
    ).fetchone()["n"]
    assert post_row_count == pre_row_count, "rollback failed — row leaked"


def test_delete_database_cascade_atomicity(tmp_db_path, monkeypatch):
    """delete_database(cascade=True) + rag.keyword_index.delete_by_db_prefix 抛异常
    → databases 行**仍然存在**(transaction 回滚)。

    修 v1.1.0 PR#1 已知非原子 bug:旧实现两次 commit,中途崩溃留脏状态。
    """
    # 准备:在 databases + keyword_index 各插一行
    conn = get_connection(tmp_db_path)
    conn.execute(
        "INSERT INTO databases (id, name, collection, created_at) "
        "VALUES ('cascade-db', 'C', 'kb_chunks_cascade-db', '2026-01-01')"
    )
    conn.commit()
    conn.close()

    # 注入失败:让 rag.keyword_index.delete_by_db_prefix 抛异常
    from backend.core.rag import keyword_index
    original = keyword_index.delete_by_db_prefix
    def boom(*args, **kwargs):
        raise RuntimeError("simulated keyword_index failure")
    monkeypatch.setattr(keyword_index, "delete_by_db_prefix", boom)

    # 还原 databases_repo 的内部 import 路径(它在函数内 lazy import)
    import importlib
    importlib.reload(databases_repo)
    monkeypatch.setattr(databases_repo, "_keyword_index_module", keyword_index)

    with pytest.raises(RuntimeError, match="simulated keyword_index failure"):
        databases_repo.delete_database("cascade-db", cascade=True)

    # 验证:databases 表行**还在**
    conn = get_connection(tmp_db_path)
    row = conn.execute(
        "SELECT 1 FROM databases WHERE id = ?", ("cascade-db",)
    ).fetchone()
    conn.close()
    assert row is not None, "transaction() did not rollback — databases row lost"

    # 清理:还原 monkeypatch
    monkeypatch.setattr(keyword_index, "delete_by_db_prefix", original)
    importlib.reload(databases_repo)


def test_keyword_index_delete_by_db_prefix(tmp_db_path):
    """新公开函数 delete_by_db_prefix(独立 conn 模式)按 prefix 删行。"""
    # 准备:插 2 行 keyword_index
    conn = get_connection(tmp_db_path)
    conn.executescript("""
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w1', 'p1', 'test-db::foo.md');
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w2', 'p2', 'test-db::bar.md');
        INSERT INTO keyword_index (word, point_id, source) VALUES ('w3', 'p3', 'other::baz.md');
    """)
    conn.commit()
    conn.close()

    # 删 test-db 前缀
    from backend.core.rag import keyword_index
    deleted = keyword_index.delete_by_db_prefix("test-db")

    assert deleted == 2

    conn = get_connection(tmp_db_path)
    remaining = conn.execute(
        "SELECT source FROM keyword_index ORDER BY source"
    ).fetchall()
    conn.close()
    assert len(remaining) == 1
    assert remaining[0]["source"] == "other::baz.md"


def test_init_db_three_steps_idempotent(tmp_db_path):
    """init_db_core / init_db_migrate / init_db_post 各跑两次不报错。"""
    # 跑第二次(第一次是 fixture 里 init_db)
    init_db_core(tmp_db_path)
    init_db_migrate(tmp_db_path)
    init_db_post(tmp_db_path)

    # 第三次
    init_db_core(tmp_db_path)
    init_db_migrate(tmp_db_path)
    init_db_post(tmp_db_path)

    # 验证:databases 行还是 'default'(ensure_default_database 不重复插)
    conn = get_connection(tmp_db_path)
    rows = conn.execute("SELECT id FROM databases").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["id"] == "default"
```

- [ ] **Step 2: 跑新测试**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/test_sqlite_refactor.py -v`

Expected: **5 passed**

如果失败,常见原因:
- `test_keyword_index_delete_by_db_prefix` 失败 → keyword_index.py 的 `delete_by_db_prefix` 没正确接 prefix 拼接(检查 `prefix + "%"`)
- `test_delete_database_cascade_atomicity` 失败 → `transaction()` rollback 没生效(检查 sqlite3 默认 rollback 行为)
- `test_init_db_three_steps_idempotent` 失败 → `ensure_default_database` 的"existing 检查"漏了

- [ ] **Step 3: 跑全套**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **257 passed**(252 + 5)

- [ ] **Step 4: 跑 ruff**

Run: `cd /e && backend/.venv/Scripts/python -m ruff check backend/ tests/unit/test_sqlite_refactor.py`

Expected: 全绿

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_sqlite_refactor.py
git commit -m "test(sqlite): 5 tests for transaction + cascade atomicity + idempotency (ADR-0001)"
```

- [ ] **Step 6: 更新 CHANGELOG.md**

在 v1.3.0 段后追加 PR #1 子段(占位文本,后面 v1.3.0 release commit 会完善):

```markdown
### PR #1 sqlite-refactor(内部重构,零行为变更)

- **5-repo 拆分**:`backend/core/sqlite.py`(1064 行 god 模块)拆为 `backend/core/sqlite/` 包,5 个 repo + connection.py + orchestrator
- **`transaction()` context manager**:跨 repo 原子写(修 `delete_database` cascade + `recover_orphans` 已知非原子 bug)
- **3 步 init_db**:`init_db_core / init_db_migrate / init_db_post`,与 boot.py SSE 阶段对齐
- **keyword_index schema 归 `core/rag/keyword_index.py`**:`CREATE TABLE` 与 CRUD 同模块
- **测试基线**:252 → 257(+5 新测)

配套 ADR:`docs/adr/0001-sqlite-repo-split.md`
```

- [ ] **Step 7: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): v1.3.0 PR #1 - sqlite refactor"
```

---

## PR #2 Tasks

### Task 2.1: 迁移 `backend/api/chat.py` import

**Files:**
- 修改: `backend/api/chat.py`

- [ ] **Step 1: 读当前 import 段**

Run: `grep -n "from backend.core.sqlite" E:/backend/api/chat.py`

当前应显示:
```python
from backend.core.sqlite import (
    count_messages,
    get_messages,
    save_degradation_event,
    save_message,
    touch_session,
)
```

- [ ] **Step 2: 改写为分别从 repo import**

替换 import 段:
```python
from backend.core.sqlite.messages_repo import count_messages, get_messages, save_message
from backend.core.sqlite.degradation_repo import save_degradation_event
from backend.core.sqlite.sessions_repo import touch_session
```

- [ ] **Step 3: 跑测试验证**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **257 passed**

- [ ] **Step 4: Commit**

```bash
git add backend/api/chat.py
git commit -m "refactor(sqlite): chat.py imports from specific repos (ADR-0001 PR #2)"
```

---

### Task 2.2: 迁移其他 backend/api/ import(同模式)

**Files:**
- 修改: `backend/api/sessions.py`
- 修改: `backend/api/databases.py`
- 修改: `backend/api/tags.py`
- 修改: `backend/api/knowledge.py`
- 修改: `backend/api/boot.py`
- 修改: `backend/api/dashboard.py`

- [ ] **Step 1: 列出每个文件的当前 import**

Run:
```bash
for f in backend/api/sessions.py backend/api/databases.py backend/api/tags.py backend/api/knowledge.py backend/api/boot.py backend/api/dashboard.py; do
  echo "=== $f ==="
  grep -n "from backend.core.sqlite" "$f"
done
```

- [ ] **Step 2: 按对应函数所属 repo 改写 import**

每个文件按以下规则:
- `sessions_*` → `from backend.core.sqlite.sessions_repo import ...`
- `messages_*` → `from backend.core.sqlite.messages_repo import ...`
- `save_degradation_event` / `list_degradation_events` / `degradation_summary_by_component` → `degradation_repo`
- `databases_repo` 函数(`list_databases` / `get_database` / `create_database` / `update_database` / `delete_database` / `ensure_default_database` / `count_documents_by_database` / `bulk_assign_documents_to_database` / `upsert_processing` / `finish_processing` / `list_orphan_processing` / `recover_orphans`) → `databases_repo`
- `create_tag` / `list_tags` / `get_tag` / `update_tag` / `delete_tag` / `assign_tags_to_doc` / `unassign_tag_from_doc` / `list_tags_for_doc` / `list_documents_by_tags` → `tags_repo`

特别处理:
- `backend/api/boot.py` 有 `from backend.core.sqlite import recover_orphans` 和 `from backend.core.sqlite import init_db`,改为:
  ```python
  from backend.core.sqlite import init_db  # orchestrator 保留 import
  from backend.core.sqlite.databases_repo import recover_orphans
  ```
- `backend/api/dashboard.py` 有 `from backend.core.sqlite import degradation_summary_by_component, list_databases as _list_dbs`,改为:
  ```python
  from backend.core.sqlite.degradation_repo import degradation_summary_by_component
  from backend.core.sqlite.databases_repo import list_databases as _list_dbs
  ```

- [ ] **Step 3: 跑全套测试**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **257 passed**

- [ ] **Step 4: Commit(可一次 commit 6 个文件)**

```bash
git add backend/api/sessions.py backend/api/databases.py backend/api/tags.py backend/api/knowledge.py backend/api/boot.py backend/api/dashboard.py
git commit -m "refactor(sqlite): api/ imports from specific repos (ADR-0001 PR #2)"
```

---

### Task 2.3: 迁移 `tests/unit/` import

**Files:**
- 修改: `tests/unit/test_limit_guard.py`
- 修改: `tests/unit/test_tags_api.py`

- [ ] **Step 1: 改 test_limit_guard.py**

当前(从 commit 历史看):
```python
from backend.core.sqlite import init_db, create_session, get_session
```

改为:
```python
from backend.core.sqlite import init_db
from backend.core.sqlite.sessions_repo import create_session, get_session
```

- [ ] **Step 2: 改 test_tags_api.py**

读 import 段:
```bash
sed -n '1,15p' E:/tests/unit/test_tags_api.py
```

按函数所属 repo 拆开(可能用到 `init_db` / `create_tag` / `list_tags` / `get_tag` / `update_tag` / `delete_tag` / `assign_tags_to_doc` / `list_tags_for_doc` / `list_databases` 等)。

- [ ] **Step 3: 跑全套测试**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **257 passed**

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_limit_guard.py tests/unit/test_tags_api.py
git commit -m "test(sqlite): migrate test imports to specific repos (ADR-0001 PR #2)"
```

---

### Task 2.4: 删 `__init__.py` 临时 re-export shim

**Files:**
- 修改: `backend/core/sqlite/__init__.py`

- [ ] **Step 1: 读 `__init__.py` 末尾**

确认 re-export shim 在 `__init__.py` 文件下半部分。

- [ ] **Step 2: 删除 shim 段**

删除从 `# ----- 临时 re-export shim (PR #1) -----` 到文件末尾的所有 re-export 赋值语句(`get_connection = connection.get_connection` 一直到 `list_documents_by_tags = tags_repo.list_documents_by_tags`)。

保留内容:
- imports
- `_REPOS` 列表
- `init_db` / `init_db_core` / `init_db_migrate` / `init_db_post` orchestrator 函数
- `__all__` 删掉 re-export 项,只留 `init_db` / `init_db_core` / `init_db_migrate` / `init_db_post`

最终 `__init__.py` 应只剩 ~40 行:

```python
"""SQLite orchestrator (v1.3.0 refactor — ADR-0001)。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.rag import keyword_index as rag_keyword_index

from . import (
    connection,
    databases_repo,
    degradation_repo,
    messages_repo,
    sessions_repo,
    tags_repo,
)

__all__ = [
    "init_db",
    "init_db_core",
    "init_db_migrate",
    "init_db_post",
]

_REPOS = [
    sessions_repo,
    messages_repo,
    degradation_repo,
    databases_repo,
    tags_repo,
]


def init_db(db_path: Optional[Path] = None) -> None:
    init_db_core(db_path)
    init_db_migrate(db_path)
    init_db_post(db_path)


def init_db_core(db_path: Optional[Path] = None) -> None:
    for repo in _REPOS:
        repo.init_schema(db_path)
    rag_keyword_index.init_schema(db_path)


def init_db_migrate(db_path: Optional[Path] = None) -> None:
    for repo in _REPOS:
        repo.migrate(db_path)


def init_db_post(db_path: Optional[Path] = None) -> None:
    databases_repo.ensure_default_database()
```

- [ ] **Step 3: 跑全套测试**

Run: `cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q`

Expected: **257 passed**

如果失败,某个调用点忘了迁移 import → 找到对应文件,按 Task 2.1/2.2/2.3 模式补改。

- [ ] **Step 4: 跑 run-checks.ps1 全套**

Run: `cd /e && pwsh -File scripts/run-checks.ps1 -SkipFrontendBuild`

Expected: 4/4 全绿

- [ ] **Step 5: Commit**

```bash
git add backend/core/sqlite/__init__.py
git commit -m "refactor(sqlite): remove re-export shim (ADR-0001 PR #2 complete)"
```

---

### Task 2.5: 更新 CHANGELOG.md + 关闭 PR #2

- [ ] **Step 1: 在 v1.3.0 段追加 PR #2 子段**

在 PR #1 子段之后追加:

```markdown
### PR #2 sqlite-imports-migration(清理 import 路径)

- 12 个调用点从 `from backend.core.sqlite import X` 改写为 `from backend.core.sqlite.X_repo import X`
- 删 `__init__.py` 临时 re-export shim
- `__init__.py` 只剩 orchestrator(init_db 3 步)+ _REPOS 列表

测试基线:257 → 257(零变化)
```

- [ ] **Step 2: 跑最终验证**

```bash
cd /e && pwsh -File scripts/run-checks.ps1 -SkipFrontendBuild
cd /e && backend/.venv/Scripts/python -m pytest tests/unit/ -q
cd /e && backend/.venv/Scripts/python -m pytest tests/integration/api/test_api.py -q
```

Expected: pytest 257/257 + 6/6 api + ruff/eslint/build 全绿

- [ ] **Step 3: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): v1.3.0 PR #2 - sqlite imports migration"
```

---

## 完成判定

- [ ] **PR #1 已合并**:`pytest 257/257`、`ruff` 全绿、`run-checks.ps1 4/4` 全绿、CHANGELOG 段已加
- [ ] **PR #2 已合并**:`__init__.py` ~40 行(只剩 orchestrator)、12 调用点已迁移、CHANGELOG 段已加
- [ ] **ADR-0001 链接**:`CHANGELOG.md` v1.3.0 段引用 `docs/adr/0001-sqlite-repo-split.md`
- [ ] **v1.3.0 release commit**:`version` 1.2.0 → 1.3.0;`AGENTS.md §13` 加 v1.3.0 节点(引用 ADR + spec + 本 plan)

---

**Status**:🟡 待用户 review · 完成 PR #1 + PR #2 后,v1.3.0 内部的"sqlite 拆分"工作闭环