import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const WebSearchView = lazy(() =>
  import('./views/WebSearchView').then((module) => ({
    default: module.WebSearchView,
  })),
);
const webSearchElement = lazyRoute(createElement(WebSearchView));

export const webSearchAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'web-search',
    chrome: getAppRouteChrome('web-search.root'),
    path: getAppRoutePattern('web-search.root'),
    element: webSearchElement,
  },
];
