"""Agent loop 单测 (v2.0 PR#2 / 工单 T11)。

全部 mock LLM(chat_with_fallback_tools),不触网:
  - 单步直答 / 两步工具链(assistant tool_calls 回传 + role=tool 观测回填)
  - max_steps 预算耗尽 → 无 tools 收尾回答(budget_exhausted)
  - 相同 (name,args) 连续 2 次 → repeat_guard 强制收尾
  - 工具异常 → error observation 续跑
  - arguments JSON 解析失败 → error observation 续跑
  - 无 tool_calls 无 content → agent_no_action 降级事件 + 空回答
  - AGENT_MAX_STEPS env 覆盖与钳位
  - usage 累计 / kb_search citations 跨步连续编号 / history 截断
"""
from __future__ import annotations

import json

import pytest

from backend.core.agent import loop as agent_loop
from backend.core.agent import trajectory


@pytest.fixture()
def _no_degradation(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        agent_loop, "save_degradation_event", lambda **kw: recorded.append(kw) or 1
    )
    # 轨迹门面全部隔离,单测不触 SQLite
    monkeypatch.setattr(trajectory, "start_run", lambda *a, **kw: "run-test")
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


def _fake_llm(responses, tools_seen=None):
    """按次序返回 (content, tool_calls, model, reason, usage);记录每次入参。"""
    calls = []

    def _fn(messages, *, primary_model, tools=None, **kwargs):
        calls.append({"messages": messages, "tools": tools})
        resp = responses.pop(0)
        if tools_seen is not None and tools is not None:
            tools_seen.append(True)
        return (
            resp.get("content", ""),
            resp.get("tool_calls", []),
            "qwen3.6-plus",
            "primary",
            resp.get("usage"),
        )

    return _fn, calls


def test_single_step_direct_answer(monkeypatch, _no_degradation):
    fn, calls = _fake_llm([{"content": "最终回答 [1]", "usage": {"input_tokens": 10, "output_tokens": 5}}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("问题"))

    types = [e["type"] for e in events]
    assert types == ["step_start", "answer"]
    answer = events[-1]
    assert answer["content"] == "最终回答 [1]"
    assert answer["finish_reason"] == "completed"
    assert answer["budget_exhausted"] is False
    assert answer["agent"]["run_id"] == "run-test"
    assert answer["agent"]["total_in"] == 10 and answer["agent"]["total_out"] == 5
    # 首次调用应带 TOOLS;messages 结构:system + user question
    assert calls[0]["tools"] == agent_loop.TOOLS
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["messages"][-1] == {"role": "user", "content": "问题"}


def test_two_step_tool_chain(monkeypatch, _no_degradation):
    responses = [
        {"content": "", "tool_calls": [_tool_call("calculator", '{"expression": "6*7"}')]},
        {"content": "答案是 42"},
    ]
    fn, calls = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("算一下"))
    types = [e["type"] for e in events]
    assert types == [
        "step_start", "tool_call", "tool_result",
        "step_start", "answer",
    ]
    assert events[1]["args"] == {"expression": "6*7"}
    result = events[2]
    assert result["ok"] is True and result["excerpt"] == "42"
    assert result["latency_ms"] >= 0

    # 第二次调用:assistant 消息带回 tool_calls,观测以 role=tool + id 回填
    second = calls[1]["messages"]
    assistant_msg = second[2]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["tool_calls"][0]["id"] == "call_1"
    tool_msg = second[3]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_1"
    assert json.loads(tool_msg["content"])["result"] == 42

    answer = events[-1]
    assert answer["agent"]["tools_used"] == ["calculator"]
    assert answer["finish_reason"] == "completed"


def test_budget_exhausted_wrap_up_without_tools(monkeypatch, _no_degradation):
    responses = [
        {"content": "", "tool_calls": [_tool_call("get_current_time", "{}", "c1")]},
        {"content": "", "tool_calls": [_tool_call("get_current_time", '{"x": 1}', "c2")]},
        {"content": "收尾回答"},
    ]
    fn, calls = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("时间问题", max_steps=2))
    answer = events[-1]
    assert answer["type"] == "answer"
    assert answer["budget_exhausted"] is True
    assert answer["finish_reason"] == "budget_exhausted"
    assert answer["content"] == "收尾回答"
    # 收尾调用不带 tools
    assert calls[2]["tools"] is None
    assert len(calls) == 3


def test_repeat_same_call_forces_wrap_up(monkeypatch, _no_degradation):
    same = {"content": "", "tool_calls": [_tool_call("calculator", '{"expression": "1+1"}')]}
    responses = [same, dict(same), {"content": "好了好了"}]
    fn, calls = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("重复问题", max_steps=8))
    answer = events[-1]
    assert answer["finish_reason"] == "repeat_guard"
    assert answer["budget_exhausted"] is False
    # 两次相同调用后立即收尾:共 3 次 LLM 调用(第 2 步没走完就收尾)
    assert len(calls) == 3


def test_tool_exception_becomes_error_observation_and_continues(monkeypatch, _no_degradation):
    def _boom(name, args):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(agent_loop, "execute_tool", _boom)
    responses = [
        {"content": "", "tool_calls": [_tool_call("kb_search", '{"query": "x"}')]},
        {"content": "改用已有信息回答"},
    ]
    fn, _ = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("q"))
    result = [e for e in events if e["type"] == "tool_result"][0]
    assert result["ok"] is False
    answer = events[-1]
    assert result["ok"] is False
    assert answer["content"] == "改用已有信息回答"
    assert answer["agent"]["tools_used"] == ["kb_search"]


