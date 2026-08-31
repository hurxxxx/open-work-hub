import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';

const PlannerView = lazy(() =>
  import('./views/PlannerView').then((module) => ({
    default: module.PlannerView,
  })),
);

export const plannerGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('planner.root'),
    path: getAppRoutePattern('planner.root'),
    element: lazyRoute(createElement(PlannerView)),
  },
];
