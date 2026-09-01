# CHANGELOG · KB-AI

> 格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),版本号遵循语义化版本。
> **版本号单一真相源 = 根目录 `version` 文件**(`scripts/version.ps1` 与 `backend/main.py` 均读取它)。
> v0.7.0 之前的里程碑细节见 `docs/releases/RELEASE-M3.md` / `docs/releases/RELEASE-M3a.md` / `docs/releases/RELEASE-M3b.md`。

## [2.1.0] - 2026-08-28

> **v2.1.0 = Streaming & Hardening**:Agent 答案 token 级流式 + prompt injection 加固 + websearch 降级修复 + 评测报告公开化。

### 新增(Agent 答案 token 级流式,v2.0 最大体验缺口)

- `llm.py` 新增 `_post_chat_stream_with_tools()`:带 tools 的流式调用,tool_calls 走 OpenAI 分片协议按 index 聚合(arguments 分段拼接还原),归一化形状与 `_extract_tool_calls` 一致;content delta 原样透传
- `llm.py` 新增 `chat_with_fallback_tools_stream()`:L0→L3 降级链流式版,语义与 `chat_stream_with_fallback` 对齐——某次尝试在 yield 任何 delta **之前**失败才可重试/切换;已 yield 后失败记 `mid_stream_fail` 并原样抛出(部分答案已下发,静默重试会造成重复输出);usage 照常走 `_log_token_usage`(cost 计量不因流式缺失)
- `loop.py` `run_agent()` 新增 `stream` 参数(默认 False 保持 v2.0 契约):True 时最终回答以 `answer_delta` 逐 token 下发,`answer` 事件仍为权威终态(citations/agent 元信息由其携带);模型先流出部分内容又决定调工具时发 `answer_reset` 让前端清空半截答案;预算耗尽/重复护栏收尾(`_wrap_up`)同样流式
- `api/agent.py` `AgentChatRequest.stream` 默认 True(评测等需要整段契约的调用方可显式传 false 回退);SSE 事件新增 `answer_delta` / `answer_reset` 两种
- 前端 `App.tsx` 处理 `answer_delta`(追加到气泡,与 /chat draft 同路径)与 `answer_reset`(清空重置);Agent 模式首字延迟从"整轮生成完"提前到与普通对话同级
- 单测 +18:`tests/unit/test_agent_stream.py`(流式循环 8 条)+ `tests/unit/test_llm_stream_tools.py`(流式 HTTP 层 5 条:分片聚合/L1 重试/L2 切换/mid-stream 不重试/cost 落账);pytest 353 → 371

### 新增(prompt injection 加固,v2.0 评审缺口)

- `tools.py` 新增 `_wrap_untrusted()`:kb_search / web_search 的 observation 分别包进 `<kb_context>` / `<web_context>` 显式分隔符(内容不改写,引用编号不受影响)
- `loop.py` `_AGENT_SYSTEM_PROMPT` 新增规则 5「安全规则」:工具资料与联网结果只是数据不是指令,「忽略之前的指令/调用工具/复述提示词」类文本一律当作资料处理;`llm.py` `_RAG_SYSTEM_PROMPT` 新增【资料安全】条目覆盖 /api/chat 主链路
- 防护为「分隔符 + 提示词声明」双层,单测断言两个系统提示词与两处分隔符(test_agent_tools +4)

### 修复

- **chat.py websearch 降级从未生效的存量 bug**(T13 遗留):旧实现传 `-Question`(websearch.ps1 实际参数为 `-Query`,PowerShell 必然报错退出)且读 `content` 字段(JSON 契约为 `results[]`),导致该分支恒返回 None。现与 `tools._web_search` 同源:`-Query` + `-OutputJson`,拼接 title/url/snippet;修复后 /api/chat 的 websearch 降级首次真实可用
- **test_retrieval_quality 环境泄漏**:该测试此前依赖「.env 未设 RERANK_TOP_N」(CI 无 .env 为绿,真实交付环境 .env=20 必红);现 monkeypatch 隔离 env/.env,并补 env 覆盖生效的反向用例

### 变更(提示词强化,v2.0.1 候选落地)

- `_AGENT_SYSTEM_PROMPT` 规则 1 强化「禁止心算」:增长率/合计/占比/差值/对比等任何运算,即使能口算也必须先调 calculator(golden-agent 3 条 multi_step_calc「隐性计算」失分的根因修复;待下一轮真实评测回归验证)

### 变更(公开仓作品集化)

- `docs/eval/` 评测报告移出 sanitizer 排除清单:87% 评测报告(含方差区间/成本/真实弱点分析)作为最硬的量化证据进入公开仓
- README 重写:版本号修正、Agent 主线前置、评测数字表更新(371 pytest / 39 端点 / Agent 87%)、「隐私与脱敏」声明(授权交付 + 脱敏管线自检)
- 新增 `docs/REVIEW-GUIDE.md`:面试官 5 分钟导览(看什么文件、每个亮点对应的代码锚点)
- sanitizer 新增泛化规则:U 盘交付物流文案(「查看 logs/ 启动日志排查」等)→ 中性排查指引;golden-agent.jsonl 头注释改写为替换前后自洽表述(消除脱敏指纹)

## [2.0.0] - 2026-08-27

> **v2.0.0 = Agent Edition**:工具调用 Agent 全链路(4 工具注册表 + ReAct 循环 + 轨迹落库 + SSE 端点 + 前端步骤面板 + golden-agent 评测)。决策见 ADR-0002(自研 vs LangGraph)。公开仓同步本版本。



### 新增(MCP Server 暴露 kb_search,工单 T24 · stretch,2026-08-27)

- 新增 `mcp_server/`:官方 Python SDK(mcp 2.x,`MCPServer`)实现 —— `kb_search` 工具经 stdio transport 暴露给任意 MCP client(Claude Desktop/Cursor/自研 Agent);**薄 HTTP 代理设计**(内部调后端 `/api/debug/retrieval`,复用检索/降级/计量全链路,零 backend 代码依赖,仅 mcp SDK + 标准库);`KB_AI_BASE_URL` 环境变量可配;后端不可达/未命中均返回明确说明不抛错
- README 新增「作为 MCP Server 使用」节(注册配置示例 + 目录结构加 mcp_server/)
- 验收:stdio client 实测 `kb_search("示例海鲜酒楼会员卡等级有哪些")` 返回真实检索片段;ruff 全绿

### 新增(golden-agent 评测集 + 评测脚本,v2.0 PR#5 / 工单 T14,2026-08-27)

- 新增 `tests/eval/golden-agent.jsonl` 23 条(5 类,注释说明格式与判定):`kb_only` 8 / `calc_only` 3 / `time_only` 3 / `multi_step_calc` 5 / `web_fallback` 4;字段对齐设计稿 §8:`expect_tools`(子集判定:实际 ⊇ 期望)+ `expect_keywords`(answer 子串,空 = 只验非空)
- 新增 `tests/eval/run_agent_eval.py`:结构化入口 `run_evaluation(base_url, dataset_path, max_steps)` 对齐 `run_eval.py:139`(供 CLI 与未来 `/api/eval` 复用);`_post_agent_chat` 消费 `/api/agent/chat` SSE 六事件聚合 tools_used/answer/steps/tokens/elapsed;指标:工具选择准确率 / 任务完成率 / 平均步数 / p95 延迟 / 每任务 token 成本 + category_stats 分桶;CLI 退出码语义对齐 run_eval.py(0 全过 / 1 有失败或空集 / 2 后端不可达),`--json` 模式供 CI 消费
- 评测脚本 ruff 全绿;数据集 23 条 ≥ 15(降级线);**首轮真实评测完成(2026-08-27)**:示例知识库 12 文档经 chunker+tokenizer 纯 keyword 入库(Qdrant 未运行,检索走 keyword-only 降级实战验证);20/23(87%),工具选择准确率 0.87(区间 87-100%),任务完成率 0.87;3 条 multi_step_calc 隐性计算(增长/间隔/翻倍)模型心算未调 calculator —— 真实弱点,记 v2.0.1 强化提示词候选;LLM 采样方差显著(两次全量失败条不同);报告 `docs/eval/2026-08-27-golden-agent-report.md` + 结构化 JSON `docs/eval/2026-08-27-golden-agent-result.json`;总成本 ¥1-3

### 新增(web_search 工具化 + 前端 Agent 步骤面板,v2.0 PR#4 / 工单 T13,2026-08-27)

