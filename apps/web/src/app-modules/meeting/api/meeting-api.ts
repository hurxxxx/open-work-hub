import { ApiRequestError, apiFetchJson, jsonHeaders } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { parseApiDateTime } from '@/src/platform/time/time-utils';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type MeetingStatus = ApiSchema<'MeetingDetail'>['status'];
export type AttendeeRole = ApiSchema<'MeetingAttendeeInput'>['role'];
export type AttendeeResponse = ApiSchema<'MeetingAttendeeOut'>['response'];

export type MeetingAttendee = ApiSchema<'MeetingAttendeeOut'>;

export type MeetingTaskLink = ApiSchema<'MeetingTaskLinkOut'>;

export type MeetingDocLink = ApiSchema<'MeetingDocLinkOut'>;

export type MeetingWhiteboardLink = ApiSchema<'MeetingWhiteboardLinkOut'>;

export type MeetingFileAttachment = ApiSchema<'MeetingFileAttachmentOut'>;

export type MeetingRecordingStatus =
  | 'pending'
  | 'transcribing'
  | 'summarizing'
  | 'extracting_insights'
  | 'generating_doc'
  | 'done'
  | 'failed';

/**
 * Recording states where the backend pipeline is still advancing the
 * row (transcribe → summarize → extract insights → generate doc). UI
 * polling keeps refetching while the recording is in one of these.
 */
export const ACTIVE_RECORDING_STATUSES: ReadonlySet<MeetingRecordingStatus> = new Set([
  'pending',
  'transcribing',
  'summarizing',
  'extracting_insights',
  'generating_doc',
]);

/**
 * States where the progress rail should be rendered. ``done`` is shown
 * with a separate completion message; rail is hidden because the
 * pipeline is finished. ``pending`` only means the audio is saved and queued,
 * so it is represented by the transcript status line instead of a progress rail.
 */
export const RAIL_VISIBLE_STATUSES: ReadonlySet<MeetingRecordingStatus> = new Set([
  'transcribing',
  'summarizing',
  'extracting_insights',
  'generating_doc',
  'failed',
]);

export type MeetingRecording = Omit<ApiSchema<'MeetingRecordingOut'>, 'transcription_status'> & {
  transcription_status: MeetingRecordingStatus;
  transcript_extracted?: boolean;
  summary_generated?: boolean;
};

export type RecordingStagingItem = ApiSchema<'RecordingStagingItem'>;

export type RecordingChunkAck = ApiSchema<'RecordingChunkAck'>;

export type RecordingPlaybackResponse = ApiSchema<'RecordingPlaybackResponse'>;

export type MeetingListItem = ApiSchema<'MeetingListItem'>;

export type MeetingListResponse = ApiSchema<'MeetingListResponse'>;

export type ActiveRecordingLock = ApiSchema<'ActiveRecordingLockOut'>;

export type MeetingDetail = Omit<
  ApiSchema<'MeetingDetail'>,
  | 'active_recording_lock'
  | 'attendees'
  | 'doc_links'
  | 'file_attachments'
  | 'recordings'
  | 'task_links'
  | 'whiteboard_link'
> & {
  attendees: MeetingAttendee[];
  task_links: MeetingTaskLink[];
  doc_links: MeetingDocLink[];
  whiteboard_link: MeetingWhiteboardLink | null;
  file_attachments: MeetingFileAttachment[];
  recordings: MeetingRecording[];
  /**
   * Non-null when another user (or the viewer themselves) currently holds
   * the meeting's single-recorder lock. The backend auto-releases the lock
   * after RECORDING_STALE_AFTER_SECONDS of inactivity so a crashed recorder
   * never permanently blocks other participants.
   */
  active_recording_lock: ActiveRecordingLock | null;
};

export type MeetingUser = ApiSchema<'MeetingUserItem'>;

export type MeetingAvailabilityBlock = ApiSchema<'MeetingAvailabilityBlock'>;

