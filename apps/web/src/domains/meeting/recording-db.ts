export interface RecordingSessionState {
  stagingId: string;
  meetingId: string;
  idempotencyKey: string;
  mimeType: string;
  linkedTaskId: string | null;
  startedAt: number;
  completedAt: number | null;
  lastChunkSeq: number;
  lastUploadedSeq: number;
  uploadCompletedAt: number | null;
}

export interface RecordingChunkState {
  stagingId: string;
  seq: number;
  blob: Blob;
  sha256: string;
  uploadedAt: number | null;
  createdAt: number;
}

const DB_NAME = 'doowon-recording';
const DB_VERSION = 1;
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
        Promise.resolve(fn(store)).then(resolve).catch(reject);
        tx.onerror = () => reject(tx.error);
        tx.oncomplete = () => db.close();
      }),
  );
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function upsertSession(session: RecordingSessionState): Promise<void> {
  await withStore(SESSION_STORE, 'readwrite', (store) =>
    requestToPromise(store.put(session)).then(() => undefined),
  );
}

export async function getSession(stagingId: string): Promise<RecordingSessionState | null> {
  return withStore(SESSION_STORE, 'readonly', (store) =>
    requestToPromise(store.get(stagingId)).then((value) => value ?? null),
  );
}

export async function listIncompleteSessions(meetingId: string): Promise<RecordingSessionState[]> {
  return withStore(SESSION_STORE, 'readonly', async (store) => {
    const index = store.index('meetingId');
    const all = (await requestToPromise(index.getAll(IDBKeyRange.only(meetingId)))) ?? [];
    return all.filter((item) => item.completedAt == null);
  });
}

export async function appendChunk(chunk: RecordingChunkState): Promise<void> {
  await withStore(CHUNK_STORE, 'readwrite', (store) =>
    requestToPromise(store.put(chunk)).then(() => undefined),
  );
}

export async function getChunks(stagingId: string): Promise<RecordingChunkState[]> {
  return withStore(CHUNK_STORE, 'readonly', async (store) => {
    const index = store.index('stagingId');
    const all = (await requestToPromise(index.getAll(IDBKeyRange.only(stagingId)))) ?? [];
    return all.sort((left, right) => left.seq - right.seq);
  });
}

export async function getPendingChunks(stagingId: string): Promise<RecordingChunkState[]> {
  const all = await getChunks(stagingId);
  return all.filter((chunk) => chunk.uploadedAt == null);
}

export async function markChunkUploaded(stagingId: string, seq: number): Promise<void> {
  const existing = await withStore(CHUNK_STORE, 'readonly', (store) =>
    requestToPromise(store.get([stagingId, seq] as [string, number])),
  );
  if (!existing) {
    return;
  }
  existing.uploadedAt = Date.now();
  await appendChunk(existing);
}

export async function clearSession(stagingId: string): Promise<void> {
  const chunks = await getChunks(stagingId);
  await withStore(CHUNK_STORE, 'readwrite', async (store) => {
    for (const chunk of chunks) {
      await requestToPromise(store.delete([chunk.stagingId, chunk.seq] as [string, number]));
    }
  });
  await withStore(SESSION_STORE, 'readwrite', (store) =>
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
