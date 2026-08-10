import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiRequestError } from '@/src/platform/api/client';
import type {
  LegacyIssueDatasetAttachment,
  LegacyIssueDatasetDefinition,
  LegacyIssueDatasetRecord,
  LegacyIssueExcelExportJob,
} from '../api/legacy-issue-api';
import type { LegacyIssueViewKey } from '../legacy-issue-datasets';
import { CoreBusinessLegacyIssueDatasetView } from './CoreBusinessLegacyIssueDatasetView';

const apiMocks = vi.hoisted(() => ({
  cancelLegacyIssueDatasetRevision: vi.fn(),
  compareLegacyIssueDatasetRevisions: vi.fn(),
  createLegacyIssueDatasetExcelExport: vi.fn(),
  deleteLegacyIssueDatasetAttachment: vi.fn(),
  deleteLegacyIssueDatasetRecord: vi.fn(),
  fetchLegacyIssueExcelExportFile: vi.fn(),
  fetchLegacyIssueExcelExportJob: vi.fn(),
  fetchLegacyIssueColumnOrder: vi.fn(),
  fetchLegacyIssueDatasetDefinition: vi.fn(),
  fetchLegacyIssueDatasetRecordHistory: vi.fn(),
  fetchLegacyIssueDatasetRecords: vi.fn(),
  fetchLegacyIssueDatasetRevisions: vi.fn(),
  releaseLegacyIssueDatasetDraftEditing: vi.fn(),
  saveLegacyIssueDatasetRecordBatch: vi.fn(),
  setLegacyIssueDatasetAttachmentPrimary: vi.fn(),
  updateLegacyIssueDatasetAttachment: vi.fn(),
  uploadLegacyIssueDatasetAttachment: vi.fn(),
}));

const browserMocks = vi.hoisted(() => ({
  downloadBlobAsFile: vi.fn(),
}));

const meetingAttachmentApiMocks = vi.hoisted(() => ({
  deleteAttachment: vi.fn(),
  downloadAttachment: vi.fn(),
  fetchAttachments: vi.fn(),
  updateAttachment: vi.fn(),
  uploadAttachment: vi.fn(),
}));

const gridPreferenceMocks = vi.hoisted(() => ({
  resetPreference: vi.fn(),
  retry: vi.fn(),
  updatePreference: vi.fn(),
}));

const gridMocks = vi.hoisted(() => ({
  visibleRowLayout: null as {
    recordIds: string[];
    layoutId: string;
    viewApplied: boolean;
  } | null,
}));

const uiMocks = vi.hoisted(() => {
  const toastError = vi.fn();
  const toastInfo = vi.fn();
  const toastSuccess = vi.fn();
  return {
    confirm: vi.fn(),
    toastApi: {
      error: toastError,
      info: toastInfo,
      success: toastSuccess,
    },
    toastError,
    toastInfo,
    toastSuccess,
  };
});

vi.mock('../api/legacy-issue-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/legacy-issue-api')>()),
  ...apiMocks,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
    user: {
      id: 'user-1',
      system_roles: ['platform_admin'],
    },
  }),
}));

vi.mock('@/src/platform/auth/auth-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/src/platform/auth/auth-api')>()),
  hasAnySystemRole: () => true,
}));

vi.mock('@/src/platform/browser/browser-download', () => browserMocks);

vi.mock(
  '../api/legacy-issue-meeting-attachments-api',
  async (importOriginal) => ({
    ...(await importOriginal<
      typeof import('../api/legacy-issue-meeting-attachments-api')
    >()),
    deleteLegacyIssueRevisionMeetingAttachment:
      meetingAttachmentApiMocks.deleteAttachment,
    fetchLegacyIssueRevisionMeetingAttachmentBlob:
      meetingAttachmentApiMocks.downloadAttachment,
    fetchLegacyIssueRevisionMeetingAttachments:
      meetingAttachmentApiMocks.fetchAttachments,
    updateLegacyIssueRevisionMeetingAttachment:
      meetingAttachmentApiMocks.updateAttachment,
    uploadLegacyIssueRevisionMeetingAttachment:
      meetingAttachmentApiMocks.uploadAttachment,
  }),
);

vi.mock('./useLegacyIssueGridPreference', () => ({
  useLegacyIssueGridPreference: () => ({
    loadFailed: false,
    preference: null,
    resetPreference: gridPreferenceMocks.resetPreference,
    retry: gridPreferenceMocks.retry,
    status: 'idle',
    updatePreference: gridPreferenceMocks.updatePreference,
  }),
}));

vi.mock('@open-alm/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-alm/ui')>()),
  useConfirm: () => ({
    confirm: uiMocks.confirm,
    confirmDialog: null,
  }),
  useToast: () => uiMocks.toastApi,
}));

vi.mock('./LegacyIssueDataGrid', async () => {
  const React = await import('react');
  return {
    legacyIssueGridCellKey: (recordId: string, columnKey: string) =>
      `${recordId}:${columnKey}`,
    LegacyIssueDataGrid: (props: {
      blankRowDefaultValues?: Record<string, string | null>;
      columns: Array<{
        key: string;
        options?: string[];
        title: string;
        tooltip?: string;
      }>;
      changedCellKeys?: readonly string[];
      detailOpen?: boolean;
      getCellValue?: (
        record: LegacyIssueDatasetRecord,
        columnKey: string,
      ) => string | null | undefined;
      onCellBatchEdit?: (params: {
        edits: Array<{
          columnKey: string;
          record: LegacyIssueDatasetRecord;
          value: string | null;
        }>;
      }) => void;
      onCellEdit?: (params: {
        columnKey: string;
        record: LegacyIssueDatasetRecord;
        value: string;
      }) => void;
      onCreateRows?: (params: {
        values: Array<Record<string, string | null>>;
      }) => void;
      onDeleteRows?: (records: LegacyIssueDatasetRecord[]) => void;
      onVisibleColumnKeysChange?: (layout: {
        columnKeys: string[];
        layoutId: string;
      }) => void;
      onVisibleRowsChange?: (layout: {
        recordIds: string[];
        layoutId: string;
        viewApplied: boolean;
      }) => void;
      onRecordOpen: (record: LegacyIssueDatasetRecord) => void;
      records: LegacyIssueDatasetRecord[];
      revisionKey?: string | null;
      layoutId: string;
      toolbarLeading?: React.ReactNode;
      toolbarTrailing?: React.ReactNode;
    }) => {
      const {
        columns,
        onVisibleColumnKeysChange,
        onVisibleRowsChange,
        layoutId,
      } = props;
      React.useEffect(() => {
        onVisibleColumnKeysChange?.({
          columnKeys: columns.map((column) => column.key),
          layoutId,
        });
      }, [columns, onVisibleColumnKeysChange, layoutId]);
      React.useEffect(() => {
        onVisibleRowsChange?.(
          gridMocks.visibleRowLayout ?? {
            recordIds: props.records.map((record) => record.id),
            layoutId,
            viewApplied: false,
          },
        );
      }, [onVisibleRowsChange, props.records, layoutId]);
      const firstRecord = props.records[0];
      const secondRecord = props.records[1];
      const statusColumn = props.columns.find(
        (column) => column.key === 'status',
      );
      const registrantColumn = props.columns.find(
        (column) => column.key === 'registrant',
      );
      return React.createElement(
        'div',
        {
          'data-detail-open': String(Boolean(props.detailOpen)),
          'data-changed-cell-keys': props.changedCellKeys?.join('|') ?? '',
          'data-can-create': String(Boolean(props.onCreateRows)),
          'data-can-delete': String(Boolean(props.onDeleteRows)),
          'data-column-keys': props.columns
            .map((column) => column.key)
            .join('|'),
          'data-new-row-revision':
            props.blankRowDefaultValues?.introduced_revision_no ?? '',
          'data-options': statusColumn?.options?.join('|') ?? '',
          'data-record-revision': firstRecord
            ? (props.getCellValue?.(firstRecord, 'introduced_revision_no') ??
              '')
            : '',
          'data-record-count': String(props.records.length),
          'data-record-value': String(firstRecord?.values.problem ?? ''),
          'data-registrant-title': registrantColumn?.title ?? '',
          'data-registrant-tooltip': registrantColumn?.tooltip ?? '',
          'data-revision-key': props.revisionKey ?? '',
          'data-testid': 'dataset-grid-probe',
        },
        props.toolbarLeading,
        props.onCreateRows
          ? React.createElement(
              'button',
              {
                onClick: () =>
                  props.onCreateRows?.({
                    values: [{ problem: 'created directly' }],
                  }),
                type: 'button',
              },
              'add probe row',
            )
          : null,
        props.onDeleteRows && firstRecord
          ? React.createElement(
              'button',
              {
                onClick: () => props.onDeleteRows?.([firstRecord]),
                type: 'button',
              },
              'delete first probe row',
            )
          : null,
        firstRecord
          ? React.createElement(
              React.Fragment,
              null,
              React.createElement(
                'button',
                {
                  onClick: () => props.onRecordOpen(firstRecord),
                  type: 'button',
                },
                'select probe record',
              ),
              React.createElement(
                'button',
                {
                  onClick: () =>
                    props.onCellEdit?.({
                      columnKey: 'problem',
                      record: firstRecord,
                      value: 'local edit',
                    }),
                  type: 'button',
                },
                'edit probe record',
              ),
              React.createElement(
                'button',
                {
                  onClick: () =>
                    props.onCellBatchEdit?.({
                      edits: [
                        {
                          columnKey: 'occurrence_date',
                          record: firstRecord,
                          value: '2026-07-24',
                        },
                      ],
                    }),
                  type: 'button',
                },
                'paste occurrence date',
              ),
            )
          : null,
        secondRecord
          ? React.createElement(
              'button',
              {
                onClick: () => props.onRecordOpen(secondRecord),
                type: 'button',
              },
              'select second probe record',
            )
          : null,
        props.toolbarTrailing,
      );
    },
  };
});

