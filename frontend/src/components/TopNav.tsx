// TopNav + StatusBar:KB-AI 顶部导航与状态栏
// v0.8.4 从 App.tsx 拆出,降低主文件复杂度。

import {
  AlertTriangle,
  BookOpen,
  ChevronLeft,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Power,
  Settings,
  Library,
  WifiOff,
} from "lucide-react";
import type { PageId, ServiceStatus } from "../lib/types";

interface TopNavProps {
  status: ServiceStatus;
  currentPage: PageId;
  onPageChange: (p: PageId) => void;
  onToggleDrawer: () => void;
  drawerOpen: boolean;
  onShutdown: () => void;
  onBoot: () => void;
}

export function TopNav(props: TopNavProps) {
  const statusMap: Record<ServiceStatus, { label: string; dot: string }> = {
    online: { label: "在线", dot: "online" },
    degraded: { label: "降级", dot: "degraded" },
    offline: { label: "离线", dot: "offline" },
    checking: { label: "检测中", dot: "" },
  };
  const s = statusMap[props.status];
  const canBoot = props.status === "offline" || props.status === "checking";

  const navItems: { id: PageId; label: string; icon: typeof BookOpen }[] = [
    { id: "chat", label: "对话", icon: MessageSquare },
    { id: "knowledge", label: "资料库", icon: Library },
    { id: "dashboard", label: "系统", icon: LayoutDashboard },
    { id: "settings", label: "设置", icon: Settings },
  ];

  return (
    <nav className="top-nav" aria-label="主导航">
      <div className="nav-left">
        <button
          className="icon-btn"
          onClick={props.onToggleDrawer}
          aria-label={props.drawerOpen ? "关闭会话历史" : "打开会话历史"}
          aria-expanded={props.drawerOpen}
          title="会话历史"
        >
          {props.drawerOpen ? <ChevronLeft size={20} /> : <Menu size={20} />}
        </button>
        <div className="brand">
          <BookOpen size={20} />
          <span>
            KB<span className="brand-accent">-AI</span>
          </span>
        </div>
        <div className="nav-items">
          {navItems.map((it) => {
            const Icon = it.icon;
            return (
              <button
                key={it.id}
                className={`nav-item ${props.currentPage === it.id ? "active" : ""}`}
                onClick={() => props.onPageChange(it.id)}
                aria-current={props.currentPage === it.id ? "page" : undefined}
              >
                <Icon size={16} />
                <span>{it.label}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="nav-right">
        <div className="status-pill">
          <span className={`status-dot ${s.dot}`} />
          <span>{s.label}</span>
        </div>
        <button
          className="icon-btn power"
          title={canBoot ? "启动 KB-AI" : "关闭 KB-AI"}
          onClick={canBoot ? props.onBoot : props.onShutdown}
          aria-label={canBoot ? "启动 KB-AI" : "关闭 KB-AI"}
        >
          <Power size={18} />
        </button>
      </div>
    </nav>
  );
}

interface StatusBarProps {
  status: ServiceStatus;
}

export function StatusBar(props: StatusBarProps) {
  if (props.status === "online" || props.status === "checking") return null;
  const config: Partial<Record<ServiceStatus, { icon: typeof AlertTriangle; text: string }>> = {
    offline: {
      icon: WifiOff,
      text: "网络连接断了，AI 暂时回答不了。您仍然可以查看历史对话和本地资料。",
    },
    degraded: {
      icon: AlertTriangle,
      text: "已换用备用方式为您查找，回答可能来自公开网络。",
    },
  };
  const c = config[props.status];
  if (!c) return null;
  const Icon = c.icon;
  return (
    <div className={`status-bar ${props.status}`} role="alert" aria-live="assertive">
      <Icon size={16} />
      <span>{c.text}</span>
    </div>
  );
}