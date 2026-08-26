# KB-AI 项目 FMEA 评估报告

> **日期**:2026-07-16 · **版本**:v0.8.5 基线
> **方法**:系统 FMEA(失效模式与影响分析),S/O/D 10 分制,RPN = S × O × D
> **证据规则**:所有失效模式附 `文件:行号`(AGENTS.md §7.1);三条证据链经独立代码核查(后端 RAG 容错 / 数据完整性与弹出 / 启动与健康检测)。
> **评估范围**:运行系统(Docker 容器、FastAPI 后端、React 前端、PS 脚本、USB SSD 数据、外部 API)+ 过程能力(测试形态)。

---

## 1. 评分标准

| 分值 | S 严重度(影响) | O 发生度(频率) | D 探测度(越高越难发现) |
|---|---|---|---|
| 9–10 | 数据全丢且不可恢复 / 密钥泄露 | 每次操作必现 | 无任何探测手段,损失发生后才知道 |
| 7–8 | 核心功能(聊天/入库)整体丧失 | 高频(每周数次) | 静默失败,或用户发问/使用时才暴露 |
| 5–6 | 主要功能受损 / 部分数据丢失 / 误导性提示 | 中频(每月数次) | 有报错但无法定位,需人工排查 |
| 3–4 | 体验降级,有绕行方案 | 低频(偶发) | 报错可见但指引不足 |
| 1–2 | 轻微不便 | 罕见 | 立即可见且有明确指引 |

**风险分级**:🔴 RPN ≥ 200(立即处理)/ 🟡 100–199(计划改进)/ 🟢 < 100(监控或接受)。
注:RPN 是排序工具非绝对值;**已在线上复现的确证 bug 不论 RPN 一律列为必修**(见 §3 末"确证缺陷")。

---

## 2. 风险总览

- **失效模式总数:26**(系统 23 + 过程 3)
- 🔴 高 14 项 · 🟡 中 8 项 · 🟢 低 4 项
- **三大风险主题**:
  1. **数据单点**:零备份 + U 盘单份 + "安全弹出"实际不停后端 → 数据丢失风险是全项目最高类
  2. **探测体系系统性薄弱**:26 项中 13 项 D ≥ 8(无日志、降级台账盲区、健康检查只探 TCP、测试全 mock)——多数失效"发生了但没人知道"
  3. **容错策略不统一**:LLM 有 4 级重试,embedding/Qdrant/持久化却零保护,向量腿强制先执行使关键词检索冗余设计失效

---

## 3. FMEA 主表(按 RPN 降序)

