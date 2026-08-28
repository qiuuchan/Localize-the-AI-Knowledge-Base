# AGENTS.md · KB-AI

> **本文件用途**:跨对话上下文恢复。当 AI 工具(LLM agent)进入 KB-AI 子项目时,**先读本文件**,再读所列引用文档。
> **适用对象**:Claude / Kimi / GPT 等任何进入本仓库工作区的 AI agent。
> **维护者**:`maintainer` 项目所有人;任何重大变动需同步用户。

---

## 0. 项目一句话定义

KB-AI 是一个**本地化、低依赖、个人用**的 AI 知识库,**目标用户**:餐饮分公司总经理(非技术)。**技术栈**:Dify 1.0 + Qdrant 1.7 + MinerU + 阿里云百炼 Qwen3.6-Plus/Max + text-embedding-v3。**编排**:5 个 Docker 容器 + FastAPI 0.111 后端(v0.8.0+)+ React 18 + Vite 前端(v0.8.2+)。**主机端** PowerShell 5.1 脚本驱动,数据全在 USB 移动 SSD(Windows 10/11)。

**架构跃迁(2026-07-13~16)**:PS 单体 `chat.ps1` → FastAPI + RAG Python 模块 + React 前端双层架构。

**求职主线(2026-08 起,最高优先级)**:本项目同时是**求职 Agent 应用开发岗(中大厂)的主力展示项目**。求职弹药全部在 `docs/career/`(简历 bullet 定稿 / STAR 故事 ×6 / 面试 FAQ ×10 / JD 对照表),公开门面 = GitHub 公开仓(经 `tmp/sanitize/sanitize_public.py` 脱敏管线生成,评测报告已公开)。改代码时注意:公开仓会同步你改的一切 —— 系统提示词/文档措辞保持「示例海鲜酒楼」虚构叙事,勿写入求职措辞与真实客户信息。

---

## 1. 文件地图(必读清单)