- `backend/core/agent/tools.py` 新增第 4 工具 **`web_search`**:复用 `scripts/websearch.ps1` 通道(Tavily → Bing),正确参数名 `-Query` + `-OutputJson`,timeout 30s(设计稿 §11 风险 #3);任何失败(脚本缺失/超时/非零退出/无结果)转 error observation 或 `ok:false`,绝不抛断循环;ctx 用「第 N 条」措辞而非 `[N]`,避免与 kb_search 的 citations 角标体系混淆;`execute_tool` 增加 keyword-only `kb_offset` 透传
- **发现 #1 修复(citation 跨调用编号错位)**:`format_chunks_only` 新增可选参数 `start_index`(默认 1,零回归);`_kb_search` 按 `kb_offset`(已聚合 citation 数)续编全局角标,回填模型的 observation 与聚合 citations 同号 —— 多轮检索后模型 `[N]` 引用与前端脚注不再错位;`loop.py` 聚合处由「二次平移」简化为直接 extend(observation 已全局编号)
- 前端:**`types.ts`** 加 `AgentStep`/`AgentMeta`/`AgentChatRequest`/`AgentRunSummary` 类型 + `Message.agentSteps/agentMeta`;**`api.ts`** 加 `postAgentChat`(返回 Response 供手动 SSE 解析)与 `fetchAgentRuns`;**新增** `components/AgentStepsPanel.tsx`(可折叠面板:工具名/参数摘要/耗时/成功·失败·运行中色点/结果摘要,≤3 条默认展开,budget_exhausted 黄色提示条);`MessageBubble` 集成面板(气泡顶部);`App.tsx` Agent 模式开关(localStorage 持久化,默认关走旧 `/api/chat`,打开走 `/api/agent/chat`)+ SSE 六事件消费(step_start/tool_call/tool_result 实时累积步骤,answer 落 citations/agentMeta);`SettingsPage` 新增「对话模式」卡片 + toggle 开关;`global.css` 增补面板与开关样式(暗黑赛博:绿/红/熔岩橙)
- 新增 `frontend/src/__tests__/AgentStepsPanel.test.tsx` 5 测(卡片渲染含参数/耗时、失败态、budget_exhausted 提示条、折叠交互、空步骤不渲染)
- 存量修复:`tests/unit/test_agent_tools.py` 原「web_search 为未知工具」断言改为不存在工具名;补 web_search 8 测(成功通道参数断言/缺 query/脚本缺失/超时/非零退出/空结果/永不抛)+ kb offset 2 测;`test_agent_loop.py` citation 连续编号测试适配新契约(断言 loop 传 kb_offset + observation 全局编号)
- 环境回归修复(ruff 0.16.4 升级):新增根 `ruff.toml` 把既有 lint 策略(select E/F/W)显式化到全仓,消除无配置目录落入新版默认规则集的存量噪音;存量 `tests/integration/` 4 处 W292/F401(文件尾换行/未使用 import)顺手修复,规则选择未变更
- pytest 344 → 353(+9);vitest 13 → 18(+5);eslint 0 errors(31 warnings 均存量);vite build 通过;run-checks 4/4 全绿

### 新增(Agent 轨迹落库 + /api/agent/* 端点,v2.0 PR#3 / 工单 T12,2026-08-26)

- 新增 `backend/core/sqlite/agent_repo.py`(第 6 个 repo,注册进 `_REPOS`,`init_db` core/migrate 自动覆盖):`agent_runs` + `agent_steps` 两表(设计稿 §5 契约)+ `idx_agent_steps_run` 索引;`init_schema`/`migrate` 幂等;CRUD:`create_run` / `finish_run`(status/steps_count/tools_used JSON/model/total_in/total_out/finished_at)/ `get_run` / `list_runs`(倒序 limit 钳位 1–100)/ `add_step`(截断规则在 repo 层强制:tool_args ≤1000、observation ≤2000)/ `get_run_steps`
- 新增 `backend/core/agent/trajectory.py` 三门面函数 `start_run` / `record_step` / `finish_run`:全部吞错不阻断主链(对齐 llm.py 吞错哲学);finish_reason→status 映射(completed/no_action→done,budget_exhausted/repeat_guard→budget_exhausted,error→error);已接线进 `run_agent()`(run 开始建行、tool_call/tool_result/answer 逐步落行、终态收尾;失败静默跳过)
- `backend/api/agent.py` 三端点:**POST `/api/agent/chat`**(SSE:status(agent_start)/step_start/tool_call/tool_result/answer/error;cost-alert level≥3 阻断复用 chat.py:136-171 模式含降级事件记录;answer 事件带 `agent:{run_id,steps,tools_used,total_in,total_out}` 嵌套契约;max_steps pydantic ge=1 le=16 越界 422)+ **GET `/api/agent/runs`** + **GET `/api/agent/runs/{id}`**(404 语义);`main.py` 注册路由
- 新增 `tests/unit/test_agent_repo.py` 6 测(幂等/往返/finish 更新/截断规则/排序/limit)+ `tests/unit/test_agent_api.py` 7 测(max_steps 边界 1/16 过、0/17 → 422、SSE 序列契约、cost-alert 阻断不触 run_agent、runs 列表、明细含 steps 与 404)
- pytest 331 → 344(+13);ruff(backend/ruff.toml 配置)全绿

### 新增(Agent 循环 + LLM tools 扩展,v2.0 PR#2 / 工单 T11,2026-08-26)

- `backend/core/rag/llm.py` 最小侵入扩展:HTTP 层抽为 `_send_chat_request`(tools/tool_choice 非空时写入请求体;`_post_chat` 契约与返回不变);新增 `_extract_tool_calls`(tool_calls 归一化,T09:arguments 为 JSON 字符串由调用方二次解析)+ `_post_chat_with_tools()`(返回 content/tool_calls/usage/finish_reason,`finish_reason="tool_calls"` 时 content 为空串不按文本解析)+ `chat_with_fallback_tools()`(复刻 L0→L3 降级链与降级事件,usage 照常走 `_log_token_usage`;返回 `(content, tool_calls, model_used, model_reason, usage)`);既有函数签名与 `chat_stream_with_fallback` 未动
- 新增 `backend/core/agent/loop.py`:`run_agent()` ReAct 生成器 —— max_steps 默认 8(env `AGENT_MAX_STEPS` 覆盖,钳位 1–16);observation 截断 2000 字符以 `role="tool"`+`tool_call_id` 回填;相同 (name,args) 连续 2 次 → repeat_guard 强制收尾;预算耗尽 → 无 tools 再调一次收尾回答(`budget_exhausted=true`);模型无 tool_calls 且无 content → 记 `agent_no_action` 降级事件;kb_search citations 跨步连续编号聚合;yield 事件:step_start / tool_call / tool_result / answer / error
- 新增 `tests/unit/test_agent_loop.py` 12 测(全 mock LLM 不触网):单步直答、两步工具链(assistant tool_calls 回传 + 观测回填)、预算耗尽收尾、重复调用强制收尾、工具异常续跑、arguments 解析失败回退、no_action 降级、env 覆盖与钳位、usage 累计、citations 连续编号、history 截断、LLM 全链失败 error 事件
- 存量修复:`tests/unit/test_health_degraded.py` / `tests/unit/test_ps_runner_skipped.py` 文件尾补换行(ruff W292,ruff 0.16 门禁报错阻断 run-checks)
- pytest 319 → 331(+12);ruff(backend/ruff.toml 配置)全绿

### 新增(Agent 工具注册表,v2.0 PR#1 / 工单 T10,2026-08-26)

- 新增 `backend/core/agent/` 包(`__init__.py` + `tools.py`):OpenAI function calling 工具注册表 `TOOLS`(kb_search / calculator / get_current_time 三个只读工具,schema description 中文写明「何时该用/不该用」,通用知识库措辞无行业身份)+ 分发器 `execute_tool(name, args)`(永不抛异常,失败一律转 `{"error": ...}` observation 供循环续跑;args 兼容 dict 与 DashScope `tool_calls` 的 JSON 字符串形态)
- `kb_search`:包 `retriever.retrieve()`(top_k 钳位 1–20)+ `format_chunks_only()`;空结果返回 `note` 提示而非 error
- `calculator`:`ast.parse(mode="eval")` 节点白名单求值 —— 仅允许数字 Constant / 四则·幂·取余 BinOp / 正负号 UnaryOp;拒绝名称、调用、属性、字符串常量、无穷大常量;表达式 ≤200 字符;Pow 指数上限 1000 防资源耗尽;除零/溢出转 error observation
- `get_current_time`:本地 ISO 时间 + 星期 + 日期
- 新增 `tests/unit/test_agent_tools.py` 15 测:schema 结构合法性、执行器齐全性、calculator 白名单(拒 `__import__` 注入/属性访问/字符串常量/超长/除零)、时间格式、kb_search mock retriever 包装与失败降级
- pytest 304 → 319(+15);ruff 全绿

### 变更(公开版脱敏准备,T01)

- `backend/core/rag/llm.py:410` few-shot 示例中的真实业务名 → 虚构名「示例海鲜酒楼」(2026-08-25 用户决策);纯示例文本,无行为变更;tests 中无该字符串断言(已全仓 grep 确认)
- 新增私有脱敏工具 `tmp/sanitize/sanitize_public.py`(`tmp/` 已 gitignore,不进仓):基于 `git ls-files`(含 `--others --exclude-standard`)精确文件清单 + 有序替换规则 + 目标树全量自检(内容 + 文件名),一键生成公开版目录树;显式排除已跟踪的 `客户必读.md` 与二进制打印件;重跑时保留目标树 `.git`(2026-08-26)

### 变更(公开版 README 重写,T03)

- `README.md` 全文重写为公开版简历导向结构:一句话定位 + mermaid 架构图(5 容器)+ 实测工程指标表(300 pytest / 13 vitest / 50 golden-QA / 36 API 端点 / 双平台)+ 设计决策摘要(便携/低依赖/降级/评测驱动/成本工程);指标数字均来自 2026-08-26 本机 grep/wc 实测;许可改为 MIT(LICENSE 文件待 T02 随公开仓一并补齐)

## [1.7.0] - 2026-07-28

### macOS 全链路支持(minor · 新平台 · maintainer 自用换机驱动)

> 目标:maintainer 个人从 Windows 换到 MacBook Air(M1/M2 + macOS 13+),要求 KB-AI 在 Mac 上以**与 Windows 等价的体验**运行(双击启动 / 双击停止 / 自动备份 / 弹"可以拔出"),**不破坏现有 Win 客户机入口**。
> 策略:**单源 PowerShell 编排 + 平台薄壳**——start.ps1/stop.ps1/precheck.ps1 在 Win/Mac 跑同一份逻辑,平台差异由 `scripts/lib/platform-utils.ps1` 统一处理;`.bat` 一行不动,Win 客户机零回归。
> 边界:**不动** `.env` / `package.bat` / `architecture-validation-report.md` Part 1 / `docker-compose.yml` 镜像 tag / 现有 `.bat` 入口。

### 新增

- **Item 1 · `scripts/lib/platform-utils.ps1` 新建**(跨平台工具,11 函数,~250 行):
  - **平台检测** `Get-KBAIPlatform`:PS 5.1 兼容,走 `$env:OS` + `uname -s`(不用 `$IsMacOS` 等 PS 6+ 自动变量,违反 AGENTS.md §3.1 红线)
  - **venv 路径三件套** `Get-KBAIPythonVenvPath/Pip/Uvicorn`:Win→`.venv/Scripts/*.exe`,Mac→`.venv/bin/*`
  - **系统交互** `Open-KBAIUrl`(Win `Start-Process` / Mac `open`)+ `Show-KBAINotice`(Win WinForms / Mac osascript heredoc + stdin,中文/换行/单引号安全)
  - **硬件探测** `Get-KBAICpuVirtualization / Get-KBAIOSVersion / Get-KBAIDiskFreeGB / Get-KBAIMemoryGB`:全平台等价
  - **平台专属** `Test-KBAISIPStatus`:macOS SIP 状态(预检用)
- **Item 2 · `precheck.ps1` 新建**(5 项客户机预检,Win/Mac 等价):
  - 5 项:CPU 虚拟化 / OS 版本 / 磁盘空间 / 内存 / 平台专属(Win S Mode / Mac SIP+Docker 检查)
  - 沿用 `start.bat` 阶段 0 的 precheck.bat 行为,exit 0/1 语义对齐
- **Item 3 · `start.ps1` 新建**(8 阶段启动编排,start.bat 完整 PowerShell 翻译):
  - 8 阶段:预检 / U 盘根 / Docker Desktop / .env 自检 / 加载镜像 / HF 模型 / docker compose up / 健康等待 / 打开浏览器
  - 平台差异:Mac `open -a Docker`,Win `Docker Desktop.exe`;Mac 路径用 `~/.cache/huggingface`,Win 用 `%USERPROFILE%\.cache\huggingface`
- **Item 4 · `stop.ps1` 新建**(5 步停止编排,stop.bat 完整 PowerShell 翻译):
  - 5 步:停后端 → 停 MinerU(Win `Get-CimInstance Win32_Process` / Mac `pkill -f mineru_server.py`)→ 停容器 → fsync 5s → 自动备份 → 弹"现在可以拔出"
- **Item 5 · `start.command` / `stop.command` 新建**(macOS 双击入口):
  - bash 8 行,`exec pwsh -NoProfile -File start.ps1 "$@"`(Mac Finder 双击自动开 Terminal)
- **Item 6 · `package.ps1` / `package.sh` 新建**(跨平台打包):
  - `Compress-Archive` 跨平台(PS 5.1+ / pwsh 7+ 都内置),`package.sh` 薄壳调 `package.ps1`
  - `package.bat` **保留**,Win 客户机零影响

### 修改

- **Item 7 · `scripts/start-backend.ps1`**:行 38/39/85 的 venv 路径走 `Get-KBAIPythonVenvPath/Pip/Uvicorn`(3 个硬编码 → 1 个 dot-source + 3 个函数调用)
- **Item 8 · `scripts/run-checks.ps1`**:行 33 venv 路径同上
- **Item 9 · `scripts/hooks/pre-commit`**(bash):加 `elif [ -x "backend/.venv/bin/ruff" ]` Mac/Linux 分支
- **Item 10 · `scripts/safe-eject.ps1`**:Windows Forms `MessageBox::Show` → `Show-KBAINotice`(平台分支)
- **Item 11 · `scripts/lib/Write-Log.ps1`**:加 `[AllowEmptyString()]` 修 `Write-LogHost ""` 空串 bug(precheck.ps1 用)
- **Item 12 · `docs/QUICKSTART.md`**:新增 §10 macOS 部署节(brew install + exFAT 格式化 + Gatekeeper + 故障排查 + 文件系统选型 + Win/Mac 体验差异表)
- **Item 13 · `AGENTS.md`** §1 文件地图 + §13 变更记录:v1.7.0 条目

### 关键设计修正(plan §十)

| 修正项 | 修正前(v1.7.0 草稿) | 修正后 |
|---|---|---|
| 平台检测 | `if (... -and $IsMacOS)` 违反 PS 5.1 兼容 | `Get-KBAIPlatform` 函数 + `uname -s` |
| 全局状态 | `$script:KBAIPlatform` 变量(dot-source 作用域污染) | 改函数,每次调用重新检测 |
| macOS 通知 | `osascript -e "..."` 中文/换行 escape 噩梦 | `osascript -l AppleScript` + stdin heredoc |
| precheck 5 项 | 自称 5 项,实际只具体写了 2 项 | 5 项全部实现:CPU/OS/磁盘/内存/平台专属 |
| 工作量 | 估 2.5 天 | 重估 4.0 天(+60%) |

### 验证结果

- **pytest 398 → 422(+24 新测)**:
  - `tests/integration/test_mac_platform_support.py`:**12 测**(静态合规 + Windows 端 PS 烟雾)
  - `tests/integration/test_start_ps1_platform.py`:**11 测**(8 阶段结构 + dot-source + 平台调用)
  - `tests/integration/test_safe_eject_platform.py`:**5 测**(MessageBox 替换 + 解析检查)
- **vitest 13(不回归)**
- **ruff / tsc / vite build** 全绿
- **Windows 端烟雾测试**:
  - `precheck.ps1` 5 项检查全跑通(识别虚拟化未启用 + Win S Mode 正常)
  - `start.ps1 -SkipPrecheck -SkipBrowser` 走到阶段 2 Docker 检查,正确检测 daemon 未运行
  - `safe-eject.ps1` / `package.ps1` 通过 PS parser 静态检查
- **已知 4 个预存在失败测** 与本 PR 无关(已在阶段 1 验证:`test_chat_sse` / `test_chat_complex_routes_to_max` / `test_retrieval_quality × 2`)

### 用户手动验收项(交付给 maintainer 自己)

v1.7.0 装到 MacBook Air 后需做的 4 件事:

1. **Apple Silicon 镜像验证**:`docker manifest inspect langgenius/dify-api:1.0.0` 看 `linux/arm64` 是否存在
2. **Docker buildx 实测**:`docker buildx build --platform linux/arm64 .` 跑过(防 libicu 等架构问题)
3. **virtiofs 并发实测**:dify-api + dify-worker 写 data/db.sqlite 30 分钟无 lock 错误
4. **Gatekeeper 首次放行**:右键 `start.command` → 打开 → 始终允许

详见 `docs/QUICKSTART.md` §10 + `docs/known-limitations.md` v1.7.0 backlog。

### 留待 v1.7.1+(已知 backlog)

- 把 `start.bat` / `stop.bat` 也改成调 `.ps1` 薄壳(单源化)
- `platform-utils.ps1` 升级为 `.psm1` module + Pester 测
- `start.ps1 + stop.ps1 + precheck.ps1 + package.ps1` 合并为 `kb-ai-cli.ps1` 命令式
- 引入 GitHub Actions `macos-latest` runner(目前 KB-AI 单机交付,验证用)

---

## [1.6.0] - 2026-07-22

### logs-summary.ps1 诊断汇总工具(minor · 新功能 · 观测矩阵"消费侧")

> 目标:v1.5.2 ~ v1.5.7 已落地 8 个观测入口的日志,但缺"能读"工具 —— 用户/maintainer 想看"最近 24h 发生过什么"时必须手动 `cat` 8 个文件。v1.6.0 新增 `scripts/logs-summary.ps1`,一屏聚合:总文件数 / 8 入口活跃度 / 错误按来源分桶 / 最近 5 条 error+warn / JSON 模式给 CI 消费。
> 边界:**只读消费侧**,不修改任何日志文件,不修改现有入口脚本;不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端。

### 变更

- **Item 1 · `scripts/logs-summary.ps1` 新建**(纯消费工具,~280 行):
  - 参数:`-LogDir`(默认 `E:\logs\`)、`-SinceStr`(支持 `24h` / `7d` / 绝对时间,空 = 全部)、`-Json`
  - 4 个核心函数:`Resolve-SinceToDateTime` / `Get-LogFiles` / `Test-WithinWindow` / `Aggregate-EntryPoint` + `Render-Report` / `Render-Json`
  - 退出码:0 = 无 error;1 = 有 error 但能输出;2 = 致命(目录不存在)
  - **只读**:`Get-Content -Raw` 读日志,**不** Add-Content / Set-Content / Move-Item / Remove-Item(`test_logs_summary_does_not_modify_log_files` 守护)

### 实施期 hotfix(🔴 关键)

- **`-Since` → `-SinceStr` 参数改名**:原 `-Since`(顶层)+ 函数内部 `[DateTime]$Since` 形参在 PowerShell 5.1 下触发 `ParameterArgumentTransformationError`(空字符串 `""` 误尝试转 `System.DateTime`)。PowerShell 5.1 解析器在解析嵌套形参时,误把顶层 `$Since` 类型推断为 `DateTime`。**解决**:顶层参数改名 `$SinceStr`,函数内仍可用 `$Since`(无冲突)。`test_logs_summary_accepts_required_params` 守护改名不漂移

### 验证结果

- `tests/integration/test_logs_summary.py` **12/12** 过(部分实跑):
  - **5 结构测**:`test_logs_summary_script_exists` / `test_logs_summary_uses_powerscriptroot_or_basedir` / `test_logs_summary_exposes_main_functions`(4 函数)/ `test_logs_summary_accepts_required_params`(`-SinceStr` 改名守护)/ `test_logs_summary_recognizes_all_8_entry_points`(8 个前缀白名单)
  - **4 子场景实跑测**:`test_logs_summary_handles_missing_log_dir`(子进程 powershell 调用)/ `test_logs_summary_extracts_errors_and_warns`(mock 日志 + JSON 解析)/ `test_logs_summary_supports_json_mode`(JSON 合法)/ `test_logs_summary_default_since_is_all`(空目录)
  - **3 防回归**:`test_logs_summary_exit_code_logic`(0/1/2 三种退出码)/ `test_logs_summary_ps_5_1_compatible`(无 `??` 等 PS 6+ 特性)/ `test_logs_summary_does_not_modify_log_files`(无 Add/Set-Content / Move/Remove-Item)
- 既有 pytest 370 + v1.6.0 +12 = **382** 全过
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**
- **6 个锁版红线全部未动**

### 连带更新

- `scripts/logs-summary.ps1`(新建,~280 行)
- `tests/integration/test_logs_summary.py`(新建,12 测)
- `version` 1.5.7 → **1.6.0**
- `README.md` 顶部版本行 `(v1.5.7)` → `(v1.6.0)`
- `AGENTS.md §13` 追加 v1.6.0 节点
- `客户必读.md` 故障指引加 logs-summary 命令
- `docs/superpowers/specs/2026-07-22-v1.6.0-logs-summary-design.md`(新建)

### 单测总数

- **基线 v1.5.7 release** = pytest 370 / vitest 13
- **v1.6.0 增量**:`tests/integration/test_logs_summary.py` 新建(**+12 测**)
- **release HEAD 总数**:**pytest 382 / vitest 13** / ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.6.0 不动 backend)
- **前端影响**:**零**

### 不在 v1.6.0 范围(明确推迟)

- ❌ Dashboard `/api/logs/recent` 端点(留待 v1.6.1+,需前端 card)
- ❌ docker events 自动 dump(留待 v1.6.1+)
- ❌ HTML 报告输出(留待 v1.6.1+)
- ❌ 自动聚合错误触发 push 通知(留待 v1.6.1+,需用户授权推送渠道)
- ❌ PRD REQ-12(收藏 / 搜索 / 重命名)— **需用户授权**

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.6.0-logs-summary-design.md`

---

## [1.5.7] - 2026-07-22

### version.ps1 日志化 · 收尾 8/8 观测矩阵(patch bump,工程性 + 观测性补漏)

> 目标:把 `scripts\version.ps1` 改用 v1.5.4 共享日志助手,**观测矩阵 8/8 完整完成**(start.bat / stop.bat / health-full.ps1 / cost-alert.ps1 / health-probe.ps1 / disk-alert.ps1 / backup.ps1 / version.ps1)。从 v1.5.2 起步,经过 6 个 patch 收官。
> 边界:不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端;**完全复用 v1.5.4 `scripts/lib/Write-Log.ps1`**。

### 变更

- **Item 1 · `scripts/version.ps1` 改造**:`. (Join-Path $PSScriptRoot 'lib/Write-Log.ps1')` dot-source(**在 disk-alert.ps1 dot-source 之后**,line ~70)+ `Initialize-LogFile -ScriptName "version"` + 3 处 `Write-Host` → `Write-LogHost`(banner 上下空行 + 1 行状态输出)+ 2 处 `Close-LogFile`(JSON 路径 line ~242 + 正常路径 line ~258)

### 不动(明确守护)

- **`-Json` 模式不被日志污染**:`$payload | ConvertTo-Json` 是 pipeline 表达式(line ~241),不被 Write-LogHost 拦截(`test_version_keeps_json_mode` 守护)
- **`get-usb-root.ps1` dot-source 不丢**:line 59 `Get-UsbRoot` 仍可用(`test_version_keeps_get_usb_root_dotsource` 守护)
- **`disk-alert.ps1` dot-source 不丢**:line 68 `Get-KBAIDiskUsage` 仍可用(`test_version_keeps_disk_alert_dotsource` 守护)
- **v1.5.5 `disk-alert.ps1` 的 `$isMain` 早退路径**:version.ps1 dot-source disk-alert 时走早退,不会触发 disk-alert 的 Initialize-LogFile,不会污染调用方

### 验证结果

- `tests/integration/test_ps_scripts_logging.py` **38/38** 过(结构性 pytest,无 powershell 实跑依赖):
  - **v1.5.4 14 测**(既有):5 lib + 4 health-full + 5 cost-alert
  - **v1.5.5 11 测**(既有):4 health-probe + 4 disk-alert + 3 防回归
  - **v1.5.6 6 测**(既有):4 backup + 1 Quiet 语义 + 1 同盘守卫
  - **v1.5.7 +7 测**:
    - 4 version 测(`test_version_dotsources_log_lib` / `test_version_initializes_log_file` / `test_version_calls_close_logfile` ≥ 2 / `test_version_min_write_loghost_count` ≥ 3)
    - 3 防回归(`test_version_keeps_json_mode` / `test_version_keeps_disk_alert_dotsource` / `test_version_keeps_get_usb_root_dotsource`)
- **既有 v1.5.2 test_start_bat_logging.py 9/9 仍过** + **v1.5.3 test_stop_bat_logging.py 12/12 仍过**
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**
- **6 个锁版红线全部未动**

### 连带更新

- `scripts/version.ps1`(258 → ~270 行,+12)
- `tests/integration/test_ps_scripts_logging.py`(扩展 +7 测,共 38)
- `version` 1.5.6 → **1.5.7**
- `README.md` 顶部版本行 `(v1.5.6)` → `(v1.5.7)`
- `AGENTS.md §13` 追加 v1.5.7 节点
- `客户必读.md` 故障指引加 `E:\logs\version-*.log`
- `docs/superpowers/specs/2026-07-22-v1.5.7-version-ps-logging-design.md`(新建)

### 单测总数

- **基线 v1.5.6 release** = pytest 363 / vitest 13
- **v1.5.7 增量**:`tests/integration/test_ps_scripts_logging.py` 扩展(**+7 测**:4 version + 3 防回归)
- **release HEAD 总数**:**pytest 370 / vitest 13** / ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.5.7 不动 backend)
- **前端影响**:**零**

### 🎯 观测矩阵完成清单

| # | 入口 | 日志 | 版本 |
|---|---|---|---|
| 1 | `start.bat` | ✅ `E:\logs\start-*.log` | v1.5.2 |
| 2 | `stop.bat` | ✅ `E:\logs\stop-*.log` | v1.5.3 |
| 3 | `scripts\health-full.ps1` | ✅ `E:\logs\health-full-*.log` | v1.5.4 |
| 4 | `scripts\cost-alert.ps1` | ✅ `E:\logs\cost-alert-*.log` | v1.5.4 |
| 5 | `scripts\health-probe.ps1` | ✅ `E:\logs\health-probe-*.log` | v1.5.5 |
| 6 | `scripts\disk-alert.ps1` | ✅ `E:\logs\disk-alert-*.log` | v1.5.5 |
| 7 | `scripts\backup.ps1` | ✅ `E:\logs\backup-*.log` | v1.5.6 |
| 8 | `scripts\version.ps1` | ✅ `E:\logs\version-*.log` | **v1.5.7** |

**8/8 完整完成**,从 v1.5.2 起步经过 6 个 patch(本会话连续推进 v1.5.2 → v1.5.7)。KB-AI 达到"长期可无人值守运行"等级。

### 不在 v1.5.7 范围(明确推迟)

- ❌ docker events 自动 dump 到 U 盘(留待 v1.6.0+)
- ❌ PRD REQ-12(收藏 / 搜索 / 重命名)— **需用户授权**
- ❌ Pester test for cost-alert.ps1(ROI 低,留待 v1.6.0+)
- ❌ 移动端响应式 UI(PRD REQ-16)— **需用户授权**
- ❌ 主动推送(PRD REQ-17)— **需用户授权**
- ❌ 真实跑 version.ps1 端到端测试

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.7-version-ps-logging-design.md`

---

## [1.5.6] - 2026-07-22

### backup.ps1 日志化(patch bump,观测性补漏 · 7/8 完成)

> 目标:把 `scripts\backup.ps1` 改用 v1.5.4 共享日志助手,**观测矩阵 7/8 完成**(剩 version.ps1 留待 v1.5.7+)。关键语义改动:`-Quiet` 模式下 console 静默但 log 文件仍写,便于 stop.bat 自动调用取证。
> 边界:不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端;**完全复用 v1.5.4 `scripts/lib/Write-Log.ps1`**。

### 变更

- **Item 1 · `scripts/backup.ps1` 改造**:`. (Join-Path $PSScriptRoot 'lib/Write-Log.ps1')` dot-source + `Initialize-LogFile -ScriptName "backup"` + Write-Ok / Write-Warn 函数体 `Write-Host` → `Write-LogHost` + 6 处直接 `Write-Host` → `Write-LogHost`(replace_all)+ 5 处 `Close-LogFile`(路径解析 / 无数据 / 空间不足 / 成功 / catch)
- **Item 2 · 🔑 `Write-Step` 函数体重构**:拆分为两个分支 — `if (-not $Quiet) { Write-LogHost }`(console + log)+ `elseif ($Script:LogFile) { Add-Content }`(仅 log)。**stop.bat 调用 backup.ps1 带 -Quiet,console 完全静默;但 log 文件仍写,事后取证不丢**

### 不动(明确守护)

- **`load-env.ps1` dot-source 不丢**:backup.ps1 line 62 仍 dot-source `lib/load-env.ps1`,v1.5.6 在它之后追加 `lib/Write-Log.ps1`(`test_backup_dotsources_log_lib` 守护)
- **同盘守卫逻辑不丢**:`$rootDrive -eq $destDrive` + 回退默认目录 + Write-Warn 三件套保留(`test_backup_same_disk_guard_preserved` 守护)
- **try/catch/finally 5 处 exit 路径**:每条都加 Close-LogFile(行 110/178/195/269/273),Write-LogHost 失败也能取证
- **Compress-Archive / Move-Item / SHA1 manifest 业务逻辑**:不动,仅替换 console 输出与加 Close-LogFile

### 验证结果

- `tests/integration/test_ps_scripts_logging.py` **31/31** 过(结构性 pytest,无 powershell 实跑依赖):
  - **v1.5.4 14 测**(既有):5 lib + 4 health-full + 5 cost-alert
  - **v1.5.5 11 测**(既有):4 health-probe + 4 disk-alert + 3 防回归
  - **v1.5.6 +6 测**:
    - `test_backup_dotsources_log_lib` / `test_backup_initializes_log_file` / `test_backup_calls_close_logfile_before_each_exit`(每个 exit 前 1-3 行必有 Close-LogFile,含 catch 路径)/ `test_backup_min_write_loghost_count`(≥ 6)
    - `test_backup_quiet_mode_keeps_log_writes`(🔑:Write-Step 函数体含 `elif ($Script:LogFile)` 分支)
    - `test_backup_same_disk_guard_preserved`(防回归:`$rootDrive -eq $destDrive` + Write-Warn 都在)
- **既有 v1.5.2 test_start_bat_logging.py 9/9 仍过** + **v1.5.3 test_stop_bat_logging.py 12/12 仍过**
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**
- **6 个锁版红线全部未动**

### 连带更新

- `scripts/backup.ps1`(257 → ~278 行,+21)
- `tests/integration/test_ps_scripts_logging.py`(扩展 +6 测,共 31)
- `version` 1.5.5 → **1.5.6**
- `README.md` 顶部版本行 `(v1.5.5)` → `(v1.5.6)`
- `AGENTS.md §13` 追加 v1.5.6 节点
- `客户必读.md` 故障指引加 `E:\logs\backup-*.log`
- `docs/superpowers/specs/2026-07-22-v1.5.6-backup-bat-logging-design.md`(新建)

### 不在 v1.5.6 范围(明确推迟)

- ❌ `scripts\version.ps1` 日志化(留待 v1.5.7+,低频次)
- ❌ backup 加密 / COS 异地(用户决策锁版)
- ❌ backup progress bar / ETA 估算
- ❌ 真实跑 backup.ps1 端到端测试

### 单测总数

- **基线 v1.5.5 release** = pytest 357 / vitest 13
- **v1.5.6 增量**:`tests/integration/test_ps_scripts_logging.py` 扩展(**+6 测**:4 backup + 1 Quiet 语义 + 1 同盘守卫防回归)
- **release HEAD 总数**:**pytest 363 / vitest 13** / ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.5.6 不动 backend)
- **前端影响**:**零**

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.6-backup-bat-logging-design.md`

---

## [1.5.5] - 2026-07-22

### PS 脚本日志统一化 · 批次 2(patch bump,观测性补漏 · 6/8 完成)

> 目标:延续 v1.5.4 模式,把 `scripts\health-probe.ps1` 与 `scripts\disk-alert.ps1` 改用 v1.5.4 共享日志助手,**观测矩阵 6/8 完成**(剩 backup.ps1 + version.ps1 留待 v1.5.6+ / v1.6.0+)。
> 边界:不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端;**完全复用 v1.5.4 `scripts/lib/Write-Log.ps1` 助手**(不新建)。

### 变更

- **Item 1 · `scripts/health-probe.ps1` 改造**:`. (Join-Path $PSScriptRoot 'lib/Write-Log.ps1')` dot-source + `Initialize-LogFile -ScriptName "health-probe"` + Write-Step / Write-Warn 函数体内 `Write-Host` → `Write-LogHost` + 6 处直接 `Write-Host` → `Write-LogHost`(replace_all) + `Close-LogFile` before `exit 0`;`-OutputJson` 模式 `$json` pipeline 表达式保持
- **Item 2 · `scripts/disk-alert.ps1` 改造**:`. (Join-Path $PSScriptRoot 'lib/Write-Log.ps1')` dot-source + `Initialize-LogFile -ScriptName "disk-alert"` + Write-Step / Write-Warn 函数体内替换 + 15 处直接 `Write-Host` → `Write-LogHost`(replace_all)+ 4 处 `Close-LogFile`(OutputJson + 3 个 level exit 各 1 次)
- **Item 3 · 🔴 关键:`Initialize-LogFile` 放在 `$isMain` 检查之后**:`disk-alert.ps1` 被 health-full.ps1 用 dot-source 加载 `Get-KBAIDiskUsage` 函数;若 Initialize-LogFile 写在 `$isMain` 检查之前,会污染调用方路径(health-full 一启动就写 `E:\logs\disk-alert-*.log`,语义错位);`test_disk_alert_initializes_after_ismain_check` 守护

### 不动(明确守护)

- **`data/disk-alerts.log` 追加逻辑不丢**:line 240 `Add-Content -Path $logFile -Value $logLine -Encoding UTF8` 保持原样(`test_disk_alert_keeps_disk_alerts_log_writes` 守护);新加的 `disk-alert-*.log`(E:\logs\)是脚本执行日志,与历史告警日志**功能正交**
- **`Get-KBAIDiskUsage` / `Get-KBAISqliteSize` 函数签名不变**:`test_disk_alert_does_not_break_dotsource_path` 守护
- **`-OutputJson` 模式不被日志污染**:`$json` pipeline 表达式不经过 Write-LogHost(`test_health_probe_keeps_outputjson_mode` 守护)
- **`disk-alerts.log` / `disk-alert-*.log` 共存不冲突**:前者是历史告警状态(line 238 CSV),后者是脚本运行 console 镜像

### 验证结果

- `tests/integration/test_ps_scripts_logging.py` **25/25** 过(结构性 pytest,无 powershell 实跑依赖):
  - **v1.5.4 14 测**(既有):5 lib + 4 health-full + 5 cost-alert
  - **v1.5.5 +11 测**:
    - 4 health-probe 测(`test_health_probe_dotsources_log_lib` / `test_health_probe_initializes_log_file` / `test_health_probe_calls_close_logfile` + close < exit 顺序 / `test_health_probe_min_write_loghost_count` ≥ 6)
    - 4 disk-alert 测(`test_disk_alert_dotsources_log_lib` / `test_disk_alert_initializes_after_ismain_check` 🔴 / `test_disk_alert_calls_close_logfile` ≥ 4 / `test_disk_alert_min_write_loghost_count` ≥ 8)
    - 3 防回归测(`test_disk_alert_does_not_break_dotsource_path` / `test_disk_alert_keeps_disk_alerts_log_writes` / `test_health_probe_keeps_outputjson_mode`)
- **既有 v1.5.2 test_start_bat_logging.py 9/9 仍过** + **既有 v1.5.3 test_stop_bat_logging.py 12/12 仍过**
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**
- **6 个锁版红线全部未动**

### 连带更新

- `scripts/health-probe.ps1`(144 → ~155 行,+11)
- `scripts/disk-alert.ps1`(281 → ~295 行,+14)
- `tests/integration/test_ps_scripts_logging.py`(扩展 +11 测,共 25)
- `version` 1.5.4 → **1.5.5**
- `README.md` 顶部版本行 `(v1.5.4)` → `(v1.5.5)`
- `AGENTS.md §13` 追加 v1.5.5 节点
- `客户必读.md` 故障指引加 `E:\logs\health-probe-*.log` + `E:\logs\disk-alert-*.log`
- `docs/superpowers/specs/2026-07-22-v1.5.5-ps-scripts-logging-batch2-design.md`(新建)

### 不在 v1.5.5 范围(明确推迟)

- ❌ `scripts\backup.ps1` 日志化(留待 v1.5.6+)
- ❌ `scripts\version.ps1` 日志化(留待 v1.6.0+,低频次)
- ❌ health-probe `-Loop` 模式(本脚本不轮询)
- ❌ disk-alert 5 级阈值动态化
- ❌ 真实跑 health-probe / disk-alert 的端到端测试

### 单测总数

- **基线 v1.5.4 release** = pytest 346 / vitest 13
- **v1.5.5 增量**:`tests/integration/test_ps_scripts_logging.py` 扩展(**+11 测**:4 health-probe + 4 disk-alert + 3 防回归)
- **release HEAD 总数**:**pytest 357 / vitest 13** / ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.5.5 不动 backend)
- **前端影响**:**零**

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.5-ps-scripts-logging-batch2-design.md`

---

## [1.5.4] - 2026-07-22

### PS 脚本日志统一化(patch bump,观测性补漏 · 完成 start/stop/health/cost-alert 矩阵)

> 目标:把 `scripts\health-full.ps1` 与 `scripts\cost-alert.ps1` 每次运行的 console 输出镜像写到 `E:\logs\<script>-YYYYMMDD-HHMMSS.log`,与 v1.5.2 start.bat / v1.5.3 stop.bat 日志配对,**完成 start/stop/health/cost-alert 四个观测性矩阵闭环**。
> 边界:不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端。

### 变更

- **Item 1 · 共享助手 `scripts/lib/Write-Log.ps1`(新建,~115 行)**:
  - `Initialize-LogFile -ScriptName "..."`:初始化日志文件到 `E:\logs\<script>-YYYYMMDD-HHMMSS.log`(`(Get-Date).ToString("yyyyMMdd-HHmmss")`)+ 保留最近 20 个(`Sort-Object LastWriteTime -Descending` + `Select-Object -Skip 20` + `Remove-Item`)
  - `Write-LogHost -Message "..." [-ForegroundColor White] [-NoNewline]`:Write-Host + 追加到 `$Script:LogFile`;失败 `try/catch` 静默兜底
  - `Close-LogFile`:写 `=== <name> 退出 (exit=N) ===` 退出摘要
  - 失败兜底:`$Script:LogFile = $null` + `Write-LogHost` 退化纯 `Write-Host`,U 盘只读不阻断
- **Item 2 · `scripts/health-full.ps1` 改造**:`. (Join-Path $scriptRoot 'lib/Write-Log.ps1')` dot-source + `Initialize-LogFile -ScriptName "health-full"` + 32 处 `Write-Host` → `Write-LogHost`(replace_all,含 `-NoNewline` 透传)+ `Close-LogFile` 在 `exit $payload.exitCode` 前;`-Json` 模式不动(纯 stdout JSON for CI)
- **Item 3 · `scripts/cost-alert.ps1` 改造**:同 Item 2;`Initialize-LogFile -ScriptName "cost-alert"` + 10 处 `Write-LogHost` + 2 处 `Close-LogFile`(DryRun 路径 + 正常结束路径);**v1.3.1 CostLog-Rotate dot-source 不动**
- **Item 4 · 退出收尾**:两脚本均通过 `Close-LogFile` 写退出 banner,日志检索时一眼看到边界

### 不动(明确守护)

- **`-Json` 模式不被日志污染**:`Render-Panel` 内 `if ($Json) { $Payload | ConvertTo-Json; return }` 路径用 pipeline 写 stdout,不被 `Write-LogHost` 拦截
- **`-Loop` 模式**:`while($true)` 循环不重复初始化,只在 finally 退出后 Close-LogFile 写一次
- **v1.3.1 CostLog-Rotate dot-source 不丢**:`cost-alert.ps1` 仍 dot-source `lib/CostLog-Rotate.ps1`(test_does_not_drop_costlog_rotate_dotsource 守护)
- **`Clear-Host` / 纯 UI 调用**:全部 `Write-Host` 替换为 `Write-LogHost`,日志完整 mirror console

### 验证结果

- `tests/integration/test_ps_scripts_logging.py` **14/14** 过(结构性 pytest,无 powershell 实跑依赖):
  - **5 个共享助手测**:`test_lib_exists` / `test_lib_exposes_three_functions` / `test_lib_uses_powerscriptroot_or_scriptsroot` / `test_lib_retention_skips_oldest_20` / `test_lib_failure_graceful`
  - **4 个 health-full.ps1 测**:`test_health_full_dotsources_log_lib` / `test_health_full_initializes_log_file` / `test_health_full_calls_close_logfile`(close < exit 顺序)/ `test_health_full_min_write_loghost_count`(≥ 12)
  - **5 个 cost-alert.ps1 测**:`test_cost_alert_dotsources_log_lib` / `test_cost_alert_initializes_log_file` / `test_cost_alert_calls_close_logfile`(≥ 2,DryRun + 正常)/ `test_cost_alert_min_write_loghost_count`(≥ 8)/ `test_cost_alert_does_not_drop_costlog_rotate_dotsource`(守护 v1.3.1)
- **既有 v1.5.2 test_start_bat_logging.py 9/9 仍过** + **既有 v1.5.3 test_stop_bat_logging.py 12/12 仍过**(守护 start.bat / stop.bat baseline)
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**(qdrant:1.7.0 / dify-api:1.0.0 × 2 / kb-ai/dify-db-init:local / kb-ai/backend:local)
- **6 个锁版红线全部未动**(.env / package.bat / start.bat / stop.bat / architecture-validation-report.md Part 1 / 容器镜像 tag)

### 连带更新

- `scripts/lib/Write-Log.ps1`(新建,115 行)
- `tests/integration/test_ps_scripts_logging.py`(新建,14 测)
- `version` 1.5.3 → **1.5.4**
- `README.md` 顶部版本行 `(v1.5.3)` → `(v1.5.4)`
- `AGENTS.md §13` 追加 v1.5.4 节点
- `客户必读.md` 故障指引加 `E:\logs\health-full-*.log`
- `docs/superpowers/specs/2026-07-22-v1.5.4-ps-scripts-logging-design.md`(新建,含 §1-§8 + 附录 A-C 观测矩阵完成清单)

### 不在 v1.5.4 范围(明确推迟)

- ❌ 其它 PS 脚本也加日志(disk-alert / health-probe / backup / version / status-bar — 留待 v1.5.5+)
- ❌ Start-Transcript 替代方案
- ❌ 集中式 logs/ 子目录按日期分层(`logs/2026-07-22/health-full-*.log`)— 留待 v1.6.0+
- ❌ 真实跑 health-full.ps1 / cost-alert.ps1 的端到端测试(本版本纯静态 + docker 依赖)
- ❌ 上传日志到云端 / 邮件

### 单测总数

- **基线 v1.5.3 release** = pytest 332 / vitest 13
- **v1.5.4 增量**:`tests/integration/test_ps_scripts_logging.py` 新建(**+14 测**:5 lib + 4 health-full + 5 cost-alert)
- **release HEAD 总数**:**pytest 346 / vitest 13** / ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.5.4 不动 backend)
- **前端影响**:**零**

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.4-ps-scripts-logging-design.md`

