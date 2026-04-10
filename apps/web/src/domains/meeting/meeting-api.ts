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

export class MeetingApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
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
