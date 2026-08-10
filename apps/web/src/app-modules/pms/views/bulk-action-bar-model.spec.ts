import { describe, expect, it } from 'vitest';

import type { PmsLabel, PmsTaskListStatus } from '../api/pms-api';
import {
  BULK_DEFAULT_STATUS_OPTIONS,
  buildBulkActionPayload,
  buildBulkLabelActions,
  buildBulkStatusOptions,
  buildBulkUpdateRequest,
  selectedTaskIdsToArray,
  type BulkUpdateAction,
} from './bulk-action-bar-model';

function t(key: string): string {
  return `translated:${key}`;
}

describe('bulk action bar model', () => {
  it('uses custom statuses when they are available', () => {
    const statuses: PmsTaskListStatus[] = [
      { slug: 'blocked', name: 'Blocked' } as PmsTaskListStatus,
      { slug: 'qa', name: 'QA' } as PmsTaskListStatus,
    ];

    expect(
      buildBulkStatusOptions({
        taskListStatuses: statuses,
        translate: () => {
          throw new Error(
            'custom statuses should not translate fallback labels',
          );
        },
      }),
    ).toEqual([
      { value: 'blocked', label: 'Blocked' },
      { value: 'qa', label: 'QA' },
    ]);
  });

  it('falls back to default status options with translated labels', () => {
    const expectedOptions = BULK_DEFAULT_STATUS_OPTIONS.map((option) => ({
      value: option.value,
      label: t(option.labelKey),
    }));

    expect(
      buildBulkStatusOptions({
        taskListStatuses: [],
        translate: t,
      }),
    ).toEqual(expectedOptions);
    expect(buildBulkStatusOptions({ translate: t })).toEqual(expectedOptions);
  });

  it('serializes selected task ids from the Set iteration order', () => {
    const selectedIds = new Set(['task-2', 'task-1']);

    const taskIds = selectedTaskIdsToArray(selectedIds);
    selectedIds.add('task-3');

    expect(taskIds).toEqual(['task-2', 'task-1']);
  });

  it('builds bulk update requests for task actions without changing payload shapes', () => {
    const taskIds = ['task-2', 'task-1'];
    const requestFor = (action: BulkUpdateAction) =>
      buildBulkUpdateRequest(taskIds, buildBulkActionPayload(action));

    expect(requestFor({ type: 'archive' })).toEqual({
      task_ids: taskIds,
      archived: true,
    });
    expect(requestFor({ type: 'restore' })).toEqual({
      task_ids: taskIds,
      archived: false,
    });
    expect(requestFor({ type: 'delete' })).toEqual({
      task_ids: taskIds,
      delete: true,
    });
    expect(requestFor({ type: 'status', status: 'in_progress' })).toEqual({
      task_ids: taskIds,
      status: 'in_progress',
    });
    expect(requestFor({ type: 'priority', priority: 'critical' })).toEqual({
      task_ids: taskIds,
      priority: 'critical',
    });
    expect(requestFor({ type: 'assignee', assigneeId: 'user-1' })).toEqual({
      task_ids: taskIds,
      assignee_id: 'user-1',
    });
    expect(requestFor({ type: 'assignee', assigneeId: null })).toEqual({
      task_ids: taskIds,
      assignee_id: null,
    });
  });

  it('builds label add and remove actions with the existing payload shapes', () => {
    const labels: PmsLabel[] = [
      { id: 'label-1', name: 'Bug', color: '#ef4444' } as PmsLabel,
    ];

    const actions = buildBulkLabelActions(labels);

    expect(actions.add).toEqual([
      {
        key: 'add-label-1',
        label: labels[0],
        payload: { add_label_ids: ['label-1'] },
      },
    ]);
    expect(actions.remove).toEqual([
      {
        key: 'rm-label-1',
        label: labels[0],
        payload: { remove_label_ids: ['label-1'] },
      },
    ]);
  });

  it('builds label action payloads for direct add and remove actions', () => {
    expect(
      buildBulkUpdateRequest(
        ['task-1'],
        buildBulkActionPayload({ type: 'add-label', labelId: 'label-1' }),
      ),
    ).toEqual({
      task_ids: ['task-1'],
      add_label_ids: ['label-1'],
    });
    expect(
      buildBulkUpdateRequest(
        ['task-1'],
        buildBulkActionPayload({ type: 'remove-label', labelId: 'label-1' }),
      ),
    ).toEqual({
      task_ids: ['task-1'],
      remove_label_ids: ['label-1'],
    });
  });
});
