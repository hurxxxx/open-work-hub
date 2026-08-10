import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button, InlineNotice, Panel } from '@ai-do/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import type { HealthCheckupSourceStatus } from '../api/health-checkup-api';

export interface HealthCheckupSourceStatusPanelProps {
  loading: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  status: HealthCheckupSourceStatus | null;
}

export function HealthCheckupSourceStatusPanel({
  loading,
  onRefresh,
  refreshing,
  status,
}: HealthCheckupSourceStatusPanelProps) {
  const { t } = useTranslation(['apps', 'common']);
  const unavailableReason = status?.reason
    ? t(`apps:healthCheckup.source.reasons.${status.reason}`, {
        defaultValue: t('apps:healthCheckup.source.unavailable'),
      })
    : t('apps:healthCheckup.source.unavailable');

  return (
    <Panel>
      <div className="grid gap-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="grid gap-1">
            <h2 className="m-0 text-app-text text-[length:var(--ui-text-h3)] font-semibold">
              {t('apps:healthCheckup.source.title')}
            </h2>
            <p className="m-0 text-app-text-muted text-[length:var(--ui-text-body-sm)]">
              {t('apps:healthCheckup.source.description')}
            </p>
          </div>
          <Button disabled={refreshing} onClick={onRefresh} variant="secondary">
            <RefreshCw
              aria-hidden="true"
              className={refreshing ? 'animate-spin' : ''}
              size={16}
            />
            {refreshing
              ? t('apps:healthCheckup.source.refreshing')
              : t('apps:healthCheckup.source.refresh')}
          </Button>
        </div>

        {loading && !status ? (
          <InlineNotice tone="info">
            {t('apps:healthCheckup.source.loading')}
          </InlineNotice>
        ) : status?.available ? (
          <InlineNotice tone="success">
            {t('apps:healthCheckup.source.accepted', {
              count: status.employee_count,
            })}
          </InlineNotice>
        ) : (
          <InlineNotice tone="warning">{unavailableReason}</InlineNotice>
        )}

        {status ? (
          <dl className="grid gap-2 text-[length:var(--ui-text-body-sm)] sm:grid-cols-2 lg:grid-cols-4">
            <div className="grid gap-0.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <dt className="text-app-text-muted">
                {t('apps:healthCheckup.source.capturedAt')}
              </dt>
              <dd className="m-0 text-app-text">
                {status.captured_at ? (
                  <UserDateTime value={status.captured_at} />
                ) : (
                  t('common:empty.none')
                )}
              </dd>
            </div>
            <div className="grid gap-0.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <dt className="text-app-text-muted">
                {t('apps:healthCheckup.source.employeeCount')}
              </dt>
              <dd className="m-0 text-app-text tabular-nums">
                {status.employee_count}
              </dd>
            </div>
            <div className="grid gap-0.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <dt className="text-app-text-muted">
                {t('apps:healthCheckup.source.schemaVersion')}
              </dt>
              <dd className="m-0 truncate text-app-text">
                {status.schema_version ?? t('common:empty.none')}
              </dd>
            </div>
            <div className="grid gap-0.5 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
              <dt className="text-app-text-muted">
                {t('apps:healthCheckup.source.runId')}
              </dt>
              <dd className="m-0 truncate font-mono text-app-text">
                {status.run_id ?? t('common:empty.none')}
              </dd>
            </div>
          </dl>
        ) : null}
      </div>
    </Panel>
  );
}
