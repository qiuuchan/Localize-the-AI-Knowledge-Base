"""Agent endpoints (v2.0 PR#3 / 工单 T12).

POST /api/agent/chat  — SSE:status / step_start / tool_call / tool_result /
                        answer / error(cost-alert 阻断复用 chat.py 模式)
GET  /api/agent/runs      — 最近 run 列表
GET  /api/agent/runs/{id} — run 明细 + steps[](调试面板用)

与 /api/chat 双链路并存,现有 chat 契约不动(设计稿 §2.3)。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.api.dashboard import _read_cost_alert
from backend.core.agent.loop import run_agent
from backend.core.sqlite.agent_repo import get_run, get_run_steps, list_runs
from backend.core.sqlite.degradation_repo import save_degradation_event
from backend.core.sqlite.messages_repo import get_messages

router = APIRouter()

logger = logging.getLogger("kb_ai.agent")


class AgentChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(default=None)
    # max_steps 边界由 pydantic ge/le 强制:越界直接 422(验收项)
    max_steps: int = Field(default=8, ge=1, le=16)
    top_k: int = Field(default=5, ge=1, le=20)
    history_limit: int = Field(default=50, ge=1, le=100)
    model_name: Optional[str] = Field(default=None)
    model_name_max: Optional[str] = Field(default=None)
    # v2.1.0:token 级流式(answer_delta/answer_reset 事件,answer 仍为权威
    # 终态)。评测脚本等需要整段契约的调用方可显式传 false 回退 v2.0 行为。
    stream: bool = Field(default=True)


async def _agent_events(payload: AgentChatRequest) -> AsyncIterator[Dict[str, Any]]:
    # v1.3.0 cost-alert level>=3 阻断模式照搬 chat.py:136-171(含降级事件记录);
    # SSE 路径只能 yield error event,不能 raise(HTTPException 会撞
    # "response already started")。
    cost_alert = _read_cost_alert()
    if cost_alert.get("level", 0) >= 3:
        try:
            save_degradation_event(
                session_id=payload.session_id,
                query=payload.question,
                source="llm",
                reason=f"cost-alert block: ¥{cost_alert.get('month_yuan', 0):.0f}",
                model=None,
                component="LLM",
            )
        except Exception:
            logger.warning("failed to record cost-alert block event", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "message": "月度配额超限，已阻断 LLM 调用",
                    "reason": "monthly_cost_exceeded",
                    "month_yuan": cost_alert.get("month_yuan", 0),
                    "threshold": cost_alert.get("thresholds", {}).get("block", 1500),
                    "hint": "知识库检索与工具调用已一并阻断",
                },
                ensure_ascii=False,
            ),
        }
        return

    yield {
        "event": "status",
        "data": json.dumps(
            {"stage": "agent_start", "message": "Agent 循环启动..."},
            ensure_ascii=False,
        ),
    }

    history: List[Dict[str, Any]] = []
    if payload.session_id:
        try:
            msgs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: get_messages(payload.session_id, limit=payload.history_limit),
            )
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]
        except Exception:
            history = []

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _worker() -> None:
        try:
            for ev in run_agent(
                payload.question,
                history,
                max_steps=payload.max_steps,
                session_id=payload.session_id,
                top_k=payload.top_k,
                history_limit=payload.history_limit,
                model_name=payload.model_name,
                model_name_max=payload.model_name_max,
                stream=payload.stream,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, ("event", ev))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))
        except Exception as exc:  # 生成器本身不应抛;双保险转 error 事件
            loop.call_soon_threadsafe(
                queue.put_nowait, ("event", {"type": "error", "message": str(exc)[:500]})
            )
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    loop.run_in_executor(None, _worker)

    while True:
        kind, val = await queue.get()
        if kind == "done":
            break
        yield {"event": val["type"], "data": json.dumps(val, ensure_ascii=False)}


@router.post("/agent/chat")
def agent_chat(payload: AgentChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_agent_events(payload))


@router.get("/agent/runs")
def agent_runs(limit: int = 20) -> List[Dict[str, Any]]:
    return list_runs(limit=limit)


@router.get("/agent/runs/{run_id}")
def agent_run_detail(run_id: str) -> Dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    run["steps"] = get_run_steps(run_id)
    return run
