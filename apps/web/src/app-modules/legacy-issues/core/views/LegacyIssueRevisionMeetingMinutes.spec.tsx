import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';
import type { LegacyIssueRevisionMeetingAttachment } from '../api/legacy-issue-meeting-attachments-api';
import type {
  LegacyIssueRevision,
  LegacyIssueRevisionOverviewHistory,
} from '../api/legacy-issue-common-api';
import {
  LegacyIssueRevisionMeetingAttachmentsPanel,
  LegacyIssueRevisionMeetingMinutes,
  type LegacyIssueRevisionMeetingMinutesRow,
} from './LegacyIssueRevisionMeetingMinutes';

const apiMocks = vi.hoisted(() => ({
  deleteAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  fetchAttachments: vi.fn(),
  updateAttachment: vi.fn(),
  uploadAttachment: vi.fn(),
}));

const browserMocks = vi.hoisted(() => ({
  downloadBlobAsFile: vi.fn(),
}));

const uiMocks = vi.hoisted(() => {
  const confirm = vi.fn();
  const toastError = vi.fn();
  const toastSuccess = vi.fn();
  return {
    confirm,
    toastApi: { error: toastError, info: vi.fn(), success: toastSuccess },
    toastError,
    toastSuccess,
  };
});

vi.mock(
  '../api/legacy-issue-meeting-attachments-api',
  async (importOriginal) => ({
    ...(await importOriginal<
      typeof import('../api/legacy-issue-meeting-attachments-api')
    >()),
    deleteLegacyIssueRevisionMeetingAttachment: apiMocks.deleteAttachment,
    fetchLegacyIssueRevisionMeetingAttachmentBlob: apiMocks.downloadAttachment,
    fetchLegacyIssueRevisionMeetingAttachments: apiMocks.fetchAttachments,
    updateLegacyIssueRevisionMeetingAttachment: apiMocks.updateAttachment,
    uploadLegacyIssueRevisionMeetingAttachment: apiMocks.uploadAttachment,
  }),
);

vi.mock('@/src/platform/browser/browser-download', () => browserMocks);

vi.mock('@ai-do/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ai-do/ui')>()),
  useConfirm: () => ({ confirm: uiMocks.confirm, confirmDialog: null }),
  useToast: () => uiMocks.toastApi,
}));

