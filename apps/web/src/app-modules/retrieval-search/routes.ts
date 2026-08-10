import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';

const RetrievalSearchView = lazy(() =>
  import('./views/RetrievalSearchView').then((module) => ({
    default: module.RetrievalSearchView,
  })),
);

export const retrievalSearchElement = lazyRoute(
  createElement(RetrievalSearchView),
);
