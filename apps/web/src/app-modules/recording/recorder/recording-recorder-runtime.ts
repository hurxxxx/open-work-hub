import { runRequestsWithConcurrency } from '@/src/platform/network/request-concurrency';

import type {
  RecordingChunkState,
  RecordingSessionSource,
  RecordingSessionState,
} from './recording-session-db';
import {
  drainRecordingUploadSession,
  resolveRecordingFinalizeReadiness,
  type RecordingUploadSessionClient,
  type RecordingUploadSessionStore,
} from './recording-upload-session';

const RECOVERABLE_UPLOAD_RESUME_CONCURRENCY = 1;

export interface RecordingCompletionPayload {
  title?: string | null;
  duration_sec_estimate?: number | null;
  source?: RecordingSessionSource;
}

export interface RecordingRecorderRuntimeStore
  extends RecordingUploadSessionStore {
  appendChunk(chunk: RecordingChunkState): Promise<void>;
  getSession(stagingId: string): Promise<RecordingSessionState | null>;
  listIncompleteSessions(options: {
    scopeKey?: string | null;
  }): Promise<RecordingSessionState[]>;
  markSessionComplete(stagingId: string): Promise<void>;
  clearSession(stagingId: string): Promise<void>;
}

export interface RecordingRecorderRuntimeClient<TRecording>
  extends RecordingUploadSessionClient {
  completeUpload(
    stagingId: string,
    payload: RecordingCompletionPayload,
  ): Promise<TRecording>;
}

export interface RecordingRecorderRuntimeEnvironment {
  now(): number;
  digestBlob(blob: Blob): Promise<string | null>;
  registerBackgroundSync(): Promise<void> | void;
  setTimeout(callback: () => void, delayMs: number): number;
  clearTimeout(timer: number): void;
}

export interface RecordingRecorderRuntimeDefaults {
  title(): string | null;
  source(): RecordingSessionSource;
}

export interface RecordingRecorderRuntimeMessages {
  tusOffsetConflict(): string;
}

export interface RecordingRecorderStats {
  queuedBytes: number;
  uploadedBytes: number;
}

export interface RecordingRecorderRuntimeCallbacks<TRecording> {
  onStatsChanged?(
    stagingId: string,
    stats: RecordingRecorderStats,
  ): Promise<void> | void;
  onChunkWriteFailed?(stagingId: string, error: unknown): Promise<void> | void;
  onPumpFailed?(stagingId: string, error: unknown): Promise<void> | void;
  onFinalizeStarted?(stagingId: string): Promise<void> | void;
  onFinalizeFailed?(stagingId: string, error: unknown): Promise<void> | void;
  onFinalizeFinished?(stagingId: string): Promise<void> | void;
  onUploadSaved?(
    stagingId: string,
    recording: TRecording,
  ): Promise<void> | void;
}

export interface RecordingRecorderRuntimeOptions<TRecording> {
  store: RecordingRecorderRuntimeStore;
  client: RecordingRecorderRuntimeClient<TRecording>;
  environment: RecordingRecorderRuntimeEnvironment;
  defaults: RecordingRecorderRuntimeDefaults;
  messages: RecordingRecorderRuntimeMessages;
  callbacks?: RecordingRecorderRuntimeCallbacks<TRecording>;
  canUpload?: () => boolean;
  retryDelayMs?: number;
}

function bytesToNumber(blobs: Blob[]): number {
  return blobs.reduce((total, blob) => total + blob.size, 0);
}

export class RecordingRecorderRuntime<TRecording> {
  private readonly pendingChunkWrites = new Set<Promise<void>>();
  private readonly pumping = new Set<string>();
  private readonly pendingFinalize = new Set<string>();
  private readonly retryTimers = new Map<string, number>();

  constructor(
    private readonly options: RecordingRecorderRuntimeOptions<TRecording>,
  ) {}

  queueChunkWrite(stagingId: string, seq: number, blob: Blob): Promise<void> {
    const write = this.attachChunk(stagingId, seq, blob).catch(
      async (error: unknown) => {
        await this.options.callbacks?.onChunkWriteFailed?.(stagingId, error);
      },
    );
    this.pendingChunkWrites.add(write);
    void write.finally(() => this.pendingChunkWrites.delete(write));
    return write;
  }

  async prepareFinalize(stagingId: string): Promise<void> {
    await this.options.store.updateSessionProgress(stagingId, {
      finalizeRequestedAt: this.options.environment.now(),
    });
    await this.waitForPendingChunkWrites();
    this.pendingFinalize.add(stagingId);
  }

  clearPendingFinalize(stagingId: string): void {
    this.pendingFinalize.delete(stagingId);
  }

