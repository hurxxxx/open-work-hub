import { apiFetchJson } from '@/src/platform/api/client';
import type { LegacyIssueDatasetKey } from '../legacy-issue-datasets';

export interface LegacyIssueAssistantPlan {
  query: string;
  dataset_keys: string[];
  keywords: string[];
  field_hints: string[];
  intent: string;
  report_focus: string[];
}

export interface LegacyIssueAssistantMatchedChunk {
  chunk_id: string;
  chunk_key: string;
  chunk_kind: string;
  field_key: string | null;
  field_label: string | null;
  field_value: string | null;
  attachment_id?: string | null;
  attachment_filename?: string | null;
  attachment_page?: number | null;
  attachment_artifact_type?: string | null;
  excerpt: string;
  methods: string[];
  score: number;
}

export interface LegacyIssueAssistantEvidenceAttachment {
  id: string;
  filename: string;
  description: string | null;
  content_type: string;
  size_bytes: number;
  index_status: string;
  indexed_at: string | null;
  matched_chunks: LegacyIssueAssistantMatchedChunk[];
  score: number;
  methods: string[];
}

export interface LegacyIssueAssistantEvidence {
  evidence_id: string;
  dataset_key: LegacyIssueDatasetKey | string;
  dataset_title: string;
  revision_id: string | null;
  revision_no: number | null;
  record_id: string;
  stable_record_id: string | null;
  label: string;
  values: Record<string, string>;
  matched_fields: string[];
  matched_chunks: LegacyIssueAssistantMatchedChunk[];
  attachments?: LegacyIssueAssistantEvidenceAttachment[];
  score: number;
  methods: string[];
}

export interface LegacyIssueAssistantEvidenceRef {
  id: string;
  dataset_key: LegacyIssueDatasetKey | string;
  dataset_title?: string | null;
  revision_id?: string | null;
  revision_no?: number | null;
  record_id: string;
  source_record_id?: string | null;
  stable_record_id?: string | null;
  label?: string | null;
  matched_fields?: string[];
  matched_chunks?: LegacyIssueAssistantMatchedChunk[];
  score?: number;
  methods?: string[];
}

export interface LegacyIssueAssistantSearchProfile {
  semantic_enabled: boolean;
  vector_extension_available: boolean;
  vector_index_available: boolean;
  trigram_extension_available: boolean;
  full_text_enabled: boolean;
  searched_dataset_keys: string[];
  searched_revision_ids: string[];
  candidate_count: number;
  evidence_count: number;
  methods: string[];
}

export interface LegacyIssueAssistantDecision {
  task_kind: string;
  policy: string;
  chosen_pool: string;
  provider: string;
  model: string;
  reason_codes: string[];
  forced_local: boolean;
  context_strategy: string;
  estimated_input_tokens: number | null;
  max_tokens: number;
}

export interface LegacyIssueAssistantRunResponse {
  run_id: string;
  question: string | null;
  created_at: string | null;
  requested_by_id: string | null;
  requested_by_name: string | null;
  requested_by_email: string | null;
  answer_markdown: string;
  analysis_plan: LegacyIssueAssistantPlan;
  analysis_result: Record<string, unknown> | null;
  evidence: LegacyIssueAssistantEvidence[];
  search_profile: LegacyIssueAssistantSearchProfile;
  gateway_decisions: LegacyIssueAssistantDecision[];
}

export interface LegacyIssueAssistantRunSummary {
  run_id: string;
  question: string;
  answer_preview: string;
  created_at: string;
  requested_by_id: string | null;
  requested_by_name: string | null;
  requested_by_email: string | null;
  evidence_count: number;
  dataset_keys: string[];
  methods: string[];
}

export interface LegacyIssueAssistantRunListResponse {
  items: LegacyIssueAssistantRunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface LegacyIssueAssistantEvidenceResolveResponse {
  retrieval_profile: Record<string, unknown>;
  evidence: LegacyIssueAssistantEvidence[];
}

export async function runLegacyIssueAssistant({
  datasetKeys,
  evidenceLimit,
  question,
  token,
  workspaceSlug,
}: {
  datasetKeys?: LegacyIssueDatasetKey[];
  evidenceLimit?: number;
  question: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueAssistantRunResponse> {
  return apiFetchJson<LegacyIssueAssistantRunResponse>(
    `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}/legacy-issues/assistant/runs`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        question,
        dataset_keys: datasetKeys?.length ? datasetKeys : undefined,
        evidence_limit: evidenceLimit,
      }),
    },
  );
}

export async function listLegacyIssueAssistantRuns({
  limit = 30,
  offset = 0,
  token,
  workspaceSlug,
}: {
  limit?: number;
  offset?: number;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueAssistantRunListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiFetchJson<LegacyIssueAssistantRunListResponse>(
    `/api/v1/workspaces/${encodeURIComponent(
      workspaceSlug,
    )}/legacy-issues/assistant/runs?${params.toString()}`,
    token,
  );
}

export async function getLegacyIssueAssistantRun({
  runId,
  token,
  workspaceSlug,
}: {
  runId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueAssistantRunResponse> {
  return apiFetchJson<LegacyIssueAssistantRunResponse>(
    `/api/v1/workspaces/${encodeURIComponent(
      workspaceSlug,
    )}/legacy-issues/assistant/runs/${encodeURIComponent(runId)}`,
    token,
  );
}

export async function resolveLegacyIssueAssistantEvidence({
  evidenceRefs,
  retrievalProfile,
  token,
  workspaceSlug,
}: {
  evidenceRefs: LegacyIssueAssistantEvidenceRef[];
  retrievalProfile?: Record<string, unknown>;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueAssistantEvidenceResolveResponse> {
  return apiFetchJson<LegacyIssueAssistantEvidenceResolveResponse>(
    `/api/v1/workspaces/${encodeURIComponent(
      workspaceSlug,
    )}/legacy-issues/assistant/evidence/resolve`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        retrieval_profile: retrievalProfile ?? {},
        evidence_refs: evidenceRefs,
      }),
    },
  );
}
