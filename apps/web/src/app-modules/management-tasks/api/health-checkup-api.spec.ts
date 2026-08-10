import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';
import { createWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-route-policy';
import { managementTasksManifest } from '../manifest';

import {
  exportTargets,
  fetchDeterminations,
  fetchSourceStatus,
  HEALTH_CHECKUP_API_PREFIX,
  HealthCheckupApiError,
  refreshDeterminations,
  uploadPriorExam,
} from './health-checkup-api';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('health checkup API client', () => {
  beforeEach(() => {
    configureWorkspaceApiRoutePolicy(
      createWorkspaceApiRoutePolicy({ sources: [managementTasksManifest] }),
    );
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.unstubAllGlobals();
  });

  it('rewrites the manifest-owned prefix for the explicit workspace', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        available: true,
        reason: null,
        run_id: 'run-1',
        captured_at: '2026-07-22T00:00:00Z',
        employee_count: 12,
        schema_version: 'erp-employee-view-v1',
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchSourceStatus({ token: 'token', workspaceSlug: 'management' });

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/workspaces/management${HEALTH_CHECKUP_API_PREFIX.slice('/api/v1'.length)}/source/status`,
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('encodes the target year and forwards cancellation', async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        run_id: 'run-1',
        status: 'ready',
        target_year: 2026,
        prior_year: 2025,
        publishable: true,
        publish_blockers: [],
        source: {
          available: true,
          reason: null,
          run_id: 'run-1',
          captured_at: '2026-07-22T00:00:00Z',
          employee_count: 0,
          schema_version: 'erp-employee-view-v1',
        },
        prior_exam_uploaded: true,
        total: 0,
        target_count: 0,
        items: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchDeterminations({
      token: 'token',
      workspaceSlug: 'management',
      year: 2026,
      signal: controller.signal,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/management/management-tasks/health-checkup/determinations?year=2026',
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it('recalculates the target year from the accepted ERP snapshot', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        run_id: 'run-2',
        status: 'preview',
        target_year: 2026,
        prior_year: 2025,
        publishable: false,
        publish_blockers: ['prior_exam_missing'],
        source: {
          available: true,
          reason: null,
          run_id: 'erp-run-1',
          captured_at: '2026-07-22T00:00:00Z',
          employee_count: 12,
          schema_version: 'erp-employee-view-v1',
        },
        prior_exam_uploaded: false,
        total: 12,
        target_count: 0,
        items: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await refreshDeterminations({
      token: 'token',
      workspaceSlug: 'management',
      year: 2026,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/management/management-tasks/health-checkup/determinations/refresh?year=2026',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('uploads the workbook as FormData without forcing a JSON content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        target_year: 2026,
        exam_year: 2025,
        source_filename: 'prior.xlsx',
        total_rows: 0,
        matched_count: 0,
        spouse_excluded_count: 0,
        unmatched_count: 0,
        ambiguous_count: 0,
        unmatched: [],
        matched: [],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await uploadPriorExam({
      token: 'token',
      workspaceSlug: 'management',
      year: 2026,
      file: new File(['workbook'], 'prior.xlsx'),
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has('Content-Type')).toBe(false);
  });

  it('preserves the HTTP status for a failed export', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ detail: 'Export is unavailable.' }, 409),
        ),
    );

    await expect(
      exportTargets({
        token: 'token',
        workspaceSlug: 'management',
        year: 2026,
      }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<HealthCheckupApiError>>({
        status: 409,
        message: 'Export is unavailable.',
      }),
    );
  });
});
