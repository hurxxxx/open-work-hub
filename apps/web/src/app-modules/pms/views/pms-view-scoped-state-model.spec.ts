import { describe, expect, it } from 'vitest';

import type { PmsTaskListStatus, TaskFilterParams } from '../api/pms-api';
import {
  EMPTY_SELECTED_TASK_IDS,
  buildInlineTaskCreatePayload,
  createDefaultTaskFilterParamsForList,
  resolveScopedTaskFilterState,
  resolveScopedTaskSelectionState,
  selectScopedTaskFilterParams,
  selectScopedTaskSelectionIds,
  type ScopedTaskFilterState,
  type ScopedTaskSelectionState,
} from './pms-view-scoped-state-model';

function status(
  slug: string,
  category: PmsTaskListStatus['category'] = 'active',
): PmsTaskListStatus {
  return {
    id: `status-${slug}`,
    name: slug,
    slug,
    category,
    sort_order: 0,
    color: '#94a3b8',
  };
}

describe('pms view scoped state model', () => {
  it('selects scoped filters only for the active task list', () => {
    const defaultParams = createDefaultTaskFilterParamsForList();
    const params: TaskFilterParams = {
      archived_state: 'active',
      q: 'release',
    };
    const state: ScopedTaskFilterState = {
      taskListId: 'list-1',
      params,
    };

    expect(selectScopedTaskFilterParams(state, 'list-1', defaultParams)).toBe(
      params,
    );
    expect(selectScopedTaskFilterParams(state, 'list-2', defaultParams)).toBe(
      defaultParams,
    );
  });

  it('resolves direct and functional scoped filter updates', () => {
    const current: ScopedTaskFilterState = {
      taskListId: 'list-1',
      params: {
        archived_state: 'active',
        q: 'existing',
      },
    };

    expect(
      resolveScopedTaskFilterState(current, 'list-1', (params) => ({
        ...params,
        q: 'next',
      })),
    ).toEqual({
      taskListId: 'list-1',
      params: {
        archived_state: 'active',
        q: 'next',
      },
    });

    expect(
      resolveScopedTaskFilterState(current, 'list-2', (params) => ({
        ...params,
        assignee_id: 'user-1',
      })),
    ).toEqual({
      taskListId: 'list-2',
      params: {
        archived_state: 'active',
        assignee_id: 'user-1',
      },
    });
  });

  it('selects and updates scoped selected task ids', () => {
    const ids = new Set(['task-1']);
    const state: ScopedTaskSelectionState = {
      taskListId: 'list-1',
      ids,
    };

    expect(selectScopedTaskSelectionIds(state, 'list-1')).toBe(ids);
    expect(selectScopedTaskSelectionIds(state, 'list-2')).toBe(
      EMPTY_SELECTED_TASK_IDS,
    );

    expect(
      Array.from(
        resolveScopedTaskSelectionState(state, 'list-1', (current) => {
          const next = new Set(current);
          next.add('task-2');
          return next;
        }).ids,
      ),
    ).toEqual(['task-1', 'task-2']);

    expect(
      Array.from(
        resolveScopedTaskSelectionState(state, 'list-2', (current) => {
          const next = new Set(current);
          next.add('task-3');
          return next;
        }).ids,
      ),
    ).toEqual(['task-3']);
  });

  it('builds inline task create payloads with the list default status', () => {
    expect(
      buildInlineTaskCreatePayload(
        'New child',
        [
          status('draft', 'not_started'),
          status('doing', 'active'),
          status('done', 'done'),
        ],
        'parent-1',
      ),
    ).toEqual({
      title: 'New child',
      description: '',
      status: 'doing',
      priority: 'medium',
      assignee_id: null,
      milestone_id: null,
      start_date: null,
      due_date: null,
      parent_id: 'parent-1',
    });
  });
});
