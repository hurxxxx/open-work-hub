import { apiFetchJson } from '@/src/platform/api/client';

export type LegacyIssueReportListView = 'mine' | 'shared';
export type LegacyIssueReportVisibility = 'private' | 'workspace';

export interface LegacyIssueReportSummary {
  report_id: string;
  report_number: string;
  title: string;
  question: string;
  preview: string;
  completed_at: string | null;
  owner_user_id: string | null;
  owner_name: string | null;
  visibility: LegacyIssueReportVisibility;
  query_count: number;
  source_count: number;
}

export interface LegacyIssueReportListResponse {
  items: LegacyIssueReportSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface LegacyIssueReportDetail
  extends Omit<LegacyIssueReportSummary, 'preview'> {
  content: string;
  content_type: string;
  created_at: string;
  conversation_id: string | null;
  conversation_turn_id: string | null;
}

export interface LegacyIssueReportQuery {
  id: string;
  ordinal: number;
  query_kind: string;
  title: string | null;
  family_id: string | null;
  query_spec: Record<string, unknown> | null;
  statement_text: string | null;
  typed_params: unknown;
  execution_status: string;
  error_code: string | null;
  query_sha256: string | null;
  result_sha256: string | null;
  row_count: number | null;
  duration_ms: number | null;
  truncated: boolean;
  payload_bytes: number | null;
  exactness: string | null;
  created_at: string;
}

export interface LegacyIssueReportQueryListResponse {
  items: LegacyIssueReportQuery[];
}

export interface LegacyIssueReportGridColumn {
  key?: string;
  label?: string;
  name?: string;
  type?: string;
}

export interface LegacyIssueReportQueryRows {
  query_id: string;
  columns: LegacyIssueReportGridColumn[] | null;
  rows: Array<Record<string, unknown>>;
  row_count: number | null;
  captured_row_count: number;
  truncated: boolean;
  limit: number;
  offset: number;
  total: number;
}

export interface LegacyIssueReportSource {
  id: string;
  ordinal: number;
  source_kind: string;
  source_ref: string | null;
  source_version: string | null;
  title: string | null;
  locator: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  content_sha256: string | null;
  grid_columns: LegacyIssueReportGridColumn[] | null;
  grid_rows: Array<Record<string, unknown>> | null;
  row_count: number | null;
  truncated: boolean;
  created_at: string;
}

export interface LegacyIssueReportSourceListResponse {
  items: LegacyIssueReportSource[];
}

function workspaceReportPath(workspaceSlug: string, suffix = ''): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues/reports${suffix}`;
}

export function listLegacyIssueReports({
  limit = 30,
  offset = 0,
  signal,
  token,
  view = 'mine',
  workspaceSlug,
}: {
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
  token: string;
  view?: LegacyIssueReportListView;
  workspaceSlug: string;
}): Promise<LegacyIssueReportListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    view,
  });
  return apiFetchJson<LegacyIssueReportListResponse>(
    workspaceReportPath(workspaceSlug, `?${params.toString()}`),
    token,
    { signal },
  );
}

export function getLegacyIssueReport({
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportDetail> {
  return apiFetchJson<LegacyIssueReportDetail>(
    workspaceReportPath(workspaceSlug, `/${encodeURIComponent(reportId)}`),
    token,
    { signal },
  );
}

export function listLegacyIssueReportQueries({
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportQueryListResponse> {
  return apiFetchJson<LegacyIssueReportQueryListResponse>(
    workspaceReportPath(
      workspaceSlug,
      `/${encodeURIComponent(reportId)}/queries`,
    ),
    token,
    { signal },
  );
}

export function getLegacyIssueReportQueryRows({
  limit = 100,
  offset = 0,
  queryId,
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  limit?: number;
  offset?: number;
  queryId: string;
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportQueryRows> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiFetchJson<LegacyIssueReportQueryRows>(
    workspaceReportPath(
      workspaceSlug,
      `/${encodeURIComponent(reportId)}/queries/${encodeURIComponent(
        queryId,
      )}/rows?${params.toString()}`,
    ),
    token,
    { signal },
  );
}

export function listLegacyIssueReportSources({
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportSourceListResponse> {
  return apiFetchJson<LegacyIssueReportSourceListResponse>(
    workspaceReportPath(
      workspaceSlug,
      `/${encodeURIComponent(reportId)}/sources`,
    ),
    token,
    { signal },
  );
}

export function shareLegacyIssueReport({
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportDetail> {
  return apiFetchJson<LegacyIssueReportDetail>(
    workspaceReportPath(
      workspaceSlug,
      `/${encodeURIComponent(reportId)}/workspace-share`,
    ),
    token,
    { method: 'PUT', signal },
  );
}

export function unshareLegacyIssueReport({
  reportId,
  signal,
  token,
  workspaceSlug,
}: {
  reportId: string;
  signal?: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueReportDetail> {
  return apiFetchJson<LegacyIssueReportDetail>(
    workspaceReportPath(
      workspaceSlug,
      `/${encodeURIComponent(reportId)}/workspace-share`,
    ),
    token,
    { method: 'DELETE', signal },
  );
}

// Compatibility alias for callers that still use the old history vocabulary.
export type LegacyIssueAssistantReportSummary = LegacyIssueReportSummary;
export type LegacyIssueAssistantReportListResponse =
  LegacyIssueReportListResponse;
export const listLegacyIssueAssistantReports = listLegacyIssueReports;
