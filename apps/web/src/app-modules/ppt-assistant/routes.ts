import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';

const PptGeneratorView = lazy(() =>
  import('./views/PptGeneratorView').then((module) => ({
    default: module.PptGeneratorView,
  })),
);
const PptHistoryView = lazy(() =>
  import('./views/PptHistoryView').then((module) => ({
    default: module.PptHistoryView,
  })),
);

export function createPptAssistantRouteElements(appId: string) {
  return {
    historyElement: lazyRoute(createElement(PptHistoryView, { appId })),
    toolElement: lazyRoute(createElement(PptGeneratorView, { appId })),
  } as const;
}
