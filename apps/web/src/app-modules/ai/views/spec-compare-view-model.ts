import { formatByteSize } from '@/src/platform/format/byte-size';

import type {
  SpecCompareJob,
  SpecCompareJobStatus,
  SpecCompareResult,
  SpecCompareSpecItem,
} from '../api/spec-compare-api';

export type ResultTab = 'report' | 'table' | 'specs' | 'evidence';

export type SubmitDisabledReason =
  | 'missing_workspace'
  | 'missing_auth'
  | 'missing_base_file'
  | 'missing_target_file'
  | 'submitting';

export type SpecCompareViewState = {
  baseFile: File | null;
  targetFile: File | null;
  jobs: SpecCompareJob[];
  selectedJob: SpecCompareJob | null;
  result: SpecCompareResult | null;
  resultTab: ResultTab;
  loadingJobs: boolean;
  submitting: boolean;
  loadingResult: boolean;
  error: string | null;
};

export type SpecCompareViewAction =
  | { type: 'baseFileChanged'; file: File | null }
  | { type: 'targetFileChanged'; file: File | null }
  | { type: 'jobsLoadStarted' }
  | { type: 'jobsLoadSucceeded'; jobs: SpecCompareJob[] }
  | { type: 'jobsLoadFailed'; message: string }
  | { type: 'jobSelected'; job: SpecCompareJob }
  | { type: 'resultTabChanged'; tab: ResultTab }
  | { type: 'resultLoadStarted'; jobId: string }
  | { type: 'resultLoadSucceeded'; jobId: string; result: SpecCompareResult }
  | { type: 'resultLoadFailed'; jobId: string; message: string }
  | { type: 'resultCleared' }
  | { type: 'pollSucceeded'; job: SpecCompareJob }
  | { type: 'pollFailed'; message: string; jobId: string }
  | { type: 'submitStarted' }
  | { type: 'submitSucceeded'; job: SpecCompareJob }
  | { type: 'submitFailed'; message: string }
  | { type: 'jobDeleted'; jobId: string }
  | { type: 'deleteFailed'; message: string }
  | { type: 'formReset' };

export type SummaryCardProjection = {
  labelKey: string;
  value: number;
};

export type SpecCompareDocumentKind = 'base' | 'target';

export type SpecCompareSpecItemRowProjection = {
  key: string;
  document: SpecCompareDocumentKind;
  itemId: string;
  category: string;
  itemName: string;
  value: string;
  condition: string;
  evidenceId: string;
  locatorLabel: string;
  sectionPath: string;
  sourceText: string;
  confidence: string;
  extractionMethod: string;
};

export type SpecCompareSpecItemsProjection = {
  baseCount: number;
  targetCount: number;
  rows: SpecCompareSpecItemRowProjection[];
};

export const ACTIVE_SPEC_COMPARE_STATUSES: SpecCompareJobStatus[] = [
  'queued',
  'running',
];

export const INITIAL_SPEC_COMPARE_VIEW_STATE: SpecCompareViewState = {
  baseFile: null,
  targetFile: null,
  jobs: [],
  selectedJob: null,
  result: null,
  resultTab: 'report',
  loadingJobs: false,
  submitting: false,
  loadingResult: false,
  error: null,
};

export function getSubmitDisabledReason(args: {
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
  baseFile: File | null;
  targetFile: File | null;
  submitting: boolean;
}): SubmitDisabledReason | null {
  if (!args.token) return 'missing_auth';
  if (!args.workspaceSlug) return 'missing_workspace';
  if (!args.baseFile) return 'missing_base_file';
  if (!args.targetFile) return 'missing_target_file';
  if (args.submitting) return 'submitting';
  return null;
}

export function canSubmitSpecCompareJob(args: {
  token: string | null | undefined;
  workspaceSlug: string | null | undefined;
  baseFile: File | null;
  targetFile: File | null;
  submitting: boolean;
}): boolean {
  return getSubmitDisabledReason(args) === null;
}

export function selectJobFromRefresh(
  jobs: SpecCompareJob[],
  selectedJob: SpecCompareJob | null,
): SpecCompareJob | null {
  if (!selectedJob) {
    return jobs[0] ?? null;
  }
  return jobs.find((job) => job.id === selectedJob.id) ?? selectedJob;
}

