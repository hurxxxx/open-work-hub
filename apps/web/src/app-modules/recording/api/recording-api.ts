import { ApiRequestError, apiFetchJson, jsonHeaders } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type Recording = ApiSchema<'RecordingOut'>;
export type RecordingContainer = ApiSchema<'RecordingContainerOut'>;
export type RecordingListResponse = ApiSchema<'RecordingListResponse'>;
export type RecordingPlaybackResponse = ApiSchema<'RecordingPlaybackResponse'>;
export type RecordingUpload = ApiSchema<'RecordingUploadOut'>;
export type RecordingUploadChunkAck = ApiSchema<'RecordingUploadChunkAck'>;
export type RecordingViewFilter = 'mine' | 'needs_review' | 'processing' | 'failed' | 'archived';

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
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path, workspaceSlug), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new RecordingApiError(error.status, error.message);
    }
    throw error;
  }
}

export function listRecordings(
  token: string,
  workspaceSlug: string,
  options: { view?: RecordingViewFilter } = {},
): Promise<RecordingListResponse> {
  const params = new URLSearchParams();
  if (options.view) {
    params.set('view', options.view);
  }
  const query = params.toString();
  return request<RecordingListResponse>(
    `/api/v1/recording/recordings${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function deleteRecording(
  token: string,
  workspaceSlug: string,
  recordingId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/recording/recordings/${recordingId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function getRecording(
  token: string,
  workspaceSlug: string,
  recordingId: string,
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/${recordingId}`,
    token,
    workspaceSlug,
  );
}

export function updateRecording(
  token: string,
  workspaceSlug: string,
  recordingId: string,
  payload: { title?: string | null },
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/${recordingId}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function retryRecording(
  token: string,
  workspaceSlug: string,
  recordingId: string,
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/${recordingId}/retry`,
    token,
    workspaceSlug,
    { method: 'POST' },
  );
}

export function attachRecordingContainer(
  token: string,
  workspaceSlug: string,
  recordingId: string,
  payload: {
    container_app: string;
    container_type: string;
    container_id: string;
    is_primary?: boolean;
    sort_order?: number;
  },
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/${recordingId}/containers`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function detachRecordingContainer(
  token: string,
  workspaceSlug: string,
  recordingId: string,
  containerId: string,
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/${recordingId}/containers/${containerId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function initRecordingUpload(
  token: string,
  workspaceSlug: string,
  payload: {
    idempotency_key: string;
    mime_type: string;
    title?: string | null;
    initial_container_app?: string | null;
    initial_container_type?: string | null;
    initial_container_id?: string | null;
    linked_task_id?: string | null;
  },
): Promise<RecordingUpload> {
  return request<RecordingUpload>(
    '/api/v1/recording/recordings/staging',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function uploadRecordingChunk(
  token: string,
  workspaceSlug: string,
  stagingId: string,
  seq: number,
  blob: Blob,
  chunkSha256: string,
): Promise<RecordingUploadChunkAck> {
  const formData = new FormData();
  formData.append('file', blob, `chunk-${seq}.webm`);
  return request<RecordingUploadChunkAck>(
    `/api/v1/recording/recordings/staging/${stagingId}/chunks/${seq}`,
    token,
    workspaceSlug,
    {
      method: 'PUT',
      headers: {
        'X-Chunk-Sha256': chunkSha256,
      },
      body: formData,
    },
  );
}

export function completeRecordingUpload(
  token: string,
  workspaceSlug: string,
  stagingId: string,
  payload: { title?: string | null; duration_sec_estimate?: number | null; source?: 'quick_record' | 'live_recording' },
): Promise<Recording> {
  return request<Recording>(
    `/api/v1/recording/recordings/staging/${stagingId}/complete`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listRecordingUploads(
  token: string,
  workspaceSlug: string,
  options: {
    initial_container_app?: string;
    initial_container_type?: string;
    initial_container_id?: string;
  } = {},
): Promise<RecordingUpload[]> {
  const params = new URLSearchParams();
  if (options.initial_container_app) params.set('initial_container_app', options.initial_container_app);
  if (options.initial_container_type) params.set('initial_container_type', options.initial_container_type);
  if (options.initial_container_id) params.set('initial_container_id', options.initial_container_id);
  const query = params.toString();
  return request<RecordingUpload[]>(
    `/api/v1/recording/recordings/staging${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function discardRecordingUpload(
  token: string,
  workspaceSlug: string,
  stagingId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/recording/recordings/staging/${stagingId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export async function importRecording(
  token: string,
  workspaceSlug: string,
  file: Blob | File,
  options: {
    title?: string | null;
    startedAt?: Date | null;
    endedAt?: Date | null;
    durationSec?: number | null;
    source?: 'quick_record' | 'manual_upload';
  } = {},
): Promise<Recording> {
  const formData = new FormData();
  const filename = file instanceof File ? file.name : buildRecordingFilename(options.startedAt);
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
    formData.append('duration_sec', String(Math.max(0, Math.round(options.durationSec))));
  }
  formData.append('source', options.source ?? 'quick_record');

  return request<Recording>(
    '/api/v1/recording/recordings/import',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: formData,
    },
  );
}

export function getRecordingPlaybackUrl(
  token: string,
  workspaceSlug: string,
  recordingId: string,
): Promise<RecordingPlaybackResponse> {
  return request<RecordingPlaybackResponse>(
    `/api/v1/recording/recordings/${recordingId}/playback`,
    token,
    workspaceSlug,
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
    throw new RecordingApiError(response.status, `Request failed with ${response.status}.`);
  }
  return URL.createObjectURL(await response.blob());
}

function buildRecordingFilename(startedAt?: Date | null): string {
  const timestamp = (startedAt ?? new Date()).toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return `${timestamp}.webm`;
}
