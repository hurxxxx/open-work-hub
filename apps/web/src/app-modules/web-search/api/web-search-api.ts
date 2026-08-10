import { jsonHeaders } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export interface WebSearchCitation {
  url: string;
  title: string;
  cited_text: string | null;
}

export interface WebSearchUsage {
  input_tokens: number | null;
  output_tokens: number | null;
  web_search_requests: number | null;
}

export interface WebSearchAnswerResponse {
  query: string;
  answer: string;
  citations: WebSearchCitation[];
  model: string;
  usage: WebSearchUsage | null;
}

export type WebSearchStreamEvent =
  | {
      type: 'conversation_attached';
      data: { conversation_id: string; display_question?: string };
    }
  | {
      type: 'content_delta';
      data: { text: string };
    }
  | {
      type: 'web_search_response';
      data: { response: WebSearchAnswerResponse };
    }
  | {
      type: 'done';
      data: { finish_reason: string };
    }
  | {
      type: 'error';
      data: { code: string; message: string; retryable: boolean };
    };

export class WebSearchApiError extends Error {
  status: number;
  code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}

export async function streamWebSearch(args: {
  token: string;
  workspaceSlug: string | null;
  question: string;
  conversationId?: string | null;
  apiPrefix?: string;
  errorI18nKey?: string;
  maxUses?: number;
  signal: AbortSignal;
}): Promise<Response> {
  const apiPrefix = args.apiPrefix ?? '/api/v1/web-search';
  const errorI18nKey = args.errorI18nKey ?? 'ai.webSearch';
  let response: Response;
  try {
    response = await fetch(
      rewriteWorkspaceApiPath(`${apiPrefix}/ask/stream`, args.workspaceSlug),
      {
        method: 'POST',
        signal: args.signal,
        cache: 'no-store',
        headers: {
          ...jsonHeaders(args.token),
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: args.question,
          max_uses: args.maxUses ?? 5,
          conversation_id: args.conversationId || undefined,
        }),
      },
    );
  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      throw error;
    }
    throw new WebSearchApiError(
      0,
      i18n.t(`apps:${errorI18nKey}.errors.connect`),
    );
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new WebSearchApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t(`apps:${errorI18nKey}.errors.requestFailed`, {
          status: response.status,
        }),
      ),
    );
  }
  if (!response.body) {
    throw new WebSearchApiError(
      0,
      i18n.t(`apps:${errorI18nKey}.errors.connect`),
    );
  }
  return response;
}
