# ADR-0002 · Agent 循环自研(不引入 LangGraph)

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-08-27 |
| **驱动版本** | KB-AI v2.0.0 |
| **配套 spec** | `docs/superpowers/specs/2026-08-25-v2.0-agent-edition-design.md`(Agent Edition 设计) |
| **决策工具** | 成本/依赖/控制粒度三维权衡 + 面试口径预演(T23) |
| **影响文件** | 新增 `backend/core/agent/`(tools.py / loop.py / trajectory.py)+ `backend/api/agent.py` + `tests/unit/test_agent_*.py`(34 测) |

---

## Context

KB-AI v1.7.0 是单程 RAG 问答(`/api/chat` 检索 1 次 + LLM 1 次)。v2.0 要升级为**工具调用 Agent**:多步推理(检索→计算→作答)、工具注册表(kb_search / calculator / get_current_time / web_search)、轨迹落库、任务级评测。

实现 Agent 循环有两个候选:

- **A. 引入 LangGraph**(`langgraph` + `langchain-core`,官方 Python SDK):StateGraph / 节点 / checkpointer / 生态工具链
- **B. 自研轻量 ReAct 循环**(<300 行,纯生成器,零新依赖)← **选定**

## Decision

**自研 `backend/core/agent/loop.py`,不引入 LangGraph/LangChain。**

`run_agent()` 是 Python 生成器,逐步 yield 事件 dict(`step_start` / `tool_call` / `tool_result` / `answer` / `error`),由 `api/agent.py` 的 SSE 层直接透传;LLM 调用走既有 `chat_with_fallback_tools()`(复用 L0→L3 降级链与 token 计量),工具走 `execute_tool()` 注册表分发,轨迹走 `trajectory.py` 三门面落 SQLite。

## 权衡(为什么不做 A)

### 1. 依赖面:与项目「低依赖 / 便携 / 离线优先」DNA 冲突

LangGraph 会引入 `langgraph + langchain-core + langchain-*` 传递依赖链,后端 venv 体积与容器镜像显著膨胀(v1.5.0 刚把镜像从 14.2GB 压到 2.89GB,镜像 tag 已锁版)。本项目跑在 U 盘上、冷启动 60s 目标,每多一个框架 = 更多安装失败面与体积。自研实现零新依赖,`requirements.txt` 一字未加。

### 2. 控制粒度:单 Agent 场景下框架抽象是负债

v2.0 的循环只有 4 个"小决策":max_steps 预算(硬顶 16)、相同 (name,args) 重复调用强制收尾(repeat_guard)、observation 截断 2000 字符回填、预算耗尽无 tools 收尾。这些在 LangGraph 里要分别映射到 StateGraph 节点/条件边/checkpointer 配置,抽象层数 > 逻辑本身;而自研是 ~280 行顺序代码,每个决策点一行注释对应设计稿 §11 风险条目。**框架的价值在于复杂状态机,这里没有。**

### 3. 调试与测试:生成器模型天然适配 SSE 与 mock

`run_agent()` 是纯生成器:单测只需 mock `chat_with_fallback_tools`,断言事件序列(`test_agent_loop.py` 12 测覆盖单步/多步/预算耗尽/repeat_guard/异常续跑/解析失败回退)。若用 LangGraph,测试要么黑盒走框架执行器、要么理解其内部状态机,`budget_exhausted` 这类自定义终止条件在框架里要绕 checkpointer 语义。**12 个单测在自研下是"读代码即懂"的白盒测试。**

### 4. 演进预留:事件协议就是抽象边界

如果未来要 planner/worker/critic 多 Agent 编排,自研 loop 的 `yield 事件 dict` 协议可以作为编排层的外部契约(LangGraph 届时可替换 loop 内部实现而不动 SSE 契约与轨迹表)。**先做对的事,不为假设的复杂度付钱**(池外清单 §5:多 Agent 编排本周期明确不做)。

### 5. 面试口径(T23 配套)

被问"为什么不用 LangGraph"时的标准回答:**"知道框架能做什么(StateGraph/checkpointer/生态),但本项目单 Agent 循环的全部状态 = 1 个 messages 列表 + 3 个计数器,框架的 checkpointer 持久化与条件边是为多 Agent/跨会话恢复设计的,当前是过度工程;我留好了事件协议边界,需要时替换成本可控。"** —— 这比"我没用过"强一个量级。

## 代价与缓解

| 代价 | 缓解 |
|---|---|
| 循环健壮性(超时/死循环/解析异常)靠手写 | 单测 12 测 + repeat_guard + max_steps 硬顶 + `execute_tool` 永不抛 + T14 golden-agent 评测回归 |
| 没有框架生态(工具封装/记忆/评估插件) | 项目已有检索/降级/计量资产,工具只有 4 个只读函数,生态用不上 |
| 面试可能被追问框架细节 | T23 LangGraph 概念速学(不改代码)+ 本 ADR 第 5 点口径 |

## Open Questions(不阻塞)

1. **多 Agent 编排**如果未来启动,是否切 LangGraph?→ 倾向是:先按本 ADR 事件协议扩展自研编排,框架切换只做 spike 评估。
2. **v2.1 末步流式**(设计稿 §11 风险 #2 候选):loop 最后一步走 `chat_stream_with_fallback`,与生成器协议兼容,无需动框架决策。

---

## References

- **Spec**:`docs/superpowers/specs/2026-08-25-v2.0-agent-edition-design.md` §2.3(非目标:不引入 LangChain/LangGraph 重写)
- **工单池**:`docs/superpowers/plans/2026-08-25-v2.0-ticket-pool.md` T10-T15
- **ADR 模板**:MADR 风格,对齐 ADR-0001
- **T09 冒烟**:DashScope 兼容模式 `tools` SUPPORTED(设计稿 §13),自研循环的实现前提
