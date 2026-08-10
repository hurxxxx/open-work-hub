import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import {
  CircleHelp,
  FileSearch,
  Plus,
  RefreshCw,
  Search,
  Target,
  Trash2,
  UserMinus,
} from 'lucide-react';

import {
  BarChartCard,
  Button,
  type ChartSeries,
  Dialog,
  InlineNotice,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
} from '@open-work-hub/ui';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

import {
  getAdminUsageDashboard,
  getAdminUsageTargets,
  listAdminUsageExcludedUsers,
  listAdminUsers,
  listAuditLogs,
  replaceAdminUsageExcludedUsers,
  replaceAdminUsageTargets,
  type AdminUsageDashboard,
  type AdminUsageExcludedUserItem,
  type AdminUsageTargetsResponse,
  type AuditLogItem,
} from './admin-api';
import {
  AUDIT_LOG_PAGE_SIZE,
  AuditLogList,
  AuditLogPager,
} from './admin-audit-section';
import {
  ADMIN_CHART_COLORS,
  ADMIN_CHART_SERIES_COLORS,
} from './admin-chart-colors';
import { buildPeopleDirectoryPagination } from './admin-directory-grid-model';
import {
  BodyCell,
  EmptyRow,
  FORM_FIELD_CLASS as fieldClassName,
  HeadCell,
  SurfaceCard,
  getErrorMessage,
} from './admin-shared';
import {
  buildUsageDateRangePreset,
  DEFAULT_USAGE_PERIOD_PRESET,
  getKstDateInputValue,
  getUsagePeriodPresetOptions,
  normalizeUsageDateRange,
  type UsageDateRange,
  type UsagePeriodPreset,
} from './admin-usage-period-model';
import {
  formatUsageBytes,
  formatUsageLatency,
  formatUsageNumber,
  formatUsagePercent,
  formatUsageTrendDate,
} from './admin-usage-format';
import {
  buildUsageExcludedCandidateQuery,
  USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
} from './usage-exclusions-model';

type UsageDashboardTab = 'dashboard' | 'users' | 'audit';
type UsageRankingMode = 'feature' | 'tokens';
type UsageUserItem = AdminUsageDashboard['users'][number];
type UsageBreakdownItem = AdminUsageDashboard['llm_by_model'][number];

interface UsageUserListRow {
  user_id: string;
  full_name: string;
  email: string;
  last_login_at?: string | null;
  login_count: number;
  audit_event_count: number;
  app_open_count: number;
  content_view_count: number;
  search_query_count: number;
  docs_view_count: number;
  docs_owned_count: number;
  docs_created_count: number;
  whiteboards_view_count: number;
  whiteboards_owned_count: number;
  whiteboards_created_count: number;
  meetings_created_count: number;
  pms_tasks_created_count: number;
  images_created_count: number;
  llm_call_count: number;
  llm_total_tokens: number;
  llm_average_latency_ms?: number | null;
  activity_score: number;
}

function usageUserRowFromUsage(item: UsageUserItem): UsageUserListRow {
  return { ...item };
}

function buildUsageTrendChart(
  dashboard: AdminUsageDashboard,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const points = dashboard.daily_trends ?? [];
  return {
    categories: points.map((point) => formatUsageTrendDate(point.date)),
    series: [
      {
        key: 'activeUsers',
        label: t('admin.console.usage.charts.activeUsers'),
        color: ADMIN_CHART_COLORS.primary,
        data: points.map((point) => point.active_user_count),
      },
    ],
  };
}

function buildHourlyAccessChart(
  dashboard: AdminUsageDashboard,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const points = dashboard.hourly_access ?? [];
  return {
    categories: points.map((point) => String(point.hour).padStart(2, '0')),
    series: [
      {
        key: 'averageSessionActiveEmployees',
        label: t('admin.console.usage.charts.averageSessionActiveEmployees'),
        color: ADMIN_CHART_COLORS.success,
        data: points.map((point) => point.average_visitor_count),
      },
      {
        key: 'averageLogins',
        label: t('admin.console.usage.charts.averageLogins'),
        color: ADMIN_CHART_COLORS.accent,
        data: points.map((point) => point.average_login_count),
      },
    ],
  };
}

function buildUsageRankingItems(
  dashboard: AdminUsageDashboard,
  rankingMode: UsageRankingMode,
  usageByApp: UsageBreakdownItem[],
): UsageBreakdownItem[] {
  if (rankingMode === 'feature') {
    return usageByApp;
  }
  if (rankingMode === 'tokens') {
    return (dashboard.token_rankings ?? []).map((item) => ({
      key: item.user_id,
      label: item.full_name,
      count: item.llm_total_tokens,
      total_tokens: item.llm_total_tokens,
    }));
  }
  return [];
}

function buildUsageRankingChart(
  items: UsageBreakdownItem[],
  rankingMode: UsageRankingMode,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const color =
    rankingMode === 'tokens'
      ? ADMIN_CHART_COLORS.accent
      : ADMIN_CHART_COLORS.primary;
  return {
    categories: items.map((item) => item.label),
    series: [
      {
        key: 'value',
        label: t(`admin.console.usage.rankingValues.${rankingMode}`),
        color,
        data: items.map((item) => item.count),
      },
    ],
  };
}

function usageContentCreated(item: UsageUserListRow): number {
  return (
    item.docs_created_count +
    item.whiteboards_created_count +
    item.meetings_created_count +
    item.pms_tasks_created_count +
    item.images_created_count
  );
}

function usageContentOwned(item: UsageUserListRow): number {
  return item.docs_owned_count + item.whiteboards_owned_count;
}

function localizeUsageBreakdownItems(
  items: UsageBreakdownItem[],
  t: (key: string, options?: { defaultValue?: string }) => string,
  prefix: string,
): UsageBreakdownItem[] {
  return items.map((item) => ({
    ...item,
    label: t(`${prefix}.${item.key}`, { defaultValue: item.label }),
  }));
}

function UsageMetric({
  label,
  value,
  detail,
  help,
}: {
  label: string;
  value: string;
  detail?: string;
  help?: string;
}) {
  return (
    <div className="rounded-md border border-app-border bg-app-surface-sidebar px-4 py-3">
      <UsageHelpLabel label={label} help={help} variant="metric" />
      <div className="app-text-title-md mt-1 text-app-ink">{value}</div>
      {detail ? (
        <div className="app-text-caption mt-1 text-app-ink/55">{detail}</div>
      ) : null}
    </div>
  );
}

interface UsageVisualItem {
  key: string;
  label: string;
  value: number;
  help?: string;
  detail?: string;
  color?: string;
}

const USAGE_VISUAL_COLORS = ADMIN_CHART_SERIES_COLORS;

