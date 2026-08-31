import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  agentTerminalWebSocketUrl,
  base64ToBytes,
  bytesToBase64,
  createAgentTerminalSession,
  deleteAgentTerminalSession,
  getAgentTerminalGitCommit,
  getAgentTerminalGitCommitDiff,
  getAgentTerminalGitDiff,
  getAgentTerminalGitHistory,
  getAgentTerminalGitStatus,
  getAgentTerminalGitSummary,
  listAgentTerminalCodexThreads,
  stopAgentTerminalSession,
} from './agent-terminal-api';

describe('agent terminal API protocol', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds a same-origin websocket URL without putting the token in the URL', () => {
    const url = new URL(agentTerminalWebSocketUrl('session id'));

    expect(url.protocol).toBe('ws:');
    expect(url.pathname).toBe(
      '/api/v1/agent-terminal/sessions/session%20id/ws',
    );
    expect(url.search).toBe('');
  });

  it('round-trips UTF-8 terminal bytes through base64 frames', () => {
    const input = new TextEncoder().encode('안녕, Codex\r\n');

    expect(Array.from(base64ToBytes(bytesToBase64(input)))).toEqual(
      Array.from(input),
    );
  });

  it('keeps stopping an active session separate from deleting its history', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({}),
      })
      .mockResolvedValueOnce({
        status: 204,
        ok: true,
        json: async () => null,
      });
    vi.stubGlobal('fetch', fetchMock);

    await stopAgentTerminalSession('test-token', 'session id');
    await deleteAgentTerminalSession('test-token', 'session id');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/agent-terminal/sessions/session%20id/stop',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/agent-terminal/sessions/session%20id',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('lists Codex history and passes the selected thread when resuming', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);

    await listAgentTerminalCodexThreads('test-token');
    await createAgentTerminalSession('test-token', {
      root_key: 'open-work-hub',
      codex_thread_id: '11111111-1111-1111-1111-111111111111',
      cols: 120,
      rows: 36,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/agent-terminal/codex/threads',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/agent-terminal/sessions',
      expect.objectContaining({
        body: JSON.stringify({
          root_key: 'open-work-hub',
          codex_thread_id: '11111111-1111-1111-1111-111111111111',
          cols: 120,
          rows: 36,
        }),
        method: 'POST',
      }),
    );
  });

  it('encodes the configured root and selected Git change', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getAgentTerminalGitStatus('test-token', 'project root');
    await getAgentTerminalGitDiff('test-token', 'project root', {
      path: 'apps/web/a b.tsx',
      scope: 'unstaged',
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/agent-terminal/roots/project%20root/git/status',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/agent-terminal/roots/project%20root/git/diff?path=apps%2Fweb%2Fa+b.tsx&scope=unstaged',
      expect.any(Object),
    );
  });

  it('keeps repository history and commit reads scoped to the configured root', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);

    await getAgentTerminalGitSummary('test-token', 'project root');
    await getAgentTerminalGitHistory('test-token', 'project root', {
      limit: 25,
      offset: 50,
    });
    await getAgentTerminalGitCommit('test-token', 'project root', 'abc/123');
    await getAgentTerminalGitCommitDiff(
      'test-token',
      'project root',
      'abc/123',
      'apps/web/a b.tsx',
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/agent-terminal/roots/project%20root/git/summary',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/agent-terminal/roots/project%20root/git/history?limit=25&offset=50',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/agent-terminal/roots/project%20root/git/commits/abc%2F123',
      expect.any(Object),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      '/api/v1/agent-terminal/roots/project%20root/git/commits/abc%2F123/diff?path=apps%2Fweb%2Fa+b.tsx',
      expect.any(Object),
    );
  });
});
