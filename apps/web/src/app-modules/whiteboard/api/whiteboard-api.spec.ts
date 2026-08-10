import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';
import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  getWhiteboard,
  listWhiteboardHub,
  listWhiteboardShareableUsers,
  normalizeWhiteboardScene,
  WhiteboardApiError,
} from './whiteboard-api';
import { whiteboardApiRoutes } from './whiteboard-routes';

describe('whiteboard scene codec', () => {
  it('compacts duplicate element ids with the last element winning', () => {
    const firstShape = { id: 'shape-1', version: 1 };
    const anonymous = { type: 'text' };
    const secondShape = { id: 'shape-2', version: 1 };
    const latestShape = { id: 'shape-1', version: 2 };

    expect(
      normalizeWhiteboardScene({
        elements: [firstShape, anonymous, secondShape, latestShape],
        appState: { zoom: 1 },
        files: { file1: { id: 'file1' } },
      }).elements,
    ).toEqual([latestShape, secondShape, anonymous]);
  });

  it('defaults invalid scene values', () => {
    expect(normalizeWhiteboardScene(null)).toEqual({
      elements: [],
      appState: {},
      files: {},
    });
    expect(normalizeWhiteboardScene(['not', 'a', 'scene'])).toEqual({
      elements: [],
      appState: {},
      files: {},
    });
    expect(
      normalizeWhiteboardScene({
        title: 'Sketch',
        elements: 'bad',
        appState: null,
        files: [],
      }),
    ).toEqual({
      title: 'Sketch',
      elements: [],
      appState: {},
      files: {},
    });
  });
});

describe('whiteboard API routes', () => {
  it('omits empty query values while preserving encoded values', () => {
    expect(
      whiteboardApiRoutes.hub({
        view: 'recent',
        q: '',
        page: 0,
        page_size: 25,
        target_id: 'task/1',
      }),
    ).toBe(
      '/api/v1/whiteboard/hub?view=recent&page=0&page_size=25&target_id=task%2F1',
    );
    expect(whiteboardApiRoutes.shareableUsers()).toBe(
      '/api/v1/whiteboard/shareable-users',
    );
  });

  it('encodes item, shared link, and sharing path segments', () => {
    expect(whiteboardApiRoutes.item('board/1')).toBe(
      '/api/v1/whiteboard/items/board%2F1',
    );
    expect(whiteboardApiRoutes.sharedLinkItem('share token/1')).toBe(
      '/api/v1/whiteboard/shared-links/share%20token%2F1/item',
    );
    expect(whiteboardApiRoutes.userShare('board/1', 'user 1')).toBe(
      '/api/v1/whiteboard/items/board%2F1/sharing/users/user%201',
    );
  });
});

describe('whiteboard API client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
    globalThis.fetch = vi.fn() as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    resetWorkspaceApiRoutePolicy();
    vi.restoreAllMocks();
  });

  it('uses route helpers for omitted query strings and workspace rewriting', async () => {
    mockJsonResponse({ items: [], page: 1, page_size: 25, total: 0 });

    await listWhiteboardHub(
      'token-1',
      { view: 'recent', q: '', page: 0, page_size: 25, target_id: 'task/1' },
      'team space',
    );

    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/workspaces/team%20space/whiteboard/hub?view=recent&page=0&page_size=25&target_id=task%2F1',
      expect.objectContaining({ cache: 'no-store' }),
    );

    mockJsonResponse([]);
    await listWhiteboardShareableUsers('token-1', '', 'team space');

    expect(fetchMock()).toHaveBeenLastCalledWith(
      '/api/v1/workspaces/team%20space/whiteboard/shareable-users',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('wraps ApiRequestError failures as WhiteboardApiError', async () => {
    mockJsonResponse({ detail: 'Whiteboard unavailable.' }, 503);

    let caught: unknown;
    try {
      await getWhiteboard('token-1', 'board 1', 'team space');
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeInstanceOf(WhiteboardApiError);
    expect(caught).toMatchObject({
      status: 503,
      message: 'Whiteboard unavailable.',
    });
    expect(fetchMock()).toHaveBeenCalledWith(
      '/api/v1/workspaces/team%20space/whiteboard/items/board%201',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });
});

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