def test_invalid_arguments_json_falls_back(monkeypatch, _no_degradation):
    responses = [
        {"content": "", "tool_calls": [_tool_call("calculator", "{bad json")]},
        {"content": "继续回答"},
    ]
    fn, calls = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("q"))
    tc_event = [e for e in events if e["type"] == "tool_call"][0]
    assert tc_event["args"] == {} and "解析失败" in tc_event["args_error"]
    tr_event = [e for e in events if e["type"] == "tool_result"][0]
    assert tr_event["ok"] is False
    # error observation 仍回填给模型
    tool_msg = calls[1]["messages"][3]
    assert json.loads(tool_msg["content"])["error"].startswith("arguments 解析失败")
    assert events[-1]["content"] == "继续回答"


def test_no_action_records_degradation(monkeypatch, _no_degradation):
    fn, _ = _fake_llm([{"content": ""}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    events = list(agent_loop.run_agent("空响应问题"))
    answer = events[-1]
    assert answer["content"] == "" and answer["finish_reason"] == "no_action"
    assert any(r.get("reason") == "agent_no_action" for r in _no_degradation)


def test_agent_max_steps_env_override_and_clamp(monkeypatch, _no_degradation):
    monkeypatch.setenv("AGENT_MAX_STEPS", "3")
    assert agent_loop._resolve_max_steps(None) == 3
    assert agent_loop._resolve_max_steps(99) == agent_loop.HARD_MAX_STEPS
    assert agent_loop._resolve_max_steps(0) == 1
    monkeypatch.setenv("AGENT_MAX_STEPS", "not-a-number")
    assert agent_loop._resolve_max_steps(None) == agent_loop.DEFAULT_MAX_STEPS


def test_usage_accumulated_across_steps(monkeypatch, _no_degradation):
    responses = [
        {
            "content": "",
            "tool_calls": [_tool_call("get_current_time", "{}")],
            "usage": {"input_tokens": 100, "output_tokens": 20},
        },
        {"content": "done", "usage": {"input_tokens": 50, "output_tokens": 30}},
    ]
    fn, _ = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    answer = list(agent_loop.run_agent("q"))[-1]
    assert answer["agent"]["total_in"] == 150 and answer["agent"]["total_out"] == 50
    assert answer["agent"]["steps"] == 2


def test_kb_search_citations_numbering_continuous_across_steps(monkeypatch, _no_degradation):
    """发现 #1:loop 传 kb_offset,observation 输出全局编号,聚合直接 extend。"""
    real_execute = agent_loop.execute_tool
    kb_payloads = [
        [{"index": 1, "source": "a.md", "snippet": "甲"}, {"index": 2, "source": "b.md", "snippet": "乙"}],
        [{"index": 3, "source": "c.md", "snippet": "丙"}],
    ]

    def _fake_execute(name, args, **kwargs):
        if name == "kb_search":
            payload = kb_payloads.pop(0)
            # kwargs["kb_offset"] 应等于已聚合 citation 数
            assert kwargs.get("kb_offset") == (0 if len(kb_payloads) == 1 else 2)
            return {"ok": True, "count": len(payload), "ctx": "...", "citations": payload}
        return real_execute(name, args)

    monkeypatch.setattr(agent_loop, "execute_tool", _fake_execute)
    responses = [
        {"content": "", "tool_calls": [_tool_call("kb_search", '{"query": "q1"}', "k1")]},
        {"content": "", "tool_calls": [_tool_call("kb_search", '{"query": "q2"}', "k2")]},
        {"content": "汇总回答"},
    ]
    fn, calls = _fake_llm(responses)
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)

    answer = list(agent_loop.run_agent("q"))[-1]
    indexes = [c["index"] for c in answer["citations"]]
    assert indexes == [1, 2, 3], "跨步编号必须连续"
    assert answer["citations"][2]["source"] == "c.md"
    # 回填模型的第二次 observation 也必须是全局编号(发现 #1 回归守护):
    # 第二次 LLM 调用(索引 1)messages 里最后一条 kb_search tool 消息
    # (即本轮刚回填的),其 citations[0].index == 3
    kb_tool_msgs = [
        m
        for m in calls[1]["messages"]
        if m.get("role") == "tool" and m.get("name") == "kb_search"
    ]
    assert len(kb_tool_msgs) == 2, "两轮 kb_search 的观测都已回填"
    obs = json.loads(kb_tool_msgs[-1]["content"])
    assert [c["index"] for c in obs["citations"]] == [3]


def test_history_truncated_to_history_limit(monkeypatch, _no_degradation):
    fn, calls = _fake_llm([{"content": "ok"}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)
    history = [{"role": "user", "content": f"msg-{i}"} for i in range(10)]

    list(agent_loop.run_agent("新问题", history=history, history_limit=4))
    msgs = calls[0]["messages"]
    # system + 最后 4 条历史 + user question
    assert len(msgs) == 6
    assert msgs[1]["content"] == "msg-6"
    assert msgs[-2]["content"] == "msg-9"


def test_llm_failure_yields_error_event(monkeypatch, _no_degradation):
    def _fail(*args, **kwargs):
        raise RuntimeError("all retries failed")

    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", _fail)
    events = list(agent_loop.run_agent("q"))
    assert events[-1] == {"type": "error", "message": "AI 调用失败: all retries failed"}
