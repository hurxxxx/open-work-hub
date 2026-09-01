import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-route-policy';
import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';
import {
  createHermesTerminalSession,
  hermesTerminalWebSocketUrl,
  listHermesTerminalFiles,
  stopHermesTerminalSession,
} from './hermes-terminal-api';

describe('Hermes terminal API protocol', () => {
  beforeEach(() => {
    configureWorkspaceApiRoutePolicy(
      createWorkspaceApiRoutePolicy({
        sources: [
          {
            contract: {
              workspaceApiPrefixes: ['/api/v1/hermes-terminal'],
            },
          },
        ],
      }),
    );
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.unstubAllGlobals();
  });

  it('keeps the auth token out of the workspace-scoped websocket URL', () => {
    const url = new URL(
      hermesTerminalWebSocketUrl('workspace slug', 'session id'),
    );

    expect(url.protocol).toBe('ws:');
    expect(url.pathname).toBe(
      '/api/v1/workspaces/workspace%20slug/hermes-terminal/sessions/session%20id/ws',
    );
    expect(url.search).toBe('');
  });

  it('sends YOLO only after the caller supplies explicit acknowledgement', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 201,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);

    await createHermesTerminalSession('test-token', 'hq', {
      mode: 'yolo',
      risk_acknowledged: true,
      cols: 120,
      rows: 36,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/hq/hermes-terminal/sessions',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          mode: 'yolo',
          risk_acknowledged: true,
          cols: 120,
          rows: 36,
        }),
      }),
    );
  });

  it('keeps session stop and contained file browsing workspace scoped', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ items: [] }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await listHermesTerminalFiles(
      'test-token',
      'hq',
      'session id',
      'reports/2026',
    );
    await stopHermesTerminalSession('test-token', 'hq', 'session id');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/hq/hermes-terminal/sessions/session%20id/files?path=reports%2F2026',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/hq/hermes-terminal/sessions/session%20id/stop',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
