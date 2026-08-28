# KB-AI 评审导览(面试官 / 技术评审,5 分钟)

> 你在看一个"单人交付、真实使用中"的本地 AI 知识库。本文按"先看结论、再看证据"组织:每个亮点给出可以直接打开的代码锚点。

## 1. 这个项目是什么

USB 移动硬盘上的本地知识库:5 个 Docker 容器 + FastAPI + React,LLM 走阿里云百炼(Qwen),检索与数据全部本地。目标用户是非技术者 —— 双击 `start.bat` 可用。**技术重心在:自研工具调用 Agent、混合检索管线、可靠性工程(降级/成本/评测)。**

## 2. 五分钟看什么(按优先级)

| 顺序 | 打开 | 看什么 |
|---|---|---|
| ① | [`docs/adr/0002-agent-loop-self-built.md`](adr/0002-agent-loop-self-built.md) | 为什么自研 ReAct 循环而不用 LangGraph —— 5 个权衡点,含依赖面/测试友好/事件协议边界 |
| ② | [`backend/core/agent/loop.py`](../backend/core/agent/loop.py) | ~370 行生成器实现完整 Agent 循环:max_steps 预算、重复调用护栏、错误转 observation 续跑、token 级流式(`answer_delta`/`answer_reset` 契约)、轨迹落库 |
| ③ | [`backend/core/agent/tools.py`](../backend/core/agent/tools.py) | OpenAI function calling JSON Schema 工具注册;`calculator` 是 ast 白名单求值(拒 `__import__`/属性访问/溢出);kb/web observation 包 `<kb_context>`/`<web_context>` 分隔符(prompt injection 加固) |
| ④ | [`docs/eval/2026-08-27-golden-agent-report.md`](eval/2026-08-27-golden-agent-report.md) | 真实 LLM 评测:23 条 golden-agent,87% 工具选择/任务完成,**含采样方差区间、成本核算、失败模式归因**(不是只报好数字) |
| ⑤ | [`backend/core/rag/retriever.py`](../backend/core/rag/retriever.py) | 混合检索:向量腿 + 关键词腿各自隔离容错 → RRF 融合 → cross-encoder 重排 → 时间加权 → 低置信度扩召回;每步可降级、可诊断 |

## 3. 常见追问 & 直接证据

- **"Agent 循环为什么不用框架?"** → ADR-0002;另外 [`tests/unit/test_agent_stream.py`](../tests/unit/test_agent_stream.py) 展示自研循环的白盒可测性(mock 流式 LLM 即可覆盖全部路径)。
- **"流式怎么做降级?"** → [`llm.py` `chat_with_fallback_tools_stream`](../backend/core/rag/llm.py):某次尝试在 yield 任何 delta **之前**失败才重试/切换;已下发 delta 后失败记 `mid_stream_fail` 并抛出(静默重试会重复输出)。
- **"检索质量怎么证明?"** → [`tests/eval/`](../tests/eval/) 双评测集(50 条 golden-QA + 23 条 golden-agent)+ [`run_eval.py`](../tests/eval/run_eval.py) / [`run_agent_eval.py`](../tests/eval/run_agent_eval.py),指标含召回/工具选择/任务完成/p95 延迟/每任务 token 成本。
- **"工具调用安全吗?"** → calculator AST 白名单(`tools.py:_eval_node`)+ prompt injection 双层防护(`_wrap_untrusted` + 系统提示词规则 5)+ cost 月度熔断(`core/cost_alert_guard.py`)。
- **"线上出问题怎么查?"** → 降级台账 `degradation_events`(Dashboard 24h 聚合)、Agent 轨迹表(每步 latency/token)、`GET /api/debug/retrieval` 全链路中间态。
- **"测试呢?"** → pytest **371** 个单测(后端)+ vitest 18(前端)+ PowerShell mock 回归 + GitHub Actions CI(`.github/workflows/test.yml`)。

## 4. 已知的取舍与弱点(诚实清单)

- 上下文按字符数预算(非 token 数);多轮历史为尾部截断,无摘要压缩 —— 单用户场景够用,SaaS 化需重做(见 FAQ/架构评审记录)。
- SSE 断连后 worker 线程不可取消,会跑完当次 LLM 调用(max_steps 硬顶兜住上限)。
- 评测的"任务完成率"是关键词命中,非 LLM-as-judge;评测结果未落库无趋势。
- Agent 步骤间无并发(单步单工具串行)。

> 这些是**单用户便携产品**场景下的主动取舍;对应规模化改造思路见 ADR 与评测报告的"真实发现"节。
