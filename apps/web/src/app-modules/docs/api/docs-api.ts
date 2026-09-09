import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

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
): Promise<T> {
  const resolvedPath = resolveDocsPath(path);
  return apiFetchJsonWithMappedError<T>(
    resolvedPath,
    token,
    init,
    (error) => new DocsApiError(error.status, error.message),
  );
}

function withShareToken(path: string, shareToken?: string | null): string {
  if (!shareToken) {
    return path;
  }
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}share_token=${encodeURIComponent(shareToken)}`;
}

function resolveDocsPath(path: string): string {
  if (
    path.startsWith('/api/v1/docs/shared-links/') ||
    path.includes('share_token=')
  ) {
    return path;
  }
  return path;
}

export type DocsShareSummary = ApiSchema<'DocsShareSummary'>;
export type DocsPrimaryTarget = ApiSchema<'DocsPrimaryTarget'>;
export type DocsDocType = ApiSchema<'DocsHubItem'>['doc_type'];
export type DocsContentFormat = ApiSchema<'DocsPageItem'>['content_format'];
export type DocsHubContentFormat = ApiSchema<'DocsHubItem'>['content_format'];
export type DocsCollectionSummary = ApiSchema<'DocsCollectionSummary'>;
export type DocsHubItem = Omit<
  ApiSchema<'DocsHubItem'>,
  | 'collection'
  | 'last_viewed_at'
  | 'primary_target'
  | 'sharing_summary'
  | 'source_deeplink'
  | 'source_ref'
  | 'trashed_at'
> & {
  source_ref: string | null;
  collection: DocsCollectionSummary | null;
  primary_target: DocsPrimaryTarget | null;
  source_deeplink: string | null;
  trashed_at: string | null;
  last_viewed_at: string | null;
  sharing_summary: DocsShareSummary | null;
};
export type DocsHubResponse = Omit<ApiSchema<'DocsHubResponse'>, 'items'> & {
  items: DocsHubItem[];
};

export function getDocsItemPrimaryTargetId(
  item: DocsHubItem,
  app?: string,
  type?: string,
): string | null {
  const target = item.primary_target;
  if (!target) {
    return null;
  }
  if (app && target.app !== app) {
    return null;
  }
  if (type && target.type !== type) {
    return null;
  }
  return target.id;
}

export function getDocsItemPrimaryTargetSortOrder(item: DocsHubItem): number {
  return item.primary_target?.sort_order ?? 0;
}

export function withDocsItemPrimaryTargetSortOrder(
  item: DocsHubItem,
  sortOrder: number,
): DocsHubItem {
  if (!item.primary_target) {
    return item;
  }
  return {
    ...item,
    primary_target: {
      ...item.primary_target,
      sort_order: sortOrder,
    },
  };
}

export type DocsPageItem = Omit<
  ApiSchema<'DocsPageItem'>,
  'content_blocks' | 'content_text' | 'parent_id' | 'trashed_at'
> & {
  parent_id: string | null;
  content_blocks: Record<string, unknown>[] | null;
  content_text: string | null;
  trashed_at: string | null;
};
export type DocsPageListResponse = Omit<
  ApiSchema<'DocsPageListResponse'>,
  'items'
> & {
  items: DocsPageItem[];
};
export type DocsPagesEventPayload = {
  doc_id?: string;
  action?: 'created' | 'updated' | 'deleted';
  page_id?: string | null;
  parent_id?: string | null;
  actor_user_id?: string | null;
};

export function mediaResourceTypeForDocsPage(): 'docs_native_page' {
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
export type DocsCollabSnapshotResponse =
  ApiSchema<'DocsCollabSnapshotResponse'>;
export type FavoriteDocItem = ApiSchema<'FavoriteDocItem'>;
export type RecentPageItem = ApiSchema<'RecentPageItem'>;
export type ShareableUserItem = ApiSchema<'ShareableUserItem'>;
export type NativeUserShareItem = ApiSchema<'NativeUserShareItem'>;
export type NativeLinkShareItem = ApiSchema<'NativeLinkShareItem'>;
export type NativeDocSharingResponse = ApiSchema<'NativeDocSharingResponse'>;
export type ResolveSharedLinkResponse = ApiSchema<'ResolveSharedLinkResponse'>;
export type RelatedPmsTaskItem = ApiSchema<'RelatedPmsTaskItem'>;
export type RelatedPmsTasksResponse = Omit<
  ApiSchema<'RelatedPmsTasksResponse'>,
  'items'
> & {
  items: RelatedPmsTaskItem[];
};

export const DOC_CONTENT_FORMAT_VALUES = ['block', 'html'] as const;
export const DOC_HUB_CONTENT_FORMAT_VALUES = [
  'block',
  'html',
  'mixed',
] as const;

export function isDocsContentFormat(
  value: unknown,
): value is DocsContentFormat {
  return DOC_CONTENT_FORMAT_VALUES.includes(value as DocsContentFormat);
}

export function resolveDocsContentFormat(
  page?: { content_format?: DocsContentFormat | null } | null,
): DocsContentFormat {
  if (isDocsContentFormat(page?.content_format)) {
    return page.content_format;
  }
  return 'block';
}

export function isDocsHubContentFormat(
  value: unknown,
): value is DocsHubContentFormat {
  return DOC_HUB_CONTENT_FORMAT_VALUES.includes(value as DocsHubContentFormat);
}

export function resolveDocsHubContentFormat(
  doc?: { content_format?: DocsHubContentFormat | null } | null,
): DocsHubContentFormat {
  if (isDocsHubContentFormat(doc?.content_format)) {
    return doc.content_format;
  }
  return 'block';
}

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
    doc_type?: DocsDocType;
    space_id?: string;
  } = {},
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
  if (params.doc_type) qs.set('doc_type', params.doc_type);
  if (params.space_id) qs.set('space_id', params.space_id);
  return request<DocsHubResponse>(`/api/v1/docs/hub?${qs}`, token, {});
}

export function createNativeDoc(
  token: string,
  payload: {
    title: string;
    company_visible?: boolean;
    company_admin_read_acknowledged?: boolean;
    first_page_title?: string;
    source_app?: string;
    source_kind?: string;
    source_ref?: string | null;
    generation_kind?: string;
    doc_type?: DocsDocType;
    content_format?: DocsContentFormat;
    first_page_content_text?: string | null;
    primary_target?: {
      company_admin_read_acknowledged?: boolean;
      app: string;
      type: string;
      id: string;
      sort_order?: number;
    } | null;
  },
): Promise<DocsHubItem> {
  return request<DocsHubItem>('/api/v1/docs/items', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getDocsItem(
  token: string,
  itemId: string,
  shareToken?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    withShareToken(`/api/v1/docs/items/${itemId}`, shareToken),
    token,
    {},
  );
}

export function listDocPmsTasks(
  token: string,
  itemId: string,
): Promise<RelatedPmsTasksResponse> {
  return request<RelatedPmsTasksResponse>(
    `/api/v1/docs/items/${itemId}/pms-tasks`,
    token,
    {},
  );
}

export function attachDocPmsTask(
  token: string,
  itemId: string,
  taskId: string,
): Promise<RelatedPmsTasksResponse> {
  return request<RelatedPmsTasksResponse>(
    `/api/v1/docs/items/${itemId}/pms-tasks`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId }),
    },
  );
}

export function detachDocPmsTask(
  token: string,
  itemId: string,
  taskId: string,
): Promise<RelatedPmsTasksResponse> {
  return request<RelatedPmsTasksResponse>(
    `/api/v1/docs/items/${itemId}/pms-tasks/${taskId}`,
    token,
    { method: 'DELETE' },
  );
}

export function updateDocsItem(
  token: string,
  itemId: string,
  payload: {
    title?: string;
    doc_type?: DocsDocType;
  },
  shareToken?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    withShareToken(`/api/v1/docs/items/${itemId}`, shareToken),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteDocsItem(
  token: string,
  itemId: string,
  shareToken?: string | null,
): Promise<void> {
  return request<void>(
    withShareToken(`/api/v1/docs/items/${itemId}`, shareToken),
    token,
    {
      method: 'DELETE',
    },
  );
}

export function duplicateDocsItem(
  token: string,
  itemId: string,
  shareToken?: string | null,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(
    withShareToken(`/api/v1/docs/items/${itemId}/duplicate`, shareToken),
    token,
    {
      method: 'POST',
    },
  );
}

export function listDocPages(
  token: string,
  itemId: string,
  shareToken?: string | null,
): Promise<DocsPageListResponse> {
  return request<DocsPageListResponse>(
    withShareToken(`/api/v1/docs/items/${itemId}/pages`, shareToken),
    token,
    {},
  );
}

export function createDocPage(
  token: string,
  itemId: string,
  payload: {
    title: string;
    parent_id?: string | null;
    content_format?: DocsContentFormat;
    content_blocks?: Record<string, unknown>[] | null;
    content_text?: string | null;
    sort_order?: number | null;
  },
  shareToken?: string | null,
): Promise<DocsPageItem> {
  return request<DocsPageItem>(
    withShareToken(`/api/v1/docs/items/${itemId}/pages`, shareToken),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateDocPage(
  token: string,
  pageId: string,
  payload: {
    title?: string;
    parent_id?: string | null;
    content_blocks?: Record<string, unknown>[] | null;
    content_text?: string | null;
    sort_order?: number | null;
  },
  shareToken?: string | null,
): Promise<DocsPageItem> {
  return request<DocsPageItem>(
    withShareToken(`/api/v1/docs/pages/${pageId}`, shareToken),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function makeDocsPageRef(
  sourceType: 'native_doc_page',
  sourcePageId: string,
): string {
  return `${sourceType}__${sourcePageId}`;
}

export function updateDocTarget(
  token: string,
  itemId: string,
  payload: {
    company_admin_read_acknowledged?: boolean;
    app: string;
    type: string;
    id: string;
    sort_order?: number;
  },
): Promise<DocsHubItem> {
  return request<DocsHubItem>(`/api/v1/docs/items/${itemId}/target`, token, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteDocTarget(
  token: string,
  itemId: string,
): Promise<DocsHubItem> {
  return request<DocsHubItem>(`/api/v1/docs/items/${itemId}/target`, token, {
    method: 'DELETE',
  });
}

export function getDocsCollabSession(
  token: string,
  pageRef: string,
): Promise<DocsCollabSession> {
  return request<DocsCollabSession>(
    `/api/v1/docs/collab/pages/${encodeURIComponent(pageRef)}/session`,
    token,
    {},
  );
}

export function saveDocsCollabSnapshot(
  token: string,
  pageRef: string,
  payload: {
    content_blocks?: Record<string, unknown>[] | null;
    yjs_state?: string | null;
  },
  init?: RequestInit,
): Promise<DocsCollabSnapshotResponse> {
  return request<DocsCollabSnapshotResponse>(
    `/api/v1/docs/collab/pages/${encodeURIComponent(pageRef)}/snapshot`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
      ...(init ?? {}),
    },
  );
}

export function deleteDocPage(
  token: string,
  pageId: string,
  shareToken?: string | null,
): Promise<void> {
  return request<void>(
    withShareToken(`/api/v1/docs/pages/${pageId}`, shareToken),
    token,
    {
      method: 'DELETE',
    },
  );
}

export function toggleDocFavorite(
  token: string,
  itemId: string,
): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(
    `/api/v1/docs/items/${itemId}/favorite`,
    token,
    {
      method: 'PATCH',
    },
  );
}

export function recordDocView(
  token: string,
  itemId: string,
  pageId?: string | null,
  shareToken?: string | null,
): Promise<void> {
  return request<void>(
    withShareToken(`/api/v1/docs/items/${itemId}/view`, shareToken),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ page_id: pageId ?? null }),
    },
  );
}

export function listFavoriteDocs(token: string): Promise<FavoriteDocItem[]> {
  return request<FavoriteDocItem[]>('/api/v1/docs/favorites', token, {});
}

export function listRecentPages(
  token: string,
  limit = 10,
): Promise<RecentPageItem[]> {
  return request<RecentPageItem[]>(
    `/api/v1/docs/recent-pages?limit=${limit}`,
    token,
    {},
  );
}

export function listShareableUsers(
  token: string,
  q?: string,
): Promise<ShareableUserItem[]> {
  const suffix = q ? `?q=${encodeURIComponent(q)}` : '';
  return request<ShareableUserItem[]>(
    `/api/v1/docs/shareable-users${suffix}`,
    token,
    {},
  );
}

export function getDocSharing(
  token: string,
  itemId: string,
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(
    `/api/v1/docs/items/${itemId}/sharing`,
    token,
    {},
  );
}

export function upsertDocUserShare(
  token: string,
  itemId: string,
  userId: string,
  accessLevel: 'read' | 'edit',
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(
    `/api/v1/docs/items/${itemId}/sharing/users/${userId}`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ access_level: accessLevel }),
    },
  );
}

export function deleteDocUserShare(
  token: string,
  itemId: string,
  userId: string,
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(
    `/api/v1/docs/items/${itemId}/sharing/users/${userId}`,
    token,
    {
      method: 'DELETE',
    },
  );
}

export function upsertDocLinkShare(
  token: string,
  itemId: string,
  payload: {
    access_level: 'read' | 'edit';
    active: boolean;
    regenerate_token?: boolean;
  },
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(
    `/api/v1/docs/items/${itemId}/sharing/link`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteDocLinkShare(
  token: string,
  itemId: string,
): Promise<NativeDocSharingResponse> {
  return request<NativeDocSharingResponse>(
    `/api/v1/docs/items/${itemId}/sharing/link`,
    token,
    {
      method: 'DELETE',
    },
  );
}

export function resolveSharedLink(
  token: string,
  shareToken: string,
): Promise<ResolveSharedLinkResponse> {
  return request<ResolveSharedLinkResponse>(
    `/api/v1/docs/shared-links/${shareToken}`,
    token,
  );
}

export async function updateDocsCompanySharing(
  token: string,
  itemId: string,
  enabled: boolean,
  acknowledged: boolean,
): Promise<DocsHubItem> {
  await request<void>(`/api/v1/docs/items/${itemId}/sharing/company`, token, {
    method: 'PUT',
    body: JSON.stringify({
      enabled,
      company_admin_read_acknowledged: acknowledged,
    }),
  });
  return getDocsItem(token, itemId);
}