export function getActiveSpecCompareJob(
  selectedJob: SpecCompareJob | null,
): SpecCompareJob | null {
  return selectedJob && ACTIVE_SPEC_COMPARE_STATUSES.includes(selectedJob.status)
    ? selectedJob
    : null;
}

export function shouldClearSpecCompareResult(args: {
  selectedJob: SpecCompareJob | null;
  result: SpecCompareResult | null;
}): boolean {
  return Boolean(args.result && args.selectedJob?.status !== 'succeeded');
}

export function shouldLoadSpecCompareResult(args: {
  selectedJob: SpecCompareJob | null;
  result: SpecCompareResult | null;
}): boolean {
  const { selectedJob, result } = args;
  if (!selectedJob || selectedJob.status !== 'succeeded') {
    return false;
  }
  return result?.job.id !== selectedJob.id || result.job.updated_at !== selectedJob.updated_at;
}

export function upsertSpecCompareJob(
  jobs: SpecCompareJob[],
  nextJob: SpecCompareJob,
  options: { prepend?: boolean } = {},
): SpecCompareJob[] {
  if (options.prepend) {
    return [nextJob, ...jobs.filter((job) => job.id !== nextJob.id)];
  }

  const existingIndex = jobs.findIndex((job) => job.id === nextJob.id);
  if (existingIndex === -1) {
    return jobs;
  }
  return jobs.map((job, index) => (index === existingIndex ? nextJob : job));
}

export function removeSpecCompareJob(
  jobs: SpecCompareJob[],
  jobId: string,
): SpecCompareJob[] {
  return jobs.filter((job) => job.id !== jobId);
}

export function isCurrentSpecCompareResultJob(
  state: SpecCompareViewState,
  jobId: string,
): boolean {
  return state.selectedJob?.id === jobId;
}

export function buildSpecCompareSummaryCards(
  result: SpecCompareResult | null,
): SummaryCardProjection[] {
  const summary = result?.summary ?? {};
  return [
    { labelKey: 'ai.specCompare.summary.total', value: numberValue(summary.total_rows) },
    { labelKey: 'ai.specCompare.summary.same', value: numberValue(summary.same) },
    { labelKey: 'ai.specCompare.summary.different', value: numberValue(summary.different) },
    { labelKey: 'ai.specCompare.summary.baseOnly', value: numberValue(summary.base_only) },
    { labelKey: 'ai.specCompare.summary.targetOnly', value: numberValue(summary.target_only) },
    { labelKey: 'ai.specCompare.summary.baseSpecs', value: specItemCount(result, 'base') },
    { labelKey: 'ai.specCompare.summary.targetSpecs', value: specItemCount(result, 'target') },
  ];
}

export function buildSpecCompareSpecItemsProjection(
  result: SpecCompareResult,
): SpecCompareSpecItemsProjection {
  const baseItems = result.spec_items?.base ?? [];
  const targetItems = result.spec_items?.target ?? [];
  return {
    baseCount: baseItems.length,
    targetCount: targetItems.length,
    rows: [
      ...baseItems.map((item, index) => buildSpecCompareSpecItemRow('base', item, index)),
      ...targetItems.map((item, index) => buildSpecCompareSpecItemRow('target', item, index)),
    ],
  };
}

export function formatSpecCompareText(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed || '-';
}

export function formatSpecCompareSpecItemValue(item: SpecCompareSpecItem): string {
  const value = item.value?.trim() ?? '';
  const unit = item.unit?.trim() ?? '';
  if (!value && !unit) {
    return '-';
  }
  if (value && unit && !value.includes(unit)) {
    return `${value} ${unit}`;
  }
  return value || unit;
}

