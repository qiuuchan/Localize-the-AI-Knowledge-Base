"""Agent API 单测 (v2.0 PR#3 / 工单 T12)。

覆盖:
  - POST /api/agent/chat max_steps 边界:1 / 16 通过;0 / 17 → 422
  - SSE 事件序列契约(status → step_start → tool_call → tool_result → answer)
  - cost-alert level>=3 阻断:run_agent 不被调用 + monthly_cost_exceeded
  - GET /api/agent/runs 列表 + limit
  - GET /api/agent/runs/{id} 明细含 steps;未知 id → 404

隔离:tmp db(connection + keyword_index)+ dashboard data 目录重定向。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated(tmp_path: Path, monkeypatch) -> Path:
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    monkeypatch.setattr("backend.core.rag.keyword_index.get_db_path", lambda: db_file)
    from backend.api import dashboard

    monkeypatch.setattr(dashboard, "get_data_dir", lambda: tmp_path)
    from backend.core.sqlite import init_db

    init_db()
    return tmp_path


def _client():
    from backend.main import app

    return TestClient(app)


@pytest.fixture()
def _mock_run_ok(monkeypatch):
    """按设计稿 §6.1 事件序列产出的假 run_agent。"""
    import backend.api.agent as agent_api

    def _gen(question, history, **kwargs):
        yield {"type": "step_start", "step": 1, "max_steps": kwargs["max_steps"]}
        yield {
            "type": "tool_call",
            "step": 1,
            "name": "kb_search",
            "args": {"query": "会员"},
        }
        yield {
            "type": "tool_result",
            "step": 1,
            "name": "kb_search",
            "ok": True,
            "latency_ms": 12,
            "excerpt": "...",
        }
        yield {
            "type": "answer",
            "content": "回答正文",
            "citations": [],
            "model": "qwen3.6-plus",
            "model_reason": "primary",
            "budget_exhausted": False,
            "finish_reason": "completed",
            "session_id": kwargs.get("session_id"),
            "agent": {
                "run_id": "run-x",
                "steps": 1,
                "tools_used": ["kb_search"],
                "total_in": 10,
                "total_out": 5,
            },
            "timestamp": "2026-08-26T10:00:00",
        }

    monkeypatch.setattr(agent_api, "run_agent", _gen)


def test_max_steps_boundary_accepted(isolated, _mock_run_ok):
    client = _client()
    for steps in (1, 16):
        resp = client.post("/api/agent/chat", json={"question": "q", "max_steps": steps})
        assert resp.status_code == 200
        assert "event: answer" in resp.text


@pytest.mark.parametrize("steps", [0, 17])
def test_max_steps_out_of_range_422(isolated, steps):
    client = _client()
    resp = client.post("/api/agent/chat", json={"question": "q", "max_steps": steps})
    assert resp.status_code == 422


def test_sse_event_sequence_contract(isolated, _mock_run_ok):
    client = _client()
    resp = client.post("/api/agent/chat", json={"question": "对比数据"})
    assert resp.status_code == 200
    text = resp.text
    # 事件顺序:status(agent_start) → step_start → tool_call → tool_result → answer
    order = [
        text.index("event: status"),
        text.index("event: step_start"),
        text.index("event: tool_call"),
        text.index("event: tool_result"),
        text.index("event: answer"),
    ]
    assert order == sorted(order)
    # answer data 契约关键字段
    answer_line = [
        line for line in text.splitlines() if line.startswith("data:") and "run_id" in line
    ][0]
    payload = json.loads(answer_line[len("data:"):])
    assert payload["type"] == "answer"
    assert payload["agent"]["run_id"] == "run-x"
    assert payload["agent"]["tools_used"] == ["kb_search"]


def test_cost_alert_block_prevents_run(isolated, monkeypatch):
    import backend.api.agent as agent_api

    called = {"flag": False}

    def _gen(*a, **kw):
        called["flag"] = True
        yield {}
        return

    monkeypatch.setattr(agent_api, "run_agent", _gen)
    recorded = []
    monkeypatch.setattr(
        agent_api, "save_degradation_event", lambda **kw: recorded.append(kw) or 1
    )
    (isolated / "health_status.json").write_text(
        json.dumps(
            {
                "cost_alert": {
                    "level": 3,
                    "today_yuan": 1500.0,
                    "month_yuan": 1800.0,
                    "thresholds": {"warn": 500, "high": 1000, "block": 1500},
                }
            }
        ),
        encoding="utf-8",
    )

    client = _client()
    resp = client.post("/api/agent/chat", json={"question": "q"})
    assert called["flag"] is False, "阻断时 run_agent 不应被调用"
    assert "monthly_cost_exceeded" in resp.text
    assert any(r.get("component") == "LLM" for r in recorded)


def test_get_runs_list(isolated):
    from backend.core.sqlite import agent_repo

    agent_repo.create_run("r-a", "问题A")
    agent_repo.create_run("r-b", "问题B")
    client = _client()
    resp = client.get("/api/agent/runs", params={"limit": 1})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["id"] == "r-b"


def test_get_run_detail_with_steps_404(isolated):
    from backend.core.sqlite import agent_repo

    agent_repo.create_run("r-detail", "问题D")
    agent_repo.add_step("r-detail", 1, "tool_call", tool_name="calculator", tool_args={"expression": "1+1"})

    client = _client()
    resp = client.get("/api/agent/runs/r-detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "r-detail"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["tool_name"] == "calculator"

    missing = client.get("/api/agent/runs/nope")
    assert missing.status_code == 404
