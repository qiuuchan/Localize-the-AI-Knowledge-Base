# dify/ 目录说明(v1.3.0)

## 文件作用

- `knowledge-pipeline.json`:**v0.7 时代 Dify Web UI 工作流的导入快照**。

## 当前状态

自 v0.8.0 起,项目已切换到 FastAPI 后端 + React 前端架构,`dify-api` / `dify-worker` 容器仍保留(为内部 LLM 工作流提供 SQLite 模式支持),但**`dify/knowledge-pipeline.json` 不再随架构演进**。该文件不再被运行时使用,仅作历史参考。

## 保留原因

- 历史考古价值:v0.7 时期的 Dify Web UI 工作流配置是项目架构演进的里程碑证据
- 零成本:文件仅几 KB,占用空间可忽略
- 删除不可恢复:verifier / 后人可能需要回溯"原始 Dify pipeline 怎么配的"

## 不要做的事

- ❌ 不要基于该文件改 Dify Web UI 配置(已无意义,v0.8.0 起改走 FastAPI + RAG Python 模块)
- ❌ 不要删除该文件(无授权)
- ❌ 不要把它当文档来阅读(它是 JSON 配置,不是 markdown)

## 关联

- `scripts/dify/knowledge-pipeline.json`(如果存在)是另一份拷贝;以本目录为准
- 真正的运行时配置在 `backend/core/rag/` 11 个 Python 模块中