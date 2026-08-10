import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiRequestError } from '@/src/platform/api/client';
import { DM_MAX_ATTACHMENT_BYTES } from '@open-work-hub/contracts/dm';

import {
  createDirectDmConversation,
  createGroupDmConversation,
  addDmConversationParticipants,
  listDmConversations,
  searchDmUsers,
  sendDmMessage,
  uploadDmAttachment,
} from './dm-api';

describe('web DM API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn() as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('normalizes DM conversation responses through the shared contract', async () => {
    mockJsonResponse({ items: [conversation()] });

    await expect(listDmConversations('token-1')).resolves.toEqual({
      items: [
        {
          ...conversation(),
          title: null,
          other_user: null,
          last_message: null,
          last_read_message_id: null,
          muted_at: null,
        },
      ],
    });
    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/dm/conversations',
      expect.objectContaining({
        cache: 'no-store',
      }),
    );
  });

  it('rejects malformed DM responses before callers render them', async () => {
    const payload = [
      {
        id: 'u/1',
        email: 'user@example.test',
        full_name: 'User One',
      },
    ];
    mockJsonResponse(payload);

    let caught: unknown;
    try {
      await searchDmUsers('token-1', 'user');
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(ApiRequestError);
    expect(caught).toMatchObject({
      status: 502,
      message: 'Invalid response format for dm:users.',
      payload,
    });
  });

  it('searches the global user directory with the requested limit', async () => {
    mockJsonResponse([]);

    await expect(
      searchDmUsers('token-1', 'user', {
        limit: 10,
      }),
    ).resolves.toEqual([]);

    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/dm/users?q=user&limit=10',
      expect.objectContaining({
        cache: 'no-store',
      }),
    );
  });

  it('scopes user search to a workspace when requested', async () => {
    mockJsonResponse([]);

    await expect(
      searchDmUsers('token-1', 'user', {
        includeCurrent: true,
        limit: 10,
        workspaceKey: '기술연구소',
      }),
    ).resolves.toEqual([]);

    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/dm/users?q=user&limit=10&include_current=true&workspace_key=%EA%B8%B0%EC%88%A0%EC%97%B0%EA%B5%AC%EC%86%8C',
      expect.objectContaining({
        cache: 'no-store',
      }),
    );
  });

  it('normalizes sent messages and keeps the shared route builder in use', async () => {
    mockJsonResponse(message({ id: 'sent-1' }));

    await expect(
      sendDmMessage('token-1', 'c1', '  hello  ', [' a1 '], ' m1 '),
    ).resolves.toEqual({
      ...message({ id: 'sent-1' }),
      attachments: [],
    });
    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/dm/conversations/c1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          body: 'hello',
          attachment_ids: ['a1'],
          reply_to_message_id: 'm1',
        }),
      }),
    );
  });

  it('normalizes DM request bodies before fetch receives them', async () => {
    mockJsonResponse(conversation({ id: 'direct-1' }));
    await createDirectDmConversation('token-1', ' u1 ');

    mockJsonResponse(conversation({ id: 'group-1' }));
    await createGroupDmConversation('token-1', [' u1 ', 'u2'], '  Team  ');

    mockJsonResponse(conversation({ id: 'members-1' }));
    await addDmConversationParticipants('token-1', 'c1', [' u3 ']);

    expect(fetchMock()).toHaveBeenNthCalledWith(
      1,
      '/api/v1/dm/conversations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ recipient_user_id: 'u1' }),
      }),
    );
    expect(fetchMock()).toHaveBeenNthCalledWith(
      2,
      '/api/v1/dm/conversations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          participant_user_ids: ['u1', 'u2'],
          title: 'Team',
        }),
      }),
    );
    expect(fetchMock()).toHaveBeenNthCalledWith(
      3,
      '/api/v1/dm/conversations/c1/participants',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ user_ids: ['u3'] }),
      }),
    );
  });

  it('rejects malformed DM request bodies before fetch', () => {
    expect(() => sendDmMessage('token-1', 'c1', '   ', [])).toThrow(
      'Invalid request format for dm:send-message.',
    );
    expect(() => createDirectDmConversation('token-1', 'u/1')).toThrow(
      'Invalid request format for dm:create-conversation.',
    );

    expect(fetchMock()).not.toHaveBeenCalled();
  });

  it('rejects malformed attachment uploads before fetch', () => {
    const oversized = new File(['x'], 'too-large.bin', {
      type: 'application/octet-stream',
    });
    Object.defineProperty(oversized, 'size', {
      configurable: true,
      value: DM_MAX_ATTACHMENT_BYTES + 1,
    });

    expect(() => uploadDmAttachment('token-1', 'c1', oversized)).toThrow(
      `Attachments must be ${DM_MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB or smaller.`,
    );
    expect(() =>
      uploadDmAttachment('token-1', 'conversation/1', new File(['x'], 'x.txt')),
    ).toThrow('DM route id');
    expect(fetchMock()).not.toHaveBeenCalled();
  });
});

function mockJsonResponse(payload: unknown): void {
  fetchMock().mockResolvedValueOnce(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

function fetchMock(): ReturnType<typeof vi.fn> {
  return globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
}

function conversation(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: 'c1',
    conversation_type: 'direct',
    thread_type: 'direct',
    display_name: 'Direct',
    participants: [],
    participant_count: 2,
    unread_count: 0,
    created_by_id: 'u1',
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

function message(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: 'm1',
    conversation_id: 'c1',
    thread_id: 'c1',
    sequence: 1,
    sender_id: 'u1',
    sender_name: 'User One',
    read_state: {
      unread_count: 0,
      read_by_all: true,
    },
    reply_to: null,
    body: 'hello',
    attachments: [],
    created_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}