| # | 失效模式 | 潜在影响 | 现行控制 | S | O | D | RPN | 证据 |
|---|---|---|---|---|---|---|---|---|
| F01 | **"安全弹出"不停 FastAPI 后端**:stop.bat 只 `docker compose stop`,从不调 stop-backend.ps1 | ① Windows 报"设备正在使用中"弹出失败 ② 用户收"可以安全拔出"提示后后端仍写 db.sqlite → 写途中拔盘 | 无(stop-backend.ps1 存在但无人调用) | 8 | 8 | 6 | **384** 🔴 | `stop.bat:28-46`;`scripts/safe-eject.ps1:243-251`;`backend/api/shutdown.py:16-21` |
| F02 | **reranker 缺席时 score 语义变化,websearch 触发阈值(0.6)对 RRF 分/logits 均未校准** | 每次提问误触发 websearch(白耗 quota + 最长 60s 延迟)或永不触发;降级链行为偏离设计 | retriever 侧有 RRF 防护但 chat 侧没有,两处策略矛盾 | 6 | 7 | 9 | **378** 🔴 | `backend/core/rag/reranker.py:103` vs `backend/api/chat.py:57-70,158`;`retriever.py:224-227` |
| F03 | **零数据备份**:db.sqlite 122MB / vectors 77MB / cache 66MB / uploads / parsed 仅 U 盘单份,全项目无任何备份/快照脚本 | U 盘丢失/损坏/拔坏 = 不可恢复的全量数据丢失 | 无;`vectors/.deleted/` 非备份;`raft_state.json` 单节点装饰 | 10 | 3 | 10 | **300** 🔴 | scripts/、backend/、docker-compose.yml 全文无 backup/snapshot;`docs/safe-eject.md:33` 还宣称存在"早期备份点"(误导) |
| F04 | **用户不走流程直接拔盘**(非技术用户高概率) | 丢最近数秒写入(WAL 保护不损坏);embedding-cache 留半行;极端情况文件系统损坏 | SQLite WAL + Qdrant WAL 5s flush;读端容错 | 7 | 6 | 8 | **336** 🔴 | `docker-compose.yml:53-54,204-205`;`embedder.py:158-169` 无 fsync |
| F05 | **阿里云 key 欠费/失效不可探测**:健康探测只验 TCP 443,HTTP 401 层面永远"在线" | 用户发问才失败;且 L0→L3 盲目重试最坏 ~244s 才报错 | L0→L1→L2→L3 fallback(仅抗瞬时故障);degradation_events | 8 | 4 | 9 | **288** 🔴 | `scripts/health-probe.ps1:64-76`;`backend/core/rag/llm.py:58,176-214` |
| F06 | **降级台账盲区**:embedding / Qdrant / reranker / query-rewrite / websearch 失败均不进 degradation_events,仅 logger.warning | 降级长期发生而无记录,远程支持无据可查;"检索质量缓慢劣化"不可见 | 台账只覆盖 LLM 与模型切换 | 4 | 8 | 9 | **288** 🔴 | `reranker.py:41,51,92`;`embedder.py` 全文无事件;`chat.py:96-105` websearch 静默 None |
| F07 | **后端启动秒退无验证、无日志**:Start-Process 只验"进程创建",不验存活;stdout/stderr 被丢弃 | 端口占用/import 错误时 start.bat 判成功,浏览器打开"无法访问此网站";崩溃后零日志可查 | start.bat 第 7 步等待但超时仅警告继续 | 7 | 5 | 8 | **280** 🔴 | `scripts/start-backend.ps1:93-97`;`start.bat:134-153`;`logs/` 下无后端日志 |
| F08 | **无一键诊断入口 + 无后端日志**:health-full.ps1 存在但只能命令行手敲;出问题靠用户口述截图 | 与"非技术用户"定位直接冲突;每次故障支持成本高 | /api/status 聚合三脚本;version.ps1 | 5 | 7 | 8 | **280** 🔴 | `scripts/health-full.ps1:254-261`;`QUICKSTART.md:144,163`;`backend/main.py` 无 logging 配置 |
| F09 | **乱码/脏数据静默入库**:GBK txt 以 errors="replace" 强读;未知扩展名(含 .doc)按纯文本读二进制;空文本生成零向量入 Qdrant | 知识库被污染,检索召回乱码;无任何告警 | 无校验、无告警 | 5 | 6 | 9 | **270** 🔴 | `backend/core/rag/mineru.py:87-88,185-188`;`embedder.py:239-241` |
| F10 | **磁盘告警对实际盘失效**:level-1 阈值 500GB > E: 盘物理容量 466GB;上传端点不查余量,写满残留半截文件 | 磁盘写满前无任何一级告警;SQLite/Qdrant/缓存写失败连锁 | disk-alert 5 级机制存在但阈值错配;只监不管 | 8 | 3 | 10 | **240** 🔴 | `scripts/disk-alert.ps1:71-77` vs 实测盘 466GB;`backend/api/knowledge.py:224-258` |
| F11 | **SQLite 写失败 → 已生成答案丢失**:save_message/touch_session 在 yield answer 之前且无 try;无 busy_timeout | LLM 已成功生成(已耗 quota)但 answer 事件发不出,前端"未收到回答";并发写撞 SQLITE_BUSY 直接崩流 | WAL(由 docker 侧开启);Python 侧零防护 | 8 | 4 | 7 | **224** 🔴 | `backend/api/chat.py:229-253`(对比 `llm.py:233-235` 有兜底);`backend/core/sqlite.py:21-27` |
| F12 | **embedding 缓存每次调用全量读 66MB+ jsonl;缓存写未保护** | 聊天延迟随缓存增长单调劣化(上限 200MB);盘满/拔出时 API 已成功仍整体报错 | LRU 200MB 淘汰 + 原子重写(仅 compact 路径);读端逐行容错 | 4 | 8 | 7 | **224** 🔴 | `embedder.py:51-86,234`(每次全量读),`:158-169`(append 无 try,对比 `mineru.py:199-200` best-effort) |
| F13 | **容器↔宿主机共享同一 db.sqlite 经 Docker bind-mount**:dify-api、dify-worker、宿主机 uvicorn 三方并发写,virtiofs 上 SQLite 锁/WAL shm 语义不被保证 | 比拔盘更隐蔽的库损坏路径;损坏即全丢(且无备份) | WAL + synchronous=NORMAL(防部分);无 integrity_check | 8 | 3 | 9 | **216** 🔴 | `docker-compose.yml:89,136`;`backend/core/config.py:90-92` |
| F14 | **占位符 .env 静默通过**:start.bat 只查文件存在性;boot.py 有检测但主流程不走 | 首次发问才"AI 调用失败",用户不知是没填 key | `Test-IsPlaceholder`(仅 boot SSE 路径) | 6 | 5 | 7 | **210** 🔴 | `start.bat:64-83`;`backend/api/boot.py:121-145`;`.env.example:11` |
| F15 | **测试假阳性(过程)**:tests/ 11 个 .ps1 全为 mock 静态断言(Test-Path/正则),[ALL PASS] 拦不住实现偏移 | 回归保护形同虚设,上表多个 bug(如 F16 前端解析 bug)可带着 PASS 上线 | 集成测试 3 组(smoke-chat/hybrid-search/test_api.py)覆盖薄 | 6 | 7 | 9 | **378** 🔴 | `tests/test_m3b.ps1:62-124`;AGENTS.md §6 |
| F16 | **Qdrant 或 Embedding API 任一不可用 → 聊天整体失败**:向量腿强制且先执行,本地 keyword_index 完全可用却不会被单独启用 | 断网/Qdrant 容器挂 = 核心功能全失;"混合检索"实际向量腿单点 | 空召回/低分重试(仅结果层面,不抗异常) | 9 | 4 | 4 | **144** 🟡 | `backend/core/rag/retriever.py:200-206`;`chat.py:140-147` |
| F17 | **reranker 瞬时加载失败 → 进程级终身禁用**;首启需联网下载 ~400MB | 离线首启后重排永久关闭(叠加 F02 放大);重启后端才恢复 | 加载失败退回原顺序,管线不断 | 4 | 5 | 8 | **160** 🟡 | `reranker.py:8-9,21,32-34` |
| F18 | **.env 明文随 U 盘丢失 → 阿里云 key + 全部业务资料泄露** | 财务损失(key 被盗刷)+ 经营数据泄露 | .gitignore 排除;Bearer 脱敏(不一致,见 F21) | 9 | 2 | 7 | **126** 🟡 | `E:/.env`;`docker-compose.yml:95,141`(docker inspect 可读) |
| F19 | **LLM 重试不区分错误类型**:HTTP 400/401/403 确定性失败也走完 4 级 + 2 次睡眠,多耗 3 次 quota | 单次提问最坏 ~244s;欠费时雪上加霜 | fallback 链本身;错误消息脱敏 | 5 | 6 | 4 | **120** 🟡 | `llm.py:78-82,176-214` |
| F20 | **部分入库不一致**:先 upsert Qdrant 后写 keyword_index,后者失败 → 文档可检索但列表不可见,无回滚无补偿 | 数据跨系统不一致,用户以为没传上而重复上传 | 任务状态可见阶段错误 | 5 | 3 | 7 | **105** 🟡 | `backend/api/knowledge.py:148-185,204-221` |
| F21 | **reembed 先删后写**:delete_by_source → upsert,upsert 失败 = 该文档向量全丢无回滚;删除文档跨系统无事务 | 单文档数据丢失;孤儿残留 | 无 | 8 | 2 | 6 | **96** 🟢 | `knowledge.py:275-291,366-375` |
| F22 | **脱敏不一致**:embedder/query_rewriter 抛错时错误体未脱敏(对比 llm.py 有 redact) | 若上游回显请求头,异常文本经 SSE 抵达前端泄 key | llm.py:80-82 已脱敏(单点) | 5 | 2 | 6 | **60** 🟢 | `embedder.py:194`;`query_rewriter.py:152` |
| F23 | **uvicorn 无守护**:进程崩溃 → 8000 整体失联,只能重跑 start.bat;Docker 侧容器有 unless-stopped,后端没有 | 可用性中断;非技术用户不会恢复 | 前端轮询 /health 可发现(但显示层有 bug,见 C1) | 7 | 4 | 3 | **84** 🟢 | `scripts/start-backend.ps1:93`;`docker-compose.yml:42,77,127` |
| F24 | **MinerU 挂 → PDF/PPTX 无 fallback**:pandoc/openpyxl 是按扩展名分派非失败降级;openpyxl 不在 requirements.txt,pandoc 依赖 PATH | 以扫描 PDF 为主的餐饮资料入库阻断 | 任务阶段化错误可见;解析缓存 | 7 | 4 | 3 | **84** 🟢 | `mineru.py:166-175,92-93`;`backend/requirements.txt:1-6` |
| F25 | **多轮历史加载失败静默失忆 / `_TASKS` 内存字典重启丢失 / websearch 双 key 未配静默跳过** | AI 突然"失忆"无感知;任务轮询 404;降级版回答无标注 | 管线不断 | 4 | 4 | 7 | **112** 🟡 | `chat.py:117-124`;`knowledge.py:59`;`chat.py:96-105` |
| F26 | **dist 缺失/过期无提示**:不挂载时 `/` 返回英文 404 JSON;无构建版本校验 | 换机/忘 build 时用户看到英文裸错误;部署机无 Node 工具链无法自助修复 | dist 当前新鲜(纯靠人工) | 6 | 3 | 5 | **90** 🟢 | `backend/main.py:56-59` |

