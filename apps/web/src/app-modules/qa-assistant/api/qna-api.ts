import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';

export interface QnaGroundedCitation {
  resource_id: string;
  source_kind: string;
  quote: string;
  locator: string | null;
}

export interface QnaGroundedAnswer {
  text: string;
  citations: QnaGroundedCitation[];
  unsupported_claims: string[];
  sources_used: string[];
}

export interface QnaHit {
  source_kind: string;
  resource_type: string;
  resource_id: string;
  title: string | null;
  summary: string | null;
  excerpt: string | null;
  score: number;
}

export interface QnaAskResponse {
  query: string;
  answer_mode: string;
  hits: QnaHit[];
  grounded_answer: QnaGroundedAnswer | null;
  sources_used: string[];
  query_profile?: Record<string, unknown>;
  trace_id?: string | null;
  latency_ms?: number;
}

export type QnaStreamEvent =
  | {
      type: 'conversation_attached';
      data: { conversation_id: string };
    }
  | {
      type: 'content_delta';
      data: { text: string };
    }
  | {
      type: 'qna_response';
      data: { response: QnaAskResponse };
    }
  | {
      type: 'done';
      data: { finish_reason: string };
    }
  | {
      type: 'error';
      data: { code: string; message: string; retryable: boolean };
    };

export interface QnaDocument {
  id: string;
  kind: 'upload' | 'notice';
  title: string;
  category: string;
  author: string | null;
  posted_at: string | null;
  attachments: string[];
  char_count: number;
  rag_status: string;
  chunk_count: number;
  uploaded_by: string | null;
  indexed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface QnaDocumentDetail extends QnaDocument {
  body_text: string;
}

export class QnaApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof detail.message === 'string'
    ) {
      return detail.message;
    }
  }
  return fallback;
}

async function qnaRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      path,
      token,
      init,
      (error) =>
        new QnaApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.qaAssistant.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof QnaApiError) {
      throw error;
    }
    throw new QnaApiError(0, i18n.t('apps:ai.qaAssistant.errors.connect'));
  }
}

export function askQna(args: {
  token: string;
  question: string;
  conversationId?: string | null;
  workspaceSlug?: string | null;
  topK?: number;
}): Promise<QnaAskResponse> {
  return qnaRequest<QnaAskResponse>(
    '/api/v1/qna/ask',
    args.token,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: args.question,
        conversation_id: args.conversationId || undefined,
        workspace_key: args.workspaceSlug || undefined,
        top_k: args.topK ?? 20,
      }),
    },
  );
}

export async function streamQna(args: {
  token: string;
  question: string;
  conversationId?: string | null;
  workspaceSlug?: string | null;
  topK?: number;
  signal: AbortSignal;
}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch('/api/v1/qna/ask/stream', {
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
        conversation_id: args.conversationId || undefined,
        workspace_key: args.workspaceSlug || undefined,
        top_k: args.topK ?? 20,
      }),
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') {
      throw error;
    }
    throw new QnaApiError(0, i18n.t('apps:ai.qaAssistant.errors.connect'));
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new QnaApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.qaAssistant.errors.requestFailed', {
          status: response.status,
        }),
      ),
    );
  }
  if (!response.body) {
    throw new QnaApiError(0, i18n.t('apps:ai.qaAssistant.errors.connect'));
  }
  return response;
}

export function listQnaDocuments(args: {
  token: string;
}): Promise<{ documents: QnaDocument[] }> {
  return qnaRequest<{ documents: QnaDocument[] }>(
    '/api/v1/qna/documents',
    args.token,
  );
}

export function listQnaNotices(args: {
  token: string;
}): Promise<{ notices: QnaDocument[] }> {
  return qnaRequest<{ notices: QnaDocument[] }>(
    '/api/v1/qna/notices',
    args.token,
  );
}

export function getQnaDocument(args: {
  token: string;
  documentId: string;
}): Promise<QnaDocumentDetail> {
  return qnaRequest<QnaDocumentDetail>(
    `/api/v1/qna/documents/${encodeURIComponent(args.documentId)}`,
    args.token,
  );
}

export function uploadQnaDocument(args: {
  token: string;
  file: File;
  category?: string;
}): Promise<QnaDocument> {
  const form = new FormData();
  form.append('file', args.file);
  if (args.category) {
    form.append('category', args.category);
  }
  return qnaRequest<QnaDocument>(
    '/api/v1/qna/documents/upload',
    args.token,
    {
      method: 'POST',
      body: form,
    },
  );
}

export function deleteQnaDocument(args: {
  token: string;
  documentId: string;
}): Promise<void> {
  return qnaRequest<void>(
    `/api/v1/qna/documents/${encodeURIComponent(args.documentId)}`,
    args.token,
    { method: 'DELETE' },
  );
}

export function syncQnaBoard(args: {
  token: string;
}): Promise<{ queued: boolean }> {
  return qnaRequest<{ queued: boolean }>(
    '/api/v1/qna/board/sync',
    args.token,
    {
      method: 'POST',
    },
  );
}

export interface QnaFileBlob {
  blob: Blob;
  contentType: string;
  filename: string;
}

export async function fetchQnaFileBlob(args: {
  token: string;
  documentId: string;
  filename: string;
}): Promise<QnaFileBlob> {
  const path = `/api/v1/qna/documents/${encodeURIComponent(args.documentId)}/files/${encodeURIComponent(args.filename)}/download`;
  const response = await fetch(path, {
    headers: jsonHeaders(args.token),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new QnaApiError(
      response.status,
      i18n.t('apps:ai.qaAssistant.errors.downloadFailed'),
    );
  }
  const blob = await response.blob();
  const contentType =
    response.headers.get('Content-Type') ||
    blob.type ||
    'application/octet-stream';
  return {
    blob: blob.type ? blob : new Blob([blob], { type: contentType }),
    contentType,
    filename: args.filename,
  };
}

export async function downloadQnaFile(args: {
  token: string;
  documentId: string;
  filename: string;
}): Promise<void> {
  const file = await fetchQnaFileBlob(args);
  const url = URL.createObjectURL(file.blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