---

## [1.5.3] - 2026-07-22

### 停止日志落地(patch bump,观测性补漏 · 配 v1.5.2 完整闭环)

> 目标:把 stop.bat 每次运行的 console 输出镜像写到 `E:\logs\stop-YYYYMMDD-HHMMSS.log`,与 v1.5.2 start.bat 日志配对,补齐"备份失败 / docker stop 卡住 / 拔盘前 fsync 没完成"的取证闭环。v1.5.2 CHANGELOG 明确标注「stop.bat 同步日志留待 v1.5.3+」,本版本收口。
> 边界:不动 `.env` / `package.bat` / `start.bat` / `docker-compose.yml` 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端。

### 变更

- **Item 1 · stop.bat 日志初始化**:行 13 后新增 19 行 block,生成 `E:\logs\stop-YYYYMMDD-HHMMSS.log`;时间戳复用 v1.5.2 方案(wmic 优先 + date/time 兜底 + `LOG_TIMESTAMP: =0` 处理小时位空格)
- **Item 2 · 保留策略**:每次启动前清理旧的,保留最近 20 个 stop-*.log(`dir /b /o-d` + `skip=20` + `del`)
- **Item 3 · echo 镜像**:27 处 echo 行尾加 `>> "%LOG_FILE%"`(banner / 4 step 标题 / warning / 5 秒倒计时 / 7 行拔出提示)
- **Item 4 · ASCII 圆括号清理**:4 处 step 标题 ASCII `()` → `·` separator(v1.5.2 C.3 hotfix 复刻) — `(kb-ai-backend)` / `(:8001)` / `(给 10 秒优雅退出)` / `(scripts\backup.ps1)`
- **Item 5 · 退出收尾**:endlocal 之前一行 `=== KB-AI stop.bat 退出 (errorlevel=N) ... ===`
- **Item 6 · 失败兜底**:U 盘只读 / 写不动 → 单行 `[警告]`,不阻断停止流程

