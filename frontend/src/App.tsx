// App · KB-AI 前端 v0.8.4
// v0.8.4 重构:组件全部拆出,本文件只保留状态管理 + 页面路由 + SSE 消费。
// v1.1.0 PR#2 Task 2.4 — SSE status 事件带 soft_warning(后端 T2.3 在 chat.py:152-162
// 实现: history_count >= history_limit*0.8 时下发"已达 X/Y 轮,接近上限")。
// 本文件包含 chat 主体(无独立 ChatPage.tsx),渲染顶部黄色横幅。

import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Send } from "lucide-react";
import { API_BASE, getJSON, postAgentChat, postJSON } from "./lib/api";
import type {
  AgentMeta,
  AgentStep,
  BootStageState,
  Citation,
  Message,
  PageId,
  ServiceStatus,
  Session,
} from "./lib/types";

import { TopNav, StatusBar } from "./components/TopNav";
import { Drawer } from "./components/Drawer";
import {
  EmptyState,
  MessageBubble,
  formatTime,
} from "./components/MessageBubble";
import { BootProgressModal, ShutdownModal } from "./components/Modals";
import { KnowledgePage } from "./pages/KnowledgePage";
import { SettingsPage } from "./pages/SettingsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { AlertTriangle, X } from "lucide-react";

// v2.0 PR#4(T13):Agent 工具参数摘要(≤60 字符,JSON 序列化失败给空串)
function summarizeAgentArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  try {
    const s = JSON.stringify(args);
    return s.length > 60 ? s.slice(0, 57) + "..." : s;
  } catch {
    return "";
  }
}

