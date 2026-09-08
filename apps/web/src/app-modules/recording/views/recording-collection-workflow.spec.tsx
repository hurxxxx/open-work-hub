import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Recording } from '../api/recording-api';
import {
  useRecordingCollectionWorkflow,
  type RecordingCollectionClient,
  type RecordingCollectionScope,
} from './recording-collection-workflow';

function recording(overrides: Partial<Recording> = {}): Recording {
  return {
    id: 'recording-1',
    owner_id: 'user-1',
    title: 'Daily Standup',
    started_at: '2026-05-30T09:00:00Z',
    ended_at: null,
    duration_sec: 65,
    source: 'quick_record',
    storage_key: null,
    file_size: 1536,
    mime_type: 'audio/webm',
    audio_status: 'saved',
    transcript_status: 'done',
    summary_status: 'done',
    meeting_insight_status: 'done',
    progress_pct: 100,
    failure_reason: null,
    transcribe_started_at: null,
    transcribe_completed_at: null,
    created_at: '2026-05-30T09:00:00Z',
    updated_at: '2026-05-30T09:00:00Z',
    trashed_at: null,
    targets: [],
    ...overrides,
  } as Recording;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((innerResolve, innerReject) => {
    resolve = innerResolve;
    reject = innerReject;
  });
  return { promise, resolve, reject };
}

function client(
  overrides: Partial<RecordingCollectionClient> = {},
): RecordingCollectionClient {
  return {
    listRecordings: vi
      .fn()
      .mockResolvedValue({ items: [recording()], total: 1 }),
    retryRecording: vi.fn().mockResolvedValue(recording()),
    deleteRecording: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

const viewScope: RecordingCollectionScope = { kind: 'view', view: 'mine' };
const targetScope: RecordingCollectionScope = {
  kind: 'target',
  targetApp: 'meeting',
  targetType: 'meeting',
  targetId: 'meeting-1',
};

function renderWorkflow(
  options: {
    client?: RecordingCollectionClient;
    scope?: RecordingCollectionScope;
    token?: string | null;
  } = {},
) {
  const usedClient = options.client ?? client();
  const rendered = renderHook(() =>
    useRecordingCollectionWorkflow({
      token: options.token === undefined ? 'token-1' : options.token,
      scope: options.scope ?? viewScope,
      messages: {
        loadFailed: 'load failed',
        retryFailed: 'retry failed',
        deleteFailed: 'delete failed',
      },
      client: usedClient,
    }),
  );
  return { ...rendered, client: usedClient };
}

describe('recording collection workflow', () => {
  it('loads view and target scopes', async () => {
    const viewClient = client();
    renderWorkflow({ client: viewClient, scope: viewScope });

    await waitFor(() => {
      expect(viewClient.listRecordings).toHaveBeenCalledWith('token-1', {
        view: 'mine',
      });
    });

    const targetClient = client();
    renderWorkflow({ client: targetClient, scope: targetScope });

    await waitFor(() => {
      expect(targetClient.listRecordings).toHaveBeenCalledWith('token-1', {
        target_app: 'meeting',
        target_type: 'meeting',
        target_id: 'meeting-1',
      });
    });
  });

  it('clears items and stores fallback load errors', async () => {
    const failingClient = client({
      listRecordings: vi.fn().mockRejectedValue('failed'),
    });
    const { result } = renderWorkflow({ client: failingClient });

    await waitFor(() => {
      expect(result.current.error).toBe('load failed');
      expect(result.current.items).toEqual([]);
      expect(result.current.loading).toBe(false);
    });
  });

  it('tracks retry busy state and refreshes after retry', async () => {
    const retryResult = deferred<Recording>();
    const retryClient = client({
      retryRecording: vi.fn().mockReturnValue(retryResult.promise),
    });
    const { result } = renderWorkflow({ client: retryClient });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    vi.mocked(retryClient.listRecordings).mockClear();

    let retryPromise!: Promise<void>;
    act(() => {
      retryPromise = result.current.retry('recording-1');
    });

    expect(result.current.busyId).toBe('recording-1');
    await act(async () => {
      retryResult.resolve(recording());
      await retryPromise;
    });

    expect(retryClient.retryRecording).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
    );
    expect(retryClient.listRecordings).toHaveBeenCalledTimes(1);
    expect(result.current.busyId).toBeNull();
  });

  it('honors delete confirmation before removing and refreshing', async () => {
    const deleteClient = client();
    const { result } = renderWorkflow({ client: deleteClient });

    await waitFor(() => expect(result.current.items).toHaveLength(1));
    vi.mocked(deleteClient.listRecordings).mockClear();

    await act(async () => {
      await result.current.remove('recording-1', async () => false);
    });

    expect(deleteClient.deleteRecording).not.toHaveBeenCalled();

    await act(async () => {
      await result.current.remove('recording-1', async () => true);
    });

    expect(deleteClient.deleteRecording).toHaveBeenCalledWith(
      'token-1',
      'recording-1',
    );
    expect(deleteClient.listRecordings).toHaveBeenCalledTimes(1);
  });

  it('guards missing token or workspace without API calls', async () => {
    const guardedClient = client();
    const { result } = renderWorkflow({
      client: guardedClient,
      token: null,
    });

    await act(async () => {
      await result.current.retry('recording-1');
      await result.current.remove('recording-1');
      await result.current.refresh();
    });

    expect(guardedClient.listRecordings).not.toHaveBeenCalled();
    expect(guardedClient.retryRecording).not.toHaveBeenCalled();
    expect(guardedClient.deleteRecording).not.toHaveBeenCalled();
    expect(result.current.error).toBe('retry failed');
  });
});
