"""Evaluation endpoint (v0.8.11 P2.1).

借鉴 Yuxi-Know `server/routers/evaluation_router.py` (8KB) — 把 eval
从命令行工具提升为产品功能,前端 Dashboard 卡片可触发 + 查看历史。

POST /api/eval/run   - 运行评测(默认 tests/eval/golden-qa.jsonl)
GET  /api/eval/results- 返回最近一次评测结果(进程内内存缓存)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# 进程内最近一次评测结果(单用户场景,不需要持久化)
_LAST_RESULT: Dict[str, Any] = {
    "result": None,
    "status": "idle",  # 'idle' | 'running' | 'done' | 'failed'
    "started_at": None,
    "finished_at": None,
    "error": None,
}
_LOCK = threading.Lock()


_DEFAULT_DATASET = "tests/eval/golden-qa.jsonl"


class RunEvalRequest(BaseModel):
    dataset_path: Optional[str] = Field(
        default=None,
        description="jsonl 数据集路径;默认 tests/eval/golden-qa.jsonl",
    )
    top_k: int = Field(default=5, ge=1, le=20)
    no_rerank: bool = Field(
        default=False,
        description="跳过 cross-encoder 重排(reranker 模型未下载时用)",
    )


def _resolve_dataset_path(user_path: Optional[str]) -> Path:
    """把客户端传入的 dataset_path 约束到项目根/tests/eval/ 下。

    只接受:
      - None   → 默认 golden-qa.jsonl
      - 裸文件名(不含路径分隔符、不以 .. 开头、不跨盘符)→ 解析到 <root>/tests/eval/ 下
      - 已经位于 <root>/tests/eval/ 之内的相对/绝对路径

    一切穿越尝试一律 400。这是有意为之的安全策略,虽然威胁模型仅 127.0.0.1 单用户。
    """
    from backend.core.config import get_root_dir

    root = Path(get_root_dir())
    allowed = (root / "tests" / "eval").resolve()
    if user_path is None or user_path == "":
        candidate = (allowed / "golden-qa.jsonl").resolve()
    else:
        # 禁止任何路径分隔符或父目录逃逸(避免 ../../etc/passwd 这种)
        p_str = user_path.replace("\\", "/")
        if "/" in p_str or ".." in Path(user_path).parts or ":" in user_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "dataset_path 仅接受 <root>/tests/eval/ 下的文件名或相对路径;"
                    "拒绝路径分隔符或父目录引用"
                ),
            )
        candidate = (allowed / user_path).resolve()
    # Python 3.12 起支持 Path.is_relative_to;直接用它做强约束
    if not candidate.is_relative_to(allowed):
        raise HTTPException(
            status_code=400,
            detail=f"dataset_path 解析后必须在 {allowed} 下",
        )
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"数据集不存在: {candidate.name}")
    return candidate


def _execute_evaluation(req: RunEvalRequest) -> Dict[str, Any]:
    """Inline call to tests/eval/run_eval.run_evaluation().

    通过 sys.path 注入 tests/ 路径,使 ``tests.eval.run_eval`` 可被 import。
    真单飞:locked 段内做 compare-and-swap,只有首个并发请求能进入 running 状态,
    其余立刻 409,避免并发跑评测烧真实阿里云 quota。
    """
    import sys
    import time

    from backend.core.config import get_root_dir

    root = Path(get_root_dir())
    # 把 tests/ 加进 sys.path(若尚未)
    tests_dir = root / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    try:
        from tests.eval.run_eval import run_evaluation
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"无法加载评测模块: {exc!r}",
        )

    # 先解析 dataset_path(任何 400/404 在翻 status 之前,失败不污染状态)
    dataset_path = str(_resolve_dataset_path(req.dataset_path))

    # 单飞 check-and-flip:持有 _LOCK 同时读+写 status,完成原子转换
    started = time.time()
    with _LOCK:
        if _LAST_RESULT["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="评测正在进行中,请稍后再试(已锁,避免并发烧钱)",
            )
        _LAST_RESULT["status"] = "running"
        _LAST_RESULT["started_at"] = started
        _LAST_RESULT["finished_at"] = None
        _LAST_RESULT["error"] = None

    base_url = "http://127.0.0.1:8000"  # 默认连本机

    try:
        result = run_evaluation(
            base_url=base_url,
            dataset_path=dataset_path,
            top_k=req.top_k,
            no_rerank=req.no_rerank,
        )
        with _LOCK:
            _LAST_RESULT["result"] = result
            _LAST_RESULT["status"] = "done"
            _LAST_RESULT["finished_at"] = time.time()
            _LAST_RESULT["error"] = result.get("error")
        return result
    except Exception as exc:
        with _LOCK:
            _LAST_RESULT["status"] = "failed"
            _LAST_RESULT["finished_at"] = time.time()
            _LAST_RESULT["error"] = repr(exc)
        # 不把内部异常透出:客户端只需要知道"失败 + 服务端日志有详情"
        logger.exception("eval run failed")
        raise HTTPException(status_code=500, detail="评测执行失败(详见服务端日志)")


@router.post("/eval/run")
def run_evaluation_endpoint(req: RunEvalRequest) -> Dict[str, Any]:
    """Run the golden-QA evaluation. Returns the structured result directly."""
    return _execute_evaluation(req)


@router.get("/eval/results")
def get_last_results() -> Dict[str, Any]:
    """Return the most recent evaluation result + status metadata."""
    with _LOCK:
        return dict(_LAST_RESULT)


@router.get("/eval/status")
def get_eval_status() -> Dict[str, Any]:
    """Lightweight status probe (no body, just state)."""
    with _LOCK:
        return {
            "status": _LAST_RESULT["status"],
            "started_at": _LAST_RESULT["started_at"],
            "finished_at": _LAST_RESULT["finished_at"],
            "has_result": _LAST_RESULT["result"] is not None,
            "error": _LAST_RESULT["error"],
        }
