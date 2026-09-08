import { describe, expect, it, vi } from 'vitest';

import type {
  RecordingChunkState,
  RecordingSessionState,
} from './recording-session-db';
import {
  drainRecordingUploadSession,
  RecordingTusOffsetConflictError,
  resolveRecordingFinalizeReadiness,
  type RecordingUploadSessionStore,
} from './recording-upload-session';

function chunk(
  seq: number,
  size: number,
  uploadedAt: number | null = null,
): RecordingChunkState {
  return {
    stagingId: 'staging-1',
    seq,
    blob: new Blob(['x'.repeat(size)]),
    sha256: `sha-${seq}`,
    uploadedAt,
    createdAt: 1_700_000_000_000 + seq,
  };
}

function session(
  overrides: Partial<RecordingSessionState> = {},
): RecordingSessionState {
  return {
    stagingId: 'staging-1',
    userId: 'user-1',
    scopeKey: 'user-1:recording:unlinked',
    idempotencyKey: 'idem-1',
    mimeType: 'audio/webm',
    title: null,
    source: 'quick_record',
    initialTargetApp: null,
    initialTargetType: null,
    initialTargetId: null,
    linkedTaskId: null,
    startedAt: 1_700_000_000_000,
    completedAt: null,
    finalizeRequestedAt: null,
    lastChunkSeq: -1,
    lastUploadedSeq: -1,
    uploadCompletedAt: null,
    interruptedAt: null,
    interruptionReason: null,
    ...overrides,
  };
}

function createStore(
  chunks: RecordingChunkState[],
): RecordingUploadSessionStore {
  return {
    getChunks: vi.fn(async () =>
      [...chunks].sort((left, right) => left.seq - right.seq),
    ),
    getPendingChunks: vi.fn(async () =>
      chunks
        .filter((item) => item.uploadedAt == null)
        .sort((left, right) => left.seq - right.seq),
    ),
    markChunkUploaded: vi.fn(async (_stagingId, seq) => {
      const item = chunks.find((candidate) => candidate.seq === seq);
      if (item) {
        item.uploadedAt = 1_700_000_100_000 + seq;
      }
    }),
    updateSessionProgress: vi.fn(async () => undefined),
  };
}

describe('recording upload session', () => {
  it('marks local chunks uploaded when the remote TUS offset already covers them', async () => {
    const store = createStore([chunk(0, 5), chunk(1, 6)]);
    const uploadChunk = vi.fn();

    const result = await drainRecordingUploadSession({
      stagingId: 'staging-1',
      store,
      offsetConflictMessage: 'offset conflict',
      client: {
        headUpload: vi.fn(async () => 11),
        uploadChunk,
      },
    });

    expect(result).toEqual({
      uploadedChunkSeqs: [],
      reconciledChunkSeqs: [0, 1],
      remoteOffset: 11,
    });
    expect(uploadChunk).not.toHaveBeenCalled();
    expect(store.markChunkUploaded).toHaveBeenCalledTimes(2);
    expect(store.markChunkUploaded).toHaveBeenNthCalledWith(1, 'staging-1', 0);
    expect(store.markChunkUploaded).toHaveBeenNthCalledWith(2, 'staging-1', 1);
    expect(store.updateSessionProgress).toHaveBeenCalledWith('staging-1', {
      lastUploadedSeq: 1,
    });
  });

  it('uploads pending chunks in sequence with the expected TUS offsets', async () => {
    const store = createStore([chunk(0, 5), chunk(1, 6)]);
    const uploadChunk = vi.fn(
      async (_stagingId, offset: number, blob: Blob) => offset + blob.size,
    );

    const result = await drainRecordingUploadSession({
      stagingId: 'staging-1',
      store,
      offsetConflictMessage: 'offset conflict',
      client: {
        headUpload: vi.fn(async () => 0),
        uploadChunk,
      },
    });

    expect(uploadChunk).toHaveBeenCalledTimes(2);
    expect(uploadChunk).toHaveBeenNthCalledWith(
      1,
      'staging-1',
      0,
      expect.objectContaining({ size: 5 }),
      'sha-0',
    );
    expect(uploadChunk).toHaveBeenNthCalledWith(
      2,
      'staging-1',
      5,
      expect.objectContaining({ size: 6 }),
      'sha-1',
    );
    expect(result.uploadedChunkSeqs).toEqual([0, 1]);
    expect(result.reconciledChunkSeqs).toEqual([]);
    expect(result.remoteOffset).toBe(11);
    expect(store.updateSessionProgress).toHaveBeenNthCalledWith(
      1,
      'staging-1',
      {
        lastUploadedSeq: 0,
      },
    );
    expect(store.updateSessionProgress).toHaveBeenNthCalledWith(
      2,
      'staging-1',
      {
        lastUploadedSeq: 1,
      },
    );
  });

  it('waits for pending chunk writes before deciding a finalize request is ready', async () => {
    let resolveWrite: () => void = () => {
      throw new Error('Expected a pending chunk write');
    };
    const pendingWrite = new Promise<void>((resolve) => {
      resolveWrite = resolve;
    });
    const getPendingChunks = vi.fn(async () => []);

    const readiness = resolveRecordingFinalizeReadiness({
      stagingId: 'staging-1',
      shouldFinalize: true,
      pendingWrites: [pendingWrite],
      store: {
        getSession: vi.fn(async () =>
          session({ finalizeRequestedAt: 1_700_000_200_000 }),
        ),
        getPendingChunks,
      },
    });

    await Promise.resolve();
    expect(getPendingChunks).not.toHaveBeenCalled();

    resolveWrite();
    await expect(readiness).resolves.toEqual({
      status: 'ready',
      session: session({ finalizeRequestedAt: 1_700_000_200_000 }),
    });
    expect(getPendingChunks).toHaveBeenCalledTimes(1);
  });

  it('reports a recoverable TUS offset conflict before finalizing', async () => {
    const store = createStore([chunk(0, 5, 1_700_000_100_000), chunk(1, 6)]);
    const uploadChunk = vi.fn();

    const drain = drainRecordingUploadSession({
      stagingId: 'staging-1',
      store,
      offsetConflictMessage: 'offset conflict',
      client: {
        headUpload: vi.fn(async () => 3),
        uploadChunk,
      },
    });

    await expect(drain).rejects.toBeInstanceOf(RecordingTusOffsetConflictError);
    await expect(drain).rejects.toMatchObject({
      name: 'RecordingTusOffsetConflictError',
      message: 'offset conflict',
      recoverable: true,
    });
    expect(uploadChunk).not.toHaveBeenCalled();
  });
});
