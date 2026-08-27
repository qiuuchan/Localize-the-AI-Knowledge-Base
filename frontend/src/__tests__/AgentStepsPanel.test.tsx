// AgentStepsPanel 单测 (v2.0 PR#4 / 工单 T13)
// vitest 13 → 17:+4(面板渲染 / 失败态 / budget_exhausted 提示 / 折叠交互)

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentStepsPanel } from '../components/AgentStepsPanel';
import type { AgentStep } from '../lib/types';

const steps: AgentStep[] = [
  {
    step: 1,
    name: 'kb_search',
    argsSummary: '{"query": "会员数据"}',
    status: 'ok',
    latencyMs: 120,
    excerpt: '已找到 2 条相关资料',
  },
  {
    step: 1,
    name: 'calculator',
    argsSummary: '{"expression": "(186000-152000)/152000*100"}',
    status: 'ok',
    latencyMs: 45,
    excerpt: '22.37',
  },
];

describe('AgentStepsPanel', () => {
  it('renders tool cards with name, args summary and latency', () => {
    render(<AgentStepsPanel steps={steps} />);
    expect(screen.getByTestId('agent-steps-panel')).toBeInTheDocument();
    expect(screen.getByText('kb_search')).toBeInTheDocument();
    expect(screen.getByText('calculator')).toBeInTheDocument();
    expect(screen.getByText('{"query": "会员数据"}')).toBeInTheDocument();
    expect(screen.getByText('120ms')).toBeInTheDocument();
    expect(screen.getByText('45ms')).toBeInTheDocument();
    expect(screen.getByText('2 步 · 2 成功')).toBeInTheDocument();
  });

  it('marks failed steps with error status', () => {
    const failed: AgentStep[] = [
      { step: 1, name: 'web_search', status: 'error', latencyMs: 30000, excerpt: '超时' },
    ];
    render(<AgentStepsPanel steps={failed} />);
    const card = document.querySelector('.agent-step-card.error');
    expect(card).not.toBeNull();
    expect(screen.getByText('失败')).toBeInTheDocument();
    expect(screen.getByText('30000ms')).toBeInTheDocument();
  });

  it('shows budget_exhausted banner', () => {
    render(<AgentStepsPanel steps={steps} budgetExhausted />);
    expect(screen.getByTestId('agent-budget-banner')).toBeInTheDocument();
    expect(screen.getByText(/已达到最大推理步数/)).toBeInTheDocument();
  });

  it('collapses and expands on toggle', () => {
    render(<AgentStepsPanel steps={steps} />);
    expect(screen.getByTestId('agent-steps-body')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('agent-steps-toggle'));
    expect(screen.queryByTestId('agent-steps-body')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('agent-steps-toggle'));
    expect(screen.getByTestId('agent-steps-body')).toBeInTheDocument();
  });

  it('renders nothing when no steps', () => {
    render(<AgentStepsPanel steps={[]} />);
    expect(screen.queryByTestId('agent-steps-panel')).not.toBeInTheDocument();
  });
});
