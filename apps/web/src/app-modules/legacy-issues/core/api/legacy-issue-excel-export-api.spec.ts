import { afterEach, describe, expect, it, vi } from 'vitest';

import { createLegacyIssueDatasetExcelExport } from './legacy-issue-dataset-api';
import type { LegacyIssueExcelExportJob } from './legacy-issue-common-api';
import {
  fetchLegacyIssueExcelExportFile,
  fetchLegacyIssueExcelExportJob,
} from './legacy-issue-excel-export-api';
import { createLegacyIssueVehicleModuleChecklistExcelExport } from './legacy-issue-vehicle-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('legacy issue asynchronous Excel export API', () => {
  it('creates dataset and checklist export jobs with scoped source data', async () => {
    const job = excelExportJob();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(job), {
        headers: { 'Content-Type': 'application/json' },
        status: 201,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await createLegacyIssueDatasetExcelExport({
      columnKeys: ['symptom', 'legacy_issue_number'],
      datasetKey: 'legacy_issue.common-master',
      departments: ['R&D'],
      includeAttachments: false,
      recordIds: ['record-2', 'record-1'],
      revisionId: 'revision/17',
      token: 'token',
      viewKey: 'compressor-electric',
      workspaceSlug: 'research team',
    });
    await createLegacyIssueVehicleModuleChecklistExcelExport({
      checklistId: 'check/17',
      columnKeys: ['check_plan', 'applied'],
      includeAttachments: true,
      token: 'token',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research%20team/legacy-issues/datasets/legacy_issue.common-master/excel-exports',
      expect.objectContaining({
        body: JSON.stringify({
          column_keys: ['symptom', 'legacy_issue_number'],
          departments: ['R&D'],
          include_attachments: false,
          record_ids: ['record-2', 'record-1'],
          revision_id: 'revision/17',
          view_key: 'compressor-electric',
        }),
        method: 'POST',
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-module-checklists/check%2F17/excel-exports',
      expect.objectContaining({
        body: JSON.stringify({
          column_keys: ['check_plan', 'applied'],
          include_attachments: true,
        }),
        method: 'POST',
      }),
    );
  });

  it('polls a job and downloads its generated workbook', async () => {
    const job = excelExportJob({ status: 'completed' });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(job), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      )
      .mockResolvedValueOnce(new Response('xlsx', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await fetchLegacyIssueExcelExportJob({
      jobId: 'job/17',
      token: 'token',
      workspaceSlug: 'research team',
    });
    const result = await fetchLegacyIssueExcelExportFile({
      jobId: 'job/17',
      token: 'token',
      workspaceSlug: 'research team',
    });

    expect(result.size).toBe(4);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research%20team/legacy-issues/excel-exports/job%2F17',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research%20team/legacy-issues/excel-exports/job%2F17/file',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });
});

function excelExportJob(
  overrides: Partial<LegacyIssueExcelExportJob> = {},
): LegacyIssueExcelExportJob {
  return { ...excelExportJobDefaults(), ...overrides };
}

function excelExportJobDefaults(): LegacyIssueExcelExportJob {
  return {
    attachment_bytes: 0,
    attachment_count: 0,
    completed_at: null,
    created_at: '2026-07-15T00:00:00Z',
    error_code: null,
    expires_at: null,
    id: 'job/17',
    include_attachments: false,
    processed_attachment_bytes: 0,
    processed_attachment_count: 0,
    record_count: 1,
    result_filename: 'legacy-issues.xlsx',
    result_size_bytes: null,
    source_kind: 'dataset',
    status: 'queued',
    updated_at: '2026-07-15T00:00:00Z',
  };
}
