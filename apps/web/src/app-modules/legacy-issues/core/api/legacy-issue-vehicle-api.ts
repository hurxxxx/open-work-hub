import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';
import type {
  LegacyIssueDatasetDefinition,
  LegacyIssueDatasetField,
  LegacyIssueFieldValue,
} from './legacy-issue-dataset-api';
import type { LegacyIssueExcelExportJob } from './legacy-issue-common-api';
import type { LegacyIssueViewKey } from '../legacy-issue-datasets';

export {
  fetchLegacyIssueExcelExportFile,
  fetchLegacyIssueExcelExportJob,
} from './legacy-issue-excel-export-api';

export interface LegacyIssueVehicleStage {
  id: string;
  vehicle_model_id: string;
  name: string;
  sequence_no: number;
  previous_stage_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleModel {
  id: string;
  vehicle_code: string;
  vehicle_name: string | null;
  notes: string | null;
  active: boolean;
  stages: LegacyIssueVehicleStage[];
  generated_checklist_count: number;
  checklist_summary: LegacyIssueVehicleChecklistSummary | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleChecklistSummaryEntry {
  revision_id: string;
  source_master_revision_no: number | null;
  updated_at: string;
}

export interface LegacyIssueVehicleChecklistSummary {
  latest_draft: LegacyIssueVehicleChecklistSummaryEntry | null;
  latest_completed: LegacyIssueVehicleChecklistSummaryEntry | null;
}

export interface LegacyIssueVehicleModelListResponse {
  items: LegacyIssueVehicleModel[];
}

export interface LegacyIssueVehicleChecklistMasterRevision {
  id: string;
  revision_no: number | null;
}

export interface LegacyIssueVehicleChecklistRevision {
  id: string;
  vehicle_model_id: string;
  revision_no: number;
  status: 'draft' | 'completed' | string;
  source_dataset_key: string;
  source_master_revision_id: string;
  source_master_revision_no: number | null;
  row_count: number;
  created_by_id: string | null;
  completed_by_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleChecklistRevisionListResponse {
  items: LegacyIssueVehicleChecklistRevision[];
  latest_master_revision: LegacyIssueVehicleChecklistMasterRevision | null;
  master_revisions: LegacyIssueVehicleChecklistMasterRevision[];
}

export interface LegacyIssueVehicleChecklistRecord {
  id: string;
  checklist_revision_id: string;
  source_record_id: string;
  source_stable_record_id: string | null;
  source_module_key: LegacyIssueViewKey | string | null;
  values: Record<string, LegacyIssueFieldValue>;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleChecklistRecordListResponse {
  definition: LegacyIssueDatasetDefinition;
  items: LegacyIssueVehicleChecklistRecord[];
  revision: LegacyIssueVehicleChecklistRevision;
  total: number;
  limit: number | null;
  offset: number;
}

export interface LegacyIssueVehicleChecklistRecordBatchUpdate {
  record_id: string;
  values: Record<string, LegacyIssueFieldValue | null>;
}

export interface LegacyIssueVehicleChecklistRecordBatchSaveResponse {
  items: LegacyIssueVehicleChecklistRecord[];
  updated: number;
}

export interface LegacyIssueVehicleChecklistHistoryItem {
  id: string;
  action: string;
  record_id: string;
  record_label: string | null;
  source_module_key: LegacyIssueViewKey | string | null;
  source_master_revision_no: number | null;
  field_key: string | null;
  field_label: string | null;
  old_value: string | null;
  new_value: string | null;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface LegacyIssueVehicleChecklistHistoryResponse {
  items: LegacyIssueVehicleChecklistHistoryItem[];
  revision: LegacyIssueVehicleChecklistRevision;
}

export type LegacyIssueVehicleChecklistField = LegacyIssueDatasetField & {
  key: string;
};

export interface LegacyIssueVehicleModuleChecklist {
  id: string;
  vehicle_model_id: string;
  stage_id: string;
  module_key: LegacyIssueViewKey | string;
  status: 'draft' | 'completed' | string;
  source_dataset_key: string;
  source_master_revision_id: string;
  source_master_revision_no: number | null;
  seeded_from_checklist_id: string | null;
  row_count: number;
  created_by_id: string | null;
  completed_by_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleChecklistModuleSummary {
  module_key: LegacyIssueViewKey | string;
  latest_master_revision: LegacyIssueVehicleChecklistMasterRevision | null;
  latest_checklist: LegacyIssueVehicleModuleChecklist | null;
  checklist_count: number;
}

export interface LegacyIssueVehicleChecklistModuleListResponse {
  items: LegacyIssueVehicleChecklistModuleSummary[];
}

export interface LegacyIssueVehicleModuleChecklistListResponse {
  items: LegacyIssueVehicleModuleChecklist[];
  latest_master_revision: LegacyIssueVehicleChecklistMasterRevision | null;
  import_candidates: LegacyIssueVehicleModuleChecklistImportCandidate[];
  master_revisions: LegacyIssueVehicleChecklistMasterRevision[];
}

export interface LegacyIssueVehicleModuleChecklistImportCandidate {
  checklist: LegacyIssueVehicleModuleChecklist;
  stage: LegacyIssueVehicleStage;
  completed_by_name: string | null;
  completed_by_email: string | null;
}

export interface LegacyIssueVehicleModuleChecklistRecord {
  id: string;
  checklist_id: string;
  source_record_id: string;
  source_stable_record_id: string | null;
  values: Record<string, LegacyIssueFieldValue>;
  attachments: LegacyIssueVehicleModuleChecklistAttachment[];
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueVehicleModuleChecklistAttachment {
  id: string;
  checklist_id: string;
  record_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_id: string | null;
  created_at: string;
}

export interface LegacyIssueVehicleModuleChecklistRecordListResponse {
  definition: LegacyIssueDatasetDefinition;
  items: LegacyIssueVehicleModuleChecklistRecord[];
  checklist: LegacyIssueVehicleModuleChecklist;
  total: number;
  limit: number | null;
  offset: number;
}

export interface LegacyIssueVehicleModuleChecklistRecordBatchUpdate {
  record_id: string;
  values: Record<string, LegacyIssueFieldValue | null>;
}

export interface LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse {
  items: LegacyIssueVehicleModuleChecklistRecord[];
  updated: number;
}

export interface LegacyIssueVehicleModuleChecklistHistoryResponse {
  items: LegacyIssueVehicleChecklistHistoryItem[];
  checklist: LegacyIssueVehicleModuleChecklist;
}

function workspaceLegacyIssueVehiclePath(
  workspaceSlug: string,
  path: string,
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues${path}`;
}

export async function fetchLegacyIssueVehicleModels({
  includeInactive = false,
  query,
  token,
  workspaceSlug,
}: {
  includeInactive?: boolean;
  query?: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModelListResponse> {
  const params = new URLSearchParams();
  if (includeInactive) {
    params.set('include_inactive', 'true');
  }
  const trimmedQuery = query?.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueVehicleModelListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models${queryString}`,
    ),
    token,
  );
}

export async function createLegacyIssueVehicleModel({
  initialStageName,
  notes,
  token,
  vehicleCode,
  vehicleName,
  workspaceSlug,
}: {
  initialStageName: string;
  notes?: string | null;
  token: string;
  vehicleCode: string;
  vehicleName?: string | null;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModel> {
  return apiFetchJson<LegacyIssueVehicleModel>(
    workspaceLegacyIssueVehiclePath(workspaceSlug, '/vehicle-models'),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        initial_stage_name: initialStageName,
        notes: notes ?? null,
        vehicle_code: vehicleCode,
        vehicle_name: vehicleName ?? null,
      }),
    },
  );
}

export async function createLegacyIssueVehicleStage({
  name,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  name: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleStage> {
  return apiFetchJson<LegacyIssueVehicleStage>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}/stages`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({ name }),
    },
  );
}

export async function updateLegacyIssueVehicleStage({
  name,
  stageId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  name: string;
  stageId: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleStage> {
  return apiFetchJson<LegacyIssueVehicleStage>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(
        vehicleModelId,
      )}/stages/${encodeURIComponent(stageId)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    },
  );
}

export async function updateLegacyIssueVehicleModel({
  active,
  notes,
  token,
  vehicleCode,
  vehicleName,
  vehicleModelId,
  workspaceSlug,
}: {
  active?: boolean;
  notes?: string | null;
  token: string;
  vehicleCode?: string;
  vehicleName?: string | null;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModel> {
  return apiFetchJson<LegacyIssueVehicleModel>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({
        ...(active === undefined ? {} : { active }),
        ...(notes === undefined ? {} : { notes }),
        ...(vehicleCode === undefined ? {} : { vehicle_code: vehicleCode }),
        ...(vehicleName === undefined ? {} : { vehicle_name: vehicleName }),
      }),
    },
  );
}

export async function deleteLegacyIssueVehicleModel({
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModel> {
  return apiFetchJson<LegacyIssueVehicleModel>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function permanentlyDeleteLegacyIssueVehicleModel({
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}/permanent`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function fetchLegacyIssueVehicleChecklistRevisions({
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRevisionListResponse> {
  return apiFetchJson<LegacyIssueVehicleChecklistRevisionListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}/checklist-revisions`,
    ),
    token,
  );
}

export async function createLegacyIssueVehicleChecklistRevision({
  sourceMasterRevisionId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  sourceMasterRevisionId?: string | null;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRevision> {
  return apiFetchJson<LegacyIssueVehicleChecklistRevision>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(vehicleModelId)}/checklist-revisions`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        source_master_revision_id: sourceMasterRevisionId ?? null,
      }),
    },
  );
}

export async function fetchLegacyIssueVehicleChecklistRecords({
  query,
  revisionId,
  token,
  viewKey,
  workspaceSlug,
}: {
  query?: string;
  revisionId: string;
  token: string;
  viewKey?: LegacyIssueViewKey | null;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRecordListResponse> {
  const params = new URLSearchParams();
  const trimmedQuery = query?.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  if (viewKey) {
    params.set('view_key', viewKey);
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueVehicleChecklistRecordListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(
        revisionId,
      )}/records${queryString}`,
    ),
    token,
  );
}

export async function saveLegacyIssueVehicleChecklistRecords({
  revisionId,
  token,
  updates,
  workspaceSlug,
}: {
  revisionId: string;
  token: string;
  updates: LegacyIssueVehicleChecklistRecordBatchUpdate[];
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRecordBatchSaveResponse> {
  return apiFetchJson<LegacyIssueVehicleChecklistRecordBatchSaveResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(revisionId)}/records/batch`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ updates }),
    },
  );
}

export async function fetchLegacyIssueVehicleChecklistHistory({
  revisionId,
  token,
  workspaceSlug,
}: {
  revisionId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistHistoryResponse> {
  return apiFetchJson<LegacyIssueVehicleChecklistHistoryResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(revisionId)}/history`,
    ),
    token,
  );
}

export async function deleteLegacyIssueVehicleChecklistRevision({
  revisionId,
  token,
  workspaceSlug,
}: {
  revisionId: string;
  token: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(revisionId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function completeLegacyIssueVehicleChecklistRevision({
  revisionId,
  token,
  workspaceSlug,
}: {
  revisionId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRevision> {
  return apiFetchJson<LegacyIssueVehicleChecklistRevision>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(revisionId)}/complete`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function reopenLegacyIssueVehicleChecklistRevision({
  revisionId,
  token,
  workspaceSlug,
}: {
  revisionId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistRevision> {
  return apiFetchJson<LegacyIssueVehicleChecklistRevision>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-checklist-revisions/${encodeURIComponent(revisionId)}/reopen`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function fetchLegacyIssueVehicleChecklistModules({
  stageId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  stageId: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleChecklistModuleListResponse> {
  const params = new URLSearchParams({ stage_id: stageId });
  return apiFetchJson<LegacyIssueVehicleChecklistModuleListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(
        vehicleModelId,
      )}/checklist-modules?${params.toString()}`,
    ),
    token,
  );
}

export async function fetchLegacyIssueVehicleModuleChecklists({
  moduleKey,
  stageId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  moduleKey: string;
  stageId: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklistListResponse> {
  const params = new URLSearchParams({ stage_id: stageId });
  return apiFetchJson<LegacyIssueVehicleModuleChecklistListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(
        vehicleModelId,
      )}/checklist-modules/${encodeURIComponent(
        moduleKey,
      )}/checklists?${params.toString()}`,
    ),
    token,
  );
}

export async function createLegacyIssueVehicleModuleChecklist({
  moduleKey,
  sourceMasterRevisionId,
  stageId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  moduleKey: string;
  sourceMasterRevisionId: string;
  stageId: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklist> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklist>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(
        vehicleModelId,
      )}/checklist-modules/${encodeURIComponent(moduleKey)}/checklists`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        source_master_revision_id: sourceMasterRevisionId,
        stage_id: stageId,
      }),
    },
  );
}

