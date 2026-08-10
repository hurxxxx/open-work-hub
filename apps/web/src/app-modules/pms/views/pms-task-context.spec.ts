import { describe, expect, it } from 'vitest';

import type { PmsTaskList } from '../api/pms-api';

import { buildPmsTaskContextLabel } from './pms-task-context';

describe('PMS task context labels', () => {
  it('uses space, folder, and list names when available', () => {
    expect(
      buildPmsTaskContextLabel({
        fallbackSpaceName: 'Default space',
        task: { list_id: 'list-1' },
        taskLists: [
          taskList({
            folder_name: 'Engineering',
            id: 'list-1',
            name: 'Release tasks',
            team_name: 'Product',
          }),
        ],
      }),
    ).toBe('Product / Engineering / Release tasks');
  });

  it('falls back to the default space name and omits missing folders', () => {
    expect(
      buildPmsTaskContextLabel({
        fallbackSpaceName: 'Default space',
        task: { list_id: 'list-1' },
        taskLists: [
          taskList({
            folder_name: null,
            id: 'list-1',
            name: 'Personal tasks',
            team_name: null,
          }),
        ],
      }),
    ).toBe('Default space / Personal tasks');
  });
});

function taskList(overrides: Partial<PmsTaskList>): PmsTaskList {
  return {
    archived: false,
    created_at: '2026-07-09T00:00:00Z',
    description: '',
    folder_id: null,
    folder_name: null,
    id: 'list-1',
    key: 'PMS',
    member_count: 1,
    milestone_count: 0,
    name: 'Tasks',
    overdue_task_count: 0,
    progress: 0,
    role: 'owner',
    sort_order: 0,
    status: 'active',
    status_mode: 'inherit',
    task_count: 0,
    team_id: null,
    team_name: null,
    updated_at: '2026-07-09T00:00:00Z',
    ...overrides,
  };
}
