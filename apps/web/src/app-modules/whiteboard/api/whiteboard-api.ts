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
export type WhiteboardHubItem = Omit<
  ApiSchema<'WhiteboardHubItem'>,
  'last_viewed_at' | 'primary_container' | 'source_deeplink' | 'source_ref' | 'trashed_at'
> & {
  source_ref: string | null;
  primary_container: WhiteboardPrimaryContainer | null;
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

export function normalizeWhiteboardScene(value: unknown): WhiteboardScene {
  if (!value || typeof value !== 'object') {
    return { elements: [], appState: {}, files: {} };
  }
  const scene = value as Record<string, unknown>;
  return {
    ...scene,
    elements: Array.isArray(scene.elements) ? scene.elements : [],
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
  item: Pick<WhiteboardHubItem, 'primary_container'>,
): number {
  return item.primary_container?.sort_order ?? 0;
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
