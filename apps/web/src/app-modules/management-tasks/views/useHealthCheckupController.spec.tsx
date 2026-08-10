import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  HealthCheckupDeterminationList,
  HealthCheckupPriorExamStatus,
  HealthCheckupPriorExamUpload,
} from '../api/health-checkup-api';
import { useHealthCheckupController } from './useHealthCheckupController';

const apiMocks = vi.hoisted(() => ({
  fetchDeterminations: vi.fn(),
  fetchPriorExamStatus: vi.fn(),
  fetchSettings: vi.fn(),
  fetchSettingsHistory: vi.fn(),
  fetchSourceStatus: vi.fn(),
  refreshDeterminations: vi.fn(),
  updateSettings: vi.fn(),
  uploadPriorExam: vi.fn(),
}));
const hookMocks = vi.hoisted(() => ({
  t: (key: string) => key,
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@open-alm/ui', () => ({
  useToast: () => hookMocks.toast,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: hookMocks.t }),
}));

vi.mock('../api/health-checkup-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/health-checkup-api')>()),
  ...apiMocks,
}));

function determinations(year: number): HealthCheckupDeterminationList {
  return {
    run_id: `run-${year}`,
    status: 'ready',
    target_year: year,
    prior_year: year - 1,
    publishable: true,
    publish_blockers: [],
    source: {
      available: true,
      reason: null,
      run_id: 'source-run',
      captured_at: '2026-07-22T00:00:00Z',
      employee_count: 1,
      schema_version: 'erp-employee-view-v1',
    },
    prior_exam_uploaded: true,
    total: 0,
    target_count: 0,
    items: [],
  };
}

function priorStatus(year: number): HealthCheckupPriorExamStatus {
  return {
    exam_year: year - 1,
    uploaded: true,
    source_filename: `${year - 1}.xlsx`,
    matched_count: 1,
    uploaded_at: '2026-07-22T00:00:00Z',
    publish_blockers: [],
    details_truncated: false,
  };
}

function uploadResult(year: number): HealthCheckupPriorExamUpload {
  return {
    upload_id: `upload-${year}`,
    target_year: year,
    exam_year: year - 1,
    source_filename: `${year - 1}.xlsx`,
    total_rows: 1,
    matched_count: 1,
    spouse_excluded_count: 0,
    unmatched_count: 0,
    ambiguous_count: 0,
    publish_blockers: [],
    details_truncated: false,
    unmatched: [],
    matched: [],
  };
}

const currentSettings = {
  age_calc_method: 'korean' as const,
  senior_age: 57,
  adult_age: 40,
  service_years_threshold: 10,
  updated_by: null,
  updated_at: null,
};

