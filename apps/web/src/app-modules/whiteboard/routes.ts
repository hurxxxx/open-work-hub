import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const WhiteboardView = lazy(() =>
  import('./views/WhiteboardView').then((module) => ({ default: module.WhiteboardView })),
);

export const whiteboardToolElement = lazyRoute(createElement(WhiteboardView));

export const whiteboardToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'whiteboard',
    element: whiteboardToolElement,
    id: 'whiteboard.main',
    match: ({ item }) => item?.appId === 'whiteboard',
    type: 'element',
  },
];

export const whiteboardWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'whiteboard',
    path: '/w/:workspaceSlug/whiteboard',
    element: whiteboardToolElement,
  },
  {
    appId: 'whiteboard',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/whiteboard/:whiteboardId',
    element: whiteboardToolElement,
  },
];

export const whiteboardGlobalRoutes: StaticRouteDefinition[] = [
  {
    path: '/whiteboard/shared/:shareToken',
    element: whiteboardToolElement,
  },
];
