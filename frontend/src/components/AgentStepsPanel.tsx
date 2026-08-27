// AgentStepsPanel · v2.0 PR#4(T13)
// 可折叠的 Agent 工具步骤面板:每个 tool_call/tool_result 渲染为一张卡片,
// 含工具名 / 参数摘要 / 耗时 / 成功·失败·运行中色点 / 结果摘要。
// 默认展开(步骤 ≤3 条),超过 3 条自动折叠,用户可手动切换。
// budget_exhausted 时顶部渲染黄色提示条。

import { useState } from "react";
import type { AgentStep } from "../lib/types";

interface AgentStepsPanelProps {
  steps: AgentStep[];
  budgetExhausted?: boolean;
}

const AUTO_COLLAPSE_THRESHOLD = 3;

function dotClass(status: AgentStep["status"]): string {
  return `agent-step-dot ${status}`;
}

function stepLabel(status: AgentStep["status"]): string {
  if (status === "running") return "执行中";
  if (status === "ok") return "成功";
  return "失败";
}

export function AgentStepsPanel({ steps, budgetExhausted }: AgentStepsPanelProps) {
  // 初始按「≤3 条默认展开」;用户可手动折叠,不做 effect 级联更新
  const [expanded, setExpanded] = useState(
    steps.length <= AUTO_COLLAPSE_THRESHOLD,
  );

  if (steps.length === 0) return null;

  const okCount = steps.filter((s) => s.status === "ok").length;

  return (
    <div className="agent-steps-panel" data-testid="agent-steps-panel">
      {budgetExhausted && (
        <div className="agent-budget-banner" data-testid="agent-budget-banner">
          ⚠ 已达到最大推理步数，以下为基于已获取信息的收尾回答
        </div>
      )}
      <button
        type="button"
        className="agent-steps-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        data-testid="agent-steps-toggle"
      >
        <span className="agent-steps-toggle-title">
          Agent 步骤
          <span className="agent-steps-count">
            {steps.length} 步 · {okCount} 成功
          </span>
        </span>
        <span className="agent-steps-arrow">{expanded ? "▾" : "▸"}</span>
      </button>
      {expanded && (
        <div className="agent-steps-body" data-testid="agent-steps-body">
          {steps.map((s, i) => (
            <div
              key={`${s.step}-${s.name}-${i}`}
              className={`agent-step-card ${s.status}`}
            >
              <span className={dotClass(s.status)} aria-hidden="true" />
              <div className="agent-step-main">
                <div className="agent-step-head">
                  <span className="agent-step-name">{s.name}</span>
                  <span className="agent-step-status">{stepLabel(s.status)}</span>
                  {typeof s.latencyMs === "number" && (
                    <span className="agent-step-latency">{s.latencyMs}ms</span>
                  )}
                </div>
                {s.argsSummary && (
                  <div className="agent-step-args" title={s.argsSummary}>
                    {s.argsSummary}
                  </div>
                )}
                {s.excerpt && (
                  <div className="agent-step-excerpt" title={s.excerpt}>
                    {s.excerpt}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
