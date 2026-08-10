import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

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

export type PmsToolPathOptions = {
  workspaceSlug?: string | null;
};

const PMS_TASK_LIST_TOOL_PREFIX = 'pms-list-';
const PMS_SPACE_TOOL_PREFIX = 'pms-space-';
const PMS_CREATE_TASK_PARAM = 'create';
const PMS_CREATE_TASK_TITLE_PARAM = 'title';
const PMS_CREATE_TASK_SOURCE_PARAM = 'source';
const PMS_CREATE_TASK_SOURCE_TODO_ID_PARAM = 'sourceTodoId';
const PMS_CREATE_TASK_PERSONAL_TODO_SOURCE = 'personal-todo';

export type PmsCreateTaskRequest = {
  sourceTodoId: string | null;
  title: string;
};

function appendQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

function buildPmsWorkspacePath(
  workspaceSlug: string | null | undefined,
  suffix: string,
): string {
  return workspaceSlug
    ? buildWorkspaceAppPath(workspaceSlug, 'pms', suffix)
    : '/';
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function resolvePmsWorkspaceViewRoute(
  pathname: string | null | undefined,
  requestedTab?: string | null,
): PmsViewRoute | null {
  const match = pathname?.match(/^\/w\/[^/]+\/pms(?:\/(.*))?$/);
  const routeRest = match?.[1] ?? '';
  if (!routeRest) {
    return null;
  }

  const segments = routeRest.split('/').filter(Boolean);
  if (segments[0] === 'lists' && segments[1]) {
    return { kind: 'list', taskListId: decodePathSegment(segments[1]) };
  }

  if (segments[0] !== 'spaces' || !segments[1]) {
    return null;
  }

  const spaceId = decodePathSegment(segments[1]);
  if (!segments[2]) {
    if (isPmsTaskListToolTab(requestedTab)) {
      return { kind: 'spaceTasks', spaceId, tab: requestedTab };
    }
    return { kind: 'spaceOverview', spaceId };
  }
  if (segments[2] === 'docs') {
    return {
      kind: 'spaceDocs',
      spaceId,
      docId: segments[3] ? decodePathSegment(segments[3]) : null,
    };
  }
  if (segments[2] === 'whiteboards') {
    return {
      kind: 'spaceWhiteboards',
      spaceId,
      whiteboardId: segments[3] ? decodePathSegment(segments[3]) : null,
    };
  }

  return null;
}

export function buildPmsTaskListToolId(taskListId: string): string {
  return `${PMS_TASK_LIST_TOOL_PREFIX}${taskListId}`;
}

export function buildPmsTaskListToolPath({
  settings = false,
  taskId,
  taskListId,
  tab = 'list',
  workspaceSlug,
}: {
  settings?: boolean;
  taskId?: string | null;
  taskListId: string;
  tab?: PmsTaskListToolTab;
} & PmsToolPathOptions): string {
  const params = new URLSearchParams();
  if (tab !== 'list') params.set('tab', tab);
  if (settings) params.set('settings', '1');
  if (taskId) params.set('task', taskId);
  return buildPmsWorkspacePath(
    workspaceSlug,
    appendQuery(`/lists/${encodePathSegment(taskListId)}`, params),
  );
}

export function buildPmsSpaceToolId(spaceId: string): string {
  return `${PMS_SPACE_TOOL_PREFIX}${spaceId}`;
}

export function buildPmsSpaceToolPath(
  spaceId: string,
  options: PmsToolPathOptions = {},
): string {
  return buildPmsWorkspacePath(
    options.workspaceSlug,
    `/spaces/${encodePathSegment(spaceId)}`,
  );
}

export function buildPmsSpaceTaskToolPath(
  args: {
    spaceId: string;
    tab: PmsTaskListToolTab;
  } & PmsToolPathOptions,
): string {
  const params = new URLSearchParams({ tab: args.tab });
  return buildPmsWorkspacePath(
    args.workspaceSlug,
    appendQuery(`/spaces/${encodePathSegment(args.spaceId)}`, params),
  );
}

export function buildPmsSpaceDocsToolId({
  docId,
  spaceId,
}: {
  docId?: string | null;
  spaceId: string;
}): string {
  return docId
    ? `${buildPmsSpaceToolId(spaceId)}-docs-${docId}`
    : `${buildPmsSpaceToolId(spaceId)}-docs`;
}

export function buildPmsSpaceDocsToolPath(
  args: {
    docId?: string | null;
    spaceId: string;
  } & PmsToolPathOptions,
): string {
  const suffix = args.docId
    ? `/spaces/${encodePathSegment(args.spaceId)}/docs/${encodePathSegment(args.docId)}`
    : `/spaces/${encodePathSegment(args.spaceId)}/docs`;
  return buildPmsWorkspacePath(args.workspaceSlug, suffix);
}

export function buildPmsSpaceWhiteboardsToolId({
  spaceId,
  whiteboardId,
}: {
  spaceId: string;
  whiteboardId?: string | null;
}): string {
  return whiteboardId
    ? `${buildPmsSpaceToolId(spaceId)}-whiteboards-${whiteboardId}`
    : `${buildPmsSpaceToolId(spaceId)}-whiteboards`;
}

export function buildPmsSpaceWhiteboardsToolPath(
  args: {
    spaceId: string;
    whiteboardId?: string | null;
  } & PmsToolPathOptions,
): string {
  const suffix = args.whiteboardId
    ? `/spaces/${encodePathSegment(args.spaceId)}/whiteboards/${encodePathSegment(args.whiteboardId)}`
    : `/spaces/${encodePathSegment(args.spaceId)}/whiteboards`;
  return buildPmsWorkspacePath(args.workspaceSlug, suffix);
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
  toolId,
}: {
  createTaskRequested: boolean;
  isNewTaskModalOpen: boolean;
  requestedTab?: string | null;
  routePathname?: string | null;
  toolId?: string;
}): PmsViewRoute {
  const workspaceRoute = resolvePmsWorkspaceViewRoute(
    routePathname,
    requestedTab,
  );
  if (workspaceRoute) {
    return workspaceRoute;
  }

  if (toolId === 'pms-tasks' || toolId === 'pms-tasks-assigned') {
    return { kind: 'assigned' };
  }
  if (toolId === 'pms-tasks-today') {
    return { kind: 'today' };
  }

  if (!toolId && (createTaskRequested || isNewTaskModalOpen)) {
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
