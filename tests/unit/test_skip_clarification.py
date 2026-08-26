"""v1.1.0 PR#3 (ui-feedback) Task 3.1 — skip_clarification 字段单测。

PRD REQ-4:用户点"按原问题回答 / 跳过反问"按钮时,前端用
``skip_clarification=true`` 重新发原问题,后端若 LLM 仍要走反问路径,
应改走 answer 路径。

本文件覆盖:
  - ChatRequest 字段契约(存在 + 默认 False)
  - SSE handler 在 LLM 返回 clarify 时改写为 answer 的行为
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest

from backend.api.chat import ChatRequest, _chat_events


# ---------------------------------------------------------------------------
# ChatRequest 字段契约
# ---------------------------------------------------------------------------


def test_chat_request_has_skip_clarification_field():
    """ChatRequest 接受 skip_clarification bool 字段。"""
    req = ChatRequest(question="test", skip_clarification=True)
    assert req.skip_clarification is True


def test_chat_request_skip_clarification_default_is_false():
    """默认不跳过反问,保留 LLM 自然行为。"""
    req = ChatRequest(question="test")
    assert req.skip_clarification is False


# ---------------------------------------------------------------------------
# _chat_events:skip_clarification 改写 clarify → answer
# ---------------------------------------------------------------------------


def _drain_events(payload: ChatRequest) -> List[Dict[str, Any]]:
    """Drain the async generator into a list of SSE event dicts."""

    async def _drain():
        out: List[Dict[str, Any]] = []
        async for ev in _chat_events(payload):
            out.append(ev)
        return out

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_drain())
    finally:
        loop.close()


def _patch_chat_skip_clarification(monkeypatch, llm_stream_text: str):
    """注入 retrieve / websearch / LLM stream,避免触达真实后端。

    llm_stream_text 应是合法 JSON 协议串(如
    ``{"type":"clarify","question":"你是哪家店?","citations":[1]}``)。
    """
    from backend.api import chat as chat_mod

    def _fake_retrieve(question, **kwargs):
        return [
            {
                "source": "a.md",
                "text": "ctx",
                "score": 0.5,
                "retrieval_confidence": 0.8,
                "retrieval_mode": "hybrid",
            }
        ]

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)

    async def _fake_ws(q):
        return None

    monkeypatch.setattr(chat_mod, "_maybe_websearch", _fake_ws)

    def _fake_stream(messages, **kwargs):
        yield llm_stream_text

    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)
    monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])
    monkeypatch.setattr(chat_mod, "save_message", lambda *a, **kw: 0)
    monkeypatch.setattr(chat_mod, "touch_session", lambda *a, **kw: None)


def _last_answer_payload(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """取最后一个 answer 事件的 data 字段(JSON dict)。"""
    answer_events = [e for e in events if e["event"] == "answer"]
    assert answer_events, f"expected answer event, got kinds={[e['event'] for e in events]}"
    return json.loads(answer_events[-1]["data"])


@pytest.fixture(autouse=True)
def _block_real_sqlite_writes(monkeypatch):
    """模块级隔离:禁止任何 test 写入真实 data/db.sqlite(与 test_chat_controls 一致)。"""
    from backend.api import chat as chat_mod

    monkeypatch.setattr(chat_mod, "save_message", lambda *a, **kw: 0)
    monkeypatch.setattr(chat_mod, "touch_session", lambda *a, **kw: None)


def test_skip_clarification_rewrites_clarify_to_answer(monkeypatch):
    """skip_clarification=True + LLM 返回 clarify → answer 路径,不下发 question。"""
    _patch_chat_skip_clarification(
        monkeypatch,
        '{"type":"clarify","question":"你是哪家店?","citations":[1]}',
    )
    payload = ChatRequest(
        question="本季度营收情况", skip_clarification=True
    )
    events = _drain_events(payload)
    answer = _last_answer_payload(events)
    assert answer["type"] == "answer", (
        f"skip_clarification should rewrite clarify→answer, got type={answer.get('type')}"
    )
    # 不应再下发 LLM 的反问 question 字段
    assert "question" not in answer, (
        f"clarify question should be cleared, got answer={answer}"
    )
    # 改写后正文是占位说明(LLM 协议无 fallback_answer 字段)
    assert "已按原问题给出回答" in answer["content"]
    assert "本季度营收情况" in answer["content"]
    # citations 仍保留
    assert answer["citations"]


def test_skip_clarification_false_keeps_clarify(monkeypatch):
    """skip_clarification=False → LLM 反问原样下发(向后兼容,旧路径不变)。"""
    _patch_chat_skip_clarification(
        monkeypatch,
        '{"type":"clarify","question":"你是哪家店?","citations":[1]}',
    )
    payload = ChatRequest(
        question="本季度营收情况", skip_clarification=False
    )
    events = _drain_events(payload)
    answer = _last_answer_payload(events)
    assert answer["type"] == "clarify"
    assert answer.get("question") == "你是哪家店?"


def test_skip_clarification_uses_fallback_answer_when_provided(monkeypatch):
    """LLM 协议未来若带 fallback_answer 字段,优先使用,不再下发占位文本。"""
    _patch_chat_skip_clarification(
        monkeypatch,
        '{"type":"clarify","question":"你是哪家店?","fallback_answer":"按当前可见资料无法回答,请补充。","citations":[1]}',
    )
    payload = ChatRequest(
        question="本季度营收情况", skip_clarification=True
    )
    events = _drain_events(payload)
    answer = _last_answer_payload(events)
    assert answer["type"] == "answer"
    assert answer["content"] == "按当前可见资料无法回答,请补充。"
    assert "question" not in answer
