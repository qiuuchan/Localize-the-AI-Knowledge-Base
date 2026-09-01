"""T10(v2.2)上下文工程:token 预算 + 滚动摘要单测。

覆盖(ADR-0003 配套):
  - estimate_tokens / estimate_message(s)_tokens:启发式计量口径
    (CJK ≈ 1 token/字符,ASCII ≈ 1 token/4 字符,×1.2 保守系数)
  - condense_history:预算内原样 / 超阈值压摘要 / 最近消息保留 /
    至少留 1 条 / 既有摘要合并 / 摘要截断到预算
  - heuristic_summary:格式 / 行级截断 / 最多 N 轮
  - build_messages:summary 参与上下文(及无 summary 回归)
  - sessions.summary 落库与迁移(ALTER TABLE 幂等)
  - run_agent:历史受 token 预算约束 + 摘要参与 + 回写落库
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.core import sqlite as sqlite_mod
from backend.core.agent import loop as agent_loop
from backend.core.agent import trajectory
from backend.core.rag import llm as rag_llm
from backend.core.rag.token_budget import (
    DEFAULT_HISTORY_TOKEN_BUDGET,
    KEEP_RATIO,
    condense_history,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    heuristic_summary,
    resolve_history_token_budget,
)
from backend.core.sqlite import sessions_repo


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def _long_history(turns: int = 6, chars_per_line: int = 2000) -> list:
    """构造超预算历史:N 轮一问一答,每行 chars_per_line 字符。"""
    history = []
    for i in range(turns):
        history.append(_msg("user", f"第{i + 1}轮问题" + "长" * chars_per_line))
        history.append(_msg("assistant", f"第{i + 1}轮回答" + "长" * chars_per_line))
    return history


# ---------------------------------------------------------------------------
# 计量口径
# ---------------------------------------------------------------------------


def test_estimate_tokens_cjk():
    # 8 个 CJK 字符 ≈ 8 token × 1.2 = 9.6 → 9
    assert estimate_tokens("餐饮门店经营分析") == 9
    assert estimate_tokens("") == 0


def test_estimate_tokens_ascii():
    # 20 个 ASCII ≈ 20/4 = 5 token × 1.2 = 6
    assert estimate_tokens("a" * 20) == 6


def test_estimate_tokens_mixed():
    mixed = "会员转化率 12.5%"  # CJK 6 + 非 CJK 5
    tokens = estimate_tokens(mixed)
    assert 7 <= tokens <= 14  # 6 + ceil(5/4)=2 → 8×1.2=9.6→10
    assert estimate_tokens("") == 0


def test_estimate_message_tokens_includes_role():
    m = _msg("user", "问题")
    assert estimate_message_tokens(m) == estimate_tokens("问题") + estimate_tokens("user") + 2


def test_estimate_messages_tokens_sums():
    msgs = [_msg("user", "问"), _msg("assistant", "答")]
    assert estimate_messages_tokens(msgs) == sum(
        estimate_message_tokens(m) for m in msgs
    )


def test_budget_env_override(monkeypatch):
    assert resolve_history_token_budget() == DEFAULT_HISTORY_TOKEN_BUDGET
    monkeypatch.setenv("HISTORY_TOKEN_BUDGET", "3000")
    assert resolve_history_token_budget() == 3000
    monkeypatch.setenv("HISTORY_TOKEN_BUDGET", "abc")
    assert resolve_history_token_budget() == DEFAULT_HISTORY_TOKEN_BUDGET
    monkeypatch.setenv("HISTORY_TOKEN_BUDGET", "100")
    assert resolve_history_token_budget() == 500  # 下限 500


# ---------------------------------------------------------------------------
# condense_history
# ---------------------------------------------------------------------------


def test_condense_under_budget_no_change():
    history = [_msg("user", "今天营业额多少?"), _msg("assistant", "约 3.2 万。")]
    kept, summary = condense_history(history, budget=6000, existing_summary="旧摘要")
    assert kept == history
    assert summary == "旧摘要"


def test_condense_over_budget_produces_summary():
    history = _long_history()
    assert estimate_messages_tokens(history) > DEFAULT_HISTORY_TOKEN_BUDGET
    kept, summary = condense_history(history, existing_summary="")
    assert kept
    assert len(kept) < len(history)
    assert "用户问:" in summary and "助手答:" in summary


def test_condense_keeps_recent_within_budget():
    # 每行 300 字符(单条 ≈ 370 token)使保留段能放下多条,预算语义可测
    history = _long_history(turns=6, chars_per_line=300)
    budget = 4000
    kept, summary = condense_history(history, budget=budget, existing_summary="")
    kept_tokens = estimate_messages_tokens(kept)
    assert kept_tokens <= int(budget * KEEP_RATIO)
    assert summary


def test_condense_keeps_at_least_one_message():
    huge = _msg("user", "巨" * 10000)
    kept, _ = condense_history([huge], budget=500)
    assert len(kept) == 1
    assert kept[0] is huge


def test_condense_merges_existing_summary():
    history = _long_history()
    kept, summary = condense_history(
        history, budget=4000, existing_summary="既有摘要内容"
    )
    assert "既有摘要内容" in summary
    assert "用户问:" in summary


def test_condense_summary_truncated_to_budget():
    history = _long_history(turns=10, chars_per_line=3000)
    budget = 2000
    kept, summary = condense_history(history, budget=budget, existing_summary="")
    summary_budget = budget - int(budget * KEEP_RATIO)
    assert estimate_tokens(summary) <= summary_budget


def test_condense_empty_history():
    kept, summary = condense_history([], existing_summary="x")
    assert kept == [] and summary == "x"


# ---------------------------------------------------------------------------
# heuristic_summary
# ---------------------------------------------------------------------------


def test_heuristic_summary_format():
    msgs = [_msg("user", "问一"), _msg("assistant", "答一"), _msg("user", "问二")]
    s = heuristic_summary(msgs)
    assert "用户问: 问一" in s
    assert "助手答: 答一" in s
    assert "用户问: 问二" in s


def test_heuristic_summary_line_truncation():
    msgs = [_msg("user", "长" * 500)]
    s = heuristic_summary(msgs, per_line_chars=100)
    assert "…" in s
    assert len(s) <= 100 + len("用户问: ") + 1


def test_heuristic_summary_max_turns():
    msgs = [
        m
        for i in range(10)
        for m in (_msg("user", f"q{i}"), _msg("assistant", f"a{i}"))
    ]
    s = heuristic_summary(msgs, max_turns=2)  # 只保留最后 2 轮
    assert "q0" not in s and "a0" not in s
    assert "q8" in s and "a9" in s


# ---------------------------------------------------------------------------
# build_messages:summary 参与上下文
# ---------------------------------------------------------------------------


def test_build_messages_includes_summary():
    messages = rag_llm.build_messages(
        question="现在呢?",
        context_chunks=[],
        history=[_msg("user", "旧问题")],
        summary="用户之前问了经营情况,助手给了 3.2 万的数字。",
    )
    user_text = messages[-1]["content"]
    assert "[会话摘要]" in user_text
    assert "用户之前问了经营情况" in user_text
    assert user_text.index("[会话摘要]") < user_text.index("[聊天历史]")


def test_build_messages_without_summary_regression():
    messages = rag_llm.build_messages(
        question="现在呢?",
        context_chunks=[],
        history=[_msg("user", "旧问题")],
    )
    user_text = messages[-1]["content"]
    assert "[会话摘要]" not in user_text
    assert "[聊天历史]" in user_text


# ---------------------------------------------------------------------------
# sessions.summary 落库与迁移
# ---------------------------------------------------------------------------


def test_session_summary_persist_roundtrip():
    with tempfile.TemporaryDirectory(prefix="kbsum-") as td:
        db = Path(td) / "t.sqlite"
        sqlite_mod.init_db(db_path=db)
        sid = sessions_repo.create_session(session_id="s1", db_path=db)
        assert sessions_repo.get_session_summary(sid, db_path=db) is None
        sessions_repo.set_session_summary(sid, "摘要内容", db_path=db)
        assert sessions_repo.get_session_summary(sid, db_path=db) == "摘要内容"
        # 幂等覆盖
        sessions_repo.set_session_summary(sid, "新摘要", db_path=db)
        assert sessions_repo.get_session_summary(sid, db_path=db) == "新摘要"


def test_session_migration_adds_summary_column_idempotent():
    """老库(无 summary 列)迁移后可读写;重复迁移不报错。"""
    with tempfile.TemporaryDirectory(prefix="kbmig-") as td:
        db = Path(td) / "t.sqlite"
        # 只建旧版 sessions 表(无 summary 列)
        conn = sqlite_mod.connection.get_connection(db)
        try:
            conn.executescript(
                """
                CREATE TABLE sessions (
                    session_id   TEXT PRIMARY KEY,
                    title        TEXT,
                    created_at   TEXT NOT NULL,
                    last_active  TEXT NOT NULL,
                    history_limit INTEGER NOT NULL DEFAULT 50
                );
                """
            )
            conn.commit()
        finally:
            conn.close()
        sessions_repo.migrate(db)
        sessions_repo.migrate(db)  # 幂等
        sid = sessions_repo.create_session(session_id="s2", db_path=db)
        sessions_repo.set_session_summary(sid, "迁移后可用", db_path=db)
        assert sessions_repo.get_session_summary(sid, db_path=db) == "迁移后可用"


# ---------------------------------------------------------------------------
# run_agent:历史 token 预算约束
# ---------------------------------------------------------------------------


@pytest.fixture()
def _no_degradation(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        agent_loop, "save_degradation_event", lambda **kw: recorded.append(kw) or 1
    )
    monkeypatch.setattr(trajectory, "start_run", lambda *a, **kw: "run-test")
    monkeypatch.setattr(trajectory, "record_step", lambda *a, **kw: None)
    monkeypatch.setattr(
        trajectory,
        "finish_run",
        lambda *a, **kw: recorded.append({"finish_run": kw}) or "done",
    )
    return recorded


def _fake_llm(responses):
    calls = []

    def _fn(messages, *, primary_model, tools=None, **kwargs):
        calls.append({"messages": messages, "tools": tools})
        resp = responses.pop(0)
        return (
            resp.get("content", ""),
            resp.get("tool_calls", []),
            "qwen3.6-plus",
            "primary",
            resp.get("usage"),
        )

    return _fn, calls


def test_run_agent_condenses_over_budget_history(monkeypatch, _no_degradation):
    """历史超 token 预算时:进入 LLM 的消息含 [会话摘要] system 段,且
    超预算的早期轮次不进 messages(上下文受预算约束)。"""
    fn, calls = _fake_llm([{"content": "最终回答", "usage": {"input_tokens": 5, "output_tokens": 3}}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)
    monkeypatch.setenv("HISTORY_TOKEN_BUDGET", "1500")

    history = [
        _msg("user", f"早期问题{i}" + "长" * 800) for i in range(4)
    ] + [_msg("assistant", f"早期回答{i}" + "长" * 800) for i in range(4)]
    # 全量必超 1500;保留段只含最近消息
    events = list(agent_loop.run_agent("新问题", history))
    assert events[-1]["type"] == "answer"

    sent = calls[0]["messages"]
    summary_msgs = [m for m in sent if m["role"] == "system" and "[会话摘要]" in m["content"]]
    assert len(summary_msgs) == 1
    # 预算内 → 早期 4 轮不应原样进入
    joined = "".join(m.get("content", "") for m in sent)
    assert "早期问题0" not in joined


def test_run_agent_summary_persisted(monkeypatch, _no_degradation):
    """run_agent 压缩历史后应回写 sessions.summary。"""
    fn, calls = _fake_llm([{"content": "最终回答", "usage": {"input_tokens": 5, "output_tokens": 3}}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)
    monkeypatch.setenv("HISTORY_TOKEN_BUDGET", "1500")
    written = {}
    monkeypatch.setattr(
        "backend.core.sqlite.sessions_repo.set_session_summary",
        lambda sid, text: written.update({sid: text}),
    )

    history = [_msg("user", "长" * 500), _msg("assistant", "长" * 500),
               _msg("user", "长" * 500), _msg("assistant", "长" * 500)]
    list(agent_loop.run_agent("新问题", history, session_id="s9"))
    assert "s9" in written
    assert "用户问:" in written["s9"]


def test_run_agent_under_budget_no_summary(monkeypatch, _no_degradation):
    """预算内历史:不产生摘要 system 段,历史原样进入。"""
    fn, calls = _fake_llm([{"content": "最终回答", "usage": {"input_tokens": 5, "output_tokens": 3}}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)
    history = [_msg("user", "小问题"), _msg("assistant", "小回答")]

    list(agent_loop.run_agent("新问题", history))
    sent = calls[0]["messages"]
    assert not any("[会话摘要]" in m.get("content", "") for m in sent)
    # messages 结构:system + 历史(user/assistant) + 新问题
    assert sent[1] == {"role": "user", "content": "小问题"}
    assert sent[2] == {"role": "assistant", "content": "小回答"}
    assert sent[-1] == {"role": "user", "content": "新问题"}


def test_run_agent_explicit_summary_rendered(monkeypatch, _no_degradation):
    """显式传入 summary:直接渲染,不再走压缩(预算内历史)。"""
    fn, calls = _fake_llm([{"content": "最终回答", "usage": {"input_tokens": 5, "output_tokens": 3}}])
    monkeypatch.setattr(agent_loop, "chat_with_fallback_tools", fn)
    list(agent_loop.run_agent(
        "新问题", [_msg("user", "小问题")], summary="既有摘要:之前聊过经营数据。"
    ))
    sent = calls[0]["messages"]
    assert any(
        m["role"] == "system" and "既有摘要:之前聊过经营数据。" in m["content"]
        for m in sent
    )
