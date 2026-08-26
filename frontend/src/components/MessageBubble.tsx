// MessageBubble + EmptyState + parseCitations
// v0.8.4 从 App.tsx 拆出。
// v0.8.8(UX):新增 ThinkingStatus — 首字前的阶段化等待提示。

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Citation } from "../lib/types";

export function formatTime(d: Date): string {
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function parseCitations(
  text: string,
  citations?: Citation[]
): ReactNode {
  if (!text) return null;
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, idx) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const index = parseInt(m[1], 10);
      const c = citations && citations[index - 1];
      return (
        <span
          key={idx}
          className="citation"
          title={c ? `${c.source} · ${c.snippet}` : "来源"}
          onClick={() => c && alert(`来源 [${index}]\n${c.source}\n${c.snippet}`)}
        >
          {part}
        </span>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

interface ImageThumbnailsProps {
  paths: string[];
  onImageClick?: (path: string) => void;
}

// v1.1.0 PR#3:图片缩略图网格(80×80, XAIAgent 令牌)
export function ImageThumbnails({ paths, onImageClick }: ImageThumbnailsProps) {
  if (!paths || paths.length === 0) return null;
  return (
    <div className="image-thumbnails" data-testid="image-thumbnails">
      {paths.map((p, idx) => (
        <img
          key={idx}
          src={p}
          alt={`附件 ${idx + 1}`}
          className="thumbnail"
          onClick={() => onImageClick?.(p)}
          loading="lazy"
        />
      ))}
    </div>
  );
}

interface OptionButtonsProps {
  options: string[];
  multi: boolean;
  onSelect: (selected: string[]) => void;
}

// v1.1.0 PR#3 Task 3.4:多选题按钮(REQ-5) — 单选直接回调 / 多选确认按钮
function OptionButtons({ options, multi, onSelect }: OptionButtonsProps) {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = (opt: string) => {
    if (multi) {
      setSelected((s) =>
        s.includes(opt) ? s.filter((x) => x !== opt) : [...s, opt]
      );
    } else {
      onSelect([opt]);
      return;
    }
  };

  const handleConfirm = () => {
    if (selected.length > 0) onSelect(selected);
  };

  return (
    <div className="option-buttons" data-testid="option-buttons">
      {options.map((opt, idx) => (
        <button
          key={idx}
          className={`option-btn ${selected.includes(opt) ? 'selected' : ''}`}
          onClick={() => toggle(opt)}
        >
          {opt}
        </button>
      ))}
      {multi && (
        <button
          className="option-confirm"
          onClick={handleConfirm}
          disabled={selected.length === 0}
        >
          确认 ({selected.length})
        </button>
      )}
    </div>
  );
}

interface SkipClarificationButtonProps {
  originalQuestion: string;
  onSkip: () => void;
}

// v1.1.0 PR#3 Task 3.5:反问跳过按钮(REQ-4) — 用户在 assistant 走 clarify 路径时
// 可以点这个按钮让后端用 skip_clarification=true 重发原问题,改走 answer 路径。
function SkipClarificationButton({
  originalQuestion,
  onSkip,
}: SkipClarificationButtonProps) {
  const trimmed = (originalQuestion || "").trim();
  const display =
    trimmed.length > 30 ? trimmed.slice(0, 30) + "…" : trimmed || "原问题";
  return (
    <button
      className="skip-clarification-btn"
      onClick={onSkip}
      data-testid="skip-clarification"
    >
      ↪ 按原问题"{display}"直接回答
    </button>
  );
}

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  time?: string;
  isStreaming?: boolean;
  stages?: string[];
  statusStartedAt?: number;
  // v1.1.0 PR#3:图片附件路径
  image_paths?: string[];
  // v1.1.0 PR#3 Task 3.4:多选题选项(REQ-5)
  options?: string[];
  question_type?: 'single_choice' | 'multi_choice';
  onUserReply?: (text: string) => void;
  // v1.1.0 PR#3 Task 3.5:反问上下文(后端走 clarify 路径时由 App 注入)
  clarification?: { original_question?: string };
  // v1.1.0 PR#3 Task 3.5:lastUserMessage 作为 original_question 的回退来源
  lastUserMessage?: string;
  // v1.1.0 PR#3 Task 3.5:跳过反问回调(App 收到回调后带 skip_clarification=true 重发)
  onSkipClarification?: () => void;
}

// v0.8.8(UX):等待期间轮换的小贴士(面向非技术用户,只讲用法)
const THINKING_TIPS = [
  "小贴士：回答里的 [1] [2] 数字可以点开，查看资料来源",
  "小贴士：问题越具体，回答越准确",
  "小贴士：Excel、Word 资料上传到「资料库」后，就能直接提问",
  "小贴士：点左上角菜单，可以查看历史对话",
];

interface ThinkingStatusProps {
  stages: string[];
  startedAt: number;
}

// v0.8.8(UX):首字前的阶段化等待提示 — 已完成阶段打勾、当前阶段呼吸闪烁、
// 实时秒数 + 轮换小贴士。把"黑盒等待"变成"看得见的工作过程"。
export function ThinkingStatus(props: ThinkingStatusProps) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = props.startedAt;
    const update = () =>
      setElapsed(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [props.startedAt]);
  const tip = THINKING_TIPS[Math.floor(elapsed / 6) % THINKING_TIPS.length];
  return (
    <div className="thinking-status" aria-label="AI 正在处理">
      <div className="thinking-stages">
        {props.stages.map((s, i) => {
          const isCurrent = i === props.stages.length - 1;
          return (
            <div
              key={i}
              className={`thinking-stage ${isCurrent ? "current" : "done"}`}
            >
              {isCurrent ? (
                <span className="thinking-dot" aria-hidden="true" />
              ) : (
                <span className="thinking-check" aria-hidden="true">
                  ✓
                </span>
              )}
              <span className="thinking-label">{s}</span>
              {isCurrent && (
                <span className="thinking-elapsed">{elapsed}s</span>
              )}
            </div>
          );
        })}
      </div>
      <div className="thinking-tip" key={tip}>
        {tip}
      </div>
    </div>
  );
}

