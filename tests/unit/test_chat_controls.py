"""Chat 端点控制参数单测(Task 5)。

覆盖范围:
  - ChatRequest:history_limit 独立于 max_tokens,默认值 20,范围 [1, 100]
  - _all_below_threshold:用 retrieval_confidence 判断,空 citations=True,
    缺 confidence 保守返回 False,全部 < threshold 才 True
  - _maybe_websearch:不再接收 threshold 参数
  - format_chunks_only:透传 retrieval_confidence / retrieval_mode
  - build_messages:history_limit 截取最后 N 条,旧调用默认 20 兼容
  - retrieve diagnostics:每个 degradation 调用一次 save_degradation_event,
    写入失败不遮蔽主链
  - 检索完全失败时仍记录 retrieval_failed 降级事件

不依赖 Qdrant / Aliyun API。retriever / sqlite / format_chunks_only / build_messages
均可直接调用;_chat_events 的副作用(retrieve / websearch)使用 monkeypatch。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from backend.api.chat import (
    ChatRequest,
    _all_below_threshold,
    _chat_events,
    _maybe_websearch,
)
from backend.core.rag import llm as rag_llm


# ---------------------------------------------------------------------------
# 模块级隔离:禁止任何 test 写入真实 data/db.sqlite。
#
# _chat_events 进入"答案持久化"分支时会调 save_message + touch_session;
# 多个 _chat_events 测试只 monkeypatch 了 retrieve / websearch / stream /
# save_degradation_event,却漏掉这两个写入函数,导致流到 answer 时悄悄写
# E:/data/db.sqlite。本 fixture 在每个用例前 no-op 它们,任何需要不同行为的
# 用例可在自身 monkeypatch 覆盖 autouse。
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _block_real_sqlite_writes(monkeypatch):
    from backend.api import chat as chat_mod

    monkeypatch.setattr(chat_mod, "save_message", lambda *a, **kw: 0)
    monkeypatch.setattr(chat_mod, "touch_session", lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# ChatRequest:history_limit 字段
# ---------------------------------------------------------------------------


class TestChatRequestHistoryLimit:
    def test_history_limit_is_independent_from_max_tokens(self):
        payload = ChatRequest(question="问题", max_tokens=2000, history_limit=7)
        assert payload.history_limit == 7
        assert payload.max_tokens == 2000

    def test_history_limit_default_is_50(self):
        """v1.1.0 PR#2: 默认从 20 提到 50(对齐 sessions.history_limit / REQ-6)。"""
        payload = ChatRequest(question="问题")
        assert payload.history_limit == 50

    def test_history_limit_lower_bound(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="问题", history_limit=0)

    def test_history_limit_upper_bound(self):
        with pytest.raises(ValidationError):
            ChatRequest(question="问题", history_limit=101)


# ---------------------------------------------------------------------------
# _all_below_threshold:用 retrieval_confidence,缺 confidence 保守 False
# ---------------------------------------------------------------------------


class TestAllBelowThreshold:
    def test_empty_citations_is_true(self):
        """无引用 -> 视为低于阈值,触发 websearch(与旧行为兼容)。"""
        assert _all_below_threshold([], 0.6) is True

    def test_uses_confidence_not_rrf_score(self):
        """retrieval_confidence 高于阈值时即使 rrf score 极低,也不应触发 websearch。"""
        citations = [
            {"index": 1, "source": "a.md", "score": 0.02, "retrieval_confidence": 0.8}
        ]
        assert _all_below_threshold(citations, 0.6) is False

    def test_missing_confidence_is_conservative(self):
        """confidence 缺失 -> 保守返回 False,避免向量腿故障时误联网。"""
        citations = [{"index": 1, "source": "a.md", "score": 0.02}]
        assert _all_below_threshold(citations, 0.6) is False

    def test_all_confidence_below_threshold(self):
        """全部 confidence < threshold -> True,触发 websearch。"""
        citations = [
            {"index": 1, "source": "a.md", "retrieval_confidence": 0.1},
            {"index": 2, "source": "b.md", "retrieval_confidence": 0.2},
        ]
        assert _all_below_threshold(citations, 0.6) is True

    def test_mixed_confidence_some_below_some_above(self):
        citations = [
            {"index": 1, "source": "a.md", "retrieval_confidence": 0.1},
            {"index": 2, "source": "b.md", "retrieval_confidence": 0.9},
        ]
        assert _all_below_threshold(citations, 0.6) is False


# ---------------------------------------------------------------------------
# _maybe_websearch:删除未使用 threshold 参数
# ---------------------------------------------------------------------------


