import { describe, expect, it } from 'vitest';

import { buildTaskDetailSubtaskPayload } from './useTaskDetailSubtasks';
import type { PmsTaskListStatus } from '../api/pms-api';

describe('buildTaskDetailSubtaskPayload', () => {
  it('trims the title and links the new task to its parent', () => {
    expect(
      buildTaskDetailSubtaskPayload({
        parentTask: { id: 'task-parent' },
        title: '  Draft subtask  ',
      }),
    ).toMatchObject({
      assignee_id: null,
      description: '',
      due_date: null,
      milestone_id: null,
      parent_id: 'task-parent',
      priority: 'medium',
      start_date: null,
      status: 'todo',
      title: 'Draft subtask',
    });
  });

  it('uses the active custom status when todo is not configured', () => {
    const statuses = [
      {
        category: 'active',
        name: 'Doing',
        slug: 'doing',
      },
    ] as PmsTaskListStatus[];

    expect(
      buildTaskDetailSubtaskPayload({
        parentTask: { id: 'task-parent' },
        taskListStatuses: statuses,
        title: 'Follow up',
      }).status,
    ).toBe('doing');
  });
});