### 确证缺陷(线上已复现,不论 RPN 一律必修)

| # | 缺陷 | 后果 | 证据 |
|---|---|---|---|
| C1 | **前端恒显示"离线"**:health_status.json endpoints 是布尔值,前端按 `e?.status==="online"` 对象解析 → 恒 false | 红色"网络连接断了"横幅常驻;Power 按钮恒"启动"→ **用户无法从 UI 关机**(叠加 F01 放大) | `frontend/src/App.tsx:64-70` vs `scripts/health-probe.ps1:92` + `data/health_status.json:5-9` 实样;dist 产物已含 bug |
| C2 | **start.bat 第 5 步探测 URL 恒无效**:`%DIFY_PORT:8080%` 是 bash 语法,cmd 不展开 | 每次冷启动白等 90s + 假警告;同时丧失对 Dify 真实故障的探测 | `start.bat:119-124`(cmd 实测原样输出不展开) |
| C3 | **小 bug 群**:`chat.py:120` `limit=payload.max_tokens or 50` 误把 max_tokens(2000) 当历史条数;`_maybe_websearch` 的 threshold 参数未使用 | 每次提问多拉历史(性能/内存);参数死代码 | `backend/api/chat.py:120,73` |

---

## 4. TOP 5 风险详析

### 🥇 F01 安全弹出承诺不兑现(RPN 384)
系统对用户最核心的承诺是"跑 stop.bat/点关机 → 可以安全拔盘"。实际链路:`/api/shutdown` → `safe-eject.ps1 -AutoYes` → `stop.bat` → `docker compose stop`,**全程无人停止宿主机 uvicorn**(`scripts/stop-backend.ps1` 存在但零调用方)。后果三连:弹出被 Windows 拒绝(venv 在 E: 盘)→ 提示"可以安全拔出"时后端仍持有 `data/db.sqlite` 句柄 → 前端页面不锁死可继续聊天写库(`App.tsx:270-278` 仅 alert)。**修复成本极低**(stop.bat 链一行调用 + 前端锁 UI),收益极高。

