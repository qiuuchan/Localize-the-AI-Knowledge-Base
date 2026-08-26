// SettingsPage:系统设置页面(服务状态 / API Key / 模型 / 路径 / 会话历史上限)
// v0.8.4 从 App.tsx 拆出;v1.1.0 PR#2 Task 2.4 加 history_limit 选择器。

import { useEffect, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Cpu,
  FolderOpen,
  History,
  Key,
  XCircle,
} from "lucide-react";
import { getJSON, updateSessionLimit } from "../lib/api";
import type { ServiceStatus, Session, StatusResponse } from "../lib/types";

interface SettingsPageProps {
  status: ServiceStatus;
  // v1.1.0 PR#2 Task 2.4:history_limit 选择器要直接读写当前会话;App 已有
  // currentSessionId + sessions 状态(sessions 来自 /api/sessions SELECT *,
  // 已含 history_limit)一并传过来,避免 SettingsPage 再发一次 GET。
  currentSession: Session | null;
  // PATCH 成功后 App.tsx 重新拉一遍 sessions 列表,保持 drawer 同步。
  onSessionUpdated: () => void;
}

// v1.1.0 PR#2 Task 2.4:history_limit 4 档(10/20/50/100),T2.1/2.3 + chat.py:58
// 已约束 backend chat 字段在 [1, 100],且 session.history_limit 默认 50。
const HISTORY_LIMIT_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 10, label: "10 轮" },
  { value: 20, label: "20 轮" },
  { value: 50, label: "50 轮(默认)" },
  { value: 100, label: "100 轮" },
];
const DEFAULT_HISTORY_LIMIT = 50;

function KeyBadge(props: { configured?: boolean }) {
  if (props.configured === undefined) {
    return <span className="status-badge bad">未知</span>;
  }
  return props.configured ? (
    <span className="status-badge ok">
      <CheckCircle2 size={12} /> 已配置
    </span>
  ) : (
    <span className="status-badge bad">
      <XCircle size={12} /> 待填写
    </span>
  );
}

