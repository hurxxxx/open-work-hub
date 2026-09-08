import {
  getAppRouteChrome,
  getAppRoutePattern,
} from '@open-work-hub/contracts/app-routes';
import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { AppRouteDefinition } from '@/src/app/shell/route-types';

const HomeView = lazy(() =>
  import('./views/HomeView/HomeView').then((module) => ({
    default: module.HomeView,
  })),
);

export const homeAppRoutes: AppRouteDefinition[] = [
  {
    appId: 'home',
    chrome: getAppRouteChrome('home.root'),
    path: getAppRoutePattern('home.root'),
    element: lazyRoute(createElement(HomeView)),
    subSidebar: 'hidden',
  },
];