### 不动(明确守护)

- **真 powershell 调用不加 `>>` 重定向**:`powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\backup.ps1"` 与 `Get-CimInstance Win32_Process ... Stop-Process`(MinerU kill)— 加 `>>` 会污染 PS 进程的 stdin,导致 backup.ps1 收不到参数或 MinerU kill 字符串匹配失败(`test_no_regression_on_powershell_calls` 守护)
- **for 块内 echo 加 `>>` 验证**:`for /L %%i in (5,-1,1) do (echo ...)` 的 echo 已加 `>>`,v1.5.2 隐含已证 CMD `for` 块不解析 echo 内括号(`test_no_regression_on_for_loop_echo` 守护)
- **goto label 不丢**:`:backup_step` / `:safe_eject` + `goto backup_step`(`test_no_regression_on_goto_labels` 守护)

### 验证结果

- `tests/integration/test_stop_bat_logging.py` **12/12** 过(结构性 pytest,无 docker 依赖):
  - 4 个 Item 1 测(`test_log_dir_points_to_logs` / `test_log_file_name_pattern` / `test_initial_banner_written` / `test_log_failure_graceful`)
  - 1 个 Item 2 测(`test_retention_trims_to_20`,含 `stop-*.log` 通配符断言)
  - 2 个 Item 3 测(`test_echo_lines_redirect_to_log` ≥ 80% 守门 + `test_no_regression_on_powershell_calls` 防 backup.ps1 / MinerU kill 误加 `>>`)
  - 1 个 Item 4 测(`test_no_ascii_parens_in_step_header_echo`,4 个白名单字符串)
  - 2 个 Item 5 测(`test_exit_summary_written` + `test_no_regression_on_logic_keywords` 8 关键字)
  - 2 个回归守护测(`test_no_regression_on_for_loop_echo` + `test_no_regression_on_goto_labels`)
- **既有 v1.5.2 `test_start_bat_logging.py` 9/9 仍过**(守护 start.bat baseline)
- ruff / tsc / vite build 全绿
- **5 个锁版镜像 tag 全部未动**(qdrant:1.7.0 / dify-api:1.0.0 × 2 / kb-ai/dify-db-init:local / kb-ai/backend:local)
- **5 个锁版红线全部未动**(.env / package.bat / start.bat / architecture-validation-report.md Part 1 / 容器镜像 tag)

### 连带更新

- `docs/superpowers/specs/2026-07-22-v1.5.3-stop-bat-logging-design.md`(新建,含 §1-§8 + 附录 A-C · hotfix 预判 + 附录 C 运维盲区清单)
- `tests/integration/test_stop_bat_logging.py`(新建,10 测)
- `version` 1.5.2 → **1.5.3**
- `README.md` 顶部版本行 `(v1.5.2)` → `(v1.5.3)`
- `AGENTS.md §13` 追加 v1.5.3 节点
- `客户必读.md` 故障指引加 `E:\logs\stop-*.log`

### 不在 v1.5.3 范围(明确推迟)

- ❌ health-full.ps1 / cost-alert.ps1 日志落地(留待 v1.5.4+)
- ❌ docker compose stop 输出捕获到 stop-*.log(v1.5.2 start.bat 同样不捕获,保持一致)
- ❌ 真实跑 docker 的端到端测试(本版本纯静态)
- ❌ 把 stop.bat 改成 PS 脚本(动态日志 UI + 颜色)
- ❌ 上传日志到云端 / 邮件
- ❌ 自动 dump docker events / Windows event viewer

### 单测总数

- **基线 v1.5.2 release** = pytest 320 / vitest 13
- **v1.5.3 增量**:`tests/integration/test_stop_bat_logging.py` 新建(**+12 测**:4 Item1 + 1 Item2 + 2 Item3 + 1 Item4 + 2 Item5 + 2 回归守护)
- **release HEAD 总数**:**pytest 332 / vitest 13**(已验证全过)/ ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(无变化;v1.5.3 不动 backend)
- **前端影响**:**零**

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.3-stop-bat-logging-design.md`

---

## [1.5.2] - 2026-07-22

### 启动日志落地(patch bump,工程性 + 观测性补漏)

> 目标:补齐 start.bat 零日志留存的盲区。2026-07-22 同事电脑(全新 WIN11)双击 start.bat 闪退,无法事后取证;v1.5.2 起,start.bat 每次运行都会在 `E:\logs\start-YYYYMMDD-HHMMSS.log` 留痕。
> 边界:不动 `.env` / `package.bat` / `stop.bat`(留待下版) / 锁版镜像 tag / 业务代码 / FastAPI 契约 / 前端。

### 变更

- **Item 1 · start.bat 日志初始化**:第 27-45 行新增 19 行 block,生成 `E:\logs\start-YYYYMMDD-HHMMSS.log`;时间戳 6 个 date/time 子串;`%LOG_TIMESTAMP: =0%` 处理小时位空格
- **Item 2 · 保留策略**:每次启动前清理旧的,保留最近 20 个 start-*.log(`dir /b /o-d` + `skip=20` + `del`)
- **Item 3 · echo 镜像**:每个 `echo` 加 `>> "%LOG_FILE%"` 后缀(~50 处替换,不动 `%TEMP%` 显式重定向)
- **Item 4 · 退出收尾**:endlocal 之前一行 `=== KB-AI start.bat 退出 (errorlevel=N) ... ===`
- **Item 5 · 失败兜底**:U 盘只读 / 写不动 → 单行 `[警告]`,不阻断启动

### 验证结果

- `tests/integration/test_start_bat_logging.py` **10/10** 过(结构性 pytest,无 docker 依赖;包含 1 个新测守护 IF 块内 echo 不能用 ASCII 圆括号的回归)
- **同事电脑实跑达标**:日志文件 `E:\logs\start-20260722-235754.log` 共 49 行,完整记录 [1/8]→[8/8] + exit summary
- **3 个 hotfix 全部落地**(实施期发现问题):
  1. 中文 locale `%date%` 含 `周三` → 用 `wmic os get localdatetime` 拿纯数字时间戳
  2. wmic 输出带 `.244000+480` 后缀 → 加 `~0,8%-%~8,6%` 切片得 `YYYYMMDD-HHMMSS`
  3. 🔴 **关键**:CMD IF 块内 echo 的 ASCII `()` 触发 `was unexpected at this time` 语法炸(Microsoft 已知 bug)→ 6 处 IF 块内 echo 全部把 ASCII 括号换成 `·` separator,并加测试守护
- ruff / tsc / vite build 全绿
- 5 个锁版镜像 tag 全部未动(qdrant:1.7.0 / dify-api:1.0.0 × 2 / kb-ai/dify-db-init:local / kb-ai/backend:local)

### 连带更新

- `docs/superpowers/specs/2026-07-22-v1.5.2-start-bat-logging-design.md`(新建)
- `tests/integration/test_start_bat_logging.py`(新建,9 测)
- `version` 1.5.1 → **1.5.2**
- `README.md` 顶部版本行 `(v1.5.1)` → `(v1.5.2)`
- `AGENTS.md §13` 追加 v1.5.2 节点
- `客户必读.md` 故障指引加 `E:\logs\start-*.log`

### 不在 v1.5.2 范围

- ❌ stop.bat 同步日志(留待 v1.5.3+;当前 stop.bat 已自带 pause + exit 兜底,失败现象比 start.bat 轻)
- ❌ 日志自动上传云端 / 邮件
- ❌ 自动 dump docker events / Windows event viewer
- ❌ 上游问题(Dify 1.5GB / 冷启动 / MinerU 容器化 / 远程 CI / COS 异地 / PRD P1-P2)

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.2-start-bat-logging-design.md`