### 🥈 F02/F15 探测与触发逻辑失准(RPN 378 ×2)
两个 378 同分项本质同源:**探测系统设计值与实现值脱节**。F02:reranker 启用与否改变 `score` 字段语义(RRF ~0.02 / logits 可负),而 `_all_below_threshold(_, 0.6)` 用同一个魔法数裁决 → websearch 不是"按需触发"而是"看 reranker 心情"。F15:11 个 mock 测试的 PASS 同样给出虚假信心。两者都属"护栏本身失效"。

### 🥉 F03+F04+F13 数据单点族(RPN 300/336/216)
零备份 + 直接拔盘高概率 + bind-mount 共享 SQLite,三项叠加意味着:**"全量数据丢失"不是会不会发生,而是何时发生**。122MB SQLite + 77MB vectors + 66MB cache 总体积 <300MB,一次 7z 压缩备份成本几乎为零,是当前全项目**性价比最高的修复**。

### F05 密钥失效盲区(RPN 288)
TCP 探测给"在线"假信号,401 只在用户发问时暴露,再叠加 F19 的 244s 盲目重试。对应 TODO #9 未补的"月度账单/余额告警"。

### F07/F08 可观测性缺失(RPN 280 ×2)
后端零日志 + 启动零验证 + 无双击诊断入口。对非技术用户,任何故障都退化为"截图发我看看"。这是支持成本的主源头。

