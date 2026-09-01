"""SQLite package orchestrator (v1.3.0 refactor — ADR-0001).

The former 1064-line ``backend/core/sqlite.py`` god module is now a package of
5 repos + connection helpers. This ``__init__`` keeps ONLY the 3-step init_db
orchestrator (init_db_core / init_db_migrate / init_db_post) — aligned with
boot.py's SSE schema_migration stage.

PR #2 removed the temporary re-export shim: callers import from the specific
repo, e.g. ``from backend.core.sqlite.sessions_repo import create_session`` or
``from backend.core.sqlite.connection import get_connection, transaction``.

v2.0 PR#3 adds agent_repo (agent_runs + agent_steps).
v2.2 T11 adds eval_repo (eval_runs — 评测结果落库趋势).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.rag import keyword_index as rag_keyword_index

from . import (
    agent_repo,
    connection,
    databases_repo,
    degradation_repo,
    eval_repo,
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
    agent_repo,
    eval_repo,
]


def init_db(db_path: Optional[Path] = None) -> None:
    """Orchestrator:core DDL → per-repo migrate → default row."""
    init_db_core(db_path)
    init_db_migrate(db_path)
    init_db_post(db_path)


def init_db_core(db_path: Optional[Path] = None) -> None:
    """所有 repo 的 CREATE TABLE + keyword_index schema(ADR-0001 Q1 B)。

    keyword_index 有自己独立的 get_db_path(不依赖 core.sqlite,避免循环依赖),
    因此当 db_path 为 None 时必须把 connection 层解析出的具体路径显式传给它,
    保证 keyword_index 表与其它表落在同一个 db 文件(prod 与测试隔离都成立)。
    """
    for repo in _REPOS:
        repo.init_schema(db_path)
    kw_path = db_path if db_path is not None else connection.get_db_path()
    rag_keyword_index.init_schema(kw_path)


def init_db_migrate(db_path: Optional[Path] = None) -> None:
    """所有 repo 的 ALTER TABLE(幂等)。

    rag.keyword_index 当前无 ALTER;未来有 ALTER 时也在这里调。
    """
    for repo in _REPOS:
        repo.migrate(db_path)


def init_db_post(db_path: Optional[Path] = None) -> None:
    """post-schema 后置钩子(目前只 ensure_default_database)。"""
    databases_repo.ensure_default_database(db_path)
