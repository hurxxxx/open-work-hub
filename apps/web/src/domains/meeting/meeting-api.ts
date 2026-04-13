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
  project_key: string;
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
  storage_key: string;
  duration_sec: number | null;
  source: string;
  transcription_status: string;
  failure_reason: string | null;
  linked_doc_id: string | null;
  created_at: string;
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

export interface MeetingDetail {
  id: string;
  workspace_id: string;
  organizer_id: string;
  organizer_name: string;
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
  created_at: string;
  updated_at: string;
}

export interface MeetingUser {
  id: string;
  email: string;
  full_name: string;
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

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(resolveMeetingPath(path), {
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

function resolveMeetingPath(path: string): string {
  return rewriteWorkspaceApiPath(path);
}

export function listMeetings(
  token: string,
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
  );
}

export function getMeeting(token: string, meetingId: string): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/v1/meeting/meetings/${meetingId}`, token);
}

export function createMeeting(
  token: string,
  payload: MeetingCreateInput,
): Promise<MeetingDetail> {
  return request<MeetingDetail>('/api/v1/meeting/meetings', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateMeeting(
  token: string,
  meetingId: string,
  payload: MeetingUpdateInput,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/v1/meeting/meetings/${meetingId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteMeeting(token: string, meetingId: string): Promise<void> {
  return request<void>(`/api/v1/meeting/meetings/${meetingId}`, token, {
    method: 'DELETE',
  });
}

export function attachTaskToMeeting(
  token: string,
  meetingId: string,
  issueId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/v1/meeting/meetings/${meetingId}/tasks`, token, {
    method: 'POST',
    body: JSON.stringify({ issue_id: issueId }),
  });
}

export function detachTaskFromMeeting(
  token: string,
  meetingId: string,
  issueId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/tasks/${issueId}`,
    token,
    { method: 'DELETE' },
  );
}

export function attachDocToMeeting(
  token: string,
  meetingId: string,
  docId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/api/v1/meeting/meetings/${meetingId}/docs`, token, {
    method: 'POST',
    body: JSON.stringify({ doc_id: docId }),
  });
}

export function detachDocFromMeeting(
  token: string,
  meetingId: string,
  docId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/docs/${docId}`,
    token,
    { method: 'DELETE' },
  );
}

export async function uploadMeetingFile(
  token: string,
  meetingId: string,
  file: File,
): Promise<MeetingDetail> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(resolveMeetingPath(`/api/v1/meeting/meetings/${meetingId}/files`), {
    method: 'POST',
    headers: {
      // Do not set Content-Type — the browser fills in the multipart boundary.
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: formData,
    cache: 'no-store',
  });
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
  meetingId: string,
  fileId: string,
): Promise<MeetingDetail> {
  return request<MeetingDetail>(
    `/api/v1/meeting/meetings/${meetingId}/files/${fileId}`,
    token,
    { method: 'DELETE' },
  );
}

export function listMeetingUsers(
  token: string,
  options: { q?: string; limit?: number } = {},
): Promise<MeetingUser[]> {
  const params = new URLSearchParams();
  if (options.q) params.set('q', options.q);
  if (options.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return request<MeetingUser[]>(
    `/api/v1/meeting/users${query ? `?${query}` : ''}`,
    token,
  );
}
