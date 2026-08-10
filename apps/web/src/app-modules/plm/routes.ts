import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const PlmView = lazy(() =>
  import('./views/PlmView').then((module) => ({ default: module.PlmView })),
);

export const plmWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'plm',
    path: '/w/:workspaceSlug/plm',
    element: lazyRoute(createElement(PlmView)),
  },
];