---

## [1.5.1] - 2026-07-22

### 容器化 patch(patch bump,工程性 + 兼容性修复)

> 目标:v1.5.0 验证发现 2 个真实问题 — 镜像 14.2GB(torch 默认拉 CUDA 全家桶)+ `/api/health` 500(Linux 容器无 host PS 脚本)。v1.5.1 收口,不改业务功能,不改契约。
> 边界:锁版镜像 tag 全部未动;既有 chat SSE / Embedding / Qdrant / 前端契约零变更;不引入新依赖。

### 变更

- **Item 1 Dockerfile hotfix(CPU torch + pwsh)**:builder stage `--index-url https://download.pytorch.org/whl/cpu` + `--extra-index-url https://pypi.org/simple`(torch CPU-only,其他 PyPI 拿);runtime stage 动态检测 libicu(`bookworm=72 / trixie=74`)+ 装 Linux pwsh 7.4 LTS(从 GitHub release tarball,无需 Microsoft repo)+ 校验步骤(`ls -la` + `pwsh --version`)
- **Item 2 ps_runner 容忍脚本缺失**:`backend/core/ps_runner.py:run_ps` 检测脚本路径不存在时返回 `{skipped: True, returncode: 0, stderr: 'script not found: ...'}`(不抛异常)
- **Item 3 health 降级返回**:`backend/api/health.py:get_health` 检测 `result['skipped']` 返回 200 + `{status: degraded, mode: container, note, timestamp}`(写入 30s cache)

### 验证结果

- **镜像体积**:14.2GB → **2.89GB**(缩减 80%)
- **`/api/health`**:500 → **200** + degraded JSON(实测 `{"status":"degraded","mode":"container","note":"host health-probe.ps1 not available in container; external probes skipped","timestamp":"2026-07-22T10:59:10.637732+00:00"}`)
- **冷启动**:5 service 全部 healthy
- **锁版 tag 全部未动**:qdrant:1.7.0 / dify-api:1.0.0 × 2 / `kb-ai/dify-db-init:local` / `kb-ai/backend:local`

### 连带更新

- `docs/superpowers/specs/2026-07-22-v1.5.1-containerization-hotfix-design.md`(新建)
- `version` 1.5.0 → **1.5.1**
- `README.md` 顶部版本行 `(v1.5.0)` → `(v1.5.1)`

### 单测总数

- **基线 v1.5.0 release `159ebcb`+ = pytest 306 / vitest 13**
- **v1.5.1 增量**:`tests/unit/test_ps_runner_skipped.py`(6 测)+ `tests/unit/test_health_degraded.py`(6 测)+ `tests/integration/test_backend_container.py`(+2 测)
- **release HEAD 总数**:**pytest 320 / vitest 13**(已验证 83.92s 全过)/ ruff clean / tsc clean / vite build clean
- **FastAPI 路由**:20(不变)
- **前端影响**:**零**

### 锁版红线(严守)

- ✅ **5 个镜像 tag 全部未变**:qdrant/qdrant:v1.7.0 / langgenius/dify-api:1.0.0 × 2 / kb-ai/dify-db-init:local / kb-ai/backend:local
- ✅ **既有 chat SSE / Embedding / Qdrant / 前端契约零变更**
- ✅ **不动 `.env` / `package.bat` / `start.bat` / `stop.bat` / `architecture-validation-report.md` Part 1**

### 不在 v1.5.1 范围

- ❌ host PS 脚本容器化(后续 v1.6.0+ 候选;非阻塞,降级模式已可用)
- ❌ 1.5GB Dify 镜像体积 / 5-10min 冷启动(上游)
- ❌ MinerU 容器化(v0.7.1 推迟)
- ❌ 远程 CI(无 git remote)
- ❌ COS 异地(用户决策)
- ❌ PRD P1/P2

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5.1-containerization-hotfix-design.md`
- v1.5.0 spec: `docs/superpowers/specs/2026-07-22-v1.5-backend-containerization-design.md`

---

## [1.5.0] - 2026-07-22

### 后端容器化(minor bump,架构性 + 工程性)

> 目标:把 v1.4.0 落地的 Dockerfile 多步构建范式应用至 KB-AI 自建 FastAPI 后端,实现"全部 5 个组件均经 docker compose 编排"的统一部署形态。
> 边界:**v1.5.0 不解决 1.5GB Dify 镜像 / 5-10min 冷启动**(上游问题);**不容器化 MinerU**(v0.7.1 推迟);**不改 chat SSE / Embedding / Qdrant 契约 / 前端契约**。

### 变更

- **Item 1 backend 多阶段 Dockerfile**:新建 `docker/backend/Dockerfile`(35 行,python:3.12-slim builder → wheel / runtime 离线装 + 源码拷贝 + HEALTHCHECK `/api/health`);镜像预算 ≤ 400MB(目标 ≤ 350MB)
- **Item 2 docker-compose 集成 `kb-ai-backend` service**:`docker-compose.yml` 新增 service(build + image: `kb-ai/backend:local` **新增本地 tag**,非 bump 已锁版官方 tag;spec §1.4 已显式声明并经用户授权);volumes 共享 `./data /vectors /cache /logs /tmp` + `./frontend/dist` 只读挂载;`depends_on` qdrant + dify-api service_healthy;healthcheck curl `/api/health`;mem_limit 1g / cpus 1.0 / pids_limit 200
- **Item 3 start.bat / stop.bat 重接(⚠️ 触发 §7.2 红线,经用户授权)**:`start.bat` 第 6 步从 `pwsh scripts\start-backend.ps1` 改 `docker compose up -d kb-ai-backend`;`stop.bat` 第 1 步从 `pwsh scripts\stop-backend.ps1` 改 `docker compose stop kb-ai-backend`;MinerU 逻辑保留(向后兼容);`scripts\start-backend.ps1` / `stop-backend.ps1` 不删除(留作 fallback)
- **Item 4 `docs/backend-container.md` 边界文档**:新建,含 §1 当前架构 + §1.3 边界声明 + §2 Dockerfile 范式 + §2.3 与 v1.4.0 dify-db-init 异同 + §3 compose 集成 + §4 .bat 重接 + §5 不在 v1.5.0 范围 + §6 未来扩展
- **Item 5 集成测试 + 体积验证**:新建 `tests/integration/test_backend_container.py`(14 测,覆盖 compose / Dockerfile / .bat / 锁版 tag 不动);**新增 14 测**(既有 292 + 14 = 306);pytest 全绿(73.69s)
- **Item 6 文档收口 + version bump**:`version` 1.4.0 → 1.5.0;README 顶部版本行 + 架构图同步;CHANGELOG + AGENTS + known-limitations 顶部日期同步

### 连带更新

- `docs/known-limitations.md` 顶部日期同步到 2026-07-22 v1.5.0
- `AGENTS.md §13` 追加 v1.5.0 节点(镜像 size 预算 + 启动序列变化 + 容器数 4 → 5)
- `version` 1.4.0 → **1.5.0**
- `README.md` 顶部版本行 `(v1.4.0)` → `(v1.5.0)`;架构图 4 容器 → 5 容器(含 kb-ai-backend)
- `docker-compose.yml` 文件头注释 4 容器 → 5 容器

### 单测总数

- **基线 v1.4.0 release `0d24db5`+ = pytest 292 / vitest 13**
- **v1.5.0 增量**:`tests/integration/test_backend_container.py` 新建(**+14 测**:compose 5 测 + Dockerfile 4 测 + .bat 4 测 + 锁版 tag 1 测)
- **release HEAD 总数**:**pytest 306 / vitest 13**(已验证 73.69s 全过)/ ruff clean(待 commit)/ tsc clean(待 commit)/ vite build clean(待 commit)
- **FastAPI 路由**:20(无变化;v1.5.0 复用 v1.4.0 路由注册)
- **前端影响**:**零**(仅 README 架构图文字更新;无代码改动)

### 锁版红线(严守)

- ✅ **4 个官方镜像 tag 全部未变**:`qdrant/qdrant:v1.7.0` / `langgenius/dify-api:1.0.0` × 2(`test_official_image_tags_unchanged` 断言通过)
- ✅ **v1.4.0 本地 tag 保留**:`kb-ai/dify-db-init:local`(`test_official_image_tags_unchanged` 断言通过)
- ✅ **v1.5.0 新增本地 tag**:`kb-ai/backend:local`(类比 v1.4.0,spec §1.4 已声明并经用户授权)
- ✅ **不动 `.env` 任何文件 / `package.bat` / `architecture-validation-report.md` Part 1**
- ✅ **既有 chat SSE / Embedding / Qdrant 契约零变更**;前端契约零变更

### 内部重构(零行为变更)

- **后端启动方式**:从 `pwsh scripts\start-backend.ps1`(host python 进程)→ `docker compose up -d kb-ai-backend`(容器)。host ps1 保留作 fallback
- **数据卷挂载**:compose 把 `./data /vectors /cache /logs /tmp` 一一对应到容器内 `/data /vectors /cache /logs /tmp`;`./frontend/dist` 只读挂载到 `/app/frontend/dist`(FastAPI `app.mount("/")` 解析路径不变)
- **环境变量**:compose env_from `.env` 注入(与 dify-api 一致);新增 `KB_AI_ROOT=/data`(向后兼容,host 路径逻辑保留)

### 不在 v1.5.0 范围(明确推迟)

- ❌ Dify 1.5GB 镜像体积(上游)
- ❌ 冷启动 5-10min(上游 + Docker Hub 国内拉取)
- ❌ MinerU 容器化(v0.7.1 推迟)
- ❌ 远程 CI(§5 #1b,无 git remote)
- ❌ COS 异地备份(§4 #5,用户决策)
- ❌ PRD P1/P2(REQ-12/14/15/16/17)
- ❌ Pester 测试 for cost-alert.ps1(§6 #E,候选 v1.6.0)

### 详见

- spec: `docs/superpowers/specs/2026-07-22-v1.5-backend-containerization-design.md`
- plan: `docs/superpowers/plans/2026-07-22-v1.5-backend-containerization.md`
- 边界: `docs/backend-container.md`
- 测试: `tests/integration/test_backend_container.py`(14 测)

---

## [1.4.0] - 2026-07-22

### Dockerfile 多步构建范式化交付(minor bump,工程性 + 文档性)

> 目标:把 known-limitations §4 #3「Dockerfile 多步构建未优化」以范式化交付形式关闭,为未来 backend 容器化预留多阶段构建入口。
> 边界:**v1.4.0 不解决 1.5GB 镜像体积 / 冷启动 5-10min**(无可优化源码),仅落地范式 + .dockerignore + 边界文档。

### 变更

- **Item 1 dify-db-init 多阶段构建范式**:新建 `docker/dify-db-init/Dockerfile`(16 行,builder 装 sqlite / runtime `apk add` 提供二进制 + 共享库;post-review fix `c8f5b83` 修复了原 `COPY --from=builder` 因缺共享库导致运行时失败的问题);`docker-compose.yml` `dify-db-init` service 从 `image: alpine:3.19` 切到 `build: + image: kb-ai/dify-db-init:local`(**新增本地 tag**,非 bump 已锁版官方 tag;spec §1.4 已显式声明并经用户授权);`entrypoint:` / `command:` 保留 v1.3.1 字面量,行为完全等价
- **Item 2 根 `.dockerignore` 范本**:新建 32 行 .dockerignore,排除运行时数据卷 / 虚拟环境 / 前端 dist / .env / 大文件;当前项目无完整 Dockerfile,本文件作为未来构建入口的范本
- **Item 3 `docs/docker-build.md` 边界文档**:新建,含 §1 当前架构 + §1.3 边界声明 + §2 范式样本 + §2.2 未来 backend 容器化扩展路径 + §3 .dockerignore 说明 + §4 不在 v1.4.0 范围

### 连带更新

- `docs/known-limitations.md §4 #3` ❌ → ✅;§6 backlog 移除该项
- `AGENTS.md §13` 追加 v1.4.0 节点
- `version` 1.3.1 → 1.4.0
- `README.md` 顶部版本行 `(v1.3.0)` → `(v1.4.0)` [v1.3.1 补丁未同步 README, 本次补齐]

### 单测总数

- 基线 v1.3.1 release `0026239+` = pytest 292 / vitest 13
- v1.4.0 增量:**0 测**(纯构建 + 文档层,无业务逻辑改动)
- release HEAD 总数:pytest 292 / vitest 13 / ruff clean / tsc clean / vite build clean
- FastAPI 路由:20(无变化)
- 前端影响:零

### 不修改(系统策略)

- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat`
- ❌ 容器镜像 tag(qdrant:1.7.0 / dify-api:1.0.0 × 2 / alpine:3.19 在 Dockerfile FROM 中锁版)
- ❌ `architecture-validation-report.md` Part 1

### 内部重构(零行为变更)

- `dify-db-init` 容器从 `image: alpine:3.19` 切到 `build: + image: kb-ai/dify-db-init:local`;runtime `apk add --no-cache sqlite` **是功能性必需**(提供 sqlite3 二进制 + 共享库 libreadline.so.8 / libsqlite3.so.0 / libncurses 等),非幂等可选;若省略会导致容器内 sqlite3 调用因缺共享库而失败。**post-review fix `c8f5b83`** 在 T5 验证时捕获并修复该问题。

## [1.3.1] - 2026-07-22

### cost-alert 鲁棒性强化(patch bump,zero surface area)

> 目标:把 known-limitations §6 列出的 A-D 4 项 whole-branch review 技术债收口,使 cost-alert 子系统达到"长期可无人值守运行"等级。
> 约束:不改 chat SSE / Embedding / Qdrant 契约 / 前端契约;不引入新依赖;不动 .env / start.bat / stop.bat / package.bat / 容器镜像 tag / `_COST_ALERT_DEFAULT` 阈值。

### 变更

- **Item A 日志轮转**:新建 `scripts/lib/CostLog-Rotate.ps1` 导出 `Rotate-CostLog`(50MB 阈值 → gzip 归档为 `cost_log.jsonl.YYYY-MM.gz`,同月重复追加 `-N`);`cost-alert.ps1` dot-source 库并在累加前调用
- **Item B UTC 规范化**:`Get-CanonicalUtcMonth` 用 `DateTimeOffset::Parse().ToUniversalTime()` 替代 `$entry.ts -like "$yearMonth*"` 字符串前缀比较;`Get-MonthlyCostFromAllSources` 同时扫描当前 + 同月归档,月度统计不再受 ISO8601 时区漂移影响
- **Item C safe_get_usage_tokens**:新建 `backend/core/cost_alert_guard.py:safe_get_usage_tokens`;`backend/core/rag/llm.py:_post_chat` (`:102-109`) 与 `_post_chat_stream` (`:167-172`) 改调 helper,malformed usage(`{"input_tokens": "abc"}` 等)不再抛 `AttributeError` 误触发 Tavily/Bing fallback;5 处 `_log_token_usage` 调用点保持 `if usage is not None: _log_token_usage(...)` 原状(语义已对)
- **Item D validate_cost_alert_payload**:`cost_alert_guard.py` 追加 `validate_cost_alert_payload` + `DEFAULT_COST_ALERT`;`backend/api/dashboard.py:_read_cost_alert()` 末尾调 validate,字段级降级(`level="3"` → 0;`thresholds=null` → 默认;负数 `month_yuan` → 0),防止 chat 入口 TypeError 崩溃

### 连带更新

- `docs/known-limitations.md §6` A-D ❌ → ✅
- `AGENTS.md §13` 追加 v1.3.1 节点
- `version` 1.3.0 → 1.3.1
- `.gitignore` 追加 `data/cost_log.jsonl.*.gz`(既有规则不动)

### 单测总数

- **基线 v1.3.0 release `cccb11e`+ 后 = pytest 275 / vitest 13**
- **v1.3.1 增量**:`tests/unit/test_cost_alert_guard.py` 新建(+15 测,safe 8 + validate 7)+ `tests/unit/test_chat_cost_alert_block.py` 追加 +2 测
- **release HEAD 总数**:**pytest 292 / vitest 13 / ruff clean / tsc clean / vite build clean**
- **FastAPI 路由**:20(无变化)
- **前端影响**:零

### 不修改(系统策略)

- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- ❌ `.gitignore` 既有规则(只追加不删除)
- ❌ `_COST_ALERT_DEFAULT` 默认阈值(warn=$500 / high=$1000 / block=$1500,v1.3.0 锁定)

### 内部重构(零行为变更)

- 单文件拆分:`scripts/lib/CostLog-Rotate.ps1` 抽出 3 个函数(原内嵌于 `cost-alert.ps1` 的轮转 / UTC 比较 / 多源累加逻辑),`cost-alert.ps1` 改 dot-source 调用
- 测试拆分:`tests/unit/test_cost_alert_guard.py` 集中覆盖 C+D 两 helper;既有 `test_chat_cost_alert_block.py` 仅追加 2 测,既有 3 测不动

## [1.3.0] - 2026-07-21

### 运维加固与文档同步(v1.3.0 收官)

> 目标:把 known-limitations §4 / §5 共 7 项运维/文档缺口一次性收口;增加月度配额告警 + pre-commit/pre-push 双 hook;零业务功能新增。
> 约束:不改变聊天 SSE / Embedding / Qdrant contract / 前端契约;不引入新依赖;不修改 .env / start.bat / stop.bat / package.bat / 容器镜像 tag。

### 变更

- **Item 1 AGENTS.md §13 同步**:`AGENTS.md:393` 追加 v1.2.0(RAG 质量 4 PR)+ v1.3.0(本版本)两节点
- **Item 2 PRD v0.7 全面同步**:`<private>/.harness/intake/custom-kb-qa-ai-prd-draft.md`(项目外):v1.0.1 三处偏离已同步,v1.3.0 PRD §0 模型命名 / §3.3 应用栈 / §3.7 启动步骤 / §5 历史四张变更表的更新**延期到下个 session**(本 session 未获用户对项目外文件的修改授权);CHANGELOG / AGENTS / known-limitations / acceptance-checklist 已分别注明此 deferred 状态
- **Item 3 QUICKSTART.md 系统边界**:插入 §9「系统边界与限制」(单设备 / 离线能力 / 文件大小 / 对话长度 / 数据规模 / 容器资源 / U 盘物理风险)
- **Item 4 cost-alert.ps1 月度配额告警**:新建 PS 5.1 脚本;`llm.py` 加 `_log_token_usage` hook + `_post_chat` 返回 `(content, usage)` + `_post_chat_stream` 加 `stream_options={"include_usage": True}`;`chat.py` 加 level≥3 阻断分支(retrieve 之前 SSE 200 + `error` event;不抛 HTTPException 因 EventSourceResponse 已启动);`dashboard.py` 加 `_read_cost_alert()`(含空字符串 sentinel)+ `_build_overview` 追加 `cost_alert` 字段;前端 `DashboardPage` 加 cost-alert 卡片(level=0 进度条 / level≥2 橙色告警 banner / 缺失时"用量数据采集中...");阈值默认 `warn=$500 / high=$1000 / block=$1500`,可 `.env` 覆盖;月度 = UTC 自然月
- **Item 5 dify/README.md**:新建,说明 `knowledge-pipeline.json` 是 v0.7 历史快照
- **Item 6 pre-commit + pre-push 双 hook**:bash hooks 走 `core.hooksPath=scripts/hooks`;pre-commit 跑 ruff;pre-push 跑 `scripts/run-checks.ps1`;`install-hooks.ps1` 含 pwsh 探测降级 + `-DryRun` / `-Uninstall`;**Hook 文件已设 executable bit(100755)**

### 连带更新

- **README.md**:版本号行 `(v0.8.6)` → `(v1.3.0)`;新增「开发命令」段
- **known-limitations.md**:§4 / §5 7 项 → 4 项已实现/移走 + 3 项明确推迟(§4 #3 Dockerfile / §4 #5 COS / §5 #2 架构评审 Part 2 → v1.3.1+ backlog);§4 #1 拆分为"本地 hooks ✅"+"远程 CI ❌"
- **acceptance-checklist.md**:顶部日期 2026-07-21;已知遗留移除已关闭项
- **degradation-guide.md**:加 §"cost-alert 阻断时 SSE error event + 知识库检索仍可用"场景(明确 HTTP 200 + event=error 契约)
- **version**:`1.2.0` → `1.3.0`
- **.gitignore**:加 `data/cost_log.jsonl`

### 单测总数

- **基线(v1.2.0 release `0c1b0eb`)**:pytest 252 / vitest 10
- **v1.3.0 cost-alert 增量**:+18 后端(`test_cost_alert.py` ×6 + `test_chat_cost_alert_block.py` ×3 + `test_dashboard_cost_alert.py` ×6 + `test_session_title.py` ×3)
- **并行 sqlite-refactor 增量**(用户独立工作,计入 release):+5 后端(`test_sqlite_refactor.py`)
- **前端 v1.3.0 增量**:+3 vitest(`DashboardPage.test.tsx` level=0 / level=2 / sentinel fallback)
- **release HEAD 总数**:`cccb11e`+ 后 = **pytest 275 / vitest 13 / ruff clean / tsc clean / vite build clean**
- **FastAPI 路由**:20(无变化;v1.3.0 复用 v1.1.0 路由注册)

### 不修改(系统策略)

- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- ❌ `.gitignore` 既有规则(只追加不删除)
- ❌ 任何业务代码白名单外的改动(`llm.py` / `chat.py` / `dashboard.py` 三处已锁定)

### 内部重构 · PR #1 sqlite-refactor(零行为变更,前置准备)

- **5-repo 拆分**:`backend/core/sqlite.py`(1064 行 god 模块)拆为 `backend/core/sqlite/` 包 —— `connection.py` + 5 个 repo(`sessions_repo` / `messages_repo` / `degradation_repo` / `databases_repo` / `tags_repo`)+ orchestrator `__init__.py`。函数体逐字搬迁,SQL / 签名 / 返回值不变。
- **`transaction()` context manager**:跨 repo 原子写(commit-on-success / rollback-on-exception),修 `delete_database(cascade=True)` 与 `recover_orphans()` 已知的两次-commit 非原子 bug。
- **3 步 init_db**:`init_db_core / init_db_migrate / init_db_post`,与 boot.py SSE schema 阶段对齐;`init_db_core` 显式把 db 路径传给 `keyword_index.init_schema`,保证其表与主库同文件。
- **keyword_index schema 归 `core/rag/keyword_index.py`**:新增 `init_schema` + `delete_by_db_prefix(db_id, *, conn=None)`,`CREATE TABLE` 与 CRUD 同模块;`delete_database` cascade 改调命名 API 而非裸 SQL。
- **临时 re-export shim**:`__init__.py` 再导出全部公开函数,12 个调用点零改(PR #2 迁移后删除)。
- **测试**:新增 `tests/unit/test_sqlite_refactor.py`(5 测:transaction commit/rollback、cascade 原子性、delete_by_db_prefix、init_db 3 步幂等);6 个既有 fixture 的 monkeypatch 目标由 `sqlite_mod.get_db_path` 迁到 `sqlite.connection.get_db_path` / `sqlite.databases_repo._rewrite_qdrant_payloads`。单测基线 270 → **275**。

配套 ADR:`docs/adr/0001-sqlite-repo-split.md`

## [1.2.0] - 2026-07-21

### RAG 质量提升(v1.2 四 PR 收官)

> 目标:收口 xlsx 召回弱、极短问题噪声、长问题检索延迟、同文档跨年份混淆四类 RAG 短板。
> 约束:不改变聊天 SSE / Embedding / Qdrant contract / 前端契约;不新增第三方依赖。

### PR #1 query-profile-and-eval(评测基线 + QueryProfile)

- `backend/core/rag/query_profile.py`:`QueryProfile` frozen dataclass(`char_count` / `meaningful_token_count` / `explicit_years` / `is_short` / `is_long`)+ `build_query_profile` + `extract_explicit_years` + `compress_for_rerank`(head+tail 512 字压缩)
- `backend/api/debug.py`:`/api/debug/retrieval` 新增 `diagnostics` 字段(retrieval_mode / rerank_ms / embedding_ms / total_ms / short_query_fallback / year_match_miss)
- `tests/eval/run_eval.py`:支持 `category` / `expect_year` / `expect_chunk_type` / `max_retrieval_ms` 字段;分类统计 + p95 延迟
- `tests/unit/test_query_profile.py`:12 测(profile 边界 / 年份提取 / 压缩)

### PR #2 xlsx-structuring-and-reparse(表格结构化 + 重解析)

- `backend/core/rag/mineru.py`:`format_xlsx_sheet` 行级结构化(表头 + 第 N 行:列=值);`_read_xlsx` 使用 `data_only=True, read_only=True`
- `backend/core/rag/metadata.py`:`extract_year_mentions(text) -> list[int]` 四位年份纯函数
- `backend/core/rag/chunker.py`:`Chunk` 新增 `year_mentions` / `sheet_name` / `row_start` / `row_end` / `columns`;`document_type="xlsx"` 时走 `xlsx_row_group` 分块模式
- `backend/core/rag/qdrant_store.py`:`delete_by_ids(ids, name)` 最小公开包装
- `backend/api/knowledge.py`:`_build_point` 写入 5 个新 payload 字段;`POST /api/knowledge/documents/{source}/reparse` 分阶段替换(upsert 新 → 删旧 → 重建 keyword_index);路径穿越防护
- `scripts/reparse-rag.ps1`:PS 5.1 兼容批量重解析(读 JSON manifest → 轮询 task 状态)
- `tests/unit/test_xlsx_structuring.py`(4 测)+ `tests/unit/test_reparse_task.py`(3 测)+ `test_qdrant_public_api.py`(+2 测)

### PR #3 retrieval-quality-gates(短问题门控 + 年份优先)

- `backend/core/rag/retriever.py`:
  - `_filter_short_keyword_hits`:is_short 时要求 phrase match 或 ≥2 token overlap;严格门控全空时 fallback 保留原结果
  - `_apply_year_priority`:explicit_years 非空时,year_mentions 命中的 chunk 前置;全不命中时保留原序 + `year_match_miss` 诊断
  - `_normalize_vector_hits` / `_normalize_keyword_hits` 透传 `year_mentions`
- `tests/unit/test_retrieval_quality.py`:7 测(短问题门控 + 年份优先)

### PR #4 long-query-optimization-and-golden-set(长问题优化 + 黄金集)

- `backend/core/rag/retriever.py`:
  - `_effective_rerank_top_n(rerank_top_n, profile)`:is_long 时 cap 到 `DEFAULT_LONG_QUERY_RERANK_TOP_N = 5`
  - `_finish_retrieval` / `_retrieve_once` 接受 `rerank_query` 参数;长问题用 `compress_for_rerank` 压缩后送 reranker
- `tests/eval/golden-qa.jsonl`:50 条黄金问答集(xlsx 9 / short 6 / long 10 / year 11 / 通用 14),pre-reparse baseline 校准
- `tests/unit/test_retrieval_quality.py`:+4 测(_effective_rerank_top_n + _finish_retrieval with rerank_query)

### 单测总数

- **后端 pytest:223 → 252(+29)**(PR1 12 + PR2 9 + PR3 7 + PR4 4 = 32 新测,减去 3 个合并/调整)
- 黄金集评测:50 条,pre-reparse baseline ≥90% 通过

### 不修改(系统策略)

- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1

## [1.1.0] - 2026-07-21

### PR #4 tag-and-title(自由标签 + 标题修复 · 已知短板 #1 / #7)

#### 已知短板关闭
- **#1 自由标签(独立于 Database)**:新表 `tags(id, database_id, name, color, created_at)` + `doc_tags(source, tag_id, created_at)` + 索引 `idx_doc_tags_tag`(`FOREIGN KEY ... ON DELETE CASCADE`);`tags` 表按 `database_id` 作用域,**跨 db 同名 tag 允许**;7 个新路由 `backend/api/tags.py`(挂载于 `backend/main.py:61`):
  - `GET  /api/knowledge/databases/{db_id}/tags` — 列 db 内 tag
  - `POST /api/knowledge/databases/{db_id}/tags` — 建 tag(同名 → 409)
  - `PATCH /api/knowledge/tags/{tag_id}` — 改 name/color
  - `DELETE /api/knowledge/tags/{tag_id}` — 删 tag(CASCADE 自动清 `doc_tags`)
  - `POST /api/knowledge/doc-tags` — 文档批量打标(`AssignTagsRequest.source + tag_ids[1..50]`)
  - `DELETE /api/knowledge/doc-tags/{source}/{tag_id}` — 单条解绑
  - `GET  /api/knowledge/databases/{db_id}/documents?tag_ids=1,2,3` — 按多 tag 交集过滤文档
  - 前端 `TagChip`(3 模式:readonly / selectable / removable)+ `TagPicker` 模态 + `KnowledgePage` 集成左侧 sidebar + 打标按钮 + tag 过滤栏;沿用 `#FF540E` 熔岩橙主色
- **#7 历史会话标题 LLM 生成**:`backend/api/sessions.py:165 generate_session_title_if_needed` 在原 streaming 实现上加 5 条结构化 `session_title_stream:` debug 日志(`missing` / `already_titled` / `below_threshold` / `triggered` / `skipped` / `persisted`),线上排查"为什么没生成"一目了然;触发条件修复 — ≥ 3 条 user 消息且当前标题仍为 `DEFAULT_SESSION_TITLE("新对话")` 才调 LLM,已有非默认标题幂等不再覆盖
- **`boot.py` 新增 `schema_migration` 阶段(8%)**:`backend/api/boot.py:189-206`,在 `orphan_recovery`(7%) 与 `root`(10%) 之间;调用 `init_db()` idempotent 跑 `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE`,tags / doc_tags 老库自动补齐表结构

#### 新增测试(18 后端 + 3 前端 = 21 测)
- `tests/unit/test_tags_api.py`(10 测):
  - `test_init_db_creates_tags_table`:`init_db` 建 tags + doc_tags + idx_doc_tags_tag 三件套
  - `test_create_and_list_tags`:create + list 闭环
  - `test_create_duplicate_tag_raises`:同名 → ValueError
  - `test_assign_and_list_doc_tags`:assign + list_tags_for_doc 闭环
  - `test_list_documents_by_tags_intersect`:多 tag 交集
  - `test_tags_endpoints_registered`:7 路由全部挂载
  - `test_create_tag_via_api` / `test_assign_doc_tags_via_api`:端到端 HTTP 路径
  - `test_cascade_delete_tag_removes_doc_tags`:FOREIGN KEY CASCADE 行为
  - `test_cross_db_isolation`:db_a / db_b 可同名 tag