export async function importPreviousStageLegacyIssueVehicleModuleChecklist({
  moduleKey,
  sourceChecklistId,
  stageId,
  token,
  vehicleModelId,
  workspaceSlug,
}: {
  moduleKey: string;
  sourceChecklistId: string;
  stageId: string;
  token: string;
  vehicleModelId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklist> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklist>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-models/${encodeURIComponent(
        vehicleModelId,
      )}/checklist-modules/${encodeURIComponent(
        moduleKey,
      )}/checklists/import-previous-stage`,
    ),
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        source_checklist_id: sourceChecklistId,
        stage_id: stageId,
      }),
    },
  );
}

export async function fetchLegacyIssueVehicleModuleChecklistRecords({
  checklistId,
  query,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  query?: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklistRecordListResponse> {
  const params = new URLSearchParams();
  const trimmedQuery = query?.trim();
  if (trimmedQuery) {
    params.set('q', trimmedQuery);
  }
  const queryString = params.toString() ? `?${params.toString()}` : '';
  return apiFetchJson<LegacyIssueVehicleModuleChecklistRecordListResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(
        checklistId,
      )}/records${queryString}`,
    ),
    token,
  );
}

export async function createLegacyIssueVehicleModuleChecklistExcelExport({
  checklistId,
  columnKeys,
  includeAttachments,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  columnKeys: string[];
  includeAttachments: boolean;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueExcelExportJob> {
  return apiFetchJson<LegacyIssueExcelExportJob>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(
        checklistId,
      )}/excel-exports`,
    ),
    token,
    {
      body: JSON.stringify({
        column_keys: columnKeys,
        include_attachments: includeAttachments,
      }),
      method: 'POST',
    },
  );
}

export async function saveLegacyIssueVehicleModuleChecklistRecords({
  checklistId,
  token,
  updates,
  workspaceSlug,
}: {
  checklistId: string;
  token: string;
  updates: LegacyIssueVehicleModuleChecklistRecordBatchUpdate[];
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklistRecordBatchSaveResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(checklistId)}/records`,
    ),
    token,
    {
      method: 'PATCH',
      body: JSON.stringify({ updates }),
    },
  );
}

