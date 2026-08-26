# KB-AI v1.3 · 已知问题与限制(Known Limitations)

> **文档目的**:**透明地**记录当前 KB-AI v1.3.0 的已知限制,避免"事后落差"。
> **配套**:交付时的 `docs/acceptance-checklist.md` 标记 ✅ 项是承诺;**本文档标记 ⚠ / ❌ 项是当前不做的事**。
> **维护**:每发现新限制 → 加表;每解决一条 → 移到 CHANGELOG。
> **最新更新**:2026-07-22 · 配套版本 KB-AI **v1.5.1**(v1.5.1 容器化 patch 收官;镜像 14.2GB→2.89GB + /api/health 降级返回;pytest 306→320(+14))

## 1. PRD 已偏离项(用户决策接受,锁版)

| # | 偏离 | 实际 | PRD 原写 | 决策证据 | 解除条件 |
|---|---|---|---|---|---|
| 1 | REQ-9 部署形态 | U 盘本地单机 | 腾讯云 CVM + COS + 堡垒机 | `frontend-design-brief.md:0.4` + AGENTS.md §0 | 用户决策改回云部署时 |
| 2 | REQ-10 设计风格 | XAIAgent 暗黑赛博风 | 浅色商务风 + PingFang | AGENTS.md §12.1 决策矩阵锁版 | 用户决策改回浅色时 |
| 3 | REQ-13 自动备份 | `stop.bat` 触发本地 zip + 7 份轮转 | 每日 03:00 + COS + AES-256 + restore 演练 | `frontend-design-brief.md:0.4` | 用户愿意接受云成本与加密时 |
| 4 | Embedding 模型 | `text-embedding-v3` | 架构文档 `Qwen3-Embedding` | 实为同一模型 | N/A(仅命名差异) |

**说明**:这些是**用户主动决策**,不是 bug;PRD 文档待 v1.2 同步更新。

## 2. 已知功能短板(v1.1.0 全部修复)

✅ **#1 自由标签(独立于 Database)** — v1.1.0 修复,见 CHANGELOG PR #4。
原方案:`doc_tags(doc_id, tag)` 表 + sidebar 标签筛选(估 1d)
实现:`tags` + `doc_tags` 表(跨 db 同名允许)+ 7 路由 + TagChip / TagPicker / KnowledgePage 集成 + `boot.py` `schema_migration` 阶段

✅ **#2 图片缩略图引用** — v1.1.0 修复,见 CHANGELOG PR #3。
原方案:MessageBubble `image_paths` 加 `<img>` 缩略(估 0.3d)
实现:`GET /api/knowledge/image` 静态端点 + MessageBubble 在 `image_paths.length > 0` 时渲染 80×80 圆角网格,点击走 `PreviewModal`

✅ **#3 单图 20MB 校验** — v1.1.0 修复,见 CHANGELOG PR #2。
原方案:FastAPI File size check(估 0.2d)
实现:`/api/knowledge/upload` > 20MB → 413 + `{limit: "20MB", received}`;前端 UploadButton 选择阶段硬拒

✅ **#4 多图 ≤ 5 张/次限流** — v1.1.0 修复,见 CHANGELOG PR #2。
原方案:前端选择器限 5(估 0.1d)
实现:`/api/knowledge/upload` > 5 张 → 413 + `{limit: 5, received}`;前端 `multiple` 限制 + 选中数校验

✅ **#5 REQ-5 多选题 UI 渲染** — v1.1.0 修复,见 CHANGELOG PR #3。
原方案:MessageBubble 检测 `options` 数组 → 渲染单选/多选(估 0.5d)
实现:`MessageBubble` 接收 `options: string[]` + `question_type` + `onUserReply`;single_choice 直调,multi_choice 多选 + 「确认」按钮

✅ **#6 REQ-4 "按原问题回答" 跳过按钮** — v1.1.0 修复,见 CHANGELOG PR #3。
原方案:加 "直接回答" 按钮(估 0.2d)
实现:`clarification` 字段 + `lastUserMessage` 联合渲染 `SkipClarificationButton`(带原问题文本)+ 后端 `skip_clarification=true` 跳过反问分支

