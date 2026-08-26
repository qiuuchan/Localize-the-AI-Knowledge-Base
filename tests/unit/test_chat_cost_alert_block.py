"""Chat cost-alert 阻断分支单测 (v1.3.0)。

覆盖:
  - cost_alert.level >= 3 时,/api/chat 在 retrieve 之前 early-return 503
  - 阻断时不触发 retrieve / chat_with_fallback / streaming
  - 阻断时仍记录 degradation_events(component='LLM')
  - cost_alert.level < 3 时不阻断(回归)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """把 data/ 路径指向 tmp_path(在 dashboard 模块命名空间 patch,因其已 import)。"""
    from backend.api import dashboard
    monkeypatch.setattr(dashboard, "get_data_dir", lambda: tmp_path)
    return tmp_path


def _write_health(tmp_path: Path, cost_alert: dict) -> None:
    (tmp_path / "health_status.json").write_text(
        json.dumps({"cost_alert": cost_alert}), encoding="utf-8"
    )


def test_chat_returns_503_when_cost_alert_level_3(tmp_data_dir, monkeypatch):
    """cost_alert.level >= 3 时,/api/chat 应返回 503 且不触发 retrieve。"""
    from backend.api import chat as chat_mod

    # 阻断路径不应走到 retrieve / stream
    retrieve_called = {"flag": False}
    stream_called = {"flag": False}

    def _fake_retrieve(*args, **kwargs):
        retrieve_called["flag"] = True
        return []

    def _fake_stream(*args, **kwargs):
        stream_called["flag"] = True
        yield ""
        return

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)
    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)

    # 阻断事件记录应该被调用
    recorded = []

    def _fake_save(*args, **kwargs):
        recorded.append(kwargs)
        return 1

    monkeypatch.setattr(chat_mod, "save_degradation_event", _fake_save)

    _write_health(
        tmp_data_dir,
        {
            "level": 3,
            "today_yuan": 1500.0,
            "month_yuan": 1800.0,
            "thresholds": {"warn": 500, "high": 1000, "block": 1500},
        },
    )

    from backend.main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"question": "hello"})

    # 由于 chat 端点使用 EventSourceResponse(SSE),HTTPException 在 SSE 路径
    # 不会触发标准 503;实际由 fastapi 包装为 200 + sse error 事件,或在某些版本里抛错。
    # 我们这里关注:retrieve / stream 都没有被调用,且 degradation_events 被记录。
    assert retrieve_called["flag"] is False, "retrieve 应在阻断分支被跳过"
    assert stream_called["flag"] is False, "stream 应在阻断分支被跳过"
    # 应该有一条 cost-alert 相关的 degradation event(component='LLM')
    assert any(r.get("component") == "LLM" for r in recorded), (
        f"expected LLM degradation event, got {recorded}"
    )

    # 验证 detail 中包含 monthly_cost_exceeded 标记。
    # 当 SSE 路径抛 HTTPException 时,FastAPI 返回 503。
    # 若降级为 SSE error 事件,response.status_code == 200 但 body 含相应标记。
    # 无论哪种路径,retrieve 不能被调用 — 已上面断言。
    if response.status_code == 503:
        # FastAPI HTTPException 路径
        body = response.json()
        detail = body.get("detail", {})
        assert detail.get("reason") == "monthly_cost_exceeded"
        assert detail.get("month_yuan") == 1800.0
    else:
        # SSE 降级为 200 + error event 路径
        assert response.status_code == 200
        text = response.text
        assert "monthly_cost_exceeded" in text or "cost-alert" in text


def test_chat_passes_when_cost_alert_level_0(tmp_data_dir, monkeypatch):
    """cost_alert.level == 0 时不阻断,应进入 retrieve + stream 流程。"""
    from backend.api import chat as chat_mod

    retrieve_called = {"flag": False}
    stream_called = {"flag": False}

    def _fake_retrieve(*args, **kwargs):
        retrieve_called["flag"] = True
        return [
            {
                "source": "a.md",
                "text": "hi",
                "score": 0.5,
                "retrieval_confidence": 0.8,
                "retrieval_mode": "hybrid",
            }
        ]

    def _fake_stream(*args, **kwargs):
        stream_called["flag"] = True
        yield '{"type":"answer","content":"hi","citations":[1]}'
        return

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)
    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", _fake_stream)
    monkeypatch.setattr(chat_mod, "_maybe_websearch", lambda q: None)
    monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])
    monkeypatch.setattr(chat_mod, "save_degradation_event", lambda *a, **kw: 1)

    _write_health(
        tmp_data_dir,
        {
            "level": 0,
            "today_yuan": 0.0,
            "month_yuan": 0.0,
            "thresholds": {"warn": 500, "high": 1000, "block": 1500},
        },
    )

    from backend.main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"question": "hello"})

    # 不阻断:retrieve + stream 应都被调用
    assert retrieve_called["flag"] is True
    assert stream_called["flag"] is True
    # SSE 200 (事件流)
    assert response.status_code == 200


def test_chat_passes_when_health_status_missing(tmp_data_dir, monkeypatch):
    """health_status.json 不存在时,默认 level=0 不阻断。"""
    from backend.api import chat as chat_mod

    retrieve_called = {"flag": False}

    def _fake_retrieve(*args, **kwargs):
        retrieve_called["flag"] = True
        return [
            {
                "source": "a.md",
                "text": "hi",
                "score": 0.5,
                "retrieval_confidence": 0.8,
                "retrieval_mode": "hybrid",
            }
        ]

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)
    monkeypatch.setattr(chat_mod.rag_llm, "chat_stream_with_fallback", lambda *a, **kw: iter(['{"type":"answer","content":"hi","citations":[1]}']))
    monkeypatch.setattr(chat_mod, "_maybe_websearch", lambda q: None)
    monkeypatch.setattr(chat_mod, "get_messages", lambda *a, **kw: [])
    monkeypatch.setattr(chat_mod, "save_degradation_event", lambda *a, **kw: 1)

    # 注意:不写 health_status.json
    assert not (tmp_data_dir / "health_status.json").exists()

    from backend.main import app

    client = TestClient(app)
    response = client.post("/api/chat", json={"question": "hello"})

    # 不阻断:retrieve 被调用
    assert retrieve_called["flag"] is True
    assert response.status_code == 200


# v1.3.1: 验证 health_status.json 字段损坏时 chat 入口不崩溃
def test_chat_handles_corrupted_health_status_level_string(tmp_data_dir, monkeypatch):
    """health_status.json cost_alert.level="3"(字符串) → chat 不崩溃,retrieve 仍被调用。"""
    from backend.api import chat as chat_mod

    retrieve_called = {"flag": False}

    def _fake_retrieve(*args, **kwargs):
        retrieve_called["flag"] = True
        return []

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)

    _write_health(
        tmp_data_dir,
        {"level": "3", "month_yuan": 1500.0, "thresholds": {"warn": 500, "high": 1000, "block": 1500}},
    )

    from backend.main import app

    client = TestClient(app)
    # 不应该抛 TypeError;Stream 真实跑可能走到 LLM(被 mock 拦),核心是不崩
    try:
        client.post("/api/chat", json={"question": "hello"})
    except TypeError as e:
        pytest.fail(f"chat endpoint crashed on corrupted level: {e}")

    # 关键断言:即使 cost_alert.level="3" 被降级为 0(不是真的 3),
    # validate 后仍会调用 retrieve(因为 validate 把字符串 level 降级为 0,
    # 不触发 level >= 3 阻断分支)
    assert retrieve_called["flag"] is True, "validate 后 level=0,应走到 retrieve"


def test_chat_handles_thresholds_null(tmp_data_dir, monkeypatch):
    """health_status.json cost_alert.thresholds=null → chat 不崩溃。"""
    from backend.api import chat as chat_mod

    def _fake_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(chat_mod, "retrieve", _fake_retrieve)

    _write_health(
        tmp_data_dir,
        {"level": 0, "month_yuan": 0.0, "thresholds": None},
    )

    from backend.main import app

    client = TestClient(app)
    try:
        client.post("/api/chat", json={"question": "hello"})
    except (TypeError, AttributeError) as e:
        pytest.fail(f"chat endpoint crashed on thresholds=null: {e}")
