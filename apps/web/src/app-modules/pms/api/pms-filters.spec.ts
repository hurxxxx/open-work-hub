import { describe, expect, it, vi, afterEach } from 'vitest';

import {
  listAllAssignedTasks,
  listAllTaskListTasks,
  listTaskListTasks,
  listTodayOverdueTasks,
  type PmsTask,
  type PmsTaskListStatus,
} from './pms-api';
import {
  createDefaultTaskFilterParams,
  filterDefaultVisibleTasks,
  getEffectiveTaskStatusFilter,
  hasSelectedCompletionStatus,
  mergeTaskListStatusesForFilter,
  reconcileSelectedTaskIds,
  setCompletionStatusesVisible,
  toLocalDateInputValue,
  withEffectiveTaskStatusFilter,
} from './pms-filters';

describe('pms filter helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults task filters to active tasks', () => {
    expect(createDefaultTaskFilterParams()).toEqual({
      archived_state: 'active',
    });
    expect(createDefaultTaskFilterParams({ q: 'deployment' })).toEqual({
      archived_state: 'active',
      q: 'deployment',
    });
  });

  it('preserves selected id set identity when selected ids are still visible', () => {
    const selectedIds = new Set(['task-1', 'task-2']);
    const nextSelection = reconcileSelectedTaskIds(selectedIds, [
      { id: 'task-1' },
      { id: 'task-2' },
      { id: 'task-4' },
    ] as Array<{ id: string }>);

    expect(nextSelection).toBe(selectedIds);
    expect(Array.from(nextSelection)).toEqual(['task-1', 'task-2']);
  });

  it('removes stale selected ids against the visible task list', () => {
    const selectedIds = new Set(['task-1', 'task-2', 'task-3']);
    const nextSelection = reconcileSelectedTaskIds(selectedIds, [
      { id: 'task-2' },
      { id: 'task-4' },
    ] as Array<{ id: string }>);

    expect(nextSelection).not.toBe(selectedIds);
    expect(Array.from(nextSelection)).toEqual(['task-2']);
  });

  it('formats local dates without UTC conversion', () => {
    expect(toLocalDateInputValue(new Date(2026, 3, 8, 0, 30))).toBe(
      '2026-04-08',
    );
  });

  it('hides completion statuses by default, including custom workflow statuses', () => {
    const tasks = [
      { id: 'task-todo', parent_id: 'task-done', status: 'todo' },
      { id: 'task-done', status: 'done' },
      { id: 'task-closed', status: 'accepted' },
    ] as PmsTask[];
    const statuses = [
      { slug: 'todo', category: 'not_started' },
      { slug: 'done', category: 'done' },
      { slug: 'accepted', category: 'closed' },
    ] as PmsTaskListStatus[];

    expect(
      filterDefaultVisibleTasks(tasks, statuses).map((task) => task.id),
    ).toEqual(['task-todo']);
  });

  it('selects every non-completion status by default', () => {
    const statuses = [
      { slug: 'backlog', category: 'not_started' },
      { slug: 'building', category: 'active' },
      { slug: 'released', category: 'done' },
      { slug: 'canceled', category: 'closed' },
    ] as PmsTaskListStatus[];

    expect(getEffectiveTaskStatusFilter(undefined, statuses)).toEqual([
      'backlog',
      'building',
    ]);
    expect(
      withEffectiveTaskStatusFilter({ archived_state: 'active' }, statuses),
    ).toEqual({
      archived_state: 'active',
      status: ['backlog', 'building'],
    });
  });

  it('adds and removes every completion status without changing other selections', () => {
    const statuses = [
      { slug: 'todo', category: 'not_started' },
      { slug: 'doing', category: 'active' },
      { slug: 'verified', category: 'done' },
      { slug: 'declined', category: 'closed' },
    ] as PmsTaskListStatus[];

    const shown = setCompletionStatusesVisible(['doing'], statuses, true);
    expect(shown).toEqual(['doing', 'verified', 'declined']);
    expect(hasSelectedCompletionStatus(shown, statuses)).toBe(true);
    expect(setCompletionStatusesVisible(shown, statuses, false)).toEqual([
      'doing',
    ]);
    expect(hasSelectedCompletionStatus(['doing'], statuses)).toBe(false);
  });

  it('uses the completion category when lists share a status slug with conflicting categories', () => {
    const statuses = [
      { id: 'active-review', slug: 'review', category: 'active' },
      { id: 'done-review', slug: 'review', category: 'done' },
      { id: 'todo', slug: 'todo', category: 'not_started' },
    ] as PmsTaskListStatus[];

    expect(
      mergeTaskListStatusesForFilter(statuses).map(({ slug, category }) => ({
        slug,
        category,
      })),
    ).toEqual([
      { slug: 'review', category: 'done' },
      { slug: 'todo', category: 'not_started' },
    ]);
  });

  it('treats an explicit empty status selection as showing no tasks', () => {
    const tasks = [
      { id: 'task-todo', status: 'todo' },
      { id: 'task-done', status: 'done' },
    ] as PmsTask[];
    const statuses = [
      { slug: 'todo', category: 'not_started' },
      { slug: 'done', category: 'done' },
    ] as PmsTaskListStatus[];

    expect(filterDefaultVisibleTasks(tasks, statuses, { status: [] })).toEqual(
      [],
    );
  });

  it('uses task progress when custom completion status metadata is unavailable', () => {
    const tasks = [
      { id: 'task-active', progress: 0.5, status: 'doing' },
      { id: 'task-done', progress: 1, status: 'approved' },
      { id: 'task-closed', progress: null, status: 'canceled-by-customer' },
    ] as PmsTask[];

    expect(filterDefaultVisibleTasks(tasks, []).map((task) => task.id)).toEqual(
      ['task-active'],
    );
  });

  it('keeps completed tasks when the user explicitly filters by status', () => {
    const tasks = [
      { id: 'task-todo', status: 'todo' },
      { id: 'task-done', status: 'done' },
    ] as PmsTask[];

    expect(
      filterDefaultVisibleTasks(tasks, [], { status: ['done'] }).map(
        (task) => task.id,
      ),
    ).toEqual(['task-done']);
  });
});

