import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
// vi.mock calls below are hoisted by vitest, so it's safe for this import to
// appear before them in source order — keeps import/first satisfied.
import { AIView } from './AIView';
import { WorkspaceBootstrapProvider } from '@/src/domains/workspaces/workspace-bootstrap-context';

const aiHarness = vi.hoisted(() => ({
  abandonAiApproval: vi.fn(),
  getLlmHealth: vi.fn(),
  resolveAiApproval: vi.fn(),
  sendAiChat: vi.fn(),
  streamAiChat: vi.fn(),
  streamAiChatResume: vi.fn(),
}));
const conversationsHarness = vi.hoisted(() => ({
  getConversation: vi.fn(),
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
    abandonAiApproval: aiHarness.abandonAiApproval,
    getLlmHealth: aiHarness.getLlmHealth,
    resolveAiApproval: aiHarness.resolveAiApproval,
    sendAiChat: aiHarness.sendAiChat,
    streamAiChat: aiHarness.streamAiChat,
    streamAiChatResume: aiHarness.streamAiChatResume,
  };
});

vi.mock('@/src/domains/ai/conversations-api', async () => {
  const actual = await vi.importActual<
    typeof import('@/src/domains/ai/conversations-api')
  >('@/src/domains/ai/conversations-api');
  return {
    ...actual,
    getConversation: conversationsHarness.getConversation,
  };
});

const meetingHarness = vi.hoisted(() => ({
  getMeeting: vi.fn(),
}));

vi.mock('@/src/domains/meeting/meeting-api', async () => {
  const actual = await vi.importActual<
    typeof import('@/src/domains/meeting/meeting-api')
  >('@/src/domains/meeting/meeting-api');
  return {
    ...actual,
    getMeeting: meetingHarness.getMeeting,
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
    errorMessage,
    isSubmitting,
    onClose,
    onResolve,
  }: {
    approval: { approval_id: string; tool: string; decision: string | null };
    errorMessage?: string | null;
    isSubmitting?: boolean;
    onClose: () => void | Promise<void>;
    onResolve: (
      decision: 'approved' | 'rejected',
      reason?: string,
    ) => void | Promise<void>;
  }) => (
    <div data-testid={`approval-${approval.approval_id}`}>
      {approval.tool}:{approval.decision ?? 'pending'}
      {errorMessage ? <div data-testid="approval-error">{errorMessage}</div> : null}
      <button
        type="button"
        onClick={() => {
          void onResolve('approved');
        }}
        disabled={isSubmitting}
      >
        mock-approve
      </button>
      <button
        type="button"
        onClick={() => {
          void onResolve('rejected', '거절 사유');
        }}
        disabled={isSubmitting}
      >
        mock-reject
      </button>
      <button
        type="button"
        onClick={() => {
          void onClose();
        }}
        disabled={isSubmitting}
      >
        mock-close
      </button>
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

function conversationDetail(
  overrides: Partial<{
    id: string;
    title: string;
    scopeRef: 'meeting' | null;
    scopeResourceId: string | null;
    livePendingApproval: {
      approvalId: string;
      agentRunId: string;
      callId: string;
      tool: string;
      resourcePreview?: string | null;
      expiresAtMs: number;
      status: 'pending' | 'approved' | 'rejected';
      reason?: string | null;
    } | null;
    turns: Array<Record<string, unknown>>;
  }> = {},
) {
  return {
    id: overrides.id ?? 'conversation-1',
    title: overrides.title ?? '',
    scopeRef: overrides.scopeRef ?? null,
    scopeResourceId: overrides.scopeResourceId ?? null,
    createdAt: '2026-04-21T00:00:00Z',
    updatedAt: '2026-04-21T00:00:00Z',
    livePendingApproval: overrides.livePendingApproval ?? null,
    turns: overrides.turns ?? [],
  };
}

function RouteProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <div data-testid="location-search">{location.search}</div>
      <button type="button" onClick={() => navigate('/w/hq/ai?c=missing')}>
        go-missing
      </button>
      <button
        type="button"
        onClick={() =>
          navigate('/w/hq/ai?draft=' + encodeURIComponent('두번째 초안'))
        }
      >
        go-second-draft
      </button>
      <button
        type="button"
        onClick={() =>
          navigate('/w/hq/ai?draft=' + encodeURIComponent('상태 기반 초안'), {
            state: {
              aiDraft: '상태 기반 초안',
              aiDraftSourceKey: 'meeting-insight:m-1:i-1',
              aiDraftOrigin: 'meeting_insight',
            },
          })
        }
      >
        go-state-draft
      </button>
    </>
  );
}

