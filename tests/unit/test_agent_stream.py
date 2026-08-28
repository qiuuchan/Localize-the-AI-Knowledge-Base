"""Agent loop 流式单测 (v2.1.0)。

全部 mock chat_with_fallback_tools_stream,不触网。覆盖:
  - stream=True 单步直答:answer_delta 逐段下发,answer 为权威终态
  - usage 经 final 事件累计(cost-alert 计量不因流式缺失)
  - 模型先流出内容又决定调工具 → answer_reset 后继续工具链
  - 纯工具调用步骤(无 content delta)不产生 answer_delta/answer_reset
  - 预算耗尽收尾(_wrap_up)同样流式,且收尾调用不带 tools
  - 重复护栏(repeat_guard)收尾路径流式可用
  - 全链失败 → error 事件 + finish_run(error)
  - stream=False 默认契约与 v2.0 完全一致(无 answer_delta 事件)
"""
from __future__ import annotations

import pytest

from backend.core.agent import loop as agent_loop
from backend.core.agent import trajectory


@pytest.fixture()
def _no_degradation(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        agent_loop, "save_degradation_event", lambda **kw: recorded.append(kw) or 1
    )
    monkeypatch.setattr(trajectory, "start_run", lambda *a, **kw: "run-stream")
    monkeypatch.setattr(trajectory, "record_step", lambda *a, **kw: None)
    monkeypatch.setattr(
        trajectory,
        "finish_run",
        lambda *a, **kw: recorded.append({"finish_run": kw}) or "done",
    )
    return recorded


