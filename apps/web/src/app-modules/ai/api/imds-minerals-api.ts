import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export interface ImdsGenerateMeta {
  sheet: string;
  car: string;
  endName: string;
  oem: string;
  dcc: string;
}

export type ImdsAnalyzeResult = ApiSchema<'ImdsAnalyzeResult'>;
export type ImdsMatchResult = ApiSchema<'ImdsMatchResult'>;

export class ImdsMineralsApiError extends Error {
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
      typeof (detail as { message?: unknown }).message === 'string'
    ) {
      return (detail as { message: string }).message;
    }
  }
  return fallback;
}

async function imdsRequest<T>(
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
        new ImdsMineralsApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.imdsMinerals.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof ImdsMineralsApiError) {
      throw error;
    }
    throw new ImdsMineralsApiError(
      0,
      i18n.t('apps:ai.imdsMinerals.errors.connect'),
    );
  }
}

export async function analyzeImds(args: {
  token: string;
  workspaceSlug: string | null;
  file: File;
}): Promise<ImdsAnalyzeResult> {
  const form = new FormData();
  form.append('file', args.file);
  return imdsRequest<ImdsAnalyzeResult>(
    '/api/v1/imds-minerals/analyze',
    args.token,
    args.workspaceSlug,
    { method: 'POST', body: form },
  );
}

export async function matchImdsMetadata(args: {
  token: string;
  workspaceSlug: string | null;
  listFile: File;
  oem: string;
}): Promise<ImdsMatchResult> {
  const form = new FormData();
  form.append('list_file', args.listFile);
  form.append('oem', args.oem);
  return imdsRequest<ImdsMatchResult>(
    '/api/v1/imds-minerals/match',
    args.token,
    args.workspaceSlug,
    { method: 'POST', body: form },
  );
}

export async function generateImds(args: {
  token: string;
  workspaceSlug: string | null;
  pdf: File;
  template: File;
  meta: ImdsGenerateMeta;
}): Promise<Blob> {
  const form = new FormData();
  form.append('pdf', args.pdf);
  form.append('template', args.template);
  form.append('sheet', args.meta.sheet);
  form.append('car', args.meta.car);
  form.append('end_name', args.meta.endName);
  form.append('oem', args.meta.oem);
  form.append('dcc', args.meta.dcc);
  let response: Response;
  try {
    response = await fetch(
      rewriteWorkspaceApiPath(
        '/api/v1/imds-minerals/generate',
        args.workspaceSlug,
      ),
      {
        method: 'POST',
        headers: jsonHeaders(args.token),
        body: form,
        cache: 'no-store',
      },
    );
  } catch {
    throw new ImdsMineralsApiError(
      0,
      i18n.t('apps:ai.imdsMinerals.errors.connect'),
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ImdsMineralsApiError(
      response.status,
      resolveErrorMessage(
        payload,
        i18n.t('apps:ai.imdsMinerals.errors.requestFailed', {
          status: response.status,
        }),
      ),
    );
  }
  return response.blob();
}
