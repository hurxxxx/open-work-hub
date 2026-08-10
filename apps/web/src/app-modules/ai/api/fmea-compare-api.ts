import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type FmeaAiMode = 'summary' | 'improvement' | 'missing';

export interface FmeaItem {
  item: string;
  failure_mode: string;
  failure_effect: string;
  failure_cause: string;
  classification: string;
  severity: string;
  occurrence: string;
  detection: string;
  rpn: string;
  prevention: string;
  detection_method: string;
  recommended_action: string;
  action_result: string;
  action_date: string;
}

export interface FmeaStats {
  total: number;
  avg_rpn: number;
  max_rpn: number;
  high_risk_count: number;
  no_action_count: number;
}

export interface FmeaAnalyzeResult {
  filename: string;
  total: number;
  stats: FmeaStats;
  items: FmeaItem[];
  high_risk: FmeaItem[];
  no_action: FmeaItem[];
}

export interface FmeaAiAnalyzeResult {
  result: string;
  mode: string;
}

export interface FmeaCompareResult {
  comparison: string;
  file_a: { filename: string; count: number };
  file_b: { filename: string; count: number };
}

export class FmeaCompareApiError extends Error {
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

async function fmeaRequest<T>(
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
        new FmeaCompareApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.fmeaCompare.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof FmeaCompareApiError) {
      throw error;
    }
    throw new FmeaCompareApiError(0, i18n.t('apps:ai.fmeaCompare.errors.connect'));
  }
}

export function analyzeFmea(args: {
  token: string;
  workspaceSlug: string | null;
  file: File;
}): Promise<FmeaAnalyzeResult> {
  const form = new FormData();
  form.append('file', args.file);
  return fmeaRequest<FmeaAnalyzeResult>('/api/v1/fmea-compare/analyze', args.token, args.workspaceSlug, {
    method: 'POST',
    body: form,
  });
}

export function aiAnalyzeFmea(args: {
  token: string;
  workspaceSlug: string | null;
  items: FmeaItem[];
  mode: FmeaAiMode;
}): Promise<FmeaAiAnalyzeResult> {
  return fmeaRequest<FmeaAiAnalyzeResult>('/api/v1/fmea-compare/ai-analyze', args.token, args.workspaceSlug, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: args.items.slice(0, 30), mode: args.mode }),
  });
}

export function compareFmea(args: {
  token: string;
  workspaceSlug: string | null;
  fileA: File;
  fileB: File;
}): Promise<FmeaCompareResult> {
  const form = new FormData();
  form.append('file_a', args.fileA);
  form.append('file_b', args.fileB);
  return fmeaRequest<FmeaCompareResult>('/api/v1/fmea-compare/compare', args.token, args.workspaceSlug, {
    method: 'POST',
    body: form,
  });
}
