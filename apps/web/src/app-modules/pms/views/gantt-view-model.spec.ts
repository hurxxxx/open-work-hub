import { describe, expect, it } from 'vitest';

import {
  addGanttDays,
  applyGanttScheduleOverride,
  getGanttBarStyle,
  getGanttDragPreviewRange,
  getGanttStatusBarStyle,
  getGanttTaskDateRange,
  toGanttDateOnly,
} from './gantt-view-model';
import type { PmsTaskListStatus } from '../api/pms-api';

function task(
  overrides: {
    due_date?: string | null;
    id?: string;
    start_date?: string | null;
  } = {},
) {
  return {
    due_date: null,
    id: 'task-1',
    start_date: null,
    ...overrides,
  };
}

function status(overrides: Partial<PmsTaskListStatus> = {}): PmsTaskListStatus {
  return {
    category: 'active',
    color: '#2563eb',
    id: 'status-1',
    name: 'In Progress',
    slug: 'in_progress',
    sort_order: 1,
    ...overrides,
  };
}

describe('gantt view model', () => {
  it('builds a local date range from start and due dates', () => {
    const range = getGanttTaskDateRange(
      task({
        due_date: '2026-05-12',
        start_date: '2026-05-10',
      }),
    );

    expect(range).not.toBeNull();
    expect(range?.start.getFullYear()).toBe(2026);
    expect(range?.start.getMonth()).toBe(4);
    expect(range?.start.getDate()).toBe(10);
    expect(range?.end.getFullYear()).toBe(2026);
    expect(range?.end.getMonth()).toBe(4);
    expect(range?.end.getDate()).toBe(12);
  });

  it('uses either date as the single-day fallback', () => {
    expect(getGanttTaskDateRange(task({ start_date: '2026-05-10' }))).toEqual({
      end: new Date(2026, 4, 10),
      start: new Date(2026, 4, 10),
    });
    expect(getGanttTaskDateRange(task({ due_date: '2026-05-12' }))).toEqual({
      end: new Date(2026, 4, 12),
      start: new Date(2026, 4, 12),
    });
  });

  it('ignores tasks without schedule dates', () => {
    expect(getGanttTaskDateRange(task())).toBeNull();
  });

  it('formats moved local dates as date-only payloads', () => {
    expect(toGanttDateOnly(addGanttDays(new Date(2026, 0, 31), 1))).toBe(
      '2026-02-01',
    );
  });

  it('applies pending schedule overrides without changing task identity fields', () => {
    expect(
      applyGanttScheduleOverride(
        task({
          due_date: '2026-05-04',
          id: 'task-1',
          start_date: '2026-05-02',
        }),
        {
          due_date: '2026-05-06',
          start_date: '2026-05-02',
        },
      ),
    ).toEqual({
      due_date: '2026-05-06',
      id: 'task-1',
      start_date: '2026-05-02',
    });
  });

  it('positions a task bar inside the visible month', () => {
    expect(
      getGanttBarStyle({
        dayWidth: 40,
        dragging: null,
        visibleEnd: new Date(2026, 4, 31),
        visibleStart: new Date(2026, 4, 1),
        task: task({ due_date: '2026-05-04', start_date: '2026-05-02' }),
      }),
    ).toEqual({ left: '40px', width: '120px' });
  });

  it('clips a task bar to the visible month', () => {
    expect(
      getGanttBarStyle({
        dayWidth: 40,
        dragging: null,
        visibleEnd: new Date(2026, 4, 31),
        visibleStart: new Date(2026, 4, 1),
        task: task({ due_date: '2026-05-02', start_date: '2026-04-30' }),
      }),
    ).toEqual({ left: '0px', width: '80px' });
  });

  it('uses the matching drag preview without mutating other tasks', () => {
    const baseInput = {
      dayWidth: 40,
      dragging: {
        deltaDays: 2,
        end: new Date(2026, 4, 4),
        mode: 'move' as const,
        start: new Date(2026, 4, 2),
        taskId: 'task-1',
      },
      visibleEnd: new Date(2026, 4, 31),
      visibleStart: new Date(2026, 4, 1),
    };

    expect(
      getGanttBarStyle({
        ...baseInput,
        task: task({ due_date: '2026-05-04', start_date: '2026-05-02' }),
      }),
    ).toEqual({ left: '120px', width: '120px' });
    expect(
      getGanttBarStyle({
        ...baseInput,
        task: task({
          due_date: '2026-05-04',
          id: 'task-2',
          start_date: '2026-05-02',
        }),
      }),
    ).toEqual({ left: '40px', width: '120px' });
  });

  it('hides task bars outside the visible month', () => {
    expect(
      getGanttBarStyle({
        dayWidth: 40,
        dragging: null,
        visibleEnd: new Date(2026, 4, 31),
        visibleStart: new Date(2026, 4, 1),
        task: task({ due_date: '2026-06-02', start_date: '2026-06-01' }),
      }),
    ).toBeNull();
  });

  it('previews resized task ranges without crossing the opposite edge', () => {
    expect(
      getGanttDragPreviewRange({
        deltaDays: 2,
        end: new Date(2026, 4, 5),
        mode: 'resize-start',
        start: new Date(2026, 4, 2),
        taskId: 'task-1',
      }),
    ).toEqual({
      end: new Date(2026, 4, 5),
      start: new Date(2026, 4, 4),
    });

    expect(
      getGanttDragPreviewRange({
        deltaDays: -10,
        end: new Date(2026, 4, 5),
        mode: 'resize-end',
        start: new Date(2026, 4, 2),
        taskId: 'task-1',
      }),
    ).toEqual({
      end: new Date(2026, 4, 2),
      start: new Date(2026, 4, 2),
    });
  });

  it('uses configured workflow status colors for gantt bars', () => {
    expect(
      getGanttStatusBarStyle({
        status: 'in_progress',
        taskListStatuses: [status({ color: '#facc15' })],
      }),
    ).toEqual({
      backgroundColor: '#facc15',
      borderColor: '#facc15',
      color: '#111827',
    });

    expect(
      getGanttStatusBarStyle({
        status: 'done',
        taskListStatuses: [status({ color: '#16a34a', slug: 'done' })],
      }),
    ).toEqual({
      backgroundColor: '#16a34a',
      borderColor: '#16a34a',
      color: '#111827',
    });
  });

  it('falls back when a status color is missing or invalid', () => {
    expect(
      getGanttStatusBarStyle({
        status: 'in_progress',
        taskListStatuses: [status({ color: 'blue' })],
      }),
    ).toBeUndefined();
  });
});
