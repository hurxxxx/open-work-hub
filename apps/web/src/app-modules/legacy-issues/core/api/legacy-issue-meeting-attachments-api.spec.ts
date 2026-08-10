import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  deleteLegacyIssueRevisionMeetingAttachment,
  fetchLegacyIssueRevisionMeetingAttachmentBlob,
  fetchLegacyIssueRevisionMeetingAttachments,
  updateLegacyIssueRevisionMeetingAttachment,
  uploadLegacyIssueRevisionMeetingAttachment,
} from './legacy-issue-meeting-attachments-api';

const apiFetchJson = vi.fn();

vi.mock('@/src/platform/api/client', () => ({
  ApiRequestError: class ApiRequestError extends Error {},
  apiFetchJson: (...args: unknown[]) => apiFetchJson(...args),
  jsonHeaders: (token: string) => ({ Authorization: `Bearer ${token}` }),
}));

const scope = {
  datasetKey: 'common-master' as const,
  token: 'token',
  viewKey: 'aircon' as const,
  workspaceSlug: 'research / one',
};

describe('legacy issue revision meeting attachment API', () => {
  beforeEach(() => {
    apiFetchJson.mockReset();
    apiFetchJson.mockResolvedValue({});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads revision-scoped meeting attachments with the module view key', async () => {
    await fetchLegacyIssueRevisionMeetingAttachments(scope);

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/datasets/common-master/revisions/meeting-attachments?view_key=aircon',
      'token',
    );
  });

  it('optionally filters meeting attachments by an encoded overview history id', async () => {
    await fetchLegacyIssueRevisionMeetingAttachments({
      ...scope,
      historyId: 'history / 1',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/datasets/common-master/revisions/meeting-attachments?view_key=aircon&history_id=history%20%2F%201',
      'token',
    );
  });

  it('uploads a file and optional description against an overview history row', async () => {
    const file = new File(['minutes'], 'minutes.pdf', {
      type: 'application/pdf',
    });

    await uploadLegacyIssueRevisionMeetingAttachment({
      ...scope,
      clientRequestId: 'request-1',
      description: 'Review outcome',
      file,
      historyId: 'history / 1',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/datasets/common-master/revisions/overview-history/history%20%2F%201/meeting-attachments?view_key=aircon',
      'token',
      expect.objectContaining({ body: expect.any(FormData), method: 'POST' }),
    );
    const body = apiFetchJson.mock.calls[0]?.[2]?.body as FormData;
    expect(body.get('file')).toBe(file);
    expect(body.get('client_request_id')).toBe('request-1');
    expect(body.get('description')).toBe('Review outcome');
  });

  it('updates and deletes an attachment through its revision endpoint', async () => {
    await updateLegacyIssueRevisionMeetingAttachment({
      ...scope,
      attachmentId: 'attachment / 1',
      description: null,
    });
    await deleteLegacyIssueRevisionMeetingAttachment({
      ...scope,
      attachmentId: 'attachment / 1',
    });

    const path =
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/datasets/common-master/revisions/meeting-attachments/attachment%20%2F%201?view_key=aircon';
    expect(apiFetchJson).toHaveBeenNthCalledWith(1, path, 'token', {
      body: JSON.stringify({ description: null }),
      method: 'PATCH',
    });
    expect(apiFetchJson).toHaveBeenNthCalledWith(2, path, 'token', {
      method: 'DELETE',
    });
  });

  it('downloads an attachment with authenticated no-store fetch', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(new Blob(['pdf'])));
    vi.stubGlobal('fetch', fetchMock);

    const blob = await fetchLegacyIssueRevisionMeetingAttachmentBlob({
      ...scope,
      attachmentId: 'attachment / 1',
    });

    expect(blob.size).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/legacy-issues/datasets/common-master/revisions/meeting-attachments/attachment%20%2F%201/file?view_key=aircon',
      {
        cache: 'no-store',
        headers: { Authorization: 'Bearer token' },
      },
    );
  });
});