const publishedRevision = {
  approval_requested_at: null,
  approval_requested_by_id: null,
  approval_requested_by_name: null,
  approved_at: null,
  approved_by_id: null,
  approved_by_name: null,
  approver_email: null,
  approver_id: null,
  approver_name: null,
  base_revision_id: null,
  canceled_at: null,
  canceled_by_id: null,
  canceled_by_name: null,
  created_at: '2026-07-15T00:00:00Z',
  created_by_id: 'user-1',
  created_by_name: 'User',
  dataset_key: 'legacy_issue.common-master.aircon',
  id: 'published-3',
  locked_by_id: null,
  locked_by_name: null,
  note: null,
  published_at: '2026-07-15T00:00:00Z',
  published_by_id: 'user-1',
  published_by_name: 'User',
  review_requested_at: null,
  review_requested_by_id: null,
  review_requested_by_name: null,
  reviewed_at: null,
  reviewed_by_id: null,
  reviewed_by_name: null,
  reviewer_email: null,
  reviewer_id: null,
  reviewer_name: null,
  revision_no: 3,
  status: 'published' as const,
  updated_at: '2026-07-15T00:00:00Z',
};

const publishedOverviewHistory = {
  approver_name: null,
  approver_user_id: null,
  author_name: 'User',
  author_user_id: 'user-1',
  dataset_key: 'legacy_issue.common-master.aircon',
  deleted_at: null,
  deleted_by_id: null,
  id: 'history-3',
  linked_revision_id: publishedRevision.id,
  origin: 'system',
  revised_on: '2026-07-15',
  reviewer_name: null,
  reviewer_user_id: null,
  revision_label: '3',
  revision_no: 3,
  sort_order: 0,
  source_filename: null,
  source_row: null,
  source_sha256: null,
  source_sheet: null,
  summary: '3차 리비전 변경 내역',
  vehicle_models: '전차종',
};

const lockedDraftRevision = {
  ...publishedRevision,
  base_revision_id: publishedRevision.id,
  id: 'draft-4',
  locked_by_id: 'user-1',
  locked_by_name: 'User',
  published_at: null,
  published_by_id: null,
  published_by_name: null,
  revision_no: null,
  status: 'draft' as const,
};

const initialDefinition = definitionWithOptions(['Legacy']);
const refreshedDefinition = definitionWithOptions(['Legacy', 'New code']);

