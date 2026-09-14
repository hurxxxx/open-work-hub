import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  decodeHermesApprovalReference,
  encodeHermesApprovalReference,
  hermesApprovalToolName,
  listHermesFileRevisions,
  previewHermesFileRevision,
  type HermesFileRevision,
} from './hermes-agent-api';

describe('Hermes approval references', () => {
  it('round-trips request ids without exposing a separate mutable lookup key', () => {
    const reference = {
      runId: 'run-123',
      requestId: 'approval:tool/한글?choice=once',
      sequence: 17,
    };

    expect(
      decodeHermesApprovalReference(encodeHermesApprovalReference(reference)),
    ).toEqual(reference);
  });

  it('rejects malformed or foreign approval ids', () => {
    expect(decodeHermesApprovalReference('legacy-approval')).toBeNull();
    expect(
      decodeHermesApprovalReference('hermes:run:not-a-number:id'),
    ).toBeNull();
    expect(decodeHermesApprovalReference('hermes::1:id')).toBeNull();
  });

  it('extracts the exact tool from the official Hermes MCP trust prompt', () => {
    expect(
      hermesApprovalToolName({
        command:
          "MCP tool 'tasks.create' on UNTRUSTED server 'owh-mcp-0123456789abcdefabcd-internal' wants to run. This tool is write-capable.",
      }),
    ).toBe('tasks.create');
    expect(
      hermesApprovalToolName({
        command:
          "MCP tool 'tasks.create' on UNTRUSTED server 'other' wants to run.",
      }),
    ).toBe('tool');
  });
});

describe('bounded immutable file preview', () => {
  const revision: HermesFileRevision = {
    id: 'revision-1',
    file_id: 'file-1',
    session_id: 'session-1',
    run_id: null,
    relative_path: 'file.txt',
    media_type: 'text/plain',
    size_bytes: 4,
    sha256: 'a'.repeat(64),
    created_at: '2026-09-14T01:00:00Z',
    expires_at: '2026-10-14T01:00:00Z',
  };
  afterEach(() => vi.unstubAllGlobals());

  it('lists conversation revisions without fabricating a file selector', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ data: [], has_more: false }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    await listHermesFileRevisions('token', 'conversation');
    const url = new URL(fetchMock.mock.calls[0][0], 'https://test.invalid');
    expect(url.pathname).toBe(
      '/api/v1/agent/sessions/conversation/file-revisions',
    );
    expect(url.searchParams.has('file_id')).toBe(false);
    expect(url.searchParams.get('limit')).toBe('100');
  });

  it('rejects an oversized declared version before starting a request', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await expect(
      previewHermesFileRevision(
        'token',
        revision,
        3,
        new AbortController().signal,
      ),
    ).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['longer-than-declared', 'a'])(
    'rejects a response whose bytes differ from metadata: %s',
    async (text) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(text)));
      await expect(
        previewHermesFileRevision(
          'token',
          revision,
          100,
          new AbortController().signal,
        ),
      ).rejects.toThrow();
    },
  );

  it('requests only the immutable authenticated path and disallows redirects/caching', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('test'));
    vi.stubGlobal('fetch', fetchMock);
    const blob = await previewHermesFileRevision(
      'token',
      revision,
      100,
      new AbortController().signal,
    );
    expect(blob.size).toBe(4);
    expect(blob.type).toBe('text/plain');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/agent/file-revisions/revision-1/content',
      expect.objectContaining({
        redirect: 'error',
        cache: 'no-store',
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it('rejects an unavailable file without returning its body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('denied', { status: 404 })),
    );
    await expect(
      previewHermesFileRevision(
        'token',
        revision,
        100,
        new AbortController().signal,
      ),
    ).rejects.toThrow();
  });
});
