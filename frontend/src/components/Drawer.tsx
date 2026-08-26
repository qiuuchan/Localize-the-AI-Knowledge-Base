// Drawer:会话历史侧栏
// v0.8.4 从 App.tsx 拆出。

import { MessageSquare, Plus } from "lucide-react";
import type { Session } from "../lib/types";

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  sessions: Session[];
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}

export function Drawer(props: DrawerProps) {
  return (
    <>
      <div
        className={`drawer-overlay ${props.open ? "open" : ""}`}
        onClick={props.onClose}
        aria-hidden="true"
      />
      <aside className={`drawer ${props.open ? "open" : ""}`} aria-label="会话历史">
        <div className="drawer-header">
          <span className="drawer-title">
            <span className="drawer-title-prefix">[01]</span>会话历史
          </span>
          <button className="drawer-new-btn" onClick={props.onNew}>
            <Plus size={14} />
            <span>新建</span>
          </button>
        </div>
        <div className="drawer-list">
          {props.sessions.length === 0 ? (
            <div className="drawer-empty">
              <MessageSquare
                size={32}
                style={{ marginBottom: 12, opacity: 0.4 }}
              />
              <div>暂无会话</div>
              <div>点击"新建"开始</div>
            </div>
          ) : (
            props.sessions.map((s) => (
              <div
                key={s.session_id}
                className={`drawer-item ${
                  s.session_id === props.currentSessionId ? "active" : ""
                }`}
                onClick={() => props.onSelect(s.session_id)}
                role="button"
                tabIndex={0}
                aria-current={
                  s.session_id === props.currentSessionId ? "true" : undefined
                }
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") props.onSelect(s.session_id);
                }}
              >
                <span className="drawer-item-icon">
                  <MessageSquare size={18} />
                </span>
                <div className="drawer-item-text">
                  <div className="drawer-item-title">{s.title || "新会话"}</div>
                  <div className="drawer-item-time">
                    {s.last_active
                      ? new Date(s.last_active).toLocaleString("zh-CN")
                      : ""}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  );
}