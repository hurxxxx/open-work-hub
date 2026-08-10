import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const PlannerView = lazy(() =>
  import('./views/PlannerView').then((module) => ({
    default: module.PlannerView,
  })),
);

export const plannerGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: 'fullSurface',
    path: '/planner',
    element: lazyRoute(createElement(PlannerView)),
  },
];
