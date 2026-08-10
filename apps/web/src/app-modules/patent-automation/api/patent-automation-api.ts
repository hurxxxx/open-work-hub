import { apiFetchJson, jsonHeaders } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

// ── Types ─────────────────────────────────────────────────────────────────────
export interface PatentFieldDef {
  key: string;
  label_ko: string;
  group_ko: string;
  column_letter: string;
  type: string;
  is_promoted: boolean;
}

export interface PatentProgressEvent {
  id: string;
  kind: string;
  seq: number;
  event_date: string | null;
  stage: string;
  note: string | null;
}

export interface PatentRecord {
  id: string;
  stable_record_id: string | null;
  application_no: string | null;
  registration_no: string | null;
  invention_title: string | null;
  inventors: string | null;
  disclosure_date: string | null;
  disclosure_year: number | null;
  application_date: string | null;
  application_year: number | null;
  patent_status: string | null;
  current_stage: string | null;
  lifecycle_phase: string | null;
  source_sheet: string | null;
  field_values: Record<string, string>;
  progress_events: PatentProgressEvent[];
  updated_at: string | null;
}

export interface PatentRecordListResponse {
  items: PatentRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface PatentImportResult {
  created: number;
  updated: number;
  skipped: number;
  removed: number;
  total_rows: number;
  progress_events: number;
  sheets: string[];
  warnings: string[];
}

export interface PatentHistoryEntry {
  id: string;
  action: string;
  field_key: string | null;
  field_label: string | null;
  old_value: string | null;
  new_value: string | null;
  actor_user_id: string | null;
  created_at: string | null;
}

export interface PatentCostLine {
  id: string;
  region: string;
  section: string;
  seq: number | null;
  vendor: string | null;
  invoice_no: string | null;
  application_no: string | null;
  registration_no: string | null;
  title: string | null;
  inventors: string | null;
  annuity_year: string | null;
  supply_amount: number | null;
  vat: number | null;
  gov_fee: number | null;
  line_total: number | null;
  foreign_currency: string | null;
  reconciled: boolean;
  record_id: string | null;
}

export interface PatentCostRun {
  id: string;
  fiscal_period: string | null;
  status: string;
  industrial_total: number | null;
  overseas_total: number | null;
  warnings: string[];
  lines: PatentCostLine[];
  has_industrial: boolean;
  has_overseas: boolean;
  created_at: string | null;
}

const XLSX_MIME =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const API_PREFIX = '/api/v1/patent-automation';

function basePath(workspaceSlug: string, path: string): string {
  return rewriteWorkspaceApiPath(`${API_PREFIX}${path}`, workspaceSlug);
}

async function parseBlobResponse(response: Response): Promise<Blob> {
  if (!response.ok) {
    throw new Error(i18n.t('apps:patentAutomation.errors.download'));
  }
  return response.blob();
}

// ── Fields ──────────────────────────────────────────────────────────────────
export async function fetchPatentFields(args: {
  token: string;
  workspaceSlug: string;
  scope?: 'domestic' | 'overseas';
}): Promise<{ fields: PatentFieldDef[] }> {
  const params = new URLSearchParams({ scope: args.scope ?? 'domestic' });
  return apiFetchJson(
    `${basePath(args.workspaceSlug, '/fields')}?${params.toString()}`,
    args.token,
  );
}

// ── Records ───────────────────────────────────────────────────────────────────
export async function fetchPatentRecords(args: {
  token: string;
  workspaceSlug: string;
  query?: string;
  source?: 'domestic' | 'overseas';
  limit?: number;
  offset?: number;
}): Promise<PatentRecordListResponse> {
  const params = new URLSearchParams({ offset: String(args.offset ?? 0) });
  if (args.limit !== undefined) params.set('limit', String(args.limit));
  const trimmed = args.query?.trim();
  if (trimmed) params.set('q', trimmed);
  if (args.source) params.set('source', args.source);
  return apiFetchJson(
    `${basePath(args.workspaceSlug, '/records')}?${params.toString()}`,
    args.token,
  );
}

export async function getPatentRecord(args: {
  token: string;
  workspaceSlug: string;
  recordId: string;
}): Promise<PatentRecord> {
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/records/${encodeURIComponent(args.recordId)}`,
    ),
    args.token,
  );
}

export async function createPatentRecord(args: {
  token: string;
  workspaceSlug: string;
  fieldValues: Record<string, string>;
}): Promise<PatentRecord> {
  return apiFetchJson(basePath(args.workspaceSlug, '/records'), args.token, {
    method: 'POST',
    body: JSON.stringify({ field_values: args.fieldValues }),
  });
}

export async function updatePatentRecord(args: {
  token: string;
  workspaceSlug: string;
  recordId: string;
  fieldValues: Record<string, string>;
}): Promise<PatentRecord> {
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/records/${encodeURIComponent(args.recordId)}`,
    ),
    args.token,
    {
      method: 'PATCH',
      body: JSON.stringify({ field_values: args.fieldValues }),
    },
  );
}

