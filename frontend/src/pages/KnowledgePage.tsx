// KnowledgePage:资料库页面(上传 / 列表 / 删除 + 数据库 sidebar)
// v0.8.4 从 App.tsx 拆出;v0.8.11(P1.1) 加 database sidebar;
// v1.1.0 PR#1 Task 1.3 — 删除分类有子文档时弹 ConfirmCascadeDeleteModal,DELETE 成功后展示 warnings 横幅。
// v1.1.0 PR#2 Task 2.4 — 多文件上传 + 客户端硬限(20MB / 5 张)提前拦截,避免大文件落库/进 Qdrant。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Clock,
  FileText,
  FolderPlus,
  Loader2,
  Tag as TagIcon,
  Trash2,
  UploadCloud,
} from "lucide-react";
import * as api from "../lib/api";
import {
  ApiError,
  deleteDatabase,
  deleteJSON,
  getJSON,
  patchJSON,
  postJSON,
  uploadFile,
} from "../lib/api";
import type { DeleteDatabaseOk } from "../lib/api";
import type { Database, Document, UploadTask } from "../lib/types";
import { ConfirmCascadeDeleteModal } from "../components/Modals";
import { TagChip } from "../components/TagChip";
import { TagPicker } from "../components/TagPicker";

const DEFAULT_DB_ID = "default";
const FILTER_SOURCE = "__filter__";

// v1.1.0 PR#2 Task 2.4:与后端 knowledge.py:70-71 一致的客户端硬限,选文件阶段立刻拦截,
// 避免大文件进 background pipeline 才被 413 拒。值与后端 MAX_IMAGE_BYTES /
// MAX_IMAGE_COUNT_PER_UPLOAD 同步变化 — 改一处必须改两处。
const MAX_IMAGE_BYTES = 20 * 1024 * 1024; // 20 MB
const MAX_IMAGE_COUNT = 5;

function sourceForDatabase(source: string, databaseId: string): string {
  if (databaseId === DEFAULT_DB_ID || source.includes("::")) return source;
  return `${databaseId}::${source}`;
}

// v1.1.0 PR#1 Task 1.3:级联删除目标 — DELETE 返回 409 + requires_cascade 时填入,弹模态让用户二次确认
interface CascadeTarget {
  dbId: string;
  dbName: string;
  childDocuments: number;
}

// v1.1.0 PR#1 Task 1.3:DELETE 成功后,warnings[] 非空时用横幅展示(Qdrant 清理失败等降级路径)
interface DeleteWarning {
  dbId: string;
  dbName: string;
  warnings: string[];
}

