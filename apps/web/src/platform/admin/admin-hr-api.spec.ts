import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  archiveAdminHrWorkforceCategory,
  createAdminHrManualMatch,
  createAdminHrWorkforceCategory,
  getAdminHrEmployee,
  getAdminHrMasterStatus,
  listAdminHrManualMatchCandidates,
  listAdminHrEmployees,
  listAdminHrWorkforceCategories,
  resetAdminHrEmployeeWorkforceCategory,
  revokeAdminHrManualMatch,
  setAdminHrEmployeeWorkforceCategory,
  updateAdminHrWorkforceCategory,
} from './admin-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('admin unified HR API', () => {
  it('sends server pagination, search, and reconciliation filters', async () => {
    const payload = {
      latest_run: null,
      status_counts: {},
      items: [],
      total: 0,
      page: 2,
      page_size: 50,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      listAdminHrEmployees('token', {
        page: 2,
        page_size: 50,
        q: ' E100 ',
        reconciliation_status: 'identity_conflict',
        workforce_category: 'unresolved',
        identity_resolution_kind: 'manual',
        group_code: ' R&D ',
        group_source: 'erp',
      }),
    ).resolves.toEqual(payload);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/admin/hr/employees?page=2&page_size=50&q=E100&reconciliation_status=identity_conflict&workforce_category=unresolved&identity_resolution_kind=manual&group_code=R%26D&group_source=erp',
    );
  });

  it('loads the latest unified HR projection attempt status', async () => {
    const payload = {
      latest_succeeded: null,
      latest_attempt: {
        id: 'run-2',
        status: 'failed',
        completed_at: '2026-07-29T07:29:22Z',
        source_erp_run_id: 'erp-1',
        source_groupware_run_id: 'gw-1',
        identity_resolution_revision: 1,
        error_code: 'unexpected_build_error',
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getAdminHrMasterStatus('token')).resolves.toEqual(payload);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/admin/hr/master-status');
  });

  it('encodes the record id when loading safe comparison details', async () => {
    const payload = {
      record_id: 'record/1',
      record_kind: 'person',
      employee_code: 'E100',
      name: 'Employee',
      has_erp: true,
      has_groupware: true,
      reconciliation_status: 'matched',
      applied_at: '2026-07-29T03:30:00Z',
      erp: null,
      groupware: null,
      conflict_reasons: [],
      provenance: { master_run_id: 'run-1' },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(getAdminHrEmployee('token', 'record/1')).resolves.toEqual(
      payload,
    );
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/admin/hr/employees/record%2F1',
    );
  });

  it('creates and revokes manual identity matches', async () => {
    const payload = {
      link_id: 'link/1',
      identity_resolution_revision: 1,
      rebuild_queued: true,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await createAdminHrManualMatch('token', {
      master_run_id: 'master-1',
      groupware_record_id: 'gw-1',
      erp_record_id: 'erp-1',
    });
    await revokeAdminHrManualMatch('token', 'link/1', {
      master_run_id: 'master-2',
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/admin/hr/manual-matches',
    );
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/admin/hr/manual-matches/link%2F1/revoke',
    );
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'POST' });
  });

  it('lists both mapping directories with independent search and pagination', async () => {
    const payload = {
      master_run_id: 'master-1',
      source: 'groupware',
      items: [],
      total: 0,
      page: 2,
      page_size: 12,
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      listAdminHrManualMatchCandidates('token', {
        source: 'groupware',
        page: 2,
        page_size: 12,
        q: ' 홍길동 ',
      }),
    ).resolves.toEqual(payload);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/admin/hr/manual-match-candidates?source=groupware&page=2&page_size=12&q=%ED%99%8D%EA%B8%B8%EB%8F%99',
    );
  });

  it('manages workforce categories and per-person category overrides', async () => {
    const payload = { items: [] };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await listAdminHrWorkforceCategories('token', true);
    await createAdminHrWorkforceCategory('token', {
      name: '프로젝트 인력',
    });
    await updateAdminHrWorkforceCategory('token', 'custom/1', {
      name: '프로젝트 전담',
    });
    await archiveAdminHrWorkforceCategory('token', 'custom/1');
    await setAdminHrEmployeeWorkforceCategory('token', 'record/1', {
      master_run_id: 'master-1',
      category_code: 'custom/1',
    });
    await resetAdminHrEmployeeWorkforceCategory('token', 'record/1', {
      master_run_id: 'master-1',
    });

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/admin/hr/workforce-categories?include_inactive=true',
      '/api/v1/admin/hr/workforce-categories',
      '/api/v1/admin/hr/workforce-categories/custom%2F1',
      '/api/v1/admin/hr/workforce-categories/custom%2F1',
      '/api/v1/admin/hr/employees/record%2F1/workforce-category',
      '/api/v1/admin/hr/employees/record%2F1/workforce-category',
    ]);
    expect(fetchMock.mock.calls.map((call) => call[1]?.method)).toEqual([
      undefined,
      'POST',
      'PATCH',
      'DELETE',
      'PUT',
      'DELETE',
    ]);
  });
});