export function SettingsPage(props: SettingsPageProps) {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  // v1.1.0 PR#2 Task 2.4:history_limit 本地副本 — 用 props 初始填充,user 改下拉
  // 即触发 PATCH;loading 用于 PATCH in-flight 防双击提交。Session 没就绪时用
  // DEFAULT_HISTORY_LIMIT 占位,不暴露"未选"歧义。
  const [historyLimit, setHistoryLimit] = useState<number>(
    props.currentSession?.history_limit ?? DEFAULT_HISTORY_LIMIT,
  );
  const [historyLimitSaving, setHistoryLimitSaving] = useState(false);
  const [historyLimitError, setHistoryLimitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const json = await getJSON<StatusResponse>("/status");
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // v1.1.0 PR#2 Task 2.4:切换会话时同步 history_limit 本地副本(否则下拉仍指旧会话)。
  useEffect(() => {
    if (props.currentSession) {
      setHistoryLimit(props.currentSession.history_limit ?? DEFAULT_HISTORY_LIMIT);
      setHistoryLimitError(null);
    }
  }, [props.currentSession?.session_id, props.currentSession?.history_limit]);

  // v1.1.0 PR#2 Task 2.4:用户切换下拉 → PATCH → App 重新拉 sessions。失败时本地
  // 回滚 + 提示;不阻断用户,毕竟手动改回下拉即可。
  const onHistoryLimitChange = async (next: number) => {
    const prev = historyLimit;
    if (next === prev) return;
    setHistoryLimit(next);
    if (!props.currentSession) {
      setHistoryLimitError("请先创建或选择会话");
      return;
    }
    setHistoryLimitSaving(true);
    setHistoryLimitError(null);
    try {
      await updateSessionLimit(props.currentSession.session_id, next);
      props.onSessionUpdated();
    } catch (e: any) {
      setHistoryLimit(prev);
      setHistoryLimitError(
        `更新失败: ${e?.message || "未知错误"} (后端 PATCH 端点可能在 T2.5 落地)`,
      );
    } finally {
      setHistoryLimitSaving(false);
    }
  };

  const healthMap: Record<ServiceStatus, { label: string; variant: string }> = {
    online: { label: "在线", variant: "ok" },
    degraded: { label: "降级", variant: "warn" },
    offline: { label: "离线", variant: "bad" },
    checking: { label: "检测中", variant: "warn" },
  };
  const h = healthMap[props.status];

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-eyebrow">[ System Config ]</div>
        <h1 className="page-title">系统设置</h1>
      </div>
      <div className="page-content">
        <div className="settings-card">
          <div className="settings-card-title">
            <Activity size={16} /> 服务状态
          </div>
          <div className="settings-row">
            <span className="settings-label">前端状态</span>
            <span className="settings-value">
              <span className={`status-badge ${h.variant}`}>{h.label}</span>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">后端版本</span>
            <span className="settings-value">
              {loading ? "..." : data?.version?.version || "未知"}
            </span>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-card-title">
            <Key size={16} /> API Key
          </div>
          {loading ? (
            <div className="settings-value muted">加载中...</div>
          ) : data?.config?.env ? (
            <div className="key-grid">
              <span className="key-grid-label">阿里云百炼 (LLM + Embedding)</span>
              <KeyBadge configured={data.config.env.ALIYUN_BAILIAN_API_KEY?.configured} />
              <span className="key-grid-label">Tavily 搜索</span>
              <KeyBadge configured={data.config.env.TAVILY_API_KEY?.configured} />
              <span className="key-grid-label">Bing 搜索</span>
              <KeyBadge configured={data.config.env.BING_SEARCH_API_KEY?.configured} />
            </div>
          ) : (
            <div className="settings-value muted">无法读取配置状态</div>
          )}
          <div
            className="settings-row"
            style={{ marginTop: 12, paddingBottom: 0, borderBottom: "none" }}
          >
            <span className="settings-label" style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Key 值不会在前端显示。如需修改，请编辑 .env 文件。
            </span>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-card-title">
            <Cpu size={16} /> 模型配置
          </div>
          <div className="settings-row">
            <span className="settings-label">默认模型</span>
            <span className="settings-value">
              {loading ? "..." : data?.config?.model?.name || "qwen3.6-plus"}
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">复杂问题模型</span>
            <span className="settings-value">
              {loading ? "..." : data?.config?.model?.name_max || "qwen3.7-max"}
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">模型路由</span>
            <span className="settings-value">
              {loading
                ? "..."
                : data?.config?.model?.routing_enabled
                ? "已启用"
                : "未启用"}
            </span>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-card-title">
            <FolderOpen size={16} /> 项目路径
          </div>
          <div className="settings-row">
            <span className="settings-label">U 盘根目录</span>
            <span
              className="settings-value muted"
              style={{
                maxWidth: "60%",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {loading ? "..." : data?.config?.root || "未知"}
            </span>
          </div>
        </div>

        {/* v1.1.0 PR#2 Task 2.4:history_limit 选择器(REQ-6 单会话软上限)。
            当前会话没就绪时显示提示而非空下拉,避免歧义;后端 PATCH 由 T2.5 落地,
            若后端未到位 SettingsPage 会把错误显示在 hint 行,不静默失败。 */}
        <div className="settings-card">
          <div className="settings-card-title">
            <History size={16} /> 会话设置
          </div>
          <div className="settings-row">
            <span className="settings-label">单会话历史轮数上限</span>
            <span className="settings-value">
              {props.currentSession ? (
                <select
                  id="history-limit"
                  className="select-input"
                  value={historyLimit}
                  onChange={(e) => onHistoryLimitChange(Number(e.target.value))}
                  disabled={historyLimitSaving}
                  aria-label="单会话历史轮数上限"
                >
                  {HISTORY_LIMIT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="settings-value muted">先去对话页创建或选个会话</span>
              )}
            </span>
          </div>
          <div
            className="settings-row"
            style={{ paddingTop: 0, borderBottom: "none" }}
          >
            <span
              className="settings-label"
              style={{ fontSize: 12, color: "var(--text-muted)" }}
            >
              {historyLimitError ? (
                <span style={{ color: "var(--error)" }}>{historyLimitError}</span>
              ) : (
                <>
                  当前会话「
                  {props.currentSession?.title || props.currentSession?.session_id || "—"}
                  」 · 超出后保留最近 N 条喂给 AI(由 chat.py:58 history_limit 字段生效)
                </>
              )}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}