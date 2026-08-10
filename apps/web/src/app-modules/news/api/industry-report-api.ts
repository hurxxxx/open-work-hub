import { apiFetchJsonWithMappedError, jsonHeaders } from '@/src/platform/api/client';

const BASE_PATH = '/api/v1/industry-report';

export type ReportItemSource =
  | 'autojournal'
  | 'kdi_nara'
  | 'kdi_material'
  | 'kdi_domestic';

export type KdiPath = 'nara' | 'material' | 'domestic';

export interface TrendCompany {
  code: string;
  label: string;
  file_count: number;
}

export interface TrendCompanyListResponse {
  status: string;
  companies: TrendCompany[];
}

export interface TrendFile {
  id: string;
  company: string;
  title: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  published_date: string;
  source: string;
}

export interface TrendFileListResponse {
  status: string;
  company: string;
  company_label: string;
  files: TrendFile[];
}

export interface ReportItem {
  source: string;
  keyword: string;
  title: string;
  org: string;
  summary: string;
  url: string;
  published_date: string;
  extra: Record<string, unknown> | null;
}

export interface ItemListResponse {
  status: string;
  source: string;
  collected_at: string | null;
  items: ReportItem[];
}

export interface AutojournalTocEntry {
  page: number;
  title: string;
}

export interface AutojournalIssueDetail {
  status: string;
  issue_id: string;
  total_pages: number;
  toc: AutojournalTocEntry[];
  pages: string[];
}

export interface KdiPdfUrlResponse {
  status: string;
  page_url: string;
  pdf_url: string | null;
}

export interface ReportStatus {
  collecting: boolean;
  collected_at: string | null;
  is_today: boolean;
}

export interface ReportFetchResult {
  status: string;
  message: string;
}

export class IndustryReportApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'IndustryReportApiError';
  }
}

function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) =>
      new IndustryReportApiError(
        error.status,
        error.message || `Industry-report request failed with ${error.status}.`,
      ),
  );
}

// ── Trend (자동차 리서치 자료) ──────────────────────────────
export function fetchTrendCompanies(token: string | null): Promise<TrendCompanyListResponse> {
  return request<TrendCompanyListResponse>(`${BASE_PATH}/trend/companies`, token);
}

export function fetchTrendFiles(
  token: string | null,
  company: string,
): Promise<TrendFileListResponse> {
  return request<TrendFileListResponse>(
    `${BASE_PATH}/trend/${encodeURIComponent(company)}/files`,
    token,
  );
}

