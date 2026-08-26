"""Unit tests for GET /api/knowledge/image static image endpoint.

v1.1.0 PR#3 Task 3.2: Backend image-serving endpoint for T3.3 ImageThumbnails.
"""

from fastapi.testclient import TestClient
from backend.main import app


def test_image_endpoint_returns_file_bytes(tmp_path, monkeypatch):
    """GET /api/knowledge/image?path= 应返回 data/uploads 下文件字节。"""
    from backend.core.config import get_data_dir
    # 准备一张假图片
    upload_dir = get_data_dir() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / "fake.png"
    target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    client = TestClient(app)
    resp = client.get("/api/knowledge/image?path=fake.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_endpoint_rejects_path_traversal():
    """path 越界(data 目录外)→ 403。"""
    client = TestClient(app)
    resp = client.get("/api/knowledge/image?path=../../etc/passwd")
    assert resp.status_code in (400, 403, 404)


def test_image_endpoint_missing_file_returns_404():
    """path 指向不存在文件 → 404。"""
    client = TestClient(app)
    resp = client.get("/api/knowledge/image?path=nonexistent_xyz.png")
    assert resp.status_code == 404
