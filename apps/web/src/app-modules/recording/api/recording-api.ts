import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type Recording = ApiSchema<'RecordingListItem'>;
export type RecordingDetail = ApiSchema<'RecordingDetailOut'>;
export type RecordingPublication = ApiSchema<'RecordingPublicationOut'>;
export type RecordingTarget = ApiSchema<'RecordingTargetOut'>;
export type RecordingListResponse = ApiSchema<'RecordingListResponse'>;
export type RecordingPlaybackResponse = ApiSchema<'RecordingPlaybackResponse'>;
export type RecordingUpload = ApiSchema<'RecordingUploadOut'>;
export type RecordingViewFilter =
  | 'mine'
  | 'needs_review'
  | 'processing'
  | 'failed'
  | 'archived';
const TUS_RESUMABLE_VERSION = '1.0.0';

export interface RecordingTargetRef {
  app: string;
  type: string;
  id: string;
}

export class RecordingApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) => new RecordingApiError(error.status, error.message),
  );
}

export function listRecordings(
  token: string,
  options: {
    view?: RecordingViewFilter;
    from?: string;
    to?: string;
    target_app?: string;
    target_type?: string;
    target_id?: string;
  } = {},
): Promise<RecordingListResponse> {
  const params = new URLSearchParams();
  if (options.view) {
    params.set('view', options.view);
  }
  if (options.from) params.set('from', options.from);
  if (options.to) params.set('to', options.to);
  if (options.target_app) params.set('target_app', options.target_app);
  if (options.target_type) params.set('target_type', options.target_type);
  if (options.target_id) params.set('target_id', options.target_id);
  const query = params.toString();
  return request<RecordingListResponse>(
    `/api/v1/recording/recordings${query ? `?${query}` : ''}`,
    token,
  );
}

export function deleteRecording(
  token: string,
  recordingId: string,
): Promise<void> {
  return request<void>(`/api/v1/recording/recordings/${recordingId}`, token, {
    method: 'DELETE',
  });
}

export function getRecording(
  token: string,
  recordingId: string,
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/${recordingId}`,
    token,
  );
}

export function updateRecording(
  token: string,
  recordingId: string,
  payload: { title?: string | null },
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/${recordingId}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function retryRecording(
  token: string,
  recordingId: string,
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/${recordingId}/retry`,
    token,
    { method: 'POST' },
  );
}

export function attachRecordingTarget(
  token: string,
  recordingId: string,
  payload: {
    target_app: string;
    target_type: string;
    target_id: string;
    is_primary?: boolean;
    sort_order?: number;
  },
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/${recordingId}/targets`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function detachRecordingTarget(
  token: string,
  recordingId: string,
  targetId: string,
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/${recordingId}/targets/${targetId}`,
    token,
    { method: 'DELETE' },
  );
}

export function publishRecordingToDocs(
  token: string,
  recordingId: string,
): Promise<RecordingPublication> {
  return request<RecordingPublication>(
    `/api/v1/recording/recordings/${recordingId}/publications/docs`,
    token,
    { method: 'POST' },
  );
}