✅ **#7 历史会话标题 LLM 生成** — v1.1.0 修复,见 CHANGELOG PR #4。
原方案:排查 v0.8.4 streaming title 是否生效(估 0.5d)
实现:`generate_session_title_if_needed` 触发条件修复(≥ 3 消息 + 标题仍为 `DEFAULT_SESSION_TITLE` 才调 LLM)+ 5 条 `session_title_stream:` 结构化 debug 日志

✅ **#8 REQ-6 单会话 50 轮软上限** — v1.1.0 修复,见 CHANGELOG PR #2。
原方案:可配置 + 超限提示(估 0.3d)
实现:`sessions.history_limit` 列(默认 50,1-100 可配);SSE `status.soft_warning` 在 ≥ 80% 阈值时携带文案;`PATCH /api/sessions/{id}` 配置入口

✅ **#9 数据库删除时级联 Qdrant collection** — v1.1.0 修复,见 CHANGELOG PR #1。
原方案:文档化 + UI 提示(估 0.3d)
实现:默认 `cascade=false` → 子文档时 409 + `{child_documents: N, requires_cascade: true}`;前端解析 detail envelope 弹二次确认;`cascade=true` 串行清理 Qdrant / keyword_index / tag 关联 / processing_state;Qdrant 不可达 → degradation_events + 200 warnings

✅ **#11 `bulk_assign_documents_to_database` 不重写 Qdrant payload** — v1.1.0 修复,见 CHANGELOG PR #1。
原方案:文档化;v1.1 加 Qdrant payload rewrite 通道(估 0.5d)
实现:`backend/core/bulk_assign.py:_rewrite_qdrant_payloads` 按旧 `source` scroll + 100 个/批 `set_payload`;失败降级写 degradation_events(component='Vector')

❌ **#10 启动进度 UI 暂停/继续** — 明确 N/A(不在 MVP 范围;SSE 单向流,无中断通道)