describe('legacy issue common-code definition refresh', () => {
  beforeEach(() => {
    for (const mock of Object.values(apiMocks)) {
      mock.mockReset();
    }
    for (const mock of Object.values(meetingAttachmentApiMocks)) {
      mock.mockReset();
    }
    meetingAttachmentApiMocks.fetchAttachments.mockResolvedValue({
      can_upload: true,
      items: [],
    });
    uiMocks.confirm.mockReset();
    uiMocks.confirm.mockResolvedValue(true);
    uiMocks.toastError.mockReset();
    uiMocks.toastInfo.mockReset();
    uiMocks.toastSuccess.mockReset();
    apiMocks.fetchLegacyIssueColumnOrder.mockResolvedValue({
      column_order: [],
    });
    apiMocks.fetchLegacyIssueDatasetDefinition.mockResolvedValue(
      initialDefinition,
    );
    gridMocks.visibleRowLayout = null;
    apiMocks.fetchLegacyIssueDatasetRecordHistory.mockResolvedValue({
      items: [],
    });
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [datasetRecord()],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [publishedRevision],
      overview_history: [],
    });
    apiMocks.compareLegacyIssueDatasetRevisions.mockResolvedValue({
      left_revision: publishedRevision,
      right_revision: lockedDraftRevision,
      rows: [],
    });
    apiMocks.releaseLegacyIssueDatasetDraftEditing.mockResolvedValue({
      created: 0,
      created_records: [],
      items: [],
      updated: 0,
    });
    apiMocks.saveLegacyIssueDatasetRecordBatch.mockResolvedValue({
      created: 0,
      created_records: [],
      items: [],
      updated: 0,
    });
    apiMocks.uploadLegacyIssueDatasetAttachment.mockResolvedValue({
      ai_summarized_at: null,
      ai_summary: null,
      ai_summary_error: null,
      ai_summary_status: 'not_summarized',
      artifact_count: 0,
      content_type: 'text/plain',
      created_at: '2026-07-15T00:00:00Z',
      description: null,
      filename: 'evidence.txt',
      id: 'attachment-1',
      index_error: null,
      index_status: 'not_indexed',
      indexed_at: null,
      is_primary: true,
      record_id: 'record-1',
      revision_id: publishedRevision.id,
      size_bytes: 8,
      updated_at: '2026-07-15T00:00:00Z',
    });
    apiMocks.updateLegacyIssueDatasetAttachment.mockResolvedValue(
      datasetAttachment({ id: 'attachment-2' }),
    );
    apiMocks.setLegacyIssueDatasetAttachmentPrimary.mockResolvedValue(
      datasetAttachment({ id: 'attachment-2', is_primary: true }),
    );
    apiMocks.deleteLegacyIssueDatasetAttachment.mockResolvedValue(undefined);
    apiMocks.createLegacyIssueDatasetExcelExport.mockResolvedValue(
      excelExportJob({ status: 'queued' }),
    );
    apiMocks.fetchLegacyIssueExcelExportJob.mockResolvedValue(
      excelExportJob({ status: 'completed' }),
    );
    apiMocks.fetchLegacyIssueExcelExportFile.mockResolvedValue(
      new Blob(['xlsx']),
    );
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('configures the countermeasure author header tooltip', async () => {
    apiMocks.fetchLegacyIssueDatasetDefinition.mockResolvedValueOnce({
      ...initialDefinition,
      fields: [
        ...initialDefinition.fields,
        {
          active: true,
          allow_multiple: false,
          field_id: null,
          field_type: 'text',
          group_key: null,
          key: 'registrant',
          label_en: 'Countermeasure Author',
          label_ko: '대책 작성자',
          module_key: null,
          options: [],
          readonly: false,
          required: false,
          source: 'system',
        },
      ],
    });

    renderDatasetView();
    const grid = await loadedGrid();

    expect(grid.dataset.registrantTitle).toBe('대책 작성자');
    expect(grid.dataset.registrantTooltip).toBe(
      '정의: 해당 내용을 가장 잘 아는 담당자',
    );
  });

  it('enforces administrator-hidden columns in the dataset grid', async () => {
    apiMocks.fetchLegacyIssueColumnOrder.mockResolvedValueOnce({
      column_order: ['problem', 'status', 'primary_attachment'],
      hidden_column_keys: ['problem'],
      updated_at: '2026-07-30T00:00:00Z',
      view_key: 'aircon',
    });

    renderDatasetView();
    const grid = await loadedGrid();

    expect(grid.dataset.columnKeys).toBe('status|primary_attachment');
  });

  it('keeps the original tabs, moves import to the header, and combines grid controls', async () => {
    renderDatasetView();
    const grid = await loadedGrid();
    const heading = screen.getByRole('heading', { name: '에어컨' });
    const header = heading.closest('header');
    const tabGroup = screen.getByRole('group', { name: '과거차 문제점' });
    const tabs = within(tabGroup).getAllByRole('button');

    expect(header).not.toBeNull();
    expect(
      screen.getByRole('button', { name: '시트 데이터' }).closest('header'),
    ).toBeNull();
    expect(
      screen.getByRole('button', { name: '개요' }).closest('header'),
    ).toBeNull();
    expect(
      screen.getByRole('button', { name: '회의록' }).closest('header'),
    ).toBeNull();
    expect(tabs).toHaveLength(3);
    expect(
      screen
        .getByRole('button', { name: '시트 데이터' })
        .getAttribute('aria-pressed'),
    ).toBe('true');
    expect(
      screen.getByRole('button', { name: '개요' }).getAttribute('aria-pressed'),
    ).toBe('false');
    expect(
      screen
        .getByRole('button', { name: '회의록' })
        .getAttribute('aria-pressed'),
    ).toBe('false');
    expect(within(header as HTMLElement).getByText('Import')).not.toBeNull();
    expect(within(grid).getByRole('textbox', { name: '검색' })).not.toBeNull();
    expect(within(grid).getByText('1 / 1건')).not.toBeNull();
  });

  it('opens the third meeting-minutes tab and writes its deep link', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(screen.getByRole('button', { name: '회의록' }));

    expect(
      await screen.findByRole('heading', {
        name: '리비전별 회의록 및 관련 문서',
      }),
    ).not.toBeNull();
    expect(screen.getByTestId('location-search').textContent).toBe(
      '?tab=minutes',
    );
    expect(
      screen
        .getByRole('button', { name: '회의록' })
        .getAttribute('aria-pressed'),
    ).toBe('true');
    expect(meetingAttachmentApiMocks.fetchAttachments).toHaveBeenCalledWith({
      datasetKey: 'legacy_issue.common-master',
      token: 'test-token',
      viewKey: 'aircon',
      workspaceSlug: 'test-workspace',
    });
  });

  it('opens a revision-scoped meeting-minutes dialog from Overview', async () => {
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValueOnce({
      events: [],
      items: [publishedRevision],
      overview_history: [publishedOverviewHistory],
    });

    renderDatasetView();
    await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: '개요' }));

    const trigger = await screen.findByRole('button', {
      name: 'Rev. 3 회의록 보기',
    });
    const overviewRow = trigger.closest('tr');
    expect(overviewRow).not.toBeNull();
    expect(
      within(overviewRow as HTMLElement).getAllByRole('button'),
    ).toHaveLength(4);
    expect(
      within(overviewRow as HTMLElement).getByRole('button', {
        name: '수정',
      }),
    ).not.toBeNull();
    expect(
      within(overviewRow as HTMLElement).getByRole('button', {
        name: '삭제',
      }),
    ).not.toBeNull();
    expect(
      (
        within(overviewRow as HTMLElement).getByRole('button', {
          name: '변경 비교',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    fireEvent.click(trigger);

    expect(
      await screen.findByRole('dialog', { name: 'Rev. 3 회의록 및 관련 문서' }),
    ).not.toBeNull();
    await waitFor(() =>
      expect(meetingAttachmentApiMocks.fetchAttachments).toHaveBeenCalledWith({
        datasetKey: 'legacy_issue.common-master',
        historyId: 'history-3',
        token: 'test-token',
        viewKey: 'aircon',
        workspaceSlug: 'test-workspace',
      }),
    );

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it('opens a meeting-minutes deep link and falls back to sheet for an unknown tab', async () => {
    const minutes = renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?tab=minutes',
    );
    expect(
      await screen.findByRole('heading', {
        name: '리비전별 회의록 및 관련 문서',
      }),
    ).not.toBeNull();
    minutes.unmount();

    renderDatasetView('/w/test-workspace/legacy-issues/aircon?tab=unknown');
    expect(await loadedGrid()).not.toBeNull();
    expect(
      screen.queryByRole('heading', {
        name: '리비전별 회의록 및 관련 문서',
      }),
    ).toBeNull();
  });

  it('keeps the common-master aggregate on sheet data without module tabs', async () => {
    renderDatasetView(
      '/w/test-workspace/legacy-issues/common-master?tab=minutes',
      'common-master',
    );

    expect(await loadedGrid()).not.toBeNull();
    expect(screen.queryByRole('button', { name: '시트 데이터' })).toBeNull();
    expect(screen.queryByRole('button', { name: '개요' })).toBeNull();
    expect(screen.queryByRole('button', { name: '회의록' })).toBeNull();
    expect(meetingAttachmentApiMocks.fetchAttachments).not.toHaveBeenCalled();
  });

  it('collapses and restores the upper controls from the grid toolbar', async () => {
    renderDatasetView();
    const grid = await loadedGrid();

    fireEvent.click(within(grid).getByRole('button', { name: '그리드 확대' }));

    expect(screen.queryByRole('heading', { name: '에어컨' })).toBeNull();
    expect(within(grid).getByRole('textbox', { name: '검색' })).not.toBeNull();

    fireEvent.click(within(grid).getByRole('button', { name: '기본 보기' }));

    expect(screen.getByRole('heading', { name: '에어컨' })).not.toBeNull();
  });

  it('opens record details as an overlay without narrowing the grid', async () => {
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValueOnce({
      items: [
        datasetRecord(),
        datasetRecord({
          id: 'record-2',
          stable_record_id: 'stable-record-2',
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 2,
    });
    renderDatasetView();
    const grid = await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );

    const dialog = screen.getByRole('dialog', {
      name: '과거차 문제점 상세',
    });
    expect(dialog.parentElement?.className).toContain('absolute');
    expect(dialog.parentElement?.className).toContain('pointer-events-none');
    expect(dialog.className).toContain('pointer-events-auto');
    expect(grid.isConnected).toBe(true);
    expect(grid.getAttribute('data-detail-open')).toBe('true');

    fireEvent.click(
      screen.getByRole('button', { name: 'select second probe record' }),
    );

    expect(within(dialog).getByText('record-2')).not.toBeNull();
    expect(grid.getAttribute('data-detail-open')).toBe('true');

    fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: '과거차 문제점 상세' }),
      ).toBeNull(),
    );
    expect(grid.getAttribute('data-detail-open')).toBe('false');
  });

  it('manually refreshes only the definition while preserving the editing context', async () => {
    renderDatasetView();
    const grid = await loadedGrid();
    const initialRevisionKey = grid.dataset.revisionKey;

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'edit probe record' }));
    fireEvent.change(screen.getByRole('textbox', { name: '검색' }), {
      target: { value: 'needle' },
    });
    await waitFor(() =>
      expect(apiMocks.fetchLegacyIssueDatasetRecords).toHaveBeenCalledWith(
        expect.objectContaining({ query: 'needle' }),
      ),
    );

    vi.clearAllMocks();
    apiMocks.fetchLegacyIssueDatasetDefinition.mockResolvedValueOnce(
      refreshedDefinition,
    );

    const refreshButton = screen.getByRole('button', {
      name: '공통코드 새로고침',
    });
    expect((refreshButton as HTMLButtonElement).disabled).toBe(false);
    expect(
      (screen.getByRole('button', { name: '새로고침' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(refreshButton);

    await waitFor(() =>
      expect(
        screen.getByTestId('dataset-grid-probe').getAttribute('data-options'),
      ).toBe('Legacy|New code'),
    );
    expect(apiMocks.fetchLegacyIssueDatasetDefinition).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchLegacyIssueDatasetRecords).not.toHaveBeenCalled();
    expect(apiMocks.fetchLegacyIssueDatasetRevisions).not.toHaveBeenCalled();
    expect(apiMocks.fetchLegacyIssueColumnOrder).not.toHaveBeenCalled();
    expect(grid.getAttribute('data-record-value')).toBe('local edit');
    expect(grid.getAttribute('data-detail-open')).toBe('true');
    expect(grid.getAttribute('data-revision-key')).toBe(initialRevisionKey);
    expect(
      (screen.getByRole('textbox', { name: '검색' }) as HTMLInputElement).value,
    ).toBe('needle');
  });

  it('saves a pasted occurrence date directly to the published revision', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'paste occurrence date' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '저장', exact: true }));

    await waitFor(() =>
      expect(apiMocks.saveLegacyIssueDatasetRecordBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          creates: [],
          releaseEditing: false,
          revisionId: publishedRevision.id,
          updates: [
            {
              record_id: 'record-1',
              values: { occurrence_date: '2026-07-24' },
            },
          ],
        }),
      ),
    );
    expect(screen.getByRole('button', { name: '수정 시작' })).not.toBeNull();
  });

  it('adds and cancels a pending row directly on the published revision', async () => {
    renderDatasetView();
    const grid = await loadedGrid();

    expect(grid.getAttribute('data-can-create')).toBe('true');
    expect(grid.getAttribute('data-can-delete')).toBe('true');
    expect(grid.getAttribute('data-record-revision')).toBe('3');
    expect(grid.getAttribute('data-new-row-revision')).toBe('3');

    fireEvent.click(screen.getByRole('button', { name: 'add probe row' }));
    await waitFor(() =>
      expect(grid.getAttribute('data-record-count')).toBe('2'),
    );
    fireEvent.click(
      screen.getByRole('button', { name: 'delete first probe row' }),
    );
    await waitFor(() =>
      expect(grid.getAttribute('data-record-count')).toBe('1'),
    );

    expect(apiMocks.deleteLegacyIssueDatasetRecord).not.toHaveBeenCalled();
  });

  it('saves a newly added row directly to the published revision', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(screen.getByRole('button', { name: 'add probe row' }));
    fireEvent.click(screen.getByRole('button', { name: '저장', exact: true }));

    await waitFor(() =>
      expect(apiMocks.saveLegacyIssueDatasetRecordBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          creates: [
            expect.objectContaining({
              values: {
                introduced_revision_no: '3',
                problem: 'created directly',
              },
            }),
          ],
          releaseEditing: false,
          revisionId: publishedRevision.id,
          updates: [],
        }),
      ),
    );
  });

  it('deletes a published record from the detail panel with direct edit access', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside');
    expect(detailPanel).not.toBeNull();
    const deleteButton = within(detailPanel as HTMLElement).getByRole(
      'button',
      { name: '삭제' },
    );
    expect((deleteButton as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(deleteButton);

    await waitFor(() =>
      expect(apiMocks.deleteLegacyIssueDatasetRecord).toHaveBeenCalledWith({
        datasetKey: 'legacy_issue.common-master',
        recordId: 'record-1',
        revisionId: publishedRevision.id,
        token: 'test-token',
        viewKey: 'aircon',
        workspaceSlug: 'test-workspace',
      }),
    );
  });

  it('keeps the existing full refresh action for records and revision context', async () => {
    renderDatasetView();
    await loadedGrid();
    vi.clearAllMocks();

    fireEvent.click(screen.getByRole('button', { name: '새로고침' }));

    await waitFor(() =>
      expect(apiMocks.fetchLegacyIssueDatasetRecords).toHaveBeenCalledTimes(1),
    );
    expect(apiMocks.fetchLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchLegacyIssueColumnOrder).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchLegacyIssueDatasetDefinition).toHaveBeenCalledTimes(1);
  });

  it('loads revisions after the first record response establishes the initial revision', async () => {
    const recordResponse = {
      items: [datasetRecord()],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    };
    const pendingRecords = deferred<typeof recordResponse>();
    apiMocks.fetchLegacyIssueDatasetRecords.mockReturnValueOnce(
      pendingRecords.promise,
    );

    renderDatasetView();

    await waitFor(() =>
      expect(apiMocks.fetchLegacyIssueDatasetRecords).toHaveBeenCalledTimes(1),
    );
    expect(apiMocks.fetchLegacyIssueDatasetRevisions).not.toHaveBeenCalled();

    await act(async () => {
      pendingRecords.resolve(recordResponse);
      await pendingRecords.promise;
    });

    await loadedGrid();
    expect(apiMocks.fetchLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(1);
  });

  it('requires a destructive confirmation before an authorized editor force-cancels another users draft', async () => {
    const otherUsersDraft = {
      ...lockedDraftRevision,
      locked_by_id: 'user-2',
      locked_by_name: '다른 작업자',
    };
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [datasetRecord()],
      limit: null,
      offset: 0,
      revision: {
        active_draft: otherUsersDraft,
        can_force_cancel_active_draft: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [otherUsersDraft, publishedRevision],
      overview_history: [],
    });
    apiMocks.cancelLegacyIssueDatasetRevision.mockResolvedValue({
      ...otherUsersDraft,
      canceled_at: '2026-07-23T00:00:00Z',
      canceled_by_id: 'user-1',
      canceled_by_name: 'User',
      locked_by_id: null,
      locked_by_name: null,
      status: 'canceled',
    });
    uiMocks.confirm.mockResolvedValueOnce(false);

    renderDatasetView();
    await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: '초안 강제 취소' }));

    await waitFor(() =>
      expect(uiMocks.confirm).toHaveBeenCalledWith(
        expect.objectContaining({
          confirmLabel: '초안 강제 취소',
          description: expect.stringContaining(
            '모든 미발행 데이터와 첨부 변경사항',
          ),
          title: '다른 작업자님의 초안을 강제로 취소할까요?',
          variant: 'danger',
        }),
      ),
    );
    expect(apiMocks.cancelLegacyIssueDatasetRevision).not.toHaveBeenCalled();

    uiMocks.confirm.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByRole('button', { name: '초안 강제 취소' }));

    await waitFor(() =>
      expect(apiMocks.cancelLegacyIssueDatasetRevision).toHaveBeenCalledWith({
        datasetKey: 'legacy_issue.common-master',
        force: true,
        revisionId: otherUsersDraft.id,
        token: 'test-token',
        viewKey: 'aircon',
        workspaceSlug: 'test-workspace',
      }),
    );
    expect(uiMocks.toastSuccess).toHaveBeenCalledWith(
      '다른 사용자의 초안을 강제로 취소했습니다.',
    );
  });

  it('requires a destructive confirmation before the owner cancels a saved draft', async () => {
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [datasetRecord({ revision_id: lockedDraftRevision.id })],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.cancelLegacyIssueDatasetRevision.mockResolvedValue({
      ...lockedDraftRevision,
      canceled_at: '2026-07-24T00:00:00Z',
      canceled_by_id: 'user-1',
      canceled_by_name: 'User',
      locked_by_id: null,
      locked_by_name: null,
      status: 'canceled',
    });
    uiMocks.confirm.mockResolvedValueOnce(false);

    renderDatasetView();
    await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: '초안 취소' }));

    await waitFor(() =>
      expect(uiMocks.confirm).toHaveBeenCalledWith(
        expect.objectContaining({
          confirmLabel: '초안 취소',
          description: expect.stringContaining(
            '저장된 모든 미발행 데이터와 첨부 변경사항',
          ),
          title: '초안 취소',
          variant: 'danger',
        }),
      ),
    );
    expect(apiMocks.cancelLegacyIssueDatasetRevision).not.toHaveBeenCalled();

    uiMocks.confirm.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByRole('button', { name: '초안 취소' }));

    await waitFor(() =>
      expect(apiMocks.cancelLegacyIssueDatasetRevision).toHaveBeenCalledWith({
        datasetKey: 'legacy_issue.common-master',
        force: false,
        revisionId: lockedDraftRevision.id,
        token: 'test-token',
        viewKey: 'aircon',
        workspaceSlug: 'test-workspace',
      }),
    );
  });

  it('releases draft editing while keeping persisted changed-cell markers', async () => {
    const unlockedDraftRevision = {
      ...lockedDraftRevision,
      locked_by_id: null,
      locked_by_name: null,
    };
    const draftRecord = datasetRecord({
      revision_id: lockedDraftRevision.id,
      values: { problem: 'draft value', status: 'Legacy' },
    });
    const lockedResponse = {
      items: [draftRecord],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    };
    const unlockedResponse = {
      ...lockedResponse,
      revision: {
        ...lockedResponse.revision,
        active_draft: unlockedDraftRevision,
        current: unlockedDraftRevision,
      },
    };
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue(lockedResponse);
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    const compareResponse = {
      left_revision: publishedRevision,
      right_revision: lockedDraftRevision,
      rows: [
        {
          cells: [
            {
              changed: true,
              field_key: 'problem',
              field_label: '문제점',
              left_value: 'server value',
              right_value: 'draft value',
            },
          ],
          label: 'LI-1',
          stable_record_id: 'stable-record-1',
          status: 'modified',
        },
      ],
    };
    const delayedRefreshCompare = deferred<typeof compareResponse>();
    apiMocks.compareLegacyIssueDatasetRevisions
      .mockResolvedValueOnce(compareResponse)
      .mockReturnValueOnce(delayedRefreshCompare.promise);
    apiMocks.saveLegacyIssueDatasetRecordBatch.mockImplementation(
      async ({ releaseEditing }: { releaseEditing?: boolean }) => {
        if (!releaseEditing) {
          return { created: 0, created_records: [], items: [], updated: 0 };
        }
        apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue(
          unlockedResponse,
        );
        apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
          events: [],
          items: [unlockedDraftRevision, publishedRevision],
          overview_history: [],
        });
        return { created: 0, created_records: [], items: [], updated: 0 };
      },
    );

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    const grid = await loadedGrid();
    await waitFor(() =>
      expect(grid.getAttribute('data-changed-cell-keys')).toBe(
        'record-1:problem',
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: '편집 종료' }));

    await waitFor(() =>
      expect(apiMocks.saveLegacyIssueDatasetRecordBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          releaseEditing: true,
          revisionId: lockedDraftRevision.id,
        }),
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '수정 시작' })).not.toBeNull(),
    );
    expect(
      screen.getByRole('button', { name: '검토자' }).hasAttribute('disabled'),
    ).toBe(false);
    expect(
      screen.getByRole('button', { name: '승인자' }).hasAttribute('disabled'),
    ).toBe(false);
    expect(apiMocks.compareLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(
      2,
    );
    expect(uiMocks.toastSuccess).toHaveBeenCalledWith(
      '초안 변경사항을 저장하고 편집을 종료했습니다.',
    );
    expect(grid.getAttribute('data-changed-cell-keys')).toBe(
      'record-1:problem',
    );
    await act(async () => {
      delayedRefreshCompare.resolve(compareResponse);
      await delayedRefreshCompare.promise;
    });
  });

  it('names the invalid column when draft value validation fails', async () => {
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [datasetRecord({ revision_id: lockedDraftRevision.id })],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.saveLegacyIssueDatasetRecordBatch.mockRejectedValue(
      new ApiRequestError(400, '과거차 모듈 컬럼 값이 올바르지 않습니다.', {
        code: 'legacy_issues.module_field_value_invalid',
        params: { detail: 'status' },
      }),
    );

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: 'edit probe record' }));
    fireEvent.click(
      screen.getByRole('button', { name: '초안 저장', exact: true }),
    );

    await waitFor(() =>
      expect(uiMocks.toastError).toHaveBeenCalledWith(
        '상태 컬럼 값이 올바르지 않습니다.',
      ),
    );
  });

  it('keeps a newly saved cell marked while the refreshed comparison is pending or fails', async () => {
    const unlockedDraftRevision = {
      ...lockedDraftRevision,
      locked_by_id: null,
      locked_by_name: null,
      updated_at: '2026-07-15T01:00:00Z',
    };
    const lockedResponse = {
      items: [
        datasetRecord({
          revision_id: lockedDraftRevision.id,
          values: { problem: 'server value', status: 'Legacy' },
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    };
    const unlockedResponse = {
      ...lockedResponse,
      items: [
        datasetRecord({
          revision_id: lockedDraftRevision.id,
          values: { problem: 'local edit', status: 'Legacy' },
        }),
      ],
      revision: {
        ...lockedResponse.revision,
        active_draft: unlockedDraftRevision,
        current: unlockedDraftRevision,
      },
    };
    const initialCompareResponse = {
      left_revision: publishedRevision,
      right_revision: lockedDraftRevision,
      rows: [],
    };
    const delayedRefreshCompare = deferred<typeof initialCompareResponse>();
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue(lockedResponse);
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.compareLegacyIssueDatasetRevisions
      .mockResolvedValueOnce(initialCompareResponse)
      .mockReturnValueOnce(delayedRefreshCompare.promise);
    apiMocks.saveLegacyIssueDatasetRecordBatch.mockImplementation(async () => {
      apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue(
        unlockedResponse,
      );
      apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
        events: [],
        items: [unlockedDraftRevision, publishedRevision],
        overview_history: [],
      });
      return {
        created: 0,
        created_records: [],
        items: unlockedResponse.items,
        updated: 1,
      };
    });

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    const grid = await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: 'edit probe record' }));
    fireEvent.click(
      screen.getByRole('button', { name: '초안 저장', exact: true }),
    );

    await waitFor(() =>
      expect(uiMocks.toastSuccess).toHaveBeenCalledWith(
        '초안 변경사항을 저장하고 편집을 종료했습니다.',
      ),
    );
    expect(grid.getAttribute('data-changed-cell-keys')).toBe(
      'record-1:problem',
    );

    await act(async () => {
      delayedRefreshCompare.reject(new Error('compare unavailable'));
      await delayedRefreshCompare.promise.catch(() => undefined);
    });
    expect(grid.getAttribute('data-changed-cell-keys')).toBe(
      'record-1:problem',
    );
  });

  it('keeps records usable and caches a failed changed-cell comparison', async () => {
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({
          revision_id: lockedDraftRevision.id,
          values: { problem: 'draft value', status: 'Legacy' },
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.compareLegacyIssueDatasetRevisions.mockRejectedValue(new Error());

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    const grid = await loadedGrid();

    await waitFor(() =>
      expect(grid.getAttribute('data-record-value')).toBe('draft value'),
    );
    expect(uiMocks.toastError).toHaveBeenCalledWith(
      '저장된 초안 변경 셀 표시를 불러오지 못했습니다.',
    );

    fireEvent.change(screen.getByRole('textbox', { name: '검색' }), {
      target: { value: 'draft' },
    });
    await waitFor(() =>
      expect(
        apiMocks.fetchLegacyIssueDatasetRecords.mock.calls.length,
      ).toBeGreaterThan(1),
    );
    expect(apiMocks.compareLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(
      1,
    );
  });

  it('does not show a stale comparison error after navigating away from the draft', async () => {
    const pendingCompare = deferred<never>();
    const draftResponse = {
      items: [
        datasetRecord({
          revision_id: lockedDraftRevision.id,
          values: { problem: 'draft value', status: 'Legacy' },
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    };
    const publishedResponse = {
      ...draftResponse,
      revision: {
        active_draft: lockedDraftRevision,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
    };
    apiMocks.fetchLegacyIssueDatasetRecords.mockImplementation(
      ({ revisionId }: { revisionId?: string | null }) =>
        Promise.resolve(
          revisionId === lockedDraftRevision.id
            ? draftResponse
            : publishedResponse,
        ),
    );
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.compareLegacyIssueDatasetRevisions.mockReturnValue(
      pendingCompare.promise,
    );

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    await loadedGrid();
    fireEvent.click(screen.getByRole('button', { name: '다른 리비전 URL' }));
    await waitFor(() =>
      expect(apiMocks.fetchLegacyIssueDatasetRecords).toHaveBeenCalledWith(
        expect.objectContaining({ revisionId: 'published-2' }),
      ),
    );

    await act(async () => {
      pendingCompare.reject(new Error('stale compare failure'));
      await pendingCompare.promise.catch(() => undefined);
    });

    expect(uiMocks.toastError).not.toHaveBeenCalledWith(
      '저장된 초안 변경 셀 표시를 불러오지 못했습니다.',
    );
  });

  it('refreshes changed-cell comparison when the mutable draft version changes', async () => {
    const updatedDraftRevision = {
      ...lockedDraftRevision,
      updated_at: '2026-07-15T01:00:00Z',
    };
    const draftResponse = {
      items: [datasetRecord({ revision_id: lockedDraftRevision.id })],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    };
    apiMocks.fetchLegacyIssueDatasetRecords.mockImplementation(
      ({ query }: { query?: string }) =>
        Promise.resolve(
          query
            ? {
                ...draftResponse,
                revision: {
                  ...draftResponse.revision,
                  active_draft: updatedDraftRevision,
                  current: updatedDraftRevision,
                },
              }
            : draftResponse,
        ),
    );
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });

    renderDatasetView(
      '/w/test-workspace/legacy-issues/aircon?revision_id=draft-4',
    );
    await loadedGrid();
    await waitFor(() =>
      expect(apiMocks.compareLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(
        1,
      ),
    );

    fireEvent.change(screen.getByRole('textbox', { name: '검색' }), {
      target: { value: 'updated draft' },
    });
    await waitFor(() =>
      expect(apiMocks.compareLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(
        2,
      ),
    );
  });

  it('waits for the attachment-tab save before uploading an existing-record attachment', async () => {
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [datasetRecord({ revision_id: lockedDraftRevision.id })],
      limit: null,
      offset: 0,
      revision: {
        active_draft: lockedDraftRevision,
        current: lockedDraftRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    apiMocks.fetchLegacyIssueDatasetRevisions.mockResolvedValue({
      events: [],
      items: [lockedDraftRevision, publishedRevision],
      overview_history: [],
    });
    apiMocks.compareLegacyIssueDatasetRevisions
      .mockResolvedValueOnce({
        left_revision: publishedRevision,
        right_revision: lockedDraftRevision,
        rows: [],
      })
      .mockRejectedValue(new Error('compare unavailable'));
    renderDatasetView();
    const grid = await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));

    const file = new File(['evidence'], 'evidence.txt', {
      type: 'text/plain',
    });
    fireEvent.change(screen.getAllByLabelText('첨부 추가')[0], {
      target: { files: [file] },
    });

    expect(apiMocks.uploadLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside');
    expect(detailPanel).not.toBeNull();
    fireEvent.click(
      within(detailPanel as HTMLElement).getByRole('button', {
        name: '저장',
        exact: true,
      }),
    );

    await waitFor(() =>
      expect(apiMocks.uploadLegacyIssueDatasetAttachment).toHaveBeenCalledWith(
        expect.objectContaining({
          datasetKey: 'legacy_issue.common-master',
          file,
          recordId: 'record-1',
        }),
      ),
    );
    expect(uiMocks.toastSuccess).toHaveBeenCalledWith(
      '첨부 변경사항을 저장했습니다.',
    );
    expect(
      apiMocks.releaseLegacyIssueDatasetDraftEditing,
    ).not.toHaveBeenCalled();
    expect(grid.getAttribute('data-changed-cell-keys')).toBe(
      'record-1:primary_attachment',
    );

    fireEvent.change(screen.getByRole('textbox', { name: '검색' }), {
      target: { value: 'attachment changed' },
    });
    await waitFor(() =>
      expect(apiMocks.compareLegacyIssueDatasetRevisions).toHaveBeenCalledTimes(
        2,
      ),
    );
    expect(grid.getAttribute('data-changed-cell-keys')).toBe(
      'record-1:primary_attachment',
    );
  });

  it('stages description, primary, and delete changes until the attachment-tab save', async () => {
    const firstAttachment = datasetAttachment({
      filename: 'first.txt',
      id: 'attachment-1',
      is_primary: true,
    });
    const secondAttachment = datasetAttachment({
      filename: 'second.txt',
      id: 'attachment-2',
    });
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({ attachments: [firstAttachment, secondAttachment] }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    renderDatasetView();
    await loadedGrid();
    await act(async () => {
      await Promise.resolve();
    });

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    const descriptionInputs =
      within(detailPanel).getAllByLabelText('첨부 설명');
    fireEvent.change(descriptionInputs[1], {
      target: { value: 'updated evidence' },
    });
    const setPrimaryButton = within(detailPanel)
      .getAllByRole('button', { name: '대표 지정' })
      .find((button) => !(button as HTMLButtonElement).disabled);
    expect(setPrimaryButton).toBeDefined();
    fireEvent.click(setPrimaryButton as HTMLButtonElement);
    const firstAttachmentCard = within(detailPanel)
      .getByText('first.txt')
      .closest('article') as HTMLElement;
    fireEvent.click(
      within(firstAttachmentCard).getByRole('button', { name: '삭제' }),
    );
    await waitFor(() =>
      expect(within(detailPanel).queryByText('first.txt')).toBeNull(),
    );

    expect(apiMocks.updateLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    expect(
      apiMocks.setLegacyIssueDatasetAttachmentPrimary,
    ).not.toHaveBeenCalled();
    expect(apiMocks.deleteLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    fireEvent.click(
      within(detailPanel).getByRole('button', {
        name: '저장',
        exact: true,
      }),
    );

    await waitFor(() => {
      expect(apiMocks.updateLegacyIssueDatasetAttachment).toHaveBeenCalledWith(
        expect.objectContaining({
          attachmentId: 'attachment-2',
          description: 'updated evidence',
        }),
      );
      expect(
        apiMocks.setLegacyIssueDatasetAttachmentPrimary,
      ).toHaveBeenCalledWith(
        expect.objectContaining({ attachmentId: 'attachment-2' }),
      );
      expect(apiMocks.deleteLegacyIssueDatasetAttachment).toHaveBeenCalledWith(
        expect.objectContaining({ attachmentId: 'attachment-1' }),
      );
    });
    expect(
      apiMocks.updateLegacyIssueDatasetAttachment.mock.invocationCallOrder[0],
    ).toBeLessThan(
      apiMocks.setLegacyIssueDatasetAttachmentPrimary.mock
        .invocationCallOrder[0],
    );
    expect(
      apiMocks.setLegacyIssueDatasetAttachmentPrimary.mock
        .invocationCallOrder[0],
    ).toBeLessThan(
      apiMocks.deleteLegacyIssueDatasetAttachment.mock.invocationCallOrder[0],
    );
  });

  it('keeps a failed staged upload available for attachment-tab save retry', async () => {
    apiMocks.uploadLegacyIssueDatasetAttachment
      .mockRejectedValueOnce(new Error('upload failed'))
      .mockResolvedValueOnce(datasetAttachment({ is_primary: true }));
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({
          attachments: [
            datasetAttachment({ filename: 'old.txt', is_primary: true }),
          ],
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    fireEvent.change(within(detailPanel).getAllByLabelText('첨부 추가')[0], {
      target: {
        files: [new File(['retry'], 'retry.txt', { type: 'text/plain' })],
      },
    });
    const oldAttachmentCard = within(detailPanel)
      .getByText('old.txt')
      .closest('article') as HTMLElement;
    fireEvent.click(
      within(oldAttachmentCard).getByRole('button', { name: '삭제' }),
    );
    await waitFor(() =>
      expect(within(detailPanel).queryByText('old.txt')).toBeNull(),
    );
    const saveButton = () =>
      within(detailPanel).getByRole('button', {
        name: '저장',
        exact: true,
      });

    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(apiMocks.uploadLegacyIssueDatasetAttachment).toHaveBeenCalledTimes(
        1,
      ),
    );
    expect(apiMocks.deleteLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    expect(within(detailPanel).getByText('retry.txt')).toBeTruthy();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(saveButton());
    await waitFor(() =>
      expect(apiMocks.uploadLegacyIssueDatasetAttachment).toHaveBeenCalledTimes(
        2,
      ),
    );
    await waitFor(() =>
      expect(apiMocks.deleteLegacyIssueDatasetAttachment).toHaveBeenCalledWith(
        expect.objectContaining({ attachmentId: 'attachment-1' }),
      ),
    );
  });

  it('does not stage an attachment delete when confirmation is cancelled', async () => {
    uiMocks.confirm.mockResolvedValueOnce(false);
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({
          attachments: [
            datasetAttachment({ filename: 'keep.txt', is_primary: true }),
          ],
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    const attachmentCard = within(detailPanel)
      .getByText('keep.txt')
      .closest('article') as HTMLElement;
    fireEvent.click(
      within(attachmentCard).getByRole('button', { name: '삭제' }),
    );

    await waitFor(() => expect(uiMocks.confirm).toHaveBeenCalledTimes(1));
    expect(within(detailPanel).getByText('keep.txt')).toBeTruthy();
    expect(apiMocks.deleteLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    expect(
      within(detailPanel).getByRole('button', {
        name: '저장',
        exact: true,
      }),
    ).toHaveProperty('disabled', true);
  });

  it('clears a staged delete when the attachment is already missing', async () => {
    apiMocks.deleteLegacyIssueDatasetAttachment.mockRejectedValueOnce(
      new ApiRequestError(404, 'Attachment not found', {
        code: 'legacy_issues.dataset_attachment_not_found',
      }),
    );
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({
          attachments: [
            datasetAttachment({
              filename: 'already-gone.txt',
              is_primary: true,
            }),
          ],
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    const attachmentCard = within(detailPanel)
      .getByText('already-gone.txt')
      .closest('article') as HTMLElement;
    fireEvent.click(
      within(attachmentCard).getByRole('button', { name: '삭제' }),
    );
    await waitFor(() =>
      expect(within(detailPanel).queryByText('already-gone.txt')).toBeNull(),
    );
    const saveButton = () =>
      within(detailPanel).getByRole('button', {
        name: '저장',
        exact: true,
      });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(apiMocks.deleteLegacyIssueDatasetAttachment).toHaveBeenCalledTimes(
        1,
      ),
    );
    await waitFor(() =>
      expect((saveButton() as HTMLButtonElement).disabled).toBe(true),
    );
  });

  it('retains a staged delete for a non-attachment 404 failure', async () => {
    apiMocks.deleteLegacyIssueDatasetAttachment.mockRejectedValueOnce(
      new ApiRequestError(404, 'Module not found', {
        code: 'legacy_issues.module_not_found',
      }),
    );
    apiMocks.fetchLegacyIssueDatasetRecords.mockResolvedValue({
      items: [
        datasetRecord({
          attachments: [
            datasetAttachment({
              filename: 'module-file.txt',
              is_primary: true,
            }),
          ],
        }),
      ],
      limit: null,
      offset: 0,
      revision: {
        active_draft: null,
        can_direct_edit_published_revision: true,
        current: publishedRevision,
        latest_published: publishedRevision,
      },
      total: 1,
    });
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    const attachmentCard = within(detailPanel)
      .getByText('module-file.txt')
      .closest('article') as HTMLElement;
    fireEvent.click(
      within(attachmentCard).getByRole('button', { name: '삭제' }),
    );
    await waitFor(() =>
      expect(within(detailPanel).queryByText('module-file.txt')).toBeNull(),
    );
    const saveButton = () =>
      within(detailPanel).getByRole('button', {
        name: '저장',
        exact: true,
      });
    fireEvent.click(saveButton());

    await waitFor(() =>
      expect(apiMocks.deleteLegacyIssueDatasetAttachment).toHaveBeenCalledTimes(
        1,
      ),
    );
    await waitFor(() =>
      expect((saveButton() as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it('keeps staged attachments when the URL requests another revision', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    fireEvent.change(within(detailPanel).getAllByLabelText('첨부 추가')[0], {
      target: {
        files: [
          new File(['pending'], 'pending-route-change.txt', {
            type: 'text/plain',
          }),
        ],
      },
    });
    await waitFor(() =>
      expect(
        within(detailPanel).getByText('pending-route-change.txt'),
      ).toBeTruthy(),
    );

    fireEvent.click(screen.getByRole('button', { name: '다른 리비전 URL' }));

    await waitFor(() =>
      expect(
        within(detailPanel).getByText('pending-route-change.txt'),
      ).toBeTruthy(),
    );
    expect(apiMocks.uploadLegacyIssueDatasetAttachment).not.toHaveBeenCalled();
    expect(
      within(detailPanel).getByRole('button', { name: '저장', exact: true }),
    ).toHaveProperty('disabled', false);
  });

  it('makes a later successful upload primary when an earlier upload fails', async () => {
    apiMocks.uploadLegacyIssueDatasetAttachment
      .mockRejectedValueOnce(new Error('first upload failed'))
      .mockResolvedValueOnce(datasetAttachment({ is_primary: true }));
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(
      screen.getByRole('button', { name: 'select probe record' }),
    );
    fireEvent.click(screen.getByRole('button', { name: '첨부파일' }));
    const detailPanel = screen
      .getByRole('heading', { name: '과거차 문제점 상세' })
      .closest('aside') as HTMLElement;
    const firstFile = new File(['first'], 'first.txt', { type: 'text/plain' });
    const secondFile = new File(['second'], 'second.txt', {
      type: 'text/plain',
    });
    fireEvent.change(within(detailPanel).getAllByLabelText('첨부 추가')[0], {
      target: { files: [firstFile, secondFile] },
    });
    fireEvent.click(
      within(detailPanel).getByRole('button', { name: '저장', exact: true }),
    );

    await waitFor(() =>
      expect(apiMocks.uploadLegacyIssueDatasetAttachment).toHaveBeenCalledTimes(
        2,
      ),
    );
    expect(apiMocks.uploadLegacyIssueDatasetAttachment).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ file: secondFile, isPrimary: true }),
    );
  });

  it('uses an asynchronous job for the existing Excel export action', async () => {
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(screen.getByRole('button', { name: 'Excel 다운로드' }));
    fireEvent.click(
      await screen.findByRole('button', { name: /데이터만 다운로드/ }),
    );

    await waitFor(() =>
      expect(apiMocks.createLegacyIssueDatasetExcelExport).toHaveBeenCalledWith(
        {
          columnKeys: ['problem', 'status'],
          datasetKey: 'legacy_issue.common-master',
          departments: [],
          includeAttachments: false,
          recordIds: null,
          revisionId: 'published-3',
          token: 'test-token',
          viewKey: 'aircon',
          workspaceSlug: 'test-workspace',
        },
      ),
    );
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'legacy-issues.xlsx',
      ),
    );
  });

  it('exports records in the filtered and sorted screen order', async () => {
    gridMocks.visibleRowLayout = {
      recordIds: ['record-2', 'record-1'],
      layoutId: 'legacy-issues.aircon.grid',
      viewApplied: true,
    };
    renderDatasetView();
    await loadedGrid();

    fireEvent.click(screen.getByRole('button', { name: 'Excel 다운로드' }));
    fireEvent.click(
      await screen.findByRole('button', { name: /데이터만 다운로드/ }),
    );

    await waitFor(() =>
      expect(apiMocks.createLegacyIssueDatasetExcelExport).toHaveBeenCalledWith(
        expect.objectContaining({
          recordIds: ['record-2', 'record-1'],
        }),
      ),
    );
  });

  it('refreshes only the definition when the window regains focus', async () => {
    renderDatasetView();
    await loadedGrid();
    vi.clearAllMocks();
    apiMocks.fetchLegacyIssueDatasetDefinition.mockResolvedValueOnce(
      refreshedDefinition,
    );

    act(() => window.dispatchEvent(new Event('focus')));

    await waitFor(() =>
      expect(
        screen.getByTestId('dataset-grid-probe').getAttribute('data-options'),
      ).toBe('Legacy|New code'),
    );
    expect(apiMocks.fetchLegacyIssueDatasetDefinition).toHaveBeenCalledTimes(1);
    expect(apiMocks.fetchLegacyIssueDatasetRecords).not.toHaveBeenCalled();
  });

  it('refreshes on visibility regain and ignores an older overlapping response', async () => {
    renderDatasetView();
    await loadedGrid();
    vi.clearAllMocks();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    const older = deferred<LegacyIssueDatasetDefinition>();
    const newer = deferred<LegacyIssueDatasetDefinition>();
    apiMocks.fetchLegacyIssueDatasetDefinition
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newer.promise);

    act(() => window.dispatchEvent(new Event('focus')));
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => {
      newer.resolve(definitionWithOptions(['Legacy', 'Newest code']));
      await newer.promise;
    });
    await waitFor(() =>
      expect(
        screen.getByTestId('dataset-grid-probe').getAttribute('data-options'),
      ).toBe('Legacy|Newest code'),
    );

    await act(async () => {
      older.resolve(definitionWithOptions(['Legacy', 'Stale code']));
      await older.promise;
    });
    expect(
      screen.getByTestId('dataset-grid-probe').getAttribute('data-options'),
    ).toBe('Legacy|Newest code');
    expect(apiMocks.fetchLegacyIssueDatasetRecords).not.toHaveBeenCalled();
  });
});

function renderDatasetView(
  initialEntry = '/w/test-workspace/legacy-issues/aircon',
  viewKey: LegacyIssueViewKey = 'aircon',
) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/legacy-issues/:viewKey"
          element={
            <>
              <RevisionNavigationProbe />
              <LocationSearchProbe />
              <CoreBusinessLegacyIssueDatasetView
                datasetKey="legacy_issue.common-master"
                viewKey={viewKey}
              />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

function LocationSearchProbe() {
  return <span data-testid="location-search">{useLocation().search}</span>;
}

function RevisionNavigationProbe() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate('?revision_id=published-2')}>
      다른 리비전 URL
    </button>
  );
}

async function loadedGrid(): Promise<HTMLElement> {
  const grid = await screen.findByTestId('dataset-grid-probe');
  await waitFor(() => expect(grid.getAttribute('data-options')).toBe('Legacy'));
  return grid;
}

function datasetRecord(
  overrides: Partial<LegacyIssueDatasetRecord> = {},
): LegacyIssueDatasetRecord {
  return {
    attachments: [],
    created_at: '2026-07-15T00:00:00Z',
    id: 'record-1',
    imported_at: null,
    imported_source_filename: null,
    module_key: 'aircon',
    primary_attachment: null,
    raw_fields: {},
    revision_id: publishedRevision.id,
    stable_record_id: 'stable-record-1',
    updated_at: '2026-07-15T00:00:00Z',
    values: {
      introduced_revision_no: '3',
      problem: 'server value',
      status: 'Legacy',
    },
    ...overrides,
  };
}

function datasetAttachment(
  overrides: Partial<LegacyIssueDatasetAttachment> = {},
): LegacyIssueDatasetAttachment {
  return {
    ai_summarized_at: null,
    ai_summary: null,
    ai_summary_error: null,
    ai_summary_status: 'not_summarized',
    artifact_count: 0,
    content_type: 'text/plain',
    created_at: '2026-07-15T00:00:00Z',
    description: null,
    filename: 'evidence.txt',
    id: 'attachment-1',
    index_error: null,
    index_status: 'not_indexed',
    indexed_at: null,
    is_primary: false,
    record_id: 'record-1',
    revision_id: publishedRevision.id,
    size_bytes: 8,
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}

function excelExportJob(
  overrides: Partial<LegacyIssueExcelExportJob> = {},
): LegacyIssueExcelExportJob {
  return {
    attachment_bytes: 0,
    attachment_count: 0,
    completed_at: null,
    created_at: '2026-07-15T00:00:00Z',
    error_code: null,
    expires_at: null,
    id: 'excel-job-1',
    include_attachments: false,
    processed_attachment_bytes: 0,
    processed_attachment_count: 0,
    record_count: 1,
    result_filename: 'legacy-issues.xlsx',
    result_size_bytes: null,
    source_kind: 'dataset',
    status: 'queued',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}

function definitionWithOptions(
  options: string[],
): LegacyIssueDatasetDefinition {
  return {
    fields: [
      {
        active: true,
        allow_multiple: false,
        field_id: 'field-problem',
        field_type: 'text',
        group_key: null,
        key: 'problem',
        label_en: 'Problem',
        label_ko: '문제점',
        module_key: 'aircon',
        options: [],
        readonly: false,
        required: false,
        source: 'module',
      },
      {
        active: true,
        allow_multiple: false,
        field_id: 'field-status',
        field_type: 'select',
        group_key: null,
        key: 'status',
        label_en: 'Status',
        label_ko: '상태',
        module_key: 'aircon',
        options,
        readonly: false,
        required: false,
        source: 'module',
      },
    ],
    group_labels_en: {},
    group_labels_ko: {},
    header_rows: 2,
    hierarchy_en: ['All', 'Air conditioner'],
    hierarchy_ko: ['전체', '에어컨'],
    key: 'common-master',
    title_en: 'Air conditioner',
    title_ko: '에어컨',
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}
