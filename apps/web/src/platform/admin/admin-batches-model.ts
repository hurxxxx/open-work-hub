import type { AdminBatchItem } from './admin-api';
import { parseApiDateTime } from '@/src/platform/time/time-utils';

export type AdminBatchTranslate = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export type BatchHealthStatus =
  | 'ok'
  | 'stale'
  | 'empty'
  | 'disabled'
  | 'building'
  | 'failed';

function batchPayloadNumber(batch: AdminBatchItem, key: string): number | null {
  const payload = batch.last_run?.payload as
    | Record<string, unknown>
    | undefined;
  const value = payload?.[key];
  return typeof value === 'number' ? value : null;
}

function batchPayloadString(batch: AdminBatchItem, key: string): string | null {
  const payload = batch.last_run?.payload as
    | Record<string, unknown>
    | undefined;
  const value = payload?.[key];
  return typeof value === 'string' ? value : null;
}

export function batchScheduleText(
  batch: AdminBatchItem,
  t: AdminBatchTranslate,
): string {
  if (batch.schedule.kind === 'interval') {
    return t('admin.console.batches.scheduleInterval', {
      everyHours: batch.schedule.every_hours ?? '-',
      minute: String(batch.schedule.minute).padStart(2, '0'),
      timeZone: batch.schedule.time_zone,
    });
  }
  return t('admin.console.batches.scheduleDaily', {
    hour: String(batch.schedule.hour ?? 0).padStart(2, '0'),
    minute: String(batch.schedule.minute).padStart(2, '0'),
    timeZone: batch.schedule.time_zone,
  });
}

export function batchAllowedDelayMs(batch: AdminBatchItem): number | null {
  if (!batch.schedule.enabled) return null;
  if (batch.schedule.kind === 'interval') {
    const hours = batch.schedule.every_hours ?? 1;
    return hours * 60 * 60 * 1000 + 30 * 60 * 1000;
  }
  return 26 * 60 * 60 * 1000;
}

export function batchHealthStatus(
  batch: AdminBatchItem,
  nowMs: number,
): BatchHealthStatus {
  if (!batch.last_run) return batch.schedule.enabled ? 'empty' : 'disabled';
  if (batch.id === 'integrated-hr') {
    const runStatus = batchPayloadString(batch, 'status');
    if (runStatus === 'building' || runStatus === 'failed') return runStatus;
    if (!batch.schedule.enabled) return 'disabled';
    if (runStatus !== 'succeeded') return 'empty';
  }
  if (!batch.schedule.enabled) return 'disabled';
  const completedAt = parseApiDateTime(batch.last_run.completed_at)?.getTime();
  const allowedDelayMs = batchAllowedDelayMs(batch);
  if (completedAt === undefined || allowedDelayMs === null) return 'empty';
  return nowMs - completedAt > allowedDelayMs ? 'stale' : 'ok';
}

export function batchHealthTone(
  status: BatchHealthStatus,
): 'default' | 'purple' | 'green' | 'amber' {
  if (status === 'ok') return 'green';
  if (status === 'stale' || status === 'failed') return 'amber';
  if (status === 'building') return 'purple';
  return 'default';
}

export function batchStatusLabel(
  status: BatchHealthStatus,
  t: AdminBatchTranslate,
): string {
  return t(`admin.console.batches.status.${status}`);
}

export function batchFreshnessText(
  batch: AdminBatchItem,
  status: BatchHealthStatus,
  t: AdminBatchTranslate,
): string {
  if (status === 'disabled')
    return t('admin.console.batches.freshness.disabled');
  if (status === 'empty') return t('admin.console.batches.freshness.empty');
  if (status === 'building')
    return t('admin.console.batches.freshness.building');
  if (status === 'failed') return t('admin.console.batches.freshness.failed');
  if (status === 'stale') return t('admin.console.batches.freshness.stale');
  if (batch.schedule.kind === 'interval') {
    return t('admin.console.batches.freshness.intervalOk', {
      everyHours: batch.schedule.every_hours ?? '-',
    });
  }
  return t('admin.console.batches.freshness.dailyOk');
}

