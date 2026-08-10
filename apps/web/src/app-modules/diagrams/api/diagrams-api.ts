import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type DiagramHubView = 'all' | 'mine' | 'archived';
export type DiagramSortBy = 'updated_at' | 'created_at' | 'title';
export type DiagramSortDir = 'asc' | 'desc';
export type DiagramVisibility = 'personal' | 'workspace';

export interface DiagramItem {
  id: string;
  workspace_id: string;
  title: string;
  visibility: DiagramVisibility;
  version: number;
  created_by_id: string;
  created_by_name: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  preview_available: boolean;
  preview_url: string | null;
  can_edit: boolean;
  can_manage: boolean;
}

export interface DiagramDetail extends DiagramItem {
  xml: string;
}

export interface DiagramHubResponse {
  items: DiagramItem[];
  view: DiagramHubView;
  page: number;
  page_size: number;
  total: number;
}

export interface DiagramHubParams {
  view?: DiagramHubView;
  q?: string;
  sort_by?: DiagramSortBy;
  sort_dir?: DiagramSortDir;
  page?: number;
  page_size?: number;
}

export class DiagramsApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const API_BASE = '/api/v1/diagrams';

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  workspaceSlug?: string | null,
): Promise<T> {
  try {
    return await apiFetchJson<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      init,
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new DiagramsApiError(error.status, error.message);
    }
    throw error;
  }
}

function withQuery(path: string, params: DiagramHubParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as Array<
    [string, string | number | undefined]
  >) {
    if (value === undefined || value === '') continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function listDiagramsHub(
  token: string,
  params: DiagramHubParams = {},
  workspaceSlug?: string | null,
): Promise<DiagramHubResponse> {
  return request<DiagramHubResponse>(
    withQuery(`${API_BASE}/hub`, params),
    token,
    {},
    workspaceSlug,
  );
}

export function createDiagram(
  token: string,
  payload: {
    title: string;
    visibility?: DiagramVisibility;
    xml?: string;
    preview_png_data_url?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<DiagramDetail> {
  return request<DiagramDetail>(
    `${API_BASE}/items`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function getDiagram(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<DiagramDetail> {
  return request<DiagramDetail>(
    `${API_BASE}/items/${encodeURIComponent(itemId)}`,
    token,
    {},
    workspaceSlug,
  );
}

export function updateDiagram(
  token: string,
  itemId: string,
  payload: {
    version: number;
    title?: string;
    visibility?: DiagramVisibility;
    xml?: string;
    preview_png_data_url?: string | null;
  },
  workspaceSlug?: string | null,
): Promise<DiagramDetail> {
  return request<DiagramDetail>(
    `${API_BASE}/items/${encodeURIComponent(itemId)}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    workspaceSlug,
  );
}

export function archiveDiagram(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<void> {
  return request<void>(
    `${API_BASE}/items/${encodeURIComponent(itemId)}`,
    token,
    { method: 'DELETE' },
    workspaceSlug,
  );
}

export function restoreDiagram(
  token: string,
  itemId: string,
  workspaceSlug?: string | null,
): Promise<DiagramDetail> {
  return request<DiagramDetail>(
    `${API_BASE}/items/${encodeURIComponent(itemId)}/restore`,
    token,
    { method: 'POST' },
    workspaceSlug,
  );
}

export async function fetchDiagramPreviewUrl(
  token: string,
  item: DiagramItem,
  workspaceSlug?: string | null,
): Promise<string | null> {
  if (!item.preview_url) return null;
  const response = await fetch(
    rewriteWorkspaceApiPath(item.preview_url, workspaceSlug),
    {
      headers: jsonHeaders(token),
      cache: 'no-store',
    },
  );
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new DiagramsApiError(
      response.status,
      `Request failed with ${response.status}.`,
    );
  }
  return URL.createObjectURL(await response.blob());
}