describe('useHealthCheckupController', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchSourceStatus.mockResolvedValue({
      available: true,
      reason: null,
      run_id: 'source-run',
      captured_at: '2026-07-22T00:00:00Z',
      employee_count: 1,
      schema_version: 'erp-employee-view-v1',
    });
    apiMocks.fetchDeterminations.mockImplementation(({ year }) =>
      Promise.resolve(determinations(year)),
    );
    apiMocks.refreshDeterminations.mockImplementation(({ year }) =>
      Promise.resolve(determinations(year)),
    );
    apiMocks.fetchPriorExamStatus.mockImplementation(({ year }) =>
      Promise.resolve(priorStatus(year)),
    );
    apiMocks.uploadPriorExam.mockImplementation(({ year }) =>
      Promise.resolve(uploadResult(year)),
    );
    apiMocks.fetchSettings.mockResolvedValue(currentSettings);
    apiMocks.fetchSettingsHistory.mockResolvedValue({ items: [] });
    apiMocks.updateSettings.mockResolvedValue(currentSettings);
  });

  it('clears prior-year upload and determination state when the year changes', async () => {
    const rendered = renderHook(
      ({ year }) =>
        useHealthCheckupController({
          settingsActive: false,
          token: 'token',
          workspaceSlug: 'management',
          year,
        }),
      { initialProps: { year: 2026 } },
    );

    await waitFor(() =>
      expect(rendered.result.current.determinations?.target_year).toBe(2026),
    );

    await act(async () => {
      await rendered.result.current.uploadPriorExamFile(
        new File(['workbook'], 'prior.xlsx'),
      );
    });
    expect(rendered.result.current.uploadResult?.target_year).toBe(2026);
    expect(rendered.result.current.priorStatus?.exam_year).toBe(2025);

    rendered.rerender({ year: 2027 });

    expect(rendered.result.current.determinations).toBeNull();
    expect(rendered.result.current.priorStatus).toBeNull();
    expect(rendered.result.current.uploadResult).toBeNull();
    expect(rendered.result.current.loadingDeterminations).toBe(true);

    await waitFor(() =>
      expect(rendered.result.current.determinations?.target_year).toBe(2027),
    );
    expect(rendered.result.current.priorStatus?.exam_year).toBe(2026);
    expect(rendered.result.current.uploadResult).toBeNull();
  });

  it('ignores a prior-year upload response that finishes after the year changes', async () => {
    let resolveUpload!: (result: HealthCheckupPriorExamUpload) => void;
    apiMocks.uploadPriorExam.mockImplementationOnce(
      () =>
        new Promise<HealthCheckupPriorExamUpload>((resolve) => {
          resolveUpload = resolve;
        }),
    );
    const rendered = renderHook(
      ({ year }) =>
        useHealthCheckupController({
          settingsActive: false,
          token: 'token',
          workspaceSlug: 'management',
          year,
        }),
      { initialProps: { year: 2026 } },
    );
    await waitFor(() =>
      expect(rendered.result.current.determinations?.target_year).toBe(2026),
    );

    let pendingUpload = Promise.resolve();
    act(() => {
      pendingUpload = rendered.result.current.uploadPriorExamFile(
        new File(['workbook'], 'prior.xlsx'),
      );
    });
    await waitFor(() => expect(rendered.result.current.uploading).toBe(true));

    rendered.rerender({ year: 2027 });
    expect(rendered.result.current.uploading).toBe(false);
    await act(async () => {
      resolveUpload(uploadResult(2026));
      await pendingUpload;
    });

    expect(rendered.result.current.uploadResult).toBeNull();
    expect(hookMocks.toast.success).not.toHaveBeenCalled();
  });

  it('recalculates the active year when a settings save finishes after a year change', async () => {
    let resolveSettings!: (result: typeof currentSettings) => void;
    apiMocks.updateSettings.mockImplementationOnce(
      () =>
        new Promise<typeof currentSettings>((resolve) => {
          resolveSettings = resolve;
        }),
    );
    const rendered = renderHook(
      ({ year }) =>
        useHealthCheckupController({
          settingsActive: false,
          token: 'token',
          workspaceSlug: 'management',
          year,
        }),
      { initialProps: { year: 2026 } },
    );
    await waitFor(() =>
      expect(rendered.result.current.determinations?.target_year).toBe(2026),
    );

    let pendingSave = Promise.resolve();
    act(() => {
      pendingSave = rendered.result.current.saveSettings({ senior_age: 61 });
    });
    rendered.rerender({ year: 2027 });
    await waitFor(() =>
      expect(rendered.result.current.determinations?.target_year).toBe(2027),
    );

    await act(async () => {
      resolveSettings({ ...currentSettings, senior_age: 61 });
      await pendingSave;
    });

    expect(apiMocks.refreshDeterminations).toHaveBeenCalledWith(
      expect.objectContaining({ year: 2027 }),
    );
    expect(
      apiMocks.refreshDeterminations.mock.calls.some(
        ([request]) => request.year === 2026,
      ),
    ).toBe(false);
    expect(rendered.result.current.determinations?.target_year).toBe(2027);
  });
});
