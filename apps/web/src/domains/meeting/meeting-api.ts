import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

export type MeetingStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
export type AttendeeRole = 'required' | 'optional';
export type AttendeeResponse = 'pending' | 'accepted' | 'declined' | 'tentative';

export interface MeetingAttendee {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: AttendeeRole;
  response: AttendeeResponse;
}

export interface MeetingTaskLink {
  id: string;
  issue_id: string;
  issue_title: string;
  list_key: string;
  issue_number: number;
  added_by_id: string;
  created_at: string;
}

export interface MeetingDocLink {
  id: string;
  doc_id: string;
  doc_title: string;
  added_by_id: string;
  created_at: string;
}

export interface MeetingFileAttachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  download_url: string;
  added_by_id: string;
  added_by_name: string;
  created_at: string;
}

export interface MeetingRecording {
  id: string;
  meeting_id: string;
  uploaded_by_id: string;
  storage_key: string;
  duration_sec: number | null;
  source: string;
  transcription_status: string;
  progress_pct: number;
  file_size: number;
  mime_type: string;
  failure_reason: string | null;
  linked_doc_id: string | null;
  linked_task_id: string | null;
  transcribe_started_at: string | null;
  transcribe_completed_at: string | null;
  created_at: string;
}

export interface RecordingStagingItem {
  id: string;
  meeting_id: string;
  uploaded_by_id: string;
  idempotency_key: string;
  status: string;
  mime_type: string;
  bytes_received: number;
  chunk_count: number;
  highest_seq: number;
  linked_task_id: string | null;
  started_at: string;
  last_chunk_at: string;
  completed_at: string | null;
}

export interface RecordingChunkAck {
  seq: number;
  bytes_received: number;
  highest_seq: number;
}

export interface RecordingPlaybackResponse {
  url: string;
  expires_at: string;
}

export interface MeetingListItem {
  id: string;
  title: string;
  organizer_id: string;
  organizer_name: string;
  start_at: string;
  end_at: string;
  status: MeetingStatus;
  attendee_count: number;
  task_link_count: number;
  doc_link_count: number;
}

export interface MeetingListResponse {
  items: MeetingListItem[];
  total: number;
}

export interface ActiveRecordingLock {
  staging_id: string;
  user_id: string;
  user_name: string;
  started_at: string;
  /** When the recorder last uploaded a chunk. Used to render "x초 전 활동". */
  last_active_at: string;
}

export interface MeetingDetail {
  id: string;
  workspace_id: string;
  organizer_id: string;
  organizer_name: string;
  notes_doc_id: string | null;
  notes_page_id: string | null;
  title: string;
  agenda: string;
  start_at: string;
  end_at: string;
  status: MeetingStatus;
  attendees: MeetingAttendee[];
  task_links: MeetingTaskLink[];
  doc_links: MeetingDocLink[];
  file_attachments: MeetingFileAttachment[];
  recordings: MeetingRecording[];
  /**
   * Non-null when another user (or the viewer themselves) currently holds
   * the meeting's single-recorder lock. The backend auto-releases the lock
   * after RECORDING_STALE_AFTER_SECONDS of inactivity so a crashed recorder
   * never permanently blocks other participants.
   */
  active_recording_lock: ActiveRecordingLock | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingUser {
  id: string;
  email: string;
  full_name: string;
}

export interface MeetingAvailabilityBlock {
  id: string;
  start: string;
  end: string;
  allDay: boolean;
  sourceType: 'meeting' | 'planner_event';
  masked: boolean;
  title: string | null;
  location: string | null;
}

export interface MeetingAvailabilityItem {
  userId: string;
  fullName: string;
  blocks: MeetingAvailabilityBlock[];
}

export interface MeetingAvailabilityResponse {
  items: MeetingAvailabilityItem[];
}

export interface MeetingAttendeeInput {
  user_id: string;
  role: AttendeeRole;
}

export interface MeetingCreateInput {
  title: string;
  agenda: string;
  start_at: string;
  end_at: string;
  attendees: MeetingAttendeeInput[];
  task_ids?: string[];
  doc_ids?: string[];
}

export interface MeetingUpdateInput {
  title?: string;
  agenda?: string;
  start_at?: string;
  end_at?: string;
  status?: MeetingStatus;
  attendees?: MeetingAttendeeInput[];
}

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
  if (iso.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(iso)) {
    return new Date(iso);
  }
  return new Date(`${iso}Z`);
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
  const response = await fetch(resolveMeetingPath(path, workspaceSlug), {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new MeetingApiError(
      response.status,
      payload?.detail ?? `Request failed with ${response.status}.`,
    );
  }

  return payload as T;
}

async function multipartRequest<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(resolveMeetingPath(path, workspaceSlug), {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new MeetingApiError(
      response.status,
      payload?.detail ?? `Request failed with ${response.status}.`,
    );
  }
  return payload as T;
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
  const response = await fetch(
    resolveMeetingPath(`/api/v1/meeting/meetings/${meetingId}/files`, workspaceSlug),
    {
      method: 'POST',
      headers: {
        // Do not set Content-Type — the browser fills in the multipart boundary.
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: formData,
      cache: 'no-store',
    },
  );
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new MeetingApiError(
      response.status,
      payload?.detail ?? `파일 업로드에 실패했습니다 (${response.status}).`,
    );
  }
  return payload as MeetingDetail;
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
