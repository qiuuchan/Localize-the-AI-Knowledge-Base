"""Unit tests for v1.0.2 公开 API:qdrant_store.get_collection_info。

原 v0.8.11 dashboard.py 借道私有 `_request` + `_base_url`;v1.0.2 把这层
约定沉到公开函数,稳定 contract:
  - 200 + 存在 → dict(含 points_count, 已清 _status)
  - 404 + allow_404=True → None
  - 底层异常透传
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.core.rag import qdrant_store as rag_qdrant


def test_get_collection_info_returns_dict_on_200():
    fake_resp = {
        "result": {
            "status": "green",
            "points_count": 42,
            "vectors_count": 42,
            "config": {"params": {"vectors": {"size": 1024}}},
        }
    }

    with patch.object(rag_qdrant, "_request", return_value=fake_resp) as mock_req:
        info = rag_qdrant.get_collection_info("kb_ai_chunks")

    assert info == {
        "status": "green",
        "points_count": 42,
        "vectors_count": 42,
        "config": {"params": {"vectors": {"size": 1024}}},
    }
    # 验证私有 status 噪音已剥掉
    assert "_status" not in info
    # 验证 _request 调用参数
    call = mock_req.call_args
    assert call.args[0] == "GET"
    assert call.args[1].endswith("/collections/kb_ai_chunks")
    assert call.kwargs.get("allow_404") is True


def test_get_collection_info_returns_none_on_404():
    fake_resp = {"_status": 404, "_body": "not found"}

    with patch.object(rag_qdrant, "_request", return_value=fake_resp):
        info = rag_qdrant.get_collection_info("nonexistent_collection")

    assert info is None


def test_get_collection_info_propagates_runtime_error():
    """底层网络/Qdrant 5xx 不应被吞,要让调用方感知。"""
    with patch.object(
        rag_qdrant, "_request", side_effect=RuntimeError("Qdrant unreachable")
    ):
        with pytest.raises(RuntimeError, match="unreachable"):
            rag_qdrant.get_collection_info("kb_ai_chunks")


def test_delete_by_ids_posts_point_ids():
    with patch.object(
        rag_qdrant, "_request", return_value={"result": {"status": "acknowledged"}}
    ) as request:
        result = rag_qdrant.delete_by_ids(["p1", "p2"], name="kb_ai_chunks")

    assert result["result"]["status"] == "acknowledged"
    assert request.call_args.args[0] == "POST"
    assert request.call_args.args[1].endswith("/collections/kb_ai_chunks/points/delete")
    assert request.call_args.kwargs["data"] == {"points": ["p1", "p2"]}


def test_delete_by_ids_empty_is_noop():
    result = rag_qdrant.delete_by_ids([])
    assert result["noop"] is True
