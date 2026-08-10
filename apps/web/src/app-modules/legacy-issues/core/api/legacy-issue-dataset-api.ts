import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';
import type {
  LegacyIssueExcelExportJob,
  LegacyIssueImportPreview,
  LegacyIssueImportPreviewColumn,
  LegacyIssueImportResponse,
  LegacyIssueRecordHistoryItem,
  LegacyIssueRecordHistoryResponse,
  LegacyIssueRevision,
  LegacyIssueRevisionCompareResponse,
  LegacyIssueRevisionContext,
  LegacyIssueRevisionListResponse,
  LegacyIssueRevisionOverviewHistory,
  LegacyIssueRevisionOverviewHistoryCreate,
  LegacyIssueRevisionOverviewHistoryUpdate,
} from './legacy-issue-common-api';
import type {
  LegacyIssueDatasetKey,
  LegacyIssueViewKey,
} from '../legacy-issue-datasets';

export type { LegacyIssueDatasetKey } from '../legacy-issue-datasets';

export interface LegacyIssueDatasetField {
  key: string;
  label_ko: string;
  label_en: string;
  group_key: string | null;
  field_type: LegacyIssueModuleFieldType;
  options: string[];
  allow_multiple: boolean;
  required: boolean;
  source: 'system' | 'module' | string;
  module_key: LegacyIssueViewKey | string | null;
  field_id: string | null;
  active: boolean;
  readonly: boolean;
}

export interface LegacyIssueDatasetDefinition {
  key: LegacyIssueDatasetKey;
  title_ko: string;
  title_en: string;
  hierarchy_ko: string[];
  hierarchy_en: string[];
  header_rows: number;
  fields: LegacyIssueDatasetField[];
  group_labels_ko: Record<string, string>;
  group_labels_en: Record<string, string>;
}

export interface LegacyIssueDatasetAttachment {
  id: string;
  record_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  description: string | null;
  is_primary: boolean;
  index_status: string;
  index_error: string | null;
  indexed_at: string | null;
  index_version: string | null;
  chunk_count: number;
  artifact_count: number;
  ai_summary: string | null;
  ai_summary_status: string;
  ai_summary_error: string | null;
  ai_summary_model: string | null;
  ai_summary_version: string | null;
  ai_summarized_at: string | null;
  created_at: string;
}

