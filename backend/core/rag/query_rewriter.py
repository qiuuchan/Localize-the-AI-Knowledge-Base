"""Query rewriting + personal entity linking for KB-AI retrieval.

Goal: turn vague / colloquial / abbreviated queries into concrete,
retrieval-friendly queries before embedding and reranking.

Pipeline:
  1. Load a static entity library (data/entities.json) of alias -> canonical.
  2. Replace aliases in the query with canonical names.
  3. Optionally call a light LLM (qwen3.6-plus) to expand pronouns / fuzzy
     time references using the entity library.

If the LLM call fails or is disabled, the function returns the entity-linked
query as a safe fallback so retrieval never breaks.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

from backend.core.config import get_data_dir, get_env_or_env_var

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3.6-plus"
CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def _entities_path() -> Path:
    env_path = get_env_or_env_var("ENTITIES_JSON_PATH")
    if env_path:
        return Path(env_path)
    return get_data_dir() / "entities.json"


def load_entities(path: Optional[Path] = None) -> Dict[str, str]:
    """Load alias -> canonical mapping from JSON.

    Expected JSON shape (flat or nested):
      {"老王": "王工", "K2.7": "项目 K2.7"}
    or
      {"aliases": {"老王": "王工"}, "people": {"王工": "王工-架构师"}}

    Nested dicts are flattened into alias -> canonical pairs.
    Missing or malformed files return an empty dict.
    """
    path = path or _entities_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        logger.warning("Cannot load entities from %s: %s", path, exc)
        return {}

    if isinstance(raw, dict):
        flat: Dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                for alias, canonical in value.items():
                    if isinstance(alias, str) and isinstance(canonical, str):
                        flat[alias] = canonical
            elif isinstance(key, str) and isinstance(value, str):
                flat[key] = value
        return flat
    return {}


def _link_entities(query: str, entities: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
    """Replace longest-matching aliases with canonical names.

    Returns (rewritten_query, {alias: canonical} used).
    """
    if not entities:
        return query, {}

    used: Dict[str, str] = {}
    rewritten = query
    # Sort aliases by length descending so longer matches win.
    for alias in sorted(entities.keys(), key=len, reverse=True):
        canonical = entities[alias]
        # Use word-boundary-like matching for Latin tokens; Chinese aliases
        # are matched as-is. Avoid replacing part of a longer word.
        pattern = re.escape(alias)
        # Only enforce word boundaries for pure ASCII words; Chinese aliases
        # are matched as-is to avoid Python's \b treating CJK as word chars.
        if re.match(r"^[a-zA-Z0-9_]+$", alias):
            pattern = r"\b" + pattern + r"\b"
        new, count = re.subn(pattern, canonical, rewritten)
        if count > 0:
            used[alias] = canonical
            rewritten = new
    return rewritten, used


def _call_rewrite_llm(
    query: str,
    entities: Dict[str, str],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Ask a light LLM to rewrite the query using the entity library."""
    api_key = api_key or get_env_or_env_var("ALIYUN_BAILIAN_API_KEY")
    if not api_key:
        raise RuntimeError("ALIYUN_BAILIAN_API_KEY not configured")

    model = model or DEFAULT_MODEL
    entity_lines = "\n".join(f"{k}: {v}" for k, v in sorted(entities.items()))
    if not entity_lines:
        entity_lines = "（暂无实体）"

    prompt = (
        "你是一名知识库查询改写助手。用户的问题可能包含口语化表达、缩写或人名绰号。\n"
        "请把以下问题改写成一个更具体、更适合向量检索的标准查询。\n"
        "如果问题里出现绰号/缩写，请用下面实体库中的标准名称替换。\n"
        "只输出改写后的查询，不要解释，不要加引号。\n\n"
        f"实体库：\n{entity_lines}\n\n"
        f"原问题：{query}\n"
        "改写后："
    )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是 KB-AI 查询改写助手，只输出改写后的查询。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 200,
        "temperature": 0.1,
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Rewrite API HTTP {e.code}: {body_text[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Rewrite API unreachable: {e}")

    parsed = json.loads(raw)
    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError("Rewrite API returned no choices")
    content = choices[0].get("message", {}).get("content", "")
    return content.strip().strip('"').strip("'")


def rewrite_query(
    query: str,
    *,
    entities: Optional[Dict[str, str]] = None,
    use_llm: Optional[bool] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """Rewrite a query for retrieval.

    Returns:
        (rewritten_query, {alias: canonical} entities used).

    Steps:
        1. Entity linking (always runs if entities provided or entities.json exists).
        2. LLM expansion (only if use_llm=True or QUERY_REWRITE_ENABLED=true).
           On LLM failure, falls back to the entity-linked query.
    """
    if not query or not query.strip():
        return query, {}

    if entities is None:
        entities = load_entities()

    linked, used = _link_entities(query, entities)

    if use_llm is None:
        env_val = (get_env_or_env_var("QUERY_REWRITE_ENABLED") or "").strip().lower()
        use_llm = env_val in ("1", "true", "yes", "on")

    if not use_llm:
        return linked, used

    try:
        rewritten = _call_rewrite_llm(linked, entities, api_key=api_key, model=model)
        if rewritten:
            return rewritten, used
    except Exception as exc:
        logger.warning("Query rewrite LLM failed, using entity-linked query: %s", exc)

    return linked, used
