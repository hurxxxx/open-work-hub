import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';
import type { LegacyIssueExcelExportJob } from './legacy-issue-common-api';

function workspaceLegacyIssueExcelExportPath(
  workspaceSlug: string,
  path: string,
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues${path}`;
}

export async function fetchLegacyIssueExcelExportJob({
  jobId,
  token,
  workspaceSlug,
}: {
  jobId: string;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueExcelExportJob> {
  return apiFetchJson<LegacyIssueExcelExportJob>(
    workspaceLegacyIssueExcelExportPath(
      workspaceSlug,
      `/excel-exports/${encodeURIComponent(jobId)}`,
    ),
    token,
  );
}

export async function fetchLegacyIssueExcelExportFile({
  jobId,
  token,
  workspaceSlug,
}: {
  jobId: string;
  token: string;
  workspaceSlug: string;
}): Promise<Blob> {
  const response = await fetch(
    workspaceLegacyIssueExcelExportPath(
      workspaceSlug,
      `/excel-exports/${encodeURIComponent(jobId)}/file`,
    ),
    {
      cache: 'no-store',
      headers: {
        ...jsonHeaders(token),
        Accept:
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      },
    },
  );
  if (response.ok) return response.blob();
  const payload = await response.json().catch(() => null);
  throw new ApiRequestError(
    response.status,
    typeof payload?.detail === 'string' ? payload.detail : '',
    payload,
  );
}