export function batchMetrics(
  batch: AdminBatchItem,
  t: AdminBatchTranslate,
): Array<{ label: string; value: number | string }> {
  if (batch.id === 'erp-hr') {
    return [
      {
        label: t('admin.console.batches.rowsSeen'),
        value: batchPayloadNumber(batch, 'rows_seen') ?? '-',
      },
    ];
  }
  if (batch.id === 'integrated-hr') {
    return [
      {
        label: t('admin.console.batches.metrics.people'),
        value: batchPayloadNumber(batch, 'person_row_count') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.groups'),
        value: batchPayloadNumber(batch, 'group_row_count') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.conflicts'),
        value: batchPayloadNumber(batch, 'conflict_row_count') ?? '-',
      },
    ];
  }
  if (batch.id === 'qna-board') {
    return [
      {
        label: t('admin.console.batches.metrics.notices'),
        value: batchPayloadNumber(batch, 'notices') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.workspace'),
        value: batchPayloadString(batch, 'workspace') ?? '-',
      },
    ];
  }
  if (batch.id === 'news') {
    return [
      {
        label: t('admin.console.batches.metrics.total'),
        value: batchPayloadNumber(batch, 'total') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.keyword'),
        value: batchPayloadNumber(batch, 'keyword') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.car'),
        value: batchPayloadNumber(batch, 'car') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.front'),
        value: batchPayloadNumber(batch, 'front') ?? '-',
      },
    ];
  }
  if (batch.id === 'industry-report') {
    const kdiTotal =
      (batchPayloadNumber(batch, 'kdi_nara') ?? 0) +
      (batchPayloadNumber(batch, 'kdi_material') ?? 0) +
      (batchPayloadNumber(batch, 'kdi_domestic') ?? 0);
    return [
      {
        label: t('admin.console.batches.metrics.total'),
        value: batchPayloadNumber(batch, 'total') ?? '-',
      },
      {
        label: t('admin.console.batches.metrics.katech'),
        value: batchPayloadNumber(batch, 'katech') ?? '-',
      },
      { label: t('admin.console.batches.metrics.kdi'), value: kdiTotal || '-' },
      {
        label: t('admin.console.batches.metrics.autojournal'),
        value: batchPayloadNumber(batch, 'autojournal') ?? '-',
      },
    ];
  }
  return [
    {
      label: t('admin.console.batches.usersSeen'),
      value: batchPayloadNumber(batch, 'users_seen') ?? '-',
    },
    {
      label: t('admin.console.batches.usersCreated'),
      value: batchPayloadNumber(batch, 'users_created') ?? '-',
    },
    {
      label: t('admin.console.batches.usersUpdated'),
      value: batchPayloadNumber(batch, 'users_updated') ?? '-',
    },
  ];
}

export function batchPrimaryMetric(
  batch: AdminBatchItem,
  t: AdminBatchTranslate,
): { label: string; value: number | string } {
  if (batch.id === 'erp-hr') {
    return {
      label: t('admin.console.batches.rowsSeen'),
      value: batchPayloadNumber(batch, 'rows_seen') ?? '-',
    };
  }
  if (batch.id === 'groupware-hr') {
    return {
      label: t('admin.console.batches.usersSeen'),
      value: batchPayloadNumber(batch, 'users_seen') ?? '-',
    };
  }
  if (batch.id === 'integrated-hr') {
    return {
      label: t('admin.console.batches.metrics.people'),
      value: batchPayloadNumber(batch, 'person_row_count') ?? '-',
    };
  }
  return {
    label: t('admin.console.batches.metrics.total'),
    value: batchPayloadNumber(batch, 'total') ?? '-',
  };
}
