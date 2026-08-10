import { describe, expect, it } from 'vitest';

import type { PmsTask, PmsTaskListMember } from '../api/pms-api';
import { buildAssigneeTaskGroups } from './list-view-grouping-model';
import { buildTaskHierarchy, sortTasksByHierarchy } from './pms-task-hierarchy';

function task(id: string, overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    board_position: 1000,
    id,
    parent_id: null,
    status: 'todo',
    title: id,
    ...overrides,
  } as PmsTask;
}

describe('list view grouping model', () => {
  it('groups a task hierarchy by the normalized root assignee set', () => {
    const root = task('root', {
      assignee_id: 'user-1',
      assignee_ids: ['user-2', 'user-1'],
      assignee_name: 'User One',
      assignee_names: ['User Two', 'User One'],
    });
    const child = task('child', {
      assignee_id: 'user-1',
      assignee_ids: ['user-1'],
      board_position: 2000,
      parent_id: root.id,
    });
    const sameCombinationRoot = task('same-combination-root', {
      assignee_id: 'user-2',
      assignee_ids: ['user-1', 'user-2'],
      assignee_name: 'User Two',
      assignee_names: ['User One', 'User Two'],
      board_position: 3000,
    });
    const tasks = [child, sameCombinationRoot, root];
    const hierarchy = buildTaskHierarchy(tasks);

    const groups = buildAssigneeTaskGroups({
      hierarchy,
      members: [
        {
          full_name: 'User Two',
          user_id: 'user-2',
        } as PmsTaskListMember,
      ],
      orderedTasks: sortTasksByHierarchy(tasks),
      unassignedLabel: 'Unassigned',
      visibleTasks: sortTasksByHierarchy(tasks),
    });

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      assigneeIds: ['user-1', 'user-2'],
      issues: [root, child, sameCombinationRoot],
      label: 'User One · User Two',
      rootCount: 2,
    });
  });
});
