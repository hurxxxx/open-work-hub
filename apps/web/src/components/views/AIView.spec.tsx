import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
// vi.mock calls below are hoisted by vitest, so it's safe for this import to
// appear before them in source order — keeps import/first satisfied.
import { AIView } from './AIView';

const aiHarness = vi.hoisted(() => ({
  getLlmHealth: vi.fn(),
  sendAiChat: vi.fn(),
  streamAiChat: vi.fn(),
}));

vi.mock('motion/react', () => ({
  motion: {
    div: ({ children, ...props }: ComponentProps<'div'>) => (
      <div {...props}>{children}</div>
    ),
  },
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/ai/ai-api', async () => {
  const actual = await vi.importActual<typeof import('@/src/domains/ai/ai-api')>(
    '@/src/domains/ai/ai-api',
  );
  return {
    ...actual,
    getLlmHealth: aiHarness.getLlmHealth,
    sendAiChat: aiHarness.sendAiChat,
    streamAiChat: aiHarness.streamAiChat,
  };
});

vi.mock('@/src/components/views/chat/ToolCallCard', () => ({
  ToolCallCard: ({ call }: { call: { call_id: string; name: string; argsBuffer: string } }) => (
    <div data-testid={`tool-call-${call.call_id}`}>
      {call.name}:{call.argsBuffer}
    </div>
  ),
}));

vi.mock('@/src/components/views/chat/ApprovalModal', () => ({
  ApprovalModal: ({
    approval,
  }: {
    approval: { approval_id: string; tool: string; decision: string | null };
  }) => (
    <div data-testid={`approval-${approval.approval_id}`}>
      {approval.tool}:{approval.decision ?? 'pending'}
    </div>
  ),
}));

function frame(type: string, seq: number, data: unknown): string {
  const payload = JSON.stringify({
    seq,
    timestamp_ms: 0,
    type,
    data,
  });
  return `event: ${type}\r\ndata: ${payload}`;
}

function sseBytes(frames: string[]): Uint8Array {
  const encoder = new TextEncoder();
  return encoder.encode(frames.map((item) => `${item}\r\n\r\n`).join(''));
}

function mockStreamResponse(payloads: Uint8Array[]): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of payloads) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  }) as Response;
}

function healthPayload() {
  return {
    ready: true,
    local: {
      pool: 'local' as const,
      provider: 'mlx-lm',
      base_url: 'http://127.0.0.1:8000',
      model: 'mlx-community/model',
      canonical_model: 'qwen3',
      status: 'ready',
      ready: true,
      detail: null,
    },
    external: {
      pool: 'external' as const,
      provider: 'openrouter',
      base_url: 'https://openrouter.ai/api/v1',
      model: 'openai/gpt-4.1-mini',
      canonical_model: 'gpt-4.1-mini',
      status: 'ready',
      ready: true,
      detail: null,
    },
  };
}

