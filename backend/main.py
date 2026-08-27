"""KB-AI FastAPI backend entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import agent, boot, chat, dashboard, databases, debug, eval, health, knowledge, sessions, shutdown, tags
from backend.core.config import get_root_dir
from backend.core.sqlite import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def _read_version() -> str:
    """读取项目根 version 文件(单一版本真相源),失败回退默认。"""
    try:
        v = (Path(get_root_dir()) / "version").read_text(encoding="utf-8").strip()
        return v or "0.8.6"
    except OSError:
        return "0.8.6"


app = FastAPI(
    title="KB-AI Backend",
    version=_read_version(),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        # Dify Web UI 同源访问(v0.8.4 之前的主入口;保留兼容)
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(knowledge.router, prefix="/api", tags=["knowledge"])
app.include_router(databases.router, prefix="/api", tags=["databases"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(shutdown.router, prefix="/api", tags=["shutdown"])
app.include_router(boot.router, prefix="/api", tags=["boot"])
app.include_router(debug.router, prefix="/api", tags=["debug"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(eval.router, prefix="/api", tags=["eval"])
app.include_router(tags.router, prefix="/api", tags=["tags"])
app.include_router(agent.router, prefix="/api", tags=["agent"])


@app.get("/api")
def api_root():
    return {"name": "KB-AI Backend", "version": _read_version(), "root": str(get_root_dir())}


# Serve frontend static build if present (Vite produces frontend/dist)
static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
