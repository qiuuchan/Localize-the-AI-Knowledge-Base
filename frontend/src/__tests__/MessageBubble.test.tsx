import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MessageBubble } from '../components/MessageBubble';

describe('MessageBubble image thumbnails', () => {
  it('renders thumbnails when image_paths provided', () => {
    render(
      <MessageBubble
        role="user"
        content="看这张图"
        image_paths={['/data/uploads/test.png', '/data/uploads/test2.png']}
      />
    );
    expect(screen.getByTestId('image-thumbnails')).toBeInTheDocument();
    expect(screen.getAllByRole('img')).toHaveLength(2);
  });

  it('does not render thumbnails when image_paths empty', () => {
    render(<MessageBubble role="user" content="no image" />);
    expect(screen.queryByTestId('image-thumbnails')).not.toBeInTheDocument();
  });
});

describe('MessageBubble option buttons', () => {
  it('renders single-choice buttons and triggers reply on click', () => {
    const onReply = vi.fn();
    render(
      <MessageBubble
        role="assistant"
        content="请选择"
        options={['A', 'B', 'C']}
        question_type="single_choice"
        onUserReply={onReply}
      />
    );
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[0]);
    expect(onReply).toHaveBeenCalledWith('A');
  });

  it('renders multi-choice with confirm button', () => {
    const onReply = vi.fn();
    render(
      <MessageBubble
        role="assistant"
        content="可多选"
        options={['X', 'Y', 'Z']}
        question_type="multi_choice"
        onUserReply={onReply}
      />
    );
    fireEvent.click(screen.getByText('X'));
    fireEvent.click(screen.getByText('Z'));
    fireEvent.click(screen.getByText(/确认/));
    expect(onReply).toHaveBeenCalledWith('X, Z');
  });

  it('does not render options when options array empty', () => {
    render(<MessageBubble role="assistant" content="no options" />);
    expect(screen.queryByTestId('option-buttons')).not.toBeInTheDocument();
  });
});

describe('MessageBubble skip clarification', () => {
  // v1.1.0 PR#3 Task 3.5:REQ-4 跳过反问按钮 — assistant 走 clarify 路径
  // 时,MessageBubble 在 content 下方渲染 SkipClarificationButton;点击回调
  // 由 App 注入,负责带 skip_clarification=true 重发原问题。
  it('renders skip button when clarification present and triggers onSkip', () => {
    const onSkip = vi.fn();
    render(
      <MessageBubble
        role="assistant"
        content="你想问哪个?"
        clarification={{ original_question: '什么是 RAG?' }}
        lastUserMessage="什么是 RAG?"
        onSkipClarification={onSkip}
      />
    );
    const btn = screen.getByTestId('skip-clarification');
    expect(btn).toBeInTheDocument();
    // v1.1.0 PR#3 Task 3.5:按钮文本里要带原问题(供用户确认要跳过哪条反问)。
    expect(btn.textContent).toContain('什么是 RAG?');
    fireEvent.click(btn);
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('does not render skip button without onSkipClarification', () => {
    render(
      <MessageBubble
        role="assistant"
        content="你想问哪个?"
        clarification={{ original_question: '什么是 RAG?' }}
      />
    );
    expect(screen.queryByTestId('skip-clarification')).not.toBeInTheDocument();
  });
});