// =========================================================================
// App 主组件:状态 + SSE 消费 + 页面路由
// =========================================================================

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<ServiceStatus>("checking");
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  // v0.8.6(F01/FMEA):关闭流程状态;shutDown=true 时整屏锁定,
  // 防止旧实现"仅 alert、页面仍可交互"导致关闭后继续聊天写库。
  const [shuttingDown, setShuttingDown] = useState(false);
  const [shutDown, setShutDown] = useState(false);
  const [bootOpen, setBootOpen] = useState(false);
  const [bootCurrentStage, setBootCurrentStage] = useState("env");
  const [bootPercent, setBootPercent] = useState(5);
  const [bootMessage, setBootMessage] = useState("准备启动...");
  const [bootError, setBootError] = useState<string | null>(null);
  const [bootDone, setBootDone] = useState(false);
  // v1.1.0 PR#2 Task 2.4:SSElimit-guard soft_warning — 当会话历史 ≥ history_limit * 0.8
  // 时,后端在第一个 status 事件里下发软上限提示,前端展示顶部黄色横幅;用户可手动关闭。
  const [softWarning, setSoftWarning] = useState<string | null>(null);
  // v2.0 PR#4(T13):Agent 模式开关 — 默认关走旧 /api/chat;打开走 /api/agent/chat。
  // localStorage 持久化,两条链路并存可对比(设计稿 §7)。
  const [agentMode, setAgentMode] = useState<boolean>(() => {
    try {
      return localStorage.getItem("kb_ai_agent_mode") === "1";
    } catch {
      return false;
    }
  });
  const [currentPage, setCurrentPage] = useState<PageId>("chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bootEsRef = useRef<EventSource | null>(null);

  const handleAgentModeChange = useCallback((v: boolean) => {
    setAgentMode(v);
    try {
      localStorage.setItem("kb_ai_agent_mode", v ? "1" : "0");
    } catch {
      // localStorage 不可用时仅内存生效
    }
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error("health probe failed");
      const data = await res.json();
      // v0.8.6 修复(C1/FMEA):health-probe.ps1 输出顶层 online 布尔 +
      // endpoints: {qwen: true, ...};旧代码按 { status: "online" } 对象解析,
      // 布尔值的 .status 为 undefined → 恒判"离线",关机按钮随之失效。
      if (data && data.online === true) {
        setStatus("online");
      } else {
        setStatus("offline");
      }
    } catch {
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const id = setInterval(checkHealth, 30000);
    return () => clearInterval(id);
  }, [checkHealth]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await getJSON<Session[]>("/sessions?limit=50");
      setSessions(data || []);
    } catch (e) {
      console.error("加载会话失败:", e);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleNewSession = useCallback(async () => {
    try {
      const data = await postJSON<Session>("/sessions", { title: null });
      setCurrentSessionId(data.session_id);
      setMessages([]);
      // v1.1.0 PR#2 Task 2.4 review fix: 新建会话时清空旧会话的 soft_warning,
      // 避免上一轮已达 80% 的黄色横幅跨会话残留。
      setSoftWarning(null);
      setDrawerOpen(false);
      setCurrentPage("chat");
      textareaRef.current?.focus();
      loadSessions();
    } catch (e: any) {
      alert("创建会话失败：" + (e?.message || "未知错误"));
    }
  }, [loadSessions]);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    // v1.1.0 PR#2 Task 2.4 review fix: 切换会话时清空 soft_warning,
    // 避免旧会话的 80% 提示挂在新会话上;新会话若同样触发,由后端 status 事件重新下发。
    setSoftWarning(null);
    setDrawerOpen(false);
    setCurrentPage("chat");
    try {
      const data = (await getJSON<any[]>(
        `/sessions/${sessionId}/messages?limit=50`,
      )) as Array<{
        message_id: string;
        role: "user" | "assistant";
        content: string;
        timestamp?: string;
        citations?: Citation[];
      }>;
      setMessages(
        (data || []).map((m) => ({
          id: m.message_id,
          role: m.role,
          content: m.content,
          time: m.timestamp ? formatTime(new Date(m.timestamp)) : "",
          citations: m.citations || [],
        })),
      );
    } catch (e: any) {
      alert("加载消息失败：" + (e?.message || "未知错误"));
    }
  }, []);

  const handleSend = useCallback(
    async (
      override?: string | React.MouseEvent,
      options?: { skip_clarification?: boolean }
    ) => {
      const overrideText = typeof override === "string" ? override : undefined;
      const text = (overrideText ?? input).trim();
      if (!text || loading) return;

      // v1.1.0 PR#3 Task 3.5:REQ-4 跳过反问 — 用户点 SkipClarificationButton
      // 后,App 用同一文本(override=lastUserMessage) + skip_clarification=true
      // 重发;后端 chat.py:395 接到此 flag 且仍返回 clarify 时改走 answer 路径。
      const skipClarification = !!options?.skip_clarification;

      let sid = currentSessionId;
      if (!sid) {
        try {
          const data = await postJSON<Session>("/sessions", { title: text.slice(0, 20) });
          sid = data.session_id;
          setCurrentSessionId(sid);
          loadSessions();
        } catch (e: any) {
          alert("创建会话失败：" + (e?.message || "未知错误"));
          return;
        }
      }

      const userMsg: Message = {
        id: Date.now() + "-user",
        role: "user",
        content: text,
        time: formatTime(new Date()),
      };
      // v1.1.0 PR#3 Task 3.5:跳过反问不需要再把原问题往气泡流里追加(屏幕上
      // 已经显示过这条用户消息),避免重复;仅在常规发送时 push。
      if (!skipClarification) {
        setMessages((prev) => [...prev, userMsg]);
      }
      setInput("");
      // v1.1.0 PR#2 Task 2.4:每次新发送把软上限提示清空,后端 status 事件会按当前
      // 会话历史重新下发;避免上一轮已达 80% 的提示一直挂在新会话里。
      setSoftWarning(null);
      setLoading(true);

      try {
        await postJSON(`/sessions/${sid}/messages`, { role: "user", content: text });
      } catch (e) {
        console.error("保存用户消息失败:", e);
      }

      const assistantId = Date.now() + "-assistant";
      // v1.1.0 PR#3 Task 3.5:跳过反问 → 复用现有助手气泡(去掉 streaming 标识)
      // 让结果直接覆盖上去;常规发送则新增一个空助手气泡。
      if (skipClarification) {
        setMessages((prev) =>
          prev.map((m) =>
            m.isStreaming
              ? {
                  ...m,
                  content: "",
                  stages: [],
                  statusStartedAt: Date.now(),
                  clarification: undefined,
                  options: undefined,
                }
              : m
          )
        );
      } else {
        setMessages((prev) => [
          ...prev,
          { id: assistantId, role: "assistant", content: "", time: "", isStreaming: true },
        ]);
      }

      try {
        // v2.0 PR#4(T13):Agent 模式走 /api/agent/chat(SSE 六事件契约),否则走旧 /api/chat。
        // 两条链路并存,开关在设置页,默认关。
        const response = agentMode
          ? await postAgentChat({
              question: text,
              session_id: sid,
              top_k: 5,
              max_steps: 8,
              history_limit: 50,
            })
          : await fetch(`${API_BASE}/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                question: text,
                session_id: sid,
                top_k: 5,
                skip_clarification: skipClarification,
              }),
            });
      if (!response.ok) throw new Error(`请求失败: ${response.status}`);

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalAnswer: any = null;
      // v2.0 PR#4:Agent 步骤的实时累积(避免 setMessages 闭包读旧值)
      let pendingSteps: AgentStep[] = [];

      const appendStep = (step: AgentStep) => {
        pendingSteps = [...pendingSteps, step];
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, agentSteps: pendingSteps } : m,
          ),
        );
      };
      const updateStep = (
        step: number,
        name: string,
        patch: Partial<AgentStep>,
      ) => {
        const idx = [...pendingSteps]
          .reverse()
          .findIndex(
            (s) =>
              s.step === step &&
              s.name === name &&
              (s.status === "running" || s.status === "ok"),
          );
        if (idx >= 0) {
          const realIdx = pendingSteps.length - 1 - idx;
          pendingSteps = pendingSteps.map((s, i) =>
            i === realIdx ? { ...s, ...patch } : s,
          );
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, agentSteps: pendingSteps } : m,
            ),
          );
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (let i = 0; i < lines.length; i++) {
          const line = lines[i];
          if (line.startsWith("event:")) {
            const eventName = line.slice(6).trim();
            const dataLine = lines[i + 1];
            if (dataLine && dataLine.startsWith("data:")) {
              const data = dataLine.slice(5).trim();
              try {
                const parsed = JSON.parse(data);
                if (eventName === "answer") {
                  finalAnswer = parsed;
                } else if (eventName === "status") {
                  // v0.8.8(UX):阶段化等待提示 — 追加到当前助手气泡的阶段轨迹
                  const label: string = parsed.message || "";
                  if (label) {
                    setMessages((prev) =>
                      prev.map((m) =>
                        m.id === assistantId
                          ? {
                              ...m,
                              statusStartedAt: m.statusStartedAt ?? Date.now(),
                              stages: (m.stages || []).includes(label)
                                ? m.stages
                                : [...(m.stages || []), label],
                            }
                          : m,
                      ),
                    );
                  }
                  // v1.1.0 PR#2 Task 2.4:解析 soft_warning(后端 T2.3 chat.py:152-162),
                  // history 接近 history_limit 上限时只在第一个 status 事件里下发,
                  // 其余 status 事件的 soft_warning 为 null,自然幂等。
                  if (parsed.soft_warning) {
                    setSoftWarning(String(parsed.soft_warning));
                  }
                } else if (eventName === "draft") {
                  // v0.8.7 流式输出:逐 token 追加到助手气泡
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: m.content + (parsed.text || "") }
                        : m,
                    ),
                  );
                } else if (eventName === "step_start") {
                  // v2.0 PR#4:Agent 循环轮次标记(无 UI 动作,预留)
                } else if (eventName === "tool_call") {
                  // v2.0 PR#4:Agent 工具调用开始 → 追加 running 步骤
                  const argsSummary = summarizeAgentArgs(parsed.args);
                  appendStep({
                    step: parsed.step ?? 0,
                    name: parsed.name || "tool",
                    argsSummary,
                    status: "running",
                  });
                } else if (eventName === "tool_result") {
                  // v2.0 PR#4:工具执行完毕 → 更新对应步骤
                  updateStep(parsed.step ?? 0, parsed.name || "tool", {
                    status: parsed.ok ? "ok" : "error",
                    latencyMs: parsed.latency_ms,
                    excerpt: parsed.excerpt,
                  });
                } else if (eventName === "error") {
                  throw new Error(parsed.message || "AI 调用失败");
                }
              } catch (e) {
                if (eventName === "error") throw new Error(data);
              }
              i++;
            }
          }
        }
      }

      if (finalAnswer) {
        // v1.1.0 PR#3 Task 3.5:反问上下文 — 后端 chat.py:456-457 在 clarify
        // 路径下发 question 字段(App 也叫 clarify_question);把当时的原问题
        // 一起塞进 clarification.original_question 供 SkipClarificationButton 渲染。
        const isClarify = finalAnswer.type === "clarify";
        const clarification = isClarify
          ? { original_question: text }
          : undefined;
        // v2.0 PR#4:Agent 元信息(run_id/步数/工具/用量/budget_exhausted)
        const agentMeta: AgentMeta | undefined = agentMode
          ? {
              ...(finalAnswer.agent || {}),
              budget_exhausted: !!finalAnswer.budget_exhausted,
            }
          : undefined;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: finalAnswer.content || "（AI 未返回内容）",
                  citations:
                    finalAnswer.citations || finalAnswer.citations_idx || [],
                  time: formatTime(new Date()),
                  isStreaming: false,
                  clarification,
                  agentMeta,
                  agentSteps: pendingSteps.length > 0 ? pendingSteps : undefined,
                }
              : m,
          ),
        );
        loadSessions();
        if (
          finalAnswer.model_reason &&
          String(finalAnswer.model_reason).startsWith("fallback")
        ) {
          setStatus("degraded");
        } else if (finalAnswer.web_source) {
          setStatus("degraded");
        }
      } else {
        throw new Error("未收到回答");
      }
    } catch (err: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: `出错了：${err.message}`,
                time: formatTime(new Date()),
                isStreaming: false,
              }
            : m,
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [input, loading, currentSessionId, loadSessions, agentMode]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // v1.1.0 PR#3 Task 3.5:REQ-4 跳过反问 — 从 messages 数组里取最近一条用户
  // 消息作为原问题,带 skip_clarification=true 重发;后端 chat.py:395 若仍
  // 返回 clarify 则改走 answer 路径。MessageBubble 的 SkipClarificationButton
  // 在用户点击时调用此函数。
  const handleSkipClarification = useCallback(() => {
    if (loading) return;
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    handleSend(lastUser.content, { skip_clarification: true });
  }, [messages, loading, handleSend]);

  const handleShutdown = async () => {
    // v0.8.6(F01/FMEA):旧实现仅 alert、页面仍可交互(可继续聊天写库);
    // 改为成功后整屏锁定,提示可以安全拔盘。
    setShuttingDown(true);
    try {
      await postJSON<{ message: string }>("/shutdown");
      setShutDown(true);
      setShutdownOpen(false);
    } catch (e: any) {
      alert("关闭请求失败：" + (e?.message || "未知错误"));
    } finally {
      setShuttingDown(false);
    }
  };

  const closeBootStream = useCallback(() => {
    bootEsRef.current?.close();
    bootEsRef.current = null;
  }, []);

  const setBootStages = (
    stage: string,
    percent: number,
    message: string,
    error: string | null,
    done: boolean,
  ) => {
    setBootCurrentStage(stage);
    setBootPercent(percent);
    setBootMessage(message);
    setBootError(error);
    setBootDone(done);
  };

  const startBoot = useCallback(() => {
    closeBootStream();
    setBootStages("env", 5, "准备启动...", null, false);
    setBootOpen(true);
    setShutdownOpen(false);

    const es = new EventSource(`${API_BASE}/boot`);
    bootEsRef.current = es;

    es.addEventListener("progress", (e: MessageEvent) => {
      try {
        const data: BootStageState = JSON.parse(e.data);
        setBootStages(data.stage, data.percent, data.message, null, !!data.done);
        if (data.error) {
          setBootError(data.message);
          setBootDone(false);
          closeBootStream();
        } else if (data.done) {
          setBootDone(true);
          setBootError(null);
          closeBootStream();
          setTimeout(checkHealth, 2000);
        }
      } catch (err) {
        console.error("解析启动进度事件失败:", err);
      }
    });

    es.addEventListener("error", (e: MessageEvent) => {
      if (e.data) {
        try {
          const data = JSON.parse(e.data);
          setBootError(data.message || "启动进度连接出错");
        } catch {
          setBootError("启动进度连接出错");
        }
      } else {
        setBootError("启动进度连接已中断");
      }
      closeBootStream();
    });

    es.onerror = () => {
      setBootError((prev) => prev || "启动进度连接已中断");
      closeBootStream();
    };
  }, [closeBootStream, checkHealth]);

  const closeBootModal = useCallback(() => {
    closeBootStream();
    setBootOpen(false);
  }, [closeBootStream]);

  const retryBoot = useCallback(() => {
    startBoot();
  }, [startBoot]);

  useEffect(() => {
    return () => closeBootStream();
  }, [closeBootStream]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
    }
  }, [input]);

  const showStatusBar = status === "offline" || status === "degraded";

  const handlePageChange = (page: PageId) => {
    setCurrentPage(page);
    setDrawerOpen(false);
  };

  return (
    <div className="app">
      <TopNav
        status={status}
        currentPage={currentPage}
        onPageChange={handlePageChange}
        onToggleDrawer={() => setDrawerOpen((o) => !o)}
        drawerOpen={drawerOpen}
        onShutdown={() => setShutdownOpen(true)}
        onBoot={startBoot}
      />
      <StatusBar status={status} />
      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
      />
      <ShutdownModal
        open={shutdownOpen}
        onClose={() => setShutdownOpen(false)}
        onConfirm={handleShutdown}
        busy={shuttingDown}
      />
      {shutDown && (
        <div className="modal-overlay open" role="dialog" aria-modal="true">
          <div className="modal">
            <h2 className="modal-header">KB-AI 已关闭</h2>
            <div className="modal-body">
              <p>数据已保存，服务已安全停止。现在可以拔出 U 盘了：</p>
              <ul>
                <li>1. 在系统托盘找到「安全删除硬件」图标</li>
                <li>2. 选择您的 USB SSD</li>
                <li>3. 等待「安全地移除设备」提示后拔出</li>
              </ul>
              <p>下次使用：重新双击 U 盘里的 start.bat</p>
            </div>
          </div>
        </div>
      )}
      <BootProgressModal
        open={bootOpen}
        currentStage={bootCurrentStage}
        percent={bootPercent}
        message={bootMessage}
        error={bootError}
        done={bootDone}
        onClose={closeBootModal}
        onRetry={retryBoot}
      />
      {currentPage === "chat" && (
        <main
          className={`chat-container ${showStatusBar ? "with-status-bar" : ""}`}
          aria-label="主内容"
        >
          {/* v1.1.0 PR#2 Task 2.4:T2.3 limit-guard soft_warning 顶部提示条 */}
          {softWarning && (
            <div
              className="soft-warning-banner"
              role="status"
              aria-live="polite"
            >
              <AlertTriangle size={16} aria-hidden="true" />
              <span className="soft-warning-text">{softWarning}</span>
              <button
                className="soft-warning-close"
                onClick={() => setSoftWarning(null)}
                aria-label="关闭提示"
                title="关闭提示"
              >
                <X size={14} />
              </button>
            </div>
          )}
          <div
            className="messages"
            role="log"
            aria-live="polite"
            aria-label="聊天消息流"
          >
            {messages.length === 0 ? (
              <EmptyState onStart={() => textareaRef.current?.focus()} />
            ) : (
              messages.map((msg, idx, arr) => {
                // v1.1.0 PR#3 Task 3.5:为每个气泡计算它"之前"最近的用户消息,
                // 用作 SkipClarificationButton 的 original_question 回退来源。
                const lastUserBefore = [...arr.slice(0, idx)]
                  .reverse()
                  .find((m) => m.role === "user");
                return (
                  <MessageBubble
                    key={msg.id || idx}
                    role={msg.role}
                    content={msg.content}
                    citations={msg.citations}
                    time={msg.time}
                    isStreaming={msg.isStreaming}
                    stages={msg.stages}
                    statusStartedAt={msg.statusStartedAt}
                    image_paths={msg.image_paths}
                    options={msg.options}
                    question_type={msg.question_type}
                    clarification={msg.clarification}
                    lastUserMessage={lastUserBefore?.content}
                    onSkipClarification={handleSkipClarification}
                    onUserReply={(text) => handleSend(text)}
                    // v2.0 PR#4(T13):Agent 步骤面板
                    agentSteps={msg.agentSteps}
                    agentMeta={msg.agentMeta}
                  />
                );
              })
            )}
            {loading && messages.length === 0 && (
              <div className="skeleton-bubble">
                <div className="skeleton-line" style={{ width: "80%" }} />
                <div className="skeleton-line" style={{ width: "60%" }} />
                <div className="skeleton-line" style={{ width: "70%" }} />
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="input-area">
            <div className="input-wrapper">
              <button className="attach-btn" aria-label="添加附件">
                <Paperclip size={20} />
              </button>
              <textarea
                ref={textareaRef}
                className="chat-input"
                rows={1}
                placeholder="问 AI 经营问题，比如：招牌菜红烧肉怎么做？"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                aria-label="输入问题"
              />
              <button
                className="send-btn"
                onClick={handleSend}
                disabled={!input.trim() || loading}
                aria-label="发送消息"
              >
                <Send size={18} />
              </button>
            </div>
            <div className="input-hint">按 Enter 发送，Shift + Enter 换行</div>
          </div>
        </main>
      )}
      {currentPage === "knowledge" && <KnowledgePage />}
      {currentPage === "settings" && (
        <SettingsPage
          status={status}
          // v1.1.0 PR#2 Task 2.4:history_limit 选择器需要绑到当前会话 —
          // SettingsPage 通过 currentSession.history_limit 显示初值,PATCH 后
          // 调用 onSessionUpdated 触发 loadSessions() 拉新数据保持同步。
          currentSession={
            currentSessionId
              ? sessions.find((s) => s.session_id === currentSessionId) ?? null
              : null
          }
          onSessionUpdated={loadSessions}
          // v2.0 PR#4(T13):Agent 模式开关
          agentMode={agentMode}
          onAgentModeChange={handleAgentModeChange}
        />
      )}
      {currentPage === "dashboard" && <DashboardPage />}
    </div>
  );
}