def _tool_call(name: str, arguments: str, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _final(content="", tool_calls=None, usage=None, reason="primary"):
    return {
        "type": "final",
        "content": content,
        "tool_calls": tool_calls or [],
        "finish_reason": "tool_calls" if tool_calls else "stop",
        "usage": usage,
        "model": "qwen3.6-plus",
        "reason": reason,
    }


def _fake_stream(steps, tools_seen=None):
    """按次序返回每步的流式事件列表;记录每次调用的 tools 入参。"""
    calls = []

    def _fn(messages, *, primary_model, tools=None, **kwargs):
        calls.append({"messages": messages, "tools": tools})
        if tools_seen is not None and tools is not None:
            tools_seen.append(True)
        events = steps.pop(0)

        def _gen():
            yield from events

        return _gen()

    return _fn, calls


def test_stream_single_step_answer_deltas(monkeypatch, _no_degradation):
    steps = [
        [
            {"type": "delta", "text": "最终"},
            {"type": "delta", "text": "回答"},
            _final(content="最终回答", usage={"input_tokens": 10, "output_tokens": 5}),
        ]
    ]
    fn, calls = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    events = list(agent_loop.run_agent("问题", stream=True))

    types = [e["type"] for e in events]
    assert types == ["step_start", "answer_delta", "answer_delta", "answer"]
    assert events[1]["delta"] == "最终" and events[2]["delta"] == "回答"
    answer = events[-1]
    assert answer["content"] == "最终回答"
    assert answer["finish_reason"] == "completed"
    assert answer["agent"]["total_in"] == 10 and answer["agent"]["total_out"] == 5
    assert calls[0]["tools"] == agent_loop.TOOLS


def test_stream_tool_call_after_deltas_resets_answer(monkeypatch, _no_degradation):
    """模型先吐内容又决定调工具:answer_reset 在 tool_call 之前,前端清空半截答案。"""
    steps = [
        [
            {"type": "delta", "text": "让我查一下"},
            _final(tool_calls=[_tool_call("calculator", '{"expression": "6*7"}')]),
        ],
        [
            {"type": "delta", "text": "答案是"},
            {"type": "delta", "text": " 42"},
            _final(content="答案是 42"),
        ],
    ]
    fn, calls = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    events = list(agent_loop.run_agent("算一下", stream=True))
    types = [e["type"] for e in events]
    assert types == [
        "step_start",
        "answer_delta",
        "answer_reset",
        "tool_call",
        "tool_result",
        "step_start",
        "answer_delta",
        "answer_delta",
        "answer",
    ]
    # reset 之后不应再有其后的 delta 累积歧义:answer 为权威终态
    assert events[-1]["content"] == "答案是 42"
    assert events[-1]["agent"]["tools_used"] == ["calculator"]
    # 第二步:assistant 消息原样带回 tool_calls,观测以 role=tool 回填
    second = calls[1]["messages"]
    assert second[2]["role"] == "assistant" and second[2]["tool_calls"][0]["id"] == "call_1"
    assert second[3]["role"] == "tool" and second[3]["tool_call_id"] == "call_1"


def test_stream_pure_tool_call_step_has_no_answer_events(monkeypatch, _no_degradation):
    """常规工具步骤(无 content delta)不产生 answer_delta/answer_reset。"""
    steps = [
        [_final(tool_calls=[_tool_call("get_current_time", "{}")])],
        [_final(content="现在")],
    ]
    fn, _ = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    events = list(agent_loop.run_agent("几点了", stream=True))
    types = [e["type"] for e in events]
    assert "answer_delta" not in types and "answer_reset" not in types
    assert types == ["step_start", "tool_call", "tool_result", "step_start", "answer"]


def test_stream_budget_exhausted_wrap_up_also_streams(monkeypatch, _no_degradation):
    """预算耗尽收尾:无 tools 调用且同样以 answer_delta 流式。"""
    steps = [
        [_final(tool_calls=[_tool_call("get_current_time", "{}", "c1")])],
        [_final(tool_calls=[_tool_call("get_current_time", '{"x": 1}', "c2")])],
        [
            {"type": "delta", "text": "收尾"},
            _final(content="收尾回答"),
        ],
    ]
    fn, calls = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    events = list(agent_loop.run_agent("时间问题", max_steps=2, stream=True))
    types = [e["type"] for e in events]
    assert "answer_delta" in types
    answer = events[-1]
    assert answer["budget_exhausted"] is True
    assert answer["finish_reason"] == "budget_exhausted"
    assert answer["content"] == "收尾回答"
    # 收尾调用不带 tools
    assert calls[2]["tools"] is None
    assert len(calls) == 3


def test_stream_repeat_guard_wrap_up_streams(monkeypatch, _no_degradation):
    same = {"type": "delta", "text": ""}
    steps = [
        [_final(tool_calls=[_tool_call("calculator", '{"expression": "1+1"}')])],
        [same, _final(tool_calls=[_tool_call("calculator", '{"expression": "1+1"}')])],
        [{"type": "delta", "text": "好了"}, _final(content="好了好了")],
    ]
    fn, _ = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    events = list(agent_loop.run_agent("重复问题", stream=True))
    answer = events[-1]
    assert answer["finish_reason"] == "repeat_guard"
    assert answer["content"] == "好了好了"


def test_stream_llm_failure_yields_error_event(monkeypatch, _no_degradation):
    def _fail(*args, **kwargs):
        raise RuntimeError("all retries failed")

    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", _fail)
    events = list(agent_loop.run_agent("q", stream=True))
    assert events[-1] == {"type": "error", "message": "AI 调用失败: all retries failed"}
    # 轨迹必须收口,run 不悬挂
    assert any("finish_run" in r for r in _no_degradation)


def test_stream_usage_accumulated_across_steps(monkeypatch, _no_degradation):
    steps = [
        [
            _final(
                tool_calls=[_tool_call("get_current_time", "{}")],
                usage={"input_tokens": 100, "output_tokens": 20},
            )
        ],
        [
            {"type": "delta", "text": "done"},
            _final(content="done", usage={"input_tokens": 50, "output_tokens": 30}),
        ],
    ]
    fn, _ = _fake_stream(steps)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools_stream", fn)

    answer = list(agent_loop.run_agent("q", stream=True))[-1]
    assert answer["agent"]["total_in"] == 150 and answer["agent"]["total_out"] == 50
    assert answer["agent"]["steps"] == 2


def test_non_stream_default_contract_unchanged(monkeypatch, _no_degradation):
    """stream=False(默认)走非流式函数,事件契约与 v2.0 一致。"""
    responses = [{"content": "直接回答"}]

    def _fn(messages, *, primary_model, tools=None, **kwargs):
        resp = responses.pop(0)
        return (resp.get("content", ""), [], "qwen3.6-plus", "primary", None)

    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", _fn)
    events = list(agent_loop.run_agent("q"))
    types = [e["type"] for e in events]
    assert types == ["step_start", "answer"]
    assert "answer_delta" not in types
