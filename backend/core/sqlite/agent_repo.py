"""Agent trajectory CRUD (v2.0 PR#3 — 工单 T12).

Owns agent_runs + agent_steps tables (设计稿 §5). Registered into
``_REPOS`` so init_db core/migrate cover it like the other 5 repos.
All truncation limits live here so callers cannot bypass them:
  - tool_args ≤ 1000 chars
  - observation ≤ 2000 chars
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.sqlite.connection import get_connection

_TOOL_ARGS_MAX_CHARS = 1000
_OBSERVATION_MAX_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                id          TEXT PRIMARY KEY,
                session_id  TEXT,
                question    TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'running',
                steps_count INTEGER NOT NULL DEFAULT 0,
                tools_used  TEXT NOT NULL DEFAULT '[]',
                model       TEXT,
                total_in    INTEGER NOT NULL DEFAULT 0,
                total_out   INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                created_at  TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_steps (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL REFERENCES agent_runs(id),
                step_idx   INTEGER NOT NULL,
                type       TEXT NOT NULL,
                tool_name  TEXT,
                tool_args  TEXT,
                observation TEXT,
                latency_ms INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_runs_session
                ON agent_runs(session_id, created_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """v2.0 新表无 ALTER;索引创建保持幂等(对齐 5-repo 模式签名)。"""
    conn = get_connection(db_path)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_steps_run "
            "ON agent_steps(run_id, step_idx)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def create_run(
    run_id: str,
    question: str,
    *,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO agent_runs (id, session_id, question, status, created_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (run_id, session_id, question, _now_iso()),
        )
        conn.commit()
        return run_id
    finally:
        conn.close()


def finish_run(
    run_id: str,
    *,
    status: str,
    steps_count: int = 0,
    tools_used: Optional[List[str]] = None,
    model: Optional[str] = None,
    total_in: int = 0,
    total_out: int = 0,
    error: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Close a run; unknown run_id 是 no-op(写失败不阻断主链由调用方兜底)。"""
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE agent_runs SET
                status = ?, steps_count = ?, tools_used = ?, model = ?,
                total_in = ?, total_out = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                int(steps_count),
                json.dumps(tools_used or [], ensure_ascii=False),
                model,
                int(total_in),
                int(total_out),
                error,
                _now_iso(),
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: str, *, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,))
        return cur.fetchone()
    finally:
        conn.close()


def list_runs(limit: int = 20, *, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT id, session_id, question, status, steps_count, tools_used,
                   model, total_in, total_out, created_at, finished_at
            FROM agent_runs ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def add_step(
    run_id: str,
    step_idx: int,
    type_: str,
    *,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    observation: Optional[str] = None,
    latency_ms: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> int:
    args_text: Optional[str] = None
    if tool_args is not None:
        args_text = json.dumps(tool_args, ensure_ascii=False)
        if len(args_text) > _TOOL_ARGS_MAX_CHARS:
            args_text = args_text[:_TOOL_ARGS_MAX_CHARS] + "...(截断)"
    if observation is not None and len(observation) > _OBSERVATION_MAX_CHARS:
        observation = observation[:_OBSERVATION_MAX_CHARS] + "...(截断)"
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO agent_steps
                (run_id, step_idx, type, tool_name, tool_args, observation,
                 latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                int(step_idx),
                type_,
                tool_name,
                args_text,
                observation,
                latency_ms,
                _now_iso(),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_run_steps(
    run_id: str, *, db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            SELECT id, run_id, step_idx, type, tool_name, tool_args,
                   observation, latency_ms, created_at
            FROM agent_steps WHERE run_id = ? ORDER BY id ASC
            """,
            (run_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()
