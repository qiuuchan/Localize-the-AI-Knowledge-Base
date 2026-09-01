"""Evaluation runs persistence (v2.2 T11 — LLM-as-judge + trend).

Owns the ``eval_runs`` table: one row per evaluation run (keyword / llm
judge 口径), keyed by a deterministic id so re-running the same-day
same-mode evaluation is idempotent (INSERT OR REPLACE → last run wins,
one row per day per mode = trend query shape).

Registered into ``_REPOS`` (backend/core/sqlite/__init__.py) so init_db
core/migrate cover it like the other 7 repos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.sqlite.connection import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_schema(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(
            # noqa: E501
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                id                   TEXT PRIMARY KEY,
                kind                 TEXT NOT NULL,
                mode                 TEXT NOT NULL,
                dataset              TEXT NOT NULL,
                created_at           TEXT NOT NULL,
                total                INTEGER NOT NULL,
                passed               INTEGER NOT NULL,
                pass_rate            REAL NOT NULL,
                tools_accuracy       REAL,
                task_completion_rate REAL,
                avg_steps            REAL,
                p95_ms               REAL,
                total_tokens         INTEGER,
                cost_estimate_yuan   REAL,
                detail_json          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_eval_runs_kind_mode
                ON eval_runs(kind, mode, created_at);
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate(db_path: Optional[Path] = None) -> None:
    """No ALTER yet; kept for _REPOS uniform contract (idempotent noop)."""
    # 未来列演进(如加 judge_model)在此追加 try/except duplicate-column 模式,
    # 对齐 degradation_repo.migrate 的写法。


# ---------------------------------------------------------------------------
# eval_runs CRUD
# ---------------------------------------------------------------------------


def save_eval_run(
    run_id: str,
    kind: str,
    mode: str,
    result: Dict[str, Any],
    cost_estimate_yuan: Optional[float] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Upsert one evaluation run. Idempotent: same run_id → row replaced.

    ``run_id`` is caller-computed (deterministic, e.g. ``agent-llm-2026-09-01``),
    which makes re-running the same-day same-mode evaluation a no-op update
    instead of unbounded row growth.
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO eval_runs (
                id, kind, mode, dataset, created_at, total, passed, pass_rate,
                tools_accuracy, task_completion_rate, avg_steps, p95_ms,
                total_tokens, cost_estimate_yuan, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                kind,
                mode,
                str(result.get("dataset") or ""),
                _now_iso(),
                int(result.get("total") or 0),
                int(result.get("passed") or 0),
                float(result.get("pass_rate") or 0.0),
                _opt_float(result.get("tools_accuracy")),
                _opt_float(result.get("task_completion_rate")),
                _opt_float(result.get("avg_steps")),
                _opt_float((result.get("latency_ms") or {}).get("p95")),
                _opt_int(result.get("total_tokens")),
                _opt_float(cost_estimate_yuan),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def get_eval_run(run_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Fetch one run; detail_json deserialized back into dict."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM eval_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_with_detail(row)
    finally:
        conn.close()


def list_eval_runs(
    kind: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Trend query: newest first, optional kind/mode filter.

    With deterministic daily ids, listing mode='llm' returns one row per
    evaluation day → the trend of pass rate / p95 / cost over time.
    """
    conn = get_connection(db_path)
    try:
        clauses = []
        params: List[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if mode:
            clauses.append("mode = ?")
            params.append(mode)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(int(limit))
        cur = conn.execute(
            f"""
            SELECT * FROM eval_runs
            {where}
            ORDER BY created_at DESC LIMIT ?
            """,
            params,
        )
        return [_row_with_detail(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_with_detail(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    try:
        out["detail"] = json.loads(out.pop("detail_json"))
    except (json.JSONDecodeError, TypeError, KeyError):
        out["detail"] = None
    return out