export function formatSpecCompareConfidence(value: number): string {
  if (!Number.isFinite(value)) {
    return '-';
  }
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

export function formatSpecCompareFileSize(value: number): string {
  return formatByteSize(value);
}

export function specCompareViewReducer(
  state: SpecCompareViewState,
  action: SpecCompareViewAction,
): SpecCompareViewState {
  switch (action.type) {
    case 'baseFileChanged':
      return { ...state, baseFile: action.file };
    case 'targetFileChanged':
      return { ...state, targetFile: action.file };
    case 'jobsLoadStarted':
      return { ...state, loadingJobs: true };
    case 'jobsLoadSucceeded':
      return {
        ...state,
        jobs: action.jobs,
        selectedJob: selectJobFromRefresh(action.jobs, state.selectedJob),
        loadingJobs: false,
      };
    case 'jobsLoadFailed':
      return { ...state, error: action.message, loadingJobs: false };
    case 'jobSelected':
      return {
        ...state,
        selectedJob: action.job,
        resultTab: 'report',
        loadingResult: false,
        // Drop a stale result from a different job so its data never renders
        // under the newly selected job's header while the new result loads.
        result: state.result?.job.id === action.job.id ? state.result : null,
      };
    case 'resultTabChanged':
      return { ...state, resultTab: action.tab };
    case 'resultLoadStarted':
      if (!isCurrentSpecCompareResultJob(state, action.jobId)) {
        return state;
      }
      return { ...state, loadingResult: true };
    case 'resultLoadSucceeded':
      if (
        action.result.job.id !== action.jobId
        || !isCurrentSpecCompareResultJob(state, action.jobId)
      ) {
        return state;
      }
      return {
        ...state,
        result: action.result,
        selectedJob: action.result.job,
        error: null,
        loadingResult: false,
      };
    case 'resultLoadFailed':
      if (!isCurrentSpecCompareResultJob(state, action.jobId)) {
        return state;
      }
      return { ...state, error: action.message, loadingResult: false };
    case 'resultCleared':
      return { ...state, result: null };
    case 'pollSucceeded':
      // Ignore a poll that resolved after its job was removed from the list
      // (e.g. deleted mid-poll) so a deleted job is not resurrected as selected.
      if (!state.jobs.some((job) => job.id === action.job.id)) {
        return state;
      }
      return {
        ...state,
        jobs: upsertSpecCompareJob(state.jobs, action.job),
        selectedJob: action.job,
      };
    case 'pollFailed':
      // Suppress the error banner for a job that no longer exists (deleted mid-poll).
      if (!state.jobs.some((job) => job.id === action.jobId)) {
        return state;
      }
      return { ...state, error: action.message };
    case 'submitStarted':
      return { ...state, submitting: true, error: null, result: null };
    case 'submitSucceeded':
      return {
        ...state,
        jobs: upsertSpecCompareJob(state.jobs, action.job, { prepend: true }),
        selectedJob: action.job,
        submitting: false,
      };
    case 'submitFailed':
      return { ...state, error: action.message, submitting: false };
    case 'jobDeleted': {
      const jobs = removeSpecCompareJob(state.jobs, action.jobId);
      const removedSelected = state.selectedJob?.id === action.jobId;
      return {
        ...state,
        jobs,
        selectedJob: removedSelected ? null : state.selectedJob,
        result: removedSelected ? null : state.result,
        loadingResult: removedSelected ? false : state.loadingResult,
        error: null,
      };
    }
    case 'deleteFailed':
      return { ...state, error: action.message };
    case 'formReset':
      return { ...state, baseFile: null, targetFile: null, error: null };
    default:
      return state;
  }
}

function specItemCount(result: SpecCompareResult | null, side: 'base' | 'target'): number {
  const items = result?.spec_items?.[side];
  if (Array.isArray(items)) {
    return items.length;
  }
  return numberValue(result?.summary?.[side === 'base' ? 'base_spec_items' : 'target_spec_items']);
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function buildSpecCompareSpecItemRow(
  document: SpecCompareDocumentKind,
  item: SpecCompareSpecItem,
  index: number,
): SpecCompareSpecItemRowProjection {
  const itemId = item.item_id?.trim() ?? '';
  return {
    key: `${document}-${itemId || index}`,
    document,
    itemId,
    category: formatSpecCompareText(item.category),
    itemName: formatSpecCompareText(item.item_name),
    value: formatSpecCompareSpecItemValue(item),
    condition: formatSpecCompareText(item.condition),
    evidenceId: formatSpecCompareText(item.evidence_id),
    locatorLabel: formatSpecCompareText(item.locator_label),
    sectionPath: formatSpecCompareText(item.section_path),
    sourceText: item.source_text,
    confidence: formatSpecCompareConfidence(item.confidence),
    extractionMethod: formatSpecCompareText(item.extraction_method),
  };
}
