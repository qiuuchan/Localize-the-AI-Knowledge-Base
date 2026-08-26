"""Unit tests for v1.1.0 PR#1 — bulk_assign Qdrant payload rewrite.

覆盖 known-limitations §2 #11:`bulk_assign_documents_to_database` 不同步
重写 Qdrant payload.source,导致向量检索按旧 source 过滤、关键词检索按新
前缀走,同文档可在两库中命中。本模块新增 `_rewrite_qdrant_payloads` 关闭该
不一致。

TDD 顺序:写失败测试 → 跑测试确认失败 (ImportError) → 实现 → 跑测试确认通过。
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from backend.core import sqlite as sqlite_mod
from backend.core.sqlite import databases_repo, connection


# ---------------------------------------------------------------------------
# Step 1:核心契约 — Qdrant payload 改写存在
# ---------------------------------------------------------------------------


def test_rewrite_payloads_calls_set_payload(monkeypatch):
    """成功场景:Qdrant 应被调用 set_payload 批量改 source。

    monkeypatch 目标:bulk_assign 模块内的 `_qdrant_set_payload_batch` /
    `_scroll_points_by_source`(私有 helper,test 可 mock)。
    """
    calls = []

    def fake_set_payload(collection, points, **kw):
        calls.append({"collection": collection, "payload": points})

    monkeypatch.setattr(
        "backend.core.bulk_assign._qdrant_set_payload_batch",
        fake_set_payload,
    )
    monkeypatch.setattr(
        "backend.core.bulk_assign._scroll_points_by_source",
        lambda *a, **kw: [
            {"id": "p1", "payload": {"source": "old_db::foo.pdf"}},
            {"id": "p2", "payload": {"source": "old_db::foo.pdf"}},
        ],
    )

    from backend.core.bulk_assign import _rewrite_qdrant_payloads

    result = _rewrite_qdrant_payloads(
        old_source="old_db::foo.pdf",
        new_source="new_db::foo.pdf",
        collection="kb_chunks_old_db",
    )

    assert result["rewritten"] == 2
    assert len(calls) == 1
    # points 是 list of {id, payload};每个 point 的 payload.source 应是新值
    rewritten_sources = [p["payload"]["source"] for p in calls[0]["payload"]]
    assert rewritten_sources == ["new_db::foo.pdf", "new_db::foo.pdf"]
    # id 必须保留(scroll 返回的 id)
    rewritten_ids = [p["id"] for p in calls[0]["payload"]]
    assert rewritten_ids == ["p1", "p2"]


# ---------------------------------------------------------------------------
# Step 6:集成 — bulk_assign_documents_to_database 触发 Qdrant rewrite
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_db(monkeypatch):
    """同 test_database_crud.py:重定向 SQLite 到临时文件,重建 schema。"""
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-bulk-assign-"))
    db_file = tmp / "test.sqlite"
    monkeypatch.setattr("backend.core.sqlite.connection.get_db_path", lambda: db_file)
    sqlite_mod.init_db()
    yield db_file
    try:
        db_file.unlink()
        os.rmdir(tmp)
    except OSError:
        pass


def test_bulk_assign_calls_qdrant_rewrite(monkeypatch, fresh_db):
    """bulk_assign_documents_to_database 应触发 Qdrant payload rewrite。

    测试契约:source 入参已带 `<old_db>::<filename>` 前缀,新 prefix = `new_db::`。
    keyword_index 重写 + Qdrant payload 重写两步都跑。
    """
    # 准备目标 db(不存在时 bulk_assign 抛 ValueError)
    databases_repo.create_database("new_db", "新库")

    # mock Qdrant rewrite(不真打 Qdrant,只断言被调过)
    rewrite_calls = []

    def fake_rewrite(**kw):
        rewrite_calls.append(kw)
        return {"rewritten": 5, "warnings": []}

    monkeypatch.setattr(
        "backend.core.sqlite.databases_repo._rewrite_qdrant_payloads",
        fake_rewrite,
    )

    # 在 keyword_index 插一些"default::foo.pdf" 假数据
    conn = connection.get_connection()
    conn.executemany(
        "INSERT INTO keyword_index (word, point_id, source, text) VALUES (?, ?, ?, ?)",
        [
            ("hello", "p1", "default::foo.pdf", "..."),
            ("world", "p2", "default::foo.pdf", "..."),
        ],
    )
    conn.commit()
    conn.close()

    affected = databases_repo.bulk_assign_documents_to_database(
        db_id="new_db",
        sources=["default::foo.pdf"],
    )
    # 至少有 1 个 source 字符串被重写
    assert affected >= 1
    # Qdrant rewrite 至少被调用 1 次(每个 source 一次)
    assert len(rewrite_calls) >= 1
    # 调用的 new_source 应带新 db_id 前缀
    assert all(
        call["new_source"].startswith("new_db::")
        for call in rewrite_calls
    )
