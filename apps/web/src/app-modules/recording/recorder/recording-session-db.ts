import { deleteOpfsSession, readOpfsChunk, writeOpfsChunk } from './recording-blob-store';

export interface RecordingTargetRef {
  app: string;
  type: string;
  id: string;
}

export type RecordingSessionSource = 'quick_record' | 'live_recording';

export interface RecordingSessionState {
  stagingId: string;
  workspaceSlug: string;
  scopeKey: string;
  idempotencyKey: string;
  mimeType: string;
  title: string | null;
  source: RecordingSessionSource;
  initialTargetApp: string | null;
  initialTargetType: string | null;
  initialTargetId: string | null;
  linkedTaskId: string | null;
  startedAt: number;
  completedAt: number | null;
  finalizeRequestedAt: number | null;
  lastChunkSeq: number;
  lastUploadedSeq: number;
  uploadCompletedAt: number | null;
  interruptedAt: number | null;
  interruptionReason: string | null;
  meetingId?: string | null;
}

export interface RecordingChunkState {
  stagingId: string;
  seq: number;
  blob: Blob;
  sha256: string | null;
  uploadedAt: number | null;
  createdAt: number;
  storageBackend?: 'idb' | 'opfs';
  storagePath?: string | null;
}

type StoredRecordingChunkState = Omit<RecordingChunkState, 'blob'> & {
  blob?: Blob | null;
};

const DB_NAME = 'open-work-hub-recording';
const DB_VERSION = 3;
const SESSION_STORE = 'sessions';
const CHUNK_STORE = 'chunks';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(SESSION_STORE)) {
        const store = db.createObjectStore(SESSION_STORE, { keyPath: 'stagingId' });
        store.createIndex('meetingId', 'meetingId', { unique: false });
        store.createIndex('workspaceSlug', 'workspaceSlug', { unique: false });
        store.createIndex('scopeKey', 'scopeKey', { unique: false });
      } else {
        const store = request.transaction?.objectStore(SESSION_STORE);
        if (store && !store.indexNames.contains('meetingId')) {
          store.createIndex('meetingId', 'meetingId', { unique: false });
        }
        if (store && !store.indexNames.contains('workspaceSlug')) {
          store.createIndex('workspaceSlug', 'workspaceSlug', { unique: false });
        }
        if (store && !store.indexNames.contains('scopeKey')) {
          store.createIndex('scopeKey', 'scopeKey', { unique: false });
        }
      }
      if (!db.objectStoreNames.contains(CHUNK_STORE)) {
        const store = db.createObjectStore(CHUNK_STORE, { keyPath: ['stagingId', 'seq'] });
        store.createIndex('stagingId', 'stagingId', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

function withStore<T>(
  storeName: string,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => Promise<T> | T,
): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const tx = db.transaction(storeName, mode);
        const store = tx.objectStore(storeName);
        let result: T;
        let settled = false;
        Promise.resolve(fn(store))
          .then((value) => {
            result = value;
            settled = true;
          })
          .catch((error) => {
            db.close();
            reject(error);
          });
        tx.onerror = () => {
          db.close();
          reject(tx.error);
        };
        tx.oncomplete = () => {
          db.close();
          if (settled) {
            resolve(result);
          }
        };
      }),
  );
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function buildRecordingScopeKey(
  workspaceSlug: string,
  target: RecordingTargetRef | null | undefined,
): string {
  if (!target) {
    return `${workspaceSlug}:recording:unlinked`;
  }
  return `${workspaceSlug}:${target.app}:${target.type}:${target.id}`;
}

export function sessionTarget(session: RecordingSessionState): RecordingTargetRef | null {
  if (session.initialTargetApp && session.initialTargetType && session.initialTargetId) {
    return {
      app: session.initialTargetApp,
      type: session.initialTargetType,
      id: session.initialTargetId,
    };
  }
  if (session.meetingId) {
    return { app: 'meeting', type: 'meeting', id: session.meetingId };
  }
  return null;
}

function normalizeSession(value: Partial<RecordingSessionState>): RecordingSessionState {
  const legacyMeetingId = value.meetingId ?? null;
  const target = value.initialTargetApp && value.initialTargetType && value.initialTargetId
    ? {
        app: value.initialTargetApp,
        type: value.initialTargetType,
        id: value.initialTargetId,
      }
    : legacyMeetingId
      ? { app: 'meeting', type: 'meeting', id: legacyMeetingId }
      : null;
  const workspaceSlug = value.workspaceSlug ?? '';
  return {
    stagingId: value.stagingId ?? '',
    workspaceSlug,
    scopeKey: value.scopeKey ?? buildRecordingScopeKey(workspaceSlug, target),
    idempotencyKey: value.idempotencyKey ?? '',
    mimeType: value.mimeType ?? 'audio/webm',
    title: value.title ?? null,
    source: value.source ?? (target?.app === 'meeting' ? 'live_recording' : 'quick_record'),
    initialTargetApp: value.initialTargetApp ?? target?.app ?? null,
    initialTargetType: value.initialTargetType ?? target?.type ?? null,
    initialTargetId: value.initialTargetId ?? target?.id ?? null,
    linkedTaskId: value.linkedTaskId ?? null,
    startedAt: value.startedAt ?? Date.now(),
    completedAt: value.completedAt ?? null,
    finalizeRequestedAt: value.finalizeRequestedAt ?? null,
    lastChunkSeq: value.lastChunkSeq ?? -1,
    lastUploadedSeq: value.lastUploadedSeq ?? -1,
    uploadCompletedAt: value.uploadCompletedAt ?? null,
    interruptedAt: value.interruptedAt ?? null,
    interruptionReason: value.interruptionReason ?? null,
    meetingId: legacyMeetingId,
  };
}

