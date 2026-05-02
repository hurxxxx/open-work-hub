import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export class WhiteboardApiError extends Error {
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
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path, workspaceSlug), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new WhiteboardApiError(error.status, error.message);
    }
    throw error;
  }
}

export interface WhiteboardScene {
  elements: unknown[];
  appState: Record<string, unknown>;
  files: Record<string, unknown>;
  [key: string]: unknown;
}

export type WhiteboardPrimaryContainer = ApiSchema<'WhiteboardPrimaryContainer'>;
export type WhiteboardContainerItem = ApiSchema<'WhiteboardContainerItem'>;
export type WhiteboardHubItem = Omit<
  ApiSchema<'WhiteboardHubItem'>,
  'containers' | 'last_viewed_at' | 'primary_container' | 'source_deeplink' | 'source_ref' | 'trashed_at'
> & {
  source_ref: string | null;
  primary_container: WhiteboardPrimaryContainer | null;
  containers: WhiteboardContainerItem[];
  source_deeplink: string | null;
  trashed_at: string | null;
  last_viewed_at: string | null;
};
export type WhiteboardDetail = WhiteboardHubItem & Omit<ApiSchema<'WhiteboardDetail'>, keyof WhiteboardHubItem | 'scene'> & {
  scene: WhiteboardScene;
};
export type WhiteboardHubResponse = Omit<ApiSchema<'WhiteboardHubResponse'>, 'items'> & {
  items: WhiteboardHubItem[];
};
export type WhiteboardContextSlotResponse = Omit<ApiSchema<'WhiteboardContextSlotResponse'>, 'item'> & {
  item: WhiteboardDetail | null;
};
export type ShareableUserItem = ApiSchema<'ShareableUserItem'>;
export type WhiteboardUserShareItem = ApiSchema<'WhiteboardUserShareItem'>;
export type WhiteboardLinkShareItem = ApiSchema<'WhiteboardLinkShareItem'>;
export type WhiteboardSharingResponse = ApiSchema<'WhiteboardSharingResponse'>;
export type ResolveWhiteboardSharedLinkResponse = Omit<ApiSchema<'ResolveWhiteboardSharedLinkResponse'>, 'item'> & {
  item: WhiteboardHubItem;
};
export type WhiteboardCollabSession = Omit<
  ApiSchema<'WhiteboardCollabSessionResponse'>,
  'read_only_reason' | 'snapshot_scene' | 'yjs_state'
> & {
  read_only_reason: 'relay_unavailable' | 'permission_revoked' | null;
  snapshot_scene: WhiteboardScene | null;
  yjs_state: string | null;
};
export type WhiteboardCollabSnapshotResponse = ApiSchema<'WhiteboardCollabSnapshotResponse'>;

function sceneElementId(element: unknown): string | null {
  if (!element || typeof element !== 'object') return null;
  const id = (element as { id?: unknown }).id;
  return typeof id === 'string' && id ? id : null;
}

function compactSceneElements(elements: unknown[]): unknown[] {
  const orderedIds: string[] = [];
  const byId = new Map<string, unknown>();
  const anonymous: unknown[] = [];

  for (const element of elements) {
    const id = sceneElementId(element);
    if (!id) {
      anonymous.push(element);
      continue;
    }
    if (!byId.has(id)) {
      orderedIds.push(id);
    }
    byId.set(id, element);
  }

  return [
    ...orderedIds.map((id) => byId.get(id)).filter((element): element is unknown => element !== undefined),
    ...anonymous,
  ];
}

export function normalizeWhiteboardScene(value: unknown): WhiteboardScene {
  if (!value || typeof value !== 'object') {
    return { elements: [], appState: {}, files: {} };
  }
  const scene = value as Record<string, unknown>;
  return {
    ...scene,
    elements: compactSceneElements(Array.isArray(scene.elements) ? scene.elements : []),
    appState: scene.appState && typeof scene.appState === 'object'
      ? scene.appState as Record<string, unknown>
      : {},
    files: scene.files && typeof scene.files === 'object'
      ? scene.files as Record<string, unknown>
      : {},
  };
}

export function getWhiteboardItemPrimaryContainerId(
  item: Pick<WhiteboardHubItem, 'primary_container'>,
  app?: string,
  type?: string,
): string | null {
  const container = item.primary_container;
  if (!container) return null;
  if (app && container.app !== app) return null;
  if (type && container.type !== type) return null;
  return container.id;
}

export function getWhiteboardItemPrimaryContainerSortOrder(
  item: Pick<WhiteboardHubItem, 'containers' | 'primary_container'>,
): number {
  return item.primary_container?.sort_order ?? item.containers[0]?.sort_order ?? 0;
}

export function listWhiteboardHub(
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
): Promise<WhiteboardHubResponse> {
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
  return request<WhiteboardHubResponse>(`/api/v1/whiteboard/hub?${qs}`, token, {}, workspaceSlug);
}

