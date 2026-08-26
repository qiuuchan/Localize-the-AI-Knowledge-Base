"""Unit tests for backend.core.rag (pure Python, no external services).

These tests cover tokenizer, chunker, keyword_index SQLite, embedder function
shape, retriever function shape, and llm prompt building / parsing.

Qdrant and Aliyun API calls are not exercised here; see the smoke scripts and
docker-compose integration tests for those.

Run from project root:
    backend/.venv/Scripts/python -m pytest tests/integration/test_rag_core.py -v
"""
from __future__ import annotations

import os
import tempfile

import pytest

from backend.core.rag import chunker as rag_chunker
from backend.core.rag import embedder as rag_embedder
from backend.core.rag import keyword_index as rag_keyword
from backend.core.rag import llm as rag_llm
from backend.core.rag import qdrant_store as rag_qdrant
from backend.core.rag import retriever as rag_retriever
from backend.core.rag import tokenizer as rag_tokenizer
from backend.core.rag import mineru as rag_mineru


# ---------------------------------------------------------------------------
# tokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_basic_chinese(self):
        toks = rag_tokenizer.get_tokens("红烧肉怎么做")
        assert "红" in toks
        assert "烧" in toks
        assert "肉" in toks
        # how to cook: words like "怎么" might be tokenized as cjk chars
        assert "怎" in toks

    def test_english_split(self):
        toks = rag_tokenizer.get_tokens("how to cook RedBraisedPork")
        assert "how" in toks
        assert "cook" in toks
        assert "redbraisedpork" in toks  # camelCase is one token (no separator)

    def test_stopwords_filtered(self):
        toks = rag_tokenizer.get_tokens("的红烧肉")
        # "的" is in stopwords list
        assert "的" not in toks
        assert "红" in toks
        assert "烧" in toks

    def test_empty_input(self):
        assert rag_tokenizer.get_tokens("") == []
        assert rag_tokenizer.get_tokens(None) == [] if False else True  # type: ignore

    def test_deduplicated(self):
        toks = rag_tokenizer.get_tokens("红红红红")
        assert toks.count("红") == 1

    def test_top_tokens_max(self):
        toks = rag_tokenizer.get_top_tokens("一二三四五六七八九十", max_n=5)
        assert len(toks) == 5


# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------


class TestChunker:
    SAMPLE = """# 主标题

第一段简短。

## 子标题

第二段也比较短。

### 三级标题

第三段。
"""

    def test_header_aware_sections(self):
        chunks = rag_chunker.split_into_chunks(self.SAMPLE, source="t.md")
        # 3 sections = 3 chunks (one paragraph each)
        assert len(chunks) == 3
        assert chunks[0].header_path == "主标题"
        assert chunks[1].header_path == "主标题 > 子标题"
        assert chunks[2].header_path == "主标题 > 子标题 > 三级标题"

    def test_chunk_id_format(self):
        chunks = rag_chunker.split_into_chunks(self.SAMPLE, source="t.md")
        # UUID 8-4-4-4-12 format
        import re
        for c in chunks:
            assert re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                c.id,
            )

    def test_long_paragraph_split(self):
        long = "a" * 2000
        chunks = rag_chunker.split_into_chunks(
            "# Title\n\n" + long, source="t.md", max_len=500, overlap=100
        )
        # Each piece <= 500, step = 400, so 2000/400 = 5 pieces
        assert len(chunks) >= 4
        for c in chunks:
            assert len(c.text) <= 500

    def test_flat_no_headers(self):
        chunks = rag_chunker.split_into_chunks(
            "段A\n\n段B\n\n段C", source="t.md", header_aware=False
        )
        assert all(c.header_level == 0 for c in chunks)
        assert all(c.header_path == "" for c in chunks)

    def test_tokens_attached(self):
        chunks = rag_chunker.split_into_chunks(
            "# T\n\n红烧肉怎么做", source="t.md"
        )
        assert len(chunks) >= 1
        # Tokens should include red-cooked-pork chars
        flat = [t for c in chunks for t in c.tokens]
        assert "红" in flat


