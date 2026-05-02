import { ApiRequestError, apiFetchJson, jsonHeaders } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type Recording = ApiSchema<'RecordingOut'>;
export type RecordingListResponse = ApiSchema<'RecordingListResponse'>;
export type RecordingPlaybackResponse = ApiSchema<'RecordingPlaybackResponse'>;
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
