"""Session and message endpoints backed by SQLite sessions.db."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.config import get_env_or_env_var
from backend.core.sqlite.connection import get_connection
from backend.core.sqlite.messages_repo import get_messages, save_message
from backend.core.sqlite.sessions_repo import create_session, get_session, list_sessions

logger = logging.getLogger("kb_ai.sessions")

router = APIRouter()

# v1.1.0 PR#4 Task 4.4:流式标题生成。
# 默认标题(create_session 兜底)被视为"未命名",真正标题在 ≥ 3 条消息后由 LLM 生成。
DEFAULT_SESSION_TITLE = "新会话"
TITLE_TRIGGER_MESSAGE_COUNT = 3
TITLE_LLM_MAX_TOKENS = 60
TITLE_LLM_TIMEOUT = 30


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class CreateMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=50000)


class UpdateSessionRequest(BaseModel):
    """v1.1.0 PR#2 Task 2.5:PATCH /api/sessions/{id} body。

    - `history_limit`:可选 1-100(REQ-6 单会话软上限配置)
    - `title`:可选 ≤256 字符
    字段为 None 时跳过更新。
    """

    history_limit: Optional[int] = Field(default=None, ge=1, le=100)
    title: Optional[str] = Field(default=None, max_length=256)


@router.get("/sessions")
def get_sessions(limit: int = 50, offset: int = 0) -> List[dict[str, Any]]:
    return list_sessions(limit=limit, offset=offset)


@router.post("/sessions")
def post_session(req: CreateSessionRequest) -> dict[str, Any]:
    sid = create_session(title=req.title)
    return {"session_id": sid}


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, limit: int = 50, offset: int = 0) -> List[dict[str, Any]]:
    if get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return get_messages(session_id, limit=limit, offset=offset)


@router.post("/sessions/{session_id}/messages")
def post_session_message(session_id: str, req: CreateMessageRequest) -> dict[str, Any]:
    if get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    mid = save_message(session_id, req.role, req.content)
    return {"session_id": session_id, "message_id": mid}


@router.patch("/sessions/{session_id}")
def update_session_endpoint(
    session_id: str,
    body: UpdateSessionRequest,
) -> dict[str, Any]:
    """v1.1.0 PR#2 Task 2.5:更新会话的可变字段(`history_limit` / `title`)。

    缺省字段(None)不更新;返回值是更新后的整行 session。
    """
    existing = get_session(session_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="session not found")

    fields: List[str] = []
    params: List[Any] = []
    if body.history_limit is not None:
        fields.append("history_limit = ?")
        params.append(body.history_limit)
    if body.title is not None:
        fields.append("title = ?")
        params.append(body.title)

    if fields:
        params.append(session_id)
        conn = get_connection()
        try:
            conn.execute(
                f"UPDATE sessions SET {', '.join(fields)} WHERE session_id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()

    refreshed = get_session(session_id)
    # refreshed 应当非 None(existing 已验证);健壮起见仍防御
    if refreshed is None:
        raise HTTPException(status_code=404, detail="session not found")
    return refreshed


# ---------------------------------------------------------------------------
# v1.1.0 PR#4 Task 4.4:流式会话标题生成
# ---------------------------------------------------------------------------
# 设计:
#   - 触发:session 当前 title 仍是默认 "新会话",且 ≥ 3 条 user/assistant 消息。
#   - 幂等:已有非默认标题的会话(API 创建时显式传 title,或 PATCH 改过)
#     不再触发;多次调用安全。
#   - 持久化:LLM 生成的标题通过 UPDATE sessions SET title 落库。
#   - 失败兜底:LLM 调用失败(无 key / 网络 / 限流)只记 warning,不抛错,
#     会话仍以默认标题继续使用。
#   - mock 入口:`_call_llm_for_title` 单独成函数,便于测试 monkeypatch。
# ---------------------------------------------------------------------------


def _call_llm_for_title(user_texts: List[str]) -> str:
    """调用 LLM(短 max_tokens)从首条用户消息生成会话标题。

    Raises:
        RuntimeError: 当 API key 未配置、为占位符,或 LLM 返回空 / 失败时。
    """
    api_key = get_env_or_env_var("ALIYUN_BAILIAN_API_KEY")
    if not api_key:
        raise RuntimeError("ALIYUN_BAILIAN_API_KEY not configured")

    from backend.core.rag import llm as rag_llm

    snippet = "\n".join(f"- {t[:200]}" for t in user_texts[:3] if t)
    prompt = (
        "你是会话标题生成器。基于以下用户消息,用 4-12 个中文字符总结一个"
        "简洁的会话标题。只输出标题本身,不要任何前缀、标点或解释。\n\n"
        f"{snippet}"
    )
    messages: List[dict[str, Any]] = [{"role": "user", "content": prompt}]
    # v1.3.0: _post_chat 现在返回 (content, usage);usage 用于 cost-alert 计量
    content, usage = rag_llm._post_chat(
        api_key=api_key,
        model=rag_llm.DEFAULT_MODEL,
        messages=messages,
        max_tokens=TITLE_LLM_MAX_TOKENS,
        timeout=TITLE_LLM_TIMEOUT,
    )
    if usage is not None:
        rag_llm._log_token_usage(
            rag_llm.DEFAULT_MODEL,
            usage["input_tokens"],
            usage["output_tokens"],
        )
    title = (content or "").strip().strip("\"'""''` ").strip()
    return title


def generate_session_title_if_needed(
    session_id: str,
    db_path: Optional[Path] = None,
) -> bool:
    """若会话仍为默认标题且消息数 ≥ 阈值,触发 LLM 生成并持久化。

    Returns:
        True  - 已生成新标题并 UPDATE 落库。
        False - 跳过(会话不存在 / 已有真实标题 / 消息不足 / LLM 失败)。

    测试约定:`db_path` 显式传参会落到该库;否则走 sqlite.get_db_path() 默认值。
    """
    s = get_session(session_id, db_path=db_path)
    if s is None:
        logger.debug(
            "session_title_stream: session_id=%s triggered=False reason=missing",
            session_id,
        )
        return False

    current_title = (s.get("title") or "").strip()
    is_default = current_title == DEFAULT_SESSION_TITLE
    if not is_default:
        logger.debug(
            "session_title_stream: session_id=%s triggered=False reason=already_titled current_title=%s",
            session_id,
            current_title,
        )
        return False

    try:
        msgs = get_messages(session_id, limit=20, offset=0)
    except Exception:
        logger.warning("title gen: get_messages failed", exc_info=True)
        return False
    meaningful = [m for m in msgs if m.get("role") in ("user", "assistant")]
    if len(meaningful) < TITLE_TRIGGER_MESSAGE_COUNT:
        logger.debug(
            "session_title_stream: session_id=%s triggered=False reason=below_threshold msg_count=%s",
            session_id,
            len(meaningful),
        )
        return False

    user_texts = [m["content"] for m in meaningful if m.get("role") == "user"]
    logger.debug(
        "session_title_stream: session_id=%s triggered=True current_title=%s msg_count=%s",
        session_id,
        current_title,
        len(meaningful),
    )

    try:
        new_title = _call_llm_for_title(user_texts)
    except Exception:
        logger.warning("title gen: LLM call failed", exc_info=True)
        return False

    new_title = (new_title or "").strip()
    # 防御性归一化:即使 _call_llm_for_title 已清洗,也再过一遍 —
    # 测试场景会直接 mock 该函数返回脏数据。LLM 偶发带前后引号 / 反引号。
    new_title = new_title.strip('"\'`"\'').strip()
    if not new_title or new_title == DEFAULT_SESSION_TITLE:
        logger.debug(
            "session_title_stream: session_id=%s skipped reason=empty_or_default new_title=%r",
            session_id,
            new_title,
        )
        return False
    if len(new_title) > 200:
        new_title = new_title[:200]

    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sessions SET title = ? WHERE session_id = ?",
            (new_title, session_id),
        )
        conn.commit()
    finally:
        conn.close()

    logger.debug(
        "session_title_stream: session_id=%s persisted new_title=%s",
        session_id,
        new_title,
    )
    return True
