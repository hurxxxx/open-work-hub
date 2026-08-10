import React from 'react';
import type { TFunction } from 'i18next';
import { Search } from 'lucide-react';

import { Button, type ChartSeries, Dialog, InlineNotice } from '@ai-do/ui';

import { formatDateTime } from '@/src/platform/time/time-utils';

import type {
  AiSecurityDetectedValueGroup,
  AiSecurityDetectedValueStat,
  AiSecurityMonitoring,
  AiSecurityMonitoringBreakdownItem,
} from './admin-api';
import { AuditLogPager } from './admin-audit-section';
import { ADMIN_CHART_COLORS } from './admin-chart-colors';
import { AI_SECURITY_DETECTED_VALUE_PAGE_SIZE } from './admin-ai-security-model';
import { BodyCell, EmptyRow, HeadCell } from './admin-shared';
import { formatUsageNumber, formatUsageTrendDate } from './admin-usage-format';

export function AiSecurityMetric({
  label,
  value,
  detail,
  onClick,
}: {
  label: string;
  value: string | number;
  detail?: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <div className="app-text-overline text-app-ink/55">{label}</div>
      <div className="app-text-title-md mt-1 text-app-ink">{value}</div>
      {detail ? (
        <div className="app-text-caption mt-1 text-app-ink/55">{detail}</div>
      ) : null}
    </>
  );
  return onClick ? (
    <button
      className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-left transition-colors hover:border-app-accent/50 hover:bg-app-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/30"
      onClick={onClick}
      type="button"
    >
      {content}
    </button>
  ) : (
    <div className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      {content}
    </div>
  );
}

export function aiSecurityMonitoringReasonLabel(
  t: TFunction,
  key: string,
): string {
  return t(`admin.console.aiSecurity.monitoring.reasons.${key}`, {
    defaultValue: key.replaceAll('_', ' '),
  });
}

export function aiSecurityMonitoringEntityLabel(
  t: TFunction,
  key: string,
): string {
  if (key.includes(':')) {
    const [base, detail] = key.split(':');
    const baseLabel = t(`admin.console.aiSecurity.blockers.${base}`, {
      defaultValue: base.replaceAll('_', ' '),
    });
    return `${baseLabel} (${detail})`;
  }
  return t(`admin.console.aiSecurity.blockers.${key}`, {
    defaultValue: t(`admin.console.aiSecurity.monitoring.entities.${key}`, {
      defaultValue: key.replaceAll('_', ' '),
    }),
  });
}

export function aiSecurityMonitoringDetectorLabel(
  t: TFunction,
  key: string,
): string {
  return t(`admin.console.aiSecurity.monitoring.detectors.${key}`, {
    defaultValue: key.replaceAll('_', ' '),
  });
}

export function buildAiSecurityMonitoringTrendChart(
  monitoring: AiSecurityMonitoring,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const points = monitoring.daily_trends ?? [];
  return {
    categories: points.map((point) => formatUsageTrendDate(point.date)),
    series: [
      {
        key: 'blocked',
        label: t('admin.console.aiSecurity.monitoring.charts.blocked'),
        color: ADMIN_CHART_COLORS.danger,
        data: points.map((point) => point.blocked_count),
      },
      {
        key: 'masked',
        label: t('admin.console.aiSecurity.monitoring.charts.masked'),
        color: ADMIN_CHART_COLORS.success,
        data: points.map((point) => point.masked_count),
      },
    ],
  };
}

export function buildAiSecurityDetectionDetectorChart(
  monitoring: AiSecurityMonitoring,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const counts = new Map<string, number>();
  for (const item of [
    ...monitoring.detected_value_groups,
    ...monitoring.privacy_filter_groups,
  ]) {
    counts.set(
      item.detector,
      (counts.get(item.detector) ?? 0) + item.occurrence_count,
    );
  }
  const items = Array.from(counts.entries()).sort(
    (left, right) => right[1] - left[1],
  );
  return {
    categories: items.map(([key]) => aiSecurityMonitoringDetectorLabel(t, key)),
    series: [
      {
        key: 'detections',
        label: t('admin.console.aiSecurity.monitoring.charts.detections'),
        color: ADMIN_CHART_COLORS.primary,
        data: items.map(([, count]) => count),
      },
    ],
  };
}

