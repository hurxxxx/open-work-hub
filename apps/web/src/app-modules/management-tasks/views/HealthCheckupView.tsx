import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
  type Ref,
} from 'react';
import { EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  Button,
  DataTable,
  EmptyState,
  InlineNotice,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useConfirm,
  useToast,
  type DataTableColumn,
} from '@ai-do/ui';

import { downloadBlobAsFile } from '@/src/platform/browser/browser-download';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { AccessDeniedView } from '@/src/platform/auth/settings-pages';
import {
  exportRoster,
  type DeterminationReason,
  type EmployeeDetermination,
} from '../api/health-checkup-api';
import { AccessibleMultiSelect } from './AccessibleMultiSelect';
import {
  HealthCheckupPagination,
  type HealthCheckupPageSize,
} from './HealthCheckupPagination';
import { HealthCheckupSettingsPanel } from './HealthCheckupSettingsPanel';
import { HealthCheckupSourceStatusPanel } from './HealthCheckupSourceStatusPanel';
import { PriorExamUploadResultPanel } from './PriorExamUploadResultPanel';
import { useHealthCheckupController } from './useHealthCheckupController';

type TabId =
  | 'targets'
  | 'nonTargets'
  | 'employees'
  | 'perPersonPrice'
  | 'settings';
type DownloadId = 'roster';

// The uploaded prior-year settlement roster fixes what we compute: this year's
// completed exams drive next year's targets, so the working target year is
// always the year after the current one. There is no manual year picker.
const TARGET_YEAR = new Date().getFullYear() + 1;

// The determination tables expose employee personal data, so keep them hidden
// until the user opts in and re-hide after this much inactivity.
const PRIVACY_IDLE_MS = 5 * 60 * 1000;

// Gate the personal data behind an explicit reveal and auto-hide it again once
// the screen has been idle, so it is never left exposed unattended.
function useIdleReveal(idleMs: number): {
  revealed: boolean;
  reveal: () => void;
} {
  const [revealed, setRevealed] = useState(false);
  const reveal = useCallback(() => setRevealed(true), []);
  useEffect(() => {
    if (!revealed) return;
    let timer: ReturnType<typeof setTimeout>;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setRevealed(false), idleMs);
    };
    const events = [
      'pointermove',
      'pointerdown',
      'keydown',
      'wheel',
      'touchstart',
    ] as const;
    reset();
    for (const name of events) {
      window.addEventListener(name, reset, { passive: true });
    }
    return () => {
      clearTimeout(timer);
      for (const name of events) window.removeEventListener(name, reset);
    };
  }, [revealed, idleMs]);
  return { revealed, reveal };
}

function HealthCheckupPrivacyGate({
  onReveal,
  revealControlRef,
}: {
  onReveal: () => void;
  revealControlRef: Ref<HTMLButtonElement>;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-[var(--ui-radius-md)] border border-dashed border-app-border p-8 text-center">
      <EyeOff aria-hidden="true" className="text-app-text-muted" size={28} />
      <div className="grid gap-1">
        <strong className="text-app-text">
          {t('healthCheckup.privacy.title')}
        </strong>
        <p className="m-0 max-w-[420px] text-app-text-muted text-[length:var(--ui-text-body-sm)]">
          {t('healthCheckup.privacy.description')}
        </p>
      </div>
      <Button
        aria-controls="health-checkup-private-content"
        aria-expanded="false"
        onClick={onReveal}
        ref={revealControlRef}
        variant="secondary"
      >
        {t('healthCheckup.privacy.reveal')}
      </Button>
    </div>
  );
}

function reasonTranslationKey(reason: DeterminationReason): string {
  switch (reason) {
    case 'senior':
      return 'healthCheckup.reasons.senior';
    case 'adult_or_service':
      return 'healthCheckup.reasons.adult_or_service';
    case 'deferred':
      return 'healthCheckup.reasons.deferred';
    case 'not_eligible':
      return 'healthCheckup.reasons.not_eligible';
    case 'dispatch':
      return 'healthCheckup.reasons.dispatch';
    default:
      return 'healthCheckup.reasons.unknown';
  }
}

interface FilterBarProps {
  departmentOptions: string[];
  departments: string[];
  hasActiveFilter: boolean;
  nameOptions: string[];
  names: string[];
  onClear: () => void;
  onDepartmentsChange: (next: string[]) => void;
  onNamesChange: (next: string[]) => void;
  onPositionsChange: (next: string[]) => void;
  positionOptions: string[];
  positions: string[];
}

