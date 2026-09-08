import type {
  RecordingChunkState,
  RecordingSessionState,
} from './recording-session-db';

export interface RecordingUploadSessionStore {
  getChunks(stagingId: string): Promise<RecordingChunkState[]>;
  getPendingChunks(stagingId: string): Promise<RecordingChunkState[]>;
  markChunkUploaded(stagingId: string, seq: number): Promise<void>;
  updateSessionProgress(
    stagingId: string,
    update: Partial<RecordingSessionState>,
  ): Promise<void>;
}

export interface RecordingUploadSessionClient {
  headUpload(stagingId: string): Promise<number>;
  uploadChunk(
    stagingId: string,
    offset: number,
    blob: Blob,
    sha256: string | null,
  ): Promise<number>;
}

export interface RecordingUploadDrainHooks {
  afterChunkUploaded?(
    stagingId: string,
    chunk: RecordingChunkState,
  ): Promise<void> | void;
}

export interface RecordingUploadDrainResult {
  uploadedChunkSeqs: number[];
  reconciledChunkSeqs: number[];
  remoteOffset: number;
}

export interface RecordingFinalizeSessionStore {
  getSession(stagingId: string): Promise<RecordingSessionState | null>;
  getPendingChunks(stagingId: string): Promise<RecordingChunkState[]>;
}

export type RecordingFinalizeReadiness =
  | { status: 'not-requested' }
  | { status: 'waiting-for-pending-chunks'; pendingChunkSeqs: number[] }
  | { status: 'ready'; session: RecordingSessionState | null };

export class RecordingTusOffsetConflictError extends Error {
  readonly recoverable = true;

  constructor(message: string) {
    super(message);
    this.name = 'RecordingTusOffsetConflictError';
  }
}

function offsetBeforeChunk(chunks: RecordingChunkState[], seq: number): number {
  return chunks
    .filter((chunk) => chunk.seq < seq)
    .reduce((total, chunk) => total + chunk.blob.size, 0);
}

function chunksCoveredByRemoteOffset(
  chunks: RecordingChunkState[],
  remoteOffset: number,
): RecordingChunkState[] {
  let localOffset = 0;
  const covered: RecordingChunkState[] = [];
  for (const chunk of chunks) {
    const nextOffset = localOffset + chunk.blob.size;
    if (remoteOffset >= nextOffset && chunk.uploadedAt == null) {
      covered.push(chunk);
    }
    localOffset = nextOffset;
  }
  return covered;
}

export async function drainRecordingUploadSession(input: {
  stagingId: string;
  store: RecordingUploadSessionStore;
  client: RecordingUploadSessionClient;
  offsetConflictMessage: string;
  hooks?: RecordingUploadDrainHooks;
}): Promise<RecordingUploadDrainResult> {
  const { stagingId, store, client, offsetConflictMessage, hooks } = input;
  const uploadedChunkSeqs: number[] = [];
  const reconciledChunkSeqs: number[] = [];
  let remoteOffset = await client.headUpload(stagingId);

  while (true) {
    const chunks = await store.getChunks(stagingId);
    const alreadyUploadedChunks = chunksCoveredByRemoteOffset(
      chunks,
      remoteOffset,
    );
    if (alreadyUploadedChunks.length > 0) {
      await Promise.all(
        alreadyUploadedChunks.map((chunk) =>
          store.markChunkUploaded(stagingId, chunk.seq),
        ),
      );
      reconciledChunkSeqs.push(
        ...alreadyUploadedChunks.map((chunk) => chunk.seq),
      );
      await store.updateSessionProgress(stagingId, {
        lastUploadedSeq:
          alreadyUploadedChunks[alreadyUploadedChunks.length - 1].seq,
      });
    }

    const pending = (await store.getPendingChunks(stagingId)).filter(
      (chunk) => chunk.blob.size > 0,
    );
    if (pending.length === 0) {
      break;
    }

    const chunk = pending[0];
    const expectedOffset = offsetBeforeChunk(chunks, chunk.seq);
    if (remoteOffset !== expectedOffset) {
      remoteOffset = await client.headUpload(stagingId);
      if (remoteOffset !== expectedOffset) {
        throw new RecordingTusOffsetConflictError(offsetConflictMessage);
      }
    }

    remoteOffset = await client.uploadChunk(
      stagingId,
      remoteOffset,
      chunk.blob,
      chunk.sha256,
    );
    await store.markChunkUploaded(stagingId, chunk.seq);
    uploadedChunkSeqs.push(chunk.seq);
    await store.updateSessionProgress(stagingId, {
      lastUploadedSeq: chunk.seq,
    });
    await hooks?.afterChunkUploaded?.(stagingId, chunk);
  }

  return {
    uploadedChunkSeqs,
    reconciledChunkSeqs,
    remoteOffset,
  };
}

export async function resolveRecordingFinalizeReadiness(input: {
  stagingId: string;
  shouldFinalize: boolean;
  pendingWrites?: Iterable<Promise<unknown>>;
  store: RecordingFinalizeSessionStore;
}): Promise<RecordingFinalizeReadiness> {
  const { stagingId, shouldFinalize, pendingWrites, store } = input;
  if (!shouldFinalize) {
    return { status: 'not-requested' };
  }

  const writes = Array.from(pendingWrites ?? []);
  if (writes.length > 0) {
    await Promise.all(writes);
  }

  const [session, pending] = await Promise.all([
    store.getSession(stagingId),
    store.getPendingChunks(stagingId),
  ]);
  if (pending.length > 0) {
    return {
      status: 'waiting-for-pending-chunks',
      pendingChunkSeqs: pending.map((chunk) => chunk.seq),
    };
  }

  return { status: 'ready', session };
}
