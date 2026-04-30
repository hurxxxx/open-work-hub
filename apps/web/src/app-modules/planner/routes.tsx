import { lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const PlannerView = lazy(() =>
  import('./views/PlannerView').then((module) => ({ default: module.PlannerView })),
);

export const plannerWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'planner',
    path: '/w/:workspaceSlug/planner',
    element: lazyRoute(<PlannerView />),
  },
];
