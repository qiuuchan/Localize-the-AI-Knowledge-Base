"""Tests for v1.5.0 backend containerization.

Static structural verification (does not require Docker daemon):
1. docker-compose.yml is valid YAML with kb-ai-backend service declared
2. kb-ai-backend has build: + image: kb-ai/backend:local
3. kb-ai-backend depends on qdrant + dify-api with service_healthy
4. kb-ai-backend has healthcheck pointing at /api/health
5. docker/backend/Dockerfile is multi-stage (builder + runtime)
6. start.bat step 6 uses docker compose up -d kb-ai-backend
7. stop.bat step 1 uses docker compose stop kb-ai-backend

Run from project root:
    backend/.venv/Scripts/python -m pytest tests/integration/test_backend_container.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
COMPOSE = REPO / "docker-compose.yml"
BACKEND_DOCKERFILE = REPO / "docker" / "backend" / "Dockerfile"
START_BAT = REPO / "start.bat"
STOP_BAT = REPO / "stop.bat"


def _load_compose() -> dict:
    """Load and parse docker-compose.yml."""
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_compose_config_parses():
    """docker-compose.yml is valid YAML and contains kb-ai-backend service."""
    data = _load_compose()
    assert "services" in data, "compose has no services section"
    assert "kb-ai-backend" in data["services"], "kb-ai-backend service missing"
    # Existing 4 services still present
    for svc in ("qdrant", "dify-api", "dify-worker", "dify-db-init"):
        assert svc in data["services"], f"{svc} service missing (regression)"


def test_kb_ai_backend_build_and_image():
    """kb-ai-backend has build: + image: kb-ai/backend:local."""
    data = _load_compose()
    svc = data["services"]["kb-ai-backend"]
    assert "build" in svc, "kb-ai-backend.build missing"
    assert svc["build"]["dockerfile"] == "docker/backend/Dockerfile"
    assert svc["image"] == "kb-ai/backend:local", (
        f"expected image 'kb-ai/backend:local', got {svc['image']!r}"
    )


def test_kb_ai_backend_depends_on_healthy():
    """kb-ai-backend depends on qdrant + dify-api with service_healthy condition."""
    data = _load_compose()
    deps = data["services"]["kb-ai-backend"]["depends_on"]
    assert deps.get("qdrant", {}).get("condition") == "service_healthy", (
        "qdrant dependency must use service_healthy condition"
    )
    assert deps.get("dify-api", {}).get("condition") == "service_healthy", (
        "dify-api dependency must use service_healthy condition"
    )


def test_kb_ai_backend_has_healthcheck():
    """kb-ai-backend has healthcheck pointing at /api/health."""
    data = _load_compose()
    hc = data["services"]["kb-ai-backend"]["healthcheck"]
    test_cmd = " ".join(hc["test"]) if isinstance(hc["test"], list) else str(hc["test"])
    assert "/api/health" in test_cmd, f"healthcheck must probe /api/health, got: {test_cmd!r}"
    assert hc.get("interval") == "30s"
    assert hc.get("retries") == 3


def test_kb_ai_backend_resource_limits():
    """kb-ai-backend has resource limits declared (matches v0.7.1 safety hardening)."""
    data = _load_compose()
    svc = data["services"]["kb-ai-backend"]
    assert svc.get("mem_limit") == "1g"
    assert svc.get("cpus") == "1.0"
    assert svc.get("pids_limit") == 200


def test_backend_dockerfile_is_multi_stage():
    """docker/backend/Dockerfile has builder + runtime stages with python:3.12-slim."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "AS builder" in df, "Dockerfile missing 'AS builder' stage"
    assert re.search(r"FROM python:3\.12-slim\b", df), "Dockerfile must use python:3.12-slim"
    # At least 2 FROM statements (multi-stage)
    from_count = len(re.findall(r"^FROM ", df, re.MULTILINE))
    assert from_count >= 2, f"Dockerfile must have >=2 FROM stages, found {from_count}"


def test_backend_dockerfile_uses_wheels():
    """Dockerfile uses pip wheel + --no-index pattern (offline install from builder)."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "pip wheel" in df, "builder stage must use 'pip wheel' for offline install"
    assert "pip install --no-index" in df, "runtime stage must use 'pip install --no-index'"
    assert "--find-links=/wheels" in df, "runtime stage must install from /wheels dir"


def test_backend_dockerfile_has_healthcheck():
    """Dockerfile declares HEALTHCHECK for kb-ai-backend container."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in df, "Dockerfile missing HEALTHCHECK directive"
    assert "/api/health" in df, "HEALTHCHECK must probe /api/health"


