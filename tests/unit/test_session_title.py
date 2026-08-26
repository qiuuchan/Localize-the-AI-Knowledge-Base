"""v1.1.0 PR#4 Task 4.4 — 流式会话标题生成单测。

覆盖 ``backend.api.sessions.generate_session_title_if_needed`` 的三条核心契约:

  1. ``test_title_generated_after_3_messages`` — ≥ 3 条消息后函数被调用,
     触发后写 ``session_title_stream`` debug 日志(便于线上排查"为什么没生成")。
  2. ``test_title_persists_after_generation`` — mock LLM 返回固定标题,
     函数必须 ``UPDATE sessions SET title`` 把新值落库。
  3. ``test_title_generation_idempotent`` — 已有非默认标题的会话,
     LLM 不应被调用,旧标题不被覆盖。

设计说明:
  - LLM 入口 ``_call_llm_for_title`` 单独成函数,monkeypatch 友好。
  - 测试走 ``fresh_db`` fixture(monkeypatch ``get_db_path``),
    避免污染真实 ``data/db.sqlite``(与 v0.8.11+ 其它单测一致)。
  - ``save_message`` 签名是 ``(session_id, role, content, citations=None)``,
    无 ``db_path`` 参数(走全局 ``get_db_path``),与 brief 中的写法略有出入,
    按真实实现对齐。
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.api.sessions import (
    DEFAULT_SESSION_TITLE,
    generate_session_title_if_needed,
)
from backend.core import sqlite as sqlite_mod
from backend.core.sqlite import sessions_repo, messages_repo


@pytest.fixture()
def fresh_db(monkeypatch):
    """把 SQLite 重定向到临时库,跑完清理。

    沿用 ``test_database_crud`` 的隔离模式:monkeypatch ``get_db_path``,
    ``init_db`` 重建 schema,避免单测污染 ``data/db.sqlite``。
    """
    tmp = Path(tempfile.mkdtemp(prefix="kbtitle-"))
    db_file = tmp / "test.sqlite"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file
    try:
        db_file.unlink()
        os.rmdir(tmp)
    except OSError:
        pass


def _save_user_messages(sid: str, count: int) -> None:
    """往临时库写 N 条 user 消息(辅助 fixture)。"""
    for i in range(count):
        messages_repo.save_message(
            session_id=sid,
            role="user",
            content=f"问题 {i}:Q3 财务情况怎么样?",
        )


# ---------------------------------------------------------------------------
# 契约 1: ≥ 3 条消息后触发 + debug 日志
# ---------------------------------------------------------------------------


def test_title_generated_after_3_messages(fresh_db, caplog):
    """≥ 3 条消息后应触发标题生成,且记录 session_title_stream debug 日志。

    mock LLM 入口让其抛 RuntimeError,模拟 "无 API key / 调用失败" 场景:
    - 函数内部 ``try/except`` 吞掉异常 → 返回 False(不抛错)
    - 触发阶段的 debug 日志在调用 LLM 之前已写出,足以证明触发条件成立
    这样测试不再依赖运行环境是否配置了真实 ALIYUN_BAILIAN_API_KEY。
    """
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 3)

    with caplog.at_level(logging.DEBUG, logger="kb_ai.sessions"), patch(
        "backend.api.sessions._call_llm_for_title",
        side_effect=RuntimeError("test: simulate API key missing"),
    ):
        result = generate_session_title_if_needed(sid)

    # LLM 调用失败 → 函数返回 False;但 debug 日志应被记录
    assert result is False, (
        "expected False when LLM call fails (simulated), "
        f"got {result}"
    )
    debug_logs = [r for r in caplog.records if "session_title_stream" in r.message]
    assert len(debug_logs) >= 1, (
        "expected ≥ 1 session_title_stream debug record, "
        f"got {[r.message for r in caplog.records]}"
    )
    # 至少有一条 triggered=True 的记录
    triggered_true = [r for r in debug_logs if "triggered=True" in r.message]
    assert triggered_true, (
        "expected triggered=True debug log after 3 messages, "
        f"got messages={[r.message for r in debug_logs]}"
    )


def test_title_below_threshold_does_not_trigger(fresh_db, caplog):
    """消息数 < 3 → 不触发 LLM,也不进入 _call_llm_for_title。"""
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 2)

    with caplog.at_level(logging.DEBUG, logger="kb_ai.sessions"), patch(
        "backend.api.sessions._call_llm_for_title"
    ) as mock_llm:
        result = generate_session_title_if_needed(sid)

    assert result is False
    mock_llm.assert_not_called()
    debug_logs = [r for r in caplog.records if "session_title_stream" in r.message]
    assert any("below_threshold" in r.message for r in debug_logs), (
        "expected below_threshold debug log, got " f"{[r.message for r in debug_logs]}"
    )


# ---------------------------------------------------------------------------
# 契约 2: 持久化
# ---------------------------------------------------------------------------


def test_title_persists_after_generation(fresh_db):
    """mock LLM 返回固定标题,断言 sessions.title 被覆盖。"""
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 3)

    with patch(
        "backend.api.sessions._call_llm_for_title",
        return_value="财务 Q3 复盘",
    ):
        result = generate_session_title_if_needed(sid)

    assert result is True, "expected True after successful LLM mock"
    s = sessions_repo.get_session(sid)
    assert s is not None
    assert s["title"] == "财务 Q3 复盘", (
        f"expected title to be persisted, got {s['title']!r}"
    )


def test_title_persists_with_stripped_whitespace(fresh_db):
    """LLM 偶发返回带空白 / 引号 / 反引号的标题 — 应当被清洗后落库。"""
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 3)

    with patch(
        "backend.api.sessions._call_llm_for_title",
        return_value='  "厨房 SOP 修订"  ',
    ):
        result = generate_session_title_if_needed(sid)

    assert result is True
    s = sessions_repo.get_session(sid)
    assert s["title"] == "厨房 SOP 修订"


def test_title_skipped_when_llm_returns_default(fresh_db):
    """LLM 不可靠 — 若返回与默认标题相同,不应覆盖(避免"新会话"被永久留下)。"""
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 3)

    with patch(
        "backend.api.sessions._call_llm_for_title",
        return_value=DEFAULT_SESSION_TITLE,
    ):
        result = generate_session_title_if_needed(sid)

    assert result is False
    s = sessions_repo.get_session(sid)
    assert s["title"] == DEFAULT_SESSION_TITLE


# ---------------------------------------------------------------------------
# 契约 3: 幂等
# ---------------------------------------------------------------------------


def test_title_generation_idempotent(fresh_db):
    """已有非默认标题的会话 — LLM 不应被调用,旧标题不被覆盖。"""
    sid = sessions_repo.create_session(title="已设标题")

    with patch(
        "backend.api.sessions._call_llm_for_title"
    ) as mock_llm:
        result = generate_session_title_if_needed(sid)

    assert result is False
    mock_llm.assert_not_called()
    s = sessions_repo.get_session(sid)
    assert s["title"] == "已设标题", (
        f"non-default title should not be overwritten, got {s['title']!r}"
    )


def test_title_generation_idempotent_on_second_call(fresh_db):
    """第二次调用同一会话 — 第一次成功后第二次应跳过(避免 LLM 重复扣费)。"""
    sid = sessions_repo.create_session(title=None)
    _save_user_messages(sid, 3)

    with patch(
        "backend.api.sessions._call_llm_for_title",
        return_value="运营复盘",
    ) as mock_llm:
        first = generate_session_title_if_needed(sid)
        # 第二次调用 — 此时 title 已不再是默认 "新会话"
        second = generate_session_title_if_needed(sid)

    assert first is True
    assert second is False
    assert mock_llm.call_count == 1
    s = sessions_repo.get_session(sid)
    assert s["title"] == "运营复盘"


# ---------------------------------------------------------------------------
# 边界:session_id 不存在
# ---------------------------------------------------------------------------


def test_title_skipped_for_missing_session(fresh_db):
    """session_id 不存在 → 返回 False,不抛错。"""
    with patch(
        "backend.api.sessions._call_llm_for_title"
    ) as mock_llm:
        result = generate_session_title_if_needed("nonexistent-session-id")

    assert result is False
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# 契约 4 (v1.3.0):_post_chat 返回 (content, usage) 时记录 token 计量
# ---------------------------------------------------------------------------


def test_title_call_llm_logs_usage_when_post_chat_returns_usage(
    monkeypatch, fresh_db
):
    """v1.3.0:`_post_chat` 返回 (content, usage) tuple;_call_llm_for_title
    必须拆 tuple 并在 usage 非 None 时调用 ``_log_token_usage``,
    以满足 cost-alert spec §2.4「每条 LLM 调用都计量」的约束。
    """
    from backend.api import sessions
    from backend.core.rag import llm as rag_llm

    monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "test-fake-key")
    log_calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(
        rag_llm,
        "_post_chat",
        lambda **kw: ("测试标题", {"input_tokens": 50, "output_tokens": 8}),
    )
    monkeypatch.setattr(
        rag_llm,
        "_log_token_usage",
        lambda model, inp, out: log_calls.append((model, inp, out)),
    )

    title = sessions._call_llm_for_title(["用户的第一条问题"])

    assert title == "测试标题"
    assert len(log_calls) == 1, (
        "expected exactly 1 _log_token_usage call, " f"got {log_calls}"
    )
    assert log_calls[0] == (rag_llm.DEFAULT_MODEL, 50, 8)


def test_title_call_llm_skips_usage_when_post_chat_returns_none(
    monkeypatch, fresh_db
):
    """v1.3.0:`_post_chat` 返回 (content, None) 时,应当不调用
    ``_log_token_usage``(API 异常 / 不返回 usage 字段),避免污染 cost_log。
    """
    from backend.api import sessions
    from backend.core.rag import llm as rag_llm

    monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "test-fake-key")
    log_calls: list[tuple[str, int, int]] = []
    monkeypatch.setattr(
        rag_llm,
        "_post_chat",
        lambda **kw: ("裸标题", None),
    )
    monkeypatch.setattr(
        rag_llm,
        "_log_token_usage",
        lambda model, inp, out: log_calls.append((model, inp, out)),
    )

    title = sessions._call_llm_for_title(["用户问题"])

    assert title == "裸标题"
    assert log_calls == [], (
        "_log_token_usage must NOT be called when usage is None, "
        f"got {log_calls}"
    )


def test_title_call_llm_strips_tuple_content(monkeypatch, fresh_db):
    """v1.3.0 regression guard:即使 _post_chat 返回 tuple,tuple 元素是
    content 字符串时仍应被 strip / 去引号,与旧 str 行为完全一致。
    """
    from backend.api import sessions
    from backend.core.rag import llm as rag_llm

    monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "test-fake-key")
    monkeypatch.setattr(
        rag_llm,
        "_post_chat",
        lambda **kw: ('  "厨房 SOP 修订"  ', {"input_tokens": 1, "output_tokens": 1}),
    )
    monkeypatch.setattr(
        rag_llm,
        "_log_token_usage",
        lambda *args, **kwargs: None,
    )

    title = sessions._call_llm_for_title(["某问题"])

    assert title == "厨房 SOP 修订"
