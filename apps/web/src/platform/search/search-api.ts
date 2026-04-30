import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type KeywordSearchEntityType = 'doc' | 'meeting' | 'pms_issue' | 'planner_event';

export interface KeywordSearchHighlight {
  start: number;
  end: number;
}

export interface KeywordSearchSnippet {
  text: string;
  highlights: KeywordSearchHighlight[];
}

export interface KeywordSearchPerson {
  role: string;
  user_id: string;
  label: string;
}

export interface KeywordSearchContainer {
  type: string;
  id: string;
  label: string;
}

export interface KeywordSearchHit {
  entity_type: KeywordSearchEntityType;
  entity_id: string;
  workspace_id: string;
  title: string;
  summary: string;
  snippet: KeywordSearchSnippet;
  score: number;
  status: string | null;
  status_label: string | null;
  visibility: string | null;
  updated_at: string;
  created_at: string;
  date_markers: Record<string, unknown>;
  people: KeywordSearchPerson[];
  containers: KeywordSearchContainer[];
  deep_link: string;
  preview_url: string | null;
  metadata: Record<string, unknown>;
}

export interface KeywordSearchFacetValue {
  value: string;
  label: string;
  count: number;
}

export interface KeywordSearchStatusFacetValue extends KeywordSearchFacetValue {
  entity_type: KeywordSearchEntityType;
}

export interface KeywordSearchContainerFacetValue {
  type: string;
  id: string;
  label: string;
  count: number;
}

export interface KeywordSearchFacets {
  entity_types: KeywordSearchFacetValue[];
  status: KeywordSearchStatusFacetValue[];
  containers: KeywordSearchContainerFacetValue[];
}

export interface KeywordSearchResponse {
  query: string;
  hits: KeywordSearchHit[];
  facets: KeywordSearchFacets;
  total: number;
  has_more: boolean;
  next_offset: number | null;
  trace_id: string | null;
}

export interface KeywordSearchPayload {
  workspace_id?: string | null;
  query: string;
  entity_types?: KeywordSearchEntityType[];
  people?: {
    role: 'any' | 'owner' | 'assignee' | 'participant';
    user_ids: string[];
  };
  status_by_type?: Partial<Record<KeywordSearchEntityType, string[]>>;
  date_filters?: Array<{
    field: 'updated_at' | 'created_at' | 'due_date' | 'start_date' | 'event_start_at';
    from?: string | null;
    to?: string | null;
  }>;
  container_refs?: Array<{
    type: string;
    id: string;
  }>;
  sort?: {
    field: 'relevance' | 'updated_at' | 'created_at';
    direction: 'desc' | 'asc';
  };
  limit?: number;
  offset?: number;
}

export class SearchApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function queryWorkspaceKeywordSearch(
  payload: KeywordSearchPayload,
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<KeywordSearchResponse> {
  const response = await fetch(
    rewriteWorkspaceApiPath('/api/v1/search/query', workspaceSlug),
    {
      method: 'POST',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: payload.query,
        workspace_id: payload.workspace_id ?? null,
        entity_types: payload.entity_types ?? [],
        people: payload.people ?? { role: 'any', user_ids: [] },
        status_by_type: payload.status_by_type ?? {},
        date_filters: payload.date_filters ?? [],
        container_refs: payload.container_refs ?? [],
        sort: payload.sort ?? { field: 'relevance', direction: 'desc' },
        limit: payload.limit ?? 20,
        offset: payload.offset ?? 0,
      }),
      signal: options?.signal,
    },
  );

  const result = await response.json().catch(() => null);
  if (!response.ok) {
    throw new SearchApiError(response.status, extractErrorMessage(result, response.status));
  }
  return result as KeywordSearchResponse;
}

function extractErrorMessage(payload: unknown, status: number): string {
  if (status === 401) {
    return '세션이 만료되었습니다. 다시 로그인해주세요.';
  }
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  return `검색 결과를 불러오지 못했습니다. (${status})`;
}
