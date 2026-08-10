import { describe, expect, it, vi } from 'vitest';

import type {
  RecordingChunkState,
  RecordingSessionState,
} from './recording-session-db';
import {
  RecordingRecorderRuntime,
  type RecordingCompletionPayload,
  type RecordingRecorderRuntimeEnvironment,
  type RecordingRecorderRuntimeStore,
} from './recording-recorder-runtime';

const NOW = 1_700_000_120_000;

interface SavedRecording {
  id: string;
  payload: RecordingCompletionPayload;
}

function chunk(seq: number, size: number, uploadedAt: number | null = null): RecordingChunkState {
  return {
    stagingId: 'staging-1',
    seq,
    blob: new Blob(['x'.repeat(size)]),
    sha256: `sha-${seq}`,
    uploadedAt,
    createdAt: NOW + seq,
  };
}

function session(overrides: Partial<RecordingSessionState> = {}): RecordingSessionState {
  return {
    stagingId: 'staging-1',
    workspaceSlug: 'hq',
    scopeKey: 'hq:recording:unlinked',
    idempotencyKey: 'idem-1',
    mimeType: 'audio/webm',
    title: null,
    source: 'quick_record',
    initialTargetApp: null,
    initialTargetType: null,
    initialTargetId: null,
    linkedTaskId: null,
    startedAt: NOW - 60_000,
    completedAt: null,
    finalizeRequestedAt: null,
    lastChunkSeq: -1,
    lastUploadedSeq: -1,
    uploadCompletedAt: null,
    interruptedAt: null,
    interruptionReason: null,
    meetingId: null,
    ...overrides,
  };
}

function createStore(input: {
  chunks?: RecordingChunkState[];
  session?: RecordingSessionState | null;
} = {}): RecordingRecorderRuntimeStore & {
  chunks: RecordingChunkState[];
  session: RecordingSessionState | null;
  updates: Array<Partial<RecordingSessionState>>;
  completed: string[];
  cleared: string[];
} {
  const store = {
    chunks: [...(input.chunks ?? [])],
    session: input.session ?? session(),
    updates: [] as Array<Partial<RecordingSessionState>>,
    completed: [] as string[],
    cleared: [] as string[],
    async appendChunk(item: RecordingChunkState) {
      store.chunks.push(item);
    },
    async getChunks() {
      return [...store.chunks].sort((left, right) => left.seq - right.seq);
    },
    async getPendingChunks() {
      return store.chunks
        .filter((item) => item.uploadedAt == null)
        .sort((left, right) => left.seq - right.seq);
    },
    async markChunkUploaded(_stagingId: string, seq: number) {
      const item = store.chunks.find((candidate) => candidate.seq === seq);
      if (item) {
        item.uploadedAt = NOW + seq;
      }
    },
    async updateSessionProgress(_stagingId: string, update: Partial<RecordingSessionState>) {
      store.updates.push(update);
      if (store.session) {
        store.session = { ...store.session, ...update };
      }
    },
    async getSession() {
      return store.session;
    },
    async listIncompleteSessions(options: { workspaceSlug: string; scopeKey?: string | null }) {
      if (!store.session || store.session.completedAt != null) {
        return [];
      }
      if (store.session.workspaceSlug !== options.workspaceSlug) {
        return [];
      }
      if (options.scopeKey && store.session.scopeKey !== options.scopeKey) {
        return [];
      }
      return [store.session];
    },
    async markSessionComplete(stagingId: string) {
      store.completed.push(stagingId);
      if (store.session) {
        store.session = {
          ...store.session,
          completedAt: NOW,
          uploadCompletedAt: NOW,
        };
      }
    },
    async clearSession(stagingId: string) {
      store.cleared.push(stagingId);
      store.session = null;
      store.chunks = [];
    },
  };
  return store;
}

function createEnvironment(
  overrides: Partial<RecordingRecorderRuntimeEnvironment> = {},
): RecordingRecorderRuntimeEnvironment & {
  timers: Map<number, () => void>;
  clearedTimers: number[];
} {
  let nextTimer = 1;
  const timers = new Map<number, () => void>();
  const clearedTimers: number[] = [];
  return {
    timers,
    clearedTimers,
    now: () => NOW,
    digestBlob: async (blob) => `digest-${blob.size}`,
    registerBackgroundSync: vi.fn(async () => undefined),
    setTimeout: vi.fn((callback) => {
      const id = nextTimer;
      nextTimer += 1;
      timers.set(id, callback);
      return id;
    }),
    clearTimeout: vi.fn((timer) => {
      clearedTimers.push(timer);
      timers.delete(timer);
    }),
    ...overrides,
  };
}

