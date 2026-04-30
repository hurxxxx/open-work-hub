import type {
  LearningPageNoteDetail,
  LearningPageNoteListResponse,
  LearningPageNoteUpsertPayload,
} from './types';

const BASE_PATH = '/api/v1/learning/notes';

export class LearningNotesApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'LearningNotesApiError';
  }
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T | null> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (response.status === 404) {
    return null;
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new LearningNotesApiError(
      response.status,
      payload?.detail ?? `Learning notes request failed with ${response.status}.`,
    );
  }
  return payload as T;
}

export async function listLearningPageNotes(
  token: string,
  courseSlug: string,
  lessonId: string,
  options?: { signal?: AbortSignal },
): Promise<LearningPageNoteListResponse> {
  const params = new URLSearchParams({ course_slug: courseSlug, lesson_id: lessonId });
  const result = await request<LearningPageNoteListResponse>(
    `${BASE_PATH}?${params.toString()}`,
    token,
    { signal: options?.signal },
  );
  return result ?? { items: [] };
}

export async function fetchMyLearningPageNote(
  token: string,
  courseSlug: string,
  lessonId: string,
  options?: { signal?: AbortSignal },
): Promise<LearningPageNoteDetail | null> {
  const params = new URLSearchParams({ course_slug: courseSlug, lesson_id: lessonId });
  return request<LearningPageNoteDetail>(
    `${BASE_PATH}/me?${params.toString()}`,
    token,
    { signal: options?.signal },
  );
}

export async function fetchLearningPageNoteDetail(
  token: string,
  docId: string,
  options?: { signal?: AbortSignal },
): Promise<LearningPageNoteDetail | null> {
  return request<LearningPageNoteDetail>(
    `${BASE_PATH}/${encodeURIComponent(docId)}`,
    token,
    { signal: options?.signal },
  );
}

export async function upsertMyLearningPageNote(
  token: string,
  payload: LearningPageNoteUpsertPayload,
): Promise<LearningPageNoteDetail> {
  const result = await request<LearningPageNoteDetail>(
    `${BASE_PATH}/me`,
    token,
    { method: 'PUT', body: JSON.stringify(payload) },
  );
  if (result === null) {
    throw new LearningNotesApiError(500, 'Upsert returned no payload.');
  }
  return result;
}

export async function archiveLearningPageNote(
  token: string,
  docId: string,
): Promise<LearningPageNoteDetail> {
  const result = await request<LearningPageNoteDetail>(
    `${BASE_PATH}/${encodeURIComponent(docId)}/archive`,
    token,
    { method: 'POST' },
  );
  if (result === null) {
    throw new LearningNotesApiError(404, 'Note not found.');
  }
  return result;
}

export async function restoreLearningPageNote(
  token: string,
  docId: string,
): Promise<LearningPageNoteDetail> {
  const result = await request<LearningPageNoteDetail>(
    `${BASE_PATH}/${encodeURIComponent(docId)}/restore`,
    token,
    { method: 'POST' },
  );
  if (result === null) {
    throw new LearningNotesApiError(404, 'Note not found.');
  }
  return result;
}
