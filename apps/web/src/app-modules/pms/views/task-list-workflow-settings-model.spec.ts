import { describe, expect, it } from 'vitest';

import type { PmsTaskListStatus } from '../api/pms-api';
import {
  buildCreateWorkflowStatusCommand,
  buildUpdateWorkflowStatusCommand,
  createTaskListWorkflowSettingsModel,
  groupStatusesByCategory,
} from './task-list-workflow-settings-model';

function status(
  id: string,
  category: PmsTaskListStatus['category'],
): PmsTaskListStatus {
  return {
    id,
    category,
    color: '#3b82f6',
    name: id,
    slug: id,
    sort_order: 0,
  } as PmsTaskListStatus;
}

describe('task list workflow settings model', () => {
  it('lets owners and admins edit list and inherited space workflows', () => {
    expect(
      createTaskListWorkflowSettingsModel({
        currentUserRole: 'owner',
        statusMode: 'custom',
        statusSource: 'list',
        statuses: [],
      }),
    ).toMatchObject({
      canEditWorkflow: true,
      workflowReadOnly: false,
    });

    expect(
      createTaskListWorkflowSettingsModel({
        currentUserRole: 'admin',
        statusMode: 'inherit',
        statusSource: 'space',
        statuses: [],
      }),
    ).toMatchObject({
      canEditWorkflow: true,
      workflowReadOnly: false,
    });

    expect(
      createTaskListWorkflowSettingsModel({
        currentUserRole: 'member',
        statusMode: 'custom',
        statusSource: 'list',
        statuses: [],
      }),
    ).toMatchObject({
      canEditWorkflow: false,
      workflowReadOnly: true,
    });
  });

  it('groups statuses by category while preserving status ordering', () => {
    const grouped = groupStatusesByCategory([
      status('todo-1', 'not_started'),
      status('doing-1', 'active'),
      status('doing-2', 'active'),
      status('done-1', 'done'),
      status('todo-2', 'not_started'),
    ]);

    expect(grouped.get('not_started')?.map((item) => item.id)).toEqual([
      'todo-1',
      'todo-2',
    ]);
    expect(grouped.get('active')?.map((item) => item.id)).toEqual([
      'doing-1',
      'doing-2',
    ]);
    expect(grouped.get('done')?.map((item) => item.id)).toEqual(['done-1']);
    expect(grouped.get('closed')).toEqual([]);
  });

  it('creates statuses through the space adapter when the source is space and team id exists', () => {
    expect(
      buildCreateWorkflowStatusCommand({
        category: 'active',
        color: '#3b82f6',
        name: ' In Progress ',
        sortOrder: 3,
        statusSource: 'space',
        taskListId: 'list-1',
        teamId: 'space-1',
      }),
    ).toEqual({
      kind: 'space',
      spaceId: 'space-1',
      payload: {
        category: 'active',
        color: '#3b82f6',
        name: 'In Progress',
        sort_order: 3,
      },
    });
  });

  it('updates statuses through the list adapter otherwise', () => {
    expect(
      buildUpdateWorkflowStatusCommand({
        category: 'done',
        color: '#16a34a',
        name: ' Done ',
        statusId: 'status-1',
        statusSource: 'list',
      }),
    ).toEqual({
      kind: 'list',
      statusId: 'status-1',
      payload: {
        category: 'done',
        color: '#16a34a',
        name: 'Done',
      },
    });
  });

  it('returns consistent no-op commands when required identifiers are missing', () => {
    expect(
      buildCreateWorkflowStatusCommand({
        category: 'active',
        color: '#3b82f6',
        name: 'Next',
        sortOrder: 0,
        statusSource: 'space',
        taskListId: 'list-1',
        teamId: null,
      }),
    ).toEqual({ kind: 'noop', reason: 'missing_team_id' });

    expect(
      buildCreateWorkflowStatusCommand({
        category: 'active',
        color: '#3b82f6',
        name: 'Next',
        sortOrder: 0,
        statusSource: 'list',
        taskListId: '',
        teamId: 'space-1',
      }),
    ).toEqual({ kind: 'noop', reason: 'missing_task_list_id' });

    expect(
      buildUpdateWorkflowStatusCommand({
        category: 'active',
        color: '#3b82f6',
        name: 'Next',
        statusId: null,
        statusSource: 'list',
      }),
    ).toEqual({ kind: 'noop', reason: 'missing_status_id' });
  });
});
