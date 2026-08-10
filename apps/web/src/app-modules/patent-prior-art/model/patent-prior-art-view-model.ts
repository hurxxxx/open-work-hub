import type {
  PatentPriorArtConfig,
  PatentPriorArtFailureCode,
  PatentPriorArtJob,
  PatentPriorArtQueryFailureCode,
  PatentPriorArtSearchPlan,
} from '../api/patent-prior-art-api';

export const EDITABLE_PLAN_FIELDS = [
  'keywords_ko',
  'keywords_en',
  'ipc_codes',
  'cpc_codes',
  'applicants',
  'excluded_terms',
] as const satisfies readonly (keyof PatentPriorArtSearchPlan)[];

export type EditablePlanField = (typeof EDITABLE_PLAN_FIELDS)[number];

export interface PatentPriorArtSelectionDefaults {
  categoryIds: string[];
  jurisdictionIds: string[];
}

export interface PatentPriorArtPlanValueLimits {
  maxValueChars: number;
  maxValuesPerField: number;
}

export function selectionDefaultsFromConfig(
  config: PatentPriorArtConfig,
): PatentPriorArtSelectionDefaults {
  return {
    categoryIds: config.categories
      .filter((option) => option.selected_by_default)
      .map((option) => option.id),
    jurisdictionIds: config.jurisdictions
      .filter((option) => option.selected_by_default)
      .map((option) => option.id),
  };
}

export function toggleSelectedValue(
  values: readonly string[],
  value: string,
): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export function addPlanValue(
  plan: PatentPriorArtSearchPlan,
  field: EditablePlanField,
  rawValue: string,
  limits: PatentPriorArtPlanValueLimits,
): PatentPriorArtSearchPlan {
  const value = rawValue.trim();
  const values = plan[field].values ?? [];
  if (
    !value ||
    value.length > limits.maxValueChars ||
    values.length >= limits.maxValuesPerField ||
    values.includes(value)
  ) {
    return plan;
  }
  return {
    ...plan,
    [field]: {
      source: 'user',
      values: [...values, value],
    },
  };
}

export function removePlanValue(
  plan: PatentPriorArtSearchPlan,
  field: EditablePlanField,
  value: string,
): PatentPriorArtSearchPlan {
  const values = plan[field].values ?? [];
  if (!values.includes(value)) {
    return plan;
  }
  return {
    ...plan,
    [field]: {
      source: 'user',
      values: values.filter((item) => item !== value),
    },
  };
}

export function isTerminalPatentPriorArtJob(job: PatentPriorArtJob): boolean {
  return ['succeeded', 'failed', 'cancelled'].includes(job.status);
}

export type PatentPriorArtJobDisplayStatus =
  | PatentPriorArtJob['status']
  | 'cleanup_pending'
  | 'retry_waiting';

export function patentPriorArtJobDisplayStatus(
  job: PatentPriorArtJob,
): PatentPriorArtJobDisplayStatus {
  if (job.status === 'cancelled' && job.stage === 'cleanup_pending') {
    return 'cleanup_pending';
  }
  if (
    (job.status === 'queued' || job.status === 'running') &&
    job.stage === 'retry_waiting'
  ) {
    return 'retry_waiting';
  }
  return job.status;
}

export type PatentPriorArtFailureMessageKey =
  `ai.patentPriorArt.job.failures.${PatentPriorArtFailureCode}`;

export function patentPriorArtFailureMessageKey(
  failureCode: PatentPriorArtJob['failure_code'],
): PatentPriorArtFailureMessageKey {
  switch (failureCode) {
    case 'access_revoked':
    case 'provider_timeout':
    case 'worker_lost':
      return `ai.patentPriorArt.job.failures.${failureCode}`;
    case 'pipeline_failed':
    default:
      return 'ai.patentPriorArt.job.failures.pipeline_failed';
  }
}

export type PatentPriorArtQueryFailureMessageKey =
  `ai.patentPriorArt.results.queryFailures.${PatentPriorArtQueryFailureCode}`;

export function patentPriorArtQueryFailureMessageKey(
  failureCode: PatentPriorArtQueryFailureCode | null | undefined,
): PatentPriorArtQueryFailureMessageKey {
  return failureCode === 'provider_timeout'
    ? 'ai.patentPriorArt.results.queryFailures.provider_timeout'
    : 'ai.patentPriorArt.results.queryFailures.provider_unavailable';
}

export function safePatentDocumentUrl(
  value: string | null | undefined,
): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (
      (url.protocol !== 'https:' && url.protocol !== 'http:') ||
      url.username ||
      url.password
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

export function upsertJob(
  jobs: readonly PatentPriorArtJob[],
  job: PatentPriorArtJob,
): PatentPriorArtJob[] {
  const remaining = jobs.filter((item) => item.id !== job.id);
  return [job, ...remaining].sort(
    (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at),
  );
}
