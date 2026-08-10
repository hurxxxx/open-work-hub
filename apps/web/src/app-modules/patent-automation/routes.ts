import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const PatentAutomationView = lazy(() =>
  import('./views/PatentAutomationView').then((module) => ({
    default: module.PatentAutomationView,
  })),
);

export const patentAutomationWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'patent-automation',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/patent-automation',
    element: lazyRoute(createElement(PatentAutomationView)),
  },
];
