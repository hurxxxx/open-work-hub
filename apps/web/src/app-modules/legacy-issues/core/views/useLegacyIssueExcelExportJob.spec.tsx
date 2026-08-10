import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiRequestError } from '@/src/platform/api/client';
import type { LegacyIssueExcelExportJob } from '../api/legacy-issue-common-api';
import {
  legacyIssueExcelExportStorageKey,
  useLegacyIssueExcelExportJob,
} from './useLegacyIssueExcelExportJob';

describe('legacy issue Excel export job workflow', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('persists a created job, polls it, and downloads the completed workbook', async () => {
    const createJob = vi
      .fn()
      .mockResolvedValue(exportJob({ status: 'queued' }));
    const fetchJob = vi
      .fn()
      .mockResolvedValue(exportJob({ status: 'completed' }));
    const fetchFile = vi.fn().mockResolvedValue(new Blob(['xlsx']));
    const onFile = vi.fn();
    const storageKey = legacyIssueExcelExportStorageKey({
      sourceKey: 'dataset:master:aircon:revision-1',
      userId: 'user-1',
      workspaceSlug: 'research',
    });
    const { result } = renderHook(() =>
      useLegacyIssueExcelExportJob({
        createJob,
        fallbackFilename: 'fallback.xlsx',
        fetchFile,
        fetchJob,
        onFile,
        sourceKey: 'dataset:master:aircon:revision-1',
        userId: 'user-1',
        workspaceSlug: 'research',
      }),
    );

    await act(() => result.current.start());

    await waitFor(() => expect(onFile).toHaveBeenCalledTimes(1));
    expect(createJob).toHaveBeenCalledWith(false);
    expect(fetchJob).toHaveBeenCalledWith('job-1');
    expect(fetchFile).toHaveBeenCalledWith('job-1');
    expect(onFile).toHaveBeenCalledWith(
      expect.any(Blob),
      'generated.xlsx',
      expect.objectContaining({ id: 'job-1', status: 'completed' }),
    );
    expect(window.localStorage.getItem(storageKey)).toBeNull();
    expect(result.current.busy).toBe(false);
  });

  it('recovers only the job stored for the same user, workspace, and source', async () => {
    const sourceKey = 'checklist:check-17';
    const storageKey = legacyIssueExcelExportStorageKey({
      sourceKey,
      userId: 'user-1',
      workspaceSlug: 'research',
    });
    window.localStorage.setItem(storageKey, 'restored-job');
    const createJob = vi.fn();
    const fetchJob = vi
      .fn()
      .mockResolvedValue(
        exportJob({ id: 'restored-job', status: 'completed' }),
      );
    const fetchFile = vi.fn().mockResolvedValue(new Blob(['xlsx']));
    const onFile = vi.fn();

    renderHook(() =>
      useLegacyIssueExcelExportJob({
        createJob,
        fallbackFilename: 'fallback.xlsx',
        fetchFile,
        fetchJob,
        onFile,
        sourceKey,
        userId: 'user-1',
        workspaceSlug: 'research',
      }),
    );

    await waitFor(() => expect(onFile).toHaveBeenCalledTimes(1));
    expect(createJob).not.toHaveBeenCalled();
    expect(fetchJob).toHaveBeenCalledWith('restored-job');
    expect(window.localStorage.getItem(storageKey)).toBeNull();
    expect(
      legacyIssueExcelExportStorageKey({
        sourceKey,
        userId: 'user-2',
        workspaceSlug: 'research',
      }),
    ).not.toBe(storageKey);
    expect(
      legacyIssueExcelExportStorageKey({
        sourceKey: 'checklist:check-18',
        userId: 'user-1',
        workspaceSlug: 'research',
      }),
    ).not.toBe(storageKey);
  });

  it('creates only one job when start is invoked twice before a rerender', async () => {
    const createJob = vi
      .fn()
      .mockResolvedValue(exportJob({ status: 'queued' }));
    const fetchJob = vi
      .fn()
      .mockResolvedValue(exportJob({ status: 'completed' }));
    const onFile = vi.fn();
    const { result } = renderHook(() =>
      useLegacyIssueExcelExportJob({
        createJob,
        fallbackFilename: 'fallback.xlsx',
        fetchFile: vi.fn().mockResolvedValue(new Blob(['xlsx'])),
        fetchJob,
        onFile,
        sourceKey: 'dataset:master:aircon:revision-1',
        userId: 'user-1',
        workspaceSlug: 'research',
      }),
    );

    await act(async () => {
      await Promise.all([result.current.start(), result.current.start()]);
    });

    await waitFor(() => expect(onFile).toHaveBeenCalledTimes(1));
    expect(createJob).toHaveBeenCalledTimes(1);
  });

  it('clears a stored job that no longer exists so a new export can start', async () => {
    const sourceKey = 'dataset:master:aircon:revision-1';
    const storageKey = legacyIssueExcelExportStorageKey({
      sourceKey,
      userId: 'user-1',
      workspaceSlug: 'research',
    });
    window.localStorage.setItem(storageKey, 'missing-job');
    const createJob = vi
      .fn()
      .mockResolvedValue(
        exportJob({ id: 'replacement-job', status: 'queued' }),
      );
    const fetchJob = vi
      .fn()
      .mockRejectedValueOnce(new ApiRequestError(404, 'Not found'))
      .mockResolvedValue(
        exportJob({ id: 'replacement-job', status: 'completed' }),
      );
    const onFailed = vi.fn();
    const onFile = vi.fn();
    const { result } = renderHook(() =>
      useLegacyIssueExcelExportJob({
        createJob,
        fallbackFilename: 'fallback.xlsx',
        fetchFile: vi.fn().mockResolvedValue(new Blob(['xlsx'])),
        fetchJob,
        onFailed,
        onFile,
        sourceKey,
        userId: 'user-1',
        workspaceSlug: 'research',
      }),
    );

    await waitFor(() => expect(result.current.busy).toBe(false));
    expect(window.localStorage.getItem(storageKey)).toBeNull();
    expect(onFailed).toHaveBeenCalledWith('poll', expect.any(ApiRequestError));

    await act(() => result.current.start());

    await waitFor(() => expect(onFile).toHaveBeenCalledTimes(1));
    expect(createJob).toHaveBeenCalledTimes(1);
  });
});

function exportJob(
  overrides: Partial<LegacyIssueExcelExportJob> = {},
): LegacyIssueExcelExportJob {
  return {
    attachment_bytes: 0,
    attachment_count: 0,
    completed_at: null,
    created_at: '2026-07-15T00:00:00Z',
    error_code: null,
    expires_at: null,
    id: 'job-1',
    include_attachments: false,
    processed_attachment_bytes: 0,
    processed_attachment_count: 0,
    record_count: 1,
    result_filename: 'generated.xlsx',
    result_size_bytes: 4,
    source_kind: 'dataset',
    status: 'queued',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}