```
KB-AI/
├── docker-compose.yml        # 5 容器编排(3 长跑 + 1 WAL init)
├── .env / .env.example       # 真实配置 / 占位符模板(只读 .env)
├── start.bat / stop.bat      # 用户双击入口;stop.bat v0.8.6 改为 4 步(停后端+容器+落盘+备份)
├── package.bat               # 打包;不修改
├── README.md / CHANGELOG.md  # 项目门面 + 版本记录(v0.8.6+)
├── version                   # 版本号单一真相源
├── .python-version           # 3.12.6
├── backend/                  # v0.8.4+ FastAPI 后端(完整 RAG 管线 + v0.8.11 Database/Dashboard + v1.1.0 PR#4 标签 + v1.3.0 sqlite 包拆分)
│   ├── main.py               # FastAPI 入口(CORS 缩窄到 localhost:8000/8080)
│   ├── api/                  # 12 路由:v0.8.11 加 databases/dashboard;v0.8.12 加 eval;v1.1.0 PR#4 加 tags;v2.0 PR#3 加 agent
│   │   ├── knowledge.py      # /knowledge CRUD + /upload(SSE) + /reembed(v0.8.11 加 database_id 参数)
│   │   ├── databases.py      # v0.8.11(P1.1) /knowledge/databases CRUD + assign
│   │   ├── chat.py           # SSE chat + hybrid retrieval + LLM fallback(降级事件带 component)
│   │   ├── agent.py          # v2.0 PR#3 三端点:POST /agent/chat(SSE 六事件 + cost-alert 阻断)+ GET /agent/runs + GET /agent/runs/{id}
│   │   ├── boot.py           # 8+2 阶段启动进度 SSE(v0.8.11 加 orphan_recovery;v1.1.0 PR#4 加 schema_migration 8%)
│   │   ├── dashboard.py      # v0.8.11(P1.6) /dashboard/overview 聚合(v1.3.0 PR#2 加 cost_alert 字段)
│   │   ├── eval.py           # v0.8.12(P2.1) /eval/run + /eval/results + /eval/status
│   │   ├── sessions.py       # 会话 CRUD + PATCH history_limit(PR#2)+ LLM streaming title(PR#4)
│   │   ├── shutdown.py       # 安全弹出
│   │   ├── debug.py          # /debug/retrieval 检索全链路
│   │   ├── tags.py           # v1.1.0 PR#4 7 端点:/tags CRUD + /doc-tags 多对多 + 按 tag 过滤文档
│   │   └── health.py         # health + status
│   ├── core/                 # 配置 + 持久化 + RAG 11 模块 + Agent(v2.0)
│   │   ├── config.py         # 项目根/.env/占位符识别
│   │   ├── ps_runner.py      # PowerShell 子进程桥接
│   │   ├── atomic_io.py      # v0.8.11(P1.3) 原子写工具(借鉴 Yuxi-Know)
│   │   ├── bulk_assign.py    # v1.1.0 PR#1 批量迁移 + Qdrant payload 重写(治 #11)
│   │   ├── agent/            # v2.0 工具调用 Agent:tools.py(4 工具注册表 + execute_tool 分发 + kb_offset 全局 citation 编号)+ loop.py(run_agent 生成器:max_steps/repeat_guard/budget 收尾)+ trajectory.py(轨迹门面,吞错不阻断)
│   │   ├── sqlite/           # v1.3.0 PR#1:6-repo 包拆分 + transaction()(connection + sessions_repo / messages_repo / degradation_repo / databases_repo / tags_repo + v2.0 agent_repo + orchestrator __init__)
│   │   └── rag/              # chunker/embedder/qdrant_store/keyword_index/mineru/llm/metadata/query_profile/retriever/reranker/query_rewriter/tokenizer
│   ├── requirements.txt      # fastapi/uvicorn/sse-starlette/sentence-transformers
│   └── requirements-dev.txt  # httpx/pytest
├── frontend/                 # v0.8.2+ React 18 + TypeScript + Vite(v0.8.11 加 DashboardPage;v1.3.0 PR#3 加成本告警卡片)
│   ├── index.html / package.json / vite.config.ts / tsconfig.json
│   ├── src/
│   │   ├── main.tsx / App.tsx          # 主组件(状态 + SSE + 路由,v0.8.11 加 /dashboard)
│   │   ├── components/                 # TopNav(v0.8.11 加系统入口)/StatusBar/Drawer/MessageBubble/Modals
│   │   ├── pages/                      # KnowledgePage(v0.8.11 sidebar+modal)/SettingsPage/DashboardPage
│   │   ├── lib/                        # api.ts(v0.8.11 加 patchJSON) + types.ts(加 Database/DashboardOverview;v1.3.0 PR#3 加 CostAlert)
│   │   ├── __tests__/                  # vitest RTL(MessageBubble + TagChip;v1.3.0 PR#3 加 DashboardPage)
│   │   └── styles/                     # global.css(v0.8.11 加 sidebar/modal/dashboard 段,~30KB)
│   └── dist/                           # 构建产物
├── scripts/                  # PowerShell 5.1 工具链(含 v1.3.0 hooks + cost-alert + v1.7.0 跨平台)
│   ├── chat.ps1              # RAG 主循环(~47KB,保留作 fallback)
│   ├── embed-and-ingest.ps1  # 文档 → Qdrant + keyword_index
│   ├── parse-doc.ps1         # 调用 MinerU 解析
│   ├── batch-parse-and-ingest.ps1  # 批量入库 + manifest
│   ├── reparse-rag.ps1       # v1.2.0 PR#2 批量重解析 JSON manifest
│   ├── health-probe.ps1      # 3 端点 → health_status.json
│   ├── health-full.ps1       # 1 屏健康度
│   ├── disk-alert.ps1        # 容量 5 级告警 + SQLite 监控
│   ├── cost-alert.ps1        # v1.3.0 PR#2 月度配额告警(滚算 data/cost_log.jsonl → health_status.json)
│   ├── backup.ps1            # data\+vectors\ zip 备份,保留 7 份 + SHA-1 manifest
│   ├── backup-code.ps1       # git 裸仓库推送到电脑硬盘
│   ├── start-backend.ps1 / stop-backend.ps1
│   ├── safe-eject.ps1        # v0.8.6 5 秒倒计时确认 + 调 stop.bat + WinForms MessageBox(v1.7.0 改 Show-KBAINotice 跨平台)
│   ├── run-checks.ps1        # ruff → pytest → eslint → vite build
│   ├── install-hooks.ps1     # v1.3.0 PR#1 git hooks 安装器(支持 -DryRun / -Uninstall)
│   ├── hooks/                # v1.3.0 PR#1 pre-commit(pre-push)bash 钩子(被 core.hooksPath 引用;v1.7.0 加 Mac .venv/bin/ruff 分支)
│   └── lib/                  # load-env / Invoke-SqliteExec / Write-Utf8NoBom / Tokenizer / CertaintyTagger / Write-Log / CostLog-Rotate / **platform-utils(v1.7.0 跨平台 11 函数)**
├── start.ps1 / stop.ps1 / precheck.ps1 / package.ps1  # v1.7.0 PowerShell 单源编排(Mac/Win 共用,薄壳 .command/.sh 在根目录)
├── start.command / stop.command  # v1.7.0 macOS 双击入口(exec pwsh -File)
├── package.sh                 # v1.7.0 macOS 打包薄壳(调 package.ps1)
├── start.bat / stop.bat / precheck.bat / package.bat  # Windows 客户机入口(v1.7.0 保留,内部一行未动)
├── tests/                    # 13 个 mock 脚本 + unit/(pytest) + integration/
│   ├── test_m1..m3c.ps1     # 各阶段回归
│   ├── test_rag1..3.ps1     # RAG 三阶段回归
│   ├── test_chunking.ps1 / test_certainty.ps1 / test_model_routing.ps1
│   ├── e2e_test.ps1
│   ├── unit/                 # pytest:reranker/query_rewriter/retriever_fallback/debug_api/temporal_weighting/rag_core/streaming_extract + v0.8.11 database_crud/atomic_io/degradation_component/dashboard_aggregations + v0.8.12 eval_route/parsed_cache_namespacing + v1.1.0 PR#1 database_cascade/bulk_assign_qdrant + PR#2 limit_guard + PR#3 skip_clarification/image_endpoint + PR#4 tags_api/session_title + v1.2.0 query_profile/xlsx_structuring/reparse_task/retrieval_quality/qdrant_public_api + v1.3.0 PR#1 sqlite_refactor + PR#2 cost_alert/chat_cost_alert_block/dashboard_cost_alert + v2.0 PR#1-3 agent_tools/agent_loop/agent_repo/agent_api
│   ├── eval/                 # RAG 评测(golden-qa.jsonl 50 条 + run_eval.py)+ Agent 评测(golden-agent.jsonl 23 条 + run_agent_eval.py)
│   └── integration/          # smoke-chat.ps1 / hybrid-search.ps1 / api/test_api.py(6 测)
├── docs/                     # 用户与工程文档
│   ├── m2-usage.md / quickstart.md / safe-eject.md / troubleshooting.md
│   ├── acceptance-checklist.md / degradation-guide.md / known-limitations.md
│   ├── adr/                  # ADR 记录(v1.3.0 ADR-0001 sqlite-repo-split)
│   ├── superpowers/
│   │   ├── specs/            # 设计文档(2026-07-* 设计稿)
│   │   └── plans/            # 实施计划(2026-07-* 计划稿)
│   └── releases/             # v0.7 之前的里程碑(RELEASE-M3*.md)
├── dify/
│   ├── README.md             # v1.3.0 新增,说明 knowledge-pipeline.json 是历史快照
│   └── knowledge-pipeline.json  # v0.7 Dify Web UI 工作流导入快照(不再随架构演进)
└── data/ vectors/ cache/ logs/ tmp/
```

**绝对禁止修改**(系统策略):
- `.env` 任何文件
- `package.bat`(已获用户单项授权 `start.bat`/`stop.bat`,见 §13)
- 容器镜像 tag(4 个 image tag 锁定)
- `<private>/architecture-validation-report.md` Part 1(§1–§5)

**2026-07-16 用户明示授权可改**:
- `start.bat`(v0.8.4 重写,v0.8.9 补 MinerU 探测)
- `dify/knowledge-pipeline.json`(v0.8.4 document_parser 加 available:false)
- `architecture-validation-report.md` Part 2(可追加)

---

## 2. 入口与启动

| 入口 | 谁用 | 怎么用 |
|---|---|---|
| **start.bat** | 终端用户 | 双击启动(5 容器 + FastAPI + 前端 → `http://localhost:8000`) |
| **stop.bat** | 终端用户 | 安全弹出前必跑(停后端 → 停容器 → fsync → 备份) |
| **scripts/setup.ps1** | 交互式引导 | `pwsh -File scripts/setup.ps1` |
| **scripts/chat.ps1** | API/CLI fallback | `pwsh -File scripts/chat.ps1 -Question "..."` |
| **scripts/start-backend.ps1** | 启动后端 | `pwsh -File scripts/start-backend.ps1 -Port 8000` |
| **FastAPI 后端** | HTTP/SSE | `http://127.0.0.1:8000/api/chat` |
| **手动启动** | 工程师 | `docker compose -f KB-AI/docker-compose.yml up -d` |

