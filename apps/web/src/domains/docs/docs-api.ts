import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

export class DocsApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  const resolvedPath = resolveDocsPath(path, workspaceSlug);
  const response = await fetch(resolvedPath, {
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
    throw new DocsApiError(
      response.status,
      payload?.detail ?? `Request failed with ${response.status}.`,
    );
  }

  return payload as T;
}

function withShareToken(path: string, shareToken?: string | null): string {
  if (!shareToken) {
    return path;
  }
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}share_token=${encodeURIComponent(shareToken)}`;
}

function resolveDocsPath(path: string, workspaceSlug?: string | null): string {
  if (
    path.startsWith('/api/v1/docs/shared-links/')
    || path.includes('share_token=')
  ) {
    return path;
  }
  return rewriteWorkspaceApiPath(path, workspaceSlug);
}

export interface DocsShareSummary {
  visibility: 'private' | 'shared';
  user_share_count: number;
  link_active: boolean;
  link_access_level: 'read' | 'edit' | null;
}

export interface DocsHubItem {
  id: string;
  source_app: string;
  source_type: 'native_doc' | 'pms_space_doc';
  source_id: string;
  structure_kind: 'page_tree';
  location_label: string;
  title: string;
  page_count: number;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
  is_favorite: boolean;
  is_private: boolean;
  last_viewed_at: string | null;
  can_view: boolean;
  can_edit: boolean;
  can_share: boolean;
  can_manage: boolean;
  sharing_summary: DocsShareSummary | null;
}

export interface DocsHubResponse {
  items: DocsHubItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocsPageItem {
  id: string;
  doc_id: string;
  source_type: 'native_doc_page' | 'pms_space_doc_page';
  source_page_id: string;
  parent_id: string | null;
  title: string;
  content_blocks: Record<string, unknown>[] | null;
  sort_order: number;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
  can_edit: boolean;
  realtime_collab: boolean;
}

export interface DocsPageListResponse {
  items: DocsPageItem[];
}

export function mediaResourceTypeForDocsPage(
  sourceType: DocsPageItem['source_type'],
): 'docs_native_page' | 'space_doc_page' {
  return sourceType === 'native_doc_page' ? 'docs_native_page' : 'space_doc_page';
}

export interface DocsCollabSession {
  page_ref: string;
  source_type: 'native_doc_page' | 'pms_space_doc_page';
  source_page_id: string;
  room_key: string;
  ws_path: string;
  can_edit: boolean;
  realtime_status: 'enabled' | 'degraded';
  read_only_reason: 'relay_unavailable' | 'permission_revoked' | null;
  user: {
    id: string;
    full_name: string;
  };
  snapshot_content_blocks: Record<string, unknown>[] | null;
  yjs_state: string | null;
}

export interface DocsCollabSnapshotResponse {
  updated_at: string;
  last_snapshot_at: string;
}

export interface FavoriteDocItem {
  id: string;
  title: string;
  source_type: string;
}

export interface RecentPageItem {
  page_id: string;
  page_title: string;
  doc_id: string;
  doc_title: string;
  source_type: string;
  location_label: string;
  last_viewed_at: string;
}

export interface ShareableUserItem {
  id: string;
  email: string;
  full_name: string;
}

export interface NativeUserShareItem {
  user_id: string;
  email: string;
  full_name: string;
  access_level: 'read' | 'edit';
}

export interface NativeLinkShareItem {
  token: string;
  access_level: 'read' | 'edit';
  active: boolean;
  share_path: string;
}

export interface NativeDocSharingResponse {
  doc_id: string;
  owner_id: string;
  users: NativeUserShareItem[];
  link_share: NativeLinkShareItem | null;
}

export interface ResolveSharedLinkResponse {
  item: DocsHubItem;
}

export function listDocsHub(
  token: string,
  params: {
    category?: string;
    q?: string;
    sort_by?: string;
    sort_dir?: string;
    page?: number;
    page_size?: number;
  } = {},
  workspaceSlug?: string | null,
): Promise<DocsHubResponse> {
  const qs = new URLSearchParams();
  if (params.category) qs.set('category', params.category);
  if (params.q) qs.set('q', params.q);
  if (params.sort_by) qs.set('sort_by', params.sort_by);
  if (params.sort_dir) qs.set('sort_dir', params.sort_dir);
  if (params.page) qs.set('page', String(params.page));
  if (params.page_size) qs.set('page_size', String(params.page_size));
  return request<DocsHubResponse>(`/api/v1/docs/hub?${qs}`, token, {}, workspaceSlug);
}

export function createNativeDoc(
  token: string,
  payload: { title: string; first_page_title?: string },
): Promise<DocsHubItem> {
  return request<DocsHubItem>('/api/v1/docs/native-docs', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getDocsItem(
  token: string,
  itemId: string,
  shareToken?: string | null,
  workspaceSlug?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    withShareToken(`/api/v1/docs/items/${itemId}`, shareToken),
    token,
    {},
    workspaceSlug,
  );
}

export function updateDocsItem(
  token: string,
  itemId: string,
  payload: { title?: string },
  shareToken?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(withShareToken(`/api/v1/docs/items/${itemId}`, shareToken), token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteDocsItem(token: string, itemId: string, shareToken?: string | null): Promise<void> {
  return request<void>(withShareToken(`/api/v1/docs/items/${itemId}`, shareToken), token, {
    method: 'DELETE',
  });
}

export function duplicateDocsItem(
  token: string,
  itemId: string,
  shareToken?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(withShareToken(`/api/v1/docs/items/${itemId}/duplicate`, shareToken), token, {
    method: 'POST',
  });
}

export function listDocPages(
  token: string,
  itemId: string,
  shareToken?: string | null,
  workspaceSlug?: string | null,
): Promise<DocsPageListResponse> {
  return request<DocsPageListResponse>(
    withShareToken(`/api/v1/docs/items/${itemId}/pages`, shareToken),
    token,
    {},
    workspaceSlug,
  );
}

export function createDocPage(
  token: string,
  itemId: string,
  payload: {
    title: string;
    parent_id?: string | null;
    content_blocks?: Record<string, unknown>[] | null;
    sort_order?: number | null;
  },
  shareToken?: string | null,
): Promise<DocsPageItem> {
  return request<DocsPageItem>(withShareToken(`/api/v1/docs/items/${itemId}/pages`, shareToken), token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateDocPage(
  token: string,
  pageId: string,
  payload: {
    title?: string;
    parent_id?: string | null;
    content_blocks?: Record<string, unknown>[] | null;
    sort_order?: number | null;
  },
  shareToken?: string | null,
  workspaceSlug?: string | null,
): Promise<DocsPageItem> {
  return request<DocsPageItem>(
    withShareToken(`/api/v1/docs/pages/${pageId}`, shareToken),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function makeDocsPageRef(
  sourceType: 'native_doc_page' | 'pms_space_doc_page',
  sourcePageId: string,
): string {
  return `${sourceType}__${sourcePageId}`;
}

export function getDocsCollabSession(
  token: string,
  pageRef: string,
  workspaceSlug?: string | null,
): Promise<DocsCollabSession> {
  return request<DocsCollabSession>(
    `/api/v1/docs/collab/pages/${encodeURIComponent(pageRef)}/session`,
    token,
    {},
    workspaceSlug,
  );
}

export function saveDocsCollabSnapshot(
  token: string,
  pageRef: string,
  payload: {
    content_blocks?: Record<string, unknown>[] | null;
    yjs_state?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<DocsCollabSnapshotResponse> {
  return request<DocsCollabSnapshotResponse>(
    `/api/v1/docs/collab/pages/${encodeURIComponent(pageRef)}/snapshot`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteDocPage(token: string, pageId: string, shareToken?: string | null): Promise<void> {
  return request<void>(withShareToken(`/api/v1/docs/pages/${pageId}`, shareToken), token, {
    method: 'DELETE',
  });
}

export function toggleDocFavorite(token: string, itemId: string): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(`/api/v1/docs/items/${itemId}/favorite`, token, {
    method: 'PATCH',
  });
}

export function recordDocView(
  token: string,
  itemId: string,
  pageId?: string | null,
  shareToken?: string | null,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    withShareToken(`/api/v1/docs/items/${itemId}/view`, shareToken),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ page_id: pageId ?? null }),
    },
    workspaceSlug,
  );
}

export function listFavoriteDocs(token: string): Promise<FavoriteDocItem[]> {
  return request<FavoriteDocItem[]>('/api/v1/docs/favorites', token);
}

export function listRecentPages(token: string, limit = 10): Promise<RecentPageItem[]> {
  return request<RecentPageItem[]>(`/api/v1/docs/recent-pages?limit=${limit}`, token);
}

export function listShareableUsers(token: string, q?: string): Promise<ShareableUserItem[]> {
  const suffix = q ? `?q=${encodeURIComponent(q)}` : '';
  return request<ShareableUserItem[]>(`/api/v1/docs/shareable-users${suffix}`, token);
}

export function getDocSharing(token: string, itemId: string): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(`/api/v1/docs/items/${itemId}/sharing`, token);
}

export function upsertDocUserShare(
  token: string,
  itemId: string,
  userId: string,
  accessLevel: 'read' | 'edit',
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(`/api/v1/docs/items/${itemId}/sharing/users/${userId}`, token, {
    method: 'PUT',
    body: JSON.stringify({ access_level: accessLevel }),
  });
}

export function deleteDocUserShare(
  token: string,
  itemId: string,
  userId: string,
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(`/api/v1/docs/items/${itemId}/sharing/users/${userId}`, token, {
    method: 'DELETE',
  });
}

export function upsertDocLinkShare(
  token: string,
  itemId: string,
  payload: { access_level: 'read' | 'edit'; active: boolean; regenerate_token?: boolean },
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(`/api/v1/docs/items/${itemId}/sharing/link`, token, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteDocLinkShare(token: string, itemId: string): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(`/api/v1/docs/items/${itemId}/sharing/link`, token, {
    method: 'DELETE',
  });
}

export function resolveSharedLink(token: string, shareToken: string): Promise<ResolveSharedLinkResponse> {
  return request<ResolveSharedLinkResponse>(`/api/v1/docs/shared-links/${shareToken}`, token);
}
