import { describe, expect, it } from 'vitest';

import type { AiChatResponse } from './chatbot-api';
import type { PendingApproval, RawAgentEvent } from './agent-events';
import {
  applyChatStreamEvent,
  cancelChatStreamState,
  CHAT_STREAM_INITIAL_STATE,
  createChatStreamStartState,
  failChatStreamState,
  mergePendingApprovals,
  resetChatStreamState,
  syncResponseToChatStreamState,
} from './chat-stream-state';

function envelope(type: string, data: unknown, timestampMs = 0): RawAgentEvent {
  return {
    type,
    seq: 0,
    timestamp_ms: timestampMs,
    data,
  };
}

function pendingApproval(
  overrides: Partial<PendingApproval> = {},
): PendingApproval {
  return {
    approval_id: 'approval-1',
    call_id: 'call-1',
    tool: 'docs.create_page',
    resource_preview: null,
    expires_at_ms: 123,
    decision: null,
    reason: null,
    ...overrides,
  };
}

describe('chat stream state', () => {
  it('keeps the pending user question in the shared run state', () => {
    const started = createChatStreamStartState({
      transport: 'stream',
      pendingUserContent: '복귀 후에도 보여야 하는 질문',
    });

    expect(started.pendingUserContent).toBe('복귀 후에도 보여야 하는 질문');
  });

  it('reduces streaming content, reasoning, usage, and done envelopes', () => {
    const started = createChatStreamStartState({ transport: 'stream' });
    const withContent = applyChatStreamEvent(
      started,
      envelope('content_delta', { text: 'Hel' }),
    ).next;
    const withReasoning = applyChatStreamEvent(
      withContent,
      envelope('reasoning_delta', { text: 'think' }),
    ).next;
    const withUsage = applyChatStreamEvent(
      withReasoning,
      envelope('usage', { total_tokens: 5 }),
    ).next;
    const done = applyChatStreamEvent(
      withUsage,
      envelope('done', {
        finish_reason: 'length',
        audit_id: null,
        meta: null,
      }),
    );

    expect(started.contentBuffer).toBe('');
    expect(withContent.contentBuffer).toBe('Hel');
    expect(withReasoning.reasoningBuffer).toBe('think');
    expect(withUsage.usage).toEqual({
      prompt_tokens: null,
      completion_tokens: null,
      total_tokens: 5,
    });
    expect(done.next.status).toBe('done');
    expect(done.next.finishReason).toBe('length');
    expect(done.terminal).toBe(true);
  });

  it('uses a pending approval as the fallback tool identity for late tool results', () => {
    const state = createChatStreamStartState({
      transport: 'stream',
      pendingApprovals: [pendingApproval()],
    });

    const { next } = applyChatStreamEvent(
      state,
      envelope(
        'tool_result',
        {
          call_id: 'call-1',
          status: 'ok',
          result_preview: '{"id":"page-1"}',
          error: null,
        },
        42,
      ),
    );

    expect(next.toolCalls).toMatchObject([
      {
        call_id: 'call-1',
        name: 'docs.create_page',
        status: 'ok',
        completedAtMs: 42,
        result: {
          status: 'ok',
          preview: '{"id":"page-1"}',
          error: null,
        },
      },
    ]);
  });

  it('deduplicates pending approvals by id with the latest value winning', () => {
    const merged = mergePendingApprovals(
      [pendingApproval({ resource_preview: 'old' })],
      [pendingApproval({ resource_preview: 'new', decision: 'approved' })],
    );

    expect(merged).toEqual([
      pendingApproval({ resource_preview: 'new', decision: 'approved' }),
    ]);
  });

  it('keeps pending approvals on reset only when requested', () => {
    const state = createChatStreamStartState({
      transport: 'stream',
      pendingApprovals: [pendingApproval()],
    });

    expect(resetChatStreamState(state)).toBe(CHAT_STREAM_INITIAL_STATE);
    expect(
      resetChatStreamState(state, { keepPendingApprovals: true })
        .pendingApprovals,
    ).toEqual([pendingApproval()]);
  });

  it('closes open artifacts on cancelled and failed terminal states', () => {
    const state = {
      ...createChatStreamStartState({ transport: 'stream' }),
      artifacts: [
        {
          id: 'artifact-1',
          type: 'document',
          title: null,
          language: null,
          content: 'draft',
          status: 'open' as const,
        },
      ],
    };

    expect(cancelChatStreamState(state).artifacts[0].status).toBe('closed');
    const failed = failChatStreamState(state, 'stream failed');
    expect(failed.status).toBe('error');
    expect(failed.errorMessage).toBe('stream failed');
    expect(failed.artifacts[0].status).toBe('closed');
  });

  it('maps sync responses into the public chat stream state shape', () => {
    const state = syncResponseToChatStreamState({
      model: 'chosen-model',
      content: 'answer',
      finish_reason: 'stop',
      usage: { prompt_tokens: 1, completion_tokens: 2, total_tokens: 3 },
      provider: 'provider',
      backend: 'primary',
      fallback_used: false,
      canonical_model: 'canonical-model',
      requested_backend_mode: 'auto',
      policy: 'local_only',
      chosen_pool: 'local',
      decision_reason: 'policy_local_only',
      forced_local: false,
      pii_hits: [],
      conversation_id: 'conversation-1',
      artifacts: [
        {
          id: 'artifact-1',
          type: 'document',
          title: 'Draft',
          language: null,
          content: 'body',
        },
      ],
    } as AiChatResponse);

    expect(state).toMatchObject({
      contentBuffer: 'answer',
      status: 'done',
      transport: 'sync',
      conversationId: 'conversation-1',
      doneMeta: {
        model: 'chosen-model',
        chosen_model: 'chosen-model',
        canonical_model: 'canonical-model',
      },
      artifacts: [
        {
          id: 'artifact-1',
          title: 'Draft',
          content: 'body',
          status: 'closed',
        },
      ],
    });
  });
});
