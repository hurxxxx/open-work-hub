import { createElement, lazy } from 'react';

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
    path: '/w/:workspaceSlug/bento',
    element: lazyRoute(createElement(BentoView)),
  },
  {
    appId: 'bento',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/bento/:documentId',
    element: lazyRoute(createElement(BentoView)),
  },
];
