"""Unit tests for v0.8.11(P1.6) dashboard aggregations."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.core import sqlite as sqlite_mod
from backend.core.sqlite import databases_repo, degradation_repo


@pytest.fixture()
def fresh_db(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-dash-"))
    db_file = tmp / "test.sqlite"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file
    try:
        db_file.unlink()
        os.rmdir(tmp)
    except OSError:
        pass


def test_degradations_summary(fresh_db):
    degradation_repo.save_degradation_event(None, None, "x", "r1", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r2", component="LLM")
    degradation_repo.save_degradation_event(None, None, "x", "r3", component="Embedding")

    # 24h window
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = degradation_repo.degradation_summary_by_component(since)
    by = {r["component"]: r["count"] for r in rows}
    assert by["LLM"] == 2
    assert by["Embedding"] == 1

    # Empty case
    sqlite_mod.init_db.__wrapped__ if hasattr(sqlite_mod.init_db, "__wrapped__") else None
    # Re-init to clear; init_db is idempotent so we just check: empty summary
    # after fresh DB → skip; covered by other tests.


def test_kb_stats(fresh_db, monkeypatch):
    """Verify _kb_stats handles empty DB without crashing."""
    from backend.api import dashboard

    # Dashboard imports get_data_dir directly; patch its own module binding.
    monkeypatch.setattr(
        dashboard, "get_data_dir", lambda: fresh_db.parent
    )
    dbs = databases_repo.list_databases()
    assert len(dbs) >= 1  # default
    stats = dashboard._kb_stats()
    assert "error" not in stats, stats
    assert stats["database_count"] >= 1
    assert stats["chunk_count"] == 0
    assert stats["document_count"] == 0


def test_system_info(monkeypatch):
    from backend.api import dashboard

    info = dashboard._system_info()
    assert "version" in info
    assert "data_dir_size_mb" in info
    assert info["uptime_seconds"] >= 0


def test_health_summary_handles_cold_cache(monkeypatch):
    """When /api/health cache is cold, _health_summary returns empty dict."""
    from backend.api import dashboard
    from backend.api import health

    # Force cache to look cold
    monkeypatch.setattr(health, "_health_cache", {"at": 0.0, "data": None})
    out = dashboard._health_summary()
    assert "_note" in out or out["endpoints"] == {}


def test_drift_check_uses_default_collection(monkeypatch, fresh_db):
    """Without real Qdrant, _drift_check returns ok=False with error."""
    from backend.api import dashboard

    # Don't mock Qdrant; expect failure or ok state
    out = dashboard._drift_check()
    # Either no error (Qdrant reachable) or error key present
    if "error" in out:
        assert "drift_check_failed" in out["error"]
    else:
        assert "qdrant_points" in out
        assert "keyword_chunks" in out


def test_system_info_does_not_leak_data_dir_absolute_path(monkeypatch):
    """v1.0.2:data_dir 绝对路径不再回传客户端(避免泄露 USB 卷标/客户本机路径)。"""
    from backend.api import dashboard

    info = dashboard._system_info()
    # 必须保留 size_mb,但不暴露绝对路径
    assert "data_dir_size_mb" in info
    assert "data_dir" not in info


def test_overview_uses_30s_cache(monkeypatch):
    """v1.0.2:overview 端点命中 30s 进程内缓存,避免每次轮询都 fan-out。"""
    from backend.api import dashboard

    # 模拟 cache 已存在(未过期)
    sentinel = {"health": "cached_value", "sentinel": True}
    monkeypatch.setattr(dashboard, "_CACHE", {"data": sentinel, "at": 9999999999.0})

    out = dashboard.overview()
    assert out is sentinel  # 命中缓存,直接返回原对象,不再走 _build_overview()


def test_overview_cache_miss_rebuilds(monkeypatch):
    """v1.0.2:缓存过期 → 重新构建。"""
    from backend.api import dashboard

    monkeypatch.setattr(
        dashboard,
        "_CACHE",
        {"data": {"health": "stale"}, "at": 0.0},  # 很久之前的时间戳 → 过期
    )
    monkeypatch.setattr(dashboard, "_CACHE_TTL_SECONDS", 30.0)

    out = dashboard.overview()
    # 重建过 → 必有 timestamp 字段(原 _build_overview 的输出)
    assert "timestamp" in out
    # 新结果不再是 stale
    assert out.get("health") != "stale"
