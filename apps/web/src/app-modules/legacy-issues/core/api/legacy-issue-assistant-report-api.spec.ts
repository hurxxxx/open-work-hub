import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getLegacyIssueReport,
  getLegacyIssueReportQueryRows,
  listLegacyIssueReportQueries,
  listLegacyIssueReports,
  listLegacyIssueReportSources,
  shareLegacyIssueReport,
  unshareLegacyIssueReport,
} from './legacy-issue-assistant-report-api';

const mocks = vi.hoisted(() => ({
  apiFetchJson: vi.fn(),
}));

vi.mock('@/src/platform/api/client', () => ({
  apiFetchJson: mocks.apiFetchJson,
}));

describe('legacy issue report api', () => {
  beforeEach(() => {
    mocks.apiFetchJson.mockReset();
    mocks.apiFetchJson.mockResolvedValue({});
  });

  it('lists the requested report management view with pagination', async () => {
    await listLegacyIssueReports({
      limit: 30,
      offset: 60,
      token: 'token',
      view: 'shared',
      workspaceSlug: 'research / one',
    });

    expect(mocks.apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/reports?limit=30&offset=60&view=shared',
      'token',
      { signal: undefined },
    );
  });

  it('loads report detail, query metadata, saved rows, and semantic sources', async () => {
    await getLegacyIssueReport({
      reportId: 'AIR-20260727-0000000001',
      token: 'token',
      workspaceSlug: 'research',
    });
    await listLegacyIssueReportQueries({
      reportId: 'AIR-20260727-0000000001',
      token: 'token',
      workspaceSlug: 'research',
    });
    await getLegacyIssueReportQueryRows({
      limit: 100,
      offset: 200,
      queryId: 'query/1',
      reportId: 'AIR-20260727-0000000001',
      token: 'token',
      workspaceSlug: 'research',
    });
    await listLegacyIssueReportSources({
      reportId: 'AIR-20260727-0000000001',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(mocks.apiFetchJson.mock.calls.map(([path]) => path)).toEqual([
      '/api/v1/workspaces/research/legacy-issues/reports/AIR-20260727-0000000001',
      '/api/v1/workspaces/research/legacy-issues/reports/AIR-20260727-0000000001/queries',
      '/api/v1/workspaces/research/legacy-issues/reports/AIR-20260727-0000000001/queries/query%2F1/rows?limit=100&offset=200',
      '/api/v1/workspaces/research/legacy-issues/reports/AIR-20260727-0000000001/sources',
    ]);
  });

  it('uses idempotent workspace share and unshare methods', async () => {
    await shareLegacyIssueReport({
      reportId: 'report/1',
      token: 'token',
      workspaceSlug: 'research',
    });
    await unshareLegacyIssueReport({
      reportId: 'report/1',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(mocks.apiFetchJson).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research/legacy-issues/reports/report%2F1/workspace-share',
      'token',
      { method: 'PUT', signal: undefined },
    );
    expect(mocks.apiFetchJson).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research/legacy-issues/reports/report%2F1/workspace-share',
      'token',
      { method: 'DELETE', signal: undefined },
    );
  });
});
