import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  patentPriorArtApi,
  type PatentPriorArtApi,
  type PatentPriorArtConfig,
  type PatentPriorArtFileParseResult,
  type PatentPriorArtJob,
  type PatentPriorArtPreview,
} from '../api/patent-prior-art-api';
import { usePatentPriorArtController } from './usePatentPriorArtController';

const config: PatentPriorArtConfig = {
  allowed_upload_extensions: ['.pdf'],
  categories: [
    {
      fallback_label: 'Vehicle',
      id: 'vehicle',
      label_key: 'ai.patentPriorArt.categories.vehicle.label',
      selected_by_default: true,
    },
  ],
  jurisdictions: [
    {
      fallback_label: 'South Korea',
      id: 'KR',
      label_key: 'ai.patentPriorArt.jurisdictions.KR',
      selected_by_default: true,
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

const completedJob: PatentPriorArtJob = {
  automatic_restart_count: 0,
  can_cancel: false,
  created_at: '2026-07-22T01:00:00Z',
  execution_attempts: 0,
  id: 'job-1',
  progress_percent: 100,
  stage: '',
  status: 'succeeded',
  title: 'Research',
  updated_at: '2026-07-22T01:10:00Z',
};

const searchValues = (values: string[] = []) => ({
  source: 'input_derived' as const,
  values,
});

const preview: PatentPriorArtPreview = {
  plan: {
    applicants: searchValues(),
    category_ids: searchValues(['vehicle']),
    cpc_codes: searchValues(),
    display_query: 'heat AND exchanger',
    excluded_terms: searchValues(),
    ipc_codes: searchValues(['B60H']),
    keywords_en: searchValues(['heat exchanger']),
    keywords_ko: searchValues(['열교환기']),
  },
  source_queries: [
    {
      jurisdiction: 'KR',
      query_text: 'heat AND exchanger',
      source_id: 'google-patents',
      source_label: 'Google Patents',
    },
  ],
  technology_summary: 'Vehicle thermal-management invention summary.',
};

describe('usePatentPriorArtController session isolation', () => {
  it('round-trips the preview technology summary into job creation', async () => {
    const createJob = vi.fn().mockResolvedValue({
      ...completedJob,
      status: 'failed' as const,
    });
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      createJob,
      getConfig: vi.fn().mockResolvedValue(config),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      previewQuery: vi.fn().mockResolvedValue(preview),
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => {
      result.current.setTitle('  Thermal research  ');
      result.current.setInventionText(
        'A sufficiently detailed invention description for preview.',
      );
    });

    await act(async () => {
      await result.current.createPreview();
    });
    await act(async () => {
      await result.current.createJob();
    });

    expect(createJob).toHaveBeenCalledWith({
      request: {
        idempotency_key: expect.any(String),
        invention_text:
          'A sufficiently detailed invention description for preview.',
        jurisdictions: ['KR'],
        search_plan: preview.plan,
        technology_summary: preview.technology_summary,
        title: 'Thermal research',
      },
      token: 'token',
      workspaceSlug: 'workspace',
    });
  });

  it('reuses the idempotency key when the same failed submission is retried', async () => {
    const createJob = vi
      .fn()
      .mockRejectedValueOnce(new Error('connection interrupted'))
      .mockResolvedValue(completedJob);
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      createJob,
      getConfig: vi.fn().mockResolvedValue(config),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      previewQuery: vi.fn().mockResolvedValue(preview),
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => {
      result.current.setInventionText(
        'A sufficiently detailed invention description for retry.',
      );
    });
    await act(async () => {
      await result.current.createPreview();
    });
    await act(async () => {
      await result.current.createJob();
    });
    await act(async () => {
      await result.current.createJob();
    });

    const firstKey = createJob.mock.calls[0]?.[0].request.idempotency_key;
    const secondKey = createJob.mock.calls[1]?.[0].request.idempotency_key;
    expect(firstKey).toEqual(expect.any(String));
    expect(secondKey).toBe(firstKey);
  });

  it('clears stale generated queries after a valid plan-chip edit', async () => {
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      getConfig: vi.fn().mockResolvedValue(config),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      previewQuery: vi.fn().mockResolvedValue(preview),
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() =>
      result.current.setInventionText(
        'A sufficiently detailed invention description for preview.',
      ),
    );
    await act(async () => {
      await result.current.createPreview();
    });

    act(() => {
      result.current.addPlanValue('keywords_en', 'thermal management');
    });

    expect(result.current.preview?.plan.keywords_en.values).toEqual([
      'heat exchanger',
      'thermal management',
    ]);
    expect(result.current.preview?.plan.display_query).toBe('');
    expect(result.current.preview?.source_queries).toEqual([]);
  });

  it('aborts and releases preview busy state when preview inputs change', async () => {
    const previewSignals: AbortSignal[] = [];
    const previewQuery: PatentPriorArtApi['previewQuery'] = vi.fn(
      (args) =>
        new Promise<PatentPriorArtPreview>((_resolve, reject) => {
          if (!args.signal) {
            reject(new Error('Missing preview abort signal'));
            return;
          }
          previewSignals.push(args.signal);
          args.signal.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true },
          );
        }),
    );
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      getConfig: vi.fn().mockResolvedValue(config),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      previewQuery,
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() =>
      result.current.setInventionText(
        'A sufficiently detailed invention description for preview.',
      ),
    );

    const mutations = [
      () =>
        result.current.setInventionText(
          'A changed invention description that invalidates preview.',
        ),
      () => result.current.toggleCategory('vehicle'),
      () => result.current.toggleJurisdiction('KR'),
    ];

    for (const mutate of mutations) {
      act(() => {
        void result.current.createPreview();
      });
      await waitFor(() => expect(result.current.busyAction).toBe('preview'));
      const signal = previewSignals[previewSignals.length - 1];

      act(mutate);

      await waitFor(() => expect(result.current.busyAction).toBeNull());
      expect(signal?.aborted).toBe(true);
      expect(result.current.preview).toBeNull();
    }
  });

  it('resets state and discards a file response from an old workspace/token', async () => {
    let resolveParse:
      | ((result: PatentPriorArtFileParseResult) => void)
      | undefined;
    const parseFile = vi.fn(
      () =>
        new Promise<PatentPriorArtFileParseResult>((resolve) => {
          resolveParse = resolve;
        }),
    );
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      getConfig: vi.fn().mockResolvedValue(config),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      parseFile,
    };
    const { result, rerender } = renderHook(
      ({ token, workspaceSlug }) =>
        usePatentPriorArtController({ api, token, workspaceSlug }),
      {
        initialProps: { token: 'token-1', workspaceSlug: 'workspace-1' },
      },
    );

    await waitFor(() => expect(result.current.config).not.toBeNull());
    act(() => result.current.setInventionText('Existing invention details'));
    act(() => {
      void result.current.parseFile(new File(['pdf'], 'invention.pdf'));
    });

    rerender({ token: 'token-2', workspaceSlug: 'workspace-2' });
    await waitFor(() => {
      expect(result.current.inventionText).toBe('');
      expect(result.current.categoryIds).toEqual(['vehicle']);
    });

    await act(async () => {
      resolveParse?.({
        character_count: 22,
        embedded_object_count: 0,
        extracted_text: 'Old workspace content',
        filename: 'invention.pdf',
        mime_type: 'application/pdf',
        warnings: [],
      });
      await Promise.resolve();
    });

    expect(result.current.inventionText).toBe('');
    expect(result.current.parsedFile).toBeNull();
  });

  it('retains history when the delete contract reports no deletion', async () => {
    const deleteJob = vi
      .fn()
      .mockResolvedValueOnce({ deleted: false, id: completedJob.id })
      .mockResolvedValueOnce({ deleted: true, id: completedJob.id });
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      deleteJob,
      getConfig: vi.fn().mockResolvedValue(config),
      getJob: vi.fn().mockResolvedValue({
        ...completedJob,
        stage: 'cleanup_pending',
        status: 'cancelled',
      }),
      listJobs: vi.fn().mockResolvedValue({ items: [completedJob], total: 1 }),
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.history).toHaveLength(1));

    await act(async () => {
      await result.current.deleteJob(completedJob);
    });
    expect(result.current.history).toEqual([
      expect.objectContaining({
        id: completedJob.id,
        stage: 'cleanup_pending',
        status: 'cancelled',
      }),
    ]);
    expect(result.current.issue).toBe('delete');

    await act(async () => {
      await result.current.deleteJob(completedJob);
    });
    expect(result.current.history).toEqual([]);
  });

  it('does not clear a newly selected job result when another deletion resolves late', async () => {
    const jobA = { ...completedJob, id: 'job-a', title: 'Research A' };
    const jobB = { ...completedJob, id: 'job-b', title: 'Research B' };
    let resolveDeletion:
      | ((result: { deleted: boolean; id: string }) => void)
      | undefined;
    const deleteJob = vi.fn(
      () =>
        new Promise<{ deleted: boolean; id: string }>((resolve) => {
          resolveDeletion = resolve;
        }),
    );
    const api: PatentPriorArtApi = {
      ...patentPriorArtApi,
      deleteJob,
      getConfig: vi.fn().mockResolvedValue(config),
      getResult: vi.fn().mockResolvedValue({
        artifacts: [],
        candidate_count: 0,
        candidates: [],
        executed_queries: [],
        job: jobB,
        report_markdown: 'Research B result',
      }),
      listJobs: vi.fn().mockResolvedValue({
        items: [jobA, jobB],
        total: 2,
      }),
    };
    const { result } = renderHook(() =>
      usePatentPriorArtController({
        api,
        token: 'token',
        workspaceSlug: 'workspace',
      }),
    );
    await waitFor(() => expect(result.current.history).toHaveLength(2));

    let deletion: Promise<void> | undefined;
    act(() => {
      deletion = result.current.deleteJob(jobA);
      result.current.selectJob(jobB);
    });
    await waitFor(() => expect(result.current.result?.job.id).toBe(jobB.id));

    await act(async () => {
      resolveDeletion?.({ deleted: true, id: jobA.id });
      await deletion;
    });

    expect(result.current.activeJob?.id).toBe(jobB.id);
    expect(result.current.result?.job.id).toBe(jobB.id);
    expect(result.current.history.map((job) => job.id)).toEqual([jobB.id]);
  });
});
