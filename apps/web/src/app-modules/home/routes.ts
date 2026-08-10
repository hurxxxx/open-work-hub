import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const WorkspaceHomeView = lazy(() =>
  import('./views/WorkspaceHomeView/WorkspaceHomeView').then((module) => ({
    default: module.WorkspaceHomeView,
  })),
);

export const homeWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'home',
    path: '/w/:workspaceSlug/home',
    element: lazyRoute(createElement(WorkspaceHomeView)),
    subSidebar: 'hidden',
  },
];
