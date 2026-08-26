"""Integration tests for the KB-AI FastAPI backend.

Run from the project root:
    backend/.venv/Scripts/python -m pytest tests/integration/api/test_api.py -v

Assumptions:
- backend/.venv exists and dependencies are installed
- .env contains a valid ALIYUN_BAILIAN_API_KEY
- Docker containers may be running or not; tests tolerate DOWN status
"""
from __future__ import annotations

import json
import os
import re

# 集成测试不下载/加载 cross-encoder 模型;关闭 rerank 避免超时。
os.environ.setdefault("RERANK_TOP_N", "0")

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_api_root(client):
    r = client.get("/api")
    assert r.status_code == 200
    assert r.json()["name"] == "KB-AI Backend"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "online" in data
    assert "endpoints" in data


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "capacity" in data
    assert "health" in data


def test_sessions_crud(client):
    # Create
    r = client.post("/api/sessions", json={"title": "API test session"})
    assert r.status_code == 200
    sid = r.json()["session_id"]

    # List
    r = client.get("/api/sessions")
    assert r.status_code == 200
    assert any(s["session_id"] == sid for s in r.json())

    # Post user message
    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"role": "user", "content": "测试消息"},
    )
    assert r.status_code == 200
    assert r.json()["message_id"] > 0

    # Get messages
    r = client.get(f"/api/sessions/{sid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 1
    assert msgs[-1]["role"] == "user"


def test_chat_sse(client):
    """End-to-end chat: calls chat.ps1, Qdrant and Qwen API."""
    payload = {"question": "红烧肉怎么做"}
    with client.stream("POST", "/api/chat", json=payload) as response:
        assert response.status_code == 200
        text = response.read().decode("utf-8")

    assert "event: status" in text
    assert "event: answer" in text

    # Extract answer payload
    m = re.search(r"event: answer\r?\ndata: (.+?)(?:\r?\n\r?\n|$)", text, re.DOTALL)
    assert m, "No answer event found in SSE stream"
    answer = json.loads(m.group(1))
    assert answer["type"] == "answer"
    assert answer["content"]
    assert "红烧肉" in answer["content"] or "五花肉" in answer["content"]
    assert answer.get("model") == "qwen3.6-plus"
    assert answer.get("model_reason") == "default"


def test_chat_complex_routes_to_max(client):
    """Complex query containing routing keyword should use qwen3.7-max."""
    payload = {"question": "对比红茶和绿茶的制作工艺"}
    with client.stream("POST", "/api/chat", json=payload) as response:
        assert response.status_code == 200
        text = response.read().decode("utf-8")

    m = re.search(r"event: answer\r?\ndata: (.+?)(?:\r?\n\r?\n|$)", text, re.DOTALL)
    assert m, "No answer event found in SSE stream"
    answer = json.loads(m.group(1))
    assert answer["type"] == "answer"
    assert answer["content"]
    assert answer.get("model") == "qwen3.7-max"
    assert answer.get("model_reason") == "complex_keyword"