function UsageDistributionPanel({
  emptyLabel,
  help,
  items,
  label,
  locale,
  totalDetail,
  value,
}: {
  emptyLabel: string;
  help?: string;
  items: UsageVisualItem[];
  label: string;
  locale: string;
  totalDetail?: string;
  value: number;
}) {
  const visibleItems = items.filter((item) => item.value > 0);
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  const totalValue = Math.max(
    value,
    items.reduce((total, item) => total + item.value, 0),
  );

  return (
    <div className="rounded-md border border-app-border bg-app-surface-sidebar p-4">
      <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
        <div className="min-w-0">
          <UsageHelpLabel help={help} label={label} variant="metric" />
          <div className="app-text-title mt-2 text-app-ink">
            {formatUsageNumber(value, locale)}
          </div>
          {totalDetail ? (
            <div className="app-text-caption mt-1 text-app-ink/55">
              {totalDetail}
            </div>
          ) : null}
        </div>
        <div className="min-w-0 space-y-3">
          {visibleItems.length === 0 ? (
            <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-6 text-center text-app-ink/55">
              {emptyLabel}
            </div>
          ) : (
            items.map((item, index) => {
              const color =
                item.color ??
                USAGE_VISUAL_COLORS[index % USAGE_VISUAL_COLORS.length];
              const width =
                item.value > 0 ? Math.max(5, (item.value / maxValue) * 100) : 0;
              return (
                <div className="space-y-1.5" key={item.key}>
                  <div className="flex items-center justify-between gap-3">
                    <UsageHelpLabel
                      help={item.help}
                      label={item.label}
                      variant="metric"
                    />
                    <span className="app-text-caption shrink-0 text-app-ink/55">
                      {formatUsageNumber(item.value, locale)}
                      <span className="text-app-ink/35">
                        {' '}
                        · {formatUsagePercent(item.value, totalValue, locale)}
                      </span>
                    </span>
                  </div>
                  {item.detail ? (
                    <div className="app-text-caption text-app-ink/55">
                      {item.detail}
                    </div>
                  ) : null}
                  <div className="h-2 overflow-hidden rounded-full bg-app-border">
                    <div
                      className="h-full rounded-full"
                      style={{ backgroundColor: color, width: `${width}%` }}
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

function UsageCompactMetricGrid({
  items,
}: {
  items: Array<{
    key: string;
    label: string;
    value: string;
    detail?: string;
    help?: string;
  }>;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          className="rounded-md border border-app-border bg-app-bg px-3 py-2.5"
          key={item.key}
        >
          <UsageHelpLabel
            help={item.help}
            label={item.label}
            variant="metric"
          />
          <div className="app-text-control mt-1 text-app-ink">{item.value}</div>
          {item.detail ? (
            <div className="app-text-caption mt-1 text-app-ink/55">
              {item.detail}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function UsageHelpLabel({
  label,
  help,
  variant = 'heading',
}: {
  label: string;
  help?: string;
  variant?: 'heading' | 'metric';
}) {
  const labelClassName =
    variant === 'metric'
      ? 'app-text-overline text-app-ink/55'
      : 'app-text-control text-app-ink';

  if (!help) {
    return <span className={labelClassName}>{label}</span>;
  }

  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span className={labelClassName}>{label}</span>
      <Tooltip content={help}>
        <button
          aria-label={help}
          className="inline-flex size-5 shrink-0 items-center justify-center rounded-full text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-ink focus:outline-none focus:ring-2 focus:ring-app-accent/40"
          type="button"
        >
          <CircleHelp size={13} />
        </button>
      </Tooltip>
    </span>
  );
}

function UsageChartTitle({ label, help }: { label: string; help: string }) {
  return <UsageHelpLabel help={help} label={label} variant="heading" />;
}

function DailyActiveEmployeeTable({
  dashboard,
  locale,
  t,
}: {
  dashboard: AdminUsageDashboard;
  locale: string;
  t: TFunction;
}) {
  const rows = [...(dashboard.daily_trends ?? [])].reverse();
  if (rows.length === 0) {
    return (
      <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-6 text-center text-app-ink/55">
        {t('admin.console.usage.charts.empty')}
      </div>
    );
  }

  return (
    <div className="max-h-72 overflow-auto rounded-md border border-app-border">
      <table className="min-w-full divide-y divide-app-border">
        <thead className="sticky top-0 bg-app-surface-sidebar">
          <tr>
            <th className="app-text-overline px-3 py-2 text-left text-app-ink/55">
              {t('admin.console.usage.activityTable.date')}
            </th>
            <th className="app-text-overline px-3 py-2 text-right text-app-ink/55">
              {t('admin.console.usage.activityTable.activeEmployees')}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border bg-app-bg">
          {rows.map((row) => (
            <tr key={row.date}>
              <td className="app-text-body-sm px-3 py-2 text-app-ink">
                {row.date}
              </td>
              <td className="app-text-body-sm px-3 py-2 text-right font-medium text-app-ink">
                {formatUsageNumber(row.active_user_count, locale)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsageBreakdownList({
  emptyLabel,
  formatValue,
  items,
  locale,
  showTokens = false,
  title,
}: {
  emptyLabel: string;
  formatValue?: (item: UsageBreakdownItem) => string;
  items: UsageBreakdownItem[];
  locale: string;
  showTokens?: boolean;
  title: string;
}) {
  const maxCount = Math.max(...items.map((item) => item.count), 1);

  return (
    <div className="rounded-md border border-app-border bg-app-bg">
      <div className="border-b border-app-border px-4 py-3">
        <h3 className="app-text-control text-app-ink">{title}</h3>
      </div>
      <div className="space-y-2 p-4">
        {items.length === 0 ? (
          <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-6 text-center text-app-ink/55">
            {emptyLabel}
          </div>
        ) : (
          items.map((item) => (
            <div className="space-y-1" key={item.key}>
              <div className="flex items-center justify-between gap-3">
                <span className="app-text-body-sm min-w-0 truncate font-medium text-app-ink">
                  {item.label}
                </span>
                <span className="app-text-caption shrink-0 text-app-ink/55">
                  {formatValue
                    ? formatValue(item)
                    : formatUsageNumber(item.count, locale)}
                  {showTokens
                    ? ` / ${formatUsageNumber(item.total_tokens, locale)}`
                    : ''}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-app-border">
                <div
                  className="h-full rounded-full bg-app-accent"
                  style={{
                    width: `${Math.max(6, (item.count / maxCount) * 100)}%`,
                  }}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

interface UsageExcludedSelectionItem {
  user_id: string;
  full_name: string;
  email: string;
}

function usageExcludedSelectionFromUser(
  user: AuthUser,
): UsageExcludedSelectionItem {
  return {
    user_id: user.id,
    full_name: user.full_name,
    email: user.email,
  };
}

function usageExcludedSelectionFromItem(
  item: AdminUsageExcludedUserItem,
): UsageExcludedSelectionItem {
  return {
    user_id: item.user_id,
    full_name: item.full_name,
    email: item.email,
  };
}

function usageTargetUserSelectionFromItem(
  item: AdminUsageTargetsResponse['users'][number],
): UsageExcludedSelectionItem {
  return {
    user_id: item.user_id,
    full_name: item.full_name,
    email: item.email,
  };
}

function sortUsageExcludedUsers<T extends UsageExcludedSelectionItem>(
  items: T[],
): T[] {
  return [...items].sort((left, right) => {
    const nameCompare = left.full_name.localeCompare(right.full_name);
    if (nameCompare !== 0) {
      return nameCompare;
    }
    return left.email.localeCompare(right.email);
  });
}
function UsageTargetsDialog({
  onOpenChange,
  onSaved,
  open,
  token,
}: {
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  open: boolean;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const [selectedUsersById, setSelectedUsersById] = useState<
    Record<string, UsageExcludedSelectionItem>
  >({});
  const [query, setQuery] = useState('');
  const [candidates, setCandidates] = useState<AuthUser[]>([]);
  const [candidatePage, setCandidatePage] = useState(1);
  const [candidateTotal, setCandidateTotal] = useState(0);
  const [resolvedUserCount, setResolvedUserCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedUsers = useMemo(
    () => sortUsageExcludedUsers(Object.values(selectedUsersById)),
    [selectedUsersById],
  );
  const candidatePagination = useMemo(
    () =>
      buildPeopleDirectoryPagination({
        page: candidatePage,
        total: candidateTotal,
        pageSize: USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
        loading: loading || searching,
      }),
    [candidatePage, candidateTotal, loading, searching],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setQuery('');
    setCandidatePage(1);
    void getAdminUsageTargets(token)
      .then((targets) => {
        if (cancelled) return;
        setSelectedUsersById(
          Object.fromEntries(
            targets.users.map((item) => [
              item.user_id,
              usageTargetUserSelectionFromItem(item),
            ]),
          ),
        );
        setResolvedUserCount(targets.resolved_user_count);
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(
            getErrorMessage(
              caughtError,
              t('admin.console.usage.targets.loadFailed'),
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, t, token]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      void listAdminUsers(
        token,
        buildUsageExcludedCandidateQuery({
          page: candidatePage,
          query,
        }),
      )
        .then((response) => {
          if (!cancelled) {
            setCandidates(response.items);
            setCandidateTotal(response.total);
          }
        })
        .catch((caughtError) => {
          if (!cancelled) {
            setError(
              getErrorMessage(
                caughtError,
                t('admin.console.usage.targets.searchFailed'),
              ),
            );
          }
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [candidatePage, open, query, t, token]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await replaceAdminUsageTargets(token, {
        user_ids: selectedUsers.map((item) => item.user_id),
      });
      setResolvedUserCount(response.resolved_user_count);
      onSaved();
      onOpenChange(false);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.usage.targets.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      actions={
        <>
          <Button
            disabled={saving}
            onClick={() => onOpenChange(false)}
            variant="secondary"
          >
            {t('common:actions.cancel')}
          </Button>
          <Button disabled={saving || loading} onClick={() => void save()}>
            {saving
              ? t('admin.console.usage.targets.saving')
              : t('common:actions.save')}
          </Button>
        </>
      }
      closeLabel={t('common:actions.close')}
      description={t('admin.console.usage.targets.description')}
      dismissOnInteractOutside={false}
      maxWidth="max-w-[920px] h-[min(720px,calc(100vh-2rem))]"
      onOpenChange={onOpenChange}
      open={open}
      title={t('admin.console.usage.targets.title')}
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink/70">
          {t('admin.console.usage.targets.resolvedUserCount', {
            count: resolvedUserCount,
          })}
        </div>
        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-2">
          <section className="flex min-h-0 flex-col rounded-md border border-app-border">
            <div className="shrink-0 border-b border-app-border px-4 py-3">
              <h3 className="app-text-control text-app-ink">
                {t('admin.console.usage.targets.users')}
              </h3>
            </div>
            <label className="m-3 mb-0 flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <Search className="shrink-0 text-app-ink/50" size={14} />
              <input
                className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
                onChange={(event) => {
                  setQuery(event.target.value);
                  setCandidatePage(1);
                }}
                placeholder={t(
                  'admin.console.usage.targets.userSearchPlaceholder',
                )}
                value={query}
              />
            </label>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
              {loading || searching ? (
                <div className="app-text-body-sm py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.targets.loading')}
                </div>
              ) : candidates.length === 0 ? (
                <div className="app-text-body-sm py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.targets.noSearchResults')}
                </div>
              ) : (
                candidates.map((candidate) => {
                  const selected = Boolean(selectedUsersById[candidate.id]);
                  return (
                    <div
                      className="flex items-center justify-between gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-[12px]"
                      key={candidate.id}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-semibold text-app-ink">
                          {candidate.full_name}
                        </div>
                        <div className="truncate text-app-ink/55">
                          {candidate.email}
                        </div>
                      </div>
                      <Button
                        disabled={selected}
                        onClick={() =>
                          setSelectedUsersById((current) => ({
                            ...current,
                            [candidate.id]:
                              usageExcludedSelectionFromUser(candidate),
                          }))
                        }
                        size="dense"
                        variant="secondary"
                      >
                        <Plus size={14} />
                        {selected
                          ? t('admin.console.usage.targets.added')
                          : t('admin.console.usage.targets.add')}
                      </Button>
                    </div>
                  );
                })
              )}
            </div>
            <div className="flex shrink-0 items-center justify-between border-t border-app-border px-3 py-2">
              <span className="app-text-caption text-app-ink/55">
                {candidatePagination.rangeText}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  disabled={candidatePagination.previousDisabled}
                  onClick={() =>
                    setCandidatePage((current) => Math.max(1, current - 1))
                  }
                  size="dense"
                  variant="ghost"
                >
                  {t('admin.shared.pagination.previous')}
                </Button>
                <Button
                  disabled={candidatePagination.nextDisabled}
                  onClick={() => setCandidatePage((current) => current + 1)}
                  size="dense"
                  variant="ghost"
                >
                  {t('admin.shared.pagination.next')}
                </Button>
              </div>
            </div>
          </section>
          <section className="flex min-h-0 flex-col rounded-md border border-app-border">
            <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
              <h3 className="app-text-control text-app-ink">
                {t('admin.console.usage.targets.selectedUsers')}
              </h3>
              <span className="app-text-caption text-app-ink/55">
                {selectedUsers.length}
              </span>
            </div>
            <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
              {selectedUsers.length === 0 ? (
                <div className="app-text-body-sm py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.targets.noSelectedUsers')}
                </div>
              ) : (
                selectedUsers.map((item) => (
                  <div
                    className="flex items-center justify-between gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-[12px]"
                    key={item.user_id}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-app-ink">
                        {item.full_name}
                      </div>
                      <div className="truncate text-app-ink/55">
                        {item.email}
                      </div>
                    </div>
                    <Button
                      onClick={() =>
                        setSelectedUsersById((current) => {
                          const next = { ...current };
                          delete next[item.user_id];
                          return next;
                        })
                      }
                      size="dense"
                      variant="ghost"
                    >
                      <Trash2 size={14} />
                      {t('admin.console.usage.targets.remove')}
                    </Button>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </Dialog>
  );
}


function UsageExcludedUsersDialog({
  onOpenChange,
  onSaved,
  open,
  token,
}: {
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
  open: boolean;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const [selectedById, setSelectedById] = useState<
    Record<string, UsageExcludedSelectionItem>
  >({});
  const [query, setQuery] = useState('');
  const [candidates, setCandidates] = useState<AuthUser[]>([]);
  const [candidatePage, setCandidatePage] = useState(1);
  const [candidateTotal, setCandidateTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedItems = useMemo(
    () => sortUsageExcludedUsers(Object.values(selectedById)),
    [selectedById],
  );
  const candidatePagination = useMemo(
    () =>
      buildPeopleDirectoryPagination({
        page: candidatePage,
        total: candidateTotal,
        pageSize: USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
        loading: loading || searching,
      }),
    [candidatePage, candidateTotal, loading, searching],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setQuery('');
    setCandidatePage(1);
    setCandidateTotal(0);
    setCandidates([]);
    void listAdminUsageExcludedUsers(token)
      .then((excludedUsers) => {
        if (cancelled) {
          return;
        }
        setSelectedById(
          Object.fromEntries(
            excludedUsers.map((item) => [
              item.user_id,
              usageExcludedSelectionFromItem(item),
            ]),
          ),
        );
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(
            getErrorMessage(
              caughtError,
              t('admin.console.usage.exclusions.loadFailed'),
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, t, token]);

  useEffect(() => {
    if (open) {
      setCandidatePage(1);
    }
  }, [open, query]);

  useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      void listAdminUsers(
        token,
        buildUsageExcludedCandidateQuery({
          page: candidatePage,
          query,
        }),
      )
        .then((response) => {
          if (!cancelled) {
            setCandidates(response.items);
            setCandidateTotal(response.total);
          }
        })
        .catch((caughtError) => {
          if (!cancelled) {
            setError(
              getErrorMessage(
                caughtError,
                t('admin.console.usage.exclusions.searchFailed'),
              ),
            );
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearching(false);
          }
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [candidatePage, open, query, t, token]);

  const addUser = (user: AuthUser) => {
    setSelectedById((current) => ({
      ...current,
      [user.id]: usageExcludedSelectionFromUser(user),
    }));
  };

  const removeUser = (userId: string) => {
    setSelectedById((current) => {
      const next = { ...current };
      delete next[userId];
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const response = await replaceAdminUsageExcludedUsers(
        token,
        selectedItems.map((item) => item.user_id),
      );
      setSelectedById(
        Object.fromEntries(
          response.map((item) => [
            item.user_id,
            usageExcludedSelectionFromItem(item),
          ]),
        ),
      );
      onSaved();
      onOpenChange(false);
    } catch (caughtError) {
      setError(
        getErrorMessage(
          caughtError,
          t('admin.console.usage.exclusions.saveFailed'),
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      closeLabel={t('common:actions.close')}
      description={t('admin.console.usage.exclusions.description')}
      dismissOnInteractOutside={false}
      maxWidth="max-w-[920px] h-[min(720px,calc(100vh-2rem))]"
      onOpenChange={onOpenChange}
      open={open}
      title={t('admin.console.usage.exclusions.title')}
      actions={
        <>
          <Button
            disabled={saving}
            onClick={() => onOpenChange(false)}
            variant="secondary"
          >
            {t('common:actions.cancel')}
          </Button>
          <Button disabled={saving || loading} onClick={() => void save()}>
            {saving
              ? t('admin.console.usage.exclusions.saving')
              : t('common:actions.save')}
          </Button>
        </>
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-4">
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <label className="grid shrink-0 gap-1.5">
          <span className="app-text-control text-app-ink">
            {t('admin.console.usage.exclusions.searchLabel')}
          </span>
          <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
            <Search size={14} className="shrink-0 text-app-ink/50" />
            <input
              className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t(
                'admin.console.usage.exclusions.searchPlaceholder',
              )}
              value={query}
            />
          </div>
        </label>

        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
          <section className="flex min-h-0 flex-col rounded-md border border-app-border">
            <div className="shrink-0 border-b border-app-border px-4 py-3">
              <h3 className="app-text-control text-app-ink">
                {t('admin.console.usage.exclusions.searchResults')}
              </h3>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {loading || searching ? (
                <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.exclusions.loading')}
                </div>
              ) : candidates.length === 0 ? (
                <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.exclusions.noSearchResults')}
                </div>
              ) : (
                <div className="space-y-2">
                  {candidates.map((candidate) => {
                    const selected = Boolean(selectedById[candidate.id]);
                    return (
                      <div
                        className="flex items-center justify-between gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-[12px]"
                        key={candidate.id}
                      >
                        <div className="grid min-w-0 flex-1 grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-2">
                          <span className="truncate font-semibold text-app-ink">
                            {candidate.full_name}
                          </span>
                          <span className="min-w-0 truncate text-app-ink/55">
                            {candidate.email}
                          </span>
                        </div>
                        <Button
                          disabled={selected}
                          onClick={() => addUser(candidate)}
                          size="dense"
                          variant="secondary"
                        >
                          <Plus size={14} />
                          {selected
                            ? t('admin.console.usage.exclusions.added')
                            : t('admin.console.usage.exclusions.add')}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center justify-between gap-2 border-t border-app-border px-3 py-2">
              <span className="app-text-caption text-app-ink/55">
                {candidatePagination.rangeText}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  disabled={candidatePagination.previousDisabled}
                  onClick={() =>
                    setCandidatePage((current) => Math.max(1, current - 1))
                  }
                  size="dense"
                  variant="ghost"
                >
                  {t('admin.shared.pagination.previous')}
                </Button>
                <span className="app-text-caption px-2 text-app-ink/55">
                  {candidatePagination.page} / {candidatePagination.totalPages}
                </span>
                <Button
                  disabled={candidatePagination.nextDisabled}
                  onClick={() => setCandidatePage((current) => current + 1)}
                  size="dense"
                  variant="ghost"
                >
                  {t('admin.shared.pagination.next')}
                </Button>
              </div>
            </div>
          </section>

          <section className="flex min-h-0 flex-col rounded-md border border-app-border">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-app-border px-4 py-3">
              <h3 className="app-text-control text-app-ink">
                {t('admin.console.usage.exclusions.selectedUsers')}
              </h3>
              <span className="app-text-caption text-app-ink/55">
                {t('admin.console.usage.exclusions.selectedCount', {
                  count: selectedItems.length,
                })}
              </span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {selectedItems.length === 0 ? (
                <div className="app-text-body-sm rounded-md border border-dashed border-app-border px-3 py-8 text-center text-app-ink/55">
                  {t('admin.console.usage.exclusions.noSelectedUsers')}
                </div>
              ) : (
                <div className="space-y-2">
                  {selectedItems.map((item) => (
                    <div
                      className="flex items-center justify-between gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-[12px]"
                      key={item.user_id}
                    >
                      <div className="grid min-w-0 flex-1 grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-2">
                        <span className="truncate font-semibold text-app-ink">
                          {item.full_name}
                        </span>
                        <span className="min-w-0 truncate text-app-ink/55">
                          {item.email}
                        </span>
                      </div>
                      <Button
                        onClick={() => removeUser(item.user_id)}
                        size="dense"
                        variant="ghost"
                      >
                        <Trash2 size={14} />
                        {t('admin.console.usage.exclusions.remove')}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </Dialog>
  );
}

function UsageUserAuditDialog({
  dateRange,
  locale,
  onOpenChange,
  open,
  timeZone,
  token,
  user,
}: {
  dateRange: UsageDateRange;
  locale: string;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  timeZone: string;
  token: string;
  user: UsageUserListRow | null;
}) {
  const { t } = useTranslation('apps');
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOffset(0);
  }, [dateRange.fromDate, dateRange.toDate, open, user?.user_id]);

  useEffect(() => {
    if (!open || !user) {
      setItems([]);
      setTotal(0);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    void listAuditLogs(token, {
      actor_user_id: user.user_id,
      from_date: dateRange.fromDate,
      to_date: dateRange.toDate,
      limit: AUDIT_LOG_PAGE_SIZE,
      offset,
    })
      .then((response) => {
        if (!cancelled) {
          setItems(response.items);
          setTotal(response.total);
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(
            getErrorMessage(
              caughtError,
              t('admin.console.usage.auditLoadFailed'),
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dateRange.fromDate, dateRange.toDate, offset, open, t, token, user]);

  return (
    <Dialog
      actions={
        <div className="flex w-full justify-end">
          <Button onClick={() => onOpenChange(false)} variant="secondary">
            {t('common:actions.close')}
          </Button>
        </div>
      }
      closeLabel={t('common:actions.close')}
      description={
        user
          ? t('admin.console.usage.userAuditDescription', {
              email: user.email,
            })
          : undefined
      }
      maxWidth="max-w-[980px] h-[min(720px,calc(100vh-2rem))]"
      onOpenChange={onOpenChange}
      open={open}
      title={
        user
          ? t('admin.console.usage.userAuditTitle', {
              name: user.full_name,
            })
          : t('admin.console.usage.userAuditFallbackTitle')
      }
    >
      <div className="flex min-h-0 flex-1 flex-col">
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="min-h-0 flex-1 overflow-auto">
          <AuditLogList
            emptyDescription={t(
              'admin.console.usage.userAuditEmptyDescription',
            )}
            emptyTitle={t('admin.console.usage.userAuditEmptyTitle')}
            items={items}
            loading={loading}
            loadingDescription={t('admin.console.usage.auditLoading')}
            loadingTitle={t('admin.console.usage.auditLoadingTitle')}
            locale={locale}
            timeZone={timeZone}
          />
        </div>
        <AuditLogPager
          limit={AUDIT_LOG_PAGE_SIZE}
          loading={loading}
          locale={locale}
          offset={offset}
          onNext={() => setOffset((current) => current + AUDIT_LOG_PAGE_SIZE)}
          onPrevious={() =>
            setOffset((current) => Math.max(0, current - AUDIT_LOG_PAGE_SIZE))
          }
          total={total}
        />
      </div>
    </Dialog>
  );
}
function UsageUsersTab({
  dashboard,
  dashboardLoading,
  dateRange,
  locale,
  timeZone,
  token,
}: {
  dashboard: AdminUsageDashboard | null;
  dashboardLoading: boolean;
  dateRange: UsageDateRange;
  locale: string;
  timeZone: string;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const [auditUser, setAuditUser] = useState<UsageUserListRow | null>(null);
  const rows = useMemo(
    () => (dashboard?.users ?? []).map(usageUserRowFromUsage),
    [dashboard],
  );

  return (
    <div className="flex h-[calc(100vh-210px)] min-h-[520px] min-w-0 flex-col overflow-hidden">
      <div className="app-text-control py-2 text-app-ink">
        {t('admin.console.usage.usersTabCount', { count: rows.length })}
      </div>
      <div className="min-h-0 flex-1 overflow-auto border-t border-app-border">
        <table className="app-text-body-sm w-full min-w-[1120px] table-fixed border-collapse">
          <thead>
            <tr className="sticky top-0 z-10 bg-app-surface-sidebar">
              <HeadCell className="w-[240px]" dense>{t('admin.console.usage.columns.user')}</HeadCell>
              <HeadCell className="w-[92px]" dense>{t('admin.console.usage.columns.logins')}</HeadCell>
              <HeadCell className="w-[120px]" dense>{t('admin.console.usage.columns.content')}</HeadCell>
              <HeadCell className="w-[120px]" dense>{t('admin.console.usage.columns.owned')}</HeadCell>
              <HeadCell className="w-[140px]" dense>{t('admin.console.usage.columns.consumption')}</HeadCell>
              <HeadCell className="w-[140px]" dense>{t('admin.console.usage.columns.llm')}</HeadCell>
              <HeadCell className="w-[150px]" dense>{t('admin.console.usage.columns.lastLogin')}</HeadCell>
              <HeadCell className="w-[100px] text-right" dense>{t('admin.console.usage.columns.actions')}</HeadCell>
            </tr>
          </thead>
          <tbody>
            {dashboardLoading && rows.length === 0 ? (
              <EmptyRow colSpan={8} description={t('admin.console.usage.loading')} title={t('admin.console.usage.usersLoadingTitle')} />
            ) : rows.length === 0 ? (
              <EmptyRow colSpan={8} description={t('admin.console.usage.usersEmptyDescription')} title={t('admin.console.usage.usersEmptyTitle')} />
            ) : (
              rows.map((item) => (
                <tr className="transition-colors hover:bg-app-surface-hover/40" key={item.user_id}>
                  <BodyCell dense>
                    <div className="min-w-0">
                      <div className="truncate font-medium text-app-ink">{item.full_name}</div>
                      <div className="truncate text-app-ink/55">{item.email}</div>
                    </div>
                  </BodyCell>
                  <BodyCell dense>{formatUsageNumber(item.login_count, locale)}</BodyCell>
                  <BodyCell dense>{formatUsageNumber(usageContentCreated(item), locale)}</BodyCell>
                  <BodyCell dense>{formatUsageNumber(usageContentOwned(item), locale)}</BodyCell>
                  <BodyCell dense>
                    <div>{formatUsageNumber(item.content_view_count, locale)}</div>
                    <div className="text-app-ink/55">
                      {t('admin.console.usage.consumption.userDetail', {
                        apps: formatUsageNumber(item.app_open_count, locale),
                        searches: formatUsageNumber(item.search_query_count, locale),
                      })}
                    </div>
                  </BodyCell>
                  <BodyCell dense>
                    <div>{formatUsageNumber(item.llm_call_count, locale)}</div>
                    <div className="text-app-ink/55">{formatUsageNumber(item.llm_total_tokens, locale)}</div>
                  </BodyCell>
                  <BodyCell dense>
                    {item.last_login_at
                      ? formatDateTime(item.last_login_at, {
                          dateStyle: 'medium',
                          locale,
                          timeStyle: 'short',
                          timeZone,
                        })
                      : t('admin.console.usage.never')}
                  </BodyCell>
                  <BodyCell className="text-right" dense>
                    <Button onClick={() => setAuditUser(item)} size="dense" variant="secondary">
                      <FileSearch size={14} />
                      {t('admin.console.usage.userDetail')}
                    </Button>
                  </BodyCell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <UsageUserAuditDialog
        dateRange={dateRange}
        locale={locale}
        onOpenChange={(open) => {
          if (!open) setAuditUser(null);
        }}
        open={Boolean(auditUser)}
        timeZone={timeZone}
        token={token}
        user={auditUser}
      />
    </div>
  );
}


export function UsageSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const { user } = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [tab, setTab] = useState<UsageDashboardTab>('dashboard');
  const todayDate = useMemo(() => getKstDateInputValue(), []);
  const [periodPreset, setPeriodPreset] = useState<
    UsagePeriodPreset | 'custom'
  >(DEFAULT_USAGE_PERIOD_PRESET);
  const [dateRange, setDateRange] = useState<UsageDateRange>(() =>
    buildUsageDateRangePreset(DEFAULT_USAGE_PERIOD_PRESET, todayDate),
  );
  const [draftDateRange, setDraftDateRange] = useState<UsageDateRange>(() =>
    buildUsageDateRangePreset(DEFAULT_USAGE_PERIOD_PRESET, todayDate),
  );
  const [rankingMode, setRankingMode] = useState<UsageRankingMode>('feature');
  const [dashboard, setDashboard] = useState<AdminUsageDashboard | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [auditItems, setAuditItems] = useState<AuditLogItem[]>([]);
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditSearch, setAuditSearch] = useState('');
  const [auditAction, setAuditAction] = useState('');
  const [appliedAuditSearch, setAppliedAuditSearch] = useState('');
  const [appliedAuditAction, setAppliedAuditAction] = useState('');
  const [targetsOpen, setTargetsOpen] = useState(false);
  const [exclusionsOpen, setExclusionsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const periodPresetOptions = useMemo(
    () => getUsagePeriodPresetOptions(t),
    [t],
  );

  const loadDashboard = useCallback(async () => {
    setDashboardLoading(true);
    setError(null);
    try {
      const response = await getAdminUsageDashboard(token, {
        from_date: dateRange.fromDate,
        to_date: dateRange.toDate,
        limit: 500,
      });
      setDashboard(response);
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.usage.loadFailed')),
      );
    } finally {
      setDashboardLoading(false);
    }
  }, [dateRange.fromDate, dateRange.toDate, t, token]);

  const loadAuditItems = useCallback(async () => {
    setAuditLoading(true);
    setError(null);
    try {
      const response = await listAuditLogs(token, {
        from_date: dateRange.fromDate,
        to_date: dateRange.toDate,
        limit: AUDIT_LOG_PAGE_SIZE,
        offset: auditOffset,
        q: appliedAuditSearch.trim() || undefined,
        action: appliedAuditAction.trim() || undefined,
      });
      setAuditItems(response.items);
      setAuditTotal(response.total);
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.usage.auditLoadFailed')),
      );
    } finally {
      setAuditLoading(false);
    }
  }, [
    appliedAuditAction,
    appliedAuditSearch,
    auditOffset,
    dateRange.fromDate,
    dateRange.toDate,
    t,
    token,
  ]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    void loadAuditItems();
  }, [loadAuditItems]);

  const totals = dashboard?.totals;
  const endDateActiveUserCount =
    dashboard && dashboard.daily_trends.length > 0
      ? dashboard.daily_trends[dashboard.daily_trends.length - 1]
          .active_user_count
      : 0;
  const averageDailyActiveUserCount = dashboard?.daily_trends.length
    ? Math.round(
        dashboard.daily_trends.reduce(
          (total, point) => total + point.active_user_count,
          0,
        ) / dashboard.daily_trends.length,
      )
    : 0;
  const usageByApp = useMemo(
    () =>
      dashboard
        ? localizeUsageBreakdownItems(dashboard.usage_by_app, t, 'shell:apps')
        : [],
    [dashboard, t],
  );
  const usageByRoute = useMemo(
    () => dashboard?.usage_by_route ?? [],
    [dashboard],
  );
  const contentViewsByKind = useMemo(
    () =>
      dashboard
        ? localizeUsageBreakdownItems(
            dashboard.content_views_by_kind,
            t,
            'admin.console.usage.contentKinds',
          )
        : [],
    [dashboard, t],
  );
  const usageTrendChart = useMemo(
    () => (dashboard ? buildUsageTrendChart(dashboard, t) : null),
    [dashboard, t],
  );
  const hourlyAccessChart = useMemo(
    () => (dashboard ? buildHourlyAccessChart(dashboard, t) : null),
    [dashboard, t],
  );
  const usageRankingItems = useMemo(
    () =>
      dashboard
        ? buildUsageRankingItems(dashboard, rankingMode, usageByApp)
        : [],
    [dashboard, rankingMode, usageByApp],
  );
  const usageRankingChart = useMemo(
    () => buildUsageRankingChart(usageRankingItems, rankingMode, t),
    [rankingMode, t, usageRankingItems],
  );
  const generatedAt = dashboard
    ? formatDateTime(dashboard.generated_at, {
        dateStyle: 'medium',
        locale,
        timeStyle: 'short',
        timeZone,
      })
    : null;
  const selectedDateRangeLabel = dashboard
    ? t('admin.console.usage.dateRangeLabel', {
        from: dashboard.from_date,
        to: dashboard.to_date,
      })
    : t('admin.console.usage.dateRangeLabel', {
        from: dateRange.fromDate,
        to: dateRange.toDate,
      });
  const targetScopeDetail = dashboard?.target_scope.configured
    ? t('admin.console.usage.metrics.targetScopeConfigured', {
        users: formatUsageNumber(
          dashboard.target_scope.explicit_user_count,
          locale,
        ),
      })
    : t('admin.console.usage.metrics.targetScopeAll');
  const contentCreationItems: UsageVisualItem[] = totals
    ? [
        {
          key: 'docs',
          label: t('admin.console.usage.content.docs'),
          value: totals.docs_created_count,
          help: t('admin.console.usage.help.content.docs'),
        },
        {
          key: 'whiteboards',
          label: t('admin.console.usage.content.whiteboards'),
          value: totals.whiteboards_created_count,
          help: t('admin.console.usage.help.content.whiteboards'),
        },
        {
          key: 'meetings',
          label: t('admin.console.usage.content.meetings'),
          value: totals.meetings_created_count,
          help: t('admin.console.usage.help.content.meetings'),
        },
        {
          key: 'tasks',
          label: t('admin.console.usage.content.tasks'),
          value: totals.pms_tasks_created_count,
          help: t('admin.console.usage.help.content.tasks'),
        },
        {
          key: 'images',
          label: t('admin.console.usage.content.images'),
          value: totals.images_created_count,
          help: t('admin.console.usage.help.content.images'),
        },
      ]
    : [];
  const contentConsumptionTotal = totals
    ? totals.app_open_count +
      totals.search_query_count +
      totals.docs_view_count +
      totals.whiteboards_view_count
    : 0;
  const contentConsumptionItems: UsageVisualItem[] = totals
    ? [
        {
          key: 'appOpens',
          label: t('admin.console.usage.consumption.appOpens'),
          value: totals.app_open_count,
          help: t('admin.console.usage.help.consumption.appOpens'),
        },
        {
          key: 'searches',
          label: t('admin.console.usage.consumption.searches'),
          value: totals.search_query_count,
          help: t('admin.console.usage.help.consumption.searches'),
        },
        {
          key: 'docs',
          label: t('admin.console.usage.consumption.docs'),
          value: totals.docs_view_count,
          help: t('admin.console.usage.help.consumption.docs'),
        },
        {
          key: 'whiteboards',
          label: t('admin.console.usage.consumption.whiteboards'),
          value: totals.whiteboards_view_count,
          help: t('admin.console.usage.help.consumption.whiteboards'),
        },
      ]
    : [];
  const llmStatusItems: UsageVisualItem[] = totals
    ? [
        {
          key: 'success',
          label: t('admin.console.usage.llmStatus.success'),
          value: totals.llm_success_count,
          color: ADMIN_CHART_COLORS.success,
        },
        {
          key: 'error',
          label: t('admin.console.usage.llmStatus.error'),
          value: totals.llm_error_count,
          color: ADMIN_CHART_COLORS.danger,
        },
        {
          key: 'cancelled',
          label: t('admin.console.usage.llmStatus.cancelled'),
          value: totals.llm_cancelled_count,
          color: ADMIN_CHART_COLORS.muted,
        },
      ]
    : [];
  const llmTokenItems: UsageVisualItem[] = totals
    ? [
        {
          key: 'prompt',
          label: t('admin.console.usage.metrics.promptTokens'),
          value: totals.llm_prompt_tokens,
          help: t('admin.console.usage.help.llmPromptTokens'),
          color: ADMIN_CHART_COLORS.primary,
        },
        {
          key: 'completion',
          label: t('admin.console.usage.metrics.completionTokens'),
          value: totals.llm_completion_tokens,
          help: t('admin.console.usage.help.llmCompletionTokens'),
          color: ADMIN_CHART_COLORS.accent,
        },
      ]
    : [];
  const pmsActivityTotal = dashboard
    ? dashboard.pms_summary.task_activity_count +
      dashboard.pms_summary.task_comment_count +
      dashboard.pms_summary.attachment_added_count
    : 0;
  const pmsActivityItems: UsageVisualItem[] = dashboard
    ? [
        {
          key: 'taskActivities',
          label: t('admin.console.usage.pms.taskActivities'),
          value: dashboard.pms_summary.task_activity_count,
          help: t('admin.console.usage.help.pms.taskActivities'),
        },
        {
          key: 'comments',
          label: t('admin.console.usage.pms.comments'),
          value: dashboard.pms_summary.task_comment_count,
          help: t('admin.console.usage.help.pms.comments'),
        },
        {
          key: 'attachmentsAdded',
          label: t('admin.console.usage.pms.attachmentsAdded'),
          value: dashboard.pms_summary.attachment_added_count,
          help: t('admin.console.usage.help.pms.attachmentsAdded'),
        },
      ]
    : [];

  const applyDateRange = (nextRange: UsageDateRange) => {
    const normalizedRange = normalizeUsageDateRange(nextRange, todayDate);
    setDraftDateRange(normalizedRange);
    setDateRange(normalizedRange);
    setAuditOffset(0);
  };

  const handlePresetChange = (preset: UsagePeriodPreset) => {
    setPeriodPreset(preset);
    applyDateRange(buildUsageDateRangePreset(preset, todayDate));
  };

  const handleDateRangeSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPeriodPreset('custom');
    applyDateRange(draftDateRange);
  };

  const handleAuditSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuditOffset(0);
    setAppliedAuditSearch(auditSearch);
    setAppliedAuditAction(auditAction);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as UsageDashboardTab)}
        >
          <TabsList>
            <TabsTrigger value="dashboard">
              {t('admin.console.usage.tabDashboard')}
            </TabsTrigger>
            <TabsTrigger value="users">
              {t('admin.console.usage.tabUsers')}
            </TabsTrigger>
            <TabsTrigger value="audit">
              {t('admin.console.usage.tabAudit')}
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="flex flex-col gap-2 xl:flex-row xl:items-center">
          <div
            aria-label={t('admin.console.usage.periodInputLabel')}
            className="flex flex-wrap gap-1"
            role="group"
          >
            {periodPresetOptions.map((option) => (
              <Button
                key={option.value}
                onClick={() => handlePresetChange(option.value)}
                size="dense"
                variant={
                  periodPreset === option.value ? 'primary' : 'secondary'
                }
              >
                {option.label}
              </Button>
            ))}
          </div>
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-center"
            onSubmit={handleDateRangeSubmit}
          >
            <label className="flex items-center gap-2">
              <span className="app-text-overline shrink-0 text-app-ink/55">
                {t('admin.console.usage.fromDateLabel')}
              </span>
              <input
                className={`${fieldClassName} h-9 w-full sm:w-36`}
                max={draftDateRange.toDate || todayDate}
                onChange={(event) => {
                  setPeriodPreset('custom');
                  setDraftDateRange((current) => ({
                    ...current,
                    fromDate: event.target.value,
                  }));
                }}
                type="date"
                value={draftDateRange.fromDate}
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="app-text-overline shrink-0 text-app-ink/55">
                {t('admin.console.usage.toDateLabel')}
              </span>
              <input
                className={`${fieldClassName} h-9 w-full sm:w-36`}
                max={todayDate}
                min={draftDateRange.fromDate}
                onChange={(event) => {
                  setPeriodPreset('custom');
                  setDraftDateRange((current) => ({
                    ...current,
                    toDate: event.target.value,
                  }));
                }}
                type="date"
                value={draftDateRange.toDate}
              />
            </label>
            <Button
              disabled={dashboardLoading || auditLoading}
              size="dense"
              type="submit"
              variant="secondary"
            >
              {t('admin.console.usage.applyDateRange')}
            </Button>
          </form>
          <Button onClick={() => setTargetsOpen(true)} variant="secondary">
            <Target size={16} />
            {t('admin.console.usage.targets.button')}
          </Button>
          <Button onClick={() => setExclusionsOpen(true)} variant="secondary">
            <UserMinus size={16} />
            {t('admin.console.usage.exclusions.button')}
          </Button>
          <Button
            disabled={dashboardLoading || auditLoading}
            onClick={() => {
              if (tab === 'audit') {
                void loadAuditItems();
                return;
              }
              void loadDashboard();
            }}
            variant="secondary"
          >
            <RefreshCw size={16} />
            {t('admin.console.usage.refresh')}
          </Button>
        </div>
      </div>

      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      {tab === 'dashboard' ? (
        <div className="space-y-4">
          {dashboardLoading && !dashboard ? (
            <div className="app-text-body rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-4 py-10 text-center text-app-ink/55">
              {t('admin.console.usage.loading')}
            </div>
          ) : dashboard && totals ? (
            <>
              <SurfaceCard
                description={
                  generatedAt
                    ? t('admin.console.usage.generatedAt', {
                        generatedAt,
                        range: selectedDateRangeLabel,
                      })
                    : t('admin.console.usage.summaryDescription')
                }
                title={t('admin.console.usage.summaryTitle')}
              >
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                  <UsageMetric
                    help={t('admin.console.usage.help.targetScope')}
                    label={t('admin.console.usage.metrics.targetEmployees')}
                    value={formatUsageNumber(totals.user_count, locale)}
                    detail={targetScopeDetail}
                  />
                  <UsageMetric
                    help={t('admin.console.usage.help.periodActiveEmployees')}
                    label={t(
                      'admin.console.usage.metrics.periodActiveEmployees',
                    )}
                    value={formatUsageNumber(totals.active_user_count, locale)}
                    detail={t(
                      'admin.console.usage.metrics.endDateActiveEmployees',
                      {
                        count: formatUsageNumber(
                          endDateActiveUserCount,
                          locale,
                        ),
                      },
                    )}
                  />
                  <UsageMetric
                    help={t('admin.console.usage.help.inactiveEmployees')}
                    label={t('admin.console.usage.metrics.inactiveEmployees')}
                    value={formatUsageNumber(
                      totals.inactive_user_count,
                      locale,
                    )}
                    detail={t(
                      'admin.console.usage.metrics.activeOfTotalUsers',
                      {
                        count: formatUsageNumber(
                          totals.active_user_count,
                          locale,
                        ),
                        active: formatUsageNumber(
                          totals.active_user_count,
                          locale,
                        ),
                        total: formatUsageNumber(totals.user_count, locale),
                      },
                    )}
                  />
                  <UsageMetric
                    help={t(
                      'admin.console.usage.help.averageDailyActiveEmployees',
                    )}
                    label={t(
                      'admin.console.usage.metrics.averageDailyActiveEmployees',
                    )}
                    value={formatUsageNumber(
                      averageDailyActiveUserCount,
                      locale,
                    )}
                    detail={selectedDateRangeLabel}
                  />
                  <UsageMetric
                    help={t('admin.console.usage.help.aiActiveEmployees')}
                    label={t('admin.console.usage.metrics.aiActiveEmployees')}
                    value={formatUsageNumber(totals.llm_user_count, locale)}
                    detail={t('admin.console.usage.metrics.aiActiveDetail', {
                      calls: formatUsageNumber(totals.llm_call_count, locale),
                      tokens: formatUsageNumber(
                        totals.llm_total_tokens,
                        locale,
                      ),
                    })}
                  />
                </div>
              </SurfaceCard>

              <div className="space-y-4">
                {usageTrendChart ? (
                  <BarChartCard
                    categories={usageTrendChart.categories}
                    emptyState={t('admin.console.usage.charts.empty')}
                    series={usageTrendChart.series}
                    status={
                      usageTrendChart.categories.length > 0 ? 'ready' : 'empty'
                    }
                    title={
                      <UsageChartTitle
                        help={t('admin.console.usage.help.dailyTrend')}
                        label={t('admin.console.usage.charts.dailyTitle')}
                      />
                    }
                  />
                ) : null}
                {hourlyAccessChart ? (
                  <BarChartCard
                    categories={hourlyAccessChart.categories}
                    emptyState={t('admin.console.usage.charts.empty')}
                    series={hourlyAccessChart.series}
                    status={
                      hourlyAccessChart.categories.length > 0
                        ? 'ready'
                        : 'empty'
                    }
                    title={
                      <UsageChartTitle
                        help={t('admin.console.usage.help.hourlyAccess')}
                        label={t('admin.console.usage.charts.hourlyTitle')}
                      />
                    }
                  />
                ) : null}
              </div>

              <SurfaceCard
                description={t('admin.console.usage.activityTable.description')}
                title={t('admin.console.usage.activityTable.title')}
              >
                <DailyActiveEmployeeTable
                  dashboard={dashboard}
                  locale={locale}
                  t={t}
                />
              </SurfaceCard>

              <div className="space-y-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <h3 className="app-text-title-sm text-app-ink">
                      {t('admin.console.usage.rankingsTitle')}
                    </h3>
                    <p className="app-text-body-sm mt-1 text-app-ink/55">
                      {t('admin.console.usage.rankingsDescription')}
                    </p>
                  </div>
                  <div
                    aria-label={t('admin.console.usage.rankingsTitle')}
                    className="flex flex-wrap gap-2"
                    role="group"
                  >
                    {(
                      ['feature', 'tokens'] as UsageRankingMode[]
                    ).map((mode) => (
                      <Button
                        key={mode}
                        onClick={() => setRankingMode(mode)}
                        variant={rankingMode === mode ? 'primary' : 'secondary'}
                      >
                        {t(`admin.console.usage.rankingModes.${mode}`)}
                      </Button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]">
                  <BarChartCard
                    categories={usageRankingChart.categories}
                    emptyState={t('admin.console.usage.noUsageBreakdown')}
                    series={usageRankingChart.series}
                    status={usageRankingItems.length > 0 ? 'ready' : 'empty'}
                    title={
                      <UsageChartTitle
                        help={t(
                          `admin.console.usage.help.rankings.${rankingMode}`,
                        )}
                        label={t(
                          `admin.console.usage.rankingTitles.${rankingMode}`,
                        )}
                      />
                    }
                  />
                  <UsageBreakdownList
                    emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                    items={usageRankingItems}
                    locale={locale}
                    title={t('admin.console.usage.rankingListTitle')}
                  />
                </div>
              </div>

              <div className="space-y-4">
                <SurfaceCard
                  description={t('admin.console.usage.contentDescription')}
                  title={t('admin.console.usage.contentTitle')}
                >
                  <UsageDistributionPanel
                    emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                    help={t('admin.console.usage.help.contentCreated')}
                    items={contentCreationItems}
                    label={t('admin.console.usage.metrics.contentCreated')}
                    locale={locale}
                    totalDetail={t('admin.console.usage.visuals.contentMix')}
                    value={totals.content_created_count}
                  />
                </SurfaceCard>

                <SurfaceCard
                  description={t('admin.console.usage.consumptionDescription')}
                  title={t('admin.console.usage.consumptionTitle')}
                >
                  <UsageDistributionPanel
                    emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                    help={t('admin.console.usage.help.contentViews')}
                    items={contentConsumptionItems}
                    label={t('admin.console.usage.metrics.workActivity')}
                    locale={locale}
                    totalDetail={t(
                      'admin.console.usage.visuals.consumptionMix',
                    )}
                    value={contentConsumptionTotal}
                  />
                </SurfaceCard>
              </div>

              <div className="space-y-4">
                <SurfaceCard
                  description={t('admin.console.usage.llmDescription', {
                    success: formatUsageNumber(
                      totals.llm_success_count,
                      locale,
                    ),
                    error: formatUsageNumber(totals.llm_error_count, locale),
                    cancelled: formatUsageNumber(
                      totals.llm_cancelled_count,
                      locale,
                    ),
                  })}
                  title={t('admin.console.usage.llmTitle')}
                >
                  <div className="grid gap-4 2xl:grid-cols-2">
                    <UsageDistributionPanel
                      emptyLabel={t('admin.console.usage.noLlmBreakdown')}
                      help={t('admin.console.usage.help.llmCalls')}
                      items={llmStatusItems}
                      label={t('admin.console.usage.aiUsage.calls')}
                      locale={locale}
                      totalDetail={t(
                        'admin.console.usage.visuals.llmStatusMix',
                      )}
                      value={totals.llm_call_count}
                    />
                    <UsageDistributionPanel
                      emptyLabel={t('admin.console.usage.noLlmBreakdown')}
                      help={t('admin.console.usage.help.aiUsage.tokens')}
                      items={llmTokenItems}
                      label={t('admin.console.usage.aiUsage.tokens')}
                      locale={locale}
                      totalDetail={t('admin.console.usage.visuals.llmLatency', {
                        latency: formatUsageLatency(
                          totals.llm_average_latency_ms,
                          locale,
                        ),
                      })}
                      value={totals.llm_total_tokens}
                    />
                  </div>
                </SurfaceCard>

                <SurfaceCard
                  description={t('admin.console.usage.pmsDescription')}
                  title={t('admin.console.usage.pmsTitle')}
                >
                  <UsageDistributionPanel
                    emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                    help={t('admin.console.usage.help.pms.periodActivity')}
                    items={pmsActivityItems}
                    label={t('admin.console.usage.pms.periodActivity')}
                    locale={locale}
                    totalDetail={t('admin.console.usage.pms.activeUserDetail', {
                      count: formatUsageNumber(
                        dashboard.pms_summary.active_user_count,
                        locale,
                      ),
                    })}
                    value={pmsActivityTotal}
                  />
                  <div className="mt-4">
                    <UsageCompactMetricGrid
                      items={[
                        {
                          key: 'projects',
                          label: t('admin.console.usage.pms.projects'),
                          value: formatUsageNumber(
                            dashboard.pms_summary.project_count,
                            locale,
                          ),
                          help: t('admin.console.usage.help.pms.projects'),
                        },
                        {
                          key: 'stakeholders',
                          label: t('admin.console.usage.pms.stakeholders'),
                          value: formatUsageNumber(
                            dashboard.pms_summary.stakeholder_count,
                            locale,
                          ),
                          help: t('admin.console.usage.help.pms.stakeholders'),
                        },
                        {
                          key: 'attachments',
                          label: t('admin.console.usage.pms.attachments'),
                          value: formatUsageNumber(
                            dashboard.pms_summary.attachment_count,
                            locale,
                          ),
                          detail: t('admin.console.usage.pms.attachmentBytes', {
                            size: formatUsageBytes(
                              dashboard.pms_summary.attachment_total_bytes,
                              locale,
                            ),
                          }),
                          help: t('admin.console.usage.help.pms.attachments'),
                        },
                      ]}
                    />
                  </div>
                </SurfaceCard>
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <SurfaceCard
                  description={t('admin.console.usage.aiUsageDescription')}
                  title={t('admin.console.usage.aiUsageTitle')}
                >
                  <UsageCompactMetricGrid
                    items={[
                      {
                        key: 'users',
                        label: t('admin.console.usage.aiUsage.users'),
                        value: formatUsageNumber(totals.llm_user_count, locale),
                        help: t('admin.console.usage.help.aiUsage.users'),
                      },
                      {
                        key: 'calls',
                        label: t('admin.console.usage.aiUsage.calls'),
                        value: formatUsageNumber(totals.llm_call_count, locale),
                        detail: t('admin.console.usage.aiUsage.callsPerUser', {
                          count: formatUsageNumber(
                            totals.llm_user_count > 0
                              ? Math.round(
                                  totals.llm_call_count / totals.llm_user_count,
                                )
                              : 0,
                            locale,
                          ),
                        }),
                        help: t('admin.console.usage.help.aiUsage.calls'),
                      },
                      {
                        key: 'successRate',
                        label: t('admin.console.usage.aiUsage.successRate'),
                        value: formatUsagePercent(
                          totals.llm_success_count,
                          totals.llm_call_count,
                          locale,
                        ),
                        detail: t('admin.console.usage.aiUsage.statusDetail', {
                          error: formatUsageNumber(
                            totals.llm_error_count,
                            locale,
                          ),
                          cancelled: formatUsageNumber(
                            totals.llm_cancelled_count,
                            locale,
                          ),
                        }),
                        help: t('admin.console.usage.help.aiUsage.successRate'),
                      },
                      {
                        key: 'tokens',
                        label: t('admin.console.usage.aiUsage.tokens'),
                        value: formatUsageNumber(
                          totals.llm_total_tokens,
                          locale,
                        ),
                        help: t('admin.console.usage.help.aiUsage.tokens'),
                      },
                    ]}
                  />
                </SurfaceCard>
              </div>

              <div className="grid gap-4 xl:grid-cols-3">
                <UsageBreakdownList
                  emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                  items={usageByApp}
                  locale={locale}
                  title={t('admin.console.usage.byApp')}
                />
                <UsageBreakdownList
                  emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                  items={usageByRoute}
                  locale={locale}
                  title={t('admin.console.usage.byRoute')}
                />
                <UsageBreakdownList
                  emptyLabel={t('admin.console.usage.noUsageBreakdown')}
                  items={contentViewsByKind}
                  locale={locale}
                  title={t('admin.console.usage.byContentKind')}
                />
              </div>

              <div className="grid gap-4 xl:grid-cols-2">
                <UsageBreakdownList
                  emptyLabel={t('admin.console.usage.noLlmBreakdown')}
                  items={dashboard.llm_by_task_kind}
                  locale={locale}
                  showTokens
                  title={t('admin.console.usage.byTaskKind')}
                />
                <UsageBreakdownList
                  emptyLabel={t('admin.console.usage.noLlmBreakdown')}
                  items={dashboard.llm_by_model}
                  locale={locale}
                  showTokens
                  title={t('admin.console.usage.byModel')}
                />
              </div>
            </>
          ) : (
            <div className="app-text-body rounded-md border border-dashed border-app-border bg-app-surface-sidebar px-4 py-10 text-center text-app-ink/55">
              {t('admin.console.usage.emptyDashboard')}
            </div>
          )}
        </div>
      ) : tab === 'users' ? (
        <UsageUsersTab
          dashboard={dashboard}
          dashboardLoading={dashboardLoading}
          dateRange={dateRange}
          locale={locale}
          timeZone={timeZone}
          token={token}
        />
      ) : (
        <SurfaceCard
          description={t('admin.console.usage.auditDescription')}
          title={t('admin.console.usage.auditTitle')}
        >
          <form
            className="mb-4 grid gap-2 lg:grid-cols-[minmax(0,1fr)_220px_auto]"
            onSubmit={handleAuditSubmit}
          >
            <div className="flex items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <Search size={14} className="shrink-0 text-app-ink/50" />
              <input
                aria-label={t('admin.console.usage.auditSearchPlaceholder')}
                className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/40"
                onChange={(event) => setAuditSearch(event.target.value)}
                placeholder={t('admin.console.usage.auditSearchPlaceholder')}
                value={auditSearch}
              />
            </div>
            <input
              aria-label={t('admin.console.usage.auditActionPlaceholder')}
              className={fieldClassName}
              onChange={(event) => setAuditAction(event.target.value)}
              placeholder={t('admin.console.usage.auditActionPlaceholder')}
              value={auditAction}
            />
            <Button disabled={auditLoading} type="submit" variant="secondary">
              {t('admin.console.usage.applyFilters')}
            </Button>
          </form>

          <AuditLogList
            emptyDescription={t('admin.console.usage.auditEmptyDescription')}
            emptyTitle={t('admin.console.usage.auditEmptyTitle')}
            items={auditItems}
            loading={auditLoading}
            loadingDescription={t('admin.console.usage.auditLoading')}
            loadingTitle={t('admin.console.usage.auditLoadingTitle')}
            locale={locale}
            timeZone={timeZone}
          />
          <AuditLogPager
            limit={AUDIT_LOG_PAGE_SIZE}
            loading={auditLoading}
            locale={locale}
            offset={auditOffset}
            onNext={() =>
              setAuditOffset((current) => current + AUDIT_LOG_PAGE_SIZE)
            }
            onPrevious={() =>
              setAuditOffset((current) =>
                Math.max(0, current - AUDIT_LOG_PAGE_SIZE),
              )
            }
            total={auditTotal}
          />
        </SurfaceCard>
      )}
      <UsageTargetsDialog
        onOpenChange={setTargetsOpen}
        onSaved={() => {
          void loadDashboard();
        }}
        open={targetsOpen}
        token={token}
      />
      <UsageExcludedUsersDialog
        onOpenChange={setExclusionsOpen}
        onSaved={() => {
          void loadDashboard();
        }}
        open={exclusionsOpen}
        token={token}
      />
    </div>
  );
}