export interface LegacyIssueDatasetRecord {
  id: string;
  revision_id: string | null;
  stable_record_id: string | null;
  module_key: LegacyIssueViewKey | string | null;
  values: Record<string, LegacyIssueFieldValue>;
  raw_fields: Record<string, unknown>;
  imported_source_filename: string | null;
  imported_at: string | null;
  attachments: LegacyIssueDatasetAttachment[];
  primary_attachment: LegacyIssueDatasetAttachment | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueDatasetRecordListResponse {
  items: LegacyIssueDatasetRecord[];
  total: number;
  limit: number | null;
  offset: number;
  revision: LegacyIssueRevisionContext;
}

export interface LegacyIssueDatasetRecordBatchUpdate {
  record_id: string;
  values: Record<string, LegacyIssueFieldValue | null>;
}

export interface LegacyIssueDatasetRecordBatchCreate {
  client_row_id?: string | null;
  values: Record<string, LegacyIssueFieldValue | null>;
}

export interface LegacyIssueDatasetRecordBatchCreated {
  client_row_id: string | null;
  record: LegacyIssueDatasetRecord;
}

export interface LegacyIssueDatasetRecordBatchSaveResponse {
  items: LegacyIssueDatasetRecord[];
  created_records: LegacyIssueDatasetRecordBatchCreated[];
  created: number;
  updated: number;
}

export type LegacyIssueDatasetRecordHistoryItem = LegacyIssueRecordHistoryItem;
export type LegacyIssueDatasetRecordHistoryResponse =
  LegacyIssueRecordHistoryResponse;
export type LegacyIssueDatasetImportPreviewColumn =
  LegacyIssueImportPreviewColumn;
export type LegacyIssueDatasetImportPreview = LegacyIssueImportPreview;
export type LegacyIssueDatasetImportResponse = LegacyIssueImportResponse;
export type LegacyIssueModuleFieldType =
  | 'text'
  | 'longText'
  | 'number'
  | 'date'
  | 'select'
  | 'boolean'
  | 'user'
  | 'orgUnit';

export interface LegacyIssueReferenceValue {
  kind: 'user' | 'orgUnit';
  id: string;
  label: string;
  email?: string;
  path?: string;
}

export type LegacyIssueFieldValue =
  | string
  | string[]
  | LegacyIssueReferenceValue
  | LegacyIssueReferenceValue[];

export interface LegacyIssueOrgUnitItem {
  id: string;
  name: string;
  slug: string;
  parent_id: string | null;
  path: string;
}

export interface LegacyIssueModuleField {
  id: string;
  module_key: LegacyIssueViewKey | string;
  field_key: string;
  label_ko: string;
  label_en: string;
  field_type: LegacyIssueModuleFieldType;
  options: string[];
  allow_multiple: boolean;
  required: boolean;
  sort_order: number;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueModuleFieldListResponse {
  items: LegacyIssueModuleField[];
}

export interface LegacyIssueSystemField {
  id: string | null;
  dataset_key: LegacyIssueDatasetKey;
  key: string;
  label_ko: string;
  label_en: string;
  group_key: string | null;
  field_type: LegacyIssueModuleFieldType;
  options: string[];
  allow_multiple: boolean;
  required: boolean;
  source: 'system' | string;
  module_key: LegacyIssueViewKey | string | null;
  field_id: string | null;
  active: boolean;
  readonly: boolean;
  updated_at: string | null;
}

export interface LegacyIssueSystemFieldListResponse {
  items: LegacyIssueSystemField[];
}

export interface LegacyIssueColumnOrder {
  view_key: LegacyIssueViewKey | string;
  column_order: string[];
  hidden_column_keys: string[];
  updated_at: string | null;
}

export interface LegacyIssueModuleFieldCreatePayload {
  module_key: LegacyIssueViewKey;
  label_ko: string;
  label_en?: string | null;
  field_type: LegacyIssueModuleFieldType;
  options?: string[] | null;
  allow_multiple?: boolean;
  required?: boolean;
  sort_order?: number | null;
}

export interface LegacyIssueModuleFieldUpdatePayload {
  label_ko?: string | null;
  label_en?: string | null;
  field_type?: LegacyIssueModuleFieldType | null;
  options?: string[] | null;
  allow_multiple?: boolean | null;
  required?: boolean | null;
  sort_order?: number | null;
  active?: boolean | null;
}

export interface LegacyIssueSystemFieldUpdatePayload {
  dataset_key?: LegacyIssueDatasetKey;
  label_ko?: string | null;
  label_en?: string | null;
  field_type?: LegacyIssueModuleFieldType | null;
  options?: string[] | null;
  allow_multiple?: boolean | null;
  required?: boolean | null;
}

export interface LegacyIssueColumnOrderUpdatePayload {
  column_order: string[];
  hidden_column_keys?: string[];
}

export type LegacyIssueGridPreferenceKind =
  | 'dataset'
  | 'vehicle-module-checklist';

export interface LegacyIssueGridPreference {
  column_order: string[];
  created_at: string;
  frozen_column_count: number;
  grid_key: string;
  grid_kind: LegacyIssueGridPreferenceKind;
  hidden_column_keys: string[];
  revision: number;
  updated_at: string;
}

export interface LegacyIssueGridPreferenceResponse {
  preference: LegacyIssueGridPreference | null;
  revision: number;
}

export interface LegacyIssueGridPreferenceUpdatePayload {
  column_order: string[];
  frozen_column_count: number;
  hidden_column_keys: string[];
}

function workspaceLegacyIssueDatasetPath(
  workspaceSlug: string,
  datasetKey: LegacyIssueDatasetKey,
  path: string,
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues/datasets/${encodeURIComponent(datasetKey)}${path}`;
}

function workspaceLegacyIssuePath(workspaceSlug: string, path: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues${path}`;
}

function appendLegacyIssueViewKey(
  params: URLSearchParams,
  viewKey?: LegacyIssueViewKey | string | null,
): void {
  if (viewKey) {
    params.set('view_key', viewKey);
  }
}

export async function fetchLegacyIssueDatasetDefinition({
  datasetKey,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetDefinition> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetDefinition>(
    workspaceLegacyIssueDatasetPath(workspaceSlug, datasetKey, query),
    token,
  );
}

export async function fetchLegacyIssueDatasetRecords({
  limit,
  datasetKey,
  offset = 0,
  query,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  limit?: number;
  datasetKey: LegacyIssueDatasetKey;
  offset?: number;
  query?: string;
  revisionId?: string | null;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetRecordListResponse> {
  const params = new URLSearchParams({ offset: String(offset) });
  appendLegacyIssueViewKey(params, viewKey);
  if (limit !== undefined) {
    params.set('limit', String(limit));
  }
  const trimmedQuery = query?.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  if (revisionId) {
    params.set('revision_id', revisionId);
  }
  return apiFetchJson<LegacyIssueDatasetRecordListResponse>(
    `${workspaceLegacyIssueDatasetPath(workspaceSlug, datasetKey, '/records')}?${params.toString()}`,
    token,
  );
}

export async function fetchLegacyIssueDatasetRecordHistory({
  datasetKey,
  recordId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  recordId: string;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetRecordHistoryResponse> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetRecordHistoryResponse>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records/${encodeURIComponent(recordId)}/history${query}`,
    ),
    token,
  );
}

export async function searchLegacyIssueOrgUnits({
  limit = 50,
  query,
  token,
  workspaceSlug,
}: {
  limit?: number;
  query: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueOrgUnitItem[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const trimmedQuery = query.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  return apiFetchJson<LegacyIssueOrgUnitItem[]>(
    `${workspaceLegacyIssuePath(workspaceSlug, '/org-units')}?${params.toString()}`,
    token,
  );
}

export async function createLegacyIssueDatasetRecord({
  datasetKey,
  token,
  values,
  workspaceSlug,
  revisionId,
  viewKey,
}: {
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  values: Record<string, LegacyIssueFieldValue | null>;
  workspaceSlug: string;
  revisionId?: string | null;
  viewKey?: LegacyIssueViewKey | null;
}): Promise<LegacyIssueDatasetRecord> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  if (revisionId) {
    params.set('revision_id', revisionId);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetRecord>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records${query}`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ values }),
    },
  );
}

export async function updateLegacyIssueDatasetRecord({
  datasetKey,
  recordId,
  token,
  values,
  workspaceSlug,
  revisionId,
  viewKey,
}: {
  datasetKey: LegacyIssueDatasetKey;
  recordId: string;
  token: string;
  values: Record<string, LegacyIssueFieldValue | null>;
  workspaceSlug: string;
  revisionId?: string | null;
  viewKey?: LegacyIssueViewKey | null;
}): Promise<LegacyIssueDatasetRecord> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  if (revisionId) {
    params.set('revision_id', revisionId);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetRecord>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records/${encodeURIComponent(recordId)}${query}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    },
  );
}

