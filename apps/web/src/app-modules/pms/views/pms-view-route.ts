import {
  buildAppHref,
  matchAppRoute,
} from '@open-work-hub/contracts/app-routes';

export type PmsViewRoute =
  | { kind: 'assigned' }
  | { kind: 'today' }
  | { kind: 'list'; taskListId: string }
  | { kind: 'spaceTasks'; spaceId: string; tab: PmsTaskListToolTab }
  | { kind: 'spaceDocs'; spaceId: string; docId: string | null }
  | {
      kind: 'spaceWhiteboards';
      spaceId: string;
      whiteboardId: string | null;
    }
  | { kind: 'spaceOverview'; spaceId: string }
  | { kind: 'overview' }
  | { kind: 'taskCreateFallback' };

export type PmsTaskListToolTab =
  | 'list'
  | 'board'
  | 'calendar'
  | 'gantt'
  | 'table';

export type PmsToolPathOptions = Record<string, never>;

const PMS_CREATE_TASK_PARAM = 'create';
const PMS_CREATE_TASK_TITLE_PARAM = 'title';
const PMS_CREATE_TASK_SOURCE_PARAM = 'source';
const PMS_CREATE_TASK_SOURCE_TODO_ID_PARAM = 'sourceTodoId';
const PMS_CREATE_TASK_PERSONAL_TODO_SOURCE = 'personal-todo';

export type PmsCreateTaskRequest = {
  sourceTodoId: string | null;
  title: string;
};

function matchPmsAppRoute(
  pathname: string | null | undefined,
  requestedTab?: string | null,
): PmsViewRoute | null {
  if (!pathname) return null;
  const route = matchAppRoute(pathname);
  if (!route || route.appId !== 'pms') return null;
  switch (route.routeId) {
    case 'pms.assigned':
      return { kind: 'assigned' };
    case 'pms.today':
      return { kind: 'today' };
    case 'pms.list':
      return { kind: 'list', taskListId: route.pathParams.taskListId };
    case 'pms.space': {
      const spaceId = route.pathParams.spaceId;
      return isPmsTaskListToolTab(requestedTab)
        ? { kind: 'spaceTasks', spaceId, tab: requestedTab }
        : { kind: 'spaceOverview', spaceId };
    }
    case 'pms.space-docs':
      return {
        kind: 'spaceDocs',
        spaceId: route.pathParams.spaceId,
        docId: null,
      };
    case 'pms.space-doc':
      return {
        kind: 'spaceDocs',
        spaceId: route.pathParams.spaceId,
        docId: route.pathParams.docId,
      };
    case 'pms.space-whiteboards':
      return {
        kind: 'spaceWhiteboards',
        spaceId: route.pathParams.spaceId,
        whiteboardId: null,
      };
    case 'pms.space-whiteboard':
      return {
        kind: 'spaceWhiteboards',
        spaceId: route.pathParams.spaceId,
        whiteboardId: route.pathParams.whiteboardId,
      };
    default:
      return null;
  }
}

export function buildPmsTaskListToolPath({
  settings = false,
  taskId,
  taskListId,
  tab = 'list',
}: {
  settings?: boolean;
  taskId?: string | null;
  taskListId: string;
  tab?: PmsTaskListToolTab;
}): string {
  const params = new URLSearchParams();
  if (tab !== 'list') params.set('tab', tab);
  if (settings) params.set('settings', '1');
  if (taskId) params.set('task', taskId);
  return buildAppHref({
    routeId: 'pms.list',
    pathParams: { taskListId },
    queryParams: Object.fromEntries(params),
  });
}

export function buildPmsSpaceToolPath(
  spaceId: string,
  options: PmsToolPathOptions = {},
): string {
  return buildAppHref({
    routeId: 'pms.space',
    pathParams: { spaceId },
  });
}

