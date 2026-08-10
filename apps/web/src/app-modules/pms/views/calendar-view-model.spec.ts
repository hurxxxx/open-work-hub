import { describe, expect, it } from 'vitest';

import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';

import {
  addCalendarMonths,
  buildPmsCalendarEvents,
  getCalendarTaskStatusColor,
  startOfCalendarMonth,
} from './calendar-view-model';

describe('calendar view model', () => {
  it('uses built-in status colors before custom status colors', () => {
    const customStatuses: PmsTaskListStatus[] = [
      status({ slug: 'todo', color: '#ffffff' }),
      status({ slug: 'blocked', color: '#111111' }),
    ];

    expect(getCalendarTaskStatusColor('todo', customStatuses)).toBe('#9ca3af');
    expect(getCalendarTaskStatusColor('blocked', customStatuses)).toBe(
      '#111111',
    );
    expect(getCalendarTaskStatusColor('unknown', customStatuses)).toBe(
      '#6b7280',
    );
  });

  it('maps multi-day PMS tasks to all-day events with exclusive end dates', () => {
    const events = buildPmsCalendarEvents([
      task({
        id: 'may-7-9',
        list_id: 'list-9',
        title: 'May span',
        start_date: '2026-05-07',
        due_date: '2026-05-09',
        status: 'in_progress',
        assignee_ids: ['user-1'],
      }),
    ]);

    expect(events).toEqual([
      expect.objectContaining({
        id: 'pms-task-may-7-9',
        title: 'May span',
        start: '2026-05-07',
        end: '2026-05-10',
        allDay: true,
        sourceType: 'pms_due',
        sourceId: 'may-7-9',
        color: 'rgb(220, 233, 253)',
        metadata: {
          taskListId: 'list-9',
          status: 'in_progress',
          assigneeIds: ['user-1'],
        },
      }),
    ]);
  });

  it('maps due-only tasks to one visible day', () => {
    const events = buildPmsCalendarEvents([
      task({ id: 'single-day', due_date: '2026-05-20' }),
    ]);

    expect(events[0]).toEqual(
      expect.objectContaining({
        start: '2026-05-20',
        end: '2026-05-21',
      }),
    );
  });

  it('normalizes reversed start and due dates', () => {
    const events = buildPmsCalendarEvents([
      task({
        id: 'reversed',
        start_date: '2026-05-09',
        due_date: '2026-05-07',
      }),
    ]);

    expect(events[0]).toEqual(
      expect.objectContaining({
        start: '2026-05-07',
        end: '2026-05-10',
      }),
    );
  });

  it('skips undated and invalid-date tasks', () => {
    const events = buildPmsCalendarEvents([
      task({ id: 'undated', due_date: null, start_date: null }),
      task({ id: 'invalid', due_date: 'not-a-date', start_date: null }),
      task({ id: 'valid', due_date: '2026-05-20' }),
    ]);

    expect(events.map((event) => event.sourceId)).toEqual(['valid']);
  });

  it('normalizes calendar month navigation to the first day of the target month', () => {
    expect(startOfCalendarMonth(new Date(2026, 4, 15))).toEqual(
      new Date(2026, 4, 1),
    );
    expect(addCalendarMonths(new Date(2026, 0, 31), 1)).toEqual(
      new Date(2026, 1, 1),
    );
    expect(addCalendarMonths(new Date(2026, 0, 1), -1)).toEqual(
      new Date(2025, 11, 1),
    );
  });
});

function task(overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    archived: false,
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    board_position: 1,
    checklist_done: 0,
    checklist_total: 0,
    comments_count: 0,
    completed_date: null,
    description: '',
    description_blocks: null,
    due_date: null,
    follower_ids: [],
    follower_names: [],
    id: 'task-1',
    labels: [],
    list_id: 'list-1',
    milestone_id: null,
    milestone_title: null,
    parent_id: null,
    priority: 'medium',
    priority_label: 'Medium',
    progress: 0,
    recurrence_rule: null,
    reference: 'AID-1',
    reporter_id: 'user-1',
    reporter_name: 'Reporter',
    start_date: null,
    status: 'todo',
    status_label: 'Todo',
    subtask_count: 0,
    title: 'Task title',
    updated_at: '2026-05-21T00:00:00Z',
    ...overrides,
  };
}

function status(overrides: Partial<PmsTaskListStatus> = {}): PmsTaskListStatus {
  return {
    id: 'status-1',
    slug: 'todo',
    name: 'Todo',
    color: '#9ca3af',
    category: 'not_started',
    sort_order: 1,
    ...overrides,
  } as PmsTaskListStatus;
}