export function MessageBubble(props: MessageBubbleProps) {
  const label = props.role === "user" ? "您的消息" : "KB-AI 回答";
  const showThinking =
    props.role === "assistant" &&
    props.isStreaming &&
    !props.content &&
    !!props.stages &&
    props.stages.length > 0 &&
    !!props.statusStartedAt;
  // v1.1.0 PR#3:图片缩略图
  const imagePaths = props.image_paths || [];
  // v1.1.0 PR#3 Task 3.4:多选题
  const options = (props.options || []) as string[];
  const isMulti = props.question_type === 'multi_choice';
  // v1.1.0 PR#3 Task 3.5:反问跳过按钮(REQ-4)— clarification 由 App 在收到
  // 后端 clarify 路径响应时注入;original_question 优先,缺则回退到上下文里
  // 最近一条用户消息(从 App 的 lastUserMessage 传入)。
  const showSkip = !!props.clarification && !!props.onSkipClarification;
  return (
    <div className={`message ${props.role}`} aria-label={label}>
      {props.role === "assistant" && (
        <div className="message-sender">KB-AI Assistant</div>
      )}
      <div className="message-bubble">
        {showThinking && (
          <ThinkingStatus
            stages={props.stages!}
            startedAt={props.statusStartedAt!}
          />
        )}
        {imagePaths.length > 0 && <ImageThumbnails paths={imagePaths} />}
        {parseCitations(props.content, props.citations)}
        {props.isStreaming && !showThinking && <span className="typing-cursor" />}
        {options.length > 0 && (
          <OptionButtons
            options={options}
            multi={isMulti}
            onSelect={(sel) => props.onUserReply?.(sel.join(', '))}
          />
        )}
        {showSkip && (
          <SkipClarificationButton
            originalQuestion={
              props.clarification!.original_question || props.lastUserMessage || ""
            }
            onSkip={props.onSkipClarification!}
          />
        )}
      </div>
      {props.time && <div className="message-time">{props.time}</div>}
    </div>
  );
}

interface EmptyStateProps {
  onStart: () => void;
}

export function EmptyState(props: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-rings" aria-hidden="true">
        <div className="ring" />
        <div className="ring" />
        <div className="ring-core" />
      </div>
      <div className="empty-label">[ System Ready ]</div>
      <h2>启动 KB-AI 助手</h2>
      <p>
        开始您的第一个问题，KB-AI 会引用您的资料回答。
        <br />
        例如：招牌菜红烧肉怎么做？
      </p>
      <button className="empty-state-btn" onClick={props.onStart}>
        开始对话
      </button>
    </div>
  );
}