  async pumpUploads(stagingId: string): Promise<void> {
    if (!this.canUpload() || this.pumping.has(stagingId)) {
      return;
    }
    this.pumping.add(stagingId);
    this.clearRetryTimer(stagingId);
    try {
      await drainRecordingUploadSession({
        stagingId,
        offsetConflictMessage: this.options.messages.tusOffsetConflict(),
        store: this.options.store,
        client: this.options.client,
        hooks: {
          afterChunkUploaded: async () => {
            await this.refreshStats(stagingId);
          },
        },
      });
      await this.finalizeIfReady(stagingId);
    } catch (error) {
      await this.options.callbacks?.onPumpFailed?.(stagingId, error);
      void Promise.resolve(
        this.options.environment.registerBackgroundSync(),
      ).catch(() => undefined);
      this.scheduleRetry(stagingId);
    } finally {
      this.pumping.delete(stagingId);
    }
  }

  async refreshStats(stagingId: string): Promise<RecordingRecorderStats> {
    const all = await this.options.store.getChunks(stagingId);
    const stats = {
      queuedBytes: bytesToNumber(all.map((chunk) => chunk.blob)),
      uploadedBytes: bytesToNumber(
        all
          .filter((chunk) => chunk.uploadedAt != null)
          .map((chunk) => chunk.blob),
      ),
    };
    await this.options.callbacks?.onStatsChanged?.(stagingId, stats);
    return stats;
  }

  async finalizeUploadedSession(stagingId: string): Promise<TRecording> {
    const session = await this.options.store.getSession(stagingId);
    const recording = await this.options.client.completeUpload(
      stagingId,
      this.buildCompletionPayload(session),
    );
    await this.options.store.clearSession(stagingId);
    return recording;
  }

  async resumeRecoverableUploads(options: {
    scopeKey?: string | null;
  }): Promise<void> {
    if (!this.canUpload()) {
      return;
    }
    const sessions = await this.options.store.listIncompleteSessions(options);
    await runRequestsWithConcurrency(
      sessions,
      RECOVERABLE_UPLOAD_RESUME_CONCURRENCY,
      (session) => this.pumpUploads(session.stagingId),
    );
  }

  cleanup(): void {
    for (const timer of this.retryTimers.values()) {
      this.options.environment.clearTimeout(timer);
    }
    this.retryTimers.clear();
  }

  private async attachChunk(
    stagingId: string,
    seq: number,
    blob: Blob,
  ): Promise<void> {
    const digest = await this.options.environment.digestBlob(blob);
    await this.options.store.appendChunk({
      stagingId,
      seq,
      blob,
      sha256: digest,
      uploadedAt: null,
      createdAt: this.options.environment.now(),
    });
    await Promise.all([
      this.options.store.updateSessionProgress(stagingId, {
        lastChunkSeq: seq,
      }),
      this.refreshStats(stagingId),
    ]);
    void this.pumpUploads(stagingId);
  }

  private async waitForPendingChunkWrites(): Promise<void> {
    if (this.pendingChunkWrites.size > 0) {
      await Promise.all(Array.from(this.pendingChunkWrites));
    }
  }

  private async finalizeIfReady(stagingId: string): Promise<void> {
    const session = await this.options.store.getSession(stagingId);
    const shouldFinalize =
      this.pendingFinalize.has(stagingId) ||
      session?.finalizeRequestedAt != null;
    const readiness = await resolveRecordingFinalizeReadiness({
      stagingId,
      shouldFinalize,
      pendingWrites: this.pendingChunkWrites,
      store: this.options.store,
    });
    if (readiness.status !== 'ready') {
      return;
    }

    await this.options.callbacks?.onFinalizeStarted?.(stagingId);
    try {
      const recording = await this.options.client.completeUpload(
        stagingId,
        this.buildCompletionPayload(readiness.session),
      );
      this.pendingFinalize.delete(stagingId);
      await this.options.store.markSessionComplete(stagingId);
      await this.options.store.clearSession(stagingId);
      await this.options.callbacks?.onUploadSaved?.(stagingId, recording);
    } catch (error) {
      await this.options.callbacks?.onFinalizeFailed?.(stagingId, error);
    } finally {
      await this.options.callbacks?.onFinalizeFinished?.(stagingId);
    }
  }

  private buildCompletionPayload(
    session: RecordingSessionState | null,
  ): RecordingCompletionPayload {
    return {
      title: session?.title ?? this.options.defaults.title(),
      duration_sec_estimate: session?.startedAt
        ? Math.max(
            0,
            Math.round(
              (this.options.environment.now() - session.startedAt) / 1000,
            ),
          )
        : undefined,
      source: session?.source ?? this.options.defaults.source(),
    };
  }

  private canUpload(): boolean {
    return this.options.canUpload?.() ?? true;
  }

  private scheduleRetry(stagingId: string): void {
    this.clearRetryTimer(stagingId);
    const timer = this.options.environment.setTimeout(() => {
      void this.pumpUploads(stagingId);
    }, this.options.retryDelayMs ?? 3000);
    this.retryTimers.set(stagingId, timer);
  }

  private clearRetryTimer(stagingId: string): void {
    const timer = this.retryTimers.get(stagingId);
    if (timer == null) {
      return;
    }
    this.options.environment.clearTimeout(timer);
    this.retryTimers.delete(stagingId);
  }
}