export function initRecordingUpload(
  token: string,
  payload: {
    idempotency_key: string;
    mime_type: string;
    title?: string | null;
    initial_target_app?: string | null;
    initial_target_type?: string | null;
    initial_target_id?: string | null;
    linked_task_id?: string | null;
  },
): Promise<RecordingUpload> {
  return request<RecordingUpload>(
    '/api/v1/recording/recordings/staging',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

function hexToBase64(hex: string): string {
  const bytes =
    hex.match(/.{1,2}/g)?.map((value) => Number.parseInt(value, 16)) ?? [];
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function readTusOffset(response: Response): number {
  const raw = response.headers.get('Upload-Offset');
  const offset = raw == null ? NaN : Number.parseInt(raw, 10);
  if (!Number.isFinite(offset) || offset < 0) {
    throw new RecordingApiError(
      response.status,
      'Tus response did not include a valid upload offset.',
    );
  }
  return offset;
}

async function tusFetch(
  token: string,
  stagingId: string,
  init: RequestInit,
): Promise<Response> {
  const response = await fetch(
    `/api/v1/recording/recordings/staging/${stagingId}/tus`,
    {
      ...init,
      headers: {
        ...jsonHeaders(token, { 'Tus-Resumable': TUS_RESUMABLE_VERSION }),
        ...(init.headers ?? {}),
      },
      cache: 'no-store',
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new RecordingApiError(
      response.status,
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Tus upload failed with ${response.status}.`,
    );
  }
  return response;
}

export async function headRecordingTusUpload(
  token: string,
  stagingId: string,
): Promise<number> {
  const response = await tusFetch(token, stagingId, {
    method: 'HEAD',
  });
  return readTusOffset(response);
}

export async function uploadRecordingTusChunk(
  token: string,
  stagingId: string,
  offset: number,
  blob: Blob,
  chunkSha256: string | null,
): Promise<number> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/offset+octet-stream',
    'Upload-Offset': String(offset),
  };
  if (chunkSha256) {
    headers['Upload-Checksum'] = `sha256 ${hexToBase64(chunkSha256)}`;
  }
  const response = await tusFetch(token, stagingId, {
    method: 'PATCH',
    headers,
    body: blob,
  });
  return readTusOffset(response);
}

export function completeRecordingUpload(
  token: string,
  stagingId: string,
  payload: {
    title?: string | null;
    duration_sec_estimate?: number | null;
    source?: 'quick_record' | 'live_recording';
  },
): Promise<RecordingDetail> {
  return request<RecordingDetail>(
    `/api/v1/recording/recordings/staging/${stagingId}/complete`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listRecordingUploads(
  token: string,
  options: {
    initial_target_app?: string;
    initial_target_type?: string;
    initial_target_id?: string;
  } = {},
): Promise<RecordingUpload[]> {
  const params = new URLSearchParams();
  if (options.initial_target_app)
    params.set('initial_target_app', options.initial_target_app);
  if (options.initial_target_type)
    params.set('initial_target_type', options.initial_target_type);
  if (options.initial_target_id)
    params.set('initial_target_id', options.initial_target_id);
  const query = params.toString();
  return request<RecordingUpload[]>(
    `/api/v1/recording/recordings/staging${query ? `?${query}` : ''}`,
    token,
  );
}

export function discardRecordingUpload(
  token: string,
  stagingId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/recording/recordings/staging/${stagingId}`,
    token,
    { method: 'DELETE' },
  );
}

export async function importRecording(
  token: string,
  file: Blob | File,
  options: {
    title?: string | null;
    startedAt?: Date | null;
    endedAt?: Date | null;
    durationSec?: number | null;
    source?: 'quick_record' | 'manual_upload';
    initialTarget?: RecordingTargetRef | null;
    linkedTaskId?: string | null;
  } = {},
): Promise<RecordingDetail> {
  const formData = new FormData();
  const filename =
    file instanceof File
      ? file.name
      : buildRecordingFilename(options.startedAt);
  formData.append('file', file, filename);
  if (options.title?.trim()) {
    formData.append('title', options.title.trim());
  }
  if (options.startedAt) {
    formData.append('started_at', options.startedAt.toISOString());
  }
  if (options.endedAt) {
    formData.append('ended_at', options.endedAt.toISOString());
  }
  if (options.durationSec !== undefined && options.durationSec !== null) {
    formData.append(
      'duration_sec',
      String(Math.max(0, Math.round(options.durationSec))),
    );
  }
  formData.append('source', options.source ?? 'quick_record');
  if (options.initialTarget) {
    formData.append('initial_target_app', options.initialTarget.app);
    formData.append('initial_target_type', options.initialTarget.type);
    formData.append('initial_target_id', options.initialTarget.id);
  }
  if (options.linkedTaskId) {
    formData.append('linked_task_id', options.linkedTaskId);
  }

  return request<RecordingDetail>(
    '/api/v1/recording/recordings/import',
    token,
    {
      method: 'POST',
      body: formData,
    },
  );
}

export function getRecordingPlaybackUrl(
  token: string,
  recordingId: string,
): Promise<RecordingPlaybackResponse> {
  return request<RecordingPlaybackResponse>(
    `/api/v1/recording/recordings/${recordingId}/playback`,
    token,
  );
}

export async function fetchRecordingPlaybackBlobUrl(
  token: string,
  playbackUrl: string,
): Promise<string> {
  const response = await fetch(playbackUrl, {
    headers: jsonHeaders(token),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new RecordingApiError(
      response.status,
      `Request failed with ${response.status}.`,
    );
  }
  return URL.createObjectURL(await response.blob());
}

function buildRecordingFilename(startedAt?: Date | null): string {
  const timestamp = (startedAt ?? new Date())
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d+Z$/, 'Z');
  return `${timestamp}.webm`;
}
