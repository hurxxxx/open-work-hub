import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Link2, Search, Settings2 } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import {
  Badge,
  Button,
  DataTable,
  DetailDrawer,
  InlineNotice,
  SearchField,
  Select,
  type DataTableColumn,
} from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';

import {
  getAdminHrMasterStatus,
  listAdminHrWorkforceCategories,
  getAdminHrEmployee,
  listAdminHrEmployees,
  resetAdminHrEmployeeWorkforceCategory,
  revokeAdminHrManualMatch,
  setAdminHrEmployeeWorkforceCategory,
  type AdminHrEmployeeDetail,
  type AdminHrEmployeeItem,
  type AdminHrEmployeesResponse,
  type AdminHrGroupSource,
  type AdminHrIdentityResolutionKind,
  type AdminHrManualMatchDirectoryItem,
  type AdminHrReconciliationStatus,
  type AdminHrSourceEmployee,
  type AdminHrWorkforceCategory,
  type AdminHrWorkforceCategoryItem,
} from './admin-api';
import {
  AdminHrCategoryManagerDialog,
  AdminHrMappingDialog,
} from './admin-hr-management-dialogs';
import {
  ADMIN_HR_PAGE_SIZE_OPTIONS,
  buildAdminHrPagination,
  getAdminHrRoleValues,
  getAdminHrSourcePresence,
  type AdminHrPageSize,
} from './admin-hr-master-model';
import { getErrorMessage } from './admin-shared';

const RECONCILIATION_STATUSES: readonly AdminHrReconciliationStatus[] = [
  'matched',
  'erp_only',
  'groupware_only',
  'identity_conflict',
];
const SYSTEM_WORKFORCE_CATEGORIES = new Set([
  'internal',
  'field',
  'external',
  'unresolved',
]);
const MASTER_REFRESH_TIMEOUT_MS = 120_000;

function ReconciliationBadge({
  status,
}: {
  status: AdminHrReconciliationStatus;
}) {
  const { t } = useTranslation('apps');
  const tone =
    status === 'matched'
      ? 'success'
      : status === 'identity_conflict'
        ? 'danger'
        : 'warning';

  return (
    <Badge tone={tone}>
      {t(`admin.console.hrMaster.reconciliation.${status}`)}
    </Badge>
  );
}

function SourceBadge({ source }: { source: AdminHrGroupSource }) {
  const { t } = useTranslation('apps');
  return (
    <Badge tone={source === 'erp' ? 'accent' : 'neutral'}>
      {t(`admin.console.hrMaster.sources.${source}`)}
    </Badge>
  );
}

function workforceCategoryLabel(
  category: AdminHrWorkforceCategory,
  categories: AdminHrWorkforceCategoryItem[],
  t: TFunction<'apps'>,
) {
  const managedCategory = categories.find((item) => item.code === category);
  if (managedCategory) {
    return managedCategory.name;
  }
  return SYSTEM_WORKFORCE_CATEGORIES.has(category)
    ? t(`admin.console.hrMaster.workforce.${category}`)
    : category;
}

function WorkforceBadge({
  categories,
  category,
}: {
  categories: AdminHrWorkforceCategoryItem[];
  category: AdminHrWorkforceCategory;
}) {
  const { t } = useTranslation('apps');
  const tone =
    category === 'internal'
      ? 'success'
      : category === 'unresolved'
        ? 'danger'
        : category === 'field'
          ? 'warning'
          : 'neutral';
  return (
    <Badge tone={tone}>{workforceCategoryLabel(category, categories, t)}</Badge>
  );
}

function EmptyValue() {
  return <span className="text-app-ink/40">-</span>;
}

function SafeValue({ value }: { value?: string | null }): ReactNode {
  return value?.trim() ? value : <EmptyValue />;
}

function mappingItemFromDetail(
  detail: AdminHrEmployeeDetail,
  source: AdminHrGroupSource,
): AdminHrManualMatchDirectoryItem | null {
  const sourceDetail = source === 'erp' ? detail.erp : detail.groupware;
  const employeeCode = sourceDetail?.employee_code?.trim();
  if (!sourceDetail || !employeeCode) {
    return null;
  }
  return {
    record_id: detail.record_id,
    employee_code: employeeCode,
    name: sourceDetail.name?.trim() || detail.name,
    group_code: sourceDetail.group_code,
    group_name: sourceDetail.group_name,
    position: sourceDetail.position,
    email: sourceDetail.email,
    login_id: sourceDetail.login_id,
  };
}

