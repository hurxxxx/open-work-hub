import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type {
  ToolViewRouteDefinition,
  WorkspaceRouteDefinition,
} from '@/src/app/shell/route-types';

const AssignedToMeView = lazy(() =>
  import('./views/AssignedToMeView').then((module) => ({
    default: module.AssignedToMeView,
  })),
);
const PMSView = lazy(() =>
  import('./views/PMSView').then((module) => ({ default: module.PMSView })),
);
const TodayOverdueView = lazy(() =>
  import('./views/TodayOverdueView').then((module) => ({
    default: module.TodayOverdueView,
  })),
);

export const pmsToolElement = lazyRoute(createElement(PMSView));

export const pmsToolViewRoutes: ToolViewRouteDefinition[] = [
  {
    appId: 'pms',
    element: pmsToolElement,
    id: 'pms.main',
    match: ({ item }) => item?.appId === 'pms',
    type: 'element',
  },
];

export const pmsWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/assigned',
    element: lazyRoute(createElement(AssignedToMeView)),
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/today',
    element: lazyRoute(createElement(TodayOverdueView)),
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/lists/:taskListId',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/spaces/:spaceId',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/spaces/:spaceId/docs',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/spaces/:spaceId/docs/:docId',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/spaces/:spaceId/whiteboards',
    element: pmsToolElement,
  },
  {
    appId: 'pms',
    chrome: 'containedSurface',
    path: '/w/:workspaceSlug/pms/spaces/:spaceId/whiteboards/:whiteboardId',
    element: pmsToolElement,
  },
];
