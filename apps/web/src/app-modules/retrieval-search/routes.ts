import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const RetrievalSearchView = lazy(() =>
  import('./views/RetrievalSearchView').then((module) => ({
    default: module.RetrievalSearchView,
  })),
);

export const retrievalSearchElement = lazyRoute(
  createElement(RetrievalSearchView),
);

export const retrievalSearchAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'retrieval-search',
    chrome: getAppRouteChrome('retrieval-search.root'),
    path: getAppRoutePattern('retrieval-search.root'),
    element: retrievalSearchElement,
  },
];
