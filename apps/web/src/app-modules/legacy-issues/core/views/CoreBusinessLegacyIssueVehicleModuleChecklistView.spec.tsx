import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { createElement, useEffect, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LegacyIssueExcelExportJob } from '../api/legacy-issue-common-api';
import type {
  LegacyIssueVehicleModuleChecklist,
  LegacyIssueVehicleModuleChecklistRecord,
} from '../api/legacy-issue-vehicle-api';
import {
  CoreBusinessLegacyIssueVehicleModuleChecklistView,
  resolveNextVehicleModuleChecklistId,
} from './CoreBusinessLegacyIssueVehicleModuleChecklistView';

const stableToast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}));

const browserMocks = vi.hoisted(() => ({
  downloadBlobAsFile: vi.fn(),
}));

const testMocks = vi.hoisted(() => ({
  completeChecklist: vi.fn(),
  confirm: vi.fn(),
  createChecklist: vi.fn(),
  createExcelExport: vi.fn(),
  deleteAttachment: vi.fn(),
  deleteChecklist: vi.fn(),
  downloadAttachment: vi.fn(),
  fetchChecklists: vi.fn(),
  fetchColumnOrder: vi.fn(),
  fetchExcelExportFile: vi.fn(),
  fetchExcelExportJob: vi.fn(),
  fetchHistory: vi.fn(),
  fetchRecords: vi.fn(),
  fetchVehicles: vi.fn(),
  importPreviousChecklist: vi.fn(),
  reopenChecklist: vi.fn(),
  routeParams: {
    moduleKey: 'aircon',
    vehicleModelId: 'vehicle-a',
    workspaceSlug: 'research',
  },
  saveRecords: vi.fn(),
  searchParams: new URLSearchParams(),
  setSearchParams: vi.fn(),
  uploadAttachment: vi.fn(),
  translate: vi.fn((key: string, options?: Record<string, unknown>) => {
    const labels: Record<string, string> = {
      'coreBusiness.vehicleChecklist.actions.applyCheckValues':
        'Apply to sheet',
      'coreBusiness.vehicleChecklist.actions.backToModules': 'Module list',
      'coreBusiness.vehicleChecklist.actions.close': 'Close',
      'coreBusiness.vehicleChecklist.actions.complete': 'Complete',
      'coreBusiness.vehicleChecklist.actions.createChecklist':
        'Create checklist',
      'coreBusiness.vehicleChecklist.actions.delete': 'Delete checklist',
      'coreBusiness.vehicleChecklist.actions.export': 'Export to Excel',
      'coreBusiness.vehicleChecklist.actions.importCompleted':
        'Import completed checklist',
      'coreBusiness.vehicleChecklist.actions.reopen': 'Edit mode',
      'coreBusiness.vehicleChecklist.actions.save': 'Save changes',
      'coreBusiness.vehicleChecklist.actions.search': 'Search',
      'coreBusiness.vehicleChecklist.actions.sourceMasterRevision':
        'Source master',
      'coreBusiness.vehicleChecklist.attachments.column': 'Attachments',
      'coreBusiness.vehicleChecklist.attachments.count': '{{count}} files',
      'coreBusiness.vehicleChecklist.attachments.deleteFile':
        'Delete {{filename}}',
      'coreBusiness.vehicleChecklist.attachments.downloadFile':
        'Download {{filename}}',
      'coreBusiness.vehicleChecklist.attachments.empty': 'No attachments.',
      'coreBusiness.vehicleChecklist.attachments.gridSummary':
        '{{filename}} · {{count}} files total',
      'coreBusiness.vehicleChecklist.attachments.title': 'Attachments',
      'coreBusiness.vehicleChecklist.attachments.upload': 'Add files',
      'coreBusiness.vehicleChecklist.attachments.uploading':
        'Uploading {{count}} files.',
      'coreBusiness.vehicleChecklist.confirmAttachmentDelete.confirm': 'Delete',
      'coreBusiness.vehicleChecklist.confirmAttachmentDelete.description':
        'Delete {{filename}} from this checklist record.',
      'coreBusiness.vehicleChecklist.confirmAttachmentDelete.title':
        'Delete attachment?',
      'coreBusiness.vehicleChecklist.status.attachmentDeleted':
        '{{filename}} deleted.',
      'coreBusiness.vehicleChecklist.status.attachmentsUploaded':
        '{{count}} attachments added.',
      'coreBusiness.vehicleChecklist.status.previousStageImported':
        'Imported the completed checklist from the {{stage}} stage.',
      'coreBusiness.vehicleChecklist.checklist': 'Checklist',
      'coreBusiness.vehicleChecklist.grid.total':
        '{{loaded}} / {{total}} records',
      'coreBusiness.vehicleChecklist.history.actions.attachment_upload':
        'Attachment added',
      'coreBusiness.vehicleChecklist.importDialog.completedAt': 'Completed at',
      'coreBusiness.vehicleChecklist.importDialog.completedBy': 'Completed by',
      'coreBusiness.vehicleChecklist.importDialog.confirm':
        'Import selected checklist',
      'coreBusiness.vehicleChecklist.importDialog.description':
        'Select a completed checklist from an earlier stage.',
      'coreBusiness.vehicleChecklist.importDialog.importing': 'Importing',
      'coreBusiness.vehicleChecklist.importDialog.masterRevision':
        'Master Rev. {{revision}}',
      'coreBusiness.vehicleChecklist.importDialog.rowCount':
        '{{count}} records',
      'coreBusiness.vehicleChecklist.importDialog.selectionLabel':
        'Completed checklist to import',
      'coreBusiness.vehicleChecklist.importDialog.title':
        'Select a completed checklist',
      'coreBusiness.vehicleChecklist.importDialog.unknownCompletedBy':
        'Completer unavailable',
      'coreBusiness.vehicleChecklist.searchPlaceholder': 'Search records',
      'coreBusiness.vehicleChecklist.tabs.history': 'History',
      'coreBusiness.vehicleChecklist.tabs.sheet': 'Sheet',
      'coreBusiness.grid.defaultView': 'Default view',
      'coreBusiness.grid.expandGrid': 'Expand grid',
      'coreBusiness.grid.preferenceRetry': 'Retry',
      'coreBusiness.fieldSettings.errors.columnOrderLoadFailed':
        'Could not load column settings.',
      'coreBusiness.excelExport.actions.preparing': 'Preparing Excel',
      'coreBusiness.excelExport.actions.preparingWithAttachments':
        'Preparing Excel with attachments',
      'coreBusiness.excelExport.modal.dataOnly.description':
        'Create Excel without attachments.',
      'coreBusiness.excelExport.modal.dataOnly.title': 'Download data only',
      'coreBusiness.excelExport.modal.description':
        'Choose the Excel download format.',
      'coreBusiness.excelExport.modal.withAttachments.description':
        'Attachments take longer. Please wait.',
      'coreBusiness.excelExport.modal.withAttachments.title':
        'Download with attachments and filenames',
      'coreBusiness.excelExport.status.downloaded': 'Excel file downloaded.',
      'coreBusiness.excelExport.status.processingAttachments':
        'Processing attachments. Please wait.',
      'nav.legacy-issues-aircon': 'Air Conditioner',
    };
    const template = labels[key] ?? key;
    return Object.entries(options ?? {}).reduce(
      (value, [name, replacement]) =>
        value.replaceAll(`{{${name}}}`, String(replacement)),
      template,
    );
  }),
}));

