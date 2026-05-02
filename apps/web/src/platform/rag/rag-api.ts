import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export const RAG_QUERY_DEFAULT_ANSWER_MODE = 'grounded-answer' as const;
export const RAG_QUERY_DEFAULT_TOP_K = 8;

export type RagQueryFilters = ApiSchema<'RagQueryFilters'>;
export type RagSourceDescriptor = ApiSchema<'RagSourceDescriptor'>;
export type RagSourceListResponse = ApiSchema<'RagSourceListResponse'>;
export type RagGroundedCitation = ApiSchema<'RagGroundedCitation'>;
export type RagGroundedAnswer = ApiSchema<'RagGroundedAnswer'>;
export type RagQueryHit = ApiSchema<'RagQueryHit'>;
export type RagQueryResponse = ApiSchema<'RagQueryResponse'>;
export type RagQueryPayload = Omit<
  ApiSchema<'RagQueryRestRequest'>,
  'answer_mode' | 'include_binary_hits' | 'source_kinds' | 'top_k'
> & {
  answer_mode?: ApiSchema<'RagAnswerMode'>;
  source_kinds?: string[];
  top_k?: number;
  include_binary_hits?: boolean;
};

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
  try {
    return await apiFetchJson<RagSourceListResponse>(
      rewriteWorkspaceApiPath('/api/v1/rag/sources', workspaceSlug),
      token,
      {
        signal: options?.signal,
      },
    );
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new RagApiError(
        error.status,
        extractErrorMessage(error.payload, error.status, i18n.t('apps:ai.search.sourcesLoadFailed')),
      );
    }
    throw error;
  }
}

export async function queryWorkspaceRag(
  payload: RagQueryPayload,
  token: string,
  workspaceSlug?: string | null,
  options?: { signal?: AbortSignal },
): Promise<RagQueryResponse> {
  try {
    return await apiFetchJson<RagQueryResponse>(
      rewriteWorkspaceApiPath('/api/v1/rag/query', workspaceSlug),
      token,
      {
        method: 'POST',
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
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new RagApiError(
        error.status,
        extractErrorMessage(error.payload, error.status, i18n.t('apps:ai.search.loadFailed')),
      );
    }
    throw error;
  }
}

function extractErrorMessage(
  payload: unknown,
  status: number,
  fallback: string,
): string {
  if (status === 401) {
    return i18n.t('apps:ai.search.sessionExpired');
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