function createRuntime(input: {
  store?: ReturnType<typeof createStore>;
  environment?: ReturnType<typeof createEnvironment>;
  canUpload?: () => boolean;
} = {}) {
  const store = input.store ?? createStore();
  const environment = input.environment ?? createEnvironment();
  const callbacks = {
    onStatsChanged: vi.fn(),
    onChunkWriteFailed: vi.fn(),
    onPumpFailed: vi.fn(),
    onFinalizeStarted: vi.fn(),
    onFinalizeFailed: vi.fn(),
    onFinalizeFinished: vi.fn(),
    onUploadSaved: vi.fn(),
  };
  const client = {
    headUpload: vi.fn(async () => 0),
    uploadChunk: vi.fn(async (_stagingId: string, offset: number, blob: Blob) =>
      offset + blob.size),
    completeUpload: vi.fn(async (_stagingId: string, payload: RecordingCompletionPayload) => ({
      id: 'recording-1',
      payload,
    })),
  };
  const runtime = new RecordingRecorderRuntime<SavedRecording>({
    store,
    client,
    environment,
    defaults: {
      title: () => 'Fallback title',
      source: () => 'quick_record',
    },
    messages: {
      tusOffsetConflict: () => 'offset conflict',
    },
    callbacks,
    canUpload: input.canUpload,
  });
  return { runtime, store, environment, callbacks, client };
}

describe('RecordingRecorderRuntime', () => {
  it('writes recorder chunks through storage ports and reports local stats', async () => {
    const { runtime, store, callbacks, client } = createRuntime({
      canUpload: () => false,
    });

    await runtime.queueChunkWrite('staging-1', 0, new Blob(['hello']));

    expect(store.chunks).toMatchObject([
      {
        stagingId: 'staging-1',
        seq: 0,
        sha256: 'digest-5',
        uploadedAt: null,
        createdAt: NOW,
      },
    ]);
    expect(store.updates).toContainEqual({ lastChunkSeq: 0 });
    expect(callbacks.onStatsChanged).toHaveBeenCalledWith('staging-1', {
      queuedBytes: 5,
      uploadedBytes: 0,
    });
    expect(client.uploadChunk).not.toHaveBeenCalled();
  });

  it('pumps chunks, completes requested finalization, and clears the local session', async () => {
    const { runtime, store, callbacks, client } = createRuntime({
      store: createStore({
        chunks: [chunk(0, 5)],
        session: session({
          title: 'Design review',
          source: 'live_recording',
          finalizeRequestedAt: NOW - 1_000,
          startedAt: NOW - 125_000,
        }),
      }),
    });

    await runtime.pumpUploads('staging-1');

    expect(client.uploadChunk).toHaveBeenCalledWith(
      'staging-1',
      0,
      expect.objectContaining({ size: 5 }),
      'sha-0',
    );
    expect(client.completeUpload).toHaveBeenCalledWith('staging-1', {
      title: 'Design review',
      duration_sec_estimate: 125,
      source: 'live_recording',
    });
    expect(store.completed).toEqual(['staging-1']);
    expect(store.cleared).toEqual(['staging-1']);
    expect(callbacks.onFinalizeStarted).toHaveBeenCalledWith('staging-1');
    expect(callbacks.onUploadSaved).toHaveBeenCalledWith(
      'staging-1',
      expect.objectContaining({ id: 'recording-1' }),
    );
    expect(callbacks.onFinalizeFinished).toHaveBeenCalledWith('staging-1');
  });

  it('waits for queued chunk writes before preparing finalization', async () => {
    let resolveDigest: ((value: string) => void) | null = null;
    const environment = createEnvironment({
      digestBlob: () =>
        new Promise<string>((resolve) => {
          resolveDigest = resolve;
        }),
    });
    const { runtime, store } = createRuntime({
      environment,
      canUpload: () => false,
    });

    const write = runtime.queueChunkWrite('staging-1', 0, new Blob(['late']));
    let prepared = false;
    const prepare = runtime.prepareFinalize('staging-1').then(() => {
      prepared = true;
    });

    await Promise.resolve();
    expect(prepared).toBe(false);

    resolveDigest?.('digest-late');
    await Promise.all([write, prepare]);

    expect(prepared).toBe(true);
    expect(store.updates).toContainEqual({ finalizeRequestedAt: NOW });
    expect(store.chunks[0]).toMatchObject({ sha256: 'digest-late' });
  });

  it('registers background sync and owns retry timer cleanup after pump failure', async () => {
    const environment = createEnvironment();
    const { runtime, callbacks, client } = createRuntime({
      environment,
      store: createStore({ chunks: [chunk(0, 5)] }),
    });
    client.headUpload.mockRejectedValueOnce(new Error('offline'));

    await runtime.pumpUploads('staging-1');

    expect(callbacks.onPumpFailed).toHaveBeenCalledWith('staging-1', expect.any(Error));
    expect(environment.registerBackgroundSync).toHaveBeenCalledTimes(1);
    expect(environment.timers.size).toBe(1);

    runtime.cleanup();

    expect(environment.timers.size).toBe(0);
    expect(environment.clearedTimers).toEqual([1]);
  });
});