const gridPreferenceMocks = vi.hoisted(() => ({
  resetPreference: vi.fn(),
  retry: vi.fn(),
  updatePreference: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US' },
    t: testMocks.translate,
  }),
}));

vi.mock('@open-alm/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-alm/ui')>()),
  useConfirm: () => ({
    confirm: testMocks.confirm,
    confirmDialog: null,
  }),
  useToast: () => stableToast,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: { id: 'user-1' } }),
}));

vi.mock('@/src/platform/browser/browser-download', () => ({
  downloadBlobAsFile: browserMocks.downloadBlobAsFile,
}));

vi.mock('../api/legacy-issue-dataset-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/legacy-issue-dataset-api')>()),
  fetchLegacyIssueColumnOrder: testMocks.fetchColumnOrder,
}));

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

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useParams: () => testMocks.routeParams,
  useSearchParams: () => [testMocks.searchParams, testMocks.setSearchParams],
}));

vi.mock('../api/legacy-issue-vehicle-api', () => ({
  completeLegacyIssueVehicleModuleChecklist: testMocks.completeChecklist,
  createLegacyIssueVehicleModuleChecklist: testMocks.createChecklist,
  createLegacyIssueVehicleModuleChecklistExcelExport:
    testMocks.createExcelExport,
  deleteLegacyIssueVehicleModuleChecklistAttachment: testMocks.deleteAttachment,
  deleteLegacyIssueVehicleModuleChecklist: testMocks.deleteChecklist,
  fetchLegacyIssueVehicleModuleChecklistAttachmentBlob:
    testMocks.downloadAttachment,
  fetchLegacyIssueVehicleModels: testMocks.fetchVehicles,
  fetchLegacyIssueExcelExportFile: testMocks.fetchExcelExportFile,
  fetchLegacyIssueExcelExportJob: testMocks.fetchExcelExportJob,
  fetchLegacyIssueVehicleModuleChecklistHistory: testMocks.fetchHistory,
  fetchLegacyIssueVehicleModuleChecklistRecords: testMocks.fetchRecords,
  fetchLegacyIssueVehicleModuleChecklists: testMocks.fetchChecklists,
  importPreviousStageLegacyIssueVehicleModuleChecklist:
    testMocks.importPreviousChecklist,
  reopenLegacyIssueVehicleModuleChecklist: testMocks.reopenChecklist,
  saveLegacyIssueVehicleModuleChecklistRecords: testMocks.saveRecords,
  uploadLegacyIssueVehicleModuleChecklistAttachment: testMocks.uploadAttachment,
}));

