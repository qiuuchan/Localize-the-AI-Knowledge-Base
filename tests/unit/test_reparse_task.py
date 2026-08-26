import pytest
from fastapi.testclient import TestClient

from backend.api import knowledge as knowledge_api
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_reparse_rejects_path_traversal(client):
    response = client.post(
        "/api/knowledge/documents/progress.xlsx/reparse",
        params={"database_id": "default", "upload_path": "../db.sqlite"},
    )

    assert response.status_code == 400
    assert "upload" in response.json()["detail"]


def test_reparse_rejects_missing_upload(client):
    response = client.post(
        "/api/knowledge/documents/progress.xlsx/reparse",
        params={"database_id": "default", "upload_path": "missing.xlsx"},
    )

    assert response.status_code == 404


def test_reparse_enqueues_task_for_safe_file(client, monkeypatch, tmp_path):
    upload = tmp_path / "stored_progress.xlsx"
    upload.write_bytes(b"xlsx")
    monkeypatch.setattr(knowledge_api, "_UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        knowledge_api,
        "_resolve_database",
        lambda database_id: {"collection": "kb_ai_chunks"},
    )
    captured = []

    def fake_add_task(self, func, *args, **kwargs):
        captured.append({"func": func.__name__, "args": args, "kwargs": kwargs})

    from fastapi import BackgroundTasks

    monkeypatch.setattr(BackgroundTasks, "add_task", fake_add_task)

    response = client.post(
        "/api/knowledge/documents/progress.xlsx/reparse",
        params={"database_id": "default", "upload_path": upload.name},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["source"] == "progress.xlsx"
    assert captured
    assert captured[0]["func"] == "_process_reparse"
