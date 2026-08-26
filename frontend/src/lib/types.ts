export type PageId = "chat" | "knowledge" | "settings" | "dashboard";
export type ServiceStatus = "online" | "degraded" | "offline" | "checking";

export interface Citation {
  index: number;
  source: string;
  snippet: string;
  score?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  time?: string;
  citations?: Citation[];
  isStreaming?: boolean;
  // v0.8.8(UX):等待可视化 — 后端 status 事件的阶段轨迹 + 起始时间戳
  stages?: string[];
  statusStartedAt?: number;
  // v1.1.0 PR#3:图片附件路径(后端返回的相对路径列表)
  image_paths?: string[];
  // v1.1.0 PR#3 Task 3.4:多选题选项(REQ-5)
  options?: string[];
  question_type?: 'single_choice' | 'multi_choice';
  // v1.1.0 PR#3 Task 3.5:反问上下文 — 当 assistant 走 clarify 路径时由 App
  // 注入,original_question 是当时发给后端的原问题(供 SkipClarificationButton 渲染)。
  clarification?: { original_question?: string };
}

export interface Session {
  session_id: string;
  title?: string;
  last_active?: string;
  // v1.1.0 PR#2 Task 2.4:history_limit(REQ-6,默认 50)。来自 SQLite sessions 表
  // (T2.1 后端 ALTER TABLE 加列 + DEFAULT 50),list_sessions / get_session
  // 通过 SELECT * 返回,前端用 updateSessionLimit 写回。
  history_limit?: number;
}

export interface Document {
  source: string;
  chunk_count: number;
  doc_id: string;
  database_id?: string;
}

export interface UploadTask {
  task_id: string;
  filename: string;
  status: "pending" | "parsing" | "embedding" | "done" | "failed";
  stage: string;
  error?: string;
  chunk_count?: number;
  database_id?: string;
}

export interface Database {
  id: string;
  name: string;
  description?: string;
  collection: string;
  embed_model: string;
  chunk_size: number;
  chunk_overlap: number;
  created_at: string;
  document_count?: number;
}

// v0.8.11(P1.6):Dashboard 类型
export interface DashboardHealth {
  online: boolean;
  endpoints: Record<string, boolean>;
}
export interface DashboardDegradation {
  component: string;
  count: number;
}
export interface DashboardKBStats {
  database_count: number;
  document_count: number;
  chunk_count: number;
  databases: Array<{ id: string; name: string; document_count: number }>;
}
export interface DashboardDrift {
  qdrant_points: number;
  keyword_chunks: number;
  drift: number;
  ok: boolean;
  per_db?: Array<{ id: string; name: string; collection: string; qdrant_points: number | null }>;
  error?: string;
}
export interface DashboardSystem {
  version: string;
  uptime_seconds?: number;
  data_dir_size_mb?: number;
}

/**
 * v1.3.0: cost-alert 月度配额告警字段。
 * 从 GET /api/dashboard/overview 返回,缺失时降级为 "用量数据采集中"。
 */
export interface CostAlert {
  level: 0 | 1 | 2 | 3;
  today_yuan: number;
  month_yuan: number;
  month: string; // YYYY-MM
  thresholds: {
    warn: number;
    high: number;
    block: number;
  };
  updated_at: string; // ISO8601
}

export interface DashboardOverview {
  health: DashboardHealth;
  degradations_24h: DashboardDegradation[];
  kb_stats: DashboardKBStats;
  drift: DashboardDrift;
  system: DashboardSystem;
  cost_alert?: CostAlert; // v1.3.0
  timestamp: string;
}

// v0.8.11(P2.1):Eval 类型
export interface EvalCaseResult {
  question: string;
  expect_source: string;
  expect_keywords?: string[];
  ok: boolean;
  detail: string;
}
export interface EvalResult {
  dataset: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  duration_seconds: number;
  results: EvalCaseResult[];
  timestamp: string;
  base_url: string;
  top_k: number;
  error?: string;
}
export interface EvalStatus {
  status: "idle" | "running" | "done" | "failed";
  started_at: number | null;
  finished_at: number | null;
  has_result: boolean;
  error: string | null;
}
export interface EvalResultsResponse {
  result: EvalResult | null;
  status: EvalStatus["status"];
  started_at: number | null;
  finished_at: number | null;
  error: string | null;
}

export interface BootStageState {
  stage: string;
  message: string;
  percent: number;
  done?: boolean;
  error?: boolean;
}

export interface StatusConfig {
  ALIYUN_BAILIAN_API_KEY?: { configured: boolean; source: string };
  TAVILY_API_KEY?: { configured: boolean; source: string };
  BING_SEARCH_API_KEY?: { configured: boolean; source: string };
}

export interface StatusModelConfig {
  name: string;
  name_max: string;
  routing_enabled: boolean;
}

export interface StatusResponse {
  health: { online: boolean; websearch_available: boolean; endpoints: Record<string, boolean> };
  config: {
    root: string;
    env: StatusConfig;
    model: StatusModelConfig;
  };
  version: { version: string; container: { state: string; running: number; total: number } };
}