export function createWhiteboard(
  token: string,
  payload: {
    title: string;
    scene?: WhiteboardScene | null;
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
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    '/api/v1/whiteboard/items',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function getWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    `/api/v1/whiteboard/items/${itemId}`,
    token,
    {},
    workspaceSlug,
  );
}

export function getSharedWhiteboard(
  token: string,
  shareToken: string,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    `/api/v1/whiteboard/shared-links/${shareToken}/item`,
    token,
  );
}

export function updateWhiteboard(
  token: string,
  itemId: string,
  payload: {
    title?: string;
    scene?: WhiteboardScene | null;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    `/api/v1/whiteboard/items/${itemId}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function updateSharedWhiteboard(
  token: string,
  shareToken: string,
  payload: {
    title?: string;
    scene?: WhiteboardScene | null;
  },
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    `/api/v1/whiteboard/shared-links/${shareToken}/item`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function getWhiteboardCollabSession(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardCollabSession> {
  return request<WhiteboardCollabSession>(
    `/api/v1/whiteboard/collab/items/${itemId}/session`,
    token,
    {},
    workspaceSlug,
  );
}

export function saveWhiteboardCollabSnapshot(
  token: string,
  itemId: string,
  payload: {
    scene?: WhiteboardScene | null;
    yjs_state?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<WhiteboardCollabSnapshotResponse> {
  return request<WhiteboardCollabSnapshotResponse>(
    `/api/v1/whiteboard/collab/items/${itemId}/snapshot`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `/api/v1/whiteboard/items/${itemId}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function permanentlyDeleteWhiteboard(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `/api/v1/whiteboard/items/${itemId}/permanent`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function toggleWhiteboardFavorite(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(
    `/api/v1/whiteboard/items/${itemId}/favorite`,
    token,
    { method: 'PATCH' },
    workspaceSlug,
  );
}

export function recordWhiteboardView(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `/api/v1/whiteboard/items/${itemId}/view`,
    token,
    { method: 'POST' },
    workspaceSlug,
  );
}

export function recordSharedWhiteboardView(
  token: string,
  shareToken: string,
): Promise<void> {
  return request<void>(
    `/api/v1/whiteboard/shared-links/${shareToken}/view`,
    token,
    { method: 'POST' },
  );
}

export function getWhiteboardContextSlot(
  token: string,
  context: { app: string; type: string; id: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardContextSlotResponse> {
  const qs = new URLSearchParams(context);
  return request<WhiteboardContextSlotResponse>(
    `/api/v1/whiteboard/contexts/slot?${qs}`,
    token,
    {},
    workspaceSlug,
  );
}

export function createWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; title?: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    '/api/v1/whiteboard/contexts/slot',
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function attachWhiteboardContextSlot(
  token: string,
  payload: { app: string; type: string; id: string; whiteboard_id: string },
  workspaceSlug?: string | null,
): Promise<WhiteboardDetail> {
  return request<WhiteboardDetail>(
    '/api/v1/whiteboard/contexts/slot',
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function detachWhiteboardContextSlot(
  token: string,
  context: { app: string; type: string; id: string },
  workspaceSlug?: string | null,
): Promise<void> {
  const qs = new URLSearchParams(context);
  return request<void>(
    `/api/v1/whiteboard/contexts/slot?${qs}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function listWhiteboardShareableUsers(
  token: string,
  q = '',
  workspaceSlug?: string | null,
): Promise<ShareableUserItem[]> {
  const qs = new URLSearchParams();
  if (q) qs.set('q', q);
  return request<ShareableUserItem[]>(
    `/api/v1/whiteboard/shareable-users?${qs}`,
    token,
    {},
    workspaceSlug,
  );
}

export function getWhiteboardSharing(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    `/api/v1/whiteboard/items/${itemId}/sharing`,
    token,
    {},
    workspaceSlug,
  );
}

export function upsertWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
  accessLevel: 'read' | 'edit',
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    `/api/v1/whiteboard/items/${itemId}/sharing/users/${userId}`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify({ access_level: accessLevel }),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboardUserShare(
  token: string,
  itemId: string,
  userId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    `/api/v1/whiteboard/items/${itemId}/sharing/users/${userId}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function upsertWhiteboardLinkShare(
  token: string,
  itemId: string,
  payload: { access_level: 'read' | 'edit'; active?: boolean; regenerate_token?: boolean },
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    `/api/v1/whiteboard/items/${itemId}/sharing/link`,
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function deleteWhiteboardLinkShare(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<WhiteboardSharingResponse> {
  return request<WhiteboardSharingResponse>(
    `/api/v1/whiteboard/items/${itemId}/sharing/link`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function resolveWhiteboardSharedLink(
  token: string,
  shareToken: string,
): Promise<ResolveWhiteboardSharedLinkResponse> {
  return request<ResolveWhiteboardSharedLinkResponse>(
    `/api/v1/whiteboard/shared-links/${shareToken}`,
    token,
  );
}
