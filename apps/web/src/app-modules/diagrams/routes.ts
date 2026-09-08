import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const DiagramsView = lazy(() =>
  import('./views/DiagramsView').then((module) => ({
    default: module.DiagramsView,
  })),
);

export const diagramsToolElement = lazyRoute(createElement(DiagramsView));

export const diagramsAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'diagrams',
    chrome: getAppRouteChrome('diagrams.root'),
    path: getAppRoutePattern('diagrams.root'),
    element: diagramsToolElement,
  },
  {
    appId: 'diagrams',
    chrome: getAppRouteChrome('diagrams.diagram'),
    path: getAppRoutePattern('diagrams.diagram'),
    element: diagramsToolElement,
  },
];