vi.mock('./LegacyIssueDataGrid', () => ({
  LegacyIssueDataGrid: ({
    columns,
    getCellValue,
    onCellClick,
    onCellEdit,
    onVisibleColumnKeysChange,
    records,
    layoutId,
    toolbarLeading,
    toolbarTrailing,
  }: {
    columns: Array<{ key: string }>;
    getCellValue: (
      record: LegacyIssueVehicleModuleChecklistRecord,
      columnKey: string,
    ) => string | null | undefined;
    onCellClick?: (params: {
      columnKey: string;
      record: LegacyIssueVehicleModuleChecklistRecord;
    }) => boolean | void;
    onCellEdit?: (params: {
      columnKey: string;
      record: LegacyIssueVehicleModuleChecklistRecord;
      value: string;
    }) => void;
    onVisibleColumnKeysChange?: (layout: {
      columnKeys: string[];
      layoutId: string;
    }) => void;
    records: LegacyIssueVehicleModuleChecklistRecord[];
    layoutId: string;
    toolbarLeading?: ReactNode;
    toolbarTrailing?: ReactNode;
  }) => {
    useEffect(() => {
      onVisibleColumnKeysChange?.({
        columnKeys: columns.map((column) => column.key),
        layoutId,
      });
    }, [columns, onVisibleColumnKeysChange, layoutId]);
    return (
      <div data-testid="checklist-grid-probe">
        {toolbarLeading}
        <span data-testid="column-keys">
          {columns.map((column) => column.key).join(',')}
        </span>
        <span data-testid="check-plan">
          {String(records[0]?.values.check_plan ?? '')}
        </span>
        <span data-testid="attachment-cell">
          {records[0]
            ? String(getCellValue(records[0], 'check_attachments') ?? '')
            : ''}
        </span>
        {records[0] && onCellClick ? (
          <button
            type="button"
            onClick={() =>
              onCellClick({
                columnKey: 'check_attachments',
                record: records[0],
              })
            }
          >
            Open attachments
          </button>
        ) : null}
        {records[0] && onCellEdit ? (
          <button
            type="button"
            onClick={() =>
              onCellEdit({
                columnKey: 'check_plan',
                record: records[0],
                value: 'local unsaved CHECK',
              })
            }
          >
            Stage CHECK edit
          </button>
        ) : null}
        {toolbarTrailing}
      </div>
    );
  },
}));

function checklist(
  id: string,
  sourceMasterRevisionNo: number,
): LegacyIssueVehicleModuleChecklist {
  return {
    completed_at: null,
    completed_by_id: null,
    created_at: '2026-07-15T00:00:00Z',
    created_by_id: 'user-1',
    id,
    module_key: 'aircon',
    row_count: 1,
    source_dataset_key: 'common-master',
    source_master_revision_id: `master-${sourceMasterRevisionNo}`,
    source_master_revision_no: sourceMasterRevisionNo,
    stage_id: 'stage-a-p1',
    seeded_from_checklist_id: null,
    status: 'draft',
    updated_at: '2026-07-15T00:00:00Z',
    vehicle_model_id: 'vehicle-a',
  };
}

function attachment(checklistId: string, id = 'attachment-1') {
  return {
    checklist_id: checklistId,
    content_type: 'text/plain',
    created_at: '2026-07-15T00:00:00Z',
    filename: 'evidence.txt',
    id,
    record_id: `record-${checklistId}`,
    size_bytes: 8,
    uploaded_by_id: 'user-1',
  };
}

function record(
  checklistId: string,
  attachments: ReturnType<typeof attachment>[] = [],
): LegacyIssueVehicleModuleChecklistRecord {
  return {
    attachments,
    checklist_id: checklistId,
    created_at: '2026-07-15T00:00:00Z',
    id: `record-${checklistId}`,
    source_record_id: 'source-1',
    source_stable_record_id: 'stable-1',
    updated_at: '2026-07-15T00:00:00Z',
    values: {
      check_plan: 'server CHECK',
      legacy_issue_number: 'AIR-001',
    },
  };
}