describe('legacy issue revision meeting minutes', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ko-KR');
    vi.clearAllMocks();
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: true,
      items: [],
    });
    apiMocks.deleteAttachment.mockResolvedValue(undefined);
    apiMocks.downloadAttachment.mockResolvedValue(new Blob(['file']));
    uiMocks.confirm.mockResolvedValue(true);
  });

  afterEach(() => {
    cleanup();
  });

  it('renders rows in the provided overview order and gates actions by API capabilities', async () => {
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: true,
      items: [
        attachment({
          can_delete: true,
          can_edit_description: true,
          description: 'Decision summary',
          filename: 'admin-minutes.pdf',
          id: 'attachment-1',
          overview_history_id: 'history-2',
        }),
        attachment({
          can_delete: false,
          can_edit_description: false,
          filename: 'member-notes.txt',
          id: 'attachment-2',
          overview_history_id: 'history-1',
        }),
      ],
    });

    renderMeetingMinutes([
      meetingRow('row-2', overviewHistory('history-2', 2)),
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);

    await screen.findByText('admin-minutes.pdf');
    const renderedRows = screen.getAllByTestId(/^meeting-row-/);
    expect(renderedRows.map((row) => row.dataset.testid)).toEqual([
      'meeting-row-row-2',
      'meeting-row-row-1',
    ]);
    expect(screen.queryByRole('table')).toBeNull();
    expect(screen.queryByRole('columnheader')).toBeNull();
    const adminRow = renderedRows.at(0);
    const memberRow = renderedRows.at(1);
    expect(adminRow).toBeDefined();
    expect(memberRow).toBeDefined();
    if (!adminRow || !memberRow) throw new Error('Expected meeting rows.');
    expect(
      within(adminRow).getByRole('heading', { level: 3, name: 'Rev. 2' }),
    ).toBeTruthy();
    expect(within(adminRow).getByText('Summary 2')).toBeTruthy();
    expect(within(adminRow).getByText('Decision summary')).toBeTruthy();
    expect(within(adminRow).getByText('Uploader')).toBeTruthy();
    expect(within(adminRow).queryByText('MX5')).toBeNull();
    expect(
      within(adminRow).getByRole('button', {
        name: 'admin-minutes.pdf 설명 수정',
      }),
    ).toBeTruthy();
    expect(
      within(adminRow).getByRole('button', {
        name: 'admin-minutes.pdf 삭제',
      }),
    ).toBeTruthy();
    expect(
      within(memberRow).queryByRole('button', {
        name: 'member-notes.txt 설명 수정',
      }),
    ).toBeNull();
    expect(
      within(memberRow).queryByRole('button', {
        name: 'member-notes.txt 삭제',
      }),
    ).toBeNull();
    expect(screen.getAllByText('파일 선택')).toHaveLength(2);
    expect(screen.getByRole('button', { name: '새로고침' })).toBeTruthy();
  });

  it('keeps an empty revision compact and uploadable', async () => {
    renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);

    const group = await screen.findByTestId('meeting-row-row-1');
    expect(
      within(group).getByText('등록된 회의록·관련 문서가 없습니다.'),
    ).toBeTruthy();
    expect(within(group).getByText('파일 선택')).toBeTruthy();
    expect(within(group).queryByRole('table')).toBeNull();
  });

  it('renders a focused reusable panel and scopes its list request', async () => {
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: true,
      items: [
        attachment({
          filename: 'focused.pdf',
          overview_history_id: 'history-2',
        }),
      ],
    });
    const rows = [
      meetingRow('row-1', overviewHistory('history-1', 1)),
      meetingRow('row-2', overviewHistory('history-2', 2)),
    ];

    render(
      <LegacyIssueRevisionMeetingAttachmentsPanel
        datasetKey="common-master"
        focusedHistoryId="history-2"
        rows={rows}
        showPageHeader={false}
        token="token"
        viewKey="aircon"
        workspaceSlug="workspace"
      />,
    );

    expect(await screen.findByText('focused.pdf')).toBeTruthy();
    expect(screen.getByTestId('meeting-row-row-2')).toBeTruthy();
    expect(screen.queryByTestId('meeting-row-row-1')).toBeNull();
    expect(screen.queryByRole('heading', { level: 2 })).toBeNull();
    expect(screen.queryByRole('button', { name: '새로고침' })).toBeNull();
    expect(apiMocks.fetchAttachments).toHaveBeenCalledWith({
      datasetKey: 'common-master',
      historyId: 'history-2',
      token: 'token',
      viewKey: 'aircon',
      workspaceSlug: 'workspace',
    });
  });

  it('keeps a failed pending file for retry while retaining successful uploads', async () => {
    const firstUploaded = attachment({
      filename: 'result.pdf',
      id: 'attachment-result',
      overview_history_id: 'history-1',
    });
    const retriedUpload = attachment({
      filename: 'retry.txt',
      id: 'attachment-retry',
      overview_history_id: 'history-1',
    });
    apiMocks.fetchAttachments
      .mockResolvedValueOnce({ can_upload: true, items: [] })
      .mockResolvedValueOnce({ can_upload: true, items: [firstUploaded] })
      .mockResolvedValueOnce({
        can_upload: true,
        items: [firstUploaded, retriedUpload],
      });
    apiMocks.uploadAttachment
      .mockResolvedValueOnce(firstUploaded)
      .mockRejectedValueOnce(new Error('retry-upload'))
      .mockResolvedValueOnce(retriedUpload);

    const rendered = renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);
    await screen.findByText('파일 선택');
    const input = rendered.container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const successfulFile = new File(['result'], 'result.pdf', {
      type: 'application/pdf',
    });
    const failedFile = new File(['retry'], 'retry.txt', {
      type: 'text/plain',
    });
    fireEvent.change(input, {
      target: { files: [successfulFile, failedFile] },
    });
    const descriptions = screen.getAllByLabelText(/파일 설명$/);
    const firstDescription = descriptions.at(0);
    expect(firstDescription).toBeDefined();
    if (!firstDescription) throw new Error('Expected a description field.');
    fireEvent.change(firstDescription, {
      target: { value: 'Meeting result' },
    });
    fireEvent.click(screen.getByRole('button', { name: '파일 업로드' }));

    await waitFor(() =>
      expect(apiMocks.uploadAttachment).toHaveBeenCalledTimes(2),
    );
    expect(await screen.findByText('result.pdf')).toBeTruthy();
    expect(screen.getByText('파일을 업로드하지 못했습니다.')).toBeTruthy();
    expect(screen.queryByText('Meeting result')).toBeNull();
    expect(apiMocks.uploadAttachment).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        description: 'Meeting result',
        file: successfulFile,
        historyId: 'history-1',
      }),
    );
    const failedClientRequestId = apiMocks.uploadAttachment.mock.calls[1]?.[0]
      ?.clientRequestId as string | undefined;
    expect(failedClientRequestId).toEqual(expect.any(String));

    fireEvent.click(screen.getByRole('button', { name: '파일 업로드' }));
    await waitFor(() =>
      expect(apiMocks.uploadAttachment).toHaveBeenCalledTimes(3),
    );
    expect(apiMocks.uploadAttachment).toHaveBeenLastCalledWith(
      expect.objectContaining({
        clientRequestId: failedClientRequestId,
        file: failedFile,
        historyId: 'history-1',
      }),
    );
    expect(await screen.findByText('retry.txt')).toBeTruthy();
    expect(screen.queryByText('파일을 업로드하지 못했습니다.')).toBeNull();
  });

  it('uploads an unlimited file selection sequentially', async () => {
    let resolveFirst:
      | ((attachment: LegacyIssueRevisionMeetingAttachment) => void)
      | undefined;
    apiMocks.uploadAttachment
      .mockReturnValueOnce(
        new Promise<LegacyIssueRevisionMeetingAttachment>((resolve) => {
          resolveFirst = resolve;
        }),
      )
      .mockResolvedValueOnce(
        attachment({
          filename: 'second.pdf',
          id: 'attachment-2',
          overview_history_id: 'history-1',
        }),
      );

    const rendered = renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);
    await screen.findByText('파일 선택');
    const input = rendered.container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [
          new File(['first'], 'first.pdf'),
          new File(['second'], 'second.pdf'),
        ],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: '파일 업로드' }));

    await waitFor(() =>
      expect(apiMocks.uploadAttachment).toHaveBeenCalledTimes(1),
    );
    await act(async () => {
      resolveFirst?.(
        attachment({
          filename: 'first.pdf',
          id: 'attachment-1',
          overview_history_id: 'history-1',
        }),
      );
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(apiMocks.uploadAttachment).toHaveBeenCalledTimes(2),
    );
  });

  it('downloads, edits, and confirms deletion using item capabilities', async () => {
    const original = attachment({
      can_delete: true,
      can_edit_description: true,
      description: 'Original',
      filename: 'decision.pdf',
      id: 'attachment-1',
      overview_history_id: 'history-1',
    });
    const updated = { ...original, description: 'Updated' };
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: false,
      items: [updated],
    });
    apiMocks.updateAttachment.mockResolvedValue(updated);

    renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);
    const filename = await screen.findByRole('button', {
      name: 'decision.pdf',
    });
    fireEvent.click(filename);
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'decision.pdf',
      ),
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'decision.pdf 설명 수정' }),
    );
    fireEvent.change(screen.getByLabelText('decision.pdf 파일 설명'), {
      target: { value: 'Updated' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(apiMocks.updateAttachment).toHaveBeenCalledWith(
        expect.objectContaining({
          attachmentId: 'attachment-1',
          description: 'Updated',
        }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'decision.pdf 삭제' }));
    await waitFor(() => expect(uiMocks.confirm).toHaveBeenCalledTimes(1));
    expect(uiMocks.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        description: expect.stringContaining('decision.pdf'),
        variant: 'danger',
      }),
    );
    await waitFor(() =>
      expect(apiMocks.deleteAttachment).toHaveBeenCalledWith(
        expect.objectContaining({ attachmentId: 'attachment-1' }),
      ),
    );
  });

  it('keeps a later file description draft when an earlier save resolves', async () => {
    const first = attachment({
      can_edit_description: true,
      description: 'First original',
      filename: 'first.pdf',
      id: 'attachment-first',
    });
    const second = attachment({
      can_edit_description: true,
      description: 'Second original',
      filename: 'second.pdf',
      id: 'attachment-second',
    });
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: false,
      items: [first, second],
    });
    let resolveFirstSave:
      | ((attachment: LegacyIssueRevisionMeetingAttachment) => void)
      | undefined;
    apiMocks.updateAttachment.mockReturnValueOnce(
      new Promise<LegacyIssueRevisionMeetingAttachment>((resolve) => {
        resolveFirstSave = resolve;
      }),
    );

    renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);
    await screen.findByText('first.pdf');
    fireEvent.click(
      screen.getByRole('button', { name: 'first.pdf 설명 수정' }),
    );
    fireEvent.change(screen.getByLabelText('first.pdf 파일 설명'), {
      target: { value: 'First updated' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(apiMocks.updateAttachment).toHaveBeenCalledWith(
        expect.objectContaining({
          attachmentId: 'attachment-first',
          description: 'First updated',
        }),
      ),
    );

    fireEvent.click(
      screen.getByRole('button', { name: 'second.pdf 설명 수정' }),
    );
    const secondEditor = screen.getByLabelText('second.pdf 파일 설명');
    fireEvent.change(secondEditor, { target: { value: 'Second draft' } });

    await act(async () => {
      resolveFirstSave?.({ ...first, description: 'First updated' });
      await Promise.resolve();
    });

    await waitFor(() =>
      expect(
        (screen.getByLabelText('second.pdf 파일 설명') as HTMLTextAreaElement)
          .value,
      ).toBe('Second draft'),
    );
  });

  it('projects an unmatched published revision with compact metadata', async () => {
    renderMeetingMinutes([
      {
        id: 'revision-revision-7',
        revision: publishedRevision(),
        sourceHistory: null,
      },
    ]);

    await screen.findByText('Rev. 7');
    const row = screen.getByTestId('meeting-row-revision-revision-7');
    expect(within(row).getByText('Published summary')).toBeTruthy();
    expect(within(row).queryByText('Publisher')).toBeNull();
    expect(within(row).queryByText('Reviewer')).toBeNull();
    expect(within(row).queryByText('Approver')).toBeNull();
    expect(within(row).queryByText('파일 선택')).toBeNull();
  });

  it('recovers the download action after a failed request', async () => {
    const fileAttachment = attachment({ filename: 'recovery.pdf' });
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: false,
      items: [fileAttachment],
    });
    apiMocks.downloadAttachment
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(new Blob(['recovered']));

    renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);
    const filename = await screen.findByRole('button', {
      name: 'recovery.pdf',
    });
    fireEvent.click(filename);
    await waitFor(() =>
      expect((filename as HTMLButtonElement).disabled).toBe(true),
    );
    await waitFor(() =>
      expect(uiMocks.toastError).toHaveBeenCalledWith(
        '첨부파일을 다운로드하지 못했습니다.',
      ),
    );
    expect((filename as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(filename);
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'recovery.pdf',
      ),
    );
  });

  it('ignores a previous auth session list response after the token changes', async () => {
    let resolveOldRequest:
      | ((value: {
          can_upload: boolean;
          items: LegacyIssueRevisionMeetingAttachment[];
        }) => void)
      | undefined;
    apiMocks.fetchAttachments
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveOldRequest = resolve;
        }),
      )
      .mockResolvedValueOnce({
        can_upload: false,
        items: [attachment({ filename: 'new-session.pdf' })],
      });
    const rows = [meetingRow('row-1', overviewHistory('history-1', 1))];
    const rendered = renderMeetingMinutes(rows, 'old-token');
    await waitFor(() =>
      expect(apiMocks.fetchAttachments).toHaveBeenCalledWith(
        expect.objectContaining({ token: 'old-token' }),
      ),
    );

    rendered.rerender(meetingMinutesElement(rows, 'new-token'));
    expect(await screen.findByText('new-session.pdf')).toBeTruthy();
    await act(async () => {
      resolveOldRequest?.({
        can_upload: false,
        items: [attachment({ filename: 'old-session.pdf' })],
      });
      await Promise.resolve();
    });

    expect(screen.queryByText('old-session.pdf')).toBeNull();
    expect(apiMocks.fetchAttachments).toHaveBeenLastCalledWith(
      expect.objectContaining({ token: 'new-token' }),
    );
  });

  it('drops an in-flight download from an old token and clears busy state for the new session', async () => {
    const fileAttachment = attachment({ filename: 'session.pdf' });
    apiMocks.fetchAttachments.mockResolvedValue({
      can_upload: false,
      items: [fileAttachment],
    });
    let resolveOldDownload: ((value: Blob) => void) | undefined;
    apiMocks.downloadAttachment
      .mockReturnValueOnce(
        new Promise<Blob>((resolve) => {
          resolveOldDownload = resolve;
        }),
      )
      .mockResolvedValueOnce(new Blob(['new-session']));
    const rows = [meetingRow('row-1', overviewHistory('history-1', 1))];
    const rendered = renderMeetingMinutes(rows, 'old-token');
    const oldButton = await screen.findByRole('button', {
      name: 'session.pdf',
    });
    fireEvent.click(oldButton);
    await waitFor(() =>
      expect((oldButton as HTMLButtonElement).disabled).toBe(true),
    );

    rendered.rerender(meetingMinutesElement(rows, 'new-token'));
    const newButton = await screen.findByRole('button', {
      name: 'session.pdf',
    });
    expect((newButton as HTMLButtonElement).disabled).toBe(false);
    await act(async () => {
      resolveOldDownload?.(new Blob(['old-session']));
      await Promise.resolve();
    });
    expect(browserMocks.downloadBlobAsFile).not.toHaveBeenCalled();

    fireEvent.click(newButton);
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'session.pdf',
      ),
    );
    expect(apiMocks.downloadAttachment).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ token: 'old-token' }),
    );
    expect(apiMocks.downloadAttachment).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ token: 'new-token' }),
    );
  });

  it('ignores a late list response after unmount', async () => {
    let resolveRequest:
      | ((value: { can_upload: boolean; items: [] }) => void)
      | undefined;
    apiMocks.fetchAttachments.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );
    const rendered = renderMeetingMinutes([
      meetingRow('row-1', overviewHistory('history-1', 1)),
    ]);

    rendered.unmount();
    resolveRequest?.({ can_upload: true, items: [] });
    await Promise.resolve();

    expect(uiMocks.toastError).not.toHaveBeenCalled();
  });
});

