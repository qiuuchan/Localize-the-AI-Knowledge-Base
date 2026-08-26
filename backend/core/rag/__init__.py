"""KB-AI RAG core: parsing, embedding, hybrid retrieval, LLM.

Modules:
  - tokenizer:      Chinese/English/number word splitting + stopwords
  - chunker:        Markdown header-aware sliding-window splitting
  - embedder:       Aliyun Bailian text-embedding-v3 + on-disk cache
  - qdrant_store:   Qdrant collection/upsert/search/delete
  - keyword_index:  SQLite keyword_index CRUD (hybrid search leg)
  - mineru:         Call MinerU HTTP service to parse documents
  - llm:            Aliyun Bailian chat completions + model routing + fallback
  - retriever:      Hybrid vector + keyword search with RRF fusion
  - reranker:       Cross-encoder reranking for the merged candidate set

Replaces scripts/{chat,embed-and-ingest,parse-doc}.ps1.
"""
