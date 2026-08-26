"""Knowledge base endpoints (pure Python RAG).

Replaces scripts/parse-doc.ps1 + scripts/embed-and-ingest.ps1 wrappers.

Endpoints:
  GET    /api/knowledge/documents
    -> [{source, chunk_count, doc_id}]

  POST   /api/knowledge/upload  (multipart file)
    -> enqueue background parse + embed + upsert task
    -> {task_id, filename, status}

  GET    /api/knowledge/tasks/{task_id}
    -> {task_id, filename, status, stage, error?}

  DELETE /api/knowledge/documents/{source}
    -> {deleted, source, qdrant, sqlite_deleted}

  GET    /api/knowledge/documents/{source}/chunks
    -> [{id, text, section, header_path}]

Pipeline (in _process_upload):
  1. Save uploaded file to data/uploads/<ts>_<filename>
  2. mineru.parse_to_markdown -> markdown
  3. chunker.split_into_chunks -> List[Chunk]
  4. embedder.embed_texts -> List[List[float]]
  5. qdrant_store.ensure_collection + upsert_points (UUID id)
  6. keyword_index.write_rows for hybrid search
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.core.config import get_data_dir
from backend.core.rag import chunker as rag_chunker
from backend.core.rag import embedder as rag_embedder
from backend.core.rag import keyword_index as rag_keyword
from backend.core.rag import metadata as rag_metadata
from backend.core.rag import mineru as rag_mineru
from backend.core.rag import qdrant_store as rag_qdrant
from backend.core.sqlite.databases_repo import (
    DEFAULT_DATABASE_ID,
    get_database,
    upsert_processing,
    finish_processing,
)
from backend.core.sqlite.degradation_repo import save_degradation_event

logger = logging.getLogger(__name__)

router = APIRouter()

_UPLOAD_DIR = get_data_dir() / "uploads"
_PARSED_DIR = get_data_dir() / "parsed"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_PARSED_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_COLLECTION = "kb_ai_chunks"

# v1.1.0 PR#2 (Task 2.2):upload 硬上限 — 防止前端误传巨大文件把
# data/uploads/ 或 Qdrant 撑爆。413 比 500 早,前端能在到达 background
# pipeline 之前拦截。
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_IMAGE_COUNT_PER_UPLOAD = 5

_TASKS: Dict[str, Dict[str, Any]] = {}


def _resolve_database(database_id: str) -> dict:
    """Look up a database by id, raise 404 if missing. Falls back to 'default' if empty."""
    db_id = database_id or DEFAULT_DATABASE_ID
    db = get_database(db_id)
    if not db:
        raise HTTPException(status_code=404, detail=f"database '{db_id}' 不存在")
    return db


def _source_in_db(source: str, database_id: str) -> str:
    """Prefix a source string with its db_id unless already prefixed.

    Used to namespace sources per database in keyword_index and Qdrant payloads.
    """
    # default db 短路:存量 source 是纯文件名,不要重写 namespace;否则
    # 'foo.md' 在 default 库里会被改成 'default::foo.md',历史数据 + 评测都炸。
    if database_id == DEFAULT_DATABASE_ID and "::" not in source:
        return source
    if "::" in source:
        # 已经是 '<db>::<file>' 形式就保持原样;v1.0.2 review 指出过:
        # 此短路不区分 db 是否匹配,假设 source 总是以正确 db 命名进入本函数
        # (调用方在 upload/delete/list 三处都已传入 database_id)。
        return source
    return f"{database_id}::{source}"


def _persist_stage(task_id: str, operation: str, source: str, database_id: str, stage: str) -> None:
    """Best-effort upsert_processing; SQLite failure MUST NOT break upload pipeline.

    失败只在 logger 输出,不污染 _TASKS — 单元测试 mock sqlite3.connect 时
    get_connection 会抛 TypeError,这是测试基础设施问题,不是产品问题。
    """
    try:
        upsert_processing(task_id, operation, source, database_id, stage, "processing")
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("kb_ai.knowledge").debug(
            "upsert_processing failed (non-fatal)", exc_info=True
        )


def _persist_finish(task_id: str, status: str, error: Optional[str] = None) -> None:
    """Best-effort finish_processing; SQLite failure MUST NOT break upload pipeline."""
    try:
        finish_processing(task_id, status, error=error)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("kb_ai.knowledge").debug(
            "finish_processing failed (non-fatal)", exc_info=True
        )


def _db_path():
    return get_data_dir() / "db.sqlite"


def _make_doc_id(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _task(task_id: str, **fields) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "task_id": task_id,
        "status": "pending",
        "stage": "等待处理",
        "created_at": int(time.time()),
    }
    base.update(fields)
    return base


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------


def _build_point(
    chunk: rag_chunker.Chunk,
    source_file: str,
    vector: list[float],
) -> dict[str, Any]:
    """Build a Qdrant point payload from a Chunk + its embedding vector.

    Kept as a small helper so the upload loop only worries about orchestration.
    ``source_file`` is defensively normalized to its bare filename via
    ``Path(...).name`` so an accidental absolute path (e.g.
    ``E:\\uploads\\report.md`` or ``/var/data/uploads/report.md``) never
    leaks into the Qdrant payload — only the basename survives.
    """
    safe_name = Path(source_file).name
    return {
        "id": chunk.id,
        "vector": vector,
        "payload": {
            "text": chunk.text,
            "source": chunk.source,
            "source_file": safe_name,
            "section": chunk.section,
            "header_path": chunk.header_path,
            "header_level": chunk.header_level,
            "date": chunk.date,
            "days_old": chunk.days_old,
            "temporal_weight": chunk.temporal_weight,
            "certainty": chunk.certainty,
            "chunk_type": chunk.chunk_type,
            # v1.2 PR2 Task 5: structured-document metadata. Defaults are
            # empty / None for non-xlsx chunks so existing payloads stay
            # backwards compatible — only the key set changes.
            "year_mentions": list(chunk.year_mentions),
            "sheet_name": chunk.sheet_name,
            "row_start": chunk.row_start,
            "row_end": chunk.row_end,
            "columns": list(chunk.columns),
        },
    }


def _process_upload(
    task_id: str,
    saved_path: Path,
    source: str,
    collection: str = DEFAULT_COLLECTION,
    database_id: str = DEFAULT_DATABASE_ID,
) -> None:
    """Parse + chunk + embed + upsert + keyword-index.

    Updates _TASKS[task_id] with progress. No exceptions escape; failures are
    captured in the task dict.

    v0.8.11(P1.1+P1.2):source 写入 keyword_index 前按 db_id 加前缀;每阶段调
    upsert_processing / finish_processing 以持久化状态,治 FMEA F07/F20。
    """
    try:
        _TASKS[task_id]["status"] = "parsing"
        _TASKS[task_id]["stage"] = "正在解析文档..."
        _persist_stage(task_id, "upload", source, database_id, "正在解析文档...")

        # 1. Parse to markdown
        try:
            doc_id = _make_doc_id(source)
            parse_result = rag_mineru.parse_to_markdown(
                saved_path,
                use_cache=True,
                cache_dir=_PARSED_DIR,
                doc_id=doc_id,
                db_id=database_id,  # v0.8.11(P2.2):解析产物按 db 分层
            )
        except Exception as e:
            _TASKS[task_id].update(
                status="failed", stage="解析失败", error=str(e)[:500]
            )
            return

        markdown = parse_result["markdown"]

        # 2. Chunk (Task 3: thread frontmatter + file mtime so each chunk
        #    carries date/days_old/temporal_weight/certainty/chunk_type).
        frontmatter, markdown_body = rag_metadata.extract_frontmatter(markdown)
        file_mtime = saved_path.stat().st_mtime
        document_date = rag_metadata.resolve_document_date(
            frontmatter, file_mtime=file_mtime
        )
        # v0.8.11(P1.1):chunker 写入的 source 在 Qdrant payload 与 keyword_index
        # 中都用 namespaced 版本,避免不同 db 的同名文件冲突。
        namespaced_source = _source_in_db(source, database_id)
        # v1.2 PR2 Task 5: thread the file extension so the chunker can
        # switch into xlsx_row_group mode and recover sheet / row metadata.
        # Anything other than "xlsx" hits the legacy text path unchanged.
        document_type = saved_path.suffix.lower().lstrip(".")
        chunks = rag_chunker.split_into_chunks(
            markdown_body,
            source=namespaced_source,
            document_date=document_date,
            document_mtime=file_mtime,
            document_type=document_type,
        )
        if not chunks:
            _TASKS[task_id].update(
                status="failed", stage="切片失败", error="未生成任何 chunk"
            )
            _persist_finish(task_id, "failed", "切片失败: 未生成任何 chunk")
            return

        _TASKS[task_id]["status"] = "embedding"
        _TASKS[task_id]["stage"] = f"正在嵌入 ({len(chunks)} 段)..."
        _persist_stage(task_id, "upload", source, database_id, f"正在嵌入 ({len(chunks)} 段)...")

        # 3. Embed
        try:
            texts = [c.text for c in chunks]
            vectors, stats = rag_embedder.embed_texts(texts)
        except Exception as e:
            _TASKS[task_id].update(
                status="failed", stage="嵌入失败", error=str(e)[:500]
            )
            _persist_finish(task_id, "failed", f"嵌入失败: {str(e)[:300]}")
            try:
                save_degradation_event(
                    None, None, "upload", f"embedding_failed: {str(e)[:200]}",
                    component="Embedding",
                )
            except Exception:
                pass
            return

        # 4. Ensure collection
        try:
            rag_qdrant.ensure_collection(collection)
        except Exception as e:
            _TASKS[task_id].update(
                status="failed", stage="Qdrant collection 失败", error=str(e)[:500]
            )
            _persist_finish(task_id, "failed", f"Qdrant ensure_collection 失败: {str(e)[:300]}")
            try:
                save_degradation_event(
                    None, None, "upload",
                    f"qdrant_ensure_collection_failed: {str(e)[:200]}",
                    component="Qdrant",
                )
            except Exception:
                pass
            return

        # 5. Upsert points
        _TASKS[task_id]["stage"] = f"正在入库 ({len(chunks)} points)..."
        _persist_stage(task_id, "upload", source, database_id, f"正在入库 ({len(chunks)} points)...")
        # source_file is the safe filename only — never the absolute path,
        # so we don't leak the USB-mounted path into the Qdrant payload.
        points: List[Dict[str, Any]] = [
            _build_point(c, saved_path.name, vec)
            for c, vec in zip(chunks, vectors)
        ]
        try:
            rag_qdrant.upsert_points(points, collection)
        except Exception as e:
            _TASKS[task_id].update(
                status="failed", stage="Qdrant upsert 失败", error=str(e)[:500]
            )
            _persist_finish(task_id, "failed", f"Qdrant upsert 失败: {str(e)[:300]}")
            try:
                save_degradation_event(
                    None, None, "upload",
                    f"qdrant_upsert_failed: {str(e)[:200]}",
                    component="Qdrant",
                )
            except Exception:
                pass
            return

        # 6. Write keyword index rows
        try:
            rows = []
            for c in chunks:
                for tok in c.tokens:
                    # 用 namespaced source 写 keyword_index
                    rows.append((tok, c.id, namespaced_source, c.text))
            if rows:
                rag_keyword.write_rows(rows)
        except Exception as e:
            _TASKS[task_id].update(
                status="failed", stage="keyword_index 失败", error=str(e)[:500]
            )
            _persist_finish(task_id, "failed", f"keyword_index 写入失败: {str(e)[:300]}")
            return

        # 7. v0.8.7 可靠性(F):入库后校验写入数 — keyword_index 覆盖的 chunk 数
        # 与切片数不一致时给出 warning(不判失败,但暴露"新资料搜不到"风险)
        verify_warning = None
        try:
            import sqlite3 as _sq

            _conn = _sq.connect(str(_db_path()))
            try:
                covered = _conn.execute(
                    "SELECT COUNT(DISTINCT point_id) FROM keyword_index WHERE source = ?",
                    (source,),
                ).fetchone()[0]
            finally:
                _conn.close()
            if covered < len(chunks):
                verify_warning = (
                    f"keyword_index 覆盖 {covered}/{len(chunks)} chunk,部分切片可能无法被关键词检索"
                )
        except Exception as e:
            verify_warning = f"入库校验异常: {str(e)[:200]}"

        _TASKS[task_id].update(
            status="done",
            stage="入库完成",
            chunk_count=len(chunks),
            embed_stats=stats,
            verified=verify_warning is None,
            warning=verify_warning,
        )
        _persist_finish(task_id, "done")
    except Exception as e:  # final safety net
        _TASKS[task_id].update(
            status="failed", stage="未捕获异常", error=str(e)[:500]
        )
        _persist_finish(task_id, "failed", f"未捕获异常: {str(e)[:300]}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/knowledge/documents")
def list_documents(
    database_id: str = Query(default=DEFAULT_DATABASE_ID, description="目标数据库 id"),
) -> List[Dict[str, Any]]:
    """List documents with chunk counts from keyword_index.

    v0.8.11(P1.1):按 database_id 过滤;namespaced source 解前缀后返回纯文件名。
    """
    db = _db_path()
    if not db.exists():
        return []
    _ = _resolve_database(database_id)  # 验证存在性,真正过滤在下面
    try:
        rows = rag_keyword.count_by_source(db)
    except Exception:
        logger.exception("查询文档失败")
        raise HTTPException(status_code=500, detail="查询文档失败(详见服务端日志)")

    prefix = "" if database_id == DEFAULT_DATABASE_ID else f"{database_id}::"
    out: List[Dict[str, Any]] = []
    for r in rows:
        src = r["source"]
        if prefix:
            if not src.startswith(prefix):
                continue
            display_source = src[len(prefix):]
        else:
            if "::" in src:
                # 其他 db 的不显示
                continue
            display_source = src
        out.append(
            {
                "source": display_source,
                "chunk_count": r["chunk_count"],
                "doc_id": _make_doc_id(display_source),
                "database_id": database_id,
            }
        )
    return out


@router.post("/knowledge/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    database_id: str = Query(default=DEFAULT_DATABASE_ID, description="目标数据库 id"),
) -> List[Dict[str, Any]]:
    """Upload one or more files for parse + embed + upsert.

    v1.1.0 PR#2 (Task 2.2):
      - 单图 ≤ MAX_IMAGE_BYTES (20MB)
      - 单次 ≤ MAX_IMAGE_COUNT_PER_UPLOAD (5 张)
      校验放在 background task 之前,前端可即时拿到 413,避免大文件阻塞
      BackgroundTasks 队列。

    Returns one task descriptor per uploaded file (in input order).
    """
    # v1.1.0 PR#2 (Task 2.2):数量硬上限 — 先于 size 检查,因为 size 需要
    # 逐个 seek/tell,数量直查 O(1)。
    if len(files) > MAX_IMAGE_COUNT_PER_UPLOAD:
        raise HTTPException(
            status_code=413,
            detail={
                "message": f"最多 {MAX_IMAGE_COUNT_PER_UPLOAD} 张/次",
                "limit": MAX_IMAGE_COUNT_PER_UPLOAD,
                "received": len(files),
            },
        )

    # v1.1.0 PR#2 (Task 2.2):单图大小硬上限 — UploadFile.size 在 starlette
    # 里可能是 None(取决于 content-length 是否到达),所以 fallback 到
    # seek 到文件尾 + tell()。注意:seek 后要 seek(0) 复位,否则下游
    # copyfileobj 会读到 0 字节。
    for f in files:
        size = getattr(f, "size", None)
        if size is None:
            f.file.seek(0, 2)
            size = f.file.tell()
            f.file.seek(0)
        if size > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "message": f"单图 ≤ {MAX_IMAGE_BYTES // (1024 * 1024)}MB",
                    "file_size_mb": round(size / (1024 * 1024), 2),
                },
            )

    db_row = _resolve_database(database_id)
    collection = db_row["collection"]

    timestamp = int(time.time())
    results: List[Dict[str, Any]] = []
    for idx, file in enumerate(files):
        if not file.filename:
            raise HTTPException(status_code=400, detail="缺少文件名")
        safe_name = Path(file.filename).name
        # 用 timestamp + idx 区分同秒多文件,避免覆盖
        saved_path = _UPLOAD_DIR / f"{timestamp}_{idx}_{safe_name}"
        try:
            with open(saved_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except Exception:
            logger.exception("保存上传文件失败 filename=%s", file.filename)
            raise HTTPException(status_code=500, detail="保存上传文件失败(详见服务端日志)")
        finally:
            try:
                file.file.close()
            except Exception:
                pass

        source = safe_name
        task_id = hashlib.sha256(
            f"{saved_path}:{time.time()}:{idx}".encode()
        ).hexdigest()[:16]
        _TASKS[task_id] = _task(
            task_id,
            filename=safe_name,
            saved_path=str(saved_path),
            source=source,
            collection=collection,
            database_id=database_id,
        )
        background_tasks.add_task(
            _process_upload, task_id, saved_path, source, collection, database_id
        )
        results.append(
            {
                "task_id": task_id,
                "filename": safe_name,
                "status": "pending",
                "database_id": database_id,
            }
        )
    return results


@router.get("/knowledge/tasks/{task_id}")
def get_task(task_id: str) -> Dict[str, Any]:
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/knowledge/documents/{source}")
def delete_document(
    source: str,
    database_id: str = Query(default=DEFAULT_DATABASE_ID, description="目标数据库 id"),
) -> Dict[str, Any]:
    if not source.strip():
        raise HTTPException(status_code=400, detail="source 不能为空")
    db_row = _resolve_database(database_id)
    collection = db_row["collection"]
    namespaced_source = _source_in_db(source, database_id)
    try:
        qdrant_resp = rag_qdrant.delete_by_source(namespaced_source, name=collection)
    except Exception:
        logger.exception("Qdrant 删除失败 source=%s collection=%s", namespaced_source, collection)
        raise HTTPException(status_code=502, detail="Qdrant 删除失败(详见服务端日志)")
    db = _db_path()
    sqlite_deleted = 0
    if db.exists():
        try:
            sqlite_deleted = rag_keyword.delete_by_source(namespaced_source, db)
        except Exception:
            logger.exception("SQLite 删除失败 source=%s", namespaced_source)
            raise HTTPException(status_code=500, detail="SQLite 删除失败(详见服务端日志)")
    return {
        "deleted": True,
        "source": source,
        "database_id": database_id,
        "qdrant": qdrant_resp.get("result", qdrant_resp),
        "sqlite_deleted": sqlite_deleted,
    }


@router.get("/knowledge/documents/{source}/chunks")
def list_chunks(
    source: str,
    database_id: str = Query(default=DEFAULT_DATABASE_ID),
    limit: int = 200,
    offset: Optional[str] = None,
) -> Dict[str, Any]:
    """List chunks for a source via Qdrant scroll-by-filter."""
    db_row = _resolve_database(database_id)
    collection = db_row["collection"]
    namespaced_source = _source_in_db(source, database_id)
    try:
        result = rag_qdrant.scroll_by_source(
            namespaced_source, name=collection, limit=min(limit, 1000), offset=offset
        )
    except Exception:
        logger.exception("Qdrant scroll 失败 source=%s collection=%s", namespaced_source, collection)
        raise HTTPException(status_code=502, detail="Qdrant scroll 失败(详见服务端日志)")
    raw_points = (result.get("result") or {}).get("points") or []
    chunks: List[Dict[str, Any]] = []
    for p in raw_points:
        payload = p.get("payload") or {}
        chunks.append(
            {
                "id": str(p.get("id")),
                "text": payload.get("text") or "",
                "section": payload.get("section"),
                "header_path": payload.get("header_path") or "",
                "source": payload.get("source") or namespaced_source,
            }
        )
    return {
        "source": source,
        "database_id": database_id,
        "chunks": chunks,
        "next_offset": (result.get("result") or {}).get("next_page_offset"),
    }


# ---------------------------------------------------------------------------
# v0.8.4 新增:重新嵌入端点 — 嵌入模型升级或缓存损坏时使用
# ---------------------------------------------------------------------------


def _reembed_source_sync(
    task_id: str,
    source: str,
    collection: str,
    database_id: str = DEFAULT_DATABASE_ID,
) -> None:
    """Re-embed all chunks for a source without re-parsing.

    Pipeline:
      1. scroll_by_source → 取所有点的 (id, text, payload)
      2. delete_by_source → 清掉旧点(留着 keyword_index + DB row 即可)
      3. embed_texts → 重新嵌入
      4. upsert_points → 写回(保持 id 不变,引用稳定)
      5. keyword_index.delete_by_source + write_rows(因为旧 keywords 可能含 stale id)
    """
    try:
        _TASKS[task_id]["status"] = "scanning"
        _TASKS[task_id]["stage"] = "扫描已有 chunks..."
        _persist_stage(task_id, "reembed", source, database_id, "扫描已有 chunks...")
        scroll = rag_qdrant.scroll_by_source(
            source, name=collection, limit=1000, offset=None
        )
        points = (scroll.get("result") or {}).get("points") or []
        if not points:
            _TASKS[task_id].update(
                status="failed", stage="无 chunks", error=f"未找到 source={source} 的 chunk"
            )
            return

        _TASKS[task_id]["status"] = "embedding"
        _TASKS[task_id]["stage"] = f"重新嵌入 {len(points)} 段..."
        texts = [(p.get("payload") or {}).get("text") or "" for p in points]
        vectors, stats = rag_embedder.embed_texts(texts)

        _TASKS[task_id]["stage"] = "删除旧点..."
        rag_qdrant.delete_by_source(source, name=collection)

        _TASKS[task_id]["stage"] = "写入新点..."
        new_points = []
        for p, vec in zip(points, vectors):
            payload = dict(p.get("payload") or {})
            new_points.append(
                {"id": str(p.get("id")), "vector": vec, "payload": payload}
            )
        rag_qdrant.upsert_points(new_points, collection)

        _TASKS[task_id]["stage"] = "重建 keyword_index..."
        db = _db_path()
        if db.exists():
            rag_keyword.delete_by_source(source, db)
            rows = []
            for p in points:
                pid = str(p.get("id"))
                payload = p.get("payload") or {}
                txt = payload.get("text") or ""
                # 直接用 tokenizer 分词
                from backend.core.rag.tokenizer import get_tokens
                for tok in get_tokens(txt):
                    rows.append((tok, pid, source, txt))
            if rows:
                rag_keyword.write_rows(rows, db)

        _TASKS[task_id].update(
            status="done",
            stage="reembed 完成",
            chunk_count=len(points),
            embed_stats=stats,
        )
        _persist_finish(task_id, "done")
    except Exception as e:
        _TASKS[task_id].update(
            status="failed", stage="reembed 失败", error=str(e)[:500]
        )
        _persist_finish(task_id, "failed", f"reembed 失败: {str(e)[:300]}")


@router.post("/knowledge/documents/{source}/reembed")
async def reembed_document(
    source: str,
    background_tasks: BackgroundTasks,
    database_id: str = Query(default=DEFAULT_DATABASE_ID),
) -> Dict[str, Any]:
    """Re-embed all chunks for a source without re-parsing.

    Use cases:
      - Embedding model upgraded (v3 → v4)
      - Cache corrupted / lost
      - Some chunks missing vectors

    Returns a task_id to poll via /api/knowledge/tasks/{task_id}.
    """
    if not source.strip():
        raise HTTPException(status_code=400, detail="source 不能为空")
    db_row = _resolve_database(database_id)
    collection = db_row["collection"]
    namespaced_source = _source_in_db(source, database_id)
    task_id = hashlib.sha256(f"reembed:{source}:{time.time()}".encode()).hexdigest()[:16]
    _TASKS[task_id] = _task(
        task_id,
        filename=f"[reembed] {source}",
        source=namespaced_source,
        collection=collection,
        database_id=database_id,
    )
    background_tasks.add_task(
        _reembed_source_sync, task_id, namespaced_source, collection, database_id
    )
    return {"task_id": task_id, "source": source, "status": "pending", "database_id": database_id}


# ---------------------------------------------------------------------------
# v1.2 PR2 Task 6: 显式 reparse — 重新解析 + 切片 + 嵌入 + staged 替换
# ---------------------------------------------------------------------------


def _process_reparse(
    task_id: str,
    saved_path: Path,
    source: str,
    collection: str = DEFAULT_COLLECTION,
    database_id: str = DEFAULT_DATABASE_ID,
) -> None:
    """Re-parse a document and replace its Qdrant points + keyword index.

    Staged replacement: new points are upserted first, then old-only IDs are
    deleted. If any pre-upsert step fails, the old index remains untouched.
    """
    namespaced_source = _source_in_db(source, database_id)
    try:
        # 1. Parse
        _TASKS[task_id]["status"] = "parsing"
        _TASKS[task_id]["stage"] = "正在重新解析文档..."
        _persist_stage(task_id, "reparse", source, database_id, "正在重新解析文档...")

        doc_id = _make_doc_id(source)
        try:
            parse_result = rag_mineru.parse_to_markdown(
                saved_path,
                use_cache=False,
                cache_dir=_PARSED_DIR,
                doc_id=doc_id,
                db_id=database_id,
            )
        except Exception as e:
            _TASKS[task_id].update(status="failed", stage="解析失败", error=str(e)[:500])
            _persist_finish(task_id, "failed", f"解析失败: {str(e)[:300]}")
            return

        markdown = parse_result["markdown"]

        # 2. Chunk
        frontmatter, markdown_body = rag_metadata.extract_frontmatter(markdown)
        file_mtime = saved_path.stat().st_mtime
        document_date = rag_metadata.resolve_document_date(frontmatter, file_mtime=file_mtime)
        document_type = saved_path.suffix.lower().lstrip(".")
        chunks = rag_chunker.split_into_chunks(
            markdown_body,
            source=namespaced_source,
            document_date=document_date,
            document_mtime=file_mtime,
            document_type=document_type,
        )
        if not chunks:
            _TASKS[task_id].update(status="failed", stage="切片失败", error="未生成任何 chunk")
            _persist_finish(task_id, "failed", "切片失败: 未生成任何 chunk")
            return

        # 3. Embed
        _TASKS[task_id]["status"] = "embedding"
        _TASKS[task_id]["stage"] = f"正在嵌入 ({len(chunks)} 段)..."
        _persist_stage(task_id, "reparse", source, database_id, f"正在嵌入 ({len(chunks)} 段)...")

        try:
            texts = [c.text for c in chunks]
            vectors, stats = rag_embedder.embed_texts(texts)
        except Exception as e:
            _TASKS[task_id].update(status="failed", stage="嵌入失败", error=str(e)[:500])
            _persist_finish(task_id, "failed", f"嵌入失败: {str(e)[:300]}")
            try:
                save_degradation_event(
                    None, None, "reparse", f"embedding_failed: {str(e)[:200]}",
                    component="Embedding",
                )
            except Exception:
                pass
            return

        # 4. Validate before touching Qdrant
        if len(vectors) != len(chunks):
            _TASKS[task_id].update(
                status="failed", stage="校验失败",
                error=f"向量数 {len(vectors)} != chunk 数 {len(chunks)}",
            )
            _persist_finish(task_id, "failed", "向量数与 chunk 数不一致")
            return
        for vec in vectors:
            if len(vec) != rag_qdrant.EMBEDDING_DIM:
                _TASKS[task_id].update(
                    status="failed", stage="校验失败",
                    error=f"向量维度 {len(vec)} != {rag_qdrant.EMBEDDING_DIM}",
                )
                _persist_finish(task_id, "failed", "向量维度校验失败")
                return

        new_points: List[Dict[str, Any]] = [
            _build_point(c, saved_path.name, vec) for c, vec in zip(chunks, vectors)
        ]
        new_ids = {p["id"] for p in new_points}
        if len(new_ids) != len(new_points):
            _TASKS[task_id].update(status="failed", stage="校验失败", error="point ID 不唯一")
            _persist_finish(task_id, "failed", "point ID 不唯一")
            return

        # 5. Scroll old IDs (read-only; old index untouched until upsert succeeds)
        _TASKS[task_id]["status"] = "replacing"
        _TASKS[task_id]["stage"] = "正在替换索引..."
        _persist_stage(task_id, "reparse", source, database_id, "正在替换索引...")

        old_ids: List[str] = []
        try:
            offset = None
            for _ in range(200):
                scroll = rag_qdrant.scroll_by_source(
                    namespaced_source, name=collection, limit=100, offset=offset
                )
                result = scroll.get("result") or {}
                for p in result.get("points") or []:
                    old_ids.append(str(p["id"]))
                offset = result.get("next_page_offset")
                if not offset:
                    break
        except Exception as e:
            _TASKS[task_id].update(status="failed", stage="scroll 失败", error=str(e)[:500])
            _persist_finish(task_id, "failed", f"scroll 旧索引失败: {str(e)[:300]}")
            return

        # 6. Upsert new points
        try:
            rag_qdrant.ensure_collection(collection)
            rag_qdrant.upsert_points(new_points, collection)
        except Exception as e:
            _TASKS[task_id].update(status="failed", stage="upsert 失败", error=str(e)[:500])
            _persist_finish(task_id, "failed", f"upsert 新索引失败: {str(e)[:300]}")
            try:
                save_degradation_event(
                    None, None, "reparse", f"qdrant_upsert_failed: {str(e)[:200]}",
                    component="Qdrant",
                )
            except Exception:
                pass
            return

        # 7. Delete old-only IDs
        stale_ids = [oid for oid in old_ids if oid not in new_ids]
        deleted_count = 0
        if stale_ids:
            try:
                rag_qdrant.delete_by_ids(stale_ids, name=collection)
                deleted_count = len(stale_ids)
            except Exception as e:
                logger.warning("reparse: 清理旧 point 失败 (non-fatal): %s", e)

        # 8. Rebuild keyword index
        db = _db_path()
        keyword_rows = 0
        try:
            if db.exists():
                rag_keyword.delete_by_source(namespaced_source, db)
                rows = []
                for c in chunks:
                    for tok in c.tokens:
                        rows.append((tok, c.id, namespaced_source, c.text))
                if rows:
                    rag_keyword.write_rows(rows, db)
                    keyword_rows = len(rows)
        except Exception as e:
            _TASKS[task_id].update(status="failed", stage="keyword_index 失败", error=str(e)[:500])
            _persist_finish(task_id, "failed", f"keyword_index 重建失败: {str(e)[:300]}")
            return

        _TASKS[task_id].update(
            status="done",
            stage="reparse 完成",
            chunk_count=len(chunks),
            old_count=len(old_ids),
            new_count=len(new_points),
            deleted_count=deleted_count,
            keyword_rows=keyword_rows,
            embed_stats=stats,
        )
        _persist_finish(task_id, "done")
    except Exception as e:
        _TASKS[task_id].update(status="failed", stage="未捕获异常", error=str(e)[:500])
        _persist_finish(task_id, "failed", f"未捕获异常: {str(e)[:300]}")


@router.post("/knowledge/documents/{source}/reparse")
async def reparse_document(
    source: str,
    background_tasks: BackgroundTasks,
    database_id: str = Query(default=DEFAULT_DATABASE_ID),
    upload_path: str = Query(..., description="data/uploads 下的相对文件名"),
) -> Dict[str, Any]:
    """Re-parse a document from its stored upload file, replacing old index.

    The upload_path must point to an existing file within data/uploads.
    Path traversal is rejected.
    """
    if not source.strip():
        raise HTTPException(status_code=400, detail="source 不能为空")

    upload_root = _UPLOAD_DIR.resolve()
    try:
        candidate = (upload_root / upload_path).resolve()
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="upload_path 无效")
    if candidate == upload_root or upload_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="upload_path 必须位于 data/uploads 内")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="upload 文件不存在")

    db_row = _resolve_database(database_id)
    collection = db_row["collection"]

    task_id = hashlib.sha256(f"reparse:{source}:{time.time()}".encode()).hexdigest()[:16]
    _TASKS[task_id] = _task(
        task_id,
        filename=f"[reparse] {source}",
        source=source,
        collection=collection,
        database_id=database_id,
    )
    _persist_stage(task_id, "reparse", source, database_id, "等待处理")
    background_tasks.add_task(
        _process_reparse, task_id, candidate, source, collection, database_id
    )
    return {"task_id": task_id, "source": source, "status": "pending", "database_id": database_id}


# ---------------------------------------------------------------------------
# v1.1.0 PR#3 Task 3.2: 静态图片端点 — 供 T3.3 ImageThumbnails 组件使用
# ---------------------------------------------------------------------------

_IMAGE_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@router.get("/knowledge/image")
def get_image(path: str = Query(..., description="data/uploads 下的相对文件名")):
    """Serve image bytes from data/uploads. Path-traversal protected.

    Pre-Flight Finding 3 修复:T3.3 ImageThumbnails 依赖此端点。
    """
    upload_dir = (get_data_dir() / "uploads").resolve()
    target = (upload_dir / path).resolve()
    # path-traversal 防护:resolved path 必须仍在 upload_dir 下
    try:
        target.relative_to(upload_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path 越界") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"image '{path}' 不存在")
    mime = _IMAGE_EXT_TO_MIME.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(str(target), media_type=mime)
