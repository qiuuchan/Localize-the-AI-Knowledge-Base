"""Unit tests for v1.1.0 PR#2 limit-guard.

Task 2.1: sessions.history_limit default 50.
Task 2.2: /api/knowledge/upload rejects > 20MB single file or > 5 files with 413.
Task 2.3: ChatRequest history_limit default 50 + SSE soft_warning at 80%.
Task 2.5: PATCH /api/sessions/{id} updates history_limit / title.
"""
from __future__ import annotations

import asyncio
import io
import json
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from backend.api.chat import ChatRequest, _chat_events
from backend.core.sqlite import init_db
from backend.core.sqlite.sessions_repo import create_session, get_session
from backend.main import app


def test_session_default_history_limit_is_50(tmp_path):
    """新建 session 不传 history_limit → 默认 50。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    sid = create_session(db_path=db_path, title="测试")
    s = get_session(sid, db_path=db_path)
    assert s["history_limit"] == 50


def test_upload_single_image_over_20mb_returns_413():
    """单文件 > 20MB → 413。"""
    client = TestClient(app)
    big = io.BytesIO(b"x" * (21 * 1024 * 1024))  # 21 MB
    resp = client.post(
        "/api/knowledge/upload",
        files=[("files", ("big.png", big, "image/png"))],
    )
    assert resp.status_code == 413
    body = resp.json()
    assert "20MB" in body.get("detail", {}).get("message", "")


def test_upload_six_images_returns_413():
    """批量 > 5 张 → 413。"""
    client = TestClient(app)
    files = [
        ("files", (f"img{i}.png", io.BytesIO(b"x" * 1024), "image/png"))
        for i in range(6)
    ]
    resp = client.post("/api/knowledge/upload", files=files)
    assert resp.status_code == 413
    body = resp.json()
    assert body["detail"]["limit"] == 5
    assert body["detail"]["received"] == 6


# ---------------------------------------------------------------------------
# Task 2.3 — ChatRequest.history_limit 默认 50
# ---------------------------------------------------------------------------


def test_chat_request_default_history_limit_is_50():
    """ChatRequest 不传 history_limit → 默认 50(v1.1.0 PR#2 REQ-6)。

    旧版默认 20(对齐 chat.ps1 历史轮数),新版提到 50(对齐 sessions.history_limit)。
    """
    req = ChatRequest(question="test")
    assert req.history_limit == 50


# ---------------------------------------------------------------------------
# Task 2.3 — SSE soft_warning:消息数 ≥ history_limit * 0.8 时触发
# ---------------------------------------------------------------------------


def _drain_events(payload: ChatRequest) -> List[Dict[str, Any]]:
    """Drain _chat_events async generator into a list of dicts.

    用独立 event loop 避免 3.12 asyncio.get_event_loop() 的 DeprecationWarning;
    与 test_chat_controls._run_events 模式一致。
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


def _patch_chat_for_soft_warning_test(monkeypatch, history_count: int):
    """为 soft_warning 测试统一 monkeypatch 外部依赖。

    注入给定的历史条数(>0 时返回 N 条模拟历史,<0 时跳过 get_messages 调用);
    mock retrieve / websearch / LLM stream,避免触达真实 Qdrant / 阿里云 / SQLite。
    """
    from backend.api import chat as chat_mod

    # 拦截 sqlite history(测试用 in-memory 模拟;不写真实 data/db.sqlite)
    if history_count >= 0:

        def _fake_get_messages(session_id, limit=None, **kwargs):
            return [
                {"role": "user", "content": f"q{i}", "id": i}
                for i in range(history_count)
            ]

        monkeypatch.setattr(chat_mod, "get_messages", _fake_get_messages)

    # 不让 retrieve / websearch 触达真实后端
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

    # LLM 流直接返回固定 JSON 答案,不调真模型
    def _fake_stream(messages, **kwargs):
        yield '{"type":"answer","content":"ok","citations":[1]}'

    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)

    # 拦截 save_message / touch_session,避免污染真实 data/db.sqlite
    monkeypatch.setattr(chat_mod, "save_message", lambda *a, **kw: 0)
    monkeypatch.setattr(chat_mod, "touch_session", lambda *a, **kw: None)