function renderMeetingMinutes(
  rows: LegacyIssueRevisionMeetingMinutesRow[],
  token = 'token',
) {
  return render(meetingMinutesElement(rows, token));
}

function meetingMinutesElement(
  rows: LegacyIssueRevisionMeetingMinutesRow[],
  token: string,
) {
  return (
    <LegacyIssueRevisionMeetingMinutes
      datasetKey="common-master"
      rows={rows}
      token={token}
      viewKey="aircon"
      workspaceSlug="workspace"
    />
  );
}

function meetingRow(
  id: string,
  sourceHistory: LegacyIssueRevisionOverviewHistory,
): LegacyIssueRevisionMeetingMinutesRow {
  return { id, revision: null, sourceHistory };
}

function overviewHistory(
  id: string,
  revisionNo: number,
): LegacyIssueRevisionOverviewHistory {
  return {
    approver_name: 'Approver',
    approver_user_id: 'approver-1',
    author_name: 'Author',
    author_user_id: 'author-1',
    dataset_key: 'common-master',
    deleted_at: null,
    deleted_by_id: null,
    id,
    linked_revision_id: null,
    origin: 'manual',
    revised_on: '2026-08-01',
    reviewer_name: 'Reviewer',
    reviewer_user_id: 'reviewer-1',
    revision_label: null,
    revision_no: revisionNo,
    sort_order: revisionNo,
    source_filename: null,
    source_row: null,
    source_sha256: null,
    source_sheet: null,
    summary: `Summary ${revisionNo}`,
    vehicle_models: 'MX5',
  };
}

