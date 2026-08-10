import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type AnnouncementScope = 'workspace' | 'company';

export interface Announcement {
  id: string;
  workspaceId: string;
  authorId: string;
  authorName: string;
  scope: AnnouncementScope;
  title: string;
  body: string;
  isPinned: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AnnouncementsResponse {
  items: Announcement[];
}

export interface AnnouncementCreateInput {
  title: string;
  body?: string;
  scope?: AnnouncementScope;
  isPinned?: boolean;
}

export interface AnnouncementUpdateInput {
  title?: string;
  body?: string;
  isPinned?: boolean;
}

export class AnnouncementApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'AnnouncementApiError';
  }
}

async function request<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    rewriteWorkspaceApiPath(path, workspaceSlug),
    token,
    init,
    (error) =>
      new AnnouncementApiError(
        error.status,
        error.message || `Announcement request failed with ${error.status}.`,
      ),
  );
}

export function listAnnouncements(
  token: string,
  workspaceSlug: string,
  options: { scope?: AnnouncementScope; limit?: number } = {},
): Promise<AnnouncementsResponse> {
  const params = new URLSearchParams();
  if (options.scope) params.set('scope', options.scope);
  if (options.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return request<AnnouncementsResponse>(
    `/api/v1/announcements${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function createAnnouncement(
  token: string,
  workspaceSlug: string,
  payload: AnnouncementCreateInput,
): Promise<Announcement> {
  return request<Announcement>('/api/v1/announcements', token, workspaceSlug, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateAnnouncement(
  token: string,
  workspaceSlug: string,
  announcementId: string,
  payload: AnnouncementUpdateInput,
): Promise<Announcement> {
  return request<Announcement>(
    `/api/v1/announcements/${announcementId}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteAnnouncement(
  token: string,
  workspaceSlug: string,
  announcementId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/announcements/${announcementId}`,
    token,
    workspaceSlug,
    { method: 'DELETE' },
  );
}