export async function saveLegacyIssueDatasetRecordBatch({
  creates,
  datasetKey,
  releaseEditing = false,
  revisionId,
  token,
  updates,
  viewKey,
  workspaceSlug,
}: {
  creates: LegacyIssueDatasetRecordBatchCreate[];
  datasetKey: LegacyIssueDatasetKey;
  releaseEditing?: boolean;
  revisionId?: string | null;
  token: string;
  updates: LegacyIssueDatasetRecordBatchUpdate[];
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetRecordBatchSaveResponse> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  if (revisionId) {
    params.set('revision_id', revisionId);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetRecordBatchSaveResponse>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records/batch${query}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({
        creates,
        release_editing: releaseEditing,
        updates,
      }),
    },
  );
}

export async function releaseLegacyIssueDatasetDraftEditing({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetRecordBatchSaveResponse> {
  return saveLegacyIssueDatasetRecordBatch({
    creates: [],
    datasetKey,
    releaseEditing: true,
    revisionId,
    token,
    updates: [],
    viewKey,
    workspaceSlug,
  });
}

export async function deleteLegacyIssueDatasetRecord({
  datasetKey,
  recordId,
  token,
  workspaceSlug,
  revisionId,
  viewKey,
}: {
  datasetKey: LegacyIssueDatasetKey;
  recordId: string;
  token: string;
  workspaceSlug: string;
  revisionId?: string | null;
  viewKey?: LegacyIssueViewKey | null;
}): Promise<void> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  if (revisionId) params.set('revision_id', revisionId);
  const query = params.toString() ? `?${params.toString()}` : '';
  await apiFetchJson<void>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records/${encodeURIComponent(recordId)}${query}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function previewLegacyIssueDatasetImport({
  file,
  datasetKey,
  token,
  viewKey,
  workspaceSlug,
}: {
  file: File;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetImportPreview> {
  const body = new FormData();
  body.append('file', file);
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueDatasetImportPreview>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/import-preview${query}`,
    ),
    token,
    { method: 'POST', body },
  );
}

export async function importLegacyIssueDatasetRecords({
  file,
  mapping,
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  file: File;
  mapping: Record<string, number>;
  datasetKey: LegacyIssueDatasetKey;
  revisionId?: string | null;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetImportResponse> {
  const body = new FormData();
  body.append('file', file);
  body.append('mapping_json', JSON.stringify(mapping));
  if (revisionId) {
    body.append('revision_id', revisionId);
  }
  if (viewKey) {
    body.append('view_key', viewKey);
  }
  return apiFetchJson<LegacyIssueDatasetImportResponse>(
    workspaceLegacyIssueDatasetPath(workspaceSlug, datasetKey, '/imports'),
    token,
    { method: 'POST', body },
  );
}

export async function exportLegacyIssueDatasetRecords({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId?: string | null;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<Blob> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  if (revisionId) {
    params.set('revision_id', revisionId);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/export.xlsx${query}`,
    ),
    {
      cache: 'no-store',
      headers: {
        ...jsonHeaders(token),
        Accept:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      },
    },
  );
  return parseBlobResponse(response);
}

export async function createLegacyIssueDatasetExcelExport({
  columnKeys,
  datasetKey,
  departments = [],
  includeAttachments,
  recordIds,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  columnKeys: string[];
  datasetKey: LegacyIssueDatasetKey;
  departments?: string[];
  includeAttachments: boolean;
  recordIds: string[] | null;
  revisionId?: string | null;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueExcelExportJob> {
  return apiFetchJson<LegacyIssueExcelExportJob>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      '/excel-exports',
    ),
    token,
    {
      body: JSON.stringify({
        column_keys: columnKeys,
        departments,
        include_attachments: includeAttachments,
        record_ids: recordIds,
        revision_id: revisionId ?? null,
        view_key: viewKey ?? null,
      }),
      method: 'POST',
    },
  );
}

export async function fetchLegacyIssueDatasetRevisions({
  datasetKey,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionListResponse> {
  return apiFetchJson<LegacyIssueRevisionListResponse>(
    `${workspaceLegacyIssueDatasetPath(workspaceSlug, datasetKey, '/revisions')}?view_key=${encodeURIComponent(viewKey)}`,
    token,
  );
}

export async function updateLegacyIssueRevisionOverviewHistory({
  datasetKey,
  historyId,
  payload,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  historyId: string;
  payload: LegacyIssueRevisionOverviewHistoryUpdate;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionOverviewHistory> {
  return apiFetchJson<LegacyIssueRevisionOverviewHistory>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/overview-history/${encodeURIComponent(historyId)}?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function createLegacyIssueRevisionOverviewHistory({
  datasetKey,
  payload,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  payload: LegacyIssueRevisionOverviewHistoryCreate;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionOverviewHistory> {
  return apiFetchJson<LegacyIssueRevisionOverviewHistory>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/overview-history?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteLegacyIssueRevisionOverviewHistory({
  datasetKey,
  historyId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  historyId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionOverviewHistory> {
  return apiFetchJson<LegacyIssueRevisionOverviewHistory>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/overview-history/${encodeURIComponent(historyId)}?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function hideLegacyIssueRevisionFromOverviewHistory({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionOverviewHistory> {
  return apiFetchJson<LegacyIssueRevisionOverviewHistory>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/overview-history/by-revision/${encodeURIComponent(revisionId)}?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function createLegacyIssueDatasetDraftRevision({
  baseRevisionId,
  datasetKey,
  note,
  token,
  viewKey,
  workspaceSlug,
}: {
  baseRevisionId?: string | null;
  datasetKey: LegacyIssueDatasetKey;
  note?: string | null;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  const params = new URLSearchParams({ view_key: viewKey });
  if (baseRevisionId) params.set('base_revision_id', baseRevisionId);
  const query = `?${params.toString()}`;
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/draft${query}`,
    ),
    token,
    {
      method: 'POST',
      body: note ? JSON.stringify({ note }) : undefined,
    },
  );
}

export async function publishLegacyIssueDatasetRevision({
  datasetKey,
  note,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  note: string;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/publish?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ note }),
    },
  );
}

export async function updateLegacyIssueDatasetRevisionSummary({
  datasetKey,
  note,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  note: string | null;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ note }),
    },
  );
}

export async function updateLegacyIssueDatasetRevisionAssignees({
  approverId,
  datasetKey,
  reviewerId,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  approverId: string | null;
  datasetKey: LegacyIssueDatasetKey;
  reviewerId: string | null;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/approval-assignees?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({
        approver_id: approverId,
        reviewer_id: reviewerId,
      }),
    },
  );
}

export async function requestLegacyIssueDatasetRevisionApproval({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId: string;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/review-request`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ view_key: viewKey ?? null }),
    },
  );
}

export async function completeLegacyIssueDatasetRevisionReview({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/review-complete?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function completeLegacyIssueDatasetRevisionApproval({
  datasetKey,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/approval-complete?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function cancelLegacyIssueDatasetRevision({
  datasetKey,
  force = false,
  note,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  force?: boolean;
  note?: string | null;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/cancel?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'POST',
      body:
        note || force
          ? JSON.stringify({
              force,
              ...(note ? { note } : {}),
            })
          : undefined,
    },
  );
}

export async function restoreLegacyIssueDatasetRevision({
  datasetKey,
  note,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  datasetKey: LegacyIssueDatasetKey;
  note?: string | null;
  revisionId: string;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueRevision> {
  return apiFetchJson<LegacyIssueRevision>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/${encodeURIComponent(revisionId)}/restore?view_key=${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'POST',
      body: note ? JSON.stringify({ note }) : undefined,
    },
  );
}

export async function compareLegacyIssueDatasetRevisions({
  leftRevisionId,
  datasetKey,
  rightRevisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  leftRevisionId: string;
  datasetKey: LegacyIssueDatasetKey;
  rightRevisionId: string;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueRevisionCompareResponse> {
  const params = new URLSearchParams({
    left_revision_id: leftRevisionId,
    right_revision_id: rightRevisionId,
  });
  appendLegacyIssueViewKey(params, viewKey);
  return apiFetchJson<LegacyIssueRevisionCompareResponse>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/revisions/compare?${params.toString()}`,
    ),
    token,
  );
}

export async function fetchLegacyIssueModuleFields({
  includeInactive = true,
  moduleKey,
  token,
  workspaceSlug,
}: {
  includeInactive?: boolean;
  moduleKey?: LegacyIssueViewKey | null;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleFieldListResponse> {
  const params = new URLSearchParams({
    include_inactive: includeInactive ? 'true' : 'false',
  });
  if (moduleKey) {
    params.set('module_key', moduleKey);
  }
  return apiFetchJson<LegacyIssueModuleFieldListResponse>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/module-fields?${params.toString()}`,
    ),
    token,
  );
}

export async function fetchLegacyIssueSystemFields({
  datasetKey,
  token,
  workspaceSlug,
}: {
  datasetKey?: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueSystemFieldListResponse> {
  const params = new URLSearchParams();
  if (datasetKey) {
    params.set('dataset_key', datasetKey);
  }
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueSystemFieldListResponse>(
    workspaceLegacyIssuePath(workspaceSlug, `/system-fields${query}`),
    token,
  );
}

export async function fetchLegacyIssueColumnOrder({
  token,
  viewKey,
  workspaceSlug,
}: {
  token: string;
  viewKey?: LegacyIssueViewKey | string | null;
  workspaceSlug: string;
}): Promise<LegacyIssueColumnOrder> {
  const params = new URLSearchParams();
  appendLegacyIssueViewKey(params, viewKey);
  const query = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueColumnOrder>(
    workspaceLegacyIssuePath(workspaceSlug, `/column-orders${query}`),
    token,
  );
}

export async function updateLegacyIssueColumnOrder({
  payload,
  token,
  viewKey,
  workspaceSlug,
}: {
  payload: LegacyIssueColumnOrderUpdatePayload;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
}): Promise<LegacyIssueColumnOrder> {
  return apiFetchJson<LegacyIssueColumnOrder>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/column-orders/${encodeURIComponent(viewKey)}`,
    ),
    token,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchLegacyIssueGridPreference({
  gridKey,
  gridKind,
  token,
  workspaceSlug,
}: {
  gridKey: string;
  gridKind: LegacyIssueGridPreferenceKind;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueGridPreferenceResponse> {
  return apiFetchJson<LegacyIssueGridPreferenceResponse>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/grid-preferences/${encodeURIComponent(gridKind)}/${encodeURIComponent(
        gridKey,
      )}`,
    ),
    token,
  );
}

export async function updateLegacyIssueGridPreference({
  expectedRevision,
  gridKey,
  gridKind,
  payload,
  token,
  workspaceSlug,
}: {
  expectedRevision: number;
  gridKey: string;
  gridKind: LegacyIssueGridPreferenceKind;
  payload: LegacyIssueGridPreferenceUpdatePayload;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueGridPreference> {
  return apiFetchJson<LegacyIssueGridPreference>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/grid-preferences/${encodeURIComponent(gridKind)}/${encodeURIComponent(
        gridKey,
      )}`,
    ),
    token,
    {
      method: 'PUT',
      body: JSON.stringify({
        ...payload,
        expected_revision: expectedRevision,
      }),
    },
  );
}

export async function deleteLegacyIssueGridPreference({
  expectedRevision,
  gridKey,
  gridKind,
  token,
  workspaceSlug,
}: {
  expectedRevision: number;
  gridKey: string;
  gridKind: LegacyIssueGridPreferenceKind;
  token: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/grid-preferences/${encodeURIComponent(gridKind)}/${encodeURIComponent(
        gridKey,
      )}?expected_revision=${expectedRevision}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function createLegacyIssueModuleField({
  payload,
  token,
  workspaceSlug,
}: {
  payload: LegacyIssueModuleFieldCreatePayload;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleField> {
  return apiFetchJson<LegacyIssueModuleField>(
    workspaceLegacyIssuePath(workspaceSlug, '/module-fields'),
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export async function updateLegacyIssueModuleField({
  fieldId,
  payload,
  token,
  workspaceSlug,
}: {
  fieldId: string;
  payload: LegacyIssueModuleFieldUpdatePayload;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleField> {
  return apiFetchJson<LegacyIssueModuleField>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/module-fields/${encodeURIComponent(fieldId)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function updateLegacyIssueSystemField({
  fieldKey,
  payload,
  token,
  workspaceSlug,
}: {
  fieldKey: string;
  payload: LegacyIssueSystemFieldUpdatePayload;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueSystemField> {
  return apiFetchJson<LegacyIssueSystemField>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/system-fields/${encodeURIComponent(fieldKey)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteLegacyIssueModuleField({
  fieldId,
  token,
  workspaceSlug,
}: {
  fieldId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleField> {
  return apiFetchJson<LegacyIssueModuleField>(
    workspaceLegacyIssuePath(
      workspaceSlug,
      `/module-fields/${encodeURIComponent(fieldId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function reorderLegacyIssueModuleFields({
  fieldIds,
  moduleKey,
  token,
  workspaceSlug,
}: {
  fieldIds: string[];
  moduleKey: LegacyIssueViewKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleFieldListResponse> {
  return apiFetchJson<LegacyIssueModuleFieldListResponse>(
    workspaceLegacyIssuePath(workspaceSlug, '/module-fields/reorder'),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({
        field_ids: fieldIds,
        module_key: moduleKey,
      }),
    },
  );
}

export async function uploadLegacyIssueDatasetAttachment({
  description,
  file,
  isPrimary,
  datasetKey,
  recordId,
  token,
  workspaceSlug,
}: {
  description?: string | null;
  file: File;
  isPrimary: boolean;
  datasetKey: LegacyIssueDatasetKey;
  recordId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetAttachment> {
  const body = new FormData();
  body.append('file', file);
  body.append('is_primary', String(isPrimary));
  if (description != null) {
    body.append('description', description);
  }
  return apiFetchJson<LegacyIssueDatasetAttachment>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/records/${encodeURIComponent(recordId)}/attachments`,
    ),
    token,
    { method: 'POST', body },
  );
}

export async function updateLegacyIssueDatasetAttachment({
  attachmentId,
  description,
  datasetKey,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  description?: string | null;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetAttachment> {
  return apiFetchJson<LegacyIssueDatasetAttachment>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/attachments/${encodeURIComponent(attachmentId)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ description }),
    },
  );
}

export async function setLegacyIssueDatasetAttachmentPrimary({
  attachmentId,
  isPrimary = true,
  datasetKey,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  isPrimary?: boolean;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetAttachment> {
  return apiFetchJson<LegacyIssueDatasetAttachment>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/attachments/${encodeURIComponent(attachmentId)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ is_primary: isPrimary }),
    },
  );
}

export async function retryLegacyIssueDatasetAttachmentIndex({
  attachmentId,
  datasetKey,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueDatasetAttachment> {
  return apiFetchJson<LegacyIssueDatasetAttachment>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/attachments/${encodeURIComponent(attachmentId)}/index`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function deleteLegacyIssueDatasetAttachment({
  attachmentId,
  datasetKey,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/attachments/${encodeURIComponent(attachmentId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function fetchLegacyIssueDatasetAttachmentBlob({
  attachmentId,
  datasetKey,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  workspaceSlug: string;
}): Promise<Blob> {
  const response = await fetch(
    workspaceLegacyIssueDatasetPath(
      workspaceSlug,
      datasetKey,
      `/attachments/${encodeURIComponent(attachmentId)}/file`,
    ),
    {
      cache: 'no-store',
      headers: jsonHeaders(token),
    },
  );
  return parseBlobResponse(response);
}

async function parseBlobResponse(response: Response): Promise<Blob> {
  if (response.ok) {
    return response.blob();
  }
  const payload = await response.json().catch(() => null);
  throw new ApiRequestError(
    response.status,
    typeof payload?.detail === 'string'
      ? payload.detail
      : `Request failed with ${response.status}.`,
    payload,
  );
}