function HealthCheckupFilterBar({
  departmentOptions,
  departments,
  hasActiveFilter,
  nameOptions,
  names,
  onClear,
  onDepartmentsChange,
  onNamesChange,
  onPositionsChange,
  positionOptions,
  positions,
}: FilterBarProps) {
  const { t } = useTranslation(['apps', 'common']);
  const commonProps = {
    allLabel: t('apps:healthCheckup.filters.all'),
    noResultsLabel: t('common:empty.noResults'),
    searchPlaceholder: t('apps:healthCheckup.filters.search'),
    selectedText: (count: number) =>
      t('apps:healthCheckup.filters.selected', { count }),
  };

  return (
    <div className="flex flex-wrap items-end gap-2">
      <AccessibleMultiSelect
        {...commonProps}
        buttonLabel={(summary) =>
          t('apps:healthCheckup.filters.triggerLabel', {
            label: t('apps:healthCheckup.columns.dept'),
            summary,
          })
        }
        label={t('apps:healthCheckup.columns.dept')}
        onChange={onDepartmentsChange}
        options={departmentOptions}
        searchLabel={t('apps:healthCheckup.filters.searchLabel', {
          label: t('apps:healthCheckup.columns.dept'),
        })}
        selected={departments}
      />
      <AccessibleMultiSelect
        {...commonProps}
        buttonLabel={(summary) =>
          t('apps:healthCheckup.filters.triggerLabel', {
            label: t('apps:healthCheckup.columns.position'),
            summary,
          })
        }
        label={t('apps:healthCheckup.columns.position')}
        onChange={onPositionsChange}
        options={positionOptions}
        searchLabel={t('apps:healthCheckup.filters.searchLabel', {
          label: t('apps:healthCheckup.columns.position'),
        })}
        selected={positions}
      />
      <AccessibleMultiSelect
        {...commonProps}
        buttonLabel={(summary) =>
          t('apps:healthCheckup.filters.triggerLabel', {
            label: t('apps:healthCheckup.columns.name'),
            summary,
          })
        }
        label={t('apps:healthCheckup.columns.name')}
        onChange={onNamesChange}
        options={nameOptions}
        searchLabel={t('apps:healthCheckup.filters.searchLabel', {
          label: t('apps:healthCheckup.columns.name'),
        })}
        selected={names}
      />
      {hasActiveFilter ? (
        <Button onClick={onClear} variant="ghost">
          {t('apps:healthCheckup.filters.clear')}
        </Button>
      ) : null}
    </div>
  );
}

function PublishBlockers({ blockers }: { blockers: string[] }) {
  const { t } = useTranslation('apps');
  if (blockers.length === 0) return null;
  return (
    <InlineNotice tone="warning">
      <div className="grid gap-1">
        <strong>{t('healthCheckup.warnings.notPublishable')}</strong>
        <ul className="m-0 pl-4">
          {blockers.map((blocker) => (
            <li key={blocker}>
              {t(`healthCheckup.publishBlockers.${blocker}`, {
                defaultValue: t('healthCheckup.publishBlockers.unknown'),
              })}
            </li>
          ))}
        </ul>
      </div>
    </InlineNotice>
  );
}

export function HealthCheckupView() {
  const { token } = useAuth();
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  if (!token || !workspaceSlug) return null;
  return <HealthCheckupContent token={token} workspaceSlug={workspaceSlug} />;
}

