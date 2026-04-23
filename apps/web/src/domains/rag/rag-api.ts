import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

type FilterScalar = string | number | boolean;
type FilterValue = FilterScalar | FilterScalar[];

export const RAG_QUERY_DEFAULT_ANSWER_MODE = 'grounded-answer' as const;
export const RAG_QUERY_DEFAULT_TOP_K = 8;

export interface RagQueryFilters {
  resource_type?: string;
  resource_id?: string;
  visibility_refs_contains?: string;
  metadata?: Record<string, FilterValue>;
}

export interface RagSourceDescriptor {
  source_kind: string;
  resource_type: string;
  label: string;
  app_id: string;
}

export interface RagSourceListResponse {
  sources: RagSourceDescriptor[];
}

export interface RagGroundedCitation {
  resource_id: string;
  source_kind: string;
  quote: string;
  locator: string | null;
}

export interface RagGroundedAnswer {
  text: string;
  citations: RagGroundedCitation[];
  unsupported_claims: string[];
  sources_used: string[];
}

export interface RagQueryHit {
  source_kind: string;
  resource_type: string;
  resource_id: string;
  workspace_id: string;
  title: string | null;
  summary: string | null;
  score: number;
  citation: string | null;
  owner_label: string | null;
  acl_summary: string[];
  origin_ref: string | null;
  metadata: Record<string, unknown>;
}

export interface RagQueryResponse {
  query: string;
  answer_mode: 'search-only' | 'grounded-answer';
  hits: RagQueryHit[];
  grounded_answer: RagGroundedAnswer | null;
  sources_used: string[];
  query_profile: Record<string, unknown>;
  trace_id: string | null;
  latency_ms: number;
}

export interface RagQueryPayload {
  query: string;
  answer_mode?: 'search-only' | 'grounded-answer';
  source_kinds?: string[];
  filters?: RagQueryFilters;
  top_k?: number;
  include_binary_hits?: boolean;
}

export class RagApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function listWorkspaceRagSources(
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<RagSourceListResponse> {
  const response = await fetch(
    rewriteWorkspaceApiPath('/api/v1/rag/sources', workspaceSlug),
    {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal: options?.signal,
    },
  );

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new RagApiError(
      response.status,
      extractErrorMessage(payload, response.status, '검색 source 목록을 불러오지 못했습니다.'),
    );
  }

  return payload as RagSourceListResponse;
}

export async function queryWorkspaceRag(
  payload: RagQueryPayload,
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<RagQueryResponse> {
  const response = await fetch(
    rewriteWorkspaceApiPath('/api/v1/rag/query', workspaceSlug),
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
        answer_mode: payload.answer_mode ?? RAG_QUERY_DEFAULT_ANSWER_MODE,
        source_kinds: payload.source_kinds ?? [],
        filters: payload.filters ?? {},
        top_k: payload.top_k ?? RAG_QUERY_DEFAULT_TOP_K,
        include_binary_hits: payload.include_binary_hits ?? false,
      }),
      signal: options?.signal,
    },
  );

  const result = await response.json().catch(() => null);
  if (!response.ok) {
    throw new RagApiError(
      response.status,
      extractErrorMessage(result, response.status, '검색 결과를 불러오지 못했습니다.'),
    );
  }

  return result as RagQueryResponse;
}

function extractErrorMessage(
  payload: unknown,
  status: number,
  fallback: string,
): string {
  if (status === 401) {
    return '세션이 만료되었습니다. 다시 로그인해주세요.';
  }
  if (
    payload
    && typeof payload === 'object'
    && 'detail' in payload
  ) {
    const detail = payload.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (!item || typeof item !== 'object') {
            return null;
          }
          const entry = item as {
            loc?: unknown;
            msg?: unknown;
          };
          const message = typeof entry.msg === 'string' ? entry.msg : null;
          const location = Array.isArray(entry.loc)
            ? entry.loc
              .map((part) => String(part))
              .join(' > ')
            : null;
          if (!message) {
            return null;
          }
          return location ? `${location}: ${message}` : message;
        })
        .filter((item): item is string => Boolean(item));
      if (messages.length > 0) {
        return messages.join('\n');
      }
    }
  }
  return `${fallback} (${status})`;
}
