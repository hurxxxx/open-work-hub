import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const BentoView = lazy(() =>
  import('./views/BentoView').then((module) => ({
    default: module.BentoView,
  })),
);

export const bentoWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'bento',
    chrome: getAppRouteChrome('bento.root'),
    path: getAppRoutePattern('bento.root'),
    element: lazyRoute(createElement(BentoView)),
  },
  {
    appId: 'bento',
    chrome: getAppRouteChrome('bento.presentation'),
    path: getAppRoutePattern('bento.presentation'),
    element: lazyRoute(createElement(BentoView)),
  },
];
