"""Aliyun Bailian text-embedding-v3 client with on-disk cache.

Mirrors scripts/embed-and-ingest.ps1:
  - POST https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding
  - Header: Authorization Bearer <KEY>
  - Body: {"model":"text-embedding-v3","input":{"texts":[...]},"parameters":{"dimension":1024}}
  - Response: output.embeddings[*].embedding (1024 floats)

Cache: ./data/embedding-cache.jsonl
  Each line: {"text": str, "vector": [float;1024], "ts": iso, "model": "text-embedding-v3"}

v0.8.4 加 LRU 淘汰: 缓存文件 > EMBEDDING_CACHE_MAX_BYTES(默认 200MB) 时,
  在 _load_cache() 末尾触发 _compact_cache() 删除最老 25% 条目,
  按时间戳 ts 升序淘汰。避免无限增长拖慢启动 + 挤占 U 盘空间。

Limitations:
  - Batch size <= 10 (DashScope limit).
  - UTF-8 JSON encoding is mandatory for Chinese.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple  # noqa: F401

from backend.core.atomic_io import atomic_append_jsonl
from backend.core.config import get_data_dir, get_env_or_env_var

MODEL_NAME = "text-embedding-v3"
EMBEDDING_DIM = 1024
EMBEDDING_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/embeddings/"
    "text-embedding/text-embedding"
)
EMBED_BATCH_MAX = 10

# v0.8.4 LRU 阈值(可通过 env override)
_DEFAULT_CACHE_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
_DEFAULT_COMPACT_RATIO = 0.25  # 删最老的 25%
_DEFAULT_COMPACT_TARGET_RATIO = 0.75  # 删到 75% 阈值即停(避免每次都全量写)


def _cache_path() -> Path:
    return get_data_dir() / "embedding-cache.jsonl"


def _load_cache() -> Dict[str, List[float]]:
    path = _cache_path()
    if not path.exists():
        return {}
    out: Dict[str, List[float]] = {}
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = obj.get("text")
                vector = obj.get("vector")
                if text and vector:
                    out[text] = vector
    except Exception:
        # Cache is best-effort; corrupt cache shouldn't block work.
        return {}

    # v0.8.4 LRU 淘汰:超过阈值时后台 compact
    try:
        max_bytes = int(
            get_env_or_env_var("EMBEDDING_CACHE_MAX_BYTES") or _DEFAULT_CACHE_MAX_BYTES
        )
        if max_bytes > 0 and path.exists():
            size = path.stat().st_size
            if size > max_bytes:
                _compact_cache(path, max_bytes)
    except Exception:
        # 淘汰失败不影响本次返回
        pass
    return out


def _compact_cache(path: Path, max_bytes: int) -> None:
    """Drop oldest entries until file size <= max_bytes * target_ratio.

    Strategy:
      1. Read all lines, parse JSON, sort by ts ascending.
      2. Drop oldest `_DEFAULT_COMPACT_RATIO` fraction.
      3. Rewrite file atomically (tmp + replace).
    """
    target_bytes = int(max_bytes * _DEFAULT_COMPACT_TARGET_RATIO)
    try:
        entries: List[Tuple[str, Dict[str, object]]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    entries.append((line, obj))
                except json.JSONDecodeError:
                    continue

        if not entries:
            return

        # 按 ts 升序,None 排到最前(老条目)
        def _ts_key(item: Tuple[str, Dict[str, object]]) -> str:
            ts = item[1].get("ts") or ""
            return str(ts)

        entries.sort(key=_ts_key)

        # 删最老 25%
        drop_count = max(1, int(len(entries) * _DEFAULT_COMPACT_RATIO))
        kept = entries[drop_count:]

        # 写入 tmp 后原子替换(避免写一半崩溃损坏缓存)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for raw, _obj in kept:
                f.write(raw + "\n")
        tmp_path.replace(path)

        # 如果还超阈值,继续删(罕见;极端一次性大写入)
        if path.exists() and path.stat().st_size > target_bytes:
            entries2 = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries2.append((line, json.loads(line)))
                    except json.JSONDecodeError:
                        continue
            entries2.sort(key=_ts_key)
            # 再删 25%
            drop_count2 = max(1, int(len(entries2) * _DEFAULT_COMPACT_RATIO))
            kept2 = entries2[drop_count2:]
            tmp_path2 = path.with_suffix(path.suffix + ".tmp")
            with tmp_path2.open("w", encoding="utf-8") as f:
                for raw, _obj in kept2:
                    f.write(raw + "\n")
            tmp_path2.replace(path)
    except Exception:
        # compact 失败不阻断主流程;下次 _load_cache() 会重试
        pass


def _append_cache(text: str, vector: List[float]) -> None:
    """Append one embedding entry to cache file.

    v0.8.11(P1.3):改用 atomic_append_jsonl,断电不会留半截行;
    缓存 > 50MB 时退回 best-effort append(下次 compact 整体重写)。
    """
    path = _cache_path()
    obj = {
        "text": text,
        "vector": vector,
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_NAME,
    }
    atomic_append_jsonl(path, obj)


def _post_embeddings(api_key: str, texts: List[str]) -> List[List[float]]:
    """Call DashScope embeddings API. Raises on failure."""
    body = {
        "model": MODEL_NAME,
        "input": {"texts": texts},
        "parameters": {"dimension": EMBEDDING_DIM},
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        EMBEDDING_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Embedding API HTTP {e.code}: {body_text[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Embedding API unreachable: {e}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Embedding API returned non-JSON: {raw[:200]}")

    embeddings = parsed.get("output", {}).get("embeddings") or []
    vectors: List[List[float]] = []
    for item in embeddings:
        v = item.get("embedding")
        if v is None:
            raise RuntimeError(f"Embedding missing vector: {item}")
        vectors.append(list(v))
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: requested {len(texts)}, got {len(vectors)}"
        )
    return vectors


def embed_texts(
    texts: List[str],
    *,
    api_key: Optional[str] = None,
    use_cache: bool = True,
) -> Tuple[List[List[float]], Dict[str, int]]:
    """Embed a list of texts. Returns (vectors, stats).

    stats contains: {"hit": N, "miss": N, "batch": N}.
    """
    if not texts:
        return [], {"hit": 0, "miss": 0, "batch": 0}

    api_key = api_key or get_env_or_env_var("ALIYUN_BAILIAN_API_KEY")
    if not api_key:
        raise RuntimeError("ALIYUN_BAILIAN_API_KEY not configured")

    cache = _load_cache() if use_cache else {}
    results: List[Optional[List[float]]] = [None] * len(texts)
    miss_indices: List[int] = []

    for idx, t in enumerate(texts):
        if not t:
            results[idx] = [0.0] * EMBEDDING_DIM
            continue
        if use_cache and t in cache:
            results[idx] = cache[t]
            continue
        miss_indices.append(idx)

    # Batch the misses into <= EMBED_BATCH_MAX groups
    batch_count = 0
    for start in range(0, len(miss_indices), EMBED_BATCH_MAX):
        batch_idx = miss_indices[start : start + EMBED_BATCH_MAX]
        batch_texts = [texts[i] for i in batch_idx]
        vectors = _post_embeddings(api_key, batch_texts)
        for i, v in zip(batch_idx, vectors):
            results[i] = v
            if use_cache:
                _append_cache(texts[i], v)
        batch_count += 1

    # Final type assertion: every result must be filled
    out: List[List[float]] = []
    for i, r in enumerate(results):
        if r is None:
            raise RuntimeError(f"Missing embedding for index {i}: {texts[i][:80]}")
        out.append(r)

    stats = {
        "hit": len(texts) - len(miss_indices),
        "miss": len(miss_indices),
        "batch": batch_count,
    }
    return out, stats


def embed_query(text: str, *, api_key: Optional[str] = None) -> List[float]:
    """Embed a single query string. Convenience wrapper."""
    vectors, _ = embed_texts([text], api_key=api_key)
    return vectors[0]