describe('listTaskListTasks', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps archived filter states to API query params', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        },
      ),
    );

    await listTaskListTasks(
      'token',
      'task-list-1',
      createDefaultTaskFilterParams(),
    );
    expect(String(fetchSpy.mock.calls[0][0])).toContain('archived=false');

    await listTaskListTasks('token', 'task-list-1', {
      archived_state: 'archived',
    });
    expect(String(fetchSpy.mock.calls[1][0])).toContain('archived=true');

    await listTaskListTasks('token', 'task-list-1', { archived_state: 'all' });
    expect(String(fetchSpy.mock.calls[2][0])).not.toContain('archived=');
  });

  it('loads every task-list task page while preserving filters', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'task-1' }],
            total: 2,
            page: 1,
            page_size: 100,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'task-2' }],
            total: 2,
            page: 2,
            page_size: 100,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      );

    const response = await listAllTaskListTasks('token', 'task-list-1', {
      archived_state: 'active',
      q: 'motor',
    });

    expect(response.items.map((item) => item.id)).toEqual(['task-1', 'task-2']);
    expect(String(fetchSpy.mock.calls[0][0])).toContain('page=1');
    expect(String(fetchSpy.mock.calls[0][0])).toContain('q=motor');
    expect(String(fetchSpy.mock.calls[0][0])).toContain('archived=false');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('page=2');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('q=motor');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('archived=false');
  });

  it('maps task list sort options to every paginated request', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'task-1' }],
            total: 2,
            page: 1,
            page_size: 100,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'task-2' }],
            total: 2,
            page: 2,
            page_size: 100,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      );

    await listAllTaskListTasks(
      'token',
      'task-list-1',
      {},
      {
        sort: { direction: 'desc', field: 'completed_date' },
      },
    );

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    for (const [request] of fetchSpy.mock.calls) {
      const url = String(request);
      expect(url).toContain('sort_by=completed_date');
      expect(url).toContain('sort_dir=desc');
    }
  });

  it('does not request every task when the status selection is explicitly empty', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    await expect(
      listAllTaskListTasks('token', 'task-list-1', { status: [] }),
    ).resolves.toEqual({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('loads every assigned task page', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'assigned-1' }],
            total: 2,
            page: 1,
            page_size: 50,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ id: 'assigned-2' }],
            total: 2,
            page: 2,
            page_size: 50,
          }),
          {
            headers: { 'Content-Type': 'application/json' },
            status: 200,
          },
        ),
      );

    const response = await listAllAssignedTasks('token');

    expect(response.items.map((item) => item.id)).toEqual([
      'assigned-1',
      'assigned-2',
    ]);
    expect(String(fetchSpy.mock.calls[0][0])).toContain('page=1');
    expect(String(fetchSpy.mock.calls[0][0])).toContain('page_size=50');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('page=2');
  });

  it('builds the today-overdue task query', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], total: 0, page: 1, page_size: 50 }),
        {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        },
      ),
    );

    await listTodayOverdueTasks('token', '2026-07-09', {
      page: 2,
      pageSize: 50,
    });

    const url = String(fetchSpy.mock.calls[0][0]);
    expect(url).toContain('/api/v1/pms/tasks/today-overdue');
    expect(url).toContain('today=2026-07-09');
    expect(url).toContain('page=2');
    expect(url).toContain('page_size=50');
  });
});
