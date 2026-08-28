"""Chat endpoint: pure Python RAG pipeline (replaces scripts/chat.ps1).

Pipeline:
  1. Retrieve top-K chunks via Hybrid Search (Qdrant vector + SQLite keyword, RRF)
  2. Format chunks into numbered ctx + citations list
  3. Optionally fall back to websearch (calls scripts/websearch.ps1)
     when all citation scores are below threshold and websearch is allowed.
  4. Build messages (system + user with context/history/web/query)
  5. Select model by routing keywords (Plus default, Max for complex queries)
  6. Call Qwen with L0->L1->L2->L3 fallback
  7. Parse LLM JSON response (answer | clarify | multi_choice)
  8. Persist session message + degradation events
  9. Yield SSE: status -> answer (or error)
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from backend.core.config import get_env_or_env_var, get_root_dir
from backend.core.ps_runner import run_ps
from backend.core.rag import llm as rag_llm
from backend.core.rag.retriever import retrieve
from backend.core.sqlite.messages_repo import get_messages, save_message
from backend.core.sqlite.degradation_repo import save_degradation_event
from backend.core.sqlite.sessions_repo import touch_session
from backend.api.dashboard import _read_cost_alert
from backend.api.sessions import generate_session_title_if_needed

router = APIRouter()

logger = logging.getLogger("kb_ai.chat")

DEFAULT_WEBSEARCH_THRESHOLD = 0.6


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(default=None)
    image_paths: Optional[List[str]] = Field(default=None)
    top_k: int = Field(default=5, ge=1, le=20)
    skip_websearch: bool = False
    max_tokens: int = Field(default=2000, ge=100, le=8000)
    # v1.1.0 PR#2: REQ-6 单会话 50 轮软上限,默认从 20 提到 50
    # (与 sessions.history_limit 默认 50、PRD REQ-6 对齐)。
    # v0.8.11(Task 5):历史轮数上限,与 max_tokens(LLM 输出 token 上限)解耦。
    # 旧实现用 payload.max_tokens 拉历史条数,导致 max_tokens 越小、上下文越短,
    # 期望历史长度只能通过调整 LLM 输出预算来实现,语义混乱。
    history_limit: int = Field(default=50, ge=1, le=100)
    model_name: Optional[str] = Field(default=None)
    model_name_max: Optional[str] = Field(default=None)
    disable_model_routing: bool = False
    model_routing_keywords: Optional[str] = Field(default=None)
    disable_hybrid: bool = False
    # v1.1.0 PR#3 (ui-feedback) Task 3.1: REQ-4 "按原问题回答" 跳过反问按钮
    # — 用户在前端点"跳过反问 / 按原问题回答"后,前端用此 flag 重新发原问题;
    # 后端若 LLM 仍返回 clarify,改写为 answer 路径(不再反问)。
    skip_clarification: bool = False


def _score_threshold() -> float:
    raw = get_env_or_env_var("SCORE_THRESHOLD")
    if not raw:
        return DEFAULT_WEBSEARCH_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_WEBSEARCH_THRESHOLD


def _all_below_threshold(citations: List[Dict[str, Any]], threshold: float) -> bool:
    """判断是否所有引用都低于阈值,触发 websearch 降级。

    v0.8.11(Task 5):基于 retrieval_confidence(标定到 [0, 1])而非 RRF 原始分数。
    RRF 分数无统一标定,单腿故障时易把"不可比"误判为"低于阈值",从而误联网。

    规则:
      - 空 citations 返回 True(无可用结果,允许 websearch,与旧行为一致)
      - 任一 citation 缺 retrieval_confidence 返回 False(保守,不联网)
      - 全部 confidence < threshold 才返回 True
    """
    if not citations:
        return True
    confidences = [c.get("retrieval_confidence") for c in citations]
    if any(confidence is None for confidence in confidences):
        return False
    return all(float(confidence) < threshold for confidence in confidences)


async def _maybe_websearch(query: str) -> Optional[Dict[str, str]]:
    """Run websearch.ps1 if available. Returns {text, source} or None.

    v0.8.11(Task 5):移除未使用的 threshold 参数;阈值判断统一在
    _all_below_threshold() 中完成,函数本身只关心"是否需要联网 + 拿到内容"。

    v2.1.0:修复自 T13 起从未生效的降级——旧实现传 `-Question`(脚本实际
    参数是 -Query,PowerShell 报错退出)且读 `content` 字段(脚本 JSON 契约
    是 results[]),导致该分支恒返回 None。现与 tools._web_search 同源:
    -Query + -OutputJson,拼接 title/url/snippet 文本。

    This is the only place the chat endpoint still touches PowerShell — it's a
    pre-existing fallback that goal-scope explicitly leaves alone.
    """
    root = get_root_dir()
    script = root / "scripts" / "websearch.ps1"
    if not script.exists():
        return None
    if not shutil.which("powershell") and not shutil.which("pwsh"):
        return None
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: run_ps(
                script,
                args=["-Query", query, "-OutputJson"],
                cwd=root,
                timeout=60,
            ),
        )
    except Exception:
        return None
    if result.get("returncode") != 0:
        return None
    payload = result.get("json") or {}
    results = payload.get("results") or []
    if not results:
        return None
    lines = []
    for i, r in enumerate(results, start=1):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        snippet = (r.get("snippet") or "").strip()
        lines.append(f"第{i}条: {title}\n来源: {url}\n摘要: {snippet}")
    return {"text": "\n\n".join(lines), "source": payload.get("source") or "web"}


async def _chat_events(payload: ChatRequest) -> AsyncIterator[Dict[str, Any]]:
    # v1.3.0: cost-alert level >= 3 在 retrieve 之前 early-return;
    # 省一次 Qdrant + keyword query;知识库检索仍可在其他端点使用。
    cost_alert = _read_cost_alert()
    if cost_alert.get("level", 0) >= 3:
        # 写 degradation_events 便于诊断;失败不遮蔽主链
        try:
            save_degradation_event(
                session_id=payload.session_id,
                query=payload.question,
                source="llm",
                reason=(
                    f"cost-alert block: ¥{cost_alert.get('month_yuan', 0):.0f}"
                ),
                model=None,
                component="LLM",
            )
        except Exception:
            logger.warning("failed to record cost-alert block event", exc_info=True)
        # SSE 路径:仅 yield error event,然后 return(不能再 raise HTTPException,
        # 否则会触发 Starlette "response already started" RuntimeError)。
        # 前端通过解析 error event.data.reason == "monthly_cost_exceeded" 来识别。
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "message": "月度配额超限,已阻断 LLM 调用",
                    "reason": "monthly_cost_exceeded",
                    "month_yuan": cost_alert.get("month_yuan", 0),
                    "threshold": cost_alert.get("thresholds", {}).get("block", 1500),
                    "hint": "知识库检索仍可用,降级到 websearch",
                },
                ensure_ascii=False,
            ),
        }
        return

    # v1.1.0 PR#2: REQ-6 单会话 50 轮软上限 — 80% 时在第一个 status 事件提示
    # 用户当前会话已接近上限(避免悄悄"塞满"才告知)。
    # 用全表计数 (limit=1000) 而非 history_limit,确保不会因截断而低估。
    soft_warning: Optional[str] = None
    if payload.session_id:
        try:
            all_msgs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: get_messages(payload.session_id, limit=1000),
            )
            history_count = len(all_msgs)
            if history_count >= payload.history_limit * 0.8:
                soft_warning = (
                    f"已达 {history_count}/{payload.history_limit} 轮,接近上限"
                )
        except Exception:
            logger.warning("soft_warning history count failed", exc_info=True)

    yield {
        "event": "status",
        "data": json.dumps(
            {
                "stage": "search",
                "message": "正在检索知识库...",
                "soft_warning": soft_warning,
            },
            ensure_ascii=False,
        ),
    }

    # 1. History
    history: List[Dict[str, Any]] = []
    if payload.session_id:
        try:
            # v0.8.11(Task 5):历史条数走 payload.history_limit,与 max_tokens 解耦。
            # 旧实现用 max_tokens 拉历史,把"输出预算"和"上下文长度"耦合。
            msgs = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: get_messages(payload.session_id, limit=payload.history_limit),
            )
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]
        except Exception:
            history = []

    # 2. Retrieve
    # v0.8.11(Task 5):retriever 现在接受 diagnostics dict,把"哪条召回腿失败 /
    # 用哪种 mode"等结构化降级原因回传给上层,逐条写入 degradation_events。
    retrieval_diagnostics: Dict[str, Any] = {}
    try:
        chunks = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: retrieve(
                payload.question,
                top_k=payload.top_k,
                hybrid_vector_candidates=20,
                hybrid_keyword_candidates=20,
                hybrid_rrf_k=60,
                disable_hybrid=payload.disable_hybrid,
                rerank_top_n=None,  # v0.8.7:跟随 retriever 默认值(10)与 RERANK_TOP_N env;原硬编码 20 会覆盖优化
                diagnostics=retrieval_diagnostics,
            ),
        )
    except Exception as e:
        # v0.8.11(Task 5):检索完全失败时,在现有 error SSE 前记录一次
        # retrieval_failed 降级事件;写入失败不能遮蔽原 error。
        try:
            save_degradation_event(
                session_id=payload.session_id,
                query=payload.question,
                source="retrieval",
                reason="retrieval_failed",
                model=None,
                component="Retrieval",
            )
        except Exception:
            logger.warning("failed to record retrieval_failed event", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": "知识库检索失败", "detail": str(e)[:500]}, ensure_ascii=False
            ),
        }
        return

    # 把每个降级原因(例如 vector_failed / keyword_failed)各写一条事件。
    # SQLite 写失败会被吞掉,绝不能影响主链 / 后续 SSE / 答案下发。
    for reason in retrieval_diagnostics.get("degradations", []) or []:
        # v0.8.11(P1.4):按 reason 拆分 component,便于 Dashboard 聚合
        comp = "Vector" if "vector" in reason else "Keyword" if "keyword" in reason else "Retrieval"
        try:
            save_degradation_event(
                session_id=payload.session_id,
                query=payload.question,
                source="retrieval",
                reason=reason,
                model=None,
                component=comp,
            )
        except Exception:
            logger.warning("failed to record retrieval degradation", exc_info=True)

    # v0.8.8(UX):检索完成后立即告知用户结果数量,等待可视化
    yield {
        "event": "status",
        "data": json.dumps(
            {"stage": "found", "message": f"已找到 {len(chunks)} 条相关资料"},
            ensure_ascii=False,
        ),
    }

    # 3. Format chunks
    formatted = rag_llm.format_chunks_only(chunks, max_context_chars=6000)
    citations = formatted["citations"]

    # 4. Optional websearch fallback
    web_results: Optional[str] = None
    web_source: Optional[str] = None
    threshold = _score_threshold()
    if not payload.skip_websearch and _all_below_threshold(citations, threshold):
        yield {
            "event": "status",
            "data": json.dumps(
                {"stage": "websearch", "message": "知识库资料不够，正在联网补充搜索..."},
                ensure_ascii=False,
            ),
        }
        ws = await _maybe_websearch(payload.question)
        if ws:
            web_results = ws["text"]
            web_source = ws["source"]

    # 5. Build messages
    messages = rag_llm.build_messages(
        question=payload.question,
        context_chunks=chunks,
        history=history,
        history_limit=payload.history_limit,
        web_results=web_results,
    )

    # 6. Model routing + chat with fallback
    primary, reason = rag_llm.select_model(
        payload.question,
        model_name=payload.model_name,
        model_name_max=payload.model_name_max,
        routing_keywords=payload.model_routing_keywords,
        disable_routing=payload.disable_model_routing,
    )

    # v0.8.8(UX):进入 LLM 流式生成前的最后阶段提示,此后 draft 逐字流出
    yield {
        "event": "status",
        "data": json.dumps(
            {"stage": "thinking", "message": "AI 正在思考并组织回答..."},
            ensure_ascii=False,
        ),
    }

    # v0.8.7 性能优化(D):流式生成 — 边收 token 边下发 draft 事件,
    # 首字时间从"整段生成完才显示"提前到"检索完 ~2s 即见字"。
    # 若模型走 JSON 契约(clarify/multi_choice,首字符为 { 或 `)则抑制 draft,
    # 等完整解析后直接下发 answer(行为与旧版一致)。
    content = ""
    meta: Dict[str, str] = {}
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _stream_worker() -> None:
        parts: List[str] = []
        try:
            for delta in rag_llm.chat_stream_with_fallback(
                messages,
                primary_model=primary,
                meta=meta,
                max_tokens=payload.max_tokens,
                session_id=payload.session_id,
                query_for_event=payload.question,
            ):
                parts.append(delta)
                loop.call_soon_threadsafe(queue.put_nowait, ("token", delta))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", "".join(parts)))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

    loop.run_in_executor(None, _stream_worker)

    draft_emitted = 0
    stream_error: Optional[Exception] = None
    while True:
        kind, val = await queue.get()
        if kind == "token":
            content += val
            stripped = content.lstrip()
            if stripped and stripped[0] in "{`":
                # JSON 契约输出:增量提取 content 字段,只把正文流给用户
                partial = rag_llm.extract_streaming_content(content)
                if len(partial) > draft_emitted:
                    yield {
                        "event": "draft",
                        "data": json.dumps(
                            {"text": partial[draft_emitted:]}, ensure_ascii=False
                        ),
                    }
                    draft_emitted = len(partial)
            else:
                yield {
                    "event": "draft",
                    "data": json.dumps({"text": val}, ensure_ascii=False),
                }
        elif kind == "done":
            content = val
            break
        else:
            stream_error = val
            break

    used_model = meta.get("model") or primary
    model_reason = reason
    if meta.get("reason") == "fallback":
        # 只有真正触发 fallback 模型时才覆盖路由原因
        model_reason = "fallback"

    if stream_error is not None:
        # All retries failed
        yield {
            "event": "error",
            "data": json.dumps(
                {"message": "AI 调用失败", "detail": str(stream_error)[:500]}, ensure_ascii=False
            ),
        }
        # v0.8.6(F11/FMEA):降级台账写入失败不得再抛错(错误事件已下发)
        try:
            save_degradation_event(
                session_id=payload.session_id,
                query=payload.question,
                source="chat",
                reason=f"all_retries_failed: {type(stream_error).__name__}",
                model=primary,
                component="LLM",
            )
        except Exception:
            logger.warning("failed to record all_retries_failed event", exc_info=True)
        return

    # 7. Parse LLM response
    parsed = rag_llm.parse_llm_response(content)
    response_type = parsed.get("type") or "answer"
    answer_content = parsed.get("content") or ""
    clarify_question = parsed.get("question")
    multi_options = parsed.get("options")

    citations_idx = parsed.get("citations") if isinstance(parsed.get("citations"), list) else []

    # v1.1.0 PR#3 (ui-feedback) Task 3.1: REQ-4 跳过反问 — 用户点"按原问题回答"后,
    # 前端带 skip_clarification=true 重发;若 LLM 仍返回 clarify,改写为 answer 路径
    # (不再下发反问 question,直接给"已按原问题给出回答"占位)。fallback_answer
    # 字段当前 LLM 协议未定义,实现端只能给出占位说明;citations 保留以便审计。
    if payload.skip_clarification and response_type == "clarify":
        fallback_answer = parsed.get("fallback_answer")
        if fallback_answer:
            answer_content = fallback_answer
        else:
            answer_content = f"已按原问题给出回答: {payload.question}"
        response_type = "answer"
        clarify_question = None

    # 8./9. Persist + degradation events
    # v0.8.6(F11/FMEA):持久化在答案下发之前,SQLite 写失败(U 盘拔出/锁定/损坏)
    # 会导致已生成的答案发不出;包 try 兜底,宁可丢记录、不可丢答案
    # (对齐 llm.py:233-235 的有意设计)。
    sid = payload.session_id
    try:
        if sid:
            persist_citations = citations_idx or [c["index"] for c in citations]
            save_message(
                session_id=sid,
                role="assistant",
                content=answer_content,
                citations=persist_citations,
            )
            touch_session(sid)

            # v1.1.0 PR#4 Task 4.4:流式标题生成。
            # 仅在当前 title 仍是默认 "新会话" 且 ≥ 3 条消息时触发,
            # 已有真实标题的会话幂等跳过。LLM 失败不阻塞 SSE。
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: generate_session_title_if_needed(sid),
                )
            except Exception:
                logger.warning("title generation trigger failed", exc_info=True)

        if model_reason == "fallback":
            save_degradation_event(
                session_id=sid,
                query=payload.question,
                source="model_fallback",
                reason=f"主模型失败后切换备用模型: {used_model}",
                model=used_model,
                component="LLM",
            )
        if web_source:
            save_degradation_event(
                session_id=sid,
                query=payload.question,
                source=web_source,
                reason="top-K 低于阈值，触发 websearch 降级",
                model=used_model,
                component="Websearch",
            )
    except Exception:
        logger.warning(
            "chat persistence failed (answer still delivered)", exc_info=True
        )

    # 10. Yield final answer
    final_answer: Dict[str, Any] = {
        "type": response_type,
        "content": answer_content,
        "citations": citations,
        "citations_idx": citations_idx,
        "web_source": web_source or "",
        "session_id": sid,
        "offline": False,
        "model": used_model,
        "model_reason": model_reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if clarify_question:
        final_answer["question"] = clarify_question
    if multi_options:
        final_answer["options"] = multi_options

    yield {
        "event": "answer",
        "data": json.dumps(final_answer, ensure_ascii=False),
    }


@router.post("/chat")
def chat(payload: ChatRequest) -> EventSourceResponse:
    return EventSourceResponse(_chat_events(payload))