export function KnowledgePage() {
  const [databases, setDatabases] = useState<Database[]>([]);
  const [activeDbId, setActiveDbId] = useState<string>(DEFAULT_DB_ID);
  const [docs, setDocs] = useState<Document[]>([]);
  const [tags, setTags] = useState<api.Tag[]>([]);
  const [filterTagIds, setFilterTagIds] = useState<number[]>([]);
  const [filteredSources, setFilteredSources] = useState<Set<string> | null>(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [pickerOpen, setPickerOpen] = useState<{ source: string } | null>(null);
  const [showNewTagInput, setShowNewTagInput] = useState(false);
  const [newTagName, setNewTagName] = useState("");
  const [creatingTag, setCreatingTag] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [showNewDbModal, setShowNewDbModal] = useState(false);
  const [newDbName, setNewDbName] = useState("");
  const [newDbDesc, setNewDbDesc] = useState("");
  const [creatingDb, setCreatingDb] = useState(false);
  // v1.1.0 PR#1 Task 1.3:级联删除二次确认 + warnings 横幅
  const [cascadeTarget, setCascadeTarget] = useState<CascadeTarget | null>(null);
  const [cascadeBusy, setCascadeBusy] = useState(false);
  const [deleteWarning, setDeleteWarning] = useState<DeleteWarning | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const showWarningsIfAny = (
    result: DeleteDatabaseOk,
    target: Pick<DeleteWarning, "dbId" | "dbName">,
  ) => {
    if (result.warnings && result.warnings.length > 0) {
      setDeleteWarning({ ...target, warnings: result.warnings });
    }
  };

  const loadDatabases = useCallback(async () => {
    try {
      const data = await getJSON<Database[]>("/knowledge/databases");
      setDatabases(data || []);
      // 保证 activeDbId 始终在列表里
      setActiveDbId((prev) => {
        if (data && data.some((d) => d.id === prev)) return prev;
        return DEFAULT_DB_ID;
      });
    } catch (e) {
      console.error("加载数据库列表失败:", e);
    }
  }, []);

  const loadDocs = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getJSON<Document[]>(
        `/knowledge/documents?database_id=${encodeURIComponent(activeDbId)}`,
      );
      setDocs(data || []);
    } catch (e) {
      console.error("加载资料库失败:", e);
      setDocs([]);
    } finally {
      setLoading(false);
    }
  }, [activeDbId]);

  const loadTags = useCallback(async () => {
    try {
      const data = await api.listTags(activeDbId);
      setTags(data || []);
    } catch (e) {
      console.error("加载标签列表失败:", e);
      setTags([]);
    }
  }, [activeDbId]);

  useEffect(() => {
    loadTags();
    setFilterTagIds([]);
    setFilteredSources(null);
    setPickerOpen(null);
    setShowNewTagInput(false);
  }, [loadTags]);

  useEffect(() => {
    if (filterTagIds.length === 0) {
      setFilteredSources(null);
      setFilterLoading(false);
      return;
    }

    let cancelled = false;
    setFilterLoading(true);
    api
      .filterDocumentsByTags(activeDbId, filterTagIds)
      .then((matches) => {
        if (!cancelled) setFilteredSources(new Set(matches.map((item) => item.source)));
      })
      .catch((e) => {
        console.error("按标签过滤资料失败:", e);
        if (!cancelled) setFilteredSources(new Set());
      })
      .finally(() => {
        if (!cancelled) setFilterLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeDbId, filterTagIds]);

  const visibleDocs = useMemo(() => {
    if (filterTagIds.length === 0 || !filteredSources) return filterTagIds.length ? [] : docs;
    return docs.filter((doc) => {
      const source = sourceForDatabase(doc.source, activeDbId);
      return filteredSources.has(doc.source) || filteredSources.has(source);
    });
  }, [activeDbId, docs, filterTagIds, filteredSources]);

  useEffect(() => {
    loadDatabases();
  }, [loadDatabases]);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  useEffect(() => {
    const pending = tasks.filter(
      (t) => t.status === "pending" || t.status === "parsing" || t.status === "embedding",
    );
    if (pending.length === 0) return;
    const interval = setInterval(async () => {
      const updated = await Promise.all(
        pending.map(async (t) => {
          try {
            const r = await getJSON<UploadTask>(`/knowledge/tasks/${t.task_id}`);
            return r;
          } catch {
            return null;
          }
        }),
      );
      setTasks((prev) => {
        const map = new Map(
          updated.filter((u): u is UploadTask => u !== null).map((t) => [t.task_id, t]),
        );
        return prev.map((t) => map.get(t.task_id) ?? t);
      });
    }, 2000);
    return () => clearInterval(interval);
  }, [tasks]);

  useEffect(() => {
    if (tasks.some((t) => t.status === "done")) {
      loadDocs();
      loadDatabases();
    }
  }, [tasks, loadDocs, loadDatabases]);

  // v1.1.0 PR#2 Task 2.4:多文件上传 + 客户端硬限(T2.2 后端契约同步)
  // - files.length ≤ MAX_IMAGE_COUNT;超量即时 toast,不入网络
  // - 单 file ≤ MAX_IMAGE_BYTES;超量逐文件名提示
  // - form.append 用复数 key "files"(T2.2 后端 `files: List[UploadFile]`)
  // - 响应解析为 UploadTask[],每文件一个 task descriptor
  const handleFiles = async (files: File[]) => {
    if (!files || files.length === 0) return;
    if (files.length > MAX_IMAGE_COUNT) {
      alert(`最多 ${MAX_IMAGE_COUNT} 张/次,当前 ${files.length} 张`);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    const oversize = files.filter((f) => f.size > MAX_IMAGE_BYTES);
    if (oversize.length > 0) {
      const names = oversize
        .map((f) => `${f.name} (${(f.size / (1024 * 1024)).toFixed(1)} MB)`)
        .join(", ");
      alert(`单文件 ≤ 20 MB,以下文件超限: ${names}`);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      for (const f of files) form.append("files", f);
      const res = await fetch(
        `${window.location.origin}/api/knowledge/upload?database_id=${encodeURIComponent(activeDbId)}`,
        { method: "POST", body: form },
      );
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(`${res.status}: ${txt.slice(0, 200)}`);
      }
      const data = (await res.json()) as UploadTask[];
      setTasks((prev) => [...prev, ...data]);
    } catch (e: any) {
      alert("上传失败:" + (e?.message || "未知错误"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleDelete = async (source: string) => {
    const display = source.split(" §")[0];
    if (!window.confirm(`确定要删除「${display}」及其所有 chunks 吗？此操作不可恢复。`)) return;
    try {
      await deleteJSON(
        `/knowledge/documents/${encodeURIComponent(source)}?database_id=${encodeURIComponent(activeDbId)}`,
      );
      loadDocs();
      loadDatabases();
    } catch (e: any) {
      alert("删除失败:" + (e?.message || "未知错误"));
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = e.dataTransfer.files
      ? Array.from(e.dataTransfer.files)
      : [];
    if (files.length > 0) handleFiles(files);
  };

  const handleCreateDatabase = async () => {
    const name = newDbName.trim();
    if (!name) {
      alert("请填写分类名称");
      return;
    }
    // 派生 id: 用拼音/英文有困难,简化为去空格 + 时间戳后缀
    const slug =
      name
        .replace(/\s+/g, "_")
        .replace(/[^\w\u4e00-\u9fa5-]/g, "")
        .slice(0, 16) +
      "_" +
      Date.now().toString(36).slice(-4);
    setCreatingDb(true);
    try {
      await postJSON("/knowledge/databases", {
        id: slug,
        name,
        description: newDbDesc,
      });
      setShowNewDbModal(false);
      setNewDbName("");
      setNewDbDesc("");
      await loadDatabases();
      setActiveDbId(slug);
    } catch (e: any) {
      alert("新建分类失败:" + (e?.message || "未知错误"));
    } finally {
      setCreatingDb(false);
    }
  };

  const handleCreateTag = async () => {
    const name = newTagName.trim();
    if (!name) return;
    setCreatingTag(true);
    try {
      const tag = await api.createTag(activeDbId, name);
      setTags((prev) => [...prev, tag].sort((a, b) => a.name.localeCompare(b.name)));
      setNewTagName("");
      setShowNewTagInput(false);
    } catch (e: any) {
      alert("新建标签失败:" + (e?.message || "未知错误"));
    } finally {
      setCreatingTag(false);
    }
  };

  const handleDeleteTag = async (tagId: number) => {
    try {
      await api.deleteTagApi(tagId);
      setTags((prev) => prev.filter((tag) => tag.id !== tagId));
      setFilterTagIds((prev) => prev.filter((id) => id !== tagId));
    } catch (e: any) {
      alert("删除标签失败:" + (e?.message || "未知错误"));
    }
  };

  const handleTagPickerConfirm = async (selectedIds: number[]) => {
    const picker = pickerOpen;
    if (!picker) return;
    try {
      if (picker.source === FILTER_SOURCE) {
        setFilterTagIds(selectedIds);
      } else {
        await api.assignDocTags(sourceForDatabase(picker.source, activeDbId), selectedIds);
      }
      setPickerOpen(null);
    } catch (e: any) {
      alert("保存标签失败:" + (e?.message || "未知错误"));
    }
  };

  const handleRenameDatabase = async (db: Database) => {
    const next = window.prompt("新分类名称", db.name);
    if (!next || next.trim() === db.name) return;
    try {
      await patchJSON(`/knowledge/databases/${encodeURIComponent(db.id)}`, {
        name: next.trim(),
      });
      loadDatabases();
    } catch (e: any) {
      alert("重命名失败:" + (e?.message || "未知错误"));
    }
  };

  // v1.1.0 PR#1 Task 1.3:首次尝试 cascade=false;若后端返回 409 + requires_cascade=true
  // 弹 ConfirmCascadeDeleteModal 让用户二次确认,确认后再以 cascade=true 重试。
  const handleDeleteDatabase = async (db: Database) => {
    if (db.id === DEFAULT_DB_ID) {
      alert("默认分类不可删除");
      return;
    }
    setDeleteWarning(null);
    try {
      const result = await deleteDatabase(db.id);
      showWarningsIfAny(result, { dbId: db.id, dbName: db.name });
      // 200:无子文档,直接删了
      if (activeDbId === db.id) setActiveDbId(DEFAULT_DB_ID);
      await loadDatabases();
      loadDocs();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const detail = e.detail as {
          requires_cascade?: boolean;
          child_documents?: number;
        };
        if (detail?.requires_cascade) {
          setCascadeTarget({
            dbId: db.id,
            dbName: db.name,
            childDocuments: detail.child_documents ?? 0,
          });
          return;
        }
      }
      alert("删除失败:" + (e instanceof Error ? e.message : String(e)));
    }
  };

  // v1.1.0 PR#1 Task 1.3:用户点击模态"确认级联删除"—— 以 cascade=true 重试 DELETE
  const handleCascadeConfirm = async () => {
    const target = cascadeTarget;
    if (!target) return;
    setCascadeBusy(true);
    try {
      const result = await deleteDatabase(target.dbId, { cascade: true });
      showWarningsIfAny(result, target);
      if (activeDbId === target.dbId) setActiveDbId(DEFAULT_DB_ID);
      setCascadeTarget(null);
      await loadDatabases();
      loadDocs();
    } catch (e) {
      // 后端 200 + warnings 之外的错误(Qdrant 路由异常等)—— 关模态弹错
      setCascadeTarget(null);
      alert("级联删除失败:" + ((e as Error)?.message || "未知错误"));
    } finally {
      setCascadeBusy(false);
    }
  };

  const activeDb = databases.find((d) => d.id === activeDbId);

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-eyebrow">[ Knowledge Base ]</div>
        <h1 className="page-title">资料库</h1>
      </div>
      <div className="page-content knowledge-layout">
        {/* v1.1.0 PR#1 Task 1.3:级联删除后展示降级警告(Qdrant 清理失败等) */}
        {deleteWarning && (
          <div
            className="delete-warnings"
            role="status"
            aria-live="polite"
            style={{ marginBottom: 12 }}
          >
            <strong>「{deleteWarning.dbName}」已删除,但有降级警告:</strong>
            <ul>
              {deleteWarning.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
            <button
              className="modal-btn"
              style={{ marginTop: 8 }}
              onClick={() => setDeleteWarning(null)}
            >
              我知道了
            </button>
          </div>
        )}
        {/* v0.8.11(P1.1):database sidebar */}
        <aside className="knowledge-sidebar">
          <div className="sidebar-title">分类</div>
          <div className="sidebar-list">
            {databases.map((db) => (
              <button
                key={db.id}
                className={`sidebar-item ${db.id === activeDbId ? "active" : ""}`}
                onClick={() => setActiveDbId(db.id)}
                aria-current={db.id === activeDbId ? "true" : undefined}
              >
                <div className="sidebar-item-name">{db.name}</div>
                <div className="sidebar-item-meta">
                  {db.document_count ?? 0} 份 · {db.id}
                </div>
              </button>
            ))}
          </div>
          <button
            className="sidebar-new-btn"
            onClick={() => setShowNewDbModal(true)}
            title="新建分类"
          >
            <FolderPlus size={14} /> 新建分类
          </button>
          {activeDb && activeDb.id !== DEFAULT_DB_ID && (
            <div className="sidebar-actions">
              <button
                className="sidebar-action-btn"
                onClick={() => handleRenameDatabase(activeDb)}
              >
                重命名
              </button>
              <button
                className="sidebar-action-btn danger"
                onClick={() => handleDeleteDatabase(activeDb)}
              >
                删除分类
              </button>
            </div>
          )}
          <div
            className="sidebar-tags-section"
            style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 2 }}
          >
            <div
              className="sidebar-tags-header"
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
            >
              <div className="sidebar-title" style={{ padding: "4px 0" }}>
                标签
              </div>
              <button
                className="modal-btn"
                onClick={() => setShowNewTagInput((open) => !open)}
                type="button"
              >
                + 新建
              </button>
            </div>
            {showNewTagInput && (
              <form
                className="modal-label"
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleCreateTag();
                }}
                style={{ display: "flex", flexDirection: "row", gap: 6, margin: "4px 0 10px" }}
              >
                <input
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  placeholder="标签名称"
                  maxLength={64}
                  autoFocus
                  style={{ minWidth: 0, flex: 1 }}
                />
                <button
                  className="modal-btn primary"
                  type="submit"
                  disabled={creatingTag || !newTagName.trim()}
                  style={{ flexShrink: 0 }}
                >
                  {creatingTag ? "..." : "确定"}
                </button>
              </form>
            )}
            <div
              className="sidebar-tags-list"
              style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "4px 0" }}
            >
              {tags.length > 0 ? (
                tags.map((tag) => (
                  <TagChip
                    key={tag.id}
                    id={tag.id}
                    name={tag.name}
                    color={tag.color}
                    mode="removable"
                    onRemove={(id) => void handleDeleteTag(id)}
                  />
                ))
              ) : (
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>暂无标签</span>
              )}
            </div>
          </div>
        </aside>

        {/* 主区 */}
        <main className="knowledge-main">
          <div
            className="doc-filter-bar"
            style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}
          >
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>标签筛选</span>
            {filterTagIds.map((id) => {
              const tag = tags.find((item) => item.id === id);
              if (!tag) return null;
              return (
                <TagChip
                  key={id}
                  id={id}
                  name={tag.name}
                  color={tag.color}
                  mode="removable"
                  onRemove={() => setFilterTagIds((prev) => prev.filter((item) => item !== id))}
                />
              );
            })}
            {filterTagIds.length > 0 && (
              <button
                className="modal-btn"
                onClick={() => setFilterTagIds([])}
                type="button"
              >
                清除
              </button>
            )}
            <button
              className="modal-btn primary"
              onClick={() => setPickerOpen({ source: FILTER_SOURCE })}
              type="button"
              disabled={tags.length === 0}
            >
              + 加过滤
            </button>
          </div>
          <div className="knowledge-toolbar">
            <span className="knowledge-count">
              {activeDb ? `${activeDb.name} · ` : ""}共 {visibleDocs.length} 份已入库资料
            </span>
          </div>

          <div
            className={`upload-zone ${dragOver ? "drag-over" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
            <input
              type="file"
              ref={fileRef}
              multiple
              onChange={(e) => {
                const files = e.target.files ? Array.from(e.target.files) : [];
                if (files.length > 0) handleFiles(files);
              }}
              accept=".pdf,.docx,.pptx,.xlsx,.txt,.md"
              disabled={uploading}
            />
            <div className="upload-zone-icon">
              {uploading ? (
                <Loader2 size={32} className="spin" />
              ) : (
                <UploadCloud size={32} />
              )}
            </div>
            <div className="upload-zone-title">
              {uploading ? "正在上传..." : `上传到「${activeDb?.name ?? activeDbId}」`}
            </div>
            <div className="upload-zone-hint">
              支持 PDF / Word / PPT / Excel / TXT / Markdown · 单次最多 {MAX_IMAGE_COUNT} 张,
              单个 ≤ 20 MB
            </div>
          </div>

          {tasks.length > 0 && (
            <div className="settings-card">
              <div className="settings-card-title">
                <Clock size={16} /> 处理任务
              </div>
              <div className="doc-list">
                {tasks.map((t) => (
                  <div key={t.task_id} className="doc-card">
                    <div className="doc-icon">
                      <FileText size={20} />
                    </div>
                    <div className="doc-info">
                      <div className="doc-title">{t.filename}</div>
                      <div className="doc-meta">
                        {t.stage}
                        {t.error ? ` · ${t.error}` : ""}
                      </div>
                    </div>
                    <span
                      className={`status-badge ${
                        t.status === "done"
                          ? "ok"
                          : t.status === "failed"
                          ? "bad"
                          : "warn"
                      }`}
                    >
                      {t.status === "done"
                        ? "完成"
                        : t.status === "failed"
                        ? "失败"
                        : "处理中"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading || filterLoading ? (
            <div className="settings-card">
              <div className="skeleton-line" style={{ width: "40%" }} />
              <div className="skeleton-line" style={{ width: "70%", marginTop: 12 }} />
            </div>
          ) : visibleDocs.length === 0 ? (
            <div className="coming-soon" style={{ minHeight: 240 }}>
              <div
                className="empty-rings"
                aria-hidden="true"
                style={{ width: 100, height: 100 }}
              >
                <div className="ring" />
                <div className="ring" />
                <div className="ring-core" />
              </div>
              <h2 style={{ fontSize: 18 }}>
                {filterTagIds.length > 0 ? "没有匹配的资料" : "暂无已入库资料"}
              </h2>
              <p>
                {filterTagIds.length > 0
                  ? "尝试移除一个标签筛选条件。"
                  : `上传第一份文档到「${activeDb?.name ?? activeDbId}」后,它会出现在这里。`}
              </p>
            </div>
          ) : (
            <div className="doc-list">
              {visibleDocs.map((doc) => {
                const display = (doc.source || "").split(" §")[0];
                return (
                  <div key={doc.doc_id} className="doc-card">
                    <div className="doc-icon">
                      <FileText size={20} />
                    </div>
                    <div className="doc-info">
                      <div className="doc-title">{display}</div>
                      <div className="doc-meta">ID: {doc.doc_id}</div>
                    </div>
                    <div className="doc-actions">
                      <span className="doc-badge">{doc.chunk_count} chunks</span>
                      <button
                        className="doc-action-btn tag"
                        onClick={() => setPickerOpen({ source: doc.source })}
                        aria-label={`给 ${display} 打标签`}
                        title="打标签"
                      >
                        <TagIcon size={16} />
                      </button>
                      <button
                        className="doc-action-btn delete"
                        onClick={() => handleDelete(doc.source)}
                        aria-label={`删除 ${display}`}
                        title="删除"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>

      {/* 新建分类 modal */}
      {showNewDbModal && (
        <div className="modal-backdrop" onClick={() => setShowNewDbModal(false)}>
          <div
            className="modal-card"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="modal-title">新建分类</div>
            <label className="modal-label">
              分类名称
              <input
                type="text"
                value={newDbName}
                onChange={(e) => setNewDbName(e.target.value)}
                placeholder="例:菜品 SOP / 财务"
                autoFocus
                maxLength={64}
              />
            </label>
            <label className="modal-label">
              描述(可选)
              <textarea
                value={newDbDesc}
                onChange={(e) => setNewDbDesc(e.target.value)}
                placeholder="这个分类放什么资料?"
                rows={3}
                maxLength={512}
              />
            </label>
            <div className="modal-actions">
              <button
                className="modal-btn"
                onClick={() => setShowNewDbModal(false)}
                disabled={creatingDb}
              >
                取消
              </button>
              <button
                className="modal-btn primary"
                onClick={handleCreateDatabase}
                disabled={creatingDb || !newDbName.trim()}
              >
                {creatingDb ? "创建中..." : "创建"}
              </button>
            </div>
          </div>
        </div>
      )}

      {pickerOpen && (
        <TagPicker
          availableTags={tags}
          initialSelectedIds={pickerOpen.source === FILTER_SOURCE ? filterTagIds : []}
          onCancel={() => setPickerOpen(null)}
          onConfirm={handleTagPickerConfirm}
        />
      )}

      {/* v1.1.0 PR#1 Task 1.3:级联删除二次确认 — 后端 409 + requires_cascade 时触发 */}
      <ConfirmCascadeDeleteModal
        open={cascadeTarget !== null}
        databaseName={cascadeTarget?.dbName ?? ""}
        childDocuments={cascadeTarget?.childDocuments ?? 0}
        busy={cascadeBusy}
        onCancel={() => {
          if (!cascadeBusy) setCascadeTarget(null);
        }}
        onConfirm={handleCascadeConfirm}
      />
    </div>
  );
}