---

## 5. 系统性发现(跨失效模式)

1. **容错策略不统一**:LLM 4 级重试 vs embedding/Qdrant/SQLite 零重试;`llm.py:233-235` 事件持久化失败被吞是有意设计,`chat.py:229-253` 同类写库却未保护;`mineru.py:199-200` 缓存写 best-effort,`embedder.py:158-169` 却裸奔。建议确立统一容错基线(见 §6 P1-3)。
2. **探测度整体塌陷**:13/26 项 D ≥ 8。健康检查探 TCP 不探业务、降级事件覆盖 1/5 模块、后端无日志、测试全 mock——"失效不可见"是本项目最大的系统性风险,单项修复无法根治,需要一次"可观测性专项"。
3. **冗余设计未兑现**:keyword_index 存在却在向量腿失败时不启用(F16);stop-backend.ps1 存在却无人调用(F01);`health()` 预检函数存在却从不被检索/解析路径调用。多处"造了备胎但没装上车"。
4. **文档与实现漂移**:`docs/safe-eject.md:33` 宣称"回滚到早期备份点"(不存在备份)、`:63` 写 `down` 实际用 `stop`;QUICKSTART 的诊断指引不可达。文档给用户虚假安全感,建议与修复同步更新。

---

## 6. 建议措施(按优先级)

### P0 · 立即(本周,全部为低成本高收益)— ✅ 2026-07-16 v0.8.6 全部完成
| 措施 | 对应 | 状态 |
|---|---|---|
| C1 修前端健康解析:改用 `data.online` 布尔字段,恢复关机按钮 | C1 | ✅ `App.tsx:64-70` 已改,dist 已重建验证 |
| C2 修 start.bat:119 探测 URL(cmd 无 `:8080` 默认值语法) | C2 | ✅ `start.bat:109-111,122` 已改,cmd 实证通过 |
| F01 stop.bat 链 stop-backend.ps1 + shutdown 成功后前端锁 UI | F01/C1 | ✅ stop.bat 改 4 步(用户单项授权);前端整屏锁定 + ShutdownModal busy |
| F03 新增 `scripts/backup.ps1`:zip 备份 db.sqlite+vectors+uploads+cache 到盘外(电脑硬盘),stop.bat 尾部自动调用 | F03/F04/F13 | ✅ 新增并接入 stop.bat [4/4];实测 251.7MB→50.5MB/23s,轮换与内容校验通过 |
| F11 chat.py 持久化移出关键路径或包 try(对齐 llm.py:233-235 模式)+ sqlite.py 加 busy_timeout | F11 | ✅ `sqlite.py:25-28`、`keyword_index.py:49-52` busy_timeout=5000;`chat.py` 两处 try 兜底 |
| F10 disk-alert 阈值按实际盘容(466GB)重定标(300/350/400/430/≥430GB) | F10 | ✅ `disk-alert.ps1:71-79` 已重定标;同步更新 `tests/test_m3a.ps1` Test 2 断言 |