function SourceComparisonTable({
  erp,
  groupware,
}: {
  erp: AdminHrSourceEmployee | null;
  groupware: AdminHrSourceEmployee | null;
}) {
  const { t } = useTranslation('apps');
  const rows = [
    {
      key: 'employeeCode',
      erp: erp?.employee_code,
      groupware: groupware?.employee_code,
    },
    {
      key: 'name',
      erp: erp?.name,
      groupware: groupware?.name,
    },
    {
      key: 'group',
      erp: [erp?.group_code, erp?.group_name].filter(Boolean).join(' · '),
      groupware: [groupware?.group_code, groupware?.group_name]
        .filter(Boolean)
        .join(' · '),
    },
    {
      key: 'position',
      erp: erp?.position,
      groupware: groupware?.position,
    },
    {
      key: 'occupation',
      erp: erp?.occupation,
      groupware: groupware?.occupation,
    },
    {
      key: 'email',
      erp: erp?.email,
      groupware: groupware?.email,
    },
    {
      key: 'loginId',
      erp: null,
      groupware: groupware?.login_id,
    },
    {
      key: 'organizationPath',
      erp: null,
      groupware: groupware?.organization_path,
    },
  ];

  return (
    <div className="overflow-hidden rounded-xl border border-app-border">
      <table className="w-full table-fixed border-collapse">
        <thead className="bg-app-surface-sidebar">
          <tr>
            <th className="w-32 border-b border-app-border px-3 py-2 text-left app-text-caption text-app-ink/50">
              {t('admin.console.hrMaster.detail.comparisonField')}
            </th>
            <th className="border-b border-l border-app-border px-3 py-2 text-left">
              <SourceBadge source="erp" />
            </th>
            <th className="border-b border-l border-app-border px-3 py-2 text-left">
              <SourceBadge source="groupware" />
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const different =
              Boolean(row.erp?.trim() && row.groupware?.trim()) &&
              row.erp?.trim() !== row.groupware?.trim();
            return (
              <tr
                className={different ? 'bg-app-warning/10' : undefined}
                key={row.key}
              >
                <th className="border-b border-app-border px-3 py-2 text-left app-text-caption font-medium text-app-ink/50">
                  {t(`admin.console.hrMaster.fields.${row.key}`)}
                  {different ? (
                    <span className="sr-only">
                      {' '}
                      {t('admin.console.hrMaster.detail.differentValue')}
                    </span>
                  ) : null}
                </th>
                <td className="border-b border-l border-app-border px-3 py-2 align-top app-text-body-sm break-words text-app-ink">
                  <SafeValue value={row.erp} />
                </td>
                <td className="border-b border-l border-app-border px-3 py-2 align-top app-text-body-sm break-words text-app-ink">
                  <SafeValue value={row.groupware} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function HrEmployeeDetail({
  categories,
  detail,
  mutationError,
  mutationMessage,
  mutating,
  onOpenMapping,
  onRevokeManualMatch,
  onResetWorkforceCategory,
  onSetWorkforceCategory,
}: {
  categories: AdminHrWorkforceCategoryItem[];
  detail: AdminHrEmployeeDetail;
  mutationError: string | null;
  mutationMessage: string | null;
  mutating: boolean;
  onOpenMapping: () => void;
  onRevokeManualMatch: () => void;
  onResetWorkforceCategory: () => void;
  onSetWorkforceCategory: (categoryCode: string) => void;
}) {
  const { t } = useTranslation('apps');
  const [selectedCategory, setSelectedCategory] = useState(
    detail.workforce_category,
  );

  useEffect(() => {
    setSelectedCategory(detail.workforce_category);
  }, [detail.record_id, detail.workforce_category]);

  const workforceOptions = categories
    .filter((category) => category.is_active)
    .map((category) => ({
      value: category.code,
      label: category.name,
    }));
  const canManageWorkforce = detail.record_kind !== 'conflict';
  const canOpenMapping =
    detail.record_kind === 'person' &&
    (detail.reconciliation_status === 'erp_only' ||
      detail.reconciliation_status === 'groupware_only');

  return (
    <div className="space-y-5 p-5">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <ReconciliationBadge status={detail.reconciliation_status} />
          <WorkforceBadge
            categories={categories}
            category={detail.workforce_category}
          />
          {detail.workforce_category_resolution_kind === 'manual' ? (
            <Badge tone="accent">
              {t('admin.console.hrMaster.workforceResolution.manual')}
            </Badge>
          ) : null}
          {getAdminHrSourcePresence(detail).map((source) => (
            <SourceBadge key={source} source={source} />
          ))}
        </div>
        <p className="app-text-body-sm text-app-ink/55">
          {t('admin.console.hrMaster.detail.safeFieldsNotice')}
        </p>
        {detail.conflict_reasons.length > 0 ? (
          <div className="space-y-2 rounded-lg border border-app-danger-border bg-app-danger/5 p-4">
            <h2 className="app-text-control text-app-ink">
              {t('admin.console.hrMaster.detail.conflictReasonsTitle')}
            </h2>
            <ul className="list-disc space-y-1 pl-5">
              {detail.conflict_reasons.map((reason) => (
                <li className="app-text-body-sm text-app-ink/70" key={reason}>
                  {t(`admin.console.hrMaster.conflictReasons.${reason}`, {
                    defaultValue: reason,
                  })}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {detail.identity_resolution_kind === 'manual' ? (
          <Badge tone="accent">
            {t('admin.console.hrMaster.identityResolution.manual')}
          </Badge>
        ) : null}
      </section>

      {mutationError ? (
        <InlineNotice role="alert" tone="danger">
          {mutationError}
        </InlineNotice>
      ) : null}
      {mutationMessage ? (
        <InlineNotice tone="success">{mutationMessage}</InlineNotice>
      ) : null}

      {canManageWorkforce ? (
        <section className="grid gap-3 rounded-xl border border-app-border bg-app-surface-sidebar p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="app-text-title-md text-app-ink">
                {t('admin.console.hrMaster.workforceEditor.title')}
              </h2>
              <p className="app-text-body-sm mt-1 text-app-ink/55">
                {t('admin.console.hrMaster.workforceEditor.description', {
                  inferred: workforceCategoryLabel(
                    detail.inferred_workforce_category,
                    categories,
                    t,
                  ),
                })}
              </p>
            </div>
            {detail.workforce_category_resolution_kind === 'manual' ? (
              <Button
                disabled={mutating}
                onClick={onResetWorkforceCategory}
                variant="ghost"
              >
                {t('admin.console.hrMaster.workforceEditor.reset')}
              </Button>
            ) : null}
          </div>
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
            <Select
              onValueChange={setSelectedCategory}
              options={workforceOptions}
              value={selectedCategory}
            />
            <Button
              disabled={
                mutating || selectedCategory === detail.workforce_category
              }
              onClick={() => onSetWorkforceCategory(selectedCategory)}
              variant="primary"
            >
              {t('admin.console.hrMaster.workforceEditor.apply')}
            </Button>
          </div>
        </section>
      ) : null}

      {canOpenMapping || detail.manual_identity_link_id ? (
        <section className="space-y-3 rounded-xl border border-app-border p-4">
          <div>
            <h2 className="app-text-title-md text-app-ink">
              {t('admin.console.hrMaster.mapping.detailTitle')}
            </h2>
            <p className="app-text-body-sm mt-1 text-app-ink/55">
              {t(
                detail.manual_identity_link_id
                  ? 'admin.console.hrMaster.mapping.activeDescription'
                  : 'admin.console.hrMaster.mapping.detailDescription',
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {canOpenMapping ? (
              <Button
                disabled={mutating}
                onClick={onOpenMapping}
                variant="primary"
              >
                <Link2 aria-hidden="true" size={15} />
                {t('admin.console.hrMaster.mapping.openForRecord')}
              </Button>
            ) : null}
            {detail.manual_identity_link_id ? (
              <Button disabled={mutating} onClick={onRevokeManualMatch}>
                {t('admin.console.hrMaster.manualMatch.revoke')}
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="app-text-title-md text-app-ink">
          {t('admin.console.hrMaster.detail.comparisonTitle')}
        </h2>
        <SourceComparisonTable erp={detail.erp} groupware={detail.groupware} />
      </section>

      <section className="space-y-3">
        <h2 className="app-text-title-md text-app-ink">
          {t('admin.console.hrMaster.detail.provenanceTitle')}
        </h2>
        <dl className="grid gap-3 rounded-lg border border-app-border p-4">
          {[
            {
              key: 'masterRunId',
              value: detail.provenance.master_run_id,
            },
            {
              key: 'erpRunId',
              value: detail.provenance.erp_run_id,
            },
            {
              key: 'groupwareRunId',
              value: detail.provenance.groupware_run_id,
            },
            {
              key: 'erpSnapshotRowId',
              value: detail.provenance.erp_snapshot_row_id,
            },
            {
              key: 'groupwareSnapshotRowId',
              value: detail.provenance.groupware_snapshot_row_id,
            },
          ].map((field) => (
            <div
              className="grid gap-1 sm:grid-cols-[140px_minmax(0,1fr)]"
              key={field.key}
            >
              <dt className="app-text-caption text-app-ink/50">
                {t(`admin.console.hrMaster.provenance.${field.key}`)}
              </dt>
              <dd className="app-text-body-sm break-all text-app-ink">
                <SafeValue value={field.value} />
              </dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

function HrMasterSummary({
  activeCategory,
  categories,
  onCategoryChange,
  response,
}: {
  activeCategory: string | 'all';
  categories: AdminHrWorkforceCategoryItem[];
  onCategoryChange: (categoryCode: string | 'all') => void;
  response: AdminHrEmployeesResponse | null;
}) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="app-text-title-md text-app-ink">
            {t('admin.console.hrMaster.summary.title')}
          </h2>
          <p className="app-text-body-sm mt-1 text-app-ink/55">
            {response?.latest_run?.completed_at ? (
              <>
                {t('admin.console.hrMaster.summary.appliedAt')}{' '}
                <UserDateTime
                  display="datetime"
                  value={response.latest_run.completed_at}
                />
              </>
            ) : (
              t('admin.console.hrMaster.summary.notBuilt')
            )}
          </p>
        </div>
        {response?.latest_run ? (
          <Badge
            tone={
              response.latest_run.status === 'succeeded'
                ? 'success'
                : response.latest_run.status === 'failed'
                  ? 'danger'
                  : 'neutral'
            }
          >
            {t(
              `admin.console.hrMaster.runStatus.${response.latest_run.status}`,
            )}
          </Badge>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {RECONCILIATION_STATUSES.map((status) => (
          <div
            className="flex items-center gap-2 rounded-full border border-app-border bg-app-surface-sidebar px-3 py-1.5"
            key={status}
          >
            <span className="app-text-caption text-app-ink/50">
              {t(`admin.console.hrMaster.reconciliation.${status}`)}
            </span>
            <span className="app-text-control text-app-ink">
              {new Intl.NumberFormat(locale).format(
                response?.status_counts[status] ?? 0,
              )}
            </span>
          </div>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {categories
          .filter((category) => category.is_active)
          .map((category) => (
            <button
              aria-pressed={activeCategory === category.code}
              className={
                activeCategory === category.code
                  ? 'rounded-xl border border-app-accent bg-app-accent/10 px-4 py-3 text-left shadow-sm'
                  : 'rounded-xl border border-app-border bg-app-surface-sidebar px-4 py-3 text-left transition-colors hover:border-app-accent/50'
              }
              key={category.code}
              onClick={() =>
                onCategoryChange(
                  activeCategory === category.code ? 'all' : category.code,
                )
              }
              type="button"
            >
              <div className="app-text-caption text-app-ink/50">
                {category.name}
              </div>
              <div className="app-text-title-md mt-1 text-app-ink">
                {new Intl.NumberFormat(locale).format(
                  response?.workforce_counts[category.code] ?? 0,
                )}
              </div>
            </button>
          ))}
      </div>
    </section>
  );
}

function DetailDrawerContent({
  categories,
  detail,
  error,
  loading,
  mutationError,
  mutationMessage,
  mutating,
  onOpenMapping,
  onRevokeManualMatch,
  onResetWorkforceCategory,
  onSetWorkforceCategory,
}: {
  categories: AdminHrWorkforceCategoryItem[];
  detail: AdminHrEmployeeDetail | null;
  error: string | null;
  loading: boolean;
  mutationError: string | null;
  mutationMessage: string | null;
  mutating: boolean;
  onOpenMapping: () => void;
  onRevokeManualMatch: () => void;
  onResetWorkforceCategory: () => void;
  onSetWorkforceCategory: (categoryCode: string) => void;
}): ReactNode {
  const { t } = useTranslation('apps');
  if (loading) {
    return (
      <output
        aria-label={t('admin.console.hrMaster.detail.loading')}
        className="block p-5 text-app-ink/55"
      >
        {t('admin.console.hrMaster.detail.loading')}
      </output>
    );
  }
  if (error) {
    return (
      <div className="p-5">
        <InlineNotice role="alert" tone="danger">
          {error}
        </InlineNotice>
      </div>
    );
  }
  return detail ? (
    <HrEmployeeDetail
      categories={categories}
      detail={detail}
      mutationError={mutationError}
      mutationMessage={mutationMessage}
      mutating={mutating}
      onOpenMapping={onOpenMapping}
      onRevokeManualMatch={onRevokeManualMatch}
      onResetWorkforceCategory={onResetWorkforceCategory}
      onSetWorkforceCategory={onSetWorkforceCategory}
    />
  ) : null;
}

export function AdminHrMasterSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [groupFilter, setGroupFilter] = useState('all');
  const [reconciliationStatus, setReconciliationStatus] = useState<
    AdminHrReconciliationStatus | 'all'
  >('all');
  const [workforceCategory, setWorkforceCategory] = useState<
    AdminHrWorkforceCategory | 'all'
  >('all');
  const [identityResolutionKind, setIdentityResolutionKind] = useState<
    AdminHrIdentityResolutionKind | 'all'
  >('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<AdminHrPageSize>(20);
  const [response, setResponse] = useState<AdminHrEmployeesResponse | null>(
    null,
  );
  const [categories, setCategories] = useState<AdminHrWorkforceCategoryItem[]>(
    [],
  );
  const [categoryManagerOpen, setCategoryManagerOpen] = useState(false);
  const [mappingOpen, setMappingOpen] = useState(false);
  const [mappingInitialErp, setMappingInitialErp] =
    useState<AdminHrManualMatchDirectoryItem | null>(null);
  const [mappingInitialGroupware, setMappingInitialGroupware] =
    useState<AdminHrManualMatchDirectoryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEmployee, setSelectedEmployee] =
    useState<AdminHrEmployeeItem | null>(null);
  const [detail, setDetail] = useState<AdminHrEmployeeDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);
  const [globalMutationMessage, setGlobalMutationMessage] = useState<
    string | null
  >(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [pendingMasterRefresh, setPendingMasterRefresh] = useState<{
    revision: number;
    startedAt: number;
  } | null>(null);
  const [mutating, setMutating] = useState(false);
  const listRequestId = useRef(0);

  const loadCategories = useCallback(async () => {
    const nextCategories = await listAdminHrWorkforceCategories(token, true);
    setCategories(nextCategories.items);
  }, [token]);

  useEffect(() => {
    void loadCategories().catch((caughtError: unknown) => {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.categoryManager.loadFailed'),
        ),
      );
    });
  }, [loadCategories, t]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [search]);

  const loadEmployees = useCallback(async () => {
    const requestId = listRequestId.current + 1;
    listRequestId.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const nextResponse = await listAdminHrEmployees(token, {
        page,
        page_size: pageSize,
        q: debouncedSearch || undefined,
        reconciliation_status:
          reconciliationStatus === 'all' ? undefined : reconciliationStatus,
        workforce_category:
          workforceCategory === 'all' ? undefined : workforceCategory,
        identity_resolution_kind:
          identityResolutionKind === 'all' ? undefined : identityResolutionKind,
        group_code:
          groupFilter === 'all'
            ? undefined
            : groupFilter.slice(groupFilter.indexOf(':') + 1),
        group_source:
          groupFilter === 'all'
            ? undefined
            : (groupFilter.slice(
                0,
                groupFilter.indexOf(':'),
              ) as AdminHrGroupSource),
      });
      if (listRequestId.current === requestId) {
        setResponse(nextResponse);
      }
    } catch (caughtError) {
      if (listRequestId.current === requestId) {
        setResponse(null);
        setError(
          getErrorMessage(
            caughtError,
            t('admin.console.hrMaster.listLoadFailed'),
          ),
        );
      }
    } finally {
      if (listRequestId.current === requestId) {
        setLoading(false);
      }
    }
  }, [
    debouncedSearch,
    groupFilter,
    identityResolutionKind,
    page,
    pageSize,
    reconciliationStatus,
    t,
    token,
    workforceCategory,
  ]);

  useEffect(() => {
    void loadEmployees();
    return () => {
      listRequestId.current += 1;
    };
  }, [loadEmployees]);

  useEffect(() => {
    if (!pendingMasterRefresh) {
      return;
    }
    let active = true;
    let checking = false;
    const checkStatus = async () => {
      if (checking) {
        return;
      }
      checking = true;
      try {
        const status = await getAdminHrMasterStatus(token);
        if (!active) {
          return;
        }
        setRefreshError(null);
        if (
          status.latest_succeeded &&
          status.latest_succeeded.identity_resolution_revision >=
            pendingMasterRefresh.revision
        ) {
          setPendingMasterRefresh(null);
          setSelectedEmployee(null);
          setGlobalMutationMessage(
            t('admin.console.hrMaster.refresh.completed'),
          );
          await loadEmployees();
          return;
        }
        if (
          status.latest_attempt?.status === 'failed' &&
          status.latest_attempt.identity_resolution_revision >=
            pendingMasterRefresh.revision
        ) {
          setPendingMasterRefresh(null);
          setGlobalMutationMessage(null);
          setRefreshError(t('admin.console.hrMaster.refresh.failed'));
          return;
        }
        if (
          Date.now() - pendingMasterRefresh.startedAt >=
          MASTER_REFRESH_TIMEOUT_MS
        ) {
          setPendingMasterRefresh(null);
          setGlobalMutationMessage(null);
          setRefreshError(t('admin.console.hrMaster.refresh.timeout'));
        }
      } catch (caughtError) {
        if (active) {
          setRefreshError(
            getErrorMessage(
              caughtError,
              t('admin.console.hrMaster.refresh.statusLoadFailed'),
            ),
          );
        }
      } finally {
        checking = false;
      }
    };
    void checkStatus();
    const intervalId = window.setInterval(() => {
      void checkStatus();
    }, 2000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [loadEmployees, pendingMasterRefresh, t, token]);

  useEffect(() => {
    if (!selectedEmployee) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      setMutationError(null);
      setMutationMessage(null);
      setMutating(false);
      return;
    }

    let active = true;
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    void getAdminHrEmployee(token, selectedEmployee.record_id)
      .then((nextDetail) => {
        if (active) {
          setDetail(nextDetail);
        }
      })
      .catch((caughtError: unknown) => {
        if (active) {
          setDetailError(
            getErrorMessage(
              caughtError,
              t('admin.console.hrMaster.detail.loadFailed'),
            ),
          );
        }
      })
      .finally(() => {
        if (active) {
          setDetailLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [selectedEmployee, t, token]);

  const openMappingForDetail = useCallback(() => {
    if (!detail) {
      return;
    }
    setMappingInitialErp(mappingItemFromDetail(detail, 'erp'));
    setMappingInitialGroupware(mappingItemFromDetail(detail, 'groupware'));
    setMappingOpen(true);
  }, [detail]);

  const handleSetWorkforceCategory = useCallback(
    async (categoryCode: string) => {
      if (!detail) {
        return;
      }
      setMutating(true);
      setMutationError(null);
      setMutationMessage(null);
      try {
        const result = await setAdminHrEmployeeWorkforceCategory(
          token,
          detail.record_id,
          {
            master_run_id: detail.provenance.master_run_id,
            category_code: categoryCode,
          },
        );
        const message = t(
          result.rebuild_queued
            ? 'admin.console.hrMaster.workforceEditor.savedQueued'
            : result.changed
              ? 'admin.console.hrMaster.workforceEditor.savedNotQueued'
              : 'admin.console.hrMaster.workforceEditor.noChange',
        );
        setMutationMessage(message);
        setGlobalMutationMessage(message);
        if (result.rebuild_queued) {
          setRefreshError(null);
          setPendingMasterRefresh({
            revision: result.identity_resolution_revision,
            startedAt: Date.now(),
          });
        }
      } catch (caughtError) {
        setMutationError(
          getErrorMessage(
            caughtError,
            t('admin.console.hrMaster.workforceEditor.saveFailed'),
          ),
        );
      } finally {
        setMutating(false);
      }
    },
    [detail, t, token],
  );

  const handleResetWorkforceCategory = useCallback(async () => {
    if (!detail) {
      return;
    }
    setMutating(true);
    setMutationError(null);
    setMutationMessage(null);
    try {
      const result = await resetAdminHrEmployeeWorkforceCategory(
        token,
        detail.record_id,
        { master_run_id: detail.provenance.master_run_id },
      );
      const message = t(
        result.rebuild_queued
          ? 'admin.console.hrMaster.workforceEditor.resetQueued'
          : result.changed
            ? 'admin.console.hrMaster.workforceEditor.savedNotQueued'
            : 'admin.console.hrMaster.workforceEditor.noChange',
      );
      setMutationMessage(message);
      setGlobalMutationMessage(message);
      if (result.rebuild_queued) {
        setRefreshError(null);
        setPendingMasterRefresh({
          revision: result.identity_resolution_revision,
          startedAt: Date.now(),
        });
      }
    } catch (caughtError) {
      setMutationError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.workforceEditor.resetFailed'),
        ),
      );
    } finally {
      setMutating(false);
    }
  }, [detail, t, token]);

  const handleRevokeManualMatch = useCallback(async () => {
    if (!detail?.manual_identity_link_id) {
      return;
    }
    if (
      !window.confirm(t('admin.console.hrMaster.manualMatch.revokeConfirm'))
    ) {
      return;
    }
    setMutating(true);
    setMutationError(null);
    setMutationMessage(null);
    try {
      const result = await revokeAdminHrManualMatch(
        token,
        detail.manual_identity_link_id,
        { master_run_id: detail.provenance.master_run_id },
      );
      const message = t(
        result.rebuild_queued
          ? 'admin.console.hrMaster.manualMatch.revokedQueued'
          : 'admin.console.hrMaster.manualMatch.revokedNotQueued',
      );
      setMutationMessage(message);
      setGlobalMutationMessage(message);
      if (result.rebuild_queued) {
        setRefreshError(null);
        setPendingMasterRefresh({
          revision: result.identity_resolution_revision,
          startedAt: Date.now(),
        });
      }
    } catch (caughtError) {
      setMutationError(
        getErrorMessage(
          caughtError,
          t('admin.console.hrMaster.manualMatch.revokeFailed'),
        ),
      );
    } finally {
      setMutating(false);
    }
  }, [detail, t, token]);

  const columns = useMemo<DataTableColumn<AdminHrEmployeeItem>[]>(
    () => [
      {
        id: 'employee',
        header: t('admin.console.hrMaster.columns.employee'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid gap-0.5">
            <span className="font-medium text-app-ink">
              <SafeValue value={row.original.name} />
            </span>
            <span className="app-text-caption font-mono text-app-ink/55">
              <SafeValue value={row.original.employee_code} />
            </span>
            <span className="app-text-caption text-app-ink/45">
              <SafeValue value={row.original.email} />
            </span>
          </div>
        ),
      },
      {
        id: 'organizationRole',
        header: t('admin.console.hrMaster.columns.organizationRole'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid gap-0.5">
            <SafeValue value={row.original.group_name} />
            <span className="app-text-caption text-app-ink/50">
              {getAdminHrRoleValues(row.original).join(' · ') || '-'}
            </span>
          </div>
        ),
      },
      {
        id: 'sources',
        header: t('admin.console.hrMaster.columns.sources'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {getAdminHrSourcePresence(row.original).map((source) => (
              <SourceBadge key={source} source={source} />
            ))}
          </div>
        ),
      },
      {
        accessorKey: 'workforce_category',
        header: t('admin.console.hrMaster.columns.workforce'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex flex-wrap items-center gap-1">
            <WorkforceBadge
              categories={categories}
              category={row.original.workforce_category}
            />
            {row.original.workforce_category_resolution_kind === 'manual' ? (
              <Badge tone="accent">
                {t('admin.console.hrMaster.workforceResolution.manualShort')}
              </Badge>
            ) : null}
          </div>
        ),
      },
      {
        accessorKey: 'reconciliation_status',
        header: t('admin.console.hrMaster.columns.reconciliation'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid gap-1">
            <div>
              <ReconciliationBadge
                status={row.original.reconciliation_status}
              />
            </div>
            <span className="app-text-caption text-app-ink/50">
              {t(
                `admin.console.hrMaster.identityResolution.${row.original.identity_resolution_kind}`,
              )}
            </span>
          </div>
        ),
      },
      {
        accessorKey: 'applied_at',
        header: t('admin.console.hrMaster.columns.appliedAt'),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.applied_at ? (
            <UserDateTime display="datetime" value={row.original.applied_at} />
          ) : (
            <EmptyValue />
          ),
      },
    ],
    [categories, t],
  );

  const pagination = buildAdminHrPagination({
    loading,
    page,
    pageSize,
    total: response?.total ?? 0,
  });
  const reconciliationOptions = useMemo(
    () => [
      {
        value: 'all',
        label: t('admin.console.hrMaster.filters.allStatuses'),
      },
      ...RECONCILIATION_STATUSES.map((status) => ({
        value: status,
        label: t(`admin.console.hrMaster.reconciliation.${status}`),
      })),
    ],
    [t],
  );
  const pageSizeOptions = useMemo(
    () =>
      ADMIN_HR_PAGE_SIZE_OPTIONS.map((value) => ({
        value: String(value),
        label: t('admin.console.hrMaster.pagination.pageSizeOption', {
          count: value,
        }),
      })),
    [t],
  );
  const workforceOptions = useMemo(
    () => [
      {
        value: 'all',
        label: t('admin.console.hrMaster.filters.allWorkforce'),
      },
      ...categories
        .filter((category) => category.is_active)
        .map((category) => ({
          value: category.code,
          label: category.name,
        })),
    ],
    [categories, t],
  );
  const identityResolutionOptions = useMemo(
    () => [
      {
        value: 'all',
        label: t('admin.console.hrMaster.filters.allIdentityResolutions'),
      },
      {
        value: 'manual',
        label: t('admin.console.hrMaster.identityResolution.manual'),
      },
      {
        value: 'employee_code',
        label: t('admin.console.hrMaster.identityResolution.employee_code'),
      },
      {
        value: 'none',
        label: t('admin.console.hrMaster.identityResolution.none'),
      },
    ],
    [t],
  );
  const groupOptions = useMemo(() => {
    const options = [
      { value: 'all', label: t('admin.console.hrMaster.filters.allGroups') },
    ];
    for (const group of response?.groups ?? []) {
      options.push({
        value: `${group.source}:${group.code}`,
        label: `${group.name} · ${group.code} · ${t(
          `admin.console.hrMaster.sources.${group.source}`,
        )}`,
      });
    }
    return options;
  }, [response?.groups, t]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="app-text-title-md text-app-ink">
            {t('admin.console.hrMaster.workspace.title')}
          </h2>
          <p className="app-text-body-sm mt-1 text-app-ink/55">
            {t('admin.console.hrMaster.workspace.description')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            disabled={Boolean(pendingMasterRefresh)}
            onClick={() => {
              setMappingInitialErp(null);
              setMappingInitialGroupware(null);
              setMappingOpen(true);
            }}
            variant="primary"
          >
            <Link2 aria-hidden="true" size={15} />
            {t('admin.console.hrMaster.mapping.open')}
          </Button>
          <Button onClick={() => setCategoryManagerOpen(true)}>
            <Settings2 aria-hidden="true" size={15} />
            {t('admin.console.hrMaster.categoryManager.open')}
          </Button>
        </div>
      </div>

      <InlineNotice tone="info">
        {t('admin.console.hrMaster.readOnlyNotice')}
      </InlineNotice>
      {globalMutationMessage ? (
        <InlineNotice tone="success">{globalMutationMessage}</InlineNotice>
      ) : null}
      {pendingMasterRefresh ? (
        <InlineNotice tone="info">
          {t('admin.console.hrMaster.refresh.pending')}
        </InlineNotice>
      ) : null}
      {refreshError ? (
        <InlineNotice role="alert" tone="danger">
          {refreshError}
        </InlineNotice>
      ) : null}

      <HrMasterSummary
        activeCategory={workforceCategory}
        categories={categories}
        onCategoryChange={(categoryCode) => {
          setWorkforceCategory(categoryCode);
          setPage(1);
        }}
        response={response}
      />

      <section className="space-y-3">
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_160px_160px_160px_220px]">
          <SearchField
            aria-label={t('admin.console.hrMaster.filters.searchLabel')}
            endAdornment={<Search aria-hidden="true" size={16} />}
            maxLength={120}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('admin.console.hrMaster.filters.searchPlaceholder')}
            value={search}
          />
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.filters.statusLabel')}
            </span>
            <Select
              className="w-full"
              onValueChange={(value) => {
                setReconciliationStatus(
                  value as AdminHrReconciliationStatus | 'all',
                );
                setPage(1);
              }}
              options={reconciliationOptions}
              value={reconciliationStatus}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.filters.identityResolutionLabel')}
            </span>
            <Select
              className="w-full"
              onValueChange={(value) => {
                setIdentityResolutionKind(
                  value as AdminHrIdentityResolutionKind | 'all',
                );
                setPage(1);
              }}
              options={identityResolutionOptions}
              value={identityResolutionKind}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.filters.workforceLabel')}
            </span>
            <Select
              className="w-full"
              onValueChange={(value) => {
                setWorkforceCategory(value as AdminHrWorkforceCategory | 'all');
                setPage(1);
              }}
              options={workforceOptions}
              value={workforceCategory}
            />
          </label>
          <label className="grid gap-1">
            <span className="app-text-caption text-app-ink/55">
              {t('admin.console.hrMaster.filters.groupLabel')}
            </span>
            <Select
              className="w-full"
              onValueChange={(value) => {
                setGroupFilter(value);
                setPage(1);
              }}
              options={groupOptions}
              value={groupFilter}
            />
          </label>
        </div>

        {error ? (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        ) : null}

        <div className="overflow-hidden rounded-xl border border-app-border bg-app-surface">
          <div className="flex items-center justify-between border-b border-app-border bg-app-surface-sidebar px-3 py-2">
            <span className="app-text-caption text-app-ink/50">
              {t('admin.console.hrMaster.listCount', {
                count: new Intl.NumberFormat(locale).format(
                  response?.total ?? 0,
                ),
              })}
            </span>
            <label className="flex items-center gap-2">
              <span className="app-text-caption text-app-ink/50">
                {t('admin.console.hrMaster.pagination.pageSizeLabel')}
              </span>
              <Select
                onValueChange={(value) => {
                  setPageSize(Number(value) as AdminHrPageSize);
                  setPage(1);
                }}
                options={pageSizeOptions}
                value={String(pageSize)}
              />
            </label>
          </div>
          <DataTable
            columns={columns}
            emptyState={
              <div className="space-y-1 py-5 text-center">
                <div className="app-text-body font-medium text-app-ink">
                  {t('admin.console.hrMaster.emptyTitle')}
                </div>
                <div className="app-text-body-sm text-app-ink/55">
                  {t('admin.console.hrMaster.emptyDescription')}
                </div>
              </div>
            }
            loading={loading}
            loadingLabel={t('admin.console.hrMaster.loading')}
            rows={response?.items ?? []}
            selection={{
              selectedRowId: selectedEmployee?.record_id,
              getRowId: (row) => row.record_id,
              onRowClick: setSelectedEmployee,
            }}
          />
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="app-text-body-sm text-app-ink/60">
            {t('admin.console.hrMaster.pagination.range', {
              from: new Intl.NumberFormat(locale).format(pagination.from),
              to: new Intl.NumberFormat(locale).format(pagination.to),
              total: new Intl.NumberFormat(locale).format(response?.total ?? 0),
            })}
          </div>
          <div className="flex gap-2">
            <Button
              disabled={pagination.previousDisabled}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              {t('admin.console.hrMaster.pagination.previous')}
            </Button>
            <Button
              disabled={pagination.nextDisabled}
              onClick={() => setPage((current) => current + 1)}
            >
              {t('admin.console.hrMaster.pagination.next')}
            </Button>
          </div>
        </div>
      </section>

      <DetailDrawer
        closeLabel={t('common:actions.close')}
        contentClassName="w-[min(920px,100vw)]"
        description={selectedEmployee?.employee_code ?? undefined}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedEmployee(null);
          }
        }}
        open={Boolean(selectedEmployee)}
        title={
          selectedEmployee?.name.trim() ||
          t('admin.console.hrMaster.detail.fallbackTitle')
        }
      >
        <DetailDrawerContent
          categories={categories}
          detail={detail}
          error={detailError}
          loading={detailLoading}
          mutationError={mutationError}
          mutationMessage={mutationMessage}
          mutating={mutating || Boolean(pendingMasterRefresh)}
          onOpenMapping={openMappingForDetail}
          onRevokeManualMatch={() => {
            void handleRevokeManualMatch();
          }}
          onResetWorkforceCategory={() => {
            void handleResetWorkforceCategory();
          }}
          onSetWorkforceCategory={(categoryCode) => {
            void handleSetWorkforceCategory(categoryCode);
          }}
        />
      </DetailDrawer>

      <AdminHrMappingDialog
        initialErp={mappingInitialErp}
        initialGroupware={mappingInitialGroupware}
        masterRunId={response?.latest_run?.id ?? null}
        onCompleted={(result) => {
          const message = t(
            result.rebuild_queued
              ? 'admin.console.hrMaster.mapping.savedQueued'
              : 'admin.console.hrMaster.mapping.savedNotQueued',
          );
          setMutationMessage(message);
          setGlobalMutationMessage(message);
          if (result.rebuild_queued) {
            setRefreshError(null);
            setPendingMasterRefresh({
              revision: result.identity_resolution_revision,
              startedAt: Date.now(),
            });
          }
        }}
        onOpenChange={setMappingOpen}
        open={mappingOpen}
        token={token}
      />

      <AdminHrCategoryManagerDialog
        categories={categories}
        onChanged={loadCategories}
        onOpenChange={setCategoryManagerOpen}
        open={categoryManagerOpen}
        token={token}
      />
    </div>
  );
}