class TestMaybeWebsearchSignature:
    def test_signature_no_threshold(self):
        import inspect

        sig = inspect.signature(_maybe_websearch)
        assert "threshold" not in sig.parameters


# ---------------------------------------------------------------------------
# format_chunks_only:透传 retrieval_confidence / retrieval_mode
# ---------------------------------------------------------------------------


class TestFormatChunksOnlyConfidence:
    def test_exposes_confidence_and_mode(self):
        out = rag_llm.format_chunks_only([
            {
                "source": "a.md",
                "text": "内容",
                "score": 0.7,
                "retrieval_confidence": 0.81,
                "retrieval_mode": "hybrid",
            }
        ])
        assert out["citations"][0]["retrieval_confidence"] == 0.81
        assert out["citations"][0]["retrieval_mode"] == "hybrid"

    def test_passthrough_without_recomputation(self):
        """置信度字段未被改写或重新计算,原样透传。"""
        raw = {
            "source": "b.md",
            "text": "abc",
            "score": 0.5,
            "retrieval_confidence": 0.123,
            "retrieval_mode": "vector_only",
        }
        out = rag_llm.format_chunks_only([raw])
        cite = out["citations"][0]
        assert cite["retrieval_confidence"] == 0.123
        assert cite["retrieval_mode"] == "vector_only"
        # 既有 index/source/snippet/可选 score 不变
        assert cite["index"] == 1
        assert cite["source"] == "b.md"
        assert cite["snippet"] == "abc"
        assert cite["score"] == 0.5

    def test_optional_fields_absent_are_omitted(self):
        """未提供 retrieval_confidence / retrieval_mode 时,该字段不出现在 citation 中。"""
        out = rag_llm.format_chunks_only([
            {"source": "c.md", "text": "x", "score": 0.4}
        ])
        cite = out["citations"][0]
        assert "retrieval_confidence" not in cite
        assert "retrieval_mode" not in cite


# ---------------------------------------------------------------------------
# build_messages:history_limit 截取
# ---------------------------------------------------------------------------


class TestBuildMessagesHistoryLimit:
    def test_respects_history_limit(self):
        history = [{"role": "user", "content": str(i)} for i in range(10)]
        messages = rag_llm.build_messages(
            question="当前问题",
            context_chunks=[],
            history=history,
            history_limit=3,
        )
        user_text = messages[-1]["content"]
        assert "7" in user_text and "9" in user_text
        assert "6" not in user_text

    def test_old_call_default_history_limit_is_20(self):
        """旧调用(不传 history_limit)默认 20,history 末尾 20 条全部保留。"""
        history = [{"role": "user", "content": f"msg-{i}"} for i in range(30)]
        messages = rag_llm.build_messages(
            question="当前问题",
            context_chunks=[],
            history=history,
        )
        user_text = messages[-1]["content"]
        # 默认 history_limit=20 -> 保留 msg-10..msg-29,丢弃 msg-0..msg-9
        assert "msg-29" in user_text
        assert "msg-10" in user_text
        assert "msg-9" not in user_text
        assert "msg-0" not in user_text

    def test_history_limit_clamped_to_at_least_1(self):
        """history_limit <=0 时 clamp 到 1,避免空 history。"""
        history = [{"role": "user", "content": "only"}]
        messages = rag_llm.build_messages(
            question="q",
            context_chunks=[],
            history=history,
            history_limit=0,
        )
        user_text = messages[-1]["content"]
        assert "only" in user_text


# ---------------------------------------------------------------------------
# _chat_events:retrieve diagnostics → save_degradation_event
# ---------------------------------------------------------------------------


def _run_events(payload):
    """Drain the async generator into a list of SSE event dicts.

    Uses an explicit ``new_event_loop()`` (closed in ``finally``) to avoid
    Python 3.12's ``DeprecationWarning: There is no current event loop``
    from ``asyncio.get_event_loop()``. Pure test helper — does not change
    production semantics.
    """

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


