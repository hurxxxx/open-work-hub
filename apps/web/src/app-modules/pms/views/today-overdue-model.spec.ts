import { describe, expect, it } from 'vitest';

import type { PmsTask } from '../api/pms-api';

import {
  buildTodayOverdueTaskGroups,
  isPmsTaskScheduleOpen,
} from './today-overdue-model';

describe('today overdue model', () => {
  it('treats terminal task statuses as closed for scheduling', () => {
    expect(isPmsTaskScheduleOpen('todo')).toBe(true);
    expect(isPmsTaskScheduleOpen('active')).toBe(true);
    expect(isPmsTaskScheduleOpen('done')).toBe(false);
    expect(isPmsTaskScheduleOpen('canceled')).toBe(false);
    expect(isPmsTaskScheduleOpen('closed')).toBe(false);
    expect(isPmsTaskScheduleOpen('complete')).toBe(false);
  });

  it('splits open tasks into overdue and today buckets while preserving order', () => {
    const groups = buildTodayOverdueTaskGroups(
      [
        task({ id: 'overdue-1', due_date: '2026-05-30' }),
        task({ id: 'today-1', due_date: '2026-05-31' }),
        task({ id: 'future', due_date: '2026-06-01' }),
        task({ id: 'undated', due_date: null }),
        task({ id: 'overdue-closed', due_date: '2026-05-30', status: 'done' }),
        task({ id: 'overdue-2', due_date: '2026-05-29' }),
        task({ id: 'today-2', due_date: '2026-05-31' }),
      ],
      '2026-05-31',
    );

    expect(groups.overdue.map((item) => item.id)).toEqual([
      'overdue-1',
      'overdue-2',
    ]);
    expect(groups.today.map((item) => item.id)).toEqual(['today-1', 'today-2']);
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
