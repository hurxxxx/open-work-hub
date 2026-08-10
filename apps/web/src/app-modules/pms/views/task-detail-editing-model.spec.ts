import { describe, expect, it, vi } from 'vitest';

import {
  applyTaskUserRoleState,
  resolveTaskDetailStatusLabel,
  restoreTaskUserRoleState,
  toggleTaskUserRoleId,
} from './task-detail-editing-model';

describe('task detail editing model', () => {
  it('applies and restores assignee state', () => {
    const previousTask = task({
      assignee_id: 'old-1',
      assignee_ids: ['old-1'],
      assignee_name: 'Old One',
      assignee_names: ['Old One'],
    });

    const updatedTask = applyTaskUserRoleState(
      previousTask,
      'assignees',
      ['new-1', 'new-2'],
      ['New One', 'New Two'],
    );

    expect(updatedTask).toMatchObject({
      assignee_id: 'new-1',
      assignee_ids: ['new-1', 'new-2'],
      assignee_name: 'New One',
      assignee_names: ['New One', 'New Two'],
    });
    expect(restoreTaskUserRoleState(updatedTask, 'assignees', previousTask)).toMatchObject({
      assignee_id: 'old-1',
      assignee_ids: ['old-1'],
      assignee_name: 'Old One',
      assignee_names: ['Old One'],
    });
  });

  it('applies and restores follower state', () => {
    const previousTask = task({
      follower_ids: ['old-1'],
      follower_names: ['Old One'],
    });

    const updatedTask = applyTaskUserRoleState(
      previousTask,
      'followers',
      ['new-1'],
      ['New One'],
    );

    expect(updatedTask).toMatchObject({
      follower_ids: ['new-1'],
      follower_names: ['New One'],
    });
    expect(restoreTaskUserRoleState(updatedTask, 'followers', previousTask)).toMatchObject({
      follower_ids: ['old-1'],
      follower_names: ['Old One'],
    });
  });

  it('toggles user role ids', () => {
    expect(toggleTaskUserRoleId(['a', 'b'], 'b')).toEqual(['a']);
    expect(toggleTaskUserRoleId(['a'], 'b')).toEqual(['a', 'b']);
  });

  it('uses configured status labels before translated defaults', () => {
    const t = vi.fn((key: string) => `translated:${key}`);

    expect(
      resolveTaskDetailStatusLabel(
        'review',
        [{ id: 'status-1', name: 'Custom Review', slug: 'review', sort_order: 0 }],
        t,
      ),
    ).toBe('Custom Review');
    expect(resolveTaskDetailStatusLabel('todo', undefined, t)).toBe(
      'translated:pms.filter.status.todo',
    );
  });
});

function task(overrides = {}) {
  return {
    id: 'task-1',
    title: 'Task',
    labels: [],
    assignee_id: null,
    assignee_ids: [],
    assignee_name: null,
    assignee_names: [],
    follower_ids: [],
    follower_names: [],
    ...overrides,
  };
}
