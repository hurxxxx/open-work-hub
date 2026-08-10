import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type {
  PmsTaskListStatus,
  PmsTaskListStatusesResponse,
} from '../api/pms-api';
import {
  useTaskListWorkflowStatusesController,
  type TaskListWorkflowStatusesClient,
  type TaskListWorkflowStatusesMessages,
} from './useTaskListWorkflowStatusesController';

function status(
  id: string,
  overrides: Partial<PmsTaskListStatus> = {},
): PmsTaskListStatus {
  return {
    id,
    category: 'active',
    color: '#3b82f6',
    name: id,
    slug: id,
    sort_order: 0,
    ...overrides,
  } as PmsTaskListStatus;
}

function statusResponse(
  overrides: Partial<PmsTaskListStatusesResponse> = {},
): PmsTaskListStatusesResponse {
  return {
    mode: 'custom',
    source: 'list',
    items: [status('todo', { category: 'not_started' })],
    ...overrides,
  };
}

function messages(): TaskListWorkflowStatusesMessages {
  return {
    createFailed: 'create failed',
    loadFailed: 'load failed',
    updateFailed: 'update failed',
    updateModeFailed: 'mode failed',
  };
}

function client(
  overrides: Partial<TaskListWorkflowStatusesClient> = {},
): TaskListWorkflowStatusesClient {
  return {
    createSpaceStatus: vi.fn().mockResolvedValue(status('space-created')),
    createTaskListStatus: vi.fn().mockResolvedValue(status('list-created')),
    listTaskListStatuses: vi.fn().mockResolvedValue(statusResponse()),
    updateSpaceStatus: vi.fn().mockResolvedValue(status('space-updated')),
    updateTaskListStatus: vi.fn().mockResolvedValue(status('list-updated')),
    updateTaskListStatusMode: vi.fn().mockResolvedValue(
      statusResponse({
        mode: 'inherit',
        source: 'space',
        items: [status('space-status', { category: 'done' })],
      }),
    ),
    ...overrides,
  };
}

function renderController(options: {
  client?: TaskListWorkflowStatusesClient;
  currentUserRole?: string | null;
  onError?: (message: string | null) => void;
  onStatusesChanged?: (statuses: PmsTaskListStatus[]) => void;
  taskListId?: string;
  teamId?: string | null;
  token?: string | null;
} = {}) {
  const testClient = options.client ?? client();
  const onError = options.onError ?? vi.fn();
  const onStatusesChanged = options.onStatusesChanged ?? vi.fn();
  const rendered = renderHook(() =>
    useTaskListWorkflowStatusesController({
      client: testClient,
      currentUserRole: options.currentUserRole ?? 'owner',
      messages: messages(),
      onError,
      onStatusesChanged,
      taskListId: options.taskListId ?? 'list-1',
      teamId: options.teamId === undefined ? 'space-1' : options.teamId,
      token: options.token === undefined ? 'token-1' : options.token,
    }),
  );
  return { ...rendered, client: testClient, onError, onStatusesChanged };
}

