"""Boot endpoint: SSE stream of container startup progress."""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend.core.config import get_env_or_env_var, get_env_path, get_root_dir

logger = logging.getLogger(__name__)
router = APIRouter()

STAGES = [
    ("root", "定位 U 盘根目录", 10),
    ("docker", "检查 Docker Desktop", 20),
    ("compose", "启动 Docker 容器", 30),
    ("qdrant", "等待 Qdrant 就绪", 45),
    ("dify", "等待 Dify Web UI 就绪", 70),
    ("worker", "等待 dify-worker 就绪", 85),
    ("ready", "KB-AI 启动完成", 100),
]


def _dify_port() -> int:
    p = get_env_or_env_var("DIFY_PORT")
    if p:
        try:
            return int(p)
        except ValueError:
            pass
    return 8080


def _docker_available() -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def _qdrant_ready() -> bool:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:6333/",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _dify_api_ready(port: int) -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _compose_up(root: Path) -> bool:
    try:
        r = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        return r.returncode == 0
    except Exception:
        return False


def _running_count(root: Path) -> int:
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if out.returncode != 0:
            return 0
        count = 0
        for line in out.stdout.decode("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                state = str(obj.get("State", obj.get("state", ""))).lower()
                if "running" in state:
                    count += 1
            except Exception:
                continue
        return count
    except Exception:
        return 0


def _env_check_status() -> Dict[str, Any]:
    """Return env readiness status before attempting docker compose up.

    Mirrors start.bat behaviour: .env must exist and ALIYUN_BAILIAN_API_KEY
    must be filled with a non-placeholder value.
    """
    env_path = get_env_path()
    if not env_path.exists():
        return {
            "ready": False,
            "stage": "env",
            "message": f".env 配置文件不存在 ({env_path})",
            "percent": 5,
        }

    key = get_env_or_env_var("ALIYUN_BAILIAN_API_KEY")
    if not key:
        return {
            "ready": False,
            "stage": "env",
            "message": "ALIYUN_BAILIAN_API_KEY 未配置或仍为占位符，请编辑 .env 填入真实 Key",
            "percent": 5,
        }

    return {"ready": True, "stage": "env", "message": "配置检查通过", "percent": 5}


def _boot_worker(root: Path, queue: asyncio.Queue) -> None:
    """Synchronous worker that pushes boot-stage events to the async queue."""

    def emit(stage: str, message: str, percent: int, done: bool = False, error: bool = False):
        queue.put_nowait(
            {
                "event": "progress",
                "data": json.dumps(
                    {"stage": stage, "message": message, "percent": percent, "done": done, "error": error},
                    ensure_ascii=False,
                ),
            }
        )

    # Pre-flight env check
    env_status = _env_check_status()
    emit(env_status["stage"], env_status["message"], env_status["percent"], error=not env_status["ready"])
    if not env_status["ready"]:
        return

    # v0.8.11(P1.2):启动时孤儿任务自检,治 FMEA F07(进程崩状态丢)
    try:
        from backend.core.sqlite.databases_repo import recover_orphans
        n = recover_orphans(max_age_seconds=600)
        if n:
            emit(
                "orphan_recovery",
                f"清理 {n} 个上次未完成的任务",
                7,
            )
        else:
            emit("orphan_recovery", "无孤儿任务", 7)
    except Exception as exc:
        emit(
            "orphan_recovery",
            f"自检失败(非致命): {str(exc)[:200]}",
            7,
            error=True,
        )

    # v1.1.0 PR#4: schema migration — 仅 tags/doc_tags 表(history_limit 在 PR#2 init_db 已加)
    queue.put_nowait(
        {
            "event": "boot_progress",
            "data": json.dumps(
                {
                    "stage": "schema_migration",
                    "percent": 8,
                    "label": "应用 v1.1.0 schema migration (tags/doc_tags)",
                }
            ),
        }
    )
    try:
        from backend.core.sqlite import init_db
        init_db()  # idempotent; CREATE IF NOT EXISTS + ALTER 跳过已存在的列
    except Exception as exc:  # noqa: BLE001
        logger.warning("schema migration 失败(已存在?): %s", exc)

    port = _dify_port()
    emit("root", "已定位 U 盘根目录", 10)

    if not _docker_available():
        emit("docker", "Docker Desktop 未运行，请启动后重试", 20, error=True)
        return
    emit("docker", "Docker Desktop 已就绪", 20)

    if not _compose_up(root):
        emit("compose", "docker compose up 失败，请检查日志", 30, error=True)
        return
    emit("compose", "容器已启动，等待服务就绪", 30)

    # Poll qdrant
    deadline = time.time() + 60
    while time.time() < deadline:
        if _qdrant_ready():
            break
        time.sleep(2)
    else:
        emit("qdrant", "Qdrant 未在 60 秒内就绪", 45, error=True)
        return
    emit("qdrant", "Qdrant 已就绪", 45)

    # Poll dify-api /health
    deadline = time.time() + 120
    while time.time() < deadline:
        if _dify_api_ready(port):
            break
        time.sleep(3)
    else:
        emit("dify", f"Dify Web UI (port {port}) 未在 120 秒内就绪", 70, error=True)
        return
    emit("dify", "Dify Web UI 已就绪", 70)

    # Wait for worker container to appear running
    deadline = time.time() + 90
    while time.time() < deadline:
        if _running_count(root) >= 3:  # qdrant + dify-api + dify-worker
            break
        time.sleep(3)
    else:
        emit("worker", "dify-worker 未在 90 秒内就绪", 85, error=True)
        return
    emit("worker", "dify-worker 已就绪", 85)

    emit("ready", "KB-AI 启动完成", 100, done=True)


async def _boot_events() -> AsyncIterator[Dict[str, Any]]:
    root = get_root_dir()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Start the blocking boot sequence in a thread
    future = loop.run_in_executor(None, _boot_worker, root, queue)

    # Drain queue until worker finishes
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=300)
            yield event
        except asyncio.TimeoutError:
            yield {
                "event": "error",
                "data": json.dumps({"message": "启动进度流超时"}, ensure_ascii=False),
            }
            return
        # If the event marks done/error, wait for worker and exit
        if event["event"] == "progress":
            data = json.loads(event["data"])
            if data.get("done") or data.get("error"):
                await future
                return


@router.get("/boot")
def boot() -> EventSourceResponse:
    return EventSourceResponse(_boot_events())
