import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import {
  HEALTH_CHECKUP_ROUTE,
  MANAGEMENT_TASKS_APP_ID,
} from './manifest';

const HealthCheckupView = lazy(() =>
  import('./views/HealthCheckupView').then((module) => ({
    default: module.HealthCheckupView,
  })),
);

export const managementTasksWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: MANAGEMENT_TASKS_APP_ID,
    chrome: 'fullSurface',
    path: HEALTH_CHECKUP_ROUTE,
    subSidebar: 'hidden',
    element: lazyRoute(createElement(HealthCheckupView)),
  },
];
