// Modals:ShutdownModal + BootProgressModal + ConfirmCascadeDeleteModal + 启动阶段常量
// v0.8.4 从 App.tsx 拆出;v1.1.0 PR#1 Task 1.3 加级联删除确认模态。

import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Info,
  Loader2,
  XCircle,
} from "lucide-react";

const BOOT_STAGE_ORDER = [
  "env",
  "root",
  "docker",
  "compose",
  "qdrant",
  "dify",
  "worker",
  "ready",
];
const BOOT_STAGE_LABELS: Record<string, string> = {
  env: "配置检查",
  root: "定位 U 盘根目录",
  docker: "Docker Desktop",
  compose: "启动 Docker 容器",
  qdrant: "Qdrant 向量库",
  dify: "Dify Web UI",
  worker: "dify-worker",
  ready: "启动完成",
};

interface ShutdownModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  busy?: boolean; // v0.8.6(F01):关闭进行中,禁用按钮防重复点击
}

export function ShutdownModal(props: ShutdownModalProps) {
  if (!props.open) return null;
  return (
    <div
      className="modal-overlay open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="shutdown-title"
    >
      <div className="modal">
        <h2 className="modal-header" id="shutdown-title">
          确定要关闭 AI Assistant 吗？
        </h2>
        <div className="modal-body">
          <p>关闭后：</p>
          <ul>
            <li>
              <span style={{ color: "var(--success)" }}>
                <CheckCircle2 size={16} />
              </span>
              当前会话已自动保存
            </li>
            <li>
              <span style={{ color: "var(--success)" }}>
                <CheckCircle2 size={16} />
              </span>
              AI 服务会安全停止
            </li>
            <li>
              <span style={{ color: "var(--success)" }}>
                <CheckCircle2 size={16} />
              </span>
              您可以安全弹出 U 盘
            </li>
            <li>
              <span style={{ color: "var(--warning)" }}>
                <AlertTriangle size={16} />
              </span>
              数据无云备份，仅在本地 U 盘
            </li>
            <li>
              <span style={{ color: "var(--info)" }}>
                <Info size={16} />
              </span>
              下次使用需要重新启动 KB-AI
            </li>
          </ul>
        </div>
        <div className="modal-footer">
          <button
            className="modal-btn modal-btn-outline"
            onClick={props.onClose}
            disabled={props.busy}
          >
            取消
          </button>
          <button
            className="modal-btn modal-btn-destructive"
            onClick={props.onConfirm}
            disabled={props.busy}
          >
            {props.busy ? "正在关闭…" : "确认关闭"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface BootProgressModalProps {
  open: boolean;
  currentStage: string;
  percent: number;
  message: string;
  error: string | null;
  done: boolean;
  onClose: () => void;
  onRetry: () => void;
}

export function BootProgressModal(props: BootProgressModalProps) {
  if (!props.open) return null;
  const isRunning = !props.done && !props.error;
  const currentIndex = BOOT_STAGE_ORDER.indexOf(props.currentStage);

  return (
    <div
      className="modal-overlay open"
      role="dialog"
      aria-modal="true"
      aria-labelledby="boot-title"
    >
      <div className="modal boot-modal">
        <h2 className="modal-header" id="boot-title">
          {props.done ? "启动完成" : props.error ? "启动失败" : "正在启动 KB-AI"}
        </h2>
        <div className="modal-body">
          <div className="boot-current">
            <div className={`boot-current-icon ${isRunning ? "spin" : ""}`}>
              {props.error ? (
                <AlertCircle size={22} />
              ) : props.done ? (
                <CheckCircle2 size={22} />
              ) : (
                <Loader2 size={22} />
              )}
            </div>
            <div className="boot-current-text">
              <div className="boot-current-label">当前阶段</div>
              <div className="boot-current-message">
                {props.message || "准备中..."}
              </div>
            </div>
          </div>

          <div className="boot-progress-track" aria-hidden="true">
            <div
              className="boot-progress-bar"
              style={{ width: `${props.percent}%` }}
            />
          </div>

          <div className="boot-stages">
            {BOOT_STAGE_ORDER.map((stage, idx) => {
              let state = "pending";
              if (props.done) state = "done";
              else if (props.error && idx === currentIndex) state = "error";
              else if (idx < currentIndex) state = "done";
              else if (idx === currentIndex) state = "active";

              const statusText =
                state === "done"
                  ? "完成"
                  : state === "error"
                  ? "失败"
                  : state === "active"
                  ? "进行中"
                  : "等待";

              return (
                <div key={stage} className={`boot-stage ${state}`}>
                  <div className="boot-stage-icon">
                    {state === "done" ? (
                      <CheckCircle2 size={18} />
                    ) : state === "error" ? (
                      <XCircle size={18} />
                    ) : state === "active" ? (
                      <Loader2 size={18} className="spin" />
                    ) : (
                      <Circle size={18} />
                    )}
                  </div>
                  <div className="boot-stage-name">{BOOT_STAGE_LABELS[stage]}</div>
                  <div className="boot-stage-status">{statusText}</div>
                </div>
              );
            })}
          </div>

          {props.error && (
            <div className="boot-error" role="alert">
              {props.error}
            </div>
          )}
        </div>
        <div className="boot-footer">
          {props.error ? (
            <>
              <button
                className="modal-btn modal-btn-outline"
                onClick={props.onClose}
              >
                关闭
              </button>
              <button
                className="modal-btn modal-btn-destructive"
                onClick={props.onRetry}
              >
                重试启动
              </button>
            </>
          ) : props.done ? (
            <button
              className="modal-btn modal-btn-destructive"
              onClick={props.onClose}
            >
              进入系统
            </button>
          ) : (
            <button
              className="modal-btn modal-btn-outline"
              onClick={props.onClose}
            >
              后台运行
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// v1.1.0 PR#1 Task 1.3:删除有子文档的数据库时的二次确认模态。
// 触发路径:KnowledgePage.handleDeleteDatabase -> DELETE 返回 409 + requires_cascade=true
// 确认后调用方需自行以 cascade=true 重试。
interface ConfirmCascadeDeleteModalProps {
  open: boolean;
  databaseName: string;
  childDocuments: number;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmCascadeDeleteModal({
  open,
  databaseName,
  childDocuments,
  busy,
  onCancel,
  onConfirm,
}: ConfirmCascadeDeleteModalProps) {
  if (!open) return null;
  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cascade-delete-title"
    >
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-title" id="cascade-delete-title">
          确认级联删除?
        </div>
        <p style={{ fontSize: 14, color: "var(--text)", lineHeight: 1.6 }}>
          数据库 <strong>{databaseName}</strong> 仍有{" "}
          <strong>{childDocuments}</strong> 个文档。
        </p>
        <p className="modal-warning">
          删除将同时清除该数据库的 Qdrant collection、keyword 索引、tag 关联、processing_state
          记录。此操作不可恢复。
        </p>
        <div className="modal-actions">
          <button className="modal-btn" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            className="modal-btn primary"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "删除中..." : "确认级联删除"}
          </button>
        </div>
      </div>
    </div>
  );
}