/** Fetch a stored report file as an object URL (auth header required). */
export async function fetchTrendFileObjectUrl(token: string | null, fileId: string): Promise<string> {
  const response = await fetch(`${BASE_PATH}/trend/file/${encodeURIComponent(fileId)}/content`, {
    headers: jsonHeaders(token),
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new IndustryReportApiError(response.status, `File download failed with ${response.status}.`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export function uploadTrendFile(
  token: string | null,
  company: string,
  payload: { file: File; title?: string; publishedDate?: string },
): Promise<TrendFile> {
  const body = new FormData();
  body.append('file', payload.file);
  if (payload.title) body.append('title', payload.title);
  if (payload.publishedDate) body.append('published_date', payload.publishedDate);
  return request<TrendFile>(`${BASE_PATH}/trend/${encodeURIComponent(company)}/upload`, token, {
    method: 'POST',
    body,
  });
}

export function deleteTrendFile(token: string | null, fileId: string): Promise<{ status: string }> {
  return request<{ status: string }>(
    `${BASE_PATH}/trend/file/${encodeURIComponent(fileId)}`,
    token,
    { method: 'DELETE' },
  );
}

// ── Autojournal (오토저널) ──────────────────────────────────
export function fetchAutojournalIssues(token: string | null): Promise<ItemListResponse> {
  return request<ItemListResponse>(`${BASE_PATH}/autojournal/issues`, token);
}

export function fetchAutojournalIssue(
  token: string | null,
  issueId: string,
): Promise<AutojournalIssueDetail> {
  return request<AutojournalIssueDetail>(
    `${BASE_PATH}/autojournal/issue/${encodeURIComponent(issueId)}`,
    token,
  );
}

// ── KDI (경제연구 자료) ─────────────────────────────────────
export function fetchKdiItems(
  token: string | null,
  path: KdiPath,
  keyword?: string,
): Promise<ItemListResponse> {
  const query = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
  return request<ItemListResponse>(`${BASE_PATH}/kdi/${path}${query}`, token);
}

export function resolveKdiPdfUrl(token: string | null, pageUrl: string): Promise<KdiPdfUrlResponse> {
  return request<KdiPdfUrlResponse>(
    `${BASE_PATH}/kdi/pdf-url?page=${encodeURIComponent(pageUrl)}`,
    token,
  );
}

// ── 추천/스크랩 산업 리포트 ─────────────────────────────────
export type ReportSnapshotKind =
  | 'trend'
  | 'autojournal'
  | 'kdi_nara'
  | 'kdi_material'
  | 'kdi_domestic';

export interface RecommendedReport {
  id: string;
  kind: ReportSnapshotKind;
  title: string;
  org: string;
  published_date: string;
  url: string;
  file_id: string | null;
  company: string;
  origin: string;
  reason: string;
  reason_detail: string;
}

export interface RecommendedReportListResponse {
  status: string;
  items: RecommendedReport[];
}

export interface ScrapReport {
  id: string;
  kind: ReportSnapshotKind;
  title: string;
  org: string;
  published_date: string;
  url: string;
  file_id: string | null;
  company: string;
}

export interface ScrapReportListResponse {
  status: string;
  items: ScrapReport[];
}

export interface ReportCurateResult {
  status: string;
  evaluated: number;
  saved: number;
  by_reason: Record<string, number>;
  error: string | null;
}

export interface ReportSnapshotPayload {
  kind: ReportSnapshotKind;
  title: string;
  org?: string;
  published_date?: string;
  url?: string;
  file_id?: string | null;
  company?: string;
}

export function fetchRecommendedReports(token: string | null): Promise<RecommendedReportListResponse> {
  return request<RecommendedReportListResponse>(`${BASE_PATH}/recommended`, token);
}

export function recommendReport(
  token: string | null,
  payload: ReportSnapshotPayload,
): Promise<RecommendedReport> {
  return request<RecommendedReport>(`${BASE_PATH}/recommended`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteRecommendedReport(token: string | null, id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE_PATH}/recommended/${encodeURIComponent(id)}`, token, {
    method: 'DELETE',
  });
}

export function fetchReportScraps(token: string | null): Promise<ScrapReportListResponse> {
  return request<ScrapReportListResponse>(`${BASE_PATH}/scraps`, token);
}

export function scrapReport(
  token: string | null,
  payload: ReportSnapshotPayload,
): Promise<ScrapReport> {
  return request<ScrapReport>(`${BASE_PATH}/scraps`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteReportScrap(token: string | null, id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`${BASE_PATH}/scraps/${encodeURIComponent(id)}`, token, {
    method: 'DELETE',
  });
}

export function fetchAiRecommendedReports(token: string | null): Promise<RecommendedReportListResponse> {
  return request<RecommendedReportListResponse>(`${BASE_PATH}/ai-recommended`, token);
}

export function triggerReportCurate(token: string | null): Promise<ReportCurateResult> {
  return request<ReportCurateResult>(`${BASE_PATH}/curate`, token, { method: 'POST' });
}

// ── Status / collection ─────────────────────────────────────
export function fetchReportStatus(token: string | null): Promise<ReportStatus> {
  return request<ReportStatus>(`${BASE_PATH}/status`, token);
}

export function triggerReportFetch(token: string | null): Promise<ReportFetchResult> {
  return request<ReportFetchResult>(`${BASE_PATH}/fetch`, token, { method: 'POST' });
}
