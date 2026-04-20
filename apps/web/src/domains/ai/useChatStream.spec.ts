import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useChatStream } from './useChatStream';

const STREAM_FLAG_KEY = 'aidoo.ai.streamEnabled';
const SEND_PAYLOAD = {
  messages: [{ role: 'user' as const, content: 'hi' }],
};

function sseBytes(frames: string[]): Uint8Array {
  const encoder = new TextEncoder();
  return encoder.encode(frames.map((frame) => `${frame}\r\n\r\n`).join(''));
}

function frame(type: string, seq: number, data: unknown): string {
  const payload = JSON.stringify({
    seq,
    timestamp_ms: 0,
    type,
    data,
  });
  return `event: ${type}\r\ndata: ${payload}`;
}

function mockStreamResponse(
  payloads: Uint8Array[],
  { ok = true, status = 200 }: { ok?: boolean; status?: number } = {},
): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of payloads) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  }) as unknown as Response;
}

function mockJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }) as unknown as Response;
}

describe('useChatStream', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    window.localStorage.removeItem(STREAM_FLAG_KEY);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.localStorage.removeItem(STREAM_FLAG_KEY);
    vi.restoreAllMocks();
  });

  it('applies content_delta events in order into contentBuffer', async () => {
    const body = sseBytes([
      frame('content_delta', 0, { text: 'Hel' }),
      frame('content_delta', 1, { text: 'lo' }),
      frame('done', 2, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.contentBuffer).toBe('Hello');
    expect(result.current.state.status).toBe('done');
    expect(result.current.state.transport).toBe('stream');
    expect(result.current.state.streamOpened).toBe(true);
  });

  it('accumulates reasoning_delta into reasoningBuffer independently', async () => {
    const body = sseBytes([
      frame('reasoning_delta', 0, { text: 'thi' }),
      frame('reasoning_delta', 1, { text: 'nk' }),
      frame('content_delta', 2, { text: 'Hi' }),
      frame('done', 3, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.reasoningBuffer).toBe('think');
    expect(result.current.state.contentBuffer).toBe('Hi');
  });

  it('populates usage with nulls for missing counts', async () => {
    const body = sseBytes([
      frame('usage', 0, { total_tokens: 42 }),
      frame('done', 1, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.usage).toEqual({
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: 42,
    });
  });

  it('sets status=error only after done(error) and preserves partial content', async () => {
    const body = sseBytes([
      frame('content_delta', 0, { text: 'partial' }),
      frame('error', 1, {
        code: 'provider_error',
        message: 'backend down',
        retryable: false,
      }),
      frame('done', 2, { finish_reason: 'error', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.status).toBe('error');
    expect(result.current.state.errorMessage).toBe('backend down');
    expect(result.current.state.contentBuffer).toBe('partial');
    expect(result.current.state.finishReason).toBe('error');
    expect(result.current.state.streamOpened).toBe(true);
  });

  it('stores finish_reason=length so the UI can surface truncation guidance', async () => {
    const body = sseBytes([
      frame('content_delta', 0, { text: 'partial' }),
      frame('done', 1, { finish_reason: 'length', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.status).toBe('done');
    expect(result.current.state.finishReason).toBe('length');
    expect(result.current.state.contentBuffer).toBe('partial');
  });

  it('captures conversation_attached so follow-up sends can reuse the same thread id', async () => {
    const body = sseBytes([
      frame('conversation_attached', 0, { conversation_id: 'c-123' }),
      frame('content_delta', 1, { text: 'saved' }),
      frame('done', 2, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.conversationId).toBe('c-123');
    expect(result.current.state.contentBuffer).toBe('saved');
  });

  it('abort() transitions to cancelled status', async () => {
    globalThis.fetch = vi.fn().mockImplementation((_input, init) => {
      const signal = (init as RequestInit).signal!;
      return new Promise((_, reject) => {
        signal.addEventListener('abort', () => {
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    }) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    let pending: Promise<void> | undefined;
    act(() => {
      pending = result.current.send(SEND_PAYLOAD);
    });
    await waitFor(() => {
      expect(result.current.state.status).toBe('streaming');
    });
    act(() => {
      result.current.abort();
    });
    await act(async () => {
      await pending;
    });
    expect(result.current.state.status).toBe('cancelled');
  });

  it('reset() aborts the active run and ignores its stale terminal updates', async () => {
    globalThis.fetch = vi.fn().mockImplementation((_input, init) => {
      const signal = (init as RequestInit).signal!;
      return new Promise((_, reject) => {
        signal.addEventListener('abort', () => {
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    }) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    let pending: Promise<void> | undefined;
    act(() => {
      pending = result.current.send(SEND_PAYLOAD);
    });
    await waitFor(() => {
      expect(result.current.state.status).toBe('streaming');
    });
    act(() => {
      result.current.reset();
    });
    await act(async () => {
      await pending;
    });
    expect(result.current.state).toEqual({
      contentBuffer: '',
      reasoningBuffer: '',
      usage: null,
      doneMeta: null,
      finishReason: null,
      status: 'idle',
      errorMessage: null,
      toolCalls: [],
      pendingApprovals: [],
      artifacts: [],
      transport: null,
      streamOpened: false,
      conversationId: null,
    });
  });

  it('falls back to sync chat when the hidden stream flag is off', async () => {
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        mockJsonResponse({
          model: 'mlx-community/model',
          content: 'sync answer',
          finish_reason: 'length',
          usage: { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3 },
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
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.status).toBe('done');
    expect(result.current.state.transport).toBe('sync');
    expect(result.current.state.streamOpened).toBe(false);
    expect(result.current.state.contentBuffer).toBe('sync answer');
    expect(result.current.state.finishReason).toBe('length');
    expect(result.current.state.doneMeta?.provider).toBe('mlx-lm');
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain('/api/v1/ai/chat');
  });

  it('keeps persistence fields on the sync fallback payload and captures the returned conversation id', async () => {
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    const fetchMock = vi.fn().mockResolvedValue(
      mockJsonResponse({
        model: 'm',
        content: 'ok',
        usage: null,
        provider: 'p',
        backend: 'primary',
        fallback_used: false,
        canonical_model: 'm',
        requested_backend_mode: 'auto',
        policy: 'local_only',
        chosen_pool: 'local',
        decision_reason: 'policy_local_only',
        forced_local: false,
        pii_hits: [],
        conversation_id: 'abc',
      }),
    );
    globalThis.fetch = fetchMock as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send({
        ...SEND_PAYLOAD,
        persist: true,
        conversation_id: 'abc',
        stream_reasoning: true,
      });
    });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.persist).toBe(true);
    expect(body.conversation_id).toBe('abc');
    expect(body.stream_reasoning).toBeUndefined();
    // Regular AiChatRequest fields still travel.
    expect(body.messages).toEqual(SEND_PAYLOAD.messages);
    expect(result.current.state.conversationId).toBe('abc');
  });

  it('propagates server-parsed artifacts verbatim on sync responses', async () => {
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        mockJsonResponse({
          model: 'm',
          content: '',
          usage: null,
          provider: 'p',
          backend: 'primary',
          fallback_used: false,
          canonical_model: 'm',
          requested_backend_mode: 'auto',
          policy: 'local_only',
          chosen_pool: 'local',
          decision_reason: 'policy_local_only',
          forced_local: false,
          pii_hits: [],
          artifacts: [
            {
              id: 'srv-1',
              type: 'document',
              title: 'A > B',
              content: 'body with > sign',
            },
          ],
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.artifacts).toHaveLength(1);
    expect(result.current.state.artifacts[0].id).toBe('srv-1');
    expect(result.current.state.artifacts[0].title).toBe('A > B');
    expect(result.current.state.artifacts[0].content).toBe('body with > sign');
  });

  it('ignores `<artifacts>` prefix collisions in sync responses', async () => {
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        mockJsonResponse({
          model: 'm',
          content: 'see <artifacts>list</artifacts> for details',
          usage: null,
          provider: 'p',
          backend: 'primary',
          fallback_used: false,
          canonical_model: 'm',
          requested_backend_mode: 'auto',
          policy: 'local_only',
          chosen_pool: 'local',
          decision_reason: 'policy_local_only',
          forced_local: false,
          pii_hits: [],
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.artifacts).toHaveLength(0);
    expect(result.current.state.contentBuffer).toBe(
      'see <artifacts>list</artifacts> for details',
    );
  });

  it('surfaces server-stripped content alongside pre-parsed artifacts', async () => {
    // The server owns parsing — the client just wires the structured
    // result into state so sync responses match the stream path shape.
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        mockJsonResponse({
          model: 'm',
          content: 'preface  tail',
          usage: null,
          provider: 'p',
          backend: 'primary',
          fallback_used: false,
          canonical_model: 'm',
          requested_backend_mode: 'auto',
          policy: 'local_only',
          chosen_pool: 'local',
          decision_reason: 'policy_local_only',
          forced_local: false,
          pii_hits: [],
          artifacts: [
            {
              id: 'srv-42',
              type: 'document',
              title: 'Draft',
              content: 'body **here**',
            },
          ],
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.contentBuffer).toBe('preface  tail');
    expect(result.current.state.artifacts).toHaveLength(1);
    const artifact = result.current.state.artifacts[0];
    expect(artifact.id).toBe('srv-42');
    expect(artifact.type).toBe('document');
    expect(artifact.title).toBe('Draft');
    expect(artifact.content).toBe('body **here**');
    expect(artifact.status).toBe('closed');
  });

  it('passes through literal `<artifact>` text when the server returns no artifacts', async () => {
    // Regression guard: with the client extractor gone, any `<artifact>`
    // text surviving in `response.content` must render as-is — the
    // server already decided it wasn't a real artifact.
    window.localStorage.setItem(STREAM_FLAG_KEY, 'false');
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(
        mockJsonResponse({
          model: 'm',
          content:
            'Use `<artifact type="document">body</artifact>` to wrap docs.',
          usage: null,
          provider: 'p',
          backend: 'primary',
          fallback_used: false,
          canonical_model: 'm',
          requested_backend_mode: 'auto',
          policy: 'local_only',
          chosen_pool: 'local',
          decision_reason: 'policy_local_only',
          forced_local: false,
          pii_hits: [],
          artifacts: [],
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.artifacts).toHaveLength(0);
    expect(result.current.state.contentBuffer).toBe(
      'Use `<artifact type="document">body</artifact>` to wrap docs.',
    );
  });

  it('falls back to sync once when stream start fails before the response opens', async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('stream unreachable'))
      .mockResolvedValueOnce(
        mockJsonResponse({
          model: 'mlx-community/model',
          content: 'fallback answer',
          usage: null,
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
          conversation_id: 'c-fallback',
        }),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.status).toBe('done');
    expect(result.current.state.transport).toBe('sync');
    expect(result.current.state.contentBuffer).toBe('fallback answer');
    expect(result.current.state.conversationId).toBe('c-fallback');
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('keeps sync fallback failures as pre-stream errors', async () => {
    globalThis.fetch = vi
      .fn()
      .mockRejectedValueOnce(new Error('stream unreachable'))
      .mockResolvedValueOnce(
        mockJsonResponse({ detail: { message: 'sync down' } }, 503),
      ) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.status).toBe('error');
    expect(result.current.state.streamOpened).toBe(false);
    expect(result.current.state.contentBuffer).toBe('');
    expect(result.current.state.errorMessage).toBe('sync down');
  });

  it('ignores unknown envelope types without throwing', async () => {
    const body = sseBytes([
      `event: novel_type\r\ndata: ${JSON.stringify({ seq: 0, timestamp_ms: 0, type: 'novel_type', data: { hello: 'world' } })}`,
      frame('content_delta', 1, { text: 'ok' }),
      frame('done', 2, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.contentBuffer).toBe('ok');
    expect(result.current.state.status).toBe('done');
  });

  it('accumulates tool_call_started + args_delta into toolCalls buffer', async () => {
    const body = sseBytes([
      frame('tool_call_started', 0, {
        call_id: 'c1',
        name: 'pms.search_issues',
        args_preview: '{"q":',
      }),
      frame('tool_call_args_delta', 1, { call_id: 'c1', delta: '{"q":"x"}' }),
      frame('tool_result', 2, {
        call_id: 'c1',
        status: 'ok',
        result_preview: 'found 3 issues',
        error: null,
      }),
      frame('done', 3, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.toolCalls).toHaveLength(1);
    expect(result.current.state.toolCalls[0].name).toBe('pms.search_issues');
    expect(result.current.state.toolCalls[0].argsBuffer).toBe('{"q":"x"}');
    expect(result.current.state.toolCalls[0].startedAtMs).toBe(0);
    expect(result.current.state.toolCalls[0].completedAtMs).toBe(0);
    expect(result.current.state.toolCalls[0].status).toBe('ok');
    expect(result.current.state.toolCalls[0].result?.status).toBe('ok');
  });

  it('handles approval_required then approval_resolved lifecycle', async () => {
    const body = sseBytes([
      frame('approval_required', 0, {
        approval_id: 'a1',
        tool: 'docs.create_page',
        resource_preview: null,
      }),
      frame('approval_resolved', 1, {
        approval_id: 'a1',
        decision: 'approved',
      }),
      frame('done', 2, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.pendingApprovals).toHaveLength(1);
    expect(result.current.state.pendingApprovals[0].decision).toBe('approved');
  });

  it('accumulates artifact deltas into a per-id buffer and marks closed on completed', async () => {
    const body = sseBytes([
      frame('artifact_started', 0, {
        artifact_id: 'art-1',
        artifact_type: 'document',
        title: 'Email',
      }),
      frame('artifact_delta', 1, { artifact_id: 'art-1', delta: 'Hello' }),
      frame('artifact_delta', 2, { artifact_id: 'art-1', delta: ' world' }),
      frame('artifact_completed', 3, { artifact_id: 'art-1' }),
      frame('done', 4, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    expect(result.current.state.artifacts).toEqual([
      {
        id: 'art-1',
        type: 'document',
        title: 'Email',
        language: null,
        content: 'Hello world',
        status: 'closed',
      },
    ]);
  });

  it('keeps multiple concurrent artifacts separate in the buffer', async () => {
    const body = sseBytes([
      frame('artifact_started', 0, {
        artifact_id: 'a',
        artifact_type: 'document',
        title: 'First',
      }),
      frame('artifact_started', 1, {
        artifact_id: 'b',
        artifact_type: 'document',
        title: 'Second',
      }),
      frame('artifact_delta', 2, { artifact_id: 'b', delta: 'B-body' }),
      frame('artifact_delta', 3, { artifact_id: 'a', delta: 'A-body' }),
      frame('artifact_completed', 4, { artifact_id: 'a' }),
      frame('done', 5, { finish_reason: 'stop', audit_id: null, meta: null }),
    ]);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(mockStreamResponse([body])) as typeof globalThis.fetch;

    const { result } = renderHook(() => useChatStream('token-abc'));
    await act(async () => {
      await result.current.send(SEND_PAYLOAD);
    });
    const artifacts = result.current.state.artifacts;
    expect(artifacts.map((a) => a.id)).toEqual(['a', 'b']);
    const a = artifacts.find((item) => item.id === 'a');
    const b = artifacts.find((item) => item.id === 'b');
    expect(a?.content).toBe('A-body');
    expect(a?.status).toBe('closed');
    expect(b?.content).toBe('B-body');
    // `b` never received artifact_completed — stays open until a
    // server-synthesized close on stream termination.
    expect(b?.status).toBe('open');
  });
});
