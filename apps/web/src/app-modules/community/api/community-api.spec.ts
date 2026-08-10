import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { COMMUNITY_CHANNELS_CHANGED_EVENT } from '@/src/platform/community/community-channel-events';
import {
  invalidateCommunityChannelsCache,
  listCommunityChannels,
  listCommunityPosts,
  markCommunityPostRead,
  resolveCommunityPostMediaUrls,
} from './community-api';

describe('community API channel cache', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    invalidateCommunityChannelsCache();
    globalThis.fetch = vi.fn() as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    invalidateCommunityChannelsCache();
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('shares in-flight channel loads and reuses the resolved response', async () => {
    mockJsonResponse({
      channels: [channel({ key: 'suggestions', name: 'Suggestions' })],
    });

    const [first, second] = await Promise.all([
      listCommunityChannels('token-1'),
      listCommunityChannels('token-1'),
    ]);
    const cached = await listCommunityChannels('token-1');

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(first.channels[0].key).toBe('suggestions');
    expect(second.channels[0].key).toBe('suggestions');
    expect(cached.channels[0].key).toBe('suggestions');
    expect(cached).not.toBe(first);
    expect(cached.channels[0]).not.toBe(first.channels[0]);
  });

  it('reloads channel cache after explicit refresh or change event', async () => {
    mockJsonResponse({
      channels: [channel({ key: 'suggestions', name: 'Suggestions' })],
    });
    await listCommunityChannels('token-1');

    mockJsonResponse({
      channels: [channel({ key: 'notice', name: 'Notice' })],
    });
    const refreshed = await listCommunityChannels('token-1', {
      forceRefresh: true,
    });
    expect(refreshed.channels[0].key).toBe('notice');

    window.dispatchEvent(new Event(COMMUNITY_CHANNELS_CHANGED_EVENT));

    mockJsonResponse({
      channels: [channel({ key: 'questions', name: 'Questions' })],
    });
    const afterEvent = await listCommunityChannels('token-1');

    expect(fetchMock()).toHaveBeenCalledTimes(3);
    expect(afterEvent.channels[0].key).toBe('questions');
  });

  it('resolves community post media with the post password context', async () => {
    mockJsonResponse({
      resolved: {
        'media:00000000-0000-0000-0000-000000000001':
          '/api/v1/media/content/00000000-0000-0000-0000-000000000001?signature=sig',
      },
    });

    const response = await resolveCommunityPostMediaUrls(
      'token-1',
      'post 1',
      ['media:00000000-0000-0000-0000-000000000001'],
      'secret-pw',
    );

    expect(response.resolved).toHaveProperty(
      'media:00000000-0000-0000-0000-000000000001',
    );
    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/community/posts/post%201/media/resolve',
      expect.objectContaining({
        body: JSON.stringify({
          urls: ['media:00000000-0000-0000-0000-000000000001'],
          password: 'secret-pw',
        }),
        method: 'POST',
      }),
    );
  });

  it('sends post list pagination and search parameters', async () => {
    mockJsonResponse({
      page: 1,
      pageSize: 20,
      posts: [],
      total: 0,
    });

    await listCommunityPosts('token-1', 'team news', {
      page: 2,
      pageSize: 50,
      search: ' release ',
    });

    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/community/channels/team%20news/posts?page=2&page_size=50&q=release',
      expect.any(Object),
    );
  });

  it('marks a community post as read with an idempotent request', async () => {
    fetchMock().mockResolvedValueOnce(new Response(null, { status: 204 }));

    await markCommunityPostRead('token-1', 'post 1');

    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/community/posts/post%201/read',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

function channel(
  overrides: Partial<
    Awaited<ReturnType<typeof listCommunityChannels>>['channels'][number]
  > = {},
) {
  return {
    active: true,
    adminOnlyContent: false,
    description: '',
    forceAnonymous: false,
    id: `channel-${overrides.key ?? 'suggestions'}`,
    key: 'suggestions',
    name: 'Suggestions',
    position: 0,
    readOnly: false,
    templateBody: '',
    templateTitle: '',
    ...overrides,
  };
}

function mockJsonResponse(payload: unknown, status = 200): void {
  fetchMock().mockResolvedValueOnce(
    new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
}

function fetchMock(): ReturnType<typeof vi.fn> {
  return globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
}
