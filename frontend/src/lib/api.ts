import type { AgentChatRequest, AgentRunSummary } from "./types";

export const API_BASE = window.location.origin + "/api";

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${path} -> ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

export async function patchJSON<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${path} -> ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

export async function deleteJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${path} -> ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

export interface Tag {
  id: number;
  database_id: string;
  name: string;
  color: string;
}

export async function listTags(databaseId: string): Promise<Tag[]> {
  return getJSON<Tag[]>(
    `/knowledge/databases/${encodeURIComponent(databaseId)}/tags`,
  );
}

export async function createTag(
  databaseId: string,
  name: string,
  color = "#FF540E",
): Promise<Tag> {
  return postJSON<Tag>(
    `/knowledge/databases/${encodeURIComponent(databaseId)}/tags`,
    { name, color },
  );
}

export async function deleteTagApi(tagId: number): Promise<void> {
  await deleteJSON(`/knowledge/tags/${tagId}`);
}

export async function assignDocTags(source: string, tagIds: number[]): Promise<void> {
  await postJSON("/knowledge/doc-tags", { source, tag_ids: tagIds });
}

export async function unassignDocTag(source: string, tagId: number): Promise<void> {
  await deleteJSON(
    `/knowledge/doc-tags/${encodeURIComponent(source)}/${tagId}`,
  );
}

export async function filterDocumentsByTags(
  databaseId: string,
  tagIds: number[],
): Promise<Array<{ source: string; tag_count: number }>> {
  return getJSON<Array<{ source: string; tag_count: number }>>(
    `/knowledge/databases/${encodeURIComponent(databaseId)}/documents?tag_ids=${tagIds.join(",")}`,
  );
}

// v1.1.0 PR#1 Task 1.3:带 cascade 选项的数据库删除包装。
// 200 -> 解析响应体(可能含 warnings[]);
// 409 -> FastAPI HTTPException(detail={...})—— 抛出 ApiError,调用方可读 detail.requires_cascade / detail.child_documents
//       决定是否弹级联确认模态;其他错误抛通用 Error。
export interface DeleteDatabaseOk {
  deleted: number;
  database_id: string;
  cascade: boolean;
  warnings: string[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly body: unknown;
  constructor(status: number, body: unknown, fallback: string) {
    super(`${status}: ${fallback}`);
    this.status = status;
    this.body = body;
    const b = body as { detail?: unknown };
    this.detail = b && typeof b === "object" && "detail" in b ? b.detail : body;
  }
}

export async function deleteDatabase(
  dbId: string,
  options?: { cascade?: boolean },
): Promise<DeleteDatabaseOk> {
  const qs = options?.cascade ? "?cascade=true" : "";
  const res = await fetch(`${API_BASE}/knowledge/databases/${encodeURIComponent(dbId)}${qs}`, {
    method: "DELETE",
  });
  const text = await res.text().catch(() => "");
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!res.ok) {
    throw new ApiError(res.status, body, text.slice(0, 200));
  }
  return body as DeleteDatabaseOk;
}

export async function uploadFile(path: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${path} -> ${res.status}: ${txt.slice(0, 200)}`);
  }
  return res.json();
}

// v1.1.0 PR#2 Task 2.4:更新会话的 history_limit 上限(后端 PATCH 端点由 T2.5 落地,
// /api/sessions/{id} body { history_limit })。当前 stub 是为了前端先解耦,等 T2.5
// 端点到位即可生效;若 T2.5 端点未到位,PATCH 会落到 FastAPI 404,由调用方捕获处理。
export async function updateSessionLimit(
  sessionId: string,
  historyLimit: number,
): Promise<void> {
  await patchJSON(`/sessions/${encodeURIComponent(sessionId)}`, {
    history_limit: historyLimit,
  });
}

// v2.0 PR#4(T13):Agent 模式 SSE 对话 — 返回原始 Response 供调用方
// 手动 reader 解析(与 App.tsx 现有 /chat 消费模式一致),事件契约见设计稿 §6.1:
// status / step_start / tool_call / tool_result / answer / error。
export async function postAgentChat(
  body: AgentChatRequest,
): Promise<Response> {
  return fetch(`${API_BASE}/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchAgentRuns(limit = 20): Promise<AgentRunSummary[]> {
  return getJSON<AgentRunSummary[]>(`/agent/runs?limit=${limit}`);
}