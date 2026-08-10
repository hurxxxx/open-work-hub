import type { components } from '@open-alm/contracts/openapi';

import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

type PatentPriorArtSchemas = components['schemas'];

export type PatentPriorArtArtifact =
  PatentPriorArtSchemas['PatentPriorArtArtifactOut'];
export type PatentPriorArtCandidate =
  PatentPriorArtSchemas['PatentPriorArtCandidateOut'];
export type PatentPriorArtCategory =
  PatentPriorArtSchemas['PatentPriorArtCategoryOption'];
export type PatentPriorArtConfig =
  PatentPriorArtSchemas['PatentPriorArtConfigResponse'];
export type PatentPriorArtDeleteResult =
  PatentPriorArtSchemas['PatentPriorArtDeleteResponse'];
export type PatentPriorArtFileParseResult =
  PatentPriorArtSchemas['PatentPriorArtFileParseResponse'];
export type PatentPriorArtJob = PatentPriorArtSchemas['PatentPriorArtJobOut'];
export type PatentPriorArtFailureCode = NonNullable<
  PatentPriorArtJob['failure_code']
>;
export type PatentPriorArtJobCreateRequest =
  PatentPriorArtSchemas['PatentPriorArtJobCreateRequest'];
export type PatentPriorArtJobList =
  PatentPriorArtSchemas['PatentPriorArtJobListResponse'];
export type PatentPriorArtJobStatus = PatentPriorArtJob['status'];
export type PatentPriorArtJurisdiction =
  PatentPriorArtSchemas['PatentPriorArtJurisdictionOption'];
export type PatentPriorArtPreviewRequest =
  PatentPriorArtSchemas['PatentPriorArtQueryPreviewRequest'];
export type PatentPriorArtPreview =
  PatentPriorArtSchemas['PatentPriorArtQueryPreviewResponse'];
export type PatentPriorArtExecutedQuery =
  PatentPriorArtSchemas['PatentPriorArtExecutedQueryOut'];
export type PatentPriorArtQueryFailureCode = NonNullable<
  PatentPriorArtExecutedQuery['failure_code']
>;
export type PatentPriorArtResult =
  PatentPriorArtSchemas['PatentPriorArtResultResponse'];
export type PatentPriorArtReportFormat =
  PatentPriorArtConfig['report_formats'][number];
export type PatentPriorArtSearchPlan =
  PatentPriorArtSchemas['PatentPriorArtSearchPlanDraft'];
export type PatentPriorArtSearchValues =
  PatentPriorArtSchemas['PatentPriorArtSearchValues'];
export type PatentPriorArtSourceQuery =
  PatentPriorArtSchemas['PatentPriorArtSourceQueryOut'];

const API_PREFIX = '/api/v1/patent-prior-art';

function appPath(workspaceSlug: string, suffix: string): string {
  return rewriteWorkspaceApiPath(`${API_PREFIX}${suffix}`, workspaceSlug);
}

function jobPath(workspaceSlug: string, jobId: string, suffix = ''): string {
  return appPath(workspaceSlug, `/jobs/${encodeURIComponent(jobId)}${suffix}`);
}

export interface PatentPriorArtRequestScope {
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}

export async function getPatentPriorArtConfig(
  args: PatentPriorArtRequestScope,
): Promise<PatentPriorArtConfig> {
  return apiFetchJson<PatentPriorArtConfig>(
    appPath(args.workspaceSlug, '/config'),
    args.token,
    { signal: args.signal },
  );
}

export async function parsePatentPriorArtFile(
  args: PatentPriorArtRequestScope & { file: File },
): Promise<PatentPriorArtFileParseResult> {
  const body = new FormData();
  body.append('file', args.file);
  return apiFetchJson<PatentPriorArtFileParseResult>(
    appPath(args.workspaceSlug, '/files/parse'),
    args.token,
    { body, method: 'POST', signal: args.signal },
  );
}

export async function previewPatentPriorArtQuery(
  args: PatentPriorArtRequestScope & {
    request: PatentPriorArtPreviewRequest;
  },
): Promise<PatentPriorArtPreview> {
  return apiFetchJson<PatentPriorArtPreview>(
    appPath(args.workspaceSlug, '/query-preview'),
    args.token,
    {
      body: JSON.stringify(args.request),
      method: 'POST',
      signal: args.signal,
    },
  );
}