export async function uploadLegacyIssueVehicleModuleChecklistAttachment({
  checklistId,
  file,
  recordId,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  file: File;
  recordId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklistAttachment> {
  const body = new FormData();
  body.append('file', file);
  return apiFetchJson<LegacyIssueVehicleModuleChecklistAttachment>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(
        checklistId,
      )}/records/${encodeURIComponent(recordId)}/attachments`,
    ),
    token,
    { body, method: 'POST' },
  );
}

export async function deleteLegacyIssueVehicleModuleChecklistAttachment({
  attachmentId,
  checklistId,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(
        checklistId,
      )}/attachments/${encodeURIComponent(attachmentId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}

export async function fetchLegacyIssueVehicleModuleChecklistAttachmentBlob({
  attachmentId,
  checklistId,
  token,
  workspaceSlug,
}: {
  attachmentId: string;
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<Blob> {
  const response = await fetch(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(
        checklistId,
      )}/attachments/${encodeURIComponent(attachmentId)}/file`,
    ),
    {
      cache: 'no-store',
      headers: jsonHeaders(token),
    },
  );
  if (response.ok) return response.blob();
  const payload = await response.json().catch(() => null);
  throw new ApiRequestError(
    response.status,
    typeof payload?.detail === 'string' ? payload.detail : '',
    payload,
  );
}

export async function fetchLegacyIssueVehicleModuleChecklistHistory({
  checklistId,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklistHistoryResponse> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklistHistoryResponse>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(checklistId)}/history`,
    ),
    token,
  );
}

export async function completeLegacyIssueVehicleModuleChecklist({
  checklistId,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklist> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklist>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(checklistId)}/complete`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function reopenLegacyIssueVehicleModuleChecklist({
  checklistId,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueVehicleModuleChecklist> {
  return apiFetchJson<LegacyIssueVehicleModuleChecklist>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(checklistId)}/reopen`,
    ),
    token,
    { method: 'POST' },
  );
}

export async function deleteLegacyIssueVehicleModuleChecklist({
  checklistId,
  token,
  workspaceSlug,
}: {
  checklistId: string;
  token: string;
  workspaceSlug: string;
}): Promise<void> {
  await apiFetchJson<void>(
    workspaceLegacyIssueVehiclePath(
      workspaceSlug,
      `/vehicle-module-checklists/${encodeURIComponent(checklistId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}