`.env` 必须由用户从 `.env.example` 复制,AI agent **不主动生成真实 key**。

---

## 3. 技术约束(写代码时必看)

| # | 约束 | 违反示例 | 检测方法 |
|---|---|---|---|
| 1 | **PowerShell 5.1 兼容**(Windows 默认 PS) | 用 `??` null-coalescing(PS 6+) | 头部 `powershell -ExecutionPolicy Bypass -File tests/*.ps1` 跑通 |
| 2 | **UTF-8 无 BOM** | 默认 Out-File 会加 BOM | `[System.IO.File]::WriteAllText($p, $s, [System.Text.UTF8Encoding]::new($false))` |
| 3 | **Get-EnvVar + Test-IsPlaceholder 用 lib/ 公共库** | 内嵌重复实现 | dot-source: `. (Join-Path $PSScriptRoot 'lib/load-env.ps1')` |
| 4 | **SQLite 经 Python 子进程** | 用 System.Data.Sqlite | 写临时 .py → `python $tmp` |
| 5 | **Windows 路径优先 + 卷标 `AIAssistant`** | 假设 Linux/macOS 路径 | Test-Path 用绝对路径 |
| 6 | **容器无资源限制** | 加 mem_limit/cpus | 当前 5 容器**全部已设**(v1.5.0) |
| 7 | **Env 变量优先级**:显式 > env var > .env > 占位符 null | 直接读 .env | 用 `Resolve-ApiKey` |
| 8 | **占位符识别**:`sk-PLEASE-FILL-IN*` / `tvly-PLEASE-FILL-IN*` / `changeme` 一律 null | 误传真实 key | `Test-IsPlaceholder` 函数 |

---

## 4. 文档与索引(项目外但相关)

- **PRD v0.7**:`<private>/.harness/intake/custom-kb-qa-ai-prd-draft.md`(12 条 P0)
- **架构 v2**:`<private>/.harness/pm/custom-kb-qa-ai/arch-v2.md`
- **架构评审报告**:`<private>/architecture-validation-report.md`(Part 1 §1–§5 一致性 + Part 2 §6–§9 AWS Well-Architected + 11 条改进 TODO)
- **U-Brain v1.1 PRD**:`<private>/.harness/intake/您的私人顾问-PRD-v1.1.md`(本仓库未实施)

---

## 5. 已知偏差(必读,免得乱动)

| # | 偏差 | 位置 | 决议 |
|---|---|---|---|
| 1 | ~~`score_threshold` 双轨(0.0 / 0.6)~~ | `knowledge-pipeline.json:48`、`chat.ps1:104` | ✅ v0.7.1 统一为 0.6 |
| 2 | 容器数:架构写 3,实际 4(3 长跑 + 1 WAL init) | `docker-compose.yml` | Part 1 §2.3 已记录,接受 |
| 3 | ~~模型:PRD 双模型未实现~~ | `.env.example`、`chat.ps1` | ✅ v0.8.1 已实现双模型路由(qwen3.6-plus + qwen3.7-max) |
| 4 | Embedding 命名:`Qwen3-Embedding`(架构) vs `text-embedding-v3`(实现) | `knowledge-pipeline.json`、`embed-and-ingest.ps1` | 实为同一模型 |
| 5 | ~~启动脚本命名:`Windows-Start.bat`(架构) vs `start.bat`(实际)~~ | `docker-compose.yml:4` vs `start.bat` | ✅ v0.8.4 已对齐 |
| 6 | `START.bat` 启动 60-90s 接受范围,实测 30-60s | `QUICKSTART.md:42-44` | 接受 |
| 7 | `kb_ai_chunks` Qdrant collection 用 Cosine 距离 | `knowledge-pipeline.json:33` | 接受 |
| 8 | ~~document_parser 引用已移除的 MinerU~~ | `knowledge-pipeline.json:37` vs `docker-compose.yml` | ✅ v0.8.4 已加 `available:false` |
| 9 | **架构跃迁:chat.ps1 → FastAPI 后端**(v0.8.0~v0.8.4) | `backend/main.py` vs `scripts/chat.ps1` | ✅ 用户批准,chat.ps1 保留 fallback |
| 10 | **前端:Dify Web UI → 自建 React 前端**(v0.8.2) | `frontend/dist/` vs `http://localhost:8000` | ✅ start.bat 改开 localhost:8000;v0.8.10 删除 `backend/static/` 旧快照后,`frontend/dist/` 成为唯一前端 |
| 11 | `data/db.sqlite` 单库(无 cluster/U 盘绑定) | `backend/core/sqlite.py:35-72` | 接受(单用户场景) |

**原则**:不要"自作主张修复",任何一个偏差都可能是显式决策;**改前必查评审报告**。

---

## 6. 测试形态(必读,防止假阳性)

| 类型 | 路径 | 覆盖范围 | 跑法 |
|---|---|---|---|
| mock 回归 | `tests/test_m*.ps1` (11 个) | 形式合规,不含真 API | `pwsh -File tests/<test>.ps1` |
| pytest 单测 | `tests/unit/*.py` (25 个,223 测) | reranker/query_rewriter/retriever_fallback/debug_api/temporal_weighting/rag_core/streaming_extract + v0.8.11 database_crud/atomic_io/degradation_component/dashboard_aggregations + v0.8.12 eval_route/parsed_cache_namespacing + v1.1.0 PR#1 database_cascade/bulk_assign_qdrant + PR#2 limit_guard + PR#3 skip_clarification/image_endpoint + PR#4 tags_api/session_title | `backend/.venv/Scripts/python -m pytest tests/unit/ -v` |
| 容器集成 | `tests/integration/hybrid-search.ps1` | Qdrant + SQLite + Embedding + LLM 全链路 | 需 Docker + 真实 API Key |
| API 集成 | `tests/integration/api/test_api.py` | health/status/sessions/chat/debug(6 测) | `backend/.venv/Scripts/python -m pytest tests/integration/api/test_api.py -v` |
| vitest RTL | `frontend/src/__tests__/*.test.tsx` (2 个,10 测) | MessageBubble(7:图片缩略图/多选/跳过反问)+ TagChip(3:readonly/removable/颜色) | `cd frontend && npx vitest run` |
| RAG 评测 | `tests/eval/run_eval.py` | `/api/debug/retrieval` 检索质量,golden-qa.jsonl | 见 `tests/eval/README.md` |

