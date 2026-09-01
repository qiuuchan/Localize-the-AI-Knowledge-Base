"""eval_repo 单测 (v2.2 T11 — LLM-as-judge 结果落库)。

覆盖:
  - init_schema 幂等(重复调用不抛)
  - save_eval_run 往返:get 反序列化 detail_json、数值字段落库
  - 幂等:同 run_id 重复保存 → 仍只有 1 行(同口径同日重跑覆盖)
  - list_eval_runs 趋势:kind/mode 过滤 + 倒序 + limit

隔离:connection 层 get_db_path 重定向到 tmp 库(对齐 test_agent_repo 模式)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.sqlite import eval_repo, init_db


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    monkeypatch.setattr("backend.core.rag.keyword_index.get_db_path", lambda: db_file)
    init_db()
    return db_file


def _make_result(question: str = "Q1", passed: int = 1, total: int = 1) -> dict:
    return {
        "dataset": "tests/eval/golden-agent.jsonl",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4),
        "results": [{"question": question, "ok": True}],
        "timestamp": "2026-09-01T00:00:00+00:00",
        "base_url": "http://127.0.0.1:8000",
        "max_steps": 8,
        "judge_mode": "llm",
        "category_stats": {},
        "tools_accuracy": 1.0,
        "task_completion_rate": 0.5,
        "avg_steps": 2.0,
        "total_tokens": 1000,
        "latency_ms": {"p95": 60.0, "p50": 10.0},
    }


def test_init_schema_idempotent(tmp_db):
    eval_repo.init_schema(tmp_db)  # 第二次调用不抛
    eval_repo.init_schema(tmp_db)


def test_save_and_get_roundtrip(tmp_db):
    run_id = eval_repo.save_eval_run(
        "agent-llm-2026-09-01", kind="agent", mode="llm",
        result=_make_result(), cost_estimate_yuan=1.23,
    )
    assert run_id == "agent-llm-2026-09-01"
    row = eval_repo.get_eval_run(run_id)
    assert row is not None
    assert row["kind"] == "agent"
    assert row["mode"] == "llm"
    assert row["passed"] == 1
    assert row["tools_accuracy"] == 1.0
    assert row["p95_ms"] == 60.0
    assert row["cost_estimate_yuan"] == 1.23
    assert row["detail"]["judge_mode"] == "llm"  # detail_json 反序列化
    assert row["detail"]["results"][0]["question"] == "Q1"


def test_save_idempotent_same_id_overwrites(tmp_db):
    eval_repo.save_eval_run(
        "agent-llm-2026-09-01", kind="agent", mode="llm",
        result=_make_result(passed=1, total=2),
    )
    eval_repo.save_eval_run(
        "agent-llm-2026-09-01", kind="agent", mode="llm",
        result=_make_result(passed=2, total=2),
    )
    runs = eval_repo.list_eval_runs(kind="agent", mode="llm")
    assert len(runs) == 1
    assert runs[0]["passed"] == 2  # 后写覆盖


def test_list_trend_filter_and_order(tmp_db):
    eval_repo.save_eval_run(
        "agent-keyword-2026-08-27", kind="agent", mode="keyword",
        result=_make_result(question="old"),
    )
    eval_repo.save_eval_run(
        "agent-llm-2026-08-28", kind="agent", mode="llm",
        result=_make_result(question="new"),
    )
    eval_repo.save_eval_run(
        "agent-llm-2026-09-01", kind="agent", mode="llm",
        result=_make_result(question="latest"),
    )
    llm_only = eval_repo.list_eval_runs(mode="llm")
    assert [r["id"] for r in llm_only] == [
        "agent-llm-2026-09-01", "agent-llm-2026-08-28",
    ]
    limited = eval_repo.list_eval_runs(limit=1)
    assert len(limited) == 1
    assert limited[0]["id"] == "agent-llm-2026-09-01"  # 倒序取最新


def test_get_missing_returns_none(tmp_db):
    assert eval_repo.get_eval_run("nope") is None
