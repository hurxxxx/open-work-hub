import { describe, expect, it } from 'vitest';

import {
  addCancellingCoreBackgroundWorkKey,
  coreBackgroundWorkItemKey,
  buildCoreBackgroundWorkSessionSnapshot,
  filterCoreBackgroundWorkSourcesForApps,
  mergeCoreBackgroundWorkSourceListResults,
  removeCancellingCoreBackgroundWorkKey,
  resolveCoreBackgroundWorkCadence,
  selectActiveCoreBackgroundWorkItems,
  type CoreBackgroundWorkItem,
  type CoreBackgroundWorkRuntimeSource,
} from './background-work';

function item(
  id: string,
  status: CoreBackgroundWorkItem['status'],
  updatedAt: string,
  overrides: Partial<CoreBackgroundWorkItem> = {},
): CoreBackgroundWorkItem {
  return {
    id,
    sourceId: 'exports',
    kind: 'document-export',
    title: id,
    status,
    updatedAt,
    ...overrides,
  };
}

describe('core background work session', () => {
  it('resolves the fastest active and idle source cadence', () => {
    expect(
      resolveCoreBackgroundWorkCadence([
        { pollIntervalMs: 7000, idlePollIntervalMs: 45000 },
        { pollIntervalMs: 3000 },
      ]),
    ).toEqual({
      activePollIntervalMs: 3000,
      idlePollIntervalMs: 30000,
    });
  });

  it('filters background sources by enabled workspace app and nav gates', () => {
    const unownedSource = {
      id: 'unowned-job',
      list: async () => [],
    } as unknown as CoreBackgroundWorkRuntimeSource;
    const sources: CoreBackgroundWorkRuntimeSource[] = [
      {
        appId: 'research',
        id: 'research-sync',
        requiredNavItemId: 'research-home',
        list: async () => [],
      },
      {
        appId: 'research',
        id: 'disabled-tool',
        requiredNavItemId: 'disabled-tool',
        list: async () => [],
      },
      { appId: 'pms', id: 'pms-job', list: async () => [] },
      unownedSource,
    ];

    expect(
      filterCoreBackgroundWorkSourcesForApps(sources, {
        enabledAppIds: ['research'],
        enabledNavItemIds: ['research-home'],
      }).map((source) => source.id),
    ).toEqual(['research-sync']);
  });

  it('emits terminal toast events only when an active item finishes', () => {
    const running = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const failed = item('export-1', 'failed', '2026-05-31T09:01:00.000Z');
    const snapshot = buildCoreBackgroundWorkSessionSnapshot({
      items: [
        failed,
        item('already-done', 'succeeded', '2026-05-31T09:01:00.000Z'),
      ],
      previousStatuses: new Map([
        [coreBackgroundWorkItemKey(running), running.status],
        ['exports:already-done', 'succeeded'],
      ]),
      cadence: { activePollIntervalMs: 1000, idlePollIntervalMs: 9000 },
    });

    expect(snapshot.toastEvents).toEqual([{ type: 'failed', item: failed }]);
    expect(snapshot.nextPollDelayMs).toBe(9000);
  });

  it('keeps last-known source items when a source list call fails', () => {
    const running = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const previousItemsBySource = new Map([['exports', [running]]]);

    expect(
      mergeCoreBackgroundWorkSourceListResults({
        previousItemsBySource,
        settled: [
          { status: 'rejected', reason: new Error('temporary outage') },
        ],
        sources: [{ id: 'exports' }],
      }).items,
    ).toEqual([running]);
  });

  it('selects active items and updates cancelling keys immutably', () => {
    const target = item('export-1', 'running', '2026-05-31T09:00:00.000Z');
    const current = new Set(['exports:other']);
    const added = addCancellingCoreBackgroundWorkKey(current, target);
    const removed = removeCancellingCoreBackgroundWorkKey(added, target);

    expect(
      selectActiveCoreBackgroundWorkItems([
        item('old-running', 'running', '2026-05-31T09:00:00.000Z'),
        item('done', 'succeeded', '2026-05-31T11:00:00.000Z'),
        item('new-queued', 'queued', '2026-05-31T10:00:00.000Z'),
      ]).map((value) => value.id),
    ).toEqual(['new-queued', 'old-running']);
    expect([...current]).toEqual(['exports:other']);
    expect([...added].sort()).toEqual(['exports:export-1', 'exports:other']);
    expect([...removed]).toEqual(['exports:other']);
  });
});