def _first_status_soft_warning(events: List[Dict[str, Any]]) -> Any:
    """从事件流中取第一个 status 事件的 soft_warning 字段。"""
    for ev in events:
        if ev["event"] == "status":
            return json.loads(ev["data"]).get("soft_warning")
    return None


def test_chat_soft_warning_at_80_percent(monkeypatch):
    """消息数 ≥ history_limit * 0.8 → 第一个 status 事件携带 soft_warning。"""
    _patch_chat_for_soft_warning_test(monkeypatch, history_count=4)
    payload = ChatRequest(
        question="新问题", session_id="sess-warn", history_limit=5
    )  # 4 >= 5*0.8 = 4 → 触发
    events = _drain_events(payload)
    warning = _first_status_soft_warning(events)
    assert warning is not None, f"expected soft_warning, got events={events}"
    assert "5" in warning
    assert "4" in warning


def test_chat_soft_warning_below_80_percent_no_warning(monkeypatch):
    """消息数 < history_limit * 0.8 → soft_warning 为 None(不打扰)。"""
    _patch_chat_for_soft_warning_test(monkeypatch, history_count=3)
    payload = ChatRequest(
        question="新问题", session_id="sess-ok", history_limit=5
    )  # 3 < 5*0.8 = 4 → 不触发
    events = _drain_events(payload)
    assert _first_status_soft_warning(events) is None


def test_chat_soft_warning_in_first_status_event_only(monkeypatch):
    """soft_warning 只挂在第一个 status 事件,后续 status(found / thinking)不带。

    后续阶段不应重复打扰用户;前端只读 first status。
    """
    _patch_chat_for_soft_warning_test(monkeypatch, history_count=10)
    payload = ChatRequest(
        question="新问题", session_id="sess-multi", history_limit=5
    )
    events = _drain_events(payload)

    status_warnings: List[Any] = []
    for ev in events:
        if ev["event"] == "status":
            status_warnings.append(json.loads(ev["data"]).get("soft_warning"))
    # 第一个非 None,后续全 None
    assert status_warnings[0] is not None
    assert all(w is None for w in status_warnings[1:]), (
        f"only first status should carry warning, got {status_warnings}"
    )


def test_chat_soft_warning_skipped_without_session_id(monkeypatch):
    """session_id 为空时不应计算 soft_warning(没有历史可统计)。"""
    from backend.api import chat as chat_mod

    # get_messages 不应被调用
    def _explode(*a, **kw):
        raise AssertionError("get_messages should not be called without session_id")

    monkeypatch.setattr(chat_mod, "get_messages", _explode)

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
        yield '{"type":"answer","content":"ok","citations":[1]}'

    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)

    payload = ChatRequest(question="无 session", session_id=None, history_limit=5)
    events = _drain_events(payload)
    assert _first_status_soft_warning(events) is None


# ---------------------------------------------------------------------------
# Task 2.5 — PATCH /api/sessions/{id}
# ---------------------------------------------------------------------------


def _isolated_sessions_endpoint(tmp_path, monkeypatch) -> "object":
    """让 backend.api.sessions 内的端点全部走 tmp_path SQLite,不动 data/db.sqlite。

    PATCH 端点的 `from backend.core.sqlite import (get_connection, get_session, ...)`
    把名字绑定到了 backend.api.sessions 的 globals。monkeypatch setattr 该模块即可
    让 FastAPI 路由(经 TestClient 进入)读写 tmp 数据库。
    """
    from backend.api import sessions as sessions_mod

    db_path = tmp_path / "iso.db"
    init_db(db_path)

    def _row_factory(cursor, row):
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    def _conn(db_path_arg: Optional[Any] = None) -> sqlite3.Connection:
        target = db_path_arg if db_path_arg else db_path
        c = sqlite3.connect(str(target))
        c.row_factory = _row_factory
        return c

    def _get_session(session_id: str, db_path_arg: Optional[Any] = None):
        c = _conn(db_path_arg)
        try:
            cur = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            r = cur.fetchone()
            return dict(r) if r else None
        finally:
            c.close()

    monkeypatch.setattr(sessions_mod, "get_connection", _conn)
    monkeypatch.setattr(sessions_mod, "get_session", _get_session)
    return db_path


