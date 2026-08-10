import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';

import { reorderTaskListTasks } from './pms-api';

describe('PMS task reorder', () => {
  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.restoreAllMocks();
  });

  it('uses the explicitly selected workspace and one batch request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    );

    await reorderTaskListTasks(
      'token',
      'list-1',
      {
        items: [
          {
            board_position: 1000,
            parent_id: null,
            task_id: 'task-1',
          },
        ],
      },
      'hq',
    );

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[0]).toBe(
      '/api/v1/workspaces/hq/pms/lists/list-1/tasks/reorder',
    );
    expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({ method: 'PATCH' });
  });
});
