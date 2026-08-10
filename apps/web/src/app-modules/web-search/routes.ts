import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const WebSearchView = lazy(() =>
  import('./views/WebSearchView').then((module) => ({
    default: module.WebSearchView,
  })),
);
const webSearchElement = lazyRoute(createElement(WebSearchView));

export const webSearchWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'web-search',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/web-search',
    subSidebar: 'hidden',
    element: webSearchElement,
  },
];