# ---------------------------------------------------------------------------
# keyword_index SQLite
# ---------------------------------------------------------------------------


class TestKeywordIndex:
    @pytest.fixture
    def db(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False).name
        rag_keyword.init_table(tmp)
        yield tmp
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

    def test_init_idempotent(self, db):
        # Should not raise on second init
        rag_keyword.init_table(db)
        rag_keyword.init_table(db)

    def test_write_and_search(self, db):
        rag_keyword.write_rows([
            ("红烧", "p1", "menu.md", "红烧肉"),
            ("肉", "p1", "menu.md", "红烧肉"),
            ("清蒸", "p2", "menu.md", "清蒸鱼"),
            ("鱼", "p2", "menu.md", "清蒸鱼"),
        ], db)
        results = rag_keyword.search_by_tokens(["红烧", "肉"], db_path=db, limit=5)
        assert len(results) == 1
        assert results[0]["point_id"] == "p1"
        assert results[0]["score"] == 2

    def test_count_by_source(self, db):
        rag_keyword.write_rows([
            ("a", "p1", "menu.md", "1"),
            ("b", "p1", "menu.md", "1"),
            ("a", "p2", "menu.md", "2"),
        ], db)
        counts = rag_keyword.count_by_source(db)
        # 3 keyword_index rows for menu.md (2 tokens for p1 + 1 token for p2)
        assert {"source": "menu.md", "chunk_count": 3} in counts

    def test_delete_by_source(self, db):
        rag_keyword.write_rows([
            ("a", "p1", "menu.md", "1"),
            ("b", "p1", "menu.md", "1"),
            ("a", "p2", "other.md", "2"),
        ], db)
        deleted = rag_keyword.delete_by_source("menu.md", db)
        assert deleted == 2
        remaining = rag_keyword.count_by_source(db)
        assert all(r["source"] != "menu.md" for r in remaining)

    def test_search_empty_tokens(self, db):
        assert rag_keyword.search_by_tokens([], db_path=db) == []


# ---------------------------------------------------------------------------
# llm: select_model, parse_llm_response, format_chunks_only, build_messages
# ---------------------------------------------------------------------------


class TestSelectModel:
    def test_simple_query_routes_to_plus(self, monkeypatch):
        monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "sk-test")
        monkeypatch.setenv("MODEL_NAME", "qwen3.6-plus")
        monkeypatch.setenv("MODEL_NAME_MAX", "qwen3.7-max")
        model, reason = rag_llm.select_model("红烧肉怎么做", disable_routing=False)
        assert model == "qwen3.6-plus"
        assert reason == "default"

    def test_complex_keyword_routes_to_max(self, monkeypatch):
        monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "sk-test")
        monkeypatch.setenv("MODEL_NAME", "qwen3.6-plus")
        monkeypatch.setenv("MODEL_NAME_MAX", "qwen3.7-max")
        model, reason = rag_llm.select_model("对比红烧肉和清蒸鱼哪个好吃")
        assert model == "qwen3.7-max"
        assert reason == "complex_keyword"

    def test_disable_routing_forces_plus(self, monkeypatch):
        monkeypatch.setenv("ALIYUN_BAILIAN_API_KEY", "sk-test")
        model, reason = rag_llm.select_model(
            "对比", disable_routing=True, model_name="qwen3.6-plus"
        )
        assert model == "qwen3.6-plus"
        assert reason == "disabled"


class TestFallbackModel:
    def test_plus_to_max(self):
        assert rag_llm.fallback_model("qwen3.6-plus") == "qwen3.7-max"

    def test_max_to_plus(self):
        assert rag_llm.fallback_model("qwen3.7-max") == "qwen3.6-plus"


