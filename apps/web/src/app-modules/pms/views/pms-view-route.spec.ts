import { describe, expect, it } from 'vitest';

import {
  buildPmsSpaceDocsToolPath,
  buildPmsSpaceTaskToolPath,
  buildPmsSpaceToolPath,
  buildPmsSpaceWhiteboardsToolPath,
  buildPmsCreateTaskSearch,
  buildPmsTaskListToolPath,
  clearPmsCreateTaskSearchParams,
  readPmsCreateTaskRequest,
  resolvePmsViewRoute,
} from './pms-view-route';

describe('PMS view route resolver', () => {
  it('builds PMS workspace paths from route inputs', () => {
    expect(
      buildPmsTaskListToolPath({
        taskListId: 'list-1',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/lists/list-1');
    expect(
      buildPmsTaskListToolPath({
        taskListId: 'list-1',
        tab: 'board',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/lists/list-1?tab=board');
    expect(
      buildPmsTaskListToolPath({
        settings: true,
        taskListId: 'list-1',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/lists/list-1?settings=1');
    expect(
      buildPmsTaskListToolPath({
        taskId: 'task-1',
        taskListId: 'list-1',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/lists/list-1?task=task-1');
    expect(buildPmsSpaceToolPath('space-1', { workspaceSlug: 'hq' })).toBe(
      '/apps/pms/workspaces/hq/spaces/space-1',
    );
    expect(
      buildPmsSpaceDocsToolPath({
        docId: 'def-456',
        spaceId: 'abc-123',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/spaces/abc-123/docs/def-456');
    expect(
      buildPmsSpaceWhiteboardsToolPath({
        spaceId: 'abc-123',
        whiteboardId: 'def-456',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/spaces/abc-123/whiteboards/def-456');
  });

  it('encodes PMS workspace path segments', () => {
    expect(
      buildPmsTaskListToolPath({
        taskListId: 'list/1',
        workspaceSlug: '기술연구소',
      }),
    ).toBe(
      '/apps/pms/workspaces/%EA%B8%B0%EC%88%A0%EC%97%B0%EA%B5%AC%EC%86%8C/lists/list%2F1',
    );
    expect(
      buildPmsSpaceDocsToolPath({
        docId: 'doc/1',
        spaceId: 'space/1',
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/spaces/space%2F1/docs/doc%2F1');
  });

  it('serializes list view query state on workspace paths', () => {
    expect(
      buildPmsTaskListToolPath({
        taskListId: 'list-1',
        tab: 'board',
        settings: true,
        workspaceSlug: 'hq',
      }),
    ).toBe('/apps/pms/workspaces/hq/lists/list-1?settings=1&tab=board');
  });

  it.each(['list', 'board', 'calendar', 'gantt', 'table'] as const)(
    'builds and resolves the %s space task view without selecting a list',
    (tab) => {
      expect(
        buildPmsSpaceTaskToolPath({
          spaceId: 'space-1',
          tab,
          workspaceSlug: 'hq',
        }),
      ).toBe(`/apps/pms/workspaces/hq/spaces/space-1?tab=${tab}`);

      expect(
        resolvePmsViewRoute({
          routePathname: '/apps/pms/workspaces/hq/spaces/space-1',
          requestedTab: tab,
          createTaskRequested: false,
          isNewTaskModalOpen: false,
        }),
      ).toEqual({ kind: 'spaceTasks', spaceId: 'space-1', tab });
    },
  );

  it('fails closed to the space overview for an unknown space tab', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/spaces/space-1',
        requestedTab: 'unknown',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'spaceOverview', spaceId: 'space-1' });
  });

  it('resolves assigned and today routes', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/assigned',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'assigned' });
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/assigned',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'assigned' });
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/today',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'today' });
  });

  it('resolves task list routes', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/lists/list-1',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'list', taskListId: 'list-1' });
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/lists/list%2F1',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'list', taskListId: 'list/1' });
  });

  it('resolves space docs routes with optional document ids', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/spaces/abc-123/docs',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'spaceDocs', spaceId: 'abc-123', docId: null });
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/spaces/abc-123/docs/def-456',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({
      kind: 'spaceDocs',
      spaceId: 'abc-123',
      docId: 'def-456',
    });
  });

  it('resolves space whiteboard routes with optional whiteboard ids', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/spaces/abc-123/whiteboards',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({
      kind: 'spaceWhiteboards',
      spaceId: 'abc-123',
      whiteboardId: null,
    });
    expect(
      resolvePmsViewRoute({
        routePathname:
          '/apps/pms/workspaces/hq/spaces/abc-123/whiteboards/def-456',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({
      kind: 'spaceWhiteboards',
      spaceId: 'abc-123',
      whiteboardId: 'def-456',
    });
  });

  it('resolves space overview before falling through to root overview', () => {
    expect(
      resolvePmsViewRoute({
        routePathname: '/apps/pms/workspaces/hq/spaces/space-1',
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'spaceOverview', spaceId: 'space-1' });
    expect(
      resolvePmsViewRoute({
        createTaskRequested: false,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'overview' });
  });

  it('keeps empty-root create task state out of the overview route', () => {
    expect(
      resolvePmsViewRoute({
        createTaskRequested: true,
        isNewTaskModalOpen: false,
      }),
    ).toEqual({ kind: 'taskCreateFallback' });
    expect(
      resolvePmsViewRoute({
        createTaskRequested: false,
        isNewTaskModalOpen: true,
      }),
    ).toEqual({ kind: 'taskCreateFallback' });
  });

  it('serializes and clears PMS create-task query state', () => {
    const search = buildPmsCreateTaskSearch({
      sourceTodoId: 'todo-1',
      title: '  Follow up  ',
    });

    expect(search).toBe(
      '?create=1&title=Follow+up&source=personal-todo&sourceTodoId=todo-1',
    );
    expect(readPmsCreateTaskRequest(new URLSearchParams(search))).toEqual({
      sourceTodoId: 'todo-1',
      title: 'Follow up',
    });

    const cleared = clearPmsCreateTaskSearchParams(
      new URLSearchParams(`${search}&tab=board`),
    );

    expect(cleared.toString()).toBe('tab=board');
  });
});
