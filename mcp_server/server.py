"""KB-AI MCP Server — 把知识库检索暴露为标准 MCP 工具。

任意 MCP client(Claude Desktop / Cursor / 自研 Agent)通过 stdio transport
连接本 server,即可调用 `kb_search` 检索 KB-AI 知识库。

设计(对齐项目「低依赖」哲学):
  - 本 server 是**薄 HTTP 代理**,零 backend 代码依赖 —— 内部调用
    KB-AI 后端的 `/api/debug/retrieval`(复用检索/降级/计量全链路),
    自身仅依赖 `mcp` SDK + 标准库;
  - 后端地址可用环境变量 `KB_AI_BASE_URL` 覆盖(默认 http://127.0.0.1:8000);
  - stdio transport(MCP 标准),无端口占用,client 侧零配置。

用法:
  1. 启动 KB-AI 后端(start.bat 或 uvicorn backend.main:app)
  2. 本目录建 venv 并装依赖: pip install -r requirements.txt
  3. 在 MCP client 里注册: "mcpServers": {"kb-ai": {"command": "<python>", "args": ["mcp_server/server.py"]}}

  或命令行验证: mcp dev mcp_server/server.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# mcp 2.x:FastMCP 已更名为 MCPServer(mcp.server.mcpserver)
from mcp.server.mcpserver import MCPServer

server = MCPServer("kb-ai")

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
RETRIEVAL_TIMEOUT = 60  # 检索含 embedding + rerank,首调较慢


def _base_url() -> str:
    return os.environ.get("KB_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


@server.tool()
def kb_search(query: str, top_k: int = 5) -> str:
    """检索本地知识库,返回带编号的资料片段(来源/摘要)。

    适合回答涉及企业内部文档、制度、经营数据、历史记录的问题;
    知识库未命中时返回说明,不会抛错。
    """
    top_k = max(1, min(int(top_k), 20))
    url = (
        f"{_base_url()}/api/debug/retrieval?"
        f"{urllib.parse.urlencode({'question': query, 'top_k': top_k})}"
    )
    try:
        with urllib.request.urlopen(url, timeout=RETRIEVAL_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:200]
        return f"[error] 后端返回 HTTP {exc.code}: {detail}"
    except urllib.error.URLError as exc:
        return (
            f"[error] 无法连接后端 {_base_url()}({exc.reason});"
            "请先启动 KB-AI(start.bat)后重试"
        )

    hits = data.get("reranked_hits") or data.get("rrf_hits") or []
    if not hits:
        return "知识库未命中相关资料,可换关键词重试"
    lines = []
    for i, hit in enumerate(hits, 1):
        source = hit.get("source") or "(未知来源)"
        text = (hit.get("text") or "").replace("\n", " ").strip()
        snippet = text[:200] + ("..." if len(text) > 200 else "")
        lines.append(f"[{i}] {source}\n{snippet}")
    return "\n\n".join(lines)


if __name__ == "__main__":
    server.run()
