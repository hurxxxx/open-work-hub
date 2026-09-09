import { describe, expect, it } from 'vitest';

import {
  addCancellingBackgroundWorkKey,
  backgroundWorkItemKey,
  buildBackgroundWorkSessionSnapshot,
  filterBackgroundWorkSourcesForApps,
  mergeBackgroundWorkSourceListResults,
  removeCancellingBackgroundWorkKey,
  resolveBackgroundWorkCadence,
  selectActiveBackgroundWorkItems,
} from './background-work-session';
import type {
  BackgroundWorkItem,
  BackgroundWorkSource,
} from './background-work-session';

function item(
  id: string,
  status: BackgroundWorkItem['status'],
  updatedAt: string,
  overrides: Partial<BackgroundWorkItem> = {},
): BackgroundWorkItem {
  return {
    id,
    sourceId: 'exports',
    kind: 'report-export',
    title: id,
    status,
    updatedAt,
    ...overrides,
  };
}

describe('background-work-session', () => {
  it('resolves the fastest active and idle source cadence', () => {
    expect(
      resolveBackgroundWorkCadence([
        { pollIntervalMs: 7000, idlePollIntervalMs: 45000 },
        { pollIntervalMs: 3000 },
      ]),
    ).toEqual({
      activePollIntervalMs: 3000,
      idlePollIntervalMs: 30000,
    });
  });

  it('uses default cadence when no sources are configured', () => {
    expect(resolveBackgroundWorkCadence([])).toEqual({
      activePollIntervalMs: 5000,
      idlePollIntervalMs: 30000,
    });
  });

  it('filters background sources by enabled app and nav gates', () => {
    const unownedSource = {
      id: 'unowned-job',
      list: async () => [],
    } as unknown as BackgroundWorkSource;
    const sources: BackgroundWorkSource[] = [
      {
        appId: 'reports',
        id: 'report-export',
        requiredNavItemId: 'report-export',
        list: async () => [],
      },
      {
        appId: 'reports',
        id: 'disabled-tool',
        requiredNavItemId: 'disabled-tool',
        list: async () => [],
      },
      { appId: 'pms', id: 'pms-job', list: async () => [] },
      unownedSource,
    ];

    expect(
      filterBackgroundWorkSourcesForApps(sources, {
        enabledAppIds: ['reports'],
        enabledNavItemIds: ['report-export'],
      }).map((source) => source.id),
    ).toEqual(['report-export']);
  });

  it('selects active items sorted by most recently updated first', () => {
    expect(
      selectActiveBackgroundWorkItems([
        item('old-running', 'running', '2026-05-31T09:00:00.000Z'),
        item('done', 'succeeded', '2026-05-31T11:00:00.000Z'),
        item('new-queued', 'queued', '2026-05-31T10:00:00.000Z'),
      ]).map((value) => value.id),
    ).toEqual(['new-queued', 'old-running']);
  });

  it('emits terminal toast events only when an active item finishes', () => {
    const running = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const failed = item('export-1', 'failed', '2026-05-31T09:01:00.000Z', {
      description: 'Prompt rejected',
    });
    const snapshot = buildBackgroundWorkSessionSnapshot({
      items: [
        failed,
        item('already-done', 'succeeded', '2026-05-31T09:01:00.000Z'),
      ],
      previousStatuses: new Map([
        [backgroundWorkItemKey(running), running.status],
        ['exports:already-done', 'succeeded'],
      ]),
      cadence: { activePollIntervalMs: 1000, idlePollIntervalMs: 9000 },
    });

    expect(snapshot.toastEvents).toEqual([{ type: 'failed', item: failed }]);
    expect(snapshot.nextPollDelayMs).toBe(9000);
    expect([...snapshot.nextStatuses.entries()]).toEqual([
      ['exports:export-1', 'failed'],
      ['exports:already-done', 'succeeded'],
    ]);
  });

  it('keeps last-known source items when a source list call fails', () => {
    const running = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const completed = item('export-1', 'succeeded', '2026-05-31T09:01:00.000Z');
    const previousItemsBySource = new Map([['exports', [running]]]);
    const failedRefresh = mergeBackgroundWorkSourceListResults({
      previousItemsBySource,
      settled: [{ status: 'rejected', reason: new Error('temporary outage') }],
      sources: [{ id: 'exports' }],
    });

    expect(failedRefresh.items).toEqual([running]);

    const failedSnapshot = buildBackgroundWorkSessionSnapshot({
      items: failedRefresh.items,
      previousStatuses: new Map([
        [backgroundWorkItemKey(running), running.status],
      ]),
      cadence: { activePollIntervalMs: 1000, idlePollIntervalMs: 9000 },
    });
    expect(failedSnapshot.activeItems).toEqual([running]);
    expect(failedSnapshot.toastEvents).toEqual([]);

    const recoveredRefresh = mergeBackgroundWorkSourceListResults({
      previousItemsBySource: failedRefresh.itemsBySource,
      settled: [{ status: 'fulfilled', value: [completed] }],
      sources: [{ id: 'exports' }],
    });
    const recoveredSnapshot = buildBackgroundWorkSessionSnapshot({
      items: recoveredRefresh.items,
      previousStatuses: failedSnapshot.nextStatuses,
      cadence: { activePollIntervalMs: 1000, idlePollIntervalMs: 9000 },
    });

    expect(recoveredSnapshot.toastEvents).toEqual([
      { type: 'completed', item: completed },
    ]);
  });

  it('keeps active cadence while any item is queued or running', () => {
    const snapshot = buildBackgroundWorkSessionSnapshot({
      items: [
        item('done', 'succeeded', '2026-05-31T09:00:00.000Z'),
        item('queued', 'queued', '2026-05-31T09:01:00.000Z'),
      ],
      previousStatuses: new Map(),
      cadence: { activePollIntervalMs: 1500, idlePollIntervalMs: 15000 },
    });

    expect(snapshot.activeItems.map((value) => value.id)).toEqual(['queued']);
    expect(snapshot.nextPollDelayMs).toBe(1500);
    expect(snapshot.toastEvents).toEqual([]);
  });

  it('adds and removes cancelling keys without mutating the current set', () => {
    const target = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const current = new Set(['exports:other']);

    const added = addCancellingBackgroundWorkKey(current, target);
    const removed = removeCancellingBackgroundWorkKey(added, target);

    expect([...current]).toEqual(['exports:other']);
    expect([...added].sort()).toEqual(['exports:export-1', 'exports:other']);
    expect([...removed]).toEqual(['exports:other']);
  });
});