function HealthCheckupContent({
  token,
  workspaceSlug,
}: {
  token: string;
  workspaceSlug: string;
}) {
  const { t, i18n } = useTranslation(['apps', 'common']);
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirm();
  const { revealed, reveal } = useIdleReveal(PRIVACY_IDLE_MS);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const revealControlRef = useRef<HTMLButtonElement>(null);
  const revealedControlRef = useRef<HTMLButtonElement>(null);
  const previouslyRevealedRef = useRef(false);
  const [activeTab, setActiveTab] = useState<TabId>('targets');
  const year = TARGET_YEAR;
  const [departments, setDepartments] = useState<string[]>([]);
  const [positions, setPositions] = useState<string[]>([]);
  const [names, setNames] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<HealthCheckupPageSize>(25);
  const [downloading, setDownloading] = useState<DownloadId | null>(null);
  const controller = useHealthCheckupController({
    settingsActive: activeTab === 'settings',
    token,
    workspaceSlug,
    year,
  });
  const allEmployees = useMemo(
    () => controller.determinations?.items ?? [],
    [controller.determinations],
  );
  const locale = i18n.resolvedLanguage ?? i18n.language;

  const distinctSorted = useCallback(
    (getter: (item: EmployeeDetermination) => string | null | undefined) =>
      Array.from(
        new Set(
          allEmployees
            .map((item) => getter(item))
            .filter((value): value is string => Boolean(value)),
        ),
      ).sort((left, right) => left.localeCompare(right, locale)),
    [allEmployees, locale],
  );
  const departmentOptions = useMemo(
    () => distinctSorted((employee) => employee.dept_name),
    [distinctSorted],
  );
  const positionOptions = useMemo(
    () => distinctSorted((employee) => employee.position),
    [distinctSorted],
  );
  const nameOptions = useMemo(
    () => distinctSorted((employee) => employee.name),
    [distinctSorted],
  );

  const applyFilters = useCallback(
    (rows: EmployeeDetermination[]) =>
      rows.filter(
        (row) =>
          (departments.length === 0 || departments.includes(row.dept_name)) &&
          (positions.length === 0 ||
            (row.position !== null && positions.includes(row.position))) &&
          (names.length === 0 || names.includes(row.name)),
      ),
    [departments, names, positions],
  );
  const targets = useMemo(
    () => allEmployees.filter((employee) => employee.is_target),
    [allEmployees],
  );
  const nonTargets = useMemo(
    () => allEmployees.filter((employee) => !employee.is_target),
    [allEmployees],
  );
  const filteredTargets = useMemo(
    () => applyFilters(targets),
    [applyFilters, targets],
  );
  const filteredNonTargets = useMemo(
    () => applyFilters(nonTargets),
    [applyFilters, nonTargets],
  );
  const filteredEmployees = useMemo(
    () => applyFilters(allEmployees),
    [allEmployees, applyFilters],
  );
  const hasActiveFilter =
    departments.length > 0 || positions.length > 0 || names.length > 0;

  useEffect(() => {
    setPage(1);
  }, [activeTab, departments, names, pageSize, positions]);

  useEffect(() => {
    if (revealed) {
      revealedControlRef.current?.focus();
    } else if (previouslyRevealedRef.current) {
      revealControlRef.current?.focus();
    }
    previouslyRevealedRef.current = revealed;
  }, [revealed]);

  const clearFilters = () => {
    setDepartments([]);
    setPositions([]);
    setNames([]);
  };

  const columns = useMemo<DataTableColumn<EmployeeDetermination>[]>(() => {
    const booleanText = (value: boolean) => (
      <span>
        <span aria-hidden="true">
          {value
            ? t('apps:healthCheckup.values.yesMark')
            : t('apps:healthCheckup.values.noMark')}
        </span>
        <span className="sr-only">
          {value
            ? t('apps:healthCheckup.values.yes')
            : t('apps:healthCheckup.values.no')}
        </span>
      </span>
    );
    const notSortable = { enableSorting: false } as const;
    return [
      {
        id: 'no',
        header: t('apps:healthCheckup.columns.no'),
        cell: ({ row }) => (page - 1) * pageSize + row.index + 1,
        ...notSortable,
      },
      {
        accessorKey: 'dept_name',
        header: t('apps:healthCheckup.columns.dept'),
        ...notSortable,
      },
      {
        accessorKey: 'position',
        header: t('apps:healthCheckup.columns.position'),
        ...notSortable,
      },
      {
        accessorKey: 'name',
        header: t('apps:healthCheckup.columns.name'),
        ...notSortable,
      },
      {
        accessorKey: 'employee_code',
        header: t('apps:healthCheckup.columns.code'),
        ...notSortable,
      },
      {
        accessorKey: 'hire_date',
        header: t('apps:healthCheckup.columns.hireDate'),
        ...notSortable,
      },
      {
        accessorKey: 'birth_date',
        header: t('apps:healthCheckup.columns.birthDate'),
        ...notSortable,
      },
      {
        accessorKey: 'age',
        header: t('apps:healthCheckup.columns.age'),
        ...notSortable,
      },
      {
        accessorKey: 'service_years',
        header: t('apps:healthCheckup.columns.serviceYears'),
        ...notSortable,
      },
      {
        id: 'senior',
        header: controller.settings
          ? t('apps:healthCheckup.columns.seniorWithAgeCompact', {
              age: controller.settings.senior_age,
            })
          : t('apps:healthCheckup.columns.senior'),
        cell: ({ row }) => booleanText(row.original.is_senior),
        ...notSortable,
      },
      {
        id: 'adult',
        header: controller.settings
          ? t('apps:healthCheckup.columns.adultWithAgeCompact', {
              age: controller.settings.adult_age,
            })
          : t('apps:healthCheckup.columns.adult'),
        cell: ({ row }) => booleanText(row.original.is_adult),
        ...notSortable,
      },
      {
        id: 'longService',
        header: controller.settings
          ? t('apps:healthCheckup.columns.longServiceWithYearsCompact', {
              years: controller.settings.service_years_threshold,
            })
          : t('apps:healthCheckup.columns.longService'),
        cell: ({ row }) => booleanText(row.original.is_long_service),
        ...notSortable,
      },
      {
        id: 'priorExam',
        header: t('apps:healthCheckup.columns.priorExam'),
        cell: ({ row }) => booleanText(row.original.prior_year_examined),
        ...notSortable,
      },
      {
        id: 'result',
        header: t('apps:healthCheckup.columns.result'),
        cell: ({ row }) =>
          row.original.is_target
            ? t('apps:healthCheckup.result.target')
            : t('apps:healthCheckup.result.nonTarget'),
        ...notSortable,
      },
    ];
  }, [controller.settings, page, pageSize, t]);
  const nonTargetColumns = useMemo<DataTableColumn<EmployeeDetermination>[]>(
    () => [
      ...columns.filter((column) => column.id !== 'result'),
      {
        id: 'reason',
        header: t('apps:healthCheckup.columns.reason'),
        cell: ({ row }) =>
          t(`apps:${reasonTranslationKey(row.original.reason)}`),
        enableSorting: false,
      },
    ],
    [columns, t],
  );

  const emptyState = (
    <EmptyState
      description={t('apps:healthCheckup.empty.description')}
      title={t('apps:healthCheckup.empty.title')}
    />
  );
  const filterBar = (
    <HealthCheckupFilterBar
      departmentOptions={departmentOptions}
      departments={departments}
      hasActiveFilter={hasActiveFilter}
      nameOptions={nameOptions}
      names={names}
      onClear={clearFilters}
      onDepartmentsChange={setDepartments}
      onNamesChange={setNames}
      onPositionsChange={setPositions}
      positionOptions={positionOptions}
      positions={positions}
    />
  );

  const renderTable = (
    rows: EmployeeDetermination[],
    tableColumns: DataTableColumn<EmployeeDetermination>[],
  ): ReactNode => {
    const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
    const safePage = Math.min(page, pageCount);
    const pageRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
    return (
      <>
        {filterBar}
        <DataTable
          columns={tableColumns}
          density="dense"
          emptyState={emptyState}
          loading={controller.loadingDeterminations}
          loadingLabel={t('apps:healthCheckup.loading.determinations')}
          rows={pageRows}
        />
        <HealthCheckupPagination
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          page={safePage}
          pageSize={pageSize}
          total={rows.length}
        />
      </>
    );
  };

  const runDownload = async (
    id: DownloadId,
    downloader: () => Promise<Blob>,
    filename: string,
  ) => {
    setDownloading(id);
    try {
      const blob = await downloader();
      downloadBlobAsFile(blob, filename);
    } catch {
      toast.error(t('apps:healthCheckup.errors.download'));
    } finally {
      setDownloading(null);
    }
  };

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) await controller.uploadPriorExamFile(file);
  };

  const handleUploadClick = async () => {
    const proceed = await confirm({
      title: t('apps:healthCheckup.upload.requirementTitle'),
      description: t('apps:healthCheckup.upload.requirementDescription'),
      confirmLabel: t('apps:healthCheckup.upload.requirementConfirm'),
      cancelLabel: t('apps:healthCheckup.upload.requirementCancel'),
    });
    if (proceed) fileInputRef.current?.click();
  };

  if (controller.fatalAccessDenied) {
    return (
      <AccessDeniedView
        description={t('apps:healthCheckup.access.workspaceAccessRequired')}
      />
    );
  }

  const data = controller.determinations;
  const determinationsReady =
    Boolean(data) && !controller.loadingDeterminations;
  const canUpload =
    Boolean(controller.sourceStatus?.available) &&
    !controller.loadingDeterminations;
  const canPublish = determinationsReady && Boolean(data?.publishable);
  const summaryMeta = data
    ? t('apps:healthCheckup.summary.targets', {
        target: data.target_count,
        total: data.total,
      })
    : '';

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="grid gap-1">
          <h1 className="m-0 text-app-text text-[length:var(--ui-text-h2)] font-semibold">
            {t('apps:healthCheckup.title')}
          </h1>
          <p className="m-0 text-app-text-muted text-[length:var(--ui-text-body-sm)]">
            {t('apps:healthCheckup.subtitle')}
          </p>
        </div>
      </header>

      {!revealed ? (
        <HealthCheckupPrivacyGate
          onReveal={reveal}
          revealControlRef={revealControlRef}
        />
      ) : (
        <div className="contents" id="health-checkup-private-content">
          <input
            accept=".xlsx"
            aria-label={t('apps:healthCheckup.upload.fileInputLabel')}
            className="hidden"
            data-testid="prior-exam-file-input"
            onChange={handleFileSelected}
            ref={fileInputRef}
            type="file"
          />
          {confirmDialog}

          <Tabs
            onValueChange={(value) => setActiveTab(value as TabId)}
            value={activeTab}
          >
            <TabsList aria-label={t('apps:healthCheckup.tabs.label')}>
              <TabsTrigger ref={revealedControlRef} value="targets">
                {t('apps:healthCheckup.tabs.targets')}
              </TabsTrigger>
              <TabsTrigger value="nonTargets">
                {t('apps:healthCheckup.tabs.nonTargets')}
              </TabsTrigger>
              <TabsTrigger value="employees">
                {t('apps:healthCheckup.tabs.employees')}
              </TabsTrigger>
              <TabsTrigger value="perPersonPrice">
                {t('apps:healthCheckup.tabs.perPersonPrice')}
              </TabsTrigger>
              <TabsTrigger value="settings">
                {t('apps:healthCheckup.tabs.settings')}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="targets">
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    disabled={controller.uploading || !canUpload}
                    onClick={() => void handleUploadClick()}
                    variant="secondary"
                  >
                    {controller.uploading
                      ? t('apps:healthCheckup.actions.uploadingPriorExam')
                      : t('apps:healthCheckup.actions.uploadPriorExam')}
                  </Button>
                  <Button
                    disabled={!canPublish || downloading !== null}
                    onClick={() =>
                      void runDownload(
                        'roster',
                        () => exportRoster({ token, workspaceSlug, year }),
                        t('apps:healthCheckup.files.roster', { year }),
                      )
                    }
                  >
                    {t('apps:healthCheckup.actions.downloadRoster')}
                  </Button>
                  {summaryMeta ? (
                    <span className="text-app-text-muted text-[length:var(--ui-text-caption)]">
                      {summaryMeta}
                    </span>
                  ) : null}
                </div>

                {controller.priorStatus && !controller.priorStatus.uploaded ? (
                  <InlineNotice tone="warning">
                    {t('apps:healthCheckup.warnings.priorExamMissing', {
                      year: year - 1,
                    })}
                  </InlineNotice>
                ) : null}
                {data ? (
                  <PublishBlockers blockers={data.publish_blockers} />
                ) : null}
                {controller.uploadResult ? (
                  <PriorExamUploadResultPanel
                    result={controller.uploadResult}
                  />
                ) : null}
                {renderTable(filteredTargets, columns)}
              </div>
            </TabsContent>

            <TabsContent value="nonTargets">
              <div className="flex flex-col gap-3">
                <span className="text-app-text-muted text-[length:var(--ui-text-caption)]">
                  {t('apps:healthCheckup.summary.nonTargets', {
                    count: nonTargets.length,
                  })}
                </span>
                {renderTable(filteredNonTargets, nonTargetColumns)}
              </div>
            </TabsContent>

            <TabsContent value="employees">
              <div className="flex flex-col gap-3">
                <span className="text-app-text-muted text-[length:var(--ui-text-caption)]">
                  {t('apps:healthCheckup.summary.total', {
                    total: allEmployees.length,
                  })}
                </span>
                {renderTable(filteredEmployees, columns)}
              </div>
            </TabsContent>

            <TabsContent value="perPersonPrice">
              <EmptyState
                description={t('apps:healthCheckup.perPersonPrice.description')}
                title={t('apps:healthCheckup.perPersonPrice.title')}
              />
            </TabsContent>

            <TabsContent value="settings">
              <div className="grid gap-4">
                <HealthCheckupSourceStatusPanel
                  loading={controller.loadingSource}
                  onRefresh={() =>
                    void controller.refreshSourceAndDeterminations()
                  }
                  refreshing={controller.refreshingSource}
                  status={controller.sourceStatus}
                />
                {controller.loadingSettings && !controller.settings ? (
                  <InlineNotice tone="info">
                    {t('apps:healthCheckup.loading.settings')}
                  </InlineNotice>
                ) : null}
                <HealthCheckupSettingsPanel
                  history={controller.history}
                  onSave={(payload) => void controller.saveSettings(payload)}
                  saving={controller.savingSettings}
                  settings={controller.settings}
                />
              </div>
            </TabsContent>
          </Tabs>
        </div>
      )}
    </div>
  );
}