export function buildPmsSpaceTaskToolPath(args: {
  spaceId: string;
  tab: PmsTaskListToolTab;
}): string {
  const params = new URLSearchParams({ tab: args.tab });
  return buildAppHref({
    routeId: 'pms.space',
    pathParams: { spaceId: args.spaceId },
    queryParams: Object.fromEntries(params),
  });
}

export function buildPmsSpaceDocsToolPath(args: {
  docId?: string | null;
  spaceId: string;
}): string {
  return args.docId
    ? buildAppHref({
        routeId: 'pms.space-doc',
        pathParams: { spaceId: args.spaceId, docId: args.docId },
      })
    : buildAppHref({
        routeId: 'pms.space-docs',
        pathParams: { spaceId: args.spaceId },
      });
}

export function buildPmsSpaceWhiteboardsToolPath(args: {
  spaceId: string;
  whiteboardId?: string | null;
}): string {
  return args.whiteboardId
    ? buildAppHref({
        routeId: 'pms.space-whiteboard',
        pathParams: {
          spaceId: args.spaceId,
          whiteboardId: args.whiteboardId,
        },
      })
    : buildAppHref({
        routeId: 'pms.space-whiteboards',
        pathParams: { spaceId: args.spaceId },
      });
}

export function buildPmsCreateTaskSearch({
  sourceTodoId,
  title,
}: {
  sourceTodoId?: string | null;
  title?: string | null;
} = {}): string {
  const params = new URLSearchParams({ [PMS_CREATE_TASK_PARAM]: '1' });
  const trimmedTitle = title?.trim();
  if (trimmedTitle) {
    params.set(PMS_CREATE_TASK_TITLE_PARAM, trimmedTitle);
  }
  if (sourceTodoId) {
    params.set(
      PMS_CREATE_TASK_SOURCE_PARAM,
      PMS_CREATE_TASK_PERSONAL_TODO_SOURCE,
    );
    params.set(PMS_CREATE_TASK_SOURCE_TODO_ID_PARAM, sourceTodoId);
  }
  return `?${params.toString()}`;
}

export function readPmsCreateTaskRequest(
  searchParams: URLSearchParams,
): PmsCreateTaskRequest {
  return {
    sourceTodoId:
      searchParams.get(PMS_CREATE_TASK_SOURCE_PARAM) ===
      PMS_CREATE_TASK_PERSONAL_TODO_SOURCE
        ? searchParams.get(PMS_CREATE_TASK_SOURCE_TODO_ID_PARAM)
        : null,
    title: searchParams.get(PMS_CREATE_TASK_TITLE_PARAM)?.trim() ?? '',
  };
}

export function clearPmsCreateTaskSearchParams(
  searchParams: URLSearchParams,
): URLSearchParams {
  const nextParams = new URLSearchParams(searchParams);
  nextParams.delete(PMS_CREATE_TASK_PARAM);
  nextParams.delete(PMS_CREATE_TASK_TITLE_PARAM);
  nextParams.delete(PMS_CREATE_TASK_SOURCE_PARAM);
  nextParams.delete(PMS_CREATE_TASK_SOURCE_TODO_ID_PARAM);
  return nextParams;
}

export function resolvePmsViewRoute({
  createTaskRequested,
  isNewTaskModalOpen,
  requestedTab,
  routePathname,
}: {
  createTaskRequested: boolean;
  isNewTaskModalOpen: boolean;
  requestedTab?: string | null;
  routePathname?: string | null;
}): PmsViewRoute {
  const appRoute = matchPmsAppRoute(routePathname, requestedTab);
  if (appRoute) {
    return appRoute;
  }

  if (createTaskRequested || isNewTaskModalOpen) {
    return { kind: 'taskCreateFallback' };
  }

  return { kind: 'overview' };
}

function isPmsTaskListToolTab(
  value: string | null | undefined,
): value is PmsTaskListToolTab {
  return (
    value === 'list' ||
    value === 'board' ||
    value === 'calendar' ||
    value === 'gantt' ||
    value === 'table'
  );
}
