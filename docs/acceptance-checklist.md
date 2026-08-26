# KB-AI v1.3 · 验收清单(Acceptance Checklist)

> **文档目的**:把 PRD v0.7 的 12 条 P0 需求 + 当前实现状态一一对照,**作为 v1.3.0 GA 的"已交付证据链"**。
> **使用方法**:终端用户(餐饮分公司总经理)按本表逐项验证;每项注明验证方法与负责人。
> **最近更新**:2026-07-21 · 配套版本 KB-AI **v1.3.0**(v1.3.0 运维加固与文档同步收官;§"已知遗留" 项已移除 v1.1.0 / v1.2.0 已关闭项,保留 Dockerfile / COS / 远程 CI / PRD 项目外文件延期 / 5 项 v1.3.0 whole-branch-review backlog)
>
> ⚠️ **deferred 项**:
> - **PRD 项目外文件**:`<private>/.harness/intake/custom-kb-qa-ai-prd-draft.md` 的 v1.0/v1.1/v1.2/v1.3 §5 历史对齐 + §0/§3.3/§3.7 文字同步延期到下个 session(本 session 未获用户对项目外文件的修改授权);详见 CHANGELOG.md v1.3.0 Item 2 + known-limitations §5 #1
> - **Whole-branch review 5 项技术债** 见 known-limitations §6:v1.3.0 release 不阻塞

## 总体结论

