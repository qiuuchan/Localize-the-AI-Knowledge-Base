"""Dashboard aggregation endpoint (v0.8.11 P1.6,v1.0.2 hardened)。

GET /api/dashboard/overview — single RTT, returns:
  - health: { online, endpoints: {qwen,tavily,bing,qdrant,mineru,dify-api} }
  - degradations_24h: [{component, count}] (按 component 聚合最近 24h)
  - kb_stats: { database_count, document_count, chunk_count, databases:[...] }
  - drift: { qdrant_points, keyword_chunks, drift, ok } — 漂移告警
  - system: { version, data_dir_size_mb, uptime_seconds }
  - timestamp

v1.0.2 硬化:
  - 整体结果加 30s 进程内缓存,避免前端轮询时同步 fan-out + os.walk
  - data_dir 绝对路径不再回传给客户端(只保留 size_mb)
  - drift_check 改用 qdrant_store.get_collection_info 公开 API(不再借道私有)

各子聚合独立 try/except,任一失败返回 {"error": "..."} 不影响其他卡片。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from backend.core.config import get_data_dir, get_root_dir
from backend.core.cost_alert_guard import validate_cost_alert_payload
from backend.core.rag import qdrant_store as rag_qdrant
from backend.core.sqlite.degradation_repo import degradation_summary_by_component
from backend.core.sqlite.databases_repo import list_databases as _list_dbs

logger = logging.getLogger(__name__)

router = APIRouter()


_START_TIME = time.time()
_CACHE_TTL_SECONDS = 30.0
_CACHE: Dict[str, Any] = {"data": None, "at": 0.0}
_CACHE_LOCK = threading.Lock()


def _now_size_mb(data_dir: Path) -> float:
    """Walk data_dir and sum file sizes; return MB rounded to 2 decimals.

    Best-effort:单个文件 getsize 失败不影响累计。
    """
    total = 0
    for root, _dirs, files in os.walk(data_dir):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)


def _read_chunk_count() -> int:
    db_file = get_data_dir() / "db.sqlite"
    if not db_file.exists():
        return 0
    with sqlite3.connect(str(db_file)) as c:
        row = c.execute("SELECT COUNT(DISTINCT point_id) FROM keyword_index").fetchone()
        return row[0] if row else 0


def _health_summary() -> Dict[str, Any]:
    """复用 /api/health 缓存(30s TTL)而非现场探测 5 个端点。"""
    try:
        from backend.api.health import _health_cache
        cached = _health_cache.get("data")
        at = _health_cache.get("at", 0.0)
        if cached and (time.time() - at) < 30.0:
            return {
                "online": cached.get("online", False),
                "endpoints": cached.get("endpoints", {}),
            }
    except Exception as exc:
        return {"error": f"health_cache_unavailable: {exc!r}"}
    return {"online": False, "endpoints": {}, "_note": "cache cold, see /api/health"}


def _degradations_summary() -> List[Dict[str, Any]]:
    try:
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        return degradation_summary_by_component(since)
    except Exception as exc:
        return [{"error": f"degradation_query_failed: {exc!r}"}]


def _kb_stats() -> Dict[str, Any]:
    try:
        dbs = _list_dbs()
        total_documents = sum((d.get("document_count") or 0) for d in dbs)
        chunk_count = _read_chunk_count()
        return {
            "database_count": len(dbs),
            "document_count": total_documents,
            "chunk_count": chunk_count,
            "databases": [
                {"id": d["id"], "name": d["name"], "document_count": d.get("document_count", 0)}
                for d in dbs
            ],
        }
    except Exception as exc:
        return {"error": f"kb_stats_failed: {exc!r}"}


def _drift_check() -> Dict[str, Any]:
    """比对 Qdrant collection 数 vs keyword_index DISTINCT point_id 数。

    v1.0.2:改用 qdrant_store.get_collection_info 公开 API(不再借道私有
    `_request` + `_base_url`)。Qdrant 不可达时该 db points 为 None,不计入总数。
    """
    try:
        dbs = _list_dbs()
        total_qdrant = 0
        per_db: List[Dict[str, Any]] = []
        for db in dbs:
            coll = db["collection"]
            try:
                info = rag_qdrant.get_collection_info(coll)
                # info 为 None → 404(新 db 还没建 collection)
                points = (info or {}).get("points_count", 0) if info is not None else 0
            except Exception:
                points = None
            per_db.append(
                {
                    "id": db["id"],
                    "name": db["name"],
                    "collection": coll,
                    "qdrant_points": points,
                }
            )
            if points is not None:
                total_qdrant += points

        total_keyword_chunks = _read_chunk_count()
        drift = total_qdrant - total_keyword_chunks
        return {
            "qdrant_points": total_qdrant,
            "keyword_chunks": total_keyword_chunks,
            "drift": drift,
            "ok": abs(drift) <= 5,
            "per_db": per_db,
        }
    except Exception as exc:
        return {"ok": False, "error": f"drift_check_failed: {exc!r}"}


def _system_info() -> Dict[str, Any]:
    try:
        version = (Path(get_root_dir()) / "version").read_text(encoding="utf-8").strip()
    except OSError:
        version = "unknown"
    data_dir = get_data_dir()
    try:
        size_mb = _now_size_mb(data_dir)
    except Exception as exc:
        logger.warning("data_dir size walk failed: %s", exc)
        size_mb = 0.0
    return {
        "version": version,
        "uptime_seconds": int(time.time() - _START_TIME),
        "data_dir_size_mb": size_mb,
        # v1.0.2:不再回传 data_dir 绝对路径(避免泄露 USB 卷标/客户本机路径)
    }


def _build_overview() -> Dict[str, Any]:
    return {
        "health": _health_summary(),
        "degradations_24h": _degradations_summary(),
        "kb_stats": _kb_stats(),
        "drift": _drift_check(),
        "system": _system_info(),
        # v1.3.0: cost-alert 字段(月度配额等级 + 当月 / 当日开销)
        "cost_alert": _read_cost_alert(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# v1.3.0: cost-alert 默认值
_COST_ALERT_DEFAULT: Dict[str, Any] = {
    "level": 0,
    "today_yuan": 0.0,
    "month_yuan": 0.0,
    "month": "",  # v1.3.0:空字符串 = 无 rollup 数据,前端降级为 "用量数据采集中..."
    "thresholds": {"warn": 500, "high": 1000, "block": 1500},
    "updated_at": "",  # v1.3.0:空字符串 = 同上 sentinel
}


def _read_cost_alert() -> Dict[str, Any]:
    """v1.3.0: 从 data/health_status.json 读 cost_alert 字段。

    文件不存在 / JSON 损坏 / 字段缺失 → 返回默认 level=0(不阻断)。
    默认阈值与 scripts/cost-alert.ps1 默认值保持一致。

    v1.3.1: 末尾调用 validate_cost_alert_payload,字段级降级(level="3" → 0,
    thresholds=null → 默认,负数 month_yuan → 0 等),防止 chat 入口崩溃。
    """
    try:
        data_dir = get_data_dir()
        health_path = data_dir / "health_status.json"
        if not health_path.exists():
            return dict(_COST_ALERT_DEFAULT)
        health = json.loads(health_path.read_text(encoding="utf-8"))
        ca = health.get("cost_alert")
        if not isinstance(ca, dict):
            return dict(_COST_ALERT_DEFAULT)
        return validate_cost_alert_payload(ca)
    except Exception:
        return dict(_COST_ALERT_DEFAULT)


@router.get("/dashboard/overview")
def overview() -> Dict[str, Any]:
    """v1.0.2:30s 进程内缓存,避免前端轮询时每次都 fan-out + os.walk。"""
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE["data"]
        at = _CACHE["at"]
        if cached is not None and (now - at) < _CACHE_TTL_SECONDS:
            return cached
    # 缓存外重新构建;lock-released-then-rebuild 是有意为之(避免持锁做慢 IO)
    fresh = _build_overview()
    with _CACHE_LOCK:
        # 即便有并发也只保留最后一次结果,谁先写谁赢
        _CACHE["data"] = fresh
        _CACHE["at"] = now
    return fresh