**核心风险**:`[ALL PASS]` 只能证明"形式合规",拦不住"实现偏移";凡涉及 chat/embedding/Qdrant 行为,务必读源代码验证。

---

## 7. 行为守则(对 AI agent)

### 7.1 必须做
- ✅ 每次进入任务先读本文件;关键变更后**同步更新本文件**
- ✅ 任何评分、引用、证据都要附**文件:行号**
- ✅ 中文输出,术语对齐 §10 术语表
- ✅ 优先读已有文档(`.harness/`、`docs/`、`architecture-validation-report.md`);不重复造轮子
- ✅ 用 `docker compose config` 干跑验证

### 7.2 禁止做
- 🚫 **修改 `.env` 任何文件**(系统策略)
- 🚫 **修改 `package.bat`**
- 🚫 **修改 `architecture-validation-report.md` Part 1(§1–§5)**
- 🚫 **修改 `docker-compose.yml` 容器镜像版本**
- 🚫 **`docker compose up` 在未确认 .env 已填真实 key 前**
- 🚫 **删除 `data/` 任何内容**
- 🚫 **`scripts/*.ps1` 内嵌新 `Get-EnvVar` 函数**
- 🚫 **`git commit` / `git push` 未获用户授权**(`install-hooks.ps1` 装的 pre-commit/pre-push 钩子会自动跑门禁,但钩子是"阻止明显错误"而非"替代人工审核";授权语义由 controller 主对话掌控)