function excelExportJob(
  overrides: Partial<LegacyIssueExcelExportJob> = {},
): LegacyIssueExcelExportJob {
  return {
    attachment_bytes: 8,
    attachment_count: 1,
    completed_at: null,
    created_at: '2026-07-15T00:00:00Z',
    error_code: null,
    expires_at: null,
    id: 'excel-job-1',
    include_attachments: false,
    processed_attachment_bytes: 0,
    processed_attachment_count: 0,
    record_count: 1,
    result_filename: 'vehicle-checklist.xlsx',
    result_size_bytes: null,
    source_kind: 'vehicle_module_checklist',
    status: 'queued',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

const definition = {
  dataset_key: 'common-master',
  fields: [
    {
      allow_multiple: false,
      field_type: 'text',
      group_key: 'check',
      key: 'check_plan',
      label_en: 'Check plan',
      label_ko: '점검방안',
      options: [],
      required: false,
    },
    {
      allow_multiple: false,
      field_type: 'select',
      group_key: 'check',
      key: 'applied',
      label_en: 'Applied',
      label_ko: '적용유무',
      options: ['O', 'X'],
      required: false,
    },
    {
      allow_multiple: false,
      field_type: 'text',
      group_key: 'check',
      key: 'reflection_result',
      label_en: 'Reflection / review result',
      label_ko: '반영/검토결과',
      options: [],
      required: false,
    },
  ],
  group_labels_en: { check: 'CHECK' },
  group_labels_ko: { check: 'CHECK' },
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  testMocks.routeParams.moduleKey = 'aircon';
  testMocks.routeParams.vehicleModelId = 'vehicle-a';
  testMocks.routeParams.workspaceSlug = 'research';
  testMocks.searchParams = new URLSearchParams('stage_id=stage-a-p1');
  testMocks.fetchVehicles.mockResolvedValue({
    items: [
      {
        active: true,
        checklist_summary: null,
        created_at: '2026-07-15T00:00:00Z',
        id: 'vehicle-a',
        notes: null,
        stages: [
          {
            created_at: '2026-07-15T00:00:00Z',
            id: 'stage-a-p0',
            name: 'P0',
            previous_stage_id: null,
            sequence_no: 1,
            updated_at: '2026-07-15T00:00:00Z',
            vehicle_model_id: 'vehicle-a',
          },
          {
            created_at: '2026-07-15T00:00:00Z',
            id: 'stage-a-p1',
            name: 'P1',
            previous_stage_id: 'stage-a-p0',
            sequence_no: 2,
            updated_at: '2026-07-15T00:00:00Z',
            vehicle_model_id: 'vehicle-a',
          },
        ],
        updated_at: '2026-07-15T00:00:00Z',
        vehicle_code: 'MX5',
        vehicle_name: 'Santa Fe',
      },
    ],
  });
  const latest = checklist('check-latest', 18);
  const older = checklist('check-older', 17);
  testMocks.fetchChecklists.mockResolvedValue({
    items: [latest, older],
    latest_master_revision: { id: 'master-18', revision_no: 18 },
    master_revisions: [
      { id: 'master-18', revision_no: 18 },
      { id: 'master-17', revision_no: 17 },
    ],
  });
  testMocks.fetchColumnOrder.mockResolvedValue({
    column_order: [
      'check_plan',
      'applied',
      'reflection_result',
      'primary_attachment',
    ],
    hidden_column_keys: [],
    updated_at: '2026-07-31T00:00:00Z',
    view_key: 'aircon',
  });
  testMocks.fetchRecords.mockImplementation(
    ({ checklistId }: { checklistId: string }) => ({
      checklist: checklistId === 'check-older' ? older : latest,
      definition,
      items: [record(checklistId)],
      limit: null,
      offset: 0,
      total: 1,
    }),
  );
  testMocks.fetchHistory.mockResolvedValue({
    checklist: latest,
    items: [],
  });
  testMocks.createExcelExport.mockResolvedValue(
    excelExportJob({ status: 'queued' }),
  );
  testMocks.fetchExcelExportJob.mockResolvedValue(
    excelExportJob({ status: 'completed' }),
  );
  testMocks.fetchExcelExportFile.mockResolvedValue(new Blob(['xlsx']));
  testMocks.saveRecords.mockResolvedValue({ items: [], updated: 0 });
  testMocks.deleteAttachment.mockResolvedValue(undefined);
  testMocks.downloadAttachment.mockResolvedValue(new Blob(['evidence']));
  testMocks.uploadAttachment.mockImplementation(
    ({ checklistId }: { checklistId: string }) => attachment(checklistId),
  );
});

afterEach(cleanup);

describe('vehicle module checklist detail', () => {
  it('combines checklist controls in the grid toolbar and expands the workspace', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    const grid = screen.getByTestId('checklist-grid-probe');

    expect(
      within(grid).getByRole('textbox', { name: 'Search' }),
    ).not.toBeNull();
    expect(within(grid).getByText('1 / 1 records')).not.toBeNull();
    expect(
      screen.getByRole('heading', {
        name: 'MX5 · Santa Fe · P1 · Air Conditioner',
      }),
    ).not.toBeNull();
    expect(screen.getByLabelText('Checklist')).not.toBeNull();
    expect(screen.getByLabelText('Source master')).not.toBeNull();

    fireEvent.click(within(grid).getByRole('button', { name: 'Expand grid' }));

    expect(
      screen.queryByRole('heading', {
        name: 'MX5 · Santa Fe · P1 · Air Conditioner',
      }),
    ).toBeNull();
    expect(screen.queryByLabelText('Checklist')).toBeNull();
    expect(
      within(grid).getByRole('textbox', { name: 'Search' }),
    ).not.toBeNull();

    fireEvent.click(within(grid).getByRole('button', { name: 'Default view' }));

    expect(
      screen.getByRole('heading', {
        name: 'MX5 · Santa Fe · P1 · Air Conditioner',
      }),
    ).not.toBeNull();
    expect(screen.getByLabelText('Checklist')).not.toBeNull();
    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
  });

  it('opens the CHECK editor as an overlay and closes it with Escape', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open attachments' }),
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog.parentElement?.className).toContain('absolute');
    expect(screen.getByTestId('checklist-grid-probe')).not.toBeNull();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('downloads an asynchronous Excel export and disables it for unsaved CHECK edits', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    const exportButton = await screen.findByRole('button', {
      name: 'Export to Excel',
    });
    await waitFor(() =>
      expect((exportButton as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(exportButton);
    fireEvent.click(
      await screen.findByRole('button', { name: /Download data only/ }),
    );

    await waitFor(() =>
      expect(testMocks.createExcelExport).toHaveBeenCalledWith({
        checklistId: 'check-latest',
        columnKeys: ['check_plan', 'applied', 'reflection_result'],
        includeAttachments: false,
        token: 'token',
        workspaceSlug: 'research',
      }),
    );
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'vehicle-checklist.xlsx',
      ),
    );
    expect(stableToast.success).toHaveBeenCalledWith('Excel file downloaded.');

    fireEvent.click(screen.getByRole('button', { name: 'Stage CHECK edit' }));
    expect(
      (
        screen.getByRole('button', {
          name: 'Export to Excel',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it('places attachment counts after the CHECK fields and opens the matching record panel', async () => {
    const latest = checklist('check-latest', 18);
    testMocks.fetchRecords.mockResolvedValue({
      checklist: latest,
      definition,
      items: [record(latest.id, [attachment(latest.id)])],
      limit: null,
      offset: 0,
      total: 1,
    });

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Open attachments' });
    expect(screen.getByTestId('column-keys').textContent).toBe(
      'check_plan,applied,reflection_result,check_attachments',
    );
    expect(screen.getByTestId('attachment-cell').textContent).toContain(
      'evidence.txt · 1 files total',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Open attachments' }));
    expect(
      await screen.findByRole('button', { name: 'Download evidence.txt' }),
    ).not.toBeNull();
  });

  it('excludes administrator-hidden module columns from the checklist grid', async () => {
    testMocks.fetchColumnOrder.mockResolvedValue({
      column_order: [
        'check_plan',
        'applied',
        'reflection_result',
        'primary_attachment',
      ],
      hidden_column_keys: ['applied'],
      updated_at: '2026-07-31T00:00:00Z',
      view_key: 'aircon',
    });

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    expect(screen.getByTestId('column-keys').textContent).toBe(
      'check_plan,reflection_result,check_attachments',
    );
    expect(testMocks.fetchColumnOrder).toHaveBeenCalledWith({
      token: 'token',
      viewKey: 'aircon',
      workspaceSlug: 'research',
    });
  });

  it('does not expose checklist columns when administrator settings fail to load and supports retry', async () => {
    testMocks.fetchColumnOrder.mockRejectedValueOnce(
      new Error('column settings unavailable'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    const alert = await screen.findByRole('alert');
    expect(
      within(alert).getByText('Could not load column settings.'),
    ).not.toBeNull();
    expect(screen.queryByTestId('checklist-grid-probe')).toBeNull();

    fireEvent.click(within(alert).getByRole('button', { name: 'Retry' }));

    expect(await screen.findByTestId('checklist-grid-probe')).not.toBeNull();
  });

  it('uploads multiple files without discarding unsaved CHECK edits', async () => {
    const pendingUpload = deferred<void>();
    testMocks.uploadAttachment.mockImplementation(
      ({
        checklistId,
        file,
        recordId,
      }: {
        checklistId: string;
        file: File;
        recordId: string;
      }) =>
        pendingUpload.promise.then(() => ({
          ...attachment(checklistId, `attachment-${file.name}`),
          filename: file.name,
          record_id: recordId,
          size_bytes: file.size,
        })),
    );
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    fireEvent.click(screen.getByRole('button', { name: 'Stage CHECK edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open attachments' }));
    fireEvent.change(screen.getByDisplayValue('local unsaved CHECK'), {
      target: { value: 'typed but not applied CHECK' },
    });
    const input = screen.getByLabelText('Add files', {
      selector: 'input',
    });
    const firstFile = new File(['evidence-a'], 'evidence-a.txt', {
      type: 'text/plain',
    });
    const secondFile = new File(['evidence-b'], 'evidence-b.txt', {
      type: 'text/plain',
    });
    fireEvent.change(input, { target: { files: [firstFile, secondFile] } });

    await waitFor(() =>
      expect(testMocks.uploadAttachment).toHaveBeenCalledTimes(2),
    );
    expect(testMocks.uploadAttachment).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        checklistId: 'check-latest',
        file: firstFile,
        recordId: 'record-check-latest',
      }),
    );
    expect(
      (
        screen.getByRole('button', {
          name: 'Save changes',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    await act(async () => {
      pendingUpload.resolve(undefined);
      await pendingUpload.promise;
    });
    await waitFor(() =>
      expect(screen.getByTestId('attachment-cell').textContent).toContain(
        'evidence-a.txt · 2 files total',
      ),
    );
    expect(screen.getByTestId('check-plan').textContent).toContain(
      'local unsaved CHECK',
    );
    expect(
      screen.getByDisplayValue('typed but not applied CHECK'),
    ).not.toBeNull();
    expect(stableToast.success).toHaveBeenCalledWith('2 attachments added.');
    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
  });

  it('reports an attachment upload failure through the shared toast', async () => {
    testMocks.uploadAttachment.mockRejectedValueOnce(
      new Error('upload exploded'),
    );
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open attachments' }),
    );
    fireEvent.change(
      screen.getByLabelText('Add files', { selector: 'input' }),
      {
        target: {
          files: [new File(['broken'], 'broken.txt', { type: 'text/plain' })],
        },
      },
    );

    await waitFor(() =>
      expect(stableToast.error).toHaveBeenCalledWith('upload exploded'),
    );
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('ignores an attachment upload response after the checklist route changes', async () => {
    const pendingUpload = deferred<ReturnType<typeof attachment>>();
    const current = checklist('check-latest', 18);
    const next = {
      ...checklist('check-next', 19),
      module_key: 'interior',
      vehicle_model_id: 'vehicle-b',
    };
    testMocks.fetchChecklists.mockImplementation(
      ({ moduleKey }: { moduleKey: string }) =>
        moduleKey === 'interior'
          ? {
              items: [next],
              latest_master_revision: { id: 'master-19', revision_no: 19 },
              master_revisions: [{ id: 'master-19', revision_no: 19 }],
            }
          : {
              items: [current],
              latest_master_revision: { id: 'master-18', revision_no: 18 },
              master_revisions: [{ id: 'master-18', revision_no: 18 }],
            },
    );
    testMocks.fetchRecords.mockImplementation(
      ({ checklistId }: { checklistId: string }) => ({
        checklist: checklistId === next.id ? next : current,
        definition,
        items: [record(checklistId)],
        limit: null,
        offset: 0,
        total: 1,
      }),
    );
    testMocks.uploadAttachment.mockReturnValue(pendingUpload.promise);
    const rendered = render(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open attachments' }),
    );
    fireEvent.change(
      screen.getByLabelText('Add files', { selector: 'input' }),
      {
        target: {
          files: [new File(['old'], 'old.txt', { type: 'text/plain' })],
        },
      },
    );
    await waitFor(() =>
      expect(testMocks.uploadAttachment).toHaveBeenCalledTimes(1),
    );

    testMocks.routeParams.moduleKey = 'interior';
    testMocks.routeParams.vehicleModelId = 'vehicle-b';
    testMocks.searchParams = new URLSearchParams(
      'stage_id=stage-a-p1&checklist_id=check-next',
    );
    rendered.rerender(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchRecords).toHaveBeenCalledWith(
        expect.objectContaining({ checklistId: 'check-next' }),
      ),
    );

    await act(async () => {
      pendingUpload.resolve({
        ...attachment(current.id, 'attachment-old'),
        filename: 'old.txt',
      });
      await pendingUpload.promise;
    });
    expect(screen.getByTestId('attachment-cell').textContent).toBe('');
  });

  it('deletes an attachment locally without discarding unsaved CHECK edits', async () => {
    const latest = checklist('check-latest', 18);
    testMocks.fetchRecords.mockResolvedValue({
      checklist: latest,
      definition,
      items: [record(latest.id, [attachment(latest.id)])],
      limit: null,
      offset: 0,
      total: 1,
    });
    testMocks.confirm.mockResolvedValue(true);
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    fireEvent.click(screen.getByRole('button', { name: 'Stage CHECK edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open attachments' }));
    fireEvent.change(screen.getByDisplayValue('local unsaved CHECK'), {
      target: { value: 'typed but not applied CHECK' },
    });
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete evidence.txt' }),
    );

    await waitFor(() =>
      expect(testMocks.deleteAttachment).toHaveBeenCalledWith({
        attachmentId: 'attachment-1',
        checklistId: 'check-latest',
        token: 'token',
        workspaceSlug: 'research',
      }),
    );
    await screen.findByText('No attachments.');
    expect(screen.getByTestId('check-plan').textContent).toContain(
      'local unsaved CHECK',
    );
    expect(
      screen.getByDisplayValue('typed but not applied CHECK'),
    ).not.toBeNull();
    expect(stableToast.success).toHaveBeenCalledWith('evidence.txt deleted.');
    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
  });

  it('keeps completed checklist attachments read-only and downloadable', async () => {
    const completed = {
      ...checklist('check-completed', 18),
      status: 'completed',
    };
    testMocks.fetchChecklists.mockResolvedValue({
      items: [completed],
      latest_master_revision: { id: 'master-18', revision_no: 18 },
      master_revisions: [{ id: 'master-18', revision_no: 18 }],
    });
    testMocks.fetchRecords.mockResolvedValue({
      checklist: completed,
      definition,
      items: [record(completed.id, [attachment(completed.id)])],
      limit: null,
      offset: 0,
      total: 1,
    });
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    fireEvent.click(
      await screen.findByRole('button', { name: 'Open attachments' }),
    );
    const downloadButton = await screen.findByRole('button', {
      name: 'Download evidence.txt',
    });
    expect(screen.queryByRole('button', { name: 'Add files' })).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Delete evidence.txt' }),
    ).toBeNull();
    fireEvent.click(downloadButton);
    await waitFor(() =>
      expect(browserMocks.downloadBlobAsFile).toHaveBeenCalledWith(
        expect.any(Blob),
        'evidence.txt',
      ),
    );
  });

  it('translates attachment actions and fields in checklist history', async () => {
    const latest = checklist('check-latest', 18);
    testMocks.fetchHistory.mockResolvedValue({
      checklist: latest,
      items: [
        {
          action: 'attachment_upload',
          actor_email: 'user@example.com',
          actor_name: 'User',
          actor_user_id: 'user-1',
          created_at: '2026-07-15T00:00:00Z',
          details: null,
          field_key: 'attachment',
          field_label: '첨부파일',
          id: 'history-attachment-1',
          new_value: 'evidence.txt',
          old_value: null,
          record_id: 'record-check-latest',
          record_label: 'AIR-001',
          source_master_revision_no: 18,
          source_module_key: 'aircon',
        },
      ],
    });
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    fireEvent.click(await screen.findByRole('button', { name: 'History' }));

    expect(await screen.findByText('Attachment added')).not.toBeNull();
    expect(screen.getByText('Attachments')).not.toBeNull();
    expect(screen.queryByText('attachment_upload')).toBeNull();
    expect(screen.queryByText('첨부파일')).toBeNull();
  });

  it('preserves a checklist deep link and loads that source Master Rev.', async () => {
    testMocks.searchParams = new URLSearchParams(
      'stage_id=stage-a-p1&checklist_id=check-older',
    );

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await waitFor(() =>
      expect(testMocks.fetchRecords).toHaveBeenCalledWith(
        expect.objectContaining({ checklistId: 'check-older' }),
      ),
    );
    expect(testMocks.setSearchParams).not.toHaveBeenCalled();
    expect(
      screen.queryByText('MX5 · Santa Fe · P1 · Air Conditioner'),
    ).not.toBeNull();
    expect(
      screen.getByRole('link', { name: 'Module list' }).getAttribute('href'),
    ).toBe(
      '/w/research/legacy-issues/vehicle-checklists/vehicle-a?stage_id=stage-a-p1',
    );
    expect(testMocks.fetchChecklists).toHaveBeenCalledWith({
      moduleKey: 'aircon',
      stageId: 'stage-a-p1',
      token: 'token',
      vehicleModelId: 'vehicle-a',
      workspaceSlug: 'research',
    });
  });

  it('creates a module checklist in the selected vehicle stage', async () => {
    const latest = checklist('check-latest', 18);
    const created = {
      ...checklist('check-created', 19),
      seeded_from_checklist_id: latest.id,
    };
    testMocks.fetchChecklists.mockResolvedValue({
      items: [latest],
      latest_master_revision: { id: 'master-19', revision_no: 19 },
      master_revisions: [
        { id: 'master-19', revision_no: 19 },
        { id: 'master-18', revision_no: 18 },
      ],
    });
    testMocks.createChecklist.mockResolvedValue(created);

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    const createButton = await screen.findByRole('button', {
      name: 'Create checklist',
    });
    await waitFor(() =>
      expect((createButton as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(createButton);

    await waitFor(() =>
      expect(testMocks.createChecklist).toHaveBeenCalledWith({
        moduleKey: 'aircon',
        sourceMasterRevisionId: 'master-19',
        stageId: 'stage-a-p1',
        token: 'token',
        vehicleModelId: 'vehicle-a',
        workspaceSlug: 'research',
      }),
    );
  });

  it('selects a completed checklist with stage details before importing', async () => {
    const p0Completed = {
      ...checklist('check-p0-completed', 18),
      completed_at: '2026-07-15T01:00:00Z',
      stage_id: 'stage-a-p0',
      status: 'completed',
    };
    const existingCompleted = {
      ...checklist('check-existing-completed', 17),
      completed_at: '2026-07-14T01:00:00Z',
      stage_id: 'stage-a-existing',
      status: 'completed',
    };
    const imported = {
      ...checklist('check-p1-imported', 17),
      seeded_from_checklist_id: existingCompleted.id,
    };
    testMocks.fetchChecklists.mockResolvedValue({
      items: [],
      latest_master_revision: { id: 'master-18', revision_no: 18 },
      master_revisions: [{ id: 'master-18', revision_no: 18 }],
      import_candidates: [
        {
          checklist: p0Completed,
          completed_by_email: 'p0@example.com',
          completed_by_name: 'P0 Completer',
          stage: {
            created_at: '2026-07-15T00:00:00Z',
            id: 'stage-a-p0',
            name: 'P0',
            previous_stage_id: 'stage-a-existing',
            sequence_no: 1,
            updated_at: '2026-07-15T00:00:00Z',
            vehicle_model_id: 'vehicle-a',
          },
        },
        {
          checklist: existingCompleted,
          completed_by_email: 'existing@example.com',
          completed_by_name: 'Existing Completer',
          stage: {
            created_at: '2026-07-14T00:00:00Z',
            id: 'stage-a-existing',
            name: 'Existing',
            previous_stage_id: null,
            sequence_no: 0,
            updated_at: '2026-07-14T00:00:00Z',
            vehicle_model_id: 'vehicle-a',
          },
        },
      ],
    });
    testMocks.importPreviousChecklist.mockResolvedValue(imported);

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    const importButton = await screen.findByRole('button', {
      name: 'Import completed checklist',
    });
    expect(testMocks.importPreviousChecklist).not.toHaveBeenCalled();
    fireEvent.click(importButton);
    expect(
      await screen.findByRole('heading', {
        name: 'Select a completed checklist',
      }),
    ).not.toBeNull();
    expect(screen.getByText('P0')).not.toBeNull();
    expect(screen.getByText('Existing')).not.toBeNull();
    expect(screen.getByText('Master Rev. 18')).not.toBeNull();
    expect(screen.getByText('Master Rev. 17')).not.toBeNull();
    expect(screen.getByRole('radio', { name: /P0 Completer/ })).not.toBeNull();
    expect(
      screen.getByRole('radio', { name: /Existing Completer/ }),
    ).not.toBeNull();
    expect(screen.getAllByText('1 records')).toHaveLength(2);
    expect(testMocks.importPreviousChecklist).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('radio', { name: /Existing/ }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Import selected checklist' }),
    );

    await waitFor(() =>
      expect(testMocks.importPreviousChecklist).toHaveBeenCalledWith({
        moduleKey: 'aircon',
        sourceChecklistId: existingCompleted.id,
        stageId: 'stage-a-p1',
        token: 'token',
        vehicleModelId: 'vehicle-a',
        workspaceSlug: 'research',
      }),
    );
    expect(testMocks.createChecklist).not.toHaveBeenCalled();
  });

  it('replaces an invalid checklist deep link and labels the selector', async () => {
    testMocks.searchParams = new URLSearchParams(
      'stage_id=stage-a-p1&checklist_id=missing',
    );

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await waitFor(() =>
      expect(testMocks.setSearchParams).toHaveBeenCalledWith(
        expect.objectContaining({}),
        { replace: true },
      ),
    );
    const normalizedParams = testMocks.setSearchParams.mock.calls[0]?.[0] as
      | URLSearchParams
      | undefined;
    expect(normalizedParams?.get('checklist_id')).toBe('check-latest');
    expect(
      (screen.getByLabelText('Checklist') as HTMLSelectElement).value,
    ).toBe('check-latest');
  });

  it('keeps a new route deep link while that module list is loading', async () => {
    const latest = checklist('check-latest', 18);
    const nextChecklist = {
      ...checklist('check-next', 19),
      module_key: 'interior',
      vehicle_model_id: 'vehicle-b',
    };
    const nextModuleResponse = deferred<{
      items: LegacyIssueVehicleModuleChecklist[];
      latest_master_revision: { id: string; revision_no: number };
      master_revisions: { id: string; revision_no: number }[];
    }>();
    testMocks.fetchChecklists
      .mockResolvedValueOnce({
        items: [latest],
        latest_master_revision: { id: 'master-18', revision_no: 18 },
        master_revisions: [{ id: 'master-18', revision_no: 18 }],
      })
      .mockReturnValueOnce(nextModuleResponse.promise);

    const rendered = render(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    testMocks.setSearchParams.mockClear();

    testMocks.searchParams = new URLSearchParams(
      'stage_id=stage-a-p1&checklist_id=check-next',
    );
    testMocks.routeParams.moduleKey = 'interior';
    testMocks.routeParams.vehicleModelId = 'vehicle-b';
    rendered.rerender(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchChecklists).toHaveBeenCalledWith(
        expect.objectContaining({
          moduleKey: 'interior',
          vehicleModelId: 'vehicle-b',
        }),
      ),
    );
    expect(testMocks.setSearchParams).not.toHaveBeenCalled();

    await act(async () => {
      nextModuleResponse.resolve({
        items: [nextChecklist],
        latest_master_revision: { id: 'master-19', revision_no: 19 },
        master_revisions: [{ id: 'master-19', revision_no: 19 }],
      });
      await nextModuleResponse.promise;
    });
    await waitFor(() =>
      expect(
        (screen.getByLabelText('Checklist') as HTMLSelectElement).value,
      ).toBe('check-next'),
    );
    expect(testMocks.setSearchParams).not.toHaveBeenCalled();
  });

  it('does not refetch or discard pending CHECK edits while typing or submitting search', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));

    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Stage CHECK edit' }));
    expect(screen.getByTestId('check-plan').textContent).toContain(
      'local unsaved CHECK',
    );

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'new search' },
    });
    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    expect(testMocks.fetchRecords).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('check-plan').textContent).toContain(
      'local unsaved CHECK',
    );
  });

  it('locks CHECK editing while a record search reload is in flight', async () => {
    const latest = checklist('check-latest', 18);
    const delayedRecords = deferred<{
      checklist: LegacyIssueVehicleModuleChecklist;
      definition: typeof definition;
      items: LegacyIssueVehicleModuleChecklistRecord[];
      limit: null;
      offset: number;
      total: number;
    }>();
    const response = {
      checklist: latest,
      definition,
      items: [record('check-latest')],
      limit: null,
      offset: 0,
      total: 1,
    };
    testMocks.fetchRecords
      .mockResolvedValueOnce(response)
      .mockReturnValueOnce(delayedRecords.promise);

    render(createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView));
    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'submitted search' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() =>
      expect(testMocks.fetchRecords).toHaveBeenCalledTimes(2),
    );
    expect(
      screen.queryByRole('button', { name: 'Stage CHECK edit' }),
    ).toBeNull();

    await act(async () => {
      delayedRecords.resolve(response);
      await delayedRecords.promise;
    });
    expect(
      await screen.findByRole('button', { name: 'Stage CHECK edit' }),
    ).not.toBeNull();
  });

  it('selects an adjacent checklist after permanent deletion', () => {
    const first = checklist('first', 18);
    const second = checklist('second', 17);
    const third = checklist('third', 16);
    expect(
      resolveNextVehicleModuleChecklistId([first, second, third], 'second'),
    ).toBe('third');
    expect(resolveNextVehicleModuleChecklistId([first], 'first')).toBeNull();
  });

  it('does not create in the previous module after a delayed confirmation', async () => {
    const confirmResult = deferred<boolean>();
    const latest = checklist('check-latest', 18);
    testMocks.fetchChecklists.mockResolvedValue({
      items: [latest],
      latest_master_revision: { id: 'master-18', revision_no: 18 },
      master_revisions: [
        { id: 'master-18', revision_no: 18 },
        { id: 'master-17', revision_no: 17 },
      ],
    });
    testMocks.confirm.mockReturnValue(confirmResult.promise);

    const rendered = render(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    const createButton = await screen.findByRole('button', {
      name: 'Create checklist',
    });
    await waitFor(() =>
      expect((createButton as HTMLButtonElement).disabled).toBe(false),
    );
    fireEvent.click(createButton);
    await waitFor(() => expect(testMocks.confirm).toHaveBeenCalledTimes(1));

    testMocks.routeParams.moduleKey = 'interior';
    testMocks.routeParams.vehicleModelId = 'vehicle-b';
    rendered.rerender(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchChecklists).toHaveBeenCalledWith(
        expect.objectContaining({
          moduleKey: 'interior',
          vehicleModelId: 'vehicle-b',
        }),
      ),
    );

    confirmResult.resolve(true);
    await confirmResult.promise;
    await Promise.resolve();
    expect(testMocks.createChecklist).not.toHaveBeenCalled();
  });

  it('does not let a delayed status response reload a newly selected checklist', async () => {
    const completeResult = deferred<LegacyIssueVehicleModuleChecklist>();
    const latest = checklist('check-latest', 18);
    testMocks.completeChecklist.mockReturnValue(completeResult.promise);

    const rendered = render(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await screen.findByRole('button', { name: 'Stage CHECK edit' });
    fireEvent.click(screen.getByRole('button', { name: 'Complete' }));
    await waitFor(() =>
      expect(testMocks.completeChecklist).toHaveBeenCalledWith(
        expect.objectContaining({ checklistId: 'check-latest' }),
      ),
    );
    const checklistSelector = screen
      .getAllByRole('combobox')
      .find(
        (element) => (element as HTMLSelectElement).value === 'check-latest',
      ) as HTMLSelectElement;
    expect(checklistSelector.disabled).toBe(true);
    expect(
      screen.queryByRole('button', { name: 'Stage CHECK edit' }),
    ).toBeNull();

    testMocks.searchParams = new URLSearchParams(
      'stage_id=stage-a-p1&checklist_id=check-older',
    );
    rendered.rerender(
      createElement(CoreBusinessLegacyIssueVehicleModuleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchRecords).toHaveBeenCalledWith(
        expect.objectContaining({ checklistId: 'check-older' }),
      ),
    );

    await act(async () => {
      completeResult.resolve({ ...latest, status: 'completed' });
      await completeResult.promise;
    });

    expect(testMocks.fetchChecklists).toHaveBeenCalledTimes(1);
    expect(testMocks.fetchRecords.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ checklistId: 'check-older' }),
    );
    expect(stableToast.success).not.toHaveBeenCalled();
  });
});
