import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

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
    chrome: getAppRouteChrome('home.root'),
    path: getAppRoutePattern('home.root'),
    element: lazyRoute(createElement(WorkspaceHomeView)),
    subSidebar: 'hidden',
  },
];