export async function deletePatentRecord(args: {
  token: string;
  workspaceSlug: string;
  recordId: string;
}): Promise<void> {
  await apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/records/${encodeURIComponent(args.recordId)}`,
    ),
    args.token,
    { method: 'DELETE' },
  );
}

export async function fetchPatentRecordHistory(args: {
  token: string;
  workspaceSlug: string;
  recordId: string;
}): Promise<{ items: PatentHistoryEntry[] }> {
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/records/${encodeURIComponent(args.recordId)}/history`,
    ),
    args.token,
  );
}

export async function addPatentProgress(args: {
  token: string;
  workspaceSlug: string;
  recordId: string;
  kind: string;
  stage: string;
  eventDate?: string | null;
  note?: string | null;
}): Promise<PatentRecord> {
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/records/${encodeURIComponent(args.recordId)}/progress`,
    ),
    args.token,
    {
      method: 'POST',
      body: JSON.stringify({
        kind: args.kind,
        stage: args.stage,
        event_date: args.eventDate ?? null,
        note: args.note ?? null,
      }),
    },
  );
}

// ── Import / Export ────────────────────────────────────────────────────────────
export async function importPatentRecords(args: {
  token: string;
  workspaceSlug: string;
  file: File;
}): Promise<PatentImportResult> {
  const body = new FormData();
  body.append('file', args.file);
  return apiFetchJson(basePath(args.workspaceSlug, '/imports'), args.token, {
    method: 'POST',
    body,
  });
}

// 직무발명신고서 업로드 → 새 행(레코드) 생성
export async function createPatentDisclosure(args: {
  token: string;
  workspaceSlug: string;
  file: File;
}): Promise<PatentRecord> {
  const body = new FormData();
  body.append('file', args.file);
  return apiFetchJson(
    basePath(args.workspaceSlug, '/disclosures'),
    args.token,
    { method: 'POST', body },
  );
}

export async function exportPatentRecords(args: {
  token: string;
  workspaceSlug: string;
}): Promise<Blob> {
  const response = await fetch(
    basePath(args.workspaceSlug, '/records-export.xlsx'),
    {
      cache: 'no-store',
      headers: { ...jsonHeaders(args.token), Accept: XLSX_MIME },
    },
  );
  return parseBlobResponse(response);
}

// ── Cost runs ─────────────────────────────────────────────────────────────────
export async function ingestPatentCostFiles(args: {
  token: string;
  workspaceSlug: string;
  files: File[];
  region: string;
  fiscalPeriod?: string;
}): Promise<PatentCostRun> {
  const body = new FormData();
  for (const file of args.files) body.append('files', file);
  body.append('region', args.region);
  if (args.fiscalPeriod) body.append('fiscal_period', args.fiscalPeriod);
  return apiFetchJson(
    basePath(args.workspaceSlug, '/cost-runs/ingest'),
    args.token,
    { method: 'POST', body },
  );
}

export async function getPatentCostRun(args: {
  token: string;
  workspaceSlug: string;
  runId: string;
}): Promise<PatentCostRun> {
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/cost-runs/${encodeURIComponent(args.runId)}`,
    ),
    args.token,
  );
}

export async function downloadPatentCostExcel(args: {
  token: string;
  workspaceSlug: string;
  runId: string;
  kind: 'industrial' | 'overseas' | 'count-amount';
}): Promise<Blob> {
  const response = await fetch(
    basePath(
      args.workspaceSlug,
      `/cost-runs/${encodeURIComponent(args.runId)}/${args.kind}.xlsx`,
    ),
    {
      cache: 'no-store',
      headers: { ...jsonHeaders(args.token), Accept: XLSX_MIME },
    },
  );
  return parseBlobResponse(response);
}

export interface PatentApprovalHtml {
  html: string;
  filename: string;
}

export async function generatePatentApprovalHtml(args: {
  token: string;
  workspaceSlug: string;
  runId: string;
  countAmountFile?: File;
}): Promise<PatentApprovalHtml> {
  const body = new FormData();
  if (args.countAmountFile)
    body.append('count_amount_file', args.countAmountFile);
  return apiFetchJson(
    basePath(
      args.workspaceSlug,
      `/cost-runs/${encodeURIComponent(args.runId)}/approval-html`,
    ),
    args.token,
    { method: 'POST', body },
  );
}