function renderAIView(
  options: {
    initialEntries?: ComponentProps<typeof MemoryRouter>['initialEntries'];
    strict?: boolean;
  } = {},
) {
  const tree = (
    <MemoryRouter initialEntries={options.initialEntries ?? ['/w/hq/ai']}>
      <WorkspaceBootstrapProvider
        value={{ data: null, error: null, loading: false }}
      >
        <Routes>
          <Route
            path="/w/:workspaceSlug/ai"
            element={(
              <>
                <AIView />
                <RouteProbe />
              </>
            )}
          />
        </Routes>
      </WorkspaceBootstrapProvider>
    </MemoryRouter>
  );
  return render(options.strict ? <StrictMode>{tree}</StrictMode> : tree);
}

describe('AIView', () => {
  beforeEach(() => {
    aiHarness.abandonAiApproval.mockReset();
    aiHarness.getLlmHealth.mockReset();
    aiHarness.resolveAiApproval.mockReset();
    aiHarness.sendAiChat.mockReset();
    aiHarness.streamAiChat.mockReset();
    aiHarness.streamAiChatResume.mockReset();
    conversationsHarness.getConversation.mockReset();
    meetingHarness.getMeeting.mockReset();
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

  it('finalizes partial assistant output and preserves approval state after in-stream error', async () => {
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
            call_id: 'call-approval-1',
            tool: 'docs.create_page',
            resource_preview: null,
            expires_at_ms: 123,
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
    expect(screen.getByTestId('approval-approval-1').textContent).toContain(
      'docs.create_page:pending',
    );
    expect(document.body.textContent).toContain(
      '현재 승인을 해결해야 다음 요청이 가능합니다.',
    );
    expect(screen.queryByText('backend down')).toBeNull();
    // After a successful submit the view transitions empty → active, which
    // remounts the composer; re-query the currently mounted textarea.
    const currentInput = screen.getByPlaceholderText(
      '현재 승인을 해결해야 다음 요청이 가능합니다.',
    );
    expect((currentInput as HTMLTextAreaElement).value).toBe('');
    expect((currentInput as HTMLTextAreaElement).disabled).toBe(true);
    expect(aiHarness.sendAiChat).not.toHaveBeenCalled();
  });

  it('updates ?c= from conversation_attached without hydrating over the live stream', async () => {
    aiHarness.streamAiChat.mockResolvedValue(
      mockStreamResponse([
        sseBytes([
          frame('conversation_attached', 0, {
            conversation_id: 'c-attached',
          }),
          frame('content_delta', 1, { text: '저장된 응답' }),
          frame('done', 2, {
            finish_reason: 'stop',
            audit_id: null,
            meta: null,
          }),
        ]),
      ]),
    );

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: '대화 저장 테스트' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByText('저장된 응답');
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toBe(
        '?c=c-attached',
      );
    });
    expect(conversationsHarness.getConversation).not.toHaveBeenCalled();
  });

  it('updates ?c= from sync fallback conversation_id without hydrating over the finalized turn', async () => {
    aiHarness.streamAiChat.mockRejectedValue(new Error('stream unreachable'));
    aiHarness.sendAiChat.mockResolvedValue({
      model: 'mlx-community/model',
      content: '동기 응답',
      usage: null,
      finish_reason: 'stop',
      provider: 'mlx-lm',
      backend: 'primary',
      fallback_used: false,
      canonical_model: 'qwen3',
      requested_backend_mode: 'auto',
      policy: 'local_only',
      chosen_pool: 'local',
      decision_reason: 'policy_local_only',
      forced_local: false,
      pii_hits: [],
      conversation_id: 'c-sync',
    });

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: 'fallback 저장 테스트' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByText('동기 응답');
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toBe(
        '?c=c-sync',
      );
    });
    expect(conversationsHarness.getConversation).not.toHaveBeenCalled();
  });

  it('disables submit until an existing conversation finishes hydrating', async () => {
    conversationsHarness.getConversation.mockReturnValue(new Promise(() => {}));

    renderAIView({ initialEntries: ['/w/hq/ai?c=c-existing'] });

    await waitFor(() => {
      expect(conversationsHarness.getConversation).toHaveBeenCalledWith(
        'test-token',
        'c-existing',
      );
    });
    const input = screen.getByPlaceholderText('대화를 불러오는 중입니다.');
    expect((input as HTMLTextAreaElement).disabled).toBe(true);
    expect(
      (
        screen.getByRole('button', { name: /전송/i }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(aiHarness.streamAiChat).not.toHaveBeenCalled();
  });

  it('seeds a live pending approval from conversation detail and blocks the composer', async () => {
    conversationsHarness.getConversation.mockResolvedValue(
      conversationDetail({
        id: 'c-pending',
        livePendingApproval: {
          approvalId: 'approval-live-1',
          agentRunId: 'agent-run-1',
          callId: 'call-live-1',
          tool: 'docs.create_page',
          resourcePreview: '분기 계획 문서 초안',
          expiresAtMs: 123,
          status: 'pending',
          reason: null,
        },
      }),
    );

    renderAIView({ initialEntries: ['/w/hq/ai?c=c-pending'] });

    await screen.findByTestId('approval-approval-live-1');
    const input = screen.getByPlaceholderText(
      '현재 승인을 해결해야 다음 요청이 가능합니다.',
    );
    expect((input as HTMLTextAreaElement).disabled).toBe(true);
    expect(document.body.textContent).toContain(
      '현재 승인을 해결해야 다음 요청이 가능합니다.',
    );
  });

  it('resolves a pending approval and resumes exactly once through the resume SSE path', async () => {
    aiHarness.resolveAiApproval.mockResolvedValue({
      id: 'approval-1',
      workspace_id: 'workspace-1',
      conversation_id: 'c-approval',
      agent_run_id: 'agent-run-1',
      tool_call_id: 'call-approval-1',
      tool_name: 'docs.create_page',
      arguments_json: '{}',
      resource_preview: '문서 초안',
      status: 'approved',
      requested_by_user_id: 'user-1',
      resolved_by_user_id: 'user-1',
      reject_reason: null,
      resolved_at: '2026-04-21T12:00:00Z',
      expires_at: '2026-04-21T12:05:00Z',
      execution_result_json: null,
      error_message: null,
      created_at: '2026-04-21T11:59:00Z',
      snapshot_status: 'resumed',
    });
    aiHarness.streamAiChat.mockResolvedValue(
      mockStreamResponse([
        sseBytes([
          frame('conversation_attached', 0, {
            conversation_id: 'c-approval',
          }),
          frame('approval_required', 1, {
            approval_id: 'approval-1',
            call_id: 'call-approval-1',
            tool: 'docs.create_page',
            resource_preview: '문서 초안',
            expires_at_ms: 123,
          }),
          frame('done', 2, {
            finish_reason: 'awaiting_approval',
            audit_id: null,
            meta: null,
          }),
        ]),
      ]),
    );
    aiHarness.streamAiChatResume.mockResolvedValue(
      mockStreamResponse([
        sseBytes([
          frame('approval_resolved', 0, {
            approval_id: 'approval-1',
            call_id: 'call-approval-1',
            decision: 'approved',
            reason: null,
          }),
          frame('content_delta', 1, { text: '재개 완료' }),
          frame('done', 2, {
            finish_reason: 'stop',
            audit_id: null,
            meta: null,
          }),
        ]),
      ]),
    );

    renderAIView();

    const input = screen.getByPlaceholderText('메시지를 입력하세요');
    fireEvent.change(input, { target: { value: '문서를 만들어줘' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/i }));

    await screen.findByTestId('approval-approval-1');
    fireEvent.click(screen.getByRole('button', { name: 'mock-approve' }));

    await waitFor(() => {
      expect(aiHarness.resolveAiApproval).toHaveBeenCalledWith(
        'test-token',
        'approval-1',
        {
          decision: 'approved',
          reason: undefined,
        },
      );
    });
    await waitFor(() => {
      expect(aiHarness.streamAiChatResume).toHaveBeenCalledTimes(1);
    });
    await screen.findByText('재개 완료');

    expect(aiHarness.streamAiChatResume).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('approval-approval-1')).toBeNull();
  });

  it('clears stale turns when navigating from a valid conversation to an invalid one', async () => {
    conversationsHarness.getConversation
      .mockResolvedValueOnce({
        id: 'c-valid',
        title: '기존 대화',
        createdAt: '2026-04-19T00:00:00',
        updatedAt: '2026-04-19T00:01:00',
        turns: [
          {
            id: 'turn-1',
            seq: 0,
            role: 'user',
            content: '기존 대화 내용',
            createdAt: '2026-04-19T00:00:10',
          },
        ],
      })
      .mockRejectedValueOnce(new Error('없는 대화입니다.'));

    renderAIView({ initialEntries: ['/w/hq/ai?c=c-valid'] });

    await screen.findByText('기존 대화 내용');
    fireEvent.click(screen.getByRole('button', { name: 'go-missing' }));

    await screen.findByText('없는 대화입니다.');
    expect(screen.queryByText('기존 대화 내용')).toBeNull();
    expect(
      (
        screen.getByPlaceholderText(
          '이 대화를 열 수 없습니다. 새 대화를 시작하거나 다른 대화를 선택하세요.',
        ) as HTMLTextAreaElement
      ).disabled,
    ).toBe(true);
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
    // persist: true opts the stream into conversation history so the "최근
    // 대화" sidebar gets populated; conversation_id is undefined on the first
    // request because the backend has not yet returned an id.
    expect(aiHarness.streamAiChat.mock.calls[0][0].payload).toEqual({
      messages: expect.any(Array),
      backend_mode: 'auto',
      temperature: 0.2,
      stream_reasoning: true,
      persist: true,
      conversation_id: undefined,
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

  it('pre-fills composer from ?draft= on a fresh chat mount', async () => {
    renderAIView({
      initialEntries: [
        '/w/hq/ai?draft=' +
          encodeURIComponent('회의 액션 이슈로 만들어줘') +
          '&context=meeting&context_id=m-1&insight_id=i-1&insight_kind=action',
      ],
    });

    const input = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(input.value).toBe('회의 액션 이슈로 만들어줘');
    });
    // The "회의 AI 제안에서 시작됨" hint appears above the composer.
    expect(screen.getByText('회의 AI 제안에서 시작됨')).toBeTruthy();
    // URL params are cleared in the same effect tick so refreshes do not
    // re-consume the draft.
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toBe('');
    });
  });

  it('pre-fills composer from ?draft= under StrictMode double effects', async () => {
    renderAIView({
      strict: true,
      initialEntries: [
        '/w/hq/ai?draft=' +
          encodeURIComponent('StrictMode 초안') +
          '&context=meeting&context_id=m-1&insight_id=i-1&insight_kind=action',
      ],
    });

    const input = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(input.value).toBe('StrictMode 초안');
    });
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toBe('');
    });
  });

  it('preserves % in the draft without double-decoding', async () => {
    // URLSearchParams.get() returns already-decoded strings, so a second
    // decodeURIComponent would corrupt legitimate '%' characters. This
    // regression guards against that (D14).
    renderAIView({
      initialEntries: [
        '/w/hq/ai?draft=' + encodeURIComponent('완료율 50% 달성안 정리'),
      ],
    });

    const input = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(input.value).toBe('완료율 50% 달성안 정리');
    });
  });

  it('re-consumes a new ?draft= when navigating between insights on a fresh chat', async () => {
    // D11 requires that clicking a second "챗에서 진행" while still
    // on a bare `/w/:slug/ai` URL re-fills the composer with the new
    // draft. The value-based ref guard skips same-value reruns but
    // accepts a different draft.
    renderAIView({
      initialEntries: [
        '/w/hq/ai?draft=' + encodeURIComponent('첫 초안'),
      ],
    });

    const firstInput = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(firstInput.value).toBe('첫 초안');
    });

    fireEvent.click(screen.getByRole('button', { name: 'go-second-draft' }));

    await waitFor(() => {
      const input = screen.getByPlaceholderText(
        '메시지를 입력하세요',
      ) as HTMLTextAreaElement;
      expect(input.value).toBe('두번째 초안');
    });
  });

  it('consumes meeting insight drafts from router state and still clears the query', async () => {
    renderAIView();

    fireEvent.click(screen.getByRole('button', { name: 'go-state-draft' }));

    await waitFor(() => {
      const input = screen.getByPlaceholderText(
        '메시지를 입력하세요',
      ) as HTMLTextAreaElement;
      expect(input.value).toBe('상태 기반 초안');
    });
    expect(screen.getByText('회의 AI 제안에서 시작됨')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toBe('');
    });
  });

  it('seeds router-state draft into an empty meeting-scoped conversation and renders the scope chip', async () => {
    conversationsHarness.getConversation.mockResolvedValue({
      id: 'c-scoped',
      title: '',
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
      turns: [],
      createdAt: '2026-04-21T00:00:00Z',
      updatedAt: '2026-04-21T00:00:00Z',
      livePendingApproval: null,
    });
    meetingHarness.getMeeting.mockResolvedValue({
      id: 'meeting-1',
      title: '주간 동기화',
    });

    renderAIView({
      initialEntries: [
        {
          pathname: '/w/hq/ai',
          search: '?c=c-scoped',
          state: {
            aiDraft: '회의 액션을 이슈로 정리해줘',
            aiDraftSourceKey: 'meeting-insight:meeting-1:insight-1',
            aiDraftOrigin: 'meeting_insight',
          },
        },
      ],
    });

    await waitFor(() => {
      expect(conversationsHarness.getConversation).toHaveBeenCalledWith(
        'test-token',
        'c-scoped',
      );
    });
    const input = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(input.value).toBe('회의 액션을 이슈로 정리해줘');
    });
    // Scope chip replaces the old "회의 AI 제안에서 시작됨" hint for
    // scoped conversations — it persists beyond the first turn and
    // carries the meeting title + a link back to the meeting view.
    const chip = await screen.findByTestId('ai-scope-chip');
    expect(chip.getAttribute('href')).toBe('/w/hq/meeting/meeting-1');
    await waitFor(() => {
      expect(chip.textContent).toContain('주간 동기화');
    });
    expect(screen.queryByText('회의 AI 제안에서 시작됨')).toBeNull();
    expect(screen.getByTestId('location-search').textContent).toBe('?c=c-scoped');
  });

  it('ignores ?draft= when ?c= points to an existing conversation', async () => {
    conversationsHarness.getConversation.mockResolvedValue({
      id: 'c-existing',
      title: '기존 대화',
      createdAt: '2026-04-19T00:00:00',
      updatedAt: '2026-04-19T00:01:00',
      turns: [],
    });

    renderAIView({
      initialEntries: [
        '/w/hq/ai?c=c-existing&draft=' + encodeURIComponent('버려질 초안'),
      ],
    });

    await waitFor(() => {
      expect(conversationsHarness.getConversation).toHaveBeenCalledWith(
        'test-token',
        'c-existing',
      );
    });
    const input = (await screen.findByPlaceholderText(
      '메시지를 입력하세요',
    )) as HTMLTextAreaElement;
    expect(input.value).toBe('');
    expect(screen.queryByText('회의 AI 제안에서 시작됨')).toBeNull();
  });
});