function publishedRevision(): LegacyIssueRevision {
  return {
    approval_requested_at: null,
    approval_requested_by_id: null,
    approval_requested_by_name: null,
    approved_at: null,
    approved_by_id: null,
    approved_by_name: null,
    approver_email: null,
    approver_id: 'approver-1',
    approver_name: 'Approver',
    base_revision_id: null,
    canceled_at: null,
    canceled_by_id: null,
    canceled_by_name: null,
    created_at: '2026-07-31T00:00:00Z',
    created_by_id: 'publisher-1',
    created_by_name: 'Publisher',
    dataset_key: 'common-master',
    id: 'revision-7',
    locked_by_id: null,
    locked_by_name: null,
    note: 'Published summary',
    published_at: '2026-08-01T00:00:00Z',
    published_by_id: 'publisher-1',
    published_by_name: 'Publisher',
    review_requested_at: null,
    review_requested_by_id: null,
    review_requested_by_name: null,
    reviewed_at: null,
    reviewed_by_id: null,
    reviewed_by_name: null,
    reviewer_email: null,
    reviewer_id: 'reviewer-1',
    reviewer_name: 'Reviewer',
    revision_no: 7,
    status: 'published',
    updated_at: '2026-08-01T00:00:00Z',
  };
}

function attachment(
  overrides: Partial<LegacyIssueRevisionMeetingAttachment> = {},
): LegacyIssueRevisionMeetingAttachment {
  return {
    can_delete: false,
    can_edit_description: false,
    content_type: 'application/pdf',
    created_at: '2026-08-01T00:00:00Z',
    description: null,
    filename: 'minutes.pdf',
    id: 'attachment-1',
    overview_history_id: 'history-1',
    size_bytes: 1024,
    updated_at: '2026-08-01T00:00:00Z',
    uploaded_by_id: 'user-1',
    uploaded_by_name: 'Uploader',
    ...overrides,
  };
}
