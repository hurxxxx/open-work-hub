import {
  apiFetchJsonWithMappedError,
  ApiRequestError,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type HealthCheckupSourceStatus =
  ApiSchema<'HealthCheckupSourceStatusResponse'>;
export type HealthCheckupDeterminationList =
  ApiSchema<'HealthCheckupDeterminationListResponse'>;
export type EmployeeDetermination =
  HealthCheckupDeterminationList['items'][number];
export type DeterminationReason = EmployeeDetermination['reason'];
export type HealthCheckupPriorExamStatus =
  ApiSchema<'HealthCheckupPriorExamStatus'>;
export type HealthCheckupPriorExamUpload =
  ApiSchema<'HealthCheckupPriorExamUploadResponse'>;
export type HealthCheckupSettings = ApiSchema<'HealthCheckupSettingsResponse'>;
export type HealthCheckupSettingsUpdate =
  ApiSchema<'HealthCheckupSettingsUpdateRequest'>;
export type HealthCheckupSettingsHistory =
  ApiSchema<'HealthCheckupSettingsHistoryResponse'>;
export type SettingsHistoryItem = HealthCheckupSettingsHistory['items'][number];
export type AgeCalcMethod = HealthCheckupSettings['age_calc_method'];

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
export const HEALTH_CHECKUP_API_PREFIX =
  '/api/v1/management-tasks/health-checkup';

export class HealthCheckupApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly payload: unknown = null,
  ) {
    super(message);
    this.name = 'HealthCheckupApiError';
  }
}

function mapApiError(error: ApiRequestError): HealthCheckupApiError {
  return new HealthCheckupApiError(error.status, error.message, error.payload);
}

function request<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T, HealthCheckupApiError>(
    rewriteWorkspaceApiPath(
      `${HEALTH_CHECKUP_API_PREFIX}${path}`,
      workspaceSlug,
    ),
    token,
    init,
    mapApiError,
  );
}

function yearQuery(year?: number): string {
  if (year === undefined) return '';
  const params = new URLSearchParams({ year: String(year) });
  return `?${params.toString()}`;
}

export function fetchSourceStatus(args: {
  token: string;
  workspaceSlug: string;
  signal?: AbortSignal;
}): Promise<HealthCheckupSourceStatus> {
  return request('/source/status', args.token, args.workspaceSlug, {
    signal: args.signal,
  });
}

export function fetchDeterminations(args: {
  token: string;
  workspaceSlug: string;
  year?: number;
  signal?: AbortSignal;
}): Promise<HealthCheckupDeterminationList> {
  return request(
    `/determinations${yearQuery(args.year)}`,
    args.token,
    args.workspaceSlug,
    { signal: args.signal },
  );
}

export function refreshDeterminations(args: {
  token: string;
  workspaceSlug: string;
  year: number;
  signal?: AbortSignal;
}): Promise<HealthCheckupDeterminationList> {
  return request(
    `/determinations/refresh${yearQuery(args.year)}`,
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      signal: args.signal,
    },
  );
}

export function fetchPriorExamStatus(args: {
  token: string;
  workspaceSlug: string;
  year?: number;
  signal?: AbortSignal;
}): Promise<HealthCheckupPriorExamStatus> {
  return request(
    `/prior-exams/status${yearQuery(args.year)}`,
    args.token,
    args.workspaceSlug,
    { signal: args.signal },
  );
}

export function uploadPriorExam(args: {
  token: string;
  workspaceSlug: string;
  year?: number;
  file: File;
}): Promise<HealthCheckupPriorExamUpload> {
  const body = new FormData();
  body.append('file', args.file);
  return request(
    `/prior-exams${yearQuery(args.year)}`,
    args.token,
    args.workspaceSlug,
    {
      method: 'POST',
      body,
    },
  );
}

export function fetchSettings(args: {
  token: string;
  workspaceSlug: string;
  signal?: AbortSignal;
}): Promise<HealthCheckupSettings> {
  return request('/settings', args.token, args.workspaceSlug, {
    signal: args.signal,
  });
}

export function updateSettings(args: {
  token: string;
  workspaceSlug: string;
  payload: HealthCheckupSettingsUpdate;
}): Promise<HealthCheckupSettings> {
  return request('/settings', args.token, args.workspaceSlug, {
    method: 'PUT',
    body: JSON.stringify(args.payload),
  });
}

export function fetchSettingsHistory(args: {
  token: string;
  workspaceSlug: string;
  signal?: AbortSignal;
}): Promise<HealthCheckupSettingsHistory> {
  return request('/settings/history', args.token, args.workspaceSlug, {
    signal: args.signal,
  });
}

async function responseFailureMessage(response: Response): Promise<string> {
  const payload = await response
    .clone()
    .json()
    .catch(() => null);
  return typeof payload?.detail === 'string' && payload.detail
    ? payload.detail
    : i18n.t('apps:healthCheckup.errors.download');
}

async function downloadXlsx(args: {
  token: string;
  workspaceSlug: string;
  path: string;
  signal?: AbortSignal;
}): Promise<Blob> {
  const response = await fetch(
    rewriteWorkspaceApiPath(
      `${HEALTH_CHECKUP_API_PREFIX}${args.path}`,
      args.workspaceSlug,
    ),
    {
      cache: 'no-store',
      headers: { ...jsonHeaders(args.token), Accept: XLSX_MIME },
      signal: args.signal,
    },
  );
  if (!response.ok) {
    throw new HealthCheckupApiError(
      response.status,
      await responseFailureMessage(response),
    );
  }
  return response.blob();
}

type ExportArgs = {
  token: string;
  workspaceSlug: string;
  year?: number;
  signal?: AbortSignal;
};

export function exportEmployees(args: ExportArgs): Promise<Blob> {
  return downloadXlsx({
    ...args,
    path: `/export/employees.xlsx${yearQuery(args.year)}`,
  });
}

export function exportTargets(args: ExportArgs): Promise<Blob> {
  return downloadXlsx({
    ...args,
    path: `/export/targets.xlsx${yearQuery(args.year)}`,
  });
}

export function exportRoster(args: ExportArgs): Promise<Blob> {
  return downloadXlsx({
    ...args,
    path: `/export/roster.xlsx${yearQuery(args.year)}`,
  });
}