class TestRetrievalDiagnostics:
    def test_degradations_recorded_as_events(self, monkeypatch):
        """retrieve diagnostics 中每个 degradation 触发一次 save_degradation_event。"""
        from backend.api import chat as chat_mod

        recorded: List[Dict[str, Any]] = []

        def _fake_save(session_id, query, source, reason, model=None, **kwargs):
            recorded.append(
                {
                    "session_id": session_id,
                    "query": query,
                    "source": source,
                    "reason": reason,
                    "model": model,
                }
            )
            return 1

        monkeypatch.setattr(chat_mod, "save_degradation_event", _fake_save)

        def _fake_retrieve(question, **kwargs):
            diag = kwargs.get("diagnostics")
            if diag is not None:
                diag.update(
                    {
                        "retrieval_mode": "hybrid",
                        "degradations": ["vector_failed"],
                        "vector_error": "boom",
                        "keyword_error": None,
                    }
                )
            return [
                {
                    "source": "a.md",
                    "text": "hello",
                    "score": 0.5,
                    "retrieval_confidence": 0.7,
                    "retrieval_mode": "hybrid",
                }
            ]

        monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)
        monkeypatch.setattr(chat_mod, "_maybe_websearch", lambda q: asyncio.sleep(0, result=None))

        # 不让 stream worker 真的发请求
        def _fake_stream(messages, **kwargs):
            if False:
                yield ""

        monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)

        # skip sqlite history
        monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])

        payload = ChatRequest(question="hi", session_id="sess-1")
        _run_events(payload)

        # 收到 answer 事件且包含 web_source=websearch 的 degradation 不会触发
        # (因为 retrieval_confidence=0.7 > threshold)
        retrieval_events = [
            r for r in recorded if r["source"] == "retrieval"
        ]
        assert any(r["reason"] == "vector_failed" for r in retrieval_events), (
            f"expected retrieval vector_failed event, got {recorded}"
        )

    def test_save_failure_does_not_mask_answer(self, monkeypatch):
        """save_degradation_event 抛错时,answer 事件仍正常下发。"""
        from backend.api import chat as chat_mod

        def _boom(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(chat_mod, "save_degradation_event", _boom)

        def _fake_retrieve(question, **kwargs):
            diag = kwargs.get("diagnostics")
            if diag is not None:
                diag.update(
                    {
                        "retrieval_mode": "hybrid",
                        "degradations": ["keyword_failed"],
                        "vector_error": None,
                        "keyword_error": "boom",
                    }
                )
            return [
                {
                    "source": "a.md",
                    "text": "hello",
                    "score": 0.5,
                    "retrieval_confidence": 0.7,
                    "retrieval_mode": "hybrid",
                }
            ]

        monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)

        async def _fake_ws(q):
            return None

        monkeypatch.setattr(chat_mod, "_maybe_websearch", _fake_ws)

        def _fake_stream(messages, **kwargs):
            yield '{"type":"answer","content":"hi","citations":[1]}'

        monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)
        monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])

        payload = ChatRequest(question="hi", session_id="sess-2")
        events = _run_events(payload)

        kinds = [e["event"] for e in events]
        assert "answer" in kinds, f"answer missing, got kinds={kinds}"
        # 没有 error 事件
        assert "error" not in kinds

    def test_retrieval_failure_records_event(self, monkeypatch):
        """retrieve 完全失败时,error 事件前记录 retrieval_failed 降级,记录失败不遮蔽原 error。"""
        from backend.api import chat as chat_mod

        def _save_dispatch(session_id, query, source, reason, model=None):
            # retrieval_failed 写入故意抛错,验证日志兜底不遮蔽原 error SSE。
            if source == "retrieval":
                raise RuntimeError("disk full")
            return 1

        monkeypatch.setattr(chat_mod, "save_degradation_event", _save_dispatch)

        def _fake_retrieve(question, **kwargs):
            raise RuntimeError("vector legs failed")

        monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)
        monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])

        payload = ChatRequest(question="hi", session_id="sess-3")
        events = _run_events(payload)

        kinds = [e["event"] for e in events]
        # 仅有 error 事件,无 answer / draft
        assert "error" in kinds
        assert "answer" not in kinds
        # 即便 save_degradation_event 抛错,error 仍正常下发
        error_data = json.loads(events[-1]["data"])
        assert "知识库检索失败" in error_data.get("message", "")


# ---------------------------------------------------------------------------
# _chat_events:get_messages 使用 history_limit
# ---------------------------------------------------------------------------


class TestHistoryLimitPlumbing:
    def test_get_messages_called_with_history_limit(self, monkeypatch):
        from backend.api import chat as chat_mod

        captured: Dict[str, Any] = {}

        def _fake_get_messages(session_id, limit=None, **kwargs):
            captured["session_id"] = session_id
            captured["limit"] = limit
            return []

        monkeypatch.setattr(chat_mod, "get_messages", _fake_get_messages)

        def _fake_retrieve(question, **kwargs):
            return [
                {
                    "source": "a.md",
                    "text": "x",
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
            yield '{"type":"answer","content":"hi","citations":[1]}'

        monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)

        payload = ChatRequest(question="hi", session_id="sess-h", history_limit=12)
        _run_events(payload)

        assert captured["session_id"] == "sess-h"
        assert captured["limit"] == 12
