"""agent_repo 单测 (v2.0 PR#3 / 工单 T12)。

覆盖:
  - init_schema / migrate 幂等(重复调用不抛)
  - create_run → get_run 往返(status 默认 running、默认值)
  - finish_run 字段更新 + finished_at;tools_used JSON 序列化
  - add_step 截断规则(tool_args ≤1000 / observation ≤2000)
  - get_run_steps 按 id 升序;list_runs 倒序 + limit

隔离:connection 层 get_db_path 重定向到 tmp 库(对齐 test_sqlite_refactor 模式)。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.core.sqlite import init_db
from backend.core.sqlite import agent_repo


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    monkeypatch.setattr("backend.core.rag.keyword_index.get_db_path", lambda: db_file)
    init_db()
    return db_file


def test_init_schema_and_migrate_idempotent(tmp_db):
    agent_repo.init_schema()
    agent_repo.migrate()
    agent_repo.init_schema()
    agent_repo.migrate()


def test_create_run_roundtrip(tmp_db):
    run_id = agent_repo.create_run("r-1", "对比两年数据", session_id="s-1", model="qwen3.6-plus")
    assert run_id == "r-1"
    row = agent_repo.get_run("r-1")
    assert row["question"] == "对比两年数据"
    assert row["status"] == "running"
    assert row["steps_count"] == 0 and row["total_in"] == 0 and row["total_out"] == 0
    assert json.loads(row["tools_used"]) == []
    assert row["finished_at"] is None
    assert agent_repo.get_run("missing") is None


def test_finish_run_updates_summary(tmp_db):
    agent_repo.create_run("r-2", "q")
    agent_repo.finish_run(
        "r-2",
        status="done",
        steps_count=3,
        tools_used=["kb_search", "calculator"],
        model="qwen3.6-plus",
        total_in=120,
        total_out=45,
    )
    row = agent_repo.get_run("r-2")
    assert row["status"] == "done"
    assert row["steps_count"] == 3
    assert json.loads(row["tools_used"]) == ["kb_search", "calculator"]
    assert row["model"] == "qwen3.6-plus"
    assert row["total_in"] == 120 and row["total_out"] == 45
    assert row["finished_at"] is not None


def test_add_step_truncation_rules(tmp_db):
    agent_repo.create_run("r-3", "q")
    big_args = {"k": "x" * 3000}
    big_obs = "y" * 5000
    agent_repo.add_step("r-3", 1, "tool_call", tool_name="kb_search", tool_args=big_args)
    agent_repo.add_step("r-3", 1, "tool_result", tool_name="kb_search", observation=big_obs)

    steps = agent_repo.get_run_steps("r-3")
    args_row = [s for s in steps if s["type"] == "tool_call"][0]
    obs_row = [s for s in steps if s["type"] == "tool_result"][0]
    assert len(args_row["tool_args"]) <= 1000 + len("...(截断)")
    assert args_row["tool_args"].endswith("(截断)")
    assert len(obs_row["observation"]) <= 2000 + len("...(截断)")
    assert obs_row["observation"].endswith("(截断)")


def test_get_run_steps_ordered_by_id(tmp_db):
    agent_repo.create_run("r-4", "q")
    for i in range(3):
        agent_repo.add_step("r-4", i // 2, "tool_call" if i % 2 == 0 else "tool_result")
    steps = agent_repo.get_run_steps("r-4")
    assert [s["id"] for s in steps] == sorted(s["id"] for s in steps)
    assert len(steps) == 3
    assert agent_repo.get_run_steps("empty") == []


def test_list_runs_desc_with_limit(tmp_db):
    for i in range(5):
        agent_repo.create_run(f"r-list-{i}", f"q{i}")
    rows = agent_repo.list_runs(limit=3)
    assert len(rows) == 3
    created = [r["created_at"] for r in rows]
    assert created == sorted(created, reverse=True)
    ids = {r["id"] for r in rows}
    assert ids.isdisjoint({"r-list-0", "r-list-1"}), "应取最新 3 条"
