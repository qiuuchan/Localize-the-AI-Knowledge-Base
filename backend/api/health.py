"""Health and status endpoints."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.core.config import get_env_or_env_var, get_env_var, get_root_dir
from backend.core.ps_runner import run_ps

router = APIRouter()

# v0.8.7 性能优化(C):/api/health 30 秒内存缓存。
# 此前每次调用都现场起 PowerShell + 顺次探测 Qwen/Tavily/Bing(数秒~十几秒),
# 前端每 30s 轮询 → 状态栏频繁卡"检测中"。30s TTL 对齐前端轮询节奏。
_HEALTH_CACHE_TTL_SECONDS = 30.0
_health_cache: Dict[str, Any] = {"at": 0.0, "data": None}


_PLACEHOLDER_PATTERNS = [
    "PLEASE-FILL-IN",
    "sk-PLEASE-FILL-IN",
    "sk-PLEASE-FILL-IN-YOUR-ALIYUN-BAILIAN-API-KEY",
    "tvly-PLEASE-FILL-IN",
    "changeme",
]


def _is_placeholder(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    for p in _PLACEHOLDER_PATTERNS:
        if value == p or value.lower().startswith(p.lower()):
            return True
    return False


def _key_status(name: str) -> Dict[str, Any]:
    """Return whether a key is configured, without exposing the value."""
    env_val = os.environ.get(name, "").strip()
    file_val = get_env_var(name)

    if env_val:
        return {"configured": True, "source": "environment"}

    if file_val:
        return {"configured": True, "source": "env_file"}

    return {"configured": False, "source": "placeholder"}


def _bool_env(name: str, default: bool = False) -> bool:
    v = get_env_or_env_var(name)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


@router.get("/health")
def get_health() -> Dict[str, Any]:
    """Return the latest health probe result (cached for 30s).

    v1.5.1:容器内无 host PowerShell 脚本时返回降级状态(degraded)而非 503。
    """
    now = time.monotonic()
    if _health_cache["data"] is not None and (now - _health_cache["at"]) < _HEALTH_CACHE_TTL_SECONDS:
        return _health_cache["data"]
    root = get_root_dir()
    result = run_ps(
        root / "scripts" / "health-probe.ps1",
        args=["-OutputJson"],
        cwd=root,
        timeout=60,
    )
    # v1.5.1:host PS 脚本不存在(容器环境)→ 返回降级状态,不算失败
    if result.get("skipped"):
        degraded = {
            "status": "degraded",
            "mode": "container",
            "note": "host health-probe.ps1 not available in container; external probes skipped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # 也写入缓存,避免每秒重跑 file_exists 检查(虽然便宜,但保持一致性)
        _health_cache["at"] = now
        _health_cache["data"] = degraded
        return degraded
    if result["returncode"] != 0:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "health probe failed",
                "stderr": result["stderr"],
                "stdout": result["stdout"],
            },
        )
    if result["json"] is None:
        raise HTTPException(
            status_code=500,
            detail={"error": "health probe returned non-JSON output", "stdout": result["stdout"]},
        )
    _health_cache["at"] = now
    _health_cache["data"] = result["json"]
    return result["json"]


@router.get("/status")
def get_status() -> Dict[str, Any]:
    """Return combined system status: version, containers, capacity, AI."""
    root = get_root_dir()

    version = run_ps(
        root / "scripts" / "version.ps1",
        args=["-Json"],
        cwd=root,
        timeout=60,
    )
    disk = run_ps(
        root / "scripts" / "disk-alert.ps1",
        args=["-OutputJson", "-NoLog"],
        cwd=root,
        timeout=60,
    )
    health = run_ps(
        root / "scripts" / "health-probe.ps1",
        args=["-OutputJson"],
        cwd=root,
        timeout=60,
    )

    return {
        "scannedAt": datetime.now(timezone.utc).isoformat(),
        "version": version["json"] if version["returncode"] == 0 else None,
        "capacity": disk["json"] if disk["returncode"] == 0 else None,
        "health": health["json"] if health["returncode"] == 0 else None,
        "config": {
            "root": str(root),
            "env": {
                "ALIYUN_BAILIAN_API_KEY": _key_status("ALIYUN_BAILIAN_API_KEY"),
                "TAVILY_API_KEY": _key_status("TAVILY_API_KEY"),
                "BING_SEARCH_API_KEY": _key_status("BING_SEARCH_API_KEY"),
            },
            "model": {
                "name": get_env_or_env_var("MODEL_NAME") or "qwen3.6-plus",
                "name_max": get_env_or_env_var("MODEL_NAME_MAX") or "qwen3.7-max",
                "routing_enabled": _bool_env("MODEL_ROUTING_ENABLED", default=False),
            },
        },
        "errors": {
            "version": version["stderr"] if version["returncode"] != 0 else None,
            "capacity": disk["stderr"] if disk["returncode"] != 0 else None,
            "health": health["stderr"] if health["returncode"] != 0 else None,
        },
    }
