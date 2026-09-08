import { createPmsTask } from '../../../../tests/fixtures/pms';
import { describe, expect, it } from 'vitest';

import type { PmsTask } from '../api/pms-api';
import {
  buildTaskHierarchy,
  getTaskBoardPositionUpdates,
  getTaskRoot,
  sortTasksByHierarchy,
  sortTasksByHierarchyUsingInputOrder,
} from './pms-task-hierarchy';

function task(
  id: string,
  title: string,
  boardPosition: number,
  parentId: string | null = null,
  status = 'todo',
): PmsTask {
  return createPmsTask({
    id,
    title,
    board_position: boardPosition,
    parent_id: parentId,
    status,
  });
}

describe('pms task hierarchy', () => {
  it('calculates depth, direct parent, child counts, and hierarchy order', () => {
    const root = task('root', 'Root task', 1);
    const child = task('child', 'Child task', 2, root.id);
    const grandchild = task('grandchild', 'Grandchild task', 3, child.id);
    const sibling = task('sibling', 'Sibling task', 4, root.id);

    const hierarchy = buildTaskHierarchy([grandchild, sibling, child, root]);

    expect(hierarchy.get(root.id)).toMatchObject({
      childCount: 2,
      depth: 0,
      parent: null,
      sortKey: [1],
    });
    expect(hierarchy.get(child.id)).toMatchObject({
      childCount: 1,
      depth: 1,
      parent: root,
      sortKey: [1, 2],
    });
    expect(hierarchy.get(grandchild.id)).toMatchObject({
      childCount: 0,
      depth: 2,
      parent: child,
      sortKey: [1, 2, 3],
    });

    expect(sortTasksByHierarchy([grandchild, sibling, child, root])).toEqual([
      root,
      child,
      grandchild,
      sibling,
    ]);
  });

  it('resolves subtasks to the top-level task for status grouping', () => {
    const root = task('root', 'Root task', 1, null, 'in_progress');
    const child = task('child', 'Child task', 2, root.id, 'todo');
    const grandchild = task(
      'grandchild',
      'Grandchild task',
      3,
      child.id,
      'done',
    );
    const todoRoot = task('todo-root', 'Todo root task', 4, null, 'todo');
    const tasks = [grandchild, todoRoot, child, root];
    const hierarchy = buildTaskHierarchy(tasks);

    const inProgressGroup = sortTasksByHierarchy(tasks).filter(
      (item) => getTaskRoot(item, hierarchy).status === 'in_progress',
    );
    const inProgressRootCount = inProgressGroup.filter(
      (item) => getTaskRoot(item, hierarchy).id === item.id,
    ).length;

    expect(inProgressGroup).toEqual([root, child, grandchild]);
    expect(inProgressRootCount).toBe(1);
    expect(getTaskRoot(todoRoot, hierarchy)).toBe(todoRoot);
  });

  it('preserves server date order while keeping descendants under their parent', () => {
    const firstRoot = task('first-root', 'First root', 1);
    const firstChild = task('first-child', 'First child', 2, firstRoot.id);
    const secondRoot = task('second-root', 'Second root', 3);
    const secondChild = task('second-child', 'Second child', 4, secondRoot.id);

    expect(
      sortTasksByHierarchyUsingInputOrder([
        secondChild,
        secondRoot,
        firstChild,
        firstRoot,
      ]),
    ).toEqual([secondRoot, secondChild, firstRoot, firstChild]);
  });

  it('calculates a single board position update when a reorder gap exists', () => {
    const first = task('first', 'First task', 1000);
    const second = task('second', 'Second task', 3000);
    const third = task('third', 'Third task', 5000);

    expect(
      getTaskBoardPositionUpdates({
        sourceTaskId: third.id,
        targetTaskId: second.id,
        tasks: [first, second, third],
        zone: 'before',
      }),
    ).toEqual([{ boardPosition: 2000, taskId: third.id }]);
  });

  it('rebalances siblings when adjacent board positions leave no gap', () => {
    const first = task('first', 'First task', 1);
    const second = task('second', 'Second task', 2);
    const third = task('third', 'Third task', 3);

    expect(
      getTaskBoardPositionUpdates({
        sourceTaskId: third.id,
        targetTaskId: first.id,
        tasks: [first, second, third],
        zone: 'before',
      }),
    ).toEqual([
      { boardPosition: 1000, taskId: third.id },
      { boardPosition: 2000, taskId: first.id },
      { boardPosition: 3000, taskId: second.id },
    ]);
  });

  it('rejects cross-status sibling reorder while grouped by status', () => {
    const todoRoot = task('todo-root', 'Todo root', 1000, null, 'todo');
    const activeRoot = task('active-root', 'Active root', 2000, null, 'doing');

    expect(
      getTaskBoardPositionUpdates({
        groupBy: 'status',
        sourceTaskId: todoRoot.id,
        targetTaskId: activeRoot.id,
        tasks: [todoRoot, activeRoot],
        zone: 'after',
      }),
    ).toEqual([]);
  });

  it('allows cross-status hierarchy moves while grouped by status', () => {
    const todoRoot = task('todo-root', 'Todo root', 1000, null, 'todo');
    const activeRoot = task('active-root', 'Active root', 2000, null, 'doing');

    expect(
      getTaskBoardPositionUpdates({
        groupBy: 'status',
        sourceTaskId: todoRoot.id,
        targetTaskId: activeRoot.id,
        tasks: [todoRoot, activeRoot],
        zone: 'inside',
      }),
    ).toEqual([
      { boardPosition: 1000, parentId: activeRoot.id, taskId: todoRoot.id },
    ]);
  });

  it('rejects cross-assignee sibling reorder while grouped by assignee', () => {
    const first = {
      ...task('first', 'First task', 1000),
      assignee_id: 'user-1',
      assignee_ids: ['user-1'],
    };
    const second = {
      ...task('second', 'Second task', 2000),
      assignee_id: 'user-2',
      assignee_ids: ['user-2'],
    };

    expect(
      getTaskBoardPositionUpdates({
        groupBy: 'assignee',
        sourceTaskId: first.id,
        targetTaskId: second.id,
        tasks: [first, second],
        zone: 'after',
      }),
    ).toEqual([]);
  });

  it('allows reorder within the same assignee set regardless of assignment order', () => {
    const first = {
      ...task('first', 'First task', 1000),
      assignee_id: 'user-1',
      assignee_ids: ['user-1', 'user-2'],
    };
    const second = {
      ...task('second', 'Second task', 2000),
      assignee_id: 'user-2',
      assignee_ids: ['user-2', 'user-1'],
    };

    expect(
      getTaskBoardPositionUpdates({
        groupBy: 'assignee',
        sourceTaskId: first.id,
        targetTaskId: second.id,
        tasks: [first, second],
        zone: 'after',
      }),
    ).toEqual([{ boardPosition: 3000, taskId: first.id }]);
  });

  it('moves a task under another task when dropped inside the target', () => {
    const first = task('first', 'First task', 1000);
    const second = task('second', 'Second task', 2000);
    const existingChild = task(
      'existing-child',
      'Existing child',
      1000,
      second.id,
    );

    expect(
      getTaskBoardPositionUpdates({
        sourceTaskId: first.id,
        targetTaskId: second.id,
        tasks: [first, second, existingChild],
        zone: 'inside',
      }),
    ).toEqual([{ boardPosition: 2000, parentId: second.id, taskId: first.id }]);
  });

  it('moves a child back to its parent level after the current parent', () => {
    const parent = task('parent', 'Parent task', 1000);
    const nextRoot = task('next-root', 'Next root', 2000);
    const child = task('child', 'Child task', 1000, parent.id);

    expect(
      getTaskBoardPositionUpdates({
        sourceTaskId: child.id,
        targetTaskId: parent.id,
        tasks: [parent, nextRoot, child],
        zone: 'after',
      }),
    ).toEqual([{ boardPosition: 1500, parentId: null, taskId: child.id }]);
  });

  it('rejects moves into the source task subtree', () => {
    const parent = task('parent', 'Parent task', 1000);
    const child = task('child', 'Child task', 1000, parent.id);
    const grandchild = task('grandchild', 'Grandchild task', 1000, child.id);

    expect(
      getTaskBoardPositionUpdates({
        sourceTaskId: parent.id,
        targetTaskId: grandchild.id,
        tasks: [parent, child, grandchild],
        zone: 'inside',
      }),
    ).toEqual([]);
  });
});
