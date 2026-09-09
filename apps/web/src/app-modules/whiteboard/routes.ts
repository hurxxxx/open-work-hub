import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { StaticRouteDefinition } from '@/src/app/shell/navigation-types';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const WhiteboardView = lazy(() =>
  import('./views/WhiteboardView').then((module) => ({
    default: module.WhiteboardView,
  })),
);

export const whiteboardToolElement = lazyRoute(createElement(WhiteboardView));

export const whiteboardAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'whiteboard',
    chrome: getAppRouteChrome('whiteboard.root'),
    path: getAppRoutePattern('whiteboard.root'),
    element: whiteboardToolElement,
  },
  {
    appId: 'whiteboard',
    chrome: getAppRouteChrome('whiteboard.board'),
    path: getAppRoutePattern('whiteboard.board'),
    element: whiteboardToolElement,
  },
];

export const whiteboardGlobalRoutes: StaticRouteDefinition[] = [
  {
    chrome: getAppRouteChrome('whiteboard.shared'),
    path: getAppRoutePattern('whiteboard.shared'),
    element: whiteboardToolElement,
  },
];