export async function upsertSession(session: RecordingSessionState): Promise<void> {
  await withStore(SESSION_STORE, 'readwrite', (store) =>
    requestToPromise(store.put(normalizeSession(session))).then(() => undefined),
  );
}

export async function getSession(stagingId: string): Promise<RecordingSessionState | null> {
  return withStore(SESSION_STORE, 'readonly', (store) =>
    requestToPromise(store.get(stagingId)).then((value) => (value ? normalizeSession(value) : null)),
  );
}

export async function listIncompleteSessions(options: {
  workspaceSlug: string;
  scopeKey?: string | null;
}): Promise<RecordingSessionState[]> {
  return withStore(SESSION_STORE, 'readonly', async (store) => {
    const all = ((await requestToPromise(store.getAll())) ?? []) as Array<
      Partial<RecordingSessionState>
    >;
    const result: RecordingSessionState[] = [];
    for (const value of all) {
      const item = normalizeSession(value);
      if (item.completedAt != null) {
        continue;
      }
      if (options.workspaceSlug && item.workspaceSlug !== options.workspaceSlug) {
        continue;
      }
      if (options.scopeKey && item.scopeKey !== options.scopeKey) {
        continue;
      }
      result.push(item);
    }
    return result;
  });
}

async function getStoredChunks(stagingId: string): Promise<StoredRecordingChunkState[]> {
  return withStore(CHUNK_STORE, 'readonly', async (store) => {
    const index = store.index('stagingId');
    const all = ((await requestToPromise(index.getAll(IDBKeyRange.only(stagingId)))) ?? []) as
      StoredRecordingChunkState[];
    return all.sort((left, right) => left.seq - right.seq);
  });
}

async function hydrateChunk(chunk: StoredRecordingChunkState): Promise<RecordingChunkState | null> {
  if (chunk.storageBackend === 'opfs' && chunk.storagePath) {
    const blob = await readOpfsChunk(chunk.stagingId, chunk.storagePath);
    if (blob) {
      return {
        ...chunk,
        blob,
        storageBackend: 'opfs',
        storagePath: chunk.storagePath,
      };
    }
  }
  if (chunk.blob) {
    return {
      ...chunk,
      blob: chunk.blob,
      storageBackend: chunk.storageBackend ?? 'idb',
      storagePath: chunk.storagePath ?? null,
    };
  }
  return null;
}

export async function appendChunk(chunk: RecordingChunkState): Promise<void> {
  const opfsPath = await writeOpfsChunk(chunk.stagingId, chunk.seq, chunk.blob);
  const stored: StoredRecordingChunkState = opfsPath
    ? {
        ...chunk,
        blob: null,
        storageBackend: 'opfs',
        storagePath: opfsPath,
      }
    : {
        ...chunk,
        storageBackend: 'idb',
        storagePath: null,
      };
  await putChunkRecord(stored);
}

async function putChunkRecord(chunk: StoredRecordingChunkState): Promise<void> {
  await withStore(CHUNK_STORE, 'readwrite', (store) =>
    requestToPromise(store.put(chunk)).then(() => undefined),
  );
}

export async function getChunks(stagingId: string): Promise<RecordingChunkState[]> {
  const all = await getStoredChunks(stagingId);
  const hydrated = await Promise.all(all.map((chunk) => hydrateChunk(chunk)));
  return hydrated.filter((chunk): chunk is RecordingChunkState => chunk != null);
}

export async function getPendingChunks(stagingId: string): Promise<RecordingChunkState[]> {
  const all = await getChunks(stagingId);
  return all.filter((chunk) => chunk.uploadedAt == null);
}

export async function markChunkUploaded(stagingId: string, seq: number): Promise<void> {
  const existing = await withStore(CHUNK_STORE, 'readonly', (store) =>
    requestToPromise(store.get([stagingId, seq] as [string, number])),
  ) as StoredRecordingChunkState | undefined;
  if (!existing) {
    return;
  }
  existing.uploadedAt = Date.now();
  await putChunkRecord(existing);
}

export async function clearSession(stagingId: string): Promise<void> {
  await Promise.all([
    getStoredChunks(stagingId).then(deleteStoredChunks),
    deleteOpfsSession(stagingId),
  ]);
  await deleteSessionRecord(stagingId);
}

function deleteStoredChunks(chunks: StoredRecordingChunkState[]): Promise<void> {
  return withStore(CHUNK_STORE, 'readwrite', (store) =>
    Promise.all(
      chunks.map((chunk) =>
        requestToPromise(store.delete([chunk.stagingId, chunk.seq] as [string, number])),
      ),
    ).then(() => undefined),
  );
}

function deleteSessionRecord(stagingId: string): Promise<void> {
  return withStore(SESSION_STORE, 'readwrite', (store) =>
    requestToPromise(store.delete(stagingId)).then(() => undefined),
  );
}

export async function markSessionComplete(stagingId: string): Promise<void> {
  const session = await getSession(stagingId);
  if (!session) return;
  session.completedAt = Date.now();
  session.uploadCompletedAt = Date.now();
  await upsertSession(session);
}

export async function updateSessionProgress(
  stagingId: string,
  update: Partial<RecordingSessionState>,
): Promise<void> {
  const session = await getSession(stagingId);
  if (!session) return;
  await upsertSession({ ...session, ...update });
}

export async function buildSessionBlob(stagingId: string): Promise<Blob | null> {
  const chunks = await getChunks(stagingId);
  if (chunks.length === 0) {
    return null;
  }
  return new Blob(
    chunks.map((chunk) => chunk.blob),
    { type: chunks[0]?.blob.type || 'audio/webm' },
  );
}
