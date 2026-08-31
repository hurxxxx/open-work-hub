import { createElement, lazy } from 'react';
import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';

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
    chrome: getAppRouteChrome('web-search.root'),
    path: getAppRoutePattern('web-search.root'),
    element: webSearchElement,
  },
];