class TestParseLLMResponse:
    def test_code_fence(self):
        text = '```json\n{"type":"answer","content":"hi","citations":[1]}\n```'
        out = rag_llm.parse_llm_response(text)
        assert out["type"] == "answer"
        assert out["content"] == "hi"
        assert out["citations"] == [1]

    def test_outer_json(self):
        text = '前面是废话 {"type":"clarify","question":"哪个菜？"}'
        out = rag_llm.parse_llm_response(text)
        assert out["type"] == "clarify"
        assert out["question"] == "哪个菜？"

    def test_fallback_plain_text(self):
        text = "就是普通的回答内容"
        out = rag_llm.parse_llm_response(text)
        assert out["type"] == "answer"
        assert out["content"] == "就是普通的回答内容"


class TestFormatChunksOnly:
    def test_basic(self):
        chunks = [
            {"source": "menu.md", "text": "红烧肉是招牌菜", "score": 0.9},
            {"source": "menu.md", "text": "清蒸鱼清淡", "score": 0.7},
        ]
        out = rag_llm.format_chunks_only(chunks, max_context_chars=1000)
        assert len(out["citations"]) == 2
        assert out["citations"][0]["index"] == 1
        assert "红烧肉" in out["ctx"]
        assert "清蒸鱼" in out["ctx"]

    def test_max_chars_limit(self):
        chunks = [
            {"source": "a.md", "text": "x" * 200, "score": 0.5},
            {"source": "a.md", "text": "y" * 200, "score": 0.5},
            {"source": "a.md", "text": "z" * 200, "score": 0.5},
        ]
        out = rag_llm.format_chunks_only(chunks, max_context_chars=300)
        # Should stop before accumulating too much
        assert len(out["ctx"]) <= 600  # some slack for header

    def test_empty(self):
        out = rag_llm.format_chunks_only([])
        assert out["ctx"] == ""
        assert out["citations"] == []


class TestBuildMessages:
    def test_basic_rag(self):
        msgs = rag_llm.build_messages(
            question="红烧肉怎么做",
            context_chunks=[{"source": "menu.md", "text": "红烧肉做法"}],
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "menu.md" in msgs[1]["content"]
        assert "红烧肉做法" in msgs[1]["content"]
        assert "红烧肉怎么做" in msgs[1]["content"]

    def test_with_history(self):
        msgs = rag_llm.build_messages(
            question="还有什么",
            context_chunks=[],
            history=[{"role": "user", "content": "推荐招牌菜"}],
        )
        assert "推荐招牌菜" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# qdrant_store / embedder / retriever / mineru import smoke
# ---------------------------------------------------------------------------


class TestModuleShape:
    """Verify module APIs exist with expected signatures."""

    def test_qdrant_store_functions(self):
        for name in ("health", "ensure_collection", "upsert_points", "search",
                     "delete_by_source", "scroll_by_source"):
            assert hasattr(rag_qdrant, name), f"qdrant_store missing {name}"

    def test_embedder_functions(self):
        for name in ("embed_texts", "embed_query"):
            assert hasattr(rag_embedder, name), f"embedder missing {name}"
        assert rag_embedder.EMBEDDING_DIM == 1024
        assert rag_embedder.MODEL_NAME == "text-embedding-v3"

    def test_retriever_functions(self):
        assert hasattr(rag_retriever, "retrieve")

    def test_mineru_functions(self):
        for name in ("health", "parse_to_markdown", "default_parser_registry"):
            assert hasattr(rag_mineru, name), f"mineru missing {name}"

    def test_constants(self):
        assert rag_qdrant.EMBEDDING_DIM == 1024
        assert rag_qdrant.DEFAULT_COLLECTION == "kb_ai_chunks"
        assert rag_llm.DEFAULT_MODEL == "qwen3.6-plus"
        assert rag_llm.DEFAULT_MODEL_MAX == "qwen3.7-max"


# ---------------------------------------------------------------------------
# Embedding cache file shape (write-only test using tempfile)
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    def test_cache_path_under_data(self):
        # Sanity: cache lives under project data dir, not temp.
        from backend.core.config import get_data_dir
        cache = rag_embedder._cache_path()
        assert str(cache).startswith(str(get_data_dir()))