export type MeetingAvailabilityItem = ApiSchema<'MeetingAvailabilityItem'>;

export type MeetingAvailabilityResponse = ApiSchema<'MeetingAvailabilityResponse'>;

export type MeetingAttendeeInput = ApiSchema<'MeetingAttendeeInput'>;

export type MeetingCreateInput = Omit<ApiSchema<'MeetingCreateRequest'>, 'attendees'> & {
  attendees: MeetingAttendeeInput[];
};

export type MeetingUpdateInput = Omit<ApiSchema<'MeetingUpdateRequest'>, 'attendees' | 'status'> & {
  status?: MeetingStatus;
  attendees?: MeetingAttendeeInput[];
};

export type MeetingScope = 'mine' | 'upcoming' | 'all';

/**
 * Parse a datetime string returned by the meeting API.
 *
 * The backend stores ``start_at``/``end_at`` in a naive ``DateTime`` column
 * and pydantic emits the value without a timezone marker (e.g.
 * ``"2026-04-10T11:00:00"``). The values are wall-time UTC — the request
 * pipeline serializes the user's input through ``Date.toISOString()`` which
 * normalizes to UTC before reaching the database.
 *
 * ``new Date("2026-04-10T11:00:00")`` would otherwise be interpreted as
 * **local** time per the ECMAScript spec, producing a 9-hour drift in
 * KST browsers. Appending ``Z`` makes the parse unambiguous and lets
 * ``toLocaleString``/``toLocaleTimeString`` render the user's wall clock
 * correctly.
 *
 * PR4 will replace this convention with a TIMESTAMPTZ column + explicit
 * tz-aware serialization, at which point this helper can be removed.
 */
export function parseServerDateTime(iso: string): Date {
  return parseApiDateTime(iso) ?? new Date(Number.NaN);
}

export class MeetingApiError extends Error {
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
    return await apiFetchJson<T>(resolveMeetingPath(path, workspaceSlug), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new MeetingApiError(error.status, error.message);
    }
    throw error;
  }
}

async function multipartRequest<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  return request<T>(path, token, workspaceSlug, init);
}

function resolveMeetingPath(path: string, workspaceSlug: string): string {
  return rewriteWorkspaceApiPath(path, workspaceSlug);
}

export function listMeetings(
  token: string,
  workspaceSlug: string,
  options: { scope?: MeetingScope; from?: string; to?: string } = {},
): Promise<MeetingListResponse> {
  const params = new URLSearchParams();
  if (options.scope) params.set('scope', options.scope);
  if (options.from) params.set('from', options.from);
  if (options.to) params.set('to', options.to);
  const query = params.toString();
  return request<MeetingListResponse>(
    `/api/v1/meeting/meetings${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function getMeeting(token: string, workspaceSlug: string, meetingId: string): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/v1/meeting/meetings/${meetingId}`, token, workspaceSlug);
}

export function createMeeting(
  token: string,
  workspaceSlug: string,
  payload: MeetingCreateInput,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    '/api/v1/meeting/meetings',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateMeeting(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  payload: MeetingUpdateInput,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

/**
 * Append attendees to an existing meeting. Allowed for any current participant
 * (organizer or existing attendee), unlike ``updateMeeting`` whose attendee
 * field is organizer-only because it can also remove people.
 */
export function addMeetingAttendees(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  attendees: MeetingAttendeeInput[],
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/attendees`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({ attendees }),
    },
  );
}

/**
 * Hard-delete a finalized meeting recording. Permission: meeting organizer
 * OR the user who originally uploaded the recording.
 */
export function deleteMeetingRecording(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  recordingId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/${recordingId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function ensureMeetingNotes(
  token: string,
  workspaceSlug: string,
  meetingId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/notes/ensure`,
    token,
    workspaceSlug,
    { method: 'POST' },
  );
}

export function deleteMeeting(token: string, workspaceSlug: string, meetingId: string): Promise<void> {
  return request<void>(
    `/api/v1/meeting/meetings/${meetingId}`,
    token,
    workspaceSlug,
    {
      method: 'DELETE',
    },
  );
}

export function attachTaskToMeeting(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  issueId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/tasks`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({ issue_id: issueId }),
    },
  );
}

export function detachTaskFromMeeting(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  issueId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/tasks/${issueId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function attachDocToMeeting(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  docId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/docs`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify({ doc_id: docId }),
    },
  );
}