export async function createPatentPriorArtJob(
  args: PatentPriorArtRequestScope & {
    request: PatentPriorArtJobCreateRequest;
  },
): Promise<PatentPriorArtJob> {
  return apiFetchJson<PatentPriorArtJob>(
    appPath(args.workspaceSlug, '/jobs'),
    args.token,
    {
      body: JSON.stringify(args.request),
      method: 'POST',
      signal: args.signal,
    },
  );
}

export async function listPatentPriorArtJobs(
  args: PatentPriorArtRequestScope & { limit?: number },
): Promise<PatentPriorArtJobList> {
  const query = new URLSearchParams({ limit: String(args.limit ?? 50) });
  return apiFetchJson<PatentPriorArtJobList>(
    appPath(args.workspaceSlug, `/jobs?${query.toString()}`),
    args.token,
    { signal: args.signal },
  );
}

export async function getPatentPriorArtJob(
  args: PatentPriorArtRequestScope & { jobId: string },
): Promise<PatentPriorArtJob> {
  return apiFetchJson<PatentPriorArtJob>(
    jobPath(args.workspaceSlug, args.jobId),
    args.token,
    { signal: args.signal },
  );
}

export async function cancelPatentPriorArtJob(
  args: PatentPriorArtRequestScope & { jobId: string },
): Promise<PatentPriorArtJob> {
  return apiFetchJson<PatentPriorArtJob>(
    jobPath(args.workspaceSlug, args.jobId, '/cancel'),
    args.token,
    { method: 'POST', signal: args.signal },
  );
}

export async function deletePatentPriorArtJob(
  args: PatentPriorArtRequestScope & { jobId: string },
): Promise<PatentPriorArtDeleteResult> {
  return apiFetchJson<PatentPriorArtDeleteResult>(
    jobPath(args.workspaceSlug, args.jobId),
    args.token,
    {
      method: 'DELETE',
      signal: args.signal,
    },
  );
}

export async function getPatentPriorArtResult(
  args: PatentPriorArtRequestScope & { jobId: string },
): Promise<PatentPriorArtResult> {
  return apiFetchJson<PatentPriorArtResult>(
    jobPath(args.workspaceSlug, args.jobId, '/result'),
    args.token,
    { signal: args.signal },
  );
}

export async function downloadPatentPriorArtArtifact(
  args: PatentPriorArtRequestScope & {
    artifactId: string;
    jobId: string;
  },
): Promise<Blob> {
  const response = await fetch(
    jobPath(
      args.workspaceSlug,
      args.jobId,
      `/artifacts/${encodeURIComponent(args.artifactId)}`,
    ),
    {
      cache: 'no-store',
      headers: jsonHeaders(args.token, { Accept: '*/*' }),
      signal: args.signal,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      'artifact_download_failed',
      payload,
    );
  }
  return response.blob();
}

export async function downloadPatentPriorArtReport(
  args: PatentPriorArtRequestScope & {
    jobId: string;
    reportFormat: PatentPriorArtReportFormat;
  },
): Promise<Blob> {
  const response = await fetch(
    jobPath(
      args.workspaceSlug,
      args.jobId,
      `/reports/${encodeURIComponent(args.reportFormat)}`,
    ),
    {
      cache: 'no-store',
      headers: jsonHeaders(args.token, { Accept: '*/*' }),
      signal: args.signal,
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiRequestError(
      response.status,
      'report_download_failed',
      payload,
    );
  }
  return response.blob();
}

export const patentPriorArtApi = {
  cancelJob: cancelPatentPriorArtJob,
  createJob: createPatentPriorArtJob,
  deleteJob: deletePatentPriorArtJob,
  downloadArtifact: downloadPatentPriorArtArtifact,
  downloadReport: downloadPatentPriorArtReport,
  getConfig: getPatentPriorArtConfig,
  getJob: getPatentPriorArtJob,
  getResult: getPatentPriorArtResult,
  listJobs: listPatentPriorArtJobs,
  parseFile: parsePatentPriorArtFile,
  previewQuery: previewPatentPriorArtQuery,
};

export type PatentPriorArtApi = typeof patentPriorArtApi;
