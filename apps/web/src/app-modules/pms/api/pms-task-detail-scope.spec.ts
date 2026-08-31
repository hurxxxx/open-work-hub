import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';

import {
  createChecklistItem,
  createTaskComment,
  createTaskListTask,
  deleteAttachment,
  deleteChecklistItem,
  deleteTask,
  getTaskDetail,
  listTaskActivityLogs,
  setTaskAssignees,
  setTaskFollowers,
  updateChecklistItem,
  updateTask,
  uploadAttachment,
} from './pms-api';

describe('PMS task-detail workspace boundary', () => {
  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.restoreAllMocks();
  });

  it('routes every detail read and mutation through the target workspace', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      ),
    );
    const workspaceSlug = 'target workspace';

    await getTaskDetail('token', 'task-1', workspaceSlug);
    await listTaskActivityLogs('token', 'task-1', workspaceSlug);
    await updateTask('token', 'task-1', { title: 'Updated' }, workspaceSlug);
    await setTaskAssignees('token', 'task-1', ['user-1'], workspaceSlug);
    await setTaskFollowers('token', 'task-1', ['user-2'], workspaceSlug);
    await createTaskListTask(
      'token',
      'list-1',
      {
        assignee_id: null,
        description: '',
        due_date: null,
        milestone_id: null,
        priority: 'medium',
        status: 'todo',
        title: 'Subtask',
      },
      workspaceSlug,
    );
    await deleteTask('token', 'task-2', workspaceSlug);
    await createChecklistItem(
      'token',
      'task-1',
      { text: 'Check' },
      workspaceSlug,
    );
    await updateChecklistItem(
      'token',
      'check-1',
      { completed: true },
      workspaceSlug,
    );
    await deleteChecklistItem('token', 'check-1', workspaceSlug);
    await uploadAttachment(
      'token',
      'task-1',
      new File(['content'], 'note.txt', { type: 'text/plain' }),
      workspaceSlug,
    );
    await deleteAttachment('token', 'attachment-1', workspaceSlug);
    await createTaskComment('token', 'task-1', 'Comment', null, workspaceSlug);

    expect(fetchSpy).toHaveBeenCalledTimes(13);
    for (const [input] of fetchSpy.mock.calls) {
      expect(String(input)).toMatch(
        /^\/api\/v1\/workspaces\/target%20workspace\/pms\//,
      );
    }
  });
});
