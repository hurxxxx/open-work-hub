import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';

const PatentPriorArtView = lazy(() =>
  import('./views/PatentPriorArtView').then((module) => ({
    default: module.PatentPriorArtView,
  })),
);

export const patentPriorArtElement = lazyRoute(
  createElement(PatentPriorArtView),
);
