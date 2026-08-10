import { describe, expect, it } from 'vitest';

import type {
  PmsLabel,
  PmsMilestone,
  PmsTaskListMember,
  TaskFilterParams,
} from '../api/pms-api';
import {
  buildTaskFilterPills,
  createClearedTaskFilterParams,
  createLoadedSavedTaskFilterParams,
  createSavedFilter,
  createSavedTaskFilterParams,
  isFilterActive,
  loadSavedFilters,
  paramsFromSavedFilter,
  removeSavedFilterAt,
  saveSavedFilters,
  type SavedFilter,
} from './filter-bar-model';

function t(key: string, options?: Record<string, unknown>): string {
  if (!options) return key;
  return `${key}:${Object.entries(options)
    .map(([name, value]) => `${name}=${String(value)}`)
    .join(',')}`;
}

function storage(initial: Record<string, string> = {}) {
  const values = { ...initial };
  return {
    getItem: (key: string) => values[key] ?? null,
    setItem: (key: string, value: string) => {
      values[key] = value;
    },
    values,
  };
}

const members: PmsTaskListMember[] = [
  {
    user_id: 'user-1',
    full_name: 'Ada Lovelace',
    email: 'ada@example.test',
  } as PmsTaskListMember,
];
const labels: PmsLabel[] = [
  { id: 'label-1', name: 'Bug', color: '#ef4444' } as PmsLabel,
];
const milestones: PmsMilestone[] = [
  { id: 'milestone-1', title: 'M1' } as PmsMilestone,
];

describe('filter bar model', () => {
  it('treats q-only and default archive filters as inactive', () => {
    expect(isFilterActive({ q: 'needle', archived_state: 'active' })).toBe(
      false,
    );
    expect(isFilterActive({ archived_state: 'archived' })).toBe(true);
    expect(isFilterActive({ status: ['todo'] })).toBe(true);
  });

  it('clears all filters while preserving search text', () => {
    expect(
      createClearedTaskFilterParams({
        q: 'needle',
        status: ['todo'],
        priority: 'high',
        archived_state: 'archived',
      }),
    ).toEqual({ archived_state: 'active', q: 'needle' });
  });

  it('strips search text when saving and restores current search when loading', () => {
    const savedParams = createSavedTaskFilterParams({
      q: 'draft search',
      label_id: 'label-1',
    });

    expect(savedParams).toEqual({
      archived_state: 'active',
      label_id: 'label-1',
      q: undefined,
    });
    expect(
      createLoadedSavedTaskFilterParams(savedParams, { q: 'current search' }),
    ).toEqual({
      archived_state: 'active',
      label_id: 'label-1',
      q: 'current search',
    });
  });

  it('normalizes saved filters and removes filters by index', () => {
    const saved = createSavedFilter('  Mine  ', {
      q: 'hidden',
      assignee_id: 'user-1',
    });
    expect(saved).toEqual({
      name: 'Mine',
      params: {
        archived_state: 'active',
        assignee_id: 'user-1',
        q: undefined,
      },
    });
    expect(createSavedFilter('   ', {})).toBeNull();

    const filters: SavedFilter[] = [
      saved as SavedFilter,
      { name: 'Other', params: { priority: 'low' } },
    ];
    expect(removeSavedFilterAt(filters, 0)).toEqual([filters[1]]);
    expect(paramsFromSavedFilter(filters[1], { q: 'search' })).toEqual({
      archived_state: 'active',
      priority: 'low',
      q: 'search',
    });
  });

  it('persists saved filters under the task list key', () => {
    const fakeStorage = storage();
    const filters: SavedFilter[] = [{ name: 'Mine', params: { status: ['todo'] } }];

    saveSavedFilters('list-1', filters, fakeStorage);

    expect(loadSavedFilters('list-1', fakeStorage)).toEqual(filters);
    expect(loadSavedFilters('list-2', fakeStorage)).toEqual([]);
  });

  it('returns no saved filters for invalid storage payloads', () => {
    const fakeStorage = storage({ pms_saved_filters_list: '{' });

    expect(loadSavedFilters('list', fakeStorage)).toEqual([]);
  });

  it('builds localized pills and clear params', () => {
    const params: TaskFilterParams = {
      status: ['todo', 'custom'],
      priority: 'high',
      assignee_id: 'user-1',
      label_id: 'label-1',
      milestone_id: 'milestone-1',
      start_date_from: '2026-05-01',
      due_date_to: '2026-05-30',
      archived_state: 'archived',
      q: 'needle',
    };

    const pills = buildTaskFilterPills({
      labels,
      members,
      milestones,
      params,
      statusOptions: [{ value: 'todo', label: 'To do' }],
      translate: t,
    });

    expect(pills.map((pill) => pill.label)).toEqual([
      'pms.filter.pillStatus:value=To do, custom',
      'pms.filter.pillPriority:value=pms.priorityHigh',
      'pms.filter.pillAssignee:value=Ada Lovelace',
      'pms.filter.pillLabel:value=Bug',
      'pms.filter.pillMilestone:value=M1',
      'pms.filter.pillStart:from=2026-05-01,to=...',
      'pms.filter.pillDue:from=...,to=2026-05-30',
      'pms.filter.pillArchive:value=pms.filter.archive.archived',
    ]);
    expect(pills[0].clearParams).toMatchObject({
      q: 'needle',
      status: undefined,
    });
    expect(pills[pills.length - 1].clearParams).toMatchObject({
      archived_state: 'active',
      q: 'needle',
    });
  });
});
