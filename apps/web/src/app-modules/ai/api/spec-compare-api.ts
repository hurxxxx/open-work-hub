import {
  apiFetchJsonWithMappedError,
  jsonHeaders,
} from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type SpecCompareReportFormat = 'docx' | 'pdf';

export type SpecCompareJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type SpecCompareRowStatus = 'same' | 'different' | 'base_only' | 'target_only' | 'unknown';

export interface SpecCompareFile {
  name: string;
  mime_type: string;
  size_bytes: number;
}

export interface SpecCompareJob {
  id: string;
  workspace_id: string;
  owner_id: string;
  title: string;
  status: SpecCompareJobStatus;
  progress: number;
  status_message: string;
  failure_reason: string | null;
  base_file: SpecCompareFile;
  target_file: SpecCompareFile;
  result_summary: Record<string, unknown> | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SpecCompareRow {
  spec_name: string;
  base_value: string;
  target_value: string;
  status: SpecCompareRowStatus;
  summary: string;
  base_evidence_ids: string[];
  target_evidence_ids: string[];
}

export interface SpecCompareSpecItem {
  item_id: string;
  document_id: string;
  category: string;
  item_name: string;
  value: string;
  unit: string;
  condition: string;
  evidence_id: string;
  locator_label: string;
  section_path: string;
  source_text: string;
  confidence: number;
  extraction_method: string;
}

export interface SpecCompareResult {
  job: SpecCompareJob;
  report_markdown: string;
  comparison_rows: SpecCompareRow[];
  evidence_blocks: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
  spec_items?: {
    base?: SpecCompareSpecItem[];
    target?: SpecCompareSpecItem[];
  };
}

export class SpecCompareApiError extends Error {
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

async function specCompareRequest<T>(
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
        new SpecCompareApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.specCompare.errors.requestFailed', {
              status: error.status,
            }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof SpecCompareApiError) {
      throw error;
    }
    throw new SpecCompareApiError(0, i18n.t('apps:ai.specCompare.errors.connect'));
  }
}

export function createSpecCompareJob(args: {
  token: string;
  workspaceSlug: string | null;
  baseFile: File;
  targetFile: File;
  title?: string;
}): Promise<SpecCompareJob> {
  const form = new FormData();
  form.append('base_file', args.baseFile);
  form.append('target_file', args.targetFile);
  form.append('title', args.title ?? '');
  return specCompareRequest<SpecCompareJob>(
    '/api/v1/spec-compare/jobs',
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      body: form,
    },
  );
}

export function listSpecCompareJobs(args: {
  token: string;
  workspaceSlug: string | null;
  limit?: number;
}): Promise<{ items: SpecCompareJob[] }> {
  const limit = args.limit ?? 20;
  return specCompareRequest<{ items: SpecCompareJob[] }>(
    `/api/v1/spec-compare/jobs?limit=${encodeURIComponent(String(limit))}`,
    args.token,
    args.workspaceSlug,
  );
}

export async function fetchSpecCompareReport(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
  format: SpecCompareReportFormat;
}): Promise<Blob> {
  const path = rewriteWorkspaceApiPath(
    `/api/v1/spec-compare/jobs/${encodeURIComponent(args.jobId)}/report.${args.format}`,
    args.workspaceSlug,
  );
  let response: Response;
  try {
    response = await fetch(path, { headers: jsonHeaders(args.token), cache: 'no-store' });
  } catch {
    throw new SpecCompareApiError(0, i18n.t('apps:ai.specCompare.errors.connect'));
  }
  if (!response.ok) {
    throw new SpecCompareApiError(
      response.status,
      i18n.t('apps:ai.specCompare.errors.download'),
    );
  }
  return response.blob();
}

export function deleteSpecCompareJob(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<{ id: string; deleted: boolean }> {
  return specCompareRequest<{ id: string; deleted: boolean }>(
    `/api/v1/spec-compare/jobs/${encodeURIComponent(args.jobId)}`,
    args.token,
    args.workspaceSlug,
    { method: 'DELETE' },
  );
}

export function getSpecCompareJob(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<SpecCompareJob> {
  return specCompareRequest<SpecCompareJob>(
    `/api/v1/spec-compare/jobs/${encodeURIComponent(args.jobId)}`,
    args.token,
    args.workspaceSlug,
  );
}

export function getSpecCompareResult(args: {
  token: string;
  workspaceSlug: string | null;
  jobId: string;
}): Promise<SpecCompareResult> {
  return specCompareRequest<SpecCompareResult>(
    `/api/v1/spec-compare/jobs/${encodeURIComponent(args.jobId)}/result`,
    args.token,
    args.workspaceSlug,
  );
}
