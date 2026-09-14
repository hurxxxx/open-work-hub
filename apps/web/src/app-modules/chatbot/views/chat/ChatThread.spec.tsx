import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ToolCallBuffer } from '../../api/agent-events';
import { ChatThread } from './ChatThread';
import type { ChatTurn } from './chat-turn';

function tool(
  id: string,
  status: ToolCallBuffer['status'] = 'ok',
): ToolCallBuffer {
  return {
    call_id: id,
    name: 'terminal',
    argsBuffer: '',
    args_preview: id,
    startedAtMs: 1,
    completedAtMs: status === 'running' ? null : 2,
    status,
    result: null,
  };
}

describe('ChatThread execution details', () => {
  let resize: () => void;
  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resize = callback;
        }
        observe = vi.fn();
        disconnect = vi.fn();
      },
    );
  });

  it('follows hydrated layout changes only while the reader is at the bottom', () => {
    const { container } = render(
      <ChatThread
        turns={[]}
        liveAssistant={null}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    const scroll = container.querySelector('.custom-scrollbar') as HTMLElement;
    Object.defineProperties(scroll, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 200 },
    });
    vi.mocked(Element.prototype.scrollTo).mockClear();
    resize();
    expect(scroll.scrollTo).toHaveBeenCalledWith({
      top: 1000,
      behavior: 'auto',
    });
    fireEvent.scroll(scroll, { target: { scrollTop: 100 } });
    vi.mocked(Element.prototype.scrollTo).mockClear();
    resize();
    expect(scroll.scrollTo).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Latest' }));
    expect(scroll.scrollTo).toHaveBeenCalledWith({
      top: 1000,
      behavior: 'smooth',
    });
  });

  it('keeps three completed runs inside their own answers and collapsed', () => {
    const turns: ChatTurn[] = [1, 2, 3].flatMap((index) => [
      { id: `question-${index}`, role: 'user', content: `Question ${index}` },
      {
        id: `answer-${index}`,
        role: 'assistant',
        content: `Answer ${index}`,
        toolCalls: [tool(`call-${index}`, index === 2 ? 'error' : 'ok')],
      },
    ]);
    const { container } = render(
      <ChatThread
        turns={turns}
        liveAssistant={null}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    expect(container.querySelectorAll('[data-tool-call-group]')).toHaveLength(
      3,
    );
    for (const index of [1, 2, 3]) {
      const answer = screen
        .getByText(`Answer ${index}`)
        .closest('[data-turn-id]') as HTMLElement;
      const toggle = within(answer).getByRole('button', { expanded: false });
      expect(within(answer).queryByText(`call-${index}`)).toBeNull();
      fireEvent.click(toggle);
      expect(within(answer).getByText(`call-${index}`)).toBeTruthy();
      expect(within(answer).queryByText(`call-${(index % 3) + 1}`)).toBeNull();
    }
    expect(container.querySelector('.animate-spin')).toBeNull();
  });

  it('retains run activity after its last tool completes, then removes it at terminal', async () => {
    const { container, rerender } = render(
      <ChatThread
        turns={[]}
        liveAssistant={{
          content: '',
          reasoning: '',
          status: 'streaming',
          toolCalls: [tool('call-current')],
        }}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
    rerender(
      <ChatThread
        turns={[
          {
            id: 'answer',
            role: 'assistant',
            content: 'Finished',
            toolCalls: [tool('call-current')],
          },
        ]}
        liveAssistant={null}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    expect(container.querySelector('.animate-pulse')).toBeNull();
    await waitFor(() =>
      expect(container.querySelectorAll('[data-tool-call-group]')).toHaveLength(
        1,
      ),
    );
  });

  it('does not animate a stranded running tool from a past response', () => {
    const { container } = render(
      <ChatThread
        turns={[
          {
            id: 'old-answer',
            role: 'assistant',
            content: 'Interrupted',
            toolCalls: [tool('stranded', 'running')],
          },
        ]}
        liveAssistant={null}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    expect(container.querySelector('.animate-spin, .animate-pulse')).toBeNull();
    expect(screen.getByText(/결과 미확인|Result unavailable/)).toBeTruthy();
  });

  it('preserves intermediate errors and distinguishes approval rejection after later success', () => {
    render(
      <ChatThread
        turns={[
          {
            id: 'answer-with-recovery',
            role: 'assistant',
            content: 'Completed output',
            toolCalls: [
              tool('blocked-code', 'error'),
              tool('script-error', 'error'),
              tool('blocked-patch', 'error'),
              tool('approval', 'rejected'),
              tool('corrected-output', 'ok'),
            ],
          },
        ]}
        liveAssistant={null}
        typingLabel="Working"
        jumpToBottomLabel="Latest"
      />,
    );
    expect(screen.getByText('도구 오류 3개')).toBeTruthy();
    expect(screen.getByText('승인 거절 1개')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    expect(screen.getByText('corrected-output')).toBeTruthy();
    expect(screen.getByText(/전체 실행 상태와는 별개/)).toBeTruthy();
  });
});
