import { describe, expect, it } from 'vitest';

import type { AdminBatchItem } from './admin-api';
import {
  batchFreshnessText,
  batchHealthStatus,
  batchHealthTone,
  batchMetrics,
  batchPrimaryMetric,
  batchScheduleText,
} from './admin-batches-model';

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${JSON.stringify(options)}` : key;

const baseLastRun = {
  completed_at: '2026-07-07T00:00:00Z',
  payload: {
    users_created: 2,
    users_seen: 10,
    users_updated: 3,
  },
  status: 'ok',
  summary: 'Synced users',
};

function batch(overrides: Partial<AdminBatchItem> = {}): AdminBatchItem {
  return {
    id: 'groupware-hr',
    queue: 'default',
    task_name: 'groupware.hr.sync',
    schedule: {
      enabled: true,
      every_hours: 6,
      hour: null,
      kind: 'interval',
      minute: 10,
      time_zone: 'Asia/Seoul',
    },
    last_run: baseLastRun,
    ...overrides,
  } as AdminBatchItem;
}

describe('admin batches model', () => {
  it('classifies disabled, empty, fresh, and stale batches', () => {
    const now = new Date('2026-07-07T06:00:00Z').getTime();

    expect(
      batchHealthStatus(
        batch({ schedule: { ...batch().schedule, enabled: false } }),
        now,
      ),
    ).toBe('disabled');
    expect(batchHealthStatus(batch({ last_run: null }), now)).toBe('empty');
    expect(batchHealthStatus(batch(), now)).toBe('ok');
    expect(
      batchHealthStatus(
        batch({
          last_run: {
            ...baseLastRun,
            completed_at: '2026-07-06T00:00:00Z',
          },
        }),
        now,
      ),
    ).toBe('stale');
  });

  it('prioritizes the unified HR run status over freshness', () => {
    const now = new Date('2026-07-07T06:00:00Z').getTime();
    const integratedBatch = (
      status?: string,
      completedAt = baseLastRun.completed_at,
    ) =>
      batch({
        id: 'integrated-hr',
        last_run: {
          ...baseLastRun,
          completed_at: completedAt,
          payload: status === undefined ? {} : { status },
        },
      });

    expect(
      batchHealthStatus(
        integratedBatch('building', '2026-07-01T00:00:00Z'),
        now,
      ),
    ).toBe('building');
    expect(batchHealthStatus(integratedBatch('failed'), now)).toBe('failed');
    expect(
      batchHealthStatus(
        batch({
          id: 'integrated-hr',
          schedule: { ...batch().schedule, enabled: false },
          last_run: {
            ...baseLastRun,
            payload: { status: 'failed' },
          },
        }),
        now,
      ),
    ).toBe('failed');
    expect(batchHealthStatus(integratedBatch('succeeded'), now)).toBe('ok');
    expect(
      batchHealthStatus(
        integratedBatch('succeeded', '2026-07-05T00:00:00Z'),
        now,
      ),
    ).toBe('stale');
    expect(batchHealthStatus(integratedBatch(), now)).toBe('empty');
  });

  it('keeps freshness behavior for other batch payload status values', () => {
    const now = new Date('2026-07-07T06:00:00Z').getTime();

    expect(
      batchHealthStatus(
        batch({
          last_run: {
            ...baseLastRun,
            payload: { status: 'failed' },
          },
        }),
        now,
      ),
    ).toBe('ok');
  });

  it('maps health statuses to badge tones and freshness labels', () => {
    expect(batchHealthTone('ok')).toBe('green');
    expect(batchHealthTone('stale')).toBe('amber');
    expect(batchHealthTone('empty')).toBe('default');
    expect(batchHealthTone('building')).toBe('purple');
    expect(batchHealthTone('failed')).toBe('amber');
    expect(batchFreshnessText(batch(), 'ok', t)).toBe(
      'admin.console.batches.freshness.intervalOk:{"everyHours":6}',
    );
    expect(batchFreshnessText(batch(), 'stale', t)).toBe(
      'admin.console.batches.freshness.stale',
    );
    expect(batchFreshnessText(batch(), 'building', t)).toBe(
      'admin.console.batches.freshness.building',
    );
    expect(batchFreshnessText(batch(), 'failed', t)).toBe(
      'admin.console.batches.freshness.failed',
    );
  });

  it('formats interval and daily schedules', () => {
    expect(batchScheduleText(batch(), t)).toBe(
      'admin.console.batches.scheduleInterval:{"everyHours":6,"minute":"10","timeZone":"Asia/Seoul"}',
    );
    expect(
      batchScheduleText(
        batch({
          schedule: {
            enabled: true,
            every_hours: null,
            hour: 9,
            kind: 'daily',
            minute: 5,
            time_zone: 'Asia/Seoul',
          },
        }),
        t,
      ),
    ).toBe(
      'admin.console.batches.scheduleDaily:{"hour":"09","minute":"05","timeZone":"Asia/Seoul"}',
    );
  });

  it('builds metrics by batch kind from the last run payload', () => {
    expect(
      batchMetrics(
        batch({
          id: 'erp-hr',
          last_run: { ...baseLastRun, payload: { rows_seen: 698 } },
        }),
        t,
      ),
    ).toEqual([{ label: 'admin.console.batches.rowsSeen', value: 698 }]);
    expect(batchMetrics(batch(), t)).toEqual([
      { label: 'admin.console.batches.usersSeen', value: 10 },
      { label: 'admin.console.batches.usersCreated', value: 2 },
      { label: 'admin.console.batches.usersUpdated', value: 3 },
    ]);
    expect(
      batchMetrics(
        batch({
          id: 'integrated-hr',
          last_run: {
            ...baseLastRun,
            payload: {
              person_row_count: 10,
              group_row_count: 3,
              conflict_row_count: 1,
            },
          },
        }),
        t,
      ),
    ).toEqual([
      { label: 'admin.console.batches.metrics.people', value: 10 },
      { label: 'admin.console.batches.metrics.groups', value: 3 },
      { label: 'admin.console.batches.metrics.conflicts', value: 1 },
    ]);
    expect(
      batchMetrics(
        batch({
          id: 'qna-board',
          last_run: {
            ...baseLastRun,
            payload: { notices: 4, workspace: 'hq' },
          },
        }),
        t,
      ),
    ).toEqual([
      { label: 'admin.console.batches.metrics.notices', value: 4 },
      { label: 'admin.console.batches.metrics.workspace', value: 'hq' },
    ]);
    expect(
      batchMetrics(
        batch({
          id: 'industry-report',
          last_run: {
            ...baseLastRun,
            payload: {
              autojournal: 5,
              katech: 2,
              kdi_domestic: 3,
              kdi_material: 4,
              kdi_nara: 1,
              total: 15,
            },
          },
        }),
        t,
      ),
    ).toContainEqual({
      label: 'admin.console.batches.metrics.kdi',
      value: 8,
    });
  });

  it('uses the most useful primary metric per batch kind', () => {
    expect(
      batchPrimaryMetric(
        batch({
          id: 'erp-hr',
          last_run: { ...baseLastRun, payload: { rows_seen: 698 } },
        }),
        t,
      ),
    ).toEqual({
      label: 'admin.console.batches.rowsSeen',
      value: 698,
    });
    expect(batchPrimaryMetric(batch(), t)).toEqual({
      label: 'admin.console.batches.usersSeen',
      value: 10,
    });
    expect(
      batchPrimaryMetric(
        batch({
          id: 'integrated-hr',
          last_run: {
            ...baseLastRun,
            payload: { person_row_count: 10 },
          },
        }),
        t,
      ),
    ).toEqual({
      label: 'admin.console.batches.metrics.people',
      value: 10,
    });
    expect(
      batchPrimaryMetric(
        batch({
          id: 'news',
          last_run: { ...baseLastRun, payload: { total: 12 } },
        }),
        t,
      ),
    ).toEqual({
      label: 'admin.console.batches.metrics.total',
      value: 12,
    });
  });
});
