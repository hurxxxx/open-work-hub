import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';

export type VideoChatSessionStatus = 'open' | 'ended';
export type VideoChatRecordingStatus =
  | 'idle'
  | 'starting'
  | 'recording'
  | 'stopping'
  | 'failed'
  | 'saved';
export type VideoChatCaptionsStatus =
  | 'off'
  | 'starting'
  | 'on'
  | 'stopping'
  | 'failed';

export interface VideoChatSession {
  id: string;

  meeting_id: string | null;
  room_name: string;
  title: string;
  status: VideoChatSessionStatus;
  provider: string;
  started_by_id: string;
  started_by_name: string;
  started_at: string;
  ended_at: string | null;
  recording_status: VideoChatRecordingStatus;
  recording_egress_id: string | null;
  recording_id: string | null;
  captions_status: VideoChatCaptionsStatus;
  captions_started_at: string | null;
  captions_ended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface VideoChatSessionListResponse {
  items: VideoChatSession[];
  total: number;
}

export interface VideoChatJoinTokenResponse {
  session: VideoChatSession;
  livekit_url: string;
  token: string;
  identity: string;
  display_name: string;
  expires_at: string;
}

export class VideoChatApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token: string | null | undefined,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) => new VideoChatApiError(error.status, error.message),
  );
}

export function listVideoChatSessions(
  token: string | null | undefined,
  status?: VideoChatSessionStatus,
): Promise<VideoChatSessionListResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return request<VideoChatSessionListResponse>(
    `/api/v1/video-chat/sessions${query}`,
    token,
  );
}

export function createVideoChatSession(
  token: string | null | undefined,
  payload: { title?: string | null; meeting_id?: string | null } = {},
): Promise<VideoChatSession> {
  return request<VideoChatSession>('/api/v1/video-chat/sessions', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getVideoChatSession(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}`,
    token,
  );
}

export function createVideoChatJoinToken(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatJoinTokenResponse> {
  return request<VideoChatJoinTokenResponse>(
    `/api/v1/video-chat/sessions/${sessionId}/join-token`,
    token,
    { method: 'POST' },
  );
}

export function endVideoChatSession(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}/end`,
    token,
    { method: 'POST' },
  );
}

export function startVideoChatRecording(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}/recording/start`,
    token,
    { method: 'POST' },
  );
}

export function stopVideoChatRecording(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}/recording/stop`,
    token,
    { method: 'POST' },
  );
}

export function startVideoChatCaptions(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}/captions/start`,
    token,
    { method: 'POST' },
  );
}

export function stopVideoChatCaptions(
  token: string | null | undefined,
  sessionId: string,
): Promise<VideoChatSession> {
  return request<VideoChatSession>(
    `/api/v1/video-chat/sessions/${sessionId}/captions/stop`,
    token,
    { method: 'POST' },
  );
}
