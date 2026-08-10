export interface LegacyIssueRecordHistoryItem {
  id: string;
  action: string;
  revision_id: string | null;
  revision_no: number | null;
  revision_status: string | null;
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

export interface LegacyIssueRecordHistoryResponse {
  items: LegacyIssueRecordHistoryItem[];
}

export interface LegacyIssueImportResponse {
  created: number;
  updated: number;
  skipped: number;
  total_rows: number;
}

export interface LegacyIssueImportPreviewColumn {
  index: number;
  header: string;
  sample_values: string[];
}

export interface LegacyIssueImportPreview {
  columns: LegacyIssueImportPreviewColumn[];
  preview_rows: string[][];
  suggested_mapping: Record<string, number>;
  total_preview_rows: number;
  record_id_field: string;
}

export type LegacyIssueExcelExportJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'expired';

export interface LegacyIssueExcelExportJob {
  id: string;
  status: LegacyIssueExcelExportJobStatus;
  source_kind: string;
  include_attachments: boolean;
  record_count: number;
  attachment_count: number;
  attachment_bytes: number;
  processed_attachment_count: number;
  processed_attachment_bytes: number;
  result_filename: string | null;
  result_size_bytes: number | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  expires_at: string | null;
}

export interface LegacyIssueRevision {
  id: string;
  dataset_key: string;
  revision_no: number | null;
  status: 'draft' | 'published' | 'canceled' | string;
  base_revision_id: string | null;
  note: string | null;
  locked_by_id: string | null;
  locked_by_name: string | null;
  created_by_id: string | null;
  created_by_name: string | null;
  published_by_id: string | null;
  published_by_name: string | null;
  canceled_by_id: string | null;
  canceled_by_name: string | null;
  reviewer_id: string | null;
  reviewer_name: string | null;
  reviewer_email: string | null;
  approver_id: string | null;
  approver_name: string | null;
  approver_email: string | null;
  review_requested_by_id: string | null;
  review_requested_by_name: string | null;
  approval_requested_by_id: string | null;
  approval_requested_by_name: string | null;
  reviewed_by_id: string | null;
  reviewed_by_name: string | null;
  approved_by_id: string | null;
  approved_by_name: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  canceled_at: string | null;
  review_requested_at: string | null;
  approval_requested_at: string | null;
  reviewed_at: string | null;
  approved_at: string | null;
}

export interface LegacyIssueRevisionContext {
  current: LegacyIssueRevision;
  latest_published: LegacyIssueRevision | null;
  active_draft: LegacyIssueRevision | null;
  can_direct_edit_published_revision?: boolean;
  can_force_cancel_active_draft?: boolean;
}

export interface LegacyIssueRevisionEvent {
  id: string;
  revision_id: string;
  dataset_key: string;
  action: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  note: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface LegacyIssueRevisionOverviewHistory {
  id: string;
  dataset_key: string;
  linked_revision_id: string | null;
  origin: 'imported' | 'manual' | 'system' | string;
  revision_no: number | null;
  revision_label: string | null;
  summary: string | null;
  revised_on: string | null;
  vehicle_models: string | null;
  author_user_id: string | null;
  reviewer_user_id: string | null;
  approver_user_id: string | null;
  author_name: string | null;
  reviewer_name: string | null;
  approver_name: string | null;
  source_filename: string | null;
  source_sha256: string | null;
  source_sheet: string | null;
  source_row: number | null;
  sort_order: number;
  deleted_at: string | null;
  deleted_by_id: string | null;
}

export type LegacyIssueRevisionOverviewHistoryUpdate = Pick<
  LegacyIssueRevisionOverviewHistory,
  | 'approver_name'
  | 'approver_user_id'
  | 'author_name'
  | 'author_user_id'
  | 'revised_on'
  | 'reviewer_name'
  | 'reviewer_user_id'
  | 'revision_no'
  | 'summary'
  | 'vehicle_models'
>;

export type LegacyIssueRevisionOverviewHistoryCreate =
  LegacyIssueRevisionOverviewHistoryUpdate & {
    linked_revision_id?: string | null;
  };

export interface LegacyIssueRevisionListResponse {
  items: LegacyIssueRevision[];
  events: LegacyIssueRevisionEvent[];
  overview_history: LegacyIssueRevisionOverviewHistory[];
}

export interface LegacyIssueRevisionCompareCell {
  field_key: string;
  field_label: string;
  left_value: string | null;
  right_value: string | null;
  changed: boolean;
}

export interface LegacyIssueRevisionCompareRow {
  stable_record_id: string;
  status: 'added' | 'removed' | 'modified' | 'unchanged' | string;
  label: string;
  cells: LegacyIssueRevisionCompareCell[];
}

export interface LegacyIssueRevisionCompareResponse {
  left_revision: LegacyIssueRevision;
  right_revision: LegacyIssueRevision;
  rows: LegacyIssueRevisionCompareRow[];
}