### 7.3 报告格式
- **中文 markdown**,优先表格 + 文件:行号锚点
- **必给**:现状 + 证据 + 建议 + 涉及文件 + 预估影响(TODO #N 格式)
- **优先级 emoji**:🔴 高 / 🟡 中 / 🟢 低

---

## 8. 危险操作清单(执行前必须问)

| 操作 | 风险 | 是否要做 |
|---|---|---|
| `docker compose up` | 启容器;占资源;撞端口;耗阿里云 quota | **未填 .env key 时禁止** |
| `docker compose down -v` | 删 volumes(含 `db.sqlite`、`vectors/*`) | **绝对禁止无确认** |
| `rm -rf data/*` | 同上 | **绝对禁止** |
| 修改容器镜像 tag | 锁版决策打破 | **禁止** |
| PS 6+ 特性加到 `scripts/*.ps1` | 破坏 PS 5.1 兼容 | **禁止** |
| `git commit` / `git push` | 用户未授权 | **禁止** |
| 跑外部 API(qwen/tavily/bing) | 消耗 token + 配额 | 任务需要时可,说明成本 |

---

## 8.5 代码门禁(v1.3.0 新增)

开发流第一步(新克隆后):

```powershell
pwsh -File scripts/install-hooks.ps1
```

装上 `core.hooksPath = scripts/hooks`,后续:

- `git commit` 自动跑 `ruff check backend/ tests/`(失败 abort,~2s)
- `git push` 自动跑 `scripts/run-checks.ps1`(全量 ruff + pytest + eslint + vite build,失败 abort,~30s)
- `pwsh` 不在 PATH 时 pre-push 降级为 noop + 警告;手动 `powershell -File scripts/run-checks.ps1` 验证

卸载:`pwsh -File scripts/install-hooks.ps1 -Uninstall`

---

## 9. 改进 TODO 索引

完整内容见 `<private>/architecture-validation-report.md` Part 2 §9。

| # | 描述 | 优先级 | 状态 |
|---|---|---|---|
| 1 | 端口裸绑 0.0.0.0(无 TLS/Auth) | 🔴 | ✅ 已修复(v0.7.1,已绑 127.0.0.1) |
| 2 | 4 容器无 mem_limit/cpus | 🔴 | ✅ 已修复(v0.7.1,全设) |
| 3 | score_threshold 双轨(0.0 / 0.6) | 🔴 | ✅ 已修复(v0.7.1,统一 0.6) |
| 4 | SQLite WAL 未显式启用 | 🔴 | ✅ 已修复(v0.7.1) |
| 5 | scripts 平铺,Get-EnvVar 重复实现 | 🟡 | 🟡 v0.7.1 建 lib/;残留已统一 Test-IsPlaceholder |
| 6 | tests 全 mock,无真集成 | 🟡 | 🟡 v0.7.1+ 建 smoke-chat/hybrid-search/test_api.py |
| 7 | health-probe "全失败才算 OFFLINE" | 🔴 | ✅ 已修复(v0.7.1,critical/optional 分级) |
| 8 | quickstart.ps1 ↔ QUICKSTART.md 同名易混 | 🔴 | ✅ 已修复(v0.7.1 重命名 setup.ps1) |
| 9 | chat.ps1 无 max_tokens 上限 | 🟢 | 🟢 v0.7.1 已加默认 2000;月度账单告警待补 |
| 10 | QUICKSTART.md 未提部署边界 | 🟢 | 保留 |
| 11 | 无 CI / linter | 🟢 | 🟡 v0.8.6 linter 已落地;CI 保留 |

---

## 10. 术语表

| 术语 | 含义 |
|---|---|
| **KB-AI** | 本项目代号,"知识库 AI 助手" |
| **Qwen3.6-Plus** | 实际生产模型 |
| **Qwen3.7-Max** | 复杂查询路由模型 |
| **text-embedding-v3** | 阿里云百炼 Embedding 模型(架构称 Qwen3-Embedding) |
| **ALIYUN_BAILIAN_API_KEY** | 阿里云百炼单一 API key(覆盖 LLM + Embedding) |
| **TAVILY_API_KEY** / **BING_SEARCH_API_KEY** | websearch 降级 |
| **AIAssistant** | USB SSD 卷标 |
| **kb_ai_chunks** | Qdrant collection 名,Cosine 距离,维度 1024 |
| **ScoreThreshold** | 0.6(v0.7.1 统一) |
| **health_status.json** | `data/health_status.json` 三端点可达性缓存 |

---

## 11. 跨对话恢复清单(给 AI 重启时)

按此顺序读,**总耗时 ~25 分钟**,即可恢复 90% 上下文:

1. **读本文件** `KB-AI/AGENTS.md`(5 min)
2. **读评审报告** `<private>/architecture-validation-report.md` 全文(8 min)
3. **读 docker-compose** 全 152 行(2 min)
4. **读 3 个核心脚本** `chat.ps1`(前 250 行)、`load-env.ps1`、`health-probe.ps1`(5 min)
5. **跑** `cd <private>/KB-AI && docker compose config`(<1 min)
6. **不修改 KB-AI/ 任何文件**,等用户指令

---

## 12. 前端设计基线(用户决策 · 2026-07-07)

> **状态**:用户已批准 4 个核心决策;设计真相源为 `design-system/MASTER.md` v1.4(历史)或 `design-system/XAIAgent-design-spec.md`(当前实施)。

### 12.1 决策矩阵(已锁版)

| # | 维度 | 决策 | 备注 |
|---|---|---|---|
| 1 | 品牌调性 | 经典商务黑灰 / XAIAgent 暗黑赛博(v0.8.2+) | 两者并存,当前实施后者 |
| 2 | 字体组 | 得意黑/阿里巴巴普惠体 + Playfair Display/Inter + JetBrains Mono | `design-system/MASTER.md` §5.1 |
| 3 | 信息架构 | 顶部 nav + 抽屉式历史 | 主区 chat;历史默认收起 |
| 4 | 模型路由 UI | **后端静默调(无 UI)** | 前端不显示模型切换 |

### 12.2 前端实施路径

- **范围**:完全替代 Dify Web UI(v0.8.2 用户批准)
- **已交付后端任务**(v0.8.0~v0.8.1):FastAPI `/api/chat`(SSE) / `/api/shutdown` / `/api/boot` / 模型路由 / `degradation_events` 表
- **当前实施风格**:XAIAgent 暗黑赛博(`design-system/XAIAgent-design-spec.md`)
  - 纯黑背景 `#000000`、熔岩橙 `#FF540E`、JetBrains Mono + Inter
  - 玻璃态卡片、3D 双环装饰、橙色主按钮
  - **已部署**:由 `backend/main.py` 挂载 `frontend/dist/` 至 :8000;设计真实载体是 `frontend/src/`(`backend/static/` 已于 v0.8.10 删除)

### 12.3 设计令牌(核心基线)

| 类别 | 值 | 类别 | 值 |
|---|---|---|---|
| 主色 | `#1F2937` | 间距阶 | 4/8/12/16/24/32/48 px |
| 强调色 | `#FF540E` | 字号阶 | 12/14/16/18/24/32/48 px |
| 背景 | `#000000` | 圆角 | 0/4/8/16 px |
| 错误 | `#DC2626` | 动效 | 150-300ms,transform/opacity |
| 警告 | `#D97706` | 辅助文字 | `#A1A1AA` |

> 变更 token 前必须同步更新 `MASTER.md` 修订记录。详细规范见 `design-system/XAIAgent-design-spec.md` 和 `MASTER.md`。

### 12.4 信息架构起点

8 个核心页面:聊天主页 / 历史抽屉(默认收起) / 资料库页 / 设置页 / 关闭确认模态 / 图片理解浮层 / 离线/降级提示条 / 启动进度模态。详细线框图见 `docs/frontend-prototype-checklist.md`。

### 12.5 角色分工

- **前端设计与实施 = AI 与用户协作**,用户保留最终决策权(品牌色、字体、页面结构等重大视觉决策需用户拍板)。
- **AI 角色**:可主动设计原型、实现组件、生成代码、复核偏差;重大决策前向用户确认。
- **AI 可做的事**:召回文档某节、解读锁版决策背景、输出设计稿/代码、列接口契约、复核设计稿。
- **AI 需先确认的事**:变更设计令牌、切换技术栈、修改受保护配置。

---

## 13. 变更记录摘要

> 完整记录见 `CHANGELOG.md`。本节仅保留关键里程碑。

| 日期 | 版本 | 关键变更 |
|---|---|---|
| 2026-08-28 | **v2.1.0** | **Streaming & Hardening(minor)**:①Agent 答案 token 级流式 —— `llm.py` 新增 `_post_chat_stream_with_tools`(tool_calls 分片按 index 聚合)+ `chat_with_fallback_tools_stream`(流式 L0→L3,已 yield delta 后失败不静默重试);`loop.py` `stream` 参数 + `answer_delta`/`answer_reset` 事件(收尾 `_wrap_up` 同样流式);前端 App.tsx 消费;②prompt injection 加固 —— kb/web observation 包 `<kb_context>`/`<web_context>` 分隔符 + 双系统提示词「数据非指令」声明;③修复 chat.py websearch 降级从未生效的存量 bug(`-Question`→`-Query` + 读 `results[]`);④`_AGENT_SYSTEM_PROMPT` 禁止心算强化(golden-agent multi_step_calc 失分根因);⑤test_retrieval_quality 环境泄漏隔离(.env RERANK_TOP_N);⑥公开仓作品集化 —— `docs/eval/` 移出 sanitizer 排除、README 重写(Agent 主线 + 隐私声明 + 版本修正)、新增 `docs/REVIEW-GUIDE.md` 面试官导览、sanitizer 增交付物流泛化规则;pytest 353→**371**(+18:test_agent_stream 8 + test_llm_stream_tools 5 + test_agent_tools 4 + 检索隔离 1)、ruff/vitest/build 全绿 |
| 2026-08-27 | **v2.0.0** | **Agent Edition(minor · 新能力)**:工具调用 Agent 全链路落地 —— 6 PR 收官(**PR#1** `agent/tools.py` 3 工具(kb_search/calculator/get_current_time);**PR#2** `llm.py` tools 扩展 + `agent/loop.py` ReAct 循环(复刻 L0→L3 降级);**PR#3** `agent_repo` 轨迹落库 + `/api/agent/*` 三端点(SSE 六事件 + cost-alert 阻断);**PR#4** `web_search` 工具 + 前端 AgentStepsPanel + 设置页 Agent 模式开关 + citation 全局编号修复;**PR#5** golden-agent 评测集 23 条 + `run_agent_eval.py`;**PR#6** 收口:version→2.0.0 + ADR-0002(自研 vs LangGraph));pytest 344→353、vitest 13→18、run-checks 4/4;公开仓同步 + `v2.0.0` tag(ADR-0002 详见 `docs/adr/0002-agent-loop-self-built.md`) |
| 2026-07-13 | v0.7.1~0.7.2 | 健康度体检全面修复;Hybrid Search 实现 |
| 2026-07-13 | v0.8.0 | FastAPI 后端包装层实现 |
| 2026-07-13 | v0.8.1 | 双模型路由;XAIAgent 暗黑赛博风格 |
| 2026-07-13 | v0.8.2 | 冷启动进度模态 |
| 2026-07-14 | v0.8.3 | frontmatter + 代码/表格分块;CrossEncoder reranker |
| 2026-07-14 | v0.8.4 | Query 改写 + 个人实体库;检索容错;调试面板 |
| 2026-07-15 | v0.8.5 | CertaintyTagger + 时间加权;全量重新入库 |
| 2026-07-16 | v0.8.6 | FMEA 全套修复(CORS/安全弹出/备份/磁盘告警) |
| 2026-07-17 | v0.8.7 | 性能优化:流式输出/health 缓存/reranker 截断 |
| 2026-07-17 | v0.8.8 | 感知性能 UX:ThinkingStatus 组件 |
| 2026-07-17 | v0.8.9 | start.bat 补 MinerU 探测;stop.bat 补 MinerU 关闭 |
| 2026-07-20 | v0.8.10 | 目录与结构整理(单 commit,无功能变更):删 9 临时 + 6 重复;迁 3 里程碑至 docs/releases/;同步 backup.ps1:11,135 + package.bat:67;同步 AGENTS.md / CHANGELOG.md / README.md;版本号 0.8.9 → 0.8.10;详见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md |
| 2026-07-20 | v0.8.11 | Yuxi-Know 借鉴落地 + PRD REQ-2 治根 + 4 条 FMEA 🔴 关闭:Database 抽象层(治 REQ-2 分类标签);processing_state 持久化 + 启动自检(治 F07/F20);atomic_io 模块(治 F11/F13);degradation_events.component 维度(治 F06);docker-compose start_period 完整化;Dashboard 后端+前端(治 F08 + GA 形态);详见 CHANGELOG.md v0.8.11 |
| 2026-07-20 | v0.8.12 | Phase 2 技术债清理:eval 路由化(治 F15 378)— `tests/eval/run_eval.py` 重构出 `run_evaluation()` 结构化函数 + `/api/eval/run` 路由 + Dashboard 金标问答卡片;解析产物分层(借鉴 H)— `parse_to_markdown` 加 `db_id` 参数,cache 走 `<db_id>/<doc_id>/` 分层,旧版路径向后兼容;`backup.ps1` 生成 SHA-1 manifest 进 zip;详见 CHANGELOG.md v0.8.12 |
| 2026-07-20 | **v1.0.0** | **GA 锁定**:3 份交付文档(`docs/acceptance-checklist.md` / `degradation-guide.md` / `known-limitations.md`);版本号 0.8.12→1.0.0;12 条 P0 全过、5 条 FMEA 🔴 已关、167 单测全绿;详见 CHANGELOG.md v1.0.0 |
| 2026-07-20 | **v1.0.1** | **PRD 三处偏离同步**(doc-only):REQ-9 腾讯云 CVM → U 盘单机;REQ-10 浅色 → XAIAgent 暗黑赛博;REQ-13 自动 COS+AES → 手动本地 7 份轮转;第 3 节部署流程与第 4 节验收清单同步 v1.0.0 现状;详见 CHANGELOG.md v1.0.1 |
| 2026-07-21 | **v1.1.0** | **4 PR 收官**:**PR#1** data-integrity(级联 409 / Qdrant payload 重写 / 治 #9 + #11);**PR#2** limit-guard(50 轮软警告 / 单图 20MB / 多图 5 张 / PATCH history_limit / 治 #3 + #4 + #8);**PR#3** ui-feedback(图片缩略图 / 多选题 / 跳过反问 / 治 #2 + #5 + #6);**PR#4** tag-and-title(自由标签 tags/doc_tags 表 + 7 端点 + TagChip/TagPicker + streaming title debug 日志 + schema_migration boot 阶段 / 治 #1 + #7)。pytest 167→223(+56)、vitest 0→10(+10)、FastAPI 路由 13→20;`scripts/run-checks.ps1` 4/4 全绿;详见 CHANGELOG.md v1.1.0 + `docs/known-limitations.md` §2(10 项已修复) |
| 2026-07-21 | v1.2.0 | RAG 质量 4 PR 收官:golden set 50/50 + QueryProfile + 短问题门控 + 年份优先 + 长问题 reranker cap;pytest 223 → 252(+29) |
| 2026-07-21 | v1.3.0 | 运维加固与文档同步:**4 PR 收官** — **PR#1** hooks(git hooks + install-hooks.ps1);**PR#2** cost-alert 后端(`llm.py` usage 采集 + `chat.py` SSE error event 阻断 + `dashboard.py` cost_alert 字段 + `cost-alert.ps1` + 18 新测);**PR#3** cost-alert 前端(DashboardPage card + `CostAlert` 类型 + 3 新测);**PR#4** 文档收口(version 1.2.0→1.3.0 + CHANGELOG + AGENTS + QUICKSTART §9 + dify/README + known-limitations/acceptance-checklist 更新 + degradation-guide SSE error event 场景)。**注意:项目外 PRD 修改延期到下个 session**(本 session 未获用户对 `<private>/.../prd-draft.md` 的修改授权);测试基线 `cccb11e`+ 后 = **pytest 252→275(+23,v1.3.0 +18 cost-alert + 用户并行 sqlite-refactor +5)/ vitest 10→13(+3 DashboardPage.test)**;ruff / tsc / vite build 全绿;详见 CHANGELOG.md v1.3.0 + `docs/superpowers/specs/2026-07-21-v1.3-ops-hardening-design.md` + `docs/known-limitations.md` §6(v1.3.1+ backlog) |
| 2026-07-22 | v1.3.1 | **cost-alert 鲁棒性强化(patch)**:whole-branch review §6 A-D 4 项收口 — 日志轮转(50MB gzip 归档)+ UTC 规范化(`DateTimeOffset`)+ `safe_get_usage_tokens` 防御性解析 + `validate_cost_alert_payload` 字段级校验;pytest 275 → 292(+17);详见 CHANGELOG.md v1.3.1 + `docs/superpowers/specs/2026-07-22-v1.3.1-cost-alert-hardening-design.md` |
| 2026-07-22 | v1.5.1 | **容器化 patch**:v1.5.0 验证发现 2 真实问题收口 — Dockerfile hotfix(镜像 14.2GB → 2.89GB;`--index-url pytorch-cpu` + 动态 libicu 检测 + 装 Linux pwsh 7.4 LTS);`backend/core/ps_runner.py` `run_ps` 缺失脚本返回 `skipped=True`;`backend/api/health.py` skipped 路径返回 200 + degraded JSON;新增 14 测;**pytest 306→320(+14)** / vitest 13(不回归)/ 锁版 tag 全部未动;详见 CHANGELOG.md v1.5.1 + `docs/superpowers/specs/2026-07-22-v1.5.1-containerization-hotfix-design.md` |
| 2026-07-22 | v1.5.2 | start.bat 启动日志落地(修闪退盲区)+ `E:\logs\start-YYYYMMDD-HHMMSS.log` 自检索(详见 CHANGELOG.md v1.5.2 + `docs/superpowers/specs/2026-07-22-v1.5.2-start-bat-logging-design.md`) |
| 2026-07-22 | v1.5.3 | **stop.bat 停止日志落地(patch)**:配 v1.5.2 完整 start/stop 观测性闭环 —— `stop.bat` 行 13 后新增 ~19 行日志初始化 + 27 处 echo 加 `>> "%LOG_FILE%"` + 4 处 ASCII 圆括号清理(`(kb-ai-backend)` / `(:8001)` / `(给 10 秒优雅退出)` / `(scripts\backup.ps1)` 全部 → `·` separator,v1.5.2 C.3 hotfix 复刻)+ 退出收尾(endlocal 前一行 `=== stop.bat 退出 (errorlevel=N) ===`)+ 失败兜底(只读单行警告不阻断);`E:\logs\stop-YYYYMMDD-HHMMSS.log`;`tests/integration/test_stop_bat_logging.py` 新建 12 测(含 4 个 ASCII paren 守护白名单 + for 块内 echo `>>` 验证 + `goto backup_step` / `:safe_eject` 标签守护 + `powershell backup.ps1` / MinerU kill 调用**不**加 `>>` 守护);**pytest 320 → 332(+12)** / vitest 13(不回归)/ 锁版镜像 tag 全部未动/ 锁版红线(`.env` / `package.bat` / `start.bat` / `architecture-validation-report.md` Part 1)全部未动;详见 CHANGELOG.md v1.5.3 + `docs/superpowers/specs/2026-07-22-v1.5.3-stop-bat-logging-design.md` |
| 2026-07-22 | v1.5.4 | **PS 脚本日志统一化(patch)**:完成 start/stop/health/cost-alert 四个观测性矩阵闭环 —— 新建共享助手 `scripts/lib/Write-Log.ps1`(3 函数 `Initialize-LogFile` / `Write-LogHost` / `Close-LogFile`,含 `-NoNewline` 透传 + 失败兜底 `$Script:LogFile=$null` + 保留最近 20 个);`scripts/health-full.ps1` dot-source 助手 + `Initialize-LogFile -ScriptName "health-full"` + 32 处 `Write-Host` → `Write-LogHost` + `Close-LogFile` 退出收尾;`scripts/cost-alert.ps1` 同(`Initialize-LogFile -ScriptName "cost-alert"` + 10 处 `Write-LogHost` + 2 处 `Close-LogFile` DryRun + 正常结束);`E:\logs\health-full-YYYYMMDD-HHMMSS.log` + `E:\logs\cost-alert-YYYYMMDD-HHMMSS.log`;`tests/integration/test_ps_scripts_logging.py` 新建 14 测(5 lib 测 + 4 health-full 测 + 5 cost-alert 测,含 v1.3.1 CostLog-Rotate dot-source 守护);**pytest 332 → 346(+14)** / vitest 13(不回归)/ 锁版红线全部未动;详见 CHANGELOG.md v1.5.4 + `docs/superpowers/specs/2026-07-22-v1.5.4-ps-scripts-logging-design.md` |
| 2026-07-22 | v1.5.5 | **PS 脚本日志统一化 · 批次 2(patch)**:补完 health-probe / disk-alert 两个观测入口 —— `scripts/health-probe.ps1` dot-source v1.5.4 助手 + `Initialize-LogFile -ScriptName "health-probe"` + 6 处 `Write-Host` → `Write-LogHost`(含 Write-Step / Write-Warn 函数体)+ `Close-LogFile` 退出收尾;`scripts/disk-alert.ps1` 同 + **`Initialize-LogFile` 放在 `$isMain` 检查之后**(🔴 关键:disk-alert 被 health-full dot-source 加载 `Get-KBAIDiskUsage`,防止日志副作用污染调用方)+ 15 处 `Write-LogHost` + 4 处 `Close-LogFile`(OutputJson + 3 个 level exit)+ `data/disk-alerts.log` 追加逻辑不破坏;`E:\logs\health-probe-*.log` + `E:\logs\disk-alert-*.log`;`tests/integration/test_ps_scripts_logging.py` 扩展 +11 测(4 health-probe + 4 disk-alert + 3 防回归:`$isMain` 顺序守护 + `disk-alerts.log` 追加守护 + `-OutputJson` 不污染);**pytest 346 → 357(+11)** / vitest 13(不回归)/ 锁版红线全部未动;**观测矩阵 6/8 完成**(剩 backup.ps1 + version.ps1 候选 v1.5.6+);详见 CHANGELOG.md v1.5.5 + `docs/superpowers/specs/2026-07-22-v1.5.5-ps-scripts-logging-batch2-design.md` |
| 2026-07-22 | v1.5.6 | **backup.ps1 日志化(patch)**:补完 backup 观测入口 —— `scripts/backup.ps1` dot-source v1.5.4 助手 + `Initialize-LogFile -ScriptName "backup"` + **`Write-Step` 函数体重构**(拆分为 `if (-not $Quiet) { Write-LogHost } elseif ($Script:LogFile) { Add-Content }` 两分支,🔑 关键语义:stop.bat 调用 -Quiet 时 console 静默但 log 文件仍写,便于取证)+ 6 处 `Write-LogHost` + 5 处 `Close-LogFile`(路径解析 / 无数据 / 空间不足 / 成功 / catch)+ 同盘守卫 `$rootDrive -eq $destDrive` 逻辑未丢;`E:\logs\backup-*.log`;`tests/integration/test_ps_scripts_logging.py` 扩展 +6 测(4 backup + 1 Quiet 模式语义守护 + 1 同盘守卫防回归);**pytest 357 → 363(+6)** / vitest 13(不回归)/ 锁版红线全部未动;**观测矩阵 7/8 完成**(剩 version.ps1 候选 v1.5.7+);详见 CHANGELOG.md v1.5.6 + `docs/superpowers/specs/2026-07-22-v1.5.6-backup-bat-logging-design.md` |
| 2026-07-22 | v1.5.7 | **version.ps1 日志化(patch) · 收尾 8/8 观测矩阵**:`scripts/version.ps1` dot-source v1.5.4 助手(在 disk-alert.ps1 dot-source **之后**)+ `Initialize-LogFile -ScriptName "version"` + 3 处 `Write-Host` → `Write-LogHost`(banner 上下空行 + 状态行)+ 2 处 `Close-LogFile`(JSON 路径 + 正常路径);`E:\logs\version-*.log`;`tests/integration/test_ps_scripts_logging.py` 扩展 +7 测(4 version + 3 防回归:`-Json` 模式不污染 + disk-alert/get-usb-root dot-source 不丢);**pytest 363 → 370(+7)** / vitest 13(不回归)/ 锁版红线全部未动;**🎯 观测矩阵 8/8 完整完成** — start.bat / stop.bat / health-full.ps1 / cost-alert.ps1 / health-probe.ps1 / disk-alert.ps1 / backup.ps1 / version.ps1 全部日志化;详见 CHANGELOG.md v1.5.7 + `docs/superpowers/specs/2026-07-22-v1.5.7-version-ps-logging-design.md` |
| 2026-07-22 | **v1.6.0** | **logs-summary.ps1 诊断汇总工具(minor · 新功能)**:新增 `scripts/logs-summary.ps1` —— 把 v1.5.2 ~ v1.5.7 落地的 8 个观测日志聚合成一屏报告:总文件数 + 8 个入口活跃度 + 错误/警告按来源分桶 + 最近 5 条 error/warn + JSON 模式给 CI 消费;参数:`-LogDir`(默认 `E:\logs\`)、`-SinceStr`(支持 `24h` / `7d` / 绝对时间,空 = 全部)、`-Json`;退出码:0 无 error / 1 有 error / 2 致命(目录不存在);**只读消费侧,纯消费 tools,不写日志文件**;实施期 hotfix:`-Since` 顶层参数与函数内 `[DateTime]$Since` 形参在 PS 5.1 下触发 ParameterArgumentTransformationError(空串误转 DateTime)→ **改名为 `-SinceStr`** 避开作用域冲突;`tests/integration/test_logs_summary.py` 新建 12 测(5 结构 + 4 子场景实跑 + 3 防回归);**pytest 370 → 382(+12)** / vitest 13(不回归)/ 锁版红线全部未动;详见 CHANGELOG.md v1.6.0 + `docs/superpowers/specs/2026-07-22-v1.6.0-logs-summary-design.md` |
| 2026-07-28 | **v1.7.0** | **macOS 全链路支持(minor · 新平台 · maintainer 自用换机驱动)**:**单源 PowerShell 编排 + 平台薄壳** —— start.ps1/stop.ps1/precheck.ps1 在 Win/Mac 跑同一份逻辑,平台差异由 `scripts/lib/platform-utils.ps1` 统一处理;`.bat` 一行不动,Win 客户机零回归。**新增 6**:platform-utils.ps1(11 函数,~250 行,PS 5.1 兼容,不用 `$IsMacOS`)+ precheck.ps1(5 项检查:CPU/OS/磁盘/内存/平台专属)+ start.ps1(8 阶段)+ stop.ps1(5 步)+ package.ps1(Compress-Archive 跨平台)+ start.command/stop.command/package.sh(Mac 双击入口);**修改 5**:start-backend.ps1 行 38/39/85 venv 路径走 `Get-KBAIPythonVenv*`+ run-checks.ps1 行 33 同上 + hooks/pre-commit 加 `.venv/bin/ruff` elif + safe-eject.ps1 MessageBox → `Show-KBAINotice` + Write-Log.ps1 加 `[AllowEmptyString()]` 修空串 bug;**新增 3 个测试文件**:test_mac_platform_support.py(12)+ test_start_ps1_platform.py(11)+ test_safe_eject_platform.py(5)= **+24 测**;**pytest 398 → 422** / vitest 13(不回归)/ 锁版红线(`.env` / `package.bat` / `start.bat` / `architecture-validation-report.md` Part 1 / 容器镜像 tag)全部未动;关键设计修正:plan §十 13 项(`$IsMacOS` PS 5.1 兼容 / `Show-KBAINotice` 改 heredoc / `$script:KBAIPlatform` 改函数 / precheck 5 项全实现 / 工作量 2.5→4.0 天 等);详见 CHANGELOG.md v1.7.0 + `docs/superpowers/specs/2026-07-28-v1.7.0-mac-support-design.md`;**maintainer 手动验收 4 项**(Mac 拿到后):`docker manifest inspect langgenius/dify-api:1.0.0` 看 linux/arm64 + `docker buildx build --platform linux/arm64 .` 跑过 + virtiofs 30min 写 SQLite 无 lock + Gatekeeper 首次放行;**留待 v1.7.1+**:start.bat 改薄壳 / platform-utils 升 .psm1 / kb-ai-cli.ps1 命令式 |
| 2026-07-22 | v1.5.0 | **后端容器化(minor)**:`docker/backend/Dockerfile` 35 行多阶段(python:3.12-slim builder→wheel / runtime 离线装 + 源码 + HEALTHCHECK `/api/health`);`docker-compose.yml` 5 service 编排 + 新增 `kb-ai-backend`(`kb-ai/backend:local` **新增本地 tag**)+ volumes 共享 + depends_on qdrant/dify-api service_healthy;`start.bat` / `stop.bat` 重接(⚠️ 触发 §7.2 红线,经用户授权)+ MinerU 保留;`docs/backend-container.md` 边界文档;`tests/integration/test_backend_container.py` 14 测;**pytest 292→306(+14)** / vitest 13(不回归)/ 锁版 tag 全部不动;详见 CHANGELOG.md v1.5.0 + `docs/superpowers/specs/2026-07-22-v1.5-backend-containerization-design.md` + `docs/superpowers/plans/2026-07-22-v1.5-backend-containerization.md` + `docs/backend-container.md`
| 2026-07-22 | v1.4.0 | **Dockerfile 多步构建范式化交付(minor)**:范式化关闭 known-limitations §4 #3(不解决 1.5GB 镜像 / 5-10min 冷启动,仅落地多阶段样本);3 项 — `docker/dify-db-init/Dockerfile`(16 行 builder+runtime, post-fix `c8f5b83` 增加 runtime `apk add` 共享库)+ `docker-compose.yml` dify-db-init 切 `build: + image: kb-ai/dify-db-init:local`(**新增本地 tag**,spec §1.4 显式声明并经用户授权)+ 根 `.dockerignore` 32 行范本 + `docs/docker-build.md` 边界文档;pytest 292 → 292(+0,纯构建/文档层);详见 CHANGELOG.md v1.4.0 + `docs/superpowers/specs/2026-07-22-v1.4-dockerfile-paradigm-design.md` + `docs/superpowers/plans/2026-07-22-v1.4-dockerfile-paradigm.md` |
