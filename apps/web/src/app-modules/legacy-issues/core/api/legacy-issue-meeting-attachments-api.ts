import {
  ApiRequestError,
  apiFetchJson,
  jsonHeaders,
} from '@/src/platform/api/client';

import type {
  LegacyIssueDatasetKey,
  LegacyIssueViewKey,
} from '../legacy-issue-datasets';

export interface LegacyIssueRevisionMeetingAttachment {
  id: string;
  overview_history_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  description: string | null;
  uploaded_by_id: string | null;
  uploaded_by_name: string | null;
  created_at: string;
  updated_at: string;
  can_edit_description: boolean;
  can_delete: boolean;
}

export interface LegacyIssueRevisionMeetingAttachmentListResponse {
  items: LegacyIssueRevisionMeetingAttachment[];
  can_upload: boolean;
}

type LegacyIssueRevisionMeetingAttachmentScope = {
  datasetKey: LegacyIssueDatasetKey;
  token: string;
  viewKey: LegacyIssueViewKey;
  workspaceSlug: string;
};

function workspaceLegacyIssueDatasetPath(
  workspaceSlug: string,
  datasetKey: LegacyIssueDatasetKey,
  path: string,
): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues/datasets/${encodeURIComponent(datasetKey)}${path}`;
}

function meetingAttachmentPath(
  scope: LegacyIssueRevisionMeetingAttachmentScope,
  path: string,
): string {
  return `${workspaceLegacyIssueDatasetPath(
    scope.workspaceSlug,
    scope.datasetKey,
    path,
  )}?view_key=${encodeURIComponent(scope.viewKey)}`;
}

export async function fetchLegacyIssueRevisionMeetingAttachments(
  scope: LegacyIssueRevisionMeetingAttachmentScope & { historyId?: string },
): Promise<LegacyIssueRevisionMeetingAttachmentListResponse> {
  const path = meetingAttachmentPath(scope, '/revisions/meeting-attachments');
  const historyQuery =
    scope.historyId === undefined
      ? ''
      : `&history_id=${encodeURIComponent(scope.historyId)}`;
  return apiFetchJson<LegacyIssueRevisionMeetingAttachmentListResponse>(
    `${path}${historyQuery}`,
    scope.token,
  );
}

export async function uploadLegacyIssueRevisionMeetingAttachment({
  clientRequestId,
  description,
  file,
  historyId,
  ...scope
}: LegacyIssueRevisionMeetingAttachmentScope & {
  clientRequestId: string;
  description?: string | null;
  file: File;
  historyId: string;
}): Promise<LegacyIssueRevisionMeetingAttachment> {
  const body = new FormData();
  body.append('file', file);
  body.append('client_request_id', clientRequestId);
  if (description != null) {
    body.append('description', description);
  }
  return apiFetchJson<LegacyIssueRevisionMeetingAttachment>(
    meetingAttachmentPath(
      scope,
      `/revisions/overview-history/${encodeURIComponent(
        historyId,
      )}/meeting-attachments`,
    ),
    scope.token,
    { body, method: 'POST' },
  );
}

export async function updateLegacyIssueRevisionMeetingAttachment({
  attachmentId,
  description,
  ...scope
}: LegacyIssueRevisionMeetingAttachmentScope & {
  attachmentId: string;
  description: string | null;
}): Promise<LegacyIssueRevisionMeetingAttachment> {
  return apiFetchJson<LegacyIssueRevisionMeetingAttachment>(
    meetingAttachmentPath(
      scope,
      `/revisions/meeting-attachments/${encodeURIComponent(attachmentId)}`,
    ),
    scope.token,
    {
      body: JSON.stringify({ description }),
      method: 'PATCH',
    },
  );
}

export async function deleteLegacyIssueRevisionMeetingAttachment({
  attachmentId,
  ...scope
}: LegacyIssueRevisionMeetingAttachmentScope & {
  attachmentId: string;
}): Promise<void> {
  await apiFetchJson<void>(
    meetingAttachmentPath(
      scope,
      `/revisions/meeting-attachments/${encodeURIComponent(attachmentId)}`,
    ),
    scope.token,
    { method: 'DELETE' },
  );
}

export async function fetchLegacyIssueRevisionMeetingAttachmentBlob({
  attachmentId,
  ...scope
}: LegacyIssueRevisionMeetingAttachmentScope & {
  attachmentId: string;
}): Promise<Blob> {
  const response = await fetch(
    meetingAttachmentPath(
      scope,
      `/revisions/meeting-attachments/${encodeURIComponent(attachmentId)}/file`,
    ),
    {
      cache: 'no-store',
      headers: jsonHeaders(scope.token),
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
