import { describe, expect, it } from 'vitest';

import type {
  PatentPriorArtConfig,
  PatentPriorArtJob,
  PatentPriorArtSearchPlan,
} from '../api/patent-prior-art-api';
import {
  addPlanValue,
  patentPriorArtFailureMessageKey,
  patentPriorArtJobDisplayStatus,
  patentPriorArtQueryFailureMessageKey,
  removePlanValue,
  safePatentDocumentUrl,
  selectionDefaultsFromConfig,
  toggleSelectedValue,
} from './patent-prior-art-view-model';

const config: PatentPriorArtConfig = {
  allowed_upload_extensions: ['.pdf'],
  categories: [
    {
      fallback_label: 'Vehicle',
      id: 'vehicle',
      label_key: 'ai.patentPriorArt.categories.vehicle.label',
      selected_by_default: true,
    },
    {
      fallback_label: 'Communications',
      id: 'communications',
      label_key: 'catalog.communications',
      selected_by_default: false,
    },
  ],
  jurisdictions: [
    {
      fallback_label: 'South Korea',
      id: 'KR',
      label_key: 'ai.patentPriorArt.jurisdictions.KR',
      selected_by_default: true,
    },
    {
      fallback_label: 'United States',
      id: 'US',
      label_key: 'ai.patentPriorArt.jurisdictions.US',
      selected_by_default: false,
    },
  ],
  max_invention_chars: 200_000,
  max_plan_value_chars: 256,
  max_plan_values_per_field: 30,
  max_upload_bytes: 1024,
  min_invention_chars: 30,
  report_formats: ['html', 'pdf', 'docx', 'summary_pdf', 'summary_docx'],
  visual_extraction_available: false,
};

const values = (items: string[] = []) => ({
  source: 'input_derived' as const,
  values: items,
});

const plan: PatentPriorArtSearchPlan = {
  applicants: values(),
  category_ids: values(['vehicle']),
  cpc_codes: values(),
  display_query: 'heat AND exchanger',
  excluded_terms: values(),
  ipc_codes: values(['B60H']),
  keywords_en: values(['heat exchanger']),
  keywords_ko: values(['열교환기']),
};

const planValueLimits = {
  maxValueChars: config.max_plan_value_chars,
  maxValuesPerField: config.max_plan_values_per_field,
};

describe('patent prior art view model', () => {
  it('keeps the server-configured vehicle category selected by default', () => {
    expect(selectionDefaultsFromConfig(config)).toEqual({
      categoryIds: ['vehicle'],
      jurisdictionIds: ['KR'],
    });
  });

  it('toggles category and jurisdiction chips without fixed allowlists', () => {
    expect(toggleSelectedValue(['vehicle'], 'communications')).toEqual([
      'vehicle',
      'communications',
    ]);
    expect(
      toggleSelectedValue(['vehicle', 'communications'], 'vehicle'),
    ).toEqual(['communications']);
  });

  it('edits provenance-aware plan values without score aliases', () => {
    const added = addPlanValue(
      plan,
      'keywords_en',
      ' thermal management ',
      planValueLimits,
    );
    expect(added.keywords_en).toEqual({
      source: 'user',
      values: ['heat exchanger', 'thermal management'],
    });
    expect(
      addPlanValue(added, 'keywords_en', 'thermal management', planValueLimits),
    ).toBe(added);
    expect(
      removePlanValue(added, 'keywords_en', 'heat exchanger').keywords_en,
    ).toEqual({
      source: 'user',
      values: ['thermal management'],
    });
    expect(added).not.toHaveProperty('score');
  });

  it('enforces configured per-value and per-field plan limits', () => {
    const valueAtLimit = 'x'.repeat(config.max_plan_value_chars);
    const withValueAtLimit = addPlanValue(
      plan,
      'applicants',
      valueAtLimit,
      planValueLimits,
    );
    expect(withValueAtLimit.applicants.values).toEqual([valueAtLimit]);
    expect(
      addPlanValue(
        withValueAtLimit,
        'applicants',
        `${valueAtLimit}x`,
        planValueLimits,
      ),
    ).toBe(withValueAtLimit);

    const valuesAtLimit = Array.from(
      { length: config.max_plan_values_per_field },
      (_, index) => `applicant-${index + 1}`,
    );
    const fullPlan: PatentPriorArtSearchPlan = {
      ...plan,
      applicants: values(valuesAtLimit),
    };
    expect(
      addPlanValue(fullPlan, 'applicants', 'one-more', planValueLimits),
    ).toBe(fullPlan);
  });

  it('allows only web URLs for external patent documents', () => {
    expect(safePatentDocumentUrl('https://patents.example/doc/1')).toBe(
      'https://patents.example/doc/1',
    );
    expect(safePatentDocumentUrl('http://patents.example/doc/2')).toBe(
      'http://patents.example/doc/2',
    );
    expect(safePatentDocumentUrl('mailto:research@example.com')).toBeNull();
    expect(safePatentDocumentUrl('data:text/html,unsafe')).toBeNull();
    expect(
      safePatentDocumentUrl('https://user:secret@patents.example'),
    ).toBeNull();
    expect(safePatentDocumentUrl('/relative/path')).toBeNull();
  });

  it('distinguishes cleanup-pending cancellation from a regular cancellation', () => {
    const cancelledJob = {
      automatic_restart_count: 0,
      can_cancel: false,
      created_at: '2026-07-22T01:00:00Z',
      execution_attempts: 0,
      id: 'job-1',
      progress_percent: 80,
      stage: 'cleanup_pending',
      status: 'cancelled' as const,
      title: 'Research',
      updated_at: '2026-07-22T01:10:00Z',
    };

    expect(patentPriorArtJobDisplayStatus(cancelledJob)).toBe(
      'cleanup_pending',
    );
    expect(patentPriorArtJobDisplayStatus({ ...cancelledJob, stage: '' })).toBe(
      'cancelled',
    );
  });

  it('distinguishes an automatic-recovery wait from a regular queue wait', () => {
    const queuedJob: PatentPriorArtJob = {
      automatic_restart_count: 1,
      can_cancel: true,
      created_at: '2026-07-22T01:00:00Z',
      execution_attempts: 1,
      id: 'job-1',
      next_attempt_at: '2026-07-22T01:02:00Z',
      progress_percent: 10,
      stage: 'retry_waiting',
      status: 'queued',
      title: 'Research',
      updated_at: '2026-07-22T01:01:00Z',
    };

    expect(patentPriorArtJobDisplayStatus(queuedJob)).toBe('retry_waiting');
    expect(
      patentPriorArtJobDisplayStatus({ ...queuedJob, stage: 'queued' }),
    ).toBe('queued');
  });

  it('maps only safe failure codes to user-facing translation keys', () => {
    expect(patentPriorArtFailureMessageKey('provider_timeout')).toBe(
      'ai.patentPriorArt.job.failures.provider_timeout',
    );
    expect(
      patentPriorArtFailureMessageKey(
        'private_provider_detail' as PatentPriorArtJob['failure_code'],
      ),
    ).toBe('ai.patentPriorArt.job.failures.pipeline_failed');
    expect(patentPriorArtQueryFailureMessageKey('provider_timeout')).toBe(
      'ai.patentPriorArt.results.queryFailures.provider_timeout',
    );
    expect(
      patentPriorArtQueryFailureMessageKey(
        'private_query_detail' as 'provider_timeout',
      ),
    ).toBe('ai.patentPriorArt.results.queryFailures.provider_unavailable');
  });
});
