"""Unit tests for v0.8.11(P2.1) run_evaluation function + eval route.

v1.0.1 安全与单飞增强:在原有 run_evaluation 单测之上,加 3 个 HTTP 层单测
覆盖路径约束 / 文件不存在 / 真单飞。
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.core import config as _core_config


def _make_dataset(tmp_path: Path) -> Path:
    p = tmp_path / "ds.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"question": "Q1", "expect_source": "a.md"}),
                json.dumps({"question": "Q2", "expect_source": "b.md", "expect_keywords": ["kw"]}),
                json.dumps({"question": "Q3", "expect_source": "missing.md"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def _make_dataset_under_eval_root() -> Path:
    """把 dataset 写到 <project_root>/tests/eval/_pytest_<uuid>.jsonl。

    满足 v1.0.1 修复后的路径约束(_resolve_dataset_path 把 dataset_path 锁在
    <root>/tests/eval/ 下,且文件名不得含路径分隔符)。调用方负责清理。
    """
    root = Path(_core_config.get_root_dir())
    eval_root = root / "tests" / "eval"
    p = eval_root / f"_pytest_{uuid.uuid4().hex}.jsonl"
    p.write_text(
        "\n".join(
            [
                json.dumps({"question": "Q1", "expect_source": "a.md"}),
                json.dumps({"question": "Q2", "expect_source": "b.md", "expect_keywords": ["kw"]}),
                json.dumps({"question": "Q3", "expect_source": "missing.md"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def _cleanup_sandbox_file(p: Path) -> None:
    """清理由 _make_dataset_under_eval_root 写出的沙箱 dataset。"""
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def test_run_evaluation_happy_path(tmp_path):
    from tests.eval.run_eval import run_evaluation

    dataset = _make_dataset(tmp_path)

    def fake_urlopen(url, timeout):
        if "missing" in url or "Q3" in url:
            body = json.dumps({"reranked_hits": [{"payload": {"source": "other.md"}}]}).encode()
        elif "Q1" in url:
            body = json.dumps({"reranked_hits": [{"payload": {"source": "a.md"}}]}).encode()
        else:
            body = json.dumps(
                {"reranked_hits": [{"payload": {"source": "b.md", "text": "this has kw"}}]}
            ).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = run_evaluation(base_url="http://x", dataset_path=str(dataset), top_k=5)

    assert result["total"] == 3
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["pass_rate"] == round(2 / 3, 4)
    assert len(result["results"]) == 3
    assert result["results"][0]["ok"] is True
    assert result["results"][2]["ok"] is False


def test_run_evaluation_missing_dataset(tmp_path):
    from tests.eval.run_eval import run_evaluation

    result = run_evaluation(dataset_path=str(tmp_path / "nope.jsonl"))
    assert result["total"] == 0
    assert "error" in result
    assert "不存在" in result["error"]
    assert result["category_stats"] == {}
    assert result["latency_ms"] == {}


def test_run_evaluation_empty_dataset(tmp_path):
    from tests.eval.run_eval import run_evaluation

    p = tmp_path / "empty.jsonl"
    p.write_text("# only comments\n", encoding="utf-8")
    result = run_evaluation(dataset_path=str(p))
    assert result["total"] == 0
    assert "error" in result
    assert "空" in result["error"]
    assert result["category_stats"] == {}
    assert result["latency_ms"] == {}


def test_run_evaluation_keyword_missing(tmp_path):
    from tests.eval.run_eval import run_evaluation

    dataset = tmp_path / "ds.jsonl"
    dataset.write_text(
        json.dumps({"question": "Q", "expect_source": "a.md", "expect_keywords": ["nothere"]})
        + "\n",
        encoding="utf-8",
    )

    def fake_urlopen(url, timeout):
        body = json.dumps(
            {"reranked_hits": [{"payload": {"source": "a.md", "text": "no match"}}]}
        ).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = run_evaluation(dataset_path=str(dataset))
    assert result["passed"] == 0
    assert result["failed"] == 1
    assert "nothere" in result["results"][0]["detail"]


def test_run_evaluation_falls_back_to_rrf_hits(tmp_path):
    """When reranked_hits is empty (reranker offline), use rrf_hits."""
    from tests.eval.run_eval import run_evaluation

    dataset = _make_dataset(tmp_path)  # only first case is used
    dataset.write_text(
        json.dumps({"question": "Q", "expect_source": "a.md"}) + "\n", encoding="utf-8"
    )

    def fake_urlopen(url, timeout):
        body = json.dumps(
            {
                "reranked_hits": [],
                "rrf_hits": [{"payload": {"source": "a.md", "text": "hi"}}],
            }
        ).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = run_evaluation(dataset_path=str(dataset))
    assert result["passed"] == 1


# --- HTTP 层单测(v1.0.1 新增覆盖:路径约束 + 单飞) ---


def test_eval_endpoint_returns_last_result(monkeypatch):
    """Hit the /api/eval/run + /api/eval/results endpoints via TestClient."""
    from fastapi.testclient import TestClient

    from backend.api import eval as eval_mod
    from backend.main import app

    client = TestClient(app)
    dataset = _make_dataset_under_eval_root()
    monkeypatch.setattr(
        eval_mod,
        "_LAST_RESULT",
        {
            "result": None,
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "error": None,
        },
    )

    def fake_urlopen(url, timeout):
        body = json.dumps({"reranked_hits": [{"payload": {"source": "a.md"}}]}).encode()
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    # dataset_path 必须是相对于 <root>/tests/eval/ 的路径(无分隔符)
    eval_root = Path(_core_config.get_root_dir()) / "tests" / "eval"
    rel_to_eval_root = dataset.relative_to(eval_root).as_posix()

    try:
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            r = client.post(
                "/api/eval/run",
                json={"dataset_path": rel_to_eval_root, "top_k": 5},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] >= 1

            r2 = client.get("/api/eval/results")
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["status"] == "done"
            assert body2["result"] is not None
            assert body2["result"]["total"] == body["total"]
            assert body2["result"]["timestamp"] == body["timestamp"]
    finally:
        _cleanup_sandbox_file(dataset)


def test_eval_endpoint_rejects_path_traversal():
    """v1.0.1 安全修复:dataset_path 含 ../ 或跨目录符一律 400。"""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)

    # 父目录逃逸
    r = client.post(
        "/api/eval/run",
        json={"dataset_path": "../../etc/passwd"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "仅接受" in detail or "必须在" in detail

    # 子目录分隔符也拒绝
    r = client.post(
        "/api/eval/run",
        json={"dataset_path": "subdir/golden-qa.jsonl"},
    )
    assert r.status_code == 400


def test_eval_endpoint_404_when_dataset_missing():
    """v1.0.1:合法的文件名 + 文件不存在 → 404,不静默跑默认集。"""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    r = client.post(
        "/api/eval/run",
        json={"dataset_path": "definitely-not-a-real-file.jsonl"},
    )
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


def test_eval_endpoint_single_flight_returns_409(monkeypatch):
    """v1.0.1 单飞:running 状态下并发第二个请求 → 409,不重复烧阿里云 quota。"""
    from fastapi.testclient import TestClient

    from backend.api import eval as eval_mod
    from backend.main import app

    # 重置全局状态,避免前序测试污染;同时强制 status='running'
    monkeypatch.setattr(eval_mod, "_LOCK", threading.Lock())
    monkeypatch.setattr(
        eval_mod,
        "_LAST_RESULT",
        {
            "result": None,
            "status": "running",
            "started_at": 0.0,
            "finished_at": None,
            "error": None,
        },
    )

    client = TestClient(app)
    r = client.post("/api/eval/run", json={"dataset_path": None})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "进行中" in detail or "稍后" in detail


def test_run_evaluation_reports_category_and_latency_stats(tmp_path):
    from tests.eval.run_eval import run_evaluation

    dataset = tmp_path / "v12.jsonl"
    dataset.write_text(
        "\n".join(
            [
                json.dumps({"question": "短", "expect_source": "a.md", "category": "short"}),
                json.dumps({"question": "2026 进度", "expect_source": "a.md", "category": "year", "expect_year": 2026}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_urlopen(url, timeout):
        body = json.dumps(
            {
                "reranked_hits": [
                    {"source": "a.md", "text": "2026 进度", "year_mentions": [2026]}
                ]
            }
        ).encode()
        response = MagicMock()
        response.read.return_value = body
        response.__enter__ = lambda value: value
        response.__exit__ = lambda value, *args: None
        return response

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = run_evaluation(dataset_path=str(dataset))

    assert result["passed"] == 2
    assert result["category_stats"]["short"]["passed"] == 1
    assert result["category_stats"]["year"]["passed"] == 1
    assert result["latency_ms"]["count"] == 0
