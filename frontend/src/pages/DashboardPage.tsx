// DashboardPage · v0.8.11(P1.6) — 4 卡片系统总览
// 借鉴 Yuxi-Know DashboardView.vue + dashboard_router.py 的最小化版本

import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertOctagon,
  Beaker,
  CheckCircle2,
  Database,
  Gauge,
  HardDrive,
  Layers,
  Plug2,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { getJSON, postJSON } from "../lib/api";
import type {
  DashboardOverview,
  EvalResultsResponse,
  EvalStatus,
} from "../lib/types";

const REFRESH_MS = 30_000;

export function DashboardPage() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<number>(0);

  // v0.8.11(P2.1):Eval 卡片状态
  const [evalStatus, setEvalStatus] = useState<EvalStatus | null>(null);
  const [evalResult, setEvalResult] = useState<EvalResultsResponse | null>(null);
  const [evalRunning, setEvalRunning] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await getJSON<DashboardOverview>("/dashboard/overview");
      setData(d);
      setError(null);
      setLastRefresh(Date.now());
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadEval = useCallback(async () => {
    try {
      const s = await getJSON<EvalStatus>("/eval/status");
      setEvalStatus(s);
      if (s.status === "done") {
        const r = await getJSON<EvalResultsResponse>("/eval/results");
        setEvalResult(r);
      }
    } catch {
      // /eval/* endpoints may not be wired in tests — ignore silently
    }
  }, []);

  const runEval = useCallback(async () => {
    setEvalRunning(true);
    setEvalError(null);
    try {
      const r = await postJSON<unknown>("/eval/run", { top_k: 5 });
      // r is the bare EvalResult (run endpoint returns the result directly)
      setEvalResult({
        result: r as any,
        status: "done",
        started_at: null,
        finished_at: Date.now() / 1000,
        error: null,
      });
      setEvalStatus({
        status: "done",
        started_at: null,
        finished_at: Date.now() / 1000,
        has_result: true,
        error: null,
      });
    } catch (e: any) {
      setEvalError(e?.message || "评测失败");
      setEvalStatus({
        status: "failed",
        started_at: null,
        finished_at: Date.now() / 1000,
        has_result: false,
        error: e?.message || "评测失败",
      });
    } finally {
      setEvalRunning(false);
    }
  }, []);

  useEffect(() => {
    load();
    loadEval();
    const t = setInterval(() => {
      load();
      loadEval();
    }, REFRESH_MS);
    return () => clearInterval(t);
  }, [load, loadEval]);

  if (loading) {
    return (
      <div className="page-container">
        <div className="page-header">
          <div className="page-eyebrow">[ System Dashboard ]</div>
          <h1 className="page-title">系统总览</h1>
        </div>
        <div className="page-content">
          <div className="settings-card">
            <div className="skeleton-line" style={{ width: "40%" }} />
            <div className="skeleton-line" style={{ width: "70%", marginTop: 12 }} />
          </div>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="page-container">
        <div className="page-header">
          <div className="page-eyebrow">[ System Dashboard ]</div>
          <h1 className="page-title">系统总览</h1>
        </div>
        <div className="page-content">
          <div className="status-bar offline" role="alert">
            <XCircle size={16} />
            <span>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  const d = data as DashboardOverview;
  const maxDeg =
    d.degradations_24h.reduce((m, r) => Math.max(m, r.count), 0) || 1;

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-eyebrow">[ System Dashboard ]</div>
        <h1 className="page-title">系统总览</h1>
        <div className="page-meta">
          <span className="version-pill">v{d.system.version}</span>
          <button
            className="icon-btn"
            onClick={load}
            aria-label="刷新"
            title="刷新"
          >
            <RefreshCw size={16} />
          </button>
          {lastRefresh > 0 && (
            <span className="page-meta-hint">
              最近刷新: {new Date(lastRefresh).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>
      <div className="page-content dashboard-grid">
        {/* 1. 系统健康 */}
        <div className="dashboard-card">
          <div className="dashboard-card-title">
            <Plug2 size={16} />
            <span>端点健康</span>
            <span
              className={`status-dot ${d.health.online ? "online" : "offline"}`}
              style={{ marginLeft: "auto" }}
            />
          </div>
          <div className="health-endpoints">
            {Object.entries(d.health.endpoints || {}).map(([k, v]) => (
              <div key={k} className="health-endpoint">
                <span
                  className={`status-dot ${v ? "online" : "offline"}`}
                />
                <span className="health-endpoint-name">{k}</span>
                <span className="health-endpoint-state">
                  {v ? "在线" : "离线"}
                </span>
              </div>
            ))}
            {Object.keys(d.health.endpoints || {}).length === 0 && (
              <div className="dashboard-empty">
                暂无端点状态(请检查 /api/health)
              </div>
            )}
          </div>
        </div>

        {/* 2. 降级事件(最近 24h) */}
        <div className="dashboard-card">
          <div className="dashboard-card-title">
            <AlertOctagon size={16} />
            <span>24h 降级事件</span>
          </div>
          {d.degradations_24h.length === 0 ? (
            <div className="dashboard-empty">
              <CheckCircle2 size={32} className="ok-icon" />
              <p>过去 24 小时没有任何降级记录,系统状态稳定。</p>
            </div>
          ) : (
            <div className="deg-bars">
              {d.degradations_24h.map((r) => (
                <div key={r.component} className="deg-bar-row">
                  <div className="deg-bar-label">{r.component}</div>
                  <div className="deg-bar-track">
                    <div
                      className={`deg-bar-fill ${r.count > 10 ? "high" : "low"}`}
                      style={{ width: `${(r.count / maxDeg) * 100}%` }}
                    />
                  </div>
                  <div className="deg-bar-count">{r.count}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 3. 知识库统计 */}
        <div className="dashboard-card">
          <div className="dashboard-card-title">
            <Database size={16} />
            <span>知识库统计</span>
          </div>
          {"error" in d.kb_stats ? (
            <div className="dashboard-empty">{d.kb_stats.error as string}</div>
          ) : (
            <>
              <div className="kb-stats-row">
                <div className="kb-stat">
                  <div className="kb-stat-num">{d.kb_stats.database_count}</div>
                  <div className="kb-stat-label">分类</div>
                </div>
                <div className="kb-stat">
                  <div className="kb-stat-num">{d.kb_stats.document_count}</div>
                  <div className="kb-stat-label">文档</div>
                </div>
                <div className="kb-stat">
                  <div className="kb-stat-num">{d.kb_stats.chunk_count}</div>
                  <div className="kb-stat-label">Chunks</div>
                </div>
              </div>
              {d.kb_stats.databases && d.kb_stats.databases.length > 0 && (
                <div className="kb-db-list">
                  {d.kb_stats.databases.map((db) => (
                    <div key={db.id} className="kb-db-row">
                      <Layers size={14} />
                      <span className="kb-db-name">{db.name}</span>
                      <span className="kb-db-count">{db.document_count} 份</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* 4. 漂移检测 */}
        <div className="dashboard-card">
          <div className="dashboard-card-title">
            <ShieldAlert size={16} />
            <span>数据一致性</span>
            {"ok" in d.drift && (
              <span
                className={`status-dot ${d.drift.ok ? "online" : "degraded"}`}
                style={{ marginLeft: "auto" }}
              />
            )}
          </div>
          {"error" in d.drift ? (
            <div className="dashboard-empty">{d.drift.error as string}</div>
          ) : (
            <>
              <div className="drift-row">
                <Gauge size={16} />
                <span className="drift-label">Qdrant 向量点</span>
                <span className="drift-num">{d.drift.qdrant_points ?? "-"}</span>
              </div>
              <div className="drift-row">
                <HardDrive size={16} />
                <span className="drift-label">Keyword 索引 chunks</span>
                <span className="drift-num">{d.drift.keyword_chunks ?? "-"}</span>
              </div>
              <div className="drift-summary">
                {d.drift.ok ? (
                  <span className="drift-ok">
                    <CheckCircle2 size={14} /> 一致(差值 ≤ 5)
                  </span>
                ) : (
                  <span className="drift-warn">
                    <AlertOctagon size={14} /> 漂移 {d.drift.drift}
                  </span>
                )}
              </div>
              {d.drift.per_db && d.drift.per_db.length > 0 && (
                <details className="drift-details">
                  <summary>按分类详情</summary>
                  {d.drift.per_db.map((db) => (
                    <div key={db.id} className="drift-per-db">
                      <span>{db.name}</span>
                      <span>{db.qdrant_points ?? "?"} points</span>
                    </div>
                  ))}
                </details>
              )}
            </>
          )}
        </div>

        {/* v1.3.0: cost-alert 月度配额告警卡片 */}
        <div className="dashboard-card cost-alert-card" data-testid="cost-alert-card">
          {!d.cost_alert || !d.cost_alert.updated_at || !d.cost_alert.month ? (
            <div className="cost-alert-loading">用量数据采集中...</div>
          ) : (
            <>
              {d.cost_alert.level >= 2 && (
                <div
                  className={`cost-alert-banner${
                    d.cost_alert.level >= 3 ? " critical" : ""
                  }`}
                  data-testid="cost-alert-banner"
                >
                  {d.cost_alert.level >= 3
                    ? `⚠️ 本月用量已达 ¥${d.cost_alert.month_yuan.toFixed(0)},超过 block 阈值,LLM 调用已临时阻断`
                    : `本月用量已达 ¥${d.cost_alert.month_yuan.toFixed(0)},接近 block 阈值(¥${d.cost_alert.thresholds.block})`}
                </div>
              )}
              <h3>本月用量</h3>
              <div className="cost-progress">
                <div className="cost-yuan">
                  ¥{d.cost_alert.month_yuan.toFixed(2)}
                  <span className="cost-month"> / {d.cost_alert.month}</span>
                </div>
                <div className="cost-bar">
                  <div
                    className="cost-bar-fill"
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(
                          100,
                          d.cost_alert.thresholds.block > 0
                            ? (d.cost_alert.month_yuan /
                                d.cost_alert.thresholds.block) *
                                100
                            : 0,
                        ),
                      )}%`,
                      background:
                        d.cost_alert.level >= 3
                          ? "#DC2626"
                          : d.cost_alert.level >= 2
                            ? "#D97706"
                            : d.cost_alert.level >= 1
                              ? "#FF540E"
                              : "#A1A1AA",
                    }}
                    data-testid="cost-bar-fill"
                  />
                </div>
                <div className="cost-thresholds">
                  阈值: ¥{d.cost_alert.thresholds.warn} (warn) / ¥
                  {d.cost_alert.thresholds.high} (high) / ¥
                  {d.cost_alert.thresholds.block} (block)
                </div>
              </div>
            </>
          )}
        </div>

        {/* v0.8.11(P2.1):金标问答回归 — 第 6 卡片,跨两列 */}
        <div className="dashboard-card dashboard-card-wide">
          <div className="dashboard-card-title">
            <Beaker size={16} />
            <span>金标问答回归</span>
            {evalResult?.result && (
              <span
                className={`status-dot ${
                  evalResult.result.failed === 0 ? "online" : "degraded"
                }`}
                style={{ marginLeft: "auto" }}
              />
            )}
            <button
              className="dashboard-action-btn"
              onClick={runEval}
              disabled={evalRunning}
              aria-label="运行评测"
              title="运行评测(可能需要数十秒)"
            >
              <PlayCircle size={14} />
              {evalRunning ? "运行中..." : "运行评测"}
            </button>
          </div>

          {evalError && (
            <div className="status-bar offline" role="alert">
              <XCircle size={16} />
              <span>{evalError}</span>
            </div>
          )}

          {!evalResult?.result && !evalError && !evalRunning && (
            <div className="dashboard-empty">
              <Beaker size={32} className="muted-icon" />
              <p>尚未运行过评测。点击「运行评测」基于 golden-qa.jsonl 跑一轮 RAG 召回回归。</p>
            </div>
          )}

          {evalResult?.result && (
            <>
              <div className="kb-stats-row">
                <div className="kb-stat">
                  <div className="kb-stat-num">{evalResult.result.passed}</div>
                  <div className="kb-stat-label">通过</div>
                </div>
                <div className="kb-stat">
                  <div
                    className="kb-stat-num"
                    style={{
                      color: evalResult.result.failed > 0 ? "#dc2626" : "var(--accent)",
                    }}
                  >
                    {evalResult.result.failed}
                  </div>
                  <div className="kb-stat-label">失败</div>
                </div>
                <div className="kb-stat">
                  <div className="kb-stat-num">
                    {Math.round(evalResult.result.pass_rate * 100)}%
                  </div>
                  <div className="kb-stat-label">通过率</div>
                </div>
                <div className="kb-stat">
                  <div className="kb-stat-num">
                    {evalResult.result.duration_seconds}s
                  </div>
                  <div className="kb-stat-label">耗时</div>
                </div>
              </div>
              {evalResult.result.results &&
                evalResult.result.results.filter((r) => !r.ok).length > 0 && (
                  <details className="drift-details">
                    <summary>
                      {evalResult.result.results.filter((r) => !r.ok).length} 条失败用例
                    </summary>
                    <div className="eval-fail-list">
                      {evalResult.result.results
                        .filter((r) => !r.ok)
                        .slice(0, 10)
                        .map((r, i) => (
                          <div key={i} className="eval-fail-row">
                            <span className="eval-fail-q">
                              {r.question.slice(0, 50)}
                            </span>
                            <span className="eval-fail-detail">{r.detail}</span>
                          </div>
                        ))}
                    </div>
                  </details>
                )}
              <div className="eval-meta">
                数据集 {evalResult.result.dataset.split("/").pop()} · top_k=
                {evalResult.result.top_k} · {new Date(evalResult.result.timestamp).toLocaleTimeString()}
              </div>
            </>
          )}
        </div>

        {/* 系统信息条 */}
        <div className="dashboard-system-strip">
          <Activity size={14} />
          <span>
            v{d.system.version} · 数据 {d.system.data_dir_size_mb} MB ·
            已运行 {Math.floor((d.system.uptime_seconds || 0) / 60)} 分钟
          </span>
          <span className="dashboard-system-strip-ts">
            更新于 {new Date(d.timestamp).toLocaleTimeString()}
          </span>
        </div>
      </div>
    </div>
  );
}