def test_patch_session_history_limit_persists(tmp_path, monkeypatch):
    """PATCH /api/sessions/{id} 改 history_limit → 持久化到 SQLite。

    T2.5 主测试。前端 SettingsPage 通过 updateSessionLimit → patchJSON
    调到此端点;验证响应 + 数据库持久化两层都正确。
    """
    db_path = _isolated_sessions_endpoint(tmp_path, monkeypatch)
    sid = create_session(db_path=db_path, title="T2.5-limit", history_limit=20)

    client = TestClient(app)
    resp = client.patch(f"/api/sessions/{sid}", json={"history_limit": 100})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_id"] == sid
    assert body["history_limit"] == 100
    # 验证 SQLite 行确实被 UPDATE
    s = get_session(sid, db_path=db_path)
    assert s["history_limit"] == 100
    assert s["title"] == "T2.5-limit"  # 未指定字段不被动


def test_patch_session_title_persists(tmp_path, monkeypatch):
    """PATCH 改 title → 持久化,history_limit 不变。"""
    db_path = _isolated_sessions_endpoint(tmp_path, monkeypatch)
    sid = create_session(db_path=db_path, title="旧标题", history_limit=50)

    client = TestClient(app)
    resp = client.patch(f"/api/sessions/{sid}", json={"title": "新标题 T2.5"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "新标题 T2.5"
    assert body["history_limit"] == 50  # 没传则保留
    s = get_session(sid, db_path=db_path)
    assert s["title"] == "新标题 T2.5"


def test_patch_session_missing_returns_404(tmp_path, monkeypatch):
    """PATCH 不存在的 session_id → 404,不写数据库。

    - 第二个 `_isolated_sessions_endpoint` 调用会重置 monkeypatch 上的 session 引用,
      但 tmp_path 是 monkeypatch fixture 隔离的,不会影响其他测试。
    """
    db_path = _isolated_sessions_endpoint(tmp_path, monkeypatch)

    client = TestClient(app)
    resp = client.patch(
        "/api/sessions/session-not-exist-xyz", json={"history_limit": 50}
    )

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]
    # 没有这条 sid,所以也不可能有 'default' 之外的其它副作用;
    # 验证 sessions 表只有我们可控的 0 行(默认行是 databases,不是 sessions)
    s = get_session("session-not-exist-xyz", db_path=db_path)
    assert s is None


def test_patch_session_history_limit_out_of_range_returns_422(tmp_path, monkeypatch):
    """history_limit 越界(< 1 或 > 100)→ Pydantic FastAPI 422。

    Pydantic Field(ge=1, le=100) 在请求体解析阶段抛错;不进入 endpoint 也不写 DB。
    """
    _isolated_sessions_endpoint(tmp_path, monkeypatch)
    sid = "sess-bad-limit"

    client = TestClient(app)
    for bad in (0, 101, -5):
        resp = client.patch(f"/api/sessions/{sid}", json={"history_limit": bad})
        assert resp.status_code == 422, f"limit={bad} 应 422, got {resp.status_code}"


def test_patch_session_empty_body_keeps_row_unchanged(tmp_path, monkeypatch):
    """PATCH body 无字段 → 不写数据库,返回当前行。

    验证 UPDATE 路径被跳过(`if fields`)→ 仍走 get_session 拉最新行返回。
    """
    db_path = _isolated_sessions_endpoint(tmp_path, monkeypatch)
    sid = create_session(db_path=db_path, title="原值", history_limit=33)

    client = TestClient(app)
    resp = client.patch(f"/api/sessions/{sid}", json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "原值"
    assert body["history_limit"] == 33
    s = get_session(sid, db_path=db_path)
    assert s["title"] == "原值"
    assert s["history_limit"] == 33