def test_backend_dockerfile_exposes_port_8000():
    """Dockerfile CMD runs uvicorn on :8000 (compose port mapping target)."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "uvicorn" in df, "CMD must invoke uvicorn"
    assert "8000" in df, "CMD must bind :8000"
    assert "0.0.0.0" in df, "uvicorn must bind 0.0.0.0 (not 127.0.0.1, needed for compose port mapping)"


def test_backend_dockerfile_cpu_torch_index():
    """v1.5.1: builder stage uses --index-url pytorch-cpu (avoid CUDA bloat)."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "download.pytorch.org/whl/cpu" in df, (
        "Dockerfile must use PyTorch CPU index to avoid CUDA toolkit bloat"
    )


def test_backend_dockerfile_installs_powershell():
    """v1.5.1: Dockerfile installs Linux PowerShell (pwsh) for ps_runner."""
    df = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "powershell" in df.lower(), "Dockerfile must install PowerShell"
    assert "github.com/PowerShell/PowerShell/releases" in df, (
        "Dockerfile should download PowerShell from official GitHub releases"
    )


def test_start_bat_uses_compose_for_backend():
    """start.bat step 6 uses docker compose up -d kb-ai-backend (v1.5.0+)."""
    content = START_BAT.read_text(encoding="utf-8")
    assert "docker compose up -d kb-ai-backend" in content, (
        "start.bat step 6 must use 'docker compose up -d kb-ai-backend'"
    )
    # v1.5.0+ header marker (允许 (v1.5.0) 或 (v1.5.0+ shipping) 两种写法)
    assert "(v1.5.0" in content, "start.bat header should reflect v1.5.0+"


def test_stop_bat_uses_compose_for_backend():
    """stop.bat step 1 uses docker compose stop kb-ai-backend (v1.5.0+)."""
    content = STOP_BAT.read_text(encoding="utf-8")
    assert "docker compose stop kb-ai-backend" in content, (
        "stop.bat step 1 must use 'docker compose stop kb-ai-backend'"
    )
    # v1.5.0 header marker
    assert "(v1.5.0)" in content, "stop.bat header should reflect v1.5.0"


def test_start_bat_mineru_logic_preserved():
    """v1.5.1+: start.bat 跳过 MinerU host-process launch(venv 路径不可移植),保留 skip 提示。

    Per CHANGELOG.md v1.5.1:
    - 移除 v0.8.9 阶段加的 `start \"KB-AI MinerU\" /min python.exe ... mineru_server.py`
    - 改为只探测 :8001 端口,跑不起来就 [跳过] + 提示用户
    - stop.bat 仍保留 v0.8.9 的 stop 逻辑(杀残留 python.exe)

    本测试守护 start.bat 的 v1.5.1+ 行为,防止它不小心重新引入
    不可移植的 host MinerU launch(回归 v0.8.9 那种问题)。
    """
    content = START_BAT.read_text(encoding="utf-8")
    # skip 提示 + fallback 必须保留
    assert "[跳过]" in content and "PDF/PPTX" in content, (
        "MinerU skip message must remain in start.bat (v1.5.1+ skip behavior)"
    )
    # 反向断言:start.bat 不应再直接调用 mineru_server.py
    # (那是 v0.8.9 的做法,被 v1.5.1 因为 venv 路径问题废弃)
    assert "mineru_server.py" not in content, (
        "start.bat should NOT directly invoke mineru_server.py "
        "(v1.5.1+ skip; venv path not portable across发盘机/客户机)"
    )


def test_stop_bat_mineru_logic_preserved():
    """stop.bat preserves MinerU host-process stop logic (v0.8.9 user authorization)."""
    content = STOP_BAT.read_text(encoding="utf-8")
    # v0.8.9 marker must remain
    assert "v0.8.9(用户授权):停止 MinerU" in content, (
        "MinerU host-process stop logic must be preserved in stop.bat"
    )
    assert "mineru_server.py" in content, "MinerU stop must remain"


def test_official_image_tags_unchanged():
    """Lock-version red lines: 4 official image tags + 1 existing local tag preserved."""
    data = _load_compose()
    images = {name: svc.get("image") for name, svc in data["services"].items()}
    # 锁版官方镜像
    assert images["qdrant"] == "qdrant/qdrant:v1.7.0", "qdrant tag must remain locked"
    assert images["dify-api"] == "langgenius/dify-api:1.0.0", "dify-api tag must remain locked"
    assert images["dify-worker"] == "langgenius/dify-api:1.0.0", "dify-worker tag must remain locked"
    # v1.4.0 local tag preserved
    assert images["dify-db-init"] == "kb-ai/dify-db-init:local", (
        "v1.4.0 dify-db-init local tag must remain"
    )
    # v1.5.0 local tag added
    assert images["kb-ai-backend"] == "kb-ai/backend:local", (
        "v1.5.0 kb-ai-backend local tag must be present"
    )