describe('useTaskListWorkflowStatusesController', () => {
  it('loads workflow statuses and derives edit permissions', async () => {
    const testClient = client();
    const onStatusesChanged = vi.fn();
    const { result } = renderController({ client: testClient, onStatusesChanged });

    await waitFor(() => expect(result.current.loadingStatuses).toBe(false));

    expect(testClient.listTaskListStatuses).toHaveBeenCalledWith(
      'token-1',
      'list-1',
    );
    expect(onStatusesChanged).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'todo' }),
    ]);
    expect(result.current.canEditWorkflow).toBe(true);
    expect(result.current.workflowReadOnly).toBe(false);
    expect(result.current.statusesByCategory.get('not_started')?.[0].id).toBe(
      'todo',
    );
  });

  it('updates mode and replaces source/status state', async () => {
    const testClient = client();
    const onStatusesChanged = vi.fn();
    const { result } = renderController({ client: testClient, onStatusesChanged });

    await waitFor(() => expect(result.current.loadingStatuses).toBe(false));
    await act(async () => {
      await result.current.handleStatusModeChange('inherit');
    });

    expect(testClient.updateTaskListStatusMode).toHaveBeenCalledWith(
      'token-1',
      'list-1',
      'inherit',
    );
    expect(result.current.statusMode).toBe('inherit');
    expect(result.current.statusSource).toBe('space');
    expect(result.current.workflowReadOnly).toBe(false);
    expect(onStatusesChanged).toHaveBeenLastCalledWith([
      expect.objectContaining({ id: 'space-status' }),
    ]);
  });

  it('creates list statuses and resets the draft', async () => {
    const created = status('created', { name: 'QA Ready' });
    const testClient = client({
      createTaskListStatus: vi.fn().mockResolvedValue(created),
    });
    const { result, onStatusesChanged } = renderController({
      client: testClient,
      teamId: null,
    });

    await waitFor(() => expect(result.current.loadingStatuses).toBe(false));
    act(() => {
      result.current.setNewStatusName(' QA Ready ');
      result.current.setNewStatusColor('#16a34a');
      result.current.setNewStatusCategory('done');
    });
    await act(async () => {
      await result.current.handleCreateStatus();
    });

    expect(testClient.createTaskListStatus).toHaveBeenCalledWith(
      'token-1',
      'list-1',
      {
        name: 'QA Ready',
        color: '#16a34a',
        category: 'done',
        sort_order: 1,
      },
    );
    expect(result.current.newStatusName).toBe('');
    expect(result.current.newStatusCategory).toBe('active');
    expect(onStatusesChanged).toHaveBeenLastCalledWith([
      expect.objectContaining({ id: 'todo' }),
      created,
    ]);
  });

  it('creates and updates space statuses when the source is inherited from space', async () => {
    const spaceStatus = status('space-status', { category: 'done' });
    const created = status('created-space', { name: 'Blocked' });
    const updated = status('space-status', {
      category: 'closed',
      color: '#dc2626',
      name: 'Closed',
    });
    const testClient = client({
      createSpaceStatus: vi.fn().mockResolvedValue(created),
      listTaskListStatuses: vi.fn().mockResolvedValue(
        statusResponse({
          mode: 'inherit',
          source: 'space',
          items: [spaceStatus],
        }),
      ),
      updateSpaceStatus: vi.fn().mockResolvedValue(updated),
    });
    const { result } = renderController({ client: testClient });

    await waitFor(() => expect(result.current.statusSource).toBe('space'));
    act(() => {
      result.current.setNewStatusName('Blocked');
    });
    await act(async () => {
      await result.current.handleCreateStatus();
    });

    expect(testClient.createSpaceStatus).toHaveBeenCalledWith(
      'token-1',
      'space-1',
      expect.objectContaining({ name: 'Blocked', sort_order: 1 }),
    );

    act(() => {
      result.current.startEditStatus(spaceStatus);
      result.current.setEditStatusName('Closed');
      result.current.setEditStatusColor('#dc2626');
      result.current.setEditStatusCategory('closed');
    });
    await act(async () => {
      await result.current.handleSaveEditStatus();
    });

    expect(testClient.updateSpaceStatus).toHaveBeenCalledWith(
      'token-1',
      'space-status',
      {
        name: 'Closed',
        color: '#dc2626',
        category: 'closed',
      },
    );
    expect(result.current.editingStatusId).toBeNull();
  });

  it('no-ops empty create/update commands and missing auth context', async () => {
    const testClient = client();
    const { result } = renderController({ client: testClient, token: null });

    await waitFor(() => expect(result.current.loadingStatuses).toBe(false));
    await act(async () => {
      await result.current.handleCreateStatus();
      await result.current.handleSaveEditStatus();
      await result.current.handleStatusModeChange('inherit');
    });

    expect(testClient.listTaskListStatuses).not.toHaveBeenCalled();
    expect(testClient.createTaskListStatus).not.toHaveBeenCalled();
    expect(testClient.createSpaceStatus).not.toHaveBeenCalled();
    expect(testClient.updateTaskListStatus).not.toHaveBeenCalled();
    expect(testClient.updateTaskListStatusMode).not.toHaveBeenCalled();
  });
});
