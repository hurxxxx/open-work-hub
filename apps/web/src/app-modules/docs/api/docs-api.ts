import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

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
  try {
    return await apiFetchJson<T>(resolvedPath, token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new DocsApiError(error.status, error.message);
    }
    throw error;
  }
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

export type DocsShareSummary = ApiSchema<'DocsShareSummary'>;
export type DocsPrimaryContainer = ApiSchema<'DocsPrimaryContainer'>;
export type DocsHubItem = Omit<
  ApiSchema<'DocsHubItem'>,
  'last_viewed_at' | 'primary_container' | 'sharing_summary' | 'source_deeplink' | 'source_ref' | 'trashed_at'
> & {
  source_ref: string | null;
  primary_container: DocsPrimaryContainer | null;
  source_deeplink: string | null;
  trashed_at: string | null;
  last_viewed_at: string | null;
  sharing_summary: DocsShareSummary | null;
};
export type DocsHubResponse = Omit<ApiSchema<'DocsHubResponse'>, 'items'> & {
  items: DocsHubItem[];
};

export function getDocsItemPrimaryContainerId(
  item: DocsHubItem,
  app?: string,
  type?: string,
): string | null {
  const container = item.primary_container;
  if (!container) {
    return null;
  }
  if (app && container.app !== app) {
    return null;
  }
  if (type && container.type !== type) {
    return null;
  }
  return container.id;
}

export function getDocsItemPrimaryContainerSortOrder(item: DocsHubItem): number {
  return item.primary_container?.sort_order ?? 0;
}

export function withDocsItemPrimaryContainerSortOrder(
  item: DocsHubItem,
  sortOrder: number,
): DocsHubItem {
  if (!item.primary_container) {
    return item;
  }
  return {
    ...item,
    primary_container: {
      ...item.primary_container,
      sort_order: sortOrder,
    },
  };
}

export type DocsPageItem = Omit<ApiSchema<'DocsPageItem'>, 'content_blocks' | 'parent_id' | 'trashed_at'> & {
  parent_id: string | null;
  content_blocks: Record<string, unknown>[] | null;
  trashed_at: string | null;
};
export type DocsPageListResponse = Omit<ApiSchema<'DocsPageListResponse'>, 'items'> & {
  items: DocsPageItem[];
};

export function mediaResourceTypeForDocsPage(
  sourceType: DocsPageItem['source_type'],
): 'docs_native_page' {
  return 'docs_native_page';
}

export type DocsCollabSession = Omit<
  ApiSchema<'DocsCollabSessionResponse'>,
  'read_only_reason' | 'snapshot_content_blocks' | 'yjs_state'
> & {
  read_only_reason: 'relay_unavailable' | 'permission_revoked' | null;
  snapshot_content_blocks: Record<string, unknown>[] | null;
  yjs_state: string | null;
};
export type DocsCollabSnapshotResponse = ApiSchema<'DocsCollabSnapshotResponse'>;
export type FavoriteDocItem = ApiSchema<'FavoriteDocItem'>;
export type RecentPageItem = ApiSchema<'RecentPageItem'>;
export type ShareableUserItem = ApiSchema<'ShareableUserItem'>;
export type NativeUserShareItem = ApiSchema<'NativeUserShareItem'>;
export type NativeLinkShareItem = ApiSchema<'NativeLinkShareItem'>;
export type NativeDocSharingResponse = ApiSchema<'NativeDocSharingResponse'>;
export type ResolveSharedLinkResponse = ApiSchema<'ResolveSharedLinkResponse'>;

export function listDocsHub(
  token: string,
  params: {
    view?: string;
    q?: string;
    sort_by?: string;
    sort_dir?: string;
    page?: number;
    page_size?: number;
    source_app?: string;
    source_kind?: string;
    container_app?: string;
    container_type?: string;
    container_id?: string;
  } = {},
  workspaceSlug?: string | null,
): Promise<DocsHubResponse> {
  const qs = new URLSearchParams();
  if (params.view) qs.set('view', params.view);
  if (params.q) qs.set('q', params.q);
  if (params.sort_by) qs.set('sort_by', params.sort_by);
  if (params.sort_dir) qs.set('sort_dir', params.sort_dir);
  if (params.page) qs.set('page', String(params.page));
  if (params.page_size) qs.set('page_size', String(params.page_size));
  if (params.source_app) qs.set('source_app', params.source_app);
  if (params.source_kind) qs.set('source_kind', params.source_kind);
  if (params.container_app) qs.set('container_app', params.container_app);
  if (params.container_type) qs.set('container_type', params.container_type);
  if (params.container_id) qs.set('container_id', params.container_id);
  return request<DocsHubResponse>(`/api/v1/docs/hub?${qs}`, token, {}, workspaceSlug);
}

export function createNativeDoc(
  token: string,
  payload: {
    title: string;
    first_page_title?: string;
    source_app?: string;
    source_kind?: string;
    source_ref?: string | null;
    generation_kind?: string;
    primary_container?: {
      app: string;
      type: string;
      id: string;
      sort_order?: number;
    } | null;
  },
  workspaceSlug?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    '/api/v1/docs/items',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
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
  workspaceSlug?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    withShareToken(`/api/v1/docs/items/${itemId}`, shareToken),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
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
  sourceType: 'native_doc_page',
  sourcePageId: string,
): string {
  return `${sourceType}__${sourcePageId}`;
}

export function updateDocContainer(
  token: string,
  itemId: string,
  payload: {
    app: string;
    type: string;
    id: string;
    sort_order?: number;
  },
  workspaceSlug?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    `/api/v1/docs/items/${itemId}/container`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteDocContainer(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    `/api/v1/docs/items/${itemId}/container`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
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

export function listRecentPages(
  token: string,
  limit = 10,
  workspaceSlug?: string | null,
): Promise<RecentPageItem[]> {
  return request<RecentPageItem[]>(`/api/v1/docs/recent-pages?limit=${limit}`, token, {}, workspaceSlug);
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