**v1.1.0 修复小结**:v1.0 GA 列出的 11 项功能短板中 10 项关闭(#1-#9 + #11),仅 #10(N/A)保留。详见 CHANGELOG.md v1.1.0 PR #1-#4。

## 3. RAG 质量短板(v1.2.0 已治理)

✅ **#1 xlsx 表格召回弱** — v1.2 PR#2 修复。
原现象:Excel 切分粒度粗,行级数据丢失。
实现:`format_xlsx_sheet` 行级结构化(表头 + 第 N 行:列=值)+ `xlsx_row_group` 分块模式 + `sheet_name` / `row_start` / `row_end` / `columns` 元数据;旧文档需执行 `scripts/reparse-rag.ps1` 重建索引后生效。

✅ **#2 极短问题(< 4 字)召回噪声高** — v1.2 PR#3 修复。
原现象:keyword 召回过多无关 chunk。
实现:`_filter_short_keyword_hits` 门控 — is_short 时要求 phrase match 或 ≥2 token overlap;严格门控全空时 fallback 保留原结果(避免零召回)。
残留:2 字单 token 查询(如"会员""积分")因语义过于宽泛,排序仍可能不含最优文档;属 embedding 模型能力边界。

✅ **#3 长问题(> 200 字)首字时间显著上升** — v1.2 PR#4 修复。
原现象:embedder batch + reranker 长文本慢(~3-5s)。
实现:`_effective_rerank_top_n` 长问题 cap 到 5 + `compress_for_rerank` head+tail 512 字压缩送 reranker;embedding API 延迟为硬件/网络 bound,非代码可优化。
残留:embedding 单次调用 ~2-4s(阿里云百炼 API);总检索时间仍 3-6s,但 rerank 阶段耗时降低 ~60%。

✅ **#4 同文档跨年份混淆** — v1.2 PR#3 修复。
原现象:时间加权未对年份强加,"财务预算 2026"和"财务预算 2025"易混。
实现:`_apply_year_priority` — explicit_years 非空时,year_mentions 命中的 chunk 前置;全不命中时保留原序 + `year_match_miss` 诊断。
残留:旧文档需 reparse 后才有 `year_mentions` 元数据;未 reparse 前年份优先不生效。

**v1.2 评测**:黄金问答集 50 条(xlsx 9 / short 6 / long 10 / year 11 / 通用 14),pre-reparse baseline ≥90% 通过。全量 reparse 后启用 `expect_year` / `max_retrieval_ms` 字段可进一步提升覆盖率。

## 4. 已知运维短板(v1.3.0 收官)

| # | 短板 | 影响 | 拟方案 | 工作量 | 状态 |
|---|---|---|---|---|---|
| 1 | **本地 hooks**:改代码不自动跑 ruff/pytest | 改代码后忘记跑本地检查 | 安装 `scripts/install-hooks.ps1`(走 `core.hooksPath=scripts/hooks`) | 0.3d | ✅ v1.3.0 关闭(pre-commit 跑 ruff;pre-push 跑 `run-checks.ps1`) |
| 1b | **远程 CI**:PR 不自动跑全套测试 | 无 remote 自动门禁,仅靠本地 | 加 `.github/workflows/test.yml` | 0.3d | ❌ **明确推迟** — 项目无 git remote(`git remote -v` 空);推到 v1.3.1+ backlog,等上 GitHub 后再启用 |
| 2 | 无月度账单告警 | 阿里云 token 用超才发现 | `scripts/disk-alert.ps1` 扩为月度配额告警 | 0.3d | ✅ v1.3.0 关闭(`scripts/cost-alert.ps1` + `data/cost_log.jsonl` + `health_status.json.cost_alert` 字段 + Dashboard 第 5 张卡片 + chat.py level≥3 阻断分支) |
| 3 | Dockerfile 多步构建未优化 | 镜像 1.5GB(冷启动 5-10 min) | 多阶段构建 + layer cache | 1d | ✅ v1.4.0 关闭(`docker/dify-db-init/Dockerfile` 16 行多阶段样本,post-fix `c8f5b83` 增加 runtime `apk add` 共享库 + `docker-compose.yml` 切 build + `kb-ai/dify-db-init:local` 本地 tag;**范式化交付,非性能优化**,详见 `docs/docker-build.md §1.3` 边界声明) |
| 4 | QUICKSTART.md 部署边界章节缺失 | 运维误判 | 加 1 节"5.4 部署边界" | 0.2d | ✅ v1.3.0 关闭(QUICKSTART.md §9「系统边界与限制」,13 行硬边界表) |
| 5 | COS / 异地备份未实现 | 数据单点(U 盘物理损坏 = 全丢) | 与 REQ-13 偏离一并解除 | 用户决策 | ❌ **明确推迟** — 用户决策(已知局限性 PRD §2.2 已接受),保留 |

## 5. 已知文档缺口(v1.3.0 收官)

| # | 文档 | 缺口 | 状态 |
|---|---|---|---|
| 1 | PRD `custom-kb-qa-ai-prd-draft.md` | v0.7 三处偏离(REQ-9 / REQ-10 / REQ-13)+ v1.0/v1.1/v1.2/v1.3 各版本 PRD §5 历史对齐 | 🟡 **v1.0.1 部分同步** + v1.3.0 **项目外文件延期** |
| 2 | 架构评审 Part 2 §9 剩余 3 TODO(均为 🟢) | 已确认推迟,无需修 | ❌ **明确推迟** — 3 项 🟢 TODO 已确认推迟到 v1.3.1+ backlog |
| 3 | QUICKSTART.md 部署边界章节 | 待补 | ✅ v1.3.0 关闭(QUICKSTART.md §9,与 §4 #4 合并) |
| 4 | `dify/knowledge-pipeline.json` | 当前仅作导入备份,不再随 Dify Web UI 演进;v1.1 评估删除 | ✅ v1.3.0 关闭(保留 + 新增 `dify/README.md` 说明历史快照定位) |

## 6. 不在 v1.x GA 范围的未来项

来自 PRD P1 / P2 队列,**用户未授权,优先级低**:
- P1 REQ-12:对话交互增强(收藏 / 重命名 / 搜索)
- P2 REQ-14:视频理解(音视频转码成本高)
- P2 REQ-15:多用户 / 多分公司知识库隔离
- P2 REQ-16:移动端 / 小程序
- P2 REQ-17:主动推送(行业资讯、复盘提醒)

### v1.3.0 关闭后 backlog(2026-07-21 同步)

> known-limitations §4 #5 COS 异地备份 / §5 #2 架构评审 Part 2 §9 3 项 🟢 TODO,优先级待用户授权,候选 v1.4.0+。

### v1.3.0 release 期间 Whole-branch Review Important backlog(2026-07-21 同步)

> 5 项技术债,v1.3.0 release 不阻塞,候选 v1.3.1+。详见 CHANGELOG.md v1.3.0 release note + `docs/superpowers/specs/2026-07-21-v1.3-ops-hardening-design.md` §6 backlog。

| # | 短板 | 影响 | 拟方案 | 工作量 | 状态 |
|---|---|---|---|---|---|
| A | `cost-alert.ps1` 50 MB 日志轮转未实现 | 长期运行后日志无限增长,人工轮转会漏算历史成本 | 超阈值时 gzip 归档 `cost_log.jsonl.YYYY-MM.gz`;rollup 同时扫描当前 + 归档 | 0.5d | ✅ v1.3.1 关闭(`scripts/lib/CostLog-Rotate.ps1:Rotate-CostLog` + `cost-alert.ps1` dot-source 库) |
| B | UTC 月份用字符串前缀比较(`$entry.ts -like "$yearMonth*"`) | 跨时区来源(`2026-08-01T00:30:00-04:00`)会被错误归类 | `DateTimeOffset.Parse(...).ToUniversalTime()` 再比较 | 0.2d | ✅ v1.3.1 关闭(`Get-CanonicalUtcMonth` + `Get-MonthlyCostFromAllSources` 替代 -like 字符串比较) |
| C | malformed `usage` 会让 fallback 误触发 | API 返回 `usage: "invalid"` 时 `int(usage.get(...))` 抛 `AttributeError` → fallback 错把成功调用当失败 | 提取封装 safe helper:验证 mapping + DashScope/OpenAI 字段名 + 非负整数;失败返回 `None` | 0.3d | ✅ v1.3.1 关闭(`backend/core/cost_alert_guard.py:safe_get_usage_tokens` 替代裸 `int(...)`) |
| D | `_read_cost_alert()` 字段形状未验证 | `health_status.json` 损坏时(如 `level: "3"`、`thresholds: null`),chat.py `>= 3` / `thresholds.block` 会抛 `TypeError` 崩聊天入口 | 字段级 merge/validation:无效 level→0;无效金额→0;无效 thresholds→默认;sentinel 空字符串保留 | 0.3d | ✅ v1.3.1 关闭(`backend/core/cost_alert_guard.py:validate_cost_alert_payload` + `backend/api/dashboard.py:_read_cost_alert` 末尾调) |
| E | `cost-alert.ps1` 无自动测试覆盖 | Python 测试全绿不能证明 `health_status.json` 计算正确;pwsh 不在 PATH 时手测困难 | 加 Pester 测试,或 `-DataDir` 参数 + fixture 测试 harness | 1d | ❌ **明确推迟** — 为单一脚本建 Pester 框架 ROI 太低;v1.4.0+ 候选 |

---

## 附录:问题反馈模板

用户遇到问题时,复制以下内容填好后发给工程师:

```
[问题发生时间]: yyyy-mm-dd HH:MM
[操作步骤]: (例:对话页输入"...")
[期望结果]: (例:AI 引用文档 X)
[实际结果]: (例:AI 回答"不知道")
[顶 nav 状态]: 🟢/🟡/🔴
[Dashboard 24h 降级]: (从「系统」页截图)
[最近 health-full.ps1 输出]: (附件)
```

---

*本清单是 v1.3.0 的"诚实声明";新发现的限制会持续更新。*