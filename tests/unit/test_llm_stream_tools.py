"""chat_with_fallback_tools_stream 单测 (v2.1.0)。

全部 mock urllib.request.urlopen,不触网。覆盖:
  - _post_chat_stream_with_tools:content delta 透传 / tool_calls 分片按 index
    聚合(arguments 分段拼接)/ usage 提取 / finish_reason 提取
  - 归一化形状与 _extract_tool_calls 一致(id/type/function.name/arguments)
  - 包装器降级链:L0 失败 → L1 重试成功(记 primary_retry_ok)
  - 降级切换:L0/L1 失败 → L2 备用模型成功(reason=fallback)
  - mid-stream 失败(已 yield delta)→ 不重试,原样抛出
  - usage 走 _log_token_usage(cost-alert 计量)
"""
from __future__ import annotations

import json

import pytest

from backend.core.rag import llm as rag_llm


class _FakeResp:
    """模拟 urlopen 返回:按行迭代的 SSE 字节流。"""

    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sse(*chunks: dict) -> list[str]:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}" for c in chunks]
    lines.append("data: [DONE]")
    return lines


def _patch_urlopen(monkeypatch, responses):
    """按调用次序返回预置响应;记录每次请求体。"""
    sent_bodies: list[dict] = []
    calls: list[_FakeResp] = []

    def _fake_urlopen(req, timeout=None):
        sent_bodies.append(json.loads(req.data.decode("utf-8")))
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        calls.append(resp)
        return resp

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    return sent_bodies


def test_stream_with_tools_deltas_and_tool_call_aggregation(monkeypatch):
    """content delta 透传;tool_calls 分片按 index 聚合,arguments 拼接。"""
    responses = [
        _FakeResp(
            _sse(
                {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
                {"choices": [{"index": 0, "delta": {"content": "你好，"}}]},
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "kb_search",
                                            "arguments": '{"que',
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": 'ry": "会员"}'},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                },
                {"choices": [], "usage": {"input_tokens": 10, "output_tokens": 5}},
            )
        )
    ]
    bodies = _patch_urlopen(monkeypatch, responses)

    events = list(
        rag_llm._post_chat_stream_with_tools(
            "sk-test", "qwen3.6-plus", [{"role": "user", "content": "q"}],
            tools=[{"type": "function", "function": {"name": "kb_search"}}],
        )
    )

    deltas = [e for e in events if e["type"] == "delta"]
    assert [d["text"] for d in deltas] == ["你好，"]
    final = events[-1]
    assert final["type"] == "final" and final["content"] == "你好，"
    assert final["finish_reason"] == "tool_calls"
    assert final["usage"] == {"input_tokens": 10, "output_tokens": 5}
    # 归一化形状与 _extract_tool_calls 一致;arguments 分片拼接还原
    assert final["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "kb_search", "arguments": '{"query": "会员"}'},
        }
    ]
    # 请求体带 tools + stream
    assert bodies[0]["stream"] is True and bodies[0]["tools"]


def test_stream_wrapper_l1_retry_after_first_failure(monkeypatch):
    """L0 失败(未 yield 任何 delta)→ L1 重试成功,reason=primary。"""
    responses = [
        RuntimeError("connection reset"),  # L0
        _FakeResp(  # L1
            _sse(
                {"choices": [{"index": 0, "delta": {"content": "ok"}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            )
        ),
    ]
    _patch_urlopen(monkeypatch, responses)
    recorded = []
    monkeypatch.setattr(rag_llm, "_record_event", lambda *a, **kw: recorded.append(kw) or kw)
    monkeypatch.setattr(rag_llm, "_log_token_usage", lambda *a, **kw: None)
    monkeypatch.setattr(rag_llm.time, "sleep", lambda s: None)

    events = list(
        rag_llm.chat_with_fallback_tools_stream(
            [{"role": "user", "content": "q"}],
            primary_model="qwen3.6-plus",
            session_id="s1",
            query_for_event="q",
        )
    )

    deltas = [e for e in events if e["type"] == "delta"]
    assert [d["text"] for d in deltas] == ["ok"]
    final = events[-1]
    assert final["model"] == "qwen3.6-plus" and final["reason"] == "primary"
    reasons = [r.get("reason") for r in recorded]
    assert "attempt_fail:RuntimeError" in reasons
    assert "primary_retry_ok" in reasons


def test_stream_wrapper_switches_to_fallback_model(monkeypatch):
    """L0/L1 全失败 → L2 切备用模型成功,reason=fallback。"""
    responses = [
        RuntimeError("boom-1"),
        RuntimeError("boom-2"),
        _FakeResp(
            _sse(
                {"choices": [{"index": 0, "delta": {"content": "备用回答"}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            )
        ),
    ]
    _patch_urlopen(monkeypatch, responses)
    recorded = []
    monkeypatch.setattr(rag_llm, "_record_event", lambda *a, **kw: recorded.append(kw) or kw)
    monkeypatch.setattr(rag_llm, "_log_token_usage", lambda *a, **kw: None)
    monkeypatch.setattr(rag_llm.time, "sleep", lambda s: None)

    events = list(
        rag_llm.chat_with_fallback_tools_stream(
            [{"role": "user", "content": "q"}],
            primary_model="qwen3.6-plus",
        )
    )
    final = events[-1]
    assert final["model"] == rag_llm.DEFAULT_MODEL_MAX and final["reason"] == "fallback"
    reasons = [r.get("reason") for r in recorded]
    assert "primary_to_fallback" in reasons


def test_stream_wrapper_mid_stream_failure_does_not_retry(monkeypatch):
    """已 yield delta 后失败:静默重试会造成重复输出,必须原样抛出。"""

    # 第一次尝试:先正常产出 delta 的流,在读行中途抛错
    class _BrokenResp(_FakeResp):
        def __iter__(self):
            yield b'data: {"choices": [{"index": 0, "delta": {"content": "a"}}]}\n'
            raise RuntimeError("mid-stream reset")

    def _fake_urlopen(req, timeout=None):
        return _BrokenResp([])

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr(rag_llm, "_record_event", lambda *a, **kw: None)
    monkeypatch.setattr(rag_llm.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="mid-stream reset"):
        list(
            rag_llm.chat_with_fallback_tools_stream(
                [{"role": "user", "content": "q"}],
                primary_model="qwen3.6-plus",
            )
        )


def test_stream_wrapper_logs_usage_for_cost_metering(monkeypatch):
    """usage 经 _log_token_usage 落账,Agent 流式链路不缺 cost 计量。"""
    responses = [
        _FakeResp(
            _sse(
                {"choices": [{"index": 0, "delta": {"content": "x"}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"input_tokens": 7, "output_tokens": 3}},
            )
        )
    ]
    _patch_urlopen(monkeypatch, responses)
    logged = []
    monkeypatch.setattr(rag_llm, "_record_event", lambda *a, **kw: None)
    monkeypatch.setattr(
        rag_llm, "_log_token_usage", lambda *a: logged.append(a) or None
    )

    list(
        rag_llm.chat_with_fallback_tools_stream(
            [{"role": "user", "content": "q"}],
            primary_model="qwen3.6-plus",
        )
    )
    assert logged == [("qwen3.6-plus", 7, 3)]
