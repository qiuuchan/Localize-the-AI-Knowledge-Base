"""Trajectory facades (v2.0 PR#3 / 工单 T12).

start_run / record_step / finish_run — the three functions the agent loop
calls. Persistence failure NEVER blocks the main chain (对齐 llm.py 吞错哲学
与 §4.3):every facade swallows exceptions and returns None.

status mapping from loop finish_reason:
  completed/no_action → done; budget_exhausted/repeat_guard → budget_exhausted;
  error path → error (+error text).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from backend.core.sqlite import agent_repo

_STATUS_BY_FINISH_REASON = {
    "completed": "done",
    "no_action": "done",
    "budget_exhausted": "budget_exhausted",
    "repeat_guard": "budget_exhausted",
}


def status_for(finish_reason: str) -> str:
    return _STATUS_BY_FINISH_REASON.get(finish_reason, "done")


def start_run(
    question: str,
    *,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Create a running run row; returns run_id or None on failure."""
    try:
        run_id = str(uuid.uuid4())
        return agent_repo.create_run(run_id, question, session_id=session_id, model=model)
    except Exception:
        return None


def record_step(
    run_id: Optional[str],
    step_idx: int,
    type_: str,
    *,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    observation: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    if not run_id:
        return
    try:
        agent_repo.add_step(
            run_id,
            step_idx,
            type_,
            tool_name=tool_name,
            tool_args=tool_args,
            observation=observation,
            latency_ms=latency_ms,
        )
    except Exception:
        return


def finish_run(
    run_id: Optional[str],
    *,
    finish_reason: str,
    steps_count: int = 0,
    tools_used: Optional[List[str]] = None,
    model: Optional[str] = None,
    total_in: int = 0,
    total_out: int = 0,
    error: Optional[str] = None,
) -> Optional[str]:
    """Close a run; returns final status or None on failure/skip."""
    if not run_id:
        return None
    try:
        status = "error" if error else status_for(finish_reason)
        agent_repo.finish_run(
            run_id,
            status=status,
            steps_count=steps_count,
            tools_used=tools_used,
            model=model,
            total_in=total_in,
            total_out=total_out,
            error=error,
        )
        return status
    except Exception:
        return None