### P0 修复附带发现(2026-07-16)
| # | 缺陷 | 状态 |
|---|---|---|
| D1 | `disk-alert.ps1` v0.8.4 引入解析错误(switch 直接作 `-ForegroundColor` 参数,PS 5.1 无法解析)→ 脚本从未成功运行,`/api/status` 的 capacity 一直失败 | ✅ 已修(预计算变量),实测 PASS |
| D2 | `status-bar.ps1` 把 `health_status.json`(ConvertFrom-Json → PSCustomObject)传给 `[hashtable]` 参数 → Format-Credits 等 2 项 mock 测试失败(既有 bug,本次修复 disk-alert 解析错误后才暴露) | 🔲 未修,建议列入 P1 |
| D3 | 备份 zip 内容校验工具 `tmp/verify_backup_zip.ps1`(可复用) | ✅ 已留存 |

### P1 · 近期(两周内)
| 措施 | 对应 | 预估工作量 |
|---|---|---|
| F05 健康探测加"真实轻量 chat 调用"档(或至少区分 HTTP 401/余额不足);LLM 重试按错误分类(4xx 不重试) | F05/F19 | 4h(TODO #9 账单告警一并做) |
| F02 websearch 触发阈值与 score 语义对齐(归一化或按来源分阈值) | F02 | 3h |
| F16 向量腿异常时降级 keyword-only 检索 + 记 degradation_event | F16/F06 | 4h |
| F07 start-backend.ps1 加启动后存活探测 + 日志重定向到 logs/backend.log | F07/F08 | 2h |
| F06 degradation_events 补齐 embedding/Qdrant/reranker/websearch 五模块 + 设置页只读展示 | F06 | 6h |
| F08 health-full.ps1 加双击 .bat 入口 + "导出诊断包"(日志+status+json 打包) | F08 | 3h |
| F09 上传入口加扩展名白名单/大小/余量校验;GBK 探测(chardet 或 BOM/启发式);空文本拒入 | F09 | 4h |

### P2 · 计划(本月)
| 措施 | 对应 |
|---|---|
| F15 tests/ 关键断言接入真容器路径(扩 integration/ 覆盖);CI 或 pre-commit 跑 mock+单测 | F15(对应 TODO #11) |
| F13 评估 db.sqlite 拆分(Dify 库与后端库分离)消除三方共享;或迁移后端库到 backend 专属文件 | F13 |
| F04 start.bat 第 1 步加"上次是否干净退出"自检(-wal 文件存在即提示先跑检查) | F04 |
| F17 reranker 失败改为可重试(N 次/定时),模型文件随 package.bat 预置 | F17 |
| F12 embedding 缓存改 SQLite 或分片 jsonl,消除每次全量读 | F12 |
| F18 U 盘 BitLocker To Go 加密(需用户决策:换机兼容性) | F18(需用户拍板) |
| F20/F21 入库流水线加补偿/回滚(reembed 先 upsert 新版本后删旧;delete 顺序反转) | F20/F21 |
| F23 uvicorn 守护:start.bat 循环检测或 NSSM/计划任务 | F23 |
| 文档同步:safe-eject.md、QUICKSTART.md 与实现对齐 | §5.4 |

---

## 7. 与既有 TODO 的映射

| 本报告 | architecture-validation-report.md Part 2 §9 |
|---|---|
| F05(账单/key 失效探测) | TODO #9 未完成部分(月度账单告警) |
| F15(测试假阳性) | TODO #6(已部分推进,integration 仍薄)、#11(无 CI/linter,保留) |
| F08(诊断入口) | 新增,原 11 条未覆盖 |
| F03(零备份) | 新增,**建议作为 TODO #12 立项** |
| F01(弹出不停后端) | 新增,**建议作为 TODO #13 立项(P0)** |
| F10(告警阈值错配) | 新增(disk-alert 属 v0.8.4 新增功能,阈值沿用旧假设) |

---

## 8. 评估限制声明

- `.env` 真实内容未读(系统策略),key 相关结论基于配置链路静态分析。
- C1/C2 为静态分析 + 产物 grep + 实样文件三重证据,未起真服务复现;建议修复后各跑一次真启动验证。
- O/D 打分基于代码路径与典型使用场景推断,非历史故障统计(项目无故障台账,F06 修复后可积累)。
- 本报告未修改任何项目文件;所有"建议措施"需用户批准后另行实施。

---

*评估完成。建议下次重大修复批次后重跑本 FMEA,对比 RPN 变化。*
