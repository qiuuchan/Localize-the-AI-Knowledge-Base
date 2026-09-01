"""上下文 token 预算 + 滚动摘要(T10 / v2.2,ADR-0003 配套)。

Spike 结论(2026-09-01):
  - `rag/tokenizer.py` 是检索关键词分词器(小写/去停用词/去重),与 LLM
    上下文 token 计量口径完全不同,不能直接复用;
  - cost 计量的单一真相源是 API 返回的真实 usage(`llm._log_token_usage`),
    但那是"事后"数字;上下文预算需要在"调用前"决定塞多少历史,只能估算;
  - 因此这里实现轻量启发式估算(零新依赖,不引 tiktoken):
      中文/CJK 字符 ≈ 1 token/字符(qwen3.6-plus 实测常见 0.6-1.2)
      ASCII 文本   ≈ 1 token / 4 字符
      整体乘保守系数 1.2 向上取整 —— 宁可高估,低估会撑爆 context。

设计决策(详见 docs/adr/0003-context-engineering.md):
  - 预算只约束"历史会话"部分;检索上下文走 format_chunks_only 字符预算,
    LLM 输出走 max_tokens,三者正交;
  - 超阈值时:最近消息保留在预算内(keep_ratio),更早的压成摘要;
    摘要追加到既有摘要后截断,落库(sessions.summary)参与后续轮次;
  - 摘要默认启发式(确定、零成本、可测试);LLM 摘要作为可选增强,
    失败时静默回退启发式(与项目"降级不阻断"DNA 一致)。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

# 默认历史 token 预算(上下文工程基线,见 ADR-0003 §决策)
DEFAULT_HISTORY_TOKEN_BUDGET = 6000
# 预算内保留"最近消息"的比例;其余历史进摘要
KEEP_RATIO = 0.55
# 保守系数:启发式估算 × 1.2,宁可高估
_CONSERVATIVE_FACTOR = 1.2
# 启发式摘要参数
SUMMARY_MAX_TURNS = 6
SUMMARY_PER_LINE_CHARS = 120

# CJK 范围(与 tokenizer.py 同源)
_CJK_RANGES = [
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
]


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    for lo, hi in _CJK_RANGES:
        if lo <= cp <= hi:
            return True
    return False


def estimate_tokens(text: str) -> int:
    """启发式估算文本 token 数(确定、零依赖、保守向上)。

    规则:
      - 空文本 → 0;
      - CJK 字符每个计 1 token;
      - 其余(ASCII/数字/空白)按 4 字符 1 token 计(ceil);
      - 总估算 × 1.2 保守系数。
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if _is_cjk(ch):
            cjk += 1
        else:
            other += 1
    raw = cjk + (other + 3) // 4
    return max(1, int(raw * _CONSERVATIVE_FACTOR))


def estimate_message_tokens(message: Dict[str, object]) -> int:
    """估算单条 message 的 token 数(role + content,含系统 prompt 边距)。"""
    role = str(message.get("role") or "")
    content = str(message.get("content") or "")
    # role 名与格式分隔符(如 [user] / [assistant])的固定开销
    return estimate_tokens(content) + estimate_tokens(role) + 2


def estimate_messages_tokens(messages: Sequence[Dict[str, object]]) -> int:
    return sum(estimate_message_tokens(m) for m in messages)


def resolve_history_token_budget() -> int:
    """预算来源:env HISTORY_TOKEN_BUDGET > 默认 6000。非法值回落默认。"""
    raw = os.environ.get("HISTORY_TOKEN_BUDGET", "").strip()
    if not raw:
        return DEFAULT_HISTORY_TOKEN_BUDGET
    try:
        return max(500, int(raw))
    except ValueError:
        return DEFAULT_HISTORY_TOKEN_BUDGET


def heuristic_summary(
    messages: Sequence[Dict[str, object]],
    *,
    max_turns: int = SUMMARY_MAX_TURNS,
    per_line_chars: int = SUMMARY_PER_LINE_CHARS,
) -> str:
    """确定性摘要:最近 N 轮(一轮 = 一问一答)各取一问一答,行级截断。

    与 LLM 摘要的取舍见 ADR-0003:启发式保证确定性/零成本/可测试,
    LLM 摘要只提升措辞质量,不改变信息覆盖策略。
    """
    lines: List[str] = []
    for m in messages[-(max_turns * 2):] or []:
        role = str(m.get("role") or "")
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        snippet = (
            content[:per_line_chars] + "…"
            if len(content) > per_line_chars
            else content
        )
        if role == "user":
            lines.append(f"用户问: {snippet}")
        elif role == "assistant":
            lines.append(f"助手答: {snippet}")
    return "\n".join(lines)


def _truncate_to_budget(text: str, budget: int) -> str:
    """把摘要文本截到预算内:从最旧的行开始丢弃(摘要按时间有序)。"""
    if estimate_tokens(text) <= budget:
        return text
    lines = text.split("\n")
    kept: List[str] = []
    total = 0
    for line in reversed(lines):
        t = estimate_tokens(line)
        if kept and total + t > budget:
            break
        kept.append(line)
        total += t
    kept.reverse()
    return "\n".join(kept)


def condense_history(
    history: Sequence[Dict[str, object]],
    *,
    budget: Optional[int] = None,
    existing_summary: str = "",
) -> Tuple[List[Dict[str, object]], str]:
    """滚动摘要核心:预算内的历史直接返回,超阈值则压摘要。

    Args:
        history:          会话历史消息(按时间升序)。
        budget:           token 预算;None 时读 env/默认。
        existing_summary: 此前轮次已落库的摘要(追加合并)。

    Returns:
        (kept_history, summary):
          - 预算内:原样返回 + 既有摘要不变;
          - 超阈值:kept 为保留的最近消息(≤ budget×KEEP_RATIO,至少 1 条),
            summary 为既有摘要 + 新压出的摘要合并后截断(≤ 剩余预算)。
    """
    history = list(history or [])
    if budget is None:
        budget = resolve_history_token_budget()
    if not history or estimate_messages_tokens(history) <= budget:
        return history, existing_summary or ""

    keep_budget = int(budget * KEEP_RATIO)
    summary_budget = budget - keep_budget

    # 从最新往旧扫,保留最近消息(至少 1 条,即使单条超预算)
    kept: List[Dict[str, object]] = []
    kept_tokens = 0
    for m in reversed(history):
        t = estimate_message_tokens(m)
        if kept and kept_tokens + t > keep_budget:
            break
        kept.append(m)
        kept_tokens += t
    kept.reverse()

    to_summarize = history[: len(history) - len(kept)]
    new_piece = heuristic_summary(to_summarize)
    if existing_summary:
        combined = f"{existing_summary}\n{new_piece}".strip()
    else:
        combined = new_piece
    return kept, _truncate_to_budget(combined, summary_budget)