export function detachDocFromMeeting(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  docId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/docs/${docId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export async function uploadMeetingFile(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  file: File,
): Promise<MeetingDetail> {
  const formData = new FormData();
  formData.append('file', file);
  return multipartRequest<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/files`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: formData,
    },
  );
}

export function deleteMeetingFile(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  fileId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/files/${fileId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}

export function initRecordingStaging(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  payload: { idempotency_key: string; mime_type: string; linked_task_id?: string | null },
): Promise<RecordingStagingItem> {
  return request<RecordingStagingItem>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/staging`,
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
  meetingId: string,
  stagingId: string,
  seq: number,
  blob: Blob,
  chunkSha256: string,
): Promise<RecordingChunkAck> {
  const formData = new FormData();
  formData.append('file', blob, `chunk-${seq}.webm`);
  return multipartRequest<RecordingChunkAck>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/staging/${stagingId}/chunks/${seq}`,
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

export function completeRecordingStaging(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  stagingId: string,
  payload: { duration_sec_estimate?: number | null },
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/staging/${stagingId}/complete`,
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function listRecordingStaging(
  token: string,
  workspaceSlug: string,
  meetingId: string,
): Promise<RecordingStagingItem[]> {
  return request<RecordingStagingItem[]>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/staging`,
    token,
    workspaceSlug,
  );
}

export function discardRecordingStaging(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  stagingId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/staging/${stagingId}`,
    token,
    workspaceSlug,
    {
      method: 'DELETE',
    },
  );
}

export async function importMeetingRecording(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  file: Blob | File,
  linkedTaskId?: string | null,
): Promise<MeetingDetail> {
  const formData = new FormData();
  const filename = file instanceof File ? file.name : 'recovered-recording.webm';
  formData.append('file', file, filename);
  if (linkedTaskId) {
    formData.append('linked_task_id', linkedTaskId);
  }
  return multipartRequest<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/import`,
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
  meetingId: string,
  recordingId: string,
): Promise<RecordingPlaybackResponse> {
  return request<RecordingPlaybackResponse>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/${recordingId}/playback`,
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
    throw new MeetingApiError(response.status, `Request failed with ${response.status}.`);
  }
  return URL.createObjectURL(await response.blob());
}

export function retryMeetingRecording(
  token: string,
  workspaceSlug: string,
  meetingId: string,
  recordingId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/recordings/${recordingId}/retry`,
    token,
    workspaceSlug,
    {
      method: 'POST',
    },
  );
}

export function listMeetingUsers(
  token: string,
  workspaceSlug: string,
  options: { q?: string; limit?: number } = {},
): Promise<MeetingUser[]> {
  const params = new URLSearchParams();
  if (options.q) params.set('q', options.q);
  if (options.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return request<MeetingUser[]>(
    `/api/v1/meeting/users${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function getMeetingAvailability(
  token: string,
  workspaceSlug: string,
  options: { userIds: string[]; from: string; to: string },
): Promise<MeetingAvailabilityResponse> {
  const params = new URLSearchParams();
  for (const userId of options.userIds) {
    params.append('user_ids', userId);
  }
  params.set('from', options.from);
  params.set('to', options.to);
  return request<MeetingAvailabilityResponse>(
    `/api/v1/meeting/availability?${params.toString()}`,
    token,
    workspaceSlug,
  );
}
