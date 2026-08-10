import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type DraftGenerateRequest = ApiSchema<'DraftGenerateRequest'>;
export type MailGenerateRequest = ApiSchema<'MailGenerateRequest'>;
export type TranslateRequest = ApiSchema<'TranslateRequest'>;
export type DocumentDownloadRequest = ApiSchema<'DocumentDownloadRequest'>;
export type WritingResult = ApiSchema<'WritingResult'>;
export type WritingLang = DraftGenerateRequest['lang'];
export type DraftType = DraftGenerateRequest['type'];
export type MailTone = MailGenerateRequest['tone'];
export type TranslateTargetLang = TranslateRequest['target_lang'];
export type DownloadFormat = DocumentDownloadRequest['format'];

export class WritingAssistantApiError extends Error {
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

async function writingRequest<T>(
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
        new WritingAssistantApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.writingAssistant.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof WritingAssistantApiError) {
      throw error;
    }
    throw new WritingAssistantApiError(
      0,
      i18n.t('apps:ai.writingAssistant.errors.connect'),
    );
  }
}

export function generateDraft(args: {
  token: string;
  workspaceSlug: string | null;
  text: string;
  type: DraftType;
  lang: WritingLang;
}): Promise<WritingResult> {
  const body: DraftGenerateRequest = {
    text: args.text,
    type: args.type,
    lang: args.lang,
  };
  return writingRequest<WritingResult>(
    '/api/v1/writing-assistant/draft/generate',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

export function translateWriting(args: {
  token: string;
  workspaceSlug: string | null;
  source: string;
  targetLang: TranslateTargetLang;
}): Promise<WritingResult> {
  const body: TranslateRequest = {
    source: args.source,
    target_lang: args.targetLang,
  };
  return writingRequest<WritingResult>(
    '/api/v1/writing-assistant/translate',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

export function generateMail(args: {
  token: string;
  workspaceSlug: string | null;
  intent: string;
  originalMail: string;
  tone: MailTone;
  lang: WritingLang;
}): Promise<WritingResult> {
  const body: MailGenerateRequest = {
    intent: args.intent,
    original_mail: args.originalMail,
    tone: args.tone,
    lang: args.lang,
  };
  return writingRequest<WritingResult>(
    '/api/v1/writing-assistant/mail/generate',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

/**
 * Generates a TXT/DOCX/PDF on the server and triggers a browser download.
 * The download endpoint returns a binary file (not JSON), so it bypasses the
 * JSON client and reads the response as a blob.
 */
export async function downloadDocument(args: {
  token: string;
  workspaceSlug: string | null;
  content: string;
  format: DownloadFormat;
  filename: string;
}): Promise<void> {
  const body: DocumentDownloadRequest = {
    content: args.content,
    format: args.format,
    filename: args.filename,
  };
  let response: Response;
  try {
    response = await fetch(
      rewriteWorkspaceApiPath(
        '/api/v1/writing-assistant/download',
        args.workspaceSlug,
      ),
      {
        method: 'POST',
        headers: jsonHeaders(args.token, {
          'Content-Type': 'application/json',
        }),
        cache: 'no-store',
        body: JSON.stringify(body),
      },
    );
  } catch {
    throw new WritingAssistantApiError(
      0,
      i18n.t('apps:ai.writingAssistant.errors.connect'),
    );
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new WritingAssistantApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.writingAssistant.errors.downloadFailed'),
      ),
    );
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${args.filename}.${args.format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
