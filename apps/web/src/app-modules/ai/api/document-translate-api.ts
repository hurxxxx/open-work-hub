import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type DocMode = 'translate' | 'summarize' | 'extract';
export type SummaryLevel = 'brief' | 'detailed';
export type TargetLang = 'ko' | 'en' | 'zh' | 'ja' | 'es' | 'de';

export interface DocProcessResult {
  result: string;
  mode: DocMode;
  char_count: number;
}

export class DocumentTranslateApiError extends Error {
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
      detail
      && typeof detail === 'object'
      && 'message' in detail
      && typeof detail.message === 'string'
    ) {
      return detail.message;
    }
  }
  return fallback;
}

async function docRequest<T>(
  path: string,
  token: string,
  workspaceSlug: string | null,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      rewriteWorkspaceApiPath(path, workspaceSlug),
      token,
      init,
      (error) =>
        new DocumentTranslateApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.documentTranslate.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof DocumentTranslateApiError) {
      throw error;
    }
    throw new DocumentTranslateApiError(0, i18n.t('apps:ai.documentTranslate.errors.connect'));
  }
}

export function processDocumentFile(args: {
  token: string;
  workspaceSlug: string | null;
  file: File;
  mode: DocMode;
  targetLang: TargetLang;
  summaryLevel: SummaryLevel;
}): Promise<DocProcessResult> {
  const form = new FormData();
  form.append('file', args.file);
  form.append('mode', args.mode);
  form.append('target_lang', args.targetLang);
  form.append('summary_level', args.summaryLevel);
  return docRequest<DocProcessResult>(
    '/api/v1/document-translate/process',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      body: form,
    },
  );
}

export function processDocumentText(args: {
  token: string;
  workspaceSlug: string | null;
  text: string;
  mode: DocMode;
  targetLang: TargetLang;
  summaryLevel: SummaryLevel;
}): Promise<DocProcessResult> {
  return docRequest<DocProcessResult>(
    '/api/v1/document-translate/process-text',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: args.text,
        mode: args.mode,
        target_lang: args.targetLang,
        summary_level: args.summaryLevel,
      }),
    },
  );
}