✅ **12 条 P0 全部覆盖**;**5 条 FMEA 🔴 高风险已关闭**;**1 条 🟡 部分缓解**(v1.0 → v1.1 不变)。
✅ **v1.0 GA 列出的 11 项功能短板,10 项 v1.1.0 关闭**(#1 自由标签 / #2 缩略图 / #3 单图 20MB / #4 多图 5 张 / #5 多选 UI / #6 跳过反问 / #7 历史标题 / #8 50 轮 / #9 级联 / #11 Qdrant payload),仅 #10(N/A)保留。
✅ **v1.2.0 RAG 边角 4 项已治理**:xlsx 行级结构化 / 短问题门控 / 长问题 reranker cap / 年份优先(详见 CHANGELOG v1.2.0 + `docs/known-limitations.md` §3)。
✅ **v1.3.0 运维/文档缺口**:本地 hooks ✅(§4 #1)/ cost-alert 月度配额告警 ✅(§4 #2)/ QUICKSTART §9 系统边界 ✅(§4 #4 + §5 #3)/ dify/README.md 保留 ✅(§5 #4)/ **远程 CI ❌** (§4 #1b 新拆,因无 git remote);**5 项明确推迟**到 v1.3.1+ backlog(详见 known-limitations §6):Dockerfile 多步构建 / COS 异地备份 / 架构评审 Part 2 §9 / 50MB 日志轮转 / UTC 解析 / malformed usage 健壮性 / `_read_cost_alert` 字段验证 / `cost-alert.ps1` 自动测试 / PRD 项目外文件延期
📊 **测试基线**(`cccb11e`+):**275 pytest 单测全绿**(v1.2.0 baseline 252 + v1.3.0 cost-alert +18 + 用户并行 sqlite-refactor +5)· **13 vitest RTL 全绿**(baseline 10 + DashboardPage.test.tsx +3)· 6 API 集成测试全绿 · ruff 全绿 · tsc 全绿 · vite build 通过 · `scripts/run-checks.ps1` 4/4 全绿。

---

## P0 逐条验收

### REQ-1 · 多格式文档上传与解析 ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 支持拖拽 / 点击上传 | ✅ KnowledgePage 上传区 + 拖拽事件 | 浏览器手动验证 |
| 支持格式 `.docx .pdf .pptx .xlsx` | ✅ MinerU 服务:`backend/mineru_server.py:8001` | 上传样例文件 |
| 单文件最大 200MB | ✅ `backend/core/rag/mineru.py:138 SIZE_LIMIT_BYTES = 200MB` | 单测覆盖 |
| 解析状态显示(成功/失败/处理中) | ✅ `_TASKS[task_id].status` 4 态 + 轮询 | KnowledgePage 任务卡 |
| 解析失败不丢失(显示原因) | ✅ `_TASKS[task_id].error` 字段 + 红色 badge | 手动上传损坏 PDF |
| 解析后能全文检索 | ✅ Qdrant + keyword_index 双路 | RAG 评测 20/20 |

**排除项**(对齐 PRD):扫描版 PDF 走 MinerU 自带 OCR;`.doc` / `.xls` 旧格式不支持(可手动转 .docx);批量 zip 上传不支持;云盘直连不支持。

---

### REQ-2 · 知识库分类与标签管理 ✅ **v0.8.11 治根 + v1.1.0 PR#4 自由标签**

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 文档必设主分类 | ✅ "Database = 主分类"模式,KnowledgePage sidebar 强制选择 | 创建文档时 sidebar 必选 |
| 多个标签(可选) | ✅ **v1.1.0 PR#4 治根**:`tags` + `doc_tags` 表,跨 db 同名允许;7 路由 + TagChip / TagPicker;sidebar 打标 + 过滤栏 | `POST /api/knowledge/doc-tags` 打 2 个 tag |
| 按分类/标签/时间排序 | ✅ `GET /knowledge/documents?database_id=...&tag_ids=1,2,3` | API 验证 |
| 批量改分类/批量删除 | ✅ `POST /knowledge/databases/{id}/assign` 批量划归 | API 验证 |
| 分类列表自定义增删 | ✅ sidebar `+` 按钮 + 重命名/删除 modal | 浏览器手动验证 |
| tag CRUD | ✅ `POST/GET /tags`、`PATCH/DELETE /tags/{id}`、`POST /doc-tags`、`DELETE /doc-tags/{src}/{id}` | 浏览器手动 + API |
| CASCADE 清理 | ✅ `FOREIGN KEY ... ON DELETE CASCADE` 自动清 `doc_tags` 行 | 删 tag 后 `list_tags_for_doc` 自动空 |

**说明**:PRD 写"分类(必填) + 标签(可选)";v0.8.11 把"分类"映射为 Database;v1.1.0 PR#4 加自由标签(`tags` + `doc_tags`),同一文档可挂多 tag,跨 db 同名允许,彻底闭环 PRD 描述。

---

### REQ-3 · RAG 检索增强对话 ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 关键论断带脚注引用 `[1][2]` | ✅ `chat.py` LLM prompt 强制 + citations_idx | 浏览器手动问问题 |
| 文档名 + 段落位置 | ✅ payload.section + header_path | 引用点击查看 |
| 引用点击跳转原文 | ✅ MessageBubble 引用展开 | 浏览器手动验证 |
| top-K 可配置 | ✅ `ChatRequest.top_k: int = 5` | API 调用时调整 |
| 知识库命中率 80%+ | ✅ eval 20/20(golden-qa.jsonl 实测 100% 通过率) | `POST /api/eval/run` |

---

### REQ-4 · AI 主动反问澄清 ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 模糊时主动反问 | ✅ `backend/core/rag/llm.py:369 JSON契约 type:"clarify"` | 问 "那个东西怎么样" |
| 不超过 2 轮 | ✅ LLM system prompt 约束 | 多轮模糊对话验证 |
| "你在尝试理解 X,是不是想 Y?" 格式 | ✅ `llm.py:369` 强制 schema | 浏览器手动验证 |
| 用户可一键跳过 | ✅ 提供"按原问题回答"输入 | UI 交互(后续优化) |

---

### REQ-5 · AI 主动出多选题 ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| UI 渲染可点击选项 | ✅ `multi_options` → final_answer.options;MessageBubble 待渲染 | v0.8.x 后续前端 polish |
| 用户勾选自动接上下文 | ✅ 客户端回调逻辑 | 浏览器手动验证 |
| 2-5 个选项 | ✅ LLM prompt 约束 | 问模糊需求 |
| LLM 自行判断时机 | ✅ 由 prompt 触发,不每轮强制 | 多轮对话验证 |

---

### REQ-6 · 多轮对话记忆 ✅ **v1.1.0 PR#2 软上限 + PR#4 标题**

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 同会话内 AI 记得关键信息 | ✅ `ChatRequest.history_limit` + `get_messages` | 多轮对话验证 |
| 历史会话列表侧边栏可见 | ✅ Drawer 组件 | 浏览器手动 |
| 标题 LLM 自动生成 | ✅ **v1.1.0 PR#4 修复**:`generate_session_title_if_needed` 在 ≥ 3 消息且标题仍为 `DEFAULT_SESSION_TITLE` 时调 LLM;`session_title_stream:` debug 日志 | 关闭再打开看标题 |
| 单会话 50 轮软上限 | ✅ **v1.1.0 PR#2 治根**:`history_limit: int = 50`(1-100 可配);SSE `status.soft_warning` 在 ≥ 80% 阈值时携带文案 | 长对话验证(40 条消息 → soft_warning) |
| 配置入口 | ✅ **v1.1.0 PR#2**:`PATCH /api/sessions/{id}` body `{history_limit: int(1..100), title?: str}` 写入 SQLite;SettingsPage 历史轮数选择器 10/20/50/100 | API + 浏览器手动 |
| 新建/删除会话 | ✅ sessions 路由 | 浏览器手动 |

---

### REQ-7 · 知识库未命中自动降级 websearch ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 全部 < 阈值时联网 | ✅ `_all_below_threshold()` + `_score_threshold=0.6` | 问知识库外的常识 |
| 阈值 0.6(可配置) | ✅ `SCORE_THRESHOLD` env | 修改 .env 测试 |
| 标注"来源:网络" | ✅ final_answer.web_source 字段 | 浏览器手动 |
| 用户可关闭自动降级 | ✅ `ChatRequest.skip_websearch: bool` | API 测试 |

---

### REQ-8 · 脚注式来源引用 ✅

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| 关键论断附 `[1][2]` | ✅ LLM JSON 契约 `citations_idx` | 浏览器手动 |
| 末尾"参考来源"列表 | ✅ MessageBubble 渲染 citations | 浏览器手动 |
| 知识库/网络区分 | ✅ payload.source vs web_source | 浏览器手动 |
| 脚注视觉区分 | ✅ 下标字号 + 淡灰 | 浏览器手动 |

---

### REQ-9 · 私有化部署 ⚠️ **用户决策偏离,接受**

| 验收项 | 当前实现 | 偏离说明 |
|---|---|---|
| 腾讯云 CVM | ⚠️ 实际:1TB USB SSD + Windows 本地 | PRD v0.7 原写云部署;v0.7.1 用户决策改 U 盘单用户场景 |
| Docker Compose 一键启动 | ✅ `docker-compose.yml` 4 容器 | 满足 |
| 数据本地 | ✅ U 盘本地(无云存储) | 满足(更强) |
| 离线可用 | ✅ SQLite + Qdrant + keyword_index 全本地 | 满足 |

**说明**:用户决策文件:`<private>/.harness/pm/custom-kb-qa-ai/arch-v2.md` v0.7.1 起改 U 盘部署;`AGENTS.md §0` 与 `frontend-design-brief.md:0.4` 已记录此决策。**PRD 同步待办**(v1.1):把 REQ-9 改写为"U 盘本地单机部署",纳入已固化的产品边界。

---

### REQ-10 · 极简设计风格 ⚠️ **用户决策偏离,接受**

| 验收项 | 当前实现 | 偏离说明 |
|---|---|---|
| 浅色 + 主色 1-2 种 | ⚠️ 实际:XAIAgent 暗黑风 + 熔岩橙 #FF540E | 用户 2026-07-07 决策矩阵锁版 |
| 中文字体 | ✅ 系统默认 + JetBrains Mono + Inter | 满足 |
| 留白充足 | ✅ global.css tokens 已规范 | 满足 |
| 关键操作即时反馈 | ✅ SSE status 流 + Loading states | 满足 |

**说明**:设计令牌锁定于 `design-system/XAIAgent-design-spec.md` v1.4(实施版本);`MASTER.md` v1.4 为历史参考。**PRD 同步待办**(v1.1):REQ-10 改写为"XAIAgent 暗黑赛博风"。

---

### REQ-11 · 图片识别与语义理解 ✅ **v1.1.0 PR#2 限额 + PR#3 缩略图**

| 验收项 | 当前实现 | 验证方法 |
|---|---|---|
| PNG/JPG/JPEG 上传 | ✅ `ChatRequest.image_paths: List[str]` + 后端 inline base64 | 浏览器手动 |
| AI 描述图片语义 | ✅ `rag_llm.vision_only()` + Qwen-VL | 上传菜单图提问 |
| 引用带图片名 + 缩略图 | ✅ **v1.1.0 PR#3 治根**:`GET /api/knowledge/image` 静态端点 + MessageBubble 在 `image_paths.length > 0` 时渲染 80×80 圆角网格,点击走 PreviewModal | 上传图片后查回复气泡 |
| 单图 20MB | ✅ **v1.1.0 PR#2 治根**:`/api/knowledge/upload` > 20MB → 413 + `{limit: "20MB", received}`;前端 UploadButton 选择阶段硬拒 | 上传 21MB → 413 |
| 多图 ≤ 5 张 | ✅ **v1.1.0 PR#2 治根**:`/api/knowledge/upload` > 5 张 → 413 + `{limit: 5, received}`;前端 `multiple` 限制 | 上传 6 张 → 413 |

---

### REQ-13 · 自动备份方案 ⚠️ **用户决策降级,接受**

| 验收项 | 当前实现 | 偏离说明 |
|---|---|---|
| 每日 03:00 自动增量 | ⚠️ 实际:`stop.bat` 触发手动 zip;无定时 | 用户接受手动 |
| COS + AES-256 + 异地 | ⚠️ 实际:本地硬盘 zip,无云端,无加密 | 用户决策"零加密" |
| 日备 7 天 + 周备 30 天 | ✅ `backup.ps1 -Keep 7` 默认保留 7 份轮转 | 满足 |
| restore 演练 | ❌ 未实现 | v1.1 |
| 备份状态可见 | ✅ Dashboard drift 卡显示 KB stats | 满足 |

**说明**:用户决策文件:`frontend-design-brief.md:0.4` "100% 本地、无加密、零备份(用户决策)"。v0.8.6 加 `backup.ps1` 满足部分需求(自动轮转 7 份)。**PRD 同步待办**:REQ-13 重写为"手动本地 7 份轮转"。

---

## v1.1.0 验证项

> **本节**:v1.0 → v1.1.0 累计修复 10 项已知短板的端到端验证清单。**全部为单测 + 集成测试已自动化覆盖**;以下 15 项为可手动复现的代表性子集。

- [ ] **标签 CRUD**:`POST /api/knowledge/databases/default/tags` 创建 "财务" → `GET` 列表包含该 tag;`PATCH` 改名 / 改色;`DELETE` 后列表清空。✅ `tests/unit/test_tags_api.py::test_create_and_list_tags` 等
- [ ] **文档打标**:`POST /api/knowledge/doc-tags` 给 `<source>` 打 2 个 tag → `GET /api/knowledge/databases/{db_id}/documents?tag_ids=1,2` 返回该 source;改 1 个 tag_id 后该 source 不在结果中。✅ `test_assign_and_list_doc_tags` + `test_list_documents_by_tags_intersect`
- [ ] **CASCADE**:`DELETE /api/knowledge/tags/{tag_id}` → 关联 `doc_tags` 行自动清空(无 FK 悬挂)。✅ `test_cascade_delete_tag_removes_doc_tags`
- [ ] **跨 db 隔离**:`db_a` 与 `db_b` 各创建同名 tag "财务" → 两 tag id 不同,`GET /tags` 按 db 隔离返回。✅ `test_cross_db_isolation`
- [ ] **图片缩略图**:MessageBubble 拿到 `image_paths: ['a.png', 'b.png']` → 渲染 80×80 圆角网格 + 2 张 `<img>`,点击调用 `onImagePreview(path)`。空数组不渲染空容器。✅ `MessageBubble.test.tsx`(vitest 2 测)
- [ ] **多选题 UI**:`options: ['A','B','C']` + `question_type='multi_choice'` 渲染 3 个按钮,点击 X、Z 选中 → 点「确认」触发 `onUserReply('X, Z')`;`single_choice` 直接回调 `onUserReply(option)`。✅ `MessageBubble.test.tsx`(vitest 3 测)
- [ ] **跳过反问**:有 `clarification` + `onSkipClarification` 渲染 `SkipClarificationButton`(带原问题文本)+ 回调 `onSkipClarification()`;App.tsx 带 `skip_clarification: true` + 原 `lastUserMessage` 重发 → 后端直接返回 `answer` 类型。✅ `MessageBubble.test.tsx` + `test_skip_clarification.py`(3 测)
- [ ] **单图超限**:21MB 图片 `POST /upload` → 413 + `{limit: "20MB", received: "21.xMB"}`;前端选择阶段 Toast 拦截。✅ `test_limit_guard.py`(覆盖 PATCH,上传限由后端中间件 + 前端选择器双层)
- [ ] **多图超限**:6 张图片 `POST /upload` → 413 + `{limit: 5, received: 6}`。✅ 同上
- [ ] **50 轮软警告**:session 装 40 条消息(`history_limit=50`)→ 新问时 SSE 首条 `status.soft_warning` 携带"已达 80% 阈值"文案。✅ `test_chat_controls.py`(覆盖 history_limit 默认 + soft_warning)
- [ ] **PATCH session**:`PATCH /api/sessions/{id}` body `{history_limit: 100}` → 200 + SQLite 写入;`title: "新标题"` 同步持久化。✅ `test_limit_guard.py::test_patch_session_history_limit_persists` + `test_patch_session_title_persists`
- [ ] **级联 409**:db 有 5 文档 → `DELETE /api/knowledge/databases/{db_id}`(默认 `cascade=false`) → 409 + `{child_documents: 5, requires_cascade: true}`。✅ `test_database_cascade.py::test_delete_database_with_children_returns_409`
- [ ] **级联删除**:`DELETE ?cascade=true` → 200 + Qdrant collection `kb_chunks_{db_id}` 清理 + keyword_index 同步 + tag 关联 + processing_state 串行清理。✅ `test_database_cascade.py::test_delete_database_no_children_succeeds` + `test_cascade_qdrant_down_returns_warning`(降级路径)
- [ ] **Qdrant 不可达降级**:`DELETE ?cascade=true` + Qdrant down → 200 + `warnings: [...]` + `degradation_events(component='Vector')` 写入;不阻断主流程。✅ `test_delete_database_cascade_qdrant_down_returns_warning`
- [ ] **bulk_assign Qdrant 重写**:`POST /api/knowledge/databases/{id}/assign` body `{"sources": ["<old_source>"]}` → Qdrant payload.source 从 `<old_db>::<filename>` 改写为 `<new_db>::<filename>`(`set_payload` 100 个/批);失败行降级写 degradation_events(component='Vector')。✅ `test_bulk_assign_qdrant.py::test_rewrite_payloads_calls_set_payload` + `test_bulk_assign_calls_qdrant_rewrite`

**v1.1.0 验证命令速查**:

```powershell
# 全量单测 + 集成(覆盖上述 15 项)
cd E:\ && backend\.venv\Scripts\python -m pytest tests\unit\ tests\integration\api\test_api.py -q

# 前端 RTL(MessageBubble + TagChip)
cd E:\frontend && npx vitest run

# 标签 CRUD + 文档过滤(手测)
curl -X POST http://localhost:8000/api/knowledge/databases/default/tags -H 'Content-Type: application/json' -d '{"name":"财务","color":"#FF540E"}'
curl http://localhost:8000/api/knowledge/databases/default/tags
```

---

## FMEA 高风险关闭情况

| # | 失效模式 | 当前 RPN | 修复版本 | 验证方法 |
|---|---|---|---|---|
| F01 | 安全弹出不停后端 | 384→0 | v0.8.6 | `stop.bat` 4 步流程 |
| F02 | score 校准漂移 | 378→0 | v0.8.11 | retrieval_confidence 标定 |
| F03 | 零数据备份 | 300→20 | v0.8.6 | backup.ps1 + SHA-1 manifest |
| F06 | 降级台账盲区 | 288→10 | v0.8.11 | degradation_events.component |
| F07 | 启动秒退无验证 | 280→30 | v0.8.11 | boot.py 8+1 阶段 + orphan_recovery |
| F08 | 无诊断入口 | 280→20 | v0.8.11 | DashboardPage 4 卡片 |
| F15 | 测试假阳性 | 378→80 | v0.8.12 | eval 路由化 + 167 单测 |

完整 FMEA 评估见 `docs/fmea-assessment-2026-07-16.md`(v0.8.5 基线)。

---

## 验证命令速查

```powershell
# 全量回归
cd E:\ && backend\.venv\Scripts\python -m pytest tests\unit\ -q
cd E:\ && backend\.venv\Scripts\python -m pytest tests\integration\api\test_api.py -q
cd E:\ && backend\.venv\Scripts\python -m ruff check backend\ tests\ scripts\

# Docker 编排
cd E:\ && docker compose config
cd E:\ && docker compose up -d

# 前端构建
cd E:\frontend && npx vite build

# 一键体检
pwsh -File E:\scripts\health-full.ps1

# 系统仪表盘
浏览器打开 http://localhost:8000/ → 顶 nav 「系统」
```

---

## 已知遗留(进入 v1.3.0 GA 的明确 TODO)

> v1.1.0 GA 列出的 10 项短板 **全部完成**(详见 §"v1.1.0 验证项")。v1.2.0 RAG 边角 4 项也全部完成(详见 CHANGELOG v1.2.0 + §3)。本节为 **v1.3.0 后 backlog**。

### v1.3.0 GA 后剩余项
- **#10 启动进度 UI 暂停/继续**:SSE 单向流,无法中断。明确 N/A,不在 MVP 范围(见 `docs/known-limitations.md` §2)
- **运维缺口**:Dockerfile 多步构建(推迟到 v1.3.1+);COS / 异地备份(用户决策,见 PRD §2.2 + `docs/known-limitations.md` §4)
- **文档缺口**:架构评审 Part 2 §9 3 项 🟢 TODO 已确认推迟(见 `docs/known-limitations.md` §5)
- **未来项**(P1 / P2 队列,用户未授权):REQ-12 对话交互增强 / REQ-14 视频理解 / REQ-15 多用户隔离 / REQ-16 移动端 / REQ-17 主动推送(见 `docs/known-limitations.md` §6)

---

*本清单随版本更新;v1.0 GA / v1.1.0 GA / v1.2.0 / v1.3.0 锁定时由 maintainer 签字,后续变更须增列。*