function renderAIView() {
  return render(
    <MemoryRouter initialEntries={['/w/hq/ai']}>
      <Routes>
        <Route path="/w/:workspaceSlug/ai" element={<AIView />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AIView', () => {
  beforeEach(() => {
    aiHarness.getLlmHealth.mockReset();
    aiHarness.sendAiChat.mockReset();
    aiHarness.streamAiChat.mockReset();
    aiHarness.getLlmHealth.mockResolvedValue(healthPayload());
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
      writable: true,
    });
    window.localStorage.removeItem('aidoo.ai.streamEnabled');
    window.localStorage.removeItem('aidoo.ai.backendMode');
  });

  it('rolls back the optimistic user turn and restores input on pre-stream fallback failure', async () => {
    aiHarness.streamAiChat.mockRejectedValue(new Error('stream unreachable'));
    aiHarness.sendAiChat.mockRejectedValue(new Error('sync down'));

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: '미복구 테스트' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByText('sync down');
    expect(screen.queryByText('응답 실패')).toBeNull();
    expect(screen.queryAllByText('미복구 테스트')).toHaveLength(1);
    expect((input as HTMLTextAreaElement).value).toBe('미복구 테스트');
  });

  it('finalizes partial assistant output and preserves tool and approval placeholders after in-stream error', async () => {
    aiHarness.streamAiChat.mockResolvedValue(
      mockStreamResponse([
        sseBytes([
          frame('tool_call_started', 0, {
            call_id: 'call-1',
            name: 'pms.search_issues',
            args_preview: '{"q":',
          }),
          frame('tool_call_args_delta', 1, {
            call_id: 'call-1',
            delta: '{"q":"bug"}',
          }),
          frame('approval_required', 2, {
            approval_id: 'approval-1',
            tool: 'docs.create_page',
            resource_preview: null,
          }),
          frame('content_delta', 3, { text: 'partial answer' }),
          frame('error', 4, {
            code: 'provider_error',
            message: 'backend down',
            retryable: false,
          }),
          frame('done', 5, {
            finish_reason: 'error',
            audit_id: null,
            meta: {
              policy: 'local_only',
              chosen_pool: 'local',
              decision_reason: 'policy_local_only',
              forced_local: false,
              pii_hits: [],
              model: 'mlx-community/model',
              canonical_model: 'qwen3',
              provider: 'mlx-lm',
            },
          }),
        ]),
      ]),
    );

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: '스트림 오류 테스트' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByText('partial answer');
    await waitFor(() => {
      expect(document.body.textContent).toContain('응답 실패');
    });
    expect(screen.getByTestId('tool-call-call-1').textContent).toBe(
      'pms.search_issues:{"q":"bug"}',
    );
    expect(screen.getByTestId('approval-approval-1').textContent).toBe(
      'docs.create_page:pending',
    );
    expect(screen.queryByText('backend down')).toBeNull();
    // After a successful submit the view transitions empty → active, which
    // remounts the composer; re-query the currently mounted textarea.
    const currentInput = screen.getByPlaceholderText('메시지를 입력하세요');
    expect((currentInput as HTMLTextAreaElement).value).toBe('');
    expect(aiHarness.sendAiChat).not.toHaveBeenCalled();
  });

  it('lets the backend choose defaults and surfaces token-limit truncation on length finish', async () => {
    aiHarness.streamAiChat.mockResolvedValue(
      mockStreamResponse([
        sseBytes([
          frame('content_delta', 0, { text: '부분 응답' }),
          frame('done', 1, {
            finish_reason: 'length',
            audit_id: null,
            meta: {
              policy: 'external',
              chosen_pool: 'external',
              decision_reason: 'policy_external',
              forced_local: false,
              pii_hits: [],
              model: 'qwen/qwen3.6-35b-a3b',
              canonical_model: 'qwen/qwen3.6-35b-a3b',
              provider: 'openrouter',
            },
          }),
        ]),
      ]),
    );

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: '긴 설명을 해줘' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByText('부분 응답');
    await waitFor(() => {
      expect(document.body.textContent).toContain('토큰 한도 도달');
    });

    expect(aiHarness.streamAiChat).toHaveBeenCalledTimes(1);
    expect(aiHarness.streamAiChat.mock.calls[0][0].payload).toEqual({
      messages: expect.any(Array),
      backend_mode: 'auto',
      temperature: 0.2,
      stream_reasoning: true,
    });
    expect(aiHarness.streamAiChat.mock.calls[0][0].payload).not.toHaveProperty(
      'max_tokens',
    );
    expect(aiHarness.streamAiChat.mock.calls[0][0].payload).not.toHaveProperty(
      'reasoning_effort',
    );

    // Regression: the API already prepends its own AGENT_SYSTEM_PROMPT on every
    // turn (apps/api/src/aidoo_api/domains/ai/agent.py). Sending a client-side
    // system message produced two consecutive system messages, which mlx-lm
    // rejected with "System message must be at the beginning" (HTTP 404).
    const sentMessages = aiHarness.streamAiChat.mock.calls[0][0].payload
      .messages as Array<{ role: string }>;
    expect(sentMessages.every((message) => message.role !== 'system')).toBe(
      true,
    );
    expect(sentMessages[0].role).toBe('user');
  });
});