- `tests/unit/test_session_title.py`(8 测):
  - `test_title_generated_after_3_messages`:`session_title_stream: triggered=True` 日志断言
  - `test_title_below_threshold_does_not_trigger` < 3 消息:`triggered=False reason=below_threshold`
  - `test_title_persists_after_generation`:`UPDATE sessions SET title` 落库断言
  - `test_title_persists_with_stripped_whitespace`:首尾空白去除
  - `test_title_skipped_when_llm_returns_default`:LLM 返回默认标题 → 跳过 UPDATE
  - `test_title_generation_idempotent` + `test_title_generation_idempotent_on_second_call`:已有非默认标题 → LLM 不调
  - `test_title_skipped_for_missing_session`:session 不存在 → False,LLM 不调
- `frontend/src/__tests__/TagChip.test.tsx`(3 测,`vitest`):
  - `renders name with color background`:`backgroundColor: rgb(255, 84, 14)`(#FF540E)
  - `renders remove button in removable mode`:点击 → `onRemove(id)` 调用
  - `does not show remove in readonly mode`:readonly 不渲染删除按钮

#### 单测总数
- **后端 pytest:205 → 223(+18)**(PR #3 完成后 205 + 本 PR 18 测;`scripts/run-checks.ps1` 4/4 全绿,`tests/integration/api/test_api.py` 6/6 通过)
- **前端 vitest:7 → 10(+3)**(PR #3 完成后 7 + 本 PR 3 测)

#### ruff housekeeping(无功能变更)
- 顺手给 PR #4 新增的 `tests/unit/test_session_title.py` 末尾补 W292 trailing newline(`ruff --fix` 自动修,PR #3 期间同款 housekeeping)— 不影响行为;`run-checks.ps1` 4/4 全绿

#### 不修改(系统策略)
- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- ❌ `.gitignore`(本任务无关,本机未提交改动待用户 review)

### PR #3 ui-feedback(REQ-4 / REQ-5 / 图片缩略图 · 已知短板 #2 / #5 / #6)

#### 已知短板关闭
- **#2 图片缩略图**:后端 `GET /api/knowledge/image?path=<rel>` 静态端点(Qdrant 之外的另一种"按文件名取图"通道,兼容 `image_paths` 相对路径);`MessageBubble` 在 `role="user"` + `image_paths.length > 0` 时渲染 80×80 圆角缩略图网格,沿用 XAIAgent 令牌 `#000000` 背景 + `#FF540E` 主色 + `border-radius: 8px`;点击调用 `onImagePreview(path)` 走 `PreviewModal`;无图片时不渲染空容器
- **#5 多选题 UI**:`MessageBubble` 接收 `options: string[]` + `question_type: 'single_choice' | 'multi_choice'` + `onUserReply`;**single_choice** 直接回调 `onUserReply(option)`;/ **multi_choice** 渲染多选按钮 + 单独「确认」按钮,点击收集 `Set<selected>` 拼成 `onUserReply("X, Z")`;沿用 `#FF540E` 主色 + 虚线边框激活态;`options.length === 0` 不渲染容器
- **#6 跳过反问按钮**:`clarification` 字段(`{original_question, fallback_answer?}`)+ `lastUserMessage` 联合渲染 `SkipClarificationButton`(虚线按钮 + `data-testid="skip-clarification"`);按钮文本带原问题(`"按原问题"<Q>"直接回答"`)便于用户复核;点击回调 `onSkipClarification()`,`App.tsx` 带 `skip_clarification: true` + 原 `lastUserMessage` 重发。后端 `chat.py:_should_clarify` 在 `skip_clarification === true` 时直接返回 fallback_answer(或改写为 answer 类型),跳过反问分支

#### 新增测试(8 后端 + 7 前端 = 15 测)
- `tests/unit/test_skip_clarification.py`(5 测):
  - `test_chat_request_has_skip_clarification_field`:ChatRequest 模型字段存在
  - `test_chat_request_skip_clarification_default_is_false`:ChatRequest 模型字段默认 False
  - `test_skip_clarification_rewrites_clarify_to_answer`:后端分支把 clarify 改写为 answer 类型
  - `test_skip_clarification_false_keeps_clarify`:False 时仍走 clarify 流程
  - `test_skip_clarification_uses_fallback_answer_when_provided`:fallback_answer 字段透传
- `tests/unit/test_image_endpoint.py`(3 测):
  - `test_get_image_returns_file_bytes`:成功路径返回二进制
  - `test_get_image_missing_path_returns_422`:缺 path → Pydantic 422
  - `test_get_image_nonexistent_returns_404`:文件不存在 → 404
- `frontend/src/__tests__/MessageBubble.test.tsx`(7 测;`vitest`):
  - **图片缩略图**(2 测):`image_paths` 有内容渲染网格 + 2 张图;空数组不渲染容器
  - **选项按钮**(3 测):single_choice 3 按钮点击触发 `onUserReply('A')`;multi_choice 选 X+Z 点「确认」触发 `onUserReply('X, Z')`;空 options 不渲染
  - **跳过反问**(2 测):有 `clarification` + `onSkipClarification` 渲染按钮(带原问题);缺回调不渲染

#### 单测总数
- **后端 pytest:197 → 205(+8)**(基线 PR #2 完成后 197 + 本 PR 8 测;`scripts/run-checks.ps1` 4/4 全绿;`tests/integration/api/test_api.py` 6/6 通过)
- **前端 vitest:0 → 7(+7)**(基线 PR #2 完成后 0 + 本 PR 7 测;首引入 RTL 套件)

#### ruff housekeeping(无功能变更)
- 顺手清理 2 个 PR #3 新文件 `tests/unit/test_image_endpoint.py` / `tests/unit/test_skip_clarification.py` 的 trailing newline(W292)— `ruff --fix` 自动修,不影响行为;`run-checks.ps1` 4/4 全绿

#### 不修改(系统策略)
- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- ❌ `.gitignore`(本任务无关,本机未提交改动待用户 review)

### PR #2 limit-guard(REQ-6 + 上传限额)

#### 已知短板关闭
- **#8 单会话软上限 50 轮**:`sessions.history_limit` 列(默认 50,1-100 可配);SSE 状态事件首条 `status.soft_warning` 当消息数 ≥ `history_limit * 0.8` 时携带提示文案;`/api/chat` body 字段同步默认 50
- **#3 单图 20MB 硬上限**:`/api/knowledge/upload` 单文件 > 20MB → 413 与 `{limit: "20MB", received: "<size>"}`;前端 `UploadButton.tsx` 文件选择阶段硬拒 + Toast 提示
- **#4 多图 5 张批量上限**:`/api/knowledge/upload` 文件数 > 5 → 413 与 `{limit: 5, received: N}`;前端选择器 `multiple` 限制 + 选中数校验
- **#8 配置入口**:`PATCH /api/sessions/{id}` body `{history_limit: int(1..100), title?: str(≤256)}` 写入 SQLite;SettingsPage 历史轮数选择器 10/20/50/100 实时持久化

#### 新增测试(5 测;`tests/unit/test_limit_guard.py`)
- `test_patch_session_history_limit_persists`:PATCH 改 history_limit → 响应 + SQLite 双层验证
- `test_patch_session_title_persists`:PATCH 改 title 持久化,history_limit 不动
- `test_patch_session_missing_returns_404`:不存在 session_id → 404,不动数据库
- `test_patch_session_history_limit_out_of_range_returns_422`:0 / 101 / -5 → Pydantic 422
- `test_patch_session_empty_body_keeps_row_unchanged`:空 body 不写数据库,返回当前行

#### 单测总数
- **192 → 197(+5)**(基线 PR #1 完成后 192 + 本 PR 5 测;`scripts/run-checks.ps1` 全绿)

#### ruff housekeeping(无功能变更)
- 顺手清理 6 个测试文件 `tests/unit/test_*.py` 的 trailing newline(W292 历史遗留)— `ruff --fix` 自动修,不影响行为;`run-checks.ps1` 4/4 全绿

#### 不修改(系统策略)
- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- ❌ `.gitignore`(本任务无关,本机未提交改动待用户 review)

### PR #1 data-integrity(REQ-9 + #11)

#### 已知短板关闭
- **#9 数据库删除级联保护**:默认 `cascade=false`;数据库仍有子文档时返回 `409` 与 `{child_documents: N, requires_cascade: true}`,前端解析 FastAPI `detail` envelope 并弹出二次确认,仅确认后请求 `?cascade=true`;级联删除串行清理 Qdrant collection、keyword 索引、tag 关联和 `processing_state`;Qdrant 不可达时写入 `degradation_events(component='Vector')`,返回 `200 + warnings`,不阻断主流程
- **#11 `bulk_assign_documents_to_database` 同步重写 Qdrant payload**:新增 `backend/core/bulk_assign.py:_rewrite_qdrant_payloads`,按旧 `source` scroll,再以不超过 100 个 point/批调用 `set_payload` 写入新 `source`;失败降级写入 `degradation_events(component='Vector')`,不阻断 keyword_index 同步与主流程

#### 新增测试(5 测)
- `tests/unit/test_database_cascade.py`:
  - `test_delete_database_with_children_returns_409`:有子文档时默认拒删并返回数量
  - `test_delete_database_no_children_succeeds`:无子文档时保持直接删除兼容行为
  - `test_delete_database_cascade_qdrant_down_returns_warning`:Qdrant 不可达时返回 warning 并记录 Vector 降级事件
- `tests/unit/test_bulk_assign_qdrant.py`:
  - `test_rewrite_payloads_calls_set_payload`:验证 Qdrant `set_payload` 批量改写
  - `test_bulk_assign_calls_qdrant_rewrite`:验证 bulk assign 主流程触发 payload 重写

#### 单测总数
- **167 → 184(+17)**(基线 v1.0.0 GA 167 + 本 PR 5 测;+17 累计含 T1.1/T1.2 实施期新增的 12 测,brief 估的 +2/+3 为低估,以实际 pytest 收集为准)

#### 不修改(系统策略)
- ❌ `.env` / `package.bat` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1

## [1.0.1] - 2026-07-20

### 文档 · PRD 三处偏离同步(doc-only,零代码变更)

PRD v0.7 原写版本与实际实现偏差已锁定在 v1.0 GA;v1.0.1 把 PRD 与现状对齐,消除"文档说一套做一套"的混乱。

#### 修改
- **`<private>/.harness/intake/custom-kb-qa-ai-prd-draft.md` REQ-9**:「腾讯云 CVM」→「1TB USB SSD + Windows 10/11 单机」(v0.7.1 用户决策)
- **REQ-10**:**「浅色商务风」→「XAIAgent 暗黑赛博风 #000000 + #FF540E」**(v0.8.1 用户决策,锁版于 `design-system/XAIAgent-design-spec.md`)
- **REQ-13**:「每日 03:00 自动 COS + AES-256」→「stop.bat 触发本地 zip + 7 份轮转」(v0.8.6 用户决策)
- **第 3 节部署流程**:`Windows-Start.bat` → `start.bat`;`localhost:8080` → `localhost:8000`;UI 关闭按钮 → 顶 nav 关闭按钮
- **第 4 节验收清单**:12 条 P0 标 ✅ + 加 2 条新验证项(`/api/eval/run` ≥ 80% 通过、Dashboard 4-5 卡片渲染)
- **PRD v0.7 段落头**:标注「v1.0.1 重写」前缀,后续 verifier 一眼看出决策时间线

#### 不修改
- ❌ 无任何代码/配置文件改动
- ❌ PRD 第 1-8 节需求定义、用户故事、范围边界整体保留

### 风险评估
- **零代码风险**:纯文档同步
- **向后兼容**:所有 v1.0.0 行为不变
- **影响面**:仅 verifier / 工程师 / 用户向文档阅读者

## [1.0.0] - 2026-07-20 · GA 锁定

### 🎯 v1.0 GA 交付清单

KB-AI v1.0 GA 锁定。功能完备、技术债清理完毕、健康度可视化、可由终端用户独立使用。

#### 新增文档(交付证据链)
- **`docs/acceptance-checklist.md`** — PRD 12 条 P0 逐条验收表 + FMEA 关闭情况 + 验证命令速查
- **`docs/degradation-guide.md`** — 降级与故障自愈手册(覆盖 8 种降级场景)
- **`docs/known-limitations.md`** — 已知问题与限制清单(4 类:PRD 偏离 / 功能短板 / RAG 边角 / 运维缺口 / 文档缺口 / 未来项)

#### 版本号
- 根 `version` 文件:`0.8.12` → **`1.0.0`**
- 语义:首个"功能完备"稳定版

#### 累计交付基线
| 维度 | v0.8.10 | v1.0.0 |
|---|---|---|
| FastAPI 路由 | 7 | **13** |
| pytest 单测 | 60 | **167** |
| 测试文件数 | 7 | **13** |
| FMEA 🔴 已关闭 | 0 | **5** |
| PRD P0 未实现 | 1(REQ-2) | **0** |
| 用户文档数 | 4 | **7** |

#### 继承自 0.8.12(详见 0.8.12 段)
- eval 路由化(`POST /api/eval/run` + Dashboard 金标问答卡片)
- 解析产物分层(`<db_id>/<doc_id>/parsed.md` + backup SHA-1 manifest)

#### 继承自 0.8.11(详见 0.8.11 段)
- Database 抽象层(治 REQ-2)+ sidebar UI
- processing_state 持久化 + 启动自检(治 F07/F20)
- atomic_io 工具(治 F11/F13)
- degradation_events.component 维度(治 F06)
- docker-compose start_period 完整化
- Dashboard 4 卡片(治 F08)

#### 已知遗留(进入 1.0 GA 的明确 TODO)
详见 `docs/known-limitations.md` §2:
- 自由标签、多选题 UI、跳过反问按钮、xlsx 召回弱、QUICKSTART 部署边界章节
- PRD REQ-9/10/13 三处偏离的文档同步(用户决策接受,1.0.1 修)

#### 不修改(系统策略)
- ❌ `.env` 任何文件
- ❌ `package.bat`
- ❌ `architecture-validation-report.md` Part 1
- ❌ `docker-compose.yml` 容器镜像 tag

## [0.8.12] - 2026-07-20

### 新增(Phase 2:借鉴 E + H,Yuxi-Know 调研收尾)

#### P2.1 · eval 路由化(治 FMEA F15 378)
- **重构** `tests/eval/run_eval.py`:新增 `run_evaluation()` 函数,返回结构化 dict(total/passed/failed/pass_rate/duration/results/timestamp);CLI 入口保持兼容
- **新路由** `backend/api/eval.py`:
  - `POST /api/eval/run` body `{dataset_path?, top_k?, no_rerank?}` → 触发评测
  - `GET /api/eval/results` → 返回最近一次结果(进程内缓存)
  - `GET /api/eval/status` → 轻量状态探针
- **前端 Dashboard 加金标问答卡片**:展示通过/失败/通过率/耗时 + 失败用例详情(可折叠)+ 「运行评测」按钮
- **新测试** `tests/unit/test_eval_route.py`(6 测):mock urlopen,覆盖 happy path / 缺数据集 / 空数据集 / 关键词缺失 / reranked_fallback / 端点缓存

#### P2.2 · 解析产物分层(借鉴 H)
- **`parse_to_markdown` 新增 `db_id` 参数**:`cache_dir / <db_id> / <doc_id> / raw.md` + `meta.json`
- **向后兼容**:旧版扁平 `cache_dir / <doc_id> / raw.md` 仍可读,首次写入新结构
- **`knowledge.py`** `_process_upload` 调 `parse_to_markdown(..., db_id=database_id)`
- **`backup.ps1`** 增加 manifest 生成:写 `backup-manifest.json`(每条路径 + bytes + SHA-1),重新打包进 zip;供恢复时校验完整性
- **新测试** `tests/unit/test_parsed_cache_namespacing.py`(4 测):分层命中 / 跨 db 隔离 / 命中同 db / 旧版 fallback / 无 db_id 走扁平

### 修复 / 质量
- **`backend/core/rag/mineru.py`** legacy_cache_path 修复:db_id 分支也设 legacy path,确保老数据可读
- **ruff 全绿**;167 单测全过(原 157 + 10 新增);vite build 通过

## [0.8.11] - 2026-07-20

### 新增(Yuxi-Know 借鉴 + PRD REQ-2 落地 + FMEA 治根)

#### P1.1 · Database 抽象层(治 REQ-2 硬阻塞)
- **新表** `databases(id, name, description, collection, embed_model, chunk_size, chunk_overlap, created_at)`
  - `default` 行自动插入,绑定到现有 `kb_ai_chunks` collection(向后兼容)
  - 新建 db 自动用 `kb_chunks_<db_id>` 命名空间
- **新路由** `backend/api/databases.py`:`GET/POST/PATCH/DELETE /api/knowledge/databases` + `/assign` 批量迁移
- **改造 5 个已有端点** 加 `?database_id=` 参数:`/knowledge/documents` `/upload` `/{source}` `/{source}/chunks` `/{source}/reembed`
- **Source 命名空间**:keyword_index 与 Qdrant payload 中的 source 用 `<db_id>::<filename>` 前缀隔离,避免跨 db 同名冲突
- **前端 KnowledgePage 全面改版**:左侧 sidebar 列出所有分类 + 「新建分类」Modal;右侧主区按当前 db 过滤
- **迁移工具** `bulk_assign_documents_to_database()` 把存量文档划归新建 db(仅改 keyword_index.source 前缀)

#### P1.2 · 任务状态持久化 + 启动自检(治 FMEA F07 280 / F20 105)
- **新表** `processing_state(task_id, operation, source, database_id, stage, status, started_at, updated_at, finished_at, error)`
- **in-memory `_TASKS` dict 双写**:同时持久化到 SQLite,进程崩了状态不丢
- **`recover_orphans()` 启动扫描**:检 `status='processing' AND updated_at < now-600s` 的孤儿 → 标记 failed + 写 `degradation_events(component='Processing')`
- **`boot.py` 启动 SSE 新增 `orphan_recovery` 阶段(7%)**:用户可见的自检结果

#### P1.3 · 原子写工具(治 FMEA F11 224 / F13 216)
- **新模块** `backend/core/atomic_io.py`:`atomic_write_text` / `atomic_write_json` / `atomic_append_jsonl`(借鉴 Yuxi-Know `base.py:524-555`)
- **embedder 迁移**:缓存追加从 `f.write()` → `atomic_append_jsonl`(>50MB 自动退回 best-effort)

#### P1.4 · degradation_events 加 component 维度(治 FMEA F06 288)
- **schema 迁移**:`ALTER TABLE degradation_events ADD COLUMN component`(try/except 捕 duplicate column)
- **新签名** `save_degradation_event(..., component=None)` — chat.py / knowledge.py 全部调用点补全
- **component 取值**:`LLM` / `Embedding` / `Qdrant` / `Reranker` / `Retrieval` / `Vector` / `Keyword` / `Websearch` / `Processing`
- **新聚合函数** `degradation_summary_by_component(since_iso)`

#### P1.5 · docker-compose start_period 完整化
- `dify-api`:60s → 120s(EAS cold start 宽限)
- `dify-worker`:30s → 60s

#### P1.6 · Dashboard(治 FMEA F08 280 + GA 形态)
- **新路由** `GET /api/dashboard/overview` — 4 类数据 1 次 RTT:健康端点 / 24h 降级事件 / KB 统计 / Qdrant↔keyword 漂移
- **新前端页面** `DashboardPage.tsx` — 4 卡片 + 30s 自动刷新 + 手动刷新按钮
- **顶 nav 新增「系统」入口**(图标 `LayoutDashboard`)
- **新测试** `tests/unit/test_dashboard_aggregations.py`

### 修复 / 质量
- **`backend/api/knowledge.py`** 修复 `saved_path.st_mtime` → `saved_path.stat().st_mtime`(单测暴露)
- **`backend/api/knowledge.py`** 修测试 mock `sqlite3.connect` 的递归调用:`_persist_stage/_finish` 全部 try/except 兜底
- **降级事件 component 列缺失时的健壮性**:`COALESCE(component, 'Unknown')` 聚合时为 NULL 转 Unknown

### 测试
- **+30 个新单测**:`test_database_crud.py` (16)、`test_atomic_io.py` (10)、`test_degradation_component.py` (5)、`test_dashboard_aggregations.py` (4)
- **157 个单测全绿**;6 个 API 集成测试全绿;ruff 全绿;vite build 通过

### 不修改(系统策略)
- ❌ `.env` 任何文件
- ❌ `package.bat`
- ❌ `architecture-validation-report.md` Part 1
- ❌ `docker-compose.yml` 容器镜像 tag

## [0.8.10] - 2026-07-20

### 整理(目录与结构一次性清理,无功能变更)
- **删除 9 个临时/历史项**:`_ubrain_backup_20260709/`、`_trim_agents.py`、`compose.err.tmp`、`compose.out.tmp`、`skills-lock.json`、根 `.ruff_cache/`、`backend/tests/integration/`(空)、`design-system/MASTER.md.v1.2.bak`、`design-system/MASTER.md.v1.3.bak`
- **删除 6 个重复/分叉项**:`docs/quickstart.md`、`design/`(自标 DEPRECATED)、`backend/static/`(frontend/dist/ 的 7/14 旧快照)、`data/sessions.db`+`backend/data/sessions.db`(v0.7.2 起统一至 `data/db.sqlite`)、`tmp/` 下 20+ 临时文件(总计约 130MB,含 122MB drift 备份)
- **迁移 3 项**:`RELEASE-M3*.md` → `docs/releases/`
- **代码层同步**:`scripts/backup.ps1:11,135` 移除 `sessions.db` 引用;`package.bat:67` 加 `docs\releases\` 前缀(用户授权)
- **文档层同步**:`AGENTS.md` §1/§5/§12.2/§13、`CHANGELOG.md` (本段)、`README.md` 目录树与版本链接
- **更新**:`.kb-ai-root/version` 0.8.2 → 0.8.9
- **版本号**:根 `version` 文件 0.8.9 → 0.8.10
- **不修改**:`backend/main.py`(挂载点现状正确)、`scripts/run-checks.ps1`(4 步仍适用)
- **验证**:见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md §6
## [0.8.9] - 2026-07-17

### 修复(用户单项授权改 start.bat + stop.bat)
- **start.bat 启动 MinerU 解析服务**:第 6 步后端启动后新增 :8001 健康探测,未运行则后台最小化窗口拉起 `backend/mineru_server.py`。根治"用户前端上传 PDF/PPTX 报 MinerU unreachable"的交付缺口(2026-07-17 数据治理批实测踩到)
- **stop.bat 停止 MinerU 进程**:第 1 步停后端后,按命令行特征 `*mineru_server.py*` 结束残留 python 进程(兼容正/反斜杠路径;实测 before 200 → after unreachable)。消除"安全弹出后 U 盘路径进程残留"

### 数据治理(同日,纯数据操作)
- keyword_index 漂移清零:垃圾 chunk 11 + 测试残留 1 + 孤儿行 3 清理;`孙圈圈IP营销知识地图(1).pdf` 整篇乱码(批量入库 PS 编码问题)经后端 Python 管线重入库 29 段;**最终 Qdrant 1204 = keyword 1204**,eval 回归 20/20
- 经验:PDF/PPTX 入库一律走后端 `/api/knowledge/upload`(Python 管线),PS 批量管线有编码风险

## [0.8.8] - 2026-07-17

### 用户体验(感知性能优化:把首字前的"黑盒等待"变成可视化工作过程)
- **阶段化等待提示**:`chat.py` SSE `status` 事件从 1 个增至 4 个真实阶段(检索中 → 已找到 N 条资料 → 联网补充[仅降级时] → AI 思考中),前端此前完全忽略 status 事件
- **ThinkingStatus 组件**(`MessageBubble.tsx`):已完成阶段打勾、当前阶段熔岩橙呼吸点 + 实时秒数、每 6 秒轮换使用小贴士(4 条,面向非技术用户);首字流出后自动消失,样式遵循 XAIAgent 设计令牌
- 实测 SSE 事件序:3×status → 42×draft → 1×answer,阶段顺序正确

## [0.8.7] - 2026-07-17

### 性能优化(用户报告"页面慢 + 回复慢",全部实测数字驱动)
- **首问 70 秒卡顿消除**:`reranker.py` 默认 `HF_HUB_OFFLINE=1` — 模型已缓存后不再向 huggingface.co 发 HEAD 校验(国内直连 10s×5 重试挂起);未缓存时快速失败优雅降级,根治首次检索挂起
- **LLM 流式输出**:`llm.py` 新增 `_post_chat_stream` / `chat_stream_with_fallback`(L0→L3 降级链保持,仅"未出字前失败"才切换);`chat.py` 新增 SSE `draft` 事件 + `extract_streaming_content` 增量解析 JSON 契约的 content 字段(转义/代理对安全);前端 App.tsx 逐 token 渲染。**实测:首字 19.2s(含首问模型加载),回答逐字流出;同问题总时长 48.7s → 23.4s**
- **rerank 候选 20→10**(`retriever.py` 默认值;修复 `chat.py` 遗留硬编码 `rerank_top_n=20` 会覆盖优化的问题)+ 重排文本截断 500 字:rerank 实测 7.8s → ~3-4s
- **`/api/health` 30 秒内存缓存**:此前每次调用现场起 PowerShell + 顺次探测 3 个外网端点;前端 30s 轮询不再卡"检测中"

### 可靠性
- **上传入库自动校验(F)**:`knowledge.py` 上传任务完成后校验 keyword_index 覆盖 chunk 数,不一致在任务结果中带 `warning` + `verified:false`
- 新增 `tests/unit/test_streaming_extract.py` 9 测(流式 JSON 增量解析:完整/半截/code fence/转义/代理对/非 answer 型)

### 已知保留观察
- xlsx"名单/进度表"类文档自然语言召回弱(记入 `tests/eval/golden-qa.jsonl` 头部注释)
- keyword_index 与 Qdrant 有 12 chunk 轻微漂移(可跑 `/api/knowledge/reembed` 修复)

## [0.8.6] - 2026-07-16

### 新增
- `scripts/backup.ps1`(FMEA F03):`data\` + `vectors\` zip 备份到电脑硬盘,保留 7 份;`stop.bat` 尾部自动调用
- 前端设计切换为 XAIAgent 暗黑机能风(`design-system/XAIAgent-design-spec.md`,应用于 `backend/static/index.html`)

### 变更
- `stop.bat` 重写为 4 步:停 FastAPI 后端 → 停容器 → SQLite 落盘 → 自动备份
- `start.bat` 第 5 步探测 URL 修正

## [0.8.5] - 2026-07-15

### 新增
- `tests/test_certainty.ps1`:CertaintyTagger 标签规则回归

## [0.8.4] - 2026-07-14

### 新增
- `backend/core/rag/` 完整 RAG 管线(11 模块):chunker / embedder / qdrant_store / keyword_index / mineru / llm / retriever / reranker / query_rewriter / tokenizer
- `scripts/lib/CertaintyTagger.ps1`:规则式 fact/opinion/draft/neutral 标签
- `/api/knowledge/reembed` 端点;embedding 缓存 LRU 淘汰(200MB 上限)
- `tests/test_chunking.ps1`、`tests/unit/test_rag_core.py`

### 变更
- `start.bat` 重写为 8 步,主入口指向 `http://localhost:8000`(自建 React 前端取代 Dify Web UI 成为用户主界面)
- FastAPI CORS 缩窄到 localhost:8000/8080(`backend/main.py`)
- 前端 `App.tsx` 拆分为 components/ + pages/ + lib/
- `dify/knowledge-pipeline.json` 的 document_parser 标注 `available: false`(MinerU 服务引用已废弃)

## [0.8.3] - 2026-07-13

### 新增
- `tests/unit/` Python 单测套件(reranker / query_rewriter / retriever_fallback / debug_api / temporal_weighting)
- `parse-doc.ps1` 超长单段滑窗切片 + 200MB 文件大小保护

## [0.8.2] - 2026-07-13

### 新增
- `frontend/`:React 18 + TypeScript + Vite 自建前端
- 批量入库脚本组:`batch-parse-and-ingest.ps1`(105 文件)+ `image-caption.ps1` + `process-remaining.ps1` + `reprocess-failed.ps1` + `reprocess-remaining.ps1`

## [0.8.1] - 2026-07-13

### 新增
- 双模型路由:默认 `qwen3.6-plus`,复杂关键词走 `qwen3.7-max`;Plus/Max 失败互切降级
- `chat.ps1 -MaxTokens` 参数(默认 2000)
- `tests/test_model_routing.ps1`;`test_api.py` 增加 `test_chat_complex_routes_to_max`

## [0.8.0] - 2026-07-13

### 新增
- **架构跃迁**:`backend/` FastAPI 后端(7 路由:health/status/knowledge/sessions/chat/shutdown/boot)取代 chat.ps1 成为主入口,chat.ps1 保留作 fallback
- SSE chat + 混合检索 + `/api/boot` 8 阶段启动进度 + `/api/shutdown` 安全弹出
- SQLite 增表 `degradation_events`(API 降级记录)
- `scripts/start-backend.ps1` / `scripts/stop-backend.ps1`
- `tests/integration/api/test_api.py` FastAPI 端点集成测试

## [0.7.2] - 2026-07-08

### 新增
- Hybrid Search 全链路:`scripts/lib/Tokenizer.ps1` 轻量分词 + SQLite 倒排表 + RRF 融合
- `tests/integration/hybrid-search.ps1` 真容器集成测试

## [0.7.1] - 2026-07-07

### 修复(架构评审 TODO #1-#4、#7、#8)
- 端口绑定收窄到 `127.0.0.1`;4 容器全部设置 `mem_limit`/`cpus`
- `score_threshold` 统一为 0.6;`dify-db-init` 服务启用 SQLite WAL
- `health-probe.ps1` 区分 critical(Qwen)/optional 端点
- `quickstart.ps1` 重命名为 `setup.ps1`;建立 `scripts/lib/` 公共库(load-env / Invoke-SqliteExec / Write-Utf8NoBom)

## [0.7.0] - 2026-07-02

### 新增(M1-M3d 阶段收官,详见 `docs/releases/RELEASE-M3.md`)
- M1 基础设施:docker-compose(Dify + Qdrant + MinerU)、start.bat / stop.bat、.env.example
- M2 核心 MVP:`chat.ps1` RAG 主循环、`parse-doc.ps1`、`embed-and-ingest.ps1`、`websearch.ps1`(Tavily→Bing 降级)
- M3a UX:`safe-eject.ps1`、`status-bar.ps1`、`disk-alert.ps1`
- M3b 跨平台:`get-usb-root.ps1`、`version.ps1`、`show-help.ps1`
- M3c 图片理解:`image-prep.ps1`、`batch-images.ps1`、chat.ps1 多模态改造
- M3d 收官:`e2e_test.ps1`、`health-full.ps1`、`QUICKSTART.md`、`package.bat`
