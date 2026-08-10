import { useCallback, useEffect, useState } from 'react';
import { FileSearch, Play, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button, Dialog, InlineNotice, Tooltip } from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';

import {
  listAdminBatches,
  runAdminBatch,
  type AdminBatchItem,
} from './admin-api';
import {
  batchFreshnessText,
  batchHealthStatus,
  batchHealthTone,
  batchMetrics,
  batchPrimaryMetric,
  batchScheduleText,
  batchStatusLabel,
  type BatchHealthStatus,
} from './admin-batches-model';
import {
  Badge,
  BodyCell,
  EmptyRow,
  HeadCell,
  SurfaceCard,
  getErrorMessage,
} from './admin-shared';

function BatchSummaryPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex min-w-[7rem] items-center justify-between gap-3 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2">
      <span className="app-text-caption text-app-ink/55">{label}</span>
      <span className="app-text-title-md text-app-ink">{value}</span>
    </div>
  );
}

function BatchDetailDialog({
  batch,
  locale,
  onOpenChange,
  onRun,
  open,
  running,
  timeZone,
}: {
  batch: AdminBatchItem | null;
  locale: string;
  onOpenChange: (open: boolean) => void;
  onRun: (batchId: AdminBatchItem['id']) => void;
  open: boolean;
  running: boolean;
  timeZone: string;
}) {
  const { t } = useTranslation('apps');
  const nowMs = Date.now();
  const status = batch ? batchHealthStatus(batch, nowMs) : 'empty';
  const metrics = batch ? batchMetrics(batch, t) : [];
  const title = batch
    ? t('admin.console.batches.detailTitle', {
        name: t(`admin.console.batches.items.${batch.id}.title`),
      })
    : t('admin.console.batches.title');

  return (
    <Dialog
      actions={
        <>
          {batch ? (
            <Button
              disabled={running}
              onClick={() => onRun(batch.id)}
              variant="primary"
            >
              {running ? (
                <RefreshCw size={16} className="animate-spin" />
              ) : (
                <Play size={16} />
              )}
              {running
                ? t('admin.console.batches.running')
                : t('admin.console.batches.runNow')}
            </Button>
          ) : null}
          <Button onClick={() => onOpenChange(false)} variant="secondary">
            {t('common:actions.close')}
          </Button>
        </>
      }
      closeLabel={t('common:actions.close')}
      description={
        batch
          ? t(`admin.console.batches.items.${batch.id}.description`)
          : undefined
      }
      maxWidth="max-w-[760px]"
      onOpenChange={onOpenChange}
      open={open}
      title={title}
    >
      {batch ? (
        <div className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-md border border-app-border px-3 py-2">
              <div className="app-text-overline text-app-ink/55">
                {t('admin.console.batches.columns.status')}
              </div>
              <div className="mt-1">
                <Badge tone={batchHealthTone(status)}>
                  {batchStatusLabel(status, t)}
                </Badge>
              </div>
            </div>
            <div className="rounded-md border border-app-border px-3 py-2">
              <div className="app-text-overline text-app-ink/55">
                {t('admin.console.batches.columns.schedule')}
              </div>
              <div className="app-text-body-sm mt-1 text-app-ink">
                {batchScheduleText(batch, t)}
              </div>
            </div>
            <div className="rounded-md border border-app-border px-3 py-2">
              <div className="app-text-overline text-app-ink/55">
                {t('admin.console.batches.lastRun')}
              </div>
              <div className="app-text-body-sm mt-1 text-app-ink">
                {batch.last_run
                  ? formatDateTime(batch.last_run.completed_at, {
                      dateStyle: 'medium',
                      locale,
                      timeStyle: 'short',
                      timeZone,
                    })
                  : t('admin.console.batches.neverRun')}
              </div>
            </div>
            <div className="rounded-md border border-app-border px-3 py-2">
              <div className="app-text-overline text-app-ink/55">
                {t('admin.console.batches.columns.freshness')}
              </div>
              <div className="app-text-body-sm mt-1 text-app-ink">
                {batchFreshnessText(batch, status, t)}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-md border border-app-border">
            <table className="w-full table-fixed border-collapse">
              <tbody>
                <tr>
                  <BodyCell
                    className="w-32 bg-app-surface-sidebar text-app-ink/55"
                    dense
                  >
                    {t('admin.console.batches.columns.queue')}
                  </BodyCell>
                  <BodyCell dense>{batch.queue}</BodyCell>
                </tr>
                <tr>
                  <BodyCell
                    className="w-32 bg-app-surface-sidebar text-app-ink/55"
                    dense
                  >
                    {t('admin.console.batches.taskName')}
                  </BodyCell>
                  <BodyCell dense>{batch.task_name}</BodyCell>
                </tr>
                <tr>
                  <BodyCell
                    className="w-32 bg-app-surface-sidebar text-app-ink/55"
                    dense
                  >
                    {t('admin.console.batches.summary')}
                  </BodyCell>
                  <BodyCell dense>
                    {batch.last_run?.summary ??
                      t('admin.console.batches.noSummary')}
                  </BodyCell>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map((metric) => (
              <div
                className="rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
                key={metric.label}
              >
                <div className="app-text-overline text-app-ink/55">
                  {metric.label}
                </div>
                <div className="app-text-title-md mt-1 text-app-ink">
                  {metric.value}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}

export function BatchesSection({ token }: { token: string }) {
  const { t, i18n } = useTranslation('apps');
  const { user } = useAuth();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<AdminBatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailBatchId, setDetailBatchId] = useState<
    AdminBatchItem['id'] | null
  >(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listAdminBatches(token);
      setItems(response.items);
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.batches.loadFailed')),
      );
    } finally {
      setLoading(false);
    }
  }, [token, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRun(batchId: AdminBatchItem['id']) {
    setRunningId(batchId);
    setNotice(null);
    setError(null);
    try {
      const response = await runAdminBatch(token, batchId);
      setNotice(
        t('admin.console.batches.runQueued', {
          taskId: response.task_id ?? t('common:empty.none'),
        }),
      );
      setItems((current) =>
        current.map((item) =>
          item.id === response.batch.id ? response.batch : item,
        ),
      );
    } catch (caughtError) {
      setError(
        getErrorMessage(caughtError, t('admin.console.batches.runFailed')),
      );
    } finally {
      setRunningId(null);
    }
  }

  const nowMs = Date.now();
  const summary = items.reduce(
    (accumulator, item) => {
      const status = batchHealthStatus(item, nowMs);
      accumulator[status] += 1;
      return accumulator;
    },
    {
      building: 0,
      disabled: 0,
      empty: 0,
      failed: 0,
      ok: 0,
      stale: 0,
    } satisfies Record<BatchHealthStatus, number>,
  );
  const detailBatch = items.find((item) => item.id === detailBatchId) ?? null;

  return (
    <div className="space-y-6">
      {notice ? <InlineNotice tone="success">{notice}</InlineNotice> : null}
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

      <SurfaceCard
        description={t('admin.console.batches.description')}
        title={t('admin.console.batches.title')}
      >
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            <BatchSummaryPill
              label={t('admin.console.batches.summaryAll')}
              value={items.length}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.ok')}
              value={summary.ok}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.stale')}
              value={summary.stale}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.building')}
              value={summary.building}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.failed')}
              value={summary.failed}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.empty')}
              value={summary.empty}
            />
            <BatchSummaryPill
              label={t('admin.console.batches.status.disabled')}
              value={summary.disabled}
            />
          </div>
          <Button
            disabled={loading}
            onClick={() => void load()}
            variant="secondary"
          >
            <RefreshCw size={16} />
            {t('admin.console.batches.refresh')}
          </Button>
        </div>

        {loading ? (
          <div className="app-text-body rounded-xl border border-dashed border-app-border bg-app-surface-sidebar px-4 py-8 text-center text-app-ink/55">
            {t('admin.console.batches.loading')}
          </div>
        ) : (
          <div className="overflow-x-auto border border-app-border">
            <table className="w-full min-w-[960px] table-fixed border-collapse">
              <thead>
                <tr className="bg-app-surface-sidebar">
                  <HeadCell className="w-[9%]" dense>
                    {t('admin.console.batches.columns.status')}
                  </HeadCell>
                  <HeadCell className="w-[20%]" dense>
                    {t('admin.console.batches.columns.name')}
                  </HeadCell>
                  <HeadCell className="w-[17%]" dense>
                    {t('admin.console.batches.columns.schedule')}
                  </HeadCell>
                  <HeadCell className="w-[17%]" dense>
                    {t('admin.console.batches.columns.lastRun')}
                  </HeadCell>
                  <HeadCell className="w-[12%]" dense>
                    {t('admin.console.batches.columns.freshness')}
                  </HeadCell>
                  <HeadCell className="w-[10%]" dense>
                    {t('admin.console.batches.columns.primaryMetric')}
                  </HeadCell>
                  <HeadCell className="w-[7%]" dense>
                    {t('admin.console.batches.columns.queue')}
                  </HeadCell>
                  <HeadCell className="w-[8%] text-right" dense>
                    {t('admin.console.batches.columns.actions')}
                  </HeadCell>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 ? (
                  <EmptyRow
                    colSpan={8}
                    description={t('admin.console.batches.emptyDescription')}
                    title={t('admin.console.batches.emptyTitle')}
                  />
                ) : (
                  items.map((batch) => {
                    const status = batchHealthStatus(batch, nowMs);
                    const primaryMetric = batchPrimaryMetric(batch, t);
                    return (
                      <tr
                        className="transition-colors hover:bg-app-surface-hover/40"
                        key={batch.id}
                      >
                        <BodyCell dense>
                          <Badge tone={batchHealthTone(status)}>
                            {batchStatusLabel(status, t)}
                          </Badge>
                        </BodyCell>
                        <BodyCell dense>
                          <div className="min-w-0">
                            <div className="truncate font-medium">
                              {t(
                                `admin.console.batches.items.${batch.id}.title`,
                              )}
                            </div>
                            <div className="truncate app-text-caption text-app-ink/55">
                              {batch.task_name}
                            </div>
                          </div>
                        </BodyCell>
                        <BodyCell dense>
                          <span className="block truncate">
                            {batchScheduleText(batch, t)}
                          </span>
                        </BodyCell>
                        <BodyCell dense>
                          <span className="block truncate">
                            {batch.last_run
                              ? formatDateTime(batch.last_run.completed_at, {
                                  dateStyle: 'medium',
                                  locale,
                                  timeStyle: 'short',
                                  timeZone,
                                })
                              : t('admin.console.batches.neverRun')}
                          </span>
                        </BodyCell>
                        <BodyCell dense>
                          <span className="block truncate">
                            {batchFreshnessText(batch, status, t)}
                          </span>
                        </BodyCell>
                        <BodyCell dense>
                          <span className="block truncate">
                            {primaryMetric.label}: {primaryMetric.value}
                          </span>
                        </BodyCell>
                        <BodyCell dense>
                          <span className="block truncate">{batch.queue}</span>
                        </BodyCell>
                        <BodyCell className="text-right" dense>
                          <div className="flex justify-end gap-1">
                            <Tooltip
                              content={
                                runningId === batch.id
                                  ? t('admin.console.batches.running')
                                  : t('admin.console.batches.runNow')
                              }
                            >
                              <Button
                                aria-label={
                                  runningId === batch.id
                                    ? t('admin.console.batches.running')
                                    : t('admin.console.batches.runNow')
                                }
                                disabled={runningId === batch.id}
                                onClick={() => void handleRun(batch.id)}
                                size="icon"
                                variant="secondary"
                              >
                                {runningId === batch.id ? (
                                  <RefreshCw
                                    size={14}
                                    className="animate-spin"
                                  />
                                ) : (
                                  <Play size={14} />
                                )}
                              </Button>
                            </Tooltip>
                            <Tooltip
                              content={t('admin.console.batches.detail')}
                            >
                              <Button
                                aria-label={t('admin.console.batches.detail')}
                                onClick={() => setDetailBatchId(batch.id)}
                                size="icon"
                                variant="secondary"
                              >
                                <FileSearch size={14} />
                              </Button>
                            </Tooltip>
                          </div>
                        </BodyCell>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </SurfaceCard>
      <BatchDetailDialog
        batch={detailBatch}
        locale={locale}
        onOpenChange={(open) => {
          if (!open) setDetailBatchId(null);
        }}
        onRun={(batchId) => void handleRun(batchId)}
        open={detailBatch !== null}
        running={detailBatch ? runningId === detailBatch.id : false}
        timeZone={timeZone}
      />
    </div>
  );
}