export function buildAiSecurityDetectionEntityChart(
  monitoring: AiSecurityMonitoring,
  t: TFunction,
): { categories: string[]; series: ChartSeries[] } {
  const counts = new Map<string, number>();
  for (const item of [
    ...monitoring.detected_value_groups,
    ...monitoring.privacy_filter_groups,
  ]) {
    counts.set(
      item.blocker_type,
      (counts.get(item.blocker_type) ?? 0) + item.occurrence_count,
    );
  }
  const items = Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8);
  return {
    categories: items.map(([key]) => aiSecurityMonitoringEntityLabel(t, key)),
    series: [
      {
        key: 'detections',
        label: t('admin.console.aiSecurity.monitoring.charts.detections'),
        color: ADMIN_CHART_COLORS.success,
        data: items.map(([, count]) => count),
      },
    ],
  };
}

export function AiSecurityMonitoringBreakdownList({
  emptyLabel,
  items,
  labelFor,
  locale,
  title,
}: {
  emptyLabel: string;
  items: AiSecurityMonitoringBreakdownItem[];
  labelFor: (key: string) => string;
  locale: string;
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
                  {labelFor(item.key)}
                </span>
                <span className="app-text-caption shrink-0 text-app-ink/55">
                  {formatUsageNumber(item.count, locale)}
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

export function aiSecurityDetectedGroupKey(
  item: Pick<
    AiSecurityDetectedValueGroup,
    'blocker_type' | 'detector' | 'entity_type'
  >,
): string {
  return `${item.detector}:${item.entity_type}:${item.blocker_type}`;
}

export function AiSecurityDetectedValueGroupTable({
  emptyDescription,
  emptyTitle,
  items,
  locale,
  onSelect,
  privacyFilterOnly = false,
  t,
  timeZone,
}: {
  emptyDescription: string;
  emptyTitle: string;
  items: AiSecurityDetectedValueGroup[];
  locale: string;
  onSelect?: (item: AiSecurityDetectedValueGroup) => void;
  privacyFilterOnly?: boolean;
  t: TFunction;
  timeZone: string;
}) {
  return (
    <div className="overflow-auto rounded-md border border-app-border">
      <table className="app-text-body-sm w-full min-w-[840px] table-fixed border-collapse">
        <thead>
          <tr className="bg-app-surface-sidebar">
            <HeadCell className="w-[180px]" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.entity')}
            </HeadCell>
            <HeadCell className="w-[170px]" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.blocker')}
            </HeadCell>
            <HeadCell className="w-[150px]" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.detector')}
            </HeadCell>
            <HeadCell className="w-[120px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.count')}
            </HeadCell>
            <HeadCell className="w-[120px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.events')}
            </HeadCell>
            <HeadCell className="w-[140px] text-right" dense>
              {t(
                'admin.console.aiSecurity.monitoring.detectedValues.distinctValues',
              )}
            </HeadCell>
            <HeadCell className="w-[170px]" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.latest')}
            </HeadCell>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border bg-app-bg">
          {items.length === 0 ? (
            <EmptyRow
              colSpan={7}
              description={emptyDescription}
              title={emptyTitle}
            />
          ) : (
            items.map((item) => (
              <tr
                className={`transition-colors ${
                  item.detail_available && onSelect
                    ? 'cursor-pointer hover:bg-app-surface-hover/40'
                    : ''
                }`}
                key={aiSecurityDetectedGroupKey(item)}
                onClick={() => {
                  if (item.detail_available && onSelect) {
                    onSelect(item);
                  }
                }}
              >
                <BodyCell dense>
                  {aiSecurityMonitoringEntityLabel(t, item.entity_type)}
                </BodyCell>
                <BodyCell dense>
                  {aiSecurityMonitoringEntityLabel(t, item.blocker_type)}
                </BodyCell>
                <BodyCell dense>
                  {aiSecurityMonitoringDetectorLabel(t, item.detector)}
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.occurrence_count, locale)}
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.event_count, locale)}
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {privacyFilterOnly
                    ? t(
                        'admin.console.aiSecurity.monitoring.detectedValues.noStoredValues',
                      )
                    : formatUsageNumber(item.distinct_value_count, locale)}
                </BodyCell>
                <BodyCell dense>
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-app-ink/55">
                      {item.latest_at
                        ? formatDateTime(item.latest_at, {
                            dateStyle: 'medium',
                            locale,
                            timeStyle: 'short',
                            timeZone,
                          })
                        : t('common:empty.none')}
                    </span>
                    {item.detail_available && onSelect ? (
                      <Button
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelect(item);
                        }}
                        size="dense"
                        type="button"
                        variant="ghost"
                      >
                        {t(
                          'admin.console.aiSecurity.monitoring.detectedValues.detail',
                        )}
                      </Button>
                    ) : null}
                  </div>
                </BodyCell>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function AiSecurityDetectedValueDetailTable({
  emptyDescription,
  emptyTitle,
  items,
  locale,
  t,
}: {
  emptyDescription: string;
  emptyTitle: string;
  items: AiSecurityDetectedValueStat[];
  locale: string;
  t: TFunction;
}) {
  return (
    <div className="overflow-auto rounded-md border border-app-border">
      <table className="app-text-body-sm w-full min-w-[680px] table-fixed border-collapse">
        <thead>
          <tr className="bg-app-surface-sidebar">
            <HeadCell className="w-[300px]" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.value')}
            </HeadCell>
            <HeadCell className="w-[180px]" dense>
              {t(
                'admin.console.aiSecurity.monitoring.detectedValues.hashLabel',
              )}
            </HeadCell>
            <HeadCell className="w-[120px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.count')}
            </HeadCell>
            <HeadCell className="w-[120px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.detectedValues.events')}
            </HeadCell>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border bg-app-bg">
          {items.length === 0 ? (
            <EmptyRow
              colSpan={4}
              description={emptyDescription}
              title={emptyTitle}
            />
          ) : (
            items.map((item) => (
              <tr
                className="transition-colors hover:bg-app-surface-hover/40"
                key={`${item.detector}:${item.entity_type}:${item.value_hash ?? item.detected_value ?? 'count'}`}
              >
                <BodyCell dense>
                  <div className="truncate font-medium text-app-ink">
                    {item.detected_value ?? t('common:empty.none')}
                  </div>
                </BodyCell>
                <BodyCell dense>
                  <span className="truncate text-app-ink/55">
                    {item.value_hash
                      ? t(
                          'admin.console.aiSecurity.monitoring.detectedValues.hash',
                          { hash: item.value_hash.slice(0, 12) },
                        )
                      : t('common:empty.none')}
                  </span>
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.occurrence_count, locale)}
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.event_count, locale)}
                </BodyCell>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function AiSecurityDetectedValueSearchForm({
  disabled,
  onQueryChange,
  onSubmit,
  placeholder,
  query,
  t,
}: {
  disabled: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  placeholder: string;
  query: string;
  t: TFunction;
}) {
  return (
    <form
      className="flex flex-col gap-2 sm:flex-row sm:items-center"
      onSubmit={onSubmit}
    >
      <label className="flex min-h-10 flex-1 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 text-app-ink focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
        <Search className="shrink-0 text-app-ink/40" size={16} />
        <input
          className="app-text-body-sm min-w-0 flex-1 bg-transparent py-2 text-app-ink outline-none placeholder:text-app-ink/40"
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={placeholder}
          value={query}
        />
      </label>
      <Button disabled={disabled} type="submit" variant="secondary">
        <Search size={16} />
        {t('common:actions.search')}
      </Button>
    </form>
  );
}

export function AiSecurityDetectedValueGroupsDialog({
  dateRangeLabel,
  error,
  items,
  loading,
  mode,
  offset,
  onApplyQuery,
  onNext,
  onOpenChange,
  onPrevious,
  onQueryChange,
  onSelect,
  open,
  query,
  total,
  locale,
  t,
  timeZone,
}: {
  dateRangeLabel: string;
  error: string | null;
  items: AiSecurityDetectedValueGroup[];
  loading: boolean;
  mode: 'stored' | 'privacy';
  offset: number;
  onApplyQuery: (event: React.FormEvent<HTMLFormElement>) => void;
  onNext: () => void;
  onOpenChange: (open: boolean) => void;
  onPrevious: () => void;
  onQueryChange: (value: string) => void;
  onSelect?: (item: AiSecurityDetectedValueGroup) => void;
  open: boolean;
  query: string;
  total: number;
  locale: string;
  t: TFunction;
  timeZone: string;
}) {
  const privacyFilterOnly = mode === 'privacy';
  return (
    <Dialog
      actions={
        <Button onClick={() => onOpenChange(false)} variant="secondary">
          {t('common:actions.close')}
        </Button>
      }
      closeLabel={t('common:actions.close')}
      description={t(
        privacyFilterOnly
          ? 'admin.console.aiSecurity.monitoring.privacyFilter.dialogDescription'
          : 'admin.console.aiSecurity.monitoring.detectedValues.dialogDescription',
        { range: dateRangeLabel },
      )}
      maxWidth="max-w-[1080px] h-[min(760px,calc(100vh-2rem))]"
      onOpenChange={onOpenChange}
      open={open}
      title={t(
        privacyFilterOnly
          ? 'admin.console.aiSecurity.monitoring.privacyFilter.dialogTitle'
          : 'admin.console.aiSecurity.monitoring.detectedValues.dialogTitle',
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <AiSecurityDetectedValueSearchForm
          disabled={loading}
          onQueryChange={onQueryChange}
          onSubmit={onApplyQuery}
          placeholder={t(
            privacyFilterOnly
              ? 'admin.console.aiSecurity.monitoring.privacyFilter.searchPlaceholder'
              : 'admin.console.aiSecurity.monitoring.detectedValues.searchPlaceholder',
          )}
          query={query}
          t={t}
        />
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="min-h-0 flex-1 overflow-auto">
          <AiSecurityDetectedValueGroupTable
            emptyDescription={t(
              privacyFilterOnly
                ? 'admin.console.aiSecurity.monitoring.privacyFilter.emptyDescription'
                : 'admin.console.aiSecurity.monitoring.detectedValues.emptyDescription',
            )}
            emptyTitle={t(
              privacyFilterOnly
                ? 'admin.console.aiSecurity.monitoring.privacyFilter.emptyTitle'
                : 'admin.console.aiSecurity.monitoring.detectedValues.emptyTitle',
            )}
            items={items}
            locale={locale}
            onSelect={privacyFilterOnly ? undefined : onSelect}
            privacyFilterOnly={privacyFilterOnly}
            t={t}
            timeZone={timeZone}
          />
        </div>
        <AuditLogPager
          limit={AI_SECURITY_DETECTED_VALUE_PAGE_SIZE}
          loading={loading}
          locale={locale}
          offset={offset}
          onNext={onNext}
          onPrevious={onPrevious}
          total={total}
        />
      </div>
    </Dialog>
  );
}

export function AiSecurityDetectedValueDetailsDialog({
  dateRangeLabel,
  error,
  group,
  items,
  loading,
  offset,
  onApplyQuery,
  onNext,
  onOpenChange,
  onPrevious,
  onQueryChange,
  open,
  query,
  total,
  locale,
  t,
}: {
  dateRangeLabel: string;
  error: string | null;
  group: AiSecurityDetectedValueGroup | null;
  items: AiSecurityDetectedValueStat[];
  loading: boolean;
  offset: number;
  onApplyQuery: (event: React.FormEvent<HTMLFormElement>) => void;
  onNext: () => void;
  onOpenChange: (open: boolean) => void;
  onPrevious: () => void;
  onQueryChange: (value: string) => void;
  open: boolean;
  query: string;
  total: number;
  locale: string;
  t: TFunction;
}) {
  const entityLabel = group
    ? aiSecurityMonitoringEntityLabel(t, group.entity_type)
    : t('common:empty.none');
  return (
    <Dialog
      actions={
        <Button onClick={() => onOpenChange(false)} variant="secondary">
          {t('common:actions.close')}
        </Button>
      }
      closeLabel={t('common:actions.close')}
      description={t(
        'admin.console.aiSecurity.monitoring.detectedValues.detailDialogDescription',
        { range: dateRangeLabel },
      )}
      maxWidth="max-w-[920px] h-[min(720px,calc(100vh-2rem))]"
      onOpenChange={onOpenChange}
      open={open}
      title={t(
        'admin.console.aiSecurity.monitoring.detectedValues.detailTitle',
        {
          entity: entityLabel,
        },
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        {group ? (
          <div className="grid gap-2 sm:grid-cols-3">
            <AiSecurityMetric
              label={t(
                'admin.console.aiSecurity.monitoring.detectedValues.entity',
              )}
              value={entityLabel}
            />
            <AiSecurityMetric
              label={t(
                'admin.console.aiSecurity.monitoring.detectedValues.detector',
              )}
              value={aiSecurityMonitoringDetectorLabel(t, group.detector)}
            />
            <AiSecurityMetric
              label={t(
                'admin.console.aiSecurity.monitoring.detectedValues.count',
              )}
              value={formatUsageNumber(group.occurrence_count, locale)}
            />
          </div>
        ) : null}
        <AiSecurityDetectedValueSearchForm
          disabled={loading}
          onQueryChange={onQueryChange}
          onSubmit={onApplyQuery}
          placeholder={t(
            'admin.console.aiSecurity.monitoring.detectedValues.detailSearchPlaceholder',
          )}
          query={query}
          t={t}
        />
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="min-h-0 flex-1 overflow-auto">
          <AiSecurityDetectedValueDetailTable
            emptyDescription={t(
              'admin.console.aiSecurity.monitoring.detectedValues.detailEmptyDescription',
            )}
            emptyTitle={t(
              'admin.console.aiSecurity.monitoring.detectedValues.detailEmptyTitle',
            )}
            items={items}
            locale={locale}
            t={t}
          />
        </div>
        <AuditLogPager
          limit={AI_SECURITY_DETECTED_VALUE_PAGE_SIZE}
          loading={loading}
          locale={locale}
          offset={offset}
          onNext={onNext}
          onPrevious={onPrevious}
          total={total}
        />
      </div>
    </Dialog>
  );
}

export function AiSecurityMonitoringUserTable({
  items,
  loading,
  locale,
  t,
  timeZone,
}: {
  items: AiSecurityMonitoring['blocked_by_user'];
  loading: boolean;
  locale: string;
  t: TFunction;
  timeZone: string;
}) {
  return (
    <div className="overflow-auto rounded-md border border-app-border">
      <table className="app-text-body-sm w-full min-w-[700px] table-fixed border-collapse">
        <thead>
          <tr className="bg-app-surface-sidebar">
            <HeadCell className="w-[300px]" dense>
              {t('admin.console.aiSecurity.monitoring.userTable.user')}
            </HeadCell>
            <HeadCell className="w-[110px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.userTable.blocked')}
            </HeadCell>
            <HeadCell className="w-[120px] text-right" dense>
              {t('admin.console.aiSecurity.monitoring.userTable.masked')}
            </HeadCell>
            <HeadCell className="w-[170px]" dense>
              {t('admin.console.aiSecurity.monitoring.userTable.lastBlocked')}
            </HeadCell>
          </tr>
        </thead>
        <tbody className="divide-y divide-app-border bg-app-bg">
          {loading && items.length === 0 ? (
            <EmptyRow
              colSpan={4}
              description={t('admin.console.aiSecurity.monitoring.loading')}
              title={t('admin.console.aiSecurity.monitoring.loadingTitle')}
            />
          ) : items.length === 0 ? (
            <EmptyRow
              colSpan={4}
              description={t(
                'admin.console.aiSecurity.monitoring.userTable.emptyDescription',
              )}
              title={t(
                'admin.console.aiSecurity.monitoring.userTable.emptyTitle',
              )}
            />
          ) : (
            items.map((item) => (
              <tr
                className="transition-colors hover:bg-app-surface-hover/40"
                key={item.user_id}
              >
                <BodyCell dense>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-app-ink">
                      {item.full_name}
                    </div>
                    <div className="truncate text-app-ink/55">{item.email}</div>
                    <div className="truncate text-app-ink/55">
                      {item.org_unit_name ?? t('admin.console.usage.noOrg')}
                    </div>
                  </div>
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.blocked_count, locale)}
                </BodyCell>
                <BodyCell className="text-right" dense>
                  {formatUsageNumber(item.masked_count, locale)}
                </BodyCell>
                <BodyCell dense>
                  {item.last_blocked_at
                    ? formatDateTime(item.last_blocked_at, {
                        dateStyle: 'medium',
                        locale,
                        timeStyle: 'short',
                        timeZone,
                      })
                    : t('common:empty.none')}
                